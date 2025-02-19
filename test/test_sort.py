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

from mock import patch

import beets.library
from beets import config, dbcore
from beets.dbcore import types
from beets.library import Album
from beets.test import _common
from beets.test.helper import BeetsTestCase


# A test case class providing a library with some dummy data and some
# assertions involving that data.
class DummyDataTestCase(BeetsTestCase):
    def setUp(self):
        super().setUp()

        albums = [
            Album(
                album="Album A",
                label="Label",
                year=2001,
                flex1="Flex1-1",
                flex2="Flex2-A",
                albumartist="Foo",
            ),
            Album(
                album="Album B",
                label="Label",
                year=2001,
                flex1="Flex1-2",
                flex2="Flex2-A",
                albumartist="Bar",
            ),
            Album(
                album="Album C",
                label="Records",
                year=2005,
                flex1="Flex1-1",
                flex2="Flex2-B",
                albumartist="Baz",
            ),
        ]
        for album in albums:
            self.lib.add(album)

        items = [_common.item() for _ in range(4)]
        items[0].title = "Foo bar"
        items[0].artist = "One"
        items[0].album = "Baz"
        items[0].year = 2001
        items[0].comp = True
        items[0].flex1 = "Flex1-0"
        items[0].flex2 = "Flex2-A"
        items[0].album_id = albums[0].id
        items[0].artist_sort = None
        items[0].path = "/path0.mp3"
        items[0].track = 1
        items[1].title = "Baz qux"
        items[1].artist = "Two"
        items[1].album = "Baz"
        items[1].year = 2002
        items[1].comp = True
        items[1].flex1 = "Flex1-1"
        items[1].flex2 = "Flex2-A"
        items[1].album_id = albums[0].id
        items[1].artist_sort = None
        items[1].path = "/patH1.mp3"
        items[1].track = 2
        items[2].title = "Beets 4 eva"
        items[2].artist = "Three"
        items[2].album = "Foo"
        items[2].year = 2003
        items[2].comp = False
        items[2].flex1 = "Flex1-2"
        items[2].flex2 = "Flex1-B"
        items[2].album_id = albums[1].id
        items[2].artist_sort = None
        items[2].path = "/paTH2.mp3"
        items[2].track = 3
        items[3].title = "Beets 4 eva"
        items[3].artist = "Three"
        items[3].album = "Foo2"
        items[3].year = 2004
        items[3].comp = False
        items[3].flex1 = "Flex1-2"
        items[3].flex2 = "Flex1-C"
        items[3].album_id = albums[2].id
        items[3].artist_sort = None
        items[3].path = "/PATH3.mp3"
        items[3].track = 4
        for item in items:
            self.lib.add(item)


