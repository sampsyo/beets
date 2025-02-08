# This file is part of beets.
# Copyright 2016, Pedro Silva.
# Copyright 2017, Quentin Young.
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

"""List missing tracks."""

from collections import defaultdict

import musicbrainzngs
from musicbrainzngs.musicbrainz import MusicBrainzError

from beets import config
from beets.autotag import hooks
from beets.dbcore import types
from beets.library import Item
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, decargs, print_


def _missing_count(album):
    """Return number of missing items in `album`."""
    return (album.albumtotal or 0) - len(album.items())


def _item(track_info, album_info, album_id):
    """Build and return `item` from `track_info` and `album info`
    objects. `item` is missing what fields cannot be obtained from
    MusicBrainz alone (encoder, rg_track_gain, rg_track_peak,
    rg_album_gain, rg_album_peak, original_year, original_month,
    original_day, length, bitrate, format, samplerate, bitdepth,
    channels, mtime.)
    """
    t = track_info
    a = album_info

    return Item(
        **{
            "album_id": album_id,
            "album": a.album,
            "albumartist": a.artist,
            "albumartist_credit": a.artist_credit,
            "albumartist_sort": a.artist_sort,
            "albumdisambig": a.albumdisambig,
            "albumstatus": a.albumstatus,
            "albumtype": a.albumtype,
            "artist": t.artist,
            "artist_credit": t.artist_credit,
            "artist_sort": t.artist_sort,
            "asin": a.asin,
            "catalognum": a.catalognum,
            "comp": a.va,
            "country": a.country,
            "day": a.day,
            "disc": t.medium,
            "disctitle": t.disctitle,
            "disctotal": a.mediums,
            "label": a.label,
            "language": a.language,
            "length": t.length,
            "mb_albumid": a.album_id,
            "mb_artistid": t.artist_id,
            "mb_releasegroupid": a.releasegroup_id,
            "mb_trackid": t.track_id,
            "media": t.media,
            "month": a.month,
            "script": a.script,
            "title": t.title,
            "track": t.index,
            "tracktotal": len(a.tracks),
            "year": a.year,
        }
    )


class MissingPlugin(BeetsPlugin):
    """List missing tracks"""

    album_types = {
        "missing": types.INTEGER,
    }

    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "count": False,
                "total": False,
                "album": False,
            }
        )

        self.album_template_fields["missing"] = _missing_count

        self._command = Subcommand("missing", help=__doc__, aliases=["miss"])
        self._command.parser.add_option(
            "-c",
            "--count",
            dest="count",
            action="store_true",
            help="count missing tracks per album",
        )
        self._command.parser.add_option(
            "-t",
            "--total",
            dest="total",
            action="store_true",
            help="count total of missing tracks",
        )
        self._command.parser.add_option(
            "-a",
            "--album",
            dest="album",
            action="store_true",
            help="show missing albums for artist instead of tracks",
        )
        self._command.parser.add_format_option()

    def commands(self):
        def _miss(lib, opts, args):
            self.config.set_args(opts)
            albms = self.config["album"].get()

            helper = self._missing_albums if albms else self._missing_tracks
            helper(lib, decargs(args))

        self._command.func = _miss
        return [self._command]

    def _missing_tracks(self, lib, query):
        """Print a listing of tracks missing from each album in the library
        matching query.
        """
        albums = lib.albums(query)

        count = self.config["count"].get()
        total = self.config["total"].get()
        fmt = config["format_album" if count else "format_item"].get()

        if total:
            print(sum([_missing_count(a) for a in albums]))
            return

        # Default format string for count mode.
        if count:
            fmt += ": $missing"

        for album in albums:
            if count:
                if _missing_count(album):
                    print_(format(album, fmt))

            else:
                for item in self._missing(album):
                    print_(format(item, fmt))

    def _missing_albums(self, lib, query):
        """Print a listing of albums missing from each artist in the library
        matching query.
        """
        total = self.config["total"].get()

        albums = lib.albums(query)
        # build dict mapping artist to list of their albums in library
        albums_by_artist = defaultdict(list)
        for alb in albums:
            artist = (alb["albumartist"], alb["mb_albumartistid"])
            albums_by_artist[artist].append(alb)

        total_missing = 0

        # build dict mapping artist to list of all albums
        for artist, albums in albums_by_artist.items():
            if artist[1] is None or artist[1] == "":
                albs_no_mbid = ["'" + a["album"] + "'" for a in albums]
                self._log.info(
                    "No musicbrainz ID for artist '{}' found in album(s) {}; "
                    "skipping",
                    artist[0],
                    ", ".join(albs_no_mbid),
                )
                continue

            try:
                resp = musicbrainzngs.browse_release_groups(artist=artist[1])
                release_groups = resp["release-group-list"]
            except MusicBrainzError as err:
                self._log.info(
                    "Couldn't fetch info for artist '{}' ({}) - '{}'",
                    artist[0],
                    artist[1],
                    err,
                )
                continue

            missing = []
            present = []
            for rg in release_groups:
                missing.append(rg)
                for alb in albums:
                    if alb["mb_releasegroupid"] == rg["id"]:
                        missing.remove(rg)
                        present.append(rg)
                        break

            total_missing += len(missing)
            if total:
                continue

            missing_titles = {rg["title"] for rg in missing}

            for release_title in missing_titles:
                print_("{} - {}".format(artist[0], release_title))

        if total:
            print(total_missing)

    def _missing(self, album):
        """Query MusicBrainz to determine items missing from `album`."""
        item_mbids = [x.mb_trackid for x in album.items()]
        if len(list(album.items())) < album.albumtotal:
            # fetch missing items
            # TODO: Implement caching that without breaking other stuff
            album_info = hooks.album_for_mbid(album.mb_albumid)
            for track_info in getattr(album_info, "tracks", []):
                if track_info.track_id not in item_mbids:
                    item = _item(track_info, album_info, album.id)
                    self._log.debug(
                        "track {0} in album {1}",
                        track_info.track_id,
                        album_info.album_id,
                    )
                    yield item
