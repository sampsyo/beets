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


from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Sequence

from beets import config, dbcore, library, logging, plugins, util
from beets.util import displayable_path, normpath, pipeline, syspath

from .stages import (
    Action,
    group_albums,
    import_asis,
    log_files,
    lookup_candidates,
    manipulate_files,
    plugin_stage,
    query_tasks,
    read_tasks,
    user_query,
)
from .state import ImportState

if TYPE_CHECKING:
    from .tasks import ImportTask


QUEUE_SIZE = 128

# Global logger.
log = logging.getLogger("beets")


# Here for now to allow for a easy replace later on
# once we can move to a PathLike
PathBytes = bytes


class ImportAbortError(Exception):
    """Raised when the user aborts the tagging operation."""

    pass


class ImportSession:
    """Controls an import action. Subclasses should implement methods to
    communicate with the user or otherwise make decisions.
    """

    logger: logging.Logger
    paths: list[bytes] | None = None
    lib: library.Library

    _is_resuming: dict[bytes, bool]
    _merged_items: set[PathBytes]
    _merged_dirs: set[PathBytes]

    def __init__(
        self,
        lib: library.Library,
        loghandler: logging.Handler | None,
        paths: Sequence[PathBytes] | None,
        query: dbcore.Query | None,
    ):
        """Create a session.

        Parameters
        ----------
        lib : library.Library
            The library instance to which items will be imported.
        loghandler : logging.Handler or None
            A logging handler to use for the session's logger. If None, a
            NullHandler will be used.
        paths : os.PathLike or None
            The paths to be imported. If None, no paths are specified.
        query : dbcore.Query or None
            A query to filter items for import. If None, no query is applied.
        """
        self.lib = lib
        self.logger = self._setup_logging(loghandler)
        self.query = query
        self._is_resuming = {}
        self._merged_items = set()
        self._merged_dirs = set()

        # Normalize the paths.
        if paths is not None:
            self.paths = list(map(normpath, paths))

    def _setup_logging(self, loghandler: logging.Handler | None):
        logger = logging.getLogger(__name__)
        logger.propagate = False
        if not loghandler:
            loghandler = logging.NullHandler()
        logger.handlers = [loghandler]
        return logger

    def set_config(self, config):
        """Set `config` property from global import config and make
        implied changes.
        """
        # FIXME: Maybe this function should not exist and should instead
        # provide "decision wrappers" like "should_resume()", etc.
        iconfig = dict(config)
        self.config = iconfig

        # Incremental and progress are mutually exclusive.
        if iconfig["incremental"]:
            iconfig["resume"] = False

        # When based on a query instead of directories, never
        # save progress or try to resume.
        if self.query is not None:
            iconfig["resume"] = False
            iconfig["incremental"] = False

        if iconfig["reflink"]:
            iconfig["reflink"] = iconfig["reflink"].as_choice(
                ["auto", True, False]
            )

        # Copy, move, reflink, link, and hardlink are mutually exclusive.
        if iconfig["move"]:
            iconfig["copy"] = False
            iconfig["link"] = False
            iconfig["hardlink"] = False
            iconfig["reflink"] = False
        elif iconfig["link"]:
            iconfig["copy"] = False
            iconfig["move"] = False
            iconfig["hardlink"] = False
            iconfig["reflink"] = False
        elif iconfig["hardlink"]:
            iconfig["copy"] = False
            iconfig["move"] = False
            iconfig["link"] = False
            iconfig["reflink"] = False
        elif iconfig["reflink"]:
            iconfig["copy"] = False
            iconfig["move"] = False
            iconfig["link"] = False
            iconfig["hardlink"] = False

        # Only delete when copying.
        if not iconfig["copy"]:
            iconfig["delete"] = False

        self.want_resume = config["resume"].as_choice([True, False, "ask"])

    def tag_log(self, status, paths: Sequence[PathBytes]):
        """Log a message about a given album to the importer log. The status
        should reflect the reason the album couldn't be tagged.
        """
        self.logger.info("{0} {1}", status, displayable_path(paths))

    def log_choice(self, task: ImportTask, duplicate=False):
        """Logs the task's current choice if it should be logged. If
        ``duplicate``, then this is a secondary choice after a duplicate was
        detected and a decision was made.
        """
        paths = task.paths
        if duplicate:
            # Duplicate: log all three choices (skip, keep both, and trump).
            if task.should_remove_duplicates:
                self.tag_log("duplicate-replace", paths)
            elif task.choice_flag in (Action.ASIS, Action.APPLY):
                self.tag_log("duplicate-keep", paths)
            elif task.choice_flag is (Action.SKIP):
                self.tag_log("duplicate-skip", paths)
        else:
            # Non-duplicate: log "skip" and "asis" choices.
            if task.choice_flag is Action.ASIS:
                self.tag_log("asis", paths)
            elif task.choice_flag is Action.SKIP:
                self.tag_log("skip", paths)

    def should_resume(self, path: PathBytes):
        raise NotImplementedError(
            "Inheriting class must implement `should_resume`"
        )

    def choose_match(self, task: ImportTask):
        raise NotImplementedError(
            "Inheriting class must implement `choose_match`"
        )

    def resolve_duplicate(self, task: ImportTask, found_duplicates):
        raise NotImplementedError(
            "Inheriting class must implement `resolve_duplicate`"
        )

    def choose_item(self, task: ImportTask):
        raise NotImplementedError(
            "Inheriting class must implement `choose_item`"
        )

    def run(self):
        """Run the import task."""
        self.logger.info("import started {0}", time.asctime())
        self.set_config(config["import"])

        # Set up the pipeline.
        if self.query is None:
            stages = [read_tasks(self)]
        else:
            stages = [query_tasks(self)]

        # In pretend mode, just log what would otherwise be imported.
        if self.config["pretend"]:
            stages += [log_files(self)]
        else:
            if self.config["group_albums"] and not self.config["singletons"]:
                # Split directory tasks into one task for each album.
                stages += [group_albums(self)]

            # These stages either talk to the user to get a decision or,
            # in the case of a non-autotagged import, just choose to
            # import everything as-is. In *both* cases, these stages
            # also add the music to the library database, so later
            # stages need to read and write data from there.
            if self.config["autotag"]:
                stages += [lookup_candidates(self), user_query(self)]
            else:
                stages += [import_asis(self)]

            # Plugin stages.
            for stage_func in plugins.early_import_stages():
                stages.append(plugin_stage(self, stage_func))
            for stage_func in plugins.import_stages():
                stages.append(plugin_stage(self, stage_func))

            stages += [manipulate_files(self)]

        pl = pipeline.Pipeline(stages)

        # Run the pipeline.
        plugins.send("import_begin", session=self)
        try:
            if config["threaded"]:
                pl.run_parallel(QUEUE_SIZE)
            else:
                pl.run_sequential()
        except ImportAbortError:
            # User aborted operation. Silently stop.
            pass

    # Incremental and resumed imports

    def already_imported(self, toppath: PathBytes, paths: Sequence[PathBytes]):
        """Returns true if the files belonging to this task have already
        been imported in a previous session.
        """
        if self.is_resuming(toppath) and all(
            [ImportState().progress_has_element(toppath, p) for p in paths]
        ):
            return True
        if self.config["incremental"] and tuple(paths) in self.history_dirs:
            return True

        return False

    _history_dirs = None

    @property
    def history_dirs(self):
        if self._history_dirs is None:
            self._history_dirs = ImportState().taghistory
        return self._history_dirs

    def already_merged(self, paths: Sequence[PathBytes]):
        """Returns true if all the paths being imported were part of a merge
        during previous tasks.
        """
        for path in paths:
            if path not in self._merged_items and path not in self._merged_dirs:
                return False
        return True

    def mark_merged(self, paths: Sequence[PathBytes]):
        """Mark paths and directories as merged for future reimport tasks."""
        self._merged_items.update(paths)
        dirs = {
            os.path.dirname(path) if os.path.isfile(syspath(path)) else path
            for path in paths
        }
        self._merged_dirs.update(dirs)

    def is_resuming(self, toppath: PathBytes):
        """Return `True` if user wants to resume import of this path.

        You have to call `ask_resume` first to determine the return value.
        """
        return self._is_resuming.get(normpath(toppath), False)

    def ask_resume(self, toppath: PathBytes):
        """If import of `toppath` was aborted in an earlier session, ask
        user if they want to resume the import.

        Determines the return value of `is_resuming(toppath)`.
        """
        if self.want_resume and ImportState().progress_has(toppath):
            # Either accept immediately or prompt for input to decide.
            if self.want_resume is True or self.should_resume(toppath):
                log.warning(
                    "Resuming interrupted import of {0}",
                    util.displayable_path(normpath(toppath)),
                )
                self._is_resuming[normpath(toppath)] = True
            else:
                # Clear progress; we're starting from the top.
                ImportState().progress_reset(toppath)


__all__ = ["ImportSession", "ImportAbortError"]
