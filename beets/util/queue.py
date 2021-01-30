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

# The queue implementation is based on queue.Queue from Python 3.7, which is
# licensed under the PSF (), and
#
# Copyright © 2001-2018 Python Software Foundation; All Rights Reserved
#
# All functionality that is not required has been stripped. Facilities for
# counting threads that feed into a queue and for invalidating the queue have
# been added.

"""Custom queue for communication between pipeline stages."""

from __future__ import division, absolute_import, print_function

from collections import deque
import threading


class CountedInvalidatingQueue():
    """A simple thread-safe queue derived from Python's `queue.Queue`.

    Implements additional methods for

    - tracking when all producers are done putting items into the queue,
    - invalidating the queue, i.e. immediatly unblocking all threads that are
      waiting to `put()` or `get()`.
    """

    def __init__(self, maxsize=0, on_finished=None):
        """Create a queue object with a given maximum size.

        If `maxsize` is <= 0, the queue size is infinite.

        After all threads have released the queue it will be invalidated with
        the value of `on_finished`.
        """
        self._maxsize = maxsize
        self._on_finished = on_finished

        self._queue = deque()
        self._invalidated = False
        self._finished = False
        self._nthreads = 0

        # _mutex must be held whenever the queue is mutating.  All methods
        # that acquire _mutex must release it before returning.  _mutex
        # is shared between the three conditions, so acquiring and
        # releasing the conditions also acquires and releases _mutex.
        self._mutex = threading.Lock()

        # Notify not_empty whenever an item is added to the queue; a
        # thread waiting to get is notified then.
        self.not_empty = threading.Condition(self._mutex)

        # Notify not_full whenever an item is removed from the queue;
        # a thread waiting to put is notified then.
        self.not_full = threading.Condition(self._mutex)

    def acquire(self):
        """Indicate that a thread will start putting into this queue.

        Must not be called after the queue is already finished.
        """
        with self._mutex:
            assert not self._finished
            self._nthreads += 1

    def release(self):
        """Indicate that a thread that was putting into this queue has exited.

        If this is the last thread using the queue, the queue is finished.
        """
        with self._mutex:
            assert self._nthreads > 0
            self._nthreads -= 1
            if self._nthreads == 0:
                # All threads are done adding to this queue. Poison it
                # when it becomes empty.
                self._finished = True
                self.not_empty.notify_all()

    def _invalidate(self, value):
        """Internal method implementing invalidation, see `invalidate()`.

        The caller must hold `self._mutex`.
        """
        self._invalid_value = value
        if not self._invalidated:
            self._invalidated = True
            self.not_full.notifyAll()
            self.not_empty.notifyAll()

    def invalidate(self, value):
        """Invalidate the queue with the given `value`.

        When invalidated, the Queue will accept more items beyond its maxsize
        and only ever return the `value`. Thus, it will never block, and wake
        up all threads that are blocked in `put()` or `get()`.
        While invalidated, the queue will not 'lose' any items such that it is
        possible to `resume()` operation at a later point.

        It is safe to call this multiple times, subsequent calls after the
        first will do nothing expcpet for updating the value.
        """
        with self._mutex:
            self._invalidate(value)

    def resume(self):
        """Resume operation after the queue has been invalidated.

        It is an error to call `resume()` when the queue is not actually
        invalidated.

        This method is not currently tested or used anywhere. It was added in
        preparation for better error handling during import sessions.
        """
        with self._mutex:
            assert self._invalidated
            if not self._finished:
                self._invalidated = False
                self._invalid_value = None
                self.not_empty.notifyAll()
                self.not_full.notifyAll()
            else:
                assert len(self._queue) == 0

    def _is_full(self):
        """Predicate factored out to increase readability of `put()`.

        For internal use only, `self._mutex` must be held.
        """
        return self._maxsize == 0 or len(self._queue) >= self._maxsize

    def put(self, item):
        """Put an item into the queue.

        Blocks if the queue is full, unless the queue is invalidated. In that
        case, store the item anyway even if `seld.maxsize` will be exceeded and
        return immediately.
        """
        with self.not_full:
            while (not self._invalidated and self._is_full()):
                self.not_full.wait()

            self._queue.append(item)
            if not self._invalidated:
                self.not_empty.notify()

    def get(self):
        """Remove and return an item from the queue.

        Blocks if the queue is empty, unless the queue is invalidated. In that
        case, the value specified on invalidation will be returned immediately.
        """
        with self.not_empty:
            while True:
                if self._invalidated:
                    return self._invalid_value

                if len(self._queue):
                    item = self._queue.popleft()
                    self.not_full.notify()
                    return item

                # When this code is reached, the queue is currently empty.
                if self._finished:
                    self._invalidate(self._on_finished)
                    return self._on_finished

                self.not_empty.wait()
