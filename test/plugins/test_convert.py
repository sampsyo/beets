# This file is part of beets.
# Copyright 2016, Thomas Scholtes.
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


import fnmatch
import os.path
import re
import sys
import unittest

from mediafile import MediaFile

from beets import util
from beets.test import _common, helper
from beets.test.helper import capture_log, control_stdin
from beets.util import bytestring_path, displayable_path


def shell_quote(text):
    import shlex

    return shlex.quote(text)


class TestHelper(helper.TestHelper):
    def tagged_copy_cmd(self, tag):
        """Return a conversion command that copies files and appends
        `tag` to the copy.
        """
        if re.search("[^a-zA-Z0-9]", tag):
            raise ValueError(
                "tag '{}' must only contain letters and digits".format(tag)
            )

        # A Python script that copies the file and appends a tag.
        stub = os.path.join(_common.RSRC, b"convert_stub.py").decode("utf-8")
        return "{} {} $source $dest {}".format(
            shell_quote(sys.executable), shell_quote(stub), tag
        )

    def assertFileTag(self, path, tag):  # noqa
        """Assert that the path is a file and the files content ends
        with `tag`.
        """
        display_tag = tag
        tag = tag.encode("utf-8")
        self.assertIsFile(path)
        with open(path, "rb") as f:
            f.seek(-len(display_tag), os.SEEK_END)
            self.assertEqual(
                f.read(),
                tag,
                "{} is not tagged with {}".format(
                    displayable_path(path), display_tag
                ),
            )

    def assertNoFileTag(self, path, tag):  # noqa
        """Assert that the path is a file and the files content does not
        end with `tag`.
        """
        display_tag = tag
        tag = tag.encode("utf-8")
        self.assertIsFile(path)
        with open(path, "rb") as f:
            f.seek(-len(tag), os.SEEK_END)
            self.assertNotEqual(
                f.read(),
                tag,
                "{} is unexpectedly tagged with {}".format(
                    displayable_path(path), display_tag
                ),
            )


@_common.slow_test()
class ImportConvertTest(_common.TestCase, TestHelper):
    def setUp(self):
        self.setup_beets(disk=True)  # Converter is threaded
        self.importer = self.create_importer()
        self.load_plugins("convert")

        self.config["convert"] = {
            "dest": os.path.join(self.temp_dir, b"convert"),
            "command": self.tagged_copy_cmd("convert"),
            # Enforce running convert
            "max_bitrate": 1,
            "auto": True,
            "quiet": False,
        }

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_import_converted(self):
        self.importer.run()
        item = self.lib.items().get()
        self.assertFileTag(item.path, "convert")

    # FIXME: fails on windows
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_import_original_on_convert_error(self):
        # `false` exits with non-zero code
        self.config["convert"]["command"] = "false"
        self.importer.run()

        item = self.lib.items().get()
        self.assertIsNotNone(item)
        self.assertIsFile(item.path)

    def test_delete_originals(self):
        self.config["convert"]["delete_originals"] = True
        self.importer.run()
        for path in self.importer.paths:
            for root, dirnames, filenames in os.walk(path):
                self.assertEqual(
                    len(fnmatch.filter(filenames, "*.mp3")),
                    0,
                    "Non-empty import directory {}".format(
                        util.displayable_path(path)
                    ),
                )

    def get_count_of_import_files(self):
        import_file_count = 0

        for path in self.importer.paths:
            for root, _, filenames in os.walk(path):
                import_file_count += len(filenames)

        return import_file_count


class ConvertCommand:
    """A mixin providing a utility method to run the `convert`command
    in tests.
    """

    def run_convert_path(self, path, *args):
        """Run the `convert` command on a given path."""
        # The path is currently a filesystem bytestring. Convert it to
        # an argument bytestring.
        path = path.decode(util._fsencoding()).encode(util.arg_encoding())

        args = args + (b"path:" + path,)
        return self.run_command("convert", *args)

    def run_convert(self, *args):
        """Run the `convert` command on `self.item`."""
        return self.run_convert_path(self.item.path, *args)


