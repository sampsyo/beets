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

"""Tests for non-query database functions of Item."""

import os
import os.path
import re
import shutil
import stat
import sys
import time
import unicodedata
import unittest

import pytest
from mediafile import MediaFile, UnreadableFileError

import beets.dbcore.query
import beets.library
from beets import config, plugins, util
from beets.library import Album
from beets.test import _common
from beets.test._common import item
from beets.test.helper import BeetsTestCase, ItemInDBTestCase
from beets.util import bytestring_path, syspath

# Shortcut to path normalization.
np = util.normpath


class LoadTest(ItemInDBTestCase):
    def test_load_restores_data_from_db(self):
        original_title = self.i.title
        self.i.title = "something"
        self.i.load()
        assert original_title == self.i.title

    def test_load_clears_dirty_flags(self):
        self.i.artist = "something"
        assert "artist" in self.i._dirty
        self.i.load()
        assert "artist" not in self.i._dirty


class StoreTest(ItemInDBTestCase):
    def test_store_changes_database_value(self):
        self.i.year = 1987
        self.i.store()
        new_year = (
            self.lib._connection()
            .execute("select year from items where title = ?", (self.i.title,))
            .fetchone()["year"]
        )
        assert new_year == 1987

    def test_store_only_writes_dirty_fields(self):
        original_artist = self.i.artist
        self.i._values_fixed["artist"] = "beatboxing"  # change w/o dirtying
        self.i.store()
        assert (
            (
                self.lib._connection()
                .execute(
                    "select artist from items where title = ?", (self.i.title,)
                )
                .fetchone()["artist"]
            )
            == original_artist
        )

    def test_store_clears_dirty_flags(self):
        self.i.composer = "tvp"
        self.i.store()
        assert "composer" not in self.i._dirty

    def test_store_album_cascades_flex_deletes(self):
        album = Album(flex1="Flex-1")
        self.lib.add(album)
        item = _common.item()
        item.album_id = album.id
        item.flex1 = "Flex-1"
        self.lib.add(item)
        del album.flex1
        album.store()
        assert "flex1" not in album
        assert "flex1" not in album.items()[0]


class AddTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.i = item()

    def test_item_add_inserts_row(self):
        self.lib.add(self.i)
        new_grouping = (
            self.lib._connection()
            .execute(
                "select grouping from items where composer = ?",
                (self.i.composer,),
            )
            .fetchone()["grouping"]
        )
        assert new_grouping == self.i.grouping

    def test_library_add_path_inserts_row(self):
        i = beets.library.Item.from_path(
            os.path.join(_common.RSRC, b"full.mp3")
        )
        self.lib.add(i)
        new_grouping = (
            self.lib._connection()
            .execute(
                "select grouping from items where composer = ?",
                (self.i.composer,),
            )
            .fetchone()["grouping"]
        )
        assert new_grouping == self.i.grouping


class RemoveTest(ItemInDBTestCase):
    def test_remove_deletes_from_db(self):
        self.i.remove()
        c = self.lib._connection().execute("select * from items")
        assert c.fetchone() is None


class GetSetTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.i = item()

    def test_set_changes_value(self):
        self.i.bpm = 4915
        assert self.i.bpm == 4915

    def test_set_sets_dirty_flag(self):
        self.i.comp = not self.i.comp
        assert "comp" in self.i._dirty

    def test_set_does_not_dirty_if_value_unchanged(self):
        self.i.title = self.i.title
        assert "title" not in self.i._dirty

    def test_invalid_field_raises_attributeerror(self):
        with pytest.raises(AttributeError):
            self.i.xyzzy

    def test_album_fallback(self):
        # integration test of item-album fallback
        i = item(self.lib)
        album = self.lib.add_album([i])
        album["flex"] = "foo"
        album.store()

        assert "flex" in i
        assert "flex" not in i.keys(with_album=False)
        assert i["flex"] == "foo"
        assert i.get("flex") == "foo"
        assert i.get("flex", with_album=False) is None
        assert i.get("flexx") is None


