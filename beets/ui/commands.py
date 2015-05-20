# This file is part of beets.
# Copyright 2015, Adrian Sampson.
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

"""This module provides the default commands for beets' command-line
interface.
"""

from __future__ import (division, absolute_import, print_function,
                        unicode_literals)

import click
import os
import re

import beets
from beets import ui
from beets.ui import print_, input_, decargs
from beets import autotag
from beets.autotag import Recommendation
from beets.autotag import hooks
from beets import plugins
from beets import importer
from beets import util
from beets.util import syspath, normpath, ancestry, displayable_path
from beets import library
from beets import config
from beets import logging
from beets.util.confit import _package_path

VARIOUS_ARTISTS = u'Various Artists'

# Global logger.
log = logging.getLogger('beets')

# The list of default subcommands. This is populated with Subcommand
# objects that can be fed to a SubcommandsOptionParser.
default_commands = []


# Utilities.

def _do_query(lib, query, album, also_items=True):
    """For commands that operate on matched items, performs a query
    and returns a list of matching items and a list of matching
    albums. (The latter is only nonempty when album is True.) Raises
    a UserError if no items match. also_items controls whether, when
    fetching albums, the associated items should be fetched also.
    """
    if album:
        albums = list(lib.albums(query))
        items = []
        if also_items:
            for al in albums:
                items += al.items()

    else:
        albums = []
        items = list(lib.items(query))

    if album and not albums:
        raise ui.UserError('No matching albums found.')
    elif not album and not items:
        raise ui.UserError('No matching items found.')

    return items, albums


# fields: Shows a list of available fields for queries and format strings.

@click.command(
    'fields',
    short_help='show fields available for queries and format strings',
)
@ui.pass_context
def fields_cmd(ctx):
    def _print_rows(names):
        names.sort()
        print_("  " + "\n  ".join(names))

    fs, pfs = library.Item.get_fields()
    print_("Item fields:")
    _print_rows(fs)
    print_("Template fields from plugins:")
    _print_rows(pfs)

    fs, pfs = library.Album.get_fields()
    print_("Album fields:")
    _print_rows(fs)
    print_("Template fields from plugins:")
    _print_rows(pfs)


default_commands.append(fields_cmd)


# help: Print help text for commands

@click.command('help',
               short_help='give detailed help on a specific sub-command')
@click.pass_context
def help_cmd(ctx):
    if not ctx.args:
        print_(ctx.parent.get_help())
        return

    cmd_name, cmd, args = ctx.parent.command.resolve_command(
        ctx.parent,
        ctx.args
    )
    with cmd.make_context(cmd_name, args, parent=ctx.parent) as ctx_:
        print_(ctx_.get_help())

help_cmd.allow_extra_args = True
default_commands.append(help_cmd)


# import: Autotagger and importer.

# Importer utilities and support.

def disambig_string(info):
    """Generate a string for an AlbumInfo or TrackInfo object that
    provides context that helps disambiguate similar-looking albums and
    tracks.
    """
    disambig = []
    if info.data_source and info.data_source != 'MusicBrainz':
        disambig.append(info.data_source)

    if isinstance(info, hooks.AlbumInfo):
        if info.media:
            if info.mediums > 1:
                disambig.append(u'{0}x{1}'.format(
                    info.mediums, info.media
                ))
            else:
                disambig.append(info.media)
        if info.year:
            disambig.append(unicode(info.year))
        if info.country:
            disambig.append(info.country)
        if info.label:
            disambig.append(info.label)
        if info.albumdisambig:
            disambig.append(info.albumdisambig)

    if disambig:
        return u', '.join(disambig)


def dist_string(dist):
    """Formats a distance (a float) as a colorized similarity percentage
    string.
    """
    out = '%.1f%%' % ((1 - dist) * 100)
    if dist <= config['match']['strong_rec_thresh'].as_number():
        out = ui.colorize('text_success', out)
    elif dist <= config['match']['medium_rec_thresh'].as_number():
        out = ui.colorize('text_warning', out)
    else:
        out = ui.colorize('text_error', out)
    return out


def penalty_string(distance, limit=None):
    """Returns a colorized string that indicates all the penalties
    applied to a distance object.
    """
    penalties = []
    for key in distance.keys():
        key = key.replace('album_', '')
        key = key.replace('track_', '')
        key = key.replace('_', ' ')
        penalties.append(key)
    if penalties:
        if limit and len(penalties) > limit:
            penalties = penalties[:limit] + ['...']
        return ui.colorize('text_warning', '(%s)' % ', '.join(penalties))


