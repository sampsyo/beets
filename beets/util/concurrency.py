# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2021, @wisp3rwind
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

"""Provides a global shared thread pool.

The common pool should be used both by beets' core and plugins. Every piece of
work that is CPU-intensive (e.g. calling a subprocess which performs the actual
work) should block a thread on the pool in order to ensure that different
tasks don't fight over resources too much.
"""

from __future__ import division, absolute_import, print_function

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import threading
from beets import logging
from beets.ui import (register_exit_handler, unregister_exit_handler)
from beets.util import cpu_count

__all__ = ["pool", "combine_futures"]

# Global logger.
log = logging.getLogger('beets')

pool = None


class _Pool():
    def __init__(self):
        self._pool = None

    def _open(self):
        """Open the global thread pool instance lazily."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=cpu_count() + 2,
                # thread_name_prefix="worker"  # not available in Python < 3.6
            )
            self.exit_handler = register_exit_handler(
                    lambda abort: self.close(abort=abort))

    def close(self, wait=False, abort=False):
        """Shutdown the thread pool.

        If `abort` is `True`, all tasks that have not been started will be
        cancelled. Tasks that are already running will not be interrupted.
        """
        if self._pool is not None:
            self._pool.shutdown(wait=wait, cancel_futures=abort)
            unregister_exit_handler(self.exit_handler)
            self.exit_handler = None
            self._pool = None

    def submit(self, transform, item):
        self._open()

        return self._pool.submit(transform, item)

    def map_iter_nowait(self, transform, items):
        """Map `transform` over `items`, yielding `Future`s.

        Apply the function `transform` to all the elements in the
        iterable `items`, like `map(transform, items)`, but in parallel.

        The parallelism uses threads (not processes), so this is only useful
        for IO-bound `transform`s.

        This yields the submitted `Future`s directly.
        """
        self._open()

        for i in items:
            yield self.submit(transform, i)

    def map_iter(self, transform, items, cancel_on_error=True):
        """Map `transform` over `items`, yielding the results.

        Apply the function `transform` to all the elements in the
        iterable `items`, like `map(transform, items)`, but in parallel.

        The parallelism uses threads (not processes), so this is only useful
        for IO-bound `transform`s.

        This yields the result of each transform as it completes.
        """
        self._open()

        # FIXME: When dropping Python 2, convert to `yield from`
        for fut in self._pool.map(transform, items):
            yield fut

    def map(self, transform, items, wait=True):
        """Map `transform` over `items`, discarding the results.

        Wrapper around `map_iter` which exhausts the iterator such that
        exceptions from threads are propagated, but discards the results.
        """
        for result in self.map_iter(transform, items, wait):
            pass


pool = _Pool()


class _CombineFutures(Future):
    """A future that aggregates a set of inner futures.

    Completes when all contained futures have completed. The result is
    determined by a callback function.

    This is useful when submitting multiple work chunks to a thread pool, which
    need to be joined and aggregated for further processing.
    """
    # All attributes are prefixed with _beets in order to prevent clashes with
    # any attributes of the base class.

    def __init__(self, func, all_futures):
        """Initialize.

        `func` is a callback that will be invoked with `all_futures` as its
        argument as soon as all items in `all_futures` have completed. Note
        that this means that error handling is fully up to `func`. If the
        latter (re-)raises an excpetion, this future will store this exception,
        otherwise, its result will be set to the return value of `func`.
        """
        super(_CombineFutures, self).__init__()

        all_futures = list(all_futures)
        self._beets_func = func
        self._beets_pending = all_futures[:]

        self._beets_done = []
        self._beets_lock = threading.Lock()

        # This might invoke the callback immediately, so we must not hold
        # the lock here. since `self._beets_pending` is a copy of
        # `all_futures`, the latter nevertheless won't change withing the loop.
        for f in all_futures:
            f.add_done_callback(self._beets_done_callback)

    def cancel(self):
        """Attempt to cancel all inner futures.

        Only if cancellation for all contained futures is successful will this
        future also be treated as cancelled. Otherwise, the callback will
        still be invoked with _all_ futures as its argument.
        """
        cancelled = True

        # Again, `cancel()` might invoke the callback immediately, so we need
        # to be careful here. Thus first make a copy
        with self._beets_lock:
            pending = self._beets_pending[:]

        # And release the lock. Now, we might `cancel()` futures that complete
        # in parallel to us, but that's not a problem, since `f.cancel()`
        # will simply do nothing in that case.
        for f in pending:
            cancelled = cancelled and f.cancel()

        # We do not set our own state the cancelled here, that is up to the
        # callback below.

        return cancelled

    def _beets_done_callback(self, fut):
        """Keep track of completed futures and aggregate results when done."""
        # Here, we do need the lock: The two list operation themselves are
        # safe, since this function can only be called once for each future.
        # However, there would be a possibility that two or more threads
        # observe that `self._beets_pending` is empty, which must be avoided.
        # In other words, this function must be able to determine reliably
        # whether it's operating on the last future.
        with self._beets_lock:
            self._beets_pending.remove(fut)
            self._beets_done.append(fut)

            # Check whether this was the last pending future, i.e. we're done.
            if not self._beets_pending:
                if all(fut.cancelled() for fut in self._beets_done):
                    # See above: Only consider cancellation successful if all
                    # inner futures could be cancelled successfully.
                    super(_CombineFutures, self).cancel()
                    self.set_running_or_notify_cancel()
                else:
                    # Otherwise, it's up to `self._beets_func` to handle the
                    # status (completed/cancelled/raised) of the individual
                    # futures. It may (re-)raise CancelledError to mark this
                    # future as cancelled, too.
                    try:
                        # Simply pass the futures to the callback, it is up to
                        # `func` to handle their status
                        result = self._beets_func(self._beets_done)
                    except CancelledError:
                        super(_CombineFutures, self).cancel()
                        self.set_running_or_notify_cancel()
                    except Exception as e:
                        self.set_exception(e)
                    else:
                        self.set_result(result)

                # Be sure to drop all references to the futures so we don't
                # keep them alive.
                del self._beets_done


def combine_futures(func, all_futures):
    """A future that aggregates a set of inner futures."""
    return _CombineFutures(func, all_futures)