class DestinationTest(BeetsTestCase):
    """Confirm tests handle temporary directory path containing '.'"""

    def create_temp_dir(self, **kwargs):
        kwargs["prefix"] = "."
        super().create_temp_dir(**kwargs)

    def setUp(self):
        super().setUp()
        self.i = item(self.lib)

    def test_directory_works_with_trailing_slash(self):
        self.lib.directory = b"one/"
        self.lib.path_formats = [("default", "two")]
        assert self.i.destination() == np("one/two")

    def test_directory_works_without_trailing_slash(self):
        self.lib.directory = b"one"
        self.lib.path_formats = [("default", "two")]
        assert self.i.destination() == np("one/two")

    def test_destination_substitutes_metadata_values(self):
        self.lib.directory = b"base"
        self.lib.path_formats = [("default", "$album/$artist $title")]
        self.i.title = "three"
        self.i.artist = "two"
        self.i.album = "one"
        assert self.i.destination() == np("base/one/two three")

    def test_destination_preserves_extension(self):
        self.lib.directory = b"base"
        self.lib.path_formats = [("default", "$title")]
        self.i.path = "hey.audioformat"
        assert self.i.destination() == np("base/the title.audioformat")

    def test_lower_case_extension(self):
        self.lib.directory = b"base"
        self.lib.path_formats = [("default", "$title")]
        self.i.path = "hey.MP3"
        assert self.i.destination() == np("base/the title.mp3")

    def test_destination_pads_some_indices(self):
        self.lib.directory = b"base"
        self.lib.path_formats = [
            ("default", "$track $tracktotal $disc $disctotal $bpm")
        ]
        self.i.track = 1
        self.i.tracktotal = 2
        self.i.disc = 3
        self.i.disctotal = 4
        self.i.bpm = 5
        assert self.i.destination() == np("base/01 02 03 04 5")

    def test_destination_pads_date_values(self):
        self.lib.directory = b"base"
        self.lib.path_formats = [("default", "$year-$month-$day")]
        self.i.year = 1
        self.i.month = 2
        self.i.day = 3
        assert self.i.destination() == np("base/0001-02-03")

    def test_destination_escapes_slashes(self):
        self.i.album = "one/two"
        dest = self.i.destination()
        assert b"one" in dest
        assert b"two" in dest
        assert b"one/two" not in dest

    def test_destination_escapes_leading_dot(self):
        self.i.album = ".something"
        dest = self.i.destination()
        assert b"something" in dest
        assert b"/.something" not in dest

    def test_destination_preserves_legitimate_slashes(self):
        self.i.artist = "one"
        self.i.album = "two"
        dest = self.i.destination()
        assert os.path.join(b"one", b"two") in dest

    def test_destination_long_names_truncated(self):
        self.i.title = "X" * 300
        self.i.artist = "Y" * 300
        for c in self.i.destination().split(util.PATH_SEP):
            assert len(c) <= 255

    def test_destination_long_names_keep_extension(self):
        self.i.title = "X" * 300
        self.i.path = b"something.extn"
        dest = self.i.destination()
        assert dest[-5:] == b".extn"

    def test_distination_windows_removes_both_separators(self):
        self.i.title = "one \\ two / three.mp3"
        with _common.platform_windows():
            p = self.i.destination()
        assert b"one \\ two" not in p
        assert b"one / two" not in p
        assert b"two \\ three" not in p
        assert b"two / three" not in p

    def test_path_with_format(self):
        self.lib.path_formats = [("default", "$artist/$album ($format)")]
        p = self.i.destination()
        assert b"(FLAC)" in p

    def test_heterogeneous_album_gets_single_directory(self):
        i1, i2 = item(), item()
        self.lib.add_album([i1, i2])
        i1.year, i2.year = 2009, 2010
        self.lib.path_formats = [("default", "$album ($year)/$track $title")]
        dest1, dest2 = i1.destination(), i2.destination()
        assert os.path.dirname(dest1) == os.path.dirname(dest2)

    def test_default_path_for_non_compilations(self):
        self.i.comp = False
        self.lib.add_album([self.i])
        self.lib.directory = b"one"
        self.lib.path_formats = [("default", "two"), ("comp:true", "three")]
        assert self.i.destination() == np("one/two")

    def test_singleton_path(self):
        i = item(self.lib)
        self.lib.directory = b"one"
        self.lib.path_formats = [
            ("default", "two"),
            ("singleton:true", "four"),
            ("comp:true", "three"),
        ]
        assert i.destination() == np("one/four")

    def test_comp_before_singleton_path(self):
        i = item(self.lib)
        i.comp = True
        self.lib.directory = b"one"
        self.lib.path_formats = [
            ("default", "two"),
            ("comp:true", "three"),
            ("singleton:true", "four"),
        ]
        assert i.destination() == np("one/three")

    def test_comp_path(self):
        self.i.comp = True
        self.lib.add_album([self.i])
        self.lib.directory = b"one"
        self.lib.path_formats = [("default", "two"), ("comp:true", "three")]
        assert self.i.destination() == np("one/three")

    def test_albumtype_query_path(self):
        self.i.comp = True
        self.lib.add_album([self.i])
        self.i.albumtype = "sometype"
        self.lib.directory = b"one"
        self.lib.path_formats = [
            ("default", "two"),
            ("albumtype:sometype", "four"),
            ("comp:true", "three"),
        ]
        assert self.i.destination() == np("one/four")

    def test_albumtype_path_fallback_to_comp(self):
        self.i.comp = True
        self.lib.add_album([self.i])
        self.i.albumtype = "sometype"
        self.lib.directory = b"one"
        self.lib.path_formats = [
            ("default", "two"),
            ("albumtype:anothertype", "four"),
            ("comp:true", "three"),
        ]
        assert self.i.destination() == np("one/three")

    def test_get_formatted_does_not_replace_separators(self):
        with _common.platform_posix():
            name = os.path.join("a", "b")
            self.i.title = name
            newname = self.i.formatted().get("title")
        assert name == newname

    def test_get_formatted_pads_with_zero(self):
        with _common.platform_posix():
            self.i.track = 1
            name = self.i.formatted().get("track")
        assert name.startswith("0")

    def test_get_formatted_uses_kbps_bitrate(self):
        with _common.platform_posix():
            self.i.bitrate = 12345
            val = self.i.formatted().get("bitrate")
        assert val == "12kbps"

    def test_get_formatted_uses_khz_samplerate(self):
        with _common.platform_posix():
            self.i.samplerate = 12345
            val = self.i.formatted().get("samplerate")
        assert val == "12kHz"

    def test_get_formatted_datetime(self):
        with _common.platform_posix():
            self.i.added = 1368302461.210265
            val = self.i.formatted().get("added")
        assert val.startswith("2013")

    def test_get_formatted_none(self):
        with _common.platform_posix():
            self.i.some_other_field = None
            val = self.i.formatted().get("some_other_field")
        assert val == ""

    def test_artist_falls_back_to_albumartist(self):
        self.i.artist = ""
        self.i.albumartist = "something"
        self.lib.path_formats = [("default", "$artist")]
        p = self.i.destination()
        assert p.rsplit(util.PATH_SEP, 1)[1] == b"something"

    def test_albumartist_falls_back_to_artist(self):
        self.i.artist = "trackartist"
        self.i.albumartist = ""
        self.lib.path_formats = [("default", "$albumartist")]
        p = self.i.destination()
        assert p.rsplit(util.PATH_SEP, 1)[1] == b"trackartist"

    def test_artist_overrides_albumartist(self):
        self.i.artist = "theartist"
        self.i.albumartist = "something"
        self.lib.path_formats = [("default", "$artist")]
        p = self.i.destination()
        assert p.rsplit(util.PATH_SEP, 1)[1] == b"theartist"

    def test_albumartist_overrides_artist(self):
        self.i.artist = "theartist"
        self.i.albumartist = "something"
        self.lib.path_formats = [("default", "$albumartist")]
        p = self.i.destination()
        assert p.rsplit(util.PATH_SEP, 1)[1] == b"something"

    def test_unicode_normalized_nfd_on_mac(self):
        instr = unicodedata.normalize("NFC", "caf\xe9")
        self.lib.path_formats = [("default", instr)]
        dest = self.i.destination(platform="darwin", fragment=True)
        assert dest == unicodedata.normalize("NFD", instr)

    def test_unicode_normalized_nfc_on_linux(self):
        instr = unicodedata.normalize("NFD", "caf\xe9")
        self.lib.path_formats = [("default", instr)]
        dest = self.i.destination(platform="linux", fragment=True)
        assert dest == unicodedata.normalize("NFC", instr)

    def test_non_mbcs_characters_on_windows(self):
        oldfunc = sys.getfilesystemencoding
        sys.getfilesystemencoding = lambda: "mbcs"
        try:
            self.i.title = "h\u0259d"
            self.lib.path_formats = [("default", "$title")]
            p = self.i.destination()
            assert b"?" not in p
            # We use UTF-8 to encode Windows paths now.
            assert "h\u0259d".encode() in p
        finally:
            sys.getfilesystemencoding = oldfunc

    def test_unicode_extension_in_fragment(self):
        self.lib.path_formats = [("default", "foo")]
        self.i.path = util.bytestring_path("bar.caf\xe9")
        dest = self.i.destination(platform="linux", fragment=True)
        assert dest == "foo.caf\xe9"

    def test_asciify_and_replace(self):
        config["asciify_paths"] = True
        self.lib.replacements = [(re.compile('"'), "q")]
        self.lib.directory = b"lib"
        self.lib.path_formats = [("default", "$title")]
        self.i.title = "\u201c\u00f6\u2014\u00cf\u201d"
        assert self.i.destination() == np("lib/qo--Iq")

    def test_asciify_character_expanding_to_slash(self):
        config["asciify_paths"] = True
        self.lib.directory = b"lib"
        self.lib.path_formats = [("default", "$title")]
        self.i.title = "ab\xa2\xbdd"
        assert self.i.destination() == np("lib/abC_ 1_2d")

    def test_destination_with_replacements(self):
        self.lib.directory = b"base"
        self.lib.replacements = [(re.compile(r"a"), "e")]
        self.lib.path_formats = [("default", "$album/$title")]
        self.i.title = "foo"
        self.i.album = "bar"
        assert self.i.destination() == np("base/ber/foo")

    def test_destination_with_replacements_argument(self):
        self.lib.directory = b"base"
        self.lib.replacements = [(re.compile(r"a"), "f")]
        self.lib.path_formats = [("default", "$album/$title")]
        self.i.title = "foo"
        self.i.album = "bar"
        replacements = [(re.compile(r"a"), "e")]
        assert self.i.destination(replacements=replacements) == np(
            "base/ber/foo"
        )

    @unittest.skip("unimplemented: #359")
    def test_destination_with_empty_component(self):
        self.lib.directory = b"base"
        self.lib.replacements = [(re.compile(r"^$"), "_")]
        self.lib.path_formats = [("default", "$album/$artist/$title")]
        self.i.title = "three"
        self.i.artist = ""
        self.i.albumartist = ""
        self.i.album = "one"
        assert self.i.destination() == np("base/one/_/three")

    @unittest.skip("unimplemented: #359")
    def test_destination_with_empty_final_component(self):
        self.lib.directory = b"base"
        self.lib.replacements = [(re.compile(r"^$"), "_")]
        self.lib.path_formats = [("default", "$album/$title")]
        self.i.title = ""
        self.i.album = "one"
        self.i.path = "foo.mp3"
        assert self.i.destination() == np("base/one/_.mp3")

    def test_legalize_path_one_for_one_replacement(self):
        # Use a replacement that should always replace the last X in any
        # path component with a Z.
        self.lib.replacements = [
            (re.compile(r"X$"), "Z"),
        ]

        # Construct an item whose untruncated path ends with a Y but whose
        # truncated version ends with an X.
        self.i.title = "X" * 300 + "Y"

        # The final path should reflect the replacement.
        dest = self.i.destination()
        assert dest[-2:] == b"XZ"

    def test_legalize_path_one_for_many_replacement(self):
        # Use a replacement that should always replace the last X in any
        # path component with four Zs.
        self.lib.replacements = [
            (re.compile(r"X$"), "ZZZZ"),
        ]

        # Construct an item whose untruncated path ends with a Y but whose
        # truncated version ends with an X.
        self.i.title = "X" * 300 + "Y"

        # The final path should ignore the user replacement and create a path
        # of the correct length, containing Xs.
        dest = self.i.destination()
        assert dest[-2:] == b"XX"

    def test_album_field_query(self):
        self.lib.directory = b"one"
        self.lib.path_formats = [("default", "two"), ("flex:foo", "three")]
        album = self.lib.add_album([self.i])
        assert self.i.destination() == np("one/two")
        album["flex"] = "foo"
        album.store()
        assert self.i.destination() == np("one/three")

    def test_album_field_in_template(self):
        self.lib.directory = b"one"
        self.lib.path_formats = [("default", "$flex/two")]
        album = self.lib.add_album([self.i])
        album["flex"] = "foo"
        album.store()
        assert self.i.destination() == np("one/foo/two")


