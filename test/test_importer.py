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

from __future__ import division, absolute_import, print_function

"""Tests for the general importer functionality.
"""
import os
import re
import shutil
import unicodedata
import sys
import stat
from six import StringIO
from tempfile import mkstemp
from zipfile import ZipFile
from tarfile import TarFile
from mock import patch, Mock
import unittest

from test import _common
from test.helper import TestHelper, has_program, capture_log
from test.helper import ImportSessionFixture
from beets import importer
from beets.importer import albums_in_dir
from mediafile import MediaFile
from beets import autotag
from beets.autotag import AlbumInfo, TrackInfo, AlbumMatch
from beets import config
from beets import logging
from beets import util
from beets.util import displayable_path, bytestring_path, py3_path, syspath


class AutotagStub(object):
    """Stub out MusicBrainz album and track matcher and control what the
    autotagger returns.
    """

    NONE = 'NONE'
    IDENT = 'IDENT'
    GOOD = 'GOOD'
    BAD = 'BAD'
    MISSING = 'MISSING'
    """Generate an album match for all but one track
    """

    length = 2
    matching = IDENT

    def install(self):
        self.mb_match_album = autotag.mb.match_album
        self.mb_match_track = autotag.mb.match_track
        self.mb_album_for_id = autotag.mb.album_for_id
        self.mb_track_for_id = autotag.mb.track_for_id

        autotag.mb.match_album = self.match_album
        autotag.mb.match_track = self.match_track
        autotag.mb.album_for_id = self.album_for_id
        autotag.mb.track_for_id = self.track_for_id

        return self

    def restore(self):
        autotag.mb.match_album = self.mb_match_album
        autotag.mb.match_track = self.mb_match_track
        autotag.mb.album_for_id = self.mb_album_for_id
        autotag.mb.track_for_id = self.mb_track_for_id

    def match_album(self, albumartist, album, tracks, extra_tags):
        if self.matching == self.IDENT:
            yield self._make_album_match(albumartist, album, tracks)

        elif self.matching == self.GOOD:
            for i in range(self.length):
                yield self._make_album_match(albumartist, album, tracks, i)

        elif self.matching == self.BAD:
            for i in range(self.length):
                yield self._make_album_match(albumartist, album, tracks, i + 1)

        elif self.matching == self.MISSING:
            yield self._make_album_match(albumartist, album, tracks, missing=1)

    def match_track(self, artist, title):
        yield TrackInfo(
            title=title.replace('Tag', 'Applied'),
            track_id=u'trackid',
            artist=artist.replace('Tag', 'Applied'),
            artist_id=u'artistid',
            length=1,
            index=0,
        )

    def album_for_id(self, mbid):
        return None

    def track_for_id(self, mbid):
        return None

    def _make_track_match(self, artist, album, number):
        return TrackInfo(
            title=u'Applied Title %d' % number,
            track_id=u'match %d' % number,
            artist=artist,
            length=1,
            index=0,
        )

    def _make_album_match(self, artist, album, tracks, distance=0, missing=0):
        if distance:
            id = ' ' + 'M' * distance
        else:
            id = ''
        if artist is None:
            artist = u"Various Artists"
        else:
            artist = artist.replace('Tag', 'Applied') + id
        album = album.replace('Tag', 'Applied') + id

        track_infos = []
        for i in range(tracks - missing):
            track_infos.append(self._make_track_match(artist, album, i + 1))

        return AlbumInfo(
            artist=artist,
            album=album,
            tracks=track_infos,
            va=False,
            album_id=u'albumid' + id,
            artist_id=u'artistid' + id,
            albumtype=u'soundtrack'
        )


class ImportHelper(TestHelper):
    """Provides tools to setup a library, a directory containing files that are
    to be imported and an import session. The class also provides stubs for the
    autotagging library and several assertions for the library.
    """

    def setup_beets(self, disk=False):
        super(ImportHelper, self).setup_beets(disk)
        self.lib.path_formats = [
            (u'default', os.path.join('$artist', '$album', '$title')),
            (u'singleton:true', os.path.join('singletons', '$title')),
            (u'comp:true', os.path.join('compilations', '$album', '$title')),
        ]

    def _create_import_dir(self, count=3):
        """Creates a directory with media files to import.
        Sets ``self.import_dir`` to the path of the directory. Also sets
        ``self.import_media`` to a list :class:`MediaFile` for all the files in
        the directory.

        The directory has following layout
          the_album/
            track_1.mp3
            track_2.mp3
            track_3.mp3

        :param count:  Number of files to create
        """
        self.import_dir = os.path.join(self.temp_dir, b'testsrcdir')
        if os.path.isdir(syspath(self.import_dir)):
            shutil.rmtree(syspath(self.import_dir))

        album_path = os.path.join(self.import_dir, b'the_album')
        os.makedirs(syspath(album_path))

        resource_path = os.path.join(_common.RSRC, b'full.mp3')

        metadata = {
            'artist': u'Tag Artist',
            'album':  u'Tag Album',
            'albumartist':  None,
            'mb_trackid': None,
            'mb_albumid': None,
            'comp': None
        }
        self.media_files = []
        for i in range(count):
            # Copy files
            medium_path = os.path.join(
                album_path,
                bytestring_path('track_%d.mp3' % (i + 1))
            )
            shutil.copy(syspath(resource_path), syspath(medium_path))
            medium = MediaFile(medium_path)

            # Set metadata
            metadata['track'] = i + 1
            metadata['title'] = u'Tag Title %d' % (i + 1)
            for attr in metadata:
                setattr(medium, attr, metadata[attr])
            medium.save()
            self.media_files.append(medium)
        self.import_media = self.media_files

    def _setup_import_session(self, import_dir=None, delete=False,
                              threaded=False, copy=True, singletons=False,
                              move=False, autotag=True, link=False,
                              hardlink=False):
        config['import']['copy'] = copy
        config['import']['delete'] = delete
        config['import']['timid'] = True
        config['threaded'] = False
        config['import']['singletons'] = singletons
        config['import']['move'] = move
        config['import']['autotag'] = autotag
        config['import']['resume'] = False
        config['import']['link'] = link
        config['import']['hardlink'] = hardlink

        self.importer = ImportSessionFixture(
            self.lib, loghandler=None, query=None,
            paths=[import_dir or self.import_dir]
        )

    def assert_file_in_lib(self, *segments):
        """Join the ``segments`` and assert that this path exists in the library
        directory
        """
        self.assertExists(os.path.join(self.libdir, *segments))

    def assert_file_not_in_lib(self, *segments):
        """Join the ``segments`` and assert that this path exists in the library
        directory
        """
        self.assertNotExists(os.path.join(self.libdir, *segments))

    def assert_lib_dir_empty(self):
        self.assertEqual(len(os.listdir(syspath(self.libdir))), 0)


