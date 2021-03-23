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

from __future__ import division, absolute_import, print_function

from beets.util.queue import CountedInvalidatingQueue
from concurrent import futures
from threading import Thread, Lock
import sys
import six

BUBBLE = '__PIPELINE_BUBBLE__'
POISON = '__PIPELINE_POISON__'

DEFAULT_QUEUE_SIZE = 16


class MultiMessage(object):
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


def stage(func):
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

    def coro(*args):
        task = None
        while True:
            task = yield task
            task = func(*(args + (task,)))
    return coro


def mutator_stage(func):
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

    def coro(*args):
        task = None
        while True:
            task = yield task
            fut = func(*(args + (task,)))
            if isinstance(fut, futures.Future):
                # Wrap the future to return the task
                outer_fut = futures.Future()

                # Using the default argument here is a trick to correctly
                # capture `task` in the closure, see
                # https://stackoverflow.com/questions/2295290/what-do-lambda-function-closures-capture
                # If omitting this, the `task = outer_fut` assignment below
                # would override `task`, creating a cycle where
                # `outer_fut.result() -> outer_fut`...
                def check_fut(fut, task=task):
                    # Access (and discard) the result to re-raise errors
                    try:
                        fut.result()
                        outer_fut.set_result(task)
                    except BaseException as e:
                        outer_fut.set_exception(e)

                fut.add_done_callback(check_fut)

                # Yield this wrapped future in the next iteration
                task = outer_fut
            else:
                # After all, this is a mutator stage.
                assert(fut is None)
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


class PipelineAborted(Exception):
    pass


class PipelineThread(Thread):
    """Abstract base class for pipeline-stage threads."""
    def __init__(self, coro, pipeline, in_queue=None, out_queue=None):
        super(PipelineThread, self).__init__()
        self.coro = coro
        self.abort_lock = Lock()
        self.abort_flag = False
        self.pipeline = pipeline
        self.exc_info = None
        self.in_queue = in_queue
        self.out_queue = out_queue
        self._startup()

    def abort(self):
        """Shut down the thread at the next chance possible.
        """
        with self.abort_lock:
            self.abort_flag = True

            # Ensure that we are not blocking on a queue read or write.
            if self.in_queue is not None:
                self.in_queue.invalidate(POISON)
            if self.out_queue is not None:
                self.out_queue.invalidate(POISON)

    def check_abort(self):
        with self.abort_lock:
            if self.abort_flag:
                raise PipelineAborted()

    def check_and_put_future(self, res, fut):
        try:
            msg = fut.result()
            self.check_abort()
            res.put(msg)
        except PipelineAborted:
            # Might be raised from check_abort(): The error occured elsewhere,
            # so the pipeline is shutting down already. So, we need to
            # release resources that might block that.
            res.discard()
        except BaseException:
            # Any errors raised in f.result(). This will be executed as a
            # callback by the ThreadpoolExecutor, which will ignore any
            # exception. Thus, the excpection can't propagate up to the check
            # in self.run(), but we need to abort the pipeline explicitly here.
            res.discard()
            self.exc_info = sys.exc_info()
            self.pipeline.abort()

    def fanout(self, messages):
        """Send messages to the next stage.
        """
        for msg in _allmsgs(messages):
            self.check_abort()
            if isinstance(msg, futures.Future):
                res = self.out_queue.reserve()
                msg.add_done_callback(
                        lambda fut: self.check_and_put_future(res, fut))
            else:
                self.out_queue.put(msg)

    def run(self):
        try:
            while True:
                self.check_abort()
                self._run_once()
        except StopIteration:
            # Pipeline is shutting down normally.
            self._shutdown()
        except PipelineAborted:
            pass
        except BaseException:
            self.exc_info = sys.exc_info()
            self.pipeline.abort()

    def _startup(self):
        pass

    def _run_once(self):
        raise NotImplementedError()

    def _shutdown(self):
        pass


class FirstPipelineThread(PipelineThread):
    """The thread running the first stage in a parallel pipeline setup.
    The coroutine should just be a generator.
    """
    def _startup(self):
        self.out_queue.acquire()

    def _run_once(self):
        # Get the value from the generator, StopIteration is intentionally
        # propagated to the caller.
        msg = next(self.coro)
        self.fanout(msg)

    def _shutdown(self):
        self.out_queue.release()


class MiddlePipelineThread(PipelineThread):
    """A thread running any stage in the pipeline except the first or
    last.
    """
    def _startup(self):
        self.out_queue.acquire()

        # Prime the coroutine.
        next(self.coro)

    def _run_once(self):
        # Get the message from the previous stage.
        msg = self.in_queue.get()
        if msg is POISON:
            raise StopIteration()

        self.check_abort()

        # Invoke the current stage.
        out = self.coro.send(msg)
        self.fanout(out)

    def _shutdown(self):
        self.out_queue.release()


