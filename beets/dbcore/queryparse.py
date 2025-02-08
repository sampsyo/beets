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

"""Parsing of strings into DBCore queries."""

from __future__ import annotations

import itertools
import re
from typing import TYPE_CHECKING

from . import query

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from ..library import LibModel
    from .query import FieldQueryType, Sort

    Prefixes = dict[str, FieldQueryType]


PARSE_QUERY_PART_REGEX = re.compile(
    # Non-capturing optional segment for the keyword.
    r"(-|\^)?"  # Negation prefixes.
    r"(?:"
    r"(\S+?)"  # The field key.
    r"(?<!\\):"  # Unescaped :
    r")?"
    r"(.*)",  # The term itself.
    re.I,  # Case-insensitive.
)


def parse_query_part(
    part: str,
    query_classes: dict[str, FieldQueryType] = {},
    prefixes: Prefixes = {},
    default_class: type[query.SubstringQuery] = query.SubstringQuery,
) -> tuple[str | None, str, FieldQueryType, bool]:
    """Parse a single *query part*, which is a chunk of a complete query
    string representing a single criterion.

    A query part is a string consisting of:
    - A *pattern*: the value to look for.
    - Optionally, a *field name* preceding the pattern, separated by a
      colon. So in `foo:bar`, `foo` is the field name and `bar` is the
      pattern.
    - Optionally, a *query prefix* just before the pattern (and after the
      optional colon) indicating the type of query that should be used. For
      example, in `~foo`, `~` might be a prefix. (The set of prefixes to
      look for is given in the `prefixes` parameter.)
    - Optionally, a negation indicator, `-` or `^`, at the very beginning.

    Both prefixes and the separating `:` character may be escaped with a
    backslash to avoid their normal meaning.

    The function returns a tuple consisting of:
    - The field name: a string or None if it's not present.
    - The pattern, a string.
    - The query class to use, which inherits from the base
      :class:`Query` type.
    - A negation flag, a bool.

    The three optional parameters determine which query class is used (i.e.,
    the third return value). They are:
    - `query_classes`, which maps field names to query classes. These
      are used when no explicit prefix is present.
    - `prefixes`, which maps prefix strings to query classes.
    - `default_class`, the fallback when neither the field nor a prefix
      indicates a query class.

    So the precedence for determining which query class to return is:
    prefix, followed by field, and finally the default.

    For example, assuming the `:` prefix is used for `RegexpQuery`:
    - `'stapler'` -> `(None, 'stapler', SubstringQuery, False)`
    - `'color:red'` -> `('color', 'red', SubstringQuery, False)`
    - `':^Quiet'` -> `(None, '^Quiet', RegexpQuery, False)`, because
      the `^` follows the `:`
    - `'color::b..e'` -> `('color', 'b..e', RegexpQuery, False)`
    - `'-color:red'` -> `('color', 'red', SubstringQuery, True)`
    """
    # Apply the regular expression and extract the components.
    part = part.strip()
    match = PARSE_QUERY_PART_REGEX.match(part)

    assert match  # Regex should always match
    negate = bool(match.group(1))
    key = match.group(2)
    term = match.group(3).replace("\\:", ":")

    # Check whether there's a prefix in the query and use the
    # corresponding query type.
    for pre, query_class in prefixes.items():
        if term.startswith(pre):
            return key, term[len(pre) :], query_class, negate

    # No matching prefix, so use either the query class determined by
    # the field or the default as a fallback.
    query_class = query_classes.get(key, default_class)
    return key, term, query_class, negate


def construct_query_part(
    model_cls: type[LibModel],
    prefixes: Prefixes,
    query_part: str,
) -> query.Query:
    """Parse a *query part* string and return a :class:`Query` object.

    :param model_cls: The :class:`Model` class that this is a query for.
      This is used to determine the appropriate query types for the
      model's fields.
    :param prefixes: A map from prefix strings to :class:`Query` types.
    :param query_part: The string to parse.

    See the documentation for `parse_query_part` for more information on
    query part syntax.
    """
    # A shortcut for empty query parts.
    if not query_part:
        return query.TrueQuery()

    out_query: query.Query

    # Use `model_cls` to build up a map from field (or query) names to
    # `Query` classes.
    query_classes: dict[str, FieldQueryType] = {}
    for k, t in itertools.chain(
        model_cls._fields.items(), model_cls._types.items()
    ):
        query_classes[k] = t.query
    query_classes.update(model_cls._queries)  # Non-field queries.

    # Parse the string.
    key, pattern, query_class, negate = parse_query_part(
        query_part, query_classes, prefixes
    )

    if key is None:
        # If there's no key (field name) specified, this is a "match anything"
        # query.
        out_query = model_cls.any_field_query(pattern, query_class)
    else:
        # Field queries get constructed according to the name of the field
        # they are querying.
        out_query = model_cls.field_query(key.lower(), pattern, query_class)

    # Apply negation.
    if negate:
        return query.NotQuery(out_query)
    else:
        return out_query


