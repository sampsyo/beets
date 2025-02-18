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

"""Searches for albums in the MusicBrainz database."""

from __future__ import annotations

import re
import traceback
from collections import Counter
from collections.abc import Iterator, Sequence
from itertools import product
from typing import Any, cast
from urllib.parse import urljoin

import musicbrainzngs

import beets
import beets.autotag.hooks
from beets import config, logging, plugins, util
from beets.plugins import MetadataSourcePlugin
from beets.util.id_extractors import (
    beatport_id_regex,
    deezer_id_regex,
    extract_discogs_id_regex,
    spotify_id_regex,
)

VARIOUS_ARTISTS_ID = "89ad4ac3-39f7-470e-963a-56509c546377"

BASE_URL = "https://musicbrainz.org/"

SKIPPED_TRACKS = ["[data track]"]

FIELDS_TO_MB_KEYS = {
    "catalognum": "catno",
    "country": "country",
    "label": "label",
    "barcode": "barcode",
    "media": "format",
    "year": "date",
}

musicbrainzngs.set_useragent("beets", beets.__version__, "https://beets.io/")


class MusicBrainzAPIError(util.HumanReadableError):
    """An error while talking to MusicBrainz. The `query` field is the
    parameter to the action and may have any type.
    """

    def __init__(self, reason, verb, query, tb=None):
        self.query = query
        if isinstance(reason, musicbrainzngs.WebServiceError):
            reason = "MusicBrainz not reachable"
        super().__init__(reason, verb, tb)

    def get_message(self):
        return "{} in {} with query {}".format(
            self._reasonstr(), self.verb, repr(self.query)
        )


log = logging.getLogger("beets")

RELEASE_INCLUDES = list(
    {
        "artists",
        "media",
        "recordings",
        "release-groups",
        "labels",
        "artist-credits",
        "aliases",
        "recording-level-rels",
        "work-rels",
        "work-level-rels",
        "artist-rels",
        "isrcs",
        "url-rels",
        "release-rels",
        "tags",
    }
    & set(musicbrainzngs.VALID_INCLUDES["release"])
)

TRACK_INCLUDES = list(
    {
        "artists",
        "aliases",
        "isrcs",
        "work-level-rels",
        "artist-rels",
    }
    & set(musicbrainzngs.VALID_INCLUDES["recording"])
)

BROWSE_INCLUDES = [
    "artist-credits",
    "work-rels",
    "artist-rels",
    "recording-rels",
    "release-rels",
]
if "work-level-rels" in musicbrainzngs.VALID_BROWSE_INCLUDES["recording"]:
    BROWSE_INCLUDES.append("work-level-rels")
BROWSE_CHUNKSIZE = 100
BROWSE_MAXTRACKS = 500


def track_url(trackid: str) -> str:
    return urljoin(BASE_URL, "recording/" + trackid)


def album_url(albumid: str) -> str:
    return urljoin(BASE_URL, "release/" + albumid)


def configure():
    """Set up the python-musicbrainz-ngs module according to settings
    from the beets configuration. This should be called at startup.
    """
    hostname = config["musicbrainz"]["host"].as_str()
    https = config["musicbrainz"]["https"].get(bool)
    # Only call set_hostname when a custom server is configured. Since
    # musicbrainz-ngs connects to musicbrainz.org with HTTPS by default
    if hostname != "musicbrainz.org":
        musicbrainzngs.set_hostname(hostname, https)
    musicbrainzngs.set_rate_limit(
        config["musicbrainz"]["ratelimit_interval"].as_number(),
        config["musicbrainz"]["ratelimit"].get(int),
    )


def _preferred_alias(aliases: list):
    """Given an list of alias structures for an artist credit, select
    and return the user's preferred alias alias or None if no matching
    alias is found.
    """
    if not aliases:
        return

    # Only consider aliases that have locales set.
    aliases = [a for a in aliases if "locale" in a]

    # Get any ignored alias types and lower case them to prevent case issues
    ignored_alias_types = config["import"]["ignored_alias_types"].as_str_seq()
    ignored_alias_types = [a.lower() for a in ignored_alias_types]

    # Search configured locales in order.
    for locale in config["import"]["languages"].as_str_seq():
        # Find matching primary aliases for this locale that are not
        # being ignored
        matches = []
        for a in aliases:
            if (
                a["locale"] == locale
                and "primary" in a
                and a.get("type", "").lower() not in ignored_alias_types
            ):
                matches.append(a)

        # Skip to the next locale if we have no matches
        if not matches:
            continue

        return matches[0]


