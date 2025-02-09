# This file is part of beets.
# Copyright 2016, Jan-Erik Dahlin
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

"""If the title is empty, try to extract track and title from the
filename.
"""

import os
import re

from beets import plugins
from beets.util import displayable_path

# Filename field extraction patterns.
PATTERNS = [
    # Useful patterns.
    (r"^(?P<track>\d+)\.?\s*-\s*(?P<artist>.+?)\s*-\s*(?P<title>.+?)"
     r"(\s*-\s*(?P<tag>.*))?$"),
    r"^(?P<artist>.+?)\s*-\s*(?P<title>.+?)(\s*-\s*(?P<tag>.*))?$",
    r"^(?P<track>\d+)\.?[\s\-_]+(?P<title>.+)$",
    r"^(?P<title>.+) by (?P<artist>.+)$",
    r"^(?P<track>\d+).*$",
    r"^(?P<title>.+)$",
]

# Titles considered "empty" and in need of replacement.
BAD_TITLE_PATTERNS = [
    r"^$",
]


def equal(seq):
    """Determine whether a sequence holds identical elements."""
    return len(set(seq)) <= 1


def equal_fields(matchdict, field):
    """Do all items in `matchdict`, whose values are dictionaries, have
    the same value for `field`? (If they do, the field is probably not
    the title.)
    """
    return equal(m[field] for m in matchdict.values())


def all_matches(names, pattern):
    """If all the filenames in the item/filename mapping match the
    pattern, return a dictionary mapping the items to dictionaries
    giving the value for each named subpattern in the match. Otherwise,
    return None.
    """
    matches = {}
    for item, name in names.items():
        m = re.match(pattern, name, re.IGNORECASE)
        if m and m.groupdict():
            # Only yield a match when the regex applies *and* has
            # capture groups. Otherwise, no information can be extracted
            # from the filename.
            matches[item] = m.groupdict()
        else:
            return None
    return matches


def bad_title(title):
    """Determine whether a given title is "bad" (empty or otherwise
    meaningless) and in need of replacement.
    """
    for pat in BAD_TITLE_PATTERNS:
        if re.match(pat, title, re.IGNORECASE):
            return True
    return False


def apply_matches(d, log):
    """Given a mapping from items to field dicts, apply the fields to
    the objects.
    """
    some_map = list(d.values())[0]
    keys = some_map.keys()

    # Only proceed if the "tag" field is equal across all filenames.
    if "tag" in keys and not equal_fields(d, "tag"):
        return

    # Given both an "artist" and "title" field, assume that one is
    # *actually* the artist, which must be uniform, and use the other
    # for the title. This, of course, won't work for VA albums.
    # Only check for "artist": patterns containing it, also contain "title"
    if "artist" in keys:
        if equal_fields(d, "artist"):
            artist = some_map["artist"]
            title_field = "title"
        elif equal_fields(d, "title"):
            artist = some_map["title"]
            title_field = "artist"
        else:
            # Both vary. Abort.
            return

        for item in d:
            if not item.artist:
                item.artist = artist
                log.info("Artist replaced with: {}".format(item.artist))
    # otherwise, if the pattern contains "title", use that for title_field
    elif "title" in keys:
        title_field = "title"
    else:
        title_field = None

    # Apply the title and track, if any.
    for item in d:
        if title_field and bad_title(item.title):
            item.title = str(d[item][title_field])
            log.info("Title replaced with: {}".format(item.title))

        if "track" in d[item] and item.track == 0:
            item.track = int(d[item]["track"])
            log.info("Track replaced with: {}".format(item.track))


# Plugin structure and hook into import process.


class FromFilenamePlugin(plugins.BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.register_listener("import_task_start", self.filename_task)

    def filename_task(self, task, session):
        """Examine each item in the task to see if we can extract a title
        from the filename. Try to match all filenames to a number of
        regexps, starting with the most complex patterns and successively
        trying less complex patterns. As soon as all filenames match the
        same regex we can make an educated guess of which part of the
        regex that contains the title.
        """
        items = task.items if task.is_album else [task.item]

        # Look for suspicious (empty or meaningless) titles.
        missing_titles = sum(bad_title(i.title) for i in items)

        if missing_titles:
            # Get the base filenames (no path or extension).
            names = {}
            for item in items:
                path = displayable_path(item.path)
                name, _ = os.path.splitext(os.path.basename(path))
                names[item] = name

            # Look for useful information in the filenames.
            for pattern in PATTERNS:
                self._log.debug("Trying pattern: {}".format(pattern))
                d = all_matches(names, pattern)
                if d:
                    apply_matches(d, self._log)
