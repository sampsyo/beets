# -*- coding: utf-8 -*-
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

"""List missing tracks.
"""
from __future__ import division, absolute_import, print_function

import musicbrainzngs

from musicbrainzngs.musicbrainz import MusicBrainzError
from collections import defaultdict
from beets.autotag import hooks
from beets.library import Item
from beets.plugins import BeetsPlugin
from beets.ui import decargs, print_, Subcommand
from beets import config
from beets.dbcore import types


def _missing_count(album):
    """Return number of missing items in `album`.
    """
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

    return Item(**{
        'album_id':           album_id,
        'album':              a.album,
        'albumartist':        a.artist,
        'albumartist_credit': a.artist_credit,
        'albumartist_sort':   a.artist_sort,
        'albumdisambig':      a.albumdisambig,
        'albumstatus':        a.albumstatus,
        'albumtype':          a.albumtype,
        'artist':             t.artist,
        'artist_credit':      t.artist_credit,
        'artist_sort':        t.artist_sort,
        'asin':               a.asin,
        'catalognum':         a.catalognum,
        'comp':               a.va,
        'country':            a.country,
        'day':                a.day,
        'disc':               t.medium,
        'disctitle':          t.disctitle,
        'disctotal':          a.mediums,
        'label':              a.label,
        'language':           a.language,
        'length':             t.length,
        'mb_albumid':         a.album_id,
        'mb_artistid':        t.artist_id,
        'mb_releasegroupid':  a.releasegroup_id,
        'mb_trackid':         t.track_id,
        'media':              t.media,
        'month':              a.month,
        'script':             a.script,
        'title':              t.title,
        'track':              t.index,
        'tracktotal':         len(a.tracks),
        'year':               a.year,
    })


def _album_item(album_info):
    """Build and return `item` from `album info`
    objects. `item` is missing what fields cannot be obtained from
    MusicBrainz alone (encoder, rg_track_gain, rg_track_peak,
    rg_album_gain, rg_album_peak, original_year, original_month,
    original_day, length, bitrate, format, samplerate, bitdepth,
    channels, mtime.)
    """
    a = album_info

    return Item(**{
        'album_id':           a.get("id"),
        'album':              a.get("release-group", {}).get("title"),
        'albumartist':        a.get("release-group", {}).get("artist-credit", [])[0].get("artist", {}).get("name") if len(a.get("release-group", {}).get("artist-credit", [])) > 0 else None,
        'albumartist_credit': a.get("release-group", {}).get("artist-credit-phrase"),
        'albumartist_sort':   a.get("release-group", {}).get("artist-credit", [])[0].get("artist", {}).get("sort-name") if len(a.get("release-group", {}).get("artist-credit", [])) > 0 else None,
        'albumdisambig':      a.get("release-group", {}).get("artist-credit", [])[0].get("artist", {}).get("disambiguation") if len(a.get("release-group", {}).get("artist-credit", [])) > 0 else None,
        'albumstatus':        a.get("status"),
        'albumtype':          a.get("release-group", {}).get("primary-type"),
        'albumsubtype':       a.get("release-group", {}).get("secondary-type-list", [])[0] if len(a.get("release-group", {}).get("secondary-type-list", [])) > 0 else None,
        'artist':             a.get("artist-credit", [])[0].get("artist", {}).get("name") if len(a.get("artist-credit", [])) > 0 else None,
        'artist_credit':      a.get("artist-credit-phrase"),
        'artist_sort':        a.get("artist-credit", [])[0].get("artist", {}).get("sort-name") if len(a.get("artist-credit", [])) > 0 else None,
        'asin':               a.get("asin"),
        'catalognum':         a.get("label-info-list", [])[0].get("catalog-number") if len(a.get("label-info-list", [])) > 0 else None,
        'comp':               a.get("artist-credit", [])[0].get("artist", {}).get("name") if len(a.get("artist-credit", [])) > 0 else None,
        'country':            a.get("country"),
        'day':                a.get("date", "")[8:10] if len(a.get("date", "")) == 10 else None,
        'disc':               None,
        'disctitle':          None,
        'disctotal':          None,
        'label':              a.get("label-info-list", [])[0].get("label", {}).get("name") if len(a.get("label-info-list", [])) > 0 else None,
        'language':           a.get("text-representation", {}).get("language"),
        'length':             None,
        'mb_albumid':         a.get("id"),
        'mb_artistid':        a.get("artist-credit", [])[0].get("artist", {}).get("id") if len(a.get("artist-credit", [])) > 0 else None,
        'mb_releasegroupid':  a.get("release-group", {}).get("id"),
        'mb_trackid':         None,
        'media':              a.get("packaging"),
        'month':              a.get("date", "")[5:7] if len(a.get("date", "")) >= 7 else None,
        'script':             a.get("text-representation", {}).get("script"),
        'title':              None,
        'track':              None,
        'tracktotal':         None,
        'year':               a.get("date", "")[0:4] if len(a.get("date", "")) >= 4 else None
    })


