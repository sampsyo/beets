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

"""Glue between metadata sources and the matching logic."""

from __future__ import annotations

import re
from functools import total_ordering
from typing import TYPE_CHECKING, Any, Callable, NamedTuple, TypeVar, cast

from jellyfish import levenshtein_distance
from unidecode import unidecode

from beets import config, logging, plugins
from beets.autotag import mb
from beets.util import as_string, cached_classproperty

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from beets.library import Item

log = logging.getLogger("beets")

V = TypeVar("V")


# Classes used to represent candidate options.
class AttrDict(dict[str, V]):
    """A dictionary that supports attribute ("dot") access, so `d.field`
    is equivalent to `d['field']`.
    """

    def __getattr__(self, attr: str) -> V:
        if attr in self:
            return self[attr]
        else:
            raise AttributeError

    def __setattr__(self, key: str, value: V):
        self.__setitem__(key, value)

    def __hash__(self):
        return id(self)


class AlbumInfo(AttrDict):
    """Describes a canonical release that may be used to match a release
    in the library. Consists of these data members:

    - ``album``: the release title
    - ``album_id``: MusicBrainz ID; UUID fragment only
    - ``artist``: name of the release's primary artist
    - ``artist_id``
    - ``tracks``: list of TrackInfo objects making up the release

    ``mediums`` along with the fields up through ``tracks`` are required.
    The others are optional and may be None.
    """

    # TYPING: are all of these correct? I've assumed optional strings
    def __init__(
        self,
        tracks: list[TrackInfo],
        album: str | None = None,
        album_id: str | None = None,
        artist: str | None = None,
        artist_id: str | None = None,
        artists: list[str] | None = None,
        artists_ids: list[str] | None = None,
        asin: str | None = None,
        albumtype: str | None = None,
        albumtypes: list[str] | None = None,
        va: bool = False,
        year: int | None = None,
        month: int | None = None,
        day: int | None = None,
        label: str | None = None,
        barcode: str | None = None,
        mediums: int | None = None,
        artist_sort: str | None = None,
        artists_sort: list[str] | None = None,
        releasegroup_id: str | None = None,
        release_group_title: str | None = None,
        catalognum: str | None = None,
        script: str | None = None,
        language: str | None = None,
        country: str | None = None,
        style: str | None = None,
        genre: str | None = None,
        albumstatus: str | None = None,
        media: str | None = None,
        albumdisambig: str | None = None,
        releasegroupdisambig: str | None = None,
        artist_credit: str | None = None,
        artists_credit: list[str] | None = None,
        original_year: int | None = None,
        original_month: int | None = None,
        original_day: int | None = None,
        data_source: str | None = None,
        data_url: str | None = None,
        discogs_albumid: str | None = None,
        discogs_labelid: str | None = None,
        discogs_artistid: str | None = None,
        **kwargs,
    ):
        self.album = album
        self.album_id = album_id
        self.artist = artist
        self.artist_id = artist_id
        self.artists = artists or []
        self.artists_ids = artists_ids or []
        self.tracks = tracks
        self.asin = asin
        self.albumtype = albumtype
        self.albumtypes = albumtypes or []
        self.va = va
        self.year = year
        self.month = month
        self.day = day
        self.label = label
        self.barcode = barcode
        self.mediums = mediums
        self.artist_sort = artist_sort
        self.artists_sort = artists_sort or []
        self.releasegroup_id = releasegroup_id
        self.release_group_title = release_group_title
        self.catalognum = catalognum
        self.script = script
        self.language = language
        self.country = country
        self.style = style
        self.genre = genre
        self.albumstatus = albumstatus
        self.media = media
        self.albumdisambig = albumdisambig
        self.releasegroupdisambig = releasegroupdisambig
        self.artist_credit = artist_credit
        self.artists_credit = artists_credit or []
        self.original_year = original_year
        self.original_month = original_month
        self.original_day = original_day
        self.data_source = data_source
        self.data_url = data_url
        self.discogs_albumid = discogs_albumid
        self.discogs_labelid = discogs_labelid
        self.discogs_artistid = discogs_artistid
        self.update(kwargs)

    def copy(self) -> AlbumInfo:
        dupe = AlbumInfo([])
        dupe.update(self)
        dupe.tracks = [track.copy() for track in self.tracks]
        return dupe