@_common.slow_test()
class ConvertCliTest(_common.TestCase, TestHelper, ConvertCommand):
    def setUp(self):
        self.setup_beets(disk=True)  # Converter is threaded
        self.album = self.add_album_fixture(ext="ogg")
        self.item = self.album.items()[0]
        self.load_plugins("convert")

        self.convert_dest = bytestring_path(
            os.path.join(self.temp_dir, b"convert_dest")
        )
        self.config["convert"] = {
            "dest": self.convert_dest,
            "paths": {"default": "converted"},
            "format": "mp3",
            "formats": {
                "mp3": self.tagged_copy_cmd("mp3"),
                "ogg": self.tagged_copy_cmd("ogg"),
                "opus": {
                    "command": self.tagged_copy_cmd("opus"),
                    "extension": "ops",
                },
            },
        }

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_convert(self):
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_convert_with_auto_confirmation(self):
        self.run_convert("--yes")
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_reject_confirmation(self):
        with control_stdin("n"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertNotExists(converted)

    def test_convert_keep_new(self):
        self.assertEqual(os.path.splitext(self.item.path)[1], b".ogg")

        with control_stdin("y"):
            self.run_convert("--keep-new")

        self.item.load()
        self.assertEqual(os.path.splitext(self.item.path)[1], b".mp3")

    def test_format_option(self):
        with control_stdin("y"):
            self.run_convert("--format", "opus")
            converted = os.path.join(self.convert_dest, b"converted.ops")
        self.assertFileTag(converted, "opus")

    def test_embed_album_art(self):
        self.config["convert"]["embed"] = True
        image_path = os.path.join(_common.RSRC, b"image-2x3.jpg")
        self.album.artpath = image_path
        self.album.store()
        with open(os.path.join(image_path), "rb") as f:
            image_data = f.read()

        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        mediafile = MediaFile(converted)
        self.assertEqual(mediafile.images[0].data, image_data)

    def test_skip_existing(self):
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.touch(converted, content="XXX")
        self.run_convert("--yes")
        with open(converted) as f:
            self.assertEqual(f.read(), "XXX")

    def test_pretend(self):
        self.run_convert("--pretend")
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertNotExists(converted)

    def test_empty_query(self):
        with capture_log("beets.convert") as logs:
            self.run_convert("An impossible query")
        self.assertEqual(logs[0], "convert: Empty query result.")

    def test_no_transcode_when_maxbr_set_high_and_different_formats(self):
        self.config["convert"]["max_bitrate"] = 5000
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_transcode_when_maxbr_set_low_and_different_formats(self):
        self.config["convert"]["max_bitrate"] = 5
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_transcode_when_maxbr_set_to_none_and_different_formats(self):
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_no_transcode_when_maxbr_set_high_and_same_formats(self):
        self.config["convert"]["max_bitrate"] = 5000
        self.config["convert"]["format"] = "ogg"
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.ogg")
        self.assertNoFileTag(converted, "ogg")

    def test_transcode_when_maxbr_set_low_and_same_formats(self):
        self.config["convert"]["max_bitrate"] = 5
        self.config["convert"]["format"] = "ogg"
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.ogg")
        self.assertFileTag(converted, "ogg")

    def test_transcode_when_maxbr_set_to_none_and_same_formats(self):
        self.config["convert"]["format"] = "ogg"
        with control_stdin("y"):
            self.run_convert()
        converted = os.path.join(self.convert_dest, b"converted.ogg")
        self.assertNoFileTag(converted, "ogg")

    def test_playlist(self):
        with control_stdin("y"):
            self.run_convert("--playlist", "playlist.m3u8")
            m3u_created = os.path.join(self.convert_dest, b"playlist.m3u8")
        self.assertTrue(os.path.exists(m3u_created))

    def test_playlist_pretend(self):
        self.run_convert("--playlist", "playlist.m3u8", "--pretend")
        m3u_created = os.path.join(self.convert_dest, b"playlist.m3u8")
        self.assertFalse(os.path.exists(m3u_created))

    def test_playlist_ext(self):
        """Test correct extension of file inside the playlist when format conversion occurs."""
        # We expect a converted file with the MP3 extension.
        self.config["convert"]["format"] = "mp3"
        with control_stdin("y"):
            self.run_convert("--playlist", "playlist.m3u8")
            # Check playlist content.
            m3u_created = os.path.join(self.convert_dest, b"playlist.m3u8")
            with open(m3u_created, "r") as m3u_file:
                self.assertTrue(m3u_file.readline() == "#EXTM3U\n")
                self.assertTrue(m3u_file.readline() == "converted.mp3\n")


@_common.slow_test()
class NeverConvertLossyFilesTest(_common.TestCase, TestHelper, ConvertCommand):
    """Test the effect of the `never_convert_lossy_files` option."""

    def setUp(self):
        self.setup_beets(disk=True)  # Converter is threaded
        self.load_plugins("convert")

        self.convert_dest = os.path.join(self.temp_dir, b"convert_dest")
        self.config["convert"] = {
            "dest": self.convert_dest,
            "paths": {"default": "converted"},
            "never_convert_lossy_files": True,
            "format": "mp3",
            "formats": {
                "mp3": self.tagged_copy_cmd("mp3"),
            },
        }

    def tearDown(self):
        self.unload_plugins()
        self.teardown_beets()

    def test_transcode_from_lossless(self):
        [item] = self.add_item_fixtures(ext="flac")
        with control_stdin("y"):
            self.run_convert_path(item.path)
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_transcode_from_lossy(self):
        self.config["convert"]["never_convert_lossy_files"] = False
        [item] = self.add_item_fixtures(ext="ogg")
        with control_stdin("y"):
            self.run_convert_path(item.path)
        converted = os.path.join(self.convert_dest, b"converted.mp3")
        self.assertFileTag(converted, "mp3")

    def test_transcode_from_lossy_prevented(self):
        [item] = self.add_item_fixtures(ext="ogg")
        with control_stdin("y"):
            self.run_convert_path(item.path)
        converted = os.path.join(self.convert_dest, b"converted.ogg")
        self.assertNoFileTag(converted, "mp3")


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main(defaultTest="suite")
