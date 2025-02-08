# This file is part of beets.
# Copyright 2016, Fabrice Laporte.
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

"""Tests for the 'bucket' plugin."""

from datetime import datetime

import pytest

from beets import config, ui
from beets.test.helper import BeetsTestCase
from beetsplug import bucket


class BucketPluginTest(BeetsTestCase):
    def setUp(self):
        super().setUp()
        self.plugin = bucket.BucketPlugin()

    def _setup_config(
        self,
        bucket_year=[],
        bucket_alpha=[],
        bucket_alpha_regex={},
        extrapolate=False,
    ):
        config["bucket"]["bucket_year"] = bucket_year
        config["bucket"]["bucket_alpha"] = bucket_alpha
        config["bucket"]["bucket_alpha_regex"] = bucket_alpha_regex
        config["bucket"]["extrapolate"] = extrapolate
        self.plugin.setup()

    def test_year_single_year(self):
        """If a single year is given, range starts from this year and stops at
        the year preceding the one of next bucket."""
        self._setup_config(bucket_year=["1950s", "1970s"])
        assert self.plugin._tmpl_bucket("1959") == "1950s"
        assert self.plugin._tmpl_bucket("1969") == "1950s"

    def test_year_single_year_last_folder(self):
        """If a single year is given for the last bucket, extend it to current
        year."""
        self._setup_config(bucket_year=["1950", "1970"])
        assert self.plugin._tmpl_bucket("2014") == "1970"
        next_year = datetime.now().year + 1
        assert self.plugin._tmpl_bucket(str(next_year)) == str(next_year)

    def test_year_two_years(self):
        """Buckets can be named with the 'from-to' syntax."""
        self._setup_config(bucket_year=["1950-59", "1960-1969"])
        assert self.plugin._tmpl_bucket("1959") == "1950-59"
        assert self.plugin._tmpl_bucket("1969") == "1960-1969"

    def test_year_multiple_years(self):
        """Buckets can be named by listing all the years"""
        self._setup_config(bucket_year=["1950,51,52,53"])
        assert self.plugin._tmpl_bucket("1953") == "1950,51,52,53"
        assert self.plugin._tmpl_bucket("1974") == "1974"

    def test_year_out_of_range(self):
        """If no range match, return the year"""
        self._setup_config(bucket_year=["1950-59", "1960-69"])
        assert self.plugin._tmpl_bucket("1974") == "1974"
        self._setup_config(bucket_year=[])
        assert self.plugin._tmpl_bucket("1974") == "1974"

    def test_year_out_of_range_extrapolate(self):
        """If no defined range match, extrapolate all ranges using the most
        common syntax amongst existing buckets and return the matching one."""
        self._setup_config(bucket_year=["1950-59", "1960-69"], extrapolate=True)
        assert self.plugin._tmpl_bucket("1914") == "1910-19"
        # pick single year format
        self._setup_config(
            bucket_year=["1962-81", "2002", "2012"], extrapolate=True
        )
        assert self.plugin._tmpl_bucket("1983") == "1982"
        # pick from-end format
        self._setup_config(
            bucket_year=["1962-81", "2002", "2012-14"], extrapolate=True
        )
        assert self.plugin._tmpl_bucket("1983") == "1982-01"
        # extrapolate add ranges, but never modifies existing ones
        self._setup_config(
            bucket_year=["1932", "1942", "1952", "1962-81", "2002"],
            extrapolate=True,
        )
        assert self.plugin._tmpl_bucket("1975") == "1962-81"

    def test_alpha_all_chars(self):
        """Alphabet buckets can be named by listing all their chars"""
        self._setup_config(bucket_alpha=["ABCD", "FGH", "IJKL"])
        assert self.plugin._tmpl_bucket("garry") == "FGH"

    def test_alpha_first_last_chars(self):
        """Alphabet buckets can be named by listing the 'from-to' syntax"""
        self._setup_config(bucket_alpha=["0->9", "A->D", "F-H", "I->Z"])
        assert self.plugin._tmpl_bucket("garry") == "F-H"
        assert self.plugin._tmpl_bucket("2pac") == "0->9"

    def test_alpha_out_of_range(self):
        """If no range match, return the initial"""
        self._setup_config(bucket_alpha=["ABCD", "FGH", "IJKL"])
        assert self.plugin._tmpl_bucket("errol") == "E"
        self._setup_config(bucket_alpha=[])
        assert self.plugin._tmpl_bucket("errol") == "E"

    def test_alpha_regex(self):
        """Check regex is used"""
        self._setup_config(
            bucket_alpha=["foo", "bar"],
            bucket_alpha_regex={"foo": "^[a-d]", "bar": "^[e-z]"},
        )
        assert self.plugin._tmpl_bucket("alpha") == "foo"
        assert self.plugin._tmpl_bucket("delta") == "foo"
        assert self.plugin._tmpl_bucket("zeta") == "bar"
        assert self.plugin._tmpl_bucket("Alpha") == "A"

    def test_alpha_regex_mix(self):
        """Check mixing regex and non-regex is possible"""
        self._setup_config(
            bucket_alpha=["A - D", "E - L"],
            bucket_alpha_regex={"A - D": "^[0-9a-dA-D…äÄ]"},
        )
        assert self.plugin._tmpl_bucket("alpha") == "A - D"
        assert self.plugin._tmpl_bucket("Ärzte") == "A - D"
        assert self.plugin._tmpl_bucket("112") == "A - D"
        assert self.plugin._tmpl_bucket("…and Oceans") == "A - D"
        assert self.plugin._tmpl_bucket("Eagles") == "E - L"

    def test_bad_alpha_range_def(self):
        """If bad alpha range definition, a UserError is raised."""
        with pytest.raises(ui.UserError):
            self._setup_config(bucket_alpha=["$%"])

    def test_bad_year_range_def_no4digits(self):
        """If bad year range definition, a UserError is raised.
        Range origin must be expressed on 4 digits.
        """
        with pytest.raises(ui.UserError):
            self._setup_config(bucket_year=["62-64"])

    def test_bad_year_range_def_nodigits(self):
        """If bad year range definition, a UserError is raised.
        At least the range origin must be declared.
        """
        with pytest.raises(ui.UserError):
            self._setup_config(bucket_year=["nodigits"])

    def check_span_from_str(self, sstr, dfrom, dto):
        d = bucket.span_from_str(sstr)
        assert dfrom == d["from"]
        assert dto == d["to"]

    def test_span_from_str(self):
        self.check_span_from_str("1980 2000", 1980, 2000)
        self.check_span_from_str("1980 00", 1980, 2000)
        self.check_span_from_str("1930 00", 1930, 2000)
        self.check_span_from_str("1930 50", 1930, 1950)
