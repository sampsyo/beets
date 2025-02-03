# This file is part of beets.
# Copyright 2016, David Hamp-Gonsalves
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

"""Send the results of a query to the configured music player as a playlist."""

import shlex
import subprocess
from os.path import relpath

from beets import config, ui, util
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand
from beets.ui.commands import PromptChoice
from beets.util import get_temp_filename

# Indicate where arguments should be inserted into the command string.
# If this is missing, they're placed at the end.
ARGS_MARKER = "$args"

# Indicate where the playlist file (with absolute path) should be inserted into
# the command string. If this is missing, its placed at the end, but before
# arguments.
PLS_MARKER = '$playlist'


def play(
    command_str,
    selection,
    paths,
    open_args,
    log,
    item_type="track",
    keep_open=False,
):
    """Play items in paths with command_str and optional arguments. If
    keep_open, return to beets, otherwise exit once command runs.
    """
    # Print number of tracks or albums to be played, log command to be run.
    item_type += "s" if len(selection) > 1 else ""
    ui.print_("Playing {} {}.".format(len(selection), item_type))
    log.debug("executing command: {} {!r}", command_str, open_args)

    try:
        if keep_open:
            command = shlex.split(command_str)
            command = command + open_args
            subprocess.call(command)
        else:
            util.interactive_open(open_args, command_str)
    except OSError as exc:
        raise ui.UserError(f"Could not play the query: {exc}")


class PlayPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        config["play"].add(
            {
                "command": None,
                "use_folders": False,
                "relative_to": None,
                "raw": False,
                "warning_threshold": 100,
                "bom": False,
            }
        )

        self.register_listener(
            "before_choose_candidate", self.before_choose_candidate_listener
        )

    def commands(self):
        play_command = Subcommand(
            "play", help="send music to a player as a playlist"
        )
        play_command.parser.add_album_option()
        play_command.parser.add_option(
            "-A",
            "--args",
            action="store",
            help="add additional arguments to the command",
        )
        play_command.parser.add_option(
            "-y",
            "--yes",
            action="store_true",
            help="skip the warning threshold",
        )
        play_command.func = self._play_command
        return [play_command]

    def _play_command(self, lib, opts, args):
        """The CLI command function for `beet play`. Create a list of paths
        from query, determine if tracks or albums are to be played.
        """
        use_folders = config["play"]["use_folders"].get(bool)
        relative_to = config["play"]["relative_to"].get()
        if relative_to:
            relative_to = util.normpath(relative_to)
        # Perform search by album and add folders rather than tracks to
        # playlist.
        if opts.album:
            selection = lib.albums(ui.decargs(args))
            paths = []

            sort = lib.get_default_album_sort()
            for album in selection:
                if use_folders:
                    paths.append(album.item_dir())
                else:
                    paths.extend(item.path for item in sort.sort(album.items()))
            item_type = "album"

        # Perform item query and add tracks to playlist.
        else:
            selection = lib.items(ui.decargs(args))
            paths = [item.path for item in selection]
            item_type = "track"

        if relative_to:
            paths = [relpath(path, relative_to) for path in paths]

        if not selection:
            ui.print_(ui.colorize("text_warning", f"No {item_type} to play."))
            return

        open_args = self._playlist_or_paths(paths)
        command_str = self._command_str(opts.args)

        if PLS_MARKER in command_str:
            if not config['play']['raw']:
                command_str = command_str.replace(PLS_MARKER,
                                                  ''.join(open_args))
                self._log.debug('command altered by PLS_MARKER to: {}',
                                command_str)
                open_args = []
            else:
                command_str = command_str.replace(PLS_MARKER, " ")

        # Check if the selection exceeds configured threshold. If True,
        # cancel, otherwise proceed with play command.
        if opts.yes or not self._exceeds_threshold(
            selection, command_str, open_args, item_type
        ):
            play(command_str, selection, paths, open_args, self._log, item_type)

    def _command_str(self, args=None):
        """Create a command string from the config command and optional args."""
        command_str = config["play"]["command"].get()
        if not command_str:
            return util.open_anything()
        # Add optional arguments to the player command.
        if args:
            if ARGS_MARKER in command_str:
                return command_str.replace(ARGS_MARKER, args)
            else:
                return f"{command_str} {args}"
        else:
            # Don't include the marker in the command.
            return command_str.replace(" " + ARGS_MARKER, "")

    def _playlist_or_paths(self, paths):
        """Return either the raw paths of items or a playlist of the items."""
        if config["play"]["raw"]:
            return paths
        else:
            return [shlex.quote(self._create_tmp_playlist(paths))]

    def _exceeds_threshold(
        self, selection, command_str, open_args, item_type="track"
    ):
        """Prompt user whether to abort if playlist exceeds threshold. If
        True, cancel playback. If False, execute play command.
        """
        warning_threshold = config["play"]["warning_threshold"].get(int)

        # Warn user before playing any huge playlists.
        if warning_threshold and len(selection) > warning_threshold:
            if len(selection) > 1:
                item_type += "s"

            ui.print_(
                ui.colorize(
                    "text_warning",
                    "You are about to queue {} {}.".format(
                        len(selection), item_type
                    ),
                )
            )

            if ui.input_options(("Continue", "Abort")) == "a":
                return True

        return False

    def _create_tmp_playlist(self, paths_list):
        """Create a temporary .m3u file. Return the filename."""
        utf8_bom = config["play"]["bom"].get(bool)
        filename = get_temp_filename(__name__, suffix=".m3u")
        with open(filename, "wb") as m3u:
            if utf8_bom:
                m3u.write(b"\xef\xbb\xbf")

            for item in paths_list:
                m3u.write(item + b"\n")

        return filename

    def before_choose_candidate_listener(self, session, task):
        """Append a "Play" choice to the interactive importer prompt."""
        return [PromptChoice("y", "plaY", self.importer_play)]

    def importer_play(self, session, task):
        """Get items from current import task and send to play function."""
        selection = task.items
        paths = [item.path for item in selection]

        open_args = self._playlist_or_paths(paths)
        command_str = self._command_str()

        if not self._exceeds_threshold(selection, command_str, open_args):
            play(
                command_str,
                selection,
                paths,
                open_args,
                self._log,
                keep_open=True,
            )
