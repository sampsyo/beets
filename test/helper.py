# -*- coding: utf-8 -*-
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

"""This module includes various helpers that provide fixtures, capture
information or mock the environment.

- The `control_stdin` and `capture_stdout` context managers allow one to
  interact with the user interface.

- `has_program` checks the presence of a command on the system.

- The `generate_album_info` and `generate_track_info` functions return
  fixtures to be used when mocking the autotagger.

- The `ImportSessionFixture` allows one to run importer code while
  controlling the interactions through code.

- The `TestHelper` class encapsulates various fixtures that can be set up.
"""


from __future__ import division, absolute_import, print_function

import sys
import os
import os.path
import shutil
import subprocess
from tempfile import mkdtemp, mkstemp
from contextlib import contextmanager
from six import StringIO
from enum import Enum

import beets
from beets import logging
from beets import config
import beets.plugins
from beets.library import Library, Item, Album
from beets import importer
from beets.autotag.hooks import AlbumInfo, TrackInfo
from mediafile import MediaFile, Image
from beets import util
from beets.util import MoveOperation, syspath, bytestring_path

# TODO Move AutotagMock here
from test import _common
import six


class LogCapture(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self)
        self.messages = []

    def emit(self, record):
        self.messages.append(six.text_type(record.msg))


@contextmanager
def capture_log(logger='beets'):
    capture = LogCapture()
    log = logging.getLogger(logger)
    log.addHandler(capture)
    try:
        yield capture.messages
    finally:
        log.removeHandler(capture)


@contextmanager
def control_stdin(input=None):
    """Sends ``input`` to stdin.

    >>> with control_stdin('yes'):
    ...     input()
    'yes'
    """
    org = sys.stdin
    sys.stdin = StringIO(input)
    if six.PY2:  # StringIO encoding attr isn't writable in python >= 3
        sys.stdin.encoding = 'utf-8'
    try:
        yield sys.stdin
    finally:
        sys.stdin = org


@contextmanager
def capture_stdout():
    """Save stdout in a StringIO.

    >>> with capture_stdout() as output:
    ...     print('spam')
    ...
    >>> output.getvalue()
    'spam'
    """
    org = sys.stdout
    sys.stdout = capture = StringIO()
    if six.PY2:  # StringIO encoding attr isn't writable in python >= 3
        sys.stdout.encoding = 'utf-8'
    try:
        yield sys.stdout
    finally:
        sys.stdout = org
        print(capture.getvalue())


def _convert_args(args):
    """Convert args to bytestrings for Python 2 and convert them to strings
       on Python 3.
    """
    for i, elem in enumerate(args):
        if six.PY2:
            if isinstance(elem, six.text_type):
                args[i] = elem.encode(util.arg_encoding())
        else:
            if isinstance(elem, bytes):
                args[i] = elem.decode(util.arg_encoding())

    return args


def has_program(cmd, args=['--version']):
    """Returns `True` if `cmd` can be executed.
    """
    full_cmd = _convert_args([cmd] + args)
    try:
        with open(os.devnull, 'wb') as devnull:
            subprocess.check_call(full_cmd, stderr=devnull,
                                  stdout=devnull, stdin=devnull)
    except OSError:
        return False
    except subprocess.CalledProcessError:
        return False
    else:
        return True