class ItemFormattedMappingTest(ItemInDBTestCase):
    def test_formatted_item_value(self):
        formatted = self.i.formatted()
        assert formatted["artist"] == "the artist"

    def test_get_unset_field(self):
        formatted = self.i.formatted()
        with pytest.raises(KeyError):
            formatted["other_field"]

    def test_get_method_with_default(self):
        formatted = self.i.formatted()
        assert formatted.get("other_field") == ""

    def test_get_method_with_specified_default(self):
        formatted = self.i.formatted()
        assert formatted.get("other_field", "default") == "default"

    def test_item_precedence(self):
        album = self.lib.add_album([self.i])
        album["artist"] = "foo"
        album.store()
        assert "foo" != self.i.formatted().get("artist")

    def test_album_flex_field(self):
        album = self.lib.add_album([self.i])
        album["flex"] = "foo"
        album.store()
        assert "foo" == self.i.formatted().get("flex")

    def test_album_field_overrides_item_field_for_path(self):
        # Make the album inconsistent with the item.
        album = self.lib.add_album([self.i])
        album.album = "foo"
        album.store()
        self.i.album = "bar"
        self.i.store()

        # Ensure the album takes precedence.
        formatted = self.i.formatted(for_path=True)
        assert formatted["album"] == "foo"

    def test_artist_falls_back_to_albumartist(self):
        self.i.artist = ""
        formatted = self.i.formatted()
        assert formatted["artist"] == "the album artist"

    def test_albumartist_falls_back_to_artist(self):
        self.i.albumartist = ""
        formatted = self.i.formatted()
        assert formatted["albumartist"] == "the artist"

    def test_both_artist_and_albumartist_empty(self):
        self.i.artist = ""
        self.i.albumartist = ""
        formatted = self.i.formatted()
        assert formatted["albumartist"] == ""


