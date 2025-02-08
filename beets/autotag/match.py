# This file is part of beets.
# Copyright 2016, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Matches existing metadata with canonical information to identify
releases and tracks.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterable, Sequence
from enum import IntEnum
from functools import cache
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar, cast

import lap
import numpy as np

from beets import config, logging, plugins
from beets.autotag import (
    AlbumInfo,
    AlbumMatch,
    Distance,
    TrackInfo,
    TrackMatch,
    hooks,
)
from beets.util import plurality

if TYPE_CHECKING:
    from beets.library import Item

# Artist signals that indicate "various artists". These are used at the
# album level to determine whether a given release is likely a VA
# release and also on the track level to to remove the penalty for
# differing artists.
VA_ARTISTS = ("", "various artists", "various", "va", "unknown")

# Global logger.
log = logging.getLogger("beets")


# Recommendation enumeration.


class Recommendation(IntEnum):
    """Indicates a qualitative suggestion to the user about what should
    be done with a given match.
    """

    none = 0
    low = 1
    medium = 2
    strong = 3


# A structure for holding a set of possible matches to choose between. This
# consists of a list of possible candidates (i.e., AlbumInfo or TrackInfo
# objects) and a recommendation value.


class Proposal(NamedTuple):
    candidates: Sequence[AlbumMatch | TrackMatch]
    recommendation: Recommendation


# Primary matching functionality.