def _preferred_release_event(release: dict[str, Any]) -> tuple[str, str]:
    """Given a release, select and return the user's preferred release
    event as a tuple of (country, release_date). Fall back to the
    default release event if a preferred event is not found.
    """
    countries = config["match"]["preferred"]["countries"].as_str_seq()
    countries = cast(Sequence, countries)

    for country in countries:
        for event in release.get("release-event-list", {}):
            try:
                if country in event["area"]["iso-3166-1-code-list"]:
                    return country, event["date"]
            except KeyError:
                pass

    return (cast(str, release.get("country")), cast(str, release.get("date")))


def _multi_artist_credit(
    credit: list[dict], include_join_phrase: bool
) -> tuple[list[str], list[str], list[str]]:
    """Given a list representing an ``artist-credit`` block, accumulate
    data into a triple of joined artist name lists: canonical, sort, and
    credit.
    """
    artist_parts = []
    artist_sort_parts = []
    artist_credit_parts = []
    for el in credit:
        if isinstance(el, str):
            # Join phrase.
            if include_join_phrase:
                artist_parts.append(el)
                artist_credit_parts.append(el)
                artist_sort_parts.append(el)

        else:
            alias = _preferred_alias(el["artist"].get("alias-list", ()))

            # An artist.
            if alias:
                cur_artist_name = alias["alias"]
            else:
                cur_artist_name = el["artist"]["name"]
            artist_parts.append(cur_artist_name)

            # Artist sort name.
            if alias:
                artist_sort_parts.append(alias["sort-name"])
            elif "sort-name" in el["artist"]:
                artist_sort_parts.append(el["artist"]["sort-name"])
            else:
                artist_sort_parts.append(cur_artist_name)

            # Artist credit.
            if "name" in el:
                artist_credit_parts.append(el["name"])
            else:
                artist_credit_parts.append(cur_artist_name)

    return (
        artist_parts,
        artist_sort_parts,
        artist_credit_parts,
    )


def _flatten_artist_credit(credit: list[dict]) -> tuple[str, str, str]:
    """Given a list representing an ``artist-credit`` block, flatten the
    data into a triple of joined artist name strings: canonical, sort, and
    credit.
    """
    artist_parts, artist_sort_parts, artist_credit_parts = _multi_artist_credit(
        credit, include_join_phrase=True
    )
    return (
        "".join(artist_parts),
        "".join(artist_sort_parts),
        "".join(artist_credit_parts),
    )


def _artist_ids(credit: list[dict]) -> list[str]:
    """
    Given a list representing an ``artist-credit``,
    return a list of artist IDs
    """
    artist_ids: list[str] = []
    for el in credit:
        if isinstance(el, dict):
            artist_ids.append(el["artist"]["id"])

    return artist_ids


def _get_related_artist_names(relations, relation_type):
    """Given a list representing the artist relationships extract the names of
    the remixers and concatenate them.
    """
    related_artists = []

    for relation in relations:
        if relation["type"] == relation_type:
            related_artists.append(relation["artist"]["name"])

    return ", ".join(related_artists)


