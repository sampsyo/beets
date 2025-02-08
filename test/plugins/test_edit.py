# This file is part of beets.
# Copyright 2016, Adrian Sampson and Diego Moreda.
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

import codecs
from unittest.mock import patch

from beets.dbcore.query import TrueQuery
from beets.library import Item
from beets.test import _common
from beets.test.helper import (
    AutotagStub,
    BeetsTestCase,
    ImportTestCase,
    PluginMixin,
    TerminalImportMixin,
    control_stdin,
)


class ModifyFileMocker:
    """Helper for modifying a file, replacing or editing its contents. Used for
    mocking the calls to the external editor during testing.
    """

    def __init__(self, contents=None, replacements=None):
        """`self.contents` and `self.replacements` are initialized here, in
        order to keep the rest of the functions of this class with the same
        signature as `EditPlugin.get_editor()`, making mocking easier.
            - `contents`: string with the contents of the file to be used for
            `overwrite_contents()`
            - `replacement`: dict with the in-place replacements to be used for
            `replace_contents()`, in the form {'previous string': 'new string'}

        TODO: check if it can be solved more elegantly with a decorator
        """
        self.contents = contents
        self.replacements = replacements
        self.action = self.overwrite_contents
        if replacements:
            self.action = self.replace_contents

    # The two methods below mock the `edit` utility function in the plugin.

    def overwrite_contents(self, filename, log):
        """Modify `filename`, replacing its contents with `self.contents`. If
        `self.contents` is empty, the file remains unchanged.
        """
        if self.contents:
            with codecs.open(filename, "w", encoding="utf-8") as f:
                f.write(self.contents)

    def replace_contents(self, filename, log):
        """Modify `filename`, reading its contents and replacing the strings
        specified in `self.replacements`.
        """
        with codecs.open(filename, "r", encoding="utf-8") as f:
            contents = f.read()
        for old, new_ in self.replacements.items():
            contents = contents.replace(old, new_)
        with codecs.open(filename, "w", encoding="utf-8") as f:
            f.write(contents)


class EditMixin(PluginMixin):
    """Helper containing some common functionality used for the Edit tests."""

    plugin = "edit"

    def assertItemFieldsModified(
        self, library_items, items, fields=[], allowed=["path"]
    ):
        """Assert that items in the library (`lib_items`) have different values
        on the specified `fields` (and *only* on those fields), compared to
        `items`.

        An empty `fields` list results in asserting that no modifications have
        been performed. `allowed` is a list of field changes that are ignored
        (they may or may not have changed; the assertion doesn't care).
        """
        for lib_item, item in zip(library_items, items):
            diff_fields = [
                field
                for field in lib_item._fields
                if lib_item[field] != item[field]
            ]
            assert set(diff_fields).difference(allowed) == set(fields)

    def run_mocked_interpreter(self, modify_file_args={}, stdin=[]):
        """Run the edit command during an import session, with mocked stdin and
        yaml writing.
        """
        m = ModifyFileMocker(**modify_file_args)
        with patch("beetsplug.edit.edit", side_effect=m.action):
            with control_stdin("\n".join(stdin)):
                self.importer.run()

    def run_mocked_command(self, modify_file_args={}, stdin=[], args=[]):
        """Run the edit command, with mocked stdin and yaml writing, and
        passing `args` to `run_command`."""
        m = ModifyFileMocker(**modify_file_args)
        with patch("beetsplug.edit.edit", side_effect=m.action):
            with control_stdin("\n".join(stdin)):
                self.run_command("edit", *args)


