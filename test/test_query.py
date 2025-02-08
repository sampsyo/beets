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

"""Various tests for querying the library database."""

import os
import sys
import unittest
from contextlib import contextmanager
from functools import partial

import pytest
from mock import patch

import beets.library
from beets import dbcore, util
from beets.dbcore import types
from beets.dbcore.query import (
    InvalidQueryArgumentValueError,
    NoneQuery,
    ParsingError,
)
from beets.test import _common
from beets.test.helper import BeetsTestCase, ItemInDBTestCase
from beets.util import syspath

# Because the absolute path begins with something like C:, we
# can't disambiguate it from an ordinary query.
WIN32_NO_IMPLICIT_PATHS = "Implicit paths are not supported on Windows"


class AssertsMixin:
    def assert_items_matched(self, results, titles):
        assert {i.title for i in results} == set(titles)

    def assert_albums_matched(self, results, albums):
        assert {a.album for a in results} == set(albums)

    def assertInResult(self, item, results):
        result_ids = [i.id for i in results]
        assert item.id in result_ids

    def assertNotInResult(self, item, results):
        result_ids = [i.id for i in results]
        assert item.id not in result_ids


# A test case class providing a library with some dummy data and some
# assertions involving that data.
class DummyDataTestCase(BeetsTestCase, AssertsMixin):
    def setUp(self):
        super().setUp()
        items = [_common.item() for _ in range(3)]
        items[0].title = "foo bar"
        items[0].artist = "one"
        items[0].artists = ["one", "eleven"]
        items[0].album = "baz"
        items[0].year = 2001
        items[0].comp = True
        items[0].genre = "rock"
        items[1].title = "baz qux"
        items[1].artist = "two"
        items[1].artists = ["two", "twelve"]
        items[1].album = "baz"
        items[1].year = 2002
        items[1].comp = True
        items[1].genre = "Rock"
        items[2].title = "beets 4 eva"
        items[2].artist = "three"
        items[2].artists = ["three", "one"]
        items[2].album = "foo"
        items[2].year = 2003
        items[2].comp = False
        items[2].genre = "Hard Rock"
        for item in items:
            self.lib.add(item)
        self.album = self.lib.add_album(items[:2])

    def assert_items_matched_all(self, results):
        self.assert_items_matched(
            results,
            [
                "foo bar",
                "baz qux",
                "beets 4 eva",
            ],
        )