def current_metadata(
    items: Iterable[Item],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract the likely current metadata for an album given a list of its
    items. Return two dictionaries:
     - The most common value for each field.
     - Whether each field's value was unanimous (values are booleans).
    """
    assert items  # Must be nonempty.

    likelies = {}
    consensus = {}
    fields = [
        "artist",
        "album",
        "albumartist",
        "year",
        "disctotal",
        "mb_albumid",
        "label",
        "barcode",
        "catalognum",
        "country",
        "media",
        "albumdisambig",
    ]
    for field in fields:
        values = [item[field] for item in items if item]
        likelies[field], freq = plurality(values)
        consensus[field] = freq == len(values)

    # If there's an album artist consensus, use this for the artist.
    if consensus["albumartist"] and likelies["albumartist"]:
        likelies["artist"] = likelies["albumartist"]

    return likelies, consensus


def assign_items(
    items: Sequence[Item],
    tracks: Sequence[TrackInfo],
) -> tuple[dict[Item, TrackInfo], list[Item], list[TrackInfo]]:
    """Given a list of Items and a list of TrackInfo objects, find the
    best mapping between them. Returns a mapping from Items to TrackInfo
    objects, a set of extra Items, and a set of extra TrackInfo
    objects. These "extra" objects occur when there is an unequal number
    of objects of the two types.
    """
    log.debug("Computing track assignment...")
    # Construct the cost matrix.
    costs = [[float(track_distance(i, t)) for t in tracks] for i in items]
    # Assign items to tracks
    _, _, assigned_item_idxs = lap.lapjv(np.array(costs), extend_cost=True)
    log.debug("...done.")

    # Each item in `assigned_item_idxs` list corresponds to a track in the
    # `tracks` list. Each value is either an index into the assigned item in
    # `items` list, or -1 if that track has no match.
    mapping = {
        items[iidx]: t
        for iidx, t in zip(assigned_item_idxs, tracks)
        if iidx != -1
    }
    extra_items = list(set(items) - mapping.keys())
    extra_items.sort(key=lambda i: (i.disc, i.track, i.title))
    extra_tracks = list(set(tracks) - set(mapping.values()))
    extra_tracks.sort(key=lambda t: (t.index, t.title))
    return mapping, extra_items, extra_tracks


def track_index_changed(item: Item, track_info: TrackInfo) -> bool:
    """Returns True if the item and track info index is different. Tolerates
    per disc and per release numbering.
    """
    return item.track not in (track_info.medium_index, track_info.index)


@cache
def get_track_length_grace() -> float:
    """Get cached grace period for track length matching."""
    return config["match"]["track_length_grace"].as_number()


@cache
def get_track_length_max() -> float:
    """Get cached maximum track length for track length matching."""
    return config["match"]["track_length_max"].as_number()


def track_distance(
    item: Item,
    track_info: TrackInfo,
    incl_artist: bool = False,
) -> Distance:
    """Determines the significance of a track metadata change. Returns a
    Distance object. `incl_artist` indicates that a distance component should
    be included for the track artist (i.e., for various-artist releases).

    ``track_length_grace`` and ``track_length_max`` configuration options are
    cached because this function is called many times during the matching
    process and their access comes with a performance overhead.
    """
    dist = hooks.Distance()

    # Length.
    if info_length := track_info.length:
        diff = abs(item.length - info_length) - get_track_length_grace()
        dist.add_ratio("track_length", diff, get_track_length_max())

    # Title.
    dist.add_string("track_title", item.title, track_info.title)

    # Artist. Only check if there is actually an artist in the track data.
    if (
        incl_artist
        and track_info.artist
        and item.artist.lower() not in VA_ARTISTS
    ):
        dist.add_string("track_artist", item.artist, track_info.artist)

    # Track index.
    if track_info.index and item.track:
        dist.add_expr("track_index", track_index_changed(item, track_info))

    # Track ID.
    if item.mb_trackid:
        dist.add_expr("track_id", item.mb_trackid != track_info.track_id)

    # Penalize mismatching disc numbers.
    if track_info.medium and item.disc:
        dist.add_expr("medium", item.disc != track_info.medium)

    # Plugins.
    dist.update(plugins.track_distance(item, track_info))

    return dist


def distance(
    items: Sequence[Item],
    album_info: AlbumInfo,
    mapping: dict[Item, TrackInfo],
) -> Distance:
    """Determines how "significant" an album metadata change would be.
    Returns a Distance object. `album_info` is an AlbumInfo object
    reflecting the album to be compared. `items` is a sequence of all
    Item objects that will be matched (order is not important).
    `mapping` is a dictionary mapping Items to TrackInfo objects; the
    keys are a subset of `items` and the values are a subset of
    `album_info.tracks`.
    """
    likelies, _ = current_metadata(items)

    dist = hooks.Distance()

    # Artist, if not various.
    if not album_info.va:
        dist.add_string("artist", likelies["artist"], album_info.artist)

    # Album.
    dist.add_string("album", likelies["album"], album_info.album)

    # Current or preferred media.
    if album_info.media:
        # Preferred media options.
        patterns = config["match"]["preferred"]["media"].as_str_seq()
        patterns = cast(Sequence[str], patterns)
        options = [re.compile(r"(\d+x)?(%s)" % pat, re.I) for pat in patterns]
        if options:
            dist.add_priority("media", album_info.media, options)
        # Current media.
        elif likelies["media"]:
            dist.add_equality("media", album_info.media, likelies["media"])

    # Mediums.
    if likelies["disctotal"] and album_info.mediums:
        dist.add_number("mediums", likelies["disctotal"], album_info.mediums)

    # Prefer earliest release.
    if album_info.year and config["match"]["preferred"]["original_year"]:
        # Assume 1889 (earliest first gramophone discs) if we don't know the
        # original year.
        original = album_info.original_year or 1889
        diff = abs(album_info.year - original)
        diff_max = abs(datetime.date.today().year - original)
        dist.add_ratio("year", diff, diff_max)
    # Year.
    elif likelies["year"] and album_info.year:
        if likelies["year"] in (album_info.year, album_info.original_year):
            # No penalty for matching release or original year.
            dist.add("year", 0.0)
        elif album_info.original_year:
            # Prefer matchest closest to the release year.
            diff = abs(likelies["year"] - album_info.year)
            diff_max = abs(
                datetime.date.today().year - album_info.original_year
            )
            dist.add_ratio("year", diff, diff_max)
        else:
            # Full penalty when there is no original year.
            dist.add("year", 1.0)

    # Preferred countries.
    patterns = config["match"]["preferred"]["countries"].as_str_seq()
    patterns = cast(Sequence[str], patterns)
    options = [re.compile(pat, re.I) for pat in patterns]
    if album_info.country and options:
        dist.add_priority("country", album_info.country, options)
    # Country.
    elif likelies["country"] and album_info.country:
        dist.add_string("country", likelies["country"], album_info.country)

    # Label.
    if likelies["label"] and album_info.label:
        dist.add_string("label", likelies["label"], album_info.label)

    # Catalog number.
    if likelies["catalognum"] and album_info.catalognum:
        dist.add_string(
            "catalognum", likelies["catalognum"], album_info.catalognum
        )

    # Disambiguation.
    if likelies["albumdisambig"] and album_info.albumdisambig:
        dist.add_string(
            "albumdisambig", likelies["albumdisambig"], album_info.albumdisambig
        )

    # Album ID.
    if likelies["mb_albumid"]:
        dist.add_equality(
            "album_id", likelies["mb_albumid"], album_info.album_id
        )

    # Tracks.
    dist.tracks = {}
    for item, track in mapping.items():
        dist.tracks[track] = track_distance(item, track, album_info.va)
        dist.add("tracks", dist.tracks[track].distance)

    # Missing tracks.
    for _ in range(len(album_info.tracks) - len(mapping)):
        dist.add("missing_tracks", 1.0)

    # Unmatched tracks.
    for _ in range(len(items) - len(mapping)):
        dist.add("unmatched_tracks", 1.0)

    # Plugins.
    dist.update(plugins.album_distance(items, album_info, mapping))

    return dist


def match_by_id(items: Iterable[Item]):
    """If the items are tagged with a MusicBrainz album ID, returns an
    AlbumInfo object for the corresponding album. Otherwise, returns
    None.
    """
    albumids = (item.mb_albumid for item in items if item.mb_albumid)

    # Did any of the items have an MB album ID?
    try:
        first = next(albumids)
    except StopIteration:
        log.debug("No album ID found.")
        return None

    # Is there a consensus on the MB album ID?
    for other in albumids:
        if other != first:
            log.debug("No album ID consensus.")
            return None
    # If all album IDs are equal, look up the album.
    log.debug("Searching for discovered album ID: {0}", first)
    return hooks.album_for_mbid(first)


def _recommendation(
    results: Sequence[AlbumMatch | TrackMatch],
) -> Recommendation:
    """Given a sorted list of AlbumMatch or TrackMatch objects, return a
    recommendation based on the results' distances.

    If the recommendation is higher than the configured maximum for
    an applied penalty, the recommendation will be downgraded to the
    configured maximum for that penalty.
    """
    if not results:
        # No candidates: no recommendation.
        return Recommendation.none

    # Basic distance thresholding.
    min_dist = results[0].distance
    if min_dist < config["match"]["strong_rec_thresh"].as_number():
        # Strong recommendation level.
        rec = Recommendation.strong
    elif min_dist <= config["match"]["medium_rec_thresh"].as_number():
        # Medium recommendation level.
        rec = Recommendation.medium
    elif len(results) == 1:
        # Only a single candidate.
        rec = Recommendation.low
    elif (
        results[1].distance - min_dist
        >= config["match"]["rec_gap_thresh"].as_number()
    ):
        # Gap between first two candidates is large.
        rec = Recommendation.low
    else:
        # No conclusion. Return immediately. Can't be downgraded any further.
        return Recommendation.none

    # Downgrade to the max rec if it is lower than the current rec for an
    # applied penalty.
    keys = set(min_dist.keys())
    if isinstance(results[0], hooks.AlbumMatch):
        for track_dist in min_dist.tracks.values():
            keys.update(list(track_dist.keys()))
    max_rec_view = config["match"]["max_rec"]
    for key in keys:
        if key in list(max_rec_view.keys()):
            max_rec = max_rec_view[key].as_choice(
                {
                    "strong": Recommendation.strong,
                    "medium": Recommendation.medium,
                    "low": Recommendation.low,
                    "none": Recommendation.none,
                }
            )
            rec = min(rec, max_rec)

    return rec


AnyMatch = TypeVar("AnyMatch", TrackMatch, AlbumMatch)


def _sort_candidates(candidates: Iterable[AnyMatch]) -> Sequence[AnyMatch]:
    """Sort candidates by distance."""
    return sorted(candidates, key=lambda match: match.distance)


def _add_candidate(
    items: Sequence[Item],
    results: dict[Any, AlbumMatch],
    info: AlbumInfo,
):
    """Given a candidate AlbumInfo object, attempt to add the candidate
    to the output dictionary of AlbumMatch objects. This involves
    checking the track count, ordering the items, checking for
    duplicates, and calculating the distance.
    """
    log.debug(
        "Candidate: {0} - {1} ({2})", info.artist, info.album, info.album_id
    )

    # Discard albums with zero tracks.
    if not info.tracks:
        log.debug("No tracks.")
        return

    # Prevent duplicates.
    if info.album_id and info.album_id in results:
        log.debug("Duplicate.")
        return

    # Discard matches without required tags.
    for req_tag in cast(
        Sequence[str], config["match"]["required"].as_str_seq()
    ):
        if getattr(info, req_tag) is None:
            log.debug("Ignored. Missing required tag: {0}", req_tag)
            return

    # Find mapping between the items and the track info.
    mapping, extra_items, extra_tracks = assign_items(items, info.tracks)

    # Get the change distance.
    dist = distance(items, info, mapping)

    # Skip matches with ignored penalties.
    penalties = [key for key, _ in dist]
    ignored = cast(Sequence[str], config["match"]["ignored"].as_str_seq())
    for penalty in ignored:
        if penalty in penalties:
            log.debug("Ignored. Penalty: {0}", penalty)
            return

    log.debug("Success. Distance: {0}", dist)
    results[info.album_id] = hooks.AlbumMatch(
        dist, info, mapping, extra_items, extra_tracks
    )


def tag_album(
    items,
    search_artist: str | None = None,
    search_album: str | None = None,
    search_ids: list[str] = [],
) -> tuple[str, str, Proposal]:
    """Return a tuple of the current artist name, the current album
    name, and a `Proposal` containing `AlbumMatch` candidates.

    The artist and album are the most common values of these fields
    among `items`.

    The `AlbumMatch` objects are generated by searching the metadata
    backends. By default, the metadata of the items is used for the
    search. This can be customized by setting the parameters.
    `search_ids` is a list of metadata backend IDs: if specified,
    it will restrict the candidates to those IDs, ignoring
    `search_artist` and `search album`. The `mapping` field of the
    album has the matched `items` as keys.

    The recommendation is calculated from the match quality of the
    candidates.
    """
    # Get current metadata.
    likelies, consensus = current_metadata(items)
    cur_artist = cast(str, likelies["artist"])
    cur_album = cast(str, likelies["album"])
    log.debug("Tagging {0} - {1}", cur_artist, cur_album)

    # The output result, keys are the MB album ID.
    candidates: dict[Any, AlbumMatch] = {}

    # Search by explicit ID.
    if search_ids:
        for search_id in search_ids:
            log.debug("Searching for album ID: {0}", search_id)
            for album_info_for_id in hooks.albums_for_id(search_id):
                _add_candidate(items, candidates, album_info_for_id)

    # Use existing metadata or text search.
    else:
        # Try search based on current ID.
        id_info = match_by_id(items)
        if id_info:
            _add_candidate(items, candidates, id_info)
            rec = _recommendation(list(candidates.values()))
            log.debug("Album ID match recommendation is {0}", rec)
            if candidates and not config["import"]["timid"]:
                # If we have a very good MBID match, return immediately.
                # Otherwise, this match will compete against metadata-based
                # matches.
                if rec == Recommendation.strong:
                    log.debug("ID match.")
                    return (
                        cur_artist,
                        cur_album,
                        Proposal(list(candidates.values()), rec),
                    )

        # Search terms.
        if not (search_artist and search_album):
            # No explicit search terms -- use current metadata.
            search_artist, search_album = cur_artist, cur_album
        log.debug("Search terms: {0} - {1}", search_artist, search_album)

        extra_tags = None
        if config["musicbrainz"]["extra_tags"]:
            tag_list = config["musicbrainz"]["extra_tags"].get()
            extra_tags = {k: v for (k, v) in likelies.items() if k in tag_list}
            log.debug("Additional search terms: {0}", extra_tags)

        # Is this album likely to be a "various artist" release?
        va_likely = (
            (not consensus["artist"])
            or (search_artist.lower() in VA_ARTISTS)
            or any(item.comp for item in items)
        )
        log.debug("Album might be VA: {0}", va_likely)

        # Get the results from the data sources.
        for matched_candidate in hooks.album_candidates(
            items, search_artist, search_album, va_likely, extra_tags
        ):
            _add_candidate(items, candidates, matched_candidate)

    log.debug("Evaluating {0} candidates.", len(candidates))
    # Sort and get the recommendation.
    candidates_sorted = _sort_candidates(candidates.values())
    rec = _recommendation(candidates_sorted)
    return cur_artist, cur_album, Proposal(candidates_sorted, rec)


def tag_item(
    item,
    search_artist: str | None = None,
    search_title: str | None = None,
    search_ids: list[str] | None = None,
) -> Proposal:
    """Find metadata for a single track. Return a `Proposal` consisting
    of `TrackMatch` objects.

    `search_artist` and `search_title` may be used
    to override the current metadata for the purposes of the MusicBrainz
    title. `search_ids` may be used for restricting the search to a list
    of metadata backend IDs.
    """
    # Holds candidates found so far: keys are MBIDs; values are
    # (distance, TrackInfo) pairs.
    candidates = {}
    rec: Recommendation | None = None

    # First, try matching by MusicBrainz ID.
    trackids = search_ids or [t for t in [item.mb_trackid] if t]
    if trackids:
        for trackid in trackids:
            log.debug("Searching for track ID: {0}", trackid)
            for track_info in hooks.tracks_for_id(trackid):
                dist = track_distance(item, track_info, incl_artist=True)
                candidates[track_info.track_id] = hooks.TrackMatch(
                    dist, track_info
                )
                # If this is a good match, then don't keep searching.
                rec = _recommendation(_sort_candidates(candidates.values()))
                if (
                    rec == Recommendation.strong
                    and not config["import"]["timid"]
                ):
                    log.debug("Track ID match.")
                    return Proposal(_sort_candidates(candidates.values()), rec)

    # If we're searching by ID, don't proceed.
    if search_ids:
        if candidates:
            assert rec is not None
            return Proposal(_sort_candidates(candidates.values()), rec)
        else:
            return Proposal([], Recommendation.none)

    # Search terms.
    if not (search_artist and search_title):
        search_artist, search_title = item.artist, item.title
    log.debug("Item search terms: {0} - {1}", search_artist, search_title)

    # Get and evaluate candidate metadata.
    for track_info in hooks.item_candidates(item, search_artist, search_title):
        dist = track_distance(item, track_info, incl_artist=True)
        candidates[track_info.track_id] = hooks.TrackMatch(dist, track_info)

    # Sort by distance and return with recommendation.
    log.debug("Found {0} candidates.", len(candidates))
    candidates_sorted = _sort_candidates(candidates.values())
    rec = _recommendation(candidates_sorted)
    return Proposal(candidates_sorted, rec)