def track_info(
    recording: dict,
    index: int | None = None,
    medium: int | None = None,
    medium_index: int | None = None,
    medium_total: int | None = None,
) -> beets.autotag.hooks.TrackInfo:
    """Translates a MusicBrainz recording result dictionary into a beets
    ``TrackInfo`` object. Three parameters are optional and are used
    only for tracks that appear on releases (non-singletons): ``index``,
    the overall track number; ``medium``, the disc number;
    ``medium_index``, the track's index on its medium; ``medium_total``,
    the number of tracks on the medium. Each number is a 1-based index.
    """
    if "alias-list" in recording:
        alias = _preferred_alias(recording["alias-list"])
    else:
        alias = None

    if alias:
        title = alias["alias"]
    else:
        title = recording["title"]

    info = beets.autotag.hooks.TrackInfo(
        title=title,
        track_id=recording["id"],
        index=index,
        medium=medium,
        medium_index=medium_index,
        medium_total=medium_total,
        data_source="MusicBrainz",
        data_url=track_url(recording["id"]),
    )

    if recording.get("artist-credit"):
        # Get the artist names.
        (
            info.artist,
            info.artist_sort,
            info.artist_credit,
        ) = _flatten_artist_credit(recording["artist-credit"])

        (
            info.artists,
            info.artists_sort,
            info.artists_credit,
        ) = _multi_artist_credit(
            recording["artist-credit"], include_join_phrase=False
        )

        info.artists_ids = _artist_ids(recording["artist-credit"])
        info.artist_id = info.artists_ids[0]

    if recording.get("artist-relation-list"):
        info.remixer = _get_related_artist_names(
            recording["artist-relation-list"], relation_type="remixer"
        )

    if recording.get("length"):
        info.length = int(recording["length"]) / 1000.0

    info.trackdisambig = recording.get("disambiguation")

    if recording.get("isrc-list"):
        info.isrc = ";".join(recording["isrc-list"])

    lyricist = []
    composer = []
    composer_sort = []
    for work_relation in recording.get("work-relation-list", ()):
        if work_relation["type"] != "performance":
            continue
        info.work = work_relation["work"]["title"]
        info.mb_workid = work_relation["work"]["id"]
        if "disambiguation" in work_relation["work"]:
            info.work_disambig = work_relation["work"]["disambiguation"]

        for artist_relation in work_relation["work"].get(
            "artist-relation-list", ()
        ):
            if "type" in artist_relation:
                type = artist_relation["type"]
                if type == "lyricist":
                    lyricist.append(artist_relation["artist"]["name"])
                elif type == "composer":
                    composer.append(artist_relation["artist"]["name"])
                    composer_sort.append(artist_relation["artist"]["sort-name"])
    if lyricist:
        info.lyricist = ", ".join(lyricist)
    if composer:
        info.composer = ", ".join(composer)
        info.composer_sort = ", ".join(composer_sort)

    arranger = []
    for artist_relation in recording.get("artist-relation-list", ()):
        if "type" in artist_relation:
            type = artist_relation["type"]
            if type == "arranger":
                arranger.append(artist_relation["artist"]["name"])
    if arranger:
        info.arranger = ", ".join(arranger)

    # Supplementary fields provided by plugins
    extra_trackdatas = plugins.send("mb_track_extract", data=recording)
    for extra_trackdata in extra_trackdatas:
        info.update(extra_trackdata)

    return info


def _set_date_str(
    info: beets.autotag.hooks.AlbumInfo,
    date_str: str,
    original: bool = False,
):
    """Given a (possibly partial) YYYY-MM-DD string and an AlbumInfo
    object, set the object's release date fields appropriately. If
    `original`, then set the original_year, etc., fields.
    """
    if date_str:
        date_parts = date_str.split("-")
        for key in ("year", "month", "day"):
            if date_parts:
                date_part = date_parts.pop(0)
                try:
                    date_num = int(date_part)
                except ValueError:
                    continue

                if original:
                    key = "original_" + key
                setattr(info, key, date_num)


