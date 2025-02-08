# This file is part of beets.
# Copyright 2020, David Swarbrick.
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

"""Tests for image resizing based on filesize."""

import os
import unittest
from unittest.mock import patch

from beets.test import _common
from beets.test.helper import BeetsTestCase, CleanupModulesMixin
from beets.util import command_output, syspath
from beets.util.artresizer import IMBackend, PILBackend


class DummyIMBackend(IMBackend):
    """An `IMBackend` which pretends that ImageMagick is available.

    The version is sufficiently recent to support image comparison.
    """

    def __init__(self):
        """Init a dummy backend class for mocked ImageMagick tests."""
        self.version = (7, 0, 0)
        self.legacy = False
        self.convert_cmd = ["magick"]
        self.identify_cmd = ["magick", "identify"]
        self.compare_cmd = ["magick", "compare"]


class DummyPILBackend(PILBackend):
    """An `PILBackend` which pretends that PIL is available."""

    def __init__(self):
        """Init a dummy backend class for mocked PIL tests."""
        pass


class ArtResizerFileSizeTest(CleanupModulesMixin, BeetsTestCase):
    """Unittest test case for Art Resizer to a specific filesize."""

    modules = (IMBackend.__module__,)

    IMG_225x225 = os.path.join(_common.RSRC, b"abbey.jpg")
    IMG_225x225_SIZE = os.stat(syspath(IMG_225x225)).st_size

    def _test_img_resize(self, backend):
        """Test resizing based on file size, given a resize_func."""
        # Check quality setting unaffected by new parameter
        im_95_qual = backend.resize(
            225,
            self.IMG_225x225,
            quality=95,
            max_filesize=0,
        )
        # check valid path returned - max_filesize hasn't broken resize command
        self.assertExists(im_95_qual)

        # Attempt a lower filesize with same quality
        im_a = backend.resize(
            225,
            self.IMG_225x225,
            quality=95,
            max_filesize=0.9 * os.stat(syspath(im_95_qual)).st_size,
        )
        self.assertExists(im_a)
        # target size was achieved
        assert (
            os.stat(syspath(im_a)).st_size
            < os.stat(syspath(im_95_qual)).st_size
        )

        # Attempt with lower initial quality
        im_75_qual = backend.resize(
            225,
            self.IMG_225x225,
            quality=75,
            max_filesize=0,
        )
        self.assertExists(im_75_qual)

        im_b = backend.resize(
            225,
            self.IMG_225x225,
            quality=95,
            max_filesize=0.9 * os.stat(syspath(im_75_qual)).st_size,
        )
        self.assertExists(im_b)
        # Check high (initial) quality still gives a smaller filesize
        assert (
            os.stat(syspath(im_b)).st_size
            < os.stat(syspath(im_75_qual)).st_size
        )

    @unittest.skipUnless(PILBackend.available(), "PIL not available")
    def test_pil_file_resize(self):
        """Test PIL resize function is lowering file size."""
        self._test_img_resize(PILBackend())

    @unittest.skipUnless(IMBackend.available(), "ImageMagick not available")
    def test_im_file_resize(self):
        """Test IM resize function is lowering file size."""
        self._test_img_resize(IMBackend())

    @unittest.skipUnless(PILBackend.available(), "PIL not available")
    def test_pil_file_deinterlace(self):
        """Test PIL deinterlace function.

        Check if the `PILBackend.deinterlace()` function returns images
        that are non-progressive
        """
        path = PILBackend().deinterlace(self.IMG_225x225)
        from PIL import Image

        with Image.open(path) as img:
            assert "progression" not in img.info

    @unittest.skipUnless(IMBackend.available(), "ImageMagick not available")
    def test_im_file_deinterlace(self):
        """Test ImageMagick deinterlace function.

        Check if the `IMBackend.deinterlace()` function returns images
        that are non-progressive.
        """
        im = IMBackend()
        path = im.deinterlace(self.IMG_225x225)
        cmd = im.identify_cmd + [
            "-format",
            "%[interlace]",
            syspath(path, prefix=False),
        ]
        out = command_output(cmd).stdout
        assert out == b"None"

    @patch("beets.util.artresizer.util")
    def test_write_metadata_im(self, mock_util):
        """Test writing image metadata."""
        metadata = {"a": "A", "b": "B"}
        im = DummyIMBackend()
        im.write_metadata("foo", metadata)
        try:
            command = im.convert_cmd + "foo -set a A -set b B foo".split()
            mock_util.command_output.assert_called_once_with(command)
        except AssertionError:
            command = im.convert_cmd + "foo -set b B -set a A foo".split()
            mock_util.command_output.assert_called_once_with(command)