@_common.slow_test()
class NonAutotaggedImportTest(_common.TestCase, ImportHelper):
    def setUp(self):
        self.setup_beets(disk=True)
        self._create_import_dir(2)
        self._setup_import_session(autotag=False)

    def tearDown(self):
        self.teardown_beets()

    def test_album_created_with_track_artist(self):
        self.importer.run()
        albums = self.lib.albums()
        self.assertEqual(len(albums), 1)
        self.assertEqual(albums[0].albumartist, u'Tag Artist')

    def test_import_copy_arrives(self):
        self.importer.run()
        for mediafile in self.import_media:
            self.assert_file_in_lib(
                b'Tag Artist', b'Tag Album',
                util.bytestring_path('{0}.mp3'.format(mediafile.title)))

    def test_threaded_import_copy_arrives(self):
        config['threaded'] = True

        self.importer.run()
        for mediafile in self.import_media:
            self.assert_file_in_lib(
                b'Tag Artist', b'Tag Album',
                util.bytestring_path('{0}.mp3'.format(mediafile.title)))

    def test_import_with_move_deletes_import_files(self):
        config['import']['move'] = True

        for mediafile in self.import_media:
            self.assertExists(mediafile.path)
        self.importer.run()
        for mediafile in self.import_media:
            self.assertNotExists(mediafile.path)

    def test_import_with_move_prunes_directory_empty(self):
        config['import']['move'] = True

        self.assertExists(os.path.join(self.import_dir, b'the_album'))
        self.importer.run()
        self.assertNotExists(os.path.join(self.import_dir, b'the_album'))

    def test_import_with_move_prunes_with_extra_clutter(self):
        self.touch(os.path.join(self.import_dir, b'the_album', b'alog.log'))
        config['clutter'] = ['*.log']
        config['import']['move'] = True

        self.assertExists(os.path.join(self.import_dir, b'the_album'))
        self.importer.run()
        self.assertNotExists(os.path.join(self.import_dir, b'the_album'))

    def test_threaded_import_move_arrives(self):
        config['import']['move'] = True
        config['import']['threaded'] = True

        self.importer.run()
        for mediafile in self.import_media:
            self.assert_file_in_lib(
                b'Tag Artist', b'Tag Album',
                util.bytestring_path('{0}.mp3'.format(mediafile.title)))

    def test_threaded_import_move_deletes_import(self):
        config['import']['move'] = True
        config['threaded'] = True

        self.importer.run()
        for mediafile in self.import_media:
            self.assertNotExists(mediafile.path)

    def test_import_without_delete_retains_files(self):
        config['import']['delete'] = False
        self.importer.run()
        for mediafile in self.import_media:
            self.assertExists(mediafile.path)

    def test_import_with_delete_removes_files(self):
        config['import']['delete'] = True

        self.importer.run()
        for mediafile in self.import_media:
            self.assertNotExists(mediafile.path)

    def test_import_with_delete_prunes_directory_empty(self):
        config['import']['delete'] = True
        self.assertExists(os.path.join(self.import_dir, b'the_album'))
        self.importer.run()
        self.assertNotExists(os.path.join(self.import_dir, b'the_album'))

    @unittest.skipUnless(_common.HAVE_SYMLINK, "need symlinks")
    def test_import_link_arrives(self):
        config['import']['link'] = True
        self.importer.run()
        for mediafile in self.import_media:
            filename = os.path.join(
                self.libdir,
                b'Tag Artist', b'Tag Album',
                util.bytestring_path('{0}.mp3'.format(mediafile.title))
            )
            self.assertExists(filename)
            self.assertTrue(os.path.islink(syspath(filename)))
            self.assert_equal_path(
                util.bytestring_path(os.readlink(syspath(filename))),
                mediafile.path
            )

    @unittest.skipUnless(_common.HAVE_HARDLINK, "need hardlinks")
    def test_import_hardlink_arrives(self):
        config['import']['hardlink'] = True
        self.importer.run()
        for mediafile in self.import_media:
            filename = os.path.join(
                self.libdir,
                b'Tag Artist', b'Tag Album',
                util.bytestring_path('{0}.mp3'.format(mediafile.title))
            )
            self.assertExists(filename)
            s1 = os.stat(syspath(mediafile.path))
            s2 = os.stat(syspath(filename))
            self.assertTrue(
                (s1[stat.ST_INO], s1[stat.ST_DEV]) ==
                (s2[stat.ST_INO], s2[stat.ST_DEV])
            )


def create_archive(session):
    (handle, path) = mkstemp(dir=py3_path(session.temp_dir))
    path = bytestring_path(path)
    os.close(handle)
    archive = ZipFile(py3_path(path), mode='w')
    archive.write(syspath(os.path.join(_common.RSRC, b'full.mp3')),
                  'full.mp3')
    archive.close()
    path = bytestring_path(path)
    return path


class RmTempTest(unittest.TestCase, ImportHelper, _common.Assertions):
    """Tests that temporarily extracted archives are properly removed
    after usage.
    """

    def setUp(self):
        self.setup_beets()
        self.want_resume = False
        self.config['incremental'] = False
        self._old_home = None

    def tearDown(self):
        self.teardown_beets()

    def test_rm(self):
        zip_path = create_archive(self)
        archive_task = importer.ArchiveImportTask(zip_path)
        archive_task.extract()
        tmp_path = archive_task.toppath
        self._setup_import_session(autotag=False, import_dir=tmp_path)
        self.assertExists(tmp_path)
        archive_task.finalize(self)
        self.assertNotExists(tmp_path)


class ImportZipTest(unittest.TestCase, ImportHelper):

    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    def test_import_zip(self):
        zip_path = create_archive(self)
        self.assertEqual(len(self.lib.items()), 0)
        self.assertEqual(len(self.lib.albums()), 0)

        self._setup_import_session(autotag=False, import_dir=zip_path)
        self.importer.run()
        self.assertEqual(len(self.lib.items()), 1)
        self.assertEqual(len(self.lib.albums()), 1)


class ImportTarTest(ImportZipTest):

    def create_archive(self):
        (handle, path) = mkstemp(dir=syspath(self.temp_dir))
        path = bytestring_path(path)
        os.close(handle)
        archive = TarFile(py3_path(path), mode='w')
        archive.add(syspath(os.path.join(_common.RSRC, b'full.mp3')),
                    'full.mp3')
        archive.close()
        return path


@unittest.skipIf(not has_program('unrar'), u'unrar program not found')
class ImportRarTest(ImportZipTest):

    def create_archive(self):
        return os.path.join(_common.RSRC, b'archive.rar')


@unittest.skip('Implement me!')
class ImportPasswordRarTest(ImportZipTest):

    def create_archive(self):
        return os.path.join(_common.RSRC, b'password.rar')


