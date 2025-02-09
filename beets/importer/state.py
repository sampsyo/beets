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

# Here for now to allow for a easy replace later on
# once we can move to a PathLike
from __future__ import annotations

import logging
import os
import pickle
from bisect import bisect_left, insort
from dataclasses import dataclass
from typing import TYPE_CHECKING

from beets import config

if TYPE_CHECKING:
    from .session import PathBytes


# Global logger.
log = logging.getLogger("beets")


@dataclass
class ImportState:
    """Representing the progress of an import task.

    Opens the state file on creation of the class. If you want
    to ensure the state is written to disk, you should use the
    context manager protocol.

    Tagprogress allows long tagging tasks to be resumed when they pause.

    Taghistory is a utility for manipulating the "incremental" import log.
    This keeps track of all directories that were ever imported, which
    allows the importer to only import new stuff.

    Usage
    -----
    ```
    # Readonly
    progress = ImportState().tagprogress

    # Read and write
    with ImportState() as state:
        state["key"] = "value"
    ```
    """

    tagprogress: dict[PathBytes, list[PathBytes]]
    taghistory: set[tuple[PathBytes, ...]]
    path: PathBytes

    def __init__(self, readonly=False, path: PathBytes | None = None):
        self.path = path or os.fsencode(config["statefile"].as_filename())
        self.tagprogress = {}
        self.taghistory = set()
        self._open()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._save()

    def _open(
        self,
    ):
        try:
            with open(self.path, "rb") as f:
                state = pickle.load(f)
                # Read the states
                self.tagprogress = state.get("tagprogress", {})
                self.taghistory = state.get("taghistory", set())
        except Exception as exc:
            # The `pickle` module can emit all sorts of exceptions during
            # unpickling, including ImportError. We use a catch-all
            # exception to avoid enumerating them all (the docs don't even have a
            # full list!).
            log.debug("state file could not be read: {0}", exc)

    def _save(self):
        try:
            with open(self.path, "wb") as f:
                pickle.dump(
                    {
                        "tagprogress": self.tagprogress,
                        "taghistory": self.taghistory,
                    },
                    f,
                )
        except OSError as exc:
            log.error("state file could not be written: {0}", exc)

    # -------------------------------- Tagprogress ------------------------------- #

    def progress_add(self, toppath: PathBytes, *paths: PathBytes):
        """Record that the files under all of the `paths` have been imported
        under `toppath`.
        """
        with self as state:
            imported = state.tagprogress.setdefault(toppath, [])
            for path in paths:
                if imported and imported[-1] <= path:
                    imported.append(path)
                else:
                    insort(imported, path)

    def progress_has_element(self, toppath: PathBytes, path: PathBytes) -> bool:
        """Return whether `path` has been imported in `toppath`."""
        imported = self.tagprogress.get(toppath, [])
        i = bisect_left(imported, path)
        return i != len(imported) and imported[i] == path

    def progress_has(self, toppath: PathBytes) -> bool:
        """Return `True` if there exist paths that have already been
        imported under `toppath`.
        """
        return toppath in self.tagprogress

    def progress_reset(self, toppath: PathBytes):
        """Reset the progress for `toppath`."""
        with self as state:
            if toppath in state.tagprogress:
                del state.tagprogress[toppath]

    # -------------------------------- Taghistory -------------------------------- #

    def history_add(self, paths: list[PathBytes]):
        """Add the paths to the history."""
        with self as state:
            state.taghistory.add(tuple(paths))