class LastPipelineThread(PipelineThread):
    """A thread running the last stage in a pipeline. The coroutine
    should yield nothing.
    """
    def _startup(self):
        # Prime the coroutine.
        next(self.coro)

    def _run_once(self):
        # Get the message from the previous stage.
        msg = self.in_queue.get()
        if msg is POISON:
            raise StopIteration()

        self.check_abort()

        # Send to consumer.
        self.coro.send(msg)


class Pipeline(object):
    """Represents a staged pattern of work. Each stage in the pipeline
    is a coroutine that receives messages from the previous stage and
    yields messages to be sent to the next stage.
    """
    def __init__(self, stages):
        """Makes a new pipeline from a list of coroutines. There must
        be at least two stages.
        """
        if len(stages) < 2:
            raise ValueError(u'pipeline must have at least two stages')
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

    def abort(self):
        """Abort all threads in the system for an exception.
        """
        for thread in self.threads:
            thread.abort()

    def run_parallel(self, queue_size=DEFAULT_QUEUE_SIZE):
        """Run the pipeline in parallel using one thread per stage. The
        messages between the stages are stored in queues of the given
        size.
        """
        queue_count = len(self.stages) - 1
        queues = [CountedInvalidatingQueue(queue_size, POISON)
                  for i in range(queue_count)]
        self.threads = []

        # Set up first stage.
        for coro in self.stages[0]:
            self.threads.append(FirstPipelineThread(
                coro, self, out_queue=queues[0],
            ))

        # Middle stages.
        for i in range(1, queue_count):
            for coro in self.stages[i]:
                self.threads.append(MiddlePipelineThread(
                    coro, self, in_queue=queues[i - 1], out_queue=queues[i]
                ))

        # Last stage.
        for coro in self.stages[-1]:
            self.threads.append(
                LastPipelineThread(coro, self, in_queue=queues[-1])
            )

        # Start threads.
        for thread in self.threads:
            thread.start()

        # Wait for termination. The final thread lasts the longest.
        try:
            # Using a timeout allows us to receive KeyboardInterrupt
            # exceptions during the join().
            while self.threads[-1].is_alive():
                self.threads[-1].join(1)

        except BaseException:
            # Stop all the threads immediately.
            for thread in self.threads:
                thread.abort()
            raise

        finally:
            # Make completely sure that all the threads have finished
            # before we return. They should already be either finished,
            # in normal operation, or aborted, in case of an exception.
            for thread in self.threads[:-1]:
                thread.join()

        for thread in self.threads:
            exc_info = thread.exc_info
            if exc_info:
                # Make the exception appear as it was raised originally.
                six.reraise(exc_info[0], exc_info[1], exc_info[2])

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

        def await_if_future(msg):
            if isinstance(msg, futures.Future):
                res = msg.result()
            else:
                res = msg
            return res

        # Begin the pipeline.
        for out in coros[0]:
            msgs = _allmsgs(out)
            for coro in coros[1:]:
                next_msgs = []
                for msg in msgs:
                    out = coro.send(await_if_future(msg))
                    next_msgs.extend(_allmsgs(out))
                msgs = next_msgs
            for msg in msgs:
                yield await_if_future(msg)

# Smoke test.
if __name__ == '__main__':
    import time

    # Test a normally-terminating pipeline both in sequence and
    # in parallel.
    def produce():
        for i in range(5):
            print(u'generating %i' % i)
            time.sleep(1)
            yield i

    def work():
        num = yield
        while True:
            print(u'processing %i' % num)
            time.sleep(2)
            num = yield num * 2

    def consume():
        while True:
            num = yield
            time.sleep(1)
            print(u'received %i' % num)

    ts_start = time.time()
    Pipeline([produce(), work(), consume()]).run_sequential()
    ts_seq = time.time()
    Pipeline([produce(), work(), consume()]).run_parallel()
    ts_par = time.time()
    Pipeline([produce(), (work(), work()), consume()]).run_parallel()
    ts_end = time.time()
    print(u'Sequential time:', ts_seq - ts_start)
    print(u'Parallel time:', ts_par - ts_seq)
    print(u'Multiply-parallel time:', ts_end - ts_par)
    print()

    # Test a pipeline that raises an exception.
    def exc_produce():
        for i in range(10):
            print(u'generating %i' % i)
            time.sleep(1)
            yield i

    def exc_work():
        num = yield
        while True:
            print(u'processing %i' % num)
            time.sleep(3)
            if num == 3:
                raise Exception()
            num = yield num * 2

    def exc_consume():
        while True:
            num = yield
            print(u'received %i' % num)

    Pipeline([exc_produce(), exc_work(), exc_consume()]).run_parallel(1)
