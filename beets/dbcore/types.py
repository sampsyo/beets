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

"""Representation of type information for DBCore model fields."""

from __future__ import annotations

import typing
from abc import ABC
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from beets.util import str2bool

from .query import (
    BooleanQuery,
    FieldQueryType,
    NumericQuery,
    SQLiteType,
    SubstringQuery,
)


class ModelType(typing.Protocol):
    """Protocol that specifies the required constructor for model types,
    i.e. a function that takes any argument and attempts to parse it to the
    given type.
    """

    def __init__(self, value: Any = None): ...


# Generic type variables, used for the value type T and null type N (if
# nullable, else T and N are set to the same type for the concrete subclasses
# of Type).
if TYPE_CHECKING:
    N = TypeVar("N", default=Any)
    T = TypeVar("T", bound=ModelType, default=Any)
else:
    N = TypeVar("N")
    T = TypeVar("T", bound=ModelType)


class Type(ABC, Generic[T, N]):
    """An object encapsulating the type of a model field. Includes
    information about how to store, query, format, and parse a given
    field.
    """

    sql: str = "TEXT"
    """The SQLite column type for the value.
    """

    query: FieldQueryType = SubstringQuery
    """The `Query` subclass to be used when querying the field.
    """

    model_type: type[T]
    """The Python type that is used to represent the value in the model.

    The model is guaranteed to return a value of this type if the field
    is accessed.  To this end, the constructor is used by the `normalize`
    and `from_sql` methods and the `default` property.
    """

    @property
    def null(self) -> N:
        """The value to be exposed when the underlying value is None."""
        # Note that this default implementation only makes sense for T = N.
        # It would be better to implement `null()` only in subclasses, or
        # have a field null_type similar to `model_type` and use that here.
        return cast(N, self.model_type())

    def format(self, value: N | T) -> str:
        """Given a value of this type, produce a Unicode string
        representing the value. This is used in template evaluation.
        """
        if value is None:
            value = self.null
        # `self.null` might be `None`
        if value is None:
            return ""
        elif isinstance(value, bytes):
            return value.decode("utf-8", "ignore")
        else:
            return str(value)

    def parse(self, string: str) -> T | N:
        """Parse a (possibly human-written) string and return the
        indicated value of this type.
        """
        try:
            return self.model_type(string)
        except ValueError:
            return self.null

    def normalize(self, value: Any) -> T | N:
        """Given a value that will be assigned into a field of this
        type, normalize the value to have the appropriate type. This
        base implementation only reinterprets `None`.
        """
        # TYPING ERROR
        if value is None:
            return self.null
        else:
            # TODO This should eventually be replaced by
            # `self.model_type(value)`
            return cast(T, value)

    def from_sql(self, sql_value: SQLiteType) -> T | N:
        """Receives the value stored in the SQL backend and return the
        value to be stored in the model.

        For fixed fields the type of `value` is determined by the column
        type affinity given in the `sql` property and the SQL to Python
        mapping of the database adapter. For more information see:
        https://www.sqlite.org/datatype3.html
        https://docs.python.org/2/library/sqlite3.html#sqlite-and-python-types

        Flexible fields have the type affinity `TEXT`. This means the
        `sql_value` is either a `memoryview` or a `unicode` object`
        and the method must handle these in addition.
        """
        if isinstance(sql_value, memoryview):
            sql_value = bytes(sql_value).decode("utf-8", "ignore")
        if isinstance(sql_value, str):
            return self.parse(sql_value)
        else:
            return self.normalize(sql_value)

    def to_sql(self, model_value: Any) -> SQLiteType:
        """Convert a value as stored in the model object to a value used
        by the database adapter.
        """
        return model_value


# Reusable types.


class Default(Type[str, None]):
    model_type = str

    @property
    def null(self):
        return None


class BaseInteger(Type[int, N]):
    """A basic integer type."""

    sql = "INTEGER"
    query = NumericQuery
    model_type = int

    def normalize(self, value: Any) -> int | N:
        try:
            return self.model_type(round(float(value)))
        except ValueError:
            return self.null
        except TypeError:
            return self.null


