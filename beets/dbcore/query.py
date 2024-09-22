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

"""The Query type hierarchy for DBCore."""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import reduce
from operator import mul, or_
from typing import (
    TYPE_CHECKING,
    Any,
    Collection,
    Generic,
    Iterator,
    List,
    MutableSequence,
    Optional,
    Pattern,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from beets import util

if TYPE_CHECKING:
    from beets.dbcore import Model


class ParsingError(ValueError):
    """Abstract class for any unparsable user-requested album/query
    specification.
    """


class InvalidQueryError(ParsingError):
    """Represent any kind of invalid query.

    The query should be a unicode string or a list, which will be space-joined.
    """

    def __init__(self, query, explanation):
        if isinstance(query, list):
            query = " ".join(query)
        message = f"'{query}': {explanation}"
        super().__init__(message)


class InvalidQueryArgumentValueError(ParsingError):
    """Represent a query argument that could not be converted as expected.

    It exists to be caught in upper stack levels so a meaningful (i.e. with the
    query) InvalidQueryError can be raised.
    """

    def __init__(self, what, expected, detail=None):
        message = f"'{what}' is not {expected}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


class Query(ABC):
    """An abstract class representing a query into the database."""

    @property
    def field_names(self) -> Set[str]:
        """Return a set with field names that this query operates on."""
        return set()

    def clause(self) -> Tuple[Optional[str], Sequence[Any]]:
        """Generate an SQLite expression implementing the query.

        Return (clause, subvals) where clause is a valid sqlite
        WHERE clause implementing the query and subvals is a list of
        items to be substituted for ?s in the clause.

        The default implementation returns None, falling back to a slow query
        using `match()`.
        """
        return None, ()

    @abstractmethod
    def match(self, obj: Model):
        """Check whether this query matches a given Model. Can be used to
        perform queries on arbitrary sets of Model.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    def __eq__(self, other) -> bool:
        return type(self) is type(other)

    def __hash__(self) -> int:
        """Minimalistic default implementation of a hash.

        Given the implementation if __eq__ above, this is
        certainly correct.
        """
        return hash(type(self))


P = TypeVar("P")
SQLiteType = Union[str, bytes, float, int, memoryview]
AnySQLiteType = TypeVar("AnySQLiteType", bound=SQLiteType)


class FieldQuery(Query, Generic[P]):
    """An abstract query that searches in a specific field for a
    pattern. Subclasses must provide a `value_match` class method, which
    determines whether a certain pattern string matches a certain value
    string. Subclasses may also provide `col_clause` to implement the
    same matching functionality in SQLite.
    """

    @property
    def field(self) -> str:
        return (
            f"{self.table}.{self.field_name}" if self.table else self.field_name
        )

    @property
    def field_names(self) -> Set[str]:
        """Return a set with field names that this query operates on."""
        return {self.field_name}

    def __init__(self, field_name: str, pattern: P, fast: bool = True):
        self.table, _, self.field_name = field_name.rpartition(".")
        self.pattern = pattern
        self.fast = fast

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        # TODO: Avoid having to insert raw text into SQL clauses.
        return self.field, ()

    def clause(self) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        if self.fast:
            return self.col_clause()
        else:
            # Matching a flexattr. This is a slow query.
            return None, ()

    @classmethod
    def value_match(cls, pattern: P, value: Any):
        """Determine whether the value matches the pattern."""
        raise NotImplementedError()

    def match(self, obj: Model) -> bool:
        return self.value_match(self.pattern, obj.get(self.field_name))

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({repr(self.field_name)}, {repr(self.pattern)}, "
            f"fast={self.fast})"
        )

    def __eq__(self, other) -> bool:
        return (
            super().__eq__(other)
            and self.field_name == other.field_name
            and self.pattern == other.pattern
        )

    def __hash__(self) -> int:
        return hash((self.field_name, hash(self.pattern)))


class MatchQuery(FieldQuery[AnySQLiteType]):
    """A query that looks for exact matches in an Model field."""

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return self.field + " = ?", [self.pattern]

    @classmethod
    def value_match(cls, pattern: AnySQLiteType, value: Any) -> bool:
        return pattern == value


class NoneQuery(FieldQuery[None]):
    """A query that checks whether a field is null."""

    def __init__(self, field, fast: bool = True):
        super().__init__(field, None, fast)

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return self.field + " IS NULL", ()

    def match(self, obj: Model) -> bool:
        return obj.get(self.field_name) is None

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({repr(self.field_name)}, {self.fast})"
        )


class StringFieldQuery(FieldQuery[P]):
    """A FieldQuery that converts values to strings before matching
    them.
    """

    @classmethod
    def value_match(cls, pattern: P, value: Any):
        """Determine whether the value matches the pattern. The value
        may have any type.
        """
        return cls.string_match(pattern, util.as_string(value))

    @classmethod
    def string_match(
        cls,
        pattern: P,
        value: str,
    ) -> bool:
        """Determine whether the value matches the pattern. Both
        arguments are strings. Subclasses implement this method.
        """
        raise NotImplementedError()


class StringQuery(StringFieldQuery[str]):
    """A query that matches a whole string in a specific Model field."""

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        search = (
            self.pattern.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        clause = self.field + " like ? escape '\\'"
        subvals = [search]
        return clause, subvals

    @classmethod
    def string_match(cls, pattern: str, value: str) -> bool:
        return pattern.lower() == value.lower()


class SubstringQuery(StringFieldQuery[str]):
    """A query that matches a substring in a specific Model field."""

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        pattern = (
            self.pattern.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        search = "%" + pattern + "%"
        clause = self.field + " like ? escape '\\'"
        subvals = [search]
        return clause, subvals

    @classmethod
    def string_match(cls, pattern: str, value: str) -> bool:
        return pattern.lower() in value.lower()


class RegexpQuery(StringFieldQuery[Pattern[str]]):
    """A query that matches a regular expression in a specific Model field.

    Raises InvalidQueryError when the pattern is not a valid regular
    expression.
    """

    def __init__(self, field_name: str, pattern: str, fast: bool = True):
        pattern = self._normalize(pattern)
        try:
            pattern_re = re.compile(pattern)
        except re.error as exc:
            # Invalid regular expression.
            raise InvalidQueryArgumentValueError(
                pattern, "a regular expression", format(exc)
            )

        super().__init__(field_name, pattern_re, fast)

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return f" regexp({self.field}, ?)", [self.pattern.pattern]

    @staticmethod
    def _normalize(s: str) -> str:
        """Normalize a Unicode string's representation (used on both
        patterns and matched values).
        """
        return unicodedata.normalize("NFC", s)

    @classmethod
    def string_match(cls, pattern: Pattern, value: str) -> bool:
        return pattern.search(cls._normalize(value)) is not None


class BooleanQuery(MatchQuery[int]):
    """Matches a boolean field. Pattern should either be a boolean or a
    string reflecting a boolean.
    """

    def __init__(
        self,
        field_name: str,
        pattern: bool,
        fast: bool = True,
    ):
        if isinstance(pattern, str):
            pattern = util.str2bool(pattern)

        pattern_int = int(pattern)

        super().__init__(field_name, pattern_int, fast)


class BytesQuery(FieldQuery[bytes]):
    """Match a raw bytes field (i.e., a path). This is a necessary hack
    to work around the `sqlite3` module's desire to treat `bytes` and
    `unicode` equivalently in Python 2. Always use this query instead of
    `MatchQuery` when matching on BLOB values.
    """

    def __init__(self, field_name: str, pattern: Union[bytes, str, memoryview]):
        # Use a buffer/memoryview representation of the pattern for SQLite
        # matching. This instructs SQLite to treat the blob as binary
        # rather than encoded Unicode.
        if isinstance(pattern, (str, bytes)):
            if isinstance(pattern, str):
                bytes_pattern = pattern.encode("utf-8")
            else:
                bytes_pattern = pattern
            self.buf_pattern = memoryview(bytes_pattern)
        elif isinstance(pattern, memoryview):
            self.buf_pattern = pattern
            bytes_pattern = bytes(pattern)
        else:
            raise ValueError("pattern must be bytes, str, or memoryview")

        super().__init__(field_name, bytes_pattern)

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return self.field + " = ?", [self.buf_pattern]

    @classmethod
    def value_match(cls, pattern: bytes, value: Any) -> bool:
        return pattern == value


class NumericQuery(FieldQuery[str]):
    """Matches numeric fields. A syntax using Ruby-style range ellipses
    (``..``) lets users specify one- or two-sided ranges. For example,
    ``year:2001..`` finds music released since the turn of the century.

    Raises InvalidQueryError when the pattern does not represent an int or
    a float.
    """

    def _convert(self, s: str) -> Union[float, int, None]:
        """Convert a string to a numeric type (float or int).

        Return None if `s` is empty.
        Raise an InvalidQueryError if the string cannot be converted.
        """
        # This is really just a bit of fun premature optimization.
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                raise InvalidQueryArgumentValueError(s, "an int or a float")

    def __init__(self, field_name: str, pattern: str, fast: bool = True):
        super().__init__(field_name, pattern, fast)

        parts = pattern.split("..", 1)
        if len(parts) == 1:
            # No range.
            self.point = self._convert(parts[0])
            self.rangemin = None
            self.rangemax = None
        else:
            # One- or two-sided range.
            self.point = None
            self.rangemin = self._convert(parts[0])
            self.rangemax = self._convert(parts[1])

    def match(self, obj: Model) -> bool:
        if self.field_name not in obj:
            return False
        value = obj[self.field_name]
        if isinstance(value, str):
            value = self._convert(value)

        if self.point is not None:
            return value == self.point
        else:
            if self.rangemin is not None and value < self.rangemin:
                return False
            if self.rangemax is not None and value > self.rangemax:
                return False
            return True

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        if self.point is not None:
            return self.field + "=?", (self.point,)
        else:
            if self.rangemin is not None and self.rangemax is not None:
                return (
                    "{0} >= ? AND {0} <= ?".format(self.field),
                    (self.rangemin, self.rangemax),
                )
            elif self.rangemin is not None:
                return f"{self.field} >= ?", (self.rangemin,)
            elif self.rangemax is not None:
                return f"{self.field} <= ?", (self.rangemax,)
            else:
                return "1", ()


class InQuery(Generic[AnySQLiteType], FieldQuery[Sequence[AnySQLiteType]]):
    """Query which matches values in the given set."""

    field_name: str
    pattern: Sequence[AnySQLiteType]
    fast: bool = True

    @property
    def subvals(self) -> Sequence[SQLiteType]:
        return self.pattern

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        placeholders = ", ".join(["?"] * len(self.subvals))
        return f"{self.field_name} IN ({placeholders})", self.subvals

    @classmethod
    def value_match(
        cls, pattern: Sequence[AnySQLiteType], value: AnySQLiteType
    ) -> bool:
        return value in pattern


class CollectionQuery(Query):
    """An abstract query class that aggregates other queries. Can be
    indexed like a list to access the sub-queries.
    """

    @property
    def field_names(self) -> Set[str]:
        """Return a set with field names that this query operates on."""
        return reduce(or_, (sq.field_names for sq in self.subqueries))

    def __init__(self, subqueries: Sequence = ()):
        self.subqueries = subqueries

    # Act like a sequence.

    def __len__(self) -> int:
        return len(self.subqueries)

    def __getitem__(self, key):
        return self.subqueries[key]

    def __iter__(self) -> Iterator:
        return iter(self.subqueries)

    def __contains__(self, subq) -> bool:
        return subq in self.subqueries

    def clause_with_joiner(
        self,
        joiner: str,
    ) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        """Return a clause created by joining together the clauses of
        all subqueries with the string joiner (padded by spaces).
        """
        clause_parts = []
        subvals = []
        for subq in self.subqueries:
            subq_clause, subq_subvals = subq.clause()
            if not subq_clause:
                # Fall back to slow query.
                return None, ()
            clause_parts.append("(" + subq_clause + ")")
            subvals += subq_subvals
        clause = (" " + joiner + " ").join(clause_parts)
        return clause, subvals

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.subqueries)})"

    def __eq__(self, other) -> bool:
        return super().__eq__(other) and self.subqueries == other.subqueries

    def __hash__(self) -> int:
        """Since subqueries are mutable, this object should not be hashable.
        However and for conveniences purposes, it can be hashed.
        """
        return reduce(mul, map(hash, self.subqueries), 1)


class AnyFieldQuery(CollectionQuery):
    """A query that matches if a given FieldQuery subclass matches in
    any field. The individual field query class is provided to the
    constructor.
    """

    @property
    def field_names(self) -> Set[str]:
        """Return a set with field names that this query operates on."""
        return set(self.fields)

    def __init__(self, pattern, fields, cls: Type[FieldQuery]):
        self.pattern = pattern
        self.fields = fields
        self.query_class = cls

        subqueries = []
        for field in self.fields:
            subqueries.append(cls(field, pattern, True))
        # TYPING ERROR
        super().__init__(subqueries)

    def clause(self) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        return self.clause_with_joiner("or")

    def match(self, obj: Model) -> bool:
        for subq in self.subqueries:
            if subq.match(obj):
                return True
        return False

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({repr(self.pattern)}, {repr(self.fields)}, "
            f"{self.query_class.__name__})"
        )

    def __eq__(self, other) -> bool:
        return super().__eq__(other) and self.query_class == other.query_class

    def __hash__(self) -> int:
        return hash((self.pattern, tuple(self.fields), self.query_class))


class MutableCollectionQuery(CollectionQuery):
    """A collection query whose subqueries may be modified after the
    query is initialized.
    """

    subqueries: MutableSequence

    def __setitem__(self, key, value):
        self.subqueries[key] = value

    def __delitem__(self, key):
        del self.subqueries[key]


class AndQuery(MutableCollectionQuery):
    """A conjunction of a list of other queries."""

    def clause(self) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        return self.clause_with_joiner("and")

    def match(self, obj: Model) -> bool:
        return all(q.match(obj) for q in self.subqueries)


class OrQuery(MutableCollectionQuery):
    """A conjunction of a list of other queries."""

    def clause(self) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        return self.clause_with_joiner("or")

    def match(self, obj: Model) -> bool:
        return any(q.match(obj) for q in self.subqueries)


class NotQuery(Query):
    """A query that matches the negation of its `subquery`, as a shortcut for
    performing `not(subquery)` without using regular expressions.
    """

    @property
    def field_names(self) -> Set[str]:
        """Return a set with field names that this query operates on."""
        return self.subquery.field_names

    def __init__(self, subquery):
        self.subquery = subquery

    def clause(self) -> Tuple[Optional[str], Sequence[SQLiteType]]:
        clause, subvals = self.subquery.clause()
        if clause:
            return f"not ({clause})", subvals
        else:
            # If there is no clause, there is nothing to negate. All the logic
            # is handled by match() for slow queries.
            return clause, subvals

    def match(self, obj: Model) -> bool:
        return not self.subquery.match(obj)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.subquery)})"

    def __eq__(self, other) -> bool:
        return super().__eq__(other) and self.subquery == other.subquery

    def __hash__(self) -> int:
        return hash(("not", hash(self.subquery)))


class TrueQuery(Query):
    """A query that always matches."""

    def clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return "1", ()

    def match(self, obj: Model) -> bool:
        return True


class FalseQuery(Query):
    """A query that never matches."""

    def clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        return "0", ()

    def match(self, obj: Model) -> bool:
        return False


# Time/date queries.


def _parse_periods(pattern: str) -> Tuple[Optional[Period], Optional[Period]]:
    """Parse a string containing two dates separated by two dots (..).
    Return a pair of `Period` objects.
    """
    parts = pattern.split("..", 1)
    if len(parts) == 1:
        instant = Period.parse(parts[0])
        return (instant, instant)
    else:
        start = Period.parse(parts[0])
        end = Period.parse(parts[1])
        return (start, end)


class Period:
    """A period of time given by a date, time and precision.

    Example: 2014-01-01 10:50:30 with precision 'month' represents all
    instants of time during January 2014.
    """

    precisions = ("year", "month", "day", "hour", "minute", "second")
    date_formats = (
        ("%Y",),  # year
        ("%Y-%m",),  # month
        ("%Y-%m-%d",),  # day
        ("%Y-%m-%dT%H", "%Y-%m-%d %H"),  # hour
        ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"),  # minute
        ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"),  # second
    )
    relative_units = {"y": 365, "m": 30, "w": 7, "d": 1}
    relative_re = (
        "(?P<sign>[+|-]?)(?P<quantity>[0-9]+)" + "(?P<timespan>[y|m|w|d])"
    )

    def __init__(self, date: datetime, precision: str):
        """Create a period with the given date (a `datetime` object) and
        precision (a string, one of "year", "month", "day", "hour", "minute",
        or "second").
        """
        if precision not in Period.precisions:
            raise ValueError(f"Invalid precision {precision}")
        self.date = date
        self.precision = precision

    @classmethod
    def parse(cls: Type["Period"], string: str) -> Optional["Period"]:
        """Parse a date and return a `Period` object or `None` if the
        string is empty, or raise an InvalidQueryArgumentValueError if
        the string cannot be parsed to a date.

        The date may be absolute or relative. Absolute dates look like
        `YYYY`, or `YYYY-MM-DD`, or `YYYY-MM-DD HH:MM:SS`, etc. Relative
        dates have three parts:

        - Optionally, a ``+`` or ``-`` sign indicating the future or the
          past. The default is the future.
        - A number: how much to add or subtract.
        - A letter indicating the unit: days, weeks, months or years
          (``d``, ``w``, ``m`` or ``y``). A "month" is exactly 30 days
          and a "year" is exactly 365 days.
        """

        def find_date_and_format(
            string: str,
        ) -> Union[Tuple[None, None], Tuple[datetime, int]]:
            for ord, format in enumerate(cls.date_formats):
                for format_option in format:
                    try:
                        date = datetime.strptime(string, format_option)
                        return date, ord
                    except ValueError:
                        # Parsing failed.
                        pass
            return (None, None)

        if not string:
            return None

        date: Optional[datetime]

        # Check for a relative date.
        match_dq = re.match(cls.relative_re, string)
        if match_dq:
            sign = match_dq.group("sign")
            quantity = match_dq.group("quantity")
            timespan = match_dq.group("timespan")

            # Add or subtract the given amount of time from the current
            # date.
            multiplier = -1 if sign == "-" else 1
            days = cls.relative_units[timespan]
            date = (
                datetime.now()
                + timedelta(days=int(quantity) * days) * multiplier
            )
            return cls(date, cls.precisions[5])

        # Check for an absolute date.
        date, ordinal = find_date_and_format(string)
        if date is None or ordinal is None:
            raise InvalidQueryArgumentValueError(
                string, "a valid date/time string"
            )
        precision = cls.precisions[ordinal]
        return cls(date, precision)

    def open_right_endpoint(self) -> datetime:
        """Based on the precision, convert the period to a precise
        `datetime` for use as a right endpoint in a right-open interval.
        """
        precision = self.precision
        date = self.date
        if "year" == self.precision:
            return date.replace(year=date.year + 1, month=1)
        elif "month" == precision:
            if date.month < 12:
                return date.replace(month=date.month + 1)
            else:
                return date.replace(year=date.year + 1, month=1)
        elif "day" == precision:
            return date + timedelta(days=1)
        elif "hour" == precision:
            return date + timedelta(hours=1)
        elif "minute" == precision:
            return date + timedelta(minutes=1)
        elif "second" == precision:
            return date + timedelta(seconds=1)
        else:
            raise ValueError(f"unhandled precision {precision}")


class DateInterval:
    """A closed-open interval of dates.

    A left endpoint of None means since the beginning of time.
    A right endpoint of None means towards infinity.
    """

    def __init__(self, start: Optional[datetime], end: Optional[datetime]):
        if start is not None and end is not None and not start < end:
            raise ValueError(f"start date {start} is not before end date {end}")
        self.start = start
        self.end = end

    @classmethod
    def from_periods(
        cls,
        start: Optional[Period],
        end: Optional[Period],
    ) -> DateInterval:
        """Create an interval with two Periods as the endpoints."""
        end_date = end.open_right_endpoint() if end is not None else None
        start_date = start.date if start is not None else None
        return cls(start_date, end_date)

    def contains(self, date: datetime) -> bool:
        if self.start is not None and date < self.start:
            return False
        if self.end is not None and date >= self.end:
            return False
        return True

    def __str__(self) -> str:
        return f"[{self.start}, {self.end})"


class DateQuery(FieldQuery[str]):
    """Matches date fields stored as seconds since Unix epoch time.

    Dates can be specified as ``year-month-day`` strings where only year
    is mandatory.

    The value of a date field can be matched against a date interval by
    using an ellipsis interval syntax similar to that of NumericQuery.
    """

    def __init__(self, field_name: str, pattern: str, fast: bool = True):
        super().__init__(field_name, pattern, fast)
        start, end = _parse_periods(pattern)
        self.interval = DateInterval.from_periods(start, end)

    def match(self, obj: Model) -> bool:
        if self.field_name not in obj:
            return False
        timestamp = float(obj[self.field_name])
        date = datetime.fromtimestamp(timestamp)
        return self.interval.contains(date)

    def col_clause(self) -> Tuple[str, Sequence[SQLiteType]]:
        clause_parts = []
        subvals = []

        # Convert the `datetime` objects to an integer number of seconds since
        # the (local) Unix epoch using `datetime.timestamp()`.
        if self.interval.start:
            clause_parts.append(f"{self.field} >= ?")
            subvals.append(int(self.interval.start.timestamp()))

        if self.interval.end:
            clause_parts.append(f"{self.field} < ?")
            subvals.append(int(self.interval.end.timestamp()))

        if clause_parts:
            # One- or two-sided interval.
            clause = " AND ".join(clause_parts)
        else:
            # Match any date.
            clause = "1"
        return clause, subvals


class DurationQuery(NumericQuery):
    """NumericQuery that allow human-friendly (M:SS) time interval formats.

    Converts the range(s) to a float value, and delegates on NumericQuery.

    Raises InvalidQueryError when the pattern does not represent an int, float
    or M:SS time interval.
    """

    def _convert(self, s: str) -> Optional[float]:
        """Convert a M:SS or numeric string to a float.

        Return None if `s` is empty.
        Raise an InvalidQueryError if the string cannot be converted.
        """
        if not s:
            return None
        try:
            return util.raw_seconds_short(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                raise InvalidQueryArgumentValueError(
                    s, "a M:SS string or a float"
                )


# Sorting.


class Sort:
    """An abstract class representing a sort operation for a query into
    the database.
    """

    def order_clause(self) -> Optional[str]:
        """Generates a SQL fragment to be used in a ORDER BY clause, or
        None if no fragment is used (i.e., this is a slow sort).
        """
        return None

    def sort(self, items: List) -> List:
        """Sort the list of objects and return a list."""
        return sorted(items)

    def is_slow(self) -> bool:
        """Indicate whether this query is *slow*, meaning that it cannot
        be executed in SQL and must be executed in Python.
        """
        return False

    def __hash__(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return type(self) is type(other)

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class MultipleSort(Sort):
    """Sort that encapsulates multiple sub-sorts."""

    def __init__(self, sorts: Optional[List[Sort]] = None):
        self.sorts = sorts or []

    def add_sort(self, sort: Sort):
        self.sorts.append(sort)

    def order_clause(self) -> str:
        """Return the list SQL clauses for those sub-sorts for which we can be
        (at least partially) fast.

        A contiguous suffix of fast (SQL-capable) sub-sorts are
        executable in SQL. The remaining, even if they are fast
        independently, must be executed slowly.
        """
        order_strings = []
        for sort in reversed(self.sorts):
            clause = sort.order_clause()
            if clause is None:
                break
            order_strings.append(clause)
        order_strings.reverse()

        return ", ".join(order_strings)

    def is_slow(self) -> bool:
        for sort in self.sorts:
            if sort.is_slow():
                return True
        return False

    def sort(self, items):
        slow_sorts = []
        switch_slow = False
        for sort in reversed(self.sorts):
            if switch_slow:
                slow_sorts.append(sort)
            elif sort.order_clause() is None:
                switch_slow = True
                slow_sorts.append(sort)
            else:
                pass

        for sort in slow_sorts:
            items = sort.sort(items)
        return items

    def __repr__(self):
        return f"{self.__class__.__name__}({repr(self.sorts)})"

    def __hash__(self):
        return hash(tuple(self.sorts))

    def __eq__(self, other):
        return super().__eq__(other) and self.sorts == other.sorts


class FieldSort(Sort):
    """An abstract sort criterion that orders by a specific field (of
    any kind).
    """

    def __init__(
        self,
        field,
        ascending: bool = True,
        case_insensitive: bool = True,
    ):
        self.field = field
        self.ascending = ascending
        self.case_insensitive = case_insensitive

    def sort(self, objs: Collection):
        # TODO: Conversion and null-detection here. In Python 3,
        # comparisons with None fail. We should also support flexible
        # attributes with different types without falling over.

        def key(obj: Model) -> Any:
            field_val = obj.get(self.field, "")
            if self.case_insensitive and isinstance(field_val, str):
                field_val = field_val.lower()
            return field_val

        return sorted(objs, key=key, reverse=not self.ascending)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"({repr(self.field)}, ascending={repr(self.ascending)})"
        )

    def __hash__(self) -> int:
        return hash((self.field, self.ascending))

    def __eq__(self, other) -> bool:
        return (
            super().__eq__(other)
            and self.field == other.field
            and self.ascending == other.ascending
        )


class FixedFieldSort(FieldSort):
    """Sort object to sort on a fixed field."""

    def order_clause(self) -> str:
        order = "ASC" if self.ascending else "DESC"
        if self.case_insensitive:
            field = (
                "(CASE "
                'WHEN TYPEOF({0})="text" THEN LOWER({0}) '
                'WHEN TYPEOF({0})="blob" THEN LOWER({0}) '
                "ELSE {0} END)".format(self.field)
            )
        else:
            field = self.field
        return f"{field} {order}"


class SlowFieldSort(FieldSort):
    """A sort criterion by some model field other than a fixed field:
    i.e., a computed or flexible field.
    """

    def is_slow(self) -> bool:
        return True


class NullSort(Sort):
    """No sorting. Leave results unsorted."""

    def sort(self, items: List) -> List:
        return items

    def __nonzero__(self) -> bool:
        return self.__bool__()

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other) -> bool:
        return type(self) is type(other) or other is None

    def __hash__(self) -> int:
        return 0