class PathFormattingMixin:
    """Utilities for testing path formatting."""

    def _setf(self, fmt):
        self.lib.path_formats.insert(0, ("default", fmt))

    def _assert_dest(self, dest, i=None):
        if i is None:
            i = self.i
        with _common.platform_posix():
            actual = i.destination()
        assert actual == dest


class DestinationFunctionTest(BeetsTestCase, PathFormattingMixin):
    def setUp(self):
        super().setUp()
        self.lib.directory = b"/base"
        self.lib.path_formats = [("default", "path")]
        self.i = item(self.lib)

    def test_upper_case_literal(self):
        self._setf("%upper{foo}")
        self._assert_dest(b"/base/FOO")

    def test_upper_case_variable(self):
        self._setf("%upper{$title}")
        self._assert_dest(b"/base/THE TITLE")

    def test_capitalize_variable(self):
        self._setf("%capitalize{$title}")
        self._assert_dest(b"/base/The title")

    def test_title_case_variable(self):
        self._setf("%title{$title}")
        self._assert_dest(b"/base/The Title")

    def test_title_case_variable_aphostrophe(self):
        self._setf("%title{I can't}")
        self._assert_dest(b"/base/I Can't")

    def test_asciify_variable(self):
        self._setf("%asciify{ab\xa2\xbdd}")
        self._assert_dest(b"/base/abC_ 1_2d")

    def test_left_variable(self):
        self._setf("%left{$title, 3}")
        self._assert_dest(b"/base/the")

    def test_right_variable(self):
        self._setf("%right{$title,3}")
        self._assert_dest(b"/base/tle")

    def test_if_false(self):
        self._setf("x%if{,foo}")
        self._assert_dest(b"/base/x")

    def test_if_false_value(self):
        self._setf("x%if{false,foo}")
        self._assert_dest(b"/base/x")

    def test_if_true(self):
        self._setf("%if{bar,foo}")
        self._assert_dest(b"/base/foo")

    def test_if_else_false(self):
        self._setf("%if{,foo,baz}")
        self._assert_dest(b"/base/baz")

    def test_if_else_false_value(self):
        self._setf("%if{false,foo,baz}")
        self._assert_dest(b"/base/baz")

    def test_if_int_value(self):
        self._setf("%if{0,foo,baz}")
        self._assert_dest(b"/base/baz")

    def test_nonexistent_function(self):
        self._setf("%foo{bar}")
        self._assert_dest(b"/base/%foo{bar}")

    def test_if_def_field_return_self(self):
        self.i.bar = 3
        self._setf("%ifdef{bar}")
        self._assert_dest(b"/base/3")

    def test_if_def_field_not_defined(self):
        self._setf(" %ifdef{bar}/$artist")
        self._assert_dest(b"/base/the artist")

    def test_if_def_field_not_defined_2(self):
        self._setf("$artist/%ifdef{bar}")
        self._assert_dest(b"/base/the artist")

    def test_if_def_true(self):
        self._setf("%ifdef{artist,cool}")
        self._assert_dest(b"/base/cool")

    def test_if_def_true_complete(self):
        self.i.series = "Now"
        self._setf("%ifdef{series,$series Series,Albums}/$album")
        self._assert_dest(b"/base/Now Series/the album")

    def test_if_def_false_complete(self):
        self._setf("%ifdef{plays,$plays,not_played}")
        self._assert_dest(b"/base/not_played")

    def test_first(self):
        self.i.genres = "Pop; Rock; Classical Crossover"
        self._setf("%first{$genres}")
        self._assert_dest(b"/base/Pop")

    def test_first_skip(self):
        self.i.genres = "Pop; Rock; Classical Crossover"
        self._setf("%first{$genres,1,2}")
        self._assert_dest(b"/base/Classical Crossover")

    def test_first_different_sep(self):
        self._setf("%first{Alice / Bob / Eve,2,0, / , & }")
        self._assert_dest(b"/base/Alice & Bob")