def show_change(cur_artist, cur_album, match):
    """Print out a representation of the changes that will be made if an
    album's tags are changed according to `match`, which must be an AlbumMatch
    object.
    """
    def show_album(artist, album):
        if artist:
            album_description = u'    %s - %s' % (artist, album)
        elif album:
            album_description = u'    %s' % album
        else:
            album_description = u'    (unknown album)'
        print_(album_description)

    def format_index(track_info):
        """Return a string representing the track index of the given
        TrackInfo or Item object.
        """
        if isinstance(track_info, hooks.TrackInfo):
            index = track_info.index
            medium_index = track_info.medium_index
            medium = track_info.medium
            mediums = match.info.mediums
        else:
            index = medium_index = track_info.track
            medium = track_info.disc
            mediums = track_info.disctotal
        if config['per_disc_numbering']:
            if mediums > 1:
                return u'{0}-{1}'.format(medium, medium_index)
            else:
                return unicode(medium_index)
        else:
            return unicode(index)

    # Identify the album in question.
    if cur_artist != match.info.artist or \
            (cur_album != match.info.album and
             match.info.album != VARIOUS_ARTISTS):
        artist_l, artist_r = cur_artist or '', match.info.artist
        album_l,  album_r = cur_album or '', match.info.album
        if artist_r == VARIOUS_ARTISTS:
            # Hide artists for VA releases.
            artist_l, artist_r = u'', u''

        artist_l, artist_r = ui.colordiff(artist_l, artist_r)
        album_l, album_r = ui.colordiff(album_l, album_r)

        print_("Correcting tags from:")
        show_album(artist_l, album_l)
        print_("To:")
        show_album(artist_r, album_r)
    else:
        print_(u"Tagging:\n    {0.artist} - {0.album}".format(match.info))

    # Data URL.
    if match.info.data_url:
        print_('URL:\n    %s' % match.info.data_url)

    # Info line.
    info = []
    # Similarity.
    info.append('(Similarity: %s)' % dist_string(match.distance))
    # Penalties.
    penalties = penalty_string(match.distance)
    if penalties:
        info.append(penalties)
    # Disambiguation.
    disambig = disambig_string(match.info)
    if disambig:
        info.append(ui.colorize('text_highlight_minor', '(%s)' % disambig))
    print_(' '.join(info))

    # Tracks.
    pairs = match.mapping.items()
    pairs.sort(key=lambda (_, track_info): track_info.index)

    # Build up LHS and RHS for track difference display. The `lines` list
    # contains ``(lhs, rhs, width)`` tuples where `width` is the length (in
    # characters) of the uncolorized LHS.
    lines = []
    medium = disctitle = None
    for item, track_info in pairs:

        # Medium number and title.
        if medium != track_info.medium or disctitle != track_info.disctitle:
            media = match.info.media or 'Media'
            if match.info.mediums > 1 and track_info.disctitle:
                lhs = '%s %s: %s' % (media, track_info.medium,
                                     track_info.disctitle)
            elif match.info.mediums > 1:
                lhs = '%s %s' % (media, track_info.medium)
            elif track_info.disctitle:
                lhs = '%s: %s' % (media, track_info.disctitle)
            else:
                lhs = None
            if lhs:
                lines.append((lhs, '', 0))
            medium, disctitle = track_info.medium, track_info.disctitle

        # Titles.
        new_title = track_info.title
        if not item.title.strip():
            # If there's no title, we use the filename.
            cur_title = displayable_path(os.path.basename(item.path))
            lhs, rhs = cur_title, new_title
        else:
            cur_title = item.title.strip()
            lhs, rhs = ui.colordiff(cur_title, new_title)
        lhs_width = len(cur_title)

        # Track number change.
        cur_track, new_track = format_index(item), format_index(track_info)
        if cur_track != new_track:
            if item.track in (track_info.index, track_info.medium_index):
                color = 'text_highlight_minor'
            else:
                color = 'text_highlight'
            templ = ui.colorize(color, u' (#{0})')
            lhs += templ.format(cur_track)
            rhs += templ.format(new_track)
            lhs_width += len(cur_track) + 4

        # Length change.
        if item.length and track_info.length and \
                abs(item.length - track_info.length) > \
                config['ui']['length_diff_thresh'].as_number():
            cur_length = ui.human_seconds_short(item.length)
            new_length = ui.human_seconds_short(track_info.length)
            templ = ui.colorize('text_highlight', u' ({0})')
            lhs += templ.format(cur_length)
            rhs += templ.format(new_length)
            lhs_width += len(cur_length) + 3

        # Penalties.
        penalties = penalty_string(match.distance.tracks[track_info])
        if penalties:
            rhs += ' %s' % penalties

        if lhs != rhs:
            lines.append((' * %s' % lhs, rhs, lhs_width))
        elif config['import']['detail']:
            lines.append((' * %s' % lhs, '', lhs_width))

    # Print each track in two columns, or across two lines.
    col_width = (ui.term_width() - len(''.join([' * ', ' -> ']))) // 2
    if lines:
        max_width = max(w for _, _, w in lines)
        for lhs, rhs, lhs_width in lines:
            if not rhs:
                print_(lhs)
            elif max_width > col_width:
                print_(u'%s ->\n   %s' % (lhs, rhs))
            else:
                pad = max_width - lhs_width
                print_(u'%s%s -> %s' % (lhs, ' ' * pad, rhs))

    # Missing and unmatched tracks.
    if match.extra_tracks:
        print_('Missing tracks ({0}/{1} - {2:.1%}):'.format(
               len(match.extra_tracks),
               len(match.info.tracks),
               len(match.extra_tracks) / len(match.info.tracks)
               ))
    for track_info in match.extra_tracks:
        line = ' ! %s (#%s)' % (track_info.title, format_index(track_info))
        if track_info.length:
            line += ' (%s)' % ui.human_seconds_short(track_info.length)
        print_(ui.colorize('text_warning', line))
    if match.extra_items:
        print_('Unmatched tracks ({0}):'.format(len(match.extra_items)))
    for item in match.extra_items:
        line = ' ! %s (#%s)' % (item.title, format_index(item))
        if item.length:
            line += ' (%s)' % ui.human_seconds_short(item.length)
        print_(ui.colorize('text_warning', line))


