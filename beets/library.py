# -*- coding: utf-8 -*-
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

"""The core data store and collection logic for beets.
"""
from __future__ import division, absolute_import, print_function

import os
import sys
import unicodedata
import time
import re
import six
import string

from beets import logging
from mediafile import MediaFile, UnreadableFileError
from beets import plugins
from beets import util
from beets.util import bytestring_path, syspath, normpath, samefile, \
    MoveOperation, lazy_property
from beets.util.functemplate import template, Template
from beets import dbcore
from beets.dbcore import types
import beets

# To use the SQLite "blob" type, it doesn't suffice to provide a byte
# string; SQLite treats that as encoded text. Wrapping it in a `buffer` or a
# `memoryview`, depending on the Python version, tells it that we
# actually mean non-text data.
if six.PY2:
    BLOB_TYPE = buffer  # noqa: F821
else:
    BLOB_TYPE = memoryview

log = logging.getLogger('beets')


# Library-specific query types.

class PathQuery(dbcore.FieldQuery):
    """A query that matches all items under a given path.

    Matching can either be case-insensitive or case-sensitive. By
    default, the behavior depends on the OS: case-insensitive on Windows
    and case-sensitive otherwise.
    """

    def __init__(self, field, pattern, fast=True, case_sensitive=None):
        """Create a path query. `pattern` must be a path, either to a
        file or a directory.

        `case_sensitive` can be a bool or `None`, indicating that the
        behavior should depend on the filesystem.
        """
        super(PathQuery, self).__init__(field, pattern, fast)

        # By default, the case sensitivity depends on the filesystem
        # that the query path is located on.
        if case_sensitive is None:
            path = util.bytestring_path(util.normpath(pattern))
            case_sensitive = beets.util.case_sensitive(path)
        self.case_sensitive = case_sensitive

        # Use a normalized-case pattern for case-insensitive matches.
        if not case_sensitive:
            pattern = pattern.lower()

        # Match the path as a single file.
        self.file_path = util.bytestring_path(util.normpath(pattern))
        # As a directory (prefix).
        self.dir_path = util.bytestring_path(os.path.join(self.file_path, b''))

    @classmethod
    def is_path_query(cls, query_part):
        """Try to guess whether a unicode query part is a path query.

        Condition: separator precedes colon and the file exists.
        """
        colon = query_part.find(':')
        if colon != -1:
            query_part = query_part[:colon]

        # Test both `sep` and `altsep` (i.e., both slash and backslash on
        # Windows).
        return (
            (os.sep in query_part or
             (os.altsep and os.altsep in query_part)) and
            os.path.exists(syspath(normpath(query_part)))
        )

    def match(self, item):
        path = item.path if self.case_sensitive else item.path.lower()
        return (path == self.file_path) or path.startswith(self.dir_path)

    def col_clause(self):
        file_blob = BLOB_TYPE(self.file_path)
        dir_blob = BLOB_TYPE(self.dir_path)

        if self.case_sensitive:
            query_part = '({0} = ?) || (substr({0}, 1, ?) = ?)'
        else:
            query_part = '(BYTELOWER({0}) = BYTELOWER(?)) || \
                         (substr(BYTELOWER({0}), 1, ?) = BYTELOWER(?))'

        return query_part.format(self.field), \
            (file_blob, len(dir_blob), dir_blob)


# Library-specific field types.

class DateType(types.Float):
    # TODO representation should be `datetime` object
    # TODO distinguish between date and time types
    query = dbcore.query.DateQuery

    def format(self, value):
        return time.strftime(beets.config['time_format'].as_str(),
                             time.localtime(value or 0))

    def parse(self, string):
        try:
            # Try a formatted date string.
            return time.mktime(
                time.strptime(string,
                              beets.config['time_format'].as_str())
            )
        except ValueError:
            # Fall back to a plain timestamp number.
            try:
                return float(string)
            except ValueError:
                return self.null


class PathType(types.Type):
    """A dbcore type for filesystem paths. These are represented as
    `bytes` objects, in keeping with the Unix filesystem abstraction.
    """

    sql = u'BLOB'
    query = PathQuery
    model_type = bytes

    def __init__(self, nullable=False):
        """Create a path type object. `nullable` controls whether the
        type may be missing, i.e., None.
        """
        self.nullable = nullable

    @property
    def null(self):
        if self.nullable:
            return None
        else:
            return b''

    def format(self, value):
        return util.displayable_path(value)

    def parse(self, string):
        return normpath(bytestring_path(string))

    def normalize(self, value):
        if isinstance(value, six.text_type):
            # Paths stored internally as encoded bytes.
            return bytestring_path(value)

        elif isinstance(value, BLOB_TYPE):
            # We unwrap buffers to bytes.
            return bytes(value)

        else:
            return value

    def from_sql(self, sql_value):
        return self.normalize(sql_value)

    def to_sql(self, value):
        if isinstance(value, bytes):
            value = BLOB_TYPE(value)
        return value


class MusicalKey(types.String):
    """String representing the musical key of a song.

    The standard format is C, Cm, C#, C#m, etc.
    """
    ENHARMONIC = {
        r'db': 'c#',
        r'eb': 'd#',
        r'gb': 'f#',
        r'ab': 'g#',
        r'bb': 'a#',
    }

    null = None

    def parse(self, key):
        key = key.lower()
        for flat, sharp in self.ENHARMONIC.items():
            key = re.sub(flat, sharp, key)
        key = re.sub(r'[\W\s]+minor', 'm', key)
        key = re.sub(r'[\W\s]+major', '', key)
        return key.capitalize()

    def normalize(self, key):
        if key is None:
            return None
        else:
            return self.parse(key)


class DurationType(types.Float):
    """Human-friendly (M:SS) representation of a time interval."""
    query = dbcore.query.DurationQuery

    def format(self, value):
        if not beets.config['format_raw_length'].get(bool):
            return beets.ui.human_seconds_short(value or 0.0)
        else:
            return value

    def parse(self, string):
        try:
            # Try to format back hh:ss to seconds.
            return util.raw_seconds_short(string)
        except ValueError:
            # Fall back to a plain float.
            try:
                return float(string)
            except ValueError:
                return self.null


