# -*- coding: utf-8 -*-
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

"""Test the "pipeline.py" restricted parallel programming library.
"""
from __future__ import division, absolute_import, print_function

from concurrent.futures import ThreadPoolExecutor
import pytest
import six
import time
import unittest

from beets.util import pipeline


# Large value to prevent failures on CI, set to something smaller for more
# convenient local debugging.
TIMEOUT = 60


# Some simple pipeline stages for testing.
def _produce(num=5):
    for i in range(num):
        yield i


def _work():
    i = None
    while True:
        i = yield i
        i *= 2


def _consume(l):
    while True:
        i = yield
        l.append(i)


# A worker that raises an exception.
class ExceptionFixture(Exception):
    pass


def _exc_work(num=3):
    i = None
    while True:
        i = yield i
        if i == num:
            raise ExceptionFixture()
        i *= 2


# This cannot be a nested function in _work_futures because we need to
# establish a new scope to properly capture i
# https://stackoverflow.com/questions/2295290/what-do-lambda-function-closures-capture
def _do_work(i, pool, exc_at, spike_at):
    def func():
        if i == spike_at:
            time.sleep(.2)
        else:
            time.sleep(.001)
        if i == exc_at:
            raise ExceptionFixture()
        return i * 2

    return pool.submit(func)


def _work_futures(pool, exc_at=-1, spike_at=-1):
    fut = None
    while True:
        i = yield fut
        fut = _do_work(i, pool, exc_at, spike_at)


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


@pytest.mark.timeout(TIMEOUT)
class SimplePipelineTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((_produce(), _work(), _consume(self.l)))

    def test_run_sequential(self):
        self.pl.run_sequential()
        self.assertEqual(self.l, [0, 2, 4, 6, 8])

    def test_run_parallel(self):
        self.pl.run_parallel()
        self.assertEqual(self.l, [0, 2, 4, 6, 8])

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _work()))
        self.assertEqual(list(pl.pull()), [0, 2, 4, 6, 8])

    def test_pull_chain(self):
        pl = pipeline.Pipeline((_produce(), _work()))
        pl2 = pipeline.Pipeline((pl.pull(), _work()))
        self.assertEqual(list(pl2.pull()), [0, 4, 8, 12, 16])


@pytest.mark.timeout(TIMEOUT)
class ParallelStageTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((
            _produce(), (_work(), _work()), _consume(self.l)
        ))

    def test_run_sequential(self):
        self.pl.run_sequential()
        self.assertEqual(self.l, [0, 2, 4, 6, 8])

    def test_run_parallel(self):
        self.pl.run_parallel()
        # Order possibly not preserved; use set equality.
        self.assertEqual(set(self.l), set([0, 2, 4, 6, 8]))

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), (_work(), _work())))
        self.assertEqual(list(pl.pull()), [0, 2, 4, 6, 8])


@pytest.mark.timeout(TIMEOUT)
class ExceptionTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((_produce(), _exc_work(),
                                     _consume(self.l)))

    def test_run_sequential(self):
        self.assertRaises(ExceptionFixture, self.pl.run_sequential)

    def test_run_parallel(self):
        self.assertRaises(ExceptionFixture, self.pl.run_parallel)

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _exc_work()))
        pull = pl.pull()
        for i in range(3):
            next(pull)
        if six.PY2:
            self.assertRaises(ExceptionFixture, pull.next)
        else:
            self.assertRaises(ExceptionFixture, pull.__next__)


@pytest.mark.timeout(TIMEOUT)
class ParallelExceptionTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((
            _produce(), (_exc_work(), _exc_work()), _consume(self.l)
        ))

    def test_run_parallel(self):
        self.assertRaises(ExceptionFixture, self.pl.run_parallel)


@pytest.mark.timeout(TIMEOUT)
class ConstrainedThreadedPipelineTest(unittest.TestCase):
    def test_constrained(self):
        l = []
        # Do a "significant" amount of work...
        pl = pipeline.Pipeline((_produce(1000), _work(), _consume(l)))
        # ... with only a single queue slot.
        pl.run_parallel(1)
        self.assertEqual(l, [i * 2 for i in range(1000)])

    def test_constrained_exception(self):
        # Raise an exception in a constrained pipeline.
        l = []
        pl = pipeline.Pipeline((_produce(1000), _exc_work(), _consume(l)))
        self.assertRaises(ExceptionFixture, pl.run_parallel, 1)

    def test_constrained_parallel(self):
        l = []
        pl = pipeline.Pipeline((
            _produce(1000), (_work(), _work()), _consume(l)
        ))
        pl.run_parallel(1)
        self.assertEqual(set(l), set(i * 2 for i in range(1000)))


@pytest.mark.timeout(TIMEOUT)
class BubbleTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((_produce(), _bub_work(),
                                     _consume(self.l)))

    def test_run_sequential(self):
        self.pl.run_sequential()
        self.assertEqual(self.l, [0, 2, 4, 8])

    def test_run_parallel(self):
        self.pl.run_parallel()
        self.assertEqual(self.l, [0, 2, 4, 8])

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _bub_work()))
        self.assertEqual(list(pl.pull()), [0, 2, 4, 8])


