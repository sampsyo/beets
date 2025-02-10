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

"""Simple but robust implementation of generator/coroutine-based
pipelines in Python. The pipelines may be run either sequentially
(single-threaded) or in parallel (one thread per pipeline stage).

This implementation supports pipeline bubbles (indications that the
processing for a certain item should abort). To use them, yield the
BUBBLE constant from any stage coroutine except the last.

In the parallel case, the implementation transparently handles thread
shutdown when the processing is complete and when a stage raises an
exception. KeyboardInterrupts (^C) are also handled.

When running a parallel pipeline, it is also possible to use
multiple coroutines for the same pipeline stage; this lets you speed
up a bottleneck stage by dividing its work among multiple threads.
To do so, pass an iterable of coroutines to the Pipeline constructor
in place of any single coroutine.
"""

from __future__ import annotations

import queue
import sys
from threading import Lock, Thread
from typing import Callable, Generator

from typing_extensions import TypeVar, TypeVarTuple, Unpack

BUBBLE = "__PIPELINE_BUBBLE__"
POISON = "__PIPELINE_POISON__"

DEFAULT_QUEUE_SIZE = 16


def _invalidate_queue(q, val=None, sync=True):
    """Breaks a Queue such that it never blocks, always has size 1,
    and has no maximum size. get()ing from the queue returns `val`,
    which defaults to None. `sync` controls whether a lock is
    required (because it's not reentrant!).
    """

    def _qsize(len=len):
        return 1

    def _put(item):
        pass

    def _get():
        return val

    if sync:
        q.mutex.acquire()

    try:
        # Originally, we set `maxsize` to 0 here, which is supposed to mean
        # an unlimited queue size. However, there is a race condition since
        # Python 3.2 when this attribute is changed while another thread is
        # waiting in put()/get() due to a full/empty queue.
        # Setting it to 2 is still hacky because Python does not give any
        # guarantee what happens if Queue methods/attributes are overwritten
        # when it is already in use. However, because of our dummy _put()
        # and _get() methods, it provides a workaround to let the queue appear
        # to be never empty or full.
        # See issue https://github.com/beetbox/beets/issues/2078
        q.maxsize = 2
        q._qsize = _qsize
        q._put = _put
        q._get = _get
        q.not_empty.notify_all()
        q.not_full.notify_all()

    finally:
        if sync:
            q.mutex.release()


class CountedQueue(queue.Queue):
    """A queue that keeps track of the number of threads that are
    still feeding into it. The queue is poisoned when all threads are
    finished with the queue.
    """

    def __init__(self, maxsize=0):
        queue.Queue.__init__(self, maxsize)
        self.nthreads = 0
        self.poisoned = False

    def acquire(self):
        """Indicate that a thread will start putting into this queue.
        Should not be called after the queue is already poisoned.
        """
        with self.mutex:
            assert not self.poisoned
            assert self.nthreads >= 0
            self.nthreads += 1

    def release(self):
        """Indicate that a thread that was putting into this queue has
        exited. If this is the last thread using the queue, the queue
        is poisoned.
        """
        with self.mutex:
            self.nthreads -= 1
            assert self.nthreads >= 0
            if self.nthreads == 0:
                # All threads are done adding to this queue. Poison it
                # when it becomes empty.
                self.poisoned = True

                # Replacement _get invalidates when no items remain.
                _old_get = self._get

                def _get():
                    out = _old_get()
                    if not self.queue:
                        _invalidate_queue(self, POISON, False)
                    return out

                if self.queue:
                    # Items remain.
                    self._get = _get
                else:
                    # No items. Invalidate immediately.
                    _invalidate_queue(self, POISON, False)


class MultiMessage:
    """A message yielded by a pipeline stage encapsulating multiple
    values to be sent to the next stage.
    """

    def __init__(self, messages):
        self.messages = messages


def multiple(messages):
    """Yield multiple([message, ..]) from a pipeline stage to send
    multiple values to the next pipeline stage.
    """
    return MultiMessage(messages)


A = TypeVarTuple("A")  # Arguments of a function (omitting the task)
T = TypeVar("T")  # Type of the task
# Normally these are concatenated i.e. (*args, task)

# Return type of the function (should normally be task but sadly
# we cant enforce this with the current stage functions without
# a refactor)
R = TypeVar("R")


def stage(
    func: Callable[
        [Unpack[A], T],
        R | None,
    ],
):
    """Decorate a function to become a simple stage.

    >>> @stage
    ... def add(n, i):
    ...     return i + n
    >>> pipe = Pipeline([
    ...     iter([1, 2, 3]),
    ...     add(2),
    ... ])
    >>> list(pipe.pull())
    [3, 4, 5]
    """

    def coro(*args: Unpack[A]) -> Generator[R | T | None, T, None]:
        task: R | T | None = None
        while True:
            task = yield task
            task = func(*(args + (task,)))

    return coro