class ImportSingletonTest(_common.TestCase, ImportHelper):
    """Test ``APPLY`` and ``ASIS`` choices for an import session with singletons
    config set to True.
    """

    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)
        self._setup_import_session()
        config['import']['singletons'] = True
        self.matcher = AutotagStub().install()

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_apply_asis_adds_track(self):
        self.assertEqual(self.lib.items().get(), None)

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'Tag Title 1')

    def test_apply_asis_does_not_add_album(self):
        self.assertEqual(self.lib.albums().get(), None)

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get(), None)

    def test_apply_asis_adds_singleton_path(self):
        self.assert_lib_dir_empty()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assert_file_in_lib(b'singletons', b'Tag Title 1.mp3')

    def test_apply_candidate_adds_track(self):
        self.assertEqual(self.lib.items().get(), None)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'Applied Title 1')

    def test_apply_candidate_does_not_add_album(self):
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.albums().get(), None)

    def test_apply_candidate_adds_singleton_path(self):
        self.assert_lib_dir_empty()

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assert_file_in_lib(b'singletons', b'Applied Title 1.mp3')

    def test_skip_does_not_add_first_track(self):
        self.importer.add_choice(importer.action.SKIP)
        self.importer.run()
        self.assertEqual(self.lib.items().get(), None)

    def test_skip_adds_other_tracks(self):
        self._create_import_dir(2)
        self.importer.add_choice(importer.action.SKIP)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(len(self.lib.items()), 1)

    def test_import_single_files(self):
        resource_path = os.path.join(_common.RSRC, b'empty.mp3')
        single_path = os.path.join(self.import_dir, b'track_2.mp3')

        util.copy(resource_path, single_path)
        import_files = [
            os.path.join(self.import_dir, b'the_album'),
            single_path
        ]
        self._setup_import_session(singletons=False)
        self.importer.paths = import_files

        self.importer.add_choice(importer.action.ASIS)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()

        self.assertEqual(len(self.lib.items()), 2)
        self.assertEqual(len(self.lib.albums()), 2)

    def test_set_fields(self):
        genre = u"\U0001F3B7 Jazz"
        collection = u"To Listen"

        config['import']['set_fields'] = {
            u'collection': collection,
            u'genre': genre
        }

        # As-is item import.
        self.assertEqual(self.lib.albums().get(), None)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()

        for item in self.lib.items():
            item.load()  # TODO: Not sure this is necessary.
            self.assertEqual(item.genre, genre)
            self.assertEqual(item.collection, collection)
            # Remove item from library to test again with APPLY choice.
            item.remove()

        # Autotagged.
        self.assertEqual(self.lib.albums().get(), None)
        self.importer.clear_choices()
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()

        for item in self.lib.items():
            item.load()
            self.assertEqual(item.genre, genre)
            self.assertEqual(item.collection, collection)


class ImportTest(_common.TestCase, ImportHelper):
    """Test APPLY, ASIS and SKIP choices.
    """
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)
        self._setup_import_session()
        self.matcher = AutotagStub().install()
        self.matcher.macthin = AutotagStub.GOOD

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_apply_asis_adds_album(self):
        self.assertEqual(self.lib.albums().get(), None)

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, u'Tag Album')

    def test_apply_asis_adds_tracks(self):
        self.assertEqual(self.lib.items().get(), None)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'Tag Title 1')

    def test_apply_asis_adds_album_path(self):
        self.assert_lib_dir_empty()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assert_file_in_lib(
            b'Tag Artist', b'Tag Album', b'Tag Title 1.mp3')

    def test_apply_candidate_adds_album(self):
        self.assertEqual(self.lib.albums().get(), None)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, u'Applied Album')

    def test_apply_candidate_adds_tracks(self):
        self.assertEqual(self.lib.items().get(), None)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'Applied Title 1')

    def test_apply_candidate_adds_album_path(self):
        self.assert_lib_dir_empty()

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assert_file_in_lib(
            b'Applied Artist', b'Applied Album', b'Applied Title 1.mp3')

    def test_apply_from_scratch_removes_other_metadata(self):
        config['import']['from_scratch'] = True

        for mediafile in self.import_media:
            mediafile.genre = u'Tag Genre'
            mediafile.save()

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().genre, u'')

    def test_apply_from_scratch_keeps_format(self):
        config['import']['from_scratch'] = True

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().format, u'MP3')

    def test_apply_from_scratch_keeps_bitrate(self):
        config['import']['from_scratch'] = True
        bitrate = 80000

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().bitrate, bitrate)

    def test_apply_with_move_deletes_import(self):
        config['import']['move'] = True

        import_file = os.path.join(
            self.import_dir, b'the_album', b'track_1.mp3')
        self.assertExists(import_file)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertNotExists(import_file)

    def test_apply_with_delete_deletes_import(self):
        config['import']['delete'] = True

        import_file = os.path.join(self.import_dir,
                                   b'the_album', b'track_1.mp3')
        self.assertExists(import_file)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertNotExists(import_file)

    def test_skip_does_not_add_track(self):
        self.importer.add_choice(importer.action.SKIP)
        self.importer.run()
        self.assertEqual(self.lib.items().get(), None)

    def test_skip_non_album_dirs(self):
        self.assertIsDir(os.path.join(self.import_dir, b'the_album'))
        self.touch(b'cruft', dir=self.import_dir)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(len(self.lib.albums()), 1)

    def test_unmatched_tracks_not_added(self):
        self._create_import_dir(2)
        self.matcher.matching = self.matcher.MISSING
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(len(self.lib.items()), 1)

    def test_empty_directory_warning(self):
        import_dir = os.path.join(self.temp_dir, b'empty')
        self.touch(b'non-audio', dir=import_dir)
        self._setup_import_session(import_dir=import_dir)
        with capture_log() as logs:
            self.importer.run()

        import_dir = displayable_path(import_dir)
        self.assertIn(u'No files imported from {0}'.format(import_dir), logs)

    def test_empty_directory_singleton_warning(self):
        import_dir = os.path.join(self.temp_dir, b'empty')
        self.touch(b'non-audio', dir=import_dir)
        self._setup_import_session(import_dir=import_dir, singletons=True)
        with capture_log() as logs:
            self.importer.run()

        import_dir = displayable_path(import_dir)
        self.assertIn(u'No files imported from {0}'.format(import_dir), logs)

    def test_asis_no_data_source(self):
        self.assertEqual(self.lib.items().get(), None)

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()

        with self.assertRaises(AttributeError):
            self.lib.items().get().data_source

    def test_set_fields(self):
        genre = u"\U0001F3B7 Jazz"
        collection = u"To Listen"

        config['import']['set_fields'] = {
            u'collection': collection,
            u'genre': genre
        }

        # As-is album import.
        self.assertEqual(self.lib.albums().get(), None)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()

        for album in self.lib.albums():
            album.load()  # TODO: Not sure this is necessary.
            self.assertEqual(album.genre, genre)
            self.assertEqual(album.collection, collection)
            # Remove album from library to test again with APPLY choice.
            album.remove()

        # Autotagged.
        self.assertEqual(self.lib.albums().get(), None)
        self.importer.clear_choices()
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()

        for album in self.lib.albums():
            album.load()
            self.assertEqual(album.genre, genre)
            self.assertEqual(album.collection, collection)


class ImportTracksTest(_common.TestCase, ImportHelper):
    """Test TRACKS and APPLY choice.
    """
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)
        self._setup_import_session()
        self.matcher = AutotagStub().install()

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_apply_tracks_adds_singleton_track(self):
        self.assertEqual(self.lib.items().get(), None)
        self.assertEqual(self.lib.albums().get(), None)

        self.importer.add_choice(importer.action.TRACKS)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'Applied Title 1')
        self.assertEqual(self.lib.albums().get(), None)

    def test_apply_tracks_adds_singleton_path(self):
        self.assert_lib_dir_empty()

        self.importer.add_choice(importer.action.TRACKS)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assert_file_in_lib(b'singletons', b'Applied Title 1.mp3')


