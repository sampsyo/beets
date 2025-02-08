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

"""Facilities for automatically determining files' correct metadata."""

from collections.abc import Mapping, Sequence
from typing import Union

from beets import config, logging
from beets.library import Album, Item, LibModel

# Parts of external interface.
from beets.util import unique_list

from .hooks import AlbumInfo, AlbumMatch, Distance, TrackInfo, TrackMatch
from .match import (
    Proposal,
    Recommendation,
    current_metadata,
    tag_album,
    tag_item,
)

__all__ = [
    "AlbumInfo",
    "AlbumMatch",
    "Distance",
    "TrackInfo",
    "TrackMatch",
    "Proposal",
    "Recommendation",
    "apply_album_metadata",
    "apply_item_metadata",
    "apply_metadata",
    "current_metadata",
    "tag_album",
    "tag_item",
]

# Global logger.
log = logging.getLogger("beets")

# Metadata fields that are already hardcoded, or where the tag name changes.
SPECIAL_FIELDS = {
    "album": (
        "va",
        "releasegroup_id",
        "artist_id",
        "artists_ids",
        "album_id",
        "mediums",
        "tracks",
        "year",
        "month",
        "day",
        "artist",
        "artists",
        "artist_credit",
        "artists_credit",
        "artist_sort",
        "artists_sort",
        "data_url",
    ),
    "track": (
        "track_alt",
        "artist_id",
        "artists_ids",
        "release_track_id",
        "medium",
        "index",
        "medium_index",
        "title",
        "artist_credit",
        "artists_credit",
        "artist_sort",
        "artists_sort",
        "artist",
        "artists",
        "track_id",
        "medium_total",
        "data_url",
        "length",
    ),
}


# Additional utilities for the main interface.


def _apply_metadata(
    info: Union[AlbumInfo, TrackInfo],
    db_obj: Union[Album, Item],
    nullable_fields: Sequence[str] = [],
):
    """Set the db_obj's metadata to match the info."""
    special_fields = SPECIAL_FIELDS[
        "album" if isinstance(info, AlbumInfo) else "track"
    ]

    for field, value in info.items():
        # We only overwrite fields that are not already hardcoded.
        if field in special_fields:
            continue

        # Don't overwrite fields with empty values unless the
        # field is explicitly allowed to be overwritten.
        if value is None and field not in nullable_fields:
            continue

        db_obj[field] = value


def correct_list_fields(m: LibModel) -> None:
    """Synchronise single and list values for the list fields that we use.

    That is, ensure the same value in the single field and the first element
    in the list.

    For context, the value we set as, say, ``mb_artistid`` is simply ignored:
    Under the current :class:`MediaFile` implementation, fields ``albumtype``,
    ``mb_artistid`` and ``mb_albumartistid`` are mapped to the first element of
    ``albumtypes``, ``mb_artistids`` and ``mb_albumartistids`` respectively.

    This means setting ``mb_artistid`` has no effect. However, beets
    functionality still assumes that ``mb_artistid`` is independent and stores
    its value in the database. If ``mb_artistid`` != ``mb_artistids[0]``,
    ``beet write`` command thinks that ``mb_artistid`` is modified and tries to
    update the field in the file. Of course nothing happens, so the same diff
    is shown every time the command is run.

    We can avoid this issue by ensuring that ``mb_artistid`` has the same value
    as ``mb_artistids[0]``, and that's what this function does.

    Note: :class:`Album` model does not have ``mb_artistids`` and
    ``mb_albumartistids`` fields therefore we need to check for their presence.
    """

    def ensure_first_value(single_field: str, list_field: str) -> None:
        """Ensure the first ``list_field`` item is equal to ``single_field``."""
        single_val, list_val = getattr(m, single_field), getattr(m, list_field)
        if single_val:
            setattr(m, list_field, unique_list([single_val, *list_val]))
        elif list_val:
            setattr(m, single_field, list_val[0])

    ensure_first_value("albumtype", "albumtypes")

    if hasattr(m, "mb_artistids"):
        ensure_first_value("mb_artistid", "mb_artistids")

    if hasattr(m, "mb_albumartistids"):
        ensure_first_value("mb_albumartistid", "mb_albumartistids")


