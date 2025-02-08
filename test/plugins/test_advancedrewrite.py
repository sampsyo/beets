# This file is part of beets.
# Copyright 2023, Max Rumpf.
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

"""Test the advancedrewrite plugin for various configurations."""

import pytest

from beets.test.helper import PluginTestCase
from beets.ui import UserError

PLUGIN_NAME = "advancedrewrite"


class AdvancedRewritePluginTest(PluginTestCase):
    plugin = "advancedrewrite"
    preload_plugin = False

    def test_simple_rewrite_example(self):
        with self.configure_plugin(
            [{"artist ODD EYE CIRCLE": "이달의 소녀 오드아이써클"}]
        ):
            item = self.add_item(
                artist="ODD EYE CIRCLE",
                albumartist="ODD EYE CIRCLE",
            )

            assert item.artist == "이달의 소녀 오드아이써클"

    def test_advanced_rewrite_example(self):
        with self.configure_plugin(
            [
                {
                    "match": "mb_artistid:dec0f331-cb08-4c8e-9c9f-aeb1f0f6d88c year:..2022",  # noqa: E501
                    "replacements": {
                        "artist": "이달의 소녀 오드아이써클",
                        "artist_sort": "LOONA / ODD EYE CIRCLE",
                    },
                },
            ]
        ):
            item_a = self.add_item(
                artist="ODD EYE CIRCLE",
                artist_sort="ODD EYE CIRCLE",
                mb_artistid="dec0f331-cb08-4c8e-9c9f-aeb1f0f6d88c",
                year=2017,
            )
            item_b = self.add_item(
                artist="ODD EYE CIRCLE",
                artist_sort="ODD EYE CIRCLE",
                mb_artistid="dec0f331-cb08-4c8e-9c9f-aeb1f0f6d88c",
                year=2023,
            )

            # Assert that all replacements were applied to item_a
            assert "이달의 소녀 오드아이써클" == item_a.artist
            assert "LOONA / ODD EYE CIRCLE" == item_a.artist_sort
            assert "LOONA / ODD EYE CIRCLE" == item_a.albumartist_sort

            # Assert that no replacements were applied to item_b
            assert "ODD EYE CIRCLE" == item_b.artist

    def test_advanced_rewrite_example_with_multi_valued_field(self):
        with self.configure_plugin(
            [
                {
                    "match": "artist:배유빈 feat. 김미현",
                    "replacements": {"artists": ["유빈", "미미"]},
                },
            ]
        ):
            item = self.add_item(
                artist="배유빈 feat. 김미현",
                artists=["배유빈", "김미현"],
            )

            assert item.artists == ["유빈", "미미"]

    def test_fail_when_replacements_empty(self):
        with (
            pytest.raises(
                UserError,
                match="Advanced rewrites must have at least one replacement",
            ),
            self.configure_plugin([{"match": "artist:A", "replacements": {}}]),
        ):
            pass

    def test_fail_when_rewriting_single_valued_field_with_list(self):
        with (
            pytest.raises(
                UserError,
                match="Field artist is not a multi-valued field but a list was given: C, D",  # noqa: E501
            ),
            self.configure_plugin(
                [
                    {
                        "match": "artist:'A & B'",
                        "replacements": {"artist": ["C", "D"]},
                    },
                ]
            ),
        ):
            pass

    def test_combined_rewrite_example(self):
        with self.configure_plugin(
            [
                {"artist A": "B"},
                {"match": "album:'C'", "replacements": {"artist": "D"}},
            ]
        ):
            item = self.add_item(artist="A", albumartist="A")
            assert item.artist == "B"

            item = self.add_item(artist="C", albumartist="C", album="C")
            assert item.artist == "D"
