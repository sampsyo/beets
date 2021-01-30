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

"""Various tests for querying the library database.
"""
from __future__ import division, absolute_import, print_function

from functools import partial
from mock import patch
import os
import sys
import unittest

from test import _common
from test import helper

import beets.library
from beets import dbcore
from beets.dbcore import types
from beets.dbcore.query import (NoneQuery, ParsingError,
                                InvalidQueryArgumentValueError)
from beets.library import Library, Item
from beets import util
from beets.util import syspath
import platform
import six


class TestHelper(helper.TestHelper):

    def assertInResult(self, item, results):  # noqa
        result_ids = [i.id for i in results]
        self.assertIn(item.id, result_ids)

    def assertNotInResult(self, item, results):  # noqa
        result_ids = [i.id for i in results]
        self.assertNotIn(item.id, result_ids)


class AnyFieldQueryTest(_common.LibTestCase):
    def test_no_restriction(self):
        q = dbcore.query.AnyFieldQuery(
            'title', beets.library.Item._fields.keys(),
            dbcore.query.SubstringQuery
        )
        self.assertEqual(self.lib.items(q).get().title, 'the title')

    def test_restriction_completeness(self):
        q = dbcore.query.AnyFieldQuery('title', [u'title'],
                                       dbcore.query.SubstringQuery)
        self.assertEqual(self.lib.items(q).get().title, u'the title')

    def test_restriction_soundness(self):
        q = dbcore.query.AnyFieldQuery('title', [u'artist'],
                                       dbcore.query.SubstringQuery)
        self.assertEqual(self.lib.items(q).get(), None)

    def test_eq(self):
        q1 = dbcore.query.AnyFieldQuery('foo', [u'bar'],
                                        dbcore.query.SubstringQuery)
        q2 = dbcore.query.AnyFieldQuery('foo', [u'bar'],
                                        dbcore.query.SubstringQuery)
        self.assertEqual(q1, q2)

        q2.query_class = None
        self.assertNotEqual(q1, q2)


class AssertsMixin(object):
    def assert_items_matched(self, results, titles):
        self.assertEqual(set([i.title for i in results]), set(titles))

    def assert_albums_matched(self, results, albums):
        self.assertEqual(set([a.album for a in results]), set(albums))


# A test case class providing a library with some dummy data and some
# assertions involving that data.
class DummyDataTestCase(_common.TestCase, AssertsMixin):
    def setUp(self):
        super(DummyDataTestCase, self).setUp()
        self.lib = beets.library.Library(':memory:')
        items = [_common.item() for _ in range(3)]
        items[0].title = u'foo bar'
        items[0].artist = u'one'
        items[0].album = u'baz'
        items[0].year = 2001
        items[0].comp = True
        items[1].title = u'baz qux'
        items[1].artist = u'two'
        items[1].album = u'baz'
        items[1].year = 2002
        items[1].comp = True
        items[2].title = u'beets 4 eva'
        items[2].artist = u'three'
        items[2].album = u'foo'
        items[2].year = 2003
        items[2].comp = False
        for item in items:
            self.lib.add(item)
        self.lib.add_album(items[:2])

    def assert_items_matched_all(self, results):
        self.assert_items_matched(results, [
            u'foo bar',
            u'baz qux',
            u'beets 4 eva',
        ])


