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

"""A simple utility for constructing filesystem-like trees from beets
libraries.
"""

from typing import Any, NamedTuple

from beets import util


class Node(NamedTuple):
    files: dict[str, Any]
    dirs: dict[str, Any]


def _insert(node, path, itemid):
    """Insert an item into a virtual filesystem node."""
    if len(path) == 1:
        # Last component. Insert file.
        node.files[path[0]] = itemid
    else:
        # In a directory.
        dirname = path[0]
        rest = path[1:]
        if dirname not in node.dirs:
            node.dirs[dirname] = Node({}, {})
        _insert(node.dirs[dirname], rest, itemid)


def libtree(lib):
    """Generates a filesystem-like directory tree for the files
    contained in `lib`. Filesystem nodes are (files, dirs) named
    tuples in which both components are dictionaries. The first
    maps filenames to Item ids. The second maps directory names to
    child node tuples.
    """
    root = Node({}, {})
    for item in lib.items():
        dest = item.destination(relative_to_libdir=True)
        parts = util.components(util.as_string(dest))
        _insert(root, parts, item.id)
    return root
