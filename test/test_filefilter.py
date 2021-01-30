# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Malte Ried.
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

"""Tests for the `filefilter` plugin.
"""

from __future__ import division, absolute_import, print_function

import os
import shutil
import unittest

from test import _common
from test.helper import capture_log
from test.test_importer import ImportHelper
from beets import config
from mediafile import MediaFile
from beets.util import displayable_path, bytestring_path, syspath
from beetsplug.filefilter import FileFilterPlugin


class FileFilterPluginTest(unittest.TestCase, ImportHelper):
    def setUp(self):
        self.setup_beets()
        self.__create_import_dir(2)
        self._setup_import_session()
        config['import']['pretend'] = True

    def tearDown(self):
        self.teardown_beets()

    def __copy_file(self, dest_path, metadata):
        # Copy files
        resource_path = os.path.join(_common.RSRC, b'full.mp3')
        shutil.copy(syspath(resource_path), syspath(dest_path))
        medium = MediaFile(dest_path)
        # Set metadata
        for attr in metadata:
            setattr(medium, attr, metadata[attr])
        medium.save()

    def __create_import_dir(self, count):
        self.import_dir = os.path.join(self.temp_dir, b'testsrcdir')
        if os.path.isdir(syspath(self.import_dir)):
            shutil.rmtree(syspath(self.import_dir))

        self.artist_path = os.path.join(self.import_dir, b'artist')
        self.album_path = os.path.join(self.artist_path, b'album')
        self.misc_path = os.path.join(self.import_dir, b'misc')
        os.makedirs(syspath(self.album_path))
        os.makedirs(syspath(self.misc_path))

        metadata = {
            'artist': 'Tag Artist',
            'album':  'Tag Album',
            'albumartist':  None,
            'mb_trackid': None,
            'mb_albumid': None,
            'comp': None,
        }
        self.album_paths = []
        for i in range(count):
            metadata['track'] = i + 1
            metadata['title'] = 'Tag Title Album %d' % (i + 1)
            track_file = bytestring_path('%02d - track.mp3' % (i + 1))
            dest_path = os.path.join(self.album_path, track_file)
            self.__copy_file(dest_path, metadata)
            self.album_paths.append(dest_path)

        self.artist_paths = []
        metadata['album'] = None
        for i in range(count):
            metadata['track'] = i + 10
            metadata['title'] = 'Tag Title Artist %d' % (i + 1)
            track_file = bytestring_path('track_%d.mp3' % (i + 1))
            dest_path = os.path.join(self.artist_path, track_file)
            self.__copy_file(dest_path, metadata)
            self.artist_paths.append(dest_path)

        self.misc_paths = []
        for i in range(count):
            metadata['artist'] = 'Artist %d' % (i + 42)
            metadata['track'] = i + 5
            metadata['title'] = 'Tag Title Misc %d' % (i + 1)
            track_file = bytestring_path('track_%d.mp3' % (i + 1))
            dest_path = os.path.join(self.misc_path, track_file)
            self.__copy_file(dest_path, metadata)
            self.misc_paths.append(dest_path)

    def __run(self, expected_lines, singletons=False):
        self.load_plugins('filefilter')

        import_files = [self.import_dir]
        self._setup_import_session(singletons=singletons)
        self.importer.paths = import_files

        with capture_log() as logs:
            self.importer.run()
        self.unload_plugins()
        FileFilterPlugin.listeners = None

        logs = [line for line in logs if not line.startswith('Sending event:')]

        self.assertEqual(logs, expected_lines)

    def test_import_default(self):
        """ The default configuration should import everything.
        """
        self.__run([
            'Album: %s' % displayable_path(self.artist_path),
            '  %s' % displayable_path(self.artist_paths[0]),
            '  %s' % displayable_path(self.artist_paths[1]),
            'Album: %s' % displayable_path(self.album_path),
            '  %s' % displayable_path(self.album_paths[0]),
            '  %s' % displayable_path(self.album_paths[1]),
            'Album: %s' % displayable_path(self.misc_path),
            '  %s' % displayable_path(self.misc_paths[0]),
            '  %s' % displayable_path(self.misc_paths[1])
        ])

    def test_import_nothing(self):
        config['filefilter']['path'] = 'not_there'
        self.__run(['No files imported from %s' % displayable_path(
            self.import_dir)])

    # Global options
    def test_import_global(self):
        config['filefilter']['path'] = '.*track_1.*\\.mp3'
        self.__run([
            'Album: %s' % displayable_path(self.artist_path),
            '  %s' % displayable_path(self.artist_paths[0]),
            'Album: %s' % displayable_path(self.misc_path),
            '  %s' % displayable_path(self.misc_paths[0]),
        ])
        self.__run([
            'Singleton: %s' % displayable_path(self.artist_paths[0]),
            'Singleton: %s' % displayable_path(self.misc_paths[0])
        ], singletons=True)

    # Album options
    def test_import_album(self):
        config['filefilter']['album_path'] = '.*track_1.*\\.mp3'
        self.__run([
            'Album: %s' % displayable_path(self.artist_path),
            '  %s' % displayable_path(self.artist_paths[0]),
            'Album: %s' % displayable_path(self.misc_path),
            '  %s' % displayable_path(self.misc_paths[0]),
        ])
        self.__run([
            'Singleton: %s' % displayable_path(self.artist_paths[0]),
            'Singleton: %s' % displayable_path(self.artist_paths[1]),
            'Singleton: %s' % displayable_path(self.album_paths[0]),
            'Singleton: %s' % displayable_path(self.album_paths[1]),
            'Singleton: %s' % displayable_path(self.misc_paths[0]),
            'Singleton: %s' % displayable_path(self.misc_paths[1])
        ], singletons=True)

    # Singleton options
    def test_import_singleton(self):
        config['filefilter']['singleton_path'] = '.*track_1.*\\.mp3'
        self.__run([
            'Singleton: %s' % displayable_path(self.artist_paths[0]),
            'Singleton: %s' % displayable_path(self.misc_paths[0])
        ], singletons=True)
        self.__run([
            'Album: %s' % displayable_path(self.artist_path),
            '  %s' % displayable_path(self.artist_paths[0]),
            '  %s' % displayable_path(self.artist_paths[1]),
            'Album: %s' % displayable_path(self.album_path),
            '  %s' % displayable_path(self.album_paths[0]),
            '  %s' % displayable_path(self.album_paths[1]),
            'Album: %s' % displayable_path(self.misc_path),
            '  %s' % displayable_path(self.misc_paths[0]),
            '  %s' % displayable_path(self.misc_paths[1])
        ])

    # Album and singleton options
    def test_import_both(self):
        config['filefilter']['album_path'] = '.*track_1.*\\.mp3'
        config['filefilter']['singleton_path'] = '.*track_2.*\\.mp3'
        self.__run([
            'Album: %s' % displayable_path(self.artist_path),
            '  %s' % displayable_path(self.artist_paths[0]),
            'Album: %s' % displayable_path(self.misc_path),
            '  %s' % displayable_path(self.misc_paths[0]),
        ])
        self.__run([
            'Singleton: %s' % displayable_path(self.artist_paths[1]),
            'Singleton: %s' % displayable_path(self.misc_paths[1])
        ], singletons=True)


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
