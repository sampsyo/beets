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


"""Gets genres for imported music based on Last.fm tags.

Uses a provided whitelist file to determine which tags are valid genres.
The included (default) genre list was originally produced by scraping Wikipedia
and has been edited to remove some questionable entries.
The scraper script used is available here:
https://gist.github.com/1241307
"""
import pylast
import codecs
import os
import yaml
import traceback

from beets import plugins
from beets import ui
from beets import config
from beets.util import normpath, plurality
from beets import library


LASTFM = pylast.LastFMNetwork(api_key=plugins.LASTFM_KEY)

PYLAST_EXCEPTIONS = (
    pylast.WSError,
    pylast.MalformedResponseError,
    pylast.NetworkError,
)

REPLACE = {
    '\u2010': '-',
}


def deduplicate(seq):
    """Remove duplicates from sequence wile preserving order.
    """
    seen = set()
    return [x for x in seq if x not in seen and not seen.add(x)]


# Canonicalization tree processing.

def flatten_tree(elem, path, branches):
    """Flatten nested lists/dictionaries into lists of strings
    (branches).
    """
    if not path:
        path = []

    if isinstance(elem, dict):
        for (k, v) in elem.items():
            flatten_tree(v, path + [k], branches)
    elif isinstance(elem, list):
        for sub in elem:
            flatten_tree(sub, path, branches)
    else:
        branches.append(path + [str(elem)])


def find_parents(candidate, branches):
    """Find parents genre of a given genre, ordered from the closest to
    the further parent.
    """
    for branch in branches:
        try:
            idx = branch.index(candidate.lower())
            return list(reversed(branch[:idx + 1]))
        except ValueError:
            continue
    return [candidate]


# Main plugin logic.

WHITELIST = os.path.join(os.path.dirname(__file__), 'genres.txt')
C14N_TREE = os.path.join(os.path.dirname(__file__), 'genres-tree.yaml')


