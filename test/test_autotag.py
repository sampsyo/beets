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

"""Tests for autotagging functionality."""

import re
import unittest

import pytest

from beets import autotag, config
from beets.autotag import AlbumInfo, TrackInfo, correct_list_fields, match
from beets.autotag.hooks import Distance, string_dist
from beets.library import Item
from beets.test.helper import BeetsTestCase, ConfigMixin
from beets.util import plurality


class PluralityTest(BeetsTestCase):
    def test_plurality_consensus(self):
        objs = [1, 1, 1, 1]
        obj, freq = plurality(objs)
        assert obj == 1
        assert freq == 4

    def test_plurality_near_consensus(self):
        objs = [1, 1, 2, 1]
        obj, freq = plurality(objs)
        assert obj == 1
        assert freq == 3

    def test_plurality_conflict(self):
        objs = [1, 1, 2, 2, 3]
        obj, freq = plurality(objs)
        assert obj in (1, 2)
        assert freq == 2

    def test_plurality_empty_sequence_raises_error(self):
        with pytest.raises(ValueError, match="must be non-empty"):
            plurality([])

    def test_current_metadata_finds_pluralities(self):
        items = [
            Item(artist="The Beetles", album="The White Album"),
            Item(artist="The Beatles", album="The White Album"),
            Item(artist="The Beatles", album="Teh White Album"),
        ]
        likelies, consensus = match.current_metadata(items)
        assert likelies["artist"] == "The Beatles"
        assert likelies["album"] == "The White Album"
        assert not consensus["artist"]

    def test_current_metadata_artist_consensus(self):
        items = [
            Item(artist="The Beatles", album="The White Album"),
            Item(artist="The Beatles", album="The White Album"),
            Item(artist="The Beatles", album="Teh White Album"),
        ]
        likelies, consensus = match.current_metadata(items)
        assert likelies["artist"] == "The Beatles"
        assert likelies["album"] == "The White Album"
        assert consensus["artist"]

    def test_albumartist_consensus(self):
        items = [
            Item(artist="tartist1", album="album", albumartist="aartist"),
            Item(artist="tartist2", album="album", albumartist="aartist"),
            Item(artist="tartist3", album="album", albumartist="aartist"),
        ]
        likelies, consensus = match.current_metadata(items)
        assert likelies["artist"] == "aartist"
        assert not consensus["artist"]

    def test_current_metadata_likelies(self):
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
        items = [Item(**{f: f"{f}_{i or 1}" for f in fields}) for i in range(5)]
        likelies, _ = match.current_metadata(items)
        for f in fields:
            if isinstance(likelies[f], int):
                assert likelies[f] == 0
            else:
                assert likelies[f] == f"{f}_1"


def _make_item(title, track, artist="some artist"):
    return Item(
        title=title,
        track=track,
        artist=artist,
        album="some album",
        length=1,
        mb_trackid="",
        mb_albumid="",
        mb_artistid="",
    )


def _make_trackinfo():
    return [
        TrackInfo(
            title="one", track_id=None, artist="some artist", length=1, index=1
        ),
        TrackInfo(
            title="two", track_id=None, artist="some artist", length=1, index=2
        ),
        TrackInfo(
            title="three",
            track_id=None,
            artist="some artist",
            length=1,
            index=3,
        ),
    ]


def _clear_weights():
    """Hack around the lazy descriptor used to cache weights for
    Distance calculations.
    """
    Distance.__dict__["_weights"].cache = {}