def show_item_change(item, match):
    """Print out the change that would occur by tagging `item` with the
    metadata from `match`, a TrackMatch object.
    """
    cur_artist, new_artist = item.artist, match.info.artist
    cur_title, new_title = item.title, match.info.title

    if cur_artist != new_artist or cur_title != new_title:
        cur_artist, new_artist = ui.colordiff(cur_artist, new_artist)
        cur_title, new_title = ui.colordiff(cur_title, new_title)

        print_("Correcting track tags from:")
        print_("    %s - %s" % (cur_artist, cur_title))
        print_("To:")
        print_("    %s - %s" % (new_artist, new_title))

    else:
        print_("Tagging track: %s - %s" % (cur_artist, cur_title))

    # Data URL.
    if match.info.data_url:
        print_('URL:\n    %s' % match.info.data_url)

    # Info line.
    info = []
    # Similarity.
    info.append('(Similarity: %s)' % dist_string(match.distance))
    # Penalties.
    penalties = penalty_string(match.distance)
    if penalties:
        info.append(penalties)
    # Disambiguation.
    disambig = disambig_string(match.info)
    if disambig:
        info.append(ui.colorize('text_highlight_minor', '(%s)' % disambig))
    print_(' '.join(info))


def summarize_items(items, singleton):
    """Produces a brief summary line describing a set of items. Used for
    manually resolving duplicates during import.

    `items` is a list of `Item` objects. `singleton` indicates whether
    this is an album or single-item import (if the latter, them `items`
    should only have one element).
    """
    summary_parts = []
    if not singleton:
        summary_parts.append("{0} items".format(len(items)))

    format_counts = {}
    for item in items:
        format_counts[item.format] = format_counts.get(item.format, 0) + 1
    if len(format_counts) == 1:
        # A single format.
        summary_parts.append(items[0].format)
    else:
        # Enumerate all the formats by decreasing frequencies:
        for fmt, count in sorted(format_counts.items(),
                                 key=lambda (f, c): (-c, f)):
            summary_parts.append('{0} {1}'.format(fmt, count))

    if items:
        average_bitrate = sum([item.bitrate for item in items]) / len(items)
        total_duration = sum([item.length for item in items])
        total_filesize = sum([item.filesize for item in items])
        summary_parts.append('{0}kbps'.format(int(average_bitrate / 1000)))
        summary_parts.append(ui.human_seconds_short(total_duration))
        summary_parts.append(ui.human_bytes(total_filesize))

    return ', '.join(summary_parts)


def _summary_judment(rec):
    """Determines whether a decision should be made without even asking
    the user. This occurs in quiet mode and when an action is chosen for
    NONE recommendations. Return an action or None if the user should be
    queried. May also print to the console if a summary judgment is
    made.
    """
    if config['import']['quiet']:
        if rec == Recommendation.strong:
            return importer.action.APPLY
        else:
            action = config['import']['quiet_fallback'].as_choice({
                'skip': importer.action.SKIP,
                'asis': importer.action.ASIS,
            })

    elif rec == Recommendation.none:
        action = config['import']['none_rec_action'].as_choice({
            'skip': importer.action.SKIP,
            'asis': importer.action.ASIS,
            'ask': None,
        })

    else:
        return None

    if action == importer.action.SKIP:
        print_('Skipping.')
    elif action == importer.action.ASIS:
        print_('Importing as-is.')
    return action


def choose_candidate(candidates, singleton, rec, cur_artist=None,
                     cur_album=None, item=None, itemcount=None):
    """Given a sorted list of candidates, ask the user for a selection
    of which candidate to use. Applies to both full albums and
    singletons  (tracks). Candidates are either AlbumMatch or TrackMatch
    objects depending on `singleton`. for albums, `cur_artist`,
    `cur_album`, and `itemcount` must be provided. For singletons,
    `item` must be provided.

    Returns the result of the choice, which may SKIP, ASIS, TRACKS, or
    MANUAL or a candidate (an AlbumMatch/TrackMatch object).
    """
    # Sanity check.
    if singleton:
        assert item is not None
    else:
        assert cur_artist is not None
        assert cur_album is not None

    # Zero candidates.
    if not candidates:
        if singleton:
            print_("No matching recordings found.")
            opts = ('Use as-is', 'Skip', 'Enter search', 'enter Id',
                    'aBort')
        else:
            print_("No matching release found for {0} tracks."
                   .format(itemcount))
            print_('For help, see: '
                   'http://beets.readthedocs.org/en/latest/faq.html#nomatch')
            opts = ('Use as-is', 'as Tracks', 'Group albums', 'Skip',
                    'Enter search', 'enter Id', 'aBort')
        sel = ui.input_options(opts)
        if sel == 'u':
            return importer.action.ASIS
        elif sel == 't':
            assert not singleton
            return importer.action.TRACKS
        elif sel == 'e':
            return importer.action.MANUAL
        elif sel == 's':
            return importer.action.SKIP
        elif sel == 'b':
            raise importer.ImportAbort()
        elif sel == 'i':
            return importer.action.MANUAL_ID
        elif sel == 'g':
            return importer.action.ALBUMS
        else:
            assert False

    # Is the change good enough?
    bypass_candidates = False
    if rec != Recommendation.none:
        match = candidates[0]
        bypass_candidates = True

    while True:
        # Display and choose from candidates.
        require = rec <= Recommendation.low

        if not bypass_candidates:
            # Display list of candidates.
            print_(u'Finding tags for {0} "{1} - {2}".'.format(
                u'track' if singleton else u'album',
                item.artist if singleton else cur_artist,
                item.title if singleton else cur_album,
            ))

            print_(u'Candidates:')
            for i, match in enumerate(candidates):
                # Index, metadata, and distance.
                line = [
                    u'{0}.'.format(i + 1),
                    u'{0} - {1}'.format(
                        match.info.artist,
                        match.info.title if singleton else match.info.album,
                    ),
                    u'({0})'.format(dist_string(match.distance)),
                ]

                # Penalties.
                penalties = penalty_string(match.distance, 3)
                if penalties:
                    line.append(penalties)

                # Disambiguation
                disambig = disambig_string(match.info)
                if disambig:
                    line.append(ui.colorize('text_highlight_minor',
                                            '(%s)' % disambig))

                print_(' '.join(line))

            # Ask the user for a choice.
            if singleton:
                opts = ('Skip', 'Use as-is', 'Enter search', 'enter Id',
                        'aBort')
            else:
                opts = ('Skip', 'Use as-is', 'as Tracks', 'Group albums',
                        'Enter search', 'enter Id', 'aBort')
            sel = ui.input_options(opts, numrange=(1, len(candidates)))
            if sel == 's':
                return importer.action.SKIP
            elif sel == 'u':
                return importer.action.ASIS
            elif sel == 'm':
                pass
            elif sel == 'e':
                return importer.action.MANUAL
            elif sel == 't':
                assert not singleton
                return importer.action.TRACKS
            elif sel == 'b':
                raise importer.ImportAbort()
            elif sel == 'i':
                return importer.action.MANUAL_ID
            elif sel == 'g':
                return importer.action.ALBUMS
            else:  # Numerical selection.
                match = candidates[sel - 1]
                if sel != 1:
                    # When choosing anything but the first match,
                    # disable the default action.
                    require = True
        bypass_candidates = False

        # Show what we're about to do.
        if singleton:
            show_item_change(item, match)
        else:
            show_change(cur_artist, cur_album, match)

        # Exact match => tag automatically if we're not in timid mode.
        if rec == Recommendation.strong and not config['import']['timid']:
            return match

        # Ask for confirmation.
        if singleton:
            opts = ('Apply', 'More candidates', 'Skip', 'Use as-is',
                    'Enter search', 'enter Id', 'aBort')
        else:
            opts = ('Apply', 'More candidates', 'Skip', 'Use as-is',
                    'as Tracks', 'Group albums', 'Enter search', 'enter Id',
                    'aBort')
        default = config['import']['default_action'].as_choice({
            'apply': 'a',
            'skip': 's',
            'asis': 'u',
            'none': None,
        })
        if default is None:
            require = True
        sel = ui.input_options(opts, require=require, default=default)
        if sel == 'a':
            return match
        elif sel == 'g':
            return importer.action.ALBUMS
        elif sel == 's':
            return importer.action.SKIP
        elif sel == 'u':
            return importer.action.ASIS
        elif sel == 't':
            assert not singleton
            return importer.action.TRACKS
        elif sel == 'e':
            return importer.action.MANUAL
        elif sel == 'b':
            raise importer.ImportAbort()
        elif sel == 'i':
            return importer.action.MANUAL_ID