class MissingPlugin(BeetsPlugin):
    """List missing tracks
    """

    album_types = {
        'missing':  types.INTEGER,
    }

    def __init__(self):
        super(MissingPlugin, self).__init__()

        self.config.add({
            'release_status': [],
            'release_type': [],
            'count': False,
            'total': False,
            'album': False,
        })

        self.album_template_fields['missing'] = _missing_count

        self._command = Subcommand('missing',
                                   help=__doc__,
                                   aliases=['miss'])
        self._command.parser.add_option(
            u'-c', u'--count', dest='count', action='store_true',
            help=u'count missing tracks per album')
        self._command.parser.add_option(
            u'-t', u'--total', dest='total', action='store_true',
            help=u'count total of missing tracks')
        self._command.parser.add_option(
            u'-a', u'--album', dest='album', action='store_true',
            help=u'show missing albums for artist instead of tracks')
        self._command.parser.add_format_option()

    def commands(self):
        def _miss(lib, opts, args):
            self.config.set_args(opts)
            albms = self.config['album'].get()

            helper = self._missing_albums if albms else self._missing_tracks
            helper(lib, decargs(args))

        self._command.func = _miss
        return [self._command]

    def _missing_tracks(self, lib, query):
        """Print a listing of tracks missing from each album in the library
        matching query.
        """
        albums = lib.albums(query)

        count = self.config['count'].get()
        total = self.config['total'].get()
        fmt = config['format_album' if count else 'format_item'].get()

        if total:
            print(sum([_missing_count(a) for a in albums]))
            return

        # Default format string for count mode.
        if count:
            fmt += ': $missing'

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
        total = self.config['total'].get()
        fmt = config['format_album'].get()

        release_status = self.config['release_status'].get()
        release_type = self.config['release_type'].get()

        albums = lib.albums(query)
        # build dict mapping artist to list of their albums in library
        albums_by_artist = defaultdict(list)
        for alb in albums:
            artist = (alb['albumartist'], alb['mb_albumartistid'])
            albums_by_artist[artist].append(alb)

        total_missing = 0

        # build dict mapping artist to list of all albums
        for artist, albums in albums_by_artist.items():
            if artist[1] is None or artist[1] == "":
                albs_no_mbid = [u"'" + a['album'] + u"'" for a in albums]
                self._log.info(
                    u"No musicbrainz ID for artist '{}' found in album(s) {}; "
                    "skipping", artist[0], u", ".join(albs_no_mbid)
                )
                continue

            try:
                resp = musicbrainzngs.browse_releases(
                        artist=artist[1],
                        release_status=release_status,
                        release_type=release_type,
                        includes=[
                            "artist-credits",
                            "labels",
                            "recordings",
                            "isrcs",
                            "release-groups",
                            "media",
                            "discids",
                            "area-rels",
                            "artist-rels",
                            "label-rels",
                            "place-rels",
                            "event-rels",
                            "recording-rels",
                            "release-rels",
                            "release-group-rels",
                            "series-rels",
                            "url-rels",
                            "work-rels",
                            "instrument-rels"
                        ]
                    )
                release_groups = resp['release-list']
            except MusicBrainzError as err:
                self._log.info(
                    u"Couldn't fetch info for artist '{}' ({}) - '{}'",
                    artist[0], artist[1], err
                )
                continue

            missing = []
            present = []
            for rg in release_groups:
                missing.append(rg)
                for alb in albums:
                    if alb['mb_releasegroupid'] == rg.get("release-group", {}).get("id"):
                        missing.remove(rg)
                        present.append(rg)
                        break

            total_missing += len(missing)
            if total:
                continue

            for r in missing:
                #self._log.info(u"{}\n\n", r)
                item = _album_item(r)
                print_(format(item, fmt))

        if total:
            print(total_missing)

    def _missing(self, album):
        """Query MusicBrainz to determine items missing from `album`.
        """
        item_mbids = [x.mb_trackid for x in album.items()]
        if len(list(album.items())) < album.albumtotal:
            # fetch missing items
            # TODO: Implement caching that without breaking other stuff
            album_info = hooks.album_for_mbid(album.mb_albumid)
            for track_info in getattr(album_info, 'tracks', []):
                if track_info.track_id not in item_mbids:
                    item = _item(track_info, album_info, album.id)
                    self._log.debug(u'track {0} in album {1}',
                                    track_info.track_id, album_info.album_id)
                    yield item
