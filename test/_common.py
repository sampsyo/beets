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

"""Some common functionality for beets' test cases."""
from __future__ import division, absolute_import, print_function

import time
import sys
import os
import tempfile
import shutil
import six
import unittest
from contextlib import contextmanager

import reflink


# Mangle the search path to include the beets sources.
sys.path.insert(0, '..')
import beets.library  # noqa: E402
from beets import importer, logging  # noqa: E402
from beets.ui import commands  # noqa: E402
from beets import util  # noqa: E402
from beets.util import bytestring_path, syspath  # noqa: E402
import beets  # noqa: E402

# Make sure the development versions of the plugins are used
import beetsplug  # noqa: E402
beetsplug.__path__ = [os.path.abspath(
    os.path.join(__file__, '..', '..', 'beetsplug')
)]

# Test resources path.
RSRC = util.bytestring_path(os.path.join(os.path.dirname(__file__), 'rsrc'))
PLUGINPATH = os.path.join(os.path.dirname(__file__), 'rsrc', 'beetsplug')

# Propagate to root logger so the test runner can capture it
log = logging.getLogger('beets')
log.propagate = True
log.setLevel(logging.DEBUG)

# Dummy item creation.
_item_ident = 0

# OS feature test.
HAVE_SYMLINK = sys.platform != 'win32'
HAVE_HARDLINK = sys.platform != 'win32'
HAVE_REFLINK = reflink.supported_at(tempfile.gettempdir())


def item(lib=None):
    global _item_ident
    _item_ident += 1
    i = beets.library.Item(
        title=u'the title',
        artist=u'the artist',
        albumartist=u'the album artist',
        album=u'the album',
        genre=u'the genre',
        lyricist=u'the lyricist',
        composer=u'the composer',
        arranger=u'the arranger',
        grouping=u'the grouping',
        work=u'the work title',
        mb_workid=u'the work musicbrainz id',
        work_disambig=u'the work disambiguation',
        year=1,
        month=2,
        day=3,
        track=4,
        tracktotal=5,
        disc=6,
        disctotal=7,
        lyrics=u'the lyrics',
        comments=u'the comments',
        bpm=8,
        comp=True,
        path='somepath{0}'.format(_item_ident),
        length=60.0,
        bitrate=128000,
        format='FLAC',
        mb_trackid='someID-1',
        mb_albumid='someID-2',
        mb_artistid='someID-3',
        mb_albumartistid='someID-4',
        mb_releasetrackid='someID-5',
        album_id=None,
        mtime=12345,
    )
    if lib:
        lib.add(i)
    return i

_album_ident = 0


def album(lib=None):
    global _item_ident
    _item_ident += 1
    i = beets.library.Album(
        artpath=None,
        albumartist=u'some album artist',
        albumartist_sort=u'some sort album artist',
        albumartist_credit=u'some album artist credit',
        album=u'the album',
        genre=u'the genre',
        year=2014,
        month=2,
        day=5,
        tracktotal=0,
        disctotal=1,
        comp=False,
        mb_albumid='someID-1',
        mb_albumartistid='someID-1'
    )
    if lib:
        lib.add(i)
    return i


# Dummy import session.
def import_session(lib=None, loghandler=None, paths=[], query=[], cli=False):
    cls = commands.TerminalImportSession if cli else importer.ImportSession
    return cls(lib, loghandler, paths, query)


class Assertions(object):
    """A mixin with additional unit test assertions."""

    def assertExists(self, path):  # noqa
        self.assertTrue(os.path.exists(syspath(path)),
                        u'file does not exist: {!r}'.format(path))

    def assertNotExists(self, path):  # noqa
        self.assertFalse(os.path.exists(syspath(path)),
                         u'file exists: {!r}'.format((path)))

    def assertIsFile(self, path):  # noqa
        self.assertExists(path)
        self.assertTrue(os.path.isfile(syspath(path)),
                        u'path exists, but is not a regular file: {!r}'
                        .format(path))

    def assertIsDir(self, path):  # noqa
        self.assertExists(path)
        self.assertTrue(os.path.isdir(syspath(path)),
                        u'path exists, but is not a directory: {!r}'
                        .format(path))

    def assert_equal_path(self, a, b):
        """Check that two paths are equal."""
        self.assertEqual(util.normpath(a), util.normpath(b),
                         u'paths are not equal: {!r} and {!r}'.format(a, b))


