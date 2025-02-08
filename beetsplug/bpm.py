# This file is part of beets.
# Copyright 2016, aroquen
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

"""Determine BPM by pressing a key to the rhythm."""

import time

from beets import ui
from beets.plugins import BeetsPlugin


def bpm(max_strokes):
    """Returns average BPM (possibly of a playing song)
    listening to Enter keystrokes.
    """
    t0 = None
    dt = []
    for i in range(max_strokes):
        # Press enter to the rhythm...
        s = input()
        if s == "":
            t1 = time.time()
            # Only start measuring at the second stroke
            if t0:
                dt.append(t1 - t0)
            t0 = t1
        else:
            break

    # Return average BPM
    # bpm = (max_strokes-1) / sum(dt) * 60
    ave = sum([1.0 / dti * 60 for dti in dt]) / len(dt)
    return ave


class BPMPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "max_strokes": 3,
                "overwrite": True,
            }
        )

    def commands(self):
        cmd = ui.Subcommand(
            "bpm",
            help="determine bpm of a song by pressing " "a key to the rhythm",
        )
        cmd.func = self.command
        return [cmd]

    def command(self, lib, opts, args):
        items = lib.items(ui.decargs(args))
        write = ui.should_write()
        self.get_bpm(items, write)

    def get_bpm(self, items, write=False):
        overwrite = self.config["overwrite"].get(bool)
        if len(items) > 1:
            raise ValueError("Can only get bpm of one song at time")

        item = items[0]
        if item["bpm"]:
            self._log.info("Found bpm {0}", item["bpm"])
            if not overwrite:
                return

        self._log.info(
            "Press Enter {0} times to the rhythm or Ctrl-D " "to exit",
            self.config["max_strokes"].get(int),
        )
        new_bpm = bpm(self.config["max_strokes"].get(int))
        item["bpm"] = int(new_bpm)
        if write:
            item.try_write()
        item.store()
        self._log.info("Added new bpm {0}", item["bpm"])
