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

"""Test file manipulation functionality of Item."""

import os
import shutil
import stat
import unittest
from os.path import join

import pytest

import beets.library
from beets import util
from beets.test import _common
from beets.test._common import item, touch
from beets.test.helper import NEEDS_REFLINK, BeetsTestCase
from beets.util import MoveOperation, bytestring_path, syspath


class MoveTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        # make a temporary file
        self.path = join(self.temp_dir, b"temp.mp3")
        shutil.copy(
            syspath(join(_common.RSRC, b"full.mp3")),
            syspath(self.path),
        )

        # add it to a temporary library
        self.i = beets.library.Item.from_path(self.path)
        self.lib.add(self.i)

        # set up the destination
        self.lib.path_formats = [
            ("default", join("$artist", "$album", "$title"))
        ]
        self.i.artist = "one"
        self.i.album = "two"
        self.i.title = "three"
        self.dest = join(self.libdir, b"one", b"two", b"three.mp3")

        self.otherdir = join(self.temp_dir, b"testotherdir")

    def test_move_arrives(self):
        self.i.move()
        self.assertExists(self.dest)

    def test_move_to_custom_dir(self):
        self.i.move(basedir=self.otherdir)
        self.assertExists(join(self.otherdir, b"one", b"two", b"three.mp3"))

    def test_move_departs(self):
        self.i.move()
        self.assertNotExists(self.path)

    def test_move_in_lib_prunes_empty_dir(self):
        self.i.move()
        old_path = self.i.path
        self.assertExists(old_path)

        self.i.artist = "newArtist"
        self.i.move()
        self.assertNotExists(old_path)
        self.assertNotExists(os.path.dirname(old_path))

    def test_copy_arrives(self):
        self.i.move(operation=MoveOperation.COPY)
        self.assertExists(self.dest)

    def test_copy_does_not_depart(self):
        self.i.move(operation=MoveOperation.COPY)
        self.assertExists(self.path)

    def test_reflink_arrives(self):
        self.i.move(operation=MoveOperation.REFLINK_AUTO)
        self.assertExists(self.dest)

    def test_reflink_does_not_depart(self):
        self.i.move(operation=MoveOperation.REFLINK_AUTO)
        self.assertExists(self.path)

    @NEEDS_REFLINK
    def test_force_reflink_arrives(self):
        self.i.move(operation=MoveOperation.REFLINK)
        self.assertExists(self.dest)

    @NEEDS_REFLINK
    def test_force_reflink_does_not_depart(self):
        self.i.move(operation=MoveOperation.REFLINK)
        self.assertExists(self.path)

    def test_move_changes_path(self):
        self.i.move()
        assert self.i.path == util.normpath(self.dest)

    def test_copy_already_at_destination(self):
        self.i.move()
        old_path = self.i.path
        self.i.move(operation=MoveOperation.COPY)
        assert self.i.path == old_path

    def test_move_already_at_destination(self):
        self.i.move()
        old_path = self.i.path
        self.i.move()
        assert self.i.path == old_path

    def test_move_file_with_colon(self):
        self.i.artist = "C:DOS"
        self.i.move()
        assert "C_DOS" in self.i.path.decode()

    def test_move_file_with_multiple_colons(self):
        # print(beets.config["replace"])
        self.i.artist = "COM:DOS"
        self.i.move()
        assert "COM_DOS" in self.i.path.decode()

    def test_move_file_with_colon_alt_separator(self):
        old = beets.config["drive_sep_replace"]
        beets.config["drive_sep_replace"] = "0"
        self.i.artist = "C:DOS"
        self.i.move()
        assert "C0DOS" in self.i.path.decode()
        beets.config["drive_sep_replace"] = old

    def test_read_only_file_copied_writable(self):
        # Make the source file read-only.
        os.chmod(syspath(self.path), 0o444)

        try:
            self.i.move(operation=MoveOperation.COPY)
            assert os.access(syspath(self.i.path), os.W_OK)
        finally:
            # Make everything writable so it can be cleaned up.
            os.chmod(syspath(self.path), 0o777)
            os.chmod(syspath(self.i.path), 0o777)

    def test_move_avoids_collision_with_existing_file(self):
        # Make a conflicting file at the destination.
        dest = self.i.destination()
        os.makedirs(syspath(os.path.dirname(dest)))
        touch(dest)

        self.i.move()
        assert self.i.path != dest
        assert os.path.dirname(self.i.path) == os.path.dirname(dest)

    @unittest.skipUnless(_common.HAVE_SYMLINK, "need symlinks")
    def test_link_arrives(self):
        self.i.move(operation=MoveOperation.LINK)
        self.assertExists(self.dest)
        assert os.path.islink(syspath(self.dest))
        assert bytestring_path(os.readlink(syspath(self.dest))) == self.path

    @unittest.skipUnless(_common.HAVE_SYMLINK, "need symlinks")
    def test_link_does_not_depart(self):
        self.i.move(operation=MoveOperation.LINK)
        self.assertExists(self.path)

    @unittest.skipUnless(_common.HAVE_SYMLINK, "need symlinks")
    def test_link_changes_path(self):
        self.i.move(operation=MoveOperation.LINK)
        assert self.i.path == util.normpath(self.dest)

    @unittest.skipUnless(_common.HAVE_HARDLINK, "need hardlinks")
    def test_hardlink_arrives(self):
        self.i.move(operation=MoveOperation.HARDLINK)
        self.assertExists(self.dest)
        s1 = os.stat(syspath(self.path))
        s2 = os.stat(syspath(self.dest))
        assert (s1[stat.ST_INO], s1[stat.ST_DEV]) == (
            s2[stat.ST_INO],
            s2[stat.ST_DEV],
        )

    @unittest.skipUnless(_common.HAVE_HARDLINK, "need hardlinks")
    def test_hardlink_does_not_depart(self):
        self.i.move(operation=MoveOperation.HARDLINK)
        self.assertExists(self.path)

    @unittest.skipUnless(_common.HAVE_HARDLINK, "need hardlinks")
    def test_hardlink_changes_path(self):
        self.i.move(operation=MoveOperation.HARDLINK)
        assert self.i.path == util.normpath(self.dest)


