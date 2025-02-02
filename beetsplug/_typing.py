from __future__ import annotations

from typing import Any

from typing_extensions import NotRequired, TypedDict

JSONDict = dict[str, Any]


class LRCLibAPI:
    class Item(TypedDict):
        """Lyrics data item returned by the LRCLib API."""

        id: int
        name: str
        trackName: str
        artistName: str
        albumName: str
        duration: float | None
        instrumental: bool
        plainLyrics: str
        syncedLyrics: str | None


class GeniusAPI:
    """Genius API data types.

    This documents *only* the fields that are used in the plugin.
    :attr:`SearchResult` is an exception, since I thought some of the other
    fields might be useful in the future.
    """

    class DateComponents(TypedDict):
        year: int
        month: int
        day: int

    class Artist(TypedDict):
        api_path: str
        header_image_url: str
        id: int
        image_url: str
        is_meme_verified: bool
        is_verified: bool
        name: str
        url: str

    class Stats(TypedDict):
        unreviewed_annotations: int
        hot: bool

    class SearchResult(TypedDict):
        annotation_count: int
        api_path: str
        artist_names: str
        full_title: str
        header_image_thumbnail_url: str
        header_image_url: str
        id: int
        lyrics_owner_id: int
        lyrics_state: str
        path: str
        primary_artist_names: str
        pyongs_count: int | None
        relationships_index_url: str
        release_date_components: GeniusAPI.DateComponents
        release_date_for_display: str
        release_date_with_abbreviated_month_for_display: str
        song_art_image_thumbnail_url: str
        song_art_image_url: str
        stats: GeniusAPI.Stats
        title: str
        title_with_featured: str
        url: str
        featured_artists: list[GeniusAPI.Artist]
        primary_artist: GeniusAPI.Artist
        primary_artists: list[GeniusAPI.Artist]

    class SearchHit(TypedDict):
        result: GeniusAPI.SearchResult

    class SearchResponse(TypedDict):
        hits: list[GeniusAPI.SearchHit]

    class Search(TypedDict):
        response: GeniusAPI.SearchResponse


class GoogleCustomSearchAPI:
    class Response(TypedDict):
        """Search response from the Google Custom Search API.

        If the search returns no results, the :attr:`items` field is not found.
        """

        items: NotRequired[list[GoogleCustomSearchAPI.Item]]

    class Item(TypedDict):
        """A Google Custom Search API result item.

        :attr:`title` field is shown to the user in the search interface, thus
        it gets truncated with an ellipsis for longer queries. For most
        results, the full title is available as ``og:title`` metatag found
        under the :attr:`pagemap` field. Note neither this metatag nor the
        ``pagemap`` field is guaranteed to be present in the data.
        """

        title: str
        link: str
        pagemap: NotRequired[GoogleCustomSearchAPI.Pagemap]

    class Pagemap(TypedDict):
        """Pagemap data with a single meta tags dict in a list."""

        metatags: list[JSONDict]


class TranslatorAPI:
    class Language(TypedDict):
        """Language data returned by the translator API."""

        language: str
        score: float

    class Translation(TypedDict):
        """Translation data returned by the translator API."""

        text: str
        to: str

    class Response(TypedDict):
        """Response from the translator API."""

        detectedLanguage: TranslatorAPI.Language
        translations: list[TranslatorAPI.Translation]