class GetTest(DummyDataTestCase):
    def test_get_empty(self):
        q = u''
        results = self.lib.items(q)
        self.assert_items_matched_all(results)

    def test_get_none(self):
        q = None
        results = self.lib.items(q)
        self.assert_items_matched_all(results)

    def test_get_one_keyed_term(self):
        q = u'title:qux'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_get_one_keyed_regexp(self):
        q = u'artist::t.+r'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_get_one_unkeyed_term(self):
        q = u'three'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_get_one_unkeyed_regexp(self):
        q = u':x$'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_get_no_matches(self):
        q = u'popebear'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

    def test_invalid_key(self):
        q = u'pope:bear'
        results = self.lib.items(q)
        # Matches nothing since the flexattr is not present on the
        # objects.
        self.assert_items_matched(results, [])

    def test_term_case_insensitive(self):
        q = u'oNE'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar'])

    def test_regexp_case_sensitive(self):
        q = u':oNE'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])
        q = u':one'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar'])

    def test_term_case_insensitive_with_key(self):
        q = u'artist:thrEE'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_key_case_insensitive(self):
        q = u'ArTiST:three'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_unkeyed_term_matches_multiple_columns(self):
        q = u'baz'
        results = self.lib.items(q)
        self.assert_items_matched(results, [
            u'foo bar',
            u'baz qux',
        ])

    def test_unkeyed_regexp_matches_multiple_columns(self):
        q = u':z$'
        results = self.lib.items(q)
        self.assert_items_matched(results, [
            u'foo bar',
            u'baz qux',
        ])

    def test_keyed_term_matches_only_one_column(self):
        q = u'title:baz'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_keyed_regexp_matches_only_one_column(self):
        q = u'title::baz'
        results = self.lib.items(q)
        self.assert_items_matched(results, [
            u'baz qux',
        ])

    def test_multiple_terms_narrow_search(self):
        q = u'qux baz'
        results = self.lib.items(q)
        self.assert_items_matched(results, [
            u'baz qux',
        ])

    def test_multiple_regexps_narrow_search(self):
        q = u':baz :qux'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_mixed_terms_regexps_narrow_search(self):
        q = u':baz qux'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_single_year(self):
        q = u'year:2001'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar'])

    def test_year_range(self):
        q = u'year:2000..2002'
        results = self.lib.items(q)
        self.assert_items_matched(results, [
            u'foo bar',
            u'baz qux',
        ])

    def test_singleton_true(self):
        q = u'singleton:true'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_singleton_false(self):
        q = u'singleton:false'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar', u'baz qux'])

    def test_compilation_true(self):
        q = u'comp:true'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar', u'baz qux'])

    def test_compilation_false(self):
        q = u'comp:false'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'beets 4 eva'])

    def test_unknown_field_name_no_results(self):
        q = u'xyzzy:nonsense'
        results = self.lib.items(q)
        titles = [i.title for i in results]
        self.assertEqual(titles, [])

    def test_unknown_field_name_no_results_in_album_query(self):
        q = u'xyzzy:nonsense'
        results = self.lib.albums(q)
        names = [a.album for a in results]
        self.assertEqual(names, [])

    def test_item_field_name_matches_nothing_in_album_query(self):
        q = u'format:nonsense'
        results = self.lib.albums(q)
        names = [a.album for a in results]
        self.assertEqual(names, [])

    def test_unicode_query(self):
        item = self.lib.items().get()
        item.title = u'caf\xe9'
        item.store()

        q = u'title:caf\xe9'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'caf\xe9'])

    def test_numeric_search_positive(self):
        q = dbcore.query.NumericQuery('year', u'2001')
        results = self.lib.items(q)
        self.assertTrue(results)

    def test_numeric_search_negative(self):
        q = dbcore.query.NumericQuery('year', u'1999')
        results = self.lib.items(q)
        self.assertFalse(results)

    def test_invalid_query(self):
        with self.assertRaises(InvalidQueryArgumentValueError) as raised:
            dbcore.query.NumericQuery('year', u'199a')
        self.assertIn(u'not an int', six.text_type(raised.exception))

        with self.assertRaises(InvalidQueryArgumentValueError) as raised:
            dbcore.query.RegexpQuery('year', u'199(')
        exception_text = six.text_type(raised.exception)
        self.assertIn(u'not a regular expression', exception_text)
        if sys.version_info >= (3, 5):
            self.assertIn(u'unterminated subpattern', exception_text)
        else:
            self.assertIn(u'unbalanced parenthesis', exception_text)
        self.assertIsInstance(raised.exception, ParsingError)


