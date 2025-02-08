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

"""Tests for the 'beatport' plugin."""

from datetime import timedelta

from beets.test import _common
from beets.test.helper import BeetsTestCase
from beetsplug import beatport


class BeatportTest(BeetsTestCase):
    def _make_release_response(self):
        """Returns a dict that mimics a response from the beatport API.

        The results were retrieved from:
        https://oauth-api.beatport.com/catalog/3/releases?id=1742984
        The list of elements on the returned dict is incomplete, including just
        those required for the tests on this class.
        """
        results = {
            "id": 1742984,
            "type": "release",
            "name": "Charade",
            "slug": "charade",
            "releaseDate": "2016-04-11",
            "publishDate": "2016-04-11",
            "audioFormat": "",
            "category": "Release",
            "currentStatus": "General Content",
            "catalogNumber": "GR089",
            "description": "",
            "label": {
                "id": 24539,
                "name": "Gravitas Recordings",
                "type": "label",
                "slug": "gravitas-recordings",
            },
            "artists": [
                {
                    "id": 326158,
                    "name": "Supersillyus",
                    "slug": "supersillyus",
                    "type": "artist",
                }
            ],
            "genres": [
                {"id": 9, "name": "Breaks", "slug": "breaks", "type": "genre"}
            ],
        }
        return results

    def _make_tracks_response(self):
        """Return a list that mimics a response from the beatport API.

        The results were retrieved from:
        https://oauth-api.beatport.com/catalog/3/tracks?releaseId=1742984
        The list of elements on the returned list is incomplete, including just
        those required for the tests on this class.
        """
        results = [
            {
                "id": 7817567,
                "type": "track",
                "sku": "track-7817567",
                "name": "Mirage a Trois",
                "trackNumber": 1,
                "mixName": "Original Mix",
                "title": "Mirage a Trois (Original Mix)",
                "slug": "mirage-a-trois-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "7:05",
                "lengthMs": 425421,
                "bpm": 90,
                "key": {
                    "standard": {
                        "letter": "G",
                        "sharp": False,
                        "flat": False,
                        "chord": "minor",
                    },
                    "shortName": "Gmin",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
            {
                "id": 7817568,
                "type": "track",
                "sku": "track-7817568",
                "name": "Aeon Bahamut",
                "trackNumber": 2,
                "mixName": "Original Mix",
                "title": "Aeon Bahamut (Original Mix)",
                "slug": "aeon-bahamut-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "7:38",
                "lengthMs": 458000,
                "bpm": 100,
                "key": {
                    "standard": {
                        "letter": "G",
                        "sharp": False,
                        "flat": False,
                        "chord": "major",
                    },
                    "shortName": "Gmaj",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
            {
                "id": 7817569,
                "type": "track",
                "sku": "track-7817569",
                "name": "Trancendental Medication",
                "trackNumber": 3,
                "mixName": "Original Mix",
                "title": "Trancendental Medication (Original Mix)",
                "slug": "trancendental-medication-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "1:08",
                "lengthMs": 68571,
                "bpm": 141,
                "key": {
                    "standard": {
                        "letter": "F",
                        "sharp": False,
                        "flat": False,
                        "chord": "major",
                    },
                    "shortName": "Fmaj",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
            {
                "id": 7817570,
                "type": "track",
                "sku": "track-7817570",
                "name": "A List of Instructions for When I'm Human",
                "trackNumber": 4,
                "mixName": "Original Mix",
                "title": "A List of Instructions for When I'm Human (Original Mix)",
                "slug": "a-list-of-instructions-for-when-im-human-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "6:57",
                "lengthMs": 417913,
                "bpm": 88,
                "key": {
                    "standard": {
                        "letter": "A",
                        "sharp": False,
                        "flat": False,
                        "chord": "minor",
                    },
                    "shortName": "Amin",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
            {
                "id": 7817571,
                "type": "track",
                "sku": "track-7817571",
                "name": "The Great Shenanigan",
                "trackNumber": 5,
                "mixName": "Original Mix",
                "title": "The Great Shenanigan (Original Mix)",
                "slug": "the-great-shenanigan-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "9:49",
                "lengthMs": 589875,
                "bpm": 123,
                "key": {
                    "standard": {
                        "letter": "E",
                        "sharp": False,
                        "flat": True,
                        "chord": "major",
                    },
                    "shortName": "E&#9837;maj",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
            {
                "id": 7817572,
                "type": "track",
                "sku": "track-7817572",
                "name": "Charade",
                "trackNumber": 6,
                "mixName": "Original Mix",
                "title": "Charade (Original Mix)",
                "slug": "charade-original-mix",
                "releaseDate": "2016-04-11",
                "publishDate": "2016-04-11",
                "currentStatus": "General Content",
                "length": "7:05",
                "lengthMs": 425423,
                "bpm": 123,
                "key": {
                    "standard": {
                        "letter": "A",
                        "sharp": False,
                        "flat": False,
                        "chord": "major",
                    },
                    "shortName": "Amaj",
                },
                "artists": [
                    {
                        "id": 326158,
                        "name": "Supersillyus",
                        "slug": "supersillyus",
                        "type": "artist",
                    }
                ],
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
                "release": {
                    "id": 1742984,
                    "name": "Charade",
                    "type": "release",
                    "slug": "charade",
                },
                "label": {
                    "id": 24539,
                    "name": "Gravitas Recordings",
                    "type": "label",
                    "slug": "gravitas-recordings",
                    "status": True,
                },
            },
        ]
        return results

    def setUp(self):
        super().setUp()

        # Set up 'album'.
        response_release = self._make_release_response()
        self.album = beatport.BeatportRelease(response_release)

        # Set up 'tracks'.
        response_tracks = self._make_tracks_response()
        self.tracks = [beatport.BeatportTrack(t) for t in response_tracks]

        # Set up 'test_album'.
        self.test_album = self.mk_test_album()

        # Set up 'test_tracks'
        self.test_tracks = self.test_album.items()

    def mk_test_album(self):
        items = [_common.item() for _ in range(6)]
        for item in items:
            item.album = "Charade"
            item.catalognum = "GR089"
            item.label = "Gravitas Recordings"
            item.artist = "Supersillyus"
            item.year = 2016
            item.comp = False
            item.label_name = "Gravitas Recordings"
            item.genre = "Glitch Hop"
            item.year = 2016
            item.month = 4
            item.day = 11
            item.mix_name = "Original Mix"

        items[0].title = "Mirage a Trois"
        items[1].title = "Aeon Bahamut"
        items[2].title = "Trancendental Medication"
        items[3].title = "A List of Instructions for When I'm Human"
        items[4].title = "The Great Shenanigan"
        items[5].title = "Charade"

        items[0].length = timedelta(minutes=7, seconds=5).total_seconds()
        items[1].length = timedelta(minutes=7, seconds=38).total_seconds()
        items[2].length = timedelta(minutes=1, seconds=8).total_seconds()
        items[3].length = timedelta(minutes=6, seconds=57).total_seconds()
        items[4].length = timedelta(minutes=9, seconds=49).total_seconds()
        items[5].length = timedelta(minutes=7, seconds=5).total_seconds()

        items[0].url = "mirage-a-trois-original-mix"
        items[1].url = "aeon-bahamut-original-mix"
        items[2].url = "trancendental-medication-original-mix"
        items[3].url = "a-list-of-instructions-for-when-im-human-original-mix"
        items[4].url = "the-great-shenanigan-original-mix"
        items[5].url = "charade-original-mix"

        counter = 0
        for item in items:
            counter += 1
            item.track_number = counter

        items[0].bpm = 90
        items[1].bpm = 100
        items[2].bpm = 141
        items[3].bpm = 88
        items[4].bpm = 123
        items[5].bpm = 123

        items[0].initial_key = "Gmin"
        items[1].initial_key = "Gmaj"
        items[2].initial_key = "Fmaj"
        items[3].initial_key = "Amin"
        items[4].initial_key = "E&#9837;maj"
        items[5].initial_key = "Amaj"

        for item in items:
            self.lib.add(item)

        album = self.lib.add_album(items)
        album.store()

        return album

    # Test BeatportRelease.
    def test_album_name_applied(self):
        assert self.album.name == self.test_album["album"]

    def test_catalog_number_applied(self):
        assert self.album.catalog_number == self.test_album["catalognum"]

    def test_label_applied(self):
        assert self.album.label_name == self.test_album["label"]

    def test_category_applied(self):
        assert self.album.category == "Release"

    def test_album_url_applied(self):
        assert self.album.url == "https://beatport.com/release/charade/1742984"

    # Test BeatportTrack.
    def test_title_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert track.name == test_track.title

    def test_mix_name_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert track.mix_name == test_track.mix_name

    def test_length_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert int(track.length.total_seconds()) == int(test_track.length)

    def test_track_url_applied(self):
        # Specify beatport ids here because an 'item.id' is beets-internal.
        ids = [
            7817567,
            7817568,
            7817569,
            7817570,
            7817571,
            7817572,
        ]
        # Concatenate with 'id' to pass strict equality test.
        for track, test_track, id in zip(self.tracks, self.test_tracks, ids):
            assert (
                track.url == f"https://beatport.com/track/{test_track.url}/{id}"
            )

    def test_bpm_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert track.bpm == test_track.bpm

    def test_initial_key_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert track.initial_key == test_track.initial_key

    def test_genre_applied(self):
        for track, test_track in zip(self.tracks, self.test_tracks):
            assert track.genre == test_track.genre


class BeatportResponseEmptyTest(BeetsTestCase):
    def _make_tracks_response(self):
        results = [
            {
                "id": 7817567,
                "name": "Mirage a Trois",
                "genres": [
                    {
                        "id": 9,
                        "name": "Breaks",
                        "slug": "breaks",
                        "type": "genre",
                    }
                ],
                "subGenres": [
                    {
                        "id": 209,
                        "name": "Glitch Hop",
                        "slug": "glitch-hop",
                        "type": "subgenre",
                    }
                ],
            }
        ]
        return results

    def setUp(self):
        super().setUp()

        # Set up 'tracks'.
        self.response_tracks = self._make_tracks_response()
        self.tracks = [beatport.BeatportTrack(t) for t in self.response_tracks]

        # Make alias to be congruent with class `BeatportTest`.
        self.test_tracks = self.response_tracks

    def test_response_tracks_empty(self):
        response_tracks = []
        tracks = [beatport.BeatportTrack(t) for t in response_tracks]
        assert tracks == []

    def test_sub_genre_empty_fallback(self):
        """No 'sub_genre' is provided. Test if fallback to 'genre' works."""
        self.response_tracks[0]["subGenres"] = []
        tracks = [beatport.BeatportTrack(t) for t in self.response_tracks]

        self.test_tracks[0]["subGenres"] = []

        assert tracks[0].genre == self.test_tracks[0]["genres"][0]["name"]

    def test_genre_empty(self):
        """No 'genre' is provided. Test if 'sub_genre' is applied."""
        self.response_tracks[0]["genres"] = []
        tracks = [beatport.BeatportTrack(t) for t in self.response_tracks]

        self.test_tracks[0]["genres"] = []

        assert tracks[0].genre == self.test_tracks[0]["subGenres"][0]["name"]
