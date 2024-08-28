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

import itertools
import os
import pickle
import re
import shutil
import time
from bisect import bisect_left, insort
from collections import defaultdict
from contextlib import contextmanager
from enum import Enum
from tempfile import mkdtemp

import mediafile

from beets import autotag, config, dbcore, library, logging, plugins, util
from beets.util import (
    MoveOperation,
    ancestry,
    displayable_path,
    normpath,
    pipeline,
    sorted_walk,
    syspath,
)

action = Enum("action", ["SKIP", "ASIS", "TRACKS", "APPLY", "ALBUMS", "RETAG"])
# The RETAG action represents "don't apply any match, but do record
# new metadata". It's not reachable via the standard command prompt but
# can be used by plugins.

QUEUE_SIZE = 128
SINGLE_ARTIST_THRESH = 0.25
PROGRESS_KEY = "tagprogress"
HISTORY_KEY = "taghistory"
# Usually flexible attributes are preserved (i.e., not updated) during
# reimports. The following two lists (globally) change this behaviour for
# certain fields. To alter these lists only when a specific plugin is in use,
# something like this can be used within that plugin's code:
#
# from beets import importer
# def extend_reimport_fresh_fields_item():
#     importer.REIMPORT_FRESH_FIELDS_ITEM.extend(['tidal_track_popularity']
# )
REIMPORT_FRESH_FIELDS_ALBUM = [
    "data_source",
    "bandcamp_album_id",
    "spotify_album_id",
    "deezer_album_id",
    "beatport_album_id",
    "tidal_album_id",
]
REIMPORT_FRESH_FIELDS_ITEM = list(REIMPORT_FRESH_FIELDS_ALBUM)

# Global logger.
log = logging.getLogger("beets")


class ImportAbort(Exception):
    """Raised when the user aborts the tagging operation."""

    pass


# Utilities.


def _open_state():
    """Reads the state file, returning a dictionary."""
    try:
        with open(config["statefile"].as_filename(), "rb") as f:
            return pickle.load(f)
    except Exception as exc:
        # The `pickle` module can emit all sorts of exceptions during
        # unpickling, including ImportError. We use a catch-all
        # exception to avoid enumerating them all (the docs don't even have a
        # full list!).
        log.debug("state file could not be read: {0}", exc)
        return {}


def _save_state(state):
    """Writes the state dictionary out to disk."""
    try:
        with open(config["statefile"].as_filename(), "wb") as f:
            pickle.dump(state, f)
    except OSError as exc:
        log.error("state file could not be written: {0}", exc)


# Utilities for reading and writing the beets progress file, which
# allows long tagging tasks to be resumed when they pause (or crash).


def progress_read():
    state = _open_state()
    return state.setdefault(PROGRESS_KEY, {})


@contextmanager
def progress_write():
    state = _open_state()
    progress = state.setdefault(PROGRESS_KEY, {})
    yield progress
    _save_state(state)


def progress_add(toppath, *paths):
    """Record that the files under all of the `paths` have been imported
    under `toppath`.
    """
    with progress_write() as state:
        imported = state.setdefault(toppath, [])
        for path in paths:
            # Normally `progress_add` will be called with the path
            # argument increasing. This is because of the ordering in
            # `albums_in_dir`. We take advantage of that to make the
            # code faster
            if imported and imported[len(imported) - 1] <= path:
                imported.append(path)
            else:
                insort(imported, path)


def progress_element(toppath, path):
    """Return whether `path` has been imported in `toppath`."""
    state = progress_read()
    if toppath not in state:
        return False
    imported = state[toppath]
    i = bisect_left(imported, path)
    return i != len(imported) and imported[i] == path


def has_progress(toppath):
    """Return `True` if there exist paths that have already been
    imported under `toppath`.
    """
    state = progress_read()
    return toppath in state


def progress_reset(toppath):
    with progress_write() as state:
        if toppath in state:
            del state[toppath]


# Similarly, utilities for manipulating the "incremental" import log.
# This keeps track of all directories that were ever imported, which
# allows the importer to only import new stuff.


def history_add(paths):
    """Indicate that the import of the album in `paths` is completed and
    should not be repeated in incremental imports.
    """
    state = _open_state()
    if HISTORY_KEY not in state:
        state[HISTORY_KEY] = set()

    state[HISTORY_KEY].add(tuple(paths))

    _save_state(state)


def history_get():
    """Get the set of completed path tuples in incremental imports."""
    state = _open_state()
    if HISTORY_KEY not in state:
        return set()
    return state[HISTORY_KEY]


# Abstract session class.


