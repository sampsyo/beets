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

"""Provides the basic, interface-agnostic workflow for importing and
autotagging music files.
"""

from .session import ImportAbortError, ImportSession
from .tasks import (
    Action,
    ArchiveImportTask,
    ImportTask,
    SentinelImportTask,
    SingletonImportTask,
)

# For backwards compatibility also adding action
action = Action

# Note: Stages are not exposed to the public API

__all__ = [
    "ImportSession",
    "ImportAbortError",
    "Action",
    "action",
    "ImportTask",
    "ArchiveImportTask",
    "SentinelImportTask",
    "SingletonImportTask",
]