class MatchTest(_common.TestCase):
    def setUp(self):
        super(MatchTest, self).setUp()
        self.item = _common.item()

    def test_regex_match_positive(self):
        q = dbcore.query.RegexpQuery('album', u'^the album$')
        self.assertTrue(q.match(self.item))

    def test_regex_match_negative(self):
        q = dbcore.query.RegexpQuery('album', u'^album$')
        self.assertFalse(q.match(self.item))

    def test_regex_match_non_string_value(self):
        q = dbcore.query.RegexpQuery('disc', u'^6$')
        self.assertTrue(q.match(self.item))

    def test_substring_match_positive(self):
        q = dbcore.query.SubstringQuery('album', u'album')
        self.assertTrue(q.match(self.item))

    def test_substring_match_negative(self):
        q = dbcore.query.SubstringQuery('album', u'ablum')
        self.assertFalse(q.match(self.item))

    def test_substring_match_non_string_value(self):
        q = dbcore.query.SubstringQuery('disc', u'6')
        self.assertTrue(q.match(self.item))

    def test_year_match_positive(self):
        q = dbcore.query.NumericQuery('year', u'1')
        self.assertTrue(q.match(self.item))

    def test_year_match_negative(self):
        q = dbcore.query.NumericQuery('year', u'10')
        self.assertFalse(q.match(self.item))

    def test_bitrate_range_positive(self):
        q = dbcore.query.NumericQuery('bitrate', u'100000..200000')
        self.assertTrue(q.match(self.item))

    def test_bitrate_range_negative(self):
        q = dbcore.query.NumericQuery('bitrate', u'200000..300000')
        self.assertFalse(q.match(self.item))

    def test_open_range(self):
        dbcore.query.NumericQuery('bitrate', u'100000..')

    def test_eq(self):
        q1 = dbcore.query.MatchQuery('foo', u'bar')
        q2 = dbcore.query.MatchQuery('foo', u'bar')
        q3 = dbcore.query.MatchQuery('foo', u'baz')
        q4 = dbcore.query.StringFieldQuery('foo', u'bar')
        self.assertEqual(q1, q2)
        self.assertNotEqual(q1, q3)
        self.assertNotEqual(q1, q4)
        self.assertNotEqual(q3, q4)