class GetTest(DummyDataTestCase):
    def test_get_empty(self):
        q = ""
        results = self.lib.items(q)
        self.assert_items_matched_all(results)

    def test_get_none(self):
        q = None
        results = self.lib.items(q)
        self.assert_items_matched_all(results)

    def test_get_one_keyed_term(self):
        q = "title:qux"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_get_one_keyed_exact(self):
        q = "genre:=rock"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])
        q = "genre:=Rock"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])
        q = 'genre:="Hard Rock"'
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_get_one_keyed_exact_nocase(self):
        q = 'genre:=~"hard rock"'
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_get_one_keyed_regexp(self):
        q = "artist::t.+r"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_get_one_unkeyed_term(self):
        q = "three"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_get_one_unkeyed_exact(self):
        q = "=rock"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])

    def test_get_one_unkeyed_exact_nocase(self):
        q = '=~"hard rock"'
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_get_one_unkeyed_regexp(self):
        q = ":x$"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_get_no_matches(self):
        q = "popebear"
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

    def test_invalid_key(self):
        q = "pope:bear"
        results = self.lib.items(q)
        # Matches nothing since the flexattr is not present on the
        # objects.
        self.assert_items_matched(results, [])

    def test_get_no_matches_exact(self):
        q = 'genre:="hard rock"'
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

    def test_term_case_insensitive(self):
        q = "oNE"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])

    def test_regexp_case_sensitive(self):
        q = ":oNE"
        results = self.lib.items(q)
        self.assert_items_matched(results, [])
        q = ":one"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])

    def test_term_case_insensitive_with_key(self):
        q = "artist:thrEE"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_term_case_regex_with_multi_key_matches(self):
        q = "artists::eleven"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])

    def test_term_case_regex_with_multi_key_matches_multiple_columns(self):
        q = "artists::one"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "beets 4 eva"])

    def test_key_case_insensitive(self):
        q = "ArTiST:three"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_keyed_matches_exact_nocase(self):
        q = "genre:=~rock"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "foo bar",
                "baz qux",
            ],
        )

    def test_unkeyed_term_matches_multiple_columns(self):
        q = "baz"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "foo bar",
                "baz qux",
            ],
        )

    def test_unkeyed_regexp_matches_multiple_columns(self):
        q = ":z$"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "foo bar",
                "baz qux",
            ],
        )

    def test_keyed_term_matches_only_one_column(self):
        q = "title:baz"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_keyed_regexp_matches_only_one_column(self):
        q = "title::baz"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "baz qux",
            ],
        )

    def test_multiple_terms_narrow_search(self):
        q = "qux baz"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "baz qux",
            ],
        )

    def test_multiple_regexps_narrow_search(self):
        q = ":baz :qux"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_mixed_terms_regexps_narrow_search(self):
        q = ":baz qux"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_single_year(self):
        q = "year:2001"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar"])

    def test_year_range(self):
        q = "year:2000..2002"
        results = self.lib.items(q)
        self.assert_items_matched(
            results,
            [
                "foo bar",
                "baz qux",
            ],
        )

    def test_singleton_true(self):
        q = "singleton:true"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_singleton_1(self):
        q = "singleton:1"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_singleton_false(self):
        q = "singleton:false"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "baz qux"])

    def test_singleton_0(self):
        q = "singleton:0"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "baz qux"])

    def test_compilation_true(self):
        q = "comp:true"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "baz qux"])

    def test_compilation_false(self):
        q = "comp:false"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["beets 4 eva"])

    def test_unknown_field_name_no_results(self):
        q = "xyzzy:nonsense"
        results = self.lib.items(q)
        titles = [i.title for i in results]
        assert titles == []

    def test_unknown_field_name_no_results_in_album_query(self):
        q = "xyzzy:nonsense"
        results = self.lib.albums(q)
        names = [a.album for a in results]
        assert names == []

    def test_item_field_name_matches_nothing_in_album_query(self):
        q = "format:nonsense"
        results = self.lib.albums(q)
        names = [a.album for a in results]
        assert names == []

    def test_unicode_query(self):
        item = self.lib.items().get()
        item.title = "caf\xe9"
        item.store()

        q = "title:caf\xe9"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["caf\xe9"])

    def test_numeric_search_positive(self):
        q = dbcore.query.NumericQuery("year", "2001")
        results = self.lib.items(q)
        assert results

    def test_numeric_search_negative(self):
        q = dbcore.query.NumericQuery("year", "1999")
        results = self.lib.items(q)
        assert not results

    def test_album_field_fallback(self):
        self.album["albumflex"] = "foo"
        self.album.store()

        q = "albumflex:foo"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "baz qux"])

    def test_invalid_query(self):
        with pytest.raises(InvalidQueryArgumentValueError, match="not an int"):
            dbcore.query.NumericQuery("year", "199a")

        msg_match = r"not a regular expression.*unterminated subpattern"
        with pytest.raises(ParsingError, match=msg_match):
            dbcore.query.RegexpQuery("year", "199(")


class MatchTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.item = _common.item()

    def test_regex_match_positive(self):
        q = dbcore.query.RegexpQuery("album", "^the album$")
        assert q.match(self.item)

    def test_regex_match_negative(self):
        q = dbcore.query.RegexpQuery("album", "^album$")
        assert not q.match(self.item)

    def test_regex_match_non_string_value(self):
        q = dbcore.query.RegexpQuery("disc", "^6$")
        assert q.match(self.item)

    def test_substring_match_positive(self):
        q = dbcore.query.SubstringQuery("album", "album")
        assert q.match(self.item)

    def test_substring_match_negative(self):
        q = dbcore.query.SubstringQuery("album", "ablum")
        assert not q.match(self.item)

    def test_substring_match_non_string_value(self):
        q = dbcore.query.SubstringQuery("disc", "6")
        assert q.match(self.item)

    def test_exact_match_nocase_positive(self):
        q = dbcore.query.StringQuery("genre", "the genre")
        assert q.match(self.item)
        q = dbcore.query.StringQuery("genre", "THE GENRE")
        assert q.match(self.item)

    def test_exact_match_nocase_negative(self):
        q = dbcore.query.StringQuery("genre", "genre")
        assert not q.match(self.item)

    def test_year_match_positive(self):
        q = dbcore.query.NumericQuery("year", "1")
        assert q.match(self.item)

    def test_year_match_negative(self):
        q = dbcore.query.NumericQuery("year", "10")
        assert not q.match(self.item)

    def test_bitrate_range_positive(self):
        q = dbcore.query.NumericQuery("bitrate", "100000..200000")
        assert q.match(self.item)

    def test_bitrate_range_negative(self):
        q = dbcore.query.NumericQuery("bitrate", "200000..300000")
        assert not q.match(self.item)

    def test_open_range(self):
        dbcore.query.NumericQuery("bitrate", "100000..")

    def test_eq(self):
        q1 = dbcore.query.MatchQuery("foo", "bar")
        q2 = dbcore.query.MatchQuery("foo", "bar")
        q3 = dbcore.query.MatchQuery("foo", "baz")
        q4 = dbcore.query.StringFieldQuery("foo", "bar")
        assert q1 == q2
        assert q1 != q3
        assert q1 != q4
        assert q3 != q4