# TYPING ERROR
def query_from_strings(
    query_cls: type[query.CollectionQuery],
    model_cls: type[LibModel],
    prefixes: Prefixes,
    query_parts: Collection[str],
) -> query.Query:
    """Creates a collection query of type `query_cls` from a list of
    strings in the format used by parse_query_part. `model_cls`
    determines how queries are constructed from strings.
    """
    subqueries = []
    for part in query_parts:
        subqueries.append(construct_query_part(model_cls, prefixes, part))
    if not subqueries:  # No terms in query.
        subqueries = [query.TrueQuery()]
    return query_cls(subqueries)


def construct_sort_part(
    model_cls: type[LibModel],
    part: str,
    case_insensitive: bool = True,
) -> Sort:
    """Create a `Sort` from a single string criterion.

    `model_cls` is the `Model` being queried. `part` is a single string
    ending in ``+`` or ``-`` indicating the sort. `case_insensitive`
    indicates whether or not the sort should be performed in a case
    sensitive manner.
    """
    assert part, "part must be a field name and + or -"
    field = part[:-1]
    assert field, "field is missing"
    direction = part[-1]
    assert direction in ("+", "-"), "part must end with + or -"
    is_ascending = direction == "+"

    if sort_cls := model_cls._sorts.get(field):
        if isinstance(sort_cls, query.SmartArtistSort):
            field = "albumartist" if model_cls.__name__ == "Album" else "artist"
    elif field in model_cls._fields:
        sort_cls = query.FixedFieldSort
    else:
        # Flexible or computed.
        sort_cls = query.SlowFieldSort

    return sort_cls(field, is_ascending, case_insensitive)


def sort_from_strings(
    model_cls: type[LibModel],
    sort_parts: Sequence[str],
    case_insensitive: bool = True,
) -> Sort:
    """Create a `Sort` from a list of sort criteria (strings)."""
    if not sort_parts:
        return query.NullSort()
    elif len(sort_parts) == 1:
        return construct_sort_part(model_cls, sort_parts[0], case_insensitive)
    else:
        sort = query.MultipleSort()
        for part in sort_parts:
            sort.add_sort(
                construct_sort_part(model_cls, part, case_insensitive)
            )
        return sort


def parse_sorted_query(
    model_cls: type[LibModel],
    parts: list[str],
    prefixes: Prefixes = {},
    case_insensitive: bool = True,
) -> tuple[query.Query, Sort]:
    """Given a list of strings, create the `Query` and `Sort` that they
    represent.
    """
    # Separate query token and sort token.
    query_parts = []
    sort_parts = []

    # Split up query in to comma-separated subqueries, each representing
    # an AndQuery, which need to be joined together in one OrQuery
    subquery_parts = []
    for part in parts + [","]:
        if part.endswith(","):
            # Ensure we can catch "foo, bar" as well as "foo , bar"
            last_subquery_part = part[:-1]
            if last_subquery_part:
                subquery_parts.append(last_subquery_part)
            # Parse the subquery in to a single AndQuery
            # TODO: Avoid needlessly wrapping AndQueries containing 1 subquery?
            query_parts.append(
                query_from_strings(
                    query.AndQuery, model_cls, prefixes, subquery_parts
                )
            )
            del subquery_parts[:]
        else:
            # Sort parts (1) end in + or -, (2) don't have a field, and
            # (3) consist of more than just the + or -.
            if part.endswith(("+", "-")) and ":" not in part and len(part) > 1:
                sort_parts.append(part)
            else:
                subquery_parts.append(part)

    # Avoid needlessly wrapping single statements in an OR
    q = query.OrQuery(query_parts) if len(query_parts) > 1 else query_parts[0]
    s = sort_from_strings(model_cls, sort_parts, case_insensitive)
    return q, s