def album_info(release: dict) -> beets.autotag.hooks.AlbumInfo:
    """Takes a MusicBrainz release result dictionary and returns a beets
    AlbumInfo object containing the interesting data about that release.
    """
    # Get artist name using join phrases.
    artist_name, artist_sort_name, artist_credit_name = _flatten_artist_credit(
        release["artist-credit"]
    )

    (
        artists_names,
        artists_sort_names,
        artists_credit_names,
    ) = _multi_artist_credit(
        release["artist-credit"], include_join_phrase=False
    )

    ntracks = sum(len(m["track-list"]) for m in release["medium-list"])

    # The MusicBrainz API omits 'artist-relation-list' and 'work-relation-list'
    # when the release has more than 500 tracks. So we use browse_recordings
    # on chunks of tracks to recover the same information in this case.
    if ntracks > BROWSE_MAXTRACKS:
        log.debug("Album {} has too many tracks", release["id"])
        recording_list = []
        for i in range(0, ntracks, BROWSE_CHUNKSIZE):
            log.debug("Retrieving tracks starting at {}", i)
            recording_list.extend(
                musicbrainzngs.browse_recordings(
                    release=release["id"],
                    limit=BROWSE_CHUNKSIZE,
                    includes=BROWSE_INCLUDES,
                    offset=i,
                )["recording-list"]
            )
        track_map = {r["id"]: r for r in recording_list}
        for medium in release["medium-list"]:
            for recording in medium["track-list"]:
                recording_info = track_map[recording["recording"]["id"]]
                recording["recording"] = recording_info

    # Basic info.
    track_infos = []
    index = 0
    for medium in release["medium-list"]:
        disctitle = medium.get("title")
        format = medium.get("format")

        if format in config["match"]["ignored_media"].as_str_seq():
            continue

        all_tracks = medium["track-list"]
        if (
            "data-track-list" in medium
            and not config["match"]["ignore_data_tracks"]
        ):
            all_tracks += medium["data-track-list"]
        track_count = len(all_tracks)

        if "pregap" in medium:
            all_tracks.insert(0, medium["pregap"])

        for track in all_tracks:
            if (
                "title" in track["recording"]
                and track["recording"]["title"] in SKIPPED_TRACKS
            ):
                continue

            if (
                "video" in track["recording"]
                and track["recording"]["video"] == "true"
                and config["match"]["ignore_video_tracks"]
            ):
                continue

            # Basic information from the recording.
            index += 1
            ti = track_info(
                track["recording"],
                index,
                int(medium["position"]),
                int(track["position"]),
                track_count,
            )
            ti.release_track_id = track["id"]
            ti.disctitle = disctitle
            ti.media = format
            ti.track_alt = track["number"]

            # Prefer track data, where present, over recording data.
            if track.get("title"):
                if "alias-list" in track["recording"]:
                    alias = _preferred_alias(track["recording"]["alias-list"])
                else:
                    alias = None

                if alias:
                    ti.title = alias["alias"]
                else:
                    ti.title = track["title"]
            if track.get("artist-credit"):
                # Get the artist names.
                (
                    ti.artist,
                    ti.artist_sort,
                    ti.artist_credit,
                ) = _flatten_artist_credit(track["artist-credit"])

                (
                    ti.artists,
                    ti.artists_sort,
                    ti.artists_credit,
                ) = _multi_artist_credit(
                    track["artist-credit"], include_join_phrase=False
                )

                ti.artists_ids = _artist_ids(track["artist-credit"])
                ti.artist_id = ti.artists_ids[0]
            if track.get("length"):
                ti.length = int(track["length"]) / (1000.0)

            track_infos.append(ti)

    album_artist_ids = _artist_ids(release["artist-credit"])

    if "alias-list" in release:
        alias = _preferred_alias(release["alias-list"])
    else:
        alias = None

    if alias:
        title = alias["alias"]
    else:
        title = release["title"]

    info = beets.autotag.hooks.AlbumInfo(
        album=title,
        album_id=release["id"],
        artist=artist_name,
        artist_id=album_artist_ids[0],
        artists=artists_names,
        artists_ids=album_artist_ids,
        tracks=track_infos,
        mediums=len(release["medium-list"]),
        artist_sort=artist_sort_name,
        artists_sort=artists_sort_names,
        artist_credit=artist_credit_name,
        artists_credit=artists_credit_names,
        data_source="MusicBrainz",
        data_url=album_url(release["id"]),
        barcode=release.get("barcode"),
    )
    info.va = info.artist_id == VARIOUS_ARTISTS_ID
    if info.va:
        info.artist = config["va_name"].as_str()
    info.asin = release.get("asin")
    info.releasegroup_id = release["release-group"]["id"]
    info.albumstatus = release.get("status")

    if release["release-group"].get("title"):
        if "alias-list" in release["release-group"]:
            alias = _preferred_alias(release["release-group"]["alias-list"])
        else:
            alias = None

        if alias:
            title = alias["alias"]
        else:
            title = release["release-group"].get("title")

        info.release_group_title = title

    # Get the disambiguation strings at the release and release group level.
    if release["release-group"].get("disambiguation"):
        info.releasegroupdisambig = release["release-group"].get(
            "disambiguation"
        )
    if release.get("disambiguation"):
        info.albumdisambig = release.get("disambiguation")

    # Get the "classic" Release type. This data comes from a legacy API
    # feature before MusicBrainz supported multiple release types.
    if "type" in release["release-group"]:
        reltype = release["release-group"]["type"]
        if reltype:
            info.albumtype = reltype.lower()

    # Set the new-style "primary" and "secondary" release types.
    albumtypes = []
    if "primary-type" in release["release-group"]:
        rel_primarytype = release["release-group"]["primary-type"]
        if rel_primarytype:
            albumtypes.append(rel_primarytype.lower())
    if "secondary-type-list" in release["release-group"]:
        if release["release-group"]["secondary-type-list"]:
            for sec_type in release["release-group"]["secondary-type-list"]:
                albumtypes.append(sec_type.lower())
    info.albumtypes = albumtypes

    # Release events.
    info.country, release_date = _preferred_release_event(release)
    release_group_date = release["release-group"].get("first-release-date")
    if not release_date:
        # Fall back if release-specific date is not available.
        release_date = release_group_date
    _set_date_str(info, release_date, False)
    _set_date_str(info, release_group_date, True)

    # Label name.
    if release.get("label-info-list"):
        label_info = release["label-info-list"][0]
        if label_info.get("label"):
            label = label_info["label"]["name"]
            if label != "[no label]":
                info.label = label
        info.catalognum = label_info.get("catalog-number")

    # Text representation data.
    if release.get("text-representation"):
        rep = release["text-representation"]
        info.script = rep.get("script")
        info.language = rep.get("language")

    # Media (format).
    if release["medium-list"]:
        # If all media are the same, use that medium name
        if len({m.get("format") for m in release["medium-list"]}) == 1:
            info.media = release["medium-list"][0].get("format")
        # Otherwise, let's just call it "Media"
        else:
            info.media = "Media"

    if config["musicbrainz"]["genres"]:
        sources = [
            release["release-group"].get("tag-list", []),
            release.get("tag-list", []),
        ]
        genres: Counter[str] = Counter()
        for source in sources:
            for genreitem in source:
                genres[genreitem["name"]] += int(genreitem["count"])
        info.genre = "; ".join(
            genre
            for genre, _count in sorted(genres.items(), key=lambda g: -g[1])
        )

    # We might find links to external sources (Discogs, Bandcamp, ...)
    external_ids = config["musicbrainz"]["external_ids"].get()
    wanted_sources = {site for site, wanted in external_ids.items() if wanted}
    if wanted_sources and (url_rels := release.get("url-relation-list")):
        urls = {}

        for source, url in product(wanted_sources, url_rels):
            if f"{source}.com" in (target := url["target"]):
                urls[source] = target
                log.debug(
                    "Found link to {} release via MusicBrainz",
                    source.capitalize(),
                )

        if "discogs" in urls:
            info.discogs_albumid = extract_discogs_id_regex(urls["discogs"])
        if "bandcamp" in urls:
            info.bandcamp_album_id = urls["bandcamp"]
        if "spotify" in urls:
            info.spotify_album_id = MetadataSourcePlugin._get_id(
                "album", urls["spotify"], spotify_id_regex
            )
        if "deezer" in urls:
            info.deezer_album_id = MetadataSourcePlugin._get_id(
                "album", urls["deezer"], deezer_id_regex
            )
        if "beatport" in urls:
            info.beatport_album_id = MetadataSourcePlugin._get_id(
                "album", urls["beatport"], beatport_id_regex
            )
        if "tidal" in urls:
            info.tidal_album_id = urls["tidal"].split("/")[-1]

    extra_albumdatas = plugins.send("mb_album_extract", data=release)
    for extra_albumdata in extra_albumdatas:
        info.update(extra_albumdata)

    return info