class Integer(BaseInteger[int]):
    @property
    def null(self) -> int:
        return 0


class NullInteger(BaseInteger[None]):
    @property
    def null(self) -> None:
        return None


class BasePaddedInt(BaseInteger[N]):
    """An integer field that is formatted with a given number of digits,
    padded with zeroes.
    """

    def __init__(self, digits: int):
        self.digits = digits

    def format(self, value: int | N) -> str:
        return "{0:0{1}d}".format(value or 0, self.digits)


class PaddedInt(BasePaddedInt[int]):
    pass


class NullPaddedInt(BasePaddedInt[None]):
    """Same as `PaddedInt`, but does not normalize `None` to `0`."""

    @property
    def null(self) -> None:
        return None


class ScaledInt(Integer):
    """An integer whose formatting operation scales the number by a
    constant and adds a suffix. Good for units with large magnitudes.
    """

    def __init__(self, unit: int, suffix: str = ""):
        self.unit = unit
        self.suffix = suffix

    def format(self, value: int) -> str:
        return "{}{}".format((value or 0) // self.unit, self.suffix)


class Id(NullInteger):
    """An integer used as the row id or a foreign key in a SQLite table.
    This type is nullable: None values are not translated to zero.
    """

    @property
    def null(self) -> None:
        return None

    def __init__(self, primary: bool = True):
        if primary:
            self.sql = "INTEGER PRIMARY KEY"


class BaseFloat(Type[float, N]):
    """A basic floating-point type. The `digits` parameter specifies how
    many decimal places to use in the human-readable representation.
    """

    sql = "REAL"
    query: FieldQueryType = NumericQuery
    model_type = float

    def __init__(self, digits: int = 1):
        self.digits = digits

    def format(self, value: float | N) -> str:
        return "{0:.{1}f}".format(value or 0, self.digits)


class Float(BaseFloat[float]):
    """Floating-point type that normalizes `None` to `0.0`."""

    @property
    def null(self) -> float:
        return 0.0


class NullFloat(BaseFloat[None]):
    """Same as `Float`, but does not normalize `None` to `0.0`."""

    @property
    def null(self) -> None:
        return None


class BaseString(Type[T, N]):
    """A Unicode string type."""

    sql = "TEXT"
    query = SubstringQuery

    def normalize(self, value: Any) -> T | N:
        if value is None:
            return self.null
        else:
            return self.model_type(value)


class String(BaseString[str, Any]):
    """A Unicode string type."""

    model_type = str


class DelimitedString(BaseString[list[str], list[str]]):
    """A list of Unicode strings, represented in-database by a single string
    containing delimiter-separated values.
    """

    model_type = list

    def __init__(self, delimiter: str):
        self.delimiter = delimiter

    def format(self, value: list[str]):
        return self.delimiter.join(value)

    def parse(self, string: str):
        if not string:
            return []
        return string.split(self.delimiter)

    def normalize(self, value: Any) -> list[str]:
        if not value:
            return []

        return value.split(self.delimiter) if isinstance(value, str) else value

    def to_sql(self, model_value: list[str]) -> str:
        return self.delimiter.join(model_value)


class Boolean(Type):
    """A boolean type."""

    sql = "INTEGER"
    query = BooleanQuery
    model_type = bool

    def format(self, value: bool) -> str:
        return str(bool(value))

    def parse(self, string: str) -> bool:
        return str2bool(string)


# Shared instances of common types.
DEFAULT = Default()
INTEGER = Integer()
PRIMARY_ID = Id(True)
FOREIGN_ID = Id(False)
FLOAT = Float()
NULL_FLOAT = NullFloat()
STRING = String()
BOOLEAN = Boolean()
SEMICOLON_SPACE_DSV = DelimitedString(delimiter="; ")

# Will set the proper null char in mediafile
MULTI_VALUE_DSV = DelimitedString(delimiter="\\␀")
