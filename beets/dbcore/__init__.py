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

"""DBCore is an abstract database package that forms the basis for beets'
Library.
"""

from .db import Database, Model, Results
from .query import (
    AndQuery,
    FieldQuery,
    InvalidQueryError,
    MatchQuery,
    OrQuery,
    Query,
)
from .queryparse import (
    parse_sorted_query,
    query_from_strings,
    sort_from_strings,
)
from .types import Type

__all__ = [
    "AndQuery",
    "Database",
    "FieldQuery",
    "InvalidQueryError",
    "MatchQuery",
    "Model",
    "OrQuery",
    "Query",
    "Results",
    "Type",
    "parse_sorted_query",
    "query_from_strings",
    "sort_from_strings",
]