def match_album(
    artist: str,
    album: str,
    tracks: int | None = None,
    extra_tags: dict[str, Any] | None = None,
) -> Iterator[beets.autotag.hooks.AlbumInfo]:
    """Searches for a single album ("release" in MusicBrainz parlance)
    and returns an iterator over AlbumInfo objects. May raise a
    MusicBrainzAPIError.

    The query consists of an artist name, an album name, and,
    optionally, a number of tracks on the album and any other extra tags.
    """
    # Build search criteria.
    criteria = {"release": album.lower().strip()}
    if artist is not None:
        criteria["artist"] = artist.lower().strip()
    else:
        # Various Artists search.
        criteria["arid"] = VARIOUS_ARTISTS_ID
    if tracks is not None:
        criteria["tracks"] = str(tracks)

    # Additional search cues from existing metadata.
    if extra_tags:
        for tag, value in extra_tags.items():
            key = FIELDS_TO_MB_KEYS[tag]
            value = str(value).lower().strip()
            if key == "catno":
                value = value.replace(" ", "")
            if value:
                criteria[key] = value

    # Abort if we have no search terms.
    if not any(criteria.values()):
        return

    try:
        log.debug("Searching for MusicBrainz releases with: {!r}", criteria)
        res = musicbrainzngs.search_releases(
            limit=config["musicbrainz"]["searchlimit"].get(int), **criteria
        )
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(
            exc, "release search", criteria, traceback.format_exc()
        )
    for release in res["release-list"]:
        # The search result is missing some data (namely, the tracks),
        # so we just use the ID and fetch the rest of the information.
        albuminfo = album_for_id(release["id"])
        if albuminfo is not None:
            yield albuminfo


