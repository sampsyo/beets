# This file is part of beets.
# Copyright 2016, Philippe Mongeau.
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

"""Get a random song or album from the library."""

import random
from itertools import groupby
from operator import attrgetter


def _length(obj, album):
    """Get the duration of an item or album."""
    if album:
        return sum(i.length for i in obj.items())
    else:
        return obj.length


def _equal_chance_permutation(objs, field="albumartist", random_gen=None):
    """Generate (lazily) a permutation of the objects where every group
    with equal values for `field` have an equal chance of appearing in
    any given position.
    """
    rand = random_gen or random

    # Group the objects by artist so we can sample from them.
    key = attrgetter(field)
    objs.sort(key=key)
    objs_by_artists = {}
    for artist, v in groupby(objs, key):
        objs_by_artists[artist] = list(v)

    # While we still have artists with music to choose from, pick one
    # randomly and pick a track from that artist.
    while objs_by_artists:
        # Choose an artist and an object for that artist, removing
        # this choice from the pool.
        artist = rand.choice(list(objs_by_artists.keys()))
        objs_from_artist = objs_by_artists[artist]
        i = rand.randint(0, len(objs_from_artist) - 1)
        yield objs_from_artist.pop(i)

        # Remove the artist if we've used up all of its objects.
        if not objs_from_artist:
            del objs_by_artists[artist]


def _take(iter, num):
    """Return a list containing the first `num` values in `iter` (or
    fewer, if the iterable ends early).
    """
    out = []
    for val in iter:
        out.append(val)
        num -= 1
        if num <= 0:
            break
    return out


def _take_time(iter, secs, album):
    """Return a list containing the first values in `iter`, which should
    be Item or Album objects, that add up to the given amount of time in
    seconds.
    """
    out = []
    total_time = 0.0
    for obj in iter:
        length = _length(obj, album)
        if total_time + length <= secs:
            out.append(obj)
            total_time += length
    return out


def random_objs(
    objs, album, number=1, time=None, equal_chance=False, random_gen=None
):
    """Get a random subset of the provided `objs`.

    If `number` is provided, produce that many matches. Otherwise, if
    `time` is provided, instead select a list whose total time is close
    to that number of minutes. If `equal_chance` is true, give each
    artist an equal chance of being included so that artists with more
    songs are not represented disproportionately.
    """
    rand = random_gen or random

    # Permute the objects either in a straightforward way or an
    # artist-balanced way.
    if equal_chance:
        perm = _equal_chance_permutation(objs)
    else:
        perm = objs
        rand.shuffle(perm)  # N.B. This shuffles the original list.

    # Select objects by time our count.
    if time:
        return _take_time(perm, time * 60, album)
    else:
        return _take(perm, number)
