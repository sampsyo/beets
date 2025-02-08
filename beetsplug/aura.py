# This file is part of beets.
# Copyright 2020, Callum Brown.
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

"""An AURA server using Flask."""

import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from mimetypes import guess_type
from typing import ClassVar

from flask import (
    Blueprint,
    Flask,
    current_app,
    make_response,
    request,
    send_file,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from beets import config
from beets.dbcore.query import (
    AndQuery,
    FixedFieldSort,
    MatchQuery,
    MultipleSort,
    NotQuery,
    RegexpQuery,
    SlowFieldSort,
    SQLiteType,
)
from beets.library import Album, Item, LibModel, Library
from beets.plugins import BeetsPlugin
from beets.ui import Subcommand, _open_library

# Constants

# AURA server information
# TODO: Add version information
SERVER_INFO = {
    "aura-version": "0",
    "server": "beets-aura",
    "server-version": "0.1",
    "auth-required": False,
    "features": ["albums", "artists", "images"],
}

# Maps AURA Track attribute to beets Item attribute
TRACK_ATTR_MAP = {
    # Required
    "title": "title",
    "artist": "artist",
    # Optional
    "album": "album",
    "track": "track",  # Track number on album
    "tracktotal": "tracktotal",
    "disc": "disc",
    "disctotal": "disctotal",
    "year": "year",
    "month": "month",
    "day": "day",
    "bpm": "bpm",
    "genre": "genre",
    "recording-mbid": "mb_trackid",  # beets trackid is MB recording
    "track-mbid": "mb_releasetrackid",
    "composer": "composer",
    "albumartist": "albumartist",
    "comments": "comments",
    # Optional for Audio Metadata
    # TODO: Support the mimetype attribute, format != mime type
    # "mimetype": track.format,
    "duration": "length",
    "framerate": "samplerate",
    # I don't think beets has a framecount field
    # "framecount": ???,
    "channels": "channels",
    "bitrate": "bitrate",
    "bitdepth": "bitdepth",
    "size": "filesize",
}

# Maps AURA Album attribute to beets Album attribute
ALBUM_ATTR_MAP = {
    # Required
    "title": "album",
    "artist": "albumartist",
    # Optional
    "tracktotal": "albumtotal",
    "disctotal": "disctotal",
    "year": "year",
    "month": "month",
    "day": "day",
    "genre": "genre",
    "release-mbid": "mb_albumid",
    "release-group-mbid": "mb_releasegroupid",
}

# Maps AURA Artist attribute to beets Item field
# Artists are not first-class in beets, so information is extracted from
# beets Items.
ARTIST_ATTR_MAP = {
    # Required
    "name": "artist",
    # Optional
    "artist-mbid": "mb_artistid",
}


@dataclass
class AURADocument:
    """Base class for building AURA documents."""

    model_cls: ClassVar[type[LibModel]]

    lib: Library
    args: Mapping[str, str]

    @classmethod
    def from_app(cls) -> Self:
        """Initialise the document using the global app and request."""
        return cls(current_app.config["lib"], request.args)

    @staticmethod
    def error(status, title, detail):
        """Make a response for an error following the JSON:API spec.

        Args:
            status: An HTTP status code string, e.g. "404 Not Found".
            title: A short, human-readable summary of the problem.
            detail: A human-readable explanation specific to this
                occurrence of the problem.
        """
        document = {
            "errors": [{"status": status, "title": title, "detail": detail}]
        }
        return make_response(document, status)

    @classmethod
    def get_attribute_converter(cls, beets_attr: str) -> type[SQLiteType]:
        """Work out what data type an attribute should be for beets.

        Args:
            beets_attr: The name of the beets attribute, e.g. "title".
        """
        try:
            # Look for field in list of Album fields
            # and get python type of database type.
            # See beets.library.Album and beets.dbcore.types
            return cls.model_cls._fields[beets_attr].model_type
        except KeyError:
            # Fall back to string (NOTE: probably not good)
            return str

    def translate_filters(self):
        """Translate filters from request arguments to a beets Query."""
        # The format of each filter key in the request parameter is:
        # filter[<attribute>]. This regex extracts <attribute>.
        pattern = re.compile(r"filter\[(?P<attribute>[a-zA-Z0-9_-]+)\]")
        queries = []
        for key, value in self.args.items():
            match = pattern.match(key)
            if match:
                # Extract attribute name from key
                aura_attr = match.group("attribute")
                # Get the beets version of the attribute name
                beets_attr = self.attribute_map.get(aura_attr, aura_attr)
                converter = self.get_attribute_converter(beets_attr)
                value = converter(value)
                # Add exact match query to list
                # Use a slow query so it works with all fields
                queries.append(
                    self.model_cls.field_query(beets_attr, value, MatchQuery)
                )
        # NOTE: AURA doesn't officially support multiple queries
        return AndQuery(queries)

    def translate_sorts(self, sort_arg):
        """Translate an AURA sort parameter into a beets Sort.

        Args:
            sort_arg: The value of the 'sort' query parameter; a comma
                separated list of fields to sort by, in order.
                E.g. "-year,title".
        """
        # Change HTTP query parameter to a list
        aura_sorts = sort_arg.strip(",").split(",")
        sorts = []
        for aura_attr in aura_sorts:
            if aura_attr[0] == "-":
                ascending = False
                # Remove leading "-"
                aura_attr = aura_attr[1:]
            else:
                # JSON:API default
                ascending = True
            # Get the beets version of the attribute name
            beets_attr = self.attribute_map.get(aura_attr, aura_attr)
            # Use slow sort so it works with all fields (inc. computed)
            sorts.append(SlowFieldSort(beets_attr, ascending=ascending))
        return MultipleSort(sorts)

    def paginate(self, collection):
        """Get a page of the collection and the URL to the next page.

        Args:
            collection: The raw data from which resource objects can be
                built. Could be an sqlite3.Cursor object (tracks and
                albums) or a list of strings (artists).
        """
        # Pages start from zero
        page = self.args.get("page", 0, int)
        # Use page limit defined in config by default.
        default_limit = config["aura"]["page_limit"].get(int)
        limit = self.args.get("limit", default_limit, int)
        # start = offset of first item to return
        start = page * limit
        # end = offset of last item + 1
        end = start + limit
        if end > len(collection):
            end = len(collection)
            next_url = None
        else:
            # Not the last page so work out links.next url
            if not self.args:
                # No existing arguments, so current page is 0
                next_url = request.url + "?page=1"
            elif not self.args.get("page", None):
                # No existing page argument, so add one to the end
                next_url = request.url + "&page=1"
            else:
                # Increment page token by 1
                next_url = request.url.replace(
                    f"page={page}", "page={}".format(page + 1)
                )
        # Get only the items in the page range
        data = [
            self.get_resource_object(self.lib, collection[i])
            for i in range(start, end)
        ]
        return data, next_url

    def get_included(self, data, include_str):
        """Build a list of resource objects for inclusion.

        Args:
            data: An array of dicts in the form of resource objects.
            include_str: A comma separated list of resource types to
                include. E.g. "tracks,images".
        """
        # Change HTTP query parameter to a list
        to_include = include_str.strip(",").split(",")
        # Build a list of unique type and id combinations
        # For each resource object in the primary data, iterate over it's
        # relationships. If a relationship matches one of the types
        # requested for inclusion (e.g. "albums") then add each type-id pair
        # under the "data" key to unique_identifiers, checking first that
        # it has not already been added. This ensures that no resources are
        # included more than once.
        unique_identifiers = []
        for res_obj in data:
            for rel_name, rel_obj in res_obj["relationships"].items():
                if rel_name in to_include:
                    # NOTE: Assumes relationship is to-many
                    for identifier in rel_obj["data"]:
                        if identifier not in unique_identifiers:
                            unique_identifiers.append(identifier)
        # TODO: I think this could be improved
        included = []
        for identifier in unique_identifiers:
            res_type = identifier["type"]
            if res_type == "track":
                track_id = int(identifier["id"])
                track = self.lib.get_item(track_id)
                included.append(
                    TrackDocument.get_resource_object(self.lib, track)
                )
            elif res_type == "album":
                album_id = int(identifier["id"])
                album = self.lib.get_album(album_id)
                included.append(
                    AlbumDocument.get_resource_object(self.lib, album)
                )
            elif res_type == "artist":
                artist_id = identifier["id"]
                included.append(
                    ArtistDocument.get_resource_object(self.lib, artist_id)
                )
            elif res_type == "image":
                image_id = identifier["id"]
                included.append(
                    ImageDocument.get_resource_object(self.lib, image_id)
                )
            else:
                raise ValueError(f"Invalid resource type: {res_type}")
        return included

    def all_resources(self):
        """Build document for /tracks, /albums or /artists."""
        query = self.translate_filters()
        sort_arg = self.args.get("sort", None)
        if sort_arg:
            sort = self.translate_sorts(sort_arg)
            # For each sort field add a query which ensures all results
            # have a non-empty, non-zero value for that field.
            query.subqueries.extend(
                NotQuery(
                    self.model_cls.field_query(s.field, "(^$|^0$)", RegexpQuery)
                )
                for s in sort.sorts
            )
        else:
            sort = None
        # Get information from the library
        collection = self.get_collection(query=query, sort=sort)
        # Convert info to AURA form and paginate it
        data, next_url = self.paginate(collection)
        document = {"data": data}
        # If there are more pages then provide a way to access them
        if next_url:
            document["links"] = {"next": next_url}
        # Include related resources for each element in "data"
        include_str = self.args.get("include", None)
        if include_str:
            document["included"] = self.get_included(data, include_str)
        return document

    def single_resource_document(self, resource_object):
        """Build document for a specific requested resource.

        Args:
            resource_object: A dictionary in the form of a JSON:API
                resource object.
        """
        document = {"data": resource_object}
        include_str = self.args.get("include", None)
        if include_str:
            # [document["data"]] is because arg needs to be list
            document["included"] = self.get_included(
                [document["data"]], include_str
            )
        return document


class TrackDocument(AURADocument):
    """Class for building documents for /tracks endpoints."""

    model_cls = Item

    attribute_map = TRACK_ATTR_MAP

    def get_collection(self, query=None, sort=None):
        """Get Item objects from the library.

        Args:
            query: A beets Query object or a beets query string.
            sort: A beets Sort object.
        """
        return self.lib.items(query, sort)

    @classmethod
    def get_attribute_converter(cls, beets_attr: str) -> type[SQLiteType]:
        """Work out what data type an attribute should be for beets.

        Args:
            beets_attr: The name of the beets attribute, e.g. "title".
        """
        # filesize is a special field (read from disk not db?)
        if beets_attr == "filesize":
            return int

        return super().get_attribute_converter(beets_attr)

    @staticmethod
    def get_resource_object(lib: Library, track):
        """Construct a JSON:API resource object from a beets Item.

        Args:
            track: A beets Item object.
        """
        attributes = {}
        # Use aura => beets attribute map, e.g. size => filesize
        for aura_attr, beets_attr in TRACK_ATTR_MAP.items():
            a = getattr(track, beets_attr)
            # Only set attribute if it's not None, 0, "", etc.
            # NOTE: This could result in required attributes not being set
            if a:
                attributes[aura_attr] = a

        # JSON:API one-to-many relationship to parent album
        relationships = {
            "artists": {"data": [{"type": "artist", "id": track.artist}]}
        }
        # Only add album relationship if not singleton
        if not track.singleton:
            relationships["albums"] = {
                "data": [{"type": "album", "id": str(track.album_id)}]
            }

        return {
            "type": "track",
            "id": str(track.id),
            "attributes": attributes,
            "relationships": relationships,
        }

    def single_resource(self, track_id):
        """Get track from the library and build a document.

        Args:
            track_id: The beets id of the track (integer).
        """
        track = self.lib.get_item(track_id)
        if not track:
            return self.error(
                "404 Not Found",
                "No track with the requested id.",
                "There is no track with an id of {} in the library.".format(
                    track_id
                ),
            )
        return self.single_resource_document(
            self.get_resource_object(self.lib, track)
        )


class AlbumDocument(AURADocument):
    """Class for building documents for /albums endpoints."""

    model_cls = Album

    attribute_map = ALBUM_ATTR_MAP

    def get_collection(self, query=None, sort=None):
        """Get Album objects from the library.

        Args:
            query: A beets Query object or a beets query string.
            sort: A beets Sort object.
        """
        return self.lib.albums(query, sort)

    @staticmethod
    def get_resource_object(lib: Library, album):
        """Construct a JSON:API resource object from a beets Album.

        Args:
            album: A beets Album object.
        """
        attributes = {}
        # Use aura => beets attribute name map
        for aura_attr, beets_attr in ALBUM_ATTR_MAP.items():
            a = getattr(album, beets_attr)
            # Only set attribute if it's not None, 0, "", etc.
            # NOTE: This could mean required attributes are not set
            if a:
                attributes[aura_attr] = a

        # Get beets Item objects for all tracks in the album sorted by
        # track number. Sorting is not required but it's nice.
        query = MatchQuery("album_id", album.id)
        sort = FixedFieldSort("track", ascending=True)
        tracks = lib.items(query, sort)
        # JSON:API one-to-many relationship to tracks on the album
        relationships = {
            "tracks": {
                "data": [{"type": "track", "id": str(t.id)} for t in tracks]
            }
        }
        # Add images relationship if album has associated images
        if album.artpath:
            path = os.fsdecode(album.artpath)
            filename = path.split("/")[-1]
            image_id = f"album-{album.id}-{filename}"
            relationships["images"] = {
                "data": [{"type": "image", "id": image_id}]
            }
        # Add artist relationship if artist name is same on tracks
        # Tracks are used to define artists so don't albumartist
        # Check for all tracks in case some have featured artists
        if album.albumartist in [t.artist for t in tracks]:
            relationships["artists"] = {
                "data": [{"type": "artist", "id": album.albumartist}]
            }

        return {
            "type": "album",
            "id": str(album.id),
            "attributes": attributes,
            "relationships": relationships,
        }

    def single_resource(self, album_id):
        """Get album from the library and build a document.

        Args:
            album_id: The beets id of the album (integer).
        """
        album = self.lib.get_album(album_id)
        if not album:
            return self.error(
                "404 Not Found",
                "No album with the requested id.",
                "There is no album with an id of {} in the library.".format(
                    album_id
                ),
            )
        return self.single_resource_document(
            self.get_resource_object(self.lib, album)
        )


class ArtistDocument(AURADocument):
    """Class for building documents for /artists endpoints."""

    model_cls = Item

    attribute_map = ARTIST_ATTR_MAP

    def get_collection(self, query=None, sort=None):
        """Get a list of artist names from the library.

        Args:
            query: A beets Query object or a beets query string.
            sort: A beets Sort object.
        """
        # Gets only tracks with matching artist information
        tracks = self.lib.items(query, sort)
        collection = []
        for track in tracks:
            # Do not add duplicates
            if track.artist not in collection:
                collection.append(track.artist)
        return collection

    @staticmethod
    def get_resource_object(lib: Library, artist_id):
        """Construct a JSON:API resource object for the given artist.

        Args:
            artist_id: A string which is the artist's name.
        """
        # Get tracks where artist field exactly matches artist_id
        query = MatchQuery("artist", artist_id)
        tracks = lib.items(query)
        if not tracks:
            return None

        # Get artist information from the first track
        # NOTE: It could be that the first track doesn't have a
        # MusicBrainz id but later tracks do, which isn't ideal.
        attributes = {}
        # Use aura => beets attribute map, e.g. artist => name
        for aura_attr, beets_attr in ARTIST_ATTR_MAP.items():
            a = getattr(tracks[0], beets_attr)
            # Only set attribute if it's not None, 0, "", etc.
            # NOTE: This could mean required attributes are not set
            if a:
                attributes[aura_attr] = a

        relationships = {
            "tracks": {
                "data": [{"type": "track", "id": str(t.id)} for t in tracks]
            }
        }
        album_query = MatchQuery("albumartist", artist_id)
        albums = lib.albums(query=album_query)
        if len(albums) != 0:
            relationships["albums"] = {
                "data": [{"type": "album", "id": str(a.id)} for a in albums]
            }

        return {
            "type": "artist",
            "id": artist_id,
            "attributes": attributes,
            "relationships": relationships,
        }

    def single_resource(self, artist_id):
        """Get info for the requested artist and build a document.

        Args:
            artist_id: A string which is the artist's name.
        """
        artist_resource = self.get_resource_object(self.lib, artist_id)
        if not artist_resource:
            return self.error(
                "404 Not Found",
                "No artist with the requested id.",
                "There is no artist with an id of {} in the library.".format(
                    artist_id
                ),
            )
        return self.single_resource_document(artist_resource)


def safe_filename(fn):
    """Check whether a string is a simple (non-path) filename.

    For example, `foo.txt` is safe because it is a "plain" filename. But
    `foo/bar.txt` and `../foo.txt` and `.` are all non-safe because they
    can traverse to other directories other than the current one.
    """
    # Rule out any directories.
    if os.path.basename(fn) != fn:
        return False

    # In single names, rule out Unix directory traversal names.
    if fn in (".", ".."):
        return False

    return True


class ImageDocument(AURADocument):
    """Class for building documents for /images/(id) endpoints."""

    model_cls = Album

    @staticmethod
    def get_image_path(lib: Library, image_id):
        """Works out the full path to the image with the given id.

        Returns None if there is no such image.

        Args:
            image_id: A string in the form
                "<parent_type>-<parent_id>-<img_filename>".
        """
        # Split image_id into its constituent parts
        id_split = image_id.split("-")
        if len(id_split) < 3:
            # image_id is not in the required format
            return None
        parent_type = id_split[0]
        parent_id = id_split[1]
        img_filename = "-".join(id_split[2:])
        if not safe_filename(img_filename):
            return None

        # Get the path to the directory parent's images are in
        if parent_type == "album":
            album = lib.get_album(int(parent_id))
            if not album or not album.artpath:
                return None
            # Cut the filename off of artpath
            # This is in preparation for supporting images in the same
            # directory that are not tracked by beets.
            artpath = os.fsdecode(album.artpath)
            dir_path = "/".join(artpath.split("/")[:-1])
        else:
            # Images for other resource types are not supported
            return None

        img_path = os.path.join(dir_path, img_filename)
        # Check the image actually exists
        if os.path.isfile(img_path):
            return img_path
        else:
            return None

    @staticmethod
    def get_resource_object(lib: Library, image_id):
        """Construct a JSON:API resource object for the given image.

        Args:
            image_id: A string in the form
                "<parent_type>-<parent_id>-<img_filename>".
        """
        # Could be called as a static method, so can't use
        # self.get_image_path()
        image_path = ImageDocument.get_image_path(lib, image_id)
        if not image_path:
            return None

        attributes = {
            "role": "cover",
            "mimetype": guess_type(image_path)[0],
            "size": os.path.getsize(image_path),
        }
        try:
            from PIL import Image
        except ImportError:
            pass
        else:
            im = Image.open(image_path)
            attributes["width"] = im.width
            attributes["height"] = im.height

        relationships = {}
        # Split id into [parent_type, parent_id, filename]
        id_split = image_id.split("-")
        relationships[id_split[0] + "s"] = {
            "data": [{"type": id_split[0], "id": id_split[1]}]
        }

        return {
            "id": image_id,
            "type": "image",
            # Remove attributes that are None, 0, "", etc.
            "attributes": {k: v for k, v in attributes.items() if v},
            "relationships": relationships,
        }

    def single_resource(self, image_id):
        """Get info for the requested image and build a document.

        Args:
            image_id: A string in the form
                "<parent_type>-<parent_id>-<img_filename>".
        """
        image_resource = self.get_resource_object(self.lib, image_id)
        if not image_resource:
            return self.error(
                "404 Not Found",
                "No image with the requested id.",
                "There is no image with an id of {} in the library.".format(
                    image_id
                ),
            )
        return self.single_resource_document(image_resource)


# Initialise flask blueprint
aura_bp = Blueprint("aura_bp", __name__)


@aura_bp.route("/server")
def server_info():
    """Respond with info about the server."""
    return {"data": {"type": "server", "id": "0", "attributes": SERVER_INFO}}


# Track endpoints


@aura_bp.route("/tracks")
def all_tracks():
    """Respond with a list of all tracks and related information."""
    return TrackDocument.from_app().all_resources()


@aura_bp.route("/tracks/<int:track_id>")
def single_track(track_id):
    """Respond with info about the specified track.

    Args:
        track_id: The id of the track provided in the URL (integer).
    """
    return TrackDocument.from_app().single_resource(track_id)


@aura_bp.route("/tracks/<int:track_id>/audio")
def audio_file(track_id):
    """Supply an audio file for the specified track.

    Args:
        track_id: The id of the track provided in the URL (integer).
    """
    track = current_app.config["lib"].get_item(track_id)
    if not track:
        return AURADocument.error(
            "404 Not Found",
            "No track with the requested id.",
            "There is no track with an id of {} in the library.".format(
                track_id
            ),
        )

    path = os.fsdecode(track.path)
    if not os.path.isfile(path):
        return AURADocument.error(
            "404 Not Found",
            "No audio file for the requested track.",
            (
                "There is no audio file for track {} at the expected location"
            ).format(track_id),
        )

    file_mimetype = guess_type(path)[0]
    if not file_mimetype:
        return AURADocument.error(
            "500 Internal Server Error",
            "Requested audio file has an unknown mimetype.",
            (
                "The audio file for track {} has an unknown mimetype. "
                "Its file extension is {}."
            ).format(track_id, path.split(".")[-1]),
        )

    # Check that the Accept header contains the file's mimetype
    # Takes into account */* and audio/*
    # Adding support for the bitrate parameter would require some effort so I
    # left it out. This means the client could be sent an error even if the
    # audio doesn't need transcoding.
    if not request.accept_mimetypes.best_match([file_mimetype]):
        return AURADocument.error(
            "406 Not Acceptable",
            "Unsupported MIME type or bitrate parameter in Accept header.",
            (
                "The audio file for track {} is only available as {} and "
                "bitrate parameters are not supported."
            ).format(track_id, file_mimetype),
        )

    return send_file(
        path,
        mimetype=file_mimetype,
        # Handles filename in Content-Disposition header
        as_attachment=True,
        # Tries to upgrade the stream to support range requests
        conditional=True,
    )


# Album endpoints


@aura_bp.route("/albums")
def all_albums():
    """Respond with a list of all albums and related information."""
    return AlbumDocument.from_app().all_resources()


@aura_bp.route("/albums/<int:album_id>")
def single_album(album_id):
    """Respond with info about the specified album.

    Args:
        album_id: The id of the album provided in the URL (integer).
    """
    return AlbumDocument.from_app().single_resource(album_id)


# Artist endpoints
# Artist ids are their names


@aura_bp.route("/artists")
def all_artists():
    """Respond with a list of all artists and related information."""
    return ArtistDocument.from_app().all_resources()


# Using the path converter allows slashes in artist_id
@aura_bp.route("/artists/<path:artist_id>")
def single_artist(artist_id):
    """Respond with info about the specified artist.

    Args:
        artist_id: The id of the artist provided in the URL. A string
            which is the artist's name.
    """
    return ArtistDocument.from_app().single_resource(artist_id)


# Image endpoints
# Image ids are in the form <parent_type>-<parent_id>-<img_filename>
# For example: album-13-cover.jpg


@aura_bp.route("/images/<string:image_id>")
def single_image(image_id):
    """Respond with info about the specified image.

    Args:
        image_id: The id of the image provided in the URL. A string in
            the form "<parent_type>-<parent_id>-<img_filename>".
    """
    return ImageDocument.from_app().single_resource(image_id)


@aura_bp.route("/images/<string:image_id>/file")
def image_file(image_id):
    """Supply an image file for the specified image.

    Args:
        image_id: The id of the image provided in the URL. A string in
            the form "<parent_type>-<parent_id>-<img_filename>".
    """
    img_path = ImageDocument.get_image_path(current_app.config["lib"], image_id)
    if not img_path:
        return AURADocument.error(
            "404 Not Found",
            "No image with the requested id.",
            "There is no image with an id of {} in the library".format(
                image_id
            ),
        )
    return send_file(img_path)


# WSGI app


def create_app():
    """An application factory for use by a WSGI server."""
    config["aura"].add(
        {
            "host": "127.0.0.1",
            "port": 8337,
            "cors": [],
            "cors_supports_credentials": False,
            "page_limit": 500,
        }
    )

    app = Flask(__name__)
    # Register AURA blueprint view functions under a URL prefix
    app.register_blueprint(aura_bp, url_prefix="/aura")
    # AURA specifies mimetype MUST be this
    app.config["JSONIFY_MIMETYPE"] = "application/vnd.api+json"
    # Disable auto-sorting of JSON keys
    app.config["JSON_SORT_KEYS"] = False
    # Provide a way to access the beets library
    # The normal method of using the Library and config provided in the
    # command function is not used because create_app() could be called
    # by an external WSGI server.
    # NOTE: this uses a 'private' function from beets.ui.__init__
    app.config["lib"] = _open_library(config)

    # Enable CORS if required
    cors = config["aura"]["cors"].as_str_seq(list)
    if cors:
        from flask_cors import CORS

        # "Accept" is the only header clients use
        app.config["CORS_ALLOW_HEADERS"] = "Accept"
        app.config["CORS_RESOURCES"] = {r"/aura/*": {"origins": cors}}
        app.config["CORS_SUPPORTS_CREDENTIALS"] = config["aura"][
            "cors_supports_credentials"
        ].get(bool)
        CORS(app)

    return app


# Beets Plugin Hook


class AURAPlugin(BeetsPlugin):
    """The BeetsPlugin subclass for the AURA server plugin."""

    def __init__(self):
        """Add configuration options for the AURA plugin."""
        super().__init__()

    def commands(self):
        """Add subcommand used to run the AURA server."""

        def run_aura(lib, opts, args):
            """Run the application using Flask's built in-server.

            Args:
                lib: A beets Library object (not used).
                opts: Command line options. An optparse.Values object.
                args: The list of arguments to process (not used).
            """
            app = create_app()
            # Start the built-in server (not intended for production)
            app.run(
                host=self.config["host"].get(str),
                port=self.config["port"].get(int),
                debug=opts.debug,
                threaded=True,
            )

        run_aura_cmd = Subcommand("aura", help="run an AURA server")
        run_aura_cmd.parser.add_option(
            "-d",
            "--debug",
            action="store_true",
            default=False,
            help="use Flask debug mode",
        )
        run_aura_cmd.func = run_aura
        return [run_aura_cmd]