@pytest.mark.timeout(TIMEOUT)
class MultiMessageTest(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.pl = pipeline.Pipeline((
            _produce(), _multi_work(), _consume(self.l)
        ))

    def test_run_sequential(self):
        self.pl.run_sequential()
        self.assertEqual(self.l, [0, 0, 1, -1, 2, -2, 3, -3, 4, -4])

    def test_run_parallel(self):
        self.pl.run_parallel()
        self.assertEqual(self.l, [0, 0, 1, -1, 2, -2, 3, -3, 4, -4])

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _multi_work()))
        self.assertEqual(list(pl.pull()), [0, 0, 1, -1, 2, -2, 3, -3, 4, -4])


@pytest.mark.timeout(TIMEOUT)
class StageDecoratorTest(unittest.TestCase):

    def test_stage_decorator(self):
        @pipeline.stage
        def add(n, i):
            return i + n

        pl = pipeline.Pipeline([
            iter([1, 2, 3]),
            add(2)
        ])
        self.assertEqual(list(pl.pull()), [3, 4, 5])

    def test_mutator_stage_decorator(self):
        @pipeline.mutator_stage
        def setkey(key, item):
            item[key] = True

        pl = pipeline.Pipeline([
            iter([{'x': False}, {'a': False}]),
            setkey('x'),
        ])
        self.assertEqual(list(pl.pull()),
                         [{'x': True}, {'a': False, 'x': True}])


@pytest.mark.timeout(TIMEOUT)
class SimpleFuturesTest(unittest.TestCase):
    def setUp(self):
        self.pool = ThreadPoolExecutor()
        self.l = []
        self.pl = pipeline.Pipeline((
            _produce(),
            _work_futures(self.pool),
            _consume(self.l),
        ))

    def tearDown(self):
        self.pool.shutdown()

    def test_run_sequential(self):
        self.pl.run_sequential()
        self.assertEqual(set(self.l), set([0, 2, 4, 6, 8]))

    def test_run_parallel(self):
        self.pl.run_parallel()
        self.assertEqual(set(self.l), set([0, 2, 4, 6, 8]))

    def test_spike(self):
        pl = pipeline.Pipeline((
            _produce(),
            _work_futures(self.pool, spike_at=4),
            _consume(self.l),
        ))
        pl.run_parallel()
        self.assertEqual(set(self.l), set([0, 2, 4, 6, 8]))

    def test_spike_and_exc(self):
        # Check that the pipeline doesn't lock up when an exception occurs and
        # there are pending futures.
        pl = pipeline.Pipeline((
            _produce(),
            _work_futures(self.pool, spike_at=3, exc_at=3),
            _consume(self.l),
        ))
        self.assertRaises(ExceptionFixture, pl.run_parallel)

    def test_spike_then_exc(self):
        # Check that the pipeline doesn't lock up when an exception occurs and
        # there are pending futures.
        pl = pipeline.Pipeline((
            _produce(),
            _work_futures(self.pool, spike_at=2, exc_at=3),
            _consume(self.l),
        ))
        self.assertRaises(ExceptionFixture, pl.run_parallel)

    def test_pull(self):
        pl = pipeline.Pipeline((_produce(), _work_futures(self.pool)))
        self.assertEqual(set(pl.pull()), set([0, 2, 4, 6, 8]))

    def test_pull_chain(self):
        pl = pipeline.Pipeline((_produce(), _work_futures(self.pool)))
        pl2 = pipeline.Pipeline((pl.pull(), _work_futures(self.pool)))
        self.assertEqual(set(pl2.pull()), set([0, 4, 8, 12, 16]))


@pytest.mark.timeout(TIMEOUT)
class ConstrainedThreadedPipelineFuturesTest(unittest.TestCase):
    def setUp(self):
        self.pool = ThreadPoolExecutor()

    def tearDown(self):
        self.pool.shutdown()

    def test_constrained(self):
        l = []
        # Do a "significant" amount of work...
        pl = pipeline.Pipeline((
            _produce(1000),
            _work_futures(self.pool),
            _consume(l),
        ))
        # ... with only a single queue slot.
        pl.run_parallel(1)
        self.assertEqual(set(l), set(i * 2 for i in range(1000)))

    def test_constrained_exception(self):
        # Raise an exception in a constrained pipeline.
        l = []
        pl = pipeline.Pipeline((
            _produce(1000),
            _work_futures(self.pool, exc_at=300),
            _consume(l),
        ))
        self.assertRaises(ExceptionFixture, pl.run_parallel, 1)

    def test_constrained_spike(self):
        # One task takes a lot longer than others.
        l = []
        pl = pipeline.Pipeline((
            _produce(1000),
            _work_futures(self.pool, spike_at=999),
            _consume(l),
        ))
        pl.run_parallel(1)
        self.assertEqual(set(l), set(i * 2 for i in range(1000)))

    def test_constrained_parallel(self):
        l = []
        pl = pipeline.Pipeline((
            _produce(1000),
            (_work_futures(self.pool), _work_futures(self.pool)),
            _consume(l),
        ))
        pl.run_parallel(1)
        self.assertEqual(set(l), set(i * 2 for i in range(1000)))


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
