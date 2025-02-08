# This file is part of beets.
# Copyright 2016, Adrian Sampson.
# Copyright 2024, Arav K.
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

"""Simple library to work out if a file is hidden on different platforms."""

import ctypes
import os
import stat
import sys
from pathlib import Path
from typing import Union


def is_hidden(path: Union[bytes, Path]) -> bool:
    """
    Determine whether the given path is treated as a 'hidden file' by the OS.
    """

    if isinstance(path, bytes):
        path = Path(os.fsdecode(path))

    # TODO: Avoid doing a platform check on every invocation of the function.
    # TODO: Stop supporting 'bytes' inputs once 'pathlib' is fully integrated.

    if sys.platform == "win32":
        # On Windows, we check for an FS-provided attribute.

        # FILE_ATTRIBUTE_HIDDEN = 2 (0x2) from GetFileAttributes documentation.
        hidden_mask = 2

        # Retrieve the attributes for the file.
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))

        # Ensure the attribute mask is valid.
        if attrs < 0:
            return False

        # Check for the hidden attribute.
        return attrs & hidden_mask

    # On OS X, we check for an FS-provided attribute.
    if sys.platform == "darwin":
        if hasattr(os.stat_result, "st_flags") and hasattr(stat, "UF_HIDDEN"):
            if path.lstat().st_flags & stat.UF_HIDDEN:
                return True

    # On all non-Windows platforms, we check for a '.'-prefixed file name.
    if path.name.startswith("."):
        return True

    return False