def mutator_stage(func: Callable[[Unpack[A], T], R]):
    """Decorate a function that manipulates items in a coroutine to
    become a simple stage.

    >>> @mutator_stage
    ... def setkey(key, item):
    ...     item[key] = True
    >>> pipe = Pipeline([
    ...     iter([{'x': False}, {'a': False}]),
    ...     setkey('x'),
    ... ])
    >>> list(pipe.pull())
    [{'x': True}, {'a': False, 'x': True}]
    """

    def coro(*args: Unpack[A]) -> Generator[T | None, T, None]:
        task = None
        while True:
            task = yield task
            func(*(args + (task,)))

    return coro


def _allmsgs(obj):
    """Returns a list of all the messages encapsulated in obj. If obj
    is a MultiMessage, returns its enclosed messages. If obj is BUBBLE,
    returns an empty list. Otherwise, returns a list containing obj.
    """
    if isinstance(obj, MultiMessage):
        return obj.messages
    elif obj == BUBBLE:
        return []
    else:
        return [obj]


class PipelineThread(Thread):
    """Abstract base class for pipeline-stage threads."""

    def __init__(self, all_threads):
        super().__init__()
        self.abort_lock = Lock()
        self.abort_flag = False
        self.all_threads = all_threads
        self.exc_info = None

    def abort(self):
        """Shut down the thread at the next chance possible."""
        with self.abort_lock:
            self.abort_flag = True

            # Ensure that we are not blocking on a queue read or write.
            if hasattr(self, "in_queue"):
                _invalidate_queue(self.in_queue, POISON)
            if hasattr(self, "out_queue"):
                _invalidate_queue(self.out_queue, POISON)

    def abort_all(self, exc_info):
        """Abort all other threads in the system for an exception."""
        self.exc_info = exc_info
        for thread in self.all_threads:
            thread.abort()


class FirstPipelineThread(PipelineThread):
    """The thread running the first stage in a parallel pipeline setup.
    The coroutine should just be a generator.
    """

    def __init__(self, coro, out_queue, all_threads):
        super().__init__(all_threads)
        self.coro = coro
        self.out_queue = out_queue
        self.out_queue.acquire()

    def run(self):
        try:
            while True:
                with self.abort_lock:
                    if self.abort_flag:
                        return

                # Get the value from the generator.
                try:
                    msg = next(self.coro)
                except StopIteration:
                    break

                # Send messages to the next stage.
                for msg in _allmsgs(msg):
                    with self.abort_lock:
                        if self.abort_flag:
                            return
                    self.out_queue.put(msg)

        except BaseException:
            self.abort_all(sys.exc_info())
            return

        # Generator finished; shut down the pipeline.
        self.out_queue.release()


class MiddlePipelineThread(PipelineThread):
    """A thread running any stage in the pipeline except the first or
    last.
    """

    def __init__(self, coro, in_queue, out_queue, all_threads):
        super().__init__(all_threads)
        self.coro = coro
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.out_queue.acquire()

    def run(self):
        try:
            # Prime the coroutine.
            next(self.coro)

            while True:
                with self.abort_lock:
                    if self.abort_flag:
                        return

                # Get the message from the previous stage.
                msg = self.in_queue.get()
                if msg is POISON:
                    break

                with self.abort_lock:
                    if self.abort_flag:
                        return

                # Invoke the current stage.
                out = self.coro.send(msg)

                # Send messages to next stage.
                for msg in _allmsgs(out):
                    with self.abort_lock:
                        if self.abort_flag:
                            return
                    self.out_queue.put(msg)

        except BaseException:
            self.abort_all(sys.exc_info())
            return

        # Pipeline is shutting down normally.
        self.out_queue.release()


class LastPipelineThread(PipelineThread):
    """A thread running the last stage in a pipeline. The coroutine
    should yield nothing.
    """

    def __init__(self, coro, in_queue, all_threads):
        super().__init__(all_threads)
        self.coro = coro
        self.in_queue = in_queue

    def run(self):
        # Prime the coroutine.
        next(self.coro)

        try:
            while True:
                with self.abort_lock:
                    if self.abort_flag:
                        return

                # Get the message from the previous stage.
                msg = self.in_queue.get()
                if msg is POISON:
                    break

                with self.abort_lock:
                    if self.abort_flag:
                        return

                # Send to consumer.
                self.coro.send(msg)

        except BaseException:
            self.abort_all(sys.exc_info())
            return


