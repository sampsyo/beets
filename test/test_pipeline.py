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

"""Test the "pipeline.py" restricted parallel programming library."""

import unittest

import pytest

from beets.util import pipeline


# Some simple pipeline stages for testing.
def _produce(num=5):
    yield from range(num)


def _work():
    i = None
    while True:
        i = yield i
        i *= 2


def _consume(result):
    while True:
        i = yield
        result.append(i)


# A worker that raises an exception.
class PipelineError(Exception):
    pass


def _exc_work(num=3):
    i = None
    while True:
        i = yield i
        if i == num:
            raise PipelineError()
        i *= 2


# A worker that yields a bubble.
def _bub_work(num=3):
    i = None
    while True:
        i = yield i
        if i == num:
            i = pipeline.BUBBLE
        else:
            i *= 2


# Yet another worker that yields multiple messages.
def _multi_work():
    i = None
    while True:
        i = yield i
        i = pipeline.multiple([i, -i])


class SimplePipelineTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), _work(), _consume(self.result))
        )

    def test_run_sequential(self):
        self.pl.run_sequential()
        assert self.result == [0, 2, 4, 6, 8]

    def test_run_parallel(self):
        self.pl.run_parallel()
        assert self.result == [0, 2, 4, 6, 8]

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _work()))
        assert list(pl.pull()) == [0, 2, 4, 6, 8]

    def test_pull_chain(self):
        pl = pipeline.Pipeline((_produce(), _work()))
        pl2 = pipeline.Pipeline((pl.pull(), _work()))
        assert list(pl2.pull()) == [0, 4, 8, 12, 16]


class ParallelStageTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), (_work(), _work()), _consume(self.result))
        )

    def test_run_sequential(self):
        self.pl.run_sequential()
        assert self.result == [0, 2, 4, 6, 8]

    def test_run_parallel(self):
        self.pl.run_parallel()
        # Order possibly not preserved; use set equality.
        assert set(self.result) == {0, 2, 4, 6, 8}

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), (_work(), _work())))
        assert list(pl.pull()) == [0, 2, 4, 6, 8]


class ExceptionTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), _exc_work(), _consume(self.result))
        )

    def test_run_sequential(self):
        with pytest.raises(PipelineError):
            self.pl.run_sequential()

    def test_run_parallel(self):
        with pytest.raises(PipelineError):
            self.pl.run_parallel()

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _exc_work()))
        pull = pl.pull()
        for i in range(3):
            next(pull)
        with pytest.raises(PipelineError):
            next(pull)


class ParallelExceptionTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), (_exc_work(), _exc_work()), _consume(self.result))
        )

    def test_run_parallel(self):
        with pytest.raises(PipelineError):
            self.pl.run_parallel()


class ConstrainedThreadedPipelineTest(unittest.TestCase):
    def setUp(self):
        self.result = []

    def test_constrained(self):
        # Do a "significant" amount of work...
        self.pl = pipeline.Pipeline(
            (_produce(1000), _work(), _consume(self.result))
        )
        # ... with only a single queue slot.
        self.pl.run_parallel(1)
        assert self.result == [i * 2 for i in range(1000)]

    def test_constrained_exception(self):
        # Raise an exception in a constrained pipeline.
        self.pl = pipeline.Pipeline(
            (_produce(1000), _exc_work(), _consume(self.result))
        )
        with pytest.raises(PipelineError):
            self.pl.run_parallel(1)

    def test_constrained_parallel(self):
        self.pl = pipeline.Pipeline(
            (_produce(1000), (_work(), _work()), _consume(self.result))
        )
        self.pl.run_parallel(1)
        assert set(self.result) == {i * 2 for i in range(1000)}


class BubbleTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), _bub_work(), _consume(self.result))
        )

    def test_run_sequential(self):
        self.pl.run_sequential()
        assert self.result == [0, 2, 4, 8]

    def test_run_parallel(self):
        self.pl.run_parallel()
        assert self.result == [0, 2, 4, 8]

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _bub_work()))
        assert list(pl.pull()) == [0, 2, 4, 8]


class MultiMessageTest(unittest.TestCase):
    def setUp(self):
        self.result = []
        self.pl = pipeline.Pipeline(
            (_produce(), _multi_work(), _consume(self.result))
        )

    def test_run_sequential(self):
        self.pl.run_sequential()
        assert self.result == [0, 0, 1, -1, 2, -2, 3, -3, 4, -4]

    def test_run_parallel(self):
        self.pl.run_parallel()
        assert self.result == [0, 0, 1, -1, 2, -2, 3, -3, 4, -4]

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _multi_work()))
        assert list(pl.pull()) == [0, 0, 1, -1, 2, -2, 3, -3, 4, -4]


class StageDecoratorTest(unittest.TestCase):
    def test_stage_decorator(self):
        @pipeline.stage
        def add(n, i):
            return i + n

        pl = pipeline.Pipeline([iter([1, 2, 3]), add(2)])
        assert list(pl.pull()) == [3, 4, 5]

    def test_mutator_stage_decorator(self):
        @pipeline.mutator_stage
        def setkey(key, item):
            item[key] = True

        pl = pipeline.Pipeline(
            [iter([{"x": False}, {"a": False}]), setkey("x")]
        )
        assert list(pl.pull()) == [{"x": True}, {"a": False, "x": True}]
