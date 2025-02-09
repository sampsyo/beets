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

"""Tests for the command-line interface."""

import os
import platform
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import pytest
from confuse import ConfigError
from mediafile import MediaFile

from beets import autotag, config, library, plugins, ui, util
from beets.autotag.match import distance
from beets.test import _common
from beets.test.helper import (
    BeetsTestCase,
    PluginTestCase,
    capture_stdout,
    control_stdin,
    has_program,
)
from beets.ui import commands
from beets.util import MoveOperation, syspath


class ListTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.item = _common.item()
        self.item.path = "xxx/yyy"
        self.lib.add(self.item)
        self.lib.add_album([self.item])

    def _run_list(self, query="", album=False, path=False, fmt=""):
        with capture_stdout() as stdout:
            commands.list_items(self.lib, query, album, fmt)
        return stdout

    def test_list_outputs_item(self):
        stdout = self._run_list()
        assert "the title" in stdout.getvalue()

    def test_list_unicode_query(self):
        self.item.title = "na\xefve"
        self.item.store()
        self.lib._connection().commit()

        stdout = self._run_list(["na\xefve"])
        out = stdout.getvalue()
        assert "na\xefve" in out

    def test_list_item_path(self):
        stdout = self._run_list(fmt="$path")
        assert stdout.getvalue().strip() == "xxx/yyy"

    def test_list_album_outputs_something(self):
        stdout = self._run_list(album=True)
        assert len(stdout.getvalue()) > 0

    def test_list_album_path(self):
        stdout = self._run_list(album=True, fmt="$path")
        assert stdout.getvalue().strip() == "xxx"

    def test_list_album_omits_title(self):
        stdout = self._run_list(album=True)
        assert "the title" not in stdout.getvalue()

    def test_list_uses_track_artist(self):
        stdout = self._run_list()
        assert "the artist" in stdout.getvalue()
        assert "the album artist" not in stdout.getvalue()

    def test_list_album_uses_album_artist(self):
        stdout = self._run_list(album=True)
        assert "the artist" not in stdout.getvalue()
        assert "the album artist" in stdout.getvalue()

    def test_list_item_format_artist(self):
        stdout = self._run_list(fmt="$artist")
        assert "the artist" in stdout.getvalue()

    def test_list_item_format_multiple(self):
        stdout = self._run_list(fmt="$artist - $album - $year")
        assert "the artist - the album - 0001" == stdout.getvalue().strip()

    def test_list_album_format(self):
        stdout = self._run_list(album=True, fmt="$genre")
        assert "the genre" in stdout.getvalue()
        assert "the album" not in stdout.getvalue()


class RemoveTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.io.install()

        # Copy a file into the library.
        self.item_path = os.path.join(_common.RSRC, b"full.mp3")
        self.i = library.Item.from_path(self.item_path)
        self.lib.add(self.i)
        self.i.move(operation=MoveOperation.COPY)

    def test_remove_items_no_delete(self):
        self.io.addinput("y")
        commands.remove_items(self.lib, "", False, False, False)
        items = self.lib.items()
        assert len(list(items)) == 0
        self.assertExists(self.i.path)

    def test_remove_items_with_delete(self):
        self.io.addinput("y")
        commands.remove_items(self.lib, "", False, True, False)
        items = self.lib.items()
        assert len(list(items)) == 0
        self.assertNotExists(self.i.path)

    def test_remove_items_with_force_no_delete(self):
        commands.remove_items(self.lib, "", False, False, True)
        items = self.lib.items()
        assert len(list(items)) == 0
        self.assertExists(self.i.path)

    def test_remove_items_with_force_delete(self):
        commands.remove_items(self.lib, "", False, True, True)
        items = self.lib.items()
        assert len(list(items)) == 0
        self.assertNotExists(self.i.path)

    def test_remove_items_select_with_delete(self):
        i2 = library.Item.from_path(self.item_path)
        self.lib.add(i2)
        i2.move(operation=MoveOperation.COPY)

        for s in ("s", "y", "n"):
            self.io.addinput(s)
        commands.remove_items(self.lib, "", False, True, False)
        items = self.lib.items()
        assert len(list(items)) == 1
        # There is probably no guarantee that the items are queried in any
        # spcecific order, thus just ensure that exactly one was removed.
        # To improve upon this, self.io would need to have the capability to
        # generate input that depends on previous output.
        num_existing = 0
        num_existing += 1 if os.path.exists(syspath(self.i.path)) else 0
        num_existing += 1 if os.path.exists(syspath(i2.path)) else 0
        assert num_existing == 1

    def test_remove_albums_select_with_delete(self):
        a1 = self.add_album_fixture()
        a2 = self.add_album_fixture()
        path1 = a1.items()[0].path
        path2 = a2.items()[0].path
        items = self.lib.items()
        assert len(list(items)) == 3

        for s in ("s", "y", "n"):
            self.io.addinput(s)
        commands.remove_items(self.lib, "", True, True, False)
        items = self.lib.items()
        assert len(list(items)) == 2  # incl. the item from setUp()
        # See test_remove_items_select_with_delete()
        num_existing = 0
        num_existing += 1 if os.path.exists(syspath(path1)) else 0
        num_existing += 1 if os.path.exists(syspath(path2)) else 0
        assert num_existing == 1


class ModifyTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.album = self.add_album_fixture()
        [self.item] = self.album.items()

    def modify_inp(self, inp, *args):
        with control_stdin(inp):
            self.run_command("modify", *args)

    def modify(self, *args):
        self.modify_inp("y", *args)

    # Item tests

    def test_modify_item(self):
        self.modify("title=newTitle")
        item = self.lib.items().get()
        assert item.title == "newTitle"

    def test_modify_item_abort(self):
        item = self.lib.items().get()
        title = item.title
        self.modify_inp("n", "title=newTitle")
        item = self.lib.items().get()
        assert item.title == title

    def test_modify_item_no_change(self):
        title = "Tracktitle"
        item = self.add_item_fixture(title=title)
        self.modify_inp("y", "title", f"title={title}")
        item = self.lib.items(title).get()
        assert item.title == title

    def test_modify_write_tags(self):
        self.modify("title=newTitle")
        item = self.lib.items().get()
        item.read()
        assert item.title == "newTitle"

    def test_modify_dont_write_tags(self):
        self.modify("--nowrite", "title=newTitle")
        item = self.lib.items().get()
        item.read()
        assert item.title != "newTitle"

    def test_move(self):
        self.modify("title=newTitle")
        item = self.lib.items().get()
        assert b"newTitle" in item.path

    def test_not_move(self):
        self.modify("--nomove", "title=newTitle")
        item = self.lib.items().get()
        assert b"newTitle" not in item.path

    def test_no_write_no_move(self):
        self.modify("--nomove", "--nowrite", "title=newTitle")
        item = self.lib.items().get()
        item.read()
        assert b"newTitle" not in item.path
        assert item.title != "newTitle"

    def test_update_mtime(self):
        item = self.item
        old_mtime = item.mtime

        self.modify("title=newTitle")
        item.load()
        assert old_mtime != item.mtime
        assert item.current_mtime() == item.mtime

    def test_reset_mtime_with_no_write(self):
        item = self.item

        self.modify("--nowrite", "title=newTitle")
        item.load()
        assert 0 == item.mtime

    def test_selective_modify(self):
        title = "Tracktitle"
        album = "album"
        original_artist = "composer"
        new_artist = "coverArtist"
        for i in range(0, 10):
            self.add_item_fixture(
                title=f"{title}{i}", artist=original_artist, album=album
            )
        self.modify_inp(
            "s\ny\ny\ny\nn\nn\ny\ny\ny\ny\nn", title, f"artist={new_artist}"
        )
        original_items = self.lib.items(f"artist:{original_artist}")
        new_items = self.lib.items(f"artist:{new_artist}")
        assert len(list(original_items)) == 3
        assert len(list(new_items)) == 7

    def test_modify_formatted(self):
        for i in range(0, 3):
            self.add_item_fixture(
                title=f"title{i}", artist="artist", album="album"
            )
        items = list(self.lib.items())
        self.modify("title=${title} - append")
        for item in items:
            orig_title = item.title
            item.load()
            assert item.title == f"{orig_title} - append"

    # Album Tests

    def test_modify_album(self):
        self.modify("--album", "album=newAlbum")
        album = self.lib.albums().get()
        assert album.album == "newAlbum"

    def test_modify_album_write_tags(self):
        self.modify("--album", "album=newAlbum")
        item = self.lib.items().get()
        item.read()
        assert item.album == "newAlbum"

    def test_modify_album_dont_write_tags(self):
        self.modify("--album", "--nowrite", "album=newAlbum")
        item = self.lib.items().get()
        item.read()
        assert item.album == "the album"

    def test_album_move(self):
        self.modify("--album", "album=newAlbum")
        item = self.lib.items().get()
        item.read()
        assert b"newAlbum" in item.path

    def test_album_not_move(self):
        self.modify("--nomove", "--album", "album=newAlbum")
        item = self.lib.items().get()
        item.read()
        assert b"newAlbum" not in item.path

    def test_modify_album_formatted(self):
        item = self.lib.items().get()
        orig_album = item.album
        self.modify("--album", "album=${album} - append")
        item.load()
        assert item.album == f"{orig_album} - append"

    # Misc

    def test_write_initial_key_tag(self):
        self.modify("initial_key=C#m")
        item = self.lib.items().get()
        mediafile = MediaFile(syspath(item.path))
        assert mediafile.initial_key == "C#m"

    def test_set_flexattr(self):
        self.modify("flexattr=testAttr")
        item = self.lib.items().get()
        assert item.flexattr == "testAttr"

    def test_remove_flexattr(self):
        item = self.lib.items().get()
        item.flexattr = "testAttr"
        item.store()

        self.modify("flexattr!")
        item = self.lib.items().get()
        assert "flexattr" not in item

    @unittest.skip("not yet implemented")
    def test_delete_initial_key_tag(self):
        item = self.lib.items().get()
        item.initial_key = "C#m"
        item.write()
        item.store()

        mediafile = MediaFile(syspath(item.path))
        assert mediafile.initial_key == "C#m"

        self.modify("initial_key!")
        mediafile = MediaFile(syspath(item.path))
        assert mediafile.initial_key is None

    def test_arg_parsing_colon_query(self):
        (query, mods, dels) = commands.modify_parse_args(
            ["title:oldTitle", "title=newTitle"]
        )
        assert query == ["title:oldTitle"]
        assert mods == {"title": "newTitle"}

    def test_arg_parsing_delete(self):
        (query, mods, dels) = commands.modify_parse_args(
            ["title:oldTitle", "title!"]
        )
        assert query == ["title:oldTitle"]
        assert dels == ["title"]

    def test_arg_parsing_query_with_exclaimation(self):
        (query, mods, dels) = commands.modify_parse_args(
            ["title:oldTitle!", "title=newTitle!"]
        )
        assert query == ["title:oldTitle!"]
        assert mods == {"title": "newTitle!"}

    def test_arg_parsing_equals_in_value(self):
        (query, mods, dels) = commands.modify_parse_args(
            ["title:foo=bar", "title=newTitle"]
        )
        assert query == ["title:foo=bar"]
        assert mods == {"title": "newTitle"}


class WriteTest(BeetsTestCase):
    def write_cmd(self, *args):
        return self.run_with_output("write", *args)

    def test_update_mtime(self):
        item = self.add_item_fixture()
        item["title"] = "a new title"
        item.store()

        item = self.lib.items().get()
        assert item.mtime == 0

        self.write_cmd()
        item = self.lib.items().get()
        assert item.mtime == item.current_mtime()

    def test_non_metadata_field_unchanged(self):
        """Changing a non-"tag" field like `bitrate` and writing should
        have no effect.
        """
        # An item that starts out "clean".
        item = self.add_item_fixture()
        item.read()

        # ... but with a mismatched bitrate.
        item.bitrate = 123
        item.store()

        output = self.write_cmd()

        assert output == ""

    def test_write_metadata_field(self):
        item = self.add_item_fixture()
        item.read()
        old_title = item.title

        item.title = "new title"
        item.store()

        output = self.write_cmd()

        assert f"{old_title} -> new title" in output


class MoveTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.io.install()

        self.itempath = os.path.join(self.libdir, b"srcfile")
        shutil.copy(
            syspath(os.path.join(_common.RSRC, b"full.mp3")),
            syspath(self.itempath),
        )

        # Add a file to the library but don't copy it in yet.
        self.i = library.Item.from_path(self.itempath)
        self.lib.add(self.i)
        self.album = self.lib.add_album([self.i])

        # Alternate destination directory.
        self.otherdir = os.path.join(self.temp_dir, b"testotherdir")

    def _move(
        self,
        query=(),
        dest=None,
        copy=False,
        album=False,
        pretend=False,
        export=False,
    ):
        commands.move_items(
            self.lib, dest, query, copy, album, pretend, export=export
        )

    def test_move_item(self):
        self._move()
        self.i.load()
        assert b"libdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_copy_item(self):
        self._move(copy=True)
        self.i.load()
        assert b"libdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertExists(self.itempath)

    def test_move_album(self):
        self._move(album=True)
        self.i.load()
        assert b"libdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_copy_album(self):
        self._move(copy=True, album=True)
        self.i.load()
        assert b"libdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertExists(self.itempath)

    def test_move_item_custom_dir(self):
        self._move(dest=self.otherdir)
        self.i.load()
        assert b"testotherdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_move_album_custom_dir(self):
        self._move(dest=self.otherdir, album=True)
        self.i.load()
        assert b"testotherdir" in self.i.path
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_pretend_move_item(self):
        self._move(dest=self.otherdir, pretend=True)
        self.i.load()
        assert b"srcfile" in self.i.path

    def test_pretend_move_album(self):
        self._move(album=True, pretend=True)
        self.i.load()
        assert b"srcfile" in self.i.path

    def test_export_item_custom_dir(self):
        self._move(dest=self.otherdir, export=True)
        self.i.load()
        assert self.i.path == self.itempath
        self.assertExists(self.otherdir)

    def test_export_album_custom_dir(self):
        self._move(dest=self.otherdir, album=True, export=True)
        self.i.load()
        assert self.i.path == self.itempath
        self.assertExists(self.otherdir)

    def test_pretend_export_item(self):
        self._move(dest=self.otherdir, pretend=True, export=True)
        self.i.load()
        assert b"srcfile" in self.i.path
        self.assertNotExists(self.otherdir)


class UpdateTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.io.install()

        # Copy a file into the library.
        item_path = os.path.join(_common.RSRC, b"full.mp3")
        item_path_two = os.path.join(_common.RSRC, b"full.flac")
        self.i = library.Item.from_path(item_path)
        self.i2 = library.Item.from_path(item_path_two)
        self.lib.add(self.i)
        self.lib.add(self.i2)
        self.i.move(operation=MoveOperation.COPY)
        self.i2.move(operation=MoveOperation.COPY)
        self.album = self.lib.add_album([self.i, self.i2])

        # Album art.
        artfile = os.path.join(self.temp_dir, b"testart.jpg")
        _common.touch(artfile)
        self.album.set_art(artfile)
        self.album.store()
        util.remove(artfile)

    def _update(
        self,
        query=(),
        album=False,
        move=False,
        reset_mtime=True,
        fields=None,
        exclude_fields=None,
    ):
        self.io.addinput("y")
        if reset_mtime:
            self.i.mtime = 0
            self.i.store()
        commands.update_items(
            self.lib,
            query,
            album,
            move,
            False,
            fields=fields,
            exclude_fields=exclude_fields,
        )

    def test_delete_removes_item(self):
        assert list(self.lib.items())
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        assert not list(self.lib.items())

    def test_delete_removes_album(self):
        assert self.lib.albums()
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        assert not self.lib.albums()

    def test_delete_removes_album_art(self):
        artpath = self.album.artpath
        self.assertExists(artpath)
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        self.assertNotExists(artpath)

    def test_modified_metadata_detected(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.save()
        self._update()
        item = self.lib.items().get()
        assert item.title == "differentTitle"

    def test_modified_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.save()
        self._update(move=True)
        item = self.lib.items().get()
        assert b"differentTitle" in item.path

    def test_modified_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.save()
        self._update(move=False)
        item = self.lib.items().get()
        assert b"differentTitle" not in item.path

    def test_selective_modified_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.genre = "differentGenre"
        mf.save()
        self._update(move=True, fields=["title"])
        item = self.lib.items().get()
        assert b"differentTitle" in item.path
        assert item.genre != "differentGenre"

    def test_selective_modified_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.genre = "differentGenre"
        mf.save()
        self._update(move=False, fields=["title"])
        item = self.lib.items().get()
        assert b"differentTitle" not in item.path
        assert item.genre != "differentGenre"

    def test_modified_album_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = "differentAlbum"
        mf.save()
        self._update(move=True)
        item = self.lib.items().get()
        assert b"differentAlbum" in item.path

    def test_modified_album_metadata_art_moved(self):
        artpath = self.album.artpath
        mf = MediaFile(syspath(self.i.path))
        mf.album = "differentAlbum"
        mf.save()
        self._update(move=True)
        album = self.lib.albums()[0]
        assert artpath != album.artpath
        assert album.artpath is not None

    def test_selective_modified_album_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = "differentAlbum"
        mf.genre = "differentGenre"
        mf.save()
        self._update(move=True, fields=["album"])
        item = self.lib.items().get()
        assert b"differentAlbum" in item.path
        assert item.genre != "differentGenre"

    def test_selective_modified_album_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = "differentAlbum"
        mf.genre = "differentGenre"
        mf.save()
        self._update(move=True, fields=["genres"])
        item = self.lib.items().get()
        assert b"differentAlbum" not in item.path
        assert item.genre == "differentGenre"

    def test_mtime_match_skips_update(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = "differentTitle"
        mf.save()

        # Make in-memory mtime match on-disk mtime.
        self.i.mtime = os.path.getmtime(syspath(self.i.path))
        self.i.store()

        self._update(reset_mtime=False)
        item = self.lib.items().get()
        assert item.title == "full"

    def test_multivalued_albumtype_roundtrip(self):
        # https://github.com/beetbox/beets/issues/4528

        # albumtypes is empty for our test fixtures, so populate it first
        album = self.album
        correct_albumtypes = ["album", "live"]

        # Setting albumtypes does not set albumtype, currently.
        # Using x[0] mirrors https://github.com/beetbox/mediafile/blob/057432ad53b3b84385e5582f69f44dc00d0a725d/mediafile.py#L1928  # noqa: E501
        correct_albumtype = correct_albumtypes[0]

        album.albumtype = correct_albumtype
        album.albumtypes = correct_albumtypes
        album.try_sync(write=True, move=False)

        album.load()
        assert album.albumtype == correct_albumtype
        assert album.albumtypes == correct_albumtypes

        self._update()

        album.load()
        assert album.albumtype == correct_albumtype
        assert album.albumtypes == correct_albumtypes

    def test_modified_metadata_excluded(self):
        mf = MediaFile(syspath(self.i.path))
        mf.lyrics = "new lyrics"
        mf.save()
        self._update(exclude_fields=["lyrics"])
        item = self.lib.items().get()
        assert item.lyrics != "new lyrics"


class PrintTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.io.install()

    def test_print_without_locale(self):
        lang = os.environ.get("LANG")
        if lang:
            del os.environ["LANG"]

        try:
            ui.print_("something")
        except TypeError:
            self.fail("TypeError during print")
        finally:
            if lang:
                os.environ["LANG"] = lang

    def test_print_with_invalid_locale(self):
        old_lang = os.environ.get("LANG")
        os.environ["LANG"] = ""
        old_ctype = os.environ.get("LC_CTYPE")
        os.environ["LC_CTYPE"] = "UTF-8"

        try:
            ui.print_("something")
        except ValueError:
            self.fail("ValueError during print")
        finally:
            if old_lang:
                os.environ["LANG"] = old_lang
            else:
                del os.environ["LANG"]
            if old_ctype:
                os.environ["LC_CTYPE"] = old_ctype
            else:
                del os.environ["LC_CTYPE"]


class ImportTest(BeetsTestCase):
    def test_quiet_timid_disallowed(self):
        config["import"]["quiet"] = True
        config["import"]["timid"] = True
        with pytest.raises(ui.UserError):
            commands.import_files(None, [], None)

    def test_parse_paths_from_logfile(self):
        if os.path.__name__ == "ntpath":
            logfile_content = (
                "import started Wed Jun 15 23:08:26 2022\n"
                "asis C:\\music\\Beatles, The\\The Beatles; C:\\music\\Beatles, The\\The Beatles\\CD 01; C:\\music\\Beatles, The\\The Beatles\\CD 02\n"  # noqa: E501
                "duplicate-replace C:\\music\\Bill Evans\\Trio '65\n"
                "skip C:\\music\\Michael Jackson\\Bad\n"
                "skip C:\\music\\Soulwax\\Any Minute Now\n"
            )
            expected_paths = [
                "C:\\music\\Beatles, The\\The Beatles",
                "C:\\music\\Michael Jackson\\Bad",
                "C:\\music\\Soulwax\\Any Minute Now",
            ]
        else:
            logfile_content = (
                "import started Wed Jun 15 23:08:26 2022\n"
                "asis /music/Beatles, The/The Beatles; /music/Beatles, The/The Beatles/CD 01; /music/Beatles, The/The Beatles/CD 02\n"  # noqa: E501
                "duplicate-replace /music/Bill Evans/Trio '65\n"
                "skip /music/Michael Jackson/Bad\n"
                "skip /music/Soulwax/Any Minute Now\n"
            )
            expected_paths = [
                "/music/Beatles, The/The Beatles",
                "/music/Michael Jackson/Bad",
                "/music/Soulwax/Any Minute Now",
            ]

        logfile = os.path.join(self.temp_dir, b"logfile.log")
        with open(logfile, mode="w") as fp:
            fp.write(logfile_content)
        actual_paths = list(commands._paths_from_logfile(logfile))
        assert actual_paths == expected_paths


@_common.slow_test()
class TestPluginTestCase(PluginTestCase):
    plugin = "test"

    def setUp(self):
        super().setUp()
        config["pluginpath"] = [_common.PLUGINPATH]


class ConfigTest(TestPluginTestCase):
    def setUp(self):
        super().setUp()

        # Don't use the BEETSDIR from `helper`. Instead, we point the home
        # directory there. Some tests will set `BEETSDIR` themselves.
        del os.environ["BEETSDIR"]

        # Also set APPDATA, the Windows equivalent of setting $HOME.
        appdata_dir = os.fsdecode(
            os.path.join(self.temp_dir, b"AppData", b"Roaming")
        )

        self._orig_cwd = os.getcwd()
        self.test_cmd = self._make_test_cmd()
        commands.default_commands.append(self.test_cmd)

        # Default user configuration
        if platform.system() == "Windows":
            self.user_config_dir = os.fsencode(
                os.path.join(appdata_dir, "beets")
            )
        else:
            self.user_config_dir = os.path.join(
                self.temp_dir, b".config", b"beets"
            )
        os.makedirs(syspath(self.user_config_dir))
        self.user_config_path = os.path.join(
            self.user_config_dir, b"config.yaml"
        )

        # Custom BEETSDIR
        self.beetsdir = os.path.join(self.temp_dir, b"beetsdir")
        os.makedirs(syspath(self.beetsdir))
        self.env_patcher = patch(
            "os.environ",
            {"HOME": os.fsdecode(self.temp_dir), "APPDATA": appdata_dir},
        )
        self.env_patcher.start()

        self._reset_config()

    def tearDown(self):
        self.env_patcher.stop()
        commands.default_commands.pop()
        os.chdir(syspath(self._orig_cwd))
        super().tearDown()

    def _make_test_cmd(self):
        test_cmd = ui.Subcommand("test", help="test")

        def run(lib, options, args):
            test_cmd.lib = lib
            test_cmd.options = options
            test_cmd.args = args

        test_cmd.func = run
        return test_cmd

    def _reset_config(self):
        # Config should read files again on demand
        config.clear()
        config._materialized = False

    def write_config_file(self):
        return open(self.user_config_path, "w")

    def test_paths_section_respected(self):
        with self.write_config_file() as config:
            config.write("paths: {x: y}")

        self.run_command("test", lib=None)
        key, template = self.test_cmd.lib.path_formats[0]
        assert key == "x"
        assert template.original == "y"

    def test_default_paths_preserved(self):
        default_formats = ui.get_path_formats()

        self._reset_config()
        with self.write_config_file() as config:
            config.write("paths: {x: y}")
        self.run_command("test", lib=None)
        key, template = self.test_cmd.lib.path_formats[0]
        assert key == "x"
        assert template.original == "y"
        assert self.test_cmd.lib.path_formats[1:] == default_formats

    def test_nonexistant_db(self):
        with self.write_config_file() as config:
            config.write("library: /xxx/yyy/not/a/real/path")

        with pytest.raises(ui.UserError):
            self.run_command("test", lib=None)

    def test_user_config_file(self):
        with self.write_config_file() as file:
            file.write("anoption: value")

        self.run_command("test", lib=None)
        assert config["anoption"].get() == "value"

    def test_replacements_parsed(self):
        with self.write_config_file() as config:
            config.write("replace: {'[xy]': z}")

        self.run_command("test", lib=None)
        replacements = self.test_cmd.lib.replacements
        repls = [(p.pattern, s) for p, s in replacements]  # Compare patterns.
        assert repls == [("[xy]", "z")]

    def test_multiple_replacements_parsed(self):
        with self.write_config_file() as config:
            config.write("replace: {'[xy]': z, foo: bar}")
        self.run_command("test", lib=None)
        replacements = self.test_cmd.lib.replacements
        repls = [(p.pattern, s) for p, s in replacements]
        assert repls == [("[xy]", "z"), ("foo", "bar")]

    def test_cli_config_option(self):
        config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(config_path, "w") as file:
            file.write("anoption: value")
        self.run_command("--config", config_path, "test", lib=None)
        assert config["anoption"].get() == "value"

    def test_cli_config_file_overwrites_user_defaults(self):
        with open(self.user_config_path, "w") as file:
            file.write("anoption: value")

        cli_config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(cli_config_path, "w") as file:
            file.write("anoption: cli overwrite")
        self.run_command("--config", cli_config_path, "test", lib=None)
        assert config["anoption"].get() == "cli overwrite"

    def test_cli_config_file_overwrites_beetsdir_defaults(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)
        env_config_path = os.path.join(self.beetsdir, b"config.yaml")
        with open(env_config_path, "w") as file:
            file.write("anoption: value")

        cli_config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(cli_config_path, "w") as file:
            file.write("anoption: cli overwrite")
        self.run_command("--config", cli_config_path, "test", lib=None)
        assert config["anoption"].get() == "cli overwrite"

    #    @unittest.skip('Difficult to implement with optparse')
    #    def test_multiple_cli_config_files(self):
    #        cli_config_path_1 = os.path.join(self.temp_dir, b'config.yaml')
    #        cli_config_path_2 = os.path.join(self.temp_dir, b'config_2.yaml')
    #
    #        with open(cli_config_path_1, 'w') as file:
    #            file.write('first: value')
    #
    #        with open(cli_config_path_2, 'w') as file:
    #            file.write('second: value')
    #
    #        self.run_command('--config', cli_config_path_1,
    #                      '--config', cli_config_path_2, 'test', lib=None)
    #        assert config['first'].get() == 'value'
    #        assert config['second'].get() == 'value'
    #
    #    @unittest.skip('Difficult to implement with optparse')
    #    def test_multiple_cli_config_overwrite(self):
    #        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
    #        cli_overwrite_config_path = os.path.join(self.temp_dir,
    #                                                 b'overwrite_config.yaml')
    #
    #        with open(cli_config_path, 'w') as file:
    #            file.write('anoption: value')
    #
    #        with open(cli_overwrite_config_path, 'w') as file:
    #            file.write('anoption: overwrite')
    #
    #        self.run_command('--config', cli_config_path,
    #                      '--config', cli_overwrite_config_path, 'test')
    #        assert config['anoption'].get() == 'cli overwrite'

    # FIXME: fails on windows
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_cli_config_paths_resolve_relative_to_user_dir(self):
        cli_config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(cli_config_path, "w") as file:
            file.write("library: beets.db\n")
            file.write("statefile: state")

        self.run_command("--config", cli_config_path, "test", lib=None)
        self.assert_equal_path(
            util.bytestring_path(config["library"].as_filename()),
            os.path.join(self.user_config_dir, b"beets.db"),
        )
        self.assert_equal_path(
            util.bytestring_path(config["statefile"].as_filename()),
            os.path.join(self.user_config_dir, b"state"),
        )

    def test_cli_config_paths_resolve_relative_to_beetsdir(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)

        cli_config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(cli_config_path, "w") as file:
            file.write("library: beets.db\n")
            file.write("statefile: state")

        self.run_command("--config", cli_config_path, "test", lib=None)
        self.assert_equal_path(
            util.bytestring_path(config["library"].as_filename()),
            os.path.join(self.beetsdir, b"beets.db"),
        )
        self.assert_equal_path(
            util.bytestring_path(config["statefile"].as_filename()),
            os.path.join(self.beetsdir, b"state"),
        )

    def test_command_line_option_relative_to_working_dir(self):
        config.read()
        os.chdir(syspath(self.temp_dir))
        self.run_command("--library", "foo.db", "test", lib=None)
        self.assert_equal_path(
            config["library"].as_filename(), os.path.join(os.getcwd(), "foo.db")
        )

    def test_cli_config_file_loads_plugin_commands(self):
        cli_config_path = os.path.join(self.temp_dir, b"config.yaml")
        with open(cli_config_path, "w") as file:
            file.write("pluginpath: %s\n" % _common.PLUGINPATH)
            file.write("plugins: test")

        self.run_command("--config", cli_config_path, "plugin", lib=None)
        assert plugins.find_plugins()[0].is_test_plugin
        self.unload_plugins()

    def test_beetsdir_config(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)

        env_config_path = os.path.join(self.beetsdir, b"config.yaml")
        with open(env_config_path, "w") as file:
            file.write("anoption: overwrite")

        config.read()
        assert config["anoption"].get() == "overwrite"

    def test_beetsdir_points_to_file_error(self):
        beetsdir = os.path.join(self.temp_dir, b"beetsfile")
        open(beetsdir, "a").close()
        os.environ["BEETSDIR"] = os.fsdecode(beetsdir)
        with pytest.raises(ConfigError):
            self.run_command("test")

    def test_beetsdir_config_does_not_load_default_user_config(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)

        with open(self.user_config_path, "w") as file:
            file.write("anoption: value")

        config.read()
        assert not config["anoption"].exists()

    def test_default_config_paths_resolve_relative_to_beetsdir(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)

        config.read()
        self.assert_equal_path(
            util.bytestring_path(config["library"].as_filename()),
            os.path.join(self.beetsdir, b"library.db"),
        )
        self.assert_equal_path(
            util.bytestring_path(config["statefile"].as_filename()),
            os.path.join(self.beetsdir, b"state.pickle"),
        )

    def test_beetsdir_config_paths_resolve_relative_to_beetsdir(self):
        os.environ["BEETSDIR"] = os.fsdecode(self.beetsdir)

        env_config_path = os.path.join(self.beetsdir, b"config.yaml")
        with open(env_config_path, "w") as file:
            file.write("library: beets.db\n")
            file.write("statefile: state")

        config.read()
        self.assert_equal_path(
            util.bytestring_path(config["library"].as_filename()),
            os.path.join(self.beetsdir, b"beets.db"),
        )
        self.assert_equal_path(
            util.bytestring_path(config["statefile"].as_filename()),
            os.path.join(self.beetsdir, b"state"),
        )


class ShowModelChangeTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.io.install()
        self.a = _common.item()
        self.b = _common.item()
        self.a.path = self.b.path

    def _show(self, **kwargs):
        change = ui.show_model_changes(self.a, self.b, **kwargs)
        out = self.io.getoutput()
        return change, out

    def test_identical(self):
        change, out = self._show()
        assert not change
        assert out == ""

    def test_string_fixed_field_change(self):
        self.b.title = "x"
        change, out = self._show()
        assert change
        assert "title" in out

    def test_int_fixed_field_change(self):
        self.b.track = 9
        change, out = self._show()
        assert change
        assert "track" in out

    def test_floats_close_to_identical(self):
        self.a.length = 1.00001
        self.b.length = 1.00005
        change, out = self._show()
        assert not change
        assert out == ""

    def test_floats_different(self):
        self.a.length = 1.00001
        self.b.length = 2.00001
        change, out = self._show()
        assert change
        assert "length" in out

    def test_both_values_shown(self):
        self.a.title = "foo"
        self.b.title = "bar"
        change, out = self._show()
        assert "foo" in out
        assert "bar" in out


class ShowChangeTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.io.install()

        self.items = [_common.item()]
        self.items[0].track = 1
        self.items[0].path = b"/path/to/file.mp3"
        self.info = autotag.AlbumInfo(
            album="the album",
            album_id="album id",
            artist="the artist",
            artist_id="artist id",
            tracks=[
                autotag.TrackInfo(
                    title="the title", track_id="track id", index=1
                )
            ],
        )

    def _show_change(
        self,
        items=None,
        info=None,
        color=False,
        cur_artist="the artist",
        cur_album="the album",
        dist=0.1,
    ):
        """Return an unicode string representing the changes"""
        items = items or self.items
        info = info or self.info
        mapping = dict(zip(items, info.tracks))
        config["ui"]["color"] = color
        config["import"]["detail"] = True
        change_dist = distance(items, info, mapping)
        change_dist._penalties = {"album": [dist], "artist": [dist]}
        commands.show_change(
            cur_artist,
            cur_album,
            autotag.AlbumMatch(change_dist, info, mapping, set(), set()),
        )
        return self.io.getoutput().lower()

    def test_null_change(self):
        msg = self._show_change()
        assert "match (90.0%)" in msg
        assert "album, artist" in msg

    def test_album_data_change(self):
        msg = self._show_change(
            cur_artist="another artist", cur_album="another album"
        )
        assert "another artist -> the artist" in msg
        assert "another album -> the album" in msg

    def test_item_data_change(self):
        self.items[0].title = "different"
        msg = self._show_change()
        assert "different" in msg
        assert "the title" in msg

    def test_item_data_change_with_unicode(self):
        self.items[0].title = "caf\xe9"
        msg = self._show_change()
        assert "caf\xe9" in msg
        assert "the title" in msg

    def test_album_data_change_with_unicode(self):
        msg = self._show_change(cur_artist="caf\xe9", cur_album="another album")
        assert "caf\xe9" in msg
        assert "the artist" in msg

    def test_item_data_change_title_missing(self):
        self.items[0].title = ""
        msg = re.sub(r"  +", " ", self._show_change())
        assert "file.mp3" in msg
        assert "the title" in msg

    def test_item_data_change_title_missing_with_unicode_filename(self):
        self.items[0].title = ""
        self.items[0].path = "/path/to/caf\xe9.mp3".encode()
        msg = re.sub(r"  +", " ", self._show_change())
        assert "caf\xe9.mp3" in msg or "caf.mp3" in msg

    def test_colorize(self):
        assert "test" == ui.uncolorize("test")
        txt = ui.uncolorize("\x1b[31mtest\x1b[39;49;00m")
        assert "test" == txt
        txt = ui.uncolorize("\x1b[31mtest\x1b[39;49;00m test")
        assert "test test" == txt
        txt = ui.uncolorize("\x1b[31mtest\x1b[39;49;00mtest")
        assert "testtest" == txt
        txt = ui.uncolorize("test \x1b[31mtest\x1b[39;49;00m test")
        assert "test test test" == txt

    def test_color_split(self):
        exp = ("test", "")
        res = ui.color_split("test", 5)
        assert exp == res
        exp = ("\x1b[31mtes\x1b[39;49;00m", "\x1b[31mt\x1b[39;49;00m")
        res = ui.color_split("\x1b[31mtest\x1b[39;49;00m", 3)
        assert exp == res

    def test_split_into_lines(self):
        # Test uncolored text
        txt = ui.split_into_lines("test test test", [5, 5, 5])
        assert txt == ["test", "test", "test"]
        # Test multiple colored texts
        colored_text = "\x1b[31mtest \x1b[39;49;00m" * 3
        split_txt = [
            "\x1b[31mtest\x1b[39;49;00m",
            "\x1b[31mtest\x1b[39;49;00m",
            "\x1b[31mtest\x1b[39;49;00m",
        ]
        txt = ui.split_into_lines(colored_text, [5, 5, 5])
        assert txt == split_txt
        # Test single color, multi space text
        colored_text = "\x1b[31m test test test \x1b[39;49;00m"
        txt = ui.split_into_lines(colored_text, [5, 5, 5])
        assert txt == split_txt
        # Test single color, different spacing
        colored_text = "\x1b[31mtest\x1b[39;49;00mtest test test"
        # ToDo: fix color_len to handle mid-text color escapes, and thus
        # split colored texts over newlines (potentially with dashes?)
        split_txt = ["\x1b[31mtest\x1b[39;49;00mt", "est", "test", "test"]
        txt = ui.split_into_lines(colored_text, [5, 5, 5])
        assert txt == split_txt

    def test_album_data_change_wrap_newline(self):
        # Patch ui.term_width to force wrapping
        with patch("beets.ui.commands.ui.term_width", return_value=30):
            # Test newline layout
            config["ui"]["import"]["layout"] = "newline"
            long_name = "another artist with a" + (" very" * 10) + " long name"
            msg = self._show_change(
                cur_artist=long_name, cur_album="another album"
            )
            # _common.log.info("Message:{}".format(msg))
            assert "artist: another artist" in msg
            assert "  -> the artist" in msg
            assert "another album -> the album" not in msg

    def test_item_data_change_wrap_column(self):
        # Patch ui.term_width to force wrapping
        with patch("beets.ui.commands.ui.term_width", return_value=54):
            # Test Column layout
            config["ui"]["import"]["layout"] = "column"
            long_title = "a track with a" + (" very" * 10) + " long name"
            self.items[0].title = long_title
            msg = self._show_change()
            assert "(#1) a track (1:00) -> (#1) the title (0:00)" in msg

    def test_item_data_change_wrap_newline(self):
        # Patch ui.term_width to force wrapping
        with patch("beets.ui.commands.ui.term_width", return_value=30):
            config["ui"]["import"]["layout"] = "newline"
            long_title = "a track with a" + (" very" * 10) + " long name"
            self.items[0].title = long_title
            msg = self._show_change()
            assert "(#1) a track with" in msg
            assert "     -> (#1) the title (0:00)" in msg


@patch("beets.library.Item.try_filesize", Mock(return_value=987))
class SummarizeItemsTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        item = library.Item()
        item.bitrate = 4321
        item.length = 10 * 60 + 54
        item.format = "F"
        self.item = item

    def test_summarize_item(self):
        summary = commands.summarize_items([], True)
        assert summary == ""

        summary = commands.summarize_items([self.item], True)
        assert summary == "F, 4kbps, 10:54, 987.0 B"

    def test_summarize_items(self):
        summary = commands.summarize_items([], False)
        assert summary == "0 items"

        summary = commands.summarize_items([self.item], False)
        assert summary == "1 items, F, 4kbps, 10:54, 987.0 B"

        # make a copy of self.item
        i2 = self.item.copy()

        summary = commands.summarize_items([self.item, i2], False)
        assert summary == "2 items, F, 4kbps, 21:48, 1.9 KiB"

        i2.format = "G"
        summary = commands.summarize_items([self.item, i2], False)
        assert summary == "2 items, F 1, G 1, 4kbps, 21:48, 1.9 KiB"

        summary = commands.summarize_items([self.item, i2, i2], False)
        assert summary == "3 items, G 2, F 1, 4kbps, 32:42, 2.9 KiB"


class PathFormatTest(BeetsTestCase):
    def test_custom_paths_prepend(self):
        default_formats = ui.get_path_formats()

        config["paths"] = {"foo": "bar"}
        pf = ui.get_path_formats()
        key, tmpl = pf[0]
        assert key == "foo"
        assert tmpl.original == "bar"
        assert pf[1:] == default_formats


@_common.slow_test()
class PluginTest(TestPluginTestCase):
    def test_plugin_command_from_pluginpath(self):
        self.run_command("test", lib=None)


@_common.slow_test()
@pytest.mark.xfail(
    os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform == "linux",
    reason="Completion is for some reason unhappy on Ubuntu 24.04 in CI",
)
class CompletionTest(TestPluginTestCase):
    def test_completion(self):
        # Do not load any other bash completion scripts on the system.
        env = dict(os.environ)
        env["BASH_COMPLETION_DIR"] = os.devnull
        env["BASH_COMPLETION_COMPAT_DIR"] = os.devnull

        # Open a `bash` process to run the tests in. We'll pipe in bash
        # commands via stdin.
        cmd = os.environ.get("BEETS_TEST_SHELL", "/bin/bash --norc").split()
        if not has_program(cmd[0]):
            self.skipTest("bash not available")
        tester = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env
        )

        # Load bash_completion library.
        for path in commands.BASH_COMPLETION_PATHS:
            if os.path.exists(syspath(path)):
                bash_completion = path
                break
        else:
            self.skipTest("bash-completion script not found")
        try:
            with open(util.syspath(bash_completion), "rb") as f:
                tester.stdin.writelines(f)
        except OSError:
            self.skipTest("could not read bash-completion script")

        # Load completion script.
        self.io.install()
        self.run_command("completion", lib=None)
        completion_script = self.io.getoutput().encode("utf-8")
        self.io.restore()
        tester.stdin.writelines(completion_script.splitlines(True))

        # Load test suite.
        test_script_name = os.path.join(_common.RSRC, b"test_completion.sh")
        with open(test_script_name, "rb") as test_script_file:
            tester.stdin.writelines(test_script_file)
        out, err = tester.communicate()
        assert tester.returncode == 0
        assert out == b"completion tests passed\n", (
            "test/test_completion.sh did not execute properly. "
            f"Output:{out.decode('utf-8')}"
        )


class CommonOptionsParserCliTest(BeetsTestCase):
    """Test CommonOptionsParser and formatting LibModel formatting on 'list'
    command.
    """

    def setUp(self):
        super().setUp()
        self.item = _common.item()
        self.item.path = b"xxx/yyy"
        self.lib.add(self.item)
        self.lib.add_album([self.item])

    def test_base(self):
        output = self.run_with_output("ls")
        assert output == "the artist - the album - the title\n"

        output = self.run_with_output("ls", "-a")
        assert output == "the album artist - the album\n"

    def test_path_option(self):
        output = self.run_with_output("ls", "-p")
        assert output == "xxx/yyy\n"

        output = self.run_with_output("ls", "-a", "-p")
        assert output == "xxx\n"

    def test_format_option(self):
        output = self.run_with_output("ls", "-f", "$artist")
        assert output == "the artist\n"

        output = self.run_with_output("ls", "-a", "-f", "$albumartist")
        assert output == "the album artist\n"

    def test_format_option_unicode(self):
        output = self.run_with_output(
            b"ls", b"-f", "caf\xe9".encode(util.arg_encoding())
        )
        assert output == "caf\xe9\n"

    def test_root_format_option(self):
        output = self.run_with_output(
            "--format-item", "$artist", "--format-album", "foo", "ls"
        )
        assert output == "the artist\n"

        output = self.run_with_output(
            "--format-item", "foo", "--format-album", "$albumartist", "ls", "-a"
        )
        assert output == "the album artist\n"

    def test_help(self):
        output = self.run_with_output("help")
        assert "Usage:" in output

        output = self.run_with_output("help", "list")
        assert "Usage:" in output

        with pytest.raises(ui.UserError):
            self.run_command("help", "this.is.not.a.real.command")

    def test_stats(self):
        output = self.run_with_output("stats")
        assert "Approximate total size:" in output

        # # Need to have more realistic library setup for this to work
        # output = self.run_with_output('stats', '-e')
        # assert 'Total size:' in output

    def test_version(self):
        output = self.run_with_output("version")
        assert "Python version" in output
        assert "no plugins loaded" in output

        # # Need to have plugin loaded
        # output = self.run_with_output('version')
        # assert 'plugins: ' in output


class CommonOptionsParserTest(BeetsTestCase):
    def test_album_option(self):
        parser = ui.CommonOptionsParser()
        assert not parser._album_flags
        parser.add_album_option()
        assert bool(parser._album_flags)

        assert parser.parse_args([]) == ({"album": None}, [])
        assert parser.parse_args(["-a"]) == ({"album": True}, [])
        assert parser.parse_args(["--album"]) == ({"album": True}, [])

    def test_path_option(self):
        parser = ui.CommonOptionsParser()
        parser.add_path_option()
        assert not parser._album_flags

        config["format_item"].set("$foo")
        assert parser.parse_args([]) == ({"path": None}, [])
        assert config["format_item"].as_str() == "$foo"

        assert parser.parse_args(["-p"]) == (
            {"path": True, "format": "$path"},
            [],
        )
        assert parser.parse_args(["--path"]) == (
            {"path": True, "format": "$path"},
            [],
        )

        assert config["format_item"].as_str() == "$path"
        assert config["format_album"].as_str() == "$path"

    def test_format_option(self):
        parser = ui.CommonOptionsParser()
        parser.add_format_option()
        assert not parser._album_flags

        config["format_item"].set("$foo")
        assert parser.parse_args([]) == ({"format": None}, [])
        assert config["format_item"].as_str() == "$foo"

        assert parser.parse_args(["-f", "$bar"]) == ({"format": "$bar"}, [])
        assert parser.parse_args(["--format", "$baz"]) == (
            {"format": "$baz"},
            [],
        )

        assert config["format_item"].as_str() == "$baz"
        assert config["format_album"].as_str() == "$baz"

    def test_format_option_with_target(self):
        with pytest.raises(KeyError):
            ui.CommonOptionsParser().add_format_option(target="thingy")

        parser = ui.CommonOptionsParser()
        parser.add_format_option(target="item")

        config["format_item"].set("$item")
        config["format_album"].set("$album")

        assert parser.parse_args(["-f", "$bar"]) == ({"format": "$bar"}, [])

        assert config["format_item"].as_str() == "$bar"
        assert config["format_album"].as_str() == "$album"

    def test_format_option_with_album(self):
        parser = ui.CommonOptionsParser()
        parser.add_album_option()
        parser.add_format_option()

        config["format_item"].set("$item")
        config["format_album"].set("$album")

        parser.parse_args(["-f", "$bar"])
        assert config["format_item"].as_str() == "$bar"
        assert config["format_album"].as_str() == "$album"

        parser.parse_args(["-a", "-f", "$foo"])
        assert config["format_item"].as_str() == "$bar"
        assert config["format_album"].as_str() == "$foo"

        parser.parse_args(["-f", "$foo2", "-a"])
        assert config["format_album"].as_str() == "$foo2"

    def test_add_all_common_options(self):
        parser = ui.CommonOptionsParser()
        parser.add_all_common_options()
        assert parser.parse_args([]) == (
            {"album": None, "path": None, "format": None},
            [],
        )


class EncodingTest(BeetsTestCase):
    """Tests for the `terminal_encoding` config option and our
    `_in_encoding` and `_out_encoding` utility functions.
    """

    def out_encoding_overridden(self):
        config["terminal_encoding"] = "fake_encoding"
        assert ui._out_encoding() == "fake_encoding"

    def in_encoding_overridden(self):
        config["terminal_encoding"] = "fake_encoding"
        assert ui._in_encoding() == "fake_encoding"

    def out_encoding_default_utf8(self):
        with patch("sys.stdout") as stdout:
            stdout.encoding = None
            assert ui._out_encoding() == "utf-8"

    def in_encoding_default_utf8(self):
        with patch("sys.stdin") as stdin:
            stdin.encoding = None
            assert ui._in_encoding() == "utf-8"