class TrackInfo(AttrDict):
    """Describes a canonical track present on a release. Appears as part
    of an AlbumInfo's ``tracks`` list. Consists of these data members:

    - ``title``: name of the track
    - ``track_id``: MusicBrainz ID; UUID fragment only

    Only ``title`` and ``track_id`` are required. The rest of the fields
    may be None. The indices ``index``, ``medium``, and ``medium_index``
    are all 1-based.
    """

    # TYPING: are all of these correct? I've assumed optional strings
    def __init__(
        self,
        title: str | None = None,
        track_id: str | None = None,
        release_track_id: str | None = None,
        artist: str | None = None,
        artist_id: str | None = None,
        artists: list[str] | None = None,
        artists_ids: list[str] | None = None,
        length: float | None = None,
        index: int | None = None,
        medium: int | None = None,
        medium_index: int | None = None,
        medium_total: int | None = None,
        artist_sort: str | None = None,
        artists_sort: list[str] | None = None,
        disctitle: str | None = None,
        artist_credit: str | None = None,
        artists_credit: list[str] | None = None,
        data_source: str | None = None,
        data_url: str | None = None,
        media: str | None = None,
        lyricist: str | None = None,
        composer: str | None = None,
        composer_sort: str | None = None,
        arranger: str | None = None,
        track_alt: str | None = None,
        work: str | None = None,
        mb_workid: str | None = None,
        work_disambig: str | None = None,
        bpm: str | None = None,
        initial_key: str | None = None,
        genre: str | None = None,
        album: str | None = None,
        **kwargs,
    ):
        self.title = title
        self.track_id = track_id
        self.release_track_id = release_track_id
        self.artist = artist
        self.artist_id = artist_id
        self.artists = artists or []
        self.artists_ids = artists_ids or []
        self.length = length
        self.index = index
        self.media = media
        self.medium = medium
        self.medium_index = medium_index
        self.medium_total = medium_total
        self.artist_sort = artist_sort
        self.artists_sort = artists_sort or []
        self.disctitle = disctitle
        self.artist_credit = artist_credit
        self.artists_credit = artists_credit or []
        self.data_source = data_source
        self.data_url = data_url
        self.lyricist = lyricist
        self.composer = composer
        self.composer_sort = composer_sort
        self.arranger = arranger
        self.track_alt = track_alt
        self.work = work
        self.mb_workid = mb_workid
        self.work_disambig = work_disambig
        self.bpm = bpm
        self.initial_key = initial_key
        self.genre = genre
        self.album = album
        self.update(kwargs)

    def copy(self) -> TrackInfo:
        dupe = TrackInfo()
        dupe.update(self)
        return dupe


# Candidate distance scoring.

# Parameters for string distance function.
# Words that can be moved to the end of a string using a comma.
SD_END_WORDS = ["the", "a", "an"]
# Reduced weights for certain portions of the string.
SD_PATTERNS = [
    (r"^the ", 0.1),
    (r"[\[\(]?(ep|single)[\]\)]?", 0.0),
    (r"[\[\(]?(featuring|feat|ft)[\. :].+", 0.1),
    (r"\(.*?\)", 0.3),
    (r"\[.*?\]", 0.3),
    (r"(, )?(pt\.|part) .+", 0.2),
]
# Replacements to use before testing distance.
SD_REPLACE = [
    (r"&", "and"),
]


def _string_dist_basic(str1: str, str2: str) -> float:
    """Basic edit distance between two strings, ignoring
    non-alphanumeric characters and case. Comparisons are based on a
    transliteration/lowering to ASCII characters. Normalized by string
    length.
    """
    assert isinstance(str1, str)
    assert isinstance(str2, str)
    str1 = as_string(unidecode(str1))
    str2 = as_string(unidecode(str2))
    str1 = re.sub(r"[^a-z0-9]", "", str1.lower())
    str2 = re.sub(r"[^a-z0-9]", "", str2.lower())
    if not str1 and not str2:
        return 0.0
    return levenshtein_distance(str1, str2) / float(max(len(str1), len(str2)))


