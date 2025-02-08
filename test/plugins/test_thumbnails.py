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


import os.path
from shutil import rmtree
from tempfile import mkdtemp
from unittest.mock import Mock, call, patch

import pytest

from beets.test.helper import BeetsTestCase
from beets.util import bytestring_path, syspath
from beetsplug.thumbnails import (
    LARGE_DIR,
    NORMAL_DIR,
    GioURI,
    PathlibURI,
    ThumbnailsPlugin,
)


class ThumbnailsTest(BeetsTestCase):
    @patch("beetsplug.thumbnails.ArtResizer")
    @patch("beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok", Mock())
    @patch("beetsplug.thumbnails.os.stat")
    def test_add_tags(self, mock_stat, mock_artresizer):
        plugin = ThumbnailsPlugin()
        plugin.get_uri = Mock(
            side_effect={b"/path/to/cover": "COVER_URI"}.__getitem__
        )
        album = Mock(artpath=b"/path/to/cover")
        mock_stat.return_value.st_mtime = 12345

        plugin.add_tags(album, b"/path/to/thumbnail")

        metadata = {"Thumb::URI": "COVER_URI", "Thumb::MTime": "12345"}
        mock_artresizer.shared.write_metadata.assert_called_once_with(
            b"/path/to/thumbnail",
            metadata,
        )
        mock_stat.assert_called_once_with(syspath(album.artpath))

    @patch("beetsplug.thumbnails.os")
    @patch("beetsplug.thumbnails.ArtResizer")
    @patch("beetsplug.thumbnails.GioURI")
    def test_check_local_ok(self, mock_giouri, mock_artresizer, mock_os):
        # test local resizing capability
        mock_artresizer.shared.local = False
        mock_artresizer.shared.can_write_metadata = False
        plugin = ThumbnailsPlugin()
        assert not plugin._check_local_ok()

        # test dirs creation
        mock_artresizer.shared.local = True
        mock_artresizer.shared.can_write_metadata = True

        def exists(path):
            if path == syspath(NORMAL_DIR):
                return False
            if path == syspath(LARGE_DIR):
                return True
            raise ValueError(f"unexpected path {path!r}")

        mock_os.path.exists = exists
        plugin = ThumbnailsPlugin()
        mock_os.makedirs.assert_called_once_with(syspath(NORMAL_DIR))
        assert plugin._check_local_ok()

        # test metadata writer function
        mock_os.path.exists = lambda _: True

        mock_artresizer.shared.local = True
        mock_artresizer.shared.can_write_metadata = False
        with pytest.raises(RuntimeError):
            ThumbnailsPlugin()

        mock_artresizer.shared.local = True
        mock_artresizer.shared.can_write_metadata = True
        assert ThumbnailsPlugin()._check_local_ok()

        # test URI getter function
        giouri_inst = mock_giouri.return_value
        giouri_inst.available = True
        assert ThumbnailsPlugin().get_uri == giouri_inst.uri

        giouri_inst.available = False
        assert ThumbnailsPlugin().get_uri.__self__.__class__ == PathlibURI

    @patch("beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok", Mock())
    @patch("beetsplug.thumbnails.ArtResizer")
    @patch("beetsplug.thumbnails.util")
    @patch("beetsplug.thumbnails.os")
    @patch("beetsplug.thumbnails.shutil")
    def test_make_cover_thumbnail(
        self, mock_shutils, mock_os, mock_util, mock_artresizer
    ):
        thumbnail_dir = os.path.normpath(b"/thumbnail/dir")
        md5_file = os.path.join(thumbnail_dir, b"md5")
        path_to_art = os.path.normpath(b"/path/to/art")
        path_to_resized_art = os.path.normpath(b"/path/to/resized/artwork")

        mock_os.path.join = os.path.join  # don't mock that function
        plugin = ThumbnailsPlugin()
        plugin.add_tags = Mock()

        album = Mock(artpath=path_to_art)
        mock_util.syspath.side_effect = lambda x: x
        plugin.thumbnail_file_name = Mock(return_value=b"md5")
        mock_os.path.exists.return_value = False

        def os_stat(target):
            if target == syspath(md5_file):
                return Mock(st_mtime=1)
            elif target == syspath(path_to_art):
                return Mock(st_mtime=2)
            else:
                raise ValueError(f"invalid target {target}")

        mock_os.stat.side_effect = os_stat

        mock_resize = mock_artresizer.shared.resize
        mock_resize.return_value = path_to_resized_art

        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)

        mock_os.path.exists.assert_called_once_with(syspath(md5_file))

        mock_resize.assert_called_once_with(12345, path_to_art, md5_file)
        plugin.add_tags.assert_called_once_with(album, path_to_resized_art)
        mock_shutils.move.assert_called_once_with(
            syspath(path_to_resized_art), syspath(md5_file)
        )

        # now test with recent thumbnail & with force
        mock_os.path.exists.return_value = True
        plugin.force = False
        mock_resize.reset_mock()

        def os_stat(target):
            if target == syspath(md5_file):
                return Mock(st_mtime=3)
            elif target == syspath(path_to_art):
                return Mock(st_mtime=2)
            else:
                raise ValueError(f"invalid target {target}")

        mock_os.stat.side_effect = os_stat

        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)
        assert mock_resize.call_count == 0

        # and with force
        plugin.config["force"] = True
        plugin.make_cover_thumbnail(album, 12345, thumbnail_dir)
        mock_resize.assert_called_once_with(12345, path_to_art, md5_file)

    @patch("beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok", Mock())
    def test_make_dolphin_cover_thumbnail(self):
        plugin = ThumbnailsPlugin()
        tmp = bytestring_path(mkdtemp())
        album = Mock(path=tmp, artpath=os.path.join(tmp, b"cover.jpg"))
        plugin.make_dolphin_cover_thumbnail(album)
        with open(os.path.join(tmp, b".directory"), "rb") as f:
            assert f.read().splitlines() == [
                b"[Desktop Entry]",
                b"Icon=./cover.jpg",
            ]

        # not rewritten when it already exists (yup that's a big limitation)
        album.artpath = b"/my/awesome/art.tiff"
        plugin.make_dolphin_cover_thumbnail(album)
        with open(os.path.join(tmp, b".directory"), "rb") as f:
            assert f.read().splitlines() == [
                b"[Desktop Entry]",
                b"Icon=./cover.jpg",
            ]

        rmtree(syspath(tmp))

    @patch("beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok", Mock())
    @patch("beetsplug.thumbnails.ArtResizer")
    def test_process_album(self, mock_artresizer):
        get_size = mock_artresizer.shared.get_size

        plugin = ThumbnailsPlugin()
        make_cover = plugin.make_cover_thumbnail = Mock(return_value=True)
        make_dolphin = plugin.make_dolphin_cover_thumbnail = Mock()

        # no art
        album = Mock(artpath=None)
        plugin.process_album(album)
        assert get_size.call_count == 0
        assert make_dolphin.call_count == 0

        # cannot get art size
        album.artpath = b"/path/to/art"
        get_size.return_value = None
        plugin.process_album(album)
        get_size.assert_called_once_with(b"/path/to/art")
        assert make_cover.call_count == 0

        # dolphin tests
        plugin.config["dolphin"] = False
        plugin.process_album(album)
        assert make_dolphin.call_count == 0

        plugin.config["dolphin"] = True
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
        make_cover.assert_has_calls(
            [call(album, 128, NORMAL_DIR), call(album, 256, LARGE_DIR)],
            any_order=True,
        )

    @patch("beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok", Mock())
    @patch("beetsplug.thumbnails.decargs")
    def test_invokations(self, mock_decargs):
        plugin = ThumbnailsPlugin()
        plugin.process_album = Mock()
        album = Mock()

        plugin.process_album.reset_mock()
        lib = Mock()
        album2 = Mock()
        lib.albums.return_value = [album, album2]
        plugin.process_query(lib, Mock(), None)
        lib.albums.assert_called_once_with(mock_decargs.return_value)
        plugin.process_album.assert_has_calls(
            [call(album), call(album2)], any_order=True
        )

    @patch("beetsplug.thumbnails.BaseDirectory")
    def test_thumbnail_file_name(self, mock_basedir):
        plug = ThumbnailsPlugin()
        plug.get_uri = Mock(return_value="file:///my/uri")
        assert (
            plug.thumbnail_file_name(b"idontcare")
            == b"9488f5797fbe12ffb316d607dfd93d04.png"
        )

    def test_uri(self):
        gio = GioURI()
        if not gio.available:
            self.skipTest("GIO library not found")

        assert gio.uri("/foo") == "file:///"  # silent fail
        assert gio.uri(b"/foo") == "file:///foo"
        assert gio.uri(b"/foo!") == "file:///foo!"
        assert (
            gio.uri(b"/music/\xec\x8b\xb8\xec\x9d\xb4")
            == "file:///music/%EC%8B%B8%EC%9D%B4"
        )


class TestPathlibURI:
    """Test PathlibURI class"""

    def test_uri(self):
        test_uri = PathlibURI()

        # test it won't break if we pass it bytes for a path
        test_uri.uri(b"/")
