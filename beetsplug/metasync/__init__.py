# This file is part of beets.
# Copyright 2016, Heinz Wiesinger.
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

"""Synchronize information from music player libraries"""

from abc import ABCMeta, abstractmethod
from importlib import import_module

from confuse import ConfigValueError

from beets import ui
from beets.plugins import BeetsPlugin

METASYNC_MODULE = "beetsplug.metasync"

# Dictionary to map the MODULE and the CLASS NAME of meta sources
SOURCES = {
    "amarok": "Amarok",
    "itunes": "Itunes",
}


class MetaSource(metaclass=ABCMeta):
    def __init__(self, config, log):
        self.item_types = {}
        self.config = config
        self._log = log

    @abstractmethod
    def sync_from_source(self, item):
        pass


def load_meta_sources():
    """Returns a dictionary of all the MetaSources
    E.g., {'itunes': Itunes} with isinstance(Itunes, MetaSource) true
    """
    meta_sources = {}

    for module_path, class_name in SOURCES.items():
        module = import_module(METASYNC_MODULE + "." + module_path)
        meta_sources[class_name.lower()] = getattr(module, class_name)

    return meta_sources


META_SOURCES = load_meta_sources()


def load_item_types():
    """Returns a dictionary containing the item_types of all the MetaSources"""
    item_types = {}
    for meta_source in META_SOURCES.values():
        item_types.update(meta_source.item_types)
    return item_types


class MetaSyncPlugin(BeetsPlugin):
    item_types = load_item_types()

    def __init__(self):
        super().__init__()

    def commands(self):
        cmd = ui.Subcommand(
            "metasync", help="update metadata from music player libraries"
        )
        cmd.parser.add_option(
            "-p",
            "--pretend",
            action="store_true",
            help="show all changes but do nothing",
        )
        cmd.parser.add_option(
            "-s",
            "--source",
            default=[],
            action="append",
            dest="sources",
            help="comma-separated list of sources to sync",
        )
        cmd.parser.add_format_option()
        cmd.func = self.func
        return [cmd]

    def func(self, lib, opts, args):
        """Command handler for the metasync function."""
        pretend = opts.pretend
        query = ui.decargs(args)

        sources = []
        for source in opts.sources:
            sources.extend(source.split(","))

        sources = sources or self.config["source"].as_str_seq()

        meta_source_instances = {}
        items = lib.items(query)

        # Avoid needlessly instantiating meta sources (can be expensive)
        if not items:
            self._log.info("No items found matching query")
            return

        # Instantiate the meta sources
        for player in sources:
            try:
                cls = META_SOURCES[player]
            except KeyError:
                self._log.error("Unknown metadata source '{}'", player)

            try:
                meta_source_instances[player] = cls(self.config, self._log)
            except (ImportError, ConfigValueError) as e:
                self._log.error(
                    "Failed to instantiate metadata source {!r}: {}", player, e
                )

        # Avoid needlessly iterating over items
        if not meta_source_instances:
            self._log.error("No valid metadata sources found")
            return

        # Sync the items with all of the meta sources
        for item in items:
            for meta_source in meta_source_instances.values():
                meta_source.sync_from_source(item)

            changed = ui.show_model_changes(item)

            if changed and not pretend:
                item.store()
