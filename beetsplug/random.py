# This file is part of beets.
# Copyright 2016, Philippe Mongeau.
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

"""Get a random song or album from the library."""

from beets.plugins import BeetsPlugin
from beets.random import random_objs
from beets.ui import Subcommand, decargs, print_


def random_func(lib, opts, args):
    """Select some random items or albums and print the results."""
    # Fetch all the objects matching the query into a list.
    query = decargs(args)
    if opts.album:
        objs = list(lib.albums(query))
    else:
        objs = list(lib.items(query))

    # Print a random subset.
    objs = random_objs(
        objs, opts.album, opts.number, opts.time, opts.equal_chance
    )
    for obj in objs:
        print_(format(obj))


random_cmd = Subcommand("random", help="choose a random track or album")
random_cmd.parser.add_option(
    "-n",
    "--number",
    action="store",
    type="int",
    help="number of objects to choose",
    default=1,
)
random_cmd.parser.add_option(
    "-e",
    "--equal-chance",
    action="store_true",
    help="each artist has the same chance",
)
random_cmd.parser.add_option(
    "-t",
    "--time",
    action="store",
    type="float",
    help="total length in minutes of objects to choose",
)
random_cmd.parser.add_all_common_options()
random_cmd.func = random_func


class Random(BeetsPlugin):
    def commands(self):
        return [random_cmd]
