# This file is part of beets.
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

"""Tests for the 'limit' plugin."""

from beets.test.helper import PluginTestCase


class LimitPluginTest(PluginTestCase):
    """Unit tests for LimitPlugin

    Note: query prefix tests do not work correctly with `run_with_output`.
    """

    plugin = "limit"

    def setUp(self):
        super().setUp()

        # we'll create an even number of tracks in the library
        self.num_test_items = 10
        assert self.num_test_items % 2 == 0
        for item_no, item in enumerate(
            self.add_item_fixtures(count=self.num_test_items)
        ):
            item.track = item_no + 1
            item.store()

        # our limit tests will use half of this number
        self.num_limit = self.num_test_items // 2
        self.num_limit_prefix = "".join(["'", "<", str(self.num_limit), "'"])

        # a subset of tests has only `num_limit` results, identified by a
        # range filter on the track number
        self.track_head_range = "track:.." + str(self.num_limit)
        self.track_tail_range = "track:" + str(self.num_limit + 1) + ".."

    def test_no_limit(self):
        """Returns all when there is no limit or filter."""
        result = self.run_with_output("lslimit")
        assert result.count("\n") == self.num_test_items

    def test_lslimit_head(self):
        """Returns the expected number with `lslimit --head`."""
        result = self.run_with_output("lslimit", "--head", str(self.num_limit))
        assert result.count("\n") == self.num_limit

    def test_lslimit_tail(self):
        """Returns the expected number with `lslimit --tail`."""
        result = self.run_with_output("lslimit", "--tail", str(self.num_limit))
        assert result.count("\n") == self.num_limit

    def test_lslimit_head_invariant(self):
        """Returns the expected number with `lslimit --head` and a filter."""
        result = self.run_with_output(
            "lslimit", "--head", str(self.num_limit), self.track_tail_range
        )
        assert result.count("\n") == self.num_limit

    def test_lslimit_tail_invariant(self):
        """Returns the expected number with `lslimit --tail` and a filter."""
        result = self.run_with_output(
            "lslimit", "--tail", str(self.num_limit), self.track_head_range
        )
        assert result.count("\n") == self.num_limit

    def test_prefix(self):
        """Returns the expected number with the query prefix."""
        result = self.lib.items(self.num_limit_prefix)
        assert len(result) == self.num_limit

    def test_prefix_when_correctly_ordered(self):
        """Returns the expected number with the query prefix and filter when
        the prefix portion (correctly) appears last."""
        correct_order = self.track_tail_range + " " + self.num_limit_prefix
        result = self.lib.items(correct_order)
        assert len(result) == self.num_limit

    def test_prefix_when_incorrectly_ordred(self):
        """Returns no results with the query prefix and filter when the prefix
        portion (incorrectly) appears first."""
        incorrect_order = self.num_limit_prefix + " " + self.track_tail_range
        result = self.lib.items(incorrect_order)
        assert len(result) == 0
