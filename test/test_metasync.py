# This file is part of beets.
# Copyright 2016, Tom Jaspers.
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


import os
import platform
import time
from datetime import datetime

from beets.library import Item
from beets.test import _common
from beets.test.helper import PluginTestCase


def _parsetime(s):
    return time.mktime(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timetuple())


def _is_windows():
    return platform.system() == "Windows"


class MetaSyncTest(PluginTestCase):
    plugin = "metasync"
    itunes_library_unix = os.path.join(_common.RSRC, b"itunes_library_unix.xml")
    itunes_library_windows = os.path.join(
        _common.RSRC, b"itunes_library_windows.xml"
    )

    def setUp(self):
        super().setUp()

        self.config["metasync"]["source"] = "itunes"

        if _is_windows():
            self.config["metasync"]["itunes"]["library"] = os.fsdecode(
                self.itunes_library_windows
            )
        else:
            self.config["metasync"]["itunes"]["library"] = os.fsdecode(
                self.itunes_library_unix
            )

        self._set_up_data()

    def _set_up_data(self):
        items = [_common.item() for _ in range(2)]

        items[0].title = "Tessellate"
        items[0].artist = "alt-J"
        items[0].albumartist = "alt-J"
        items[0].album = "An Awesome Wave"
        items[0].itunes_rating = 60

        items[1].title = "Breezeblocks"
        items[1].artist = "alt-J"
        items[1].albumartist = "alt-J"
        items[1].album = "An Awesome Wave"

        if _is_windows():
            items[
                0
            ].path = "G:\\Music\\Alt-J\\An Awesome Wave\\03 Tessellate.mp3"
            items[
                1
            ].path = "G:\\Music\\Alt-J\\An Awesome Wave\\04 Breezeblocks.mp3"
        else:
            items[0].path = "/Music/Alt-J/An Awesome Wave/03 Tessellate.mp3"
            items[1].path = "/Music/Alt-J/An Awesome Wave/04 Breezeblocks.mp3"

        for item in items:
            self.lib.add(item)

    def test_load_item_types(self):
        # This test also verifies that the MetaSources have loaded correctly
        assert "amarok_score" in Item._types
        assert "itunes_rating" in Item._types

    def test_pretend_sync_from_itunes(self):
        out = self.run_with_output("metasync", "-p")

        assert "itunes_rating: 60 -> 80" in out
        assert "itunes_rating: 100" in out
        assert "itunes_playcount: 31" in out
        assert "itunes_skipcount: 3" in out
        assert "itunes_lastplayed: 2015-05-04 12:20:51" in out
        assert "itunes_lastskipped: 2015-02-05 15:41:04" in out
        assert "itunes_dateadded: 2014-04-24 09:28:38" in out
        assert self.lib.items()[0].itunes_rating == 60

    def test_sync_from_itunes(self):
        self.run_command("metasync")

        assert self.lib.items()[0].itunes_rating == 80
        assert self.lib.items()[0].itunes_playcount == 0
        assert self.lib.items()[0].itunes_skipcount == 3
        assert not hasattr(self.lib.items()[0], "itunes_lastplayed")
        assert self.lib.items()[0].itunes_lastskipped == _parsetime(
            "2015-02-05 15:41:04"
        )
        assert self.lib.items()[0].itunes_dateadded == _parsetime(
            "2014-04-24 09:28:38"
        )

        assert self.lib.items()[1].itunes_rating == 100
        assert self.lib.items()[1].itunes_playcount == 31
        assert self.lib.items()[1].itunes_skipcount == 0
        assert self.lib.items()[1].itunes_lastplayed == _parsetime(
            "2015-05-04 12:20:51"
        )
        assert self.lib.items()[1].itunes_dateadded == _parsetime(
            "2014-04-24 09:28:38"
        )
        assert not hasattr(self.lib.items()[1], "itunes_lastskipped")