class DisambiguationTest(BeetsTestCase, PathFormattingMixin):
    def setUp(self):
        super().setUp()
        self.lib.directory = b"/base"
        self.lib.path_formats = [("default", "path")]

        self.i1 = item()
        self.i1.year = 2001
        self.lib.add_album([self.i1])
        self.i2 = item()
        self.i2.year = 2002
        self.lib.add_album([self.i2])
        self.lib._connection().commit()

        self._setf("foo%aunique{albumartist album,year}/$title")

    def test_unique_expands_to_disambiguating_year(self):
        self._assert_dest(b"/base/foo [2001]/the title", self.i1)

    def test_unique_with_default_arguments_uses_albumtype(self):
        album2 = self.lib.get_album(self.i1)
        album2.albumtype = "bar"
        album2.store()
        self._setf("foo%aunique{}/$title")
        self._assert_dest(b"/base/foo [bar]/the title", self.i1)

    def test_unique_expands_to_nothing_for_distinct_albums(self):
        album2 = self.lib.get_album(self.i2)
        album2.album = "different album"
        album2.store()

        self._assert_dest(b"/base/foo/the title", self.i1)

    def test_use_fallback_numbers_when_identical(self):
        album2 = self.lib.get_album(self.i2)
        album2.year = 2001
        album2.store()

        self._assert_dest(b"/base/foo [1]/the title", self.i1)
        self._assert_dest(b"/base/foo [2]/the title", self.i2)

    def test_unique_falls_back_to_second_distinguishing_field(self):
        self._setf("foo%aunique{albumartist album,month year}/$title")
        self._assert_dest(b"/base/foo [2001]/the title", self.i1)

    def test_unique_sanitized(self):
        album2 = self.lib.get_album(self.i2)
        album2.year = 2001
        album1 = self.lib.get_album(self.i1)
        album1.albumtype = "foo/bar"
        album2.store()
        album1.store()
        self._setf("foo%aunique{albumartist album,albumtype}/$title")
        self._assert_dest(b"/base/foo [foo_bar]/the title", self.i1)

    def test_drop_empty_disambig_string(self):
        album1 = self.lib.get_album(self.i1)
        album1.albumdisambig = None
        album2 = self.lib.get_album(self.i2)
        album2.albumdisambig = "foo"
        album1.store()
        album2.store()
        self._setf("foo%aunique{albumartist album,albumdisambig}/$title")
        self._assert_dest(b"/base/foo/the title", self.i1)

    def test_change_brackets(self):
        self._setf("foo%aunique{albumartist album,year,()}/$title")
        self._assert_dest(b"/base/foo (2001)/the title", self.i1)

    def test_remove_brackets(self):
        self._setf("foo%aunique{albumartist album,year,}/$title")
        self._assert_dest(b"/base/foo 2001/the title", self.i1)

    def test_key_flexible_attribute(self):
        album1 = self.lib.get_album(self.i1)
        album1.flex = "flex1"
        album2 = self.lib.get_album(self.i2)
        album2.flex = "flex2"
        album1.store()
        album2.store()
        self._setf("foo%aunique{albumartist album flex,year}/$title")
        self._assert_dest(b"/base/foo/the title", self.i1)


class SingletonDisambiguationTest(BeetsTestCase, PathFormattingMixin):
    def setUp(self):
        super().setUp()
        self.lib.directory = b"/base"
        self.lib.path_formats = [("default", "path")]

        self.i1 = item()
        self.i1.year = 2001
        self.lib.add(self.i1)
        self.i2 = item()
        self.i2.year = 2002
        self.lib.add(self.i2)
        self.lib._connection().commit()

        self._setf("foo/$title%sunique{artist title,year}")

    def test_sunique_expands_to_disambiguating_year(self):
        self._assert_dest(b"/base/foo/the title [2001]", self.i1)

    def test_sunique_with_default_arguments_uses_trackdisambig(self):
        self.i1.trackdisambig = "live version"
        self.i1.year = self.i2.year
        self.i1.store()
        self._setf("foo/$title%sunique{}")
        self._assert_dest(b"/base/foo/the title [live version]", self.i1)

    def test_sunique_expands_to_nothing_for_distinct_singletons(self):
        self.i2.title = "different track"
        self.i2.store()

        self._assert_dest(b"/base/foo/the title", self.i1)

    def test_sunique_does_not_match_album(self):
        self.lib.add_album([self.i2])
        self._assert_dest(b"/base/foo/the title", self.i1)

    def test_sunique_use_fallback_numbers_when_identical(self):
        self.i2.year = self.i1.year
        self.i2.store()

        self._assert_dest(b"/base/foo/the title [1]", self.i1)
        self._assert_dest(b"/base/foo/the title [2]", self.i2)

    def test_sunique_falls_back_to_second_distinguishing_field(self):
        self._setf("foo/$title%sunique{albumartist album,month year}")
        self._assert_dest(b"/base/foo/the title [2001]", self.i1)

    def test_sunique_sanitized(self):
        self.i2.year = self.i1.year
        self.i1.trackdisambig = "foo/bar"
        self.i2.store()
        self.i1.store()
        self._setf("foo/$title%sunique{artist title,trackdisambig}")
        self._assert_dest(b"/base/foo/the title [foo_bar]", self.i1)

    def test_drop_empty_disambig_string(self):
        self.i1.trackdisambig = None
        self.i2.trackdisambig = "foo"
        self.i1.store()
        self.i2.store()
        self._setf("foo/$title%sunique{albumartist album,trackdisambig}")
        self._assert_dest(b"/base/foo/the title", self.i1)

    def test_change_brackets(self):
        self._setf("foo/$title%sunique{artist title,year,()}")
        self._assert_dest(b"/base/foo/the title (2001)", self.i1)

    def test_remove_brackets(self):
        self._setf("foo/$title%sunique{artist title,year,}")
        self._assert_dest(b"/base/foo/the title 2001", self.i1)

    def test_key_flexible_attribute(self):
        self.i1.flex = "flex1"
        self.i2.flex = "flex2"
        self.i1.store()
        self.i2.store()
        self._setf("foo/$title%sunique{artist title flex,year}")
        self._assert_dest(b"/base/foo/the title", self.i1)


