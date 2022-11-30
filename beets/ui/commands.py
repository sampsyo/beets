# This file is part of beets.
# Copyright 2016, Adrian Sampson.
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


import os
import re
from platform import python_version
from collections import namedtuple, Counter
from itertools import chain

import beets
from beets import ui
from beets.ui import print_, input_, decargs, show_path_changes
from beets import autotag
from beets.autotag import Recommendation
from beets.autotag import hooks
from beets import plugins
from beets import importer
from beets import util
from beets.util import syspath, normpath, ancestry, displayable_path, \
    MoveOperation, functemplate
from beets import library
from beets import config
from beets import logging

from . import _store_dict

VARIOUS_ARTISTS = 'Various Artists'
PromptChoice = namedtuple('PromptChoice', ['short', 'long', 'callback'])

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


def _paths_from_logfile(path):
    """Parse the logfile and yield skipped paths to pass to the `import`
    command.
    """
    with open(path, mode="r", encoding="utf-8") as fp:
        for i, line in enumerate(fp, start=1):
            verb, sep, paths = line.rstrip("\n").partition(" ")
            if not sep:
                raise ValueError(f"line {i} is invalid")

            # Ignore informational lines that don't need to be re-imported.
            if verb in {"import", "duplicate-keep", "duplicate-replace"}:
                continue

            if verb not in {"asis", "skip", "duplicate-skip"}:
                raise ValueError(f"line {i} contains unknown verb {verb}")

            yield os.path.commonpath(paths.split("; "))


def _parse_logfiles(logfiles):
    """Parse all `logfiles` and yield paths from it."""
    for logfile in logfiles:
        try:
            yield from _paths_from_logfile(syspath(normpath(logfile)))
        except ValueError as err:
            raise ui.UserError('malformed logfile {}: {}'.format(
                util.displayable_path(logfile),
                str(err)
            )) from err
        except IOError as err:
            raise ui.UserError('unreadable logfile {}: {}'.format(
                util.displayable_path(logfile),
                str(err)
            )) from err


# fields: Shows a list of available fields for queries and format strings.

def _print_keys(query):
    """Given a SQLite query result, print the `key` field of each
    returned row, with indentation of 2 spaces.
    """
    for row in query:
        print_(' ' * 2 + row['key'])


def fields_func(lib, opts, args):
    def _print_rows(names):
        names.sort()
        print_('  ' + '\n  '.join(names))

    print_("Item fields:")
    _print_rows(library.Item.all_keys())

    print_("Album fields:")
    _print_rows(library.Album.all_keys())

    with lib.transaction() as tx:
        # The SQL uses the DISTINCT to get unique values from the query
        unique_fields = 'SELECT DISTINCT key FROM (%s)'

        print_("Item flexible attributes:")
        _print_keys(tx.query(unique_fields % library.Item._flex_table))

        print_("Album flexible attributes:")
        _print_keys(tx.query(unique_fields % library.Album._flex_table))


fields_cmd = ui.Subcommand(
    'fields',
    help='show fields available for queries and format strings'
)
fields_cmd.func = fields_func
default_commands.append(fields_cmd)


# help: Print help text for commands

class HelpCommand(ui.Subcommand):

    def __init__(self):
        super().__init__(
            'help', aliases=('?',),
            help='give detailed help on a specific sub-command',
        )

    def func(self, lib, opts, args):
        if args:
            cmdname = args[0]
            helpcommand = self.root_parser._subcommand_for_name(cmdname)
            if not helpcommand:
                raise ui.UserError(f"unknown command '{cmdname}'")
            helpcommand.print_help()
        else:
            self.root_parser.print_help()