class DistanceTest(BeetsTestCase):
    def tearDown(self):
        super().tearDown()
        _clear_weights()

    def test_add(self):
        dist = Distance()
        dist.add("add", 1.0)
        assert dist._penalties == {"add": [1.0]}

    def test_add_equality(self):
        dist = Distance()
        dist.add_equality("equality", "ghi", ["abc", "def", "ghi"])
        assert dist._penalties["equality"] == [0.0]

        dist.add_equality("equality", "xyz", ["abc", "def", "ghi"])
        assert dist._penalties["equality"] == [0.0, 1.0]

        dist.add_equality("equality", "abc", re.compile(r"ABC", re.I))
        assert dist._penalties["equality"] == [0.0, 1.0, 0.0]

    def test_add_expr(self):
        dist = Distance()
        dist.add_expr("expr", True)
        assert dist._penalties["expr"] == [1.0]

        dist.add_expr("expr", False)
        assert dist._penalties["expr"] == [1.0, 0.0]

    def test_add_number(self):
        dist = Distance()
        # Add a full penalty for each number of difference between two numbers.

        dist.add_number("number", 1, 1)
        assert dist._penalties["number"] == [0.0]

        dist.add_number("number", 1, 2)
        assert dist._penalties["number"] == [0.0, 1.0]

        dist.add_number("number", 2, 1)
        assert dist._penalties["number"] == [0.0, 1.0, 1.0]

        dist.add_number("number", -1, 2)
        assert dist._penalties["number"] == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0]

    def test_add_priority(self):
        dist = Distance()
        dist.add_priority("priority", "abc", "abc")
        assert dist._penalties["priority"] == [0.0]

        dist.add_priority("priority", "def", ["abc", "def"])
        assert dist._penalties["priority"] == [0.0, 0.5]

        dist.add_priority(
            "priority", "gh", ["ab", "cd", "ef", re.compile("GH", re.I)]
        )
        assert dist._penalties["priority"] == [0.0, 0.5, 0.75]

        dist.add_priority("priority", "xyz", ["abc", "def"])
        assert dist._penalties["priority"] == [0.0, 0.5, 0.75, 1.0]

    def test_add_ratio(self):
        dist = Distance()
        dist.add_ratio("ratio", 25, 100)
        assert dist._penalties["ratio"] == [0.25]

        dist.add_ratio("ratio", 10, 5)
        assert dist._penalties["ratio"] == [0.25, 1.0]

        dist.add_ratio("ratio", -5, 5)
        assert dist._penalties["ratio"] == [0.25, 1.0, 0.0]

        dist.add_ratio("ratio", 5, 0)
        assert dist._penalties["ratio"] == [0.25, 1.0, 0.0, 0.0]

    def test_add_string(self):
        dist = Distance()
        sdist = string_dist("abc", "bcd")
        dist.add_string("string", "abc", "bcd")
        assert dist._penalties["string"] == [sdist]
        assert dist._penalties["string"] != [0]

    def test_add_string_none(self):
        dist = Distance()
        dist.add_string("string", None, "string")
        assert dist._penalties["string"] == [1]

    def test_add_string_both_none(self):
        dist = Distance()
        dist.add_string("string", None, None)
        assert dist._penalties["string"] == [0]

    def test_distance(self):
        config["match"]["distance_weights"]["album"] = 2.0
        config["match"]["distance_weights"]["medium"] = 1.0
        _clear_weights()

        dist = Distance()
        dist.add("album", 0.5)
        dist.add("media", 0.25)
        dist.add("media", 0.75)
        assert dist.distance == 0.5

        # __getitem__()
        assert dist["album"] == 0.25
        assert dist["media"] == 0.25

    def test_max_distance(self):
        config["match"]["distance_weights"]["album"] = 3.0
        config["match"]["distance_weights"]["medium"] = 1.0
        _clear_weights()

        dist = Distance()
        dist.add("album", 0.5)
        dist.add("medium", 0.0)
        dist.add("medium", 0.0)
        assert dist.max_distance == 5.0

    def test_operators(self):
        config["match"]["distance_weights"]["source"] = 1.0
        config["match"]["distance_weights"]["album"] = 2.0
        config["match"]["distance_weights"]["medium"] = 1.0
        _clear_weights()

        dist = Distance()
        dist.add("source", 0.0)
        dist.add("album", 0.5)
        dist.add("medium", 0.25)
        dist.add("medium", 0.75)
        assert len(dist) == 2
        assert list(dist) == [("album", 0.2), ("medium", 0.2)]
        assert dist == 0.4
        assert dist < 1.0
        assert dist > 0.0
        assert dist - 0.4 == 0.0
        assert 0.4 - dist == 0.0
        assert float(dist) == 0.4

    def test_raw_distance(self):
        config["match"]["distance_weights"]["album"] = 3.0
        config["match"]["distance_weights"]["medium"] = 1.0
        _clear_weights()

        dist = Distance()
        dist.add("album", 0.5)
        dist.add("medium", 0.25)
        dist.add("medium", 0.5)
        assert dist.raw_distance == 2.25

    def test_items(self):
        config["match"]["distance_weights"]["album"] = 4.0
        config["match"]["distance_weights"]["medium"] = 2.0
        _clear_weights()

        dist = Distance()
        dist.add("album", 0.1875)
        dist.add("medium", 0.75)
        assert dist.items() == [("medium", 0.25), ("album", 0.125)]

        # Sort by key if distance is equal.
        dist = Distance()
        dist.add("album", 0.375)
        dist.add("medium", 0.75)
        assert dist.items() == [("album", 0.25), ("medium", 0.25)]

    def test_update(self):
        dist1 = Distance()
        dist1.add("album", 0.5)
        dist1.add("media", 1.0)

        dist2 = Distance()
        dist2.add("album", 0.75)
        dist2.add("album", 0.25)
        dist2.add("media", 0.05)

        dist1.update(dist2)

        assert dist1._penalties == {
            "album": [0.5, 0.75, 0.25],
            "media": [1.0, 0.05],
        }


