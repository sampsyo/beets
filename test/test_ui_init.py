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

"""Test module for file ui/__init__.py"""

import os
import shutil
from copy import deepcopy
from random import random

from beets import config, ui
from beets.test import _common
from beets.test.helper import BeetsTestCase, ItemInDBTestCase, control_stdin


class InputMethodsTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.io.install()

    def _print_helper(self, s):
        print(s)

    def _print_helper2(self, s, prefix):
        print(prefix, s)

    def test_input_select_objects(self):
        full_items = ["1", "2", "3", "4", "5"]

        # Test no
        self.io.addinput("n")
        items = ui.input_select_objects(
            "Prompt", full_items, self._print_helper
        )
        assert items == []

        # Test yes
        self.io.addinput("y")
        items = ui.input_select_objects(
            "Prompt", full_items, self._print_helper
        )
        assert items == full_items

        # Test selective 1
        self.io.addinput("s")
        self.io.addinput("n")
        self.io.addinput("y")
        self.io.addinput("n")
        self.io.addinput("y")
        self.io.addinput("n")
        items = ui.input_select_objects(
            "Prompt", full_items, self._print_helper
        )
        assert items == ["2", "4"]

        # Test selective 2
        self.io.addinput("s")
        self.io.addinput("y")
        self.io.addinput("y")
        self.io.addinput("n")
        self.io.addinput("y")
        self.io.addinput("n")
        items = ui.input_select_objects(
            "Prompt", full_items, lambda s: self._print_helper2(s, "Prefix")
        )
        assert items == ["1", "2", "4"]

        # Test selective 3
        self.io.addinput("s")
        self.io.addinput("y")
        self.io.addinput("n")
        self.io.addinput("y")
        self.io.addinput("q")
        items = ui.input_select_objects(
            "Prompt", full_items, self._print_helper
        )
        assert items == ["1", "3"]


class InitTest(ItemInDBTestCase):
    def test_human_bytes(self):
        tests = [
            (0, "0.0 B"),
            (30, "30.0 B"),
            (pow(2, 10), "1.0 KiB"),
            (pow(2, 20), "1.0 MiB"),
            (pow(2, 30), "1.0 GiB"),
            (pow(2, 40), "1.0 TiB"),
            (pow(2, 50), "1.0 PiB"),
            (pow(2, 60), "1.0 EiB"),
            (pow(2, 70), "1.0 ZiB"),
            (pow(2, 80), "1.0 YiB"),
            (pow(2, 90), "1.0 HiB"),
            (pow(2, 100), "big"),
        ]
        for i, h in tests:
            assert h == ui.human_bytes(i)

    def test_human_seconds(self):
        tests = [
            (0, "0.0 seconds"),
            (30, "30.0 seconds"),
            (60, "1.0 minutes"),
            (90, "1.5 minutes"),
            (125, "2.1 minutes"),
            (3600, "1.0 hours"),
            (86400, "1.0 days"),
            (604800, "1.0 weeks"),
            (31449600, "1.0 years"),
            (314496000, "1.0 decades"),
        ]
        for i, h in tests:
            assert h == ui.human_seconds(i)


class ParentalDirCreation(BeetsTestCase):
    def test_create_yes(self):
        non_exist_path = _common.os.fsdecode(
            os.path.join(self.temp_dir, b"nonexist", str(random()).encode())
        )
        # Deepcopy instead of recovering because exceptions might
        # occur; wish I can use a golang defer here.
        test_config = deepcopy(config)
        test_config["library"] = non_exist_path
        with control_stdin("y"):
            lib = ui._open_library(test_config)
        lib._close()

    def test_create_no(self):
        non_exist_path_parent = _common.os.fsdecode(
            os.path.join(self.temp_dir, b"nonexist")
        )
        non_exist_path = _common.os.fsdecode(
            os.path.join(non_exist_path_parent.encode(), str(random()).encode())
        )
        test_config = deepcopy(config)
        test_config["library"] = non_exist_path

        with control_stdin("n"):
            try:
                lib = ui._open_library(test_config)
            except ui.UserError:
                if os.path.exists(non_exist_path_parent):
                    shutil.rmtree(non_exist_path_parent)
                    raise OSError("Parent directories should not be created.")
            else:
                if lib:
                    lib._close()
                raise OSError("Parent directories should not be created.")