class PathQueryTest(ItemInDBTestCase, AssertsMixin):
    def setUp(self):
        super().setUp()

        # This is the item we'll try to match.
        self.i.path = util.normpath("/a/b/c.mp3")
        self.i.title = "path item"
        self.i.album = "path album"
        self.i.store()
        self.lib.add_album([self.i])

        # A second item for testing exclusion.
        i2 = _common.item()
        i2.path = util.normpath("/x/y/z.mp3")
        i2.title = "another item"
        i2.album = "another album"
        self.lib.add(i2)
        self.lib.add_album([i2])

    @contextmanager
    def force_implicit_query_detection(self):
        # Unadorned path queries with path separators in them are considered
        # path queries only when the path in question actually exists. So we
        # mock the existence check to return true.
        beets.library.PathQuery.force_implicit_query_detection = True
        yield
        beets.library.PathQuery.force_implicit_query_detection = False

    def test_path_exact_match(self):
        q = "path:/a/b/c.mp3"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["path item"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    # FIXME: fails on windows
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_parent_directory_no_slash(self):
        q = "path:/a"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["path item"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    # FIXME: fails on windows
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_parent_directory_with_slash(self):
        q = "path:/a/"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["path item"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    def test_no_match(self):
        q = "path:/xyzzy/"
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_fragment_no_match(self):
        q = "path:/b/"
        results = self.lib.items(q)
        self.assert_items_matched(results, [])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, [])

    def test_nonnorm_path(self):
        q = "path:/x/../a/b"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["path item"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    @unittest.skipIf(sys.platform == "win32", WIN32_NO_IMPLICIT_PATHS)
    def test_slashed_query_matches_path(self):
        with self.force_implicit_query_detection():
            q = "/a/b"
            results = self.lib.items(q)
            self.assert_items_matched(results, ["path item"])

            results = self.lib.albums(q)
            self.assert_albums_matched(results, ["path album"])

    @unittest.skipIf(sys.platform == "win32", WIN32_NO_IMPLICIT_PATHS)
    def test_path_query_in_or_query(self):
        with self.force_implicit_query_detection():
            q = "/a/b , /a/b"
            results = self.lib.items(q)
            self.assert_items_matched(results, ["path item"])

    def test_non_slashed_does_not_match_path(self):
        with self.force_implicit_query_detection():
            q = "c.mp3"
            results = self.lib.items(q)
            self.assert_items_matched(results, [])

            results = self.lib.albums(q)
            self.assert_albums_matched(results, [])

    def test_slashes_in_explicit_field_does_not_match_path(self):
        with self.force_implicit_query_detection():
            q = "title:/a/b"
            results = self.lib.items(q)
            self.assert_items_matched(results, [])

    def test_path_item_regex(self):
        q = "path::c\\.mp3$"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["path item"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    def test_path_album_regex(self):
        q = "path::b"
        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["path album"])

    def test_escape_underscore(self):
        self.add_album(
            path=b"/a/_/title.mp3",
            title="with underscore",
            album="album with underscore",
        )
        q = "path:/a/_"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["with underscore"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["album with underscore"])

    def test_escape_percent(self):
        self.add_album(
            path=b"/a/%/title.mp3",
            title="with percent",
            album="album with percent",
        )
        q = "path:/a/%"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["with percent"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["album with percent"])

    def test_escape_backslash(self):
        self.add_album(
            path=rb"/a/\x/title.mp3",
            title="with backslash",
            album="album with backslash",
        )
        q = "path:/a/\\\\x"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["with backslash"])

        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["album with backslash"])

    def test_case_sensitivity(self):
        self.add_album(path=b"/A/B/C2.mp3", title="caps path")

        makeq = partial(beets.library.PathQuery, "path", "/A/B")

        results = self.lib.items(makeq(case_sensitive=True))
        self.assert_items_matched(results, ["caps path"])

        results = self.lib.items(makeq(case_sensitive=False))
        self.assert_items_matched(results, ["path item", "caps path"])

    # FIXME: Also create a variant of this test for windows, which tests
    # both os.sep and os.altsep
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_path_sep_detection(self):
        is_path_query = beets.library.PathQuery.is_path_query

        with self.force_implicit_query_detection():
            assert is_path_query("/foo/bar")
            assert is_path_query("foo/bar")
            assert is_path_query("foo/")
            assert not is_path_query("foo")
            assert is_path_query("foo/:bar")
            assert not is_path_query("foo:bar/")
            assert not is_path_query("foo:/bar")

    # FIXME: shouldn't this also work on windows?
    @unittest.skipIf(sys.platform == "win32", WIN32_NO_IMPLICIT_PATHS)
    def test_detect_absolute_path(self):
        """Test detection of implicit path queries based on whether or
        not the path actually exists, when using an absolute path query.

        Thus, don't use the `force_implicit_query_detection()`
        contextmanager which would disable the existence check.
        """
        is_path_query = beets.library.PathQuery.is_path_query

        path = self.touch(os.path.join(b"foo", b"bar"))
        assert os.path.isabs(util.syspath(path))
        path_str = path.decode("utf-8")

        # The file itself.
        assert is_path_query(path_str)

        # The parent directory.
        parent = os.path.dirname(path_str)
        assert is_path_query(parent)

        # Some non-existent path.
        assert not is_path_query(f"{path_str}baz")

    def test_detect_relative_path(self):
        """Test detection of implicit path queries based on whether or
        not the path actually exists, when using a relative path query.

        Thus, don't use the `force_implicit_query_detection()`
        contextmanager which would disable the existence check.
        """
        is_path_query = beets.library.PathQuery.is_path_query

        self.touch(os.path.join(b"foo", b"bar"))

        # Temporarily change directory so relative paths work.
        cur_dir = os.getcwd()
        try:
            os.chdir(syspath(self.temp_dir))
            assert is_path_query("foo/")
            assert is_path_query("foo/bar")
            assert is_path_query("foo/bar:tagada")
            assert not is_path_query("bar")
        finally:
            os.chdir(cur_dir)


class IntQueryTest(BeetsTestCase):
    def test_exact_value_match(self):
        item = self.add_item(bpm=120)
        matched = self.lib.items("bpm:120").get()
        assert item.id == matched.id

    def test_range_match(self):
        item = self.add_item(bpm=120)
        self.add_item(bpm=130)

        matched = self.lib.items("bpm:110..125")
        assert 1 == len(matched)
        assert item.id == matched.get().id

    @patch("beets.library.Item._types", {"myint": types.Integer()})
    def test_flex_range_match(self):
        item = self.add_item(myint=2)
        matched = self.lib.items("myint:2").get()
        assert item.id == matched.id

    @patch("beets.library.Item._types", {"myint": types.Integer()})
    def test_flex_dont_match_missing(self):
        self.add_item()
        matched = self.lib.items("myint:2").get()
        assert matched is None

    def test_no_substring_match(self):
        self.add_item(bpm=120)
        matched = self.lib.items("bpm:12").get()
        assert matched is None


@patch("beets.library.Item._types", {"flexbool": types.Boolean()})
class BoolQueryTest(BeetsTestCase, AssertsMixin):
    def test_parse_true(self):
        item_true = self.add_item(comp=True)
        item_false = self.add_item(comp=False)
        matched = self.lib.items("comp:true")
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_true(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items("flexbool:true")
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_false(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items("flexbool:false")
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)

    def test_flex_parse_1(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items("flexbool:1")
        self.assertInResult(item_true, matched)
        self.assertNotInResult(item_false, matched)

    def test_flex_parse_0(self):
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items("flexbool:0")
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)

    def test_flex_parse_any_string(self):
        # TODO this should be the other way around
        item_true = self.add_item(flexbool=True)
        item_false = self.add_item(flexbool=False)
        matched = self.lib.items("flexbool:something")
        self.assertInResult(item_false, matched)
        self.assertNotInResult(item_true, matched)


class DefaultSearchFieldsTest(DummyDataTestCase):
    def test_albums_matches_album(self):
        albums = list(self.lib.albums("baz"))
        assert len(albums) == 1

    def test_albums_matches_albumartist(self):
        albums = list(self.lib.albums(["album artist"]))
        assert len(albums) == 1

    def test_items_matches_title(self):
        items = self.lib.items("beets")
        self.assert_items_matched(items, ["beets 4 eva"])

    def test_items_does_not_match_year(self):
        items = self.lib.items("2001")
        self.assert_items_matched(items, [])


class NoneQueryTest(BeetsTestCase, AssertsMixin):
    def test_match_singletons(self):
        singleton = self.add_item()
        album_item = self.add_album().items().get()

        matched = self.lib.items(NoneQuery("album_id"))
        self.assertInResult(singleton, matched)
        self.assertNotInResult(album_item, matched)

    def test_match_after_set_none(self):
        item = self.add_item(rg_track_gain=0)
        matched = self.lib.items(NoneQuery("rg_track_gain"))
        self.assertNotInResult(item, matched)

        item["rg_track_gain"] = None
        item.store()
        matched = self.lib.items(NoneQuery("rg_track_gain"))
        self.assertInResult(item, matched)

    def test_match_slow(self):
        item = self.add_item()
        matched = self.lib.items(NoneQuery("rg_track_peak", fast=False))
        self.assertInResult(item, matched)

    def test_match_slow_after_set_none(self):
        item = self.add_item(rg_track_gain=0)
        matched = self.lib.items(NoneQuery("rg_track_gain", fast=False))
        self.assertNotInResult(item, matched)

        item["rg_track_gain"] = None
        item.store()
        matched = self.lib.items(NoneQuery("rg_track_gain", fast=False))
        self.assertInResult(item, matched)


class NotQueryMatchTest(BeetsTestCase):
    """Test `query.NotQuery` matching against a single item, using the same
    cases and assertions as on `MatchTest`, plus assertion on the negated
    queries (ie. assert q -> assert not NotQuery(q)).
    """

    def setUp(self):
        super().setUp()
        self.item = _common.item()

    def test_regex_match_positive(self):
        q = dbcore.query.RegexpQuery("album", "^the album$")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_regex_match_negative(self):
        q = dbcore.query.RegexpQuery("album", "^album$")
        assert not q.match(self.item)
        assert dbcore.query.NotQuery(q).match(self.item)

    def test_regex_match_non_string_value(self):
        q = dbcore.query.RegexpQuery("disc", "^6$")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_substring_match_positive(self):
        q = dbcore.query.SubstringQuery("album", "album")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_substring_match_negative(self):
        q = dbcore.query.SubstringQuery("album", "ablum")
        assert not q.match(self.item)
        assert dbcore.query.NotQuery(q).match(self.item)

    def test_substring_match_non_string_value(self):
        q = dbcore.query.SubstringQuery("disc", "6")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_year_match_positive(self):
        q = dbcore.query.NumericQuery("year", "1")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_year_match_negative(self):
        q = dbcore.query.NumericQuery("year", "10")
        assert not q.match(self.item)
        assert dbcore.query.NotQuery(q).match(self.item)

    def test_bitrate_range_positive(self):
        q = dbcore.query.NumericQuery("bitrate", "100000..200000")
        assert q.match(self.item)
        assert not dbcore.query.NotQuery(q).match(self.item)

    def test_bitrate_range_negative(self):
        q = dbcore.query.NumericQuery("bitrate", "200000..300000")
        assert not q.match(self.item)
        assert dbcore.query.NotQuery(q).match(self.item)

    def test_open_range(self):
        q = dbcore.query.NumericQuery("bitrate", "100000..")
        dbcore.query.NotQuery(q)


class NotQueryTest(DummyDataTestCase):
    """Test `query.NotQuery` against the dummy data:
    - `test_type_xxx`: tests for the negation of a particular XxxQuery class.
    - `test_get_yyy`: tests on query strings (similar to `GetTest`)
    """

    def assertNegationProperties(self, q):
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
        all_titles = {i.title for i in self.lib.items()}
        q_results = {i.title for i in self.lib.items(q)}
        not_q_results = {i.title for i in self.lib.items(not_q)}
        assert q_results.union(not_q_results) == all_titles
        assert q_results.intersection(not_q_results) == set()

        # round trip
        not_not_q = dbcore.query.NotQuery(not_q)
        assert {i.title for i in self.lib.items(q)} == {
            i.title for i in self.lib.items(not_not_q)
        }

    def test_type_and(self):
        # not(a and b) <-> not(a) or not(b)
        q = dbcore.query.AndQuery(
            [
                dbcore.query.BooleanQuery("comp", True),
                dbcore.query.NumericQuery("year", "2002"),
            ],
        )
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["foo bar", "beets 4 eva"])
        self.assertNegationProperties(q)

    def test_type_boolean(self):
        q = dbcore.query.BooleanQuery("comp", True)
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["beets 4 eva"])
        self.assertNegationProperties(q)

    def test_type_date(self):
        q = dbcore.query.DateQuery("added", "2000-01-01")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        # query date is in the past, thus the 'not' results should contain all
        # items
        self.assert_items_matched(
            not_results, ["foo bar", "baz qux", "beets 4 eva"]
        )
        self.assertNegationProperties(q)

    def test_type_false(self):
        q = dbcore.query.FalseQuery()
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched_all(not_results)
        self.assertNegationProperties(q)

    def test_type_match(self):
        q = dbcore.query.MatchQuery("year", "2003")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["foo bar", "baz qux"])
        self.assertNegationProperties(q)

    def test_type_none(self):
        q = dbcore.query.NoneQuery("rg_track_gain")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [])
        self.assertNegationProperties(q)

    def test_type_numeric(self):
        q = dbcore.query.NumericQuery("year", "2001..2002")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["beets 4 eva"])
        self.assertNegationProperties(q)

    def test_type_or(self):
        # not(a or b) <-> not(a) and not(b)
        q = dbcore.query.OrQuery(
            [
                dbcore.query.BooleanQuery("comp", True),
                dbcore.query.NumericQuery("year", "2002"),
            ]
        )
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["beets 4 eva"])
        self.assertNegationProperties(q)

    def test_type_regexp(self):
        q = dbcore.query.RegexpQuery("artist", "^t")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["foo bar"])
        self.assertNegationProperties(q)

    def test_type_substring(self):
        q = dbcore.query.SubstringQuery("album", "ba")
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, ["beets 4 eva"])
        self.assertNegationProperties(q)

    def test_type_true(self):
        q = dbcore.query.TrueQuery()
        not_results = self.lib.items(dbcore.query.NotQuery(q))
        self.assert_items_matched(not_results, [])
        self.assertNegationProperties(q)

    def test_get_prefixes_keyed(self):
        """Test both negation prefixes on a keyed query."""
        q0 = "-title:qux"
        q1 = "^title:qux"
        results0 = self.lib.items(q0)
        results1 = self.lib.items(q1)
        self.assert_items_matched(results0, ["foo bar", "beets 4 eva"])
        self.assert_items_matched(results1, ["foo bar", "beets 4 eva"])

    def test_get_prefixes_unkeyed(self):
        """Test both negation prefixes on an unkeyed query."""
        q0 = "-qux"
        q1 = "^qux"
        results0 = self.lib.items(q0)
        results1 = self.lib.items(q1)
        self.assert_items_matched(results0, ["foo bar", "beets 4 eva"])
        self.assert_items_matched(results1, ["foo bar", "beets 4 eva"])

    def test_get_one_keyed_regexp(self):
        q = "-artist::t.+r"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "baz qux"])

    def test_get_one_unkeyed_regexp(self):
        q = "-:x$"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["foo bar", "beets 4 eva"])

    def test_get_multiple_terms(self):
        q = "baz -bar"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_get_mixed_terms(self):
        q = "baz -title:bar"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["baz qux"])

    def test_fast_vs_slow(self):
        """Test that the results are the same regardless of the `fast` flag
        for negated `FieldQuery`s.

        TODO: investigate NoneQuery(fast=False), as it is raising
        AttributeError: type object 'NoneQuery' has no attribute 'field'
        at NoneQuery.match() (due to being @classmethod, and no self?)
        """
        classes = [
            (dbcore.query.DateQuery, ["added", "2001-01-01"]),
            (dbcore.query.MatchQuery, ["artist", "one"]),
            # (dbcore.query.NoneQuery, ['rg_track_gain']),
            (dbcore.query.NumericQuery, ["year", "2002"]),
            (dbcore.query.StringFieldQuery, ["year", "2001"]),
            (dbcore.query.RegexpQuery, ["album", "^.a"]),
            (dbcore.query.SubstringQuery, ["title", "x"]),
        ]

        for klass, args in classes:
            q_fast = dbcore.query.NotQuery(klass(*(args + [True])))
            q_slow = dbcore.query.NotQuery(klass(*(args + [False])))

            try:
                assert [i.title for i in self.lib.items(q_fast)] == [
                    i.title for i in self.lib.items(q_slow)
                ]
            except NotImplementedError:
                # ignore classes that do not provide `fast` implementation
                pass