@_common.slow_test()
@patch("beets.library.Item.write")
class EditCommandTest(EditMixin, BeetsTestCase):
    """Black box tests for `beetsplug.edit`. Command line interaction is
    simulated using `test.helper.control_stdin()`, and yaml editing via an
    external editor is simulated using `ModifyFileMocker`.
    """

    ALBUM_COUNT = 1
    TRACK_COUNT = 10

    def setUp(self):
        super().setUp()
        # Add an album, storing the original fields for comparison.
        self.album = self.add_album_fixture(track_count=self.TRACK_COUNT)
        self.album_orig = {f: self.album[f] for f in self.album._fields}
        self.items_orig = [
            {f: item[f] for f in item._fields} for item in self.album.items()
        ]

    def assertCounts(
        self,
        mock_write,
        album_count=ALBUM_COUNT,
        track_count=TRACK_COUNT,
        write_call_count=TRACK_COUNT,
        title_starts_with="",
    ):
        """Several common assertions on Album, Track and call counts."""
        assert len(self.lib.albums()) == album_count
        assert len(self.lib.items()) == track_count
        assert mock_write.call_count == write_call_count
        assert all(
            i.title.startswith(title_starts_with) for i in self.lib.items()
        )

    def test_title_edit_discard(self, mock_write):
        """Edit title for all items in the library, then discard changes."""
        # Edit track titles.
        self.run_mocked_command(
            {"replacements": {"t\u00eftle": "modified t\u00eftle"}},
            # Cancel.
            ["c"],
        )

        self.assertCounts(
            mock_write, write_call_count=0, title_starts_with="t\u00eftle"
        )
        self.assertItemFieldsModified(self.album.items(), self.items_orig, [])

    def test_title_edit_apply(self, mock_write):
        """Edit title for all items in the library, then apply changes."""
        # Edit track titles.
        self.run_mocked_command(
            {"replacements": {"t\u00eftle": "modified t\u00eftle"}},
            # Apply changes.
            ["a"],
        )

        self.assertCounts(
            mock_write,
            write_call_count=self.TRACK_COUNT,
            title_starts_with="modified t\u00eftle",
        )
        self.assertItemFieldsModified(
            self.album.items(), self.items_orig, ["title", "mtime"]
        )

    def test_single_title_edit_apply(self, mock_write):
        """Edit title for one item in the library, then apply changes."""
        # Edit one track title.
        self.run_mocked_command(
            {"replacements": {"t\u00eftle 9": "modified t\u00eftle 9"}},
            # Apply changes.
            ["a"],
        )

        self.assertCounts(
            mock_write,
            write_call_count=1,
        )
        # No changes except on last item.
        self.assertItemFieldsModified(
            list(self.album.items())[:-1], self.items_orig[:-1], []
        )
        assert list(self.album.items())[-1].title == "modified t\u00eftle 9"

    def test_noedit(self, mock_write):
        """Do not edit anything."""
        # Do not edit anything.
        self.run_mocked_command(
            {"contents": None},
            # No stdin.
            [],
        )

        self.assertCounts(
            mock_write, write_call_count=0, title_starts_with="t\u00eftle"
        )
        self.assertItemFieldsModified(self.album.items(), self.items_orig, [])

    def test_album_edit_apply(self, mock_write):
        """Edit the album field for all items in the library, apply changes.
        By design, the album should not be updated.""
        """
        # Edit album.
        self.run_mocked_command(
            {"replacements": {"\u00e4lbum": "modified \u00e4lbum"}},
            # Apply changes.
            ["a"],
        )

        self.assertCounts(mock_write, write_call_count=self.TRACK_COUNT)
        self.assertItemFieldsModified(
            self.album.items(), self.items_orig, ["album", "mtime"]
        )
        # Ensure album is *not* modified.
        self.album.load()
        assert self.album.album == "\u00e4lbum"

    def test_single_edit_add_field(self, mock_write):
        """Edit the yaml file appending an extra field to the first item, then
        apply changes."""
        # Append "foo: bar" to item with id == 2. ("id: 1" would match both
        # "id: 1" and "id: 10")
        self.run_mocked_command(
            {"replacements": {"id: 2": "id: 2\nfoo: bar"}},
            # Apply changes.
            ["a"],
        )

        assert self.lib.items("id:2")[0].foo == "bar"
        # Even though a flexible attribute was written (which is not directly
        # written to the tags), write should still be called since templates
        # might use it.
        self.assertCounts(
            mock_write, write_call_count=1, title_starts_with="t\u00eftle"
        )

    def test_a_album_edit_apply(self, mock_write):
        """Album query (-a), edit album field, apply changes."""
        self.run_mocked_command(
            {"replacements": {"\u00e4lbum": "modified \u00e4lbum"}},
            # Apply changes.
            ["a"],
            args=["-a"],
        )

        self.album.load()
        self.assertCounts(mock_write, write_call_count=self.TRACK_COUNT)
        assert self.album.album == "modified \u00e4lbum"
        self.assertItemFieldsModified(
            self.album.items(), self.items_orig, ["album", "mtime"]
        )

    def test_a_albumartist_edit_apply(self, mock_write):
        """Album query (-a), edit albumartist field, apply changes."""
        self.run_mocked_command(
            {"replacements": {"album artist": "modified album artist"}},
            # Apply changes.
            ["a"],
            args=["-a"],
        )

        self.album.load()
        self.assertCounts(mock_write, write_call_count=self.TRACK_COUNT)
        assert self.album.albumartist == "the modified album artist"
        self.assertItemFieldsModified(
            self.album.items(), self.items_orig, ["albumartist", "mtime"]
        )

    def test_malformed_yaml(self, mock_write):
        """Edit the yaml file incorrectly (resulting in a malformed yaml
        document)."""
        # Edit the yaml file to an invalid file.
        self.run_mocked_command(
            {"contents": "!MALFORMED"},
            # Edit again to fix? No.
            ["n"],
        )

        self.assertCounts(
            mock_write, write_call_count=0, title_starts_with="t\u00eftle"
        )

    def test_invalid_yaml(self, mock_write):
        """Edit the yaml file incorrectly (resulting in a well-formed but
        invalid yaml document)."""
        # Edit the yaml file to an invalid but parseable file.
        self.run_mocked_command(
            {"contents": "wellformed: yes, but invalid"},
            # No stdin.
            [],
        )

        self.assertCounts(
            mock_write, write_call_count=0, title_starts_with="t\u00eftle"
        )