default_commands.append(HelpCommand())


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
            if info.mediums and info.mediums > 1:
                disambig.append('{}x{}'.format(
                    info.mediums, info.media
                ))
            else:
                disambig.append(info.media)
        if info.year:
            disambig.append(str(info.year))
        if info.country:
            disambig.append(info.country)
        if info.label:
            disambig.append(info.label)
        if info.catalognum:
            disambig.append(info.catalognum)
        if info.albumdisambig:
            disambig.append(info.albumdisambig)

    if disambig:
        return ', '.join(disambig)


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
            album_description = f'    {artist} - {album}'
        elif album:
            album_description = '    %s' % album
        else:
            album_description = '    (unknown album)'
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
            if mediums and mediums > 1:
                return f'{medium}-{medium_index}'
            else:
                return str(medium_index if medium_index is not None
                           else index)
        else:
            return str(index)

    # Identify the album in question.
    if cur_artist != match.info.artist or \
            (cur_album != match.info.album and
             match.info.album != VARIOUS_ARTISTS):
        artist_l, artist_r = cur_artist or '', match.info.artist
        album_l, album_r = cur_album or '', match.info.album
        if artist_r == VARIOUS_ARTISTS:
            # Hide artists for VA releases.
            artist_l, artist_r = '', ''

        if config['artist_credit']:
            artist_r = match.info.artist_credit

        artist_l, artist_r = ui.colordiff(artist_l, artist_r)
        album_l, album_r = ui.colordiff(album_l, album_r)

        print_("Correcting tags from:")
        show_album(artist_l, album_l)
        print_("To:")
        show_album(artist_r, album_r)
    else:
        print_("Tagging:\n    {0.artist} - {0.album}".format(match.info))

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
    pairs = list(match.mapping.items())
    pairs.sort(key=lambda item_and_track_info: item_and_track_info[1].index)

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
                lhs = '{} {}: {}'.format(media, track_info.medium,
                                         track_info.disctitle)
            elif match.info.mediums > 1:
                lhs = f'{media} {track_info.medium}'
            elif track_info.disctitle:
                lhs = f'{media}: {track_info.disctitle}'
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
            templ = ui.colorize(color, ' (#{0})')
            lhs += templ.format(cur_track)
            rhs += templ.format(new_track)
            lhs_width += len(cur_track) + 4

        # Length change.
        if item.length and track_info.length and \
                abs(item.length - track_info.length) > \
                config['ui']['length_diff_thresh'].as_number():
            cur_length = ui.human_seconds_short(item.length)
            new_length = ui.human_seconds_short(track_info.length)
            templ = ui.colorize('text_highlight', ' ({0})')
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
                print_(f'{lhs} ->\n   {rhs}')
            else:
                pad = max_width - lhs_width
                print_('{}{} -> {}'.format(lhs, ' ' * pad, rhs))

    # Missing and unmatched tracks.
    if match.extra_tracks:
        print_('Missing tracks ({}/{} - {:.1%}):'.format(
               len(match.extra_tracks),
               len(match.info.tracks),
               len(match.extra_tracks) / len(match.info.tracks)
               ))
        pad_width = max(len(track_info.title) for track_info in
                        match.extra_tracks)
    for track_info in match.extra_tracks:
        line = ' ! {0: <{width}} (#{1: >2})'.format(track_info.title,
                                                    format_index(track_info),
                                                    width=pad_width)
        if track_info.length:
            line += ' (%s)' % ui.human_seconds_short(track_info.length)
        print_(ui.colorize('text_warning', line))
    if match.extra_items:
        print_('Unmatched tracks ({}):'.format(len(match.extra_items)))
        pad_width = max(len(item.title) for item in match.extra_items)
    for item in match.extra_items:
        line = ' ! {0: <{width}} (#{1: >2})'.format(item.title,
                                                    format_index(item),
                                                    width=pad_width)
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
        print_(f"    {cur_artist} - {cur_title}")
        print_("To:")
        print_(f"    {new_artist} - {new_title}")

    else:
        print_(f"Tagging track: {cur_artist} - {cur_title}")

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
        summary_parts.append("{} items".format(len(items)))

    format_counts = {}
    for item in items:
        format_counts[item.format] = format_counts.get(item.format, 0) + 1
    if len(format_counts) == 1:
        # A single format.
        summary_parts.append(items[0].format)
    else:
        # Enumerate all the formats by decreasing frequencies:
        for fmt, count in sorted(
            format_counts.items(),
            key=lambda fmt_and_count: (-fmt_and_count[1], fmt_and_count[0])
        ):
            summary_parts.append(f'{fmt} {count}')

    if items:
        average_bitrate = sum([item.bitrate for item in items]) / len(items)
        total_duration = sum([item.length for item in items])
        total_filesize = sum([item.filesize for item in items])
        summary_parts.append('{}kbps'.format(int(average_bitrate / 1000)))
        if items[0].format == "FLAC":
            sample_bits = '{}kHz/{} bit'.format(
                round(int(items[0].samplerate) / 1000, 1), items[0].bitdepth)
            summary_parts.append(sample_bits)
        summary_parts.append(ui.human_seconds_short(total_duration))
        summary_parts.append(ui.human_bytes(total_filesize))

    return ', '.join(summary_parts)