def string_dist(str1: str | None, str2: str | None) -> float:
    """Gives an "intuitive" edit distance between two strings. This is
    an edit distance, normalized by the string length, with a number of
    tweaks that reflect intuition about text.
    """
    if str1 is None and str2 is None:
        return 0.0
    if str1 is None or str2 is None:
        return 1.0

    str1 = str1.lower()
    str2 = str2.lower()

    # Don't penalize strings that move certain words to the end. For
    # example, "the something" should be considered equal to
    # "something, the".
    for word in SD_END_WORDS:
        if str1.endswith(", %s" % word):
            str1 = "{} {}".format(word, str1[: -len(word) - 2])
        if str2.endswith(", %s" % word):
            str2 = "{} {}".format(word, str2[: -len(word) - 2])

    # Perform a couple of basic normalizing substitutions.
    for pat, repl in SD_REPLACE:
        str1 = re.sub(pat, repl, str1)
        str2 = re.sub(pat, repl, str2)

    # Change the weight for certain string portions matched by a set
    # of regular expressions. We gradually change the strings and build
    # up penalties associated with parts of the string that were
    # deleted.
    base_dist = _string_dist_basic(str1, str2)
    penalty = 0.0
    for pat, weight in SD_PATTERNS:
        # Get strings that drop the pattern.
        case_str1 = re.sub(pat, "", str1)
        case_str2 = re.sub(pat, "", str2)

        if case_str1 != str1 or case_str2 != str2:
            # If the pattern was present (i.e., it is deleted in the
            # the current case), recalculate the distances for the
            # modified strings.
            case_dist = _string_dist_basic(case_str1, case_str2)
            case_delta = max(0.0, base_dist - case_dist)
            if case_delta == 0.0:
                continue

            # Shift our baseline strings down (to avoid rematching the
            # same part of the string) and add a scaled distance
            # amount to the penalties.
            str1 = case_str1
            str2 = case_str2
            base_dist = case_dist
            penalty += weight * case_delta

    return base_dist + penalty


