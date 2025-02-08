"""Tests for the 'ihate' plugin"""

import unittest

from beets import importer
from beets.library import Item
from beetsplug.ihate import IHatePlugin


class IHatePluginTest(unittest.TestCase):
    def test_hate(self):
        match_pattern = {}
        test_item = Item(
            genre="TestGenre", album="TestAlbum", artist="TestArtist"
        )
        task = importer.SingletonImportTask(None, test_item)

        # Empty query should let it pass.
        assert not IHatePlugin.do_i_hate_this(task, match_pattern)

        # 1 query match.
        match_pattern = ["artist:bad_artist", "artist:TestArtist"]
        assert IHatePlugin.do_i_hate_this(task, match_pattern)

        # 2 query matches, either should trigger.
        match_pattern = ["album:test", "artist:testartist"]
        assert IHatePlugin.do_i_hate_this(task, match_pattern)

        # Query is blocked by AND clause.
        match_pattern = ["album:notthis genre:testgenre"]
        assert not IHatePlugin.do_i_hate_this(task, match_pattern)

        # Both queries are blocked by AND clause with unmatched condition.
        match_pattern = [
            "album:notthis genre:testgenre",
            "artist:testartist album:notthis",
        ]
        assert not IHatePlugin.do_i_hate_this(task, match_pattern)

        # Only one query should fire.
        match_pattern = [
            "album:testalbum genre:testgenre",
            "artist:testartist album:notthis",
        ]
        assert IHatePlugin.do_i_hate_this(task, match_pattern)
