"""Adds a `source_path` attribute to imported albums indicating from what path
the album was imported from. Also suggests removing that source path in case
you've removed the album from the library.

"""

import os
from shutil import rmtree

from beets import library
from beets.plugins import BeetsPlugin
from beets.ui import colorize as colorize_text
from beets.ui import input_options
from beets.util import syspath


class ImportHistPlugin(BeetsPlugin):
    """Main plugin class."""

    def __init__(self):
        """Initialize the plugin and read configuration."""
        super(ImportHistPlugin, self).__init__()
        self.config.add(
            {
                "suggest_removal": False,
            }
        )
        self.import_stages = [self.import_stage]
        self.register_listener("item_removed", self.suggest_removal)
        # In order to stop suggestions for certain albums in
        # self.suggest_removal, we initialize an empty set of `mb_albumid`s
        # that these will be ignored in future runs of the suggest_removal.
        self.stop_suggestions_for_albums = set()
        # In case 'import --library' is used, we will get both the import
        # event triggered, and the item_removed event triggered because
        # that's how 'import --library' works. Unfortuneatly, but
        # naturally, the item_removed event is triggered first, and we need
        # to prevent suggesting to remove the source_path because that has
        # nothing to do with the import. Hence we use this event, and use
        # the self.stop_suggestions_for_albums array
        self.register_listener(
            "import_task_choice", self.prevent_suggest_removal
        )

    def prevent_suggest_removal(self, session, task):
        for item in task.imported_items():
            if "mb_albumid" in item:
                self.stop_suggestions_for_albums.add(item.mb_albumid)

    def import_stage(self, _, task):
        """Event handler for albums import finished."""
        for item in task.imported_items():
            # If import --library is used, this check prevents changing the
            # source_path attribute to the path from the music library -
            # something which would make this attribute completely useless.
            if "source_path" not in item:
                item["source_path"] = item.path
                item.try_sync(write=True, move=False)
            else:
                self._log.info(
                    "Preserving source_path of reimported item {}", item.id
                )

    def suggest_removal(self, item):
        """Prompts the user to delete the original path the item was imported from."""
        if not self.config["suggest_removal"]:
            return
        if "source_path" not in item:
            self._log.warning(
                "Item without source_path (probably imported before plugin "
                "usage): {}",
                item.path.decode("utf-8"),
            )
            return
        if item.mb_albumid in self.stop_suggestions_for_albums:
            return
        if not os.path.isfile(syspath(item.source_path)):
            self._log.warning(
                "Item with source_path that doesn't exist: {}",
                item.source_path.decode("utf-8"),
            )
            return
        source_dir = os.path.dirname(syspath(item.source_path))
        if not (
            os.access(syspath(item.source_path), os.W_OK)
            and os.access(source_dir, os.W_OK | os.X_OK)
        ):
            self._log.warning(
                "Item with source_path not deletable: {}",
                item.source_path.decode("utf-8"),
            )
            return
        # We ask the user whether they'd like to delete the item's source
        # directory
        print(
            "The item:\n{path}\nis originated from:\n{source}\n"
            "What would you like to do?".format(
                path=colorize_text("text_warning", item.path.decode("utf-8")),
                source=colorize_text(
                    "text_warning", item.source_path.decode("utf-8")
                ),
            )
        )
        resp = input_options(
            [
                "Delete the item's source",
                "Recursively delete the source's directory",
                "do Nothing",
                "do nothing and Stop suggesting to delete items from this album",
            ],
            require=True,
        )
        if resp == "d":
            self._log.info(
                "Deleting the item's source file: {}", item.source_path
            )
            os.remove(syspath(item.source_path))
        elif resp == "r":
            self._log.info(
                "Searching for other items with a source_path attr containing: {}",
                source_dir,
            )
            source_dir_query = library.PathQuery(
                "source_path",
                source_dir,
                # The "source_path" attribute may not be present in all
                # items of the library, so we avoid errors with this:
                fast=False,
            )
            print("Doing so will delete the following items' sources as well:")
            for searched_item in item._db.items(source_dir_query):
                print(
                    colorize_text(
                        "text_warning",
                        searched_item["path"].decode("utf-8"),
                    )
                )
            print("Would you like to continue?")
            continue_resp = input_options(
                ["Yes", "delete None", "delete just the File"],
                require=False,  # Yes is the a default
            )
            if continue_resp == "y":
                self._log.info(
                    "Deleting the item's source directory: {}", source_dir
                )
                rmtree(source_dir)
            elif continue_resp == "n":
                self._log.info("doing nothing - aborting hook function")
                return
            elif continue_resp == "f":
                self._log.info(
                    "removing just the item's original source: {}",
                    item.source_path,
                )
                os.remove(item.source_path)
        elif resp == "s":
            self.stop_suggestions_for_albums.add(item.mb_albumid)
        else:
            self._log.info("Doing nothing")