def manual_search(singleton):
    """Input either an artist and album (for full albums) or artist and
    track name (for singletons) for manual search.
    """
    artist = input_('Artist:')
    name = input_('Track:' if singleton else 'Album:')
    return artist.strip(), name.strip()


def manual_id(singleton):
    """Input an ID, either for an album ("release") or a track ("recording").
    """
    prompt = u'Enter {0} ID:'.format('recording' if singleton else 'release')
    return input_(prompt).strip()


class TerminalImportSession(importer.ImportSession):
    """An import session that runs in a terminal.
    """
    def choose_match(self, task):
        """Given an initial autotagging of items, go through an interactive
        dance with the user to ask for a choice of metadata. Returns an
        AlbumMatch object, ASIS, or SKIP.
        """
        # Show what we're tagging.
        print_()
        print_(displayable_path(task.paths, u'\n') +
               u' ({0} items)'.format(len(task.items)))

        # Take immediate action if appropriate.
        action = _summary_judment(task.rec)
        if action == importer.action.APPLY:
            match = task.candidates[0]
            show_change(task.cur_artist, task.cur_album, match)
            return match
        elif action is not None:
            return action

        # Loop until we have a choice.
        candidates, rec = task.candidates, task.rec
        while True:
            # Ask for a choice from the user.
            choice = choose_candidate(
                candidates, False, rec, task.cur_artist, task.cur_album,
                itemcount=len(task.items)
            )

            # Choose which tags to use.
            if choice in (importer.action.SKIP, importer.action.ASIS,
                          importer.action.TRACKS, importer.action.ALBUMS):
                # Pass selection to main control flow.
                return choice
            elif choice is importer.action.MANUAL:
                # Try again with manual search terms.
                search_artist, search_album = manual_search(False)
                _, _, candidates, rec = autotag.tag_album(
                    task.items, search_artist, search_album
                )
            elif choice is importer.action.MANUAL_ID:
                # Try a manually-entered ID.
                search_id = manual_id(False)
                if search_id:
                    _, _, candidates, rec = autotag.tag_album(
                        task.items, search_id=search_id
                    )
            else:
                # We have a candidate! Finish tagging. Here, choice is an
                # AlbumMatch object.
                assert isinstance(choice, autotag.AlbumMatch)
                return choice

    def choose_item(self, task):
        """Ask the user for a choice about tagging a single item. Returns
        either an action constant or a TrackMatch object.
        """
        print_()
        print_(task.item.path)
        candidates, rec = task.candidates, task.rec

        # Take immediate action if appropriate.
        action = _summary_judment(task.rec)
        if action == importer.action.APPLY:
            match = candidates[0]
            show_item_change(task.item, match)
            return match
        elif action is not None:
            return action

        while True:
            # Ask for a choice.
            choice = choose_candidate(candidates, True, rec, item=task.item)

            if choice in (importer.action.SKIP, importer.action.ASIS):
                return choice
            elif choice == importer.action.TRACKS:
                assert False  # TRACKS is only legal for albums.
            elif choice == importer.action.MANUAL:
                # Continue in the loop with a new set of candidates.
                search_artist, search_title = manual_search(True)
                candidates, rec = autotag.tag_item(task.item, search_artist,
                                                   search_title)
            elif choice == importer.action.MANUAL_ID:
                # Ask for a track ID.
                search_id = manual_id(True)
                if search_id:
                    candidates, rec = autotag.tag_item(task.item,
                                                       search_id=search_id)
            else:
                # Chose a candidate.
                assert isinstance(choice, autotag.TrackMatch)
                return choice

    def resolve_duplicate(self, task, found_duplicates):
        """Decide what to do when a new album or item seems similar to one
        that's already in the library.
        """
        log.warn(u"This {0} is already in the library!",
                 ("album" if task.is_album else "item"))

        # skip empty albums (coming from a previous failed import session)
        if task.is_album:
            real_duplicates = [dup for dup in found_duplicates if dup.items()]
            if not real_duplicates:
                log.info("All duplicates are empty, we ignore them")
                task.should_remove_duplicates = True
                return
        else:
            real_duplicates = found_duplicates

        if config['import']['quiet']:
            # In quiet mode, don't prompt -- just skip.
            log.info(u'Skipping.')
            sel = 's'
        else:
            # Print some detail about the existing and new items so the
            # user can make an informed decision.
            for duplicate in real_duplicates:
                print_("Old: " + summarize_items(
                    list(duplicate.items()) if task.is_album else [duplicate],
                    not task.is_album,
                ))

            if real_duplicates != found_duplicates:  # there's empty albums
                count = len(found_duplicates) - len(real_duplicates)
                print_("Old: {0} empty album{1}".format(
                       count, "s" if count > 1 else ""))

            print_("New: " + summarize_items(
                task.imported_items(),
                not task.is_album,
            ))

            sel = ui.input_options(
                ('Skip new', 'Keep both', 'Remove old')
            )

        if sel == 's':
            # Skip new.
            task.set_choice(importer.action.SKIP)
        elif sel == 'k':
            # Keep both. Do nothing; leave the choice intact.
            pass
        elif sel == 'r':
            # Remove old.
            task.should_remove_duplicates = True
        else:
            assert False

    def should_resume(self, path):
        return ui.input_yn(u"Import of the directory:\n{0}\n"
                           "was interrupted. Resume (Y/n)?"
                           .format(displayable_path(path)))