class TrackDistanceTest(BeetsTestCase):
    def test_identical_tracks(self):
        item = _make_item("one", 1)
        info = _make_trackinfo()[0]
        dist = match.track_distance(item, info, incl_artist=True)
        assert dist == 0.0

    def test_different_title(self):
        item = _make_item("foo", 1)
        info = _make_trackinfo()[0]
        dist = match.track_distance(item, info, incl_artist=True)
        assert dist != 0.0

    def test_different_artist(self):
        item = _make_item("one", 1)
        item.artist = "foo"
        info = _make_trackinfo()[0]
        dist = match.track_distance(item, info, incl_artist=True)
        assert dist != 0.0

    def test_various_artists_tolerated(self):
        item = _make_item("one", 1)
        item.artist = "Various Artists"
        info = _make_trackinfo()[0]
        dist = match.track_distance(item, info, incl_artist=True)
        assert dist == 0.0


class AlbumDistanceTest(BeetsTestCase):
    def _mapping(self, items, info):
        out = {}
        for i, t in zip(items, info.tracks):
            out[i] = t
        return out

    def _dist(self, items, info):
        return match.distance(items, info, self._mapping(items, info))

    def test_identical_albums(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        assert self._dist(items, info) == 0

    def test_incomplete_album(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        dist = self._dist(items, info)
        assert dist != 0
        # Make sure the distance is not too great
        assert dist < 0.2

    def test_global_artists_differ(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="someone else",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        assert self._dist(items, info) != 0

    def test_comp_track_artists_match(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="should be ignored",
            album="some album",
            tracks=_make_trackinfo(),
            va=True,
        )
        assert self._dist(items, info) == 0

    def test_comp_no_track_artists(self):
        # Some VA releases don't have track artists (incomplete metadata).
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="should be ignored",
            album="some album",
            tracks=_make_trackinfo(),
            va=True,
        )
        info.tracks[0].artist = None
        info.tracks[1].artist = None
        info.tracks[2].artist = None
        assert self._dist(items, info) == 0

    def test_comp_track_artists_do_not_match(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2, "someone else"))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=True,
        )
        assert self._dist(items, info) != 0

    def test_tracks_out_of_order(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("three", 2))
        items.append(_make_item("two", 3))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        dist = self._dist(items, info)
        assert 0 < dist < 0.2

    def test_two_medium_release(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 3))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        info.tracks[0].medium_index = 1
        info.tracks[1].medium_index = 2
        info.tracks[2].medium_index = 1
        dist = self._dist(items, info)
        assert dist == 0

    def test_per_medium_track_numbers(self):
        items = []
        items.append(_make_item("one", 1))
        items.append(_make_item("two", 2))
        items.append(_make_item("three", 1))
        info = AlbumInfo(
            artist="some artist",
            album="some album",
            tracks=_make_trackinfo(),
            va=False,
        )
        info.tracks[0].medium_index = 1
        info.tracks[1].medium_index = 2
        info.tracks[2].medium_index = 1
        dist = self._dist(items, info)
        assert dist == 0


