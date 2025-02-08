# This file is part of beets.
# Copyright 2019, Joris Jensen
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


import random
import string
from hashlib import md5
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests

from beets.dbcore import AndQuery
from beets.dbcore.query import MatchQuery
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

__author__ = "https://github.com/MrNuggelz"


def filter_to_be_removed(items, keys):
    if len(items) > len(keys):
        dont_remove = []
        for artist, album, title in keys:
            for item in items:
                if (
                    artist == item["artist"]
                    and album == item["album"]
                    and title == item["title"]
                ):
                    dont_remove.append(item)
        return [item for item in items if item not in dont_remove]
    else:

        def to_be_removed(item):
            for artist, album, title in keys:
                if (
                    artist == item["artist"]
                    and album == item["album"]
                    and title == item["title"]
                ):
                    return False
            return True

        return [item for item in items if to_be_removed(item)]


class SubsonicPlaylistPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "delete": False,
                "playlist_ids": [],
                "playlist_names": [],
                "username": "",
                "password": "",
            }
        )
        self.config["password"].redact = True

    def update_tags(self, playlist_dict, lib):
        with lib.transaction():
            for query, playlist_tag in playlist_dict.items():
                query = AndQuery(
                    [
                        MatchQuery("artist", query[0]),
                        MatchQuery("album", query[1]),
                        MatchQuery("title", query[2]),
                    ]
                )
                items = lib.items(query)
                if not items:
                    self._log.warn(
                        "{} | track not found ({})", playlist_tag, query
                    )
                    continue
                for item in items:
                    item.subsonic_playlist = playlist_tag
                    item.try_sync(write=True, move=False)

    def get_playlist(self, playlist_id):
        xml = self.send("getPlaylist", {"id": playlist_id}).text
        playlist = ElementTree.fromstring(xml)[0]
        if playlist.attrib.get("code", "200") != "200":
            alt_error = "error getting playlist, but no error message found"
            self._log.warn(playlist.attrib.get("message", alt_error))
            return

        name = playlist.attrib.get("name", "undefined")
        tracks = [
            (t.attrib["artist"], t.attrib["album"], t.attrib["title"])
            for t in playlist
        ]
        return name, tracks

    def commands(self):
        def build_playlist(lib, opts, args):
            self.config.set_args(opts)
            ids = self.config["playlist_ids"].as_str_seq()
            if self.config["playlist_names"].as_str_seq():
                playlists = ElementTree.fromstring(
                    self.send("getPlaylists").text
                )[0]
                if playlists.attrib.get("code", "200") != "200":
                    alt_error = (
                        "error getting playlists," " but no error message found"
                    )
                    self._log.warn(playlists.attrib.get("message", alt_error))
                    return
                for name in self.config["playlist_names"].as_str_seq():
                    for playlist in playlists:
                        if name == playlist.attrib["name"]:
                            ids.append(playlist.attrib["id"])

            playlist_dict = self.get_playlists(ids)

            # delete old tags
            if self.config["delete"]:
                existing = list(lib.items('subsonic_playlist:";"'))
                to_be_removed = filter_to_be_removed(
                    existing, playlist_dict.keys()
                )
                for item in to_be_removed:
                    item["subsonic_playlist"] = ""
                    with lib.transaction():
                        item.try_sync(write=True, move=False)

            self.update_tags(playlist_dict, lib)

        subsonicplaylist_cmds = Subcommand(
            "subsonicplaylist", help="import a subsonic playlist"
        )
        subsonicplaylist_cmds.parser.add_option(
            "-d",
            "--delete",
            action="store_true",
            help="delete tag from items not in any playlist anymore",
        )
        subsonicplaylist_cmds.func = build_playlist
        return [subsonicplaylist_cmds]

    def generate_token(self):
        salt = "".join(random.choices(string.ascii_lowercase + string.digits))
        return (
            md5((self.config["password"].get() + salt).encode()).hexdigest(),
            salt,
        )

    def send(self, endpoint, params=None):
        if params is None:
            params = {}
        a, b = self.generate_token()
        params["u"] = self.config["username"]
        params["t"] = a
        params["s"] = b
        params["v"] = "1.12.0"
        params["c"] = "beets"
        resp = requests.get(
            "{}/rest/{}?{}".format(
                self.config["base_url"].get(), endpoint, urlencode(params)
            ),
            timeout=10,
        )
        return resp

    def get_playlists(self, ids):
        output = {}
        for playlist_id in ids:
            name, tracks = self.get_playlist(playlist_id)
            for track in tracks:
                if track not in output:
                    output[track] = ";"
                output[track] += name + ";"
        return output
