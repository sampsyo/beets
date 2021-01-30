# -*- coding: utf-8 -*-
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

"""Tests for the command-line interface.
"""
from __future__ import division, absolute_import, print_function

import os
import shutil
import re
import subprocess
import platform
import six
import unittest

from mock import patch, Mock
from test import _common
from test.helper import capture_stdout, has_program, TestHelper, control_stdin

from beets import library
from beets import ui
from beets.ui import commands
from beets import autotag
from beets.autotag.match import distance
from mediafile import MediaFile
from beets import config
from beets import plugins
from confuse import ConfigError
from beets import util
from beets.util import syspath, MoveOperation


class ListTest(unittest.TestCase):
    def setUp(self):
        self.lib = library.Library(':memory:')
        self.item = _common.item()
        self.item.path = 'xxx/yyy'
        self.lib.add(self.item)
        self.lib.add_album([self.item])

    def _run_list(self, query=u'', album=False, path=False, fmt=u''):
        with capture_stdout() as stdout:
            commands.list_items(self.lib, query, album, fmt)
        return stdout

    def test_list_outputs_item(self):
        stdout = self._run_list()
        self.assertIn(u'the title', stdout.getvalue())

    def test_list_unicode_query(self):
        self.item.title = u'na\xefve'
        self.item.store()
        self.lib._connection().commit()

        stdout = self._run_list([u'na\xefve'])
        out = stdout.getvalue()
        if six.PY2:
            out = out.decode(stdout.encoding)
        self.assertTrue(u'na\xefve' in out)

    def test_list_item_path(self):
        stdout = self._run_list(fmt=u'$path')
        self.assertEqual(stdout.getvalue().strip(), u'xxx/yyy')

    def test_list_album_outputs_something(self):
        stdout = self._run_list(album=True)
        self.assertGreater(len(stdout.getvalue()), 0)

    def test_list_album_path(self):
        stdout = self._run_list(album=True, fmt=u'$path')
        self.assertEqual(stdout.getvalue().strip(), u'xxx')

    def test_list_album_omits_title(self):
        stdout = self._run_list(album=True)
        self.assertNotIn(u'the title', stdout.getvalue())

    def test_list_uses_track_artist(self):
        stdout = self._run_list()
        self.assertIn(u'the artist', stdout.getvalue())
        self.assertNotIn(u'the album artist', stdout.getvalue())

    def test_list_album_uses_album_artist(self):
        stdout = self._run_list(album=True)
        self.assertNotIn(u'the artist', stdout.getvalue())
        self.assertIn(u'the album artist', stdout.getvalue())

    def test_list_item_format_artist(self):
        stdout = self._run_list(fmt=u'$artist')
        self.assertIn(u'the artist', stdout.getvalue())

    def test_list_item_format_multiple(self):
        stdout = self._run_list(fmt=u'$artist - $album - $year')
        self.assertEqual(u'the artist - the album - 0001',
                         stdout.getvalue().strip())

    def test_list_album_format(self):
        stdout = self._run_list(album=True, fmt=u'$genre')
        self.assertIn(u'the genre', stdout.getvalue())
        self.assertNotIn(u'the album', stdout.getvalue())


class RemoveTest(_common.TestCase, TestHelper):
    def setUp(self):
        super(RemoveTest, self).setUp()

        self.io.install()

        self.libdir = os.path.join(self.temp_dir, b'testlibdir')
        os.mkdir(syspath(self.libdir))

        # Copy a file into the library.
        self.lib = library.Library(':memory:', self.libdir)
        self.item_path = os.path.join(_common.RSRC, b'full.mp3')
        self.i = library.Item.from_path(self.item_path)
        self.lib.add(self.i)
        self.i.move(operation=MoveOperation.COPY)

    def test_remove_items_no_delete(self):
        self.io.addinput('y')
        commands.remove_items(self.lib, u'', False, False, False)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 0)
        self.assertExists(self.i.path)

    def test_remove_items_with_delete(self):
        self.io.addinput('y')
        commands.remove_items(self.lib, u'', False, True, False)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 0)
        self.assertNotExists(self.i.path)

    def test_remove_items_with_force_no_delete(self):
        commands.remove_items(self.lib, u'', False, False, True)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 0)
        self.assertExists(self.i.path)

    def test_remove_items_with_force_delete(self):
        commands.remove_items(self.lib, u'', False, True, True)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 0)
        self.assertNotExists(self.i.path)

    def test_remove_items_select_with_delete(self):
        i2 = library.Item.from_path(self.item_path)
        self.lib.add(i2)
        i2.move(operation=MoveOperation.COPY)

        for s in ('s', 'y', 'n'):
            self.io.addinput(s)
        commands.remove_items(self.lib, u'', False, True, False)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 1)
        # There is probably no guarantee that the items are queried in any
        # spcecific order, thus just ensure that exactly one was removed.
        # To improve upon this, self.io would need to have the capability to
        # generate input that depends on previous output.
        num_existing = 0
        num_existing += 1 if os.path.exists(syspath(self.i.path)) else 0
        num_existing += 1 if os.path.exists(syspath(i2.path)) else 0
        self.assertEqual(num_existing, 1)

    def test_remove_albums_select_with_delete(self):
        a1 = self.add_album_fixture()
        a2 = self.add_album_fixture()
        path1 = a1.items()[0].path
        path2 = a2.items()[0].path
        items = self.lib.items()
        self.assertEqual(len(list(items)), 3)

        for s in ('s', 'y', 'n'):
            self.io.addinput(s)
        commands.remove_items(self.lib, u'', True, True, False)
        items = self.lib.items()
        self.assertEqual(len(list(items)), 2)  # incl. the item from setUp()
        # See test_remove_items_select_with_delete()
        num_existing = 0
        num_existing += 1 if os.path.exists(syspath(path1)) else 0
        num_existing += 1 if os.path.exists(syspath(path2)) else 0
        self.assertEqual(num_existing, 1)


class ModifyTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.setup_beets()
        self.album = self.add_album_fixture()
        [self.item] = self.album.items()

    def tearDown(self):
        self.teardown_beets()

    def modify_inp(self, inp, *args):
        with control_stdin(inp):
            self.run_command('modify', *args)

    def modify(self, *args):
        self.modify_inp('y', *args)

    # Item tests

    def test_modify_item(self):
        self.modify(u"title=newTitle")
        item = self.lib.items().get()
        self.assertEqual(item.title, u'newTitle')

    def test_modify_item_abort(self):
        item = self.lib.items().get()
        title = item.title
        self.modify_inp('n', u"title=newTitle")
        item = self.lib.items().get()
        self.assertEqual(item.title, title)

    def test_modify_item_no_change(self):
        title = u"Tracktitle"
        item = self.add_item_fixture(title=title)
        self.modify_inp('y', u"title", u"title={0}".format(title))
        item = self.lib.items(title).get()
        self.assertEqual(item.title, title)

    def test_modify_write_tags(self):
        self.modify(u"title=newTitle")
        item = self.lib.items().get()
        item.read()
        self.assertEqual(item.title, u'newTitle')

    def test_modify_dont_write_tags(self):
        self.modify(u"--nowrite", u"title=newTitle")
        item = self.lib.items().get()
        item.read()
        self.assertNotEqual(item.title, 'newTitle')

    def test_move(self):
        self.modify(u"title=newTitle")
        item = self.lib.items().get()
        self.assertIn(b'newTitle', item.path)

    def test_not_move(self):
        self.modify(u"--nomove", u"title=newTitle")
        item = self.lib.items().get()
        self.assertNotIn(b'newTitle', item.path)

    def test_no_write_no_move(self):
        self.modify(u"--nomove", u"--nowrite", u"title=newTitle")
        item = self.lib.items().get()
        item.read()
        self.assertNotIn(b'newTitle', item.path)
        self.assertNotEqual(item.title, u'newTitle')

    def test_update_mtime(self):
        item = self.item
        old_mtime = item.mtime

        self.modify(u"title=newTitle")
        item.load()
        self.assertNotEqual(old_mtime, item.mtime)
        self.assertEqual(item.current_mtime(), item.mtime)

    def test_reset_mtime_with_no_write(self):
        item = self.item

        self.modify(u"--nowrite", u"title=newTitle")
        item.load()
        self.assertEqual(0, item.mtime)

    def test_selective_modify(self):
        title = u"Tracktitle"
        album = u"album"
        original_artist = u"composer"
        new_artist = u"coverArtist"
        for i in range(0, 10):
            self.add_item_fixture(title=u"{0}{1}".format(title, i),
                                  artist=original_artist,
                                  album=album)
        self.modify_inp('s\ny\ny\ny\nn\nn\ny\ny\ny\ny\nn',
                        title, u"artist={0}".format(new_artist))
        original_items = self.lib.items(u"artist:{0}".format(original_artist))
        new_items = self.lib.items(u"artist:{0}".format(new_artist))
        self.assertEqual(len(list(original_items)), 3)
        self.assertEqual(len(list(new_items)), 7)

    # Album Tests

    def test_modify_album(self):
        self.modify(u"--album", u"album=newAlbum")
        album = self.lib.albums().get()
        self.assertEqual(album.album, u'newAlbum')

    def test_modify_album_write_tags(self):
        self.modify(u"--album", u"album=newAlbum")
        item = self.lib.items().get()
        item.read()
        self.assertEqual(item.album, u'newAlbum')

    def test_modify_album_dont_write_tags(self):
        self.modify(u"--album", u"--nowrite", u"album=newAlbum")
        item = self.lib.items().get()
        item.read()
        self.assertEqual(item.album, u'the album')

    def test_album_move(self):
        self.modify(u"--album", u"album=newAlbum")
        item = self.lib.items().get()
        item.read()
        self.assertIn(b'newAlbum', item.path)

    def test_album_not_move(self):
        self.modify(u"--nomove", u"--album", u"album=newAlbum")
        item = self.lib.items().get()
        item.read()
        self.assertNotIn(b'newAlbum', item.path)

    # Misc

    def test_write_initial_key_tag(self):
        self.modify(u"initial_key=C#m")
        item = self.lib.items().get()
        mediafile = MediaFile(syspath(item.path))
        self.assertEqual(mediafile.initial_key, u'C#m')

    def test_set_flexattr(self):
        self.modify(u"flexattr=testAttr")
        item = self.lib.items().get()
        self.assertEqual(item.flexattr, u'testAttr')

    def test_remove_flexattr(self):
        item = self.lib.items().get()
        item.flexattr = u'testAttr'
        item.store()

        self.modify(u"flexattr!")
        item = self.lib.items().get()
        self.assertNotIn(u"flexattr", item)

    @unittest.skip(u'not yet implemented')
    def test_delete_initial_key_tag(self):
        item = self.lib.items().get()
        item.initial_key = u'C#m'
        item.write()
        item.store()

        mediafile = MediaFile(syspath(item.path))
        self.assertEqual(mediafile.initial_key, u'C#m')

        self.modify(u"initial_key!")
        mediafile = MediaFile(syspath(item.path))
        self.assertIsNone(mediafile.initial_key)

    def test_arg_parsing_colon_query(self):
        (query, mods, dels) = commands.modify_parse_args([u"title:oldTitle",
                                                          u"title=newTitle"])
        self.assertEqual(query, [u"title:oldTitle"])
        self.assertEqual(mods, {"title": u"newTitle"})

    def test_arg_parsing_delete(self):
        (query, mods, dels) = commands.modify_parse_args([u"title:oldTitle",
                                                          u"title!"])
        self.assertEqual(query, [u"title:oldTitle"])
        self.assertEqual(dels, ["title"])

    def test_arg_parsing_query_with_exclaimation(self):
        (query, mods, dels) = commands.modify_parse_args([u"title:oldTitle!",
                                                          u"title=newTitle!"])
        self.assertEqual(query, [u"title:oldTitle!"])
        self.assertEqual(mods, {"title": u"newTitle!"})

    def test_arg_parsing_equals_in_value(self):
        (query, mods, dels) = commands.modify_parse_args([u"title:foo=bar",
                                                          u"title=newTitle"])
        self.assertEqual(query, [u"title:foo=bar"])
        self.assertEqual(mods, {"title": u"newTitle"})


class WriteTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    def write_cmd(self, *args):
        return self.run_with_output('write', *args)

    def test_update_mtime(self):
        item = self.add_item_fixture()
        item['title'] = u'a new title'
        item.store()

        item = self.lib.items().get()
        self.assertEqual(item.mtime, 0)

        self.write_cmd()
        item = self.lib.items().get()
        self.assertEqual(item.mtime, item.current_mtime())

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

        self.assertEqual(output, '')

    def test_write_metadata_field(self):
        item = self.add_item_fixture()
        item.read()
        old_title = item.title

        item.title = u'new title'
        item.store()

        output = self.write_cmd()

        self.assertTrue(u'{0} -> new title'.format(old_title)
                        in output)


class MoveTest(_common.TestCase):
    def setUp(self):
        super(MoveTest, self).setUp()

        self.io.install()

        self.libdir = os.path.join(self.temp_dir, b'testlibdir')
        os.mkdir(syspath(self.libdir))

        self.itempath = os.path.join(self.libdir, b'srcfile')
        shutil.copy(
            syspath(os.path.join(_common.RSRC, b'full.mp3')),
            syspath(self.itempath),
        )

        # Add a file to the library but don't copy it in yet.
        self.lib = library.Library(':memory:', self.libdir)
        self.i = library.Item.from_path(self.itempath)
        self.lib.add(self.i)
        self.album = self.lib.add_album([self.i])

        # Alternate destination directory.
        self.otherdir = os.path.join(self.temp_dir, b'testotherdir')

    def _move(self, query=(), dest=None, copy=False, album=False,
              pretend=False, export=False):
        commands.move_items(self.lib, dest, query, copy, album, pretend,
                            export=export)

    def test_move_item(self):
        self._move()
        self.i.load()
        self.assertTrue(b'testlibdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_copy_item(self):
        self._move(copy=True)
        self.i.load()
        self.assertTrue(b'testlibdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertExists(self.itempath)

    def test_move_album(self):
        self._move(album=True)
        self.i.load()
        self.assertTrue(b'testlibdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_copy_album(self):
        self._move(copy=True, album=True)
        self.i.load()
        self.assertTrue(b'testlibdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertExists(self.itempath)

    def test_move_item_custom_dir(self):
        self._move(dest=self.otherdir)
        self.i.load()
        self.assertTrue(b'testotherdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_move_album_custom_dir(self):
        self._move(dest=self.otherdir, album=True)
        self.i.load()
        self.assertTrue(b'testotherdir' in self.i.path)
        self.assertExists(self.i.path)
        self.assertNotExists(self.itempath)

    def test_pretend_move_item(self):
        self._move(dest=self.otherdir, pretend=True)
        self.i.load()
        self.assertIn(b'srcfile', self.i.path)

    def test_pretend_move_album(self):
        self._move(album=True, pretend=True)
        self.i.load()
        self.assertIn(b'srcfile', self.i.path)

    def test_export_item_custom_dir(self):
        self._move(dest=self.otherdir, export=True)
        self.i.load()
        self.assertEqual(self.i.path, self.itempath)
        self.assertExists(self.otherdir)

    def test_export_album_custom_dir(self):
        self._move(dest=self.otherdir, album=True, export=True)
        self.i.load()
        self.assertEqual(self.i.path, self.itempath)
        self.assertExists(self.otherdir)

    def test_pretend_export_item(self):
        self._move(dest=self.otherdir, pretend=True, export=True)
        self.i.load()
        self.assertIn(b'srcfile', self.i.path)
        self.assertNotExists(self.otherdir)


class UpdateTest(_common.TestCase):
    def setUp(self):
        super(UpdateTest, self).setUp()

        self.io.install()

        self.libdir = os.path.join(self.temp_dir, b'testlibdir')

        # Copy a file into the library.
        self.lib = library.Library(':memory:', self.libdir)
        item_path = os.path.join(_common.RSRC, b'full.mp3')
        item_path_two = os.path.join(_common.RSRC, b'full.flac')
        self.i = library.Item.from_path(item_path)
        self.i2 = library.Item.from_path(item_path_two)
        self.lib.add(self.i)
        self.lib.add(self.i2)
        self.i.move(operation=MoveOperation.COPY)
        self.i2.move(operation=MoveOperation.COPY)
        self.album = self.lib.add_album([self.i, self.i2])

        # Album art.
        artfile = os.path.join(self.temp_dir, b'testart.jpg')
        _common.touch(artfile)
        self.album.set_art(artfile)
        self.album.store()
        util.remove(artfile)

    def _update(self, query=(), album=False, move=False, reset_mtime=True,
                fields=None):
        self.io.addinput('y')
        if reset_mtime:
            self.i.mtime = 0
            self.i.store()
        commands.update_items(self.lib, query, album, move, False,
                              fields=fields)

    def test_delete_removes_item(self):
        self.assertTrue(list(self.lib.items()))
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        self.assertFalse(list(self.lib.items()))

    def test_delete_removes_album(self):
        self.assertTrue(self.lib.albums())
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        self.assertFalse(self.lib.albums())

    def test_delete_removes_album_art(self):
        artpath = self.album.artpath
        self.assertExists(artpath)
        util.remove(self.i.path)
        util.remove(self.i2.path)
        self._update()
        self.assertNotExists(artpath)

    def test_modified_metadata_detected(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.save()
        self._update()
        item = self.lib.items().get()
        self.assertEqual(item.title, u'differentTitle')

    def test_modified_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.save()
        self._update(move=True)
        item = self.lib.items().get()
        self.assertTrue(b'differentTitle' in item.path)

    def test_modified_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.save()
        self._update(move=False)
        item = self.lib.items().get()
        self.assertTrue(b'differentTitle' not in item.path)

    def test_selective_modified_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.genre = u'differentGenre'
        mf.save()
        self._update(move=True, fields=['title'])
        item = self.lib.items().get()
        self.assertTrue(b'differentTitle' in item.path)
        self.assertNotEqual(item.genre, u'differentGenre')

    def test_selective_modified_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.genre = u'differentGenre'
        mf.save()
        self._update(move=False, fields=['title'])
        item = self.lib.items().get()
        self.assertTrue(b'differentTitle' not in item.path)
        self.assertNotEqual(item.genre, u'differentGenre')

    def test_modified_album_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = u'differentAlbum'
        mf.save()
        self._update(move=True)
        item = self.lib.items().get()
        self.assertTrue(b'differentAlbum' in item.path)

    def test_modified_album_metadata_art_moved(self):
        artpath = self.album.artpath
        mf = MediaFile(syspath(self.i.path))
        mf.album = u'differentAlbum'
        mf.save()
        self._update(move=True)
        album = self.lib.albums()[0]
        self.assertNotEqual(artpath, album.artpath)
        self.assertIsNotNone(album.artpath)

    def test_selective_modified_album_metadata_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = u'differentAlbum'
        mf.genre = u'differentGenre'
        mf.save()
        self._update(move=True, fields=['album'])
        item = self.lib.items().get()
        self.assertTrue(b'differentAlbum' in item.path)
        self.assertNotEqual(item.genre, u'differentGenre')

    def test_selective_modified_album_metadata_not_moved(self):
        mf = MediaFile(syspath(self.i.path))
        mf.album = u'differentAlbum'
        mf.genre = u'differentGenre'
        mf.save()
        self._update(move=True, fields=['genre'])
        item = self.lib.items().get()
        self.assertTrue(b'differentAlbum' not in item.path)
        self.assertEqual(item.genre, u'differentGenre')

    def test_mtime_match_skips_update(self):
        mf = MediaFile(syspath(self.i.path))
        mf.title = u'differentTitle'
        mf.save()

        # Make in-memory mtime match on-disk mtime.
        self.i.mtime = os.path.getmtime(syspath(self.i.path))
        self.i.store()

        self._update(reset_mtime=False)
        item = self.lib.items().get()
        self.assertEqual(item.title, u'full')


class PrintTest(_common.TestCase):
    def setUp(self):
        super(PrintTest, self).setUp()
        self.io.install()

    def test_print_without_locale(self):
        lang = os.environ.get('LANG')
        if lang:
            del os.environ['LANG']

        try:
            ui.print_(u'something')
        except TypeError:
            self.fail(u'TypeError during print')
        finally:
            if lang:
                os.environ['LANG'] = lang

    def test_print_with_invalid_locale(self):
        old_lang = os.environ.get('LANG')
        os.environ['LANG'] = ''
        old_ctype = os.environ.get('LC_CTYPE')
        os.environ['LC_CTYPE'] = 'UTF-8'

        try:
            ui.print_(u'something')
        except ValueError:
            self.fail(u'ValueError during print')
        finally:
            if old_lang:
                os.environ['LANG'] = old_lang
            else:
                del os.environ['LANG']
            if old_ctype:
                os.environ['LC_CTYPE'] = old_ctype
            else:
                del os.environ['LC_CTYPE']


class ImportTest(_common.TestCase):
    def test_quiet_timid_disallowed(self):
        config['import']['quiet'] = True
        config['import']['timid'] = True
        self.assertRaises(ui.UserError, commands.import_files, None, [],
                          None)


@_common.slow_test()
class ConfigTest(unittest.TestCase, TestHelper, _common.Assertions):
    def setUp(self):
        self.setup_beets()

        # Don't use the BEETSDIR from `helper`. Instead, we point the home
        # directory there. Some tests will set `BEETSDIR` themselves.
        del os.environ['BEETSDIR']
        self._old_home = os.environ.get('HOME')
        os.environ['HOME'] = util.py3_path(self.temp_dir)

        # Also set APPDATA, the Windows equivalent of setting $HOME.
        self._old_appdata = os.environ.get('APPDATA')
        os.environ['APPDATA'] = \
            util.py3_path(os.path.join(self.temp_dir, b'AppData', b'Roaming'))

        self._orig_cwd = os.getcwd()
        self.test_cmd = self._make_test_cmd()
        commands.default_commands.append(self.test_cmd)

        # Default user configuration
        if platform.system() == 'Windows':
            self.user_config_dir = os.path.join(
                self.temp_dir, b'AppData', b'Roaming', b'beets'
            )
        else:
            self.user_config_dir = os.path.join(
                self.temp_dir, b'.config', b'beets'
            )
        os.makedirs(syspath(self.user_config_dir))
        self.user_config_path = os.path.join(self.user_config_dir,
                                             b'config.yaml')

        # Custom BEETSDIR
        self.beetsdir = os.path.join(self.temp_dir, b'beetsdir')
        os.makedirs(syspath(self.beetsdir))

        self._reset_config()

    def tearDown(self):
        commands.default_commands.pop()
        os.chdir(syspath(self._orig_cwd))
        if self._old_home is not None:
            os.environ['HOME'] = self._old_home
        if self._old_appdata is None:
            del os.environ['APPDATA']
        else:
            os.environ['APPDATA'] = self._old_appdata
        self.teardown_beets()

    def _make_test_cmd(self):
        test_cmd = ui.Subcommand('test', help=u'test')

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
        return open(self.user_config_path, 'w')

    def test_paths_section_respected(self):
        with self.write_config_file() as config:
            config.write('paths: {x: y}')

        self.run_command('test', lib=None)
        key, template = self.test_cmd.lib.path_formats[0]
        self.assertEqual(key, 'x')
        self.assertEqual(template.original, 'y')

    def test_default_paths_preserved(self):
        default_formats = ui.get_path_formats()

        self._reset_config()
        with self.write_config_file() as config:
            config.write('paths: {x: y}')
        self.run_command('test', lib=None)
        key, template = self.test_cmd.lib.path_formats[0]
        self.assertEqual(key, 'x')
        self.assertEqual(template.original, 'y')
        self.assertEqual(self.test_cmd.lib.path_formats[1:],
                         default_formats)

    def test_nonexistant_db(self):
        with self.write_config_file() as config:
            config.write('library: /xxx/yyy/not/a/real/path')

        with self.assertRaises(ui.UserError):
            self.run_command('test', lib=None)

    def test_user_config_file(self):
        with self.write_config_file() as file:
            file.write('anoption: value')

        self.run_command('test', lib=None)
        self.assertEqual(config['anoption'].get(), 'value')

    def test_replacements_parsed(self):
        with self.write_config_file() as config:
            config.write("replace: {'[xy]': z}")

        self.run_command('test', lib=None)
        replacements = self.test_cmd.lib.replacements
        repls = [(p.pattern, s) for p, s in replacements]  # Compare patterns.
        self.assertEqual(repls, [(u'[xy]', 'z')])

    def test_multiple_replacements_parsed(self):
        with self.write_config_file() as config:
            config.write("replace: {'[xy]': z, foo: bar}")
        self.run_command('test', lib=None)
        replacements = self.test_cmd.lib.replacements
        repls = [(p.pattern, s) for p, s in replacements]
        self.assertEqual(repls, [
            (u'[xy]', u'z'),
            (u'foo', u'bar'),
        ])

    def test_cli_config_option(self):
        config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(config_path, 'w') as file:
            file.write('anoption: value')
        self.run_command('--config', config_path, 'test', lib=None)
        self.assertEqual(config['anoption'].get(), 'value')

    def test_cli_config_file_overwrites_user_defaults(self):
        with open(self.user_config_path, 'w') as file:
            file.write('anoption: value')

        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(cli_config_path, 'w') as file:
            file.write('anoption: cli overwrite')
        self.run_command('--config', cli_config_path, 'test', lib=None)
        self.assertEqual(config['anoption'].get(), 'cli overwrite')

    def test_cli_config_file_overwrites_beetsdir_defaults(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)
        env_config_path = os.path.join(self.beetsdir, b'config.yaml')
        with open(env_config_path, 'w') as file:
            file.write('anoption: value')

        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(cli_config_path, 'w') as file:
            file.write('anoption: cli overwrite')
        self.run_command('--config', cli_config_path, 'test', lib=None)
        self.assertEqual(config['anoption'].get(), 'cli overwrite')

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
#        self.assertEqual(config['first'].get(), 'value')
#        self.assertEqual(config['second'].get(), 'value')
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
#        self.assertEqual(config['anoption'].get(), 'cli overwrite')

    def test_cli_config_paths_resolve_relative_to_user_dir(self):
        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(cli_config_path, 'w') as file:
            file.write('library: beets.db\n')
            file.write('statefile: state')

        self.run_command('--config', cli_config_path, 'test', lib=None)
        self.assert_equal_path(
            util.bytestring_path(config['library'].as_filename()),
            os.path.join(self.user_config_dir, b'beets.db')
        )
        self.assert_equal_path(
            util.bytestring_path(config['statefile'].as_filename()),
            os.path.join(self.user_config_dir, b'state')
        )

    def test_cli_config_paths_resolve_relative_to_beetsdir(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)

        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(cli_config_path, 'w') as file:
            file.write('library: beets.db\n')
            file.write('statefile: state')

        self.run_command('--config', cli_config_path, 'test', lib=None)
        self.assert_equal_path(
            util.bytestring_path(config['library'].as_filename()),
            os.path.join(self.beetsdir, b'beets.db')
        )
        self.assert_equal_path(
            util.bytestring_path(config['statefile'].as_filename()),
            os.path.join(self.beetsdir, b'state')
        )

    def test_command_line_option_relative_to_working_dir(self):
        config.read()
        os.chdir(syspath(self.temp_dir))
        self.run_command('--library', 'foo.db', 'test', lib=None)
        self.assert_equal_path(config['library'].as_filename(),
                               os.path.join(os.getcwd(), 'foo.db'))

    def test_cli_config_file_loads_plugin_commands(self):
        cli_config_path = os.path.join(self.temp_dir, b'config.yaml')
        with open(cli_config_path, 'w') as file:
            file.write('pluginpath: %s\n' % _common.PLUGINPATH)
            file.write('plugins: test')

        self.run_command('--config', cli_config_path, 'plugin', lib=None)
        self.assertTrue(plugins.find_plugins()[0].is_test_plugin)

    def test_beetsdir_config(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)

        env_config_path = os.path.join(self.beetsdir, b'config.yaml')
        with open(env_config_path, 'w') as file:
            file.write('anoption: overwrite')

        config.read()
        self.assertEqual(config['anoption'].get(), 'overwrite')

    def test_beetsdir_points_to_file_error(self):
        beetsdir = os.path.join(self.temp_dir, b'beetsfile')
        open(beetsdir, 'a').close()
        os.environ['BEETSDIR'] = util.py3_path(beetsdir)
        self.assertRaises(ConfigError, self.run_command, 'test')

    def test_beetsdir_config_does_not_load_default_user_config(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)

        with open(self.user_config_path, 'w') as file:
            file.write('anoption: value')

        config.read()
        self.assertFalse(config['anoption'].exists())

    def test_default_config_paths_resolve_relative_to_beetsdir(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)

        config.read()
        self.assert_equal_path(
            util.bytestring_path(config['library'].as_filename()),
            os.path.join(self.beetsdir, b'library.db')
        )
        self.assert_equal_path(
            util.bytestring_path(config['statefile'].as_filename()),
            os.path.join(self.beetsdir, b'state.pickle')
        )

    def test_beetsdir_config_paths_resolve_relative_to_beetsdir(self):
        os.environ['BEETSDIR'] = util.py3_path(self.beetsdir)

        env_config_path = os.path.join(self.beetsdir, b'config.yaml')
        with open(env_config_path, 'w') as file:
            file.write('library: beets.db\n')
            file.write('statefile: state')

        config.read()
        self.assert_equal_path(
            util.bytestring_path(config['library'].as_filename()),
            os.path.join(self.beetsdir, b'beets.db')
        )
        self.assert_equal_path(
            util.bytestring_path(config['statefile'].as_filename()),
            os.path.join(self.beetsdir, b'state')
        )


class ShowModelChangeTest(_common.TestCase):
    def setUp(self):
        super(ShowModelChangeTest, self).setUp()
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
        self.assertFalse(change)
        self.assertEqual(out, '')

    def test_string_fixed_field_change(self):
        self.b.title = 'x'
        change, out = self._show()
        self.assertTrue(change)
        self.assertTrue(u'title' in out)

    def test_int_fixed_field_change(self):
        self.b.track = 9
        change, out = self._show()
        self.assertTrue(change)
        self.assertTrue(u'track' in out)

    def test_floats_close_to_identical(self):
        self.a.length = 1.00001
        self.b.length = 1.00005
        change, out = self._show()
        self.assertFalse(change)
        self.assertEqual(out, u'')

    def test_floats_different(self):
        self.a.length = 1.00001
        self.b.length = 2.00001
        change, out = self._show()
        self.assertTrue(change)
        self.assertTrue(u'length' in out)

    def test_both_values_shown(self):
        self.a.title = u'foo'
        self.b.title = u'bar'
        change, out = self._show()
        self.assertTrue(u'foo' in out)
        self.assertTrue(u'bar' in out)


class ShowChangeTest(_common.TestCase):
    def setUp(self):
        super(ShowChangeTest, self).setUp()
        self.io.install()

        self.items = [_common.item()]
        self.items[0].track = 1
        self.items[0].path = b'/path/to/file.mp3'
        self.info = autotag.AlbumInfo(
            album=u'the album', album_id=u'album id', artist=u'the artist',
            artist_id=u'artist id', tracks=[
                autotag.TrackInfo(title=u'the title', track_id=u'track id',
                                  index=1)
            ]
        )

    def _show_change(self, items=None, info=None,
                     cur_artist=u'the artist', cur_album=u'the album',
                     dist=0.1):
        """Return an unicode string representing the changes"""
        items = items or self.items
        info = info or self.info
        mapping = dict(zip(items, info.tracks))
        config['ui']['color'] = False
        album_dist = distance(items, info, mapping)
        album_dist._penalties = {'album': [dist]}
        commands.show_change(
            cur_artist,
            cur_album,
            autotag.AlbumMatch(album_dist, info, mapping, set(), set()),
        )
        # FIXME decoding shouldn't be done here
        return util.text_string(self.io.getoutput().lower())

    def test_null_change(self):
        msg = self._show_change()
        self.assertTrue('similarity: 90' in msg)
        self.assertTrue('tagging:' in msg)

    def test_album_data_change(self):
        msg = self._show_change(cur_artist='another artist',
                                cur_album='another album')
        self.assertTrue('correcting tags from:' in msg)

    def test_item_data_change(self):
        self.items[0].title = u'different'
        msg = self._show_change()
        self.assertTrue('different -> the title' in msg)

    def test_item_data_change_with_unicode(self):
        self.items[0].title = u'caf\xe9'
        msg = self._show_change()
        self.assertTrue(u'caf\xe9 -> the title' in msg)

    def test_album_data_change_with_unicode(self):
        msg = self._show_change(cur_artist=u'caf\xe9',
                                cur_album=u'another album')
        self.assertTrue(u'correcting tags from:' in msg)

    def test_item_data_change_title_missing(self):
        self.items[0].title = u''
        msg = re.sub(r'  +', ' ', self._show_change())
        self.assertTrue(u'file.mp3 -> the title' in msg)

    def test_item_data_change_title_missing_with_unicode_filename(self):
        self.items[0].title = u''
        self.items[0].path = u'/path/to/caf\xe9.mp3'.encode('utf-8')
        msg = re.sub(r'  +', ' ', self._show_change())
        self.assertTrue(u'caf\xe9.mp3 -> the title' in msg or
                        u'caf.mp3 ->' in msg)


@patch('beets.library.Item.try_filesize', Mock(return_value=987))
class SummarizeItemsTest(_common.TestCase):
    def setUp(self):
        super(SummarizeItemsTest, self).setUp()
        item = library.Item()
        item.bitrate = 4321
        item.length = 10 * 60 + 54
        item.format = "F"
        self.item = item

    def test_summarize_item(self):
        summary = commands.summarize_items([], True)
        self.assertEqual(summary, u"")

        summary = commands.summarize_items([self.item], True)
        self.assertEqual(summary, u"F, 4kbps, 10:54, 987.0 B")

    def test_summarize_items(self):
        summary = commands.summarize_items([], False)
        self.assertEqual(summary, u"0 items")

        summary = commands.summarize_items([self.item], False)
        self.assertEqual(summary, u"1 items, F, 4kbps, 10:54, 987.0 B")

        # make a copy of self.item
        i2 = self.item.copy()

        summary = commands.summarize_items([self.item, i2], False)
        self.assertEqual(summary, u"2 items, F, 4kbps, 21:48, 1.9 KiB")

        i2.format = "G"
        summary = commands.summarize_items([self.item, i2], False)
        self.assertEqual(summary, u"2 items, F 1, G 1, 4kbps, 21:48, 1.9 KiB")

        summary = commands.summarize_items([self.item, i2, i2], False)
        self.assertEqual(summary, u"3 items, G 2, F 1, 4kbps, 32:42, 2.9 KiB")


class PathFormatTest(_common.TestCase):
    def test_custom_paths_prepend(self):
        default_formats = ui.get_path_formats()

        config['paths'] = {u'foo': u'bar'}
        pf = ui.get_path_formats()
        key, tmpl = pf[0]
        self.assertEqual(key, u'foo')
        self.assertEqual(tmpl.original, u'bar')
        self.assertEqual(pf[1:], default_formats)


@_common.slow_test()
class PluginTest(_common.TestCase, TestHelper):
    def test_plugin_command_from_pluginpath(self):
        config['pluginpath'] = [_common.PLUGINPATH]
        config['plugins'] = ['test']
        self.run_command('test', lib=None)


@_common.slow_test()
class CompletionTest(_common.TestCase, TestHelper):
    def test_completion(self):
        # Load plugin commands
        config['pluginpath'] = [_common.PLUGINPATH]
        config['plugins'] = ['test']

        # Do not load any other bash completion scripts on the system.
        env = dict(os.environ)
        env['BASH_COMPLETION_DIR'] = os.devnull
        env['BASH_COMPLETION_COMPAT_DIR'] = os.devnull

        # Open a `bash` process to run the tests in. We'll pipe in bash
        # commands via stdin.
        cmd = os.environ.get('BEETS_TEST_SHELL', '/bin/bash --norc').split()
        if not has_program(cmd[0]):
            self.skipTest(u'bash not available')
        tester = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, env=env)

        # Load bash_completion library.
        for path in commands.BASH_COMPLETION_PATHS:
            if os.path.exists(syspath(path)):
                bash_completion = path
                break
        else:
            self.skipTest(u'bash-completion script not found')
        try:
            with open(util.syspath(bash_completion), 'rb') as f:
                tester.stdin.writelines(f)
        except IOError:
            self.skipTest(u'could not read bash-completion script')

        # Load completion script.
        self.io.install()
        self.run_command('completion', lib=None)
        completion_script = self.io.getoutput().encode('utf-8')
        self.io.restore()
        tester.stdin.writelines(completion_script.splitlines(True))

        # Load test suite.
        test_script_name = os.path.join(_common.RSRC, b'test_completion.sh')
        with open(test_script_name, 'rb') as test_script_file:
            tester.stdin.writelines(test_script_file)
        out, err = tester.communicate()
        if tester.returncode != 0 or out != b'completion tests passed\n':
            print(out.decode('utf-8'))
            self.fail(u'test/test_completion.sh did not execute properly')


class CommonOptionsParserCliTest(unittest.TestCase, TestHelper):
    """Test CommonOptionsParser and formatting LibModel formatting on 'list'
    command.
    """
    def setUp(self):
        self.setup_beets()
        self.item = _common.item()
        self.item.path = b'xxx/yyy'
        self.lib.add(self.item)
        self.lib.add_album([self.item])
        self.load_plugins()

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_base(self):
        l = self.run_with_output(u'ls')
        self.assertEqual(l, u'the artist - the album - the title\n')

        l = self.run_with_output(u'ls', u'-a')
        self.assertEqual(l, u'the album artist - the album\n')

    def test_path_option(self):
        l = self.run_with_output(u'ls', u'-p')
        self.assertEqual(l, u'xxx/yyy\n')

        l = self.run_with_output(u'ls', u'-a', u'-p')
        self.assertEqual(l, u'xxx\n')

    def test_format_option(self):
        l = self.run_with_output(u'ls', u'-f', u'$artist')
        self.assertEqual(l, u'the artist\n')

        l = self.run_with_output(u'ls', u'-a', u'-f', u'$albumartist')
        self.assertEqual(l, u'the album artist\n')

    def test_format_option_unicode(self):
        l = self.run_with_output(b'ls', b'-f',
                                 u'caf\xe9'.encode(util.arg_encoding()))
        self.assertEqual(l, u'caf\xe9\n')

    def test_root_format_option(self):
        l = self.run_with_output(u'--format-item', u'$artist',
                                 u'--format-album', u'foo', u'ls')
        self.assertEqual(l, u'the artist\n')

        l = self.run_with_output(u'--format-item', u'foo',
                                 u'--format-album', u'$albumartist',
                                 u'ls', u'-a')
        self.assertEqual(l, u'the album artist\n')

    def test_help(self):
        l = self.run_with_output(u'help')
        self.assertIn(u'Usage:', l)

        l = self.run_with_output(u'help', u'list')
        self.assertIn(u'Usage:', l)

        with self.assertRaises(ui.UserError):
            self.run_command(u'help', u'this.is.not.a.real.command')

    def test_stats(self):
        l = self.run_with_output(u'stats')
        self.assertIn(u'Approximate total size:', l)

        # # Need to have more realistic library setup for this to work
        # l = self.run_with_output('stats', '-e')
        # self.assertIn('Total size:', l)

    def test_version(self):
        l = self.run_with_output(u'version')
        self.assertIn(u'Python version', l)
        self.assertIn(u'no plugins loaded', l)

        # # Need to have plugin loaded
        # l = self.run_with_output('version')
        # self.assertIn('plugins: ', l)


class CommonOptionsParserTest(unittest.TestCase, TestHelper):
    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    def test_album_option(self):
        parser = ui.CommonOptionsParser()
        self.assertFalse(parser._album_flags)
        parser.add_album_option()
        self.assertTrue(bool(parser._album_flags))

        self.assertEqual(parser.parse_args([]), ({'album': None}, []))
        self.assertEqual(parser.parse_args([u'-a']), ({'album': True}, []))
        self.assertEqual(parser.parse_args([u'--album']),
                         ({'album': True}, []))

    def test_path_option(self):
        parser = ui.CommonOptionsParser()
        parser.add_path_option()
        self.assertFalse(parser._album_flags)

        config['format_item'].set('$foo')
        self.assertEqual(parser.parse_args([]), ({'path': None}, []))
        self.assertEqual(config['format_item'].as_str(), u'$foo')

        self.assertEqual(parser.parse_args([u'-p']),
                         ({'path': True, 'format': u'$path'}, []))
        self.assertEqual(parser.parse_args(['--path']),
                         ({'path': True, 'format': u'$path'}, []))

        self.assertEqual(config['format_item'].as_str(), u'$path')
        self.assertEqual(config['format_album'].as_str(), u'$path')

    def test_format_option(self):
        parser = ui.CommonOptionsParser()
        parser.add_format_option()
        self.assertFalse(parser._album_flags)

        config['format_item'].set('$foo')
        self.assertEqual(parser.parse_args([]), ({'format': None}, []))
        self.assertEqual(config['format_item'].as_str(), u'$foo')

        self.assertEqual(parser.parse_args([u'-f', u'$bar']),
                         ({'format': u'$bar'}, []))
        self.assertEqual(parser.parse_args([u'--format', u'$baz']),
                         ({'format': u'$baz'}, []))

        self.assertEqual(config['format_item'].as_str(), u'$baz')
        self.assertEqual(config['format_album'].as_str(), u'$baz')

    def test_format_option_with_target(self):
        with self.assertRaises(KeyError):
            ui.CommonOptionsParser().add_format_option(target='thingy')

        parser = ui.CommonOptionsParser()
        parser.add_format_option(target='item')

        config['format_item'].set('$item')
        config['format_album'].set('$album')

        self.assertEqual(parser.parse_args([u'-f', u'$bar']),
                         ({'format': u'$bar'}, []))

        self.assertEqual(config['format_item'].as_str(), u'$bar')
        self.assertEqual(config['format_album'].as_str(), u'$album')

    def test_format_option_with_album(self):
        parser = ui.CommonOptionsParser()
        parser.add_album_option()
        parser.add_format_option()

        config['format_item'].set('$item')
        config['format_album'].set('$album')

        parser.parse_args([u'-f', u'$bar'])
        self.assertEqual(config['format_item'].as_str(), u'$bar')
        self.assertEqual(config['format_album'].as_str(), u'$album')

        parser.parse_args([u'-a', u'-f', u'$foo'])
        self.assertEqual(config['format_item'].as_str(), u'$bar')
        self.assertEqual(config['format_album'].as_str(), u'$foo')

        parser.parse_args([u'-f', u'$foo2', u'-a'])
        self.assertEqual(config['format_album'].as_str(), u'$foo2')

    def test_add_all_common_options(self):
        parser = ui.CommonOptionsParser()
        parser.add_all_common_options()
        self.assertEqual(parser.parse_args([]),
                         ({'album': None, 'path': None, 'format': None}, []))


class EncodingTest(_common.TestCase):
    """Tests for the `terminal_encoding` config option and our
    `_in_encoding` and `_out_encoding` utility functions.
    """

    def out_encoding_overridden(self):
        config['terminal_encoding'] = 'fake_encoding'
        self.assertEqual(ui._out_encoding(), 'fake_encoding')

    def in_encoding_overridden(self):
        config['terminal_encoding'] = 'fake_encoding'
        self.assertEqual(ui._in_encoding(), 'fake_encoding')

    def out_encoding_default_utf8(self):
        with patch('sys.stdout') as stdout:
            stdout.encoding = None
            self.assertEqual(ui._out_encoding(), 'utf-8')

    def in_encoding_default_utf8(self):
        with patch('sys.stdin') as stdin:
            stdin.encoding = None
            self.assertEqual(ui._in_encoding(), 'utf-8')


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