# Library-specific sort types.

class SmartArtistSort(dbcore.query.Sort):
    """Sort by artist (either album artist or track artist),
    prioritizing the sort field over the raw field.
    """
    def __init__(self, model_cls, ascending=True, case_insensitive=True):
        self.album = model_cls is Album
        self.ascending = ascending
        self.case_insensitive = case_insensitive

    def order_clause(self):
        order = "ASC" if self.ascending else "DESC"
        field = 'albumartist' if self.album else 'artist'
        collate = 'COLLATE NOCASE' if self.case_insensitive else ''
        return ('(CASE {0}_sort WHEN NULL THEN {0} '
                'WHEN "" THEN {0} '
                'ELSE {0}_sort END) {1} {2}').format(field, collate, order)

    def sort(self, objs):
        if self.album:
            field = lambda a: a.albumartist_sort or a.albumartist
        else:
            field = lambda i: i.artist_sort or i.artist

        if self.case_insensitive:
            key = lambda x: field(x).lower()
        else:
            key = field
        return sorted(objs, key=key, reverse=not self.ascending)


# Special path format key.
PF_KEY_DEFAULT = 'default'


# Exceptions.
@six.python_2_unicode_compatible
class FileOperationError(Exception):
    """Indicates an error when interacting with a file on disk.
    Possibilities include an unsupported media type, a permissions
    error, and an unhandled Mutagen exception.
    """
    def __init__(self, path, reason):
        """Create an exception describing an operation on the file at
        `path` with the underlying (chained) exception `reason`.
        """
        super(FileOperationError, self).__init__(path, reason)
        self.path = path
        self.reason = reason

    def text(self):
        """Get a string representing the error. Describes both the
        underlying reason and the file path in question.
        """
        return u'{0}: {1}'.format(
            util.displayable_path(self.path),
            six.text_type(self.reason)
        )

    # define __str__ as text to avoid infinite loop on super() calls
    # with @six.python_2_unicode_compatible
    __str__ = text


@six.python_2_unicode_compatible
class ReadError(FileOperationError):
    """An error while reading a file (i.e. in `Item.read`).
    """
    def __str__(self):
        return u'error reading ' + super(ReadError, self).text()


@six.python_2_unicode_compatible
class WriteError(FileOperationError):
    """An error while writing a file (i.e. in `Item.write`).
    """
    def __str__(self):
        return u'error writing ' + super(WriteError, self).text()


# Item and Album model classes.

@six.python_2_unicode_compatible
class LibModel(dbcore.Model):
    """Shared concrete functionality for Items and Albums.
    """

    _format_config_key = None
    """Config key that specifies how an instance should be formatted.
    """

    def _template_funcs(self):
        funcs = DefaultTemplateFunctions(self, self._db).functions()
        funcs.update(plugins.template_funcs())
        return funcs

    def store(self, fields=None):
        super(LibModel, self).store(fields)
        plugins.send('database_change', lib=self._db, model=self)

    def remove(self):
        super(LibModel, self).remove()
        plugins.send('database_change', lib=self._db, model=self)

    def add(self, lib=None):
        super(LibModel, self).add(lib)
        plugins.send('database_change', lib=self._db, model=self)

    def __format__(self, spec):
        if not spec:
            spec = beets.config[self._format_config_key].as_str()
        assert isinstance(spec, six.text_type)
        return self.evaluate_template(spec)

    def __str__(self):
        return format(self)

    def __bytes__(self):
        return self.__str__().encode('utf-8')


class FormattedItemMapping(dbcore.db.FormattedMapping):
    """Add lookup for album-level fields.

    Album-level fields take precedence if `for_path` is true.
    """

    def __init__(self, item, for_path=False):
        super(FormattedItemMapping, self).__init__(item, for_path)
        self.item = item

    @lazy_property
    def all_keys(self):
        return set(self.model_keys).union(self.album_keys)

    @lazy_property
    def album_keys(self):
        album_keys = []
        if self.album:
            for key in self.album.keys(True):
                if key in Album.item_keys \
                        or key not in self.item._fields.keys():
                    album_keys.append(key)
        return album_keys

    @lazy_property
    def album(self):
        return self.item.get_album()

    def _get(self, key):
        """Get the value for a key, either from the album or the item.
        Raise a KeyError for invalid keys.
        """
        if self.for_path and key in self.album_keys:
            return self._get_formatted(self.album, key)
        elif key in self.model_keys:
            return self._get_formatted(self.model, key)
        elif key in self.album_keys:
            return self._get_formatted(self.album, key)
        else:
            raise KeyError(key)

    def __getitem__(self, key):
        """Get the value for a key. `artist` and `albumartist`
        are fallback values for each other when not set.
        """
        value = self._get(key)

        # `artist` and `albumartist` fields fall back to one another.
        # This is helpful in path formats when the album artist is unset
        # on as-is imports.
        if key == 'artist' and not value:
            return self._get('albumartist')
        elif key == 'albumartist' and not value:
            return self._get('artist')
        else:
            return value

    def __iter__(self):
        return iter(self.all_keys)

    def __len__(self):
        return len(self.all_keys)


