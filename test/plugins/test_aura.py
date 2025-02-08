import os
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional

import pytest
from flask.testing import Client

from beets.test.helper import TestHelper


@pytest.fixture(scope="session", autouse=True)
def helper():
    helper = TestHelper()
    helper.setup_beets()
    yield helper
    helper.teardown_beets()


@pytest.fixture(scope="session")
def app(helper):
    from beetsplug.aura import create_app

    app = create_app()
    app.config["lib"] = helper.lib
    return app


@pytest.fixture(scope="session")
def item(helper):
    return helper.add_item_fixture(
        album="Album",
        title="Title",
        artist="Artist",
        albumartist="Album Artist",
    )


@pytest.fixture(scope="session")
def album(helper, item):
    return helper.lib.add_album([item])


@pytest.fixture(scope="session", autouse=True)
def _other_album_and_item(helper):
    """Add another item and album to prove that filtering works."""
    item = helper.add_item_fixture(
        album="Other Album",
        title="Other Title",
        artist="Other Artist",
        albumartist="Other Album Artist",
    )
    helper.lib.add_album([item])


class TestAuraResponse:
    @pytest.fixture
    def get_response_data(self, client: Client, item):
        """Return a callback accepting `endpoint` and `params` parameters."""

        def get(
            endpoint: str, params: dict[str, str]
        ) -> Optional[dict[str, Any]]:
            """Add additional `params` and GET the given endpoint.

            `include` parameter is added to every call to check that the
            functionality that fetches related entities works.

            Before returning the response data, ensure that the request is
            successful.
            """
            response = client.get(
                endpoint,
                query_string={"include": "tracks,artists,albums", **params},
            )

            assert response.status_code == HTTPStatus.OK

            return response.json

        return get

    @pytest.fixture(scope="class")
    def track_document(self, item, album):
        return {
            "type": "track",
            "id": str(item.id),
            "attributes": {
                "album": item.album,
                "albumartist": item.albumartist,
                "artist": item.artist,
                "size": Path(os.fsdecode(item.path)).stat().st_size,
                "title": item.title,
                "track": 1,
            },
            "relationships": {
                "albums": {"data": [{"id": str(album.id), "type": "album"}]},
                "artists": {"data": [{"id": item.artist, "type": "artist"}]},
            },
        }

    @pytest.fixture(scope="class")
    def artist_document(self, item):
        return {
            "type": "artist",
            "id": item.artist,
            "attributes": {"name": item.artist},
            "relationships": {
                "tracks": {"data": [{"id": str(item.id), "type": "track"}]}
            },
        }

    @pytest.fixture(scope="class")
    def album_document(self, album):
        return {
            "type": "album",
            "id": str(album.id),
            "attributes": {"artist": album.albumartist, "title": album.album},
            "relationships": {
                "tracks": {"data": [{"id": str(album.id), "type": "track"}]}
            },
        }

    def test_tracks(
        self,
        get_response_data,
        item,
        album_document,
        artist_document,
        track_document,
    ):
        data = get_response_data("/aura/tracks", {"filter[title]": item.title})

        assert data == {
            "data": [track_document],
            "included": [artist_document, album_document],
        }

    def test_artists(
        self, get_response_data, item, artist_document, track_document
    ):
        data = get_response_data(
            "/aura/artists", {"filter[artist]": item.artist}
        )

        assert data == {"data": [artist_document], "included": [track_document]}

    def test_albums(
        self, get_response_data, album, album_document, track_document
    ):
        data = get_response_data("/aura/albums", {"filter[album]": album.album})

        assert data == {"data": [album_document], "included": [track_document]}