# The import command.


def import_files(lib, paths, query):
    """Import the files in the given list of paths or matching the
    query.
    """
    # Check the user-specified directories.
    for path in paths:
        if not os.path.exists(syspath(normpath(path))):
            raise ui.UserError(u'no such file or directory: {0}'.format(
                displayable_path(path)))

    # Check parameter consistency.
    if config['import']['quiet'] and config['import']['timid']:
        raise ui.UserError("can't be both quiet and timid")

    # Open the log.
    if config['import']['log'].get() is not None:
        logpath = syspath(config['import']['log'].as_filename())
        try:
            loghandler = logging.FileHandler(logpath)
        except IOError:
            raise ui.UserError(u"could not open log file for writing: "
                               u"{0}".format(displayable_path(logpath)))
    else:
        loghandler = None

    # Never ask for input in quiet mode.
    if config['import']['resume'].get() == 'ask' and \
            config['import']['quiet']:
        config['import']['resume'] = False

    session = TerminalImportSession(lib, loghandler, paths, query)
    session.run()

    # Emit event.
    plugins.send('import', lib=lib, paths=paths)


# TODO: add 'imp' and 'im' aliases
@click.command('import', short_help='import new music')
@click.option('copy', '-c', '--copy', flag_value=True,
              help='copy tracks into library directory (default)')
@click.option('copy', '-C', '--nocopy', flag_value=False, default=None,
              help="don't copy tracks (opposite of -c)")
@click.option('write', '-w', '--write', flag_value=True,
              help="write new metadata to files' tags (default)")
@click.option('write', '-W', '--nowrite', flag_value=False, default=None,
              help="don't write metadata (opposite of -w)")
@click.option('autotag', '-a', '--autotag', flag_value=True,
              help='infer tags for imported files (default)')
@click.option('autotag', '-A', '--noautotag', flag_value=False, default=None,
              help="don't infer tags for imported files (opposite of -a)")
@click.option('resume', '-p', '--resume', flag_value=True,
              help='resume importing if interrupted')
@click.option('resume', '-P', '--noresume', flag_value=False, default=None,
              help='resume importing if interrupted')
@click.option('-q', '--quiet', is_flag=True, default=None,
              help='never prompt for input: skip albums instead')
@click.option('-l', '--log', metavar='LOG', default=None,
              help='file to log untaggable albums for later review')
@click.option('-s', '--singletons', is_flag=True, default=None,
              help='import individual tracks instead of full albums')
@click.option('-t', '--timid', is_flag=True, default=None,
              help='always confirm all actions')
@click.option('-L', '--library', metavar='LIBRARY', default=None,
              help='retag items matching a query')
@click.option('incremental', '-i', '--incremental', flag_value=True,
              help='skip already-import directories')
@click.option('incremental', '-I', '--noincremental', flag_value=False,
              default=None, help='do not skip already-imported directories')
@click.option('--flat', is_flag=True, default=None,
              help='import an entire tree as a single album')
@click.option('-g', '--group-albums', is_flag=True, default=None,
              help='group tracks in a folder into separate albums')
@click.option('--pretend', is_flag=True, default=None,
              help='just print the files to import')
@click.argument('query', nargs=-1)
@ui.pass_context
def import_cmd(ctx, query, **opts):
    config['import'].set_args(opts)

    # Special case: --copy flag suppresses import_move (which would
    # otherwise take precedence).
    if opts['copy']:
        config['import']['move'] = False

    if opts['library']:
        query = decargs(query)
        paths = []
    else:
        query = None
        paths = query
        if not paths:
            raise ui.UserError('no path specified')

    import_files(ctx.lib, paths, query)