class Item(LibModel):
    _table = 'items'
    _flex_table = 'item_attributes'
    _fields = {
        'id':       types.PRIMARY_ID,
        'path':     PathType(),
        'album_id': types.FOREIGN_ID,

        'title':                types.STRING,
        'artist':               types.STRING,
        'artist_sort':          types.STRING,
        'artist_credit':        types.STRING,
        'album':                types.STRING,
        'albumartist':          types.STRING,
        'albumartist_sort':     types.STRING,
        'albumartist_credit':   types.STRING,
        'genre':                types.STRING,
        'style':                types.STRING,
        'discogs_albumid':      types.INTEGER,
        'discogs_artistid':     types.INTEGER,
        'discogs_labelid':      types.INTEGER,
        'lyricist':             types.STRING,
        'composer':             types.STRING,
        'composer_sort':        types.STRING,
        'work':                 types.STRING,
        'mb_workid':            types.STRING,
        'work_disambig':        types.STRING,
        'arranger':             types.STRING,
        'grouping':             types.STRING,
        'year':                 types.PaddedInt(4),
        'month':                types.PaddedInt(2),
        'day':                  types.PaddedInt(2),
        'track':                types.PaddedInt(2),
        'tracktotal':           types.PaddedInt(2),
        'disc':                 types.PaddedInt(2),
        'disctotal':            types.PaddedInt(2),
        'lyrics':               types.STRING,
        'comments':             types.STRING,
        'bpm':                  types.INTEGER,
        'comp':                 types.BOOLEAN,
        'mb_trackid':           types.STRING,
        'mb_albumid':           types.STRING,
        'mb_artistid':          types.STRING,
        'mb_albumartistid':     types.STRING,
        'mb_releasetrackid':    types.STRING,
        'albumtype':            types.STRING,
        'label':                types.STRING,
        'acoustid_fingerprint': types.STRING,
        'acoustid_id':          types.STRING,
        'mb_releasegroupid':    types.STRING,
        'asin':                 types.STRING,
        'catalognum':           types.STRING,
        'script':               types.STRING,
        'language':             types.STRING,
        'country':              types.STRING,
        'albumstatus':          types.STRING,
        'media':                types.STRING,
        'albumdisambig':        types.STRING,
        'releasegroupdisambig': types.STRING,
        'disctitle':            types.STRING,
        'encoder':              types.STRING,
        'rg_track_gain':        types.NULL_FLOAT,
        'rg_track_peak':        types.NULL_FLOAT,
        'rg_album_gain':        types.NULL_FLOAT,
        'rg_album_peak':        types.NULL_FLOAT,
        'r128_track_gain':      types.NullPaddedInt(6),
        'r128_album_gain':      types.NullPaddedInt(6),
        'original_year':        types.PaddedInt(4),
        'original_month':       types.PaddedInt(2),
        'original_day':         types.PaddedInt(2),
        'initial_key':          MusicalKey(),

        'length':      DurationType(),
        'bitrate':     types.ScaledInt(1000, u'kbps'),
        'format':      types.STRING,
        'samplerate':  types.ScaledInt(1000, u'kHz'),
        'bitdepth':    types.INTEGER,
        'channels':    types.INTEGER,
        'mtime':       DateType(),
        'added':       DateType(),
    }

    _search_fields = ('artist', 'title', 'comments',
                      'album', 'albumartist', 'genre')

    _types = {
        'data_source': types.STRING,
    }

    _media_fields = set(MediaFile.readable_fields()) \
        .intersection(_fields.keys())
    """Set of item fields that are backed by `MediaFile` fields.

    Any kind of field (fixed, flexible, and computed) may be a media
    field. Only these fields are read from disk in `read` and written in
    `write`.
    """

    _media_tag_fields = set(MediaFile.fields()).intersection(_fields.keys())
    """Set of item fields that are backed by *writable* `MediaFile` tag
    fields.

    This excludes fields that represent audio data, such as `bitrate` or
    `length`.
    """

    _formatter = FormattedItemMapping

    _sorts = {'artist': SmartArtistSort}

    _format_config_key = 'format_item'

    @classmethod
    def _getters(cls):
        getters = plugins.item_field_getters()
        getters['singleton'] = lambda i: i.album_id is None
        getters['filesize'] = Item.try_filesize  # In bytes.
        return getters

    @classmethod
    def from_path(cls, path):
        """Creates a new item from the media file at the specified path.
        """
        # Initiate with values that aren't read from files.
        i = cls(album_id=None)
        i.read(path)
        i.mtime = i.current_mtime()  # Initial mtime.
        return i

    def __setitem__(self, key, value):
        """Set the item's value for a standard field or a flexattr.
        """
        # Encode unicode paths and read buffers.
        if key == 'path':
            if isinstance(value, six.text_type):
                value = bytestring_path(value)
            elif isinstance(value, BLOB_TYPE):
                value = bytes(value)

        changed = super(Item, self)._setitem(key, value)

        if changed and key in MediaFile.fields():
            self.mtime = 0  # Reset mtime on dirty.

    def update(self, values):
        """Set all key/value pairs in the mapping. If mtime is
        specified, it is not reset (as it might otherwise be).
        """
        super(Item, self).update(values)
        if self.mtime == 0 and 'mtime' in values:
            self.mtime = values['mtime']

    def clear(self):
        """Set all key/value pairs to None."""
        for key in self._media_tag_fields:
            setattr(self, key, None)

    def get_album(self):
        """Get the Album object that this item belongs to, if any, or
        None if the item is a singleton or is not associated with a
        library.
        """
        if not self._db:
            return None
        return self._db.get_album(self)

    # Interaction with file metadata.

    def read(self, read_path=None):
        """Read the metadata from the associated file.

        If `read_path` is specified, read metadata from that file
        instead. Updates all the properties in `_media_fields`
        from the media file.

        Raises a `ReadError` if the file could not be read.
        """
        if read_path is None:
            read_path = self.path
        else:
            read_path = normpath(read_path)
        try:
            mediafile = MediaFile(syspath(read_path))
        except UnreadableFileError as exc:
            raise ReadError(read_path, exc)

        for key in self._media_fields:
            value = getattr(mediafile, key)
            if isinstance(value, six.integer_types):
                if value.bit_length() > 63:
                    value = 0
            self[key] = value

        # Database's mtime should now reflect the on-disk value.
        if read_path == self.path:
            self.mtime = self.current_mtime()

        self.path = read_path

    def write(self, path=None, tags=None, id3v23=None):
        """Write the item's metadata to a media file.

        All fields in `_media_fields` are written to disk according to
        the values on this object.

        `path` is the path of the mediafile to write the data to. It
        defaults to the item's path.

        `tags` is a dictionary of additional metadata the should be
        written to the file. (These tags need not be in `_media_fields`.)

        `id3v23` will override the global `id3v23` config option if it is
        set to something other than `None`.

        Can raise either a `ReadError` or a `WriteError`.
        """
        if path is None:
            path = self.path
        else:
            path = normpath(path)

        if id3v23 is None:
            id3v23 = beets.config['id3v23'].get(bool)

        # Get the data to write to the file.
        item_tags = dict(self)
        item_tags = {k: v for k, v in item_tags.items()
                     if k in self._media_fields}  # Only write media fields.
        if tags is not None:
            item_tags.update(tags)
        plugins.send('write', item=self, path=path, tags=item_tags)

        # Open the file.
        try:
            mediafile = MediaFile(syspath(path), id3v23=id3v23)
        except UnreadableFileError as exc:
            raise ReadError(path, exc)

        # Write the tags to the file.
        mediafile.update(item_tags)
        try:
            mediafile.save()
        except UnreadableFileError as exc:
            raise WriteError(self.path, exc)

        # The file has a new mtime.
        if path == self.path:
            self.mtime = self.current_mtime()
        plugins.send('after_write', item=self, path=path)

    def try_write(self, *args, **kwargs):
        """Calls `write()` but catches and logs `FileOperationError`
        exceptions.

        Returns `False` an exception was caught and `True` otherwise.
        """
        try:
            self.write(*args, **kwargs)
            return True
        except FileOperationError as exc:
            log.error(u"{0}", exc)
            return False

    def try_sync(self, write, move, with_album=True):
        """Synchronize the item with the database and, possibly, updates its
        tags on disk and its path (by moving the file).

        `write` indicates whether to write new tags into the file. Similarly,
        `move` controls whether the path should be updated. In the
        latter case, files are *only* moved when they are inside their
        library's directory (if any).

        Similar to calling :meth:`write`, :meth:`move`, and :meth:`store`
        (conditionally).
        """
        if write:
            self.try_write()
        if move:
            # Check whether this file is inside the library directory.
            if self._db and self._db.directory in util.ancestry(self.path):
                log.debug(u'moving {0} to synchronize path',
                          util.displayable_path(self.path))
                self.move(with_album=with_album)
        self.store()

    # Files themselves.

    def move_file(self, dest, operation=MoveOperation.MOVE):
        """Move, copy, link or hardlink the item's depending on `operation`,
        updating the path value if the move succeeds.

        If a file exists at `dest`, then it is slightly modified to be unique.

        `operation` should be an instance of `util.MoveOperation`.
        """
        if not util.samefile(self.path, dest):
            dest = util.unique_path(dest)
        if operation == MoveOperation.MOVE:
            plugins.send("before_item_moved", item=self, source=self.path,
                         destination=dest)
            util.move(self.path, dest)
            plugins.send("item_moved", item=self, source=self.path,
                         destination=dest)
        elif operation == MoveOperation.COPY:
            util.copy(self.path, dest)
            plugins.send("item_copied", item=self, source=self.path,
                         destination=dest)
        elif operation == MoveOperation.LINK:
            util.link(self.path, dest)
            plugins.send("item_linked", item=self, source=self.path,
                         destination=dest)
        elif operation == MoveOperation.HARDLINK:
            util.hardlink(self.path, dest)
            plugins.send("item_hardlinked", item=self, source=self.path,
                         destination=dest)
        elif operation == MoveOperation.REFLINK:
            util.reflink(self.path, dest, fallback=False)
            plugins.send("item_reflinked", item=self, source=self.path,
                         destination=dest)
        elif operation == MoveOperation.REFLINK_AUTO:
            util.reflink(self.path, dest, fallback=True)
            plugins.send("item_reflinked", item=self, source=self.path,
                         destination=dest)
        else:
            assert False, 'unknown MoveOperation'

        # Either copying or moving succeeded, so update the stored path.
        self.path = dest

    def current_mtime(self):
        """Returns the current mtime of the file, rounded to the nearest
        integer.
        """
        return int(os.path.getmtime(syspath(self.path)))

    def try_filesize(self):
        """Get the size of the underlying file in bytes.

        If the file is missing, return 0 (and log a warning).
        """
        try:
            return os.path.getsize(syspath(self.path))
        except (OSError, Exception) as exc:
            log.warning(u'could not get filesize: {0}', exc)
            return 0

    # Model methods.

    def remove(self, delete=False, with_album=True):
        """Removes the item. If `delete`, then the associated file is
        removed from disk. If `with_album`, then the item's album (if
        any) is removed if it the item was the last in the album.
        """
        super(Item, self).remove()

        # Remove the album if it is empty.
        if with_album:
            album = self.get_album()
            if album and not album.items():
                album.remove(delete, False)

        # Send a 'item_removed' signal to plugins
        plugins.send('item_removed', item=self)

        # Delete the associated file.
        if delete:
            util.remove(self.path)
            util.prune_dirs(os.path.dirname(self.path), self._db.directory)

        self._db._memotable = {}

    def move(self, operation=MoveOperation.MOVE, basedir=None,
             with_album=True, store=True):
        """Move the item to its designated location within the library
        directory (provided by destination()). Subdirectories are
        created as needed. If the operation succeeds, the item's path
        field is updated to reflect the new location.

        Instead of moving the item it can also be copied, linked or hardlinked
        depending on `operation` which should be an instance of
        `util.MoveOperation`.

        `basedir` overrides the library base directory for the destination.

        If the item is in an album and `with_album` is `True`, the album is
        given an opportunity to move its art.

        By default, the item is stored to the database if it is in the
        database, so any dirty fields prior to the move() call will be written
        as a side effect.
        If `store` is `False` however, the item won't be stored and you'll
        have to manually store it after invoking this method.
        """
        self._check_db()
        dest = self.destination(basedir=basedir)

        # Create necessary ancestry for the move.
        util.mkdirall(dest)

        # Perform the move and store the change.
        old_path = self.path
        self.move_file(dest, operation)
        if store:
            self.store()

        # If this item is in an album, move its art.
        if with_album:
            album = self.get_album()
            if album:
                album.move_art(operation)
                if store:
                    album.store()

        # Prune vacated directory.
        if operation == MoveOperation.MOVE:
            util.prune_dirs(os.path.dirname(old_path), self._db.directory)

    # Templating.

    def destination(self, fragment=False, basedir=None, platform=None,
                    path_formats=None):
        """Returns the path in the library directory designated for the
        item (i.e., where the file ought to be). fragment makes this
        method return just the path fragment underneath the root library
        directory; the path is also returned as Unicode instead of
        encoded as a bytestring. basedir can override the library's base
        directory for the destination.
        """
        self._check_db()
        platform = platform or sys.platform
        basedir = basedir or self._db.directory
        path_formats = path_formats or self._db.path_formats

        # Use a path format based on a query, falling back on the
        # default.
        for query, path_format in path_formats:
            if query == PF_KEY_DEFAULT:
                continue
            query, _ = parse_query_string(query, type(self))
            if query.match(self):
                # The query matches the item! Use the corresponding path
                # format.
                break
        else:
            # No query matched; fall back to default.
            for query, path_format in path_formats:
                if query == PF_KEY_DEFAULT:
                    break
            else:
                assert False, u"no default path format"
        if isinstance(path_format, Template):
            subpath_tmpl = path_format
        else:
            subpath_tmpl = template(path_format)

        # Evaluate the selected template.
        subpath = self.evaluate_template(subpath_tmpl, True)

        # Prepare path for output: normalize Unicode characters.
        if platform == 'darwin':
            subpath = unicodedata.normalize('NFD', subpath)
        else:
            subpath = unicodedata.normalize('NFC', subpath)

        if beets.config['asciify_paths']:
            subpath = util.asciify_path(
                subpath,
                beets.config['path_sep_replace'].as_str()
            )

        maxlen = beets.config['max_filename_length'].get(int)
        if not maxlen:
            # When zero, try to determine from filesystem.
            maxlen = util.max_filename_length(self._db.directory)

        subpath, fellback = util.legalize_path(
            subpath, self._db.replacements, maxlen,
            os.path.splitext(self.path)[1], fragment
        )
        if fellback:
            # Print an error message if legalization fell back to
            # default replacements because of the maximum length.
            log.warning(
                u'Fell back to default replacements when naming '
                u'file {}. Configure replacements to avoid lengthening '
                u'the filename.',
                subpath
            )

        if fragment:
            return util.as_string(subpath)
        else:
            return normpath(os.path.join(basedir, subpath))


