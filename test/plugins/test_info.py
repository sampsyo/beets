# This file is part of beets.
# Copyright 2016, Thomas Scholtes.
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


from mediafile import MediaFile

from beets.test.helper import PluginTestCase
from beets.util import displayable_path


class InfoTest(PluginTestCase):
    plugin = "info"

    def test_path(self):
        path = self.create_mediafile_fixture()

        mediafile = MediaFile(path)
        mediafile.albumartist = "AAA"
        mediafile.disctitle = "DDD"
        mediafile.genres = ["a", "b", "c"]
        mediafile.composer = None
        mediafile.save()

        out = self.run_with_output("info", path)
        assert displayable_path(path) in out
        assert "albumartist: AAA" in out
        assert "disctitle: DDD" in out
        assert "genres: a; b; c" in out
        assert "composer:" not in out

    def test_item_query(self):
        item1, item2 = self.add_item_fixtures(count=2)
        item1.album = "xxxx"
        item1.write()
        item1.album = "yyyy"
        item1.store()

        out = self.run_with_output("info", "album:yyyy")
        assert displayable_path(item1.path) in out
        assert "album: xxxx" in out

        assert displayable_path(item2.path) not in out

    def test_item_library_query(self):
        (item,) = self.add_item_fixtures()
        item.album = "xxxx"
        item.store()

        out = self.run_with_output("info", "--library", "album:xxxx")
        assert displayable_path(item.path) in out
        assert "album: xxxx" in out

    def test_collect_item_and_path(self):
        path = self.create_mediafile_fixture()
        mediafile = MediaFile(path)
        (item,) = self.add_item_fixtures()

        item.album = mediafile.album = "AAA"
        item.tracktotal = mediafile.tracktotal = 5
        item.title = "TTT"
        mediafile.title = "SSS"

        item.write()
        item.store()
        mediafile.save()

        out = self.run_with_output("info", "--summarize", "album:AAA", path)
        assert "album: AAA" in out
        assert "tracktotal: 5" in out
        assert "title: [various]" in out

    def test_collect_item_and_path_with_multi_values(self):
        path = self.create_mediafile_fixture()
        mediafile = MediaFile(path)
        (item,) = self.add_item_fixtures()

        item.album = mediafile.album = "AAA"
        item.tracktotal = mediafile.tracktotal = 5
        item.title = "TTT"
        mediafile.title = "SSS"

        item.albumartists = ["Artist A", "Artist B"]
        mediafile.albumartists = ["Artist C", "Artist D"]

        item.artists = ["Artist A", "Artist Z"]
        mediafile.artists = ["Artist A", "Artist Z"]

        item.write()
        item.store()
        mediafile.save()

        out = self.run_with_output("info", "--summarize", "album:AAA", path)
        assert "album: AAA" in out
        assert "tracktotal: 5" in out
        assert "title: [various]" in out
        assert "albumartists: [various]" in out
        assert "artists: Artist A; Artist Z" in out

    def test_custom_format(self):
        self.add_item_fixtures()
        out = self.run_with_output(
            "info",
            "--library",
            "--format",
            "$track. $title - $artist ($length)",
        )
        assert "02. tïtle 0 - the artist (0:01)\n" == out
