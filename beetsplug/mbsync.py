# This file is part of beets.
# Copyright 2016, Jakob Schnitzer.
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

"""Update library's tags using MusicBrainz."""

import re
from collections import defaultdict

from beets import autotag, library, ui, util
from beets.autotag import hooks
from beets.plugins import BeetsPlugin, apply_item_changes

MBID_REGEX = r"(\d|\w){8}-(\d|\w){4}-(\d|\w){4}-(\d|\w){4}-(\d|\w){12}"


class MBSyncPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

    def commands(self):
        cmd = ui.Subcommand("mbsync", help="update metadata from musicbrainz")
        cmd.parser.add_option(
            "-p",
            "--pretend",
            action="store_true",
            help="show all changes but do nothing",
        )
        cmd.parser.add_option(
            "-m",
            "--move",
            action="store_true",
            dest="move",
            help="move files in the library directory",
        )
        cmd.parser.add_option(
            "-M",
            "--nomove",
            action="store_false",
            dest="move",
            help="don't move files in library",
        )
        cmd.parser.add_option(
            "-W",
            "--nowrite",
            action="store_false",
            default=None,
            dest="write",
            help="don't write updated metadata to files",
        )
        cmd.parser.add_option(
            "-t",
            "--timid",
            dest="timid",
            action="store_true",
            help="always confirm all actions",
        )
        cmd.parser.add_format_option()
        cmd.func = self.func
        return [cmd]

    def func(self, lib, opts, args):
        """Command handler for the mbsync function."""
        move = ui.should_move(opts.move)
        pretend = opts.pretend
        timid = opts.timid
        write = ui.should_write(opts.write)
        query = ui.decargs(args)

        self.singletons(lib, query, move, pretend, write, timid)
        self.albums(lib, query, move, pretend, write, timid)

    def singletons(self, lib, query, move, pretend, write, timid):
        """Retrieve and apply info from the autotagger for items matched by
        query.
        """
        for item in lib.items(query + ["singleton:true"]):
            item_formatted = format(item)
            if not item.mb_trackid:
                self._log.info(
                    "Skipping singleton with no mb_trackid: {0}", item_formatted
                )
                continue

            # Do we have a valid MusicBrainz track ID?
            if not re.match(MBID_REGEX, item.mb_trackid):
                self._log.info(
                    "Skipping singleton with invalid mb_trackid:" + " {0}",
                    item_formatted,
                )
                continue

            # Get the MusicBrainz recording info.
            track_info = hooks.track_for_mbid(item.mb_trackid)
            if not track_info:
                self._log.info(
                    "Recording ID not found: {0} for track {0}",
                    item.mb_trackid,
                    item_formatted,
                )
                continue

            item_old = item.copy()
            autotag.apply_item_metadata(item, track_info)
            if not ui.show_model_changes(item, item_old):
                continue

            if timid:
                print()
                choice = ui.input_options(("Apply", "cancel", "skip"))
                if choice == "a":  # Apply.
                    pass
                elif choice == "c":  # Cancel.
                    return
                elif choice == "s":  # Skip.
                    continue

            # Apply.
            with lib.transaction():
                apply_item_changes(lib, item, move, pretend, write)

    def albums(self, lib, query, move, pretend, write, timid):
        """Retrieve and apply info from the autotagger for albums matched by
        query and their items.
        """
        # Process matching albums.
        for a in lib.albums(query):
            album_formatted = format(a)
            if not a.mb_albumid:
                self._log.info(
                    "Skipping album with no mb_albumid: {0}", album_formatted
                )
                continue

            items = list(a.items())

            # Do we have a valid MusicBrainz album ID?
            if not re.match(MBID_REGEX, a.mb_albumid):
                self._log.info(
                    "Skipping album with invalid mb_albumid: {0}",
                    album_formatted,
                )
                continue

            # Get the MusicBrainz album information.
            album_info = hooks.album_for_mbid(a.mb_albumid)
            if not album_info:
                self._log.info(
                    "Release ID {0} not found for album {1}",
                    a.mb_albumid,
                    album_formatted,
                )
                continue

            # Map release track and recording MBIDs to their information.
            # Recordings can appear multiple times on a release, so each MBID
            # maps to a list of TrackInfo objects.
            releasetrack_index = {}
            track_index = defaultdict(list)
            for track_info in album_info.tracks:
                releasetrack_index[track_info.release_track_id] = track_info
                track_index[track_info.track_id].append(track_info)

            # Construct a track mapping according to MBIDs (release track MBIDs
            # first, if available, and recording MBIDs otherwise). This should
            # work for albums that have missing or extra tracks.
            mapping = {}
            for item in items:
                if (
                    item.mb_releasetrackid
                    and item.mb_releasetrackid in releasetrack_index
                ):
                    mapping[item] = releasetrack_index[item.mb_releasetrackid]
                else:
                    candidates = track_index[item.mb_trackid]
                    if len(candidates) == 1:
                        mapping[item] = candidates[0]
                    else:
                        # If there are multiple copies of a recording, they are
                        # disambiguated using their disc and track number.
                        for c in candidates:
                            if (
                                c.medium_index == item.track
                                and c.medium == item.disc
                            ):
                                mapping[item] = c
                                break

            # Gather changes.
            changed = []
            items_old = [item.copy() for item in items]
            autotag.apply_metadata(album_info, mapping)
            for item, item_old in zip(items, items_old):
                if ui.show_model_changes(item, item_old):
                    changed.append(item)

            if len(changed) == 0:
                continue

            if timid:
                print()
                choice = ui.input_options(("Apply", "cancel", "skip"))
                if choice == "a":  # Apply.
                    pass
                elif choice == "c":  # Cancel.
                    return
                elif choice == "s":  # Skip.
                    continue

            # Apply.
            self._log.debug("applying changes to {}", album_formatted)
            with lib.transaction():
                for item in changed:
                    apply_item_changes(lib, item, move, pretend, write)

                if not pretend:
                    # Update album structure to reflect an item in it.
                    for key in library.Album.item_keys:
                        a[key] = changed[0][key]
                    a.store()

                    # Move album art (and any inconsistent items).
                    if move and lib.directory in util.ancestry(items[0].path):
                        self._log.debug("moving album {0}", album_formatted)
                        a.move()
