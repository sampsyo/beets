# This file is part of beets.
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

"""Adds head/tail functionality to list/ls.

1. Implemented as `lslimit` command with `--head` and `--tail` options. This is
   the idiomatic way to use this plugin.
2. Implemented as query prefix `<` for head functionality only. This is the
   composable way to use the plugin (plays nicely with anything that uses the
   query language).
"""

from collections import deque
from itertools import islice

from beets.dbcore import FieldQuery
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, decargs, print_


def lslimit(lib, opts, args):
    """Query command with head/tail."""

    if (opts.head is not None) and (opts.tail is not None):
        raise ValueError("Only use one of --head and --tail")
    if (opts.head or opts.tail or 0) < 0:
        raise ValueError("Limit value must be non-negative")

    query = decargs(args)
    if opts.album:
        objs = lib.albums(query)
    else:
        objs = lib.items(query)

    if opts.head is not None:
        objs = islice(objs, opts.head)
    elif opts.tail is not None:
        objs = deque(objs, opts.tail)

    for obj in objs:
        print_(format(obj))


lslimit_cmd = Subcommand("lslimit", help="query with optional head or tail")

lslimit_cmd.parser.add_option(
    "--head", action="store", type="int", default=None
)

lslimit_cmd.parser.add_option(
    "--tail", action="store", type="int", default=None
)

lslimit_cmd.parser.add_all_common_options()
lslimit_cmd.func = lslimit


class LimitPlugin(BeetsPlugin):
    """Query limit functionality via command and query prefix."""

    def commands(self):
        """Expose `lslimit` subcommand."""
        return [lslimit_cmd]

    def queries(self):
        class HeadQuery(FieldQuery):
            """This inner class pattern allows the query to track state."""

            n = 0
            N = None

            def __init__(self, *args, **kwargs) -> None:
                """Force the query to be slow so that 'value_match' is called."""
                super().__init__(*args, **kwargs)
                self.fast = False

            @classmethod
            def value_match(cls, pattern, value):
                if cls.N is None:
                    cls.N = int(pattern)
                    if cls.N < 0:
                        raise ValueError("Limit value must be non-negative")
                cls.n += 1
                return cls.n <= cls.N

        return {"<": HeadQuery}