class ImportSession:
    """Controls an import action. Subclasses should implement methods to
    communicate with the user or otherwise make decisions.
    """

    def __init__(self, lib, loghandler, paths, query):
        """Create a session. `lib` is a Library object. `loghandler` is a
        logging.Handler. Either `paths` or `query` is non-null and indicates
        the source of files to be imported.
        """
        self.lib = lib
        self.logger = self._setup_logging(loghandler)
        self.paths = paths
        self.query = query
        self._is_resuming = {}
        self._merged_items = set()
        self._merged_dirs = set()

        # Normalize the paths.
        if self.paths:
            self.paths = list(map(normpath, self.paths))

    def _setup_logging(self, loghandler):
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

    def tag_log(self, status, paths):
        """Log a message about a given album to the importer log. The status
        should reflect the reason the album couldn't be tagged.
        """
        self.logger.info("{0} {1}", status, displayable_path(paths))

    def log_choice(self, task, duplicate=False):
        """Logs the task's current choice if it should be logged. If
        ``duplicate``, then this is a secondary choice after a duplicate was
        detected and a decision was made.
        """
        paths = task.paths
        if duplicate:
            # Duplicate: log all three choices (skip, keep both, and trump).
            if task.should_remove_duplicates:
                self.tag_log("duplicate-replace", paths)
            elif task.choice_flag in (action.ASIS, action.APPLY):
                self.tag_log("duplicate-keep", paths)
            elif task.choice_flag is (action.SKIP):
                self.tag_log("duplicate-skip", paths)
        else:
            # Non-duplicate: log "skip" and "asis" choices.
            if task.choice_flag is action.ASIS:
                self.tag_log("asis", paths)
            elif task.choice_flag is action.SKIP:
                self.tag_log("skip", paths)

    def should_resume(self, path):
        raise NotImplementedError

    def choose_match(self, task):
        raise NotImplementedError

    def resolve_duplicate(self, task, found_duplicates):
        raise NotImplementedError

    def choose_item(self, task):
        raise NotImplementedError

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
        except ImportAbort:
            # User aborted operation. Silently stop.
            pass

    # Incremental and resumed imports

    def already_imported(self, toppath, paths):
        """Returns true if the files belonging to this task have already
        been imported in a previous session.
        """
        if self.is_resuming(toppath) and all(
            [progress_element(toppath, p) for p in paths]
        ):
            return True
        if self.config["incremental"] and tuple(paths) in self.history_dirs:
            return True

        return False

    @property
    def history_dirs(self):
        if not hasattr(self, "_history_dirs"):
            self._history_dirs = history_get()
        return self._history_dirs

    def already_merged(self, paths):
        """Returns true if all the paths being imported were part of a merge
        during previous tasks.
        """
        for path in paths:
            if path not in self._merged_items and path not in self._merged_dirs:
                return False
        return True

    def mark_merged(self, paths):
        """Mark paths and directories as merged for future reimport tasks."""
        self._merged_items.update(paths)
        dirs = {
            os.path.dirname(path) if os.path.isfile(syspath(path)) else path
            for path in paths
        }
        self._merged_dirs.update(dirs)

    def is_resuming(self, toppath):
        """Return `True` if user wants to resume import of this path.

        You have to call `ask_resume` first to determine the return value.
        """
        return self._is_resuming.get(toppath, False)

    def ask_resume(self, toppath):
        """If import of `toppath` was aborted in an earlier session, ask
        user if they want to resume the import.

        Determines the return value of `is_resuming(toppath)`.
        """
        if self.want_resume and has_progress(toppath):
            # Either accept immediately or prompt for input to decide.
            if self.want_resume is True or self.should_resume(toppath):
                log.warning(
                    "Resuming interrupted import of {0}",
                    util.displayable_path(toppath),
                )
                self._is_resuming[toppath] = True
            else:
                # Clear progress; we're starting from the top.
                progress_reset(toppath)


# The importer task class.


class BaseImportTask:
    """An abstract base class for importer tasks.

    Tasks flow through the importer pipeline. Each stage can update
    them."""

    def __init__(self, toppath, paths, items):
        """Create a task. The primary fields that define a task are:

        * `toppath`: The user-specified base directory that contains the
          music for this task. If the task has *no* user-specified base
          (for example, when importing based on an -L query), this can
          be None. This is used for tracking progress and history.
        * `paths`: A list of *specific* paths where the music for this task
          came from. These paths can be directories, when their entire
          contents are being imported, or files, when the task comprises
          individual tracks. This is used for progress/history tracking and
          for displaying the task to the user.
        * `items`: A list of `Item` objects representing the music being
          imported.

        These fields should not change after initialization.
        """
        self.toppath = toppath
        self.paths = paths
        self.items = items