default_commands.append(import_cmd)


# list: Query and show library contents.

def list_items(lib, query, album, fmt=''):
    """Print out items in lib matching query. If album, then search for
    albums instead of single items.
    """
    if album:
        for album in lib.albums(query):
            ui.print_(format(album, fmt))
    else:
        for item in lib.items(query):
            ui.print_(format(item, fmt))


# TODO: add 'ls' alias
@click.command('list', short_help='query the library')
@click.argument('query', nargs=-1)
@ui.all_common_options
@ui.pass_context
def list_cmd(ctx, query, album, path):
    list_items(ctx.lib, query, album)


default_commands.append(list_cmd)


# update: Update library contents according to on-disk tags.

def update_items(lib, query, album, move, pretend):
    """For all the items matched by the query, update the library to
    reflect the item's embedded tags.
    """
    with lib.transaction():
        items, _ = _do_query(lib, query, album)

        # Walk through the items and pick up their changes.
        affected_albums = set()
        for item in items:
            # Item deleted?
            if not os.path.exists(syspath(item.path)):
                ui.print_(format(item))
                ui.print_(ui.colorize('text_error', u'  deleted'))
                if not pretend:
                    item.remove(True)
                affected_albums.add(item.album_id)
                continue

            # Did the item change since last checked?
            if item.current_mtime() <= item.mtime:
                log.debug(u'skipping {0} because mtime is up to date ({1})',
                          displayable_path(item.path), item.mtime)
                continue

            # Read new data.
            try:
                item.read()
            except library.ReadError as exc:
                log.error(u'error reading {0}: {1}',
                          displayable_path(item.path), exc)
                continue

            # Special-case album artist when it matches track artist. (Hacky
            # but necessary for preserving album-level metadata for non-
            # autotagged imports.)
            if not item.albumartist:
                old_item = lib.get_item(item.id)
                if old_item.albumartist == old_item.artist == item.artist:
                    item.albumartist = old_item.albumartist
                    item._dirty.discard('albumartist')

            # Check for and display changes.
            changed = ui.show_model_changes(item,
                                            fields=library.Item._media_fields)

            # Save changes.
            if not pretend:
                if changed:
                    # Move the item if it's in the library.
                    if move and lib.directory in ancestry(item.path):
                        item.move()

                    item.store()
                    affected_albums.add(item.album_id)
                else:
                    # The file's mtime was different, but there were no
                    # changes to the metadata. Store the new mtime,
                    # which is set in the call to read(), so we don't
                    # check this again in the future.
                    item.store()

        # Skip album changes while pretending.
        if pretend:
            return

        # Modify affected albums to reflect changes in their items.
        for album_id in affected_albums:
            if album_id is None:  # Singletons.
                continue
            album = lib.get_album(album_id)
            if not album:  # Empty albums have already been removed.
                log.debug(u'emptied album {0}', album_id)
                continue
            first_item = album.items().get()

            # Update album structure to reflect an item in it.
            for key in library.Album.item_keys:
                album[key] = first_item[key]
            album.store()

            # Move album art (and any inconsistent items).
            if move and lib.directory in ancestry(first_item.path):
                log.debug(u'moving album {0}', album_id)
                album.move()


# TODO: add 'up' and 'upd' aliases
@click.command('update', short_help='update the library')
@ui.album_option
@ui.format_option()
@click.option('move', '-M', '--nomove', is_flag=True, default=True,
              help="don't move files in library")
@click.option('-p', '--pretend', is_flag=True,
              help='show all changes but do nothing')
@click.argument('query', nargs=-1)
@ui.pass_context
def update_cmd(ctx, query, album, move, pretend):
    update_items(ctx.lib, query, album, move, pretend)


default_commands.append(update_cmd)


# remove: Remove items from library, delete files.

def remove_items(lib, query, album, delete):
    """Remove items matching query from lib. If album, then match and
    remove whole albums. If delete, also remove files from disk.
    """
    # Get the matching items.
    items, albums = _do_query(lib, query, album)

    # Prepare confirmation with user.
    print_()
    if delete:
        fmt = u'$path - $title'
        prompt = 'Really DELETE %i files (y/n)?' % len(items)
    else:
        fmt = ''
        prompt = 'Really remove %i items from the library (y/n)?' % \
                 len(items)

    # Show all the items.
    for item in items:
        ui.print_(format(item, fmt))

    # Confirm with user.
    if not ui.input_yn(prompt, True):
        return

    # Remove (and possibly delete) items.
    with lib.transaction():
        for obj in (albums if album else items):
            obj.remove(delete)


# TODO: add 'rm' alias
@click.command('remove', short_help='remove matching items from the library')
@click.option('-d', '--delete', is_flag=True,
              help='also remove files from disk')
@ui.album_option
@click.argument('query', nargs=-1)
@ui.pass_context
def remove_cmd(ctx, query, album, delete):
    remove_items(ctx.lib, query, album, delete)


default_commands.append(remove_cmd)


# stats: Show library/query statistics.

@click.command('stats',
               short_help='show statistics about the library or a query')