class TestAssignment(ConfigMixin):
    A = "one"
    B = "two"
    C = "three"

    @pytest.fixture(autouse=True)
    def _setup_config(self):
        self.config["match"]["track_length_grace"] = 10
        self.config["match"]["track_length_max"] = 30

    @pytest.mark.parametrize(
        # 'expected' is a tuple of expected (mapping, extra_items, extra_tracks)
        "item_titles, track_titles, expected",
        [
            # items ordering gets corrected
            ([A, C, B], [A, B, C], ({A: A, B: B, C: C}, [], [])),
            # unmatched tracks are returned as 'extra_tracks'
            # the first track is unmatched
            ([B, C], [A, B, C], ({B: B, C: C}, [], [A])),
            # the middle track is unmatched
            ([A, C], [A, B, C], ({A: A, C: C}, [], [B])),
            # the last track is unmatched
            ([A, B], [A, B, C], ({A: A, B: B}, [], [C])),
            # unmatched items are returned as 'extra_items'
            ([A, C, B], [A, C], ({A: A, C: C}, [B], [])),
        ],
    )
    def test_assign_tracks(self, item_titles, track_titles, expected):
        expected_mapping, expected_extra_items, expected_extra_tracks = expected

        items = [Item(title=title) for title in item_titles]
        tracks = [TrackInfo(title=title) for title in track_titles]

        mapping, extra_items, extra_tracks = match.assign_items(items, tracks)

        assert (
            {i.title: t.title for i, t in mapping.items()},
            [i.title for i in extra_items],
            [t.title for t in extra_tracks],
        ) == (expected_mapping, expected_extra_items, expected_extra_tracks)

    def test_order_works_when_track_names_are_entirely_wrong(self):
        # A real-world test case contributed by a user.
        def item(i, length):
            return Item(
                artist="ben harper",
                album="burn to shine",
                title=f"ben harper - Burn to Shine {i}",
                track=i,
                length=length,
            )

        items = []
        items.append(item(1, 241.37243007106997))
        items.append(item(2, 342.27781704375036))
        items.append(item(3, 245.95070222338137))
        items.append(item(4, 472.87662515485437))
        items.append(item(5, 279.1759535763187))
        items.append(item(6, 270.33333768012))
        items.append(item(7, 247.83435613222923))
        items.append(item(8, 216.54504531525072))
        items.append(item(9, 225.72775379800484))
        items.append(item(10, 317.7643606963552))
        items.append(item(11, 243.57001238834192))
        items.append(item(12, 186.45916150485752))

        def info(index, title, length):
            return TrackInfo(title=title, length=length, index=index)

        trackinfo = []
        trackinfo.append(info(1, "Alone", 238.893))
        trackinfo.append(info(2, "The Woman in You", 341.44))
        trackinfo.append(info(3, "Less", 245.59999999999999))
        trackinfo.append(info(4, "Two Hands of a Prayer", 470.49299999999999))
        trackinfo.append(info(5, "Please Bleed", 277.86599999999999))
        trackinfo.append(info(6, "Suzie Blue", 269.30599999999998))
        trackinfo.append(info(7, "Steal My Kisses", 245.36000000000001))
        trackinfo.append(info(8, "Burn to Shine", 214.90600000000001))
        trackinfo.append(info(9, "Show Me a Little Shame", 224.0929999999999))
        trackinfo.append(info(10, "Forgiven", 317.19999999999999))
        trackinfo.append(info(11, "Beloved One", 243.733))
        trackinfo.append(info(12, "In the Lord's Arms", 186.13300000000001))

        expected = dict(zip(items, trackinfo)), [], []

        assert match.assign_items(items, trackinfo) == expected


