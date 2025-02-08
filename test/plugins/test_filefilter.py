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

"""Tests for the `filefilter` plugin."""

from beets.test.helper import ImportTestCase, PluginMixin
from beets.util import bytestring_path


class FileFilterPluginMixin(PluginMixin, ImportTestCase):
    plugin = "filefilter"
    preload_plugin = False

    def setUp(self):
        super().setUp()
        self.prepare_tracks_for_import()

    def prepare_tracks_for_import(self):
        self.album_track, self.other_album_track, self.single_track = (
            bytestring_path(self.prepare_album_for_import(1, album_path=p)[0])
            for p in [
                self.import_path / "album",
                self.import_path / "other_album",
                self.import_path,
            ]
        )
        self.all_tracks = {
            self.album_track,
            self.other_album_track,
            self.single_track,
        }

    def _run(self, config, expected_album_count, expected_paths):
        with self.configure_plugin(config):
            self.importer.run()

        assert len(self.lib.albums()) == expected_album_count
        assert {i.path for i in self.lib.items()} == expected_paths


class FileFilterPluginNonSingletonTest(FileFilterPluginMixin):
    def setUp(self):
        super().setUp()
        self.importer = self.setup_importer(autotag=False, copy=False)

    def test_import_default(self):
        """The default configuration should import everything."""
        self._run({}, 3, self.all_tracks)

    def test_import_nothing(self):
        self._run({"path": "not_there"}, 0, set())

    def test_global_config(self):
        self._run(
            {"path": ".*album.*"},
            2,
            {self.album_track, self.other_album_track},
        )

    def test_album_config(self):
        self._run(
            {"album_path": ".*other_album.*"},
            1,
            {self.other_album_track},
        )

    def test_singleton_config(self):
        """Check that singleton configuration is ignored for album import."""
        self._run({"singleton_path": ".*other_album.*"}, 3, self.all_tracks)


class FileFilterPluginSingletonTest(FileFilterPluginMixin):
    def setUp(self):
        super().setUp()
        self.importer = self.setup_singleton_importer(autotag=False, copy=False)

    def test_global_config(self):
        self._run(
            {"path": ".*album.*"}, 0, {self.album_track, self.other_album_track}
        )

    def test_album_config(self):
        """Check that album configuration is ignored for singleton import."""
        self._run({"album_path": ".*other_album.*"}, 0, self.all_tracks)

    def test_singleton_config(self):
        self._run(
            {"singleton_path": ".*other_album.*"}, 0, {self.other_album_track}
        )
