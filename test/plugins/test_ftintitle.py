# This file is part of beets.
# Copyright 2016, Fabrice Laporte.
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

"""Tests for the 'ftintitle' plugin."""

import unittest

from beets.test.helper import PluginTestCase
from beetsplug import ftintitle


class FtInTitlePluginFunctional(PluginTestCase):
    plugin = "ftintitle"

    def _ft_add_item(self, path, artist, title, aartist):
        return self.add_item(
            path=path,
            artist=artist,
            artist_sort=artist,
            title=title,
            albumartist=aartist,
        )

    def _ft_set_config(
        self, ftformat, drop=False, auto=True, keep_in_artist=False
    ):
        self.config["ftintitle"]["format"] = ftformat
        self.config["ftintitle"]["drop"] = drop
        self.config["ftintitle"]["auto"] = auto
        self.config["ftintitle"]["keep_in_artist"] = keep_in_artist

    def test_functional_drop(self):
        item = self._ft_add_item("/", "Alice ft Bob", "Song 1", "Alice")
        self.run_command("ftintitle", "-d")
        item.load()
        assert item["artist"] == "Alice"
        assert item["title"] == "Song 1"

    def test_functional_not_found(self):
        item = self._ft_add_item("/", "Alice ft Bob", "Song 1", "George")
        self.run_command("ftintitle", "-d")
        item.load()
        # item should be unchanged
        assert item["artist"] == "Alice ft Bob"
        assert item["title"] == "Song 1"

    def test_functional_custom_format(self):
        self._ft_set_config("feat. {0}")
        item = self._ft_add_item("/", "Alice ft Bob", "Song 1", "Alice")
        self.run_command("ftintitle")
        item.load()
        assert item["artist"] == "Alice"
        assert item["title"] == "Song 1 feat. Bob"

        self._ft_set_config("featuring {0}")
        item = self._ft_add_item("/", "Alice feat. Bob", "Song 1", "Alice")
        self.run_command("ftintitle")
        item.load()
        assert item["artist"] == "Alice"
        assert item["title"] == "Song 1 featuring Bob"

        self._ft_set_config("with {0}")
        item = self._ft_add_item("/", "Alice feat Bob", "Song 1", "Alice")
        self.run_command("ftintitle")
        item.load()
        assert item["artist"] == "Alice"
        assert item["title"] == "Song 1 with Bob"

    def test_functional_keep_in_artist(self):
        self._ft_set_config("feat. {0}", keep_in_artist=True)
        item = self._ft_add_item("/", "Alice ft Bob", "Song 1", "Alice")
        self.run_command("ftintitle")
        item.load()
        assert item["artist"] == "Alice ft Bob"
        assert item["title"] == "Song 1 feat. Bob"

        item = self._ft_add_item("/", "Alice ft Bob", "Song 1", "Alice")
        self.run_command("ftintitle", "-d")
        item.load()
        assert item["artist"] == "Alice ft Bob"
        assert item["title"] == "Song 1"


class FtInTitlePluginTest(unittest.TestCase):
    def setUp(self):
        """Set up configuration"""
        ftintitle.FtInTitlePlugin()

    def test_find_feat_part(self):
        test_cases = [
            {
                "artist": "Alice ft. Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice feat Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice featuring Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice & Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice and Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice With Bob",
                "album_artist": "Alice",
                "feat_part": "Bob",
            },
            {
                "artist": "Alice defeat Bob",
                "album_artist": "Alice",
                "feat_part": None,
            },
            {
                "artist": "Alice & Bob",
                "album_artist": "Bob",
                "feat_part": "Alice",
            },
            {
                "artist": "Alice ft. Bob",
                "album_artist": "Bob",
                "feat_part": "Alice",
            },
            {
                "artist": "Alice ft. Carol",
                "album_artist": "Bob",
                "feat_part": None,
            },
        ]

        for test_case in test_cases:
            feat_part = ftintitle.find_feat_part(
                test_case["artist"], test_case["album_artist"]
            )
            assert feat_part == test_case["feat_part"]

    def test_split_on_feat(self):
        parts = ftintitle.split_on_feat("Alice ft. Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice feat Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice feat. Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice featuring Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice & Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice and Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice With Bob")
        assert parts == ("Alice", "Bob")
        parts = ftintitle.split_on_feat("Alice defeat Bob")
        assert parts == ("Alice defeat Bob", None)

    def test_contains_feat(self):
        assert ftintitle.contains_feat("Alice ft. Bob")
        assert ftintitle.contains_feat("Alice feat. Bob")
        assert ftintitle.contains_feat("Alice feat Bob")
        assert ftintitle.contains_feat("Alice featuring Bob")
        assert ftintitle.contains_feat("Alice (ft. Bob)")
        assert ftintitle.contains_feat("Alice (feat. Bob)")
        assert ftintitle.contains_feat("Alice [ft. Bob]")
        assert ftintitle.contains_feat("Alice [feat. Bob]")
        assert not ftintitle.contains_feat("Alice defeat Bob")
        assert not ftintitle.contains_feat("Aliceft.Bob")
        assert not ftintitle.contains_feat("Alice (defeat Bob)")
        assert not ftintitle.contains_feat("Live and Let Go")
        assert not ftintitle.contains_feat("Come With Me")
