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

"""Some simple performance benchmarks for beets."""

import cProfile
import timeit

from beets import importer, library, plugins, ui, vfs
from beets.autotag import match
from beets.plugins import BeetsPlugin
from beets.util.functemplate import Template


def aunique_benchmark(lib, prof):
    def _build_tree():
        vfs.libtree(lib)

    # Measure path generation performance with %aunique{} included.
    lib.path_formats = [
        (
            library.PF_KEY_DEFAULT,
            Template("$albumartist/$album%aunique{}/$track $title"),
        ),
    ]
    if prof:
        cProfile.runctx(
            "_build_tree()",
            {},
            {"_build_tree": _build_tree},
            "paths.withaunique.prof",
        )
    else:
        interval = timeit.timeit(_build_tree, number=1)
        print("With %aunique:", interval)

    # And with %aunique replaceed with a "cheap" no-op function.
    lib.path_formats = [
        (
            library.PF_KEY_DEFAULT,
            Template("$albumartist/$album%lower{}/$track $title"),
        ),
    ]
    if prof:
        cProfile.runctx(
            "_build_tree()",
            {},
            {"_build_tree": _build_tree},
            "paths.withoutaunique.prof",
        )
    else:
        interval = timeit.timeit(_build_tree, number=1)
        print("Without %aunique:", interval)


def match_benchmark(lib, prof, query=None, album_id=None):
    # If no album ID is provided, we'll match against a suitably huge
    # album.
    if not album_id:
        album_id = "9c5c043e-bc69-4edb-81a4-1aaf9c81e6dc"

    # Get an album from the library to use as the source for the match.
    items = lib.albums(query).get().items()

    # Ensure fingerprinting is invoked (if enabled).
    plugins.send(
        "import_task_start",
        task=importer.ImportTask(None, None, items),
        session=importer.ImportSession(lib, None, None, None),
    )

    # Run the match.
    def _run_match():
        match.tag_album(items, search_ids=[album_id])

    if prof:
        cProfile.runctx(
            "_run_match()", {}, {"_run_match": _run_match}, "match.prof"
        )
    else:
        interval = timeit.timeit(_run_match, number=1)
        print("match duration:", interval)


class BenchmarkPlugin(BeetsPlugin):
    """A plugin for performing some simple performance benchmarks."""

    def commands(self):
        aunique_bench_cmd = ui.Subcommand(
            "bench_aunique", help="benchmark for %aunique{}"
        )
        aunique_bench_cmd.parser.add_option(
            "-p",
            "--profile",
            action="store_true",
            default=False,
            help="performance profiling",
        )
        aunique_bench_cmd.func = lambda lib, opts, args: aunique_benchmark(
            lib, opts.profile
        )

        match_bench_cmd = ui.Subcommand(
            "bench_match", help="benchmark for track matching"
        )
        match_bench_cmd.parser.add_option(
            "-p",
            "--profile",
            action="store_true",
            default=False,
            help="performance profiling",
        )
        match_bench_cmd.parser.add_option(
            "-i", "--id", default=None, help="album ID to match against"
        )
        match_bench_cmd.func = lambda lib, opts, args: match_benchmark(
            lib, opts.profile, ui.decargs(args), opts.id
        )

        return [aunique_bench_cmd, match_bench_cmd]