@total_ordering
class Distance:
    """Keeps track of multiple distance penalties. Provides a single
    weighted distance for all penalties as well as a weighted distance
    for each individual penalty.
    """

    def __init__(self):
        self._penalties = {}
        self.tracks: dict[TrackInfo, Distance] = {}

    @cached_classproperty
    def _weights(cls) -> dict[str, float]:
        """A dictionary from keys to floating-point weights."""
        weights_view = config["match"]["distance_weights"]
        weights = {}
        for key in weights_view.keys():
            weights[key] = weights_view[key].as_number()
        return weights

    # Access the components and their aggregates.

    @property
    def distance(self) -> float:
        """Return a weighted and normalized distance across all
        penalties.
        """
        dist_max = self.max_distance
        if dist_max:
            return self.raw_distance / self.max_distance
        return 0.0

    @property
    def max_distance(self) -> float:
        """Return the maximum distance penalty (normalization factor)."""
        dist_max = 0.0
        for key, penalty in self._penalties.items():
            dist_max += len(penalty) * self._weights[key]
        return dist_max

    @property
    def raw_distance(self) -> float:
        """Return the raw (denormalized) distance."""
        dist_raw = 0.0
        for key, penalty in self._penalties.items():
            dist_raw += sum(penalty) * self._weights[key]
        return dist_raw

    def items(self) -> list[tuple[str, float]]:
        """Return a list of (key, dist) pairs, with `dist` being the
        weighted distance, sorted from highest to lowest. Does not
        include penalties with a zero value.
        """
        list_ = []
        for key in self._penalties:
            dist = self[key]
            if dist:
                list_.append((key, dist))
        # Convert distance into a negative float we can sort items in
        # ascending order (for keys, when the penalty is equal) and
        # still get the items with the biggest distance first.
        return sorted(
            list_, key=lambda key_and_dist: (-key_and_dist[1], key_and_dist[0])
        )

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other) -> bool:
        return self.distance == other

    # Behave like a float.

    def __lt__(self, other) -> bool:
        return self.distance < other

    def __float__(self) -> float:
        return self.distance

    def __sub__(self, other) -> float:
        return self.distance - other

    def __rsub__(self, other) -> float:
        return other - self.distance

    def __str__(self) -> str:
        return f"{self.distance:.2f}"

    # Behave like a dict.

    def __getitem__(self, key) -> float:
        """Returns the weighted distance for a named penalty."""
        dist = sum(self._penalties[key]) * self._weights[key]
        dist_max = self.max_distance
        if dist_max:
            return dist / dist_max
        return 0.0

    def __iter__(self) -> Iterator[tuple[str, float]]:
        return iter(self.items())

    def __len__(self) -> int:
        return len(self.items())

    def keys(self) -> list[str]:
        return [key for key, _ in self.items()]

    def update(self, dist: Distance):
        """Adds all the distance penalties from `dist`."""
        if not isinstance(dist, Distance):
            raise ValueError(
                "`dist` must be a Distance object, not {}".format(type(dist))
            )
        for key, penalties in dist._penalties.items():
            self._penalties.setdefault(key, []).extend(penalties)

    # Adding components.

    def _eq(self, value1: re.Pattern[str] | Any, value2: Any) -> bool:
        """Returns True if `value1` is equal to `value2`. `value1` may
        be a compiled regular expression, in which case it will be
        matched against `value2`.
        """
        if isinstance(value1, re.Pattern):
            value2 = cast(str, value2)
            return bool(value1.match(value2))
        return value1 == value2

    def add(self, key: str, dist: float):
        """Adds a distance penalty. `key` must correspond with a
        configured weight setting. `dist` must be a float between 0.0
        and 1.0, and will be added to any existing distance penalties
        for the same key.
        """
        if not 0.0 <= dist <= 1.0:
            raise ValueError(f"`dist` must be between 0.0 and 1.0, not {dist}")
        self._penalties.setdefault(key, []).append(dist)

    def add_equality(
        self,
        key: str,
        value: Any,
        options: list[Any] | tuple[Any, ...] | Any,
    ):
        """Adds a distance penalty of 1.0 if `value` doesn't match any
        of the values in `options`. If an option is a compiled regular
        expression, it will be considered equal if it matches against
        `value`.
        """
        if not isinstance(options, (list, tuple)):
            options = [options]
        for opt in options:
            if self._eq(opt, value):
                dist = 0.0
                break
        else:
            dist = 1.0
        self.add(key, dist)

    def add_expr(self, key: str, expr: bool):
        """Adds a distance penalty of 1.0 if `expr` evaluates to True,
        or 0.0.
        """
        if expr:
            self.add(key, 1.0)
        else:
            self.add(key, 0.0)

    def add_number(self, key: str, number1: int, number2: int):
        """Adds a distance penalty of 1.0 for each number of difference
        between `number1` and `number2`, or 0.0 when there is no
        difference. Use this when there is no upper limit on the
        difference between the two numbers.
        """
        diff = abs(number1 - number2)
        if diff:
            for i in range(diff):
                self.add(key, 1.0)
        else:
            self.add(key, 0.0)

    def add_priority(
        self,
        key: str,
        value: Any,
        options: list[Any] | tuple[Any, ...] | Any,
    ):
        """Adds a distance penalty that corresponds to the position at
        which `value` appears in `options`. A distance penalty of 0.0
        for the first option, or 1.0 if there is no matching option. If
        an option is a compiled regular expression, it will be
        considered equal if it matches against `value`.
        """
        if not isinstance(options, (list, tuple)):
            options = [options]
        unit = 1.0 / (len(options) or 1)
        for i, opt in enumerate(options):
            if self._eq(opt, value):
                dist = i * unit
                break
        else:
            dist = 1.0
        self.add(key, dist)

    def add_ratio(
        self,
        key: str,
        number1: int | float,
        number2: int | float,
    ):
        """Adds a distance penalty for `number1` as a ratio of `number2`.
        `number1` is bound at 0 and `number2`.
        """
        number = float(max(min(number1, number2), 0))
        if number2:
            dist = number / number2
        else:
            dist = 0.0
        self.add(key, dist)

    def add_string(self, key: str, str1: str | None, str2: str | None):
        """Adds a distance penalty based on the edit distance between
        `str1` and `str2`.
        """
        dist = string_dist(str1, str2)
        self.add(key, dist)


