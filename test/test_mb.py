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

"""Tests for MusicBrainz API wrapper."""

from unittest import mock

from beets import config
from beets.autotag import mb
from beets.test.helper import BeetsTestCase


class MBAlbumInfoTest(BeetsTestCase):
    def _make_release(
        self,
        date_str="2009",
        tracks=None,
        track_length=None,
        track_artist=False,
        multi_artist_credit=False,
        data_tracks=None,
        medium_format="FORMAT",
    ):
        release = {
            "title": "ALBUM TITLE",
            "id": "ALBUM ID",
            "asin": "ALBUM ASIN",
            "disambiguation": "R_DISAMBIGUATION",
            "release-group": {
                "type": "Album",
                "first-release-date": date_str,
                "id": "RELEASE GROUP ID",
                "disambiguation": "RG_DISAMBIGUATION",
            },
            "artist-credit": [
                {
                    "artist": {
                        "name": "ARTIST NAME",
                        "id": "ARTIST ID",
                        "sort-name": "ARTIST SORT NAME",
                    },
                    "name": "ARTIST CREDIT",
                }
            ],
            "date": "3001",
            "medium-list": [],
            "label-info-list": [
                {
                    "catalog-number": "CATALOG NUMBER",
                    "label": {"name": "LABEL NAME"},
                }
            ],
            "text-representation": {
                "script": "SCRIPT",
                "language": "LANGUAGE",
            },
            "country": "COUNTRY",
            "status": "STATUS",
            "barcode": "BARCODE",
        }

        if multi_artist_credit:
            release["artist-credit"].append(" & ")  # add join phase
            release["artist-credit"].append(
                {
                    "artist": {
                        "name": "ARTIST 2 NAME",
                        "id": "ARTIST 2 ID",
                        "sort-name": "ARTIST 2 SORT NAME",
                    },
                    "name": "ARTIST MULTI CREDIT",
                }
            )

        i = 0
        track_list = []
        if tracks:
            for recording in tracks:
                i += 1
                track = {
                    "id": "RELEASE TRACK ID %d" % i,
                    "recording": recording,
                    "position": i,
                    "number": "A1",
                }
                if track_length:
                    # Track lengths are distinct from recording lengths.
                    track["length"] = track_length
                if track_artist:
                    # Similarly, track artists can differ from recording
                    # artists.
                    track["artist-credit"] = [
                        {
                            "artist": {
                                "name": "TRACK ARTIST NAME",
                                "id": "TRACK ARTIST ID",
                                "sort-name": "TRACK ARTIST SORT NAME",
                            },
                            "name": "TRACK ARTIST CREDIT",
                        }
                    ]

                    if multi_artist_credit:
                        track["artist-credit"].append(" & ")  # add join phase
                        track["artist-credit"].append(
                            {
                                "artist": {
                                    "name": "TRACK ARTIST 2 NAME",
                                    "id": "TRACK ARTIST 2 ID",
                                    "sort-name": "TRACK ARTIST 2 SORT NAME",
                                },
                                "name": "TRACK ARTIST 2 CREDIT",
                            }
                        )

                track_list.append(track)
        data_track_list = []
        if data_tracks:
            for recording in data_tracks:
                i += 1
                data_track = {
                    "id": "RELEASE TRACK ID %d" % i,
                    "recording": recording,
                    "position": i,
                    "number": "A1",
                }
                data_track_list.append(data_track)
        release["medium-list"].append(
            {
                "position": "1",
                "track-list": track_list,
                "data-track-list": data_track_list,
                "format": medium_format,
                "title": "MEDIUM TITLE",
            }
        )
        return release

    def _make_track(
        self,
        title,
        tr_id,
        duration,
        artist=False,
        video=False,
        disambiguation=None,
        remixer=False,
        multi_artist_credit=False,
    ):
        track = {
            "title": title,
            "id": tr_id,
        }
        if duration is not None:
            track["length"] = duration
        if artist:
            track["artist-credit"] = [
                {
                    "artist": {
                        "name": "RECORDING ARTIST NAME",
                        "id": "RECORDING ARTIST ID",
                        "sort-name": "RECORDING ARTIST SORT NAME",
                    },
                    "name": "RECORDING ARTIST CREDIT",
                }
            ]
            if multi_artist_credit:
                track["artist-credit"].append(" & ")  # add join phase
                track["artist-credit"].append(
                    {
                        "artist": {
                            "name": "RECORDING ARTIST 2 NAME",
                            "id": "RECORDING ARTIST 2 ID",
                            "sort-name": "RECORDING ARTIST 2 SORT NAME",
                        },
                        "name": "RECORDING ARTIST 2 CREDIT",
                    }
                )
        if remixer:
            track["artist-relation-list"] = [
                {
                    "type": "remixer",
                    "type-id": "RELATION TYPE ID",
                    "target": "RECORDING REMIXER ARTIST ID",
                    "direction": "RECORDING RELATION DIRECTION",
                    "artist": {
                        "id": "RECORDING REMIXER ARTIST ID",
                        "type": "RECORDING REMIXER ARTIST TYPE",
                        "name": "RECORDING REMIXER ARTIST NAME",
                        "sort-name": "RECORDING REMIXER ARTIST SORT NAME",
                    },
                }
            ]
        if video:
            track["video"] = "true"
        if disambiguation:
            track["disambiguation"] = disambiguation
        return track

    def test_parse_release_with_year(self):
        release = self._make_release("1984")
        d = mb.album_info(release)
        assert d.album == "ALBUM TITLE"
        assert d.album_id == "ALBUM ID"
        assert d.artist == "ARTIST NAME"
        assert d.artist_id == "ARTIST ID"
        assert d.original_year == 1984
        assert d.year == 3001
        assert d.artist_credit == "ARTIST CREDIT"

    def test_parse_release_type(self):
        release = self._make_release("1984")
        d = mb.album_info(release)
        assert d.albumtype == "album"

    def test_parse_release_full_date(self):
        release = self._make_release("1987-03-31")
        d = mb.album_info(release)
        assert d.original_year == 1987
        assert d.original_month == 3
        assert d.original_day == 31

    def test_parse_tracks(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)

        d = mb.album_info(release)
        t = d.tracks
        assert len(t) == 2
        assert t[0].title == "TITLE ONE"
        assert t[0].track_id == "ID ONE"
        assert t[0].length == 100.0
        assert t[1].title == "TITLE TWO"
        assert t[1].track_id == "ID TWO"
        assert t[1].length == 200.0

    def test_parse_track_indices(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)

        d = mb.album_info(release)
        t = d.tracks
        assert t[0].medium_index == 1
        assert t[0].index == 1
        assert t[1].medium_index == 2
        assert t[1].index == 2

    def test_parse_medium_numbers_single_medium(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)

        d = mb.album_info(release)
        assert d.mediums == 1
        t = d.tracks
        assert t[0].medium == 1
        assert t[1].medium == 1

    def test_parse_medium_numbers_two_mediums(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=[tracks[0]])
        second_track_list = [
            {
                "id": "RELEASE TRACK ID 2",
                "recording": tracks[1],
                "position": "1",
                "number": "A1",
            }
        ]
        release["medium-list"].append(
            {
                "position": "2",
                "track-list": second_track_list,
            }
        )

        d = mb.album_info(release)
        assert d.mediums == 2
        t = d.tracks
        assert t[0].medium == 1
        assert t[0].medium_index == 1
        assert t[0].index == 1
        assert t[1].medium == 2
        assert t[1].medium_index == 1
        assert t[1].index == 2

    def test_parse_release_year_month_only(self):
        release = self._make_release("1987-03")
        d = mb.album_info(release)
        assert d.original_year == 1987
        assert d.original_month == 3

    def test_no_durations(self):
        tracks = [self._make_track("TITLE", "ID", None)]
        release = self._make_release(tracks=tracks)
        d = mb.album_info(release)
        assert d.tracks[0].length is None

    def test_track_length_overrides_recording_length(self):
        tracks = [self._make_track("TITLE", "ID", 1.0 * 1000.0)]
        release = self._make_release(tracks=tracks, track_length=2.0 * 1000.0)
        d = mb.album_info(release)
        assert d.tracks[0].length == 2.0

    def test_no_release_date(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert not d.original_year
        assert not d.original_month
        assert not d.original_day

    def test_various_artists_defaults_false(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert not d.va

    def test_detect_various_artists(self):
        release = self._make_release(None)
        release["artist-credit"][0]["artist"]["id"] = mb.VARIOUS_ARTISTS_ID
        d = mb.album_info(release)
        assert d.va

    def test_parse_artist_sort_name(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.artist_sort == "ARTIST SORT NAME"

    def test_parse_releasegroupid(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.releasegroup_id == "RELEASE GROUP ID"

    def test_parse_asin(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.asin == "ALBUM ASIN"

    def test_parse_catalognum(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.catalognum == "CATALOG NUMBER"

    def test_parse_textrepr(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.script == "SCRIPT"
        assert d.language == "LANGUAGE"

    def test_parse_country(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.country == "COUNTRY"

    def test_parse_status(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.albumstatus == "STATUS"

    def test_parse_barcode(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.barcode == "BARCODE"

    def test_parse_media(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(None, tracks=tracks)
        d = mb.album_info(release)
        assert d.media == "FORMAT"

    def test_parse_disambig(self):
        release = self._make_release(None)
        d = mb.album_info(release)
        assert d.albumdisambig == "R_DISAMBIGUATION"
        assert d.releasegroupdisambig == "RG_DISAMBIGUATION"

    def test_parse_disctitle(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(None, tracks=tracks)
        d = mb.album_info(release)
        t = d.tracks
        assert t[0].disctitle == "MEDIUM TITLE"
        assert t[1].disctitle == "MEDIUM TITLE"

    def test_missing_language(self):
        release = self._make_release(None)
        del release["text-representation"]["language"]
        d = mb.album_info(release)
        assert d.language is None

    def test_parse_recording_artist(self):
        tracks = [self._make_track("a", "b", 1, True)]
        release = self._make_release(None, tracks=tracks)
        track = mb.album_info(release).tracks[0]
        assert track.artist == "RECORDING ARTIST NAME"
        assert track.artist_id == "RECORDING ARTIST ID"
        assert track.artist_sort == "RECORDING ARTIST SORT NAME"
        assert track.artist_credit == "RECORDING ARTIST CREDIT"

    def test_parse_recording_artist_multi(self):
        tracks = [self._make_track("a", "b", 1, True, multi_artist_credit=True)]
        release = self._make_release(None, tracks=tracks)
        track = mb.album_info(release).tracks[0]
        assert track.artist == "RECORDING ARTIST NAME & RECORDING ARTIST 2 NAME"
        assert track.artist_id == "RECORDING ARTIST ID"
        assert (
            track.artist_sort
            == "RECORDING ARTIST SORT NAME & RECORDING ARTIST 2 SORT NAME"
        )
        assert (
            track.artist_credit
            == "RECORDING ARTIST CREDIT & RECORDING ARTIST 2 CREDIT"
        )

        assert track.artists == [
            "RECORDING ARTIST NAME",
            "RECORDING ARTIST 2 NAME",
        ]
        assert track.artists_ids == [
            "RECORDING ARTIST ID",
            "RECORDING ARTIST 2 ID",
        ]
        assert track.artists_sort == [
            "RECORDING ARTIST SORT NAME",
            "RECORDING ARTIST 2 SORT NAME",
        ]
        assert track.artists_credit == [
            "RECORDING ARTIST CREDIT",
            "RECORDING ARTIST 2 CREDIT",
        ]

    def test_track_artist_overrides_recording_artist(self):
        tracks = [self._make_track("a", "b", 1, True)]
        release = self._make_release(None, tracks=tracks, track_artist=True)
        track = mb.album_info(release).tracks[0]
        assert track.artist == "TRACK ARTIST NAME"
        assert track.artist_id == "TRACK ARTIST ID"
        assert track.artist_sort == "TRACK ARTIST SORT NAME"
        assert track.artist_credit == "TRACK ARTIST CREDIT"

    def test_track_artist_overrides_recording_artist_multi(self):
        tracks = [self._make_track("a", "b", 1, True, multi_artist_credit=True)]
        release = self._make_release(
            None, tracks=tracks, track_artist=True, multi_artist_credit=True
        )
        track = mb.album_info(release).tracks[0]
        assert track.artist == "TRACK ARTIST NAME & TRACK ARTIST 2 NAME"
        assert track.artist_id == "TRACK ARTIST ID"
        assert (
            track.artist_sort
            == "TRACK ARTIST SORT NAME & TRACK ARTIST 2 SORT NAME"
        )
        assert (
            track.artist_credit == "TRACK ARTIST CREDIT & TRACK ARTIST 2 CREDIT"
        )

        assert track.artists == ["TRACK ARTIST NAME", "TRACK ARTIST 2 NAME"]
        assert track.artists_ids == ["TRACK ARTIST ID", "TRACK ARTIST 2 ID"]
        assert track.artists_sort == [
            "TRACK ARTIST SORT NAME",
            "TRACK ARTIST 2 SORT NAME",
        ]
        assert track.artists_credit == [
            "TRACK ARTIST CREDIT",
            "TRACK ARTIST 2 CREDIT",
        ]

    def test_parse_recording_remixer(self):
        tracks = [self._make_track("a", "b", 1, remixer=True)]
        release = self._make_release(None, tracks=tracks)
        track = mb.album_info(release).tracks[0]
        assert track.remixer == "RECORDING REMIXER ARTIST NAME"

    def test_data_source(self):
        release = self._make_release()
        d = mb.album_info(release)
        assert d.data_source == "MusicBrainz"

    def test_ignored_media(self):
        config["match"]["ignored_media"] = ["IGNORED1", "IGNORED2"]
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks, medium_format="IGNORED1")
        d = mb.album_info(release)
        assert len(d.tracks) == 0

    def test_no_ignored_media(self):
        config["match"]["ignored_media"] = ["IGNORED1", "IGNORED2"]
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks, medium_format="NON-IGNORED")
        d = mb.album_info(release)
        assert len(d.tracks) == 2

    def test_skip_data_track(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("[data track]", "ID DATA TRACK", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 2
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"

    def test_skip_audio_data_tracks_by_default(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        data_tracks = [
            self._make_track(
                "TITLE AUDIO DATA", "ID DATA TRACK", 100.0 * 1000.0
            )
        ]
        release = self._make_release(tracks=tracks, data_tracks=data_tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 2
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"

    def test_no_skip_audio_data_tracks_if_configured(self):
        config["match"]["ignore_data_tracks"] = False
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        data_tracks = [
            self._make_track(
                "TITLE AUDIO DATA", "ID DATA TRACK", 100.0 * 1000.0
            )
        ]
        release = self._make_release(tracks=tracks, data_tracks=data_tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 3
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"
        assert d.tracks[2].title == "TITLE AUDIO DATA"

    def test_skip_video_tracks_by_default(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track(
                "TITLE VIDEO", "ID VIDEO", 100.0 * 1000.0, False, True
            ),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 2
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"

    def test_skip_video_data_tracks_by_default(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        data_tracks = [
            self._make_track(
                "TITLE VIDEO", "ID VIDEO", 100.0 * 1000.0, False, True
            )
        ]
        release = self._make_release(tracks=tracks, data_tracks=data_tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 2
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"

    def test_no_skip_video_tracks_if_configured(self):
        config["match"]["ignore_data_tracks"] = False
        config["match"]["ignore_video_tracks"] = False
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track(
                "TITLE VIDEO", "ID VIDEO", 100.0 * 1000.0, False, True
            ),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        release = self._make_release(tracks=tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 3
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE VIDEO"
        assert d.tracks[2].title == "TITLE TWO"

    def test_no_skip_video_data_tracks_if_configured(self):
        config["match"]["ignore_data_tracks"] = False
        config["match"]["ignore_video_tracks"] = False
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track("TITLE TWO", "ID TWO", 200.0 * 1000.0),
        ]
        data_tracks = [
            self._make_track(
                "TITLE VIDEO", "ID VIDEO", 100.0 * 1000.0, False, True
            )
        ]
        release = self._make_release(tracks=tracks, data_tracks=data_tracks)
        d = mb.album_info(release)
        assert len(d.tracks) == 3
        assert d.tracks[0].title == "TITLE ONE"
        assert d.tracks[1].title == "TITLE TWO"
        assert d.tracks[2].title == "TITLE VIDEO"

    def test_track_disambiguation(self):
        tracks = [
            self._make_track("TITLE ONE", "ID ONE", 100.0 * 1000.0),
            self._make_track(
                "TITLE TWO",
                "ID TWO",
                200.0 * 1000.0,
                disambiguation="SECOND TRACK",
            ),
        ]
        release = self._make_release(tracks=tracks)

        d = mb.album_info(release)
        t = d.tracks
        assert len(t) == 2
        assert t[0].trackdisambig is None
        assert t[1].trackdisambig == "SECOND TRACK"


class ParseIDTest(BeetsTestCase):
    def test_parse_id_correct(self):
        id_string = "28e32c71-1450-463e-92bf-e0a46446fc11"
        out = mb._parse_id(id_string)
        assert out == id_string

    def test_parse_id_non_id_returns_none(self):
        id_string = "blah blah"
        out = mb._parse_id(id_string)
        assert out is None

    def test_parse_id_url_finds_id(self):
        id_string = "28e32c71-1450-463e-92bf-e0a46446fc11"
        id_url = "https://musicbrainz.org/entity/%s" % id_string
        out = mb._parse_id(id_url)
        assert out == id_string


class ArtistFlatteningTest(BeetsTestCase):
    def _credit_dict(self, suffix=""):
        return {
            "artist": {
                "name": "NAME" + suffix,
                "sort-name": "SORT" + suffix,
            },
            "name": "CREDIT" + suffix,
        }

    def _add_alias(self, credit_dict, suffix="", locale="", primary=False):
        alias = {
            "alias": "ALIAS" + suffix,
            "locale": locale,
            "sort-name": "ALIASSORT" + suffix,
        }
        if primary:
            alias["primary"] = "primary"
        if "alias-list" not in credit_dict["artist"]:
            credit_dict["artist"]["alias-list"] = []
        credit_dict["artist"]["alias-list"].append(alias)

    def test_single_artist(self):
        credit = [self._credit_dict()]
        a, s, c = mb._flatten_artist_credit(credit)
        assert a == "NAME"
        assert s == "SORT"
        assert c == "CREDIT"

        a, s, c = mb._multi_artist_credit(credit, include_join_phrase=False)
        assert a == ["NAME"]
        assert s == ["SORT"]
        assert c == ["CREDIT"]

    def test_two_artists(self):
        credit = [self._credit_dict("a"), " AND ", self._credit_dict("b")]
        a, s, c = mb._flatten_artist_credit(credit)
        assert a == "NAMEa AND NAMEb"
        assert s == "SORTa AND SORTb"
        assert c == "CREDITa AND CREDITb"

        a, s, c = mb._multi_artist_credit(credit, include_join_phrase=False)
        assert a == ["NAMEa", "NAMEb"]
        assert s == ["SORTa", "SORTb"]
        assert c == ["CREDITa", "CREDITb"]

    def test_alias(self):
        credit_dict = self._credit_dict()
        self._add_alias(credit_dict, suffix="en", locale="en", primary=True)
        self._add_alias(
            credit_dict, suffix="en_GB", locale="en_GB", primary=True
        )
        self._add_alias(credit_dict, suffix="fr", locale="fr")
        self._add_alias(credit_dict, suffix="fr_P", locale="fr", primary=True)
        self._add_alias(credit_dict, suffix="pt_BR", locale="pt_BR")

        # test no alias
        config["import"]["languages"] = [""]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("NAME", "SORT", "CREDIT")

        # test en primary
        config["import"]["languages"] = ["en"]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("ALIASen", "ALIASSORTen", "CREDIT")

        # test en_GB en primary
        config["import"]["languages"] = ["en_GB", "en"]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("ALIASen_GB", "ALIASSORTen_GB", "CREDIT")

        # test en en_GB primary
        config["import"]["languages"] = ["en", "en_GB"]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("ALIASen", "ALIASSORTen", "CREDIT")

        # test fr primary
        config["import"]["languages"] = ["fr"]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("ALIASfr_P", "ALIASSORTfr_P", "CREDIT")

        # test for not matching non-primary
        config["import"]["languages"] = ["pt_BR", "fr"]
        flat = mb._flatten_artist_credit([credit_dict])
        assert flat == ("ALIASfr_P", "ALIASSORTfr_P", "CREDIT")


class MBLibraryTest(BeetsTestCase):
    def test_match_track(self):
        with mock.patch("musicbrainzngs.search_recordings") as p:
            p.return_value = {
                "recording-list": [
                    {
                        "title": "foo",
                        "id": "bar",
                        "length": 42,
                    }
                ],
            }
            ti = list(mb.match_track("hello", "there"))[0]

            p.assert_called_with(artist="hello", recording="there", limit=5)
            assert ti.title == "foo"
            assert ti.track_id == "bar"

    def test_match_album(self):
        mbid = "d2a6f856-b553-40a0-ac54-a321e8e2da99"
        with mock.patch("musicbrainzngs.search_releases") as sp:
            sp.return_value = {
                "release-list": [
                    {
                        "id": mbid,
                    }
                ],
            }
            with mock.patch("musicbrainzngs.get_release_by_id") as gp:
                gp.return_value = {
                    "release": {
                        "title": "hi",
                        "id": mbid,
                        "status": "status",
                        "medium-list": [
                            {
                                "track-list": [
                                    {
                                        "id": "baz",
                                        "recording": {
                                            "title": "foo",
                                            "id": "bar",
                                            "length": 42,
                                        },
                                        "position": 9,
                                        "number": "A1",
                                    }
                                ],
                                "position": 5,
                            }
                        ],
                        "artist-credit": [
                            {
                                "artist": {
                                    "name": "some-artist",
                                    "id": "some-id",
                                },
                            }
                        ],
                        "release-group": {
                            "id": "another-id",
                        },
                    }
                }

                ai = list(mb.match_album("hello", "there"))[0]

                sp.assert_called_with(artist="hello", release="there", limit=5)
                gp.assert_called_with(mbid, mock.ANY)
                assert ai.tracks[0].title == "foo"
                assert ai.album == "hi"

    def test_match_track_empty(self):
        with mock.patch("musicbrainzngs.search_recordings") as p:
            til = list(mb.match_track(" ", " "))
            assert not p.called
            assert til == []

    def test_match_album_empty(self):
        with mock.patch("musicbrainzngs.search_releases") as p:
            ail = list(mb.match_album(" ", " "))
            assert not p.called
            assert ail == []

    def test_follow_pseudo_releases(self):
        side_effect = [
            {
                "release": {
                    "title": "pseudo",
                    "id": "d2a6f856-b553-40a0-ac54-a321e8e2da02",
                    "status": "Pseudo-Release",
                    "medium-list": [
                        {
                            "track-list": [
                                {
                                    "id": "baz",
                                    "recording": {
                                        "title": "translated title",
                                        "id": "bar",
                                        "length": 42,
                                    },
                                    "position": 9,
                                    "number": "A1",
                                }
                            ],
                            "position": 5,
                        }
                    ],
                    "artist-credit": [
                        {
                            "artist": {
                                "name": "some-artist",
                                "id": "some-id",
                            },
                        }
                    ],
                    "release-group": {
                        "id": "another-id",
                    },
                    "release-relation-list": [
                        {
                            "type": "transl-tracklisting",
                            "target": "d2a6f856-b553-40a0-ac54-a321e8e2da01",
                            "direction": "backward",
                        }
                    ],
                }
            },
            {
                "release": {
                    "title": "actual",
                    "id": "d2a6f856-b553-40a0-ac54-a321e8e2da01",
                    "status": "Official",
                    "medium-list": [
                        {
                            "track-list": [
                                {
                                    "id": "baz",
                                    "recording": {
                                        "title": "original title",
                                        "id": "bar",
                                        "length": 42,
                                    },
                                    "position": 9,
                                    "number": "A1",
                                }
                            ],
                            "position": 5,
                        }
                    ],
                    "artist-credit": [
                        {
                            "artist": {
                                "name": "some-artist",
                                "id": "some-id",
                            },
                        }
                    ],
                    "release-group": {
                        "id": "another-id",
                    },
                    "country": "COUNTRY",
                }
            },
        ]

        with mock.patch("musicbrainzngs.get_release_by_id") as gp:
            gp.side_effect = side_effect
            album = mb.album_for_id("d2a6f856-b553-40a0-ac54-a321e8e2da02")
            assert album.country == "COUNTRY"

    def test_pseudo_releases_with_empty_links(self):
        side_effect = [
            {
                "release": {
                    "title": "pseudo",
                    "id": "d2a6f856-b553-40a0-ac54-a321e8e2da02",
                    "status": "Pseudo-Release",
                    "medium-list": [
                        {
                            "track-list": [
                                {
                                    "id": "baz",
                                    "recording": {
                                        "title": "translated title",
                                        "id": "bar",
                                        "length": 42,
                                    },
                                    "position": 9,
                                    "number": "A1",
                                }
                            ],
                            "position": 5,
                        }
                    ],
                    "artist-credit": [
                        {
                            "artist": {
                                "name": "some-artist",
                                "id": "some-id",
                            },
                        }
                    ],
                    "release-group": {
                        "id": "another-id",
                    },
                    "release-relation-list": [],
                }
            },
        ]

        with mock.patch("musicbrainzngs.get_release_by_id") as gp:
            gp.side_effect = side_effect
            album = mb.album_for_id("d2a6f856-b553-40a0-ac54-a321e8e2da02")
            assert album.country is None

    def test_pseudo_releases_without_links(self):
        side_effect = [
            {
                "release": {
                    "title": "pseudo",
                    "id": "d2a6f856-b553-40a0-ac54-a321e8e2da02",
                    "status": "Pseudo-Release",
                    "medium-list": [
                        {
                            "track-list": [
                                {
                                    "id": "baz",
                                    "recording": {
                                        "title": "translated title",
                                        "id": "bar",
                                        "length": 42,
                                    },
                                    "position": 9,
                                    "number": "A1",
                                }
                            ],
                            "position": 5,
                        }
                    ],
                    "artist-credit": [
                        {
                            "artist": {
                                "name": "some-artist",
                                "id": "some-id",
                            },
                        }
                    ],
                    "release-group": {
                        "id": "another-id",
                    },
                }
            },
        ]

        with mock.patch("musicbrainzngs.get_release_by_id") as gp:
            gp.side_effect = side_effect
            album = mb.album_for_id("d2a6f856-b553-40a0-ac54-a321e8e2da02")
            assert album.country is None

    def test_pseudo_releases_with_unsupported_links(self):
        side_effect = [
            {
                "release": {
                    "title": "pseudo",
                    "id": "d2a6f856-b553-40a0-ac54-a321e8e2da02",
                    "status": "Pseudo-Release",
                    "medium-list": [
                        {
                            "track-list": [
                                {
                                    "id": "baz",
                                    "recording": {
                                        "title": "translated title",
                                        "id": "bar",
                                        "length": 42,
                                    },
                                    "position": 9,
                                    "number": "A1",
                                }
                            ],
                            "position": 5,
                        }
                    ],
                    "artist-credit": [
                        {
                            "artist": {
                                "name": "some-artist",
                                "id": "some-id",
                            },
                        }
                    ],
                    "release-group": {
                        "id": "another-id",
                    },
                    "release-relation-list": [
                        {
                            "type": "remaster",
                            "target": "d2a6f856-b553-40a0-ac54-a321e8e2da01",
                            "direction": "backward",
                        }
                    ],
                }
            },
        ]

        with mock.patch("musicbrainzngs.get_release_by_id") as gp:
            gp.side_effect = side_effect
            album = mb.album_for_id("d2a6f856-b553-40a0-ac54-a321e8e2da02")
            assert album.country is None