class ApplyTestUtil:
    def _apply(self, info=None, per_disc_numbering=False, artist_credit=False):
        info = info or self.info
        mapping = {}
        for i, t in zip(self.items, info.tracks):
            mapping[i] = t
        config["per_disc_numbering"] = per_disc_numbering
        config["artist_credit"] = artist_credit
        autotag.apply_metadata(info, mapping)


class ApplyTest(BeetsTestCase, ApplyTestUtil):
    def setUp(self):
        super().setUp()

        self.items = []
        self.items.append(Item({}))
        self.items.append(Item({}))
        trackinfo = []
        trackinfo.append(
            TrackInfo(
                title="oneNew",
                track_id="dfa939ec-118c-4d0f-84a0-60f3d1e6522c",
                medium=1,
                medium_index=1,
                medium_total=1,
                index=1,
                artist_credit="trackArtistCredit",
                artists_credit=["trackArtistCredit"],
                artist_sort="trackArtistSort",
                artists_sort=["trackArtistSort"],
            )
        )
        trackinfo.append(
            TrackInfo(
                title="twoNew",
                track_id="40130ed1-a27c-42fd-a328-1ebefb6caef4",
                medium=2,
                medium_index=1,
                index=2,
                medium_total=1,
            )
        )
        self.info = AlbumInfo(
            tracks=trackinfo,
            artist="artistNew",
            artists=["artistNew", "artistNew2"],
            album="albumNew",
            album_id="7edb51cb-77d6-4416-a23c-3a8c2994a2c7",
            artist_id="a6623d39-2d8e-4f70-8242-0a9553b91e50",
            artists_ids=[
                "a6623d39-2d8e-4f70-8242-0a9553b91e50",
                "a6623d39-2d8e-4f70-8242-0a9553b91e51",
            ],
            artist_credit="albumArtistCredit",
            artists_credit=["albumArtistCredit", "albumArtistCredit2"],
            artist_sort="albumArtistSort",
            artists_sort=["albumArtistSort", "albumArtistSort2"],
            albumtype="album",
            va=False,
            mediums=2,
        )

    def test_titles_applied(self):
        self._apply()
        assert self.items[0].title == "oneNew"
        assert self.items[1].title == "twoNew"

    def test_album_and_artist_applied_to_all(self):
        self._apply()
        assert self.items[0].album == "albumNew"
        assert self.items[1].album == "albumNew"
        assert self.items[0].artist == "artistNew"
        assert self.items[1].artist == "artistNew"
        assert self.items[0].artists == ["artistNew", "artistNew2"]
        assert self.items[1].artists == ["artistNew", "artistNew2"]
        assert self.items[0].albumartists == ["artistNew", "artistNew2"]
        assert self.items[1].albumartists == ["artistNew", "artistNew2"]

    def test_track_index_applied(self):
        self._apply()
        assert self.items[0].track == 1
        assert self.items[1].track == 2

    def test_track_total_applied(self):
        self._apply()
        assert self.items[0].tracktotal == 2
        assert self.items[1].tracktotal == 2

    def test_disc_index_applied(self):
        self._apply()
        assert self.items[0].disc == 1
        assert self.items[1].disc == 2

    def test_disc_total_applied(self):
        self._apply()
        assert self.items[0].disctotal == 2
        assert self.items[1].disctotal == 2

    def test_per_disc_numbering(self):
        self._apply(per_disc_numbering=True)
        assert self.items[0].track == 1
        assert self.items[1].track == 1

    def test_per_disc_numbering_track_total(self):
        self._apply(per_disc_numbering=True)
        assert self.items[0].tracktotal == 1
        assert self.items[1].tracktotal == 1

    def test_artist_credit(self):
        self._apply(artist_credit=True)
        assert self.items[0].artist == "trackArtistCredit"
        assert self.items[1].artist == "albumArtistCredit"
        assert self.items[0].albumartist == "albumArtistCredit"
        assert self.items[1].albumartist == "albumArtistCredit"
        assert self.items[0].albumartists == [
            "albumArtistCredit",
            "albumArtistCredit2",
        ]
        assert self.items[1].albumartists == [
            "albumArtistCredit",
            "albumArtistCredit2",
        ]

    def test_artist_credit_prefers_artist_over_albumartist_credit(self):
        self.info.tracks[0].artist = "oldArtist"
        self.info.tracks[0].artist_credit = None
        self._apply(artist_credit=True)
        assert self.items[0].artist == "oldArtist"

    def test_artist_credit_falls_back_to_albumartist(self):
        self.info.artist_credit = None
        self._apply(artist_credit=True)
        assert self.items[1].artist == "artistNew"

    def test_mb_trackid_applied(self):
        self._apply()
        assert (
            self.items[0].mb_trackid == "dfa939ec-118c-4d0f-84a0-60f3d1e6522c"
        )
        assert (
            self.items[1].mb_trackid == "40130ed1-a27c-42fd-a328-1ebefb6caef4"
        )

    def test_mb_albumid_and_artistid_applied(self):
        self._apply()
        for item in self.items:
            assert item.mb_albumid == "7edb51cb-77d6-4416-a23c-3a8c2994a2c7"
            assert item.mb_artistid == "a6623d39-2d8e-4f70-8242-0a9553b91e50"
            assert item.mb_artistids == [
                "a6623d39-2d8e-4f70-8242-0a9553b91e50",
                "a6623d39-2d8e-4f70-8242-0a9553b91e51",
            ]

    def test_albumtype_applied(self):
        self._apply()
        assert self.items[0].albumtype == "album"
        assert self.items[1].albumtype == "album"

    def test_album_artist_overrides_empty_track_artist(self):
        my_info = self.info.copy()
        self._apply(info=my_info)
        assert self.items[0].artist == "artistNew"
        assert self.items[1].artist == "artistNew"
        assert self.items[0].artists == ["artistNew", "artistNew2"]
        assert self.items[1].artists == ["artistNew", "artistNew2"]

    def test_album_artist_overridden_by_nonempty_track_artist(self):
        my_info = self.info.copy()
        my_info.tracks[0].artist = "artist1!"
        my_info.tracks[1].artist = "artist2!"
        my_info.tracks[0].artists = ["artist1!", "artist1!!"]
        my_info.tracks[1].artists = ["artist2!", "artist2!!"]
        self._apply(info=my_info)
        assert self.items[0].artist == "artist1!"
        assert self.items[1].artist == "artist2!"
        assert self.items[0].artists == ["artist1!", "artist1!!"]
        assert self.items[1].artists == ["artist2!", "artist2!!"]

    def test_artist_credit_applied(self):
        self._apply()
        assert self.items[0].albumartist_credit == "albumArtistCredit"
        assert self.items[0].albumartists_credit == [
            "albumArtistCredit",
            "albumArtistCredit2",
        ]
        assert self.items[0].artist_credit == "trackArtistCredit"
        assert self.items[0].artists_credit == ["trackArtistCredit"]
        assert self.items[1].albumartist_credit == "albumArtistCredit"
        assert self.items[1].albumartists_credit == [
            "albumArtistCredit",
            "albumArtistCredit2",
        ]
        assert self.items[1].artist_credit == "albumArtistCredit"
        assert self.items[1].artists_credit == [
            "albumArtistCredit",
            "albumArtistCredit2",
        ]

    def test_artist_sort_applied(self):
        self._apply()
        assert self.items[0].albumartist_sort == "albumArtistSort"
        assert self.items[0].albumartists_sort == [
            "albumArtistSort",
            "albumArtistSort2",
        ]
        assert self.items[0].artist_sort == "trackArtistSort"
        assert self.items[0].artists_sort == ["trackArtistSort"]
        assert self.items[1].albumartist_sort == "albumArtistSort"
        assert self.items[1].albumartists_sort == [
            "albumArtistSort",
            "albumArtistSort2",
        ]
        assert self.items[1].artist_sort == "albumArtistSort"
        assert self.items[1].artists_sort == [
            "albumArtistSort",
            "albumArtistSort2",
        ]

    def test_full_date_applied(self):
        my_info = self.info.copy()
        my_info.year = 2013
        my_info.month = 12
        my_info.day = 18
        self._apply(info=my_info)

        assert self.items[0].year == 2013
        assert self.items[0].month == 12
        assert self.items[0].day == 18

    def test_date_only_zeros_month_and_day(self):
        self.items = []
        self.items.append(Item(year=1, month=2, day=3))
        self.items.append(Item(year=4, month=5, day=6))

        my_info = self.info.copy()
        my_info.year = 2013
        self._apply(info=my_info)

        assert self.items[0].year == 2013
        assert self.items[0].month == 0
        assert self.items[0].day == 0

    def test_missing_date_applies_nothing(self):
        self.items = []
        self.items.append(Item(year=1, month=2, day=3))
        self.items.append(Item(year=4, month=5, day=6))

        self._apply()

        assert self.items[0].year == 1
        assert self.items[0].month == 2
        assert self.items[0].day == 3

    def test_data_source_applied(self):
        my_info = self.info.copy()
        my_info.data_source = "MusicBrainz"
        self._apply(info=my_info)

        assert self.items[0].data_source == "MusicBrainz"