def match_track(
    artist: str,
    title: str,
) -> Iterator[beets.autotag.hooks.TrackInfo]:
    """Searches for a single track and returns an iterable of TrackInfo
    objects. May raise a MusicBrainzAPIError.
    """
    criteria = {
        "artist": artist.lower().strip(),
        "recording": title.lower().strip(),
    }

    if not any(criteria.values()):
        return

    try:
        res = musicbrainzngs.search_recordings(
            limit=config["musicbrainz"]["searchlimit"].get(int), **criteria
        )
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(
            exc, "recording search", criteria, traceback.format_exc()
        )
    for recording in res["recording-list"]:
        yield track_info(recording)


def _parse_id(s: str) -> str | None:
    """Search for a MusicBrainz ID in the given string and return it. If
    no ID can be found, return None.
    """
    # Find the first thing that looks like a UUID/MBID.
    match = re.search("[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}", s)
    if match is not None:
        return match.group() if match else None
    return None


def _is_translation(r):
    _trans_key = "transl-tracklisting"
    return r["type"] == _trans_key and r["direction"] == "backward"


def _find_actual_release_from_pseudo_release(
    pseudo_rel: dict,
) -> dict | None:
    try:
        relations = pseudo_rel["release"]["release-relation-list"]
    except KeyError:
        return None

    # currently we only support trans(liter)ation's
    translations = [r for r in relations if _is_translation(r)]

    if not translations:
        return None

    actual_id = translations[0]["target"]

    return musicbrainzngs.get_release_by_id(actual_id, RELEASE_INCLUDES)


def _merge_pseudo_and_actual_album(
    pseudo: beets.autotag.hooks.AlbumInfo, actual: beets.autotag.hooks.AlbumInfo
) -> beets.autotag.hooks.AlbumInfo | None:
    """
    Merges a pseudo release with its actual release.

    This implementation is naive, it doesn't overwrite fields,
    like status or ids.

    According to the ticket PICARD-145, the main release id should be used.
    But the ticket has been in limbo since over a decade now.
    It also suggests the introduction of the tag `musicbrainz_pseudoreleaseid`,
    but as of this field can't be found in any official Picard docs,
    hence why we did not implement that for now.
    """
    merged = pseudo.copy()
    from_actual = {
        k: actual[k]
        for k in [
            "media",
            "mediums",
            "country",
            "catalognum",
            "year",
            "month",
            "day",
            "original_year",
            "original_month",
            "original_day",
            "label",
            "barcode",
            "asin",
            "style",
            "genre",
        ]
    }
    merged.update(from_actual)
    return merged


def album_for_id(releaseid: str) -> beets.autotag.hooks.AlbumInfo | None:
    """Fetches an album by its MusicBrainz ID and returns an AlbumInfo
    object or None if the album is not found. May raise a
    MusicBrainzAPIError.
    """
    log.debug("Requesting MusicBrainz release {}", releaseid)
    albumid = _parse_id(releaseid)
    if not albumid:
        log.debug("Invalid MBID ({0}).", releaseid)
        return None
    try:
        res = musicbrainzngs.get_release_by_id(albumid, RELEASE_INCLUDES)

        # resolve linked release relations
        actual_res = None

        if res["release"].get("status") == "Pseudo-Release":
            actual_res = _find_actual_release_from_pseudo_release(res)

    except musicbrainzngs.ResponseError:
        log.debug("Album ID match failed.")
        return None
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(
            exc, "get release by ID", albumid, traceback.format_exc()
        )

    # release is potentially a pseudo release
    release = album_info(res["release"])

    # should be None unless we're dealing with a pseudo release
    if actual_res is not None:
        actual_release = album_info(actual_res["release"])
        return _merge_pseudo_and_actual_album(release, actual_release)
    else:
        return release


def track_for_id(releaseid: str) -> beets.autotag.hooks.TrackInfo | None:
    """Fetches a track by its MusicBrainz ID. Returns a TrackInfo object
    or None if no track is found. May raise a MusicBrainzAPIError.
    """
    trackid = _parse_id(releaseid)
    if not trackid:
        log.debug("Invalid MBID ({0}).", releaseid)
        return None
    try:
        res = musicbrainzngs.get_recording_by_id(trackid, TRACK_INCLUDES)
    except musicbrainzngs.ResponseError:
        log.debug("Track ID match failed.")
        return None
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(
            exc, "get recording by ID", trackid, traceback.format_exc()
        )
    return track_info(res["recording"])