class Album(LibModel):
    """Provides access to information about albums stored in a
    library. Reflects the library's "albums" table, including album
    art.
    """
    _table = 'albums'
    _flex_table = 'album_attributes'
    _always_dirty = True
    _fields = {
        'id':      types.PRIMARY_ID,
        'artpath': PathType(True),
        'added':   DateType(),

        'albumartist':          types.STRING,
        'albumartist_sort':     types.STRING,
        'albumartist_credit':   types.STRING,
        'album':                types.STRING,
        'genre':                types.STRING,
        'style':                types.STRING,
        'discogs_albumid':      types.INTEGER,
        'discogs_artistid':     types.INTEGER,
        'discogs_labelid':      types.INTEGER,
        'year':                 types.PaddedInt(4),
        'month':                types.PaddedInt(2),
        'day':                  types.PaddedInt(2),
        'disctotal':            types.PaddedInt(2),
        'comp':                 types.BOOLEAN,
        'mb_albumid':           types.STRING,
        'mb_albumartistid':     types.STRING,
        'albumtype':            types.STRING,
        'label':                types.STRING,
        'mb_releasegroupid':    types.STRING,
        'asin':                 types.STRING,
        'catalognum':           types.STRING,
        'script':               types.STRING,
        'language':             types.STRING,
        'country':              types.STRING,
        'albumstatus':          types.STRING,
        'albumdisambig':        types.STRING,
        'releasegroupdisambig': types.STRING,
        'rg_album_gain':        types.NULL_FLOAT,
        'rg_album_peak':        types.NULL_FLOAT,
        'r128_album_gain':      types.NullPaddedInt(6),
        'original_year':        types.PaddedInt(4),
        'original_month':       types.PaddedInt(2),
        'original_day':         types.PaddedInt(2),
    }

    _search_fields = ('album', 'albumartist', 'genre')

    _types = {
        'path':        PathType(),
        'data_source': types.STRING,
    }

    _sorts = {
        'albumartist': SmartArtistSort,
        'artist': SmartArtistSort,
    }

    item_keys = [
        'added',
        'albumartist',
        'albumartist_sort',
        'albumartist_credit',
        'album',
        'genre',
        'style',
        'discogs_albumid',
        'discogs_artistid',
        'discogs_labelid',
        'year',
        'month',
        'day',
        'disctotal',
        'comp',
        'mb_albumid',
        'mb_albumartistid',
        'albumtype',
        'label',
        'mb_releasegroupid',
        'asin',
        'catalognum',
        'script',
        'language',
        'country',
        'albumstatus',
        'albumdisambig',
        'releasegroupdisambig',
        'rg_album_gain',
        'rg_album_peak',
        'r128_album_gain',
        'original_year',
        'original_month',
        'original_day',
    ]
    """List of keys that are set on an album's items.
    """

    _format_config_key = 'format_album'

    @classmethod
    def _getters(cls):
        # In addition to plugin-provided computed fields, also expose
        # the album's directory as `path`.
        getters = plugins.album_field_getters()
        getters['path'] = Album.item_dir
        getters['albumtotal'] = Album._albumtotal
        return getters

    def items(self):
        """Returns an iterable over the items associated with this
        album.
        """
        return self._db.items(dbcore.MatchQuery('album_id', self.id))

    def remove(self, delete=False, with_items=True):
        """Removes this album and all its associated items from the
        library. If delete, then the items' files are also deleted
        from disk, along with any album art. The directories
        containing the album are also removed (recursively) if empty.
        Set with_items to False to avoid removing the album's items.
        """
        super(Album, self).remove()

        # Delete art file.
        if delete:
            artpath = self.artpath
            if artpath:
                util.remove(artpath)

        # Remove (and possibly delete) the constituent items.
        if with_items:
            for item in self.items():
                item.remove(delete, False)

    def move_art(self, operation=MoveOperation.MOVE):
        """Move, copy, link or hardlink (depending on `operation`) any
        existing album art so that it remains in the same directory as
        the items.

        `operation` should be an instance of `util.MoveOperation`.
        """
        old_art = self.artpath
        if not old_art:
            return

        if not os.path.exists(syspath(old_art)):
            log.error(u'removing reference to missing album art file {}',
                      util.displayable_path(old_art))
            self.artpath = None
            return

        new_art = self.art_destination(old_art)
        if new_art == old_art:
            return

        new_art = util.unique_path(new_art)
        log.debug(u'moving album art {0} to {1}',
                  util.displayable_path(old_art),
                  util.displayable_path(new_art))
        if operation == MoveOperation.MOVE:
            util.move(old_art, new_art)
            util.prune_dirs(os.path.dirname(old_art), self._db.directory)
        elif operation == MoveOperation.COPY:
            util.copy(old_art, new_art)
        elif operation == MoveOperation.LINK:
            util.link(old_art, new_art)
        elif operation == MoveOperation.HARDLINK:
            util.hardlink(old_art, new_art)
        elif operation == MoveOperation.REFLINK:
            util.reflink(old_art, new_art, fallback=False)
        elif operation == MoveOperation.REFLINK_AUTO:
            util.reflink(old_art, new_art, fallback=True)
        else:
            assert False, 'unknown MoveOperation'
        self.artpath = new_art

    def move(self, operation=MoveOperation.MOVE, basedir=None, store=True):
        """Move, copy, link or hardlink (depending on `operation`)
        all items to their destination. Any album art moves along with them.

        `basedir` overrides the library base directory for the destination.

        `operation` should be an instance of `util.MoveOperation`.

        By default, the album is stored to the database, persisting any
        modifications to its metadata. If `store` is `False` however,
        the album is not stored automatically, and you'll have to manually
        store it after invoking this method.
        """
        basedir = basedir or self._db.directory

        # Ensure new metadata is available to items for destination
        # computation.
        if store:
            self.store()

        # Move items.
        items = list(self.items())
        for item in items:
            item.move(operation, basedir=basedir, with_album=False,
                      store=store)

        # Move art.
        self.move_art(operation)
        if store:
            self.store()

    def item_dir(self):
        """Returns the directory containing the album's first item,
        provided that such an item exists.
        """
        item = self.items().get()
        if not item:
            raise ValueError(u'empty album for album id %d' % self.id)
        return os.path.dirname(item.path)

    def _albumtotal(self):
        """Return the total number of tracks on all discs on the album
        """
        if self.disctotal == 1 or not beets.config['per_disc_numbering']:
            return self.items()[0].tracktotal

        counted = []
        total = 0

        for item in self.items():
            if item.disc in counted:
                continue

            total += item.tracktotal
            counted.append(item.disc)

            if len(counted) == self.disctotal:
                break

        return total

    def art_destination(self, image, item_dir=None):
        """Returns a path to the destination for the album art image
        for the album. `image` is the path of the image that will be
        moved there (used for its extension).

        The path construction uses the existing path of the album's
        items, so the album must contain at least one item or
        item_dir must be provided.
        """
        image = bytestring_path(image)
        item_dir = item_dir or self.item_dir()

        filename_tmpl = template(
            beets.config['art_filename'].as_str())
        subpath = self.evaluate_template(filename_tmpl, True)
        if beets.config['asciify_paths']:
            subpath = util.asciify_path(
                subpath,
                beets.config['path_sep_replace'].as_str()
            )
        subpath = util.sanitize_path(subpath,
                                     replacements=self._db.replacements)
        subpath = bytestring_path(subpath)

        _, ext = os.path.splitext(image)
        dest = os.path.join(item_dir, subpath + ext)

        return bytestring_path(dest)

    def set_art(self, path, copy=True):
        """Sets the album's cover art to the image at the given path.
        The image is copied (or moved) into place, replacing any
        existing art.

        Sends an 'art_set' event with `self` as the sole argument.
        """
        path = bytestring_path(path)
        oldart = self.artpath
        artdest = self.art_destination(path)

        if oldart and samefile(path, oldart):
            # Art already set.
            return
        elif samefile(path, artdest):
            # Art already in place.
            self.artpath = path
            return

        # Normal operation.
        if oldart == artdest:
            util.remove(oldart)
        artdest = util.unique_path(artdest)
        if copy:
            util.copy(path, artdest)
        else:
            util.move(path, artdest)
        self.artpath = artdest

        plugins.send('art_set', album=self)

    def store(self, fields=None):
        """Update the database with the album information. The album's
        tracks are also updated.
        :param fields: The fields to be stored. If not specified, all fields
        will be.
        """
        # Get modified track fields.
        track_updates = {}
        for key in self.item_keys:
            if key in self._dirty:
                track_updates[key] = self[key]

        with self._db.transaction():
            super(Album, self).store(fields)
            if track_updates:
                for item in self.items():
                    for key, value in track_updates.items():
                        item[key] = value
                    item.store()

    def try_sync(self, write, move):
        """Synchronize the album and its items with the database.
        Optionally, also write any new tags into the files and update
        their paths.

        `write` indicates whether to write tags to the item files, and
        `move` controls whether files (both audio and album art) are
        moved.
        """
        self.store()
        for item in self.items():
            item.try_sync(write, move)