# A test harness for all beets tests.
# Provides temporary, isolated configuration.
class TestCase(unittest.TestCase, Assertions):
    """A unittest.TestCase subclass that saves and restores beets'
    global configuration. This allows tests to make temporary
    modifications that will then be automatically removed when the test
    completes. Also provides some additional assertion methods, a
    temporary directory, and a DummyIO.
    """
    def setUp(self):
        # A "clean" source list including only the defaults.
        beets.config.sources = []
        beets.config.read(user=False, defaults=True)

        # Direct paths to a temporary directory. Tests can also use this
        # temporary directory.
        self.temp_dir = util.bytestring_path(tempfile.mkdtemp())

        beets.config['statefile'] = \
            util.py3_path(os.path.join(self.temp_dir, b'state.pickle'))
        beets.config['library'] = \
            util.py3_path(os.path.join(self.temp_dir, b'library.db'))
        beets.config['directory'] = \
            util.py3_path(os.path.join(self.temp_dir, b'libdir'))

        # Set $HOME, which is used by Confuse to create directories.
        self._old_home = os.environ.get('HOME')
        os.environ['HOME'] = util.py3_path(self.temp_dir)

        # Initialize, but don't install, a DummyIO.
        self.io = DummyIO()

    def tearDown(self):
        if os.path.isdir(syspath(self.temp_dir)):
            shutil.rmtree(syspath(self.temp_dir))
        if self._old_home is None:
            del os.environ['HOME']
        else:
            os.environ['HOME'] = self._old_home
        self.io.restore()

        beets.config.clear()
        beets.config._materialized = False


class LibTestCase(TestCase):
    """A test case that includes an in-memory library object (`lib`) and
    an item added to the library (`i`).
    """
    def setUp(self):
        super(LibTestCase, self).setUp()
        self.lib = beets.library.Library(':memory:')
        self.i = item(self.lib)

    def tearDown(self):
        self.lib._connection().close()
        super(LibTestCase, self).tearDown()


# Mock timing.

class Timecop(object):
    """Mocks the timing system (namely time() and sleep()) for testing.
    Inspired by the Ruby timecop library.
    """
    def __init__(self):
        self.now = time.time()

    def time(self):
        return self.now

    def sleep(self, amount):
        self.now += amount

    def install(self):
        self.orig = {
            'time': time.time,
            'sleep': time.sleep,
        }
        time.time = self.time
        time.sleep = self.sleep

    def restore(self):
        time.time = self.orig['time']
        time.sleep = self.orig['sleep']


# Mock I/O.

class InputException(Exception):
    def __init__(self, output=None):
        self.output = output

    def __str__(self):
        msg = "Attempt to read with no input provided."
        if self.output is not None:
            msg += " Output: {!r}".format(self.output)
        return msg


class DummyOut(object):
    encoding = 'utf-8'

    def __init__(self):
        self.buf = []

    def write(self, s):
        self.buf.append(s)

    def get(self):
        if six.PY2:
            return b''.join(self.buf)
        else:
            return ''.join(self.buf)

    def flush(self):
        self.clear()

    def clear(self):
        self.buf = []


class DummyIn(object):
    encoding = 'utf-8'

    def __init__(self, out=None):
        self.buf = []
        self.reads = 0
        self.out = out

    def add(self, s):
        if six.PY2:
            self.buf.append(s + b'\n')
        else:
            self.buf.append(s + '\n')

    def close(self):
        pass

    def readline(self):
        if not self.buf:
            if self.out:
                raise InputException(self.out.get())
            else:
                raise InputException()
        self.reads += 1
        return self.buf.pop(0)


class DummyIO(object):
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
    open(syspath(path), 'a').close()


class Bag(object):
    """An object that exposes a set of fields given as keyword
    arguments. Any field not found in the dictionary appears to be None.
    Used for mocking Album objects and the like.
    """
    def __init__(self, **fields):
        self.fields = fields

    def __getattr__(self, key):
        return self.fields.get(key)


# Convenience methods for setting up a temporary sandbox directory for tests
# that need to interact with the filesystem.

class TempDirMixin(object):
    """Text mixin for creating and deleting a temporary directory.
    """

    def create_temp_dir(self):
        """Create a temporary directory and assign it into `self.temp_dir`.
        Call `remove_temp_dir` later to delete it.
        """
        self.temp_dir = bytestring_path(tempfile.mkdtemp())

    def remove_temp_dir(self):
        """Delete the temporary directory created by `create_temp_dir`.
        """
        if os.path.isdir(syspath(self.temp_dir)):
            shutil.rmtree(syspath(self.temp_dir))


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
    if 'SKIP_SLOW_TESTS' in os.environ:
        return unittest.skip(u'test is slow')
    return _id