@click.option('-e', '--exact', is_flag=True, help='exact size and time')
@click.argument('query', nargs=-1)
@ui.pass_context
def stats_cmd(ctx, query, exact):
    """Shows some statistics about the matched items."""
    items = ctx.lib.items(query)

    total_size = 0
    total_time = 0.0
    total_items = 0
    artists = set()
    albums = set()
    album_artists = set()

    for item in items:
        if exact:
            total_size += os.path.getsize(item.path)
        else:
            total_size += int(item.length * item.bitrate / 8)
        total_time += item.length
        total_items += 1
        artists.add(item.artist)
        album_artists.add(item.albumartist)
        if item.album_id:
            albums.add(item.album_id)

    size_str = '' + ui.human_bytes(total_size)
    if exact:
        size_str += ' ({0} bytes)'.format(total_size)

    print_("""Tracks: {0}
Total time: {1}{2}
{3}: {4}
Artists: {5}
Albums: {6}
Album artists: {7}""".format(
        total_items,
        ui.human_seconds(total_time),
        ' ({0:.2f} seconds)'.format(total_time) if exact else '',
        'Total size' if exact else 'Approximate total size',
        size_str,
        len(artists),
        len(albums),
        len(album_artists)),
    )


default_commands.append(stats_cmd)


# version: Show current beets version.

@click.command('version', short_help='output version information')
def version_cmd():
    print_('beets version %s' % beets.__version__)
    # Show plugins.
    names = sorted(p.name for p in plugins.find_plugins())
    if names:
        print_('plugins:', ', '.join(names))
    else:
        print_('no plugins loaded')


default_commands.append(version_cmd)


# modify: Declaratively change metadata.

def modify_items(lib, mods, dels, query, write, move, album, confirm):
    """Modifies matching items according to user-specified assignments and
    deletions.

    `mods` is a dictionary of field and value pairse indicating
    assignments. `dels` is a list of fields to be deleted.
    """
    # Parse key=value specifications into a dictionary.
    model_cls = library.Album if album else library.Item

    for key, value in mods.items():
        mods[key] = model_cls._parse(key, value)

    # Get the items to modify.
    items, albums = _do_query(lib, query, album, False)
    objs = albums if album else items

    # Apply changes *temporarily*, preview them, and collect modified
    # objects.
    print_('Modifying {0} {1}s.'
           .format(len(objs), 'album' if album else 'item'))
    changed = set()
    for obj in objs:
        obj.update(mods)
        for field in dels:
            try:
                del obj[field]
            except KeyError:
                pass
        if ui.show_model_changes(obj):
            changed.add(obj)

    # Still something to do?
    if not changed:
        print_('No changes to make.')
        return

    # Confirm action.
    if confirm:
        if write and move:
            extra = ', move and write tags'
        elif write:
            extra = ' and write tags'
        elif move:
            extra = ' and move'
        else:
            extra = ''

        if not ui.input_yn('Really modify%s (Y/n)?' % extra):
            return

    # Apply changes to database and files
    with lib.transaction():
        for obj in changed:
            if move:
                cur_path = obj.path
                if lib.directory in ancestry(cur_path):  # In library?
                    log.debug(u'moving object {0}', displayable_path(cur_path))
                    obj.move()

            obj.try_sync(write)


def modify_parse_args(args):
    """Split the arguments for the modify subcommand into query parts,
    assignments (field=value), and deletions (field!).  Returns the result as
    a three-tuple in that order.
    """
    mods = {}
    dels = []
    query = []
    for arg in args:
        if arg.endswith('!') and '=' not in arg and ':' not in arg:
            dels.append(arg[:-1])  # Strip trailing !.
        elif '=' in arg and ':' not in arg.split('=', 1)[0]:
            key, val = arg.split('=', 1)
            mods[key] = val
        else:
            query.append(arg)
    return query, mods, dels


# TODO: add 'mod' alias
@click.command('modify', short_help='change metadata fields')
@click.option('move', '-M', '--nomove', is_flag=True, default=True,
              help="don't move files in library")
@click.option('write', '-w', '--write', flag_value=True,
              help="write new metadata to files' tags (default)")
@click.option('write', '-W', '--nowrite', flag_value=False, default=None,
              help="don't write metadata (opposite of -w)")
@ui.album_option
@ui.format_option(target='item')
@click.option('-y', '--yes', is_flag=True, help='skip_confirmation')
@click.argument('query', nargs=-1)
@ui.pass_context
def modify_cmd(ctx, query, write, move, album, yes):
    query, mods, dels = modify_parse_args(query)
    if not mods and not dels:
        raise ui.UserError('no modifications specified')
    write = write if write is not None else \
        config['import']['write'].get(bool)
    modify_items(ctx.lib, mods, dels, query, write, move, album, not yes)


default_commands.append(modify_cmd)


# move: Move/copy files to the library or a new base directory.

def move_items(lib, dest, query, copy, album):
    """Moves or copies items to a new base directory, given by dest. If
    dest is None, then the library's base directory is used, making the
    command "consolidate" files.
    """
    items, albums = _do_query(lib, query, album, False)
    objs = albums if album else items

    action = 'Copying' if copy else 'Moving'
    entity = 'album' if album else 'item'
    log.info(u'{0} {1} {2}s.', action, len(objs), entity)
    for obj in objs:
        log.debug(u'moving: {0}', util.displayable_path(obj.path))

        obj.move(copy, basedir=dest)
        obj.store()


# TODO: add 'mv' alias
@click.command('move', short_help='move or copy items')
@click.option('-d', '--dest', metavar='DIR', help='destination directory')
@click.option('-c', '--copy', is_flag=True, help='copy instead of moving')
@ui.album_option
@click.argument('query', nargs=-1)
@ui.pass_context
def move_cmd(ctx, dest, query, copy, album):
    if dest is not None:
        dest = normpath(dest)
        if not os.path.isdir(dest):
            raise ui.UserError('no such directory: {}'.format(dest))

    move_items(ctx.lib, dest, query, copy, album)


default_commands.append(move_cmd)


# write: Write tags into files.

