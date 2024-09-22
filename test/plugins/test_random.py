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

"""Test the beets.random utilities associated with the random plugin."""

import math
import unittest
from random import Random

import pytest

from beets import random
from beets.test.helper import TestHelper


class RandomTest(TestHelper, unittest.TestCase):
    def setUp(self):
        self.lib = None
        self.artist1 = "Artist 1"
        self.artist2 = "Artist 2"
        self.item1 = self.create_item(artist=self.artist1)
        self.item2 = self.create_item(artist=self.artist2)
        self.items = [self.item1, self.item2]
        for _ in range(8):
            self.items.append(self.create_item(artist=self.artist2))
        self.random_gen = Random()
        self.random_gen.seed(12345)

    def _stats(self, data):
        mean = sum(data) / len(data)
        stdev = math.sqrt(sum((p - mean) ** 2 for p in data) / (len(data) - 1))
        quot, rem = divmod(len(data), 2)
        if rem:
            median = sorted(data)[quot]
        else:
            median = sum(sorted(data)[quot - 1 : quot + 1]) / 2
        return mean, stdev, median

    def test_equal_permutation(self):
        """We have a list of items where only one item is from artist1 and the
        rest are from artist2. If we permute weighted by the artist field then
        the solo track will almost always end up near the start. If we use a
        different field then it'll be in the middle on average.
        """

        def experiment(field, histogram=False):
            """Permutes the list of items 500 times and calculates the position
            of self.item1 each time. Returns stats about that position.
            """
            positions = []
            for _ in range(500):
                shuffled = list(
                    random._equal_chance_permutation(
                        self.items, field=field, random_gen=self.random_gen
                    )
                )
                positions.append(shuffled.index(self.item1))
            # Print a histogram (useful for debugging).
            if histogram:
                for i in range(len(self.items)):
                    print(f"{i:2d} {'*'*positions.count(i)}")
            return self._stats(positions)

        mean1, stdev1, median1 = experiment("artist")
        mean2, stdev2, median2 = experiment("track")
        assert 0 == pytest.approx(median1, abs=1)
        assert len(self.items) // 2 == pytest.approx(median2, abs=1)
        assert stdev2 > stdev1