class TestHelper(object):
    """Helper mixin for high-level cli and plugin tests.

    This mixin provides methods to isolate beets' global state provide
    fixtures.
    """
    # TODO automate teardown through hook registration

    def setup_beets(self, disk=False):
        """Setup pristine global configuration and library for testing.

        Sets ``beets.config`` so we can safely use any functionality
        that uses the global configuration.  All paths used are
        contained in a temporary directory

        Sets the following properties on itself.

        - ``temp_dir`` Path to a temporary directory containing all
          files specific to beets

        - ``libdir`` Path to a subfolder of ``temp_dir``, containing the
          library's media files. Same as ``config['directory']``.

        - ``config`` The global configuration used by beets.

        - ``lib`` Library instance created with the settings from
          ``config``.

        Make sure you call ``teardown_beets()`` afterwards.
        """
        self.create_temp_dir()
        os.environ['BEETSDIR'] = util.py3_path(self.temp_dir)

        self.config = beets.config
        self.config.clear()
        self.config.read()

        self.config['plugins'] = []
        self.config['verbose'] = 1
        self.config['ui']['color'] = False
        self.config['threaded'] = False

        self.libdir = os.path.join(self.temp_dir, b'libdir')
        os.mkdir(syspath(self.libdir))
        self.config['directory'] = util.py3_path(self.libdir)

        if disk:
            dbpath = util.bytestring_path(
                self.config['library'].as_filename()
            )
        else:
            dbpath = ':memory:'
        self.lib = Library(dbpath, self.libdir)

    def teardown_beets(self):
        self.lib._close()
        if 'BEETSDIR' in os.environ:
            del os.environ['BEETSDIR']
        self.remove_temp_dir()
        self.config.clear()
        beets.config.read(user=False, defaults=True)

    def load_plugins(self, *plugins):
        """Load and initialize plugins by names.

        Similar setting a list of plugins in the configuration. Make
        sure you call ``unload_plugins()`` afterwards.
        """
        # FIXME this should eventually be handled by a plugin manager
        beets.config['plugins'] = plugins
        beets.plugins.load_plugins(plugins)
        beets.plugins.find_plugins()

        # Take a backup of the original _types and _queries to restore
        # when unloading.
        Item._original_types = dict(Item._types)
        Album._original_types = dict(Album._types)
        Item._types.update(beets.plugins.types(Item))
        Album._types.update(beets.plugins.types(Album))

        Item._original_queries = dict(Item._queries)
        Album._original_queries = dict(Album._queries)
        Item._queries.update(beets.plugins.named_queries(Item))
        Album._queries.update(beets.plugins.named_queries(Album))

    def unload_plugins(self):
        """Unload all plugins and remove the from the configuration.
        """
        # FIXME this should eventually be handled by a plugin manager
        beets.config['plugins'] = []
        beets.plugins._classes = set()
        beets.plugins._instances = {}
        Item._types = Item._original_types
        Album._types = Album._original_types
        Item._queries = Item._original_queries
        Album._queries = Album._original_queries

    def create_importer(self, item_count=1, album_count=1):
        """Create files to import and return corresponding session.

        Copies the specified number of files to a subdirectory of
        `self.temp_dir` and creates a `ImportSessionFixture` for this path.
        """
        import_dir = os.path.join(self.temp_dir, b'import')
        if not os.path.isdir(syspath(import_dir)):
            os.mkdir(syspath(import_dir))

        album_no = 0
        while album_count:
            album = util.bytestring_path(u'album {0}'.format(album_no))
            album_dir = os.path.join(import_dir, album)
            if os.path.exists(syspath(album_dir)):
                album_no += 1
                continue
            os.mkdir(syspath(album_dir))
            album_count -= 1

            track_no = 0
            album_item_count = item_count
            while album_item_count:
                title = u'track {0}'.format(track_no)
                src = os.path.join(_common.RSRC, b'full.mp3')
                title_file = util.bytestring_path('{0}.mp3'.format(title))
                dest = os.path.join(album_dir, title_file)
                if os.path.exists(syspath(dest)):
                    track_no += 1
                    continue
                album_item_count -= 1
                shutil.copy(syspath(src), syspath(dest))
                mediafile = MediaFile(dest)
                mediafile.update({
                    'artist': 'artist',
                    'albumartist': 'album artist',
                    'title': title,
                    'album': album,
                    'mb_albumid': None,
                    'mb_trackid': None,
                })
                mediafile.save()

        config['import']['quiet'] = True
        config['import']['autotag'] = False
        config['import']['resume'] = False

        return ImportSessionFixture(self.lib, loghandler=None, query=None,
                                    paths=[import_dir])

    # Library fixtures methods

    def create_item(self, **values):
        """Return an `Item` instance with sensible default values.

        The item receives its attributes from `**values` paratmeter. The
        `title`, `artist`, `album`, `track`, `format` and `path`
        attributes have defaults if they are not given as parameters.
        The `title` attribute is formated with a running item count to
        prevent duplicates. The default for the `path` attribute
        respects the `format` value.

        The item is attached to the database from `self.lib`.
        """
        item_count = self._get_item_count()
        values_ = {
            'title': u't\u00eftle {0}',
            'artist': u'the \u00e4rtist',
            'album': u'the \u00e4lbum',
            'track': item_count,
            'format': 'MP3',
        }
        values_.update(values)
        values_['title'] = values_['title'].format(item_count)
        values_['db'] = self.lib
        item = Item(**values_)
        if 'path' not in values:
            item['path'] = 'audio.' + item['format'].lower()
        # mtime needs to be set last since other assignments reset it.
        item.mtime = 12345
        return item

    def add_item(self, **values):
        """Add an item to the library and return it.

        Creates the item by passing the parameters to `create_item()`.

        If `path` is not set in `values` it is set to `item.destination()`.
        """
        # When specifying a path, store it normalized (as beets does
        # ordinarily).
        if 'path' in values:
            values['path'] = util.normpath(values['path'])

        item = self.create_item(**values)
        item.add(self.lib)

        # Ensure every item has a path.
        if 'path' not in values:
            item['path'] = item.destination()
            item.store()

        return item

    def add_item_fixture(self, **values):
        """Add an item with an actual audio file to the library.
        """
        item = self.create_item(**values)
        extension = item['format'].lower()
        item['path'] = os.path.join(_common.RSRC,
                                    util.bytestring_path('min.' + extension))
        item.add(self.lib)
        item.move(operation=MoveOperation.COPY)
        item.store()
        return item

    def add_album(self, **values):
        item = self.add_item(**values)
        return self.lib.add_album([item])

    def add_item_fixtures(self, ext='mp3', count=1):
        """Add a number of items with files to the database.
        """
        # TODO base this on `add_item()`
        items = []
        path = os.path.join(_common.RSRC, util.bytestring_path('full.' + ext))
        for i in range(count):
            item = Item.from_path(path)
            item.album = u'\u00e4lbum {0}'.format(i)  # Check unicode paths
            item.title = u't\u00eftle {0}'.format(i)
            # mtime needs to be set last since other assignments reset it.
            item.mtime = 12345
            item.add(self.lib)
            item.move(operation=MoveOperation.COPY)
            item.store()
            items.append(item)
        return items

    def add_album_fixture(self, track_count=1, ext='mp3'):
        """Add an album with files to the database.
        """
        items = []
        path = os.path.join(_common.RSRC, util.bytestring_path('full.' + ext))
        for i in range(track_count):
            item = Item.from_path(path)
            item.album = u'\u00e4lbum'  # Check unicode paths
            item.title = u't\u00eftle {0}'.format(i)
            # mtime needs to be set last since other assignments reset it.
            item.mtime = 12345
            item.add(self.lib)
            item.move(operation=MoveOperation.COPY)
            item.store()
            items.append(item)
        return self.lib.add_album(items)

    def create_mediafile_fixture(self, ext='mp3', images=[]):
        """Copies a fixture mediafile with the extension to a temporary
        location and returns the path.

        It keeps track of the created locations and will delete the with
        `remove_mediafile_fixtures()`

        `images` is a subset of 'png', 'jpg', and 'tiff'. For each
        specified extension a cover art image is added to the media
        file.
        """
        src = os.path.join(_common.RSRC, util.bytestring_path('full.' + ext))
        handle, path = mkstemp()
        path = bytestring_path(path)
        os.close(handle)
        shutil.copyfile(syspath(src), syspath(path))

        if images:
            mediafile = MediaFile(path)
            imgs = []
            for img_ext in images:
                file = util.bytestring_path('image-2x3.{0}'.format(img_ext))
                img_path = os.path.join(_common.RSRC, file)
                with open(img_path, 'rb') as f:
                    imgs.append(Image(f.read()))
            mediafile.images = imgs
            mediafile.save()

        if not hasattr(self, '_mediafile_fixtures'):
            self._mediafile_fixtures = []
        self._mediafile_fixtures.append(path)

        return path

    def remove_mediafile_fixtures(self):
        if hasattr(self, '_mediafile_fixtures'):
            for path in self._mediafile_fixtures:
                os.remove(syspath(path))

    def _get_item_count(self):
        if not hasattr(self, '__item_count'):
            count = 0
        self.__item_count = count + 1
        return count

    # Running beets commands

    def run_command(self, *args, **kwargs):
        """Run a beets command with an arbitrary amount of arguments. The
           Library` defaults to `self.lib`, but can be overridden with
           the keyword argument `lib`.
        """
        sys.argv = ['beet']  # avoid leakage from test suite args
        lib = None
        if hasattr(self, 'lib'):
            lib = self.lib
        lib = kwargs.get('lib', lib)
        beets.ui._raw_main(_convert_args(list(args)), lib)

    def run_with_output(self, *args):
        with capture_stdout() as out:
            self.run_command(*args)
        return util.text_string(out.getvalue())

    # Safe file operations

    def create_temp_dir(self):
        """Create a temporary directory and assign it into
        `self.temp_dir`. Call `remove_temp_dir` later to delete it.
        """
        temp_dir = mkdtemp()
        self.temp_dir = util.bytestring_path(temp_dir)

    def remove_temp_dir(self):
        """Delete the temporary directory created by `create_temp_dir`.
        """
        shutil.rmtree(syspath(self.temp_dir))

    def touch(self, path, dir=None, content=''):
        """Create a file at `path` with given content.

        If `dir` is given, it is prepended to `path`. After that, if the
        path is relative, it is resolved with respect to
        `self.temp_dir`.
        """
        if dir:
            path = os.path.join(dir, path)

        if not os.path.isabs(path):
            path = os.path.join(self.temp_dir, path)

        parent = os.path.dirname(path)
        if not os.path.isdir(syspath(parent)):
            os.makedirs(syspath(parent))

        with open(syspath(path), 'a+') as f:
            f.write(content)
        return path