class ImportCompilationTest(_common.TestCase, ImportHelper):
    """Test ASIS import of a folder containing tracks with different artists.
    """
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(3)
        self._setup_import_session()
        self.matcher = AutotagStub().install()

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_asis_homogenous_sets_albumartist(self):
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().albumartist, u'Tag Artist')
        for item in self.lib.items():
            self.assertEqual(item.albumartist, u'Tag Artist')

    def test_asis_heterogenous_sets_various_albumartist(self):
        self.import_media[0].artist = u'Other Artist'
        self.import_media[0].save()
        self.import_media[1].artist = u'Another Artist'
        self.import_media[1].save()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().albumartist,
                         u'Various Artists')
        for item in self.lib.items():
            self.assertEqual(item.albumartist, u'Various Artists')

    def test_asis_heterogenous_sets_sompilation(self):
        self.import_media[0].artist = u'Other Artist'
        self.import_media[0].save()
        self.import_media[1].artist = u'Another Artist'
        self.import_media[1].save()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        for item in self.lib.items():
            self.assertTrue(item.comp)

    def test_asis_sets_majority_albumartist(self):
        self.import_media[0].artist = u'Other Artist'
        self.import_media[0].save()
        self.import_media[1].artist = u'Other Artist'
        self.import_media[1].save()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().albumartist, u'Other Artist')
        for item in self.lib.items():
            self.assertEqual(item.albumartist, u'Other Artist')

    def test_asis_albumartist_tag_sets_albumartist(self):
        self.import_media[0].artist = u'Other Artist'
        self.import_media[1].artist = u'Another Artist'
        for mediafile in self.import_media:
            mediafile.albumartist = u'Album Artist'
            mediafile.mb_albumartistid = u'Album Artist ID'
            mediafile.save()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().albumartist, u'Album Artist')
        self.assertEqual(self.lib.albums().get().mb_albumartistid,
                         u'Album Artist ID')
        for item in self.lib.items():
            self.assertEqual(item.albumartist, u'Album Artist')
            self.assertEqual(item.mb_albumartistid, u'Album Artist ID')


class ImportExistingTest(_common.TestCase, ImportHelper):
    """Test importing files that are already in the library directory.
    """
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)
        self.matcher = AutotagStub().install()

        self._setup_import_session()
        self.setup_importer = self.importer
        self.setup_importer.default_choice = importer.action.APPLY

        self._setup_import_session(import_dir=self.libdir)

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_does_not_duplicate_item(self):
        self.setup_importer.run()
        self.assertEqual(len((self.lib.items())), 1)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(len((self.lib.items())), 1)

    def test_does_not_duplicate_album(self):
        self.setup_importer.run()
        self.assertEqual(len((self.lib.albums())), 1)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(len((self.lib.albums())), 1)

    def test_does_not_duplicate_singleton_track(self):
        self.setup_importer.add_choice(importer.action.TRACKS)
        self.setup_importer.add_choice(importer.action.APPLY)
        self.setup_importer.run()
        self.assertEqual(len((self.lib.items())), 1)

        self.importer.add_choice(importer.action.TRACKS)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(len((self.lib.items())), 1)

    def test_asis_updates_metadata(self):
        self.setup_importer.run()
        medium = MediaFile(self.lib.items().get().path)
        medium.title = u'New Title'
        medium.save()

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, u'New Title')

    def test_asis_updated_moves_file(self):
        self.setup_importer.run()
        medium = MediaFile(self.lib.items().get().path)
        medium.title = u'New Title'
        medium.save()

        old_path = os.path.join(b'Applied Artist', b'Applied Album',
                                b'Applied Title 1.mp3')
        self.assert_file_in_lib(old_path)

        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assert_file_in_lib(b'Applied Artist', b'Applied Album',
                                b'New Title.mp3')
        self.assert_file_not_in_lib(old_path)

    def test_asis_updated_without_copy_does_not_move_file(self):
        self.setup_importer.run()
        medium = MediaFile(self.lib.items().get().path)
        medium.title = u'New Title'
        medium.save()

        old_path = os.path.join(b'Applied Artist', b'Applied Album',
                                b'Applied Title 1.mp3')
        self.assert_file_in_lib(old_path)

        config['import']['copy'] = False
        self.importer.add_choice(importer.action.ASIS)
        self.importer.run()
        self.assert_file_not_in_lib(b'Applied Artist', b'Applied Album',
                                    b'New Title.mp3')
        self.assert_file_in_lib(old_path)

    def test_outside_file_is_copied(self):
        config['import']['copy'] = False
        self.setup_importer.run()
        self.assert_equal_path(self.lib.items().get().path,
                               self.import_media[0].path)

        config['import']['copy'] = True
        self._setup_import_session()
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        new_path = os.path.join(b'Applied Artist', b'Applied Album',
                                b'Applied Title 1.mp3')

        self.assert_file_in_lib(new_path)
        self.assert_equal_path(self.lib.items().get().path,
                               os.path.join(self.libdir, new_path))

    def test_outside_file_is_moved(self):
        config['import']['copy'] = False
        self.setup_importer.run()
        self.assert_equal_path(self.lib.items().get().path,
                               self.import_media[0].path)

        self._setup_import_session(move=True)
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertNotExists(self.import_media[0].path)


class GroupAlbumsImportTest(_common.TestCase, ImportHelper):
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(3)
        self.matcher = AutotagStub().install()
        self.matcher.matching = AutotagStub.NONE
        self._setup_import_session()

        # Split tracks into two albums and use both as-is
        self.importer.add_choice(importer.action.ALBUMS)
        self.importer.add_choice(importer.action.ASIS)
        self.importer.add_choice(importer.action.ASIS)

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_add_album_for_different_artist_and_different_album(self):
        self.import_media[0].artist = u"Artist B"
        self.import_media[0].album = u"Album B"
        self.import_media[0].save()

        self.importer.run()
        albums = set([album.album for album in self.lib.albums()])
        self.assertEqual(albums, set(['Album B', 'Tag Album']))

    def test_add_album_for_different_artist_and_same_albumartist(self):
        self.import_media[0].artist = u"Artist B"
        self.import_media[0].albumartist = u"Album Artist"
        self.import_media[0].save()
        self.import_media[1].artist = u"Artist C"
        self.import_media[1].albumartist = u"Album Artist"
        self.import_media[1].save()

        self.importer.run()
        artists = set([album.albumartist for album in self.lib.albums()])
        self.assertEqual(artists, set(['Album Artist', 'Tag Artist']))

    def test_add_album_for_same_artist_and_different_album(self):
        self.import_media[0].album = u"Album B"
        self.import_media[0].save()

        self.importer.run()
        albums = set([album.album for album in self.lib.albums()])
        self.assertEqual(albums, set(['Album B', 'Tag Album']))

    def test_add_album_for_same_album_and_different_artist(self):
        self.import_media[0].artist = u"Artist B"
        self.import_media[0].save()

        self.importer.run()
        artists = set([album.albumartist for album in self.lib.albums()])
        self.assertEqual(artists, set(['Artist B', 'Tag Artist']))

    def test_incremental(self):
        config['import']['incremental'] = True
        self.import_media[0].album = u"Album B"
        self.import_media[0].save()

        self.importer.run()
        albums = set([album.album for album in self.lib.albums()])
        self.assertEqual(albums, set(['Album B', 'Tag Album']))


class GlobalGroupAlbumsImportTest(GroupAlbumsImportTest):

    def setUp(self):
        super(GlobalGroupAlbumsImportTest, self).setUp()
        self.importer.clear_choices()
        self.importer.default_choice = importer.action.ASIS
        config['import']['group_albums'] = True


class ChooseCandidateTest(_common.TestCase, ImportHelper):
    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)
        self._setup_import_session()
        self.matcher = AutotagStub().install()
        self.matcher.matching = AutotagStub.BAD

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def test_choose_first_candidate(self):
        self.importer.add_choice(1)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, u'Applied Album M')

    def test_choose_second_candidate(self):
        self.importer.add_choice(2)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, u'Applied Album MM')


