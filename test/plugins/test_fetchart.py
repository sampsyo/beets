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


import ctypes
import os
import sys

from beets import util
from beets.test.helper import PluginTestCase


class FetchartCliTest(PluginTestCase):
    plugin = "fetchart"

    def setUp(self):
        super().setUp()
        self.config["fetchart"]["cover_names"] = "c\xc3\xb6ver.jpg"
        self.config["art_filename"] = "mycover"
        self.album = self.add_album()
        self.cover_path = os.path.join(self.album.path, b"mycover.jpg")

    def check_cover_is_stored(self):
        assert self.album["artpath"] == self.cover_path
        with open(util.syspath(self.cover_path)) as f:
            assert f.read() == "IMAGE"

    def hide_file_windows(self):
        hidden_mask = 2
        success = ctypes.windll.kernel32.SetFileAttributesW(
            self.cover_path, hidden_mask
        )
        if not success:
            self.skipTest("unable to set file attributes")

    def test_set_art_from_folder(self):
        self.touch(b"c\xc3\xb6ver.jpg", dir=self.album.path, content="IMAGE")

        self.run_command("fetchart")

        self.album.load()
        self.check_cover_is_stored()

    def test_filesystem_does_not_pick_up_folder(self):
        os.makedirs(os.path.join(self.album.path, b"mycover.jpg"))
        self.run_command("fetchart")
        self.album.load()
        assert self.album["artpath"] is None

    def test_filesystem_does_not_pick_up_ignored_file(self):
        self.touch(b"co_ver.jpg", dir=self.album.path, content="IMAGE")
        self.config["ignore"] = ["*_*"]
        self.run_command("fetchart")
        self.album.load()
        assert self.album["artpath"] is None

    def test_filesystem_picks_up_non_ignored_file(self):
        self.touch(b"cover.jpg", dir=self.album.path, content="IMAGE")
        self.config["ignore"] = ["*_*"]
        self.run_command("fetchart")
        self.album.load()
        self.check_cover_is_stored()

    def test_filesystem_does_not_pick_up_hidden_file(self):
        self.touch(b".cover.jpg", dir=self.album.path, content="IMAGE")
        if sys.platform == "win32":
            self.hide_file_windows()
        self.config["ignore"] = []  # By default, ignore includes '.*'.
        self.config["ignore_hidden"] = True
        self.run_command("fetchart")
        self.album.load()
        assert self.album["artpath"] is None

    def test_filesystem_picks_up_non_hidden_file(self):
        self.touch(b"cover.jpg", dir=self.album.path, content="IMAGE")
        self.config["ignore_hidden"] = True
        self.run_command("fetchart")
        self.album.load()
        self.check_cover_is_stored()

    def test_filesystem_picks_up_hidden_file(self):
        self.touch(b".cover.jpg", dir=self.album.path, content="IMAGE")
        if sys.platform == "win32":
            self.hide_file_windows()
        self.config["ignore"] = []  # By default, ignore includes '.*'.
        self.config["ignore_hidden"] = False
        self.run_command("fetchart")
        self.album.load()
        self.check_cover_is_stored()