class ImportSessionFixture(importer.ImportSession):
    """ImportSession that can be controlled programaticaly.

    >>> lib = Library(':memory:')
    >>> importer = ImportSessionFixture(lib, paths=['/path/to/import'])
    >>> importer.add_choice(importer.action.SKIP)
    >>> importer.add_choice(importer.action.ASIS)
    >>> importer.default_choice = importer.action.APPLY
    >>> importer.run()

    This imports ``/path/to/import`` into `lib`. It skips the first
    album and imports thesecond one with metadata from the tags. For the
    remaining albums, the metadata from the autotagger will be applied.
    """

    def __init__(self, *args, **kwargs):
        super(ImportSessionFixture, self).__init__(*args, **kwargs)
        self._choices = []
        self._resolutions = []

    default_choice = importer.action.APPLY

    def add_choice(self, choice):
        self._choices.append(choice)

    def clear_choices(self):
        self._choices = []

    def choose_match(self, task):
        try:
            choice = self._choices.pop(0)
        except IndexError:
            choice = self.default_choice

        if choice == importer.action.APPLY:
            return task.candidates[0]
        elif isinstance(choice, int):
            return task.candidates[choice - 1]
        else:
            return choice

    choose_item = choose_match

    Resolution = Enum('Resolution', 'REMOVE SKIP KEEPBOTH MERGE')

    default_resolution = 'REMOVE'

    def add_resolution(self, resolution):
        assert isinstance(resolution, self.Resolution)
        self._resolutions.append(resolution)

    def resolve_duplicate(self, task, found_duplicates):
        try:
            res = self._resolutions.pop(0)
        except IndexError:
            res = self.default_resolution

        if res == self.Resolution.SKIP:
            task.set_choice(importer.action.SKIP)
        elif res == self.Resolution.REMOVE:
            task.should_remove_duplicates = True
        elif res == self.Resolution.MERGE:
            task.should_merge_duplicates = True