class ImportTask(BaseImportTask):
    """Represents a single set of items to be imported along with its
    intermediate state. May represent an album or a single item.

    The import session and stages call the following methods in the
    given order.

    * `lookup_candidates()` Sets the `common_artist`, `common_album`,
      `candidates`, and `rec` attributes. `candidates` is a list of
      `AlbumMatch` objects.

    * `choose_match()` Uses the session to set the `match` attribute
      from the `candidates` list.

    * `find_duplicates()` Returns a list of albums from `lib` with the
      same artist and album name as the task.

    * `apply_metadata()` Sets the attributes of the items from the
      task's `match` attribute.

    * `add()` Add the imported items and album to the database.

    * `manipulate_files()` Copy, move, and write files depending on the
      session configuration.

    * `set_fields()` Sets the fields given at CLI or configuration to
      the specified values.

    * `finalize()` Update the import progress and cleanup the file
      system.
    """

    def __init__(self, toppath, paths, items):
        super().__init__(toppath, paths, items)
        self.choice_flag = None
        self.cur_album = None
        self.cur_artist = None
        self.candidates = []
        self.rec = None
        self.should_remove_duplicates = False
        self.should_merge_duplicates = False
        self.is_album = True
        self.search_ids = []  # user-supplied candidate IDs.

    def set_choice(self, choice):
        """Given an AlbumMatch or TrackMatch object or an action constant,
        indicates that an action has been selected for this task.
        """
        # Not part of the task structure:
        assert choice != action.APPLY  # Only used internally.
        if choice in (
            action.SKIP,
            action.ASIS,
            action.TRACKS,
            action.ALBUMS,
            action.RETAG,
        ):
            self.choice_flag = choice
            self.match = None
        else:
            self.choice_flag = action.APPLY  # Implicit choice.
            self.match = choice

    def save_progress(self):
        """Updates the progress state to indicate that this album has
        finished.
        """
        if self.toppath:
            progress_add(self.toppath, *self.paths)

    def save_history(self):
        """Save the directory in the history for incremental imports."""
        if self.paths:
            history_add(self.paths)

    # Logical decisions.

    @property
    def apply(self):
        return self.choice_flag == action.APPLY

    @property
    def skip(self):
        return self.choice_flag == action.SKIP

    # Convenient data.

    def chosen_info(self):
        """Return a dictionary of metadata about the current choice.
        May only be called when the choice flag is ASIS or RETAG
        (in which case the data comes from the files' current metadata)
        or APPLY (in which case the data comes from the choice).
        """
        if self.choice_flag in (action.ASIS, action.RETAG):
            likelies, consensus = autotag.current_metadata(self.items)
            return likelies
        elif self.choice_flag is action.APPLY:
            return self.match.info.copy()
        assert False

    def imported_items(self):
        """Return a list of Items that should be added to the library.

        If the tasks applies an album match the method only returns the
        matched items.
        """
        if self.choice_flag in (action.ASIS, action.RETAG):
            return list(self.items)
        elif self.choice_flag == action.APPLY:
            return list(self.match.mapping.keys())
        else:
            assert False

    def apply_metadata(self):
        """Copy metadata from match info to the items."""
        if config["import"]["from_scratch"]:
            for item in self.match.mapping:
                item.clear()

        autotag.apply_metadata(self.match.info, self.match.mapping)

    def duplicate_items(self, lib):
        duplicate_items = []
        for album in self.find_duplicates(lib):
            duplicate_items += album.items()
        return duplicate_items

    def remove_duplicates(self, lib):
        duplicate_items = self.duplicate_items(lib)
        log.debug("removing {0} old duplicated items", len(duplicate_items))
        for item in duplicate_items:
            item.remove()
            if lib.directory in util.ancestry(item.path):
                log.debug(
                    "deleting duplicate {0}", util.displayable_path(item.path)
                )
                util.remove(item.path)
                util.prune_dirs(os.path.dirname(item.path), lib.directory)

    def set_fields(self, lib):
        """Sets the fields given at CLI or configuration to the specified
        values, for both the album and all its items.
        """
        items = self.imported_items()
        for field, view in config["import"]["set_fields"].items():
            value = view.get()
            log.debug(
                "Set field {1}={2} for {0}",
                displayable_path(self.paths),
                field,
                value,
            )
            self.album.set_parse(field, format(self.album, value))
            for item in items:
                item.set_parse(field, format(item, value))
        with lib.transaction():
            for item in items:
                item.store()
            self.album.store()

    def finalize(self, session):
        """Save progress, clean up files, and emit plugin event."""
        # Update progress.
        if session.want_resume:
            self.save_progress()
        if session.config["incremental"] and not (
            # Should we skip recording to incremental list?
            self.skip
            and session.config["incremental_skip_later"]
        ):
            self.save_history()

        self.cleanup(
            copy=session.config["copy"],
            delete=session.config["delete"],
            move=session.config["move"],
        )

        if not self.skip:
            self._emit_imported(session.lib)

    def cleanup(self, copy=False, delete=False, move=False):
        """Remove and prune imported paths."""
        # Do not delete any files or prune directories when skipping.
        if self.skip:
            return

        items = self.imported_items()

        # When copying and deleting originals, delete old files.
        if copy and delete:
            new_paths = [os.path.realpath(item.path) for item in items]
            for old_path in self.old_paths:
                # Only delete files that were actually copied.
                if old_path not in new_paths:
                    util.remove(syspath(old_path), False)
                    self.prune(old_path)

        # When moving, prune empty directories containing the original files.
        elif move:
            for old_path in self.old_paths:
                self.prune(old_path)

    def _emit_imported(self, lib):
        plugins.send("album_imported", lib=lib, album=self.album)

    def handle_created(self, session):
        """Send the `import_task_created` event for this task. Return a list of
        tasks that should continue through the pipeline. By default, this is a
        list containing only the task itself, but plugins can replace the task
        with new ones.
        """
        tasks = plugins.send("import_task_created", session=session, task=self)
        if not tasks:
            tasks = [self]
        else:
            # The plugins gave us a list of lists of tasks. Flatten it.
            tasks = [t for inner in tasks for t in inner]
        return tasks

    def lookup_candidates(self):
        """Retrieve and store candidates for this album. User-specified
        candidate IDs are stored in self.search_ids: if present, the
        initial lookup is restricted to only those IDs.
        """
        artist, album, prop = autotag.tag_album(
            self.items, search_ids=self.search_ids
        )
        self.cur_artist = artist
        self.cur_album = album
        self.candidates = prop.candidates
        self.rec = prop.recommendation

    def find_duplicates(self, lib):
        """Return a list of albums from `lib` with the same artist and
        album name as the task.
        """
        info = self.chosen_info()
        info["albumartist"] = info["artist"]

        if info["artist"] is None:
            # As-is import with no artist. Skip check.
            return []

        # Construct a query to find duplicates with this metadata. We
        # use a temporary Album object to generate any computed fields.
        tmp_album = library.Album(lib, **info)
        keys = config["import"]["duplicate_keys"]["album"].as_str_seq()
        dup_query = library.Album.all_fields_query(
            {key: tmp_album.get(key) for key in keys}
        )

        # Don't count albums with the same files as duplicates.
        task_paths = {i.path for i in self.items if i}

        duplicates = []
        for album in lib.albums(dup_query):
            # Check whether the album paths are all present in the task
            # i.e. album is being completely re-imported by the task,
            # in which case it is not a duplicate (will be replaced).
            album_paths = {i.path for i in album.items()}
            if not (album_paths <= task_paths):
                duplicates.append(album)

        return duplicates

    def align_album_level_fields(self):
        """Make some album fields equal across `self.items`. For the
        RETAG action, we assume that the responsible for returning it
        (ie. a plugin) always ensures that the first item contains
        valid data on the relevant fields.
        """
        changes = {}

        if self.choice_flag == action.ASIS:
            # Taking metadata "as-is". Guess whether this album is VA.
            plur_albumartist, freq = util.plurality(
                [i.albumartist or i.artist for i in self.items]
            )
            if freq == len(self.items) or (
                freq > 1
                and float(freq) / len(self.items) >= SINGLE_ARTIST_THRESH
            ):
                # Single-artist album.
                changes["albumartist"] = plur_albumartist
                changes["comp"] = False
            else:
                # VA.
                changes["albumartist"] = config["va_name"].as_str()
                changes["comp"] = True

        elif self.choice_flag in (action.APPLY, action.RETAG):
            # Applying autotagged metadata. Just get AA from the first
            # item.
            if not self.items[0].albumartist:
                changes["albumartist"] = self.items[0].artist
            if not self.items[0].albumartists:
                changes["albumartists"] = self.items[0].artists
            if not self.items[0].mb_albumartistid:
                changes["mb_albumartistid"] = self.items[0].mb_artistid
            if not self.items[0].mb_albumartistids:
                changes["mb_albumartistids"] = self.items[0].mb_artistids

        # Apply new metadata.
        for item in self.items:
            item.update(changes)

    def manipulate_files(self, operation=None, write=False, session=None):
        """Copy, move, link, hardlink or reflink (depending on `operation`)
        the files as well as write metadata.

        `operation` should be an instance of `util.MoveOperation`.

        If `write` is `True` metadata is written to the files.
        """

        if session is not None and "verify" in session.config:
            verify = session.config["verify"]
        else:
            verify = False

        items = self.imported_items()
        # Save the original paths of all items for deletion and pruning
        # in the next step (finalization).
        self.old_paths = [item.path for item in items]
        for item in items:
            if operation is not None:
                # In copy and link modes, treat re-imports specially:
                # move in-library files. (Out-of-library files are
                # copied/moved as usual).
                old_path = item.path
                if (
                    operation != MoveOperation.MOVE
                    and self.replaced_items[item]
                    and session.lib.directory in util.ancestry(old_path)
                ):
                    item.move(verify=verify)
                    # We moved the item, so remove the
                    # now-nonexistent file from old_paths.
                    self.old_paths.remove(old_path)
                else:
                    # A normal import. Just copy files and keep track of
                    # old paths.
                    item.move(operation, verify=verify)

            if write and (self.apply or self.choice_flag == action.RETAG):
                item.try_write()

        with session.lib.transaction():
            for item in self.imported_items():
                item.store()

        plugins.send("import_task_files", session=session, task=self)

    def add(self, lib):
        """Add the items as an album to the library and remove replaced items."""
        self.align_album_level_fields()
        with lib.transaction():
            self.record_replaced(lib)
            self.remove_replaced(lib)

            self.album = lib.add_album(self.imported_items())
            if self.choice_flag == action.APPLY:
                # Copy album flexible fields to the DB
                # TODO: change the flow so we create the `Album` object earlier,
                #   and we can move this into `self.apply_metadata`, just like
                #   is done for tracks.
                autotag.apply_album_metadata(self.match.info, self.album)
                self.album.store()

            self.reimport_metadata(lib)

    def record_replaced(self, lib):
        """Records the replaced items and albums in the `replaced_items`
        and `replaced_albums` dictionaries.
        """
        self.replaced_items = defaultdict(list)
        self.replaced_albums = defaultdict(list)
        replaced_album_ids = set()
        for item in self.imported_items():
            dup_items = list(
                lib.items(dbcore.query.BytesQuery("path", item.path))
            )
            self.replaced_items[item] = dup_items
            for dup_item in dup_items:
                if (
                    not dup_item.album_id
                    or dup_item.album_id in replaced_album_ids
                ):
                    continue
                replaced_album = dup_item._cached_album
                if replaced_album:
                    replaced_album_ids.add(dup_item.album_id)
                    self.replaced_albums[replaced_album.path] = replaced_album

    def reimport_metadata(self, lib):
        """For reimports, preserves metadata for reimported items and
        albums.
        """

        def _reduce_and_log(new_obj, existing_fields, overwrite_keys):
            """Some flexible attributes should be overwritten (rather than
            preserved) on reimports; Copies existing_fields, logs and removes
            entries that should not be preserved and returns a dict containing
            those fields left to actually be preserved.
            """
            noun = "album" if isinstance(new_obj, library.Album) else "item"
            existing_fields = dict(existing_fields)
            overwritten_fields = [
                k
                for k in existing_fields
                if k in overwrite_keys
                and new_obj.get(k)
                and existing_fields.get(k) != new_obj.get(k)
            ]
            if overwritten_fields:
                log.debug(
                    "Reimported {} {}. Not preserving flexible attributes {}. "
                    "Path: {}",
                    noun,
                    new_obj.id,
                    overwritten_fields,
                    displayable_path(new_obj.path),
                )
                for key in overwritten_fields:
                    del existing_fields[key]
            return existing_fields

        if self.is_album:
            replaced_album = self.replaced_albums.get(self.album.path)
            if replaced_album:
                album_fields = _reduce_and_log(
                    self.album,
                    replaced_album._values_flex,
                    REIMPORT_FRESH_FIELDS_ALBUM,
                )
                self.album.added = replaced_album.added
                self.album.update(album_fields)
                self.album.artpath = replaced_album.artpath
                self.album.store()
                log.debug(
                    "Reimported album {}. Preserving attribute ['added']. "
                    "Path: {}",
                    self.album.id,
                    displayable_path(self.album.path),
                )
                log.debug(
                    "Reimported album {}. Preserving flexible attributes {}. "
                    "Path: {}",
                    self.album.id,
                    list(album_fields.keys()),
                    displayable_path(self.album.path),
                )

        for item in self.imported_items():
            dup_items = self.replaced_items[item]
            for dup_item in dup_items:
                if dup_item.added and dup_item.added != item.added:
                    item.added = dup_item.added
                    log.debug(
                        "Reimported item {}. Preserving attribute ['added']. "
                        "Path: {}",
                        item.id,
                        displayable_path(item.path),
                    )
                item_fields = _reduce_and_log(
                    item, dup_item._values_flex, REIMPORT_FRESH_FIELDS_ITEM
                )
                item.update(item_fields)
                log.debug(
                    "Reimported item {}. Preserving flexible attributes {}. "
                    "Path: {}",
                    item.id,
                    list(item_fields.keys()),
                    displayable_path(item.path),
                )
                item.store()

    def remove_replaced(self, lib):
        """Removes all the items from the library that have the same
        path as an item from this task.
        """
        for item in self.imported_items():
            for dup_item in self.replaced_items[item]:
                log.debug(
                    "Replacing item {0}: {1}",
                    dup_item.id,
                    displayable_path(item.path),
                )
                dup_item.remove()
        log.debug(
            "{0} of {1} items replaced",
            sum(bool(l) for l in self.replaced_items.values()),
            len(self.imported_items()),
        )

    def choose_match(self, session):
        """Ask the session which match should apply and apply it."""
        choice = session.choose_match(self)
        self.set_choice(choice)
        session.log_choice(self)

    def reload(self):
        """Reload albums and items from the database."""
        for item in self.imported_items():
            item.load()
        self.album.load()

    # Utilities.

    def prune(self, filename):
        """Prune any empty directories above the given file. If this
        task has no `toppath` or the file path provided is not within
        the `toppath`, then this function has no effect. Similarly, if
        the file still exists, no pruning is performed, so it's safe to
        call when the file in question may not have been removed.
        """
        if self.toppath and not os.path.exists(syspath(filename)):
            util.prune_dirs(
                os.path.dirname(filename),
                self.toppath,
                clutter=config["clutter"].as_str_seq(),
            )


