# This file is part of beets.
# Copyright 2017, Dorian Soergel
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

"""Tests for the 'parentwork' plugin."""

from unittest.mock import patch

import pytest

from beets.library import Item
from beets.test.helper import PluginTestCase
from beetsplug import parentwork

work = {
    "work": {
        "id": "1",
        "title": "work",
        "work-relation-list": [
            {"type": "parts", "direction": "backward", "work": {"id": "2"}}
        ],
        "artist-relation-list": [
            {
                "type": "composer",
                "artist": {
                    "name": "random composer",
                    "sort-name": "composer, random",
                },
            }
        ],
    }
}
dp_work = {
    "work": {
        "id": "2",
        "title": "directparentwork",
        "work-relation-list": [
            {"type": "parts", "direction": "backward", "work": {"id": "3"}}
        ],
        "artist-relation-list": [
            {
                "type": "composer",
                "artist": {
                    "name": "random composer",
                    "sort-name": "composer, random",
                },
            }
        ],
    }
}
p_work = {
    "work": {
        "id": "3",
        "title": "parentwork",
        "artist-relation-list": [
            {
                "type": "composer",
                "artist": {
                    "name": "random composer",
                    "sort-name": "composer, random",
                },
            }
        ],
    }
}


def mock_workid_response(mbid, includes):
    if mbid == "1":
        return work
    elif mbid == "2":
        return dp_work
    elif mbid == "3":
        return p_work


@pytest.mark.integration_test
class ParentWorkIntegrationTest(PluginTestCase):
    plugin = "parentwork"

    # test how it works with real musicbrainz data
    def test_normal_case_real(self):
        item = Item(
            path="/file",
            mb_workid="e27bda6e-531e-36d3-9cd7-b8ebc18e8c53",
            parentwork_workid_current="e27bda6e-531e-36d3-9cd7-\
                    b8ebc18e8c53",
        )
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "32c8943f-1b27-3a23-8660-4567f4847c94"

    def test_force_real(self):
        self.config["parentwork"]["force"] = True
        item = Item(
            path="/file",
            mb_workid="e27bda6e-531e-36d3-9cd7-b8ebc18e8c53",
            mb_parentworkid="XXX",
            parentwork_workid_current="e27bda6e-531e-36d3-9cd7-\
                    b8ebc18e8c53",
            parentwork="whatever",
        )
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "32c8943f-1b27-3a23-8660-4567f4847c94"

    def test_no_force_real(self):
        self.config["parentwork"]["force"] = False
        item = Item(
            path="/file",
            mb_workid="e27bda6e-531e-36d3-9cd7-\
                    b8ebc18e8c53",
            mb_parentworkid="XXX",
            parentwork_workid_current="e27bda6e-531e-36d3-9cd7-\
                    b8ebc18e8c53",
            parentwork="whatever",
        )
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "XXX"

    # test different cases, still with Matthew Passion Ouverture or Mozart
    # requiem

    def test_direct_parent_work_real(self):
        mb_workid = "2e4a3668-458d-3b2a-8be2-0b08e0d8243a"
        assert (
            "f04b42df-7251-4d86-a5ee-67cfa49580d1"
            == parentwork.direct_parent_id(mb_workid)[0]
        )
        assert (
            "45afb3b2-18ac-4187-bc72-beb1b1c194ba"
            == parentwork.work_parent_id(mb_workid)[0]
        )


class ParentWorkTest(PluginTestCase):
    plugin = "parentwork"

    def setUp(self):
        """Set up configuration"""
        super().setUp()
        self.patcher = patch(
            "musicbrainzngs.get_work_by_id", side_effect=mock_workid_response
        )
        self.patcher.start()

    def tearDown(self):
        super().tearDown()
        self.patcher.stop()

    def test_normal_case(self):
        item = Item(path="/file", mb_workid="1", parentwork_workid_current="1")
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "3"

    def test_force(self):
        self.config["parentwork"]["force"] = True
        item = Item(
            path="/file",
            mb_workid="1",
            mb_parentworkid="XXX",
            parentwork_workid_current="1",
            parentwork="parentwork",
        )
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "3"

    def test_no_force(self):
        self.config["parentwork"]["force"] = False
        item = Item(
            path="/file",
            mb_workid="1",
            mb_parentworkid="XXX",
            parentwork_workid_current="1",
            parentwork="parentwork",
        )
        item.add(self.lib)

        self.run_command("parentwork")

        item.load()
        assert item["mb_parentworkid"] == "XXX"

    def test_direct_parent_work(self):
        assert "2" == parentwork.direct_parent_id("1")[0]
        assert "3" == parentwork.work_parent_id("1")[0]