class InferAlbumDataTest(_common.TestCase):
    def setUp(self):
        super(InferAlbumDataTest, self).setUp()

        i1 = _common.item()
        i2 = _common.item()
        i3 = _common.item()
        i1.title = u'first item'
        i2.title = u'second item'
        i3.title = u'third item'
        i1.comp = i2.comp = i3.comp = False
        i1.albumartist = i2.albumartist = i3.albumartist = ''
        i1.mb_albumartistid = i2.mb_albumartistid = i3.mb_albumartistid = ''
        self.items = [i1, i2, i3]

        self.task = importer.ImportTask(paths=['a path'], toppath='top path',
                                        items=self.items)

    def test_asis_homogenous_single_artist(self):
        self.task.set_choice(importer.action.ASIS)
        self.task.align_album_level_fields()
        self.assertFalse(self.items[0].comp)
        self.assertEqual(self.items[0].albumartist, self.items[2].artist)

    def test_asis_heterogenous_va(self):
        self.items[0].artist = u'another artist'
        self.items[1].artist = u'some other artist'
        self.task.set_choice(importer.action.ASIS)

        self.task.align_album_level_fields()

        self.assertTrue(self.items[0].comp)
        self.assertEqual(self.items[0].albumartist, u'Various Artists')

    def test_asis_comp_applied_to_all_items(self):
        self.items[0].artist = u'another artist'
        self.items[1].artist = u'some other artist'
        self.task.set_choice(importer.action.ASIS)

        self.task.align_album_level_fields()

        for item in self.items:
            self.assertTrue(item.comp)
            self.assertEqual(item.albumartist, u'Various Artists')

    def test_asis_majority_artist_single_artist(self):
        self.items[0].artist = u'another artist'
        self.task.set_choice(importer.action.ASIS)

        self.task.align_album_level_fields()

        self.assertFalse(self.items[0].comp)
        self.assertEqual(self.items[0].albumartist, self.items[2].artist)

    def test_asis_track_albumartist_override(self):
        self.items[0].artist = u'another artist'
        self.items[1].artist = u'some other artist'
        for item in self.items:
            item.albumartist = u'some album artist'
            item.mb_albumartistid = u'some album artist id'
        self.task.set_choice(importer.action.ASIS)

        self.task.align_album_level_fields()

        self.assertEqual(self.items[0].albumartist,
                         u'some album artist')
        self.assertEqual(self.items[0].mb_albumartistid,
                         u'some album artist id')

    def test_apply_gets_artist_and_id(self):
        self.task.set_choice(AlbumMatch(0, None, {}, set(), set()))  # APPLY

        self.task.align_album_level_fields()

        self.assertEqual(self.items[0].albumartist, self.items[0].artist)
        self.assertEqual(self.items[0].mb_albumartistid,
                         self.items[0].mb_artistid)

    def test_apply_lets_album_values_override(self):
        for item in self.items:
            item.albumartist = u'some album artist'
            item.mb_albumartistid = u'some album artist id'
        self.task.set_choice(AlbumMatch(0, None, {}, set(), set()))  # APPLY

        self.task.align_album_level_fields()

        self.assertEqual(self.items[0].albumartist,
                         u'some album artist')
        self.assertEqual(self.items[0].mb_albumartistid,
                         u'some album artist id')

    def test_small_single_artist_album(self):
        self.items = [self.items[0]]
        self.task.items = self.items
        self.task.set_choice(importer.action.ASIS)
        self.task.align_album_level_fields()
        self.assertFalse(self.items[0].comp)


def test_album_info(*args, **kwargs):
    """Create an AlbumInfo object for testing.
    """
    track_info = TrackInfo(
        title=u'new title',
        track_id=u'trackid',
        index=0,
    )
    album_info = AlbumInfo(
        artist=u'artist',
        album=u'album',
        tracks=[track_info],
        album_id=u'albumid',
        artist_id=u'artistid',
    )
    return iter([album_info])


@patch('beets.autotag.mb.match_album', Mock(side_effect=test_album_info))
class ImportDuplicateAlbumTest(unittest.TestCase, TestHelper,
                               _common.Assertions):

    def setUp(self):
        self.setup_beets()

        # Original album
        self.add_album_fixture(albumartist=u'artist', album=u'album')

        # Create import session
        self.importer = self.create_importer()
        config['import']['autotag'] = True

    def tearDown(self):
        self.teardown_beets()

    def test_remove_duplicate_album(self):
        item = self.lib.items().get()
        self.assertEqual(item.title, u't\xeftle 0')
        self.assertExists(item.path)

        self.importer.default_resolution = self.importer.Resolution.REMOVE
        self.importer.run()

        self.assertNotExists(item.path)
        self.assertEqual(len(self.lib.albums()), 1)
        self.assertEqual(len(self.lib.items()), 1)
        item = self.lib.items().get()
        self.assertEqual(item.title, u'new title')

    def test_no_autotag_keeps_duplicate_album(self):
        config['import']['autotag'] = False
        item = self.lib.items().get()
        self.assertEqual(item.title, u't\xeftle 0')
        self.assertExists(item.path)

        # Imported item has the same artist and album as the one in the
        # library.
        import_file = os.path.join(self.importer.paths[0],
                                   b'album 0', b'track 0.mp3')
        import_file = MediaFile(import_file)
        import_file.artist = item['artist']
        import_file.albumartist = item['artist']
        import_file.album = item['album']
        import_file.title = 'new title'

        self.importer.default_resolution = self.importer.Resolution.REMOVE
        self.importer.run()

        self.assertExists(item.path)
        self.assertEqual(len(self.lib.albums()), 2)
        self.assertEqual(len(self.lib.items()), 2)

    def test_keep_duplicate_album(self):
        self.importer.default_resolution = self.importer.Resolution.KEEPBOTH
        self.importer.run()

        self.assertEqual(len(self.lib.albums()), 2)
        self.assertEqual(len(self.lib.items()), 2)

    def test_skip_duplicate_album(self):
        item = self.lib.items().get()
        self.assertEqual(item.title, u't\xeftle 0')

        self.importer.default_resolution = self.importer.Resolution.SKIP
        self.importer.run()

        self.assertEqual(len(self.lib.albums()), 1)
        self.assertEqual(len(self.lib.items()), 1)
        item = self.lib.items().get()
        self.assertEqual(item.title, u't\xeftle 0')

    def test_merge_duplicate_album(self):
        self.importer.default_resolution = self.importer.Resolution.MERGE
        self.importer.run()

        self.assertEqual(len(self.lib.albums()), 1)

    def test_twice_in_import_dir(self):
        self.skipTest('write me')

    def add_album_fixture(self, **kwargs):
        # TODO move this into upstream
        album = super(ImportDuplicateAlbumTest, self).add_album_fixture()
        album.update(kwargs)
        album.store()
        return album


def test_track_info(*args, **kwargs):
    return iter([TrackInfo(
        artist=u'artist', title=u'title',
        track_id=u'new trackid', index=0,)])


