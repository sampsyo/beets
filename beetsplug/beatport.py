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

"""Adds Beatport release and track search support to the autotagger"""

import json
import re
from datetime import datetime, timedelta

import confuse
from requests_oauthlib import OAuth1Session
from requests_oauthlib.oauth1_session import (
    TokenMissing,
    TokenRequestDenied,
    VerifierMissing,
)

import beets
import beets.ui
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.plugins import BeetsPlugin, MetadataSourcePlugin, get_distance
from beets.util.id_extractors import beatport_id_regex

AUTH_ERRORS = (TokenRequestDenied, TokenMissing, VerifierMissing)
USER_AGENT = f"beets/{beets.__version__} +https://beets.io/"


class BeatportAPIError(Exception):
    pass


class BeatportObject:
    def __init__(self, data):
        self.beatport_id = data["id"]
        self.name = str(data["name"])
        if "releaseDate" in data:
            self.release_date = datetime.strptime(
                data["releaseDate"], "%Y-%m-%d"
            )
        if "artists" in data:
            self.artists = [(x["id"], str(x["name"])) for x in data["artists"]]
        if "genres" in data:
            self.genres = [str(x["name"]) for x in data["genres"]]


class BeatportClient:
    _api_base = "https://oauth-api.beatport.com"

    def __init__(self, c_key, c_secret, auth_key=None, auth_secret=None):
        """Initiate the client with OAuth information.

        For the initial authentication with the backend `auth_key` and
        `auth_secret` can be `None`. Use `get_authorize_url` and
        `get_access_token` to obtain them for subsequent uses of the API.

        :param c_key:       OAuth1 client key
        :param c_secret:    OAuth1 client secret
        :param auth_key:    OAuth1 resource owner key
        :param auth_secret: OAuth1 resource owner secret
        """
        self.api = OAuth1Session(
            client_key=c_key,
            client_secret=c_secret,
            resource_owner_key=auth_key,
            resource_owner_secret=auth_secret,
            callback_uri="oob",
        )
        self.api.headers = {"User-Agent": USER_AGENT}

    def get_authorize_url(self):
        """Generate the URL for the user to authorize the application.

        Retrieves a request token from the Beatport API and returns the
        corresponding authorization URL on their end that the user has
        to visit.

        This is the first step of the initial authorization process with the
        API. Once the user has visited the URL, call
        :py:method:`get_access_token` with the displayed data to complete
        the process.

        :returns:   Authorization URL for the user to visit
        :rtype:     unicode
        """
        self.api.fetch_request_token(
            self._make_url("/identity/1/oauth/request-token")
        )
        return self.api.authorization_url(
            self._make_url("/identity/1/oauth/authorize")
        )

    def get_access_token(self, auth_data):
        """Obtain the final access token and secret for the API.

        :param auth_data:   URL-encoded authorization data as displayed at
                            the authorization url (obtained via
                            :py:meth:`get_authorize_url`) after signing in
        :type auth_data:    unicode
        :returns:           OAuth resource owner key and secret
        :rtype:             (unicode, unicode) tuple
        """
        self.api.parse_authorization_response(
            "https://beets.io/auth?" + auth_data
        )
        access_data = self.api.fetch_access_token(
            self._make_url("/identity/1/oauth/access-token")
        )
        return access_data["oauth_token"], access_data["oauth_token_secret"]

    def search(self, query, release_type="release", details=True):
        """Perform a search of the Beatport catalogue.

        :param query:           Query string
        :param release_type:    Type of releases to search for, can be
                                'release' or 'track'
        :param details:         Retrieve additional information about the
                                search results. Currently this will fetch
                                the tracklist for releases and do nothing for
                                tracks
        :returns:               Search results
        :rtype:                 generator that yields
                                py:class:`BeatportRelease` or
                                :py:class:`BeatportTrack`
        """
        response = self._get(
            "catalog/3/search",
            query=query,
            perPage=5,
            facets=[f"fieldType:{release_type}"],
        )
        for item in response:
            if release_type == "release":
                if details:
                    release = self.get_release(item["id"])
                else:
                    release = BeatportRelease(item)
                yield release
            elif release_type == "track":
                yield BeatportTrack(item)

    def get_release(self, beatport_id):
        """Get information about a single release.

        :param beatport_id:     Beatport ID of the release
        :returns:               The matching release
        :rtype:                 :py:class:`BeatportRelease`
        """
        response = self._get("/catalog/3/releases", id=beatport_id)
        if response:
            release = BeatportRelease(response[0])
            release.tracks = self.get_release_tracks(beatport_id)
            return release
        return None

    def get_release_tracks(self, beatport_id):
        """Get all tracks for a given release.

        :param beatport_id:     Beatport ID of the release
        :returns:               Tracks in the matching release
        :rtype:                 list of :py:class:`BeatportTrack`
        """
        response = self._get(
            "/catalog/3/tracks", releaseId=beatport_id, perPage=100
        )
        return [BeatportTrack(t) for t in response]

    def get_track(self, beatport_id):
        """Get information about a single track.

        :param beatport_id:     Beatport ID of the track
        :returns:               The matching track
        :rtype:                 :py:class:`BeatportTrack`
        """
        response = self._get("/catalog/3/tracks", id=beatport_id)
        return BeatportTrack(response[0])

    def _make_url(self, endpoint):
        """Get complete URL for a given API endpoint."""
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        return self._api_base + endpoint

    def _get(self, endpoint, **kwargs):
        """Perform a GET request on a given API endpoint.

        Automatically extracts result data from the response and converts HTTP
        exceptions into :py:class:`BeatportAPIError` objects.
        """
        try:
            response = self.api.get(self._make_url(endpoint), params=kwargs)
        except Exception as e:
            raise BeatportAPIError(f"Error connecting to Beatport API: {e}")
        if not response:
            raise BeatportAPIError(
                f"Error {response.status_code} for '{response.request.path_url}"
            )
        return response.json()["results"]


