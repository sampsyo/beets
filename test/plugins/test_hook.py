# This file is part of beets.
# Copyright 2015, Thomas Scholtes.
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


from __future__ import annotations

import os.path
import sys
import unittest
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable

from beets import plugins
from beets.test.helper import PluginTestCase, capture_log

if TYPE_CHECKING:
    from collections.abc import Iterator


class HookTestCase(PluginTestCase):
    plugin = "hook"
    preload_plugin = False

    def _get_hook(self, event: str, command: str) -> dict[str, str]:
        return {"event": event, "command": command}


class HookLogsTest(HookTestCase):
    @contextmanager
    def _configure_logs(self, command: str) -> Iterator[list[str]]:
        config = {"hooks": [self._get_hook("test_event", command)]}

        with self.configure_plugin(config), capture_log("beets.hook") as logs:
            plugins.send("test_event")
            yield logs

    def test_hook_empty_command(self):
        with self._configure_logs("") as logs:
            assert 'hook: invalid command ""' in logs

    # FIXME: fails on windows
    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_hook_non_zero_exit(self):
        with self._configure_logs('sh -c "exit 1"') as logs:
            assert "hook: hook for test_event exited with status 1" in logs

    def test_hook_non_existent_command(self):
        with self._configure_logs("non-existent-command") as logs:
            logs = "\n".join(logs)

        assert "hook: hook for test_event failed: " in logs
        # The error message is different for each OS. Unfortunately the text is
        # different in each case, where the only shared text is the string
        # 'file' and substring 'Err'
        assert "Err" in logs
        assert "file" in logs


class HookCommandTest(HookTestCase):
    TEST_HOOK_COUNT = 2

    events = [f"test_event_{i}" for i in range(TEST_HOOK_COUNT)]

    def setUp(self):
        super().setUp()
        temp_dir = os.fsdecode(self.temp_dir)
        self.paths = [os.path.join(temp_dir, e) for e in self.events]

    def _test_command(
        self,
        make_test_path: Callable[[str, str], str],
        send_path_kwarg: bool = False,
    ) -> None:
        """Check that each of the configured hooks is executed.

        Configure hooks for each event:
        1. Use the given 'make_test_path' callable to create a test path from the event
           and the original path.
        2. Configure a hook with a command to touch this path.

        For each of the original paths:
        1. Send a test event
        2. Assert that a file has been created under the original path, which proves
           that the configured hook command has been executed.
        """
        hooks = [
            self._get_hook(e, f"touch {make_test_path(e, p)}")
            for e, p in zip(self.events, self.paths)
        ]

        with self.configure_plugin({"hooks": hooks}):
            for event, path in zip(self.events, self.paths):
                if send_path_kwarg:
                    plugins.send(event, path=path)
                else:
                    plugins.send(event)
                assert os.path.isfile(path)

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_hook_no_arguments(self):
        self._test_command(lambda _, p: p)

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_hook_event_substitution(self):
        self._test_command(lambda e, p: p.replace(e, "{event}"))

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_hook_argument_substitution(self):
        self._test_command(lambda *_: "{path}", send_path_kwarg=True)

    @unittest.skipIf(sys.platform == "win32", "win32")
    def test_hook_bytes_interpolation(self):
        self.paths = [p.encode() for p in self.paths]
        self._test_command(lambda *_: "{path}", send_path_kwarg=True)