class SingletonImportTask(ImportTask):
    """ImportTask for a single track that is not associated to an album."""

    def __init__(self, toppath, item):
        super().__init__(toppath, [item.path], [item])
        self.item = item
        self.is_album = False
        self.paths = [item.path]

    def chosen_info(self):
        """Return a dictionary of metadata about the current choice.
        May only be called when the choice flag is ASIS or RETAG
        (in which case the data comes from the files' current metadata)
        or APPLY (in which case the data comes from the choice).
        """
        assert self.choice_flag in (action.ASIS, action.RETAG, action.APPLY)
        if self.choice_flag in (action.ASIS, action.RETAG):
            return dict(self.item)
        elif self.choice_flag is action.APPLY:
            return self.match.info.copy()

    def imported_items(self):
        return [self.item]

    def apply_metadata(self):
        autotag.apply_item_metadata(self.item, self.match.info)

    def _emit_imported(self, lib):
        for item in self.imported_items():
            plugins.send("item_imported", lib=lib, item=item)

    def lookup_candidates(self):
        prop = autotag.tag_item(self.item, search_ids=self.search_ids)
        self.candidates = prop.candidates
        self.rec = prop.recommendation

    def find_duplicates(self, lib):
        """Return a list of items from `lib` that have the same artist
        and title as the task.
        """
        info = self.chosen_info()

        # Query for existing items using the same metadata. We use a
        # temporary `Item` object to generate any computed fields.
        tmp_item = library.Item(lib, **info)
        keys = config["import"]["duplicate_keys"]["item"].as_str_seq()
        dup_query = library.Album.all_fields_query(
            {key: tmp_item.get(key) for key in keys}
        )

        found_items = []
        for other_item in lib.items(dup_query):
            # Existing items not considered duplicates.
            if other_item.path != self.item.path:
                found_items.append(other_item)
        return found_items

    duplicate_items = find_duplicates

    def add(self, lib):
        with lib.transaction():
            self.record_replaced(lib)
            self.remove_replaced(lib)
            lib.add(self.item)
            self.reimport_metadata(lib)

    def infer_album_fields(self):
        raise NotImplementedError

    def choose_match(self, session):
        """Ask the session which match should apply and apply it."""
        choice = session.choose_item(self)
        self.set_choice(choice)
        session.log_choice(self)

    def reload(self):
        self.item.load()

    def set_fields(self, lib):
        """Sets the fields given at CLI or configuration to the specified
        values, for the singleton item.
        """
        for field, view in config["import"]["set_fields"].items():
            value = view.get()
            log.debug(
                "Set field {1}={2} for {0}",
                displayable_path(self.paths),
                field,
                value,
            )
            self.item.set_parse(field, format(self.item, value))
        self.item.store()


