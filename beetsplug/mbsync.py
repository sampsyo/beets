# -*- coding: utf-8 -*-
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
"""Update library's tags using MusicBrainz.
"""
from __future__ import division, absolute_import, print_function

from beets.plugins import BeetsPlugin, apply_item_changes
from beets import autotag, library, ui, util
from beets.autotag import hooks
from collections import defaultdict

import re

MBID_REGEX = r"(\d|\w){8}-(\d|\w){4}-(\d|\w){4}-(\d|\w){4}-(\d|\w){12}"


def track_performers(info):
    artists = {}
    for artist_relation in info.get('artist-relation-list', ()):
        if 'type' in artist_relation:
            role = 'mbsync '
            role += artist_relation['type']
            if 'balance' in role or 'recording' in role or 'sound' in role:
                role += ' engineer'
            if 'performing orchestra' in role:
                role = 'mbsync orchestra'
            role_sort = role + ' sort'
            if 'attribute-list' in artist_relation:
                role += ' - '
                role_sort += ' - '
                role += ', '.join(artist_relation['attribute-list'])
                role_sort += ', '.join(artist_relation['attribute-list'])
            if 'attributes' in artist_relation:
                for attribute in artist_relation['attributes']:
                    if 'credited-as' in attribute:
                        role += ' (' + attribute['credited-as'] + ')'
                        role_sort += ' (' + attribute['credited-as'] + ')'
            role = role.replace(" ", "_")
            role_sort = role_sort.replace(' ', '_')
            if role in artists:
                artists[role].append(artist_relation['artist']['name'])
                artists[role_sort].append(
                        artist_relation['artist']['sort-name'])
            else:
                artists[role] = [artist_relation['artist']['name']]
                artists[role_sort] = [artist_relation[
                        'artist']['sort-name']]
    for key in artists:
        artists[key] = u'; '.join(artists[key])
    return artists


def album_performers(info):
    """ placeholder for more album-related performers
    """

    artists = {}
    for artist_relation in info.get('artist-relation-list', ()):
        if 'type' in artist_relation:
            role = 'mbsync album '
            role += artist_relation['type']
            if 'balance' in role or 'recording' in role or 'sound' in role:
                role += ' engineer'
            if 'performing orchestra' in role:
                role = 'mbsync album orchestra'
            role_sort = role + ' sort'
            if 'attribute-list' in artist_relation:
                role += ' - '
                role_sort += ' - '
                role += ', '.join(artist_relation['attribute-list'])
                role_sort += ', '.join(artist_relation['attribute-list'])
            if 'attributes' in artist_relation:
                for attribute in artist_relation['attributes']:
                    if 'credited-as' in attribute:
                        role += ' (' + attribute['credited-as'] + ')'
                        role_sort += ' (' + attribute['credited-as'] + ')'
            role = role.replace(" ", "_")
            role_sort = role_sort.replace(' ', '_')
            if role in artists:
                artists[role].append(artist_relation['artist']['name'])
                artists[role_sort].append(
                        artist_relation['artist']['sort-name'])
            else:
                artists[role] = [artist_relation['artist']['name']]
                artists[role_sort] = [artist_relation[
                        'artist']['sort-name']]
    for key in artists:
        artists[key] = u'; '.join(artists[key])

    return artists


