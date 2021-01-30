# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2016, Bruno Cauet.
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

from os import path, remove
from tempfile import mkdtemp
from shutil import rmtree
import unittest

from mock import Mock, MagicMock

from beetsplug.smartplaylist import SmartPlaylistPlugin
from beets.library import Item, Album, parse_query_string
from beets.dbcore import OrQuery
from beets.dbcore.query import NullSort, MultipleSort, FixedFieldSort
from beets.util import syspath, bytestring_path, py3_path, CHAR_REPLACE
from beets.ui import UserError
from beets import config

from test import _common
from test.helper import TestHelper


class SmartPlaylistTest(_common.TestCase):
    def test_build_queries(self):
        spl = SmartPlaylistPlugin()
        self.assertEqual(spl._matched_playlists, None)
        self.assertEqual(spl._unmatched_playlists, None)

        config['smartplaylist']['playlists'].set([])
        spl.build_queries()
        self.assertEqual(spl._matched_playlists, set())
        self.assertEqual(spl._unmatched_playlists, set())

        config['smartplaylist']['playlists'].set([
            {'name': u'foo',
             'query': u'FOO foo'},
            {'name': u'bar',
             'album_query': [u'BAR bar1', u'BAR bar2']},
            {'name': u'baz',
             'query': u'BAZ baz',
             'album_query': u'BAZ baz'}
        ])
        spl.build_queries()
        self.assertEqual(spl._matched_playlists, set())
        foo_foo = parse_query_string(u'FOO foo', Item)
        baz_baz = parse_query_string(u'BAZ baz', Item)
        baz_baz2 = parse_query_string(u'BAZ baz', Album)
        bar_bar = OrQuery((parse_query_string(u'BAR bar1', Album)[0],
                           parse_query_string(u'BAR bar2', Album)[0]))
        self.assertEqual(spl._unmatched_playlists, set([
            (u'foo', foo_foo, (None, None)),
            (u'baz', baz_baz, baz_baz2),
            (u'bar', (None, None), (bar_bar, None)),
        ]))

    def test_build_queries_with_sorts(self):
        spl = SmartPlaylistPlugin()
        config['smartplaylist']['playlists'].set([
            {'name': u'no_sort',
             'query': u'foo'},
            {'name': u'one_sort',
             'query': u'foo year+'},
            {'name': u'only_empty_sorts',
             'query': [u'foo', u'bar']},
            {'name': u'one_non_empty_sort',
             'query': [u'foo year+', u'bar']},
            {'name': u'multiple_sorts',
             'query': [u'foo year+', u'bar genre-']},
            {'name': u'mixed',
             'query': [u'foo year+', u'bar', u'baz genre+ id-']}
        ])

        spl.build_queries()
        sorts = dict((name, sort)
                     for name, (_, sort), _ in spl._unmatched_playlists)

        asseq = self.assertEqual  # less cluttered code
        sort = FixedFieldSort  # short cut since we're only dealing with this
        asseq(sorts["no_sort"], NullSort())
        asseq(sorts["one_sort"], sort(u'year'))
        asseq(sorts["only_empty_sorts"], None)
        asseq(sorts["one_non_empty_sort"], sort(u'year'))
        asseq(sorts["multiple_sorts"],
              MultipleSort([sort('year'), sort(u'genre', False)]))
        asseq(sorts["mixed"],
              MultipleSort([sort('year'), sort(u'genre'), sort(u'id', False)]))

    def test_matches(self):
        spl = SmartPlaylistPlugin()

        a = MagicMock(Album)
        i = MagicMock(Item)

        self.assertFalse(spl.matches(i, None, None))
        self.assertFalse(spl.matches(a, None, None))

        query = Mock()
        query.match.side_effect = {i: True}.__getitem__
        self.assertTrue(spl.matches(i, query, None))
        self.assertFalse(spl.matches(a, query, None))

        a_query = Mock()
        a_query.match.side_effect = {a: True}.__getitem__
        self.assertFalse(spl.matches(i, None, a_query))
        self.assertTrue(spl.matches(a, None, a_query))

        self.assertTrue(spl.matches(i, query, a_query))
        self.assertTrue(spl.matches(a, query, a_query))

    def test_db_changes(self):
        spl = SmartPlaylistPlugin()

        nones = None, None
        pl1 = '1', (u'q1', None), nones
        pl2 = '2', (u'q2', None), nones
        pl3 = '3', (u'q3', None), nones

        spl._unmatched_playlists = set([pl1, pl2, pl3])
        spl._matched_playlists = set()

        spl.matches = Mock(return_value=False)
        spl.db_change(None, u"nothing")
        self.assertEqual(spl._unmatched_playlists, set([pl1, pl2, pl3]))
        self.assertEqual(spl._matched_playlists, set())

        spl.matches.side_effect = lambda _, q, __: q == u'q3'
        spl.db_change(None, u"matches 3")
        self.assertEqual(spl._unmatched_playlists, set([pl1, pl2]))
        self.assertEqual(spl._matched_playlists, set([pl3]))

        spl.matches.side_effect = lambda _, q, __: q == u'q1'
        spl.db_change(None, u"matches 3")
        self.assertEqual(spl._matched_playlists, set([pl1, pl3]))
        self.assertEqual(spl._unmatched_playlists, set([pl2]))

    def test_playlist_update(self):
        spl = SmartPlaylistPlugin()

        i = Mock(path=b'/tagada.mp3')
        i.evaluate_template.side_effect = \
            lambda pl, _: pl.replace(b'$title', b'ta:ga:da').decode()

        lib = Mock()
        lib.replacements = CHAR_REPLACE
        lib.items.return_value = [i]
        lib.albums.return_value = []

        q = Mock()
        a_q = Mock()
        pl = b'$title-my<playlist>.m3u', (q, None), (a_q, None)
        spl._matched_playlists = [pl]

        dir = bytestring_path(mkdtemp())
        config['smartplaylist']['relative_to'] = False
        config['smartplaylist']['playlist_dir'] = py3_path(dir)
        try:
            spl.update_playlists(lib)
        except Exception:
            rmtree(syspath(dir))
            raise

        lib.items.assert_called_once_with(q, None)
        lib.albums.assert_called_once_with(a_q, None)

        m3u_filepath = path.join(dir, b'ta_ga_da-my_playlist_.m3u')
        self.assertExists(m3u_filepath)
        with open(syspath(m3u_filepath), 'rb') as f:
            content = f.read()
        rmtree(syspath(dir))

        self.assertEqual(content, b'/tagada.mp3\n')


