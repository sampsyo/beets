# This file is part of beets.
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


import fnmatch
import os
import tempfile
from collections.abc import Sequence

import beets
from beets.dbcore.query import InQuery
from beets.library import BLOB_TYPE
from beets.util import path_as_posix


class PlaylistQuery(InQuery[bytes]):
    """Matches files listed by a playlist file."""

    @property
    def subvals(self) -> Sequence[BLOB_TYPE]:
        return [BLOB_TYPE(p) for p in self.pattern]

    def __init__(self, _, pattern: str, __):
        config = beets.config["playlist"]

        # Get the full path to the playlist
        playlist_paths = (
            pattern,
            os.path.abspath(
                os.path.join(
                    config["playlist_dir"].as_filename(),
                    f"{pattern}.m3u",
                )
            ),
        )

        paths = []
        for playlist_path in playlist_paths:
            if not fnmatch.fnmatch(playlist_path, "*.[mM]3[uU]"):
                # This is not am M3U playlist, skip this candidate
                continue

            try:
                f = open(beets.util.syspath(playlist_path), mode="rb")
            except OSError:
                continue

            if config["relative_to"].get() == "library":
                relative_to = beets.config["directory"].as_filename()
            elif config["relative_to"].get() == "playlist":
                relative_to = os.path.dirname(playlist_path)
            else:
                relative_to = config["relative_to"].as_filename()
            relative_to = beets.util.bytestring_path(relative_to)

            for line in f:
                if line[0] == "#":
                    # ignore comments, and extm3u extension
                    continue

                paths.append(
                    beets.util.normpath(
                        os.path.join(relative_to, line.rstrip())
                    )
                )
            f.close()
            break
        super().__init__("path", paths)


class PlaylistPlugin(beets.plugins.BeetsPlugin):
    item_queries = {"playlist": PlaylistQuery}

    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "auto": False,
                "playlist_dir": ".",
                "relative_to": "library",
                "forward_slash": False,
            }
        )

        self.playlist_dir = self.config["playlist_dir"].as_filename()
        self.changes = {}

        if self.config["relative_to"].get() == "library":
            self.relative_to = beets.util.bytestring_path(
                beets.config["directory"].as_filename()
            )
        elif self.config["relative_to"].get() != "playlist":
            self.relative_to = beets.util.bytestring_path(
                self.config["relative_to"].as_filename()
            )
        else:
            self.relative_to = None

        if self.config["auto"]:
            self.register_listener("item_moved", self.item_moved)
            self.register_listener("item_removed", self.item_removed)
            self.register_listener("cli_exit", self.cli_exit)

    def item_moved(self, item, source, destination):
        self.changes[source] = destination

    def item_removed(self, item):
        if not os.path.exists(beets.util.syspath(item.path)):
            self.changes[item.path] = None

    def cli_exit(self, lib):
        for playlist in self.find_playlists():
            self._log.info(f"Updating playlist: {playlist}")
            base_dir = beets.util.bytestring_path(
                self.relative_to
                if self.relative_to
                else os.path.dirname(playlist)
            )

            try:
                self.update_playlist(playlist, base_dir)
            except beets.util.FilesystemError:
                self._log.error(
                    "Failed to update playlist: {}".format(
                        beets.util.displayable_path(playlist)
                    )
                )

    def find_playlists(self):
        """Find M3U playlists in the playlist directory."""
        try:
            dir_contents = os.listdir(beets.util.syspath(self.playlist_dir))
        except OSError:
            self._log.warning(
                "Unable to open playlist directory {}".format(
                    beets.util.displayable_path(self.playlist_dir)
                )
            )
            return

        for filename in dir_contents:
            if fnmatch.fnmatch(filename, "*.[mM]3[uU]"):
                yield os.path.join(self.playlist_dir, filename)

    def update_playlist(self, filename, base_dir):
        """Find M3U playlists in the specified directory."""
        changes = 0
        deletions = 0

        with tempfile.NamedTemporaryFile(mode="w+b", delete=False) as tempfp:
            new_playlist = tempfp.name
            with open(filename, mode="rb") as fp:
                for line in fp:
                    original_path = line.rstrip(b"\r\n")

                    # Ensure that path from playlist is absolute
                    is_relative = not os.path.isabs(line)
                    if is_relative:
                        lookup = os.path.join(base_dir, original_path)
                    else:
                        lookup = original_path

                    try:
                        new_path = self.changes[beets.util.normpath(lookup)]
                    except KeyError:
                        if self.config["forward_slash"]:
                            line = path_as_posix(line)
                        tempfp.write(line)
                    else:
                        if new_path is None:
                            # Item has been deleted
                            deletions += 1
                            continue

                        changes += 1
                        if is_relative:
                            new_path = os.path.relpath(new_path, base_dir)
                        line = line.replace(original_path, new_path)
                        if self.config["forward_slash"]:
                            line = path_as_posix(line)
                        tempfp.write(line)

        if changes or deletions:
            self._log.info(
                "Updated playlist {} ({} changes, {} deletions)".format(
                    filename, changes, deletions
                )
            )
            beets.util.copy(new_playlist, filename, replace=True)
        beets.util.remove(new_playlist)
