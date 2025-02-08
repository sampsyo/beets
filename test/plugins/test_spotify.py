"""Tests for the 'spotify' plugin"""

import os
from urllib.parse import parse_qs, urlparse

import responses

from beets.library import Item
from beets.test import _common
from beets.test.helper import BeetsTestCase
from beetsplug import spotify


class ArgumentsMock:
    def __init__(self, mode, show_failures):
        self.mode = mode
        self.show_failures = show_failures
        self.verbose = 1


def _params(url):
    """Get the query parameters from a URL."""
    return parse_qs(urlparse(url).query)


class SpotifyPluginTest(BeetsTestCase):
    @responses.activate
    def setUp(self):
        super().setUp()
        responses.add(
            responses.POST,
            spotify.SpotifyPlugin.oauth_token_url,
            status=200,
            json={
                "access_token": "3XyiC3raJySbIAV5LVYj1DaWbcocNi3LAJTNXRnYY"
                "GVUl6mbbqXNhW3YcZnQgYXNWHFkVGSMlc0tMuvq8CF",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "",
            },
        )
        self.spotify = spotify.SpotifyPlugin()
        opts = ArgumentsMock("list", False)
        self.spotify._parse_opts(opts)

    def test_args(self):
        opts = ArgumentsMock("fail", True)
        assert not self.spotify._parse_opts(opts)
        opts = ArgumentsMock("list", False)
        assert self.spotify._parse_opts(opts)

    def test_empty_query(self):
        assert self.spotify._match_library_tracks(self.lib, "1=2") is None

    @responses.activate
    def test_missing_request(self):
        json_file = os.path.join(
            _common.RSRC, b"spotify", b"missing_request.json"
        )
        with open(json_file, "rb") as f:
            response_body = f.read()

        responses.add(
            responses.GET,
            spotify.SpotifyPlugin.search_url,
            body=response_body,
            status=200,
            content_type="application/json",
        )
        item = Item(
            mb_trackid="01234",
            album="lkajsdflakjsd",
            albumartist="ujydfsuihse",
            title="duifhjslkef",
            length=10,
        )
        item.add(self.lib)
        assert [] == self.spotify._match_library_tracks(self.lib, "")

        params = _params(responses.calls[0].request.url)
        query = params["q"][0]
        assert "duifhjslkef" in query
        assert "artist:ujydfsuihse" in query
        assert "album:lkajsdflakjsd" in query
        assert params["type"] == ["track"]

    @responses.activate
    def test_track_request(self):
        json_file = os.path.join(
            _common.RSRC, b"spotify", b"track_request.json"
        )
        with open(json_file, "rb") as f:
            response_body = f.read()

        responses.add(
            responses.GET,
            spotify.SpotifyPlugin.search_url,
            body=response_body,
            status=200,
            content_type="application/json",
        )
        item = Item(
            mb_trackid="01234",
            album="Despicable Me 2",
            albumartist="Pharrell Williams",
            title="Happy",
            length=10,
        )
        item.add(self.lib)
        results = self.spotify._match_library_tracks(self.lib, "Happy")
        assert 1 == len(results)
        assert "6NPVjNh8Jhru9xOmyQigds" == results[0]["id"]
        self.spotify._output_match_results(results)

        params = _params(responses.calls[0].request.url)
        query = params["q"][0]
        assert "Happy" in query
        assert "artist:Pharrell Williams" in query
        assert "album:Despicable Me 2" in query
        assert params["type"] == ["track"]

    @responses.activate
    def test_track_for_id(self):
        """Tests if plugin is able to fetch a track by its Spotify ID"""

        # Mock the Spotify 'Get Track' call
        json_file = os.path.join(_common.RSRC, b"spotify", b"track_info.json")
        with open(json_file, "rb") as f:
            response_body = f.read()

        responses.add(
            responses.GET,
            spotify.SpotifyPlugin.track_url + "6NPVjNh8Jhru9xOmyQigds",
            body=response_body,
            status=200,
            content_type="application/json",
        )

        # Mock the Spotify 'Get Album' call
        json_file = os.path.join(_common.RSRC, b"spotify", b"album_info.json")
        with open(json_file, "rb") as f:
            response_body = f.read()

        responses.add(
            responses.GET,
            spotify.SpotifyPlugin.album_url + "5l3zEmMrOhOzG8d8s83GOL",
            body=response_body,
            status=200,
            content_type="application/json",
        )

        # Mock the Spotify 'Search' call
        json_file = os.path.join(
            _common.RSRC, b"spotify", b"track_request.json"
        )
        with open(json_file, "rb") as f:
            response_body = f.read()

        responses.add(
            responses.GET,
            spotify.SpotifyPlugin.search_url,
            body=response_body,
            status=200,
            content_type="application/json",
        )

        track_info = self.spotify.track_for_id("6NPVjNh8Jhru9xOmyQigds")
        item = Item(
            mb_trackid=track_info.track_id,
            albumartist=track_info.artist,
            title=track_info.title,
            length=track_info.length,
        )
        item.add(self.lib)

        results = self.spotify._match_library_tracks(self.lib, "Happy")
        assert 1 == len(results)
        assert "6NPVjNh8Jhru9xOmyQigds" == results[0]["id"]
