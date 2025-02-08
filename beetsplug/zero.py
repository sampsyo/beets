# This file is part of beets.
# Copyright 2016, Blemjhoo Tezoulbr <baobab@heresiarch.info>.
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

"""Clears tag fields in media files."""

import re

import confuse
from mediafile import MediaFile

from beets.importer import action
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, decargs, input_yn

__author__ = "baobab@heresiarch.info"


class ZeroPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.register_listener("write", self.write_event)
        self.register_listener(
            "import_task_choice", self.import_task_choice_event
        )

        self.config.add(
            {
                "auto": True,
                "fields": [],
                "keep_fields": [],
                "update_database": False,
            }
        )

        self.fields_to_progs = {}
        self.warned = False

        """Read the bulk of the config into `self.fields_to_progs`.
        After construction, `fields_to_progs` contains all the fields that
        should be zeroed as keys and maps each of those to a list of compiled
        regexes (progs) as values.
        A field is zeroed if its value matches one of the associated progs. If
        progs is empty, then the associated field is always zeroed.
        """
        if self.config["fields"] and self.config["keep_fields"]:
            self._log.warning("cannot blacklist and whitelist at the same time")
        # Blacklist mode.
        elif self.config["fields"]:
            for field in self.config["fields"].as_str_seq():
                self._set_pattern(field)
        # Whitelist mode.
        elif self.config["keep_fields"]:
            for field in MediaFile.fields():
                if (
                    field not in self.config["keep_fields"].as_str_seq()
                    and
                    # These fields should always be preserved.
                    field not in ("id", "path", "album_id")
                ):
                    self._set_pattern(field)

    def commands(self):
        zero_command = Subcommand("zero", help="set fields to null")

        def zero_fields(lib, opts, args):
            if not decargs(args) and not input_yn(
                "Remove fields for all items? (Y/n)", True
            ):
                return
            for item in lib.items(decargs(args)):
                self.process_item(item)

        zero_command.func = zero_fields
        return [zero_command]

    def _set_pattern(self, field):
        """Populate `self.fields_to_progs` for a given field.
        Do some sanity checks then compile the regexes.
        """
        if field not in MediaFile.fields():
            self._log.error("invalid field: {0}", field)
        elif field in ("id", "path", "album_id"):
            self._log.warning(
                "field '{0}' ignored, zeroing " "it would be dangerous", field
            )
        else:
            try:
                for pattern in self.config[field].as_str_seq():
                    prog = re.compile(pattern, re.IGNORECASE)
                    self.fields_to_progs.setdefault(field, []).append(prog)
            except confuse.NotFoundError:
                # Matches everything
                self.fields_to_progs[field] = []

    def import_task_choice_event(self, session, task):
        if task.choice_flag == action.ASIS and not self.warned:
            self._log.warning('cannot zero in "as-is" mode')
            self.warned = True
        # TODO request write in as-is mode

    def write_event(self, item, path, tags):
        if self.config["auto"]:
            self.set_fields(item, tags)

    def set_fields(self, item, tags):
        """Set values in `tags` to `None` if the field is in
        `self.fields_to_progs` and any of the corresponding `progs` matches the
        field value.
        Also update the `item` itself if `update_database` is set in the
        config.
        """
        fields_set = False

        if not self.fields_to_progs:
            self._log.warning("no fields, nothing to do")
            return False

        for field, progs in self.fields_to_progs.items():
            if field in tags:
                value = tags[field]
                match = _match_progs(tags[field], progs)
            else:
                value = ""
                match = not progs

            if match:
                fields_set = True
                self._log.debug("{0}: {1} -> None", field, value)
                tags[field] = None
                if self.config["update_database"]:
                    item[field] = None

        return fields_set

    def process_item(self, item):
        tags = dict(item)

        if self.set_fields(item, tags):
            item.write(tags=tags)
            if self.config["update_database"]:
                item.store(fields=tags)


def _match_progs(value, progs):
    """Check if `value` (as string) is matching any of the compiled regexes in
    the `progs` list.
    """
    if not progs:
        return True
    for prog in progs:
        if prog.search(str(value)):
            return True
    return False
