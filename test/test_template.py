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

"""Tests for template engine."""

import unittest

from beets.util import functemplate


def _normexpr(expr):
    """Normalize an Expression object's parts, collapsing multiple
    adjacent text blocks and removing empty text blocks. Generates a
    sequence of parts.
    """
    textbuf = []
    for part in expr.parts:
        if isinstance(part, str):
            textbuf.append(part)
        else:
            if textbuf:
                text = "".join(textbuf)
                if text:
                    yield text
                    textbuf = []
            yield part
    if textbuf:
        text = "".join(textbuf)
        if text:
            yield text


def _normparse(text):
    """Parse a template and then normalize the resulting Expression."""
    return _normexpr(functemplate._parse(text))


class ParseTest(unittest.TestCase):
    def test_empty_string(self):
        assert list(_normparse("")) == []

    def _assert_symbol(self, obj, ident):
        """Assert that an object is a Symbol with the given identifier."""
        assert isinstance(obj, functemplate.Symbol), f"not a Symbol: {obj}"
        assert obj.ident == ident, f"wrong identifier: {obj.ident} vs. {ident}"

    def _assert_call(self, obj, ident, numargs):
        """Assert that an object is a Call with the given identifier and
        argument count.
        """
        assert isinstance(obj, functemplate.Call), f"not a Call: {obj}"
        assert obj.ident == ident, f"wrong identifier: {obj.ident} vs. {ident}"
        assert (
            len(obj.args) == numargs
        ), f"wrong argument count in {obj.ident}: {len(obj.args)} vs. {numargs}"

    def test_plain_text(self):
        assert list(_normparse("hello world")) == ["hello world"]

    def test_escaped_character_only(self):
        assert list(_normparse("$$")) == ["$"]

    def test_escaped_character_in_text(self):
        assert list(_normparse("a $$ b")) == ["a $ b"]

    def test_escaped_character_at_start(self):
        assert list(_normparse("$$ hello")) == ["$ hello"]

    def test_escaped_character_at_end(self):
        assert list(_normparse("hello $$")) == ["hello $"]

    def test_escaped_function_delim(self):
        assert list(_normparse("a $% b")) == ["a % b"]

    def test_escaped_sep(self):
        assert list(_normparse("a $, b")) == ["a , b"]

    def test_escaped_close_brace(self):
        assert list(_normparse("a $} b")) == ["a } b"]

    def test_bare_value_delim_kept_intact(self):
        assert list(_normparse("a $ b")) == ["a $ b"]

    def test_bare_function_delim_kept_intact(self):
        assert list(_normparse("a % b")) == ["a % b"]

    def test_bare_opener_kept_intact(self):
        assert list(_normparse("a { b")) == ["a { b"]

    def test_bare_closer_kept_intact(self):
        assert list(_normparse("a } b")) == ["a } b"]

    def test_bare_sep_kept_intact(self):
        assert list(_normparse("a , b")) == ["a , b"]

    def test_symbol_alone(self):
        parts = list(_normparse("$foo"))
        assert len(parts) == 1
        self._assert_symbol(parts[0], "foo")

    def test_symbol_in_text(self):
        parts = list(_normparse("hello $foo world"))
        assert len(parts) == 3
        assert parts[0] == "hello "
        self._assert_symbol(parts[1], "foo")
        assert parts[2] == " world"

    def test_symbol_with_braces(self):
        parts = list(_normparse("hello${foo}world"))
        assert len(parts) == 3
        assert parts[0] == "hello"
        self._assert_symbol(parts[1], "foo")
        assert parts[2] == "world"

    def test_unclosed_braces_symbol(self):
        assert list(_normparse("a ${ b")) == ["a ${ b"]

    def test_empty_braces_symbol(self):
        assert list(_normparse("a ${} b")) == ["a ${} b"]

    def test_call_without_args_at_end(self):
        assert list(_normparse("foo %bar")) == ["foo %bar"]

    def test_call_without_args(self):
        assert list(_normparse("foo %bar baz")) == ["foo %bar baz"]

    def test_call_with_unclosed_args(self):
        assert list(_normparse("foo %bar{ baz")) == ["foo %bar{ baz"]

    def test_call_with_unclosed_multiple_args(self):
        assert list(_normparse("foo %bar{bar,bar baz")) == [
            "foo %bar{bar,bar baz"
        ]

    def test_call_empty_arg(self):
        parts = list(_normparse("%foo{}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 1)
        assert list(_normexpr(parts[0].args[0])) == []

    def test_call_single_arg(self):
        parts = list(_normparse("%foo{bar}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 1)
        assert list(_normexpr(parts[0].args[0])) == ["bar"]

    def test_call_two_args(self):
        parts = list(_normparse("%foo{bar,baz}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 2)
        assert list(_normexpr(parts[0].args[0])) == ["bar"]
        assert list(_normexpr(parts[0].args[1])) == ["baz"]

    def test_call_with_escaped_sep(self):
        parts = list(_normparse("%foo{bar$,baz}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 1)
        assert list(_normexpr(parts[0].args[0])) == ["bar,baz"]

    def test_call_with_escaped_close(self):
        parts = list(_normparse("%foo{bar$}baz}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 1)
        assert list(_normexpr(parts[0].args[0])) == ["bar}baz"]

    def test_call_with_symbol_argument(self):
        parts = list(_normparse("%foo{$bar,baz}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 2)
        arg_parts = list(_normexpr(parts[0].args[0]))
        assert len(arg_parts) == 1
        self._assert_symbol(arg_parts[0], "bar")
        assert list(_normexpr(parts[0].args[1])) == ["baz"]

    def test_call_with_nested_call_argument(self):
        parts = list(_normparse("%foo{%bar{},baz}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 2)
        arg_parts = list(_normexpr(parts[0].args[0]))
        assert len(arg_parts) == 1
        self._assert_call(arg_parts[0], "bar", 1)
        assert list(_normexpr(parts[0].args[1])) == ["baz"]

    def test_nested_call_with_argument(self):
        parts = list(_normparse("%foo{%bar{baz}}"))
        assert len(parts) == 1
        self._assert_call(parts[0], "foo", 1)
        arg_parts = list(_normexpr(parts[0].args[0]))
        assert len(arg_parts) == 1
        self._assert_call(arg_parts[0], "bar", 1)
        assert list(_normexpr(arg_parts[0].args[0])) == ["baz"]

    def test_sep_before_call_two_args(self):
        parts = list(_normparse("hello, %foo{bar,baz}"))
        assert len(parts) == 2
        assert parts[0] == "hello, "
        self._assert_call(parts[1], "foo", 2)
        assert list(_normexpr(parts[1].args[0])) == ["bar"]
        assert list(_normexpr(parts[1].args[1])) == ["baz"]

    def test_sep_with_symbols(self):
        parts = list(_normparse("hello,$foo,$bar"))
        assert len(parts) == 4
        assert parts[0] == "hello,"
        self._assert_symbol(parts[1], "foo")
        assert parts[2] == ","
        self._assert_symbol(parts[3], "bar")

    def test_newline_at_end(self):
        parts = list(_normparse("foo\n"))
        assert len(parts) == 1
        assert parts[0] == "foo\n"


class EvalTest(unittest.TestCase):
    def _eval(self, template):
        values = {
            "foo": "bar",
            "baz": "BaR",
        }
        functions = {
            "lower": str.lower,
            "len": len,
        }
        return functemplate.Template(template).substitute(values, functions)

    def test_plain_text(self):
        assert self._eval("foo") == "foo"

    def test_subtitute_value(self):
        assert self._eval("$foo") == "bar"

    def test_subtitute_value_in_text(self):
        assert self._eval("hello $foo world") == "hello bar world"

    def test_not_subtitute_undefined_value(self):
        assert self._eval("$bar") == "$bar"

    def test_function_call(self):
        assert self._eval("%lower{FOO}") == "foo"

    def test_function_call_with_text(self):
        assert self._eval("A %lower{FOO} B") == "A foo B"

    def test_nested_function_call(self):
        assert self._eval("%lower{%lower{FOO}}") == "foo"

    def test_symbol_in_argument(self):
        assert self._eval("%lower{$baz}") == "bar"

    def test_function_call_exception(self):
        res = self._eval("%lower{a,b,c,d,e}")
        assert isinstance(res, str)

    def test_function_returning_integer(self):
        assert self._eval("%len{foo}") == "3"

    def test_not_subtitute_undefined_func(self):
        assert self._eval("%bar{}") == "%bar{}"

    def test_not_subtitute_func_with_no_args(self):
        assert self._eval("%lower") == "%lower"

    def test_function_call_with_empty_arg(self):
        assert self._eval("%len{}") == "0"