class ApplyCompilationTest(BeetsTestCase, ApplyTestUtil):
    def setUp(self):
        super().setUp()

        self.items = []
        self.items.append(Item({}))
        self.items.append(Item({}))
        trackinfo = []
        trackinfo.append(
            TrackInfo(
                title="oneNew",
                track_id="dfa939ec-118c-4d0f-84a0-60f3d1e6522c",
                artist="artistOneNew",
                artist_id="a05686fc-9db2-4c23-b99e-77f5db3e5282",
                index=1,
            )
        )
        trackinfo.append(
            TrackInfo(
                title="twoNew",
                track_id="40130ed1-a27c-42fd-a328-1ebefb6caef4",
                artist="artistTwoNew",
                artist_id="80b3cf5e-18fe-4c59-98c7-e5bb87210710",
                index=2,
            )
        )
        self.info = AlbumInfo(
            tracks=trackinfo,
            artist="variousNew",
            album="albumNew",
            album_id="3b69ea40-39b8-487f-8818-04b6eff8c21a",
            artist_id="89ad4ac3-39f7-470e-963a-56509c546377",
            albumtype="compilation",
        )

    def test_album_and_track_artists_separate(self):
        self._apply()
        assert self.items[0].artist == "artistOneNew"
        assert self.items[1].artist == "artistTwoNew"
        assert self.items[0].albumartist == "variousNew"
        assert self.items[1].albumartist == "variousNew"

    def test_mb_albumartistid_applied(self):
        self._apply()
        assert (
            self.items[0].mb_albumartistid
            == "89ad4ac3-39f7-470e-963a-56509c546377"
        )
        assert (
            self.items[1].mb_albumartistid
            == "89ad4ac3-39f7-470e-963a-56509c546377"
        )
        assert (
            self.items[0].mb_artistid == "a05686fc-9db2-4c23-b99e-77f5db3e5282"
        )
        assert (
            self.items[1].mb_artistid == "80b3cf5e-18fe-4c59-98c7-e5bb87210710"
        )

    def test_va_flag_cleared_does_not_set_comp(self):
        self._apply()
        assert not self.items[0].comp
        assert not self.items[1].comp

    def test_va_flag_sets_comp(self):
        va_info = self.info.copy()
        va_info.va = True
        self._apply(info=va_info)
        assert self.items[0].comp
        assert self.items[1].comp