@patch('beets.autotag.mb.match_track', Mock(side_effect=test_track_info))
class ImportDuplicateSingletonTest(unittest.TestCase, TestHelper,
                                   _common.Assertions):

    def setUp(self):
        self.setup_beets()

        # Original file in library
        self.add_item_fixture(artist=u'artist', title=u'title',
                              mb_trackid='old trackid')

        # Import session
        self.importer = self.create_importer()
        config['import']['autotag'] = True
        config['import']['singletons'] = True

    def tearDown(self):
        self.teardown_beets()

    def test_remove_duplicate(self):
        item = self.lib.items().get()
        self.assertEqual(item.mb_trackid, u'old trackid')
        self.assertExists(item.path)

        self.importer.default_resolution = self.importer.Resolution.REMOVE
        self.importer.run()

        self.assertNotExists(item.path)
        self.assertEqual(len(self.lib.items()), 1)
        item = self.lib.items().get()
        self.assertEqual(item.mb_trackid, u'new trackid')

    def test_keep_duplicate(self):
        self.assertEqual(len(self.lib.items()), 1)

        self.importer.default_resolution = self.importer.Resolution.KEEPBOTH
        self.importer.run()

        self.assertEqual(len(self.lib.items()), 2)

    def test_skip_duplicate(self):
        item = self.lib.items().get()
        self.assertEqual(item.mb_trackid, u'old trackid')

        self.importer.default_resolution = self.importer.Resolution.SKIP
        self.importer.run()

        self.assertEqual(len(self.lib.items()), 1)
        item = self.lib.items().get()
        self.assertEqual(item.mb_trackid, u'old trackid')

    def test_twice_in_import_dir(self):
        self.skipTest('write me')

    def add_item_fixture(self, **kwargs):
        # Move this to TestHelper
        item = self.add_item_fixtures()[0]
        item.update(kwargs)
        item.store()
        return item


class TagLogTest(_common.TestCase):
    def test_tag_log_line(self):
        sio = StringIO()
        handler = logging.StreamHandler(sio)
        session = _common.import_session(loghandler=handler)
        session.tag_log('status', 'path')
        self.assertIn('status path', sio.getvalue())

    def test_tag_log_unicode(self):
        sio = StringIO()
        handler = logging.StreamHandler(sio)
        session = _common.import_session(loghandler=handler)
        session.tag_log('status', u'caf\xe9')  # send unicode
        self.assertIn(u'status caf\xe9', sio.getvalue())


class ResumeImportTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    @patch('beets.plugins.send')
    def test_resume_album(self, plugins_send):
        self.importer = self.create_importer(album_count=2)
        self.config['import']['resume'] = True

        # Aborts import after one album. This also ensures that we skip
        # the first album in the second try.
        def raise_exception(event, **kwargs):
            if event == 'album_imported':
                raise importer.ImportAbort
        plugins_send.side_effect = raise_exception

        self.importer.run()
        self.assertEqual(len(self.lib.albums()), 1)
        self.assertIsNotNone(self.lib.albums(u'album:album 0').get())

        self.importer.run()
        self.assertEqual(len(self.lib.albums()), 2)
        self.assertIsNotNone(self.lib.albums(u'album:album 1').get())

    @patch('beets.plugins.send')
    def test_resume_singleton(self, plugins_send):
        self.importer = self.create_importer(item_count=2)
        self.config['import']['resume'] = True
        self.config['import']['singletons'] = True

        # Aborts import after one track. This also ensures that we skip
        # the first album in the second try.
        def raise_exception(event, **kwargs):
            if event == 'item_imported':
                raise importer.ImportAbort
        plugins_send.side_effect = raise_exception

        self.importer.run()
        self.assertEqual(len(self.lib.items()), 1)
        self.assertIsNotNone(self.lib.items(u'title:track 0').get())

        self.importer.run()
        self.assertEqual(len(self.lib.items()), 2)
        self.assertIsNotNone(self.lib.items(u'title:track 1').get())


class IncrementalImportTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.setup_beets()
        self.config['import']['incremental'] = True

    def tearDown(self):
        self.teardown_beets()

    def test_incremental_album(self):
        importer = self.create_importer(album_count=1)
        importer.run()

        # Change album name so the original file would be imported again
        # if incremental was off.
        album = self.lib.albums().get()
        album['album'] = 'edited album'
        album.store()

        importer = self.create_importer(album_count=1)
        importer.run()
        self.assertEqual(len(self.lib.albums()), 2)

    def test_incremental_item(self):
        self.config['import']['singletons'] = True
        importer = self.create_importer(item_count=1)
        importer.run()

        # Change track name so the original file would be imported again
        # if incremental was off.
        item = self.lib.items().get()
        item['artist'] = 'edited artist'
        item.store()

        importer = self.create_importer(item_count=1)
        importer.run()
        self.assertEqual(len(self.lib.items()), 2)

    def test_invalid_state_file(self):
        importer = self.create_importer()
        with open(self.config['statefile'].as_filename(), 'wb') as f:
            f.write(b'000')
        importer.run()
        self.assertEqual(len(self.lib.albums()), 1)


def _mkmp3(path):
    shutil.copyfile(
        syspath(os.path.join(_common.RSRC, b'min.mp3')),
        syspath(path),
    )


class AlbumsInDirTest(_common.TestCase):
    def setUp(self):
        super(AlbumsInDirTest, self).setUp()

        # create a directory structure for testing
        self.base = os.path.abspath(os.path.join(self.temp_dir, b'tempdir'))
        os.mkdir(syspath(self.base))

        os.mkdir(syspath(os.path.join(self.base, b'album1')))
        os.mkdir(syspath(os.path.join(self.base, b'album2')))
        os.mkdir(syspath(os.path.join(self.base, b'more')))
        os.mkdir(syspath(os.path.join(self.base, b'more', b'album3')))
        os.mkdir(syspath(os.path.join(self.base, b'more', b'album4')))

        _mkmp3(os.path.join(self.base, b'album1', b'album1song1.mp3'))
        _mkmp3(os.path.join(self.base, b'album1', b'album1song2.mp3'))
        _mkmp3(os.path.join(self.base, b'album2', b'album2song.mp3'))
        _mkmp3(os.path.join(self.base, b'more', b'album3', b'album3song.mp3'))
        _mkmp3(os.path.join(self.base, b'more', b'album4', b'album4song.mp3'))

    def test_finds_all_albums(self):
        albums = list(albums_in_dir(self.base))
        self.assertEqual(len(albums), 4)

    def test_separates_contents(self):
        found = []
        for _, album in albums_in_dir(self.base):
            found.append(re.search(br'album(.)song', album[0]).group(1))
        self.assertTrue(b'1' in found)
        self.assertTrue(b'2' in found)
        self.assertTrue(b'3' in found)
        self.assertTrue(b'4' in found)

    def test_finds_multiple_songs(self):
        for _, album in albums_in_dir(self.base):
            n = re.search(br'album(.)song', album[0]).group(1)
            if n == b'1':
                self.assertEqual(len(album), 2)
            else:
                self.assertEqual(len(album), 1)