def write_items(lib, query, pretend, force):
    """Write tag information from the database to the respective files
    in the filesystem.
    """
    items, albums = _do_query(lib, query, False, False)

    for item in items:
        # Item deleted?
        if not os.path.exists(syspath(item.path)):
            log.info(u'missing file: {0}', util.displayable_path(item.path))
            continue

        # Get an Item object reflecting the "clean" (on-disk) state.
        try:
            clean_item = library.Item.from_path(item.path)
        except library.ReadError as exc:
            log.error(u'error reading {0}: {1}',
                      displayable_path(item.path), exc)
            continue

        # Check for and display changes.
        changed = ui.show_model_changes(item, clean_item,
                                        library.Item._media_tag_fields, force)
        if (changed or force) and not pretend:
            item.try_sync()


@click.command('write', short_help='write tag information to files')
@click.option('-p', '--pretend', is_flag=True,
              help='show all changes but do nothing')
@click.option('-f', '--force', is_flag=True,
              help='write tags even if the existing tags match the database')
@click.argument('query', nargs=-1)
@ui.pass_context
def write_cmd(ctx, query, pretend, force):
    write_items(ctx.lib, query, pretend, force)


default_commands.append(write_cmd)


# config: Show and edit user configuration.

def config_edit(ctx, param, value):
    """Open a program to edit the user configuration.
    """
    if not value or ctx.resilient_parsing:
        return

    path = config.user_config_path()

    editor = os.environ.get('EDITOR')

    try:
        util.interactive_open(path, editor)
        ctx.exit()
    except OSError as exc:
        message = "Could not edit configuration: {0}".format(exc)
        if not editor:
            message += ". Please set the EDITOR environment variable"
        raise ui.UserError(message)


@click.command('config', short_help='show or edit the user configuration')
@click.option('-p', '--paths', is_flag=True,
              help='Show files that configuration was loaded from.')
@click.option('-e', '--edit', is_flag=True, callback=config_edit,
              help='Edit user configuration with $EDITOR.')
@click.option('-d', '--defaults', is_flag=True,
              help='Include the default configuration.')
@click.option('-c', '--clear', 'redact', is_flag=True, default=True,
              help='Do not redact sensitive fields.')
def config_cmd(*args, **opts):
    # Make sure lazy configuration is loaded
    config.resolve()

    # Print paths.
    if opts['paths']:
        filenames = []
        for source in config.sources:
            if not opts['defaults'] and source.default:
                continue
            if source.filename:
                filenames.append(source.filename)

        # In case the user config file does not exist, prepend it to the
        # list.
        user_path = config.user_config_path()
        if user_path not in filenames:
            filenames.insert(0, user_path)

        for filename in filenames:
            print_(filename)

    # Open in editor.
    elif opts['edit']:
        config_edit()

    # Dump configuration.
    else:
        print_(config.dump(full=opts['defaults'], redact=opts['redact']))

default_commands.append(config_cmd)


# completion: print completion script

def print_completion(*args):
    for line in completion_script(default_commands + plugins.commands()):
        print_(line, end='')
    if not any(map(os.path.isfile, BASH_COMPLETION_PATHS)):
        log.warn(u'Warning: Unable to find the bash-completion package. '
                 u'Command line completion might not work.')

BASH_COMPLETION_PATHS = map(syspath, [
    u'/etc/bash_completion',
    u'/usr/share/bash-completion/bash_completion',
    u'/usr/share/local/bash-completion/bash_completion',
    u'/opt/local/share/bash-completion/bash_completion',  # SmartOS
    u'/usr/local/etc/bash_completion',  # Homebrew
])


def completion_script(commands):
    """Yield the full completion shell script as strings.

    ``commands`` is alist of ``ui.Subcommand`` instances to generate
    completion data for.
    """
    base_script = os.path.join(_package_path('beets.ui'), 'completion_base.sh')
    with open(base_script, 'r') as base_script:
        yield base_script.read()

    options = {}
    aliases = {}
    command_names = []

    # Collect subcommands
    for cmd in commands:
        name = cmd.name
        command_names.append(name)

        for alias in cmd.aliases:
            if re.match(r'^\w+$', alias):
                aliases[alias] = name

        options[name] = {'flags': [], 'opts': []}
        for opts in cmd.parser._get_all_options()[1:]:
            if opts.action in ('store_true', 'store_false'):
                option_type = 'flags'
            else:
                option_type = 'opts'

            options[name][option_type].extend(
                opts._short_opts + opts._long_opts
            )

    # Add global options
    options['_global'] = {
        'flags': ['-v', '--verbose'],
        'opts': '-l --library -c --config -d --directory -h --help'.split(' ')
    }

    # Add flags common to all commands
    options['_common'] = {
        'flags': ['-h', '--help']
    }

    # Start generating the script
    yield "_beet() {\n"

    # Command names
    yield "  local commands='%s'\n" % ' '.join(command_names)
    yield "\n"

    # Command aliases
    yield "  local aliases='%s'\n" % ' '.join(aliases.keys())
    for alias, cmd in aliases.items():
        yield "  local alias__%s=%s\n" % (alias, cmd)
    yield '\n'

    # Fields
    yield "  fields='%s'\n" % ' '.join(
        set(library.Item._fields.keys() + library.Album._fields.keys())
    )

    # Command options
    for cmd, opts in options.items():
        for option_type, option_list in opts.items():
            if option_list:
                option_list = ' '.join(option_list)
                yield "  local %s__%s='%s'\n" % (option_type, cmd, option_list)

    yield '  _beet_dispatch\n'
    yield '}\n'


completion_cmd = ui.Subcommand(
    'completion',
    help='print shell script that provides command line completion'
)
completion_cmd.func = print_completion
completion_cmd.hide = True
default_commands.append(completion_cmd)