# FIXME The inheritance relationships are inverted. This is why there
# are so many methods which pass. More responsibility should be delegated to
# the BaseImportTask class.
class SentinelImportTask(ImportTask):
    """A sentinel task marks the progress of an import and does not
    import any items itself.

    If only `toppath` is set the task indicates the end of a top-level
    directory import. If the `paths` argument is also given, the task
    indicates the progress in the `toppath` import.
    """

    def __init__(self, toppath, paths):
        super().__init__(toppath, paths, ())
        # TODO Remove the remaining attributes eventually
        self.should_remove_duplicates = False
        self.is_album = True
        self.choice_flag = None

    def save_history(self):
        pass

    def save_progress(self):
        if self.paths is None:
            # "Done" sentinel.
            progress_reset(self.toppath)
        else:
            # "Directory progress" sentinel for singletons
            progress_add(self.toppath, *self.paths)

    def skip(self):
        return True

    def set_choice(self, choice):
        raise NotImplementedError

    def cleanup(self, **kwargs):
        pass

    def _emit_imported(self, session):
        pass


class ArchiveImportTask(SentinelImportTask):
    """An import task that represents the processing of an archive.

    `toppath` must be a `zip`, `tar`, or `rar` archive. Archive tasks
    serve two purposes:
    - First, it will unarchive the files to a temporary directory and
      return it. The client should read tasks from the resulting
      directory and send them through the pipeline.
    - Second, it will clean up the temporary directory when it proceeds
      through the pipeline. The client should send the archive task
      after sending the rest of the music tasks to make this work.
    """

    def __init__(self, toppath):
        super().__init__(toppath, ())
        self.extracted = False

    @classmethod
    def is_archive(cls, path):
        """Returns true if the given path points to an archive that can
        be handled.
        """
        if not os.path.isfile(path):
            return False

        for path_test, _ in cls.handlers():
            if path_test(os.fsdecode(path)):
                return True
        return False

    @classmethod
    def handlers(cls):
        """Returns a list of archive handlers.

        Each handler is a `(path_test, ArchiveClass)` tuple. `path_test`
        is a function that returns `True` if the given path can be
        handled by `ArchiveClass`. `ArchiveClass` is a class that
        implements the same interface as `tarfile.TarFile`.
        """
        if not hasattr(cls, "_handlers"):
            cls._handlers = []
            from zipfile import ZipFile, is_zipfile

            cls._handlers.append((is_zipfile, ZipFile))
            import tarfile

            cls._handlers.append((tarfile.is_tarfile, tarfile.open))
            try:
                from rarfile import RarFile, is_rarfile
            except ImportError:
                pass
            else:
                cls._handlers.append((is_rarfile, RarFile))
            try:
                from py7zr import SevenZipFile, is_7zfile
            except ImportError:
                pass
            else:
                cls._handlers.append((is_7zfile, SevenZipFile))

        return cls._handlers

    def cleanup(self, **kwargs):
        """Removes the temporary directory the archive was extracted to."""
        if self.extracted:
            log.debug(
                "Removing extracted directory: {0}",
                displayable_path(self.toppath),
            )
            shutil.rmtree(syspath(self.toppath))

    def extract(self):
        """Extracts the archive to a temporary directory and sets
        `toppath` to that directory.
        """
        for path_test, handler_class in self.handlers():
            if path_test(os.fsdecode(self.toppath)):
                break

        extract_to = mkdtemp()
        archive = handler_class(os.fsdecode(self.toppath), mode="r")
        try:
            archive.extractall(extract_to)

            # Adjust the files' mtimes to match the information from the
            # archive. Inspired by: https://stackoverflow.com/q/9813243
            for f in archive.infolist():
                # The date_time will need to adjusted otherwise
                # the item will have the current date_time of extraction.
                # The (0, 0, -1) is added to date_time because the
                # function time.mktime expects a 9-element tuple.
                # The -1 indicates that the DST flag is unknown.
                date_time = time.mktime(f.date_time + (0, 0, -1))
                fullpath = os.path.join(extract_to, f.filename)
                os.utime(fullpath, (date_time, date_time))

        finally:
            archive.close()
        self.extracted = True
        self.toppath = extract_to


