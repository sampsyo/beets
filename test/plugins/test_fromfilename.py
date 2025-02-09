# This file is part of beets.
# Copyright 2016, Jan-Erik Dahlin.
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

"""Tests for the fromfilename plugin.
"""

import unittest
from unittest.mock import Mock
from beetsplug import fromfilename


class FromfilenamePluginTest(unittest.TestCase):

    def setUp(self):
        """Create mock objects for import session and task."""
        self.session = Mock()

        item1config = {'path': '', 'track': 0, 'artist': '', 'title': ''}
        self.item1 = Mock(**item1config)

        item2config = {'path': '', 'track': 0, 'artist': '', 'title': ''}
        self.item2 = Mock(**item2config)

        taskconfig = {'is_album': True, 'items': [self.item1, self.item2]}
        self.task = Mock(**taskconfig)

    def tearDown(self):
        del self.session, self.task, self.item1, self.item2

    def test_sep_sds(self):
        """Test filenames that use " - " as separator."""

        self.item1.path = "/music/files/01 - Artist Name - Song One.m4a"
        self.item2.path = "/music/files/02. - Artist Name - Song Two.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 1)
        self.assertEqual(self.task.items[1].track, 2)
        self.assertEqual(self.task.items[0].artist, "Artist Name")
        self.assertEqual(self.task.items[1].artist, "Artist Name")
        self.assertEqual(self.task.items[0].title, "Song One")
        self.assertEqual(self.task.items[1].title, "Song Two")

    def test_sep_dash(self):
        """Test filenames that use "-" as separator."""

        self.item1.path = "/music/files/01-Artist_Name-Song_One.m4a"
        self.item2.path = "/music/files/02.-Artist_Name-Song_Two.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 1)
        self.assertEqual(self.task.items[1].track, 2)
        self.assertEqual(self.task.items[0].artist, "Artist_Name")
        self.assertEqual(self.task.items[1].artist, "Artist_Name")
        self.assertEqual(self.task.items[0].title, "Song_One")
        self.assertEqual(self.task.items[1].title, "Song_Two")

    def test_track_title(self):
        """Test filenames including track and title."""

        self.item1.path = "/music/files/01 - Song_One.m4a"
        self.item2.path = "/music/files/02. Song_Two.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 1)
        self.assertEqual(self.task.items[1].track, 2)
        self.assertEqual(self.task.items[0].artist, "")
        self.assertEqual(self.task.items[1].artist, "")
        self.assertEqual(self.task.items[0].title, "Song_One")
        self.assertEqual(self.task.items[1].title, "Song_Two")

    def test_title_by_artist(self):
        """Test filenames including title by artist."""

        self.item1.path = "/music/files/Song One by The Artist.m4a"
        self.item2.path = "/music/files/Song Two by The Artist.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 0)
        self.assertEqual(self.task.items[1].track, 0)
        self.assertEqual(self.task.items[0].artist, "The Artist")
        self.assertEqual(self.task.items[1].artist, "The Artist")
        self.assertEqual(self.task.items[0].title, "Song One")
        self.assertEqual(self.task.items[1].title, "Song Two")

    def test_track_only(self):
        """Test filenames including only track."""

        self.item1.path = "/music/files/01.m4a"
        self.item2.path = "/music/files/02.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 1)
        self.assertEqual(self.task.items[1].track, 2)
        self.assertEqual(self.task.items[0].artist, "")
        self.assertEqual(self.task.items[1].artist, "")
        self.assertEqual(self.task.items[0].title, "01")
        self.assertEqual(self.task.items[1].title, "02")

    def test_title_only(self):
        """Test filenames including only title."""

        self.item1.path = "/music/files/Song One.m4a"
        self.item2.path = "/music/files/Song Two.m4a"

        f = fromfilename.FromFilenamePlugin()
        f.filename_task(self.task, self.session)

        self.assertEqual(self.task.items[0].track, 0)
        self.assertEqual(self.task.items[1].track, 0)
        self.assertEqual(self.task.items[0].artist, "")
        self.assertEqual(self.task.items[1].artist, "")
        self.assertEqual(self.task.items[0].title, "Song One")
        self.assertEqual(self.task.items[1].title, "Song Two")


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main(defaultTest="suite")