@_common.slow_test()
class EditDuringImporterTestCase(
    EditMixin, TerminalImportMixin, ImportTestCase
):
    """TODO"""

    IGNORED = ["added", "album_id", "id", "mtime", "path"]

    def setUp(self):
        super().setUp()
        # Create some mediafiles, and store them for comparison.
        self.prepare_album_for_import(1)
        self.items_orig = [Item.from_path(f.path) for f in self.import_media]
        self.matcher = AutotagStub().install()
        self.matcher.matching = AutotagStub.GOOD

    def tearDown(self):
        super().tearDown()
        self.matcher.restore()


@_common.slow_test()
class EditDuringImporterNonSingletonTest(EditDuringImporterTestCase):
    def setUp(self):
        super().setUp()
        self.importer = self.setup_importer()

    def test_edit_apply_asis(self):
        """Edit the album field for all items in the library, apply changes,
        using the original item tags.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Tag Track": "Edited Track"}},
            # eDit, Apply changes.
            ["d", "a"],
        )

        # Check that only the 'title' field is modified.
        self.assertItemFieldsModified(
            self.lib.items(),
            self.items_orig,
            ["title"],
            self.IGNORED
            + [
                "albumartist",
                "mb_albumartistid",
                "mb_albumartistids",
            ],
        )
        assert all("Edited Track" in i.title for i in self.lib.items())

        # Ensure album is *not* fetched from a candidate.
        assert self.lib.albums()[0].mb_albumid == ""

    def test_edit_discard_asis(self):
        """Edit the album field for all items in the library, discard changes,
        using the original item tags.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Tag Track": "Edited Track"}},
            # eDit, Cancel, Use as-is.
            ["d", "c", "u"],
        )

        # Check that nothing is modified, the album is imported ASIS.
        self.assertItemFieldsModified(
            self.lib.items(),
            self.items_orig,
            [],
            self.IGNORED + ["albumartist", "mb_albumartistid"],
        )
        assert all("Tag Track" in i.title for i in self.lib.items())

        # Ensure album is *not* fetched from a candidate.
        assert self.lib.albums()[0].mb_albumid == ""

    def test_edit_apply_candidate(self):
        """Edit the album field for all items in the library, apply changes,
        using a candidate.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Applied Track": "Edited Track"}},
            # edit Candidates, 1, Apply changes.
            ["c", "1", "a"],
        )

        # Check that 'title' field is modified, and other fields come from
        # the candidate.
        assert all("Edited Track " in i.title for i in self.lib.items())
        assert all("match " in i.mb_trackid for i in self.lib.items())

        # Ensure album is fetched from a candidate.
        assert "albumid" in self.lib.albums()[0].mb_albumid

    def test_edit_retag_apply(self):
        """Import the album using a candidate, then retag and edit and apply
        changes.
        """
        self.run_mocked_interpreter(
            {},
            # 1, Apply changes.
            ["1", "a"],
        )

        # Retag and edit track titles.  On retag, the importer will reset items
        # ids but not the db connections.
        self.importer.paths = []
        self.importer.query = TrueQuery()
        self.run_mocked_interpreter(
            {"replacements": {"Applied Track": "Edited Track"}},
            # eDit, Apply changes.
            ["d", "a"],
        )

        # Check that 'title' field is modified, and other fields come from
        # the candidate.
        assert all("Edited Track " in i.title for i in self.lib.items())
        assert all("match " in i.mb_trackid for i in self.lib.items())

        # Ensure album is fetched from a candidate.
        assert "albumid" in self.lib.albums()[0].mb_albumid

    def test_edit_discard_candidate(self):
        """Edit the album field for all items in the library, discard changes,
        using a candidate.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Applied Track": "Edited Track"}},
            # edit Candidates, 1, Apply changes.
            ["c", "1", "a"],
        )

        # Check that 'title' field is modified, and other fields come from
        # the candidate.
        assert all("Edited Track " in i.title for i in self.lib.items())
        assert all("match " in i.mb_trackid for i in self.lib.items())

        # Ensure album is fetched from a candidate.
        assert "albumid" in self.lib.albums()[0].mb_albumid

    def test_edit_apply_candidate_singleton(self):
        """Edit the album field for all items in the library, apply changes,
        using a candidate and singleton mode.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Applied Track": "Edited Track"}},
            # edit Candidates, 1, Apply changes, aBort.
            ["c", "1", "a", "b"],
        )

        # Check that 'title' field is modified, and other fields come from
        # the candidate.
        assert all("Edited Track " in i.title for i in self.lib.items())
        assert all("match " in i.mb_trackid for i in self.lib.items())


@_common.slow_test()
class EditDuringImporterSingletonTest(EditDuringImporterTestCase):
    def setUp(self):
        super().setUp()
        self.importer = self.setup_singleton_importer()

    def test_edit_apply_asis_singleton(self):
        """Edit the album field for all items in the library, apply changes,
        using the original item tags and singleton mode.
        """
        # Edit track titles.
        self.run_mocked_interpreter(
            {"replacements": {"Tag Track": "Edited Track"}},
            # eDit, Apply changes, aBort.
            ["d", "a", "b"],
        )

        # Check that only the 'title' field is modified.
        self.assertItemFieldsModified(
            self.lib.items(),
            self.items_orig,
            ["title"],
            self.IGNORED + ["albumartist", "mb_albumartistid"],
        )
        assert all("Edited Track" in i.title for i in self.lib.items())
