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
import unittest
from unittest.mock import patch

import jwt

from beets.test._common import item
from beets.test.helper import (
    AutotagStub,
    ImportHelper,
    TerminalImportSessionSetup,
    TestHelper,
    capture_stdout,
    control_stdin,
)
from beetsplug.mbsubmit import CreateReleaseTask, MBSubmitPlugin


class MBSubmitPluginTest(
    TerminalImportSessionSetup, unittest.TestCase, ImportHelper, TestHelper
):
    def setUp(self):
        self.setup_beets()
        self.load_plugins("mbsubmit")
        self._create_import_dir(2)
        self._setup_import_session()
        self.matcher = AutotagStub().install()

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()
        self.matcher.restore()

    def test_print_tracks_output(self):
        """Test the output of the "print tracks" choice."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin("\n".join(["p", "s"])):
                # Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (
            "Create release on musicbrainz? "
            "01. Tag Title 1 - Tag Artist (0:01)\n"
            "02. Tag Title 2 - Tag Artist (0:01)"
        )
        self.assertIn(tracklist, output.getvalue())

    def test_print_tracks_output_as_tracks(self):
        """Test the output of the "print tracks" choice, as singletons."""
        self.matcher.matching = AutotagStub.BAD

        with capture_stdout() as output:
            with control_stdin("\n".join(["t", "s", "p", "s"])):
                # as Tracks; Skip; Print tracks; Skip
                self.importer.run()

        # Manually build the string for comparing the output.
        tracklist = (
            "Open files with Picard? " "02. Tag Title 2 - Tag Artist (0:01)"
        )
        self.assertIn(tracklist, output.getvalue())

    @patch.object(MBSubmitPlugin, "_wait_for_condition", autospec=True)
    def test_create_release(self, wait_for_condition_mock):
        self.matcher.matching = AutotagStub.BAD

        def _wait_for_condition(plugin: MBSubmitPlugin, condition):
            self.assertEqual(1, len(plugin._create_release_tasks))
            task_id = list(plugin._create_release_tasks.keys())[0]
            if wait_for_condition_mock.call_count == 1:
                plugin._create_release_tasks[task_id].browser_opened = True
            if wait_for_condition_mock.call_count == 2:
                plugin._create_release_tasks[task_id].result_release_mbid = (
                    "new_id"
                )

        wait_for_condition_mock.side_effect = _wait_for_condition

        with control_stdin("\n".join(["c", "s"])):
            # Create release on MusicBrainz, Skip
            self.importer.run()

        self.assertEqual(2, wait_for_condition_mock.call_count)

    def test_create_release_server_add(self):
        plugin = MBSubmitPlugin()
        client = plugin.flask_app.test_client()

        r = client.get("/")
        self.assertEqual(404, r.status_code)

        r = client.get(("/add"))
        self.assertEqual(400, r.status_code)

        r = client.get(("/add?token=12356"))
        self.assertEqual(400, r.status_code)

        token = jwt.encode(
            {"task_key": "unique_key"},
            plugin._jwt_key,
            algorithm=plugin._jwt_algorithm,
        )

        r = client.get((f"/add?token={token}"))
        self.assertEqual(400, r.status_code)

        task = CreateReleaseTask(
            {"a": 1, "b": "Something'test\"", "c": 6767.74}
        )
        plugin._create_release_tasks["unique_key"] = task

        self.assertFalse(task.browser_opened)

        r = client.get((f"/add?token={token}"))
        self.assertEqual(200, r.status_code)
        self.assertIn('<input type="hidden" name="a" value="1">', r.text)
        self.assertIn(
            '<input type="hidden" name="b" value="Something&#39;test&#34;">',
            r.text,
        )
        self.assertIn('<input type="hidden" name="c" value="6767.74">', r.text)

        self.assertTrue(task.browser_opened)

        r = client.get(("/complete_add"))
        self.assertEqual(400, r.status_code)

        r = client.get(("/complete_add?token=12356"))
        self.assertEqual(400, r.status_code)

        r = client.get((f"/complete_add?token={token}"))
        self.assertEqual(400, r.status_code)

        self.assertIsNone(task.result_release_mbid)

        r = client.get(f"/complete_add?token={token}&release_mbid=the_new_id")
        self.assertEqual(200, r.status_code)

        self.assertEqual("the_new_id", task.result_release_mbid)

    def test_build_formdata_empty(self):
        plugin = MBSubmitPlugin()
        self.assertDictEqual({}, plugin._build_formdata([], None))

    def test_build_formdata_redirect(self):
        plugin = MBSubmitPlugin()
        self.assertDictEqual(
            {"redirect_uri": "redirect_to_somewhere"},
            plugin._build_formdata([], "redirect_to_somewhere"),
        )

    def test_build_formdata_items(self):
        plugin = MBSubmitPlugin()
        item1 = item(self.lib)
        item1.track = 1
        item1.title = "Track 1"
        item1.albumtype = "Album"
        item1.barcode = 1234567890
        item1.media = "CD"

        item2 = item(self.lib)
        item2.track = 2
        item2.artists = ["a", "b"]
        item2.title = "Track 2"
        item2.albumtype = "Album"
        item2.barcode = 1234567890
        item2.media = "CD"

        item3 = item(self.lib)
        item3.track = 3
        item3.disc = None
        item3.artists = ["a", "b", "c"]
        item3.title = "Track 3"
        item3.albumtype = "Album"
        item3.barcode = 1234567890
        item3.media = "Digital Media"

        self.maxDiff = None

        self.assertDictEqual(
            {
                "name": "the album",
                "barcode": "1234567890",
                "type": "Album",
                "events.0.date.year": 1,
                "events.0.date.month": 2,
                "events.0.date.day": 3,
                "artist_credit.names.0.artist.name": "the album artist",
                "mediums.5.format": "CD",
                "mediums.5.track.0.artist_credit.names.0.artist.name": "the artist",
                "mediums.5.track.0.length": 60000,
                "mediums.5.track.0.name": "Track 1",
                "mediums.5.track.0.number": 1,
                "mediums.5.track.1.artist_credit.names.0.artist.name": "a",
                "mediums.5.track.1.artist_credit.names.0.join_phrase": " & ",
                "mediums.5.track.1.artist_credit.names.1.artist.name": "b",
                "mediums.5.track.1.length": 60000,
                "mediums.5.track.1.name": "Track 2",
                "mediums.5.track.1.number": 2,
                "mediums.0.format": "Digital Media",
                "mediums.0.track.0.artist_credit.names.0.artist.name": "a",
                "mediums.0.track.0.artist_credit.names.0.join_phrase": ", ",
                "mediums.0.track.0.artist_credit.names.1.artist.name": "b",
                "mediums.0.track.0.artist_credit.names.1.join_phrase": " & ",
                "mediums.0.track.0.artist_credit.names.2.artist.name": "c",
                "mediums.0.track.0.length": 60000,
                "mediums.0.track.0.name": "Track 3",
                "mediums.0.track.0.number": 3,
            },
            plugin._build_formdata([item1, item2, item3], None),
        )

    def test_build_formdata_defaults(self):
        plugin = MBSubmitPlugin()
        plugin.config["create_release_default_type"] = "Album"
        plugin.config["create_release_default_language"] = "eng"
        plugin.config["create_release_default_script"] = "Latn"
        plugin.config["create_release_default_status"] = "Official"
        plugin.config["create_release_default_packaging"] = "Box"
        plugin.config["create_release_default_edit_note"] = (
            "Created via beets mbsubmit plugin"
        )
        self.assertDictEqual(
            {
                "type": "Album",
                "language": "eng",
                "script": "Latn",
                "status": "Official",
                "packaging": "Box",
                "edit_note": "Created via beets mbsubmit plugin",
            },
            plugin._build_formdata([], None),
        )

    def test_build_formdata_defaults_override(self):
        plugin = MBSubmitPlugin()
        plugin.config["create_release_default_type"] = "Album"

        item1 = item(self.lib)
        item1.albumtype = "Single"

        formdata = plugin._build_formdata([item1], None)
        self.assertEqual(formdata["type"], "Single")


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main(defaultTest="suite")