class StringDistanceTest(unittest.TestCase):
    def test_equal_strings(self):
        dist = string_dist("Some String", "Some String")
        assert dist == 0.0

    def test_different_strings(self):
        dist = string_dist("Some String", "Totally Different")
        assert dist != 0.0

    def test_punctuation_ignored(self):
        dist = string_dist("Some String", "Some.String!")
        assert dist == 0.0

    def test_case_ignored(self):
        dist = string_dist("Some String", "sOME sTring")
        assert dist == 0.0

    def test_leading_the_has_lower_weight(self):
        dist1 = string_dist("XXX Band Name", "Band Name")
        dist2 = string_dist("The Band Name", "Band Name")
        assert dist2 < dist1

    def test_parens_have_lower_weight(self):
        dist1 = string_dist("One .Two.", "One")
        dist2 = string_dist("One (Two)", "One")
        assert dist2 < dist1

    def test_brackets_have_lower_weight(self):
        dist1 = string_dist("One .Two.", "One")
        dist2 = string_dist("One [Two]", "One")
        assert dist2 < dist1

    def test_ep_label_has_zero_weight(self):
        dist = string_dist("My Song (EP)", "My Song")
        assert dist == 0.0

    def test_featured_has_lower_weight(self):
        dist1 = string_dist("My Song blah Someone", "My Song")
        dist2 = string_dist("My Song feat Someone", "My Song")
        assert dist2 < dist1

    def test_postfix_the(self):
        dist = string_dist("The Song Title", "Song Title, The")
        assert dist == 0.0

    def test_postfix_a(self):
        dist = string_dist("A Song Title", "Song Title, A")
        assert dist == 0.0

    def test_postfix_an(self):
        dist = string_dist("An Album Title", "Album Title, An")
        assert dist == 0.0

    def test_empty_strings(self):
        dist = string_dist("", "")
        assert dist == 0.0

    def test_solo_pattern(self):
        # Just make sure these don't crash.
        string_dist("The ", "")
        string_dist("(EP)", "(EP)")
        string_dist(", An", "")

    def test_heuristic_does_not_harm_distance(self):
        dist = string_dist("Untitled", "[Untitled]")
        assert dist == 0.0

    def test_ampersand_expansion(self):
        dist = string_dist("And", "&")
        assert dist == 0.0

    def test_accented_characters(self):
        dist = string_dist("\xe9\xe1\xf1", "ean")
        assert dist == 0.0


@pytest.mark.parametrize(
    "single_field,list_field",
    [
        ("mb_artistid", "mb_artistids"),
        ("mb_albumartistid", "mb_albumartistids"),
        ("albumtype", "albumtypes"),
    ],
)
@pytest.mark.parametrize(
    "single_value,list_value",
    [
        (None, []),
        (None, ["1"]),
        (None, ["1", "2"]),
        ("1", []),
        ("1", ["1"]),
        ("1", ["1", "2"]),
        ("1", ["2", "1"]),
    ],
)
def test_correct_list_fields(
    single_field, list_field, single_value, list_value
):
    """Ensure that the first value in a list field matches the single field."""
    data = {single_field: single_value, list_field: list_value}
    item = Item(**data)

    correct_list_fields(item)

    single_val, list_val = item[single_field], item[list_field]
    assert (not single_val and not list_val) or single_val == list_val[0]
