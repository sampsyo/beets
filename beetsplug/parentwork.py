# This file is part of beets.
# Copyright 2017, Dorian Soergel.
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

"""Gets parent work, its disambiguation and id, composer, composer sort name
and work composition date
"""

import musicbrainzngs

from beets import ui
from beets.plugins import BeetsPlugin


def direct_parent_id(mb_workid, work_date=None):
    """Given a Musicbrainz work id, find the id one of the works the work is
    part of and the first composition date it encounters.
    """
    work_info = musicbrainzngs.get_work_by_id(
        mb_workid, includes=["work-rels", "artist-rels"]
    )
    if "artist-relation-list" in work_info["work"] and work_date is None:
        for artist in work_info["work"]["artist-relation-list"]:
            if artist["type"] == "composer":
                if "end" in artist.keys():
                    work_date = artist["end"]

    if "work-relation-list" in work_info["work"]:
        for direct_parent in work_info["work"]["work-relation-list"]:
            if (
                direct_parent["type"] == "parts"
                and direct_parent.get("direction") == "backward"
            ):
                direct_id = direct_parent["work"]["id"]
                return direct_id, work_date
    return None, work_date


def work_parent_id(mb_workid):
    """Find the parent work id and composition date of a work given its id."""
    work_date = None
    while True:
        new_mb_workid, work_date = direct_parent_id(mb_workid, work_date)
        if not new_mb_workid:
            return mb_workid, work_date
        mb_workid = new_mb_workid
    return mb_workid, work_date


def find_parentwork_info(mb_workid):
    """Get the MusicBrainz information dict about a parent work, including
    the artist relations, and the composition date for a work's parent work.
    """
    parent_id, work_date = work_parent_id(mb_workid)
    work_info = musicbrainzngs.get_work_by_id(
        parent_id, includes=["artist-rels"]
    )
    return work_info, work_date


class ParentWorkPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "auto": False,
                "force": False,
            }
        )

        if self.config["auto"]:
            self.import_stages = [self.imported]

    def commands(self):
        def func(lib, opts, args):
            self.config.set_args(opts)
            force_parent = self.config["force"].get(bool)
            write = ui.should_write()

            for item in lib.items(ui.decargs(args)):
                changed = self.find_work(item, force_parent, verbose=True)
                if changed:
                    item.store()
                    if write:
                        item.try_write()

        command = ui.Subcommand(
            "parentwork", help="fetch parent works, composers and dates"
        )

        command.parser.add_option(
            "-f",
            "--force",
            dest="force",
            action="store_true",
            default=None,
            help="re-fetch when parent work is already present",
        )

        command.func = func
        return [command]

    def imported(self, session, task):
        """Import hook for fetching parent works automatically."""
        force_parent = self.config["force"].get(bool)

        for item in task.imported_items():
            self.find_work(item, force_parent, verbose=False)
            item.store()

    def get_info(self, item, work_info):
        """Given the parent work info dict, fetch parent_composer,
        parent_composer_sort, parentwork, parentwork_disambig, mb_workid and
        composer_ids.
        """

        parent_composer = []
        parent_composer_sort = []
        parentwork_info = {}

        composer_exists = False
        if "artist-relation-list" in work_info["work"]:
            for artist in work_info["work"]["artist-relation-list"]:
                if artist["type"] == "composer":
                    composer_exists = True
                    parent_composer.append(artist["artist"]["name"])
                    parent_composer_sort.append(artist["artist"]["sort-name"])
                    if "end" in artist.keys():
                        parentwork_info["parentwork_date"] = artist["end"]

            parentwork_info["parent_composer"] = ", ".join(parent_composer)
            parentwork_info["parent_composer_sort"] = ", ".join(
                parent_composer_sort
            )

        if not composer_exists:
            self._log.debug(
                "no composer for {}; add one at "
                "https://musicbrainz.org/work/{}",
                item,
                work_info["work"]["id"],
            )

        parentwork_info["parentwork"] = work_info["work"]["title"]
        parentwork_info["mb_parentworkid"] = work_info["work"]["id"]

        if "disambiguation" in work_info["work"]:
            parentwork_info["parentwork_disambig"] = work_info["work"][
                "disambiguation"
            ]

        else:
            parentwork_info["parentwork_disambig"] = None

        return parentwork_info

    def find_work(self, item, force, verbose):
        """Finds the parent work of a recording and populates the tags
        accordingly.

        The parent work is found recursively, by finding the direct parent
        repeatedly until there are no more links in the chain. We return the
        final, topmost work in the chain.

        Namely, the tags parentwork, parentwork_disambig, mb_parentworkid,
        parent_composer, parent_composer_sort and work_date are populated.
        """

        if not item.mb_workid:
            self._log.info(
                "No work for {}, \
add one at https://musicbrainz.org/recording/{}",
                item,
                item.mb_trackid,
            )
            return

        hasparent = hasattr(item, "parentwork")
        work_changed = True
        if hasattr(item, "parentwork_workid_current"):
            work_changed = item.parentwork_workid_current != item.mb_workid
        if force or not hasparent or work_changed:
            try:
                work_info, work_date = find_parentwork_info(item.mb_workid)
            except musicbrainzngs.musicbrainz.WebServiceError as e:
                self._log.debug("error fetching work: {}", e)
                return
            parent_info = self.get_info(item, work_info)
            parent_info["parentwork_workid_current"] = item.mb_workid
            if "parent_composer" in parent_info:
                self._log.debug(
                    "Work fetched: {} - {}",
                    parent_info["parentwork"],
                    parent_info["parent_composer"],
                )
            else:
                self._log.debug(
                    "Work fetched: {} - no parent composer",
                    parent_info["parentwork"],
                )

        elif hasparent:
            self._log.debug("{}: Work present, skipping", item)
            return

        # apply all non-null values to the item
        for key, value in parent_info.items():
            if value:
                item[key] = value

        if work_date:
            item["work_date"] = work_date
        if verbose:
            return ui.show_model_changes(
                item,
                fields=[
                    "parentwork",
                    "parentwork_disambig",
                    "mb_parentworkid",
                    "parent_composer",
                    "parent_composer_sort",
                    "work_date",
                    "parentwork_workid_current",
                    "parentwork_date",
                ],
            )