# Query construction helpers.

def parse_query_parts(parts, model_cls):
    """Given a beets query string as a list of components, return the
    `Query` and `Sort` they represent.

    Like `dbcore.parse_sorted_query`, with beets query prefixes and
    special path query detection.
    """
    # Get query types and their prefix characters.
    prefixes = {':': dbcore.query.RegexpQuery}
    prefixes.update(plugins.queries())

    # Special-case path-like queries, which are non-field queries
    # containing path separators (/).
    path_parts = []
    non_path_parts = []
    for s in parts:
        if PathQuery.is_path_query(s):
            path_parts.append(s)
        else:
            non_path_parts.append(s)

    case_insensitive = beets.config['sort_case_insensitive'].get(bool)

    query, sort = dbcore.parse_sorted_query(
        model_cls, non_path_parts, prefixes, case_insensitive
    )

    # Add path queries to aggregate query.
    # Match field / flexattr depending on whether the model has the path field
    fast_path_query = 'path' in model_cls._fields
    query.subqueries += [PathQuery('path', s, fast_path_query)
                         for s in path_parts]

    return query, sort


def parse_query_string(s, model_cls):
    """Given a beets query string, return the `Query` and `Sort` they
    represent.

    The string is split into components using shell-like syntax.
    """
    message = u"Query is not unicode: {0!r}".format(s)
    assert isinstance(s, six.text_type), message
    try:
        parts = util.shlex_split(s)
    except ValueError as exc:
        raise dbcore.InvalidQueryError(s, exc)
    return parse_query_parts(parts, model_cls)


