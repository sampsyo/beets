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

"""Some common functionality for beets' test cases."""

import os
import sys
import unittest
from contextlib import contextmanager

import beets
import beets.library

# Make sure the development versions of the plugins are used
import beetsplug
from beets import importer, logging, util
from beets.ui import commands
from beets.util import syspath

beetsplug.__path__ = [
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir,
            os.path.pardir,
            "beetsplug",
        )
    )
]

# Test resources path.
RSRC = util.bytestring_path(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir,
            os.path.pardir,
            "test",
            "rsrc",
        )
    )
)
PLUGINPATH = os.path.join(RSRC.decode(), "beetsplug")

# Propagate to root logger so the test runner can capture it
log = logging.getLogger("beets")
log.propagate = True
log.setLevel(logging.DEBUG)

# OS feature test.
HAVE_SYMLINK = sys.platform != "win32"
HAVE_HARDLINK = sys.platform != "win32"


def item(lib=None):
    i = beets.library.Item(
        title="the title",
        artist="the artist",
        albumartist="the album artist",
        album="the album",
        genre="the genre",
        lyricist="the lyricist",
        composer="the composer",
        arranger="the arranger",
        grouping="the grouping",
        work="the work title",
        mb_workid="the work musicbrainz id",
        work_disambig="the work disambiguation",
        year=1,
        month=2,
        day=3,
        track=4,
        tracktotal=5,
        disc=6,
        disctotal=7,
        lyrics="the lyrics",
        comments="the comments",
        bpm=8,
        comp=True,
        length=60.0,
        bitrate=128000,
        format="FLAC",
        mb_trackid="someID-1",
        mb_albumid="someID-2",
        mb_artistid="someID-3",
        mb_albumartistid="someID-4",
        mb_releasetrackid="someID-5",
        album_id=None,
        mtime=12345,
    )
    if lib:
        lib.add(i)
    return i


# Dummy import session.
def import_session(lib=None, loghandler=None, paths=[], query=[], cli=False):
    cls = commands.TerminalImportSession if cli else importer.ImportSession
    return cls(lib, loghandler, paths, query)


class Assertions:
    """A mixin with additional unit test assertions."""

    def assertExists(self, path):
        assert os.path.exists(syspath(path)), f"file does not exist: {path!r}"

    def assertNotExists(self, path):
        assert not os.path.exists(syspath(path)), f"file exists: {path!r}"

    def assertIsFile(self, path):
        self.assertExists(path)
        assert os.path.isfile(
            syspath(path)
        ), "path exists, but is not a regular file: {!r}".format(path)

    def assertIsDir(self, path):
        self.assertExists(path)
        assert os.path.isdir(
            syspath(path)
        ), "path exists, but is not a directory: {!r}".format(path)

    def assert_equal_path(self, a, b):
        """Check that two paths are equal."""
        a_bytes, b_bytes = util.normpath(a), util.normpath(b)

        assert a_bytes == b_bytes, f"{a_bytes=} != {b_bytes=}"


# Mock I/O.


class InputError(Exception):
    def __init__(self, output=None):
        self.output = output

    def __str__(self):
        msg = "Attempt to read with no input provided."
        if self.output is not None:
            msg += f" Output: {self.output!r}"
        return msg


class DummyOut:
    encoding = "utf-8"

    def __init__(self):
        self.buf = []

    def write(self, s):
        self.buf.append(s)

    def get(self):
        return "".join(self.buf)

    def flush(self):
        self.clear()

    def clear(self):
        self.buf = []


class DummyIn:
    encoding = "utf-8"

    def __init__(self, out=None):
        self.buf = []
        self.reads = 0
        self.out = out

    def add(self, s):
        self.buf.append(s + "\n")

    def close(self):
        pass

    def readline(self):
        if not self.buf:
            if self.out:
                raise InputError(self.out.get())
            else:
                raise InputError()
        self.reads += 1
        return self.buf.pop(0)


class DummyIO:
    """Mocks input and output streams for testing UI code."""

    def __init__(self):
        self.stdout = DummyOut()
        self.stdin = DummyIn(self.stdout)

    def addinput(self, s):
        self.stdin.add(s)

    def getoutput(self):
        res = self.stdout.get()
        self.stdout.clear()
        return res

    def readcount(self):
        return self.stdin.reads

    def install(self):
        sys.stdin = self.stdin
        sys.stdout = self.stdout

    def restore(self):
        sys.stdin = sys.__stdin__
        sys.stdout = sys.__stdout__


# Utility.


def touch(path):
    open(syspath(path), "a").close()


class Bag:
    """An object that exposes a set of fields given as keyword
    arguments. Any field not found in the dictionary appears to be None.
    Used for mocking Album objects and the like.
    """

    def __init__(self, **fields):
        self.fields = fields

    def __getattr__(self, key):
        return self.fields.get(key)


# Platform mocking.


@contextmanager
def platform_windows():
    import ntpath

    old_path = os.path
    try:
        os.path = ntpath
        yield
    finally:
        os.path = old_path


@contextmanager
def platform_posix():
    import posixpath

    old_path = os.path
    try:
        os.path = posixpath
        yield
    finally:
        os.path = old_path


@contextmanager
def system_mock(name):
    import platform

    old_system = platform.system
    platform.system = lambda: name
    try:
        yield
    finally:
        platform.system = old_system


def slow_test(unused=None):
    def _id(obj):
        return obj

    if "SKIP_SLOW_TESTS" in os.environ:
        return unittest.skip("test is slow")
    return _id
