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
"""Tests for base utils from the beets.util package."""

import os
import platform
import re
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import pytest

from beets import util
from beets.test import _common
from beets.test.helper import BeetsTestCase


class UtilTest(unittest.TestCase):
    def test_open_anything(self):
        with _common.system_mock("Windows"):
            assert util.open_anything() == "start"

        with _common.system_mock("Darwin"):
            assert util.open_anything() == "open"

        with _common.system_mock("Tagada"):
            assert util.open_anything() == "xdg-open"

    @patch("os.execlp")
    @patch("beets.util.open_anything")
    def test_interactive_open(self, mock_open, mock_execlp):
        mock_open.return_value = "tagada"
        util.interactive_open(["foo"], util.open_anything())
        mock_execlp.assert_called_once_with("tagada", "tagada", "foo")
        mock_execlp.reset_mock()

        util.interactive_open(["foo"], "bar")
        mock_execlp.assert_called_once_with("bar", "bar", "foo")

    def test_sanitize_unix_replaces_leading_dot(self):
        with _common.platform_posix():
            p = util.sanitize_path("one/.two/three")
        assert "." not in p

    def test_sanitize_windows_replaces_trailing_dot(self):
        with _common.platform_windows():
            p = util.sanitize_path("one/two./three")
        assert "." not in p

    def test_sanitize_windows_replaces_illegal_chars(self):
        with _common.platform_windows():
            p = util.sanitize_path(':*?"<>|')
        assert ":" not in p
        assert "*" not in p
        assert "?" not in p
        assert '"' not in p
        assert "<" not in p
        assert ">" not in p
        assert "|" not in p

    def test_sanitize_windows_replaces_trailing_space(self):
        with _common.platform_windows():
            p = util.sanitize_path("one/two /three")
        assert " " not in p

    def test_sanitize_path_works_on_empty_string(self):
        with _common.platform_posix():
            p = util.sanitize_path("")
        assert p == ""

    def test_sanitize_with_custom_replace_overrides_built_in_sub(self):
        with _common.platform_posix():
            p = util.sanitize_path("a/.?/b", [(re.compile(r"foo"), "bar")])
        assert p == "a/.?/b"

    def test_sanitize_with_custom_replace_adds_replacements(self):
        with _common.platform_posix():
            p = util.sanitize_path("foo/bar", [(re.compile(r"foo"), "bar")])
        assert p == "bar/bar"

    @unittest.skip("unimplemented: #359")
    def test_sanitize_empty_component(self):
        with _common.platform_posix():
            p = util.sanitize_path("foo//bar", [(re.compile(r"^$"), "_")])
        assert p == "foo/_/bar"

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_convert_command_args_keeps_undecodeable_bytes(self):
        arg = b"\x82"  # non-ascii bytes
        cmd_args = util.convert_command_args([arg])

        assert cmd_args[0] == arg.decode(util.arg_encoding(), "surrogateescape")

    @patch("beets.util.subprocess.Popen")
    def test_command_output(self, mock_popen):
        def popen_fail(*args, **kwargs):
            m = Mock(returncode=1)
            m.communicate.return_value = "foo", "bar"
            return m

        mock_popen.side_effect = popen_fail
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            util.command_output(["taga", "\xc3\xa9"])
        assert exc_info.value.returncode == 1
        assert exc_info.value.cmd == "taga \xc3\xa9"

    def test_case_sensitive_default(self):
        path = util.bytestring_path(
            util.normpath(
                "/this/path/does/not/exist",
            )
        )

        assert util.case_sensitive(path) == (platform.system() != "Windows")

    @unittest.skipIf(sys.platform == "win32", "fs is not case sensitive")
    def test_case_sensitive_detects_sensitive(self):
        # FIXME: Add tests for more code paths of case_sensitive()
        # when the filesystem on the test runner is not case sensitive
        pass

    @unittest.skipIf(sys.platform != "win32", "fs is case sensitive")
    def test_case_sensitive_detects_insensitive(self):
        # FIXME: Add tests for more code paths of case_sensitive()
        # when the filesystem on the test runner is case sensitive
        pass


class PathConversionTest(BeetsTestCase):
    def test_syspath_windows_format(self):
        with _common.platform_windows():
            path = os.path.join("a", "b", "c")
            outpath = util.syspath(path)
        assert isinstance(outpath, str)
        assert outpath.startswith("\\\\?\\")

    def test_syspath_windows_format_unc_path(self):
        # The \\?\ prefix on Windows behaves differently with UNC
        # (network share) paths.
        path = "\\\\server\\share\\file.mp3"
        with _common.platform_windows():
            outpath = util.syspath(path)
        assert isinstance(outpath, str)
        assert outpath == "\\\\?\\UNC\\server\\share\\file.mp3"

    def test_syspath_posix_unchanged(self):
        with _common.platform_posix():
            path = os.path.join("a", "b", "c")
            outpath = util.syspath(path)
        assert path == outpath

    def _windows_bytestring_path(self, path):
        old_gfse = sys.getfilesystemencoding
        sys.getfilesystemencoding = lambda: "mbcs"
        try:
            with _common.platform_windows():
                return util.bytestring_path(path)
        finally:
            sys.getfilesystemencoding = old_gfse

    def test_bytestring_path_windows_encodes_utf8(self):
        path = "caf\xe9"
        outpath = self._windows_bytestring_path(path)
        assert path == outpath.decode("utf-8")

    def test_bytesting_path_windows_removes_magic_prefix(self):
        path = "\\\\?\\C:\\caf\xe9"
        outpath = self._windows_bytestring_path(path)
        assert outpath == "C:\\caf\xe9".encode()


class PathTruncationTest(BeetsTestCase):
    def test_truncate_bytestring(self):
        with _common.platform_posix():
            p = util.truncate_path(b"abcde/fgh", 4)
        assert p == b"abcd/fgh"

    def test_truncate_unicode(self):
        with _common.platform_posix():
            p = util.truncate_path("abcde/fgh", 4)
        assert p == "abcd/fgh"

    def test_truncate_preserves_extension(self):
        with _common.platform_posix():
            p = util.truncate_path("abcde/fgh.ext", 5)
        assert p == "abcde/f.ext"