class SortFixedFieldTest(DummyDataTestCase):
    def test_sort_asc(self):
        q = ""
        sort = dbcore.query.FixedFieldSort("year", True)
        results = self.lib.items(q, sort)
        assert results[0]["year"] <= results[1]["year"]
        assert results[0]["year"] == 2001
        # same thing with query string
        q = "year+"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_desc(self):
        q = ""
        sort = dbcore.query.FixedFieldSort("year", False)
        results = self.lib.items(q, sort)
        assert results[0]["year"] >= results[1]["year"]
        assert results[0]["year"] == 2004
        # same thing with query string
        q = "year-"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_two_field_asc(self):
        q = ""
        s1 = dbcore.query.FixedFieldSort("album", True)
        s2 = dbcore.query.FixedFieldSort("year", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.items(q, sort)
        assert results[0]["album"] <= results[1]["album"]
        assert results[1]["album"] <= results[2]["album"]
        assert results[0]["album"] == "Baz"
        assert results[1]["album"] == "Baz"
        assert results[0]["year"] <= results[1]["year"]
        # same thing with query string
        q = "album+ year+"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_path_field(self):
        q = ""
        sort = dbcore.query.FixedFieldSort("path", True)
        results = self.lib.items(q, sort)
        assert results[0]["path"] == b"/path0.mp3"
        assert results[1]["path"] == b"/patH1.mp3"
        assert results[2]["path"] == b"/paTH2.mp3"
        assert results[3]["path"] == b"/PATH3.mp3"


class SortFlexFieldTest(DummyDataTestCase):
    def test_sort_asc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("flex1", True)
        results = self.lib.items(q, sort)
        assert results[0]["flex1"] <= results[1]["flex1"]
        assert results[0]["flex1"] == "Flex1-0"
        # same thing with query string
        q = "flex1+"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_desc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("flex1", False)
        results = self.lib.items(q, sort)
        assert results[0]["flex1"] >= results[1]["flex1"]
        assert results[1]["flex1"] >= results[2]["flex1"]
        assert results[2]["flex1"] >= results[3]["flex1"]
        assert results[0]["flex1"] == "Flex1-2"
        # same thing with query string
        q = "flex1-"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_two_field(self):
        q = ""
        s1 = dbcore.query.SlowFieldSort("flex2", False)
        s2 = dbcore.query.SlowFieldSort("flex1", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.items(q, sort)
        assert results[0]["flex2"] >= results[1]["flex2"]
        assert results[1]["flex2"] >= results[2]["flex2"]
        assert results[0]["flex2"] == "Flex2-A"
        assert results[1]["flex2"] == "Flex2-A"
        assert results[0]["flex1"] <= results[1]["flex1"]
        # same thing with query string
        q = "flex2- flex1+"
        results2 = self.lib.items(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id


class SortAlbumFixedFieldTest(DummyDataTestCase):
    def test_sort_asc(self):
        q = ""
        sort = dbcore.query.FixedFieldSort("year", True)
        results = self.lib.albums(q, sort)
        assert results[0]["year"] <= results[1]["year"]
        assert results[0]["year"] == 2001
        # same thing with query string
        q = "year+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_desc(self):
        q = ""
        sort = dbcore.query.FixedFieldSort("year", False)
        results = self.lib.albums(q, sort)
        assert results[0]["year"] >= results[1]["year"]
        assert results[0]["year"] == 2005
        # same thing with query string
        q = "year-"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_two_field_asc(self):
        q = ""
        s1 = dbcore.query.FixedFieldSort("label", True)
        s2 = dbcore.query.FixedFieldSort("album", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.albums(q, sort)
        assert results[0]["label"] <= results[1]["label"]
        assert results[1]["label"] <= results[2]["label"]
        assert results[1]["label"] == "Label"
        assert results[2]["label"] == "Records"
        assert results[1]["album"] <= results[2]["album"]
        # same thing with query string
        q = "label+ album+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id


class SortAlbumFlexFieldTest(DummyDataTestCase):
    def test_sort_asc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("flex1", True)
        results = self.lib.albums(q, sort)
        assert results[0]["flex1"] <= results[1]["flex1"]
        assert results[1]["flex1"] <= results[2]["flex1"]
        # same thing with query string
        q = "flex1+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_desc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("flex1", False)
        results = self.lib.albums(q, sort)
        assert results[0]["flex1"] >= results[1]["flex1"]
        assert results[1]["flex1"] >= results[2]["flex1"]
        # same thing with query string
        q = "flex1-"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_two_field_asc(self):
        q = ""
        s1 = dbcore.query.SlowFieldSort("flex2", True)
        s2 = dbcore.query.SlowFieldSort("flex1", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.albums(q, sort)
        assert results[0]["flex2"] <= results[1]["flex2"]
        assert results[1]["flex2"] <= results[2]["flex2"]
        assert results[0]["flex2"] == "Flex2-A"
        assert results[1]["flex2"] == "Flex2-A"
        assert results[0]["flex1"] <= results[1]["flex1"]
        # same thing with query string
        q = "flex2+ flex1+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id


class SortAlbumComputedFieldTest(DummyDataTestCase):
    def test_sort_asc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("path", True)
        results = self.lib.albums(q, sort)
        assert results[0]["path"] <= results[1]["path"]
        assert results[1]["path"] <= results[2]["path"]
        # same thing with query string
        q = "path+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_sort_desc(self):
        q = ""
        sort = dbcore.query.SlowFieldSort("path", False)
        results = self.lib.albums(q, sort)
        assert results[0]["path"] >= results[1]["path"]
        assert results[1]["path"] >= results[2]["path"]
        # same thing with query string
        q = "path-"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id


class SortCombinedFieldTest(DummyDataTestCase):
    def test_computed_first(self):
        q = ""
        s1 = dbcore.query.SlowFieldSort("path", True)
        s2 = dbcore.query.FixedFieldSort("year", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.albums(q, sort)
        assert results[0]["path"] <= results[1]["path"]
        assert results[1]["path"] <= results[2]["path"]
        q = "path+ year+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id

    def test_computed_second(self):
        q = ""
        s1 = dbcore.query.FixedFieldSort("year", True)
        s2 = dbcore.query.SlowFieldSort("path", True)
        sort = dbcore.query.MultipleSort()
        sort.add_sort(s1)
        sort.add_sort(s2)
        results = self.lib.albums(q, sort)
        assert results[0]["year"] <= results[1]["year"]
        assert results[1]["year"] <= results[2]["year"]
        assert results[0]["path"] <= results[1]["path"]
        q = "year+ path+"
        results2 = self.lib.albums(q)
        for r1, r2 in zip(results, results2):
            assert r1.id == r2.id


class ConfigSortTest(DummyDataTestCase):
    def test_default_sort_item(self):
        results = list(self.lib.items())
        assert results[0].artist < results[1].artist

    def test_config_opposite_sort_item(self):
        config["sort_item"] = "artist-"
        results = list(self.lib.items())
        assert results[0].artist > results[1].artist

    def test_default_sort_album(self):
        results = list(self.lib.albums())
        assert results[0].albumartist < results[1].albumartist

    def test_config_opposite_sort_album(self):
        config["sort_album"] = "albumartist-"
        results = list(self.lib.albums())
        assert results[0].albumartist > results[1].albumartist


class CaseSensitivityTest(DummyDataTestCase, BeetsTestCase):
    """If case_insensitive is false, lower-case values should be placed
    after all upper-case values. E.g., `Foo Qux bar`
    """

    def setUp(self):
        super().setUp()

        album = Album(
            album="album",
            label="label",
            year="2001",
            flex1="flex1",
            flex2="flex2-A",
            albumartist="bar",
        )
        self.lib.add(album)

        item = _common.item()
        item.title = "another"
        item.artist = "lowercase"
        item.album = "album"
        item.year = 2001
        item.comp = True
        item.flex1 = "flex1"
        item.flex2 = "flex2-A"
        item.album_id = album.id
        item.artist_sort = None
        item.track = 10
        self.lib.add(item)

        self.new_album = album
        self.new_item = item

    def tearDown(self):
        self.new_item.remove(delete=True)
        self.new_album.remove(delete=True)
        super().tearDown()

    def test_smart_artist_case_insensitive(self):
        config["sort_case_insensitive"] = True
        q = "artist+"
        results = list(self.lib.items(q))
        assert results[0].artist == "lowercase"
        assert results[1].artist == "One"

    def test_smart_artist_case_sensitive(self):
        config["sort_case_insensitive"] = False
        q = "artist+"
        results = list(self.lib.items(q))
        assert results[0].artist == "One"
        assert results[-1].artist == "lowercase"

    def test_fixed_field_case_insensitive(self):
        config["sort_case_insensitive"] = True
        q = "album+"
        results = list(self.lib.albums(q))
        assert results[0].album == "album"
        assert results[1].album == "Album A"

    def test_fixed_field_case_sensitive(self):
        config["sort_case_insensitive"] = False
        q = "album+"
        results = list(self.lib.albums(q))
        assert results[0].album == "Album A"
        assert results[-1].album == "album"

    def test_flex_field_case_insensitive(self):
        config["sort_case_insensitive"] = True
        q = "flex1+"
        results = list(self.lib.items(q))
        assert results[0].flex1 == "flex1"
        assert results[1].flex1 == "Flex1-0"

    def test_flex_field_case_sensitive(self):
        config["sort_case_insensitive"] = False
        q = "flex1+"
        results = list(self.lib.items(q))
        assert results[0].flex1 == "Flex1-0"
        assert results[-1].flex1 == "flex1"

    def test_case_sensitive_only_affects_text(self):
        config["sort_case_insensitive"] = True
        q = "track+"
        results = list(self.lib.items(q))
        # If the numerical values were sorted as strings,
        # then ['1', '10', '2'] would be valid.
        # print([r.track for r in results])
        assert results[0].track == 1
        assert results[1].track == 2
        assert results[-1].track == 10


class NonExistingFieldTest(DummyDataTestCase):
    """Test sorting by non-existing fields"""

    def test_non_existing_fields_not_fail(self):
        qs = ["foo+", "foo-", "--", "-+", "+-", "++", "-foo-", "-foo+", "---"]

        q0 = "foo+"
        results0 = list(self.lib.items(q0))
        for q1 in qs:
            results1 = list(self.lib.items(q1))
            for r1, r2 in zip(results0, results1):
                assert r1.id == r2.id

    def test_combined_non_existing_field_asc(self):
        all_results = list(self.lib.items("id+"))
        q = "foo+ id+"
        results = list(self.lib.items(q))
        assert len(all_results) == len(results)
        for r1, r2 in zip(all_results, results):
            assert r1.id == r2.id

    def test_combined_non_existing_field_desc(self):
        all_results = list(self.lib.items("id+"))
        q = "foo- id+"
        results = list(self.lib.items(q))
        assert len(all_results) == len(results)
        for r1, r2 in zip(all_results, results):
            assert r1.id == r2.id

    def test_field_present_in_some_items(self):
        """Test ordering by a (string) field not present on all items."""
        # append 'foo' to two items (1,2)
        lower_foo_item, higher_foo_item, *items_without_foo = self.lib.items(
            "id+"
        )
        lower_foo_item.foo, higher_foo_item.foo = "bar1", "bar2"
        lower_foo_item.store()
        higher_foo_item.store()

        results_asc = list(self.lib.items("foo+ id+"))
        assert [i.id for i in results_asc] == [
            # items without field first
            *[i.id for i in items_without_foo],
            lower_foo_item.id,
            higher_foo_item.id,
        ]

        results_desc = list(self.lib.items("foo- id+"))
        assert [i.id for i in results_desc] == [
            higher_foo_item.id,
            lower_foo_item.id,
            # items without field last
            *[i.id for i in items_without_foo],
        ]

    @patch("beets.library.Item._types", {"myint": types.Integer()})
    def test_int_field_present_in_some_items(self):
        """Test ordering by an int-type field not present on all items."""
        # append int-valued 'myint' to two items (1,2)
        lower_myint_item, higher_myint_item, *items_without_myint = (
            self.lib.items("id+")
        )
        lower_myint_item.myint, higher_myint_item.myint = 1, 2
        lower_myint_item.store()
        higher_myint_item.store()

        results_asc = list(self.lib.items("myint+ id+"))
        assert [i.id for i in results_asc] == [
            # items without field first
            *[i.id for i in items_without_myint],
            lower_myint_item.id,
            higher_myint_item.id,
        ]

        results_desc = list(self.lib.items("myint- id+"))
        assert [i.id for i in results_desc] == [
            higher_myint_item.id,
            lower_myint_item.id,
            # items without field last
            *[i.id for i in items_without_myint],
        ]

    def test_negation_interaction(self):
        """Test the handling of negation and sorting together.

        If a string ends with a sorting suffix, it takes precedence over the
        NotQuery parsing.
        """
        query, sort = beets.library.parse_query_string(
            "-bar+", beets.library.Item
        )
        assert len(query.subqueries) == 1
        assert isinstance(query.subqueries[0], dbcore.query.TrueQuery)
        assert isinstance(sort, dbcore.query.SlowFieldSort)
        assert sort.field == "-bar"