def generate_album_info(album_id, track_values):
    """Return `AlbumInfo` populated with mock data.

    Sets the album info's `album_id` field is set to the corresponding
    argument. For each pair (`id`, `values`) in `track_values` the `TrackInfo`
    from `generate_track_info` is added to the album info's `tracks` field.
    Most other fields of the album and track info are set to "album
    info" and "track info", respectively.
    """
    tracks = [generate_track_info(id, values) for id, values in track_values]
    album = AlbumInfo(
        album_id=u'album info',
        album=u'album info',
        artist=u'album info',
        artist_id=u'album info',
        tracks=tracks,
    )
    for field in ALBUM_INFO_FIELDS:
        setattr(album, field, u'album info')

    return album

ALBUM_INFO_FIELDS = ['album', 'album_id', 'artist', 'artist_id',
                     'asin', 'albumtype', 'va', 'label',
                     'artist_sort', 'releasegroup_id', 'catalognum',
                     'language', 'country', 'albumstatus', 'media',
                     'albumdisambig', 'releasegroupdisambig', 'artist_credit',
                     'data_source', 'data_url']


def generate_track_info(track_id='track info', values={}):
    """Return `TrackInfo` populated with mock data.

    The `track_id` field is set to the corresponding argument. All other
    string fields are set to "track info".
    """
    track = TrackInfo(
        title=u'track info',
        track_id=track_id,
    )
    for field in TRACK_INFO_FIELDS:
        setattr(track, field, u'track info')
    for field, value in values.items():
        setattr(track, field, value)
    return track

TRACK_INFO_FIELDS = ['artist', 'artist_id', 'artist_sort',
                     'disctitle', 'artist_credit', 'data_source',
                     'data_url']