class MultiDiscAlbumsInDirTest(_common.TestCase):
    def create_music(self, files=True, ascii=True):
        """Create some music in multiple album directories.

        `files` indicates whether to create the files (otherwise, only
        directories are made). `ascii` indicates ACII-only filenames;
        otherwise, we use Unicode names.
        """
        self.base = os.path.abspath(os.path.join(self.temp_dir, b'tempdir'))
        os.mkdir(syspath(self.base))

        name = b'CAT' if ascii else util.bytestring_path(u'C\xc1T')
        name_alt_case = b'CAt' if ascii else util.bytestring_path(u'C\xc1t')

        self.dirs = [
            # Nested album, multiple subdirs.
            # Also, false positive marker in root dir, and subtitle for disc 3.
            os.path.join(self.base, b'ABCD1234'),
            os.path.join(self.base, b'ABCD1234', b'cd 1'),
            os.path.join(self.base, b'ABCD1234', b'cd 3 - bonus'),

            # Nested album, single subdir.
            # Also, punctuation between marker and disc number.
            os.path.join(self.base, b'album'),
            os.path.join(self.base, b'album', b'cd _ 1'),

            # Flattened album, case typo.
            # Also, false positive marker in parent dir.
            os.path.join(self.base, b'artist [CD5]'),
            os.path.join(self.base, b'artist [CD5]', name + b' disc 1'),
            os.path.join(self.base, b'artist [CD5]',
                         name_alt_case + b' disc 2'),

            # Single disc album, sorted between CAT discs.
            os.path.join(self.base, b'artist [CD5]', name + b'S'),
        ]
        self.files = [
            os.path.join(self.base, b'ABCD1234', b'cd 1', b'song1.mp3'),
            os.path.join(self.base, b'ABCD1234',
                         b'cd 3 - bonus', b'song2.mp3'),
            os.path.join(self.base, b'ABCD1234',
                         b'cd 3 - bonus', b'song3.mp3'),
            os.path.join(self.base, b'album', b'cd _ 1', b'song4.mp3'),
            os.path.join(self.base, b'artist [CD5]', name + b' disc 1',
                         b'song5.mp3'),
            os.path.join(self.base, b'artist [CD5]',
                         name_alt_case + b' disc 2', b'song6.mp3'),
            os.path.join(self.base, b'artist [CD5]', name + b'S',
                         b'song7.mp3'),
        ]

        if not ascii:
            self.dirs = [self._normalize_path(p) for p in self.dirs]
            self.files = [self._normalize_path(p) for p in self.files]

        for path in self.dirs:
            os.mkdir(syspath(path))
        if files:
            for path in self.files:
                _mkmp3(util.syspath(path))

    def _normalize_path(self, path):
        """Normalize a path's Unicode combining form according to the
        platform.
        """
        path = path.decode('utf-8')
        norm_form = 'NFD' if sys.platform == 'darwin' else 'NFC'
        path = unicodedata.normalize(norm_form, path)
        return path.encode('utf-8')

    def test_coalesce_nested_album_multiple_subdirs(self):
        self.create_music()
        albums = list(albums_in_dir(self.base))
        self.assertEqual(len(albums), 4)
        root, items = albums[0]
        self.assertEqual(root, self.dirs[0:3])
        self.assertEqual(len(items), 3)

    def test_coalesce_nested_album_single_subdir(self):
        self.create_music()
        albums = list(albums_in_dir(self.base))
        root, items = albums[1]
        self.assertEqual(root, self.dirs[3:5])
        self.assertEqual(len(items), 1)

    def test_coalesce_flattened_album_case_typo(self):
        self.create_music()
        albums = list(albums_in_dir(self.base))
        root, items = albums[2]
        self.assertEqual(root, self.dirs[6:8])
        self.assertEqual(len(items), 2)

    def test_single_disc_album(self):
        self.create_music()
        albums = list(albums_in_dir(self.base))
        root, items = albums[3]
        self.assertEqual(root, self.dirs[8:])
        self.assertEqual(len(items), 1)

    def test_do_not_yield_empty_album(self):
        self.create_music(files=False)
        albums = list(albums_in_dir(self.base))
        self.assertEqual(len(albums), 0)

    def test_single_disc_unicode(self):
        self.create_music(ascii=False)
        albums = list(albums_in_dir(self.base))
        root, items = albums[3]
        self.assertEqual(root, self.dirs[8:])
        self.assertEqual(len(items), 1)

    def test_coalesce_multiple_unicode(self):
        self.create_music(ascii=False)
        albums = list(albums_in_dir(self.base))
        self.assertEqual(len(albums), 4)
        root, items = albums[0]
        self.assertEqual(root, self.dirs[0:3])
        self.assertEqual(len(items), 3)


class ReimportTest(unittest.TestCase, ImportHelper, _common.Assertions):
    """Test "re-imports", in which the autotagging machinery is used for
    music that's already in the library.

    This works by importing new database entries for the same files and
    replacing the old data with the new data. We also copy over flexible
    attributes and the added date.
    """

    def setUp(self):
        self.setup_beets()

        # The existing album.
        album = self.add_album_fixture()
        album.added = 4242.0
        album.foo = u'bar'  # Some flexible attribute.
        album.store()
        item = album.items().get()
        item.baz = u'qux'
        item.added = 4747.0
        item.store()

        # Set up an import pipeline with a "good" match.
        self.matcher = AutotagStub().install()
        self.matcher.matching = AutotagStub.GOOD

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def _setup_session(self, singletons=False):
        self._setup_import_session(self._album().path, singletons=singletons)
        self.importer.add_choice(importer.action.APPLY)

    def _album(self):
        return self.lib.albums().get()

    def _item(self):
        return self.lib.items().get()

    def test_reimported_album_gets_new_metadata(self):
        self._setup_session()
        self.assertEqual(self._album().album, u'\xe4lbum')
        self.importer.run()
        self.assertEqual(self._album().album, u'the album')

    def test_reimported_album_preserves_flexattr(self):
        self._setup_session()
        self.importer.run()
        self.assertEqual(self._album().foo, u'bar')

    def test_reimported_album_preserves_added(self):
        self._setup_session()
        self.importer.run()
        self.assertEqual(self._album().added, 4242.0)

    def test_reimported_album_preserves_item_flexattr(self):
        self._setup_session()
        self.importer.run()
        self.assertEqual(self._item().baz, u'qux')

    def test_reimported_album_preserves_item_added(self):
        self._setup_session()
        self.importer.run()
        self.assertEqual(self._item().added, 4747.0)

    def test_reimported_item_gets_new_metadata(self):
        self._setup_session(True)
        self.assertEqual(self._item().title, u't\xeftle 0')
        self.importer.run()
        self.assertEqual(self._item().title, u'full')

    def test_reimported_item_preserves_flexattr(self):
        self._setup_session(True)
        self.importer.run()
        self.assertEqual(self._item().baz, u'qux')

    def test_reimported_item_preserves_added(self):
        self._setup_session(True)
        self.importer.run()
        self.assertEqual(self._item().added, 4747.0)

    def test_reimported_item_preserves_art(self):
        self._setup_session()
        art_source = os.path.join(_common.RSRC, b'abbey.jpg')
        replaced_album = self._album()
        replaced_album.set_art(art_source)
        replaced_album.store()
        old_artpath = replaced_album.artpath
        self.importer.run()
        new_album = self._album()
        new_artpath = new_album.art_destination(art_source)
        self.assertEqual(new_album.artpath, new_artpath)
        self.assertExists(new_artpath)
        if new_artpath != old_artpath:
            self.assertNotExists(old_artpath)


