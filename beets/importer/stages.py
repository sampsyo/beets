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

import itertools
import logging
from typing import TYPE_CHECKING, Callable

from beets import config, plugins
from beets.util import MoveOperation, displayable_path, pipeline

from .tasks import (
    Action,
    ImportTask,
    ImportTaskFactory,
    SentinelImportTask,
    SingletonImportTask,
)

if TYPE_CHECKING:
    from beets import library

    from .session import ImportSession

# Global logger.
log = logging.getLogger("beets")

# ---------------------------- Producer functions ---------------------------- #
# Functions that are called first i.e. they generate import tasks


def read_tasks(session: ImportSession):
    """A generator yielding all the albums (as ImportTask objects) found
    in the user-specified list of paths. In the case of a singleton
    import, yields single-item tasks instead.
    """
    skipped = 0
    if session.paths is None:
        log.warning("No path specified in session.")
        return

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


def query_tasks(session: ImportSession):
    """A generator that works as a drop-in-replacement for read_tasks.
    Instead of finding files from the filesystem, a query is used to
    match items from the library.
    """
    if session.config["singletons"]:
        # Search for items.
        for item in session.lib.items(session.query):
            singleton_task = SingletonImportTask(None, item)
            for task in singleton_task.handle_created(session):
                yield singleton_task

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


# ---------------------------------- Stages ---------------------------------- #
# Functions that process import tasks, may transform or filter them
# They are chained together in the pipeline e.g. stage2(stage1(task)) -> task


def group_albums(session: ImportSession):
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
        sorted_items: list[library.Item] = sorted(task.items, key=group)
        for _, items in itertools.groupby(sorted_items, group):
            l_items = list(items)
            task = ImportTask(task.toppath, [i.path for i in l_items], l_items)
            tasks += task.handle_created(session)
        tasks.append(SentinelImportTask(task.toppath, task.paths))

        task = pipeline.multiple(tasks)


@pipeline.mutator_stage
def lookup_candidates(session: ImportSession, task: ImportTask):
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
def user_query(session: ImportSession, task: ImportTask):
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
    if task.choice_flag is Action.TRACKS:
        # Set up a little pipeline for dealing with the singletons.
        def emitter(task):
            for item in task.items:
                task = SingletonImportTask(task.toppath, item)
                yield from task.handle_created(session)
            yield SentinelImportTask(task.toppath, task.paths)

        return _extend_pipeline(
            emitter(task),
            lookup_candidates(session),
            user_query(session),
        )

    # As albums: group items by albums and create task for each album
    if task.choice_flag is Action.ALBUMS:
        return _extend_pipeline(
            [task],
            group_albums(session),
            lookup_candidates(session),
            user_query(session),
        )

    _resolve_duplicates(session, task)

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

    _apply_choice(session, task)
    return task


@pipeline.mutator_stage
def import_asis(session: ImportSession, task: ImportTask):
    """Select the `action.ASIS` choice for all tasks.

    This stage replaces the initial_lookup and user_query stages
    when the importer is run without autotagging.
    """
    if task.skip:
        return

    log.info("{}", displayable_path(task.paths))
    task.set_choice(Action.ASIS)
    _apply_choice(session, task)


@pipeline.mutator_stage
def plugin_stage(
    session: ImportSession,
    func: Callable[[ImportSession, ImportTask], None],
    task: ImportTask,
):
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
def log_files(session: ImportSession, task: ImportTask):
    """A coroutine (pipeline stage) to log each file to be imported."""
    if isinstance(task, SingletonImportTask):
        log.info("Singleton: {0}", displayable_path(task.item["path"]))
    elif task.items:
        log.info("Album: {0}", displayable_path(task.paths[0]))
        for item in task.items:
            log.info("  {0}", displayable_path(item["path"]))


# --------------------------------- Consumer --------------------------------- #
# Anything that should be placed last in the pipeline
# In theory every stage could be a consumer, but in practice there are some
# functions which are typically placed last in the pipeline


@pipeline.stage
def manipulate_files(session: ImportSession, task: ImportTask):
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


# ---------------------------- Utility functions ----------------------------- #
# Private functions only used in the stages above


def _apply_choice(
    session: ImportSession,
    task: ImportTask,
):
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


def _resolve_duplicates(
    session: ImportSession,
    task: ImportTask,
):
    """Check if a task conflicts with items or albums already imported
    and ask the session to resolve this.
    """
    if task.choice_flag in (Action.ASIS, Action.APPLY, Action.RETAG):
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
                task.set_choice(Action.SKIP)
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


__all__ = [
    "Action",
    "read_tasks",
    "query_tasks",
    "group_albums",
    "lookup_candidates",
    "user_query",
    "import_asis",
    "plugin_stage",
    "log_files",
    "manipulate_files",
]