class RelatedQueriesTest(BeetsTestCase, AssertsMixin):
    """Test album-level queries with track-level filters and vice-versa."""

    def setUp(self):
        super().setUp()

        albums = []
        for album_idx in range(1, 3):
            album_name = f"Album{album_idx}"
            album_items = []
            for item_idx in range(1, 3):
                item = _common.item()
                item.album = album_name
                item.title = f"{album_name} Item{item_idx}"
                self.lib.add(item)
                album_items.append(item)
            album = self.lib.add_album(album_items)
            album.artpath = f"{album_name} Artpath"
            album.catalognum = "ABC"
            album.store()
            albums.append(album)

        self.album, self.another_album = albums

    def test_get_albums_filter_by_track_field(self):
        q = "title:Album1"
        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["Album1"])

    def test_get_items_filter_by_album_field(self):
        q = "artpath::Album1"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["Album1 Item1", "Album1 Item2"])

    def test_filter_albums_by_common_field(self):
        # title:Album1 ensures that the items table is joined for the query
        q = "title:Album1 Album1"
        results = self.lib.albums(q)
        self.assert_albums_matched(results, ["Album1"])

    def test_filter_items_by_common_field(self):
        # artpath::A ensures that the albums table is joined for the query
        q = "artpath::A Album1"
        results = self.lib.items(q)
        self.assert_items_matched(results, ["Album1 Item1", "Album1 Item2"])
