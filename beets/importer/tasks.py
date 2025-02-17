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

import logging
import os
import re
import shutil
import time
from collections import defaultdict
from enum import Enum
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Callable, Iterable, Sequence

import mediafile

from beets import autotag, config, dbcore, library, plugins, util

from .state import ImportState

if TYPE_CHECKING:
    from .session import ImportSession, PathBytes

# Global logger.
log = logging.getLogger("beets")


SINGLE_ARTIST_THRESH = 0.25

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


class ImportAbortError(Exception):
    """Raised when the user aborts the tagging operation."""

    pass


class Action(Enum):
    """Enumeration of possible actions for an import task."""

    SKIP = "SKIP"
    ASIS = "ASIS"
    TRACKS = "TRACKS"
    APPLY = "APPLY"
    ALBUMS = "ALBUMS"
    RETAG = "RETAG"
    # The RETAG action represents "don't apply any match, but do record
    # new metadata". It's not reachable via the standard command prompt but
    # can be used by plugins.


class BaseImportTask:
    """An abstract base class for importer tasks.

    Tasks flow through the importer pipeline. Each stage can update
    them."""

    toppath: PathBytes | None
    paths: list[PathBytes]
    items: list[library.Item]

    def __init__(
        self,
        toppath: PathBytes | None,
        paths: Iterable[PathBytes] | None,
        items: Iterable[library.Item] | None,
    ):
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
        self.paths = list(paths) if paths is not None else []
        self.items = list(items) if items is not None else []


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

    choice_flag: Action | None = None
    match: autotag.AlbumMatch | autotag.TrackMatch | None = None

    # Keep track of the current task item
    cur_album: str | None = None
    cur_artist: str | None = None
    candidates: Sequence[autotag.AlbumMatch | autotag.TrackMatch] = []

    def __init__(
        self,
        toppath: PathBytes | None,
        paths: Iterable[PathBytes] | None,
        items: Iterable[library.Item] | None,
    ):
        super().__init__(toppath, paths, items)
        self.rec = None
        self.should_remove_duplicates = False
        self.should_merge_duplicates = False
        self.is_album = True
        self.search_ids = []  # user-supplied candidate IDs.

    def set_choice(
        self, choice: Action | autotag.AlbumMatch | autotag.TrackMatch
    ):
        """Given an AlbumMatch or TrackMatch object or an action constant,
        indicates that an action has been selected for this task.

        Album and trackmatch are implemented as tuples, so we can't
        use isinstance to check for them.
        """
        # Not part of the task structure:
        assert choice != Action.APPLY  # Only used internally.

        if choice in (
            Action.SKIP,
            Action.ASIS,
            Action.TRACKS,
            Action.ALBUMS,
            Action.RETAG,
        ):
            # TODO: redesign to stricten the type
            self.choice_flag = choice  # type: ignore[assignment]
            self.match = None
        else:
            self.choice_flag = Action.APPLY  # Implicit choice.
            self.match = choice  # type: ignore[assignment]

    def save_progress(self):
        """Updates the progress state to indicate that this album has
        finished.
        """
        if self.toppath:
            ImportState().progress_add(self.toppath, *self.paths)

    def save_history(self):
        """Save the directory in the history for incremental imports."""
        ImportState().history_add(self.paths)

    # Logical decisions.

    @property
    def apply(self):
        return self.choice_flag == Action.APPLY

    @property
    def skip(self):
        return self.choice_flag == Action.SKIP

    # Convenient data.

    def chosen_info(self):
        """Return a dictionary of metadata about the current choice.
        May only be called when the choice flag is ASIS or RETAG
        (in which case the data comes from the files' current metadata)
        or APPLY (in which case the data comes from the choice).
        """
        if self.choice_flag in (Action.ASIS, Action.RETAG):
            likelies, consensus = autotag.current_metadata(self.items)
            return likelies
        elif self.choice_flag is Action.APPLY and self.match:
            return self.match.info.copy()
        assert False

    def imported_items(self):
        """Return a list of Items that should be added to the library.

        If the tasks applies an album match the method only returns the
        matched items.
        """
        if self.choice_flag in (Action.ASIS, Action.RETAG):
            return list(self.items)
        elif self.choice_flag == Action.APPLY and isinstance(
            self.match, autotag.AlbumMatch
        ):
            return list(self.match.mapping.keys())
        else:
            assert False

    def apply_metadata(self):
        """Copy metadata from match info to the items."""
        if config["import"]["from_scratch"]:
            for item in self.match.mapping:
                item.clear()

        autotag.apply_metadata(self.match.info, self.match.mapping)

    def duplicate_items(self, lib: library.Library):
        duplicate_items = []
        for album in self.find_duplicates(lib):
            duplicate_items += album.items()
        return duplicate_items

    def remove_duplicates(self, lib: library.Library):
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

    def set_fields(self, lib: library.Library):
        """Sets the fields given at CLI or configuration to the specified
        values, for both the album and all its items.
        """
        items = self.imported_items()
        for field, view in config["import"]["set_fields"].items():
            value = str(view.get())
            log.debug(
                "Set field {1}={2} for {0}",
                util.displayable_path(self.paths),
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

    def finalize(self, session: ImportSession):
        """Save progress, clean up files, and emit plugin event."""
        # Update progress.
        if session.want_resume:
            self.save_progress()
        if session.config["incremental"] and not (
            # Should we skip recording to incremental list?
            self.skip and session.config["incremental_skip_later"]
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
                    util.remove(old_path, False)
                    self.prune(old_path)

        # When moving, prune empty directories containing the original files.
        elif move:
            for old_path in self.old_paths:
                self.prune(old_path)

    def _emit_imported(self, lib: library.Library):
        plugins.send("album_imported", lib=lib, album=self.album)

    def handle_created(self, session: ImportSession):
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

    def find_duplicates(self, lib: library.Library):
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
        keys: list[str] = config["import"]["duplicate_keys"][
            "album"
        ].as_str_seq()
        dup_query = tmp_album.duplicates_query(keys)

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

        if self.choice_flag == Action.ASIS:
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

        elif self.choice_flag in (Action.APPLY, Action.RETAG):
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

    def manipulate_files(
        self,
        session: ImportSession,
        operation: util.MoveOperation | None = None,
        write=False,
    ):
        """Copy, move, link, hardlink or reflink (depending on `operation`)
        the files as well as write metadata.

        `operation` should be an instance of `util.MoveOperation`.

        If `write` is `True` metadata is written to the files.
        # TODO: Introduce a MoveOperation.NONE or SKIP
        """

        items = self.imported_items()
        # Save the original paths of all items for deletion and pruning
        # in the next step (finalization).
        self.old_paths: list[PathBytes] = [item.path for item in items]
        for item in items:
            if operation is not None:
                # In copy and link modes, treat re-imports specially:
                # move in-library files. (Out-of-library files are
                # copied/moved as usual).
                old_path = item.path
                if (
                    operation != util.MoveOperation.MOVE
                    and self.replaced_items[item]
                    and session.lib.directory in util.ancestry(old_path)
                ):
                    item.move()
                    # We moved the item, so remove the
                    # now-nonexistent file from old_paths.
                    self.old_paths.remove(old_path)
                else:
                    # A normal import. Just copy files and keep track of
                    # old paths.
                    item.move(operation)

            if write and (self.apply or self.choice_flag == Action.RETAG):
                item.try_write()

        with session.lib.transaction():
            for item in self.imported_items():
                item.store()

        plugins.send("import_task_files", session=session, task=self)

    def add(self, lib: library.Library):
        """Add the items as an album to the library and remove replaced items."""
        self.align_album_level_fields()
        with lib.transaction():
            self.record_replaced(lib)
            self.remove_replaced(lib)

            self.album = lib.add_album(self.imported_items())
            if self.choice_flag == Action.APPLY and isinstance(
                self.match, autotag.AlbumMatch
            ):
                # Copy album flexible fields to the DB
                # TODO: change the flow so we create the `Album` object earlier,
                #   and we can move this into `self.apply_metadata`, just like
                #   is done for tracks.
                autotag.apply_album_metadata(self.match.info, self.album)
                self.album.store()

            self.reimport_metadata(lib)

    def record_replaced(self, lib: library.Library):
        """Records the replaced items and albums in the `replaced_items`
        and `replaced_albums` dictionaries.
        """
        self.replaced_items = defaultdict(list)
        self.replaced_albums: dict[PathBytes, library.Album] = defaultdict()
        replaced_album_ids = set()
        for item in self.imported_items():
            dup_items = list(
                lib.items(query=dbcore.query.BytesQuery("path", item.path))
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

    def reimport_metadata(self, lib: library.Library):
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
                    util.displayable_path(new_obj.path),
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
                    util.displayable_path(self.album.path),
                )
                log.debug(
                    "Reimported album {}. Preserving flexible attributes {}. "
                    "Path: {}",
                    self.album.id,
                    list(album_fields.keys()),
                    util.displayable_path(self.album.path),
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
                        util.displayable_path(item.path),
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
                    util.displayable_path(item.path),
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
                    util.displayable_path(item.path),
                )
                dup_item.remove()
        log.debug(
            "{0} of {1} items replaced",
            sum(bool(v) for v in self.replaced_items.values()),
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
        if self.toppath and not os.path.exists(util.syspath(filename)):
            util.prune_dirs(
                os.path.dirname(filename),
                self.toppath,
                clutter=config["clutter"].as_str_seq(),
            )


class SingletonImportTask(ImportTask):
    """ImportTask for a single track that is not associated to an album."""

    def __init__(self, toppath: PathBytes | None, item: library.Item):
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
        assert self.choice_flag in (Action.ASIS, Action.RETAG, Action.APPLY)
        if self.choice_flag in (Action.ASIS, Action.RETAG):
            return dict(self.item)
        elif self.choice_flag is Action.APPLY:
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
        keys: list[str] = config["import"]["duplicate_keys"][
            "item"
        ].as_str_seq()
        dup_query = tmp_item.duplicates_query(keys)

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

    def choose_match(self, session: ImportSession):
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
            value = str(view.get())
            log.debug(
                "Set field {1}={2} for {0}",
                util.displayable_path(self.paths),
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
        if not self.paths:
            # "Done" sentinel.
            ImportState().progress_reset(self.toppath)
        elif self.toppath:
            # "Directory progress" sentinel for singletons
            super().save_progress()

    @property
    def skip(self) -> bool:
        return True

    def set_choice(self, choice):
        raise NotImplementedError

    def cleanup(self, copy=False, delete=False, move=False):
        pass

    def _emit_imported(self, lib):
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
            cls._handlers: list[tuple[Callable, ...]] = []
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

    def cleanup(self, copy=False, delete=False, move=False):
        """Removes the temporary directory the archive was extracted to."""
        if self.extracted and self.toppath:
            log.debug(
                "Removing extracted directory: {0}",
                util.displayable_path(self.toppath),
            )
            shutil.rmtree(util.syspath(self.toppath))

    def extract(self):
        """Extracts the archive to a temporary directory and sets
        `toppath` to that directory.
        """
        assert self.toppath is not None, "toppath must be set"

        for path_test, handler_class in self.handlers():
            if path_test(os.fsdecode(self.toppath)):
                break
        else:
            raise ValueError(f"No handler found for archive: {self.toppath}")
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

    def __init__(self, toppath: PathBytes, session: ImportSession):
        """Create a new task factory.

        `toppath` is the user-specified path to search for music to
        import. `session` is the `ImportSession`, which controls how
        tasks are read from the directory.
        """
        self.toppath = toppath
        self.session = session
        self.skipped = 0  # Skipped due to incremental/resume.
        self.imported = 0  # "Real" tasks created.
        self.is_archive = ArchiveImportTask.is_archive(util.syspath(toppath))

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
        archive_task: ArchiveImportTask | None = None
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
        yield archive_task or self.sentinel()

    def _create(self, task: ImportTask | None):
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
        if not os.path.isdir(util.syspath(self.toppath)):
            yield [self.toppath], [self.toppath]
        elif self.session.config["flat"]:
            paths = []
            for dirs, paths_in_dir in albums_in_dir(self.toppath):
                paths += paths_in_dir
            yield [self.toppath], paths
        else:
            for dirs, paths in albums_in_dir(self.toppath):
                yield dirs, paths

    def singleton(self, path: PathBytes):
        """Return a `SingletonImportTask` for the music file."""
        if self.session.already_imported(self.toppath, [path]):
            log.debug(
                "Skipping previously-imported path: {0}",
                util.displayable_path(path),
            )
            self.skipped += 1
            return None

        item = self.read_item(path)
        if item:
            return SingletonImportTask(self.toppath, item)
        else:
            return None

    def album(self, paths: Iterable[PathBytes], dirs=None):
        """Return a `ImportTask` with all media files from paths.

        `dirs` is a list of parent directories used to record already
        imported albums.
        """

        if dirs is None:
            dirs = list({os.path.dirname(p) for p in paths})

        if self.session.already_imported(self.toppath, dirs):
            log.debug(
                "Skipping previously-imported path: {0}",
                util.displayable_path(dirs),
            )
            self.skipped += 1
            return None

        items: list[library.Item] = [
            item for item in map(self.read_item, paths) if item
        ]

        if len(items) > 0:
            return ImportTask(self.toppath, dirs, items)
        else:
            return None

    def sentinel(self, paths: Iterable[PathBytes] | None = None):
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

        log.debug(
            "Extracting archive: {0}", util.displayable_path(self.toppath)
        )
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

    def read_item(self, path: PathBytes):
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
                log.warning("unreadable file: {0}", util.displayable_path(path))
            else:
                log.error(
                    "error reading {0}: {1}", util.displayable_path(path), exc
                )


MULTIDISC_MARKERS = (rb"dis[ck]", rb"cd")
MULTIDISC_PAT_FMT = rb"^(.*%s[\W_]*)\d"


def is_subdir_of_any_in_list(path, dirs):
    """Returns True if path os a subdirectory of any directory in dirs
    (a list). In other case, returns False.
    """
    ancestors = util.ancestry(path)
    return any(d in ancestors for d in dirs)


def albums_in_dir(path: PathBytes):
    """Recursively searches the given directory and returns an iterable
    of (paths, items) where paths is a list of directories and items is
    a list of Items that is probably an album. Specifically, any folder
    containing any media files is an album.
    """
    collapse_pat = collapse_paths = collapse_items = None
    ignore: list[str] = config["ignore"].as_str_seq()
    ignore_hidden: bool = config["ignore_hidden"].get(bool)

    for root, dirs, files in util.sorted_walk(
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


__all__ = [
    "Action",
    "ImportTask",
    "SingletonImportTask",
    "SentinelImportTask",
    "ArchiveImportTask",
    "ImportTaskFactory",
    "REIMPORT_FRESH_FIELDS_ALBUM",
    "REIMPORT_FRESH_FIELDS_ITEM",
]
