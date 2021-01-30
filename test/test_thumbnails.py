# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Bruno Cauet
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

from __future__ import division, absolute_import, print_function

import os.path
from mock import Mock, patch, call
from tempfile import mkdtemp
from shutil import rmtree
import unittest

from test.helper import TestHelper

from beets.util import bytestring_path, syspath
from beetsplug.thumbnails import (ThumbnailsPlugin, NORMAL_DIR, LARGE_DIR,
                                  write_metadata_im, write_metadata_pil,
                                  PathlibURI, GioURI)


class ThumbnailsTest(unittest.TestCase, TestHelper):
    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    @patch('beetsplug.thumbnails.util')
    def test_write_metadata_im(self, mock_util):
        metadata = {"a": u"A", "b": u"B"}
        write_metadata_im("foo", metadata)
        try:
            command = u"convert foo -set a A -set b B foo".split(' ')
            mock_util.command_output.assert_called_once_with(command)
        except AssertionError:
            command = u"convert foo -set b B -set a A foo".split(' ')
            mock_util.command_output.assert_called_once_with(command)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.os.stat')
    def test_add_tags(self, mock_stat, _):
        plugin = ThumbnailsPlugin()
        plugin.write_metadata = Mock()
        plugin.get_uri = Mock(side_effect={b"/path/to/cover":
                                           "COVER_URI"}.__getitem__)
        album = Mock(artpath=b"/path/to/cover")
        mock_stat.return_value.st_mtime = 12345

        plugin.add_tags(album, b"/path/to/thumbnail")

        metadata = {"Thumb::URI": "COVER_URI",
                    "Thumb::MTime": u"12345"}
        plugin.write_metadata.assert_called_once_with(b"/path/to/thumbnail",
                                                      metadata)
        mock_stat.assert_called_once_with(syspath(album.artpath))

    @patch('beetsplug.thumbnails.os')
    @patch('beetsplug.thumbnails.ArtResizer')
    @patch('beetsplug.thumbnails.get_im_version')
    @patch('beetsplug.thumbnails.get_pil_version')
    @patch('beetsplug.thumbnails.GioURI')
    def test_check_local_ok(self, mock_giouri, mock_pil, mock_im,
                            mock_artresizer, mock_os):
        # test local resizing capability
        mock_artresizer.shared.local = False
        plugin = ThumbnailsPlugin()
        self.assertFalse(plugin._check_local_ok())

        # test dirs creation
        mock_artresizer.shared.local = True

        def exists(path):
            if path == syspath(NORMAL_DIR):
                return False
            if path == syspath(LARGE_DIR):
                return True
            raise ValueError(u"unexpected path {0!r}".format(path))
        mock_os.path.exists = exists
        plugin = ThumbnailsPlugin()
        mock_os.makedirs.assert_called_once_with(syspath(NORMAL_DIR))
        self.assertTrue(plugin._check_local_ok())

        # test metadata writer function
        mock_os.path.exists = lambda _: True
        mock_pil.return_value = False
        mock_im.return_value = False
        with self.assertRaises(AssertionError):
            ThumbnailsPlugin()

        mock_pil.return_value = True
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_pil)

        mock_im.return_value = True
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_im)

        mock_pil.return_value = False
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_im)

        self.assertTrue(ThumbnailsPlugin()._check_local_ok())

        # test URI getter function
        giouri_inst = mock_giouri.return_value
        giouri_inst.available = True
        self.assertEqual(ThumbnailsPlugin().get_uri, giouri_inst.uri)

        giouri_inst.available = False
        self.assertEqual(ThumbnailsPlugin().get_uri.__self__.__class__,
                         PathlibURI)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.ArtResizer')
    @patch('beetsplug.thumbnails.util')
    @patch('beetsplug.thumbnails.os')
    @patch('beetsplug.thumbnails.shutil')
    def test_make_cover_thumbnail(self, mock_shutils, mock_os, mock_util,
                                  mock_artresizer, _):
        thumbnail_dir = os.path.normpath(b"/thumbnail/dir")
        md5_file = os.path.join(thumbnail_dir, b"md5")
        path_to_art = os.path.normpath(b"/path/to/art")

        mock_os.path.join = os.path.join  # don't mock that function
        plugin = ThumbnailsPlugin()
        plugin.add_tags = Mock()

        album = Mock(artpath=path_to_art)
        mock_util.syspath.side_effect = lambda x: x
        plugin.thumbnail_file_name = Mock(return_value=b'md5')
        mock_os.path.exists.return_value = False
        md5_file = syspath(md5_file)

        def os_stat(target):
            if target == syspath(md5_file):
                return Mock(st_mtime=1)
            elif target == syspath(path_to_art):
                return Mock(st_mtime=2)
            else:
                raise ValueError(u"invalid target {0}".format(target))
        mock_os.stat.side_effect = os_stat

        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)

        mock_os.path.exists.assert_called_once_with(syspath(md5_file))
        mock_os.stat.has_calls([call(syspath(md5_file)),
                                call(syspath(path_to_art))],
                               any_order=True)

        resize = mock_artresizer.shared.resize
        resize.assert_called_once_with(12345, path_to_art, md5_file)
        plugin.add_tags.assert_called_once_with(album, resize.return_value)
        mock_shutils.move.assert_called_once_with(resize.return_value,
                                                  syspath(md5_file))

        # now test with recent thumbnail & with force
        mock_os.path.exists.return_value = True
        plugin.force = False
        resize.reset_mock()

        def os_stat(target):
            if target == syspath(md5_file):
                return Mock(st_mtime=3)
            elif target == syspath(path_to_art):
                return Mock(st_mtime=2)
            else:
                raise ValueError(u"invalid target {0}".format(target))
        mock_os.stat.side_effect = os_stat

        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)
        self.assertEqual(resize.call_count, 0)

        # and with force
        plugin.config['force'] = True
        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)
        resize.assert_called_once_with(12345, path_to_art, md5_file)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    def test_make_dolphin_cover_thumbnail(self, _):
        plugin = ThumbnailsPlugin()
        tmp = bytestring_path(mkdtemp())
        album = Mock(path=tmp,
                     artpath=os.path.join(tmp, b"cover.jpg"))
        plugin.make_dolphin_cover_thumbnail(album)
        with open(os.path.join(tmp, b".directory"), "rb") as f:
            self.assertEqual(
                f.read().splitlines(),
                [b"[Desktop Entry]", b"Icon=./cover.jpg"]
            )

        # not rewritten when it already exists (yup that's a big limitation)
        album.artpath = b"/my/awesome/art.tiff"
        plugin.make_dolphin_cover_thumbnail(album)
        with open(os.path.join(tmp, b".directory"), "rb") as f:
            self.assertEqual(
                f.read().splitlines(),
                [b"[Desktop Entry]", b"Icon=./cover.jpg"]
            )

        rmtree(syspath(tmp))

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.ArtResizer')
    def test_process_album(self, mock_artresizer, _):
        get_size = mock_artresizer.shared.get_size

        plugin = ThumbnailsPlugin()
        make_cover = plugin.make_cover_thumbnail = Mock(return_value=True)
        make_dolphin = plugin.make_dolphin_cover_thumbnail = Mock()

        # no art
        album = Mock(artpath=None)
        plugin.process_album(album)
        self.assertEqual(get_size.call_count, 0)
        self.assertEqual(make_dolphin.call_count, 0)

        # cannot get art size
        album.artpath = b"/path/to/art"
        get_size.return_value = None
        plugin.process_album(album)
        get_size.assert_called_once_with(b"/path/to/art")
        self.assertEqual(make_cover.call_count, 0)

        # dolphin tests
        plugin.config['dolphin'] = False
        plugin.process_album(album)
        self.assertEqual(make_dolphin.call_count, 0)

        plugin.config['dolphin'] = True
        plugin.process_album(album)
        make_dolphin.assert_called_once_with(album)

        # small art
        get_size.return_value = 200, 200
        plugin.process_album(album)
        make_cover.assert_called_once_with(album, 128, NORMAL_DIR)

        # big art
        make_cover.reset_mock()
        get_size.return_value = 500, 500
        plugin.process_album(album)
        make_cover.has_calls([call(album, 128, NORMAL_DIR),
                              call(album, 256, LARGE_DIR)], any_order=True)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.decargs')
    def test_invokations(self, mock_decargs, _):
        plugin = ThumbnailsPlugin()
        plugin.process_album = Mock()
        album = Mock()

        plugin.process_album.reset_mock()
        lib = Mock()
        album2 = Mock()
        lib.albums.return_value = [album, album2]
        plugin.process_query(lib, Mock(), None)
        lib.albums.assert_called_once_with(mock_decargs.return_value)
        plugin.process_album.has_calls([call(album), call(album2)],
                                       any_order=True)

    @patch('beetsplug.thumbnails.BaseDirectory')
    def test_thumbnail_file_name(self, mock_basedir):
        plug = ThumbnailsPlugin()
        plug.get_uri = Mock(return_value=u"file:///my/uri")
        self.assertEqual(plug.thumbnail_file_name(b'idontcare'),
                         b"9488f5797fbe12ffb316d607dfd93d04.png")

    def test_uri(self):
        gio = GioURI()
        if not gio.available:
            self.skipTest(u"GIO library not found")

        self.assertEqual(gio.uri(u"/foo"), u"file:///")  # silent fail
        self.assertEqual(gio.uri(b"/foo"), u"file:///foo")
        self.assertEqual(gio.uri(b"/foo!"), u"file:///foo!")
        self.assertEqual(
            gio.uri(b'/music/\xec\x8b\xb8\xec\x9d\xb4'),
            u'file:///music/%EC%8B%B8%EC%9D%B4')


class TestPathlibURI():
    """Test PathlibURI class"""
    def test_uri(self):
        test_uri = PathlibURI()

        # test it won't break if we pass it bytes for a path
        test_uri.uri(b'/')


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