class PathQueryTest(_common.LibTestCase, TestHelper, AssertsMixin):
    def setUp(self):
        super(PathQueryTest, self).setUp()

        # This is the item we'll try to match.
        self.i.path = util.normpath('/a/b/c.mp3')
        self.i.title = u'path item'
        self.i.album = u'path album'
        self.i.store()
        self.lib.add_album([self.i])

        # A second item for testing exclusion.
        i2 = _common.item()
        i2.path = util.normpath('/x/y/z.mp3')
        i2.title = 'another item'
        i2.album = 'another album'
        self.lib.add(i2)
        self.lib.add_album([i2])

        # Unadorned path queries with path separators in them are considered
        # path queries only when the path in question actually exists. So we
        # mock the existence check to return true.
        self.patcher_exists = patch('beets.library.os.path.exists')
        self.patcher_exists.start().return_value = True

        # We have to create function samefile as it does not exist on
        # Windows and python 2.7
        self.patcher_samefile = patch('beets.library.os.path.samefile',
                                      create=True)
        self.patcher_samefile.start().return_value = True

    def tearDown(self):
        super(PathQueryTest, self).tearDown()

        self.patcher_samefile.stop()
        self.patcher_exists.stop()

    def test_path_exact_match(self):
        q = u'path:/a/b/c.mp3'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_parent_directory_no_slash(self):
        q = u'path:/a'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'path album'])

    def test_parent_directory_with_slash(self):
        q = u'path:/a/'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'path album'])

    def test_no_match(self):
        q = u'path:/xyzzy/'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_fragment_no_match(self):
        q = u'path:/b/'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_nonnorm_path(self):
        q = u'path:/x/../a/b'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'path album'])

    def test_slashed_query_matches_path(self):
        q = u'/a/b'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'path album'])

    @unittest.skip('unfixed (#1865)')
    def test_path_query_in_or_query(self):
        q = '/a/b , /a/b'
        results = self.lib.items(q)
        self.assert_items_matched(results, ['path item'])

    def test_non_slashed_does_not_match_path(self):
        q = u'c.mp3'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_slashes_in_explicit_field_does_not_match_path(self):
        q = u'title:/a/b'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

    def test_path_item_regex(self):
        q = u'path::c\\.mp3$'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'path item'])

    def test_path_album_regex(self):
        q = u'path::b'
        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'path album'])

    def test_escape_underscore(self):
        self.add_album(path=b'/a/_/title.mp3', title=u'with underscore',
                       album=u'album with underscore')
        q = u'path:/a/_'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'with underscore'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'album with underscore'])

    def test_escape_percent(self):
        self.add_album(path=b'/a/%/title.mp3', title=u'with percent',
                       album=u'album with percent')
        q = u'path:/a/%'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'with percent'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'album with percent'])

    def test_escape_backslash(self):
        self.add_album(path=br'/a/\x/title.mp3', title=u'with backslash',
                       album=u'album with backslash')
        q = u'path:/a/\\\\x'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'with backslash'])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [u'album with backslash'])

    def test_case_sensitivity(self):
        self.add_album(path=b'/A/B/C2.mp3', title=u'caps path')

        makeq = partial(beets.library.PathQuery, u'path', '/A/B')

        results = self.lib.items(makeq(case_sensitive=True))
        self.assert_items_matched(results, [u'caps path'])

        results = self.lib.items(makeq(case_sensitive=False))
        self.assert_items_matched(results, [u'path item', u'caps path'])

        # Check for correct case sensitivity selection (this check
        # only works on non-Windows OSes).
        with _common.system_mock('Darwin'):
            # exists = True and samefile = True => Case insensitive
            q = makeq()
            self.assertEqual(q.case_sensitive, False)

            # exists = True and samefile = False => Case sensitive
            self.patcher_samefile.stop()
            self.patcher_samefile.start().return_value = False
            try:
                q = makeq()
                self.assertEqual(q.case_sensitive, True)
            finally:
                self.patcher_samefile.stop()
                self.patcher_samefile.start().return_value = True

        # Test platform-aware default sensitivity when the library path
        # does not exist. For the duration of this check, we change the
        # `os.path.exists` mock to return False.
        self.patcher_exists.stop()
        self.patcher_exists.start().return_value = False
        try:
            with _common.system_mock('Darwin'):
                q = makeq()
                self.assertEqual(q.case_sensitive, True)

            with _common.system_mock('Windows'):
                q = makeq()
                self.assertEqual(q.case_sensitive, False)
        finally:
            # Restore the `os.path.exists` mock to its original state.
            self.patcher_exists.stop()
            self.patcher_exists.start().return_value = True

    @patch('beets.library.os')
    def test_path_sep_detection(self, mock_os):
        mock_os.sep = '/'
        mock_os.altsep = None
        mock_os.path.exists = lambda p: True
        is_path = beets.library.PathQuery.is_path_query

        self.assertTrue(is_path('/foo/bar'))
        self.assertTrue(is_path('foo/bar'))
        self.assertTrue(is_path('foo/'))
        self.assertFalse(is_path('foo'))
        self.assertTrue(is_path('foo/:bar'))
        self.assertFalse(is_path('foo:bar/'))
        self.assertFalse(is_path('foo:/bar'))

    def test_detect_absolute_path(self):
        if platform.system() == 'Windows':
            # Because the absolute path begins with something like C:, we
            # can't disambiguate it from an ordinary query.
            self.skipTest('Windows absolute paths do not work as queries')

        # Don't patch `os.path.exists`; we'll actually create a file when
        # it exists.
        self.patcher_exists.stop()
        is_path = beets.library.PathQuery.is_path_query

        try:
            path = self.touch(os.path.join(b'foo', b'bar'))
            path = path.decode('utf-8')

            # The file itself.
            self.assertTrue(is_path(path))

            # The parent directory.
            parent = os.path.dirname(path)
            self.assertTrue(is_path(parent))

            # Some non-existent path.
            self.assertFalse(is_path(path + u'baz'))

        finally:
            # Restart the `os.path.exists` patch.
            self.patcher_exists.start()

    def test_detect_relative_path(self):
        self.patcher_exists.stop()
        is_path = beets.library.PathQuery.is_path_query

        try:
            self.touch(os.path.join(b'foo', b'bar'))

            # Temporarily change directory so relative paths work.
            cur_dir = os.getcwd()
            try:
                os.chdir(syspath(self.temp_dir))
                self.assertTrue(is_path(u'foo/'))
                self.assertTrue(is_path(u'foo/bar'))
                self.assertTrue(is_path(u'foo/bar:tagada'))
                self.assertFalse(is_path(u'bar'))
            finally:
                os.chdir(cur_dir)

        finally:
            self.patcher_exists.start()


class IntQueryTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.lib = Library(':memory:')

    def tearDown(self):
        Item._types = {}

    def test_exact_value_match(self):
        item = self.add_item(bpm=120)
        matched = self.lib.items(u'bpm:120').get()
        self.assertEqual(item.id, matched.id)

    def test_range_match(self):
        item = self.add_item(bpm=120)
        self.add_item(bpm=130)

        matched = self.lib.items(u'bpm:110..125')
        self.assertEqual(1, len(matched))
        self.assertEqual(item.id, matched.get().id)

    def test_flex_range_match(self):
        Item._types = {'myint': types.Integer()}
        item = self.add_item(myint=2)
        matched = self.lib.items(u'myint:2').get()
        self.assertEqual(item.id, matched.id)

    def test_flex_dont_match_missing(self):
        Item._types = {'myint': types.Integer()}
        self.add_item()
        matched = self.lib.items(u'myint:2').get()
        self.assertIsNone(matched)

    def test_no_substring_match(self):
        self.add_item(bpm=120)
        matched = self.lib.items(u'bpm:12').get()
        self.assertIsNone(matched)


class BoolQueryTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.lib = Library(':memory:')
        Item._types = {'flexbool': types.Boolean()}

    def tearDown(self):
        Item._types = {}

    def test_parse_true(self):
        item_true = self.add_item(comp=True)
        item_false = self.add_item(comp=False)
        matched = self.lib.items(u'comp:true')
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_true(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items(u'flexbool:true')
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_false(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items(u'flexbool:false')
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)

    def test_flex_parse_1(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items(u'flexbool:1')
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_0(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items(u'flexbool:0')
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)

    def test_flex_parse_any_string(self):
        # TODO this should be the other way around
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items(u'flexbool:something')
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)


class DefaultSearchFieldsTest(DummyDataTestCase):
    def test_albums_matches_album(self):
        albums = list(self.lib.albums(u'baz'))
        self.assertEqual(len(albums), 1)

    def test_albums_matches_albumartist(self):
        albums = list(self.lib.albums([u'album artist']))
        self.assertEqual(len(albums), 1)

    def test_items_matches_title(self):
        items = self.lib.items(u'beets')
        self.assert_items_matched(items, [u'beets 4 eva'])

    def test_items_does_not_match_year(self):
        items = self.lib.items(u'2001')
        self.assert_items_matched(items, [])


class NoneQueryTest(unittest.TestCase, TestHelper):

    def setUp(self):
        self.lib = Library(':memory:')

    def test_match_singletons(self):
        singleton = self.add_item()
        album_item = self.add_album().items().get()

        matched = self.lib.items(NoneQuery(u'album_id'))
        self.assertInResult(singleton, matched)
        self.assertNotInResult(album_item, matched)

    def test_match_after_set_none(self):
        item = self.add_item(rg_track_gain=0)
        matched = self.lib.items(NoneQuery(u'rg_track_gain'))
        self.assertNotInResult(item, matched)

        item['rg_track_gain'] = None
        item.store()
        matched = self.lib.items(NoneQuery(u'rg_track_gain'))
        self.assertInResult(item, matched)

    def test_match_slow(self):
        item = self.add_item()
        matched = self.lib.items(NoneQuery(u'rg_track_peak', fast=False))
        self.assertInResult(item, matched)

    def test_match_slow_after_set_none(self):
        item = self.add_item(rg_track_gain=0)
        matched = self.lib.items(NoneQuery(u'rg_track_gain', fast=False))
        self.assertNotInResult(item, matched)

        item['rg_track_gain'] = None
        item.store()
        matched = self.lib.items(NoneQuery(u'rg_track_gain', fast=False))
        self.assertInResult(item, matched)


class NotQueryMatchTest(_common.TestCase):
    """Test `query.NotQuery` matching against a single item, using the same
    cases and assertions as on `MatchTest`, plus assertion on the negated
    queries (ie. assertTrue(q) -> assertFalse(NotQuery(q))).
    """
    def setUp(self):
        super(NotQueryMatchTest, self).setUp()
        self.item = _common.item()

    def test_regex_match_positive(self):
        q = dbcore.query.RegexpQuery(u'album', u'^the album$')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_regex_match_negative(self):
        q = dbcore.query.RegexpQuery(u'album', u'^album$')
        self.assertFalse(q.match(self.item))
        self.assertTrue(dbcore.query.NotQuery(q).match(self.item))

    def test_regex_match_non_string_value(self):
        q = dbcore.query.RegexpQuery(u'disc', u'^6$')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_substring_match_positive(self):
        q = dbcore.query.SubstringQuery(u'album', u'album')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_substring_match_negative(self):
        q = dbcore.query.SubstringQuery(u'album', u'ablum')
        self.assertFalse(q.match(self.item))
        self.assertTrue(dbcore.query.NotQuery(q).match(self.item))

    def test_substring_match_non_string_value(self):
        q = dbcore.query.SubstringQuery(u'disc', u'6')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_year_match_positive(self):
        q = dbcore.query.NumericQuery(u'year', u'1')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_year_match_negative(self):
        q = dbcore.query.NumericQuery(u'year', u'10')
        self.assertFalse(q.match(self.item))
        self.assertTrue(dbcore.query.NotQuery(q).match(self.item))

    def test_bitrate_range_positive(self):
        q = dbcore.query.NumericQuery(u'bitrate', u'100000..200000')
        self.assertTrue(q.match(self.item))
        self.assertFalse(dbcore.query.NotQuery(q).match(self.item))

    def test_bitrate_range_negative(self):
        q = dbcore.query.NumericQuery(u'bitrate', u'200000..300000')
        self.assertFalse(q.match(self.item))
        self.assertTrue(dbcore.query.NotQuery(q).match(self.item))

    def test_open_range(self):
        q = dbcore.query.NumericQuery(u'bitrate', u'100000..')
        dbcore.query.NotQuery(q)


class NotQueryTest(DummyDataTestCase):
    """Test `query.NotQuery` against the dummy data:
    - `test_type_xxx`: tests for the negation of a particular XxxQuery class.
    - `test_get_yyy`: tests on query strings (similar to `GetTest`)
    """
    def assertNegationProperties(self, q):  # noqa
        """Given a Query `q`, assert that:
        - q OR not(q) == all items
        - q AND not(q) == 0
        - not(not(q)) == q
        """
        not_q = dbcore.query.NotQuery(q)
        # assert using OrQuery, AndQuery
        q_or = dbcore.query.OrQuery([q, not_q])
        q_and = dbcore.query.AndQuery([q, not_q])
        self.assert_items_matched_all(self.lib.items(q_or))
        self.assert_items_matched(self.lib.items(q_and), [])

        # assert manually checking the item titles
        all_titles = set([i.title for i in self.lib.items()])
        q_results = set([i.title for i in self.lib.items(q)])
        not_q_results = set([i.title for i in self.lib.items(not_q)])
        self.assertEqual(q_results.union(not_q_results), all_titles)
        self.assertEqual(q_results.intersection(not_q_results), set())

        # round trip
        not_not_q = dbcore.query.NotQuery(not_q)
        self.assertEqual(set([i.title for i in self.lib.items(q)]),
                         set([i.title for i in self.lib.items(not_not_q)]))

    def test_type_and(self):
        # not(a and b) <-> not(a) or not(b)
        q = dbcore.query.AndQuery([
            dbcore.query.BooleanQuery(u'comp', True),
            dbcore.query.NumericQuery(u'year', u'2002')],
        )
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'foo bar', u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_anyfield(self):
        q = dbcore.query.AnyFieldQuery(u'foo', [u'title', u'artist', u'album'],
                                       dbcore.query.SubstringQuery)
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'baz qux'])
        self.assertNegationProperties(q)

    def test_type_boolean(self):
        q = dbcore.query.BooleanQuery(u'comp', True)
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_date(self):
        q = dbcore.query.DateQuery(u'added', u'2000-01-01')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        # query date is in the past, thus the 'not' results should contain all
        # items
        self.assert_items_matched(not_results, [u'foo bar', u'baz qux',
                                                u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_false(self):
        q = dbcore.query.FalseQuery()
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched_all(not_results)
        self.assertNegationProperties(q)

    def test_type_match(self):
        q = dbcore.query.MatchQuery(u'year', u'2003')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'foo bar', u'baz qux'])
        self.assertNegationProperties(q)

    def test_type_none(self):
        q = dbcore.query.NoneQuery(u'rg_track_gain')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [])
        self.assertNegationProperties(q)

    def test_type_numeric(self):
        q = dbcore.query.NumericQuery(u'year', u'2001..2002')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_or(self):
        # not(a or b) <-> not(a) and not(b)
        q = dbcore.query.OrQuery([dbcore.query.BooleanQuery(u'comp', True),
                                  dbcore.query.NumericQuery(u'year', u'2002')])
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_regexp(self):
        q = dbcore.query.RegexpQuery(u'artist', u'^t')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'foo bar'])
        self.assertNegationProperties(q)

    def test_type_substring(self):
        q = dbcore.query.SubstringQuery(u'album', u'ba')
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [u'beets 4 eva'])
        self.assertNegationProperties(q)

    def test_type_true(self):
        q = dbcore.query.TrueQuery()
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [])
        self.assertNegationProperties(q)

    def test_get_prefixes_keyed(self):
        """Test both negation prefixes on a keyed query."""
        q0 = u'-title:qux'
        q1 = u'^title:qux'
        results0 = self.lib.items(q0)
        results1 = self.lib.items(q1)
        self.assert_items_matched(results0, [u'foo bar', u'beets 4 eva'])
        self.assert_items_matched(results1, [u'foo bar', u'beets 4 eva'])

    def test_get_prefixes_unkeyed(self):
        """Test both negation prefixes on an unkeyed query."""
        q0 = u'-qux'
        q1 = u'^qux'
        results0 = self.lib.items(q0)
        results1 = self.lib.items(q1)
        self.assert_items_matched(results0, [u'foo bar', u'beets 4 eva'])
        self.assert_items_matched(results1, [u'foo bar', u'beets 4 eva'])

    def test_get_one_keyed_regexp(self):
        q = u'-artist::t.+r'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar', u'baz qux'])

    def test_get_one_unkeyed_regexp(self):
        q = u'-:x$'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'foo bar', u'beets 4 eva'])

    def test_get_multiple_terms(self):
        q = u'baz -bar'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_get_mixed_terms(self):
        q = u'baz -title:bar'
        results = self.lib.items(q)
        self.assert_items_matched(results, [u'baz qux'])

    def test_fast_vs_slow(self):
        """Test that the results are the same regardless of the `fast` flag
        for negated `FieldQuery`s.

        TODO: investigate NoneQuery(fast=False), as it is raising
        AttributeError: type object 'NoneQuery' has no attribute 'field'
        at NoneQuery.match() (due to being @classmethod, and no self?)
        """
        classes = [(dbcore.query.DateQuery, [u'added', u'2001-01-01']),
                   (dbcore.query.MatchQuery, [u'artist', u'one']),
                   # (dbcore.query.NoneQuery, ['rg_track_gain']),
                   (dbcore.query.NumericQuery, [u'year', u'2002']),
                   (dbcore.query.StringFieldQuery, [u'year', u'2001']),
                   (dbcore.query.RegexpQuery, [u'album', u'^.a']),
                   (dbcore.query.SubstringQuery, [u'title', u'x'])]

        for klass, args in classes:
            q_fast = dbcore.query.NotQuery(klass(*(args + [True])))
            q_slow = dbcore.query.NotQuery(klass(*(args + [False])))

            try:
                self.assertEqual([i.title for i in self.lib.items(q_fast)],
                                 [i.title for i in self.lib.items(q_slow)])
            except NotImplementedError:
                # ignore classes that do not provide `fast` implementation
                pass


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
