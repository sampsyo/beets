# This file is part of beets.
# Copyright 2019, Carl Suster
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

"""Test the beets.export utilities associated with the export plugin."""

import json
import re  # used to test csv format
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from beets.test.helper import PluginTestCase


class ExportPluginTest(PluginTestCase):
    plugin = "export"

    def setUp(self):
        super().setUp()
        self.test_values = {"title": "xtitle", "album": "xalbum"}

    def execute_command(self, format_type, artist):
        query = ",".join(self.test_values.keys())
        out = self.run_with_output(
            "export", "-f", format_type, "-i", query, artist
        )
        return out

    def create_item(self):
        (item,) = self.add_item_fixtures()
        item.artist = "xartist"
        item.title = self.test_values["title"]
        item.album = self.test_values["album"]
        item.write()
        item.store()
        return item

    def test_json_output(self):
        item1 = self.create_item()
        out = self.execute_command(format_type="json", artist=item1.artist)
        json_data = json.loads(out)[0]
        for key, val in self.test_values.items():
            assert key in json_data
            assert val == json_data[key]

    def test_jsonlines_output(self):
        item1 = self.create_item()
        out = self.execute_command(format_type="jsonlines", artist=item1.artist)
        json_data = json.loads(out)
        for key, val in self.test_values.items():
            assert key in json_data
            assert val == json_data[key]

    def test_csv_output(self):
        item1 = self.create_item()
        out = self.execute_command(format_type="csv", artist=item1.artist)
        csv_list = re.split("\r", re.sub("\n", "", out))
        head = re.split(",", csv_list[0])
        vals = re.split(",|\r", csv_list[1])
        for index, column in enumerate(head):
            assert self.test_values.get(column, None) is not None
            assert vals[index] == self.test_values[column]

    def test_xml_output(self):
        item1 = self.create_item()
        out = self.execute_command(format_type="xml", artist=item1.artist)
        library = ElementTree.fromstring(out)
        assert isinstance(library, Element)
        for track in library[0]:
            for details in track:
                tag = details.tag
                txt = details.text
                assert tag in self.test_values, tag
                assert self.test_values[tag] == txt, txt