class ImportTaskFactory:
    """Generate album and singleton import tasks for all media files
    indicated by a path.
    """

    def __init__(self, toppath, session):
        """Create a new task factory.

        `toppath` is the user-specified path to search for music to
        import. `session` is the `ImportSession`, which controls how
        tasks are read from the directory.
        """
        self.toppath = toppath
        self.session = session
        self.skipped = 0  # Skipped due to incremental/resume.
        self.imported = 0  # "Real" tasks created.
        self.is_archive = ArchiveImportTask.is_archive(syspath(toppath))

    def tasks(self):
        """Yield all import tasks for music found in the user-specified
        path `self.toppath`. Any necessary sentinel tasks are also
        produced.

        During generation, update `self.skipped` and `self.imported`
        with the number of tasks that were not produced (due to
        incremental mode or resumed imports) and the number of concrete
        tasks actually produced, respectively.

        If `self.toppath` is an archive, it is adjusted to point to the
        extracted data.
        """
        # Check whether this is an archive.
        if self.is_archive:
            archive_task = self.unarchive()
            if not archive_task:
                return

        # Search for music in the directory.
        for dirs, paths in self.paths():
            if self.session.config["singletons"]:
                for path in paths:
                    tasks = self._create(self.singleton(path))
                    yield from tasks
                yield self.sentinel(dirs)

            else:
                tasks = self._create(self.album(paths, dirs))
                yield from tasks

        # Produce the final sentinel for this toppath to indicate that
        # it is finished. This is usually just a SentinelImportTask, but
        # for archive imports, send the archive task instead (to remove
        # the extracted directory).
        if self.is_archive:
            yield archive_task
        else:
            yield self.sentinel()

    def _create(self, task):
        """Handle a new task to be emitted by the factory.

        Emit the `import_task_created` event and increment the
        `imported` count if the task is not skipped. Return the same
        task. If `task` is None, do nothing.
        """
        if task:
            tasks = task.handle_created(self.session)
            self.imported += len(tasks)
            return tasks
        return []

    def paths(self):
        """Walk `self.toppath` and yield `(dirs, files)` pairs where
        `files` are individual music files and `dirs` the set of
        containing directories where the music was found.

        This can either be a recursive search in the ordinary case, a
        single track when `toppath` is a file, a single directory in
        `flat` mode.
        """
        if not os.path.isdir(syspath(self.toppath)):
            yield [self.toppath], [self.toppath]
        elif self.session.config["flat"]:
            paths = []
            for dirs, paths_in_dir in albums_in_dir(self.toppath):
                paths += paths_in_dir
            yield [self.toppath], paths
        else:
            for dirs, paths in albums_in_dir(self.toppath):
                yield dirs, paths

    def singleton(self, path):
        """Return a `SingletonImportTask` for the music file."""
        if self.session.already_imported(self.toppath, [path]):
            log.debug(
                "Skipping previously-imported path: {0}", displayable_path(path)
            )
            self.skipped += 1
            return None

        item = self.read_item(path)
        if item:
            return SingletonImportTask(self.toppath, item)
        else:
            return None

    def album(self, paths, dirs=None):
        """Return a `ImportTask` with all media files from paths.

        `dirs` is a list of parent directories used to record already
        imported albums.
        """
        if not paths:
            return None

        if dirs is None:
            dirs = list({os.path.dirname(p) for p in paths})

        if self.session.already_imported(self.toppath, dirs):
            log.debug(
                "Skipping previously-imported path: {0}", displayable_path(dirs)
            )
            self.skipped += 1
            return None

        items = map(self.read_item, paths)
        items = [item for item in items if item]

        if items:
            return ImportTask(self.toppath, dirs, items)
        else:
            return None

    def sentinel(self, paths=None):
        """Return a `SentinelImportTask` indicating the end of a
        top-level directory import.
        """
        return SentinelImportTask(self.toppath, paths)

    def unarchive(self):
        """Extract the archive for this `toppath`.

        Extract the archive to a new directory, adjust `toppath` to
        point to the extracted directory, and return an
        `ArchiveImportTask`. If extraction fails, return None.
        """
        assert self.is_archive

        if not (self.session.config["move"] or self.session.config["copy"]):
            log.warning(
                "Archive importing requires either "
                "'copy' or 'move' to be enabled."
            )
            return

        log.debug("Extracting archive: {0}", displayable_path(self.toppath))
        archive_task = ArchiveImportTask(self.toppath)
        try:
            archive_task.extract()
        except Exception as exc:
            log.error("extraction failed: {0}", exc)
            return

        # Now read albums from the extracted directory.
        self.toppath = archive_task.toppath
        log.debug("Archive extracted to: {0}", self.toppath)
        return archive_task

    def read_item(self, path):
        """Return an `Item` read from the path.

        If an item cannot be read, return `None` instead and log an
        error.
        """
        try:
            return library.Item.from_path(path)
        except library.ReadError as exc:
            if isinstance(exc.reason, mediafile.FileTypeError):
                # Silently ignore non-music files.
                pass
            elif isinstance(exc.reason, mediafile.UnreadableFileError):
                log.warning("unreadable file: {0}", displayable_path(path))
            else:
                log.error("error reading {0}: {1}", displayable_path(path), exc)


# Pipeline utilities


def _freshen_items(items):
    # Clear IDs from re-tagged items so they appear "fresh" when
    # we add them back to the library.
    for item in items:
        item.id = None
        item.album_id = None


def _extend_pipeline(tasks, *stages):
    # Return pipeline extension for stages with list of tasks
    if isinstance(tasks, list):
        task_iter = iter(tasks)
    else:
        task_iter = tasks

    ipl = pipeline.Pipeline([task_iter] + list(stages))
    return pipeline.multiple(ipl.pull())


# Full-album pipeline stages.


