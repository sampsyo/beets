"""Tests for the 'permissions' plugin."""

import os
import platform
from unittest.mock import Mock, patch

from beets.test._common import touch
from beets.test.helper import AsIsImporterMixin, ImportTestCase, PluginMixin
from beets.util import displayable_path
from beetsplug.permissions import (
    check_permissions,
    convert_perm,
    dirs_in_library,
)


class PermissionsPluginTest(AsIsImporterMixin, PluginMixin, ImportTestCase):
    plugin = "permissions"

    def setUp(self):
        super().setUp()

        self.config["permissions"] = {"file": "777", "dir": "777"}

    def test_permissions_on_album_imported(self):
        self.do_thing(True)

    def test_permissions_on_item_imported(self):
        self.config["import"]["singletons"] = True
        self.do_thing(True)

    @patch("os.chmod", Mock())
    def test_failing_to_set_permissions(self):
        self.do_thing(False)

    def do_thing(self, expect_success):
        if platform.system() == "Windows":
            self.skipTest("permissions not available on Windows")

        def get_stat(v):
            return (
                os.stat(os.path.join(self.temp_dir, b"import", *v)).st_mode
                & 0o777
            )

        typs = ["file", "dir"]

        track_file = (b"album", b"track_1.mp3")
        self.exp_perms = {
            True: {
                k: convert_perm(self.config["permissions"][k].get())
                for k in typs
            },
            False: {k: get_stat(v) for (k, v) in zip(typs, (track_file, ()))},
        }

        self.run_asis_importer()
        item = self.lib.items().get()

        self.assertPerms(item.path, "file", expect_success)

        for path in dirs_in_library(self.lib.directory, item.path):
            self.assertPerms(path, "dir", expect_success)

    def assertPerms(self, path, typ, expect_success):
        for x in [
            (True, self.exp_perms[expect_success][typ], "!="),
            (False, self.exp_perms[not expect_success][typ], "=="),
        ]:
            msg = "{} : {} {} {}".format(
                displayable_path(path),
                oct(os.stat(path).st_mode),
                x[2],
                oct(x[1]),
            )
            assert x[0] == check_permissions(path, x[1]), msg

    def test_convert_perm_from_string(self):
        assert convert_perm("10") == 8

    def test_convert_perm_from_int(self):
        assert convert_perm(10) == 8

    def test_permissions_on_set_art(self):
        self.do_set_art(True)

    @patch("os.chmod", Mock())
    def test_failing_permissions_on_set_art(self):
        self.do_set_art(False)

    def do_set_art(self, expect_success):
        if platform.system() == "Windows":
            self.skipTest("permissions not available on Windows")
        self.run_asis_importer()
        album = self.lib.albums().get()
        artpath = os.path.join(self.temp_dir, b"cover.jpg")
        touch(artpath)
        album.set_art(artpath)
        assert expect_success == check_permissions(album.artpath, 0o777)