class MBSyncPlugin(BeetsPlugin):
    def __init__(self):
        super(MBSyncPlugin, self).__init__()

        self.config.add({
            u'bin': u'mbsync',
            u'performer_info': False,
        })

        if self.config['performer_info'].get(bool):
            self.register_listener('extracting_trackdata', track_performers)
            self.register_listener('extracting_albumdata', album_performers)

    def commands(self):
        cmd = ui.Subcommand('mbsync',
                            help=u'update metadata from musicbrainz')
        cmd.parser.add_option(
            u'-p', u'--pretend', action='store_true',
            help=u'show all changes but do nothing')
        cmd.parser.add_option(
            u'-m', u'--move', action='store_true', dest='move',
            help=u"move files in the library directory")
        cmd.parser.add_option(
            u'-M', u'--nomove', action='store_false', dest='move',
            help=u"don't move files in library")
        cmd.parser.add_option(
            u'-W', u'--nowrite', action='store_false',
            default=None, dest='write',
            help=u"don't write updated metadata to files")
        cmd.parser.add_option(
            u'-P', u'--performer_info', action='store_true',
            dest='performer_info',
            default=self.config['performer_info'].get(bool),
            help=u"Fetch performer info")
        cmd.parser.add_format_option()
        cmd.func = self.func
        return [cmd]

    def func(self, lib, opts, args):
        """Command handler for the mbsync function.
        """
        move = ui.should_move(opts.move)
        pretend = opts.pretend
        write = ui.should_write(opts.write)
        performer_info = opts.performer_info
        query = ui.decargs(args)

        self.singletons(lib, query, move, pretend, write, performer_info)
        self.albums(lib, query, move, pretend, write, performer_info)

    def singletons(self, lib, query, move, pretend, write, performer_info):
        """Retrieve and apply info from the autotagger for items matched by
        query.
        """
        for item in lib.items(query + [u'singleton:true']):
            item_formatted = format(item)
            if not item.mb_trackid:
                self._log.info(u'Skipping singleton with no mb_trackid: {0}',
                               item_formatted)
                continue

            # Do we have a valid MusicBrainz track ID?
            if not re.match(MBID_REGEX, item.mb_trackid):
                self._log.info(u'Skipping singleton with invalid mb_trackid:' +
                               ' {0}', item_formatted)
                continue

            # Get the MusicBrainz recording info.
            track_info = hooks.track_for_mbid(item.mb_trackid)
            if not track_info:
                self._log.info(u'Recording ID not found: {0} for track {0}',
                               item.mb_trackid,
                               item_formatted)
                continue
            # Clean up obsolete flexible fields
            if performer_info:
                for tag in item:
                    if tag[:6] == 'mbsync' and tag not in track_info:
                        del item[tag]
            # Apply.
            with lib.transaction():
                autotag.apply_item_metadata(item, track_info)
                ui.show_model_changes(item)
                apply_item_changes(lib, item, move, pretend, write)

    def albums(self, lib, query, move, pretend, write, performer_info):
        """Retrieve and apply info from the autotagger for albums matched by
        query and their items.
        """
        # Process matching albums.
        for a in lib.albums(query):
            album_formatted = format(a)
            if not a.mb_albumid:
                self._log.info(u'Skipping album with no mb_albumid: {0}',
                               album_formatted)
                continue

            items = list(a.items())

            # Do we have a valid MusicBrainz album ID?
            if not re.match(MBID_REGEX, a.mb_albumid):
                self._log.info(u'Skipping album with invalid mb_albumid: {0}',
                               album_formatted)
                continue

            # Get the MusicBrainz album information.
            album_info = hooks.album_for_mbid(a.mb_albumid)
            if not album_info:
                self._log.info(u'Release ID {0} not found for album {1}',
                               a.mb_albumid,
                               album_formatted)
                continue

            # Map release track and recording MBIDs to their information.
            # Recordings can appear multiple times on a release, so each MBID
            # maps to a list of TrackInfo objects.
            releasetrack_index = dict()
            track_index = defaultdict(list)
            for track_info in album_info.tracks:
                releasetrack_index[track_info.release_track_id] = track_info
                track_index[track_info.track_id].append(track_info)

            # Construct a track mapping according to MBIDs (release track MBIDs
            # first, if available, and recording MBIDs otherwise). This should
            # work for albums that have missing or extra tracks.
            mapping = {}
            for item in items:
                # Clean up obsolete flexible fields
                if performer_info:
                    for tag in item:
                        if tag[:6] == 'mbsync' and (tag not in track_info or
                                                    tag not in album_info):
                            del item[tag]
                if item.mb_releasetrackid and \
                        item.mb_releasetrackid in releasetrack_index:
                    mapping[item] = releasetrack_index[item.mb_releasetrackid]
                else:
                    candidates = track_index[item.mb_trackid]
                    if len(candidates) == 1:
                        mapping[item] = candidates[0]
                    else:
                        # If there are multiple copies of a recording, they are
                        # disambiguated using their disc and track number.
                        for c in candidates:
                            if (c.medium_index == item.track and
                                    c.medium == item.disc):
                                mapping[item] = c
                                break

            # Apply.
            self._log.debug(u'applying changes to {}', album_formatted)
            with lib.transaction():
                autotag.apply_metadata(album_info, mapping)
                changed = False
                # Find any changed item to apply MusicBrainz changes to album.
                any_changed_item = items[0]
                for item in items:
                    item_changed = ui.show_model_changes(item)
                    changed |= item_changed
                    if item_changed:
                        any_changed_item = item
                        apply_item_changes(lib, item, move, pretend, write)

                if not changed:
                    # No change to any item.
                    continue

                if not pretend:
                    # Update album structure to reflect an item in it.
                    for key in library.Album.item_keys:
                        a[key] = any_changed_item[key]
                    a.store()

                    # Move album art (and any inconsistent items).
                    if move and lib.directory in util.ancestry(items[0].path):
                        self._log.debug(u'moving album {0}', album_formatted)
                        a.move()