def read_tasks(session):
    """A generator yielding all the albums (as ImportTask objects) found
    in the user-specified list of paths. In the case of a singleton
    import, yields single-item tasks instead.
    """
    skipped = 0
    for toppath in session.paths:
        # Check whether we need to resume the import.
        session.ask_resume(toppath)

        # Generate tasks.
        task_factory = ImportTaskFactory(toppath, session)
        yield from task_factory.tasks()
        skipped += task_factory.skipped

        if not task_factory.imported:
            log.warning("No files imported from {0}", displayable_path(toppath))

    # Show skipped directories (due to incremental/resume).
    if skipped:
        log.info("Skipped {0} paths.", skipped)


def query_tasks(session):
    """A generator that works as a drop-in-replacement for read_tasks.
    Instead of finding files from the filesystem, a query is used to
    match items from the library.
    """
    if session.config["singletons"]:
        # Search for items.
        for item in session.lib.items(session.query):
            task = SingletonImportTask(None, item)
            for task in task.handle_created(session):
                yield task

    else:
        # Search for albums.
        for album in session.lib.albums(session.query):
            log.debug(
                "yielding album {0}: {1} - {2}",
                album.id,
                album.albumartist,
                album.album,
            )
            items = list(album.items())
            _freshen_items(items)

            task = ImportTask(None, [album.item_dir()], items)
            for task in task.handle_created(session):
                yield task


@pipeline.mutator_stage
def lookup_candidates(session, task):
    """A coroutine for performing the initial MusicBrainz lookup for an
    album. It accepts lists of Items and yields
    (items, cur_artist, cur_album, candidates, rec) tuples. If no match
    is found, all of the yielded parameters (except items) are None.
    """
    if task.skip:
        # FIXME This gets duplicated a lot. We need a better
        # abstraction.
        return

    plugins.send("import_task_start", session=session, task=task)
    log.debug("Looking up: {0}", displayable_path(task.paths))

    # Restrict the initial lookup to IDs specified by the user via the -m
    # option. Currently all the IDs are passed onto the tasks directly.
    task.search_ids = session.config["search_ids"].as_str_seq()

    task.lookup_candidates()


@pipeline.stage
def user_query(session, task):
    """A coroutine for interfacing with the user about the tagging
    process.

    The coroutine accepts an ImportTask objects. It uses the
    session's `choose_match` method to determine the `action` for
    this task. Depending on the action additional stages are executed
    and the processed task is yielded.

    It emits the ``import_task_choice`` event for plugins. Plugins have
    access to the choice via the ``task.choice_flag`` property and may
    choose to change it.
    """
    if task.skip:
        return task

    if session.already_merged(task.paths):
        return pipeline.BUBBLE

    # Ask the user for a choice.
    task.choose_match(session)
    plugins.send("import_task_choice", session=session, task=task)

    # As-tracks: transition to singleton workflow.
    if task.choice_flag is action.TRACKS:
        # Set up a little pipeline for dealing with the singletons.
        def emitter(task):
            for item in task.items:
                task = SingletonImportTask(task.toppath, item)
                yield from task.handle_created(session)
            yield SentinelImportTask(task.toppath, task.paths)

        return _extend_pipeline(
            emitter(task), lookup_candidates(session), user_query(session)
        )

    # As albums: group items by albums and create task for each album
    if task.choice_flag is action.ALBUMS:
        return _extend_pipeline(
            [task],
            group_albums(session),
            lookup_candidates(session),
            user_query(session),
        )

    resolve_duplicates(session, task)

    if task.should_merge_duplicates:
        # Create a new task for tagging the current items
        # and duplicates together
        duplicate_items = task.duplicate_items(session.lib)

        # Duplicates would be reimported so make them look "fresh"
        _freshen_items(duplicate_items)
        duplicate_paths = [item.path for item in duplicate_items]

        # Record merged paths in the session so they are not reimported
        session.mark_merged(duplicate_paths)

        merged_task = ImportTask(
            None, task.paths + duplicate_paths, task.items + duplicate_items
        )

        return _extend_pipeline(
            [merged_task], lookup_candidates(session), user_query(session)
        )

    apply_choice(session, task)
    return task


def resolve_duplicates(session, task):
    """Check if a task conflicts with items or albums already imported
    and ask the session to resolve this.
    """
    if task.choice_flag in (action.ASIS, action.APPLY, action.RETAG):
        found_duplicates = task.find_duplicates(session.lib)
        if found_duplicates:
            log.debug(
                "found duplicates: {}".format([o.id for o in found_duplicates])
            )

            # Get the default action to follow from config.
            duplicate_action = config["import"]["duplicate_action"].as_choice(
                {
                    "skip": "s",
                    "keep": "k",
                    "remove": "r",
                    "merge": "m",
                    "ask": "a",
                }
            )
            log.debug("default action for duplicates: {0}", duplicate_action)

            if duplicate_action == "s":
                # Skip new.
                task.set_choice(action.SKIP)
            elif duplicate_action == "k":
                # Keep both. Do nothing; leave the choice intact.
                pass
            elif duplicate_action == "r":
                # Remove old.
                task.should_remove_duplicates = True
            elif duplicate_action == "m":
                # Merge duplicates together
                task.should_merge_duplicates = True
            else:
                # No default action set; ask the session.
                session.resolve_duplicate(task, found_duplicates)

            session.log_choice(task, True)


@pipeline.mutator_stage
def import_asis(session, task):
    """Select the `action.ASIS` choice for all tasks.

    This stage replaces the initial_lookup and user_query stages
    when the importer is run without autotagging.
    """
    if task.skip:
        return

    log.info("{}", displayable_path(task.paths))
    task.set_choice(action.ASIS)
    apply_choice(session, task)


def apply_choice(session, task):
    """Apply the task's choice to the Album or Item it contains and add
    it to the library.
    """
    if task.skip:
        return

    # Change metadata.
    if task.apply:
        task.apply_metadata()
        plugins.send("import_task_apply", session=session, task=task)

    task.add(session.lib)

    # If ``set_fields`` is set, set those fields to the
    # configured values.
    # NOTE: This cannot be done before the ``task.add()`` call above,
    # because then the ``ImportTask`` won't have an `album` for which
    # it can set the fields.
    if config["import"]["set_fields"]:
        task.set_fields(session.lib)