class PluginDestinationTest(BeetsTestCase):
    def setUp(self):
        super().setUp()

        # Mock beets.plugins.item_field_getters.
        self._tv_map = {}

        def field_getters():
            getters = {}
            for key, value in self._tv_map.items():
                getters[key] = lambda _: value
            return getters

        self.old_field_getters = plugins.item_field_getters
        plugins.item_field_getters = field_getters

        self.lib.directory = b"/base"
        self.lib.path_formats = [("default", "$artist $foo")]
        self.i = item(self.lib)

    def tearDown(self):
        super().tearDown()
        plugins.item_field_getters = self.old_field_getters

    def _assert_dest(self, dest):
        with _common.platform_posix():
            the_dest = self.i.destination()
        assert the_dest == b"/base/" + dest

    def test_undefined_value_not_substituted(self):
        self._assert_dest(b"the artist $foo")

    def test_plugin_value_not_substituted(self):
        self._tv_map = {
            "foo": "bar",
        }
        self._assert_dest(b"the artist bar")

    def test_plugin_value_overrides_attribute(self):
        self._tv_map = {
            "artist": "bar",
        }
        self._assert_dest(b"bar $foo")

    def test_plugin_value_sanitized(self):
        self._tv_map = {
            "foo": "bar/baz",
        }
        self._assert_dest(b"the artist bar_baz")


class AlbumInfoTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.i = item()
        self.lib.add_album((self.i,))

    def test_albuminfo_reflects_metadata(self):
        ai = self.lib.get_album(self.i)
        assert ai.mb_albumartistid == self.i.mb_albumartistid
        assert ai.albumartist == self.i.albumartist
        assert ai.album == self.i.album
        assert ai.year == self.i.year

    def test_albuminfo_stores_art(self):
        ai = self.lib.get_album(self.i)
        ai.artpath = "/my/great/art"
        ai.store()
        new_ai = self.lib.get_album(self.i)
        assert new_ai.artpath == b"/my/great/art"

    def test_albuminfo_for_two_items_doesnt_duplicate_row(self):
        i2 = item(self.lib)
        self.lib.get_album(self.i)
        self.lib.get_album(i2)

        c = self.lib._connection().cursor()
        c.execute("select * from albums where album=?", (self.i.album,))
        # Cursor should only return one row.
        assert c.fetchone() is not None
        assert c.fetchone() is None

    def test_individual_tracks_have_no_albuminfo(self):
        i2 = item()
        i2.album = "aTotallyDifferentAlbum"
        self.lib.add(i2)
        ai = self.lib.get_album(i2)
        assert ai is None

    def test_get_album_by_id(self):
        ai = self.lib.get_album(self.i)
        ai = self.lib.get_album(self.i.id)
        assert ai is not None

    def test_album_items_consistent(self):
        ai = self.lib.get_album(self.i)
        for i in ai.items():
            if i.id == self.i.id:
                break
        else:
            self.fail("item not found")

    def test_albuminfo_changes_affect_items(self):
        ai = self.lib.get_album(self.i)
        ai.album = "myNewAlbum"
        ai.store()
        i = self.lib.items()[0]
        assert i.album == "myNewAlbum"

    def test_albuminfo_change_albumartist_changes_items(self):
        ai = self.lib.get_album(self.i)
        ai.albumartist = "myNewArtist"
        ai.store()
        i = self.lib.items()[0]
        assert i.albumartist == "myNewArtist"
        assert i.artist != "myNewArtist"

    def test_albuminfo_change_artist_does_change_items(self):
        ai = self.lib.get_album(self.i)
        ai.artist = "myNewArtist"
        ai.store(inherit=True)
        i = self.lib.items()[0]
        assert i.artist == "myNewArtist"

    def test_albuminfo_change_artist_does_not_change_items(self):
        ai = self.lib.get_album(self.i)
        ai.artist = "myNewArtist"
        ai.store(inherit=False)
        i = self.lib.items()[0]
        assert i.artist != "myNewArtist"

    def test_albuminfo_remove_removes_items(self):
        item_id = self.i.id
        self.lib.get_album(self.i).remove()
        c = self.lib._connection().execute(
            "SELECT id FROM items WHERE id=?", (item_id,)
        )
        assert c.fetchone() is None

    def test_removing_last_item_removes_album(self):
        assert len(self.lib.albums()) == 1
        self.i.remove()
        assert len(self.lib.albums()) == 0

    def test_noop_albuminfo_changes_affect_items(self):
        i = self.lib.items()[0]
        i.album = "foobar"
        i.store()
        ai = self.lib.get_album(self.i)
        ai.album = ai.album
        ai.store()
        i = self.lib.items()[0]
        assert i.album == ai.album


class ArtDestinationTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        config["art_filename"] = "artimage"
        config["replace"] = {"X": "Y"}
        self.lib.replacements = [(re.compile("X"), "Y")]
        self.i = item(self.lib)
        self.i.path = self.i.destination()
        self.ai = self.lib.add_album((self.i,))

    def test_art_filename_respects_setting(self):
        art = self.ai.art_destination("something.jpg")
        new_art = bytestring_path("%sartimage.jpg" % os.path.sep)
        assert new_art in art

    def test_art_path_in_item_dir(self):
        art = self.ai.art_destination("something.jpg")
        track = self.i.destination()
        assert os.path.dirname(art) == os.path.dirname(track)

    def test_art_path_sanitized(self):
        config["art_filename"] = "artXimage"
        art = self.ai.art_destination("something.jpg")
        assert b"artYimage" in art


class PathStringTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.i = item(self.lib)

    def test_item_path_is_bytestring(self):
        assert isinstance(self.i.path, bytes)

    def test_fetched_item_path_is_bytestring(self):
        i = list(self.lib.items())[0]
        assert isinstance(i.path, bytes)

    def test_unicode_path_becomes_bytestring(self):
        self.i.path = "unicodepath"
        assert isinstance(self.i.path, bytes)

    def test_unicode_in_database_becomes_bytestring(self):
        self.lib._connection().execute(
            """
        update items set path=? where id=?
        """,
            (self.i.id, "somepath"),
        )
        i = list(self.lib.items())[0]
        assert isinstance(i.path, bytes)

    def test_special_chars_preserved_in_database(self):
        path = "b\xe1r".encode()
        self.i.path = path
        self.i.store()
        i = list(self.lib.items())[0]
        assert i.path == path

    def test_special_char_path_added_to_database(self):
        self.i.remove()
        path = "b\xe1r".encode()
        i = item()
        i.path = path
        self.lib.add(i)
        i = list(self.lib.items())[0]
        assert i.path == path

    def test_destination_returns_bytestring(self):
        self.i.artist = "b\xe1r"
        dest = self.i.destination()
        assert isinstance(dest, bytes)

    def test_art_destination_returns_bytestring(self):
        self.i.artist = "b\xe1r"
        alb = self.lib.add_album([self.i])
        dest = alb.art_destination("image.jpg")
        assert isinstance(dest, bytes)

    def test_artpath_stores_special_chars(self):
        path = b"b\xe1r"
        alb = self.lib.add_album([self.i])
        alb.artpath = path
        alb.store()
        alb = self.lib.get_album(self.i)
        assert path == alb.artpath

    def test_sanitize_path_with_special_chars(self):
        path = "b\xe1r?"
        new_path = util.sanitize_path(path)
        assert new_path.startswith("b\xe1r")

    def test_sanitize_path_returns_unicode(self):
        path = "b\xe1r?"
        new_path = util.sanitize_path(path)
        assert isinstance(new_path, str)

    def test_unicode_artpath_becomes_bytestring(self):
        alb = self.lib.add_album([self.i])
        alb.artpath = "somep\xe1th"
        assert isinstance(alb.artpath, bytes)

    def test_unicode_artpath_in_database_decoded(self):
        alb = self.lib.add_album([self.i])
        self.lib._connection().execute(
            "update albums set artpath=? where id=?", ("somep\xe1th", alb.id)
        )
        alb = self.lib.get_album(alb.id)
        assert isinstance(alb.artpath, bytes)


class MtimeTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.ipath = os.path.join(self.temp_dir, b"testfile.mp3")
        shutil.copy(
            syspath(os.path.join(_common.RSRC, b"full.mp3")),
            syspath(self.ipath),
        )
        self.i = beets.library.Item.from_path(self.ipath)
        self.lib.add(self.i)

    def tearDown(self):
        super().tearDown()
        if os.path.exists(self.ipath):
            os.remove(self.ipath)

    def _mtime(self):
        return int(os.path.getmtime(self.ipath))

    def test_mtime_initially_up_to_date(self):
        assert self.i.mtime >= self._mtime()

    def test_mtime_reset_on_db_modify(self):
        self.i.title = "something else"
        assert self.i.mtime < self._mtime()

    def test_mtime_up_to_date_after_write(self):
        self.i.title = "something else"
        self.i.write()
        assert self.i.mtime >= self._mtime()

    def test_mtime_up_to_date_after_read(self):
        self.i.title = "something else"
        self.i.read()
        assert self.i.mtime >= self._mtime()


class ImportTimeTest(BeetsTestCase):
    def added(self):
        self.track = item()
        self.album = self.lib.add_album((self.track,))
        assert self.album.added > 0
        assert self.track.added > 0

    def test_atime_for_singleton(self):
        self.singleton = item(self.lib)
        assert self.singleton.added > 0


class TemplateTest(ItemInDBTestCase):
    def test_year_formatted_in_template(self):
        self.i.year = 123
        self.i.store()
        assert self.i.evaluate_template("$year") == "0123"

    def test_album_flexattr_appears_in_item_template(self):
        self.album = self.lib.add_album([self.i])
        self.album.foo = "baz"
        self.album.store()
        assert self.i.evaluate_template("$foo") == "baz"

    def test_album_and_item_format(self):
        config["format_album"] = "foö $foo"
        album = beets.library.Album()
        album.foo = "bar"
        album.tagada = "togodo"
        assert f"{album}" == "foö bar"
        assert f"{album:$tagada}" == "togodo"
        assert str(album) == "foö bar"
        assert bytes(album) == b"fo\xc3\xb6 bar"

        config["format_item"] = "bar $foo"
        item = beets.library.Item()
        item.foo = "bar"
        item.tagada = "togodo"
        assert f"{item}" == "bar bar"
        assert f"{item:$tagada}" == "togodo"