# Structures that compose all the information for a candidate match.


class AlbumMatch(NamedTuple):
    distance: Distance
    info: AlbumInfo
    mapping: dict[Item, TrackInfo]
    extra_items: list[Item]
    extra_tracks: list[TrackInfo]


class TrackMatch(NamedTuple):
    distance: Distance
    info: TrackInfo


# Aggregation of sources.


def album_for_mbid(release_id: str) -> AlbumInfo | None:
    """Get an AlbumInfo object for a MusicBrainz release ID. Return None
    if the ID is not found.
    """
    try:
        if album := mb.album_for_id(release_id):
            plugins.send("albuminfo_received", info=album)
        return album
    except mb.MusicBrainzAPIError as exc:
        exc.log(log)
        return None


def track_for_mbid(recording_id: str) -> TrackInfo | None:
    """Get a TrackInfo object for a MusicBrainz recording ID. Return None
    if the ID is not found.
    """
    try:
        if track := mb.track_for_id(recording_id):
            plugins.send("trackinfo_received", info=track)
        return track
    except mb.MusicBrainzAPIError as exc:
        exc.log(log)
        return None


def album_for_id(_id: str) -> AlbumInfo | None:
    """Get AlbumInfo object for the given ID string."""
    return album_for_mbid(_id) or plugins.album_for_id(_id)


def track_for_id(_id: str) -> TrackInfo | None:
    """Get AlbumInfo object for the given ID string."""
    return track_for_mbid(_id) or plugins.track_for_id(_id)


def invoke_mb(call_func: Callable, *args):
    try:
        return call_func(*args)
    except mb.MusicBrainzAPIError as exc:
        exc.log(log)
        return ()


@plugins.notify_info_yielded("albuminfo_received")
def album_candidates(
    items: list[Item],
    artist: str,
    album: str,
    va_likely: bool,
    extra_tags: dict,
) -> Iterable[tuple]:
    """Search for album matches. ``items`` is a list of Item objects
    that make up the album. ``artist`` and ``album`` are the respective
    names (strings), which may be derived from the item list or may be
    entered by the user. ``va_likely`` is a boolean indicating whether
    the album is likely to be a "various artists" release. ``extra_tags``
    is an optional dictionary of additional tags used to further
    constrain the search.
    """

    if config["musicbrainz"]["enabled"]:
        # Base candidates if we have album and artist to match.
        if artist and album:
            yield from invoke_mb(
                mb.match_album, artist, album, len(items), extra_tags
            )

        # Also add VA matches from MusicBrainz where appropriate.
        if va_likely and album:
            yield from invoke_mb(
                mb.match_album, None, album, len(items), extra_tags
            )

    # Candidates from plugins.
    yield from plugins.candidates(items, artist, album, va_likely, extra_tags)


@plugins.notify_info_yielded("trackinfo_received")
def item_candidates(item: Item, artist: str, title: str) -> Iterable[tuple]:
    """Search for item matches. ``item`` is the Item to be matched.
    ``artist`` and ``title`` are strings and either reflect the item or
    are specified by the user.
    """

    # MusicBrainz candidates.
    if config["musicbrainz"]["enabled"] and artist and title:
        yield from invoke_mb(mb.match_track, artist, title)

    # Plugin candidates.
    yield from plugins.item_candidates(item, artist, title)