@pipeline.mutator_stage
def plugin_stage(session, func, task):
    """A coroutine (pipeline stage) that calls the given function with
    each non-skipped import task. These stages occur between applying
    metadata changes and moving/copying/writing files.
    """
    if task.skip:
        return

    func(session, task)

    # Stage may modify DB, so re-load cached item data.
    # FIXME Importer plugins should not modify the database but instead
    # the albums and items attached to tasks.
    task.reload()


@pipeline.stage
def manipulate_files(session, task):
    """A coroutine (pipeline stage) that performs necessary file
    manipulations *after* items have been added to the library and
    finalizes each task.
    """
    if not task.skip:
        if task.should_remove_duplicates:
            task.remove_duplicates(session.lib)

        if session.config["move"]:
            operation = MoveOperation.MOVE
        elif session.config["copy"]:
            operation = MoveOperation.COPY
        elif session.config["link"]:
            operation = MoveOperation.LINK
        elif session.config["hardlink"]:
            operation = MoveOperation.HARDLINK
        elif session.config["reflink"] == "auto":
            operation = MoveOperation.REFLINK_AUTO
        elif session.config["reflink"]:
            operation = MoveOperation.REFLINK
        else:
            operation = None

        task.manipulate_files(
            operation,
            write=session.config["write"],
            session=session,
        )

    # Progress, cleanup, and event.
    task.finalize(session)


@pipeline.stage
def log_files(session, task):
    """A coroutine (pipeline stage) to log each file to be imported."""
    if isinstance(task, SingletonImportTask):
        log.info("Singleton: {0}", displayable_path(task.item["path"]))
    elif task.items:
        log.info("Album: {0}", displayable_path(task.paths[0]))
        for item in task.items:
            log.info("  {0}", displayable_path(item["path"]))


def group_albums(session):
    """A pipeline stage that groups the items of each task into albums
    using their metadata.

    Groups are identified using their artist and album fields. The
    pipeline stage emits new album tasks for each discovered group.
    """

    def group(item):
        return (item.albumartist or item.artist, item.album)

    task = None
    while True:
        task = yield task
        if task.skip:
            continue
        tasks = []
        sorted_items = sorted(task.items, key=group)
        for _, items in itertools.groupby(sorted_items, group):
            items = list(items)
            task = ImportTask(task.toppath, [i.path for i in items], items)
            tasks += task.handle_created(session)
        tasks.append(SentinelImportTask(task.toppath, task.paths))

        task = pipeline.multiple(tasks)


MULTIDISC_MARKERS = (rb"dis[ck]", rb"cd")
MULTIDISC_PAT_FMT = rb"^(.*%s[\W_]*)\d"


def is_subdir_of_any_in_list(path, dirs):
    """Returns True if path os a subdirectory of any directory in dirs
    (a list). In other case, returns False.
    """
    ancestors = ancestry(path)
    return any(d in ancestors for d in dirs)


def albums_in_dir(path):
    """Recursively searches the given directory and returns an iterable
    of (paths, items) where paths is a list of directories and items is
    a list of Items that is probably an album. Specifically, any folder
    containing any media files is an album.
    """
    collapse_pat = collapse_paths = collapse_items = None
    ignore = config["ignore"].as_str_seq()
    ignore_hidden = config["ignore_hidden"].get(bool)

    for root, dirs, files in sorted_walk(
        path, ignore=ignore, ignore_hidden=ignore_hidden, logger=log
    ):
        items = [os.path.join(root, f) for f in files]
        # If we're currently collapsing the constituent directories in a
        # multi-disc album, check whether we should continue collapsing
        # and add the current directory. If so, just add the directory
        # and move on to the next directory. If not, stop collapsing.
        if collapse_paths:
            if (is_subdir_of_any_in_list(root, collapse_paths)) or (
                collapse_pat and collapse_pat.match(os.path.basename(root))
            ):
                # Still collapsing.
                collapse_paths.append(root)
                collapse_items += items
                continue
            else:
                # Collapse finished. Yield the collapsed directory and
                # proceed to process the current one.
                if collapse_items:
                    yield collapse_paths, collapse_items
                collapse_pat = collapse_paths = collapse_items = None

        # Check whether this directory looks like the *first* directory
        # in a multi-disc sequence. There are two indicators: the file
        # is named like part of a multi-disc sequence (e.g., "Title Disc
        # 1") or it contains no items but only directories that are
        # named in this way.
        start_collapsing = False
        for marker in MULTIDISC_MARKERS:
            # We're using replace on %s due to lack of .format() on bytestrings
            p = MULTIDISC_PAT_FMT.replace(b"%s", marker)
            marker_pat = re.compile(p, re.I)
            match = marker_pat.match(os.path.basename(root))

            # Is this directory the root of a nested multi-disc album?
            if dirs and not items:
                # Check whether all subdirectories have the same prefix.
                start_collapsing = True
                subdir_pat = None
                for subdir in dirs:
                    subdir = util.bytestring_path(subdir)
                    # The first directory dictates the pattern for
                    # the remaining directories.
                    if not subdir_pat:
                        match = marker_pat.match(subdir)
                        if match:
                            match_group = re.escape(match.group(1))
                            subdir_pat = re.compile(
                                b"".join([b"^", match_group, rb"\d"]), re.I
                            )
                        else:
                            start_collapsing = False
                            break

                    # Subsequent directories must match the pattern.
                    elif not subdir_pat.match(subdir):
                        start_collapsing = False
                        break

                # If all subdirectories match, don't check other
                # markers.
                if start_collapsing:
                    break

            # Is this directory the first in a flattened multi-disc album?
            elif match:
                start_collapsing = True
                # Set the current pattern to match directories with the same
                # prefix as this one, followed by a digit.
                collapse_pat = re.compile(
                    b"".join([b"^", re.escape(match.group(1)), rb"\d"]), re.I
                )
                break

        # If either of the above heuristics indicated that this is the
        # beginning of a multi-disc album, initialize the collapsed
        # directory and item lists and check the next directory.
        if start_collapsing:
            # Start collapsing; continue to the next iteration.
            collapse_paths = [root]
            collapse_items = items
            continue

        # If it's nonempty, yield it.
        if items:
            yield [root], items

    # Clear out any unfinished collapse.
    if collapse_paths and collapse_items:
        yield collapse_paths, collapse_items