class Pipeline:
    """Represents a staged pattern of work. Each stage in the pipeline
    is a coroutine that receives messages from the previous stage and
    yields messages to be sent to the next stage.
    """

    def __init__(self, stages):
        """Makes a new pipeline from a list of coroutines. There must
        be at least two stages.
        """
        if len(stages) < 2:
            raise ValueError("pipeline must have at least two stages")
        self.stages = []
        for stage in stages:
            if isinstance(stage, (list, tuple)):
                self.stages.append(stage)
            else:
                # Default to one thread per stage.
                self.stages.append((stage,))

    def run_sequential(self):
        """Run the pipeline sequentially in the current thread. The
        stages are run one after the other. Only the first coroutine
        in each stage is used.
        """
        list(self.pull())

    def run_parallel(self, queue_size=DEFAULT_QUEUE_SIZE):
        """Run the pipeline in parallel using one thread per stage. The
        messages between the stages are stored in queues of the given
        size.
        """
        queue_count = len(self.stages) - 1
        queues = [CountedQueue(queue_size) for i in range(queue_count)]
        threads = []

        # Set up first stage.
        for coro in self.stages[0]:
            threads.append(FirstPipelineThread(coro, queues[0], threads))

        # Middle stages.
        for i in range(1, queue_count):
            for coro in self.stages[i]:
                threads.append(
                    MiddlePipelineThread(
                        coro, queues[i - 1], queues[i], threads
                    )
                )

        # Last stage.
        for coro in self.stages[-1]:
            threads.append(LastPipelineThread(coro, queues[-1], threads))

        # Start threads.
        for thread in threads:
            thread.start()

        # Wait for termination. The final thread lasts the longest.
        try:
            # Using a timeout allows us to receive KeyboardInterrupt
            # exceptions during the join().
            while threads[-1].is_alive():
                threads[-1].join(1)

        except BaseException:
            # Stop all the threads immediately.
            for thread in threads:
                thread.abort()
            raise

        finally:
            # Make completely sure that all the threads have finished
            # before we return. They should already be either finished,
            # in normal operation, or aborted, in case of an exception.
            for thread in threads[:-1]:
                thread.join()

        for thread in threads:
            exc_info = thread.exc_info
            if exc_info:
                # Make the exception appear as it was raised originally.
                raise exc_info[1].with_traceback(exc_info[2])

    def pull(self):
        """Yield elements from the end of the pipeline. Runs the stages
        sequentially until the last yields some messages. Each of the messages
        is then yielded by ``pulled.next()``. If the pipeline has a consumer,
        that is the last stage does not yield any messages, then pull will not
        yield any messages. Only the first coroutine in each stage is used
        """
        coros = [stage[0] for stage in self.stages]

        # "Prime" the coroutines.
        for coro in coros[1:]:
            next(coro)

        # Begin the pipeline.
        for out in coros[0]:
            msgs = _allmsgs(out)
            for coro in coros[1:]:
                next_msgs = []
                for msg in msgs:
                    out = coro.send(msg)
                    next_msgs.extend(_allmsgs(out))
                msgs = next_msgs
            for msg in msgs:
                yield msg


# Smoke test.
if __name__ == "__main__":
    import time

    # Test a normally-terminating pipeline both in sequence and
    # in parallel.
    def produce():
        for i in range(5):
            print("generating %i" % i)
            time.sleep(1)
            yield i

    def work():
        num = yield
        while True:
            print("processing %i" % num)
            time.sleep(2)
            num = yield num * 2

    def consume():
        while True:
            num = yield
            time.sleep(1)
            print("received %i" % num)

    ts_start = time.time()
    Pipeline([produce(), work(), consume()]).run_sequential()
    ts_seq = time.time()
    Pipeline([produce(), work(), consume()]).run_parallel()
    ts_par = time.time()
    Pipeline([produce(), (work(), work()), consume()]).run_parallel()
    ts_end = time.time()
    print("Sequential time:", ts_seq - ts_start)
    print("Parallel time:", ts_par - ts_seq)
    print("Multiply-parallel time:", ts_end - ts_par)
    print()

    # Test a pipeline that raises an exception.
    def exc_produce():
        for i in range(10):
            print("generating %i" % i)
            time.sleep(1)
            yield i

    def exc_work():
        num = yield
        while True:
            print("processing %i" % num)
            time.sleep(3)
            if num == 3:
                raise Exception()
            num = yield num * 2

    def exc_consume():
        while True:
            num = yield
            print("received %i" % num)

    Pipeline([exc_produce(), exc_work(), exc_consume()]).run_parallel(1)