class BeatportRelease(BeatportObject):
    def __str__(self):
        if len(self.artists) < 4:
            artist_str = ", ".join(x[1] for x in self.artists)
        else:
            artist_str = "Various Artists"
        return f"<BeatportRelease: {artist_str} - {self.name} ({self.catalog_number})>"

    def __repr__(self):
        return str(self).encode("utf-8")

    def __init__(self, data):
        BeatportObject.__init__(self, data)
        if "catalogNumber" in data:
            self.catalog_number = data["catalogNumber"]
        if "label" in data:
            self.label_name = data["label"]["name"]
        if "category" in data:
            self.category = data["category"]
        if "slug" in data:
            self.url = "https://beatport.com/release/{}/{}".format(
                data["slug"], data["id"]
            )
        self.genre = data.get("genre")


class BeatportTrack(BeatportObject):
    def __str__(self):
        artist_str = ", ".join(x[1] for x in self.artists)
        return f"<BeatportTrack: {artist_str} - {self.name} ({self.mix_name})>"

    def __repr__(self):
        return str(self).encode("utf-8")

    def __init__(self, data):
        BeatportObject.__init__(self, data)
        if "title" in data:
            self.title = str(data["title"])
        if "mixName" in data:
            self.mix_name = str(data["mixName"])
        self.length = timedelta(milliseconds=data.get("lengthMs", 0) or 0)
        if not self.length:
            try:
                min, sec = data.get("length", "0:0").split(":")
                self.length = timedelta(minutes=int(min), seconds=int(sec))
            except ValueError:
                pass
        if "slug" in data:
            self.url = "https://beatport.com/track/{}/{}".format(
                data["slug"], data["id"]
            )
        self.track_number = data.get("trackNumber")
        self.bpm = data.get("bpm")
        self.initial_key = str((data.get("key") or {}).get("shortName"))

        # Use 'subgenre' and if not present, 'genre' as a fallback.
        if data.get("subGenres"):
            self.genre = str(data["subGenres"][0].get("name"))
        elif data.get("genres"):
            self.genre = str(data["genres"][0].get("name"))


