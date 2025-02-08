# This file is part of beets.
# Copyright 2016, Dang Mai <contact@dangmai.net>.
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

"""Generates smart playlists based on beets queries."""

import json
import os
from urllib.request import pathname2url

from beets import ui
from beets.dbcore import OrQuery
from beets.dbcore.query import MultipleSort, ParsingError
from beets.library import Album, Item, parse_query_string
from beets.plugins import BeetsPlugin
from beets.plugins import send as send_event
from beets.util import (
    bytestring_path,
    displayable_path,
    mkdirall,
    normpath,
    path_as_posix,
    sanitize_path,
    syspath,
)


class SmartPlaylistPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "relative_to": None,
                "playlist_dir": ".",
                "auto": True,
                "playlists": [],
                "uri_format": None,
                "fields": [],
                "forward_slash": False,
                "prefix": "",
                "urlencode": False,
                "pretend_paths": False,
                "output": "m3u",
            }
        )

        self.config["prefix"].redact = True  # May contain username/password.
        self._matched_playlists = None
        self._unmatched_playlists = None

        if self.config["auto"]:
            self.register_listener("database_change", self.db_change)

    def commands(self):
        spl_update = ui.Subcommand(
            "splupdate",
            help="update the smart playlists. Playlist names may be "
            "passed as arguments.",
        )
        spl_update.parser.add_option(
            "-p",
            "--pretend",
            action="store_true",
            help="display query results but don't write playlist files.",
        )
        spl_update.parser.add_option(
            "--pretend-paths",
            action="store_true",
            dest="pretend_paths",
            help="in pretend mode, log the playlist item URIs/paths.",
        )
        spl_update.parser.add_option(
            "-d",
            "--playlist-dir",
            dest="playlist_dir",
            metavar="PATH",
            type="string",
            help="directory to write the generated playlist files to.",
        )
        spl_update.parser.add_option(
            "--relative-to",
            dest="relative_to",
            metavar="PATH",
            type="string",
            help="generate playlist item paths relative to this path.",
        )
        spl_update.parser.add_option(
            "--prefix",
            type="string",
            help="prepend string to every path in the playlist file.",
        )
        spl_update.parser.add_option(
            "--forward-slash",
            action="store_true",
            dest="forward_slash",
            help="force forward slash in paths within playlists.",
        )
        spl_update.parser.add_option(
            "--urlencode",
            action="store_true",
            help="URL-encode all paths.",
        )
        spl_update.parser.add_option(
            "--uri-format",
            dest="uri_format",
            type="string",
            help="playlist item URI template, e.g. http://beets:8337/item/$id/file.",
        )
        spl_update.parser.add_option(
            "--output",
            type="string",
            help="specify the playlist format: m3u|extm3u.",
        )
        spl_update.func = self.update_cmd
        return [spl_update]

    def update_cmd(self, lib, opts, args):
        self.build_queries()
        if args:
            args = set(ui.decargs(args))
            for a in list(args):
                if not a.endswith(".m3u"):
                    args.add(f"{a}.m3u")

            playlists = {
                (name, q, a_q)
                for name, q, a_q in self._unmatched_playlists
                if name in args
            }
            if not playlists:
                raise ui.UserError(
                    "No playlist matching any of {} found".format(
                        [name for name, _, _ in self._unmatched_playlists]
                    )
                )

            self._matched_playlists = playlists
            self._unmatched_playlists -= playlists
        else:
            self._matched_playlists = self._unmatched_playlists

        self.__apply_opts_to_config(opts)
        self.update_playlists(lib, opts.pretend)

    def __apply_opts_to_config(self, opts):
        for k, v in opts.__dict__.items():
            if v is not None and k in self.config:
                self.config[k] = v

    def build_queries(self):
        """
        Instantiate queries for the playlists.

        Each playlist has 2 queries: one or items one for albums, each with a
        sort. We must also remember its name. _unmatched_playlists is a set of
        tuples (name, (q, q_sort), (album_q, album_q_sort)).

        sort may be any sort, or NullSort, or None. None and NullSort are
        equivalent and both eval to False.
        More precisely
        - it will be NullSort when a playlist query ('query' or 'album_query')
          is a single item or a list with 1 element
        - it will be None when there are multiple items i a query
        """
        self._unmatched_playlists = set()
        self._matched_playlists = set()

        for playlist in self.config["playlists"].get(list):
            if "name" not in playlist:
                self._log.warning("playlist configuration is missing name")
                continue

            playlist_data = (playlist["name"],)
            try:
                for key, model_cls in (("query", Item), ("album_query", Album)):
                    qs = playlist.get(key)
                    if qs is None:
                        query_and_sort = None, None
                    elif isinstance(qs, str):
                        query_and_sort = parse_query_string(qs, model_cls)
                    elif len(qs) == 1:
                        query_and_sort = parse_query_string(qs[0], model_cls)
                    else:
                        # multiple queries and sorts
                        queries, sorts = zip(
                            *(parse_query_string(q, model_cls) for q in qs)
                        )
                        query = OrQuery(queries)
                        final_sorts = []
                        for s in sorts:
                            if s:
                                if isinstance(s, MultipleSort):
                                    final_sorts += s.sorts
                                else:
                                    final_sorts.append(s)
                        if not final_sorts:
                            sort = None
                        elif len(final_sorts) == 1:
                            (sort,) = final_sorts
                        else:
                            sort = MultipleSort(final_sorts)
                        query_and_sort = query, sort

                    playlist_data += (query_and_sort,)

            except ParsingError as exc:
                self._log.warning(
                    "invalid query in playlist {}: {}", playlist["name"], exc
                )
                continue

            self._unmatched_playlists.add(playlist_data)

    def matches(self, model, query, album_query):
        if album_query and isinstance(model, Album):
            return album_query.match(model)
        if query and isinstance(model, Item):
            return query.match(model)
        return False

    def db_change(self, lib, model):
        if self._unmatched_playlists is None:
            self.build_queries()

        for playlist in self._unmatched_playlists:
            n, (q, _), (a_q, _) = playlist
            if self.matches(model, q, a_q):
                self._log.debug("{0} will be updated because of {1}", n, model)
                self._matched_playlists.add(playlist)
                self.register_listener("cli_exit", self.update_playlists)

        self._unmatched_playlists -= self._matched_playlists

    def update_playlists(self, lib, pretend=False):
        if pretend:
            self._log.info(
                "Showing query results for {0} smart playlists...",
                len(self._matched_playlists),
            )
        else:
            self._log.info(
                "Updating {0} smart playlists...", len(self._matched_playlists)
            )

        playlist_dir = self.config["playlist_dir"].as_filename()
        playlist_dir = bytestring_path(playlist_dir)
        tpl = self.config["uri_format"].get()
        prefix = bytestring_path(self.config["prefix"].as_str())
        relative_to = self.config["relative_to"].get()
        if relative_to:
            relative_to = normpath(relative_to)

        # Maps playlist filenames to lists of track filenames.
        m3us = {}

        for playlist in self._matched_playlists:
            name, (query, q_sort), (album_query, a_q_sort) = playlist
            if pretend:
                self._log.info("Results for playlist {}:", name)
            else:
                self._log.info("Creating playlist {0}", name)
            items = []

            if query:
                items.extend(lib.items(query, q_sort))
            if album_query:
                for album in lib.albums(album_query, a_q_sort):
                    items.extend(album.items())

            # As we allow tags in the m3u names, we'll need to iterate through
            # the items and generate the correct m3u file names.
            for item in items:
                m3u_name = item.evaluate_template(name, True)
                m3u_name = sanitize_path(m3u_name, lib.replacements)
                if m3u_name not in m3us:
                    m3us[m3u_name] = []
                item_uri = item.path
                if tpl:
                    item_uri = tpl.replace("$id", str(item.id)).encode("utf-8")
                else:
                    if relative_to:
                        item_uri = os.path.relpath(item_uri, relative_to)
                    if self.config["forward_slash"].get():
                        item_uri = path_as_posix(item_uri)
                    if self.config["urlencode"]:
                        item_uri = bytestring_path(pathname2url(item_uri))
                    item_uri = prefix + item_uri

                if item_uri not in m3us[m3u_name]:
                    m3us[m3u_name].append(PlaylistItem(item, item_uri))
                    if pretend and self.config["pretend_paths"]:
                        print(displayable_path(item_uri))
                    elif pretend:
                        print(item)

        if not pretend:
            # Write all of the accumulated track lists to files.
            for m3u in m3us:
                m3u_path = normpath(
                    os.path.join(playlist_dir, bytestring_path(m3u))
                )
                mkdirall(m3u_path)
                pl_format = self.config["output"].get()
                if pl_format != "m3u" and pl_format != "extm3u":
                    msg = "Unsupported output format '{}' provided! "
                    msg += "Supported: m3u, extm3u"
                    raise Exception(msg.format(pl_format))
                extm3u = pl_format == "extm3u"
                with open(syspath(m3u_path), "wb") as f:
                    keys = []
                    if extm3u:
                        keys = self.config["fields"].get(list)
                        f.write(b"#EXTM3U\n")
                    for entry in m3us[m3u]:
                        item = entry.item
                        comment = ""
                        if extm3u:
                            attr = [(k, entry.item[k]) for k in keys]
                            al = [
                                f" {a[0]}={json.dumps(str(a[1]))}" for a in attr
                            ]
                            attrs = "".join(al)
                            comment = "#EXTINF:{}{},{} - {}\n".format(
                                int(item.length), attrs, item.artist, item.title
                            )
                        f.write(comment.encode("utf-8") + entry.uri + b"\n")
            # Send an event when playlists were updated.
            send_event("smartplaylist_update")

        if pretend:
            self._log.info(
                "Displayed results for {0} playlists",
                len(self._matched_playlists),
            )
        else:
            self._log.info(
                "{0} playlists updated", len(self._matched_playlists)
            )


class PlaylistItem:
    def __init__(self, item, uri):
        self.item = item
        self.uri = uri
