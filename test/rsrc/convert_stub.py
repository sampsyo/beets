#!/usr/bin/env python3

"""A tiny tool used to test the `convert` plugin. It copies a file and appends
a specified text tag.
"""

import locale
import sys


# From `beets.util`.
def arg_encoding():
    try:
        return locale.getdefaultlocale()[1] or "utf-8"
    except ValueError:
        return "utf-8"


def convert(in_file, out_file, tag):
    """Copy `in_file` to `out_file` and append the string `tag`."""
    if not isinstance(tag, bytes):
        tag = tag.encode("utf-8")

    with open(out_file, "wb") as out_f:
        with open(in_file, "rb") as in_f:
            out_f.write(in_f.read())
        out_f.write(tag)


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2], sys.argv[3])