class BeatportPlugin(BeetsPlugin):
    data_source = "Beatport"
    id_regex = beatport_id_regex

    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "apikey": "57713c3906af6f5def151b33601389176b37b429",
                "apisecret": "b3fe08c93c80aefd749fe871a16cd2bb32e2b954",
                "tokenfile": "beatport_token.json",
                "source_weight": 0.5,
            }
        )
        self.config["apikey"].redact = True
        self.config["apisecret"].redact = True
        self.client = None
        self.register_listener("import_begin", self.setup)

    def setup(self, session=None):
        c_key = self.config["apikey"].as_str()
        c_secret = self.config["apisecret"].as_str()

        # Get the OAuth token from a file or log in.
        try:
            with open(self._tokenfile()) as f:
                tokendata = json.load(f)
        except OSError:
            # No token yet. Generate one.
            token, secret = self.authenticate(c_key, c_secret)
        else:
            token = tokendata["token"]
            secret = tokendata["secret"]

        self.client = BeatportClient(c_key, c_secret, token, secret)

    def authenticate(self, c_key, c_secret):
        # Get the link for the OAuth page.
        auth_client = BeatportClient(c_key, c_secret)
        try:
            url = auth_client.get_authorize_url()
        except AUTH_ERRORS as e:
            self._log.debug("authentication error: {0}", e)
            raise beets.ui.UserError("communication with Beatport failed")

        beets.ui.print_("To authenticate with Beatport, visit:")
        beets.ui.print_(url)

        # Ask for the verifier data and validate it.
        data = beets.ui.input_("Enter the string displayed in your browser:")
        try:
            token, secret = auth_client.get_access_token(data)
        except AUTH_ERRORS as e:
            self._log.debug("authentication error: {0}", e)
            raise beets.ui.UserError("Beatport token request failed")

        # Save the token for later use.
        self._log.debug("Beatport token {0}, secret {1}", token, secret)
        with open(self._tokenfile(), "w") as f:
            json.dump({"token": token, "secret": secret}, f)

        return token, secret

    def _tokenfile(self):
        """Get the path to the JSON file for storing the OAuth token."""
        return self.config["tokenfile"].get(confuse.Filename(in_app_dir=True))

    def album_distance(self, items, album_info, mapping):
        """Returns the Beatport source weight and the maximum source weight
        for albums.
        """
        return get_distance(
            data_source=self.data_source, info=album_info, config=self.config
        )

    def track_distance(self, item, track_info):
        """Returns the Beatport source weight and the maximum source weight
        for individual tracks.
        """
        return get_distance(
            data_source=self.data_source, info=track_info, config=self.config
        )

    def candidates(self, items, artist, release, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for beatport search results
        matching release and artist (if not various).
        """
        if va_likely:
            query = release
        else:
            query = f"{artist} {release}"
        try:
            return self._get_releases(query)
        except BeatportAPIError as e:
            self._log.debug("API Error: {0} (query: {1})", e, query)
            return []

    def item_candidates(self, item, artist, title):
        """Returns a list of TrackInfo objects for beatport search results
        matching title and artist.
        """
        query = f"{artist} {title}"
        try:
            return self._get_tracks(query)
        except BeatportAPIError as e:
            self._log.debug("API Error: {0} (query: {1})", e, query)
            return []

    def album_for_id(self, release_id):
        """Fetches a release by its Beatport ID and returns an AlbumInfo object
        or None if the query is not a valid ID or release is not found.
        """
        self._log.debug("Searching for release {0}", release_id)

        release_id = self._get_id("album", release_id, self.id_regex)
        if release_id is None:
            self._log.debug("Not a valid Beatport release ID.")
            return None

        release = self.client.get_release(release_id)
        if release:
            return self._get_album_info(release)
        return None

    def track_for_id(self, track_id):
        """Fetches a track by its Beatport ID and returns a TrackInfo object
        or None if the track is not a valid Beatport ID or track is not found.
        """
        self._log.debug("Searching for track {0}", track_id)
        match = re.search(r"(^|beatport\.com/track/.+/)(\d+)$", track_id)
        if not match:
            self._log.debug("Not a valid Beatport track ID.")
            return None
        bp_track = self.client.get_track(match.group(2))
        if bp_track is not None:
            return self._get_track_info(bp_track)
        return None

    def _get_releases(self, query):
        """Returns a list of AlbumInfo objects for a beatport search query."""
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r"\W+", " ", query, flags=re.UNICODE)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r"\b(CD|disc)\s*\d+", "", query, flags=re.I)
        albums = [self._get_album_info(x) for x in self.client.search(query)]
        return albums

    def _get_album_info(self, release):
        """Returns an AlbumInfo object for a Beatport Release object."""
        va = len(release.artists) > 3
        artist, artist_id = self._get_artist(release.artists)
        if va:
            artist = "Various Artists"
        tracks = [self._get_track_info(x) for x in release.tracks]

        return AlbumInfo(
            album=release.name,
            album_id=release.beatport_id,
            beatport_album_id=release.beatport_id,
            artist=artist,
            artist_id=artist_id,
            tracks=tracks,
            albumtype=release.category,
            va=va,
            year=release.release_date.year,
            month=release.release_date.month,
            day=release.release_date.day,
            label=release.label_name,
            catalognum=release.catalog_number,
            media="Digital",
            data_source=self.data_source,
            data_url=release.url,
            genre=release.genre,
        )

    def _get_track_info(self, track):
        """Returns a TrackInfo object for a Beatport Track object."""
        title = track.name
        if track.mix_name != "Original Mix":
            title += f" ({track.mix_name})"
        artist, artist_id = self._get_artist(track.artists)
        length = track.length.total_seconds()
        return TrackInfo(
            title=title,
            track_id=track.beatport_id,
            artist=artist,
            artist_id=artist_id,
            length=length,
            index=track.track_number,
            medium_index=track.track_number,
            data_source=self.data_source,
            data_url=track.url,
            bpm=track.bpm,
            initial_key=track.initial_key,
            genre=track.genre,
        )

    def _get_artist(self, artists):
        """Returns an artist string (all artists) and an artist_id (the main
        artist) for a list of Beatport release or track artists.
        """
        return MetadataSourcePlugin.get_artist(
            artists=artists, id_key=0, name_key=1
        )

    def _get_tracks(self, query):
        """Returns a list of TrackInfo objects for a Beatport query."""
        bp_tracks = self.client.search(query, release_type="track")
        tracks = [self._get_track_info(x) for x in bp_tracks]
        return tracks