class LastGenrePlugin(plugins.BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.orig_genre = None

        self.config.add({
            'whitelist': True,
            'min_weight': 10,
            'count': 1,
            'fallback': None,
            'canonical': False,
            'source': 'album',
            'force': True,
            'auto': True,
            'separator': ', ',
            'prefer_specific': False,
            'title_case': True,
        })

        self.setup()

    def setup(self):
        """Setup plugin from config options
        """
        if self.config['auto']:
            self.import_stages = [self.imported]

        self._genre_cache = {}

        # Read the whitelist file if enabled.
        self.whitelist = set()
        wl_filename = self.config['whitelist'].get()
        if wl_filename in (True, ''):  # Indicates the default whitelist.
            wl_filename = WHITELIST
        if wl_filename:
            wl_filename = normpath(wl_filename)
            with open(wl_filename, 'rb') as f:
                for line in f:
                    line = line.decode('utf-8').strip().lower()
                    if line and not line.startswith('#'):
                        self.whitelist.add(line)
        # Read the genres tree for canonicalization if enabled.
        self.c14n_branches = []
        c14n_filename = self.config['canonical'].get()
        self.canonicalize = c14n_filename is not False

        # Default tree
        if c14n_filename in (True, ''):
            c14n_filename = C14N_TREE
        elif not self.canonicalize and self.config['prefer_specific'].get():
            # prefer_specific requires a tree, load default tree
            c14n_filename = C14N_TREE

        # Read the tree
        if c14n_filename:
            self._log.debug('Loading canonicalization tree {0}', c14n_filename)
            c14n_filename = normpath(c14n_filename)
            with codecs.open(c14n_filename, 'r', encoding='utf-8') as f:
                genres_tree = yaml.safe_load(f)
            flatten_tree(genres_tree, [], self.c14n_branches)

    @property
    def sources(self):
        """A tuple of allowed genre sources. May contain 'track',
        'album', or 'artist.'
        """
        source = self.config['source'].as_choice(('track', 'album', 'artist'))
        if source == 'track':
            return 'track', 'album', 'artist'
        elif source == 'album':
            return 'album', 'artist'
        elif source == 'artist':
            return 'artist',

    def _get_depth(self, tag):
        """Find the depth of a tag in the genres tree.
        """
        depth = None
        for key, value in enumerate(self.c14n_branches):
            if tag in value:
                depth = value.index(tag)
                break
        return depth

    def _sort_by_depth(self, tags):
        """Given a list of tags, sort the tags by their depths in the
        genre tree.
        """
        depth_tag_pairs = [(self._get_depth(t), t) for t in tags]
        depth_tag_pairs = [e for e in depth_tag_pairs if e[0] is not None]
        depth_tag_pairs.sort(reverse=True)
        return [p[1] for p in depth_tag_pairs]

    def _resolve_genres(self, tags):
        """Given a list of strings, return a genre by joining them into a
        single string and (optionally) canonicalizing each.
        """
        if not tags:
            return None
        print(f"self.orig_genre_pre: {self.orig_genre}")
        # split self.orig_genre into list using the separator
        if self.orig_genre is None:
            self.orig_genre = ''
        else:
            self.orig_genre = [
                genre.lower() for genre in self.orig_genre.split(
                    self.config['separator'].as_str()
                )
            ]
        print(f"new tags: {tags}")
        # write tags to all_genres.txt file saved in the all_genre_fn path. We need to check if the tag is already in the file and only add it if it is not in a new line
        all_genre_fn = self.config['all_genres'].get()
        if all_genre_fn:
            all_genre_fn = normpath(all_genre_fn)
            with open(all_genre_fn, 'r+') as f:
                lines = f.readlines()
                print(f"lines: {lines}")
                # remove the \n from the lines
                lines = [line.strip() for line in lines]
                # check if tags is in the list and find tags that are not in the list
                new_tags = [tag for tag in tags if tag not in lines]
                print(f"new tags: {new_tags}")
                # remove duplicates
                new_tags = deduplicate(new_tags)
                # sort the list
                new_tags.sort()
                print(f"new tags dedup: {new_tags}")
                # write new tags to the file in a new line
                for tag in new_tags:
                    f.write(tag + "\n")                
        if not self.orig_genre is None:
            tags = self.orig_genre + tags
        count = self.config['count'].get(int)
        if self.canonicalize:
            # Extend the list to consider tags parents in the c14n tree
            tags_all = []
            for tag in tags:
                # Add parents that are in the whitelist, or add the oldest
                # ancestor if no whitelist
                if self.whitelist:
                    parents = [x for x in find_parents(tag, self.c14n_branches)
                               if self._is_allowed(x)]
                else:
                    parents = [find_parents(tag, self.c14n_branches)[-1]]
                self._log.debug('Canonicalizing {0} to {1}', tag, parents)
                tags_all += parents
                # Stop if we have enough tags already, unless we need to find
                # the most specific tag (instead of the most popular).
                if (not self.config['prefer_specific'] and
                        len(tags_all) >= count):
                    break
            tags = tags_all
        tags = deduplicate(tags)
        print(f"tags post-dedup: {tags}")

        # Sort the tags by specificity.
        if self.config['prefer_specific']:
            tags = self._sort_by_depth(tags)
        print(f"tags post-sort: {tags}")

        # c14n only adds allowed genres but we may have had forbidden genres in
        # the original tags list
        for tag in tags:
            if not self._is_allowed(tag):
                tags.remove(tag)
        tags = [self._format_tag(x) for x in tags if self._is_allowed(x)]
        print(f"tags post-allowed: {tags}")

        return self.config['separator'].as_str().join(
            tags[:self.config['count'].get(int)]
        )

    def _format_tag(self, tag):
        if self.config["title_case"]:
            return tag.title()
        return tag

    def fetch_genre(self, lastfm_obj):
        """Return the genre for a pylast entity or None if no suitable genre
        can be found. Ex. 'Electronic, House, Dance'
        """
        min_weight = self.config['min_weight'].get(int)
        return self._resolve_genres(self._tags_for(lastfm_obj, min_weight))

    def _is_allowed(self, genre):
        """Determine whether the genre is present in the whitelist,
        returning a boolean.
        """
        if genre is None:
            return False
        if not self.whitelist or genre in self.whitelist:
            return True
        return False

    # Cached entity lookups.

    def _last_lookup(self, entity, method, *args):
        """Get a genre based on the named entity using the callable `method`
        whose arguments are given in the sequence `args`. The genre lookup
        is cached based on the entity name and the arguments. Before the
        lookup, each argument is has some Unicode characters replaced with
        rough ASCII equivalents in order to return better results from the
        Last.fm database.
        """
        # Shortcut if we're missing metadata.
        if any(not s for s in args):
            return None

        key = '{}.{}'.format(entity,
                             '-'.join(str(a) for a in args))
        if key in self._genre_cache:
            return self._genre_cache[key]
        else:
            args_replaced = []
            for arg in args:
                for k, v in REPLACE.items():
                    arg = arg.replace(k, v)
                args_replaced.append(arg)

            genre = self.fetch_genre(method(*args_replaced))
            self._genre_cache[key] = genre
            return genre

    def fetch_album_genre(self, obj):
        """Return the album genre for this Item or Album.
        """
        return self._last_lookup(
            'album', LASTFM.get_album, obj.albumartist, obj.album
        )

    def fetch_album_artist_genre(self, obj):
        """Return the album artist genre for this Item or Album.
        """
        return self._last_lookup(
            'artist', LASTFM.get_artist, obj.albumartist
        )

    def fetch_artist_genre(self, item):
        """Returns the track artist genre for this Item.
        """
        return self._last_lookup(
            'artist', LASTFM.get_artist, item.artist
        )

    def fetch_track_genre(self, obj):
        """Returns the track genre for this Item.
        """
        return self._last_lookup(
            'track', LASTFM.get_track, obj.artist, obj.title
        )

    def _get_genre(self, obj):
        """Get the genre string for an Album or Item object based on
        self.sources. Return a `(genre, source)` pair. The
        prioritization order is:
            - track (for Items only)
            - album
            - artist
            - original
            - fallback
            - None
        """

        # Shortcut to existing genre if not forcing.
        if not self.config['force'] and self._is_allowed(obj.genre):
            return obj.genre, 'keep'

        # Track genre (for Items only).
        if isinstance(obj, library.Item):
            if 'track' in self.sources:
                result = self.fetch_track_genre(obj)
                if result:
                    return result, 'track'

        # Album genre.
        if 'album' in self.sources:
            result = self.fetch_album_genre(obj)
            if result:
                return result, 'album'

        # Artist (or album artist) genre.
        if 'artist' in self.sources:
            result = None
            if isinstance(obj, library.Item):
                result = self.fetch_artist_genre(obj)
            elif obj.albumartist != config['va_name'].as_str():
                result = self.fetch_album_artist_genre(obj)
            else:
                # For "Various Artists", pick the most popular track genre.
                item_genres = []
                for item in obj.items():
                    item_genre = None
                    if 'track' in self.sources:
                        item_genre = self.fetch_track_genre(item)
                    if not item_genre:
                        item_genre = self.fetch_artist_genre(item)
                    if item_genre:
                        item_genres.append(item_genre)
                if item_genres:
                    result, _ = plurality(item_genres)

            if result:
                return result, 'artist'

        # Filter the existing genre.
        if obj.genre:
            result = self._resolve_genres([obj.genre])
            if result:
                return result, 'original'

        # Fallback string.
        fallback = self.config['fallback'].get()
        if fallback:
            return fallback, 'fallback'

        return None, None

    def commands(self):
        lastgenre_cmd = ui.Subcommand('lastgenre', help='fetch genres')
        lastgenre_cmd.parser.add_option(
            '-f', '--force', dest='force',
            action='store_true',
            help='re-download genre when already present'
        )
        lastgenre_cmd.parser.add_option(
            '-s', '--source', dest='source', type='string',
            help='genre source: artist, album, or track'
        )
        lastgenre_cmd.parser.add_option(
            '-A', '--items', action='store_false', dest='album',
            help='match items instead of albums')
        lastgenre_cmd.parser.add_option(
            '-a', '--albums', action='store_true', dest='album',
            help='match albums instead of items')
        lastgenre_cmd.parser.set_defaults(album=True)

        def lastgenre_func(lib, opts, args):
            write = ui.should_write()
            self.config.set_args(opts)

            if opts.album:
                # Fetch genres for whole albums
                for album in lib.albums(ui.decargs(args)):
                    print(f"Processing album {album.album} ({album.year})")
                    self.orig_genre = album.genre
                    album.genre, src = self._get_genre(album)
                    print(f"Final genre: {album.genre}")
                    self._log.debug('genre for album {0} ({1}): {0.genre}',
                                   album, src)
                    # album.store()

                    for item in album.items():
                        # If we're using track-level sources, also look up each
                        # track on the album.
                        if 'track' in self.sources:
                            item.genre, src = self._get_genre(item)
                            item.store()
                            self._log.info(
                                'genre for track {0} ({1}): {0.genre}',
                                item, src)

                        if write:
                            item.try_write()
            else:
                # Just query singletons, i.e. items that are not part of
                # an album
                for item in lib.items(ui.decargs(args)):
                    item.genre, src = self._get_genre(item)
                    self._log.debug('added last.fm item genre ({0}): {1}',
                                    src, item.genre)
                    item.store()

        lastgenre_cmd.func = lastgenre_func
        return [lastgenre_cmd]

    def imported(self, session, task):
        """Event hook called when an import task finishes."""
        if task.is_album:
            album = task.album
            album.genre, src = self._get_genre(album)
            self._log.debug('added last.fm album genre ({0}): {1}',
                            src, album.genre)
            album.store()

            if 'track' in self.sources:
                for item in album.items():
                    item.genre, src = self._get_genre(item)
                    self._log.debug('added last.fm item genre ({0}): {1}',
                                    src, item.genre)
                    item.store()

        else:
            item = task.item
            item.genre, src = self._get_genre(item)
            self._log.debug('added last.fm item genre ({0}): {1}',
                            src, item.genre)
            item.store()

    def _tags_for(self, obj, min_weight=None):
        """Core genre identification routine.

        Given a pylast entity (album or track), return a list of
        tag names for that entity. Return an empty list if the entity is
        not found or another error occurs.

        If `min_weight` is specified, tags are filtered by weight.
        """
        # Work around an inconsistency in pylast where
        # Album.get_top_tags() does not return TopItem instances.
        # https://github.com/pylast/pylast/issues/86
        if isinstance(obj, pylast.Album):
            obj = super(pylast.Album, obj)

        try:
            res = obj.get_top_tags()
        except PYLAST_EXCEPTIONS as exc:
            self._log.debug('last.fm error: {0}', exc)
            return []
        except Exception as exc:
            # Isolate bugs in pylast.
            self._log.debug('{}', traceback.format_exc())
            self._log.error('error in pylast library: {0}', exc)
            return []

        # Filter by weight (optionally).
        if min_weight:
            res = [el for el in res if (int(el.weight or 0)) >= min_weight]

        # Get strings from tags.
        res = [el.item.get_name().lower() for el in res]

        return res