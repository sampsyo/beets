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


from unittest.mock import patch

from beets import util
from beets.library import Item
from beets.test.helper import AsIsImporterMixin, ImportTestCase, PluginMixin


@patch("beets.util.command_output")
class KeyFinderTest(AsIsImporterMixin, PluginMixin, ImportTestCase):
    plugin = "keyfinder"

    def test_add_key(self, command_output):
        item = Item(path="/file")
        item.add(self.lib)

        command_output.return_value = util.CommandOutput(b"dbm", b"")
        self.run_command("keyfinder")

        item.load()
        assert item["initial_key"] == "C#m"
        command_output.assert_called_with(
            ["KeyFinder", "-f", util.syspath(item.path)]
        )

    def test_add_key_on_import(self, command_output):
        command_output.return_value = util.CommandOutput(b"dbm", b"")
        self.run_asis_importer()

        item = self.lib.items().get()
        assert item["initial_key"] == "C#m"

    def test_force_overwrite(self, command_output):
        self.config["keyfinder"]["overwrite"] = True

        item = Item(path="/file", initial_key="F")
        item.add(self.lib)

        command_output.return_value = util.CommandOutput(b"C#m", b"")
        self.run_command("keyfinder")

        item.load()
        assert item["initial_key"] == "C#m"

    def test_do_not_overwrite(self, command_output):
        item = Item(path="/file", initial_key="F")
        item.add(self.lib)

        command_output.return_value = util.CommandOutput(b"dbm", b"")
        self.run_command("keyfinder")

        item.load()
        assert item["initial_key"] == "F"

    def test_no_key(self, command_output):
        item = Item(path="/file")
        item.add(self.lib)

        command_output.return_value = util.CommandOutput(b"", b"")
        self.run_command("keyfinder")

        item.load()
        assert item["initial_key"] is None