def _sqlite_bytelower(bytestring):
    """ A custom ``bytelower`` sqlite function so we can compare
        bytestrings in a semi case insensitive fashion.  This is to work
        around sqlite builds are that compiled with
        ``-DSQLITE_LIKE_DOESNT_MATCH_BLOBS``. See
        ``https://github.com/beetbox/beets/issues/2172`` for details.
    """
    if not six.PY2:
        return bytestring.lower()

    return buffer(bytes(bytestring).lower())  # noqa: F821


# The Library: interface to the database.

class Library(dbcore.Database):
    """A database of music containing songs and albums.
    """
    _models = (Item, Album)

    def __init__(self, path='library.blb',
                 directory='~/Music',
                 path_formats=((PF_KEY_DEFAULT,
                               '$artist/$album/$track $title'),),
                 replacements=None):
        timeout = beets.config['timeout'].as_number()
        super(Library, self).__init__(path, timeout=timeout)

        self.directory = bytestring_path(normpath(directory))
        self.path_formats = path_formats
        self.replacements = replacements

        self._memotable = {}  # Used for template substitution performance.

    def _create_connection(self):
        conn = super(Library, self)._create_connection()
        conn.create_function('bytelower', 1, _sqlite_bytelower)
        return conn

    # Adding objects to the database.

    def add(self, obj):
        """Add the :class:`Item` or :class:`Album` object to the library
        database. Return the object's new id.
        """
        obj.add(self)
        self._memotable = {}
        return obj.id

    def add_album(self, items):
        """Create a new album consisting of a list of items.

        The items are added to the database if they don't yet have an
        ID. Return a new :class:`Album` object. The list items must not
        be empty.
        """
        if not items:
            raise ValueError(u'need at least one item')

        # Create the album structure using metadata from the first item.
        values = dict((key, items[0][key]) for key in Album.item_keys)
        album = Album(self, **values)

        # Add the album structure and set the items' album_id fields.
        # Store or add the items.
        with self.transaction():
            album.add(self)
            for item in items:
                item.album_id = album.id
                if item.id is None:
                    item.add(self)
                else:
                    item.store()

        return album

    # Querying.

    def _fetch(self, model_cls, query, sort=None):
        """Parse a query and fetch. If a order specification is present
        in the query string the `sort` argument is ignored.
        """
        # Parse the query, if necessary.
        try:
            parsed_sort = None
            if isinstance(query, six.string_types):
                query, parsed_sort = parse_query_string(query, model_cls)
            elif isinstance(query, (list, tuple)):
                query, parsed_sort = parse_query_parts(query, model_cls)
        except dbcore.query.InvalidQueryArgumentValueError as exc:
            raise dbcore.InvalidQueryError(query, exc)

        # Any non-null sort specified by the parsed query overrides the
        # provided sort.
        if parsed_sort and not isinstance(parsed_sort, dbcore.query.NullSort):
            sort = parsed_sort

        return super(Library, self)._fetch(
            model_cls, query, sort
        )

    @staticmethod
    def get_default_album_sort():
        """Get a :class:`Sort` object for albums from the config option.
        """
        return dbcore.sort_from_strings(
            Album, beets.config['sort_album'].as_str_seq())

    @staticmethod
    def get_default_item_sort():
        """Get a :class:`Sort` object for items from the config option.
        """
        return dbcore.sort_from_strings(
            Item, beets.config['sort_item'].as_str_seq())

    def albums(self, query=None, sort=None):
        """Get :class:`Album` objects matching the query.
        """
        return self._fetch(Album, query, sort or self.get_default_album_sort())

    def items(self, query=None, sort=None):
        """Get :class:`Item` objects matching the query.
        """
        return self._fetch(Item, query, sort or self.get_default_item_sort())

    # Convenience accessors.

    def get_item(self, id):
        """Fetch an :class:`Item` by its ID. Returns `None` if no match is
        found.
        """
        return self._get(Item, id)

    def get_album(self, item_or_id):
        """Given an album ID or an item associated with an album, return
        an :class:`Album` object for the album. If no such album exists,
        returns `None`.
        """
        if isinstance(item_or_id, int):
            album_id = item_or_id
        else:
            album_id = item_or_id.album_id
        if album_id is None:
            return None
        return self._get(Album, album_id)


