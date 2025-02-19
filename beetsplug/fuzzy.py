# This file is part of beets.
# Copyright 2016, Philippe Mongeau.
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

"""Provides a fuzzy matching query."""

import difflib

from beets import config
from beets.dbcore.query import StringFieldQuery
from beets.plugins import BeetsPlugin


class FuzzyQuery(StringFieldQuery[str]):
    @classmethod
    def string_match(cls, pattern: str, val: str):
        # smartcase
        if pattern.islower():
            val = val.lower()
        query_matcher = difflib.SequenceMatcher(None, pattern, val)
        threshold = config["fuzzy"]["threshold"].as_number()
        # Adjust match threshold for the case that the pattern is shorter
        # than the value being matched. This allows the pattern to match
        # substrings of the value, not just the entire value.
        if len(pattern) < len(val):
            max_possible_ratio = 2 * len(pattern) / (len(pattern) + len(val))
            threshold *= max_possible_ratio

        # If upper bound of the ratio meets threshold, then calculate
        # the actual ratio.
        if query_matcher.quick_ratio() >= threshold:
            return query_matcher.ratio() >= threshold
        
        return False


class FuzzyPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "prefix": "~",
                "threshold": 0.7,
            }
        )

    def queries(self):
        prefix = self.config["prefix"].as_str()
        return {prefix: FuzzyQuery}