def _summary_judgment(rec):
    """Determines whether a decision should be made without even asking
    the user. This occurs in quiet mode and when an action is chosen for
    NONE recommendations. Return None if the user should be queried.
    Otherwise, returns an action. May also print to the console if a
    summary judgment is made.
    """

    if config['import']['quiet']:
        if rec == Recommendation.strong:
            return importer.action.APPLY
        else:
            action = config['import']['quiet_fallback'].as_choice({
                'skip': importer.action.SKIP,
                'asis': importer.action.ASIS,
            })
    elif config['import']['timid']:
        return None
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
                     cur_album=None, item=None, itemcount=None,
                     choices=[]):
    """Given a sorted list of candidates, ask the user for a selection
    of which candidate to use. Applies to both full albums and
    singletons  (tracks). Candidates are either AlbumMatch or TrackMatch
    objects depending on `singleton`. for albums, `cur_artist`,
    `cur_album`, and `itemcount` must be provided. For singletons,
    `item` must be provided.

    `choices` is a list of `PromptChoice`s to be used in each prompt.

    Returns one of the following:
    * the result of the choice, which may be SKIP or ASIS
    * a candidate (an AlbumMatch/TrackMatch object)
    * a chosen `PromptChoice` from `choices`
    """
    # Sanity check.
    if singleton:
        assert item is not None
    else:
        assert cur_artist is not None
        assert cur_album is not None

    # Build helper variables for the prompt choices.
    choice_opts = tuple(c.long for c in choices)
    choice_actions = {c.short: c for c in choices}

    # Zero candidates.
    if not candidates:
        if singleton:
            print_("No matching recordings found.")
        else:
            print_("No matching release found for {} tracks."
                   .format(itemcount))
            print_('For help, see: '
                   'https://beets.readthedocs.org/en/latest/faq.html#nomatch')
        sel = ui.input_options(choice_opts)
        if sel in choice_actions:
            return choice_actions[sel]
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
            print_('Finding tags for {} "{} - {}".'.format(
                'track' if singleton else 'album',
                item.artist if singleton else cur_artist,
                item.title if singleton else cur_album,
            ))

            print_('Candidates:')
            for i, match in enumerate(candidates):
                # Index, metadata, and distance.
                line = [
                    '{}.'.format(i + 1),
                    '{} - {}'.format(
                        match.info.artist,
                        match.info.title if singleton else match.info.album,
                    ),
                    '({})'.format(dist_string(match.distance)),
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
            sel = ui.input_options(choice_opts,
                                   numrange=(1, len(candidates)))
            if sel == 'm':
                pass
            elif sel in choice_actions:
                return choice_actions[sel]
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
            plugins.send('matchinfo_received', match=match)
            return match

        # Ask for confirmation.
        default = config['import']['default_action'].as_choice({
            'apply': 'a',
            'skip': 's',
            'asis': 'u',
            'none': None,
        })
        if default is None:
            require = True
        # Bell ring when user interaction is needed.
        if config['import']['bell']:
            ui.print_('\a', end='')
        sel = ui.input_options(('Apply', 'More candidates') + choice_opts,
                               require=require, default=default)
        if sel == 'a':
            plugins.send('matchinfo_received', match=match)
            return match
        elif sel in choice_actions:
            return choice_actions[sel]


def manual_search(session, task):
    """Get a new `Proposal` using manual search criteria.

    Input either an artist and album (for full albums) or artist and
    track name (for singletons) for manual search.
    """
    artist = input_('Artist:').strip()
    name = input_('Album:' if task.is_album else 'Track:').strip()

    if task.is_album:
        _, _, prop = autotag.tag_album(
            task.items, artist, name
        )
        return prop
    else:
        return autotag.tag_item(task.item, artist, name)


def manual_id(session, task):
    """Get a new `Proposal` using a manually-entered ID.

    Input an ID, either for an album ("release") or a track ("recording").
    """
    prompt = 'Enter {} ID:'.format('release' if task.is_album
                                   else 'recording')
    search_id = input_(prompt).strip()

    if task.is_album:
        _, _, prop = autotag.tag_album(
            task.items, search_ids=search_id.split()
        )
        return prop
    else:
        return autotag.tag_item(task.item, search_ids=search_id.split())


def abort_action(session, task):
    """A prompt choice callback that aborts the importer.
    """
    raise importer.ImportAbort()


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
        print_(displayable_path(task.paths, '\n') +
               ' ({} items)'.format(len(task.items)))

        # Let plugins display info or prompt the user before we go through the
        # process of selecting candidate.
        results = plugins.send('import_task_before_choice',
                               session=self, task=task)
        actions = [action for action in results if action]

        if len(actions) == 1:
            return actions[0]
        elif len(actions) > 1:
            raise plugins.PluginConflictException(
                'Only one handler for `import_task_before_choice` may return '
                'an action.')

        # Take immediate action if appropriate.
        action = _summary_judgment(task.rec)
        if action == importer.action.APPLY:
            match = task.candidates[0]
            show_change(task.cur_artist, task.cur_album, match)
            return match
        elif action is not None:
            return action

        # Loop until we have a choice.
        while True:
            # Ask for a choice from the user. The result of
            # `choose_candidate` may be an `importer.action`, an
            # `AlbumMatch` object for a specific selection, or a
            # `PromptChoice`.
            choices = self._get_choices(task)
            choice = choose_candidate(
                task.candidates, False, task.rec, task.cur_artist,
                task.cur_album, itemcount=len(task.items), choices=choices
            )

            # Basic choices that require no more action here.
            if choice in (importer.action.SKIP, importer.action.ASIS):
                # Pass selection to main control flow.
                return choice

            # Plugin-provided choices. We invoke the associated callback
            # function.
            elif choice in choices:
                post_choice = choice.callback(self, task)
                if isinstance(post_choice, importer.action):
                    return post_choice
                elif isinstance(post_choice, autotag.Proposal):
                    # Use the new candidates and continue around the loop.
                    task.candidates = post_choice.candidates
                    task.rec = post_choice.recommendation

            # Otherwise, we have a specific match selection.
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
        print_(displayable_path(task.item.path))
        candidates, rec = task.candidates, task.rec

        # Take immediate action if appropriate.
        action = _summary_judgment(task.rec)
        if action == importer.action.APPLY:
            match = candidates[0]
            show_item_change(task.item, match)
            return match
        elif action is not None:
            return action

        while True:
            # Ask for a choice.
            choices = self._get_choices(task)
            choice = choose_candidate(candidates, True, rec, item=task.item,
                                      choices=choices)

            if choice in (importer.action.SKIP, importer.action.ASIS):
                return choice

            elif choice in choices:
                post_choice = choice.callback(self, task)
                if isinstance(post_choice, importer.action):
                    return post_choice
                elif isinstance(post_choice, autotag.Proposal):
                    candidates = post_choice.candidates
                    rec = post_choice.recommendation

            else:
                # Chose a candidate.
                assert isinstance(choice, autotag.TrackMatch)
                return choice

    def resolve_duplicate(self, task, found_duplicates):
        """Decide what to do when a new album or item seems similar to one
        that's already in the library.
        """
        log.warning("This {0} is already in the library!",
                    ("album" if task.is_album else "item"))

        if config['import']['quiet']:
            # In quiet mode, don't prompt -- just skip.
            log.info('Skipping.')
            sel = 's'
        else:
            # Print some detail about the existing and new items so the
            # user can make an informed decision.
            for duplicate in found_duplicates:
                print_("Old: " + summarize_items(
                    list(duplicate.items()) if task.is_album else [duplicate],
                    not task.is_album,
                ))

            print_("New: " + summarize_items(
                task.imported_items(),
                not task.is_album,
            ))

            sel = ui.input_options(
                ('Skip new', 'Keep all', 'Remove old', 'Merge all')
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
        elif sel == 'm':
            task.should_merge_duplicates = True
        else:
            assert False

    def should_resume(self, path):
        return ui.input_yn("Import of the directory:\n{}\n"
                           "was interrupted. Resume (Y/n)?"
                           .format(displayable_path(path)))

    def _get_choices(self, task):
        """Get the list of prompt choices that should be presented to the
        user. This consists of both built-in choices and ones provided by
        plugins.

        The `before_choose_candidate` event is sent to the plugins, with
        session and task as its parameters. Plugins are responsible for
        checking the right conditions and returning a list of `PromptChoice`s,
        which is flattened and checked for conflicts.

        If two or more choices have the same short letter, a warning is
        emitted and all but one choices are discarded, giving preference
        to the default importer choices.

        Returns a list of `PromptChoice`s.
        """
        # Standard, built-in choices.
        choices = [
            PromptChoice('s', 'Skip',
                         lambda s, t: importer.action.SKIP),
            PromptChoice('u', 'Use as-is',
                         lambda s, t: importer.action.ASIS)
        ]
        if task.is_album:
            choices += [
                PromptChoice('t', 'as Tracks',
                             lambda s, t: importer.action.TRACKS),
                PromptChoice('g', 'Group albums',
                             lambda s, t: importer.action.ALBUMS),
            ]
        choices += [
            PromptChoice('e', 'Enter search', manual_search),
            PromptChoice('i', 'enter Id', manual_id),
            PromptChoice('b', 'aBort', abort_action),
        ]

        # Send the before_choose_candidate event and flatten list.
        extra_choices = list(chain(*plugins.send('before_choose_candidate',
                                                 session=self, task=task)))

        # Add a "dummy" choice for the other baked-in option, for
        # duplicate checking.
        all_choices = [
            PromptChoice('a', 'Apply', None),
        ] + choices + extra_choices

        # Check for conflicts.
        short_letters = [c.short for c in all_choices]
        if len(short_letters) != len(set(short_letters)):
            # Duplicate short letter has been found.
            duplicates = [i for i, count in Counter(short_letters).items()
                          if count > 1]
            for short in duplicates:
                # Keep the first of the choices, removing the rest.
                dup_choices = [c for c in all_choices if c.short == short]
                for c in dup_choices[1:]:
                    log.warning("Prompt choice '{0}' removed due to conflict "
                                "with '{1}' (short letter: '{2}')",
                                c.long, dup_choices[0].long, c.short)
                    extra_choices.remove(c)

        return choices + extra_choices


# The import command.


def import_files(lib, paths, query):
    """Import the files in the given list of paths or matching the
    query.
    """
    # Check parameter consistency.
    if config['import']['quiet'] and config['import']['timid']:
        raise ui.UserError("can't be both quiet and timid")

    # Open the log.
    if config['import']['log'].get() is not None:
        logpath = syspath(config['import']['log'].as_filename())
        try:
            loghandler = logging.FileHandler(logpath)
        except OSError:
            raise ui.UserError("could not open log file for writing: "
                               "{}".format(displayable_path(logpath)))
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


def import_func(lib, opts, args):
    config['import'].set_args(opts)

    # Special case: --copy flag suppresses import_move (which would
    # otherwise take precedence).
    if opts.copy:
        config['import']['move'] = False

    if opts.library:
        query = decargs(args)
        paths = []
    else:
        query = None
        paths = args

        # The paths from the logfiles go into a separate list to allow handling
        # errors differently from user-specified paths.
        paths_from_logfiles = list(_parse_logfiles(opts.from_logfiles or []))

        if not paths and not paths_from_logfiles:
            raise ui.UserError('no path specified')

        # On Python 2, we used to get filenames as raw bytes, which is
        # what we need. On Python 3, we need to undo the "helpful"
        # conversion to Unicode strings to get the real bytestring
        # filename.
        paths = [p.encode(util.arg_encoding(), 'surrogateescape')
                 for p in paths]
        paths_from_logfiles = [p.encode(util.arg_encoding(), 'surrogateescape')
                               for p in paths_from_logfiles]

        # Check the user-specified directories.
        for path in paths:
            if not os.path.exists(syspath(normpath(path))):
                raise ui.UserError('no such file or directory: {}'.format(
                    displayable_path(path)))

        # Check the directories from the logfiles, but don't throw an error in
        # case those paths don't exist. Maybe some of those paths have already
        # been imported and moved separately, so logging a warning should
        # suffice.
        for path in paths_from_logfiles:
            if not os.path.exists(syspath(normpath(path))):
                log.warning('No such file or directory: {}'.format(
                    displayable_path(path)))
                continue

            paths.append(path)

        # If all paths were read from a logfile, and none of them exist, throw
        # an error
        if not paths:
            raise ui.UserError('none of the paths are importable')

    import_files(lib, paths, query)


import_cmd = ui.Subcommand(
    'import', help='import new music', aliases=('imp', 'im')
)
import_cmd.parser.add_option(
    '-c', '--copy', action='store_true', default=None,
    help="copy tracks into library directory (default)"
)
import_cmd.parser.add_option(
    '-C', '--nocopy', action='store_false', dest='copy',
    help="don't copy tracks (opposite of -c)"
)
import_cmd.parser.add_option(
    '-m', '--move', action='store_true', dest='move',
    help="move tracks into the library (overrides -c)"
)
import_cmd.parser.add_option(
    '-w', '--write', action='store_true', default=None,
    help="write new metadata to files' tags (default)"
)
import_cmd.parser.add_option(
    '-W', '--nowrite', action='store_false', dest='write',
    help="don't write metadata (opposite of -w)"
)
import_cmd.parser.add_option(
    '-a', '--autotag', action='store_true', dest='autotag',
    help="infer tags for imported files (default)"
)
import_cmd.parser.add_option(
    '-A', '--noautotag', action='store_false', dest='autotag',
    help="don't infer tags for imported files (opposite of -a)"
)
import_cmd.parser.add_option(
    '-p', '--resume', action='store_true', default=None,
    help="resume importing if interrupted"
)
import_cmd.parser.add_option(
    '-P', '--noresume', action='store_false', dest='resume',
    help="do not try to resume importing"
)
import_cmd.parser.add_option(
    '-q', '--quiet', action='store_true', dest='quiet',
    help="never prompt for input: skip albums instead"
)
import_cmd.parser.add_option(
    '-l', '--log', dest='log',
    help='file to log untaggable albums for later review'
)
import_cmd.parser.add_option(
    '-s', '--singletons', action='store_true',
    help='import individual tracks instead of full albums'
)
import_cmd.parser.add_option(
    '-t', '--timid', dest='timid', action='store_true',
    help='always confirm all actions'
)
import_cmd.parser.add_option(
    '-L', '--library', dest='library', action='store_true',
    help='retag items matching a query'
)
import_cmd.parser.add_option(
    '-i', '--incremental', dest='incremental', action='store_true',
    help='skip already-imported directories'
)
import_cmd.parser.add_option(
    '-I', '--noincremental', dest='incremental', action='store_false',
    help='do not skip already-imported directories'
)
import_cmd.parser.add_option(
    '--from-scratch', dest='from_scratch', action='store_true',
    help='erase existing metadata before applying new metadata'
)
import_cmd.parser.add_option(
    '--flat', dest='flat', action='store_true',
    help='import an entire tree as a single album'
)
import_cmd.parser.add_option(
    '-g', '--group-albums', dest='group_albums', action='store_true',
    help='group tracks in a folder into separate albums'
)
import_cmd.parser.add_option(
    '--pretend', dest='pretend', action='store_true',
    help='just print the files to import'
)
import_cmd.parser.add_option(
    '-S', '--search-id', dest='search_ids', action='append',
    metavar='ID',
    help='restrict matching to a specific metadata backend ID'
)
import_cmd.parser.add_option(
    '--from-logfile', dest='from_logfiles', action='append',
    metavar='PATH',
    help='read skipped paths from an existing logfile'
)
import_cmd.parser.add_option(
    '--set', dest='set_fields', action='callback',
    callback=_store_dict,
    metavar='FIELD=VALUE',
    help='set the given fields to the supplied values'
)
import_cmd.func = import_func
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


def list_func(lib, opts, args):
    list_items(lib, decargs(args), opts.album)


list_cmd = ui.Subcommand('list', help='query the library', aliases=('ls',))
list_cmd.parser.usage += "\n" \
    'Example: %prog -f \'$album: $title\' artist:beatles'
list_cmd.parser.add_all_common_options()
list_cmd.func = list_func
default_commands.append(list_cmd)


# update: Update library contents according to on-disk tags.

def update_items(lib, query, album, move, pretend, fields):
    """For all the items matched by the query, update the library to
    reflect the item's embedded tags.
    :param fields: The fields to be stored. If not specified, all fields will
    be.
    """
    with lib.transaction():
        if move and fields is not None and 'path' not in fields:
            # Special case: if an item needs to be moved, the path field has to
            # updated; otherwise the new path will not be reflected in the
            # database.
            fields.append('path')
        items, _ = _do_query(lib, query, album)

        # Walk through the items and pick up their changes.
        affected_albums = set()
        for item in items:
            # Item deleted?
            if not os.path.exists(syspath(item.path)):
                ui.print_(format(item))
                ui.print_(ui.colorize('text_error', '  deleted'))
                if not pretend:
                    item.remove(True)
                affected_albums.add(item.album_id)
                continue

            # Did the item change since last checked?
            if item.current_mtime() <= item.mtime:
                log.debug('skipping {0} because mtime is up to date ({1})',
                          displayable_path(item.path), item.mtime)
                continue

            # Read new data.
            try:
                item.read()
            except library.ReadError as exc:
                log.error('error reading {0}: {1}',
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
            changed = ui.show_model_changes(
                item,
                fields=fields or library.Item._media_fields)

            # Save changes.
            if not pretend:
                if changed:
                    # Move the item if it's in the library.
                    if move and lib.directory in ancestry(item.path):
                        item.move(store=False)

                    item.store(fields=fields)
                    affected_albums.add(item.album_id)
                else:
                    # The file's mtime was different, but there were no
                    # changes to the metadata. Store the new mtime,
                    # which is set in the call to read(), so we don't
                    # check this again in the future.
                    item.store(fields=fields)

        # Skip album changes while pretending.
        if pretend:
            return

        # Modify affected albums to reflect changes in their items.
        for album_id in affected_albums:
            if album_id is None:  # Singletons.
                continue
            album = lib.get_album(album_id)
            if not album:  # Empty albums have already been removed.
                log.debug('emptied album {0}', album_id)
                continue
            first_item = album.items().get()

            # Update album structure to reflect an item in it.
            for key in library.Album.item_keys:
                album[key] = first_item[key]
            album.store(fields=fields)

            # Move album art (and any inconsistent items).
            if move and lib.directory in ancestry(first_item.path):
                log.debug('moving album {0}', album_id)

                # Manually moving and storing the album.
                items = list(album.items())
                for item in items:
                    item.move(store=False, with_album=False)
                    item.store(fields=fields)
                album.move(store=False)
                album.store(fields=fields)


def update_func(lib, opts, args):
    # Verify that the library folder exists to prevent accidental wipes.
    if not os.path.isdir(lib.directory):
        ui.print_("Library path is unavailable or does not exist.")
        ui.print_(lib.directory)
        if not ui.input_yn("Are you sure you want to continue (y/n)?", True):
            return
    update_items(lib, decargs(args), opts.album, ui.should_move(opts.move),
                 opts.pretend, opts.fields)


update_cmd = ui.Subcommand(
    'update', help='update the library', aliases=('upd', 'up',)
)
update_cmd.parser.add_album_option()
update_cmd.parser.add_format_option()
update_cmd.parser.add_option(
    '-m', '--move', action='store_true', dest='move',
    help="move files in the library directory"
)
update_cmd.parser.add_option(
    '-M', '--nomove', action='store_false', dest='move',
    help="don't move files in library"
)
update_cmd.parser.add_option(
    '-p', '--pretend', action='store_true',
    help="show all changes but do nothing"
)
update_cmd.parser.add_option(
    '-F', '--field', default=None, action='append', dest='fields',
    help='list of fields to update'
)
update_cmd.func = update_func
default_commands.append(update_cmd)


# remove: Remove items from library, delete files.

def remove_items(lib, query, album, delete, force):
    """Remove items matching query from lib. If album, then match and
    remove whole albums. If delete, also remove files from disk.
    """
    # Get the matching items.
    items, albums = _do_query(lib, query, album)
    objs = albums if album else items

    # Confirm file removal if not forcing removal.
    if not force:
        # Prepare confirmation with user.
        album_str = " in {} album{}".format(
            len(albums), 's' if len(albums) > 1 else ''
        ) if album else ""

        if delete:
            fmt = '$path - $title'
            prompt = 'Really DELETE'
            prompt_all = 'Really DELETE {} file{}{}'.format(
                len(items), 's' if len(items) > 1 else '', album_str
            )
        else:
            fmt = ''
            prompt = 'Really remove from the library?'
            prompt_all = 'Really remove {} item{}{} from the library?'.format(
                len(items), 's' if len(items) > 1 else '', album_str
            )

        # Helpers for printing affected items
        def fmt_track(t):
            ui.print_(format(t, fmt))

        def fmt_album(a):
            ui.print_()
            for i in a.items():
                fmt_track(i)

        fmt_obj = fmt_album if album else fmt_track

        # Show all the items.
        for o in objs:
            fmt_obj(o)

        # Confirm with user.
        objs = ui.input_select_objects(prompt, objs, fmt_obj,
                                       prompt_all=prompt_all)

    if not objs:
        return

    # Remove (and possibly delete) items.
    with lib.transaction():
        for obj in objs:
            obj.remove(delete)


def remove_func(lib, opts, args):
    remove_items(lib, decargs(args), opts.album, opts.delete, opts.force)


remove_cmd = ui.Subcommand(
    'remove', help='remove matching items from the library', aliases=('rm',)
)
remove_cmd.parser.add_option(
    "-d", "--delete", action="store_true",
    help="also remove files from disk"
)
remove_cmd.parser.add_option(
    "-f", "--force", action="store_true",
    help="do not ask when removing items"
)
remove_cmd.parser.add_album_option()
remove_cmd.func = remove_func
default_commands.append(remove_cmd)


# stats: Show library/query statistics.

def show_stats(lib, query, exact):
    """Shows some statistics about the matched items."""
    items = lib.items(query)

    total_size = 0
    total_time = 0.0
    total_items = 0
    artists = set()
    albums = set()
    album_artists = set()

    for item in items:
        if exact:
            try:
                total_size += os.path.getsize(syspath(item.path))
            except OSError as exc:
                log.info('could not get size of {}: {}', item.path, exc)
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
        size_str += f' ({total_size} bytes)'

    print_("""Tracks: {}
Total time: {}{}
{}: {}
Artists: {}
Albums: {}
Album artists: {}""".format(
        total_items,
        ui.human_seconds(total_time),
        f' ({total_time:.2f} seconds)' if exact else '',
        'Total size' if exact else 'Approximate total size',
        size_str,
        len(artists),
        len(albums),
        len(album_artists)),
    )


def stats_func(lib, opts, args):
    show_stats(lib, decargs(args), opts.exact)


stats_cmd = ui.Subcommand(
    'stats', help='show statistics about the library or a query'
)
stats_cmd.parser.add_option(
    '-e', '--exact', action='store_true',
    help='exact size and time'
)
stats_cmd.func = stats_func
default_commands.append(stats_cmd)


# version: Show current beets version.

def show_version(lib, opts, args):
    print_('beets version %s' % beets.__version__)
    print_(f'Python version {python_version()}')
    # Show plugins.
    names = sorted(p.name for p in plugins.find_plugins())
    if names:
        print_('plugins:', ', '.join(names))
    else:
        print_('no plugins loaded')


version_cmd = ui.Subcommand(
    'version', help='output version information'
)
version_cmd.func = show_version
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

    # Get the items to modify.
    items, albums = _do_query(lib, query, album, False)
    objs = albums if album else items

    # Apply changes *temporarily*, preview them, and collect modified
    # objects.
    print_('Modifying {} {}s.'
           .format(len(objs), 'album' if album else 'item'))
    changed = []
    templates = {key: functemplate.template(value)
                 for key, value in mods.items()}
    for obj in objs:
        obj_mods = {
            key: model_cls._parse(key, obj.evaluate_template(templates[key]))
            for key in mods.keys()
        }
        if print_and_modify(obj, obj_mods, dels) and obj not in changed:
            changed.append(obj)

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

        changed = ui.input_select_objects(
            'Really modify%s' % extra, changed,
            lambda o: print_and_modify(o, mods, dels)
        )

    # Apply changes to database and files
    with lib.transaction():
        for obj in changed:
            obj.try_sync(write, move)


def print_and_modify(obj, mods, dels):
    """Print the modifications to an item and return a bool indicating
    whether any changes were made.

    `mods` is a dictionary of fields and values to update on the object;
    `dels` is a sequence of fields to delete.
    """
    obj.update(mods)
    for field in dels:
        try:
            del obj[field]
        except KeyError:
            pass
    return ui.show_model_changes(obj)


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


def modify_func(lib, opts, args):
    query, mods, dels = modify_parse_args(decargs(args))
    if not mods and not dels:
        raise ui.UserError('no modifications specified')
    modify_items(lib, mods, dels, query, ui.should_write(opts.write),
                 ui.should_move(opts.move), opts.album, not opts.yes)


modify_cmd = ui.Subcommand(
    'modify', help='change metadata fields', aliases=('mod',)
)
modify_cmd.parser.add_option(
    '-m', '--move', action='store_true', dest='move',
    help="move files in the library directory"
)
modify_cmd.parser.add_option(
    '-M', '--nomove', action='store_false', dest='move',
    help="don't move files in library"
)
modify_cmd.parser.add_option(
    '-w', '--write', action='store_true', default=None,
    help="write new metadata to files' tags (default)"
)
modify_cmd.parser.add_option(
    '-W', '--nowrite', action='store_false', dest='write',
    help="don't write metadata (opposite of -w)"
)
modify_cmd.parser.add_album_option()
modify_cmd.parser.add_format_option(target='item')
modify_cmd.parser.add_option(
    '-y', '--yes', action='store_true',
    help='skip confirmation'
)
modify_cmd.func = modify_func
default_commands.append(modify_cmd)


# move: Move/copy files to the library or a new base directory.

def move_items(lib, dest, query, copy, album, pretend, confirm=False,
               export=False):
    """Moves or copies items to a new base directory, given by dest. If
    dest is None, then the library's base directory is used, making the
    command "consolidate" files.
    """
    items, albums = _do_query(lib, query, album, False)
    objs = albums if album else items
    num_objs = len(objs)

    # Filter out files that don't need to be moved.
    def isitemmoved(item):
        return item.path != item.destination(basedir=dest)

    def isalbummoved(album):
        return any(isitemmoved(i) for i in album.items())

    objs = [o for o in objs if (isalbummoved if album else isitemmoved)(o)]
    num_unmoved = num_objs - len(objs)
    # Report unmoved files that match the query.
    unmoved_msg = ''
    if num_unmoved > 0:
        unmoved_msg = f' ({num_unmoved} already in place)'

    copy = copy or export  # Exporting always copies.
    action = 'Copying' if copy else 'Moving'
    act = 'copy' if copy else 'move'
    entity = 'album' if album else 'item'
    log.info('{0} {1} {2}{3}{4}.', action, len(objs), entity,
             's' if len(objs) != 1 else '', unmoved_msg)
    if not objs:
        return

    if pretend:
        if album:
            show_path_changes([(item.path, item.destination(basedir=dest))
                               for obj in objs for item in obj.items()])
        else:
            show_path_changes([(obj.path, obj.destination(basedir=dest))
                               for obj in objs])
    else:
        if confirm:
            objs = ui.input_select_objects(
                'Really %s' % act, objs,
                lambda o: show_path_changes(
                    [(o.path, o.destination(basedir=dest))]))

        for obj in objs:
            log.debug('moving: {0}', util.displayable_path(obj.path))

            if export:
                # Copy without affecting the database.
                obj.move(operation=MoveOperation.COPY, basedir=dest,
                         store=False)
            else:
                # Ordinary move/copy: store the new path.
                if copy:
                    obj.move(operation=MoveOperation.COPY, basedir=dest)
                else:
                    obj.move(operation=MoveOperation.MOVE, basedir=dest)


def move_func(lib, opts, args):
    dest = opts.dest
    if dest is not None:
        dest = normpath(dest)
        if not os.path.isdir(dest):
            raise ui.UserError('no such directory: %s' % dest)

    move_items(lib, dest, decargs(args), opts.copy, opts.album, opts.pretend,
               opts.timid, opts.export)


move_cmd = ui.Subcommand(
    'move', help='move or copy items', aliases=('mv',)
)
move_cmd.parser.add_option(
    '-d', '--dest', metavar='DIR', dest='dest',
    help='destination directory'
)
move_cmd.parser.add_option(
    '-c', '--copy', default=False, action='store_true',
    help='copy instead of moving'
)
move_cmd.parser.add_option(
    '-p', '--pretend', default=False, action='store_true',
    help='show how files would be moved, but don\'t touch anything'
)
move_cmd.parser.add_option(
    '-t', '--timid', dest='timid', action='store_true',
    help='always confirm all actions'
)
move_cmd.parser.add_option(
    '-e', '--export', default=False, action='store_true',
    help='copy without changing the database path'
)
move_cmd.parser.add_album_option()
move_cmd.func = move_func
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
            log.info('missing file: {0}', util.displayable_path(item.path))
            continue

        # Get an Item object reflecting the "clean" (on-disk) state.
        try:
            clean_item = library.Item.from_path(item.path)
        except library.ReadError as exc:
            log.error('error reading {0}: {1}',
                      displayable_path(item.path), exc)
            continue

        # Check for and display changes.
        changed = ui.show_model_changes(item, clean_item,
                                        library.Item._media_tag_fields, force)
        if (changed or force) and not pretend:
            # We use `try_sync` here to keep the mtime up to date in the
            # database.
            item.try_sync(True, False)


def write_func(lib, opts, args):
    write_items(lib, decargs(args), opts.pretend, opts.force)


write_cmd = ui.Subcommand('write', help='write tag information to files')
write_cmd.parser.add_option(
    '-p', '--pretend', action='store_true',
    help="show all changes but do nothing"
)
write_cmd.parser.add_option(
    '-f', '--force', action='store_true',
    help="write tags even if the existing tags match the database"
)
write_cmd.func = write_func
default_commands.append(write_cmd)


# config: Show and edit user configuration.

def config_func(lib, opts, args):
    # Make sure lazy configuration is loaded
    config.resolve()

    # Print paths.
    if opts.paths:
        filenames = []
        for source in config.sources:
            if not opts.defaults and source.default:
                continue
            if source.filename:
                filenames.append(source.filename)

        # In case the user config file does not exist, prepend it to the
        # list.
        user_path = config.user_config_path()
        if user_path not in filenames:
            filenames.insert(0, user_path)

        for filename in filenames:
            print_(displayable_path(filename))

    # Open in editor.
    elif opts.edit:
        config_edit()

    # Dump configuration.
    else:
        config_out = config.dump(full=opts.defaults, redact=opts.redact)
        if config_out.strip() != '{}':
            print_(util.text_string(config_out))
        else:
            print("Empty configuration")


def config_edit():
    """Open a program to edit the user configuration.
    An empty config file is created if no existing config file exists.
    """
    path = config.user_config_path()
    editor = util.editor_command()
    try:
        if not os.path.isfile(path):
            open(path, 'w+').close()
        util.interactive_open([path], editor)
    except OSError as exc:
        message = f"Could not edit configuration: {exc}"
        if not editor:
            message += ". Please set the EDITOR environment variable"
        raise ui.UserError(message)


config_cmd = ui.Subcommand('config',
                           help='show or edit the user configuration')
config_cmd.parser.add_option(
    '-p', '--paths', action='store_true',
    help='show files that configuration was loaded from'
)
config_cmd.parser.add_option(
    '-e', '--edit', action='store_true',
    help='edit user configuration with $EDITOR'
)
config_cmd.parser.add_option(
    '-d', '--defaults', action='store_true',
    help='include the default configuration'
)
config_cmd.parser.add_option(
    '-c', '--clear', action='store_false',
    dest='redact', default=True,
    help='do not redact sensitive fields'
)
config_cmd.func = config_func
default_commands.append(config_cmd)


# completion: print completion script

def print_completion(*args):
    for line in completion_script(default_commands + plugins.commands()):
        print_(line, end='')
    if not any(map(os.path.isfile, BASH_COMPLETION_PATHS)):
        log.warning('Warning: Unable to find the bash-completion package. '
                    'Command line completion might not work.')


BASH_COMPLETION_PATHS = map(syspath, [
    '/etc/bash_completion',
    '/usr/share/bash-completion/bash_completion',
    '/usr/local/share/bash-completion/bash_completion',
    # SmartOS
    '/opt/local/share/bash-completion/bash_completion',
    # Homebrew (before bash-completion2)
    '/usr/local/etc/bash_completion',
])


def completion_script(commands):
    """Yield the full completion shell script as strings.

    ``commands`` is alist of ``ui.Subcommand`` instances to generate
    completion data for.
    """
    base_script = os.path.join(os.path.dirname(__file__), 'completion_base.sh')
    with open(base_script) as base_script:
        yield util.text_string(base_script.read())

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
        'opts':
            '-l --library -c --config -d --directory -h --help'.split(' ')
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
        yield "  local alias__{}={}\n".format(alias.replace('-', '_'), cmd)
    yield '\n'

    # Fields
    yield "  fields='%s'\n" % ' '.join(
        set(
            list(library.Item._fields.keys()) +
            list(library.Album._fields.keys())
        )
    )

    # Command options
    for cmd, opts in options.items():
        for option_type, option_list in opts.items():
            if option_list:
                option_list = ' '.join(option_list)
                yield "  local {}__{}='{}'\n".format(
                    option_type, cmd.replace('-', '_'), option_list)

    yield '  _beet_dispatch\n'
    yield '}\n'


completion_cmd = ui.Subcommand(
    'completion',
    help='print shell script that provides command line completion'
)
completion_cmd.func = print_completion
completion_cmd.hide = True
default_commands.append(completion_cmd)