def apply_item_metadata(item: Item, track_info: TrackInfo):
    """Set an item's metadata from its matched TrackInfo object."""
    item.artist = track_info.artist
    item.artists = track_info.artists
    item.artist_sort = track_info.artist_sort
    item.artists_sort = track_info.artists_sort
    item.artist_credit = track_info.artist_credit
    item.artists_credit = track_info.artists_credit
    item.title = track_info.title
    item.mb_trackid = track_info.track_id
    item.mb_releasetrackid = track_info.release_track_id
    if track_info.artist_id:
        item.mb_artistid = track_info.artist_id
    if track_info.artists_ids:
        item.mb_artistids = track_info.artists_ids

    _apply_metadata(track_info, item)
    correct_list_fields(item)

    # At the moment, the other metadata is left intact (including album
    # and track number). Perhaps these should be emptied?


def apply_album_metadata(album_info: AlbumInfo, album: Album):
    """Set the album's metadata to match the AlbumInfo object."""
    _apply_metadata(album_info, album)
    correct_list_fields(album)


def apply_metadata(album_info: AlbumInfo, mapping: Mapping[Item, TrackInfo]):
    """Set the items' metadata to match an AlbumInfo object using a
    mapping from Items to TrackInfo objects.
    """
    for item, track_info in mapping.items():
        # Artist or artist credit.
        if config["artist_credit"]:
            item.artist = (
                track_info.artist_credit
                or track_info.artist
                or album_info.artist_credit
                or album_info.artist
            )
            item.artists = (
                track_info.artists_credit
                or track_info.artists
                or album_info.artists_credit
                or album_info.artists
            )
            item.albumartist = album_info.artist_credit or album_info.artist
            item.albumartists = album_info.artists_credit or album_info.artists
        else:
            item.artist = track_info.artist or album_info.artist
            item.artists = track_info.artists or album_info.artists
            item.albumartist = album_info.artist
            item.albumartists = album_info.artists

        # Album.
        item.album = album_info.album

        # Artist sort and credit names.
        item.artist_sort = track_info.artist_sort or album_info.artist_sort
        item.artists_sort = track_info.artists_sort or album_info.artists_sort
        item.artist_credit = (
            track_info.artist_credit or album_info.artist_credit
        )
        item.artists_credit = (
            track_info.artists_credit or album_info.artists_credit
        )
        item.albumartist_sort = album_info.artist_sort
        item.albumartists_sort = album_info.artists_sort
        item.albumartist_credit = album_info.artist_credit
        item.albumartists_credit = album_info.artists_credit

        # Release date.
        for prefix in "", "original_":
            if config["original_date"] and not prefix:
                # Ignore specific release date.
                continue

            for suffix in "year", "month", "day":
                key = prefix + suffix
                value = getattr(album_info, key) or 0

                # If we don't even have a year, apply nothing.
                if suffix == "year" and not value:
                    break

                # Otherwise, set the fetched value (or 0 for the month
                # and day if not available).
                item[key] = value

                # If we're using original release date for both fields,
                # also set item.year = info.original_year, etc.
                if config["original_date"]:
                    item[suffix] = value

        # Title.
        item.title = track_info.title

        if config["per_disc_numbering"]:
            # We want to let the track number be zero, but if the medium index
            # is not provided we need to fall back to the overall index.
            if track_info.medium_index is not None:
                item.track = track_info.medium_index
            else:
                item.track = track_info.index
            item.tracktotal = track_info.medium_total or len(album_info.tracks)
        else:
            item.track = track_info.index
            item.tracktotal = len(album_info.tracks)

        # Disc and disc count.
        item.disc = track_info.medium
        item.disctotal = album_info.mediums

        # MusicBrainz IDs.
        item.mb_trackid = track_info.track_id
        item.mb_releasetrackid = track_info.release_track_id
        item.mb_albumid = album_info.album_id
        if track_info.artist_id:
            item.mb_artistid = track_info.artist_id
        else:
            item.mb_artistid = album_info.artist_id

        if track_info.artists_ids:
            item.mb_artistids = track_info.artists_ids
        else:
            item.mb_artistids = album_info.artists_ids

        item.mb_albumartistid = album_info.artist_id
        item.mb_albumartistids = album_info.artists_ids
        item.mb_releasegroupid = album_info.releasegroup_id

        # Compilation flag.
        item.comp = album_info.va

        # Track alt.
        item.track_alt = track_info.track_alt

        _apply_metadata(
            album_info,
            item,
            nullable_fields=config["overwrite_null"]["album"].as_str_seq(),
        )

        _apply_metadata(
            track_info,
            item,
            nullable_fields=config["overwrite_null"]["track"].as_str_seq(),
        )

        correct_list_fields(item)
