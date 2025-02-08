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

"""Uses the `KeyFinder` program to add the `initial_key` field."""

import os.path
import subprocess

from beets import ui, util
from beets.plugins import BeetsPlugin


class KeyFinderPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "bin": "KeyFinder",
                "auto": True,
                "overwrite": False,
            }
        )

        if self.config["auto"].get(bool):
            self.import_stages = [self.imported]

    def commands(self):
        cmd = ui.Subcommand(
            "keyfinder", help="detect and add initial key from audio"
        )
        cmd.func = self.command
        return [cmd]

    def command(self, lib, opts, args):
        self.find_key(lib.items(ui.decargs(args)), write=ui.should_write())

    def imported(self, session, task):
        self.find_key(task.imported_items())

    def find_key(self, items, write=False):
        overwrite = self.config["overwrite"].get(bool)
        command = [self.config["bin"].as_str()]
        # The KeyFinder GUI program needs the -f flag before the path.
        # keyfinder-cli is similar, but just wants the path with no flag.
        if "keyfinder-cli" not in os.path.basename(command[0]).lower():
            command.append("-f")

        for item in items:
            if item["initial_key"] and not overwrite:
                continue

            try:
                output = util.command_output(
                    command + [util.syspath(item.path)]
                ).stdout
            except (subprocess.CalledProcessError, OSError) as exc:
                self._log.error("execution failed: {0}", exc)
                continue

            try:
                key_raw = output.rsplit(None, 1)[-1]
            except IndexError:
                # Sometimes keyfinder-cli returns 0 but with no key, usually
                # when the file is silent or corrupt, so we log and skip.
                self._log.error("no key returned for path: {0}", item.path)
                continue

            try:
                key = key_raw.decode("utf-8")
            except UnicodeDecodeError:
                self._log.error("output is invalid UTF-8")
                continue

            item["initial_key"] = key
            self._log.info(
                "added computed initial key {0} for {1}",
                key,
                util.displayable_path(item.path),
            )

            if write:
                item.try_write()
            item.store()
