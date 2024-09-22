# This file is part of beets.
# Copyright (c) 2011, Jeffrey Aylesworth <mail@jeffrey.red>
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


import re

import musicbrainzngs

from beets import config, ui
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

SUBMISSION_CHUNK_SIZE = 200
FETCH_CHUNK_SIZE = 100
UUID_REGEX = r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$"


def mb_call(func, *args, **kwargs):
    """Call a MusicBrainz API function and catch exceptions."""
    try:
        return func(*args, **kwargs)
    except musicbrainzngs.AuthenticationError:
        raise ui.UserError("authentication with MusicBrainz failed")
    except (musicbrainzngs.ResponseError, musicbrainzngs.NetworkError) as exc:
        raise ui.UserError(f"MusicBrainz API error: {exc}")
    except musicbrainzngs.UsageError:
        raise ui.UserError("MusicBrainz credentials missing")


def submit_albums(collection_id, release_ids):
    """Add all of the release IDs to the indicated collection. Multiple
    requests are made if there are many release IDs to submit.
    """
    for i in range(0, len(release_ids), SUBMISSION_CHUNK_SIZE):
        chunk = release_ids[i : i + SUBMISSION_CHUNK_SIZE]
        mb_call(musicbrainzngs.add_releases_to_collection, collection_id, chunk)


class MusicBrainzCollectionPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        config["musicbrainz"]["pass"].redact = True
        musicbrainzngs.auth(
            config["musicbrainz"]["user"].as_str(),
            config["musicbrainz"]["pass"].as_str(),
        )
        self.config.add(
            {
                "auto": False,
                "collection": "",
                "remove": False,
            }
        )
        if self.config["auto"]:
            self.import_stages = [self.imported]

    def _get_collection(self):
        collections = mb_call(musicbrainzngs.get_collections)
        if not collections["collection-list"]:
            raise ui.UserError("no collections exist for user")

        # Get all collection IDs, avoiding event collections
        collection_ids = [x["id"] for x in collections["collection-list"]]
        if not collection_ids:
            raise ui.UserError("No collection found.")

        # Check that the collection exists so we can present a nice error
        collection = self.config["collection"].as_str()
        if collection:
            if collection not in collection_ids:
                raise ui.UserError(f"invalid collection ID: {collection}")
            return collection

        # No specified collection. Just return the first collection ID
        return collection_ids[0]

    def _get_albums_in_collection(self, id):
        def _fetch(offset):
            res = mb_call(
                musicbrainzngs.get_releases_in_collection,
                id,
                limit=FETCH_CHUNK_SIZE,
                offset=offset,
            )["collection"]
            return [x["id"] for x in res["release-list"]], res["release-count"]

        offset = 0
        albums_in_collection, release_count = _fetch(offset)
        for i in range(0, release_count, FETCH_CHUNK_SIZE):
            albums_in_collection += _fetch(offset)[0]
            offset += FETCH_CHUNK_SIZE

        return albums_in_collection

    def commands(self):
        mbupdate = Subcommand("mbupdate", help="Update MusicBrainz collection")
        mbupdate.parser.add_option(
            "-r",
            "--remove",
            action="store_true",
            default=None,
            dest="remove",
            help="Remove albums not in beets library",
        )
        mbupdate.func = self.update_collection
        return [mbupdate]

    def remove_missing(self, collection_id, lib_albums):
        lib_ids = {x.mb_albumid for x in lib_albums}
        albums_in_collection = self._get_albums_in_collection(collection_id)
        remove_me = list(set(albums_in_collection) - lib_ids)
        for i in range(0, len(remove_me), FETCH_CHUNK_SIZE):
            chunk = remove_me[i : i + FETCH_CHUNK_SIZE]
            mb_call(
                musicbrainzngs.remove_releases_from_collection,
                collection_id,
                chunk,
            )

    def update_collection(self, lib, opts, args):
        self.config.set_args(opts)
        remove_missing = self.config["remove"].get(bool)
        self.update_album_list(lib, lib.albums(), remove_missing)

    def imported(self, session, task):
        """Add each imported album to the collection."""
        if task.is_album:
            self.update_album_list(session.lib, [task.album])

    def update_album_list(self, lib, album_list, remove_missing=False):
        """Update the MusicBrainz collection from a list of Beets albums"""
        collection_id = self._get_collection()

        # Get a list of all the album IDs.
        album_ids = []
        for album in album_list:
            aid = album.mb_albumid
            if aid:
                if re.match(UUID_REGEX, aid):
                    album_ids.append(aid)
                else:
                    self._log.info("skipping invalid MBID: {0}", aid)

        # Submit to MusicBrainz.
        self._log.info("Updating MusicBrainz collection {0}...", collection_id)
        submit_albums(collection_id, album_ids)
        if remove_missing:
            self.remove_missing(collection_id, lib.albums())
        self._log.info("...MusicBrainz collection updated.")
