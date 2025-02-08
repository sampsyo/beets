# This file is part of beets.
# Copyright 2022, J0J0 Todos.
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
"""Testsuite for the M3UFile class."""

import sys
import unittest
from os import path
from shutil import rmtree
from tempfile import mkdtemp

import pytest

from beets.test._common import RSRC
from beets.util import bytestring_path
from beets.util.m3u import EmptyPlaylistError, M3UFile


class M3UFileTest(unittest.TestCase):
    """Tests the M3UFile class."""

    def test_playlist_write_empty(self):
        """Test whether saving an empty playlist file raises an error."""
        tempdir = bytestring_path(mkdtemp())
        the_playlist_file = path.join(tempdir, b"playlist.m3u8")
        m3ufile = M3UFile(the_playlist_file)
        with pytest.raises(EmptyPlaylistError):
            m3ufile.write()
        rmtree(tempdir)

    def test_playlist_write(self):
        """Test saving ascii paths to a playlist file."""
        tempdir = bytestring_path(mkdtemp())
        the_playlist_file = path.join(tempdir, b"playlist.m3u")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.set_contents(
            [
                bytestring_path("/This/is/a/path/to_a_file.mp3"),
                bytestring_path("/This/is/another/path/to_a_file.mp3"),
            ]
        )
        m3ufile.write()
        assert path.exists(the_playlist_file)
        rmtree(tempdir)

    def test_playlist_write_unicode(self):
        """Test saving unicode paths to a playlist file."""
        tempdir = bytestring_path(mkdtemp())
        the_playlist_file = path.join(tempdir, b"playlist.m3u8")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.set_contents(
            [
                bytestring_path("/This/is/å/path/to_a_file.mp3"),
                bytestring_path("/This/is/another/path/tö_a_file.mp3"),
            ]
        )
        m3ufile.write()
        assert path.exists(the_playlist_file)
        rmtree(tempdir)

    @unittest.skipUnless(sys.platform == "win32", "win32")
    def test_playlist_write_and_read_unicode_windows(self):
        """Test saving unicode paths to a playlist file on Windows."""
        tempdir = bytestring_path(mkdtemp())
        the_playlist_file = path.join(
            tempdir, b"playlist_write_and_read_windows.m3u8"
        )
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.set_contents(
            [
                bytestring_path(r"x:\This\is\å\path\to_a_file.mp3"),
                bytestring_path(r"x:\This\is\another\path\tö_a_file.mp3"),
            ]
        )
        m3ufile.write()
        assert path.exists(the_playlist_file)
        m3ufile_read = M3UFile(the_playlist_file)
        m3ufile_read.load()
        assert m3ufile.media_list[0] == bytestring_path(
            path.join("x:\\", "This", "is", "å", "path", "to_a_file.mp3")
        )
        assert m3ufile.media_list[1] == bytestring_path(
            r"x:\This\is\another\path\tö_a_file.mp3"
        ), bytestring_path(
            path.join("x:\\", "This", "is", "another", "path", "tö_a_file.mp3")
        )
        rmtree(tempdir)

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_playlist_load_ascii(self):
        """Test loading ascii paths from a playlist file."""
        the_playlist_file = path.join(RSRC, b"playlist.m3u")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.load()
        assert m3ufile.media_list[0] == bytestring_path(
            "/This/is/a/path/to_a_file.mp3"
        )

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_playlist_load_unicode(self):
        """Test loading unicode paths from a playlist file."""
        the_playlist_file = path.join(RSRC, b"playlist.m3u8")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.load()
        assert m3ufile.media_list[0] == bytestring_path(
            "/This/is/å/path/to_a_file.mp3"
        )

    @unittest.skipUnless(sys.platform == "win32", "win32")
    def test_playlist_load_unicode_windows(self):
        """Test loading unicode paths from a playlist file."""
        the_playlist_file = path.join(RSRC, b"playlist_windows.m3u8")
        winpath = bytestring_path(
            path.join("x:\\", "This", "is", "å", "path", "to_a_file.mp3")
        )
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.load()
        assert m3ufile.media_list[0] == winpath

    def test_playlist_load_extm3u(self):
        """Test loading a playlist with an #EXTM3U header."""
        the_playlist_file = path.join(RSRC, b"playlist.m3u")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.load()
        assert m3ufile.extm3u

    def test_playlist_load_non_extm3u(self):
        """Test loading a playlist without an #EXTM3U header."""
        the_playlist_file = path.join(RSRC, b"playlist_non_ext.m3u")
        m3ufile = M3UFile(the_playlist_file)
        m3ufile.load()
        assert not m3ufile.extm3u