class HelperTest(BeetsTestCase):
    def test_ancestry_works_on_file(self):
        p = "/a/b/c"
        a = ["/", "/a", "/a/b"]
        assert util.ancestry(p) == a

    def test_ancestry_works_on_dir(self):
        p = "/a/b/c/"
        a = ["/", "/a", "/a/b", "/a/b/c"]
        assert util.ancestry(p) == a

    def test_ancestry_works_on_relative(self):
        p = "a/b/c"
        a = ["a", "a/b"]
        assert util.ancestry(p) == a

    def test_components_works_on_file(self):
        p = "/a/b/c"
        a = ["/", "a", "b", "c"]
        assert util.components(p) == a

    def test_components_works_on_dir(self):
        p = "/a/b/c/"
        a = ["/", "a", "b", "c"]
        assert util.components(p) == a

    def test_components_works_on_relative(self):
        p = "a/b/c"
        a = ["a", "b", "c"]
        assert util.components(p) == a

    def test_forward_slash(self):
        p = rb"C:\a\b\c"
        a = rb"C:/a/b/c"
        assert util.path_as_posix(p) == a


class AlbumFileTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        # Make library and item.
        self.lib.path_formats = [
            ("default", join("$albumartist", "$album", "$title"))
        ]
        self.i = item(self.lib)
        # Make a file for the item.
        self.i.path = self.i.destination()
        util.mkdirall(self.i.path)
        touch(self.i.path)
        # Make an album.
        self.ai = self.lib.add_album((self.i,))
        # Alternate destination dir.
        self.otherdir = os.path.join(self.temp_dir, b"testotherdir")

    def test_albuminfo_move_changes_paths(self):
        self.ai.album = "newAlbumName"
        self.ai.move()
        self.ai.store()
        self.i.load()

        assert b"newAlbumName" in self.i.path

    def test_albuminfo_move_moves_file(self):
        oldpath = self.i.path
        self.ai.album = "newAlbumName"
        self.ai.move()
        self.ai.store()
        self.i.load()

        self.assertNotExists(oldpath)
        self.assertExists(self.i.path)

    def test_albuminfo_move_copies_file(self):
        oldpath = self.i.path
        self.ai.album = "newAlbumName"
        self.ai.move(operation=MoveOperation.COPY)
        self.ai.store()
        self.i.load()

        self.assertExists(oldpath)
        self.assertExists(self.i.path)

    @NEEDS_REFLINK
    def test_albuminfo_move_reflinks_file(self):
        oldpath = self.i.path
        self.ai.album = "newAlbumName"
        self.ai.move(operation=MoveOperation.REFLINK)
        self.ai.store()
        self.i.load()

        assert os.path.exists(oldpath)
        assert os.path.exists(self.i.path)

    def test_albuminfo_move_to_custom_dir(self):
        self.ai.move(basedir=self.otherdir)
        self.i.load()
        self.ai.store()
        assert b"testotherdir" in self.i.path


class ArtFileTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        # Make library and item.
        self.i = item(self.lib)
        self.i.path = self.i.destination()
        # Make a music file.
        util.mkdirall(self.i.path)
        touch(self.i.path)
        # Make an album.
        self.ai = self.lib.add_album((self.i,))
        # Make an art file too.
        self.art = self.lib.get_album(self.i).art_destination("something.jpg")
        touch(self.art)
        self.ai.artpath = self.art
        self.ai.store()
        # Alternate destination dir.
        self.otherdir = os.path.join(self.temp_dir, b"testotherdir")

    def test_art_deleted_when_items_deleted(self):
        self.assertExists(self.art)
        self.ai.remove(True)
        self.assertNotExists(self.art)

    def test_art_moves_with_album(self):
        self.assertExists(self.art)
        oldpath = self.i.path
        self.ai.album = "newAlbum"
        self.ai.move()
        self.i.load()

        assert self.i.path != oldpath
        self.assertNotExists(self.art)
        newart = self.lib.get_album(self.i).art_destination(self.art)
        self.assertExists(newart)

    def test_art_moves_with_album_to_custom_dir(self):
        # Move the album to another directory.
        self.ai.move(basedir=self.otherdir)
        self.ai.store()
        self.i.load()

        # Art should be in new directory.
        self.assertNotExists(self.art)
        newart = self.lib.get_album(self.i).artpath
        self.assertExists(newart)
        assert b"testotherdir" in newart

    def test_setart_copies_image(self):
        util.remove(self.art)

        newart = os.path.join(self.libdir, b"newart.jpg")
        touch(newart)
        i2 = item()
        i2.path = self.i.path
        i2.artist = "someArtist"
        ai = self.lib.add_album((i2,))
        i2.move(operation=MoveOperation.COPY)

        assert ai.artpath is None
        ai.set_art(newart)
        self.assertExists(ai.artpath)

    def test_setart_to_existing_art_works(self):
        util.remove(self.art)

        # Original art.
        newart = os.path.join(self.libdir, b"newart.jpg")
        touch(newart)
        i2 = item()
        i2.path = self.i.path
        i2.artist = "someArtist"
        ai = self.lib.add_album((i2,))
        i2.move(operation=MoveOperation.COPY)
        ai.set_art(newart)

        # Set the art again.
        ai.set_art(ai.artpath)
        self.assertExists(ai.artpath)

    def test_setart_to_existing_but_unset_art_works(self):
        newart = os.path.join(self.libdir, b"newart.jpg")
        touch(newart)
        i2 = item()
        i2.path = self.i.path
        i2.artist = "someArtist"
        ai = self.lib.add_album((i2,))
        i2.move(operation=MoveOperation.COPY)

        # Copy the art to the destination.
        artdest = ai.art_destination(newart)
        shutil.copy(syspath(newart), syspath(artdest))

        # Set the art again.
        ai.set_art(artdest)
        self.assertExists(ai.artpath)

    def test_setart_to_conflicting_file_gets_new_path(self):
        newart = os.path.join(self.libdir, b"newart.jpg")
        touch(newart)
        i2 = item()
        i2.path = self.i.path
        i2.artist = "someArtist"
        ai = self.lib.add_album((i2,))
        i2.move(operation=MoveOperation.COPY)

        # Make a file at the destination.
        artdest = ai.art_destination(newart)
        touch(artdest)

        # Set the art.
        ai.set_art(newart)
        assert artdest != ai.artpath
        assert os.path.dirname(artdest) == os.path.dirname(ai.artpath)

    def test_setart_sets_permissions(self):
        util.remove(self.art)

        newart = os.path.join(self.libdir, b"newart.jpg")
        touch(newart)
        os.chmod(syspath(newart), 0o400)  # read-only

        try:
            i2 = item()
            i2.path = self.i.path
            i2.artist = "someArtist"
            ai = self.lib.add_album((i2,))
            i2.move(operation=MoveOperation.COPY)
            ai.set_art(newart)

            mode = stat.S_IMODE(os.stat(syspath(ai.artpath)).st_mode)
            assert mode & stat.S_IRGRP
            assert os.access(syspath(ai.artpath), os.W_OK)

        finally:
            # Make everything writable so it can be cleaned up.
            os.chmod(syspath(newart), 0o777)
            os.chmod(syspath(ai.artpath), 0o777)

    def test_move_last_file_moves_albumart(self):
        oldartpath = self.lib.albums()[0].artpath
        self.assertExists(oldartpath)

        self.ai.album = "different_album"
        self.ai.store()
        self.ai.items()[0].move()

        artpath = self.lib.albums()[0].artpath
        assert b"different_album" in artpath
        self.assertExists(artpath)
        self.assertNotExists(oldartpath)

    def test_move_not_last_file_does_not_move_albumart(self):
        i2 = item()
        i2.albumid = self.ai.id
        self.lib.add(i2)

        oldartpath = self.lib.albums()[0].artpath
        self.assertExists(oldartpath)

        self.i.album = "different_album"
        self.i.album_id = None  # detach from album
        self.i.move()

        artpath = self.lib.albums()[0].artpath
        assert b"different_album" not in artpath
        assert artpath == oldartpath
        self.assertExists(oldartpath)


class RemoveTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        # Make library and item.
        self.i = item(self.lib)
        self.i.path = self.i.destination()
        # Make a music file.
        util.mkdirall(self.i.path)
        touch(self.i.path)
        # Make an album with the item.
        self.ai = self.lib.add_album((self.i,))

    def test_removing_last_item_prunes_empty_dir(self):
        parent = os.path.dirname(self.i.path)
        self.assertExists(parent)
        self.i.remove(True)
        self.assertNotExists(parent)

    def test_removing_last_item_preserves_nonempty_dir(self):
        parent = os.path.dirname(self.i.path)
        touch(os.path.join(parent, b"dummy.txt"))
        self.i.remove(True)
        self.assertExists(parent)

    def test_removing_last_item_prunes_dir_with_blacklisted_file(self):
        parent = os.path.dirname(self.i.path)
        touch(os.path.join(parent, b".DS_Store"))
        self.i.remove(True)
        self.assertNotExists(parent)

    def test_removing_without_delete_leaves_file(self):
        path = self.i.path
        self.i.remove(False)
        self.assertExists(path)

    def test_removing_last_item_preserves_library_dir(self):
        self.i.remove(True)
        self.assertExists(self.libdir)

    def test_removing_item_outside_of_library_deletes_nothing(self):
        self.lib.directory = os.path.join(self.temp_dir, b"xxx")
        parent = os.path.dirname(self.i.path)
        self.i.remove(True)
        self.assertExists(parent)

    def test_removing_last_item_in_album_with_albumart_prunes_dir(self):
        artfile = os.path.join(self.temp_dir, b"testart.jpg")
        touch(artfile)
        self.ai.set_art(artfile)
        self.ai.store()

        parent = os.path.dirname(self.i.path)
        self.i.remove(True)
        self.assertNotExists(parent)


# Tests that we can "delete" nonexistent files.
class SoftRemoveTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.path = os.path.join(self.temp_dir, b"testfile")
        touch(self.path)

    def test_soft_remove_deletes_file(self):
        util.remove(self.path, True)
        self.assertNotExists(self.path)

    def test_soft_remove_silent_on_no_file(self):
        try:
            util.remove(self.path + b"XXX", True)
        except OSError:
            self.fail("OSError when removing path")


class SafeMoveCopyTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.path = os.path.join(self.temp_dir, b"testfile")
        touch(self.path)
        self.otherpath = os.path.join(self.temp_dir, b"testfile2")
        touch(self.otherpath)
        self.dest = self.path + b".dest"

    def test_successful_move(self):
        util.move(self.path, self.dest)
        self.assertExists(self.dest)
        self.assertNotExists(self.path)

    def test_successful_copy(self):
        util.copy(self.path, self.dest)
        self.assertExists(self.dest)
        self.assertExists(self.path)

    @NEEDS_REFLINK
    def test_successful_reflink(self):
        util.reflink(self.path, self.dest)
        self.assertExists(self.dest)
        self.assertExists(self.path)

    def test_unsuccessful_move(self):
        with pytest.raises(util.FilesystemError):
            util.move(self.path, self.otherpath)

    def test_unsuccessful_copy(self):
        with pytest.raises(util.FilesystemError):
            util.copy(self.path, self.otherpath)

    def test_unsuccessful_reflink(self):
        with pytest.raises(util.FilesystemError, match="target exists"):
            util.reflink(self.path, self.otherpath)

    def test_self_move(self):
        util.move(self.path, self.path)
        self.assertExists(self.path)

    def test_self_copy(self):
        util.copy(self.path, self.path)
        self.assertExists(self.path)


class PruneTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.base = os.path.join(self.temp_dir, b"testdir")
        os.mkdir(syspath(self.base))
        self.sub = os.path.join(self.base, b"subdir")
        os.mkdir(syspath(self.sub))

    def test_prune_existent_directory(self):
        util.prune_dirs(self.sub, self.base)
        self.assertExists(self.base)
        self.assertNotExists(self.sub)

    def test_prune_nonexistent_directory(self):
        util.prune_dirs(os.path.join(self.sub, b"another"), self.base)
        self.assertExists(self.base)
        self.assertNotExists(self.sub)


class WalkTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.base = os.path.join(self.temp_dir, b"testdir")
        os.mkdir(syspath(self.base))
        touch(os.path.join(self.base, b"y"))
        touch(os.path.join(self.base, b"x"))
        os.mkdir(syspath(os.path.join(self.base, b"d")))
        touch(os.path.join(self.base, b"d", b"z"))

    def test_sorted_files(self):
        res = list(util.sorted_walk(self.base))
        assert len(res) == 2
        assert res[0] == (self.base, [b"d"], [b"x", b"y"])
        assert res[1] == (os.path.join(self.base, b"d"), [], [b"z"])

    def test_ignore_file(self):
        res = list(util.sorted_walk(self.base, (b"x",)))
        assert len(res) == 2
        assert res[0] == (self.base, [b"d"], [b"y"])
        assert res[1] == (os.path.join(self.base, b"d"), [], [b"z"])

    def test_ignore_directory(self):
        res = list(util.sorted_walk(self.base, (b"d",)))
        assert len(res) == 1
        assert res[0] == (self.base, [], [b"x", b"y"])

    def test_ignore_everything(self):
        res = list(util.sorted_walk(self.base, (b"*",)))
        assert len(res) == 1
        assert res[0] == (self.base, [], [])


class UniquePathTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        self.base = os.path.join(self.temp_dir, b"testdir")
        os.mkdir(syspath(self.base))
        touch(os.path.join(self.base, b"x.mp3"))
        touch(os.path.join(self.base, b"x.1.mp3"))
        touch(os.path.join(self.base, b"x.2.mp3"))
        touch(os.path.join(self.base, b"y.mp3"))

    def test_new_file_unchanged(self):
        path = util.unique_path(os.path.join(self.base, b"z.mp3"))
        assert path == os.path.join(self.base, b"z.mp3")

    def test_conflicting_file_appends_1(self):
        path = util.unique_path(os.path.join(self.base, b"y.mp3"))
        assert path == os.path.join(self.base, b"y.1.mp3")

    def test_conflicting_file_appends_higher_number(self):
        path = util.unique_path(os.path.join(self.base, b"x.mp3"))
        assert path == os.path.join(self.base, b"x.3.mp3")

    def test_conflicting_file_with_number_increases_number(self):
        path = util.unique_path(os.path.join(self.base, b"x.1.mp3"))
        assert path == os.path.join(self.base, b"x.3.mp3")


class MkDirAllTest(BeetsTestCase):
    def test_parent_exists(self):
        path = os.path.join(self.temp_dir, b"foo", b"bar", b"baz", b"qux.mp3")
        util.mkdirall(path)
        self.assertIsDir(os.path.join(self.temp_dir, b"foo", b"bar", b"baz"))

    def test_child_does_not_exist(self):
        path = os.path.join(self.temp_dir, b"foo", b"bar", b"baz", b"qux.mp3")
        util.mkdirall(path)
        self.assertNotExists(path)