class UnicodePathTest(ItemInDBTestCase):
    def test_unicode_path(self):
        self.i.path = os.path.join(_common.RSRC, "unicode\u2019d.mp3".encode())
        # If there are any problems with unicode paths, we will raise
        # here and fail.
        self.i.read()
        self.i.write()


class WriteTest(BeetsTestCase):
    def test_write_nonexistant(self):
        item = self.create_item()
        item.path = b"/path/does/not/exist"
        with pytest.raises(beets.library.ReadError):
            item.write()

    def test_no_write_permission(self):
        item = self.add_item_fixture()
        path = syspath(item.path)
        os.chmod(path, stat.S_IRUSR)

        try:
            with pytest.raises(beets.library.WriteError):
                item.write()

        finally:
            # Restore write permissions so the file can be cleaned up.
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    def test_write_with_custom_path(self):
        item = self.add_item_fixture()
        custom_path = os.path.join(self.temp_dir, b"custom.mp3")
        shutil.copy(syspath(item.path), syspath(custom_path))

        item["artist"] = "new artist"
        assert MediaFile(syspath(custom_path)).artist != "new artist"
        assert MediaFile(syspath(item.path)).artist != "new artist"

        item.write(custom_path)
        assert MediaFile(syspath(custom_path)).artist == "new artist"
        assert MediaFile(syspath(item.path)).artist != "new artist"

    def test_write_custom_tags(self):
        item = self.add_item_fixture(artist="old artist")
        item.write(tags={"artist": "new artist"})
        assert item.artist != "new artist"
        assert MediaFile(syspath(item.path)).artist == "new artist"

    def test_write_multi_tags(self):
        item = self.add_item_fixture(artist="old artist")
        item.write(tags={"artists": ["old artist", "another artist"]})

        assert MediaFile(syspath(item.path)).artists == [
            "old artist",
            "another artist",
        ]

    def test_write_multi_tags_id3v23(self):
        item = self.add_item_fixture(artist="old artist")
        item.write(
            tags={"artists": ["old artist", "another artist"]}, id3v23=True
        )

        assert MediaFile(syspath(item.path)).artists == [
            "old artist/another artist"
        ]

    def test_write_date_field(self):
        # Since `date` is not a MediaField, this should do nothing.
        item = self.add_item_fixture()
        clean_year = item.year
        item.date = "foo"
        item.write()
        assert MediaFile(syspath(item.path)).year == clean_year


class ItemReadTest(unittest.TestCase):
    def test_unreadable_raise_read_error(self):
        unreadable = os.path.join(_common.RSRC, b"image-2x3.png")
        item = beets.library.Item()
        with pytest.raises(beets.library.ReadError) as exc_info:
            item.read(unreadable)
        assert isinstance(exc_info.value.reason, UnreadableFileError)

    def test_nonexistent_raise_read_error(self):
        item = beets.library.Item()
        with pytest.raises(beets.library.ReadError):
            item.read("/thisfiledoesnotexist")


class FilesizeTest(BeetsTestCase):
    def test_filesize(self):
        item = self.add_item_fixture()
        assert item.filesize != 0

    def test_nonexistent_file(self):
        item = beets.library.Item()
        assert item.filesize == 0


class ParseQueryTest(unittest.TestCase):
    def test_parse_invalid_query_string(self):
        with pytest.raises(beets.dbcore.query.ParsingError):
            beets.library.parse_query_string('foo"', None)

    def test_parse_bytes(self):
        with pytest.raises(AssertionError):
            beets.library.parse_query_string(b"query", None)


class LibraryFieldTypesTest(unittest.TestCase):
    """Test format() and parse() for library-specific field types"""

    def test_datetype(self):
        t = beets.library.DateType()

        # format
        time_format = beets.config["time_format"].as_str()
        time_local = time.strftime(time_format, time.localtime(123456789))
        assert time_local == t.format(123456789)
        # parse
        assert 123456789.0 == t.parse(time_local)
        assert 123456789.0 == t.parse("123456789.0")
        assert t.null == t.parse("not123456789.0")
        assert t.null == t.parse("1973-11-29")

    def test_pathtype(self):
        t = beets.library.PathType()

        # format
        assert "/tmp" == t.format("/tmp")
        assert "/tmp/\xe4lbum" == t.format("/tmp/\u00e4lbum")
        # parse
        assert np(b"/tmp") == t.parse("/tmp")
        assert np(b"/tmp/\xc3\xa4lbum") == t.parse("/tmp/\u00e4lbum/")

    def test_musicalkey(self):
        t = beets.library.MusicalKey()

        # parse
        assert "C#m" == t.parse("c#m")
        assert "Gm" == t.parse("g   minor")
        assert "Not c#m" == t.parse("not C#m")

    def test_durationtype(self):
        t = beets.library.DurationType()

        # format
        assert "1:01" == t.format(61.23)
        assert "60:01" == t.format(3601.23)
        assert "0:00" == t.format(None)
        # parse
        assert 61.0 == t.parse("1:01")
        assert 61.23 == t.parse("61.23")
        assert 3601.0 == t.parse("60:01")
        assert t.null == t.parse("1:00:01")
        assert t.null == t.parse("not61.23")
        # config format_raw_length
        beets.config["format_raw_length"] = True
        assert 61.23 == t.format(61.23)
        assert 3601.23 == t.format(3601.23)