class SmartPlaylistCLITest(_common.TestCase, TestHelper):
    def setUp(self):
        self.setup_beets()

        self.item = self.add_item()
        config['smartplaylist']['playlists'].set([
            {'name': 'my_playlist.m3u',
             'query': self.item.title},
            {'name': 'all.m3u',
             'query': u''}
        ])
        config['smartplaylist']['playlist_dir'].set(py3_path(self.temp_dir))
        self.load_plugins('smartplaylist')

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_splupdate(self):
        with self.assertRaises(UserError):
            self.run_with_output(u'splupdate', u'tagada')

        self.run_with_output(u'splupdate', u'my_playlist')
        m3u_path = path.join(self.temp_dir, b'my_playlist.m3u')
        self.assertExists(m3u_path)
        with open(syspath(m3u_path), 'rb') as f:
            self.assertEqual(f.read(), self.item.path + b"\n")
        remove(syspath(m3u_path))

        self.run_with_output(u'splupdate', u'my_playlist.m3u')
        with open(syspath(m3u_path), 'rb') as f:
            self.assertEqual(f.read(), self.item.path + b"\n")
        remove(syspath(m3u_path))

        self.run_with_output(u'splupdate')
        for name in (b'my_playlist.m3u', b'all.m3u'):
            with open(path.join(self.temp_dir, name), 'rb') as f:
                self.assertEqual(f.read(), self.item.path + b"\n")


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