class ImportPretendTest(_common.TestCase, ImportHelper):
    """ Test the pretend commandline option
    """

    def __init__(self, method_name='runTest'):
        super(ImportPretendTest, self).__init__(method_name)
        self.matcher = None

    def setUp(self):
        super(ImportPretendTest, self).setUp()
        self.setup_beets()
        self.__create_import_dir()
        self.__create_empty_import_dir()
        self._setup_import_session()
        config['import']['pretend'] = True
        self.matcher = AutotagStub().install()
        self.io.install()

    def tearDown(self):
        self.teardown_beets()
        self.matcher.restore()

    def __create_import_dir(self):
        self._create_import_dir(1)
        resource_path = os.path.join(_common.RSRC, b'empty.mp3')
        single_path = os.path.join(self.import_dir, b'track_2.mp3')
        shutil.copy(syspath(resource_path), syspath(single_path))
        self.import_paths = [
            os.path.join(self.import_dir, b'the_album'),
            single_path
        ]
        self.import_files = [
            displayable_path(
                os.path.join(self.import_paths[0], b'track_1.mp3')),
            displayable_path(single_path)
        ]

    def __create_empty_import_dir(self):
        path = os.path.join(self.temp_dir, b'empty')
        os.makedirs(syspath(path))
        self.empty_path = path

    def __run(self, import_paths, singletons=True):
        self._setup_import_session(singletons=singletons)
        self.importer.paths = import_paths

        with capture_log() as logs:
            self.importer.run()

        logs = [line for line in logs if not line.startswith('Sending event:')]

        self.assertEqual(len(self.lib.items()), 0)
        self.assertEqual(len(self.lib.albums()), 0)

        return logs

    def test_import_singletons_pretend(self):
        logs = self.__run(self.import_paths)

        self.assertEqual(logs, [
            'Singleton: %s' % displayable_path(self.import_files[0]),
            'Singleton: %s' % displayable_path(self.import_paths[1])])

    def test_import_album_pretend(self):
        logs = self.__run(self.import_paths, singletons=False)

        self.assertEqual(logs, [
            'Album: %s' % displayable_path(self.import_paths[0]),
            '  %s' % displayable_path(self.import_files[0]),
            'Album: %s' % displayable_path(self.import_paths[1]),
            '  %s' % displayable_path(self.import_paths[1])])

    def test_import_pretend_empty(self):
        logs = self.__run([self.empty_path])

        self.assertEqual(logs, [u'No files imported from {0}'
                         .format(displayable_path(self.empty_path))])

# Helpers for ImportMusicBrainzIdTest.


def mocked_get_release_by_id(id_, includes=[], release_status=[],
                             release_type=[]):
    """Mimic musicbrainzngs.get_release_by_id, accepting only a restricted list
    of MB ids (ID_RELEASE_0, ID_RELEASE_1). The returned dict differs only in
    the release title and artist name, so that ID_RELEASE_0 is a closer match
    to the items created by ImportHelper._create_import_dir()."""
    # Map IDs to (release title, artist), so the distances are different.
    releases = {ImportMusicBrainzIdTest.ID_RELEASE_0: ('VALID_RELEASE_0',
                                                       'TAG ARTIST'),
                ImportMusicBrainzIdTest.ID_RELEASE_1: ('VALID_RELEASE_1',
                                                       'DISTANT_MATCH')}

    return {
        'release': {
            'title': releases[id_][0],
            'id': id_,
            'medium-list': [{
                'track-list': [{
                    'id': 'baz',
                    'recording': {
                        'title': 'foo',
                        'id': 'bar',
                        'length': 59,
                    },
                    'position': 9,
                    'number': 'A2'
                }],
                'position': 5,
            }],
            'artist-credit': [{
                'artist': {
                    'name': releases[id_][1],
                    'id': 'some-id',
                },
            }],
            'release-group': {
                'id': 'another-id',
            }
        }
    }


def mocked_get_recording_by_id(id_, includes=[], release_status=[],
                               release_type=[]):
    """Mimic musicbrainzngs.get_recording_by_id, accepting only a restricted
    list of MB ids (ID_RECORDING_0, ID_RECORDING_1). The returned dict differs
    only in the recording title and artist name, so that ID_RECORDING_0 is a
    closer match to the items created by ImportHelper._create_import_dir()."""
    # Map IDs to (recording title, artist), so the distances are different.
    releases = {ImportMusicBrainzIdTest.ID_RECORDING_0: ('VALID_RECORDING_0',
                                                         'TAG ARTIST'),
                ImportMusicBrainzIdTest.ID_RECORDING_1: ('VALID_RECORDING_1',
                                                         'DISTANT_MATCH')}

    return {
        'recording': {
            'title': releases[id_][0],
            'id': id_,
            'length': 59,
            'artist-credit': [{
                'artist': {
                    'name': releases[id_][1],
                    'id': 'some-id',
                },
            }],
        }
    }


@patch('musicbrainzngs.get_recording_by_id',
       Mock(side_effect=mocked_get_recording_by_id))
@patch('musicbrainzngs.get_release_by_id',
       Mock(side_effect=mocked_get_release_by_id))
class ImportMusicBrainzIdTest(_common.TestCase, ImportHelper):
    """Test the --musicbrainzid argument."""

    MB_RELEASE_PREFIX = 'https://musicbrainz.org/release/'
    MB_RECORDING_PREFIX = 'https://musicbrainz.org/recording/'
    ID_RELEASE_0 = '00000000-0000-0000-0000-000000000000'
    ID_RELEASE_1 = '11111111-1111-1111-1111-111111111111'
    ID_RECORDING_0 = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    ID_RECORDING_1 = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

    def setUp(self):
        self.setup_beets()
        self._create_import_dir(1)

    def tearDown(self):
        self.teardown_beets()

    def test_one_mbid_one_album(self):
        self.config['import']['search_ids'] = \
            [self.MB_RELEASE_PREFIX + self.ID_RELEASE_0]
        self._setup_import_session()

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, 'VALID_RELEASE_0')

    def test_several_mbid_one_album(self):
        self.config['import']['search_ids'] = \
            [self.MB_RELEASE_PREFIX + self.ID_RELEASE_0,
             self.MB_RELEASE_PREFIX + self.ID_RELEASE_1]
        self._setup_import_session()

        self.importer.add_choice(2)  # Pick the 2nd best match (release 1).
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.albums().get().album, 'VALID_RELEASE_1')

    def test_one_mbid_one_singleton(self):
        self.config['import']['search_ids'] = \
            [self.MB_RECORDING_PREFIX + self.ID_RECORDING_0]
        self._setup_import_session(singletons=True)

        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, 'VALID_RECORDING_0')

    def test_several_mbid_one_singleton(self):
        self.config['import']['search_ids'] = \
            [self.MB_RECORDING_PREFIX + self.ID_RECORDING_0,
             self.MB_RECORDING_PREFIX + self.ID_RECORDING_1]
        self._setup_import_session(singletons=True)

        self.importer.add_choice(2)  # Pick the 2nd best match (recording 1).
        self.importer.add_choice(importer.action.APPLY)
        self.importer.run()
        self.assertEqual(self.lib.items().get().title, 'VALID_RECORDING_1')

    def test_candidates_album(self):
        """Test directly ImportTask.lookup_candidates()."""
        task = importer.ImportTask(paths=self.import_dir,
                                   toppath='top path',
                                   items=[_common.item()])
        task.search_ids = [self.MB_RELEASE_PREFIX + self.ID_RELEASE_0,
                           self.MB_RELEASE_PREFIX + self.ID_RELEASE_1,
                           'an invalid and discarded id']

        task.lookup_candidates()
        self.assertEqual(set(['VALID_RELEASE_0', 'VALID_RELEASE_1']),
                         set([c.info.album for c in task.candidates]))

    def test_candidates_singleton(self):
        """Test directly SingletonImportTask.lookup_candidates()."""
        task = importer.SingletonImportTask(toppath='top path',
                                            item=_common.item())
        task.search_ids = [self.MB_RECORDING_PREFIX + self.ID_RECORDING_0,
                           self.MB_RECORDING_PREFIX + self.ID_RECORDING_1,
                           'an invalid and discarded id']

        task.lookup_candidates()
        self.assertEqual(set(['VALID_RECORDING_0', 'VALID_RECORDING_1']),
                         set([c.info.title for c in task.candidates]))


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