# Default path template resources.

def _int_arg(s):
    """Convert a string argument to an integer for use in a template
    function.  May raise a ValueError.
    """
    return int(s.strip())


class DefaultTemplateFunctions(object):
    """A container class for the default functions provided to path
    templates. These functions are contained in an object to provide
    additional context to the functions -- specifically, the Item being
    evaluated.
    """
    _prefix = 'tmpl_'

    def __init__(self, item=None, lib=None):
        """Parametrize the functions. If `item` or `lib` is None, then
        some functions (namely, ``aunique``) will always evaluate to the
        empty string.
        """
        self.item = item
        self.lib = lib

    def functions(self):
        """Returns a dictionary containing the functions defined in this
        object. The keys are function names (as exposed in templates)
        and the values are Python functions.
        """
        out = {}
        for key in self._func_names:
            out[key[len(self._prefix):]] = getattr(self, key)
        return out

    @staticmethod
    def tmpl_lower(s):
        """Convert a string to lower case."""
        return s.lower()

    @staticmethod
    def tmpl_upper(s):
        """Covert a string to upper case."""
        return s.upper()

    @staticmethod
    def tmpl_title(s):
        """Convert a string to title case."""
        return string.capwords(s)

    @staticmethod
    def tmpl_left(s, chars):
        """Get the leftmost characters of a string."""
        return s[0:_int_arg(chars)]

    @staticmethod
    def tmpl_right(s, chars):
        """Get the rightmost characters of a string."""
        return s[-_int_arg(chars):]

    @staticmethod
    def tmpl_if(condition, trueval, falseval=u''):
        """If ``condition`` is nonempty and nonzero, emit ``trueval``;
        otherwise, emit ``falseval`` (if provided).
        """
        try:
            int_condition = _int_arg(condition)
        except ValueError:
            if condition.lower() == "false":
                return falseval
        else:
            condition = int_condition

        if condition:
            return trueval
        else:
            return falseval

    @staticmethod
    def tmpl_asciify(s):
        """Translate non-ASCII characters to their ASCII equivalents.
        """
        return util.asciify_path(s, beets.config['path_sep_replace'].as_str())

    @staticmethod
    def tmpl_time(s, fmt):
        """Format a time value using `strftime`.
        """
        cur_fmt = beets.config['time_format'].as_str()
        return time.strftime(fmt, time.strptime(s, cur_fmt))

    def tmpl_aunique(self, keys=None, disam=None, bracket=None):
        """Generate a string that is guaranteed to be unique among all
        albums in the library who share the same set of keys. A fields
        from "disam" is used in the string if one is sufficient to
        disambiguate the albums. Otherwise, a fallback opaque value is
        used. Both "keys" and "disam" should be given as
        whitespace-separated lists of field names, while "bracket" is a
        pair of characters to be used as brackets surrounding the
        disambiguator or empty to have no brackets.
        """
        # Fast paths: no album, no item or library, or memoized value.
        if not self.item or not self.lib:
            return u''

        if isinstance(self.item, Item):
            album_id = self.item.album_id
        elif isinstance(self.item, Album):
            album_id = self.item.id

        if album_id is None:
            return u''

        memokey = ('aunique', keys, disam, album_id)
        memoval = self.lib._memotable.get(memokey)
        if memoval is not None:
            return memoval

        keys = keys or beets.config['aunique']['keys'].as_str()
        disam = disam or beets.config['aunique']['disambiguators'].as_str()
        if bracket is None:
            bracket = beets.config['aunique']['bracket'].as_str()
        keys = keys.split()
        disam = disam.split()

        # Assign a left and right bracket or leave blank if argument is empty.
        if len(bracket) == 2:
            bracket_l = bracket[0]
            bracket_r = bracket[1]
        else:
            bracket_l = u''
            bracket_r = u''

        album = self.lib.get_album(album_id)
        if not album:
            # Do nothing for singletons.
            self.lib._memotable[memokey] = u''
            return u''

        # Find matching albums to disambiguate with.
        subqueries = []
        for key in keys:
            value = album.get(key, '')
            subqueries.append(dbcore.MatchQuery(key, value))
        albums = self.lib.albums(dbcore.AndQuery(subqueries))

        # If there's only one album to matching these details, then do
        # nothing.
        if len(albums) == 1:
            self.lib._memotable[memokey] = u''
            return u''

        # Find the first disambiguator that distinguishes the albums.
        for disambiguator in disam:
            # Get the value for each album for the current field.
            disam_values = set([a.get(disambiguator, '') for a in albums])

            # If the set of unique values is equal to the number of
            # albums in the disambiguation set, we're done -- this is
            # sufficient disambiguation.
            if len(disam_values) == len(albums):
                break

        else:
            # No disambiguator distinguished all fields.
            res = u' {1}{0}{2}'.format(album.id, bracket_l, bracket_r)
            self.lib._memotable[memokey] = res
            return res

        # Flatten disambiguation value into a string.
        disam_value = album.formatted(True).get(disambiguator)

        # Return empty string if disambiguator is empty.
        if disam_value:
            res = u' {1}{0}{2}'.format(disam_value, bracket_l, bracket_r)
        else:
            res = u''

        self.lib._memotable[memokey] = res
        return res

    @staticmethod
    def tmpl_first(s, count=1, skip=0, sep=u'; ', join_str=u'; '):
        """ Gets the item(s) from x to y in a string separated by something
        and join then with something

        :param s: the string
        :param count: The number of items included
        :param skip: The number of items skipped
        :param sep: the separator. Usually is '; ' (default) or '/ '
        :param join_str: the string which will join the items, default '; '.
        """
        skip = int(skip)
        count = skip + int(count)
        return join_str.join(s.split(sep)[skip:count])

    def tmpl_ifdef(self, field, trueval=u'', falseval=u''):
        """ If field exists return trueval or the field (default)
        otherwise, emit return falseval (if provided).

        :param field: The name of the field
        :param trueval: The string if the condition is true
        :param falseval: The string if the condition is false
        :return: The string, based on condition
        """
        if self.item.formatted().get(field):
            return trueval if trueval else self.item.formatted().get(field)
        else:
            return falseval


# Get the name of tmpl_* functions in the above class.
DefaultTemplateFunctions._func_names = \
    [s for s in dir(DefaultTemplateFunctions)
     if s.startswith(DefaultTemplateFunctions._prefix)]
