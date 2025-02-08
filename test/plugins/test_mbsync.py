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

from unittest.mock import patch

from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.library import Item
from beets.test.helper import PluginTestCase, capture_log


class MbsyncCliTest(PluginTestCase):
    plugin = "mbsync"

    @patch("beets.autotag.mb.album_for_id")
    @patch("beets.autotag.mb.track_for_id")
    def test_update_library(self, track_for_id, album_for_id):
        album_item = Item(
            album="old album",
            mb_albumid="81ae60d4-5b75-38df-903a-db2cfa51c2c6",
            mb_trackid="track id",
        )
        self.lib.add_album([album_item])

        singleton = Item(
            title="old title", mb_trackid="b8c2cf90-83f9-3b5f-8ccd-31fb866fcf37"
        )
        self.lib.add(singleton)

        album_for_id.return_value = AlbumInfo(
            album_id="album id",
            album="new album",
            tracks=[
                TrackInfo(track_id=album_item.mb_trackid, title="new title")
            ],
        )
        track_for_id.return_value = TrackInfo(
            track_id=singleton.mb_trackid, title="new title"
        )

        with capture_log() as logs:
            self.run_command("mbsync")

        assert "Sending event: albuminfo_received" in logs
        assert "Sending event: trackinfo_received" in logs

        singleton.load()
        assert singleton.title == "new title"

        album_item.load()
        assert album_item.title == "new title"
        assert album_item.mb_trackid == "track id"
        assert album_item.get_album().album == "new album"

    def test_custom_format(self):
        for item in [
            Item(artist="albumartist", album="no id"),
            Item(
                artist="albumartist",
                album="invalid id",
                mb_albumid="a1b2c3d4",
            ),
        ]:
            self.lib.add_album([item])

        for item in [
            Item(artist="artist", title="no id"),
            Item(artist="artist", title="invalid id", mb_trackid="a1b2c3d4"),
        ]:
            self.lib.add(item)

        with capture_log("beets.mbsync") as logs:
            self.run_command("mbsync", "-f", "'%if{$album,$album,$title}'")
        assert set(logs) == {
            "mbsync: Skipping album with no mb_albumid: 'no id'",
            "mbsync: Skipping album with invalid mb_albumid: 'invalid id'",
            "mbsync: Skipping singleton with no mb_trackid: 'no id'",
            "mbsync: Skipping singleton with invalid mb_trackid: 'invalid id'",
        }
