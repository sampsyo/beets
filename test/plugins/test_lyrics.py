# This file is part of beets.
# Copyright 2016, Fabrice Laporte.
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

"""Tests for the 'lyrics' plugin."""

import re
import textwrap
from functools import partial
from http import HTTPStatus

import pytest

from beets.library import Item
from beets.test.helper import PluginMixin
from beetsplug import lyrics

from .lyrics_pages import LyricsPage, lyrics_pages

PHRASE_BY_TITLE = {
    "Lady Madonna": "friday night arrives without a suitcase",
    "Jazz'n'blues": "as i check my balance i kiss the screen",
    "Beets song": "via plugins, beets becomes a panacea",
}


class TestLyricsUtils:
    @pytest.mark.parametrize(
        "artist, title",
        [
            ("Various Artists", "Title"),
            ("Artist", ""),
            ("", "Title"),
            (" ", ""),
            ("", " "),
            ("", ""),
        ],
    )
    def test_search_empty(self, artist, title):
        actual_pairs = lyrics.search_pairs(Item(artist=artist, title=title))

        assert not list(actual_pairs)

    @pytest.mark.parametrize(
        "artist, artist_sort, expected_extra_artists",
        [
            ("Alice ft. Bob", "", ["Alice"]),
            ("Alice feat Bob", "", ["Alice"]),
            ("Alice feat. Bob", "", ["Alice"]),
            ("Alice feats Bob", "", []),
            ("Alice featuring Bob", "", ["Alice"]),
            ("Alice & Bob", "", ["Alice"]),
            ("Alice and Bob", "", ["Alice"]),
            ("Alice", "", []),
            ("Alice", "Alice", []),
            ("Alice", "alice", []),
            ("Alice", "alice ", []),
            ("Alice", "Alice A", ["Alice A"]),
            ("CHVRCHΞS", "CHVRCHES", ["CHVRCHES"]),
            ("横山克", "Masaru Yokoyama", ["Masaru Yokoyama"]),
        ],
    )
    def test_search_pairs_artists(
        self, artist, artist_sort, expected_extra_artists
    ):
        item = Item(artist=artist, artist_sort=artist_sort, title="song")

        actual_artists = [a for a, _ in lyrics.search_pairs(item)]

        # Make sure that the original artist name is still the first entry
        assert actual_artists == [artist, *expected_extra_artists]

    @pytest.mark.parametrize(
        "title, expected_extra_titles",
        [
            ("1/2", []),
            ("1 / 2", ["1", "2"]),
            ("Song (live)", ["Song"]),
            ("Song (live) (new)", ["Song"]),
            ("Song (live (new))", ["Song"]),
            ("Song ft. B", ["Song"]),
            ("Song featuring B", ["Song"]),
            ("Song and B", []),
            ("Song: B", ["Song"]),
        ],
    )
    def test_search_pairs_titles(self, title, expected_extra_titles):
        item = Item(title=title, artist="A")

        actual_titles = {
            t: None for _, tit in lyrics.search_pairs(item) for t in tit
        }

        assert list(actual_titles) == [title, *expected_extra_titles]

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("test", "test"),
            ("Mørdag", "mordag"),
            ("l'été c'est fait pour jouer", "l-ete-c-est-fait-pour-jouer"),
            ("\xe7afe au lait (boisson)", "cafe-au-lait-boisson"),
            ("Multiple  spaces -- and symbols! -- merged", "multiple-spaces-and-symbols-merged"),  # noqa: E501
            ("\u200bno-width-space", "no-width-space"),
            ("El\u002dp", "el-p"),
            ("\u200bblackbear", "blackbear"),
            ("\u200d", ""),
            ("\u2010", ""),
        ],
    )  # fmt: skip
    def test_slug(self, text, expected):
        assert lyrics.slug(text) == expected


class TestHtml:
    def test_scrape_strip_cruft(self):
        initial = """<!--lyrics below-->
                  &nbsp;one
                  <br class='myclass'>
                  two  !
                  <br><br \\>
                  <blink>four</blink>"""
        expected = "<!--lyrics below-->\none\ntwo !\n\n<blink>four</blink>"

        assert lyrics.Html.normalize_space(initial) == expected

    def test_scrape_merge_paragraphs(self):
        text = "one</p>   <p class='myclass'>two</p><p>three"
        expected = "one\ntwo\n\nthree"

        assert lyrics.Html.merge_paragraphs(text) == expected


class TestSearchBackend:
    @pytest.fixture
    def backend(self, dist_thresh):
        plugin = lyrics.LyricsPlugin()
        plugin.config.set({"dist_thresh": dist_thresh})
        return lyrics.SearchBackend(plugin.config, plugin._log)

    @pytest.mark.parametrize(
        "dist_thresh, target_artist, artist, should_match",
        [
            (0.11, "Target Artist", "Target Artist", True),
            (0.11, "Target Artist", "Target Artis", True),
            (0.11, "Target Artist", "Target Arti", False),
            (0.11, "Psychonaut", "Psychonaut (BEL)", True),
            (0.11, "beets song", "beats song", True),
            (0.10, "beets song", "beats song", False),
            (
                0.11,
                "Lucid Dreams (Forget Me)",
                "Lucid Dreams (Remix) ft. Lil Uzi Vert",
                False,
            ),
            (
                0.12,
                "Lucid Dreams (Forget Me)",
                "Lucid Dreams (Remix) ft. Lil Uzi Vert",
                True,
            ),
        ],
    )
    def test_check_match(self, backend, target_artist, artist, should_match):
        result = lyrics.SearchResult(artist, "", "")

        assert backend.check_match(target_artist, "", result) == should_match


@pytest.fixture(scope="module")
def lyrics_root_dir(pytestconfig: pytest.Config):
    return pytestconfig.rootpath / "test" / "rsrc" / "lyrics"


class LyricsPluginMixin(PluginMixin):
    plugin = "lyrics"

    @pytest.fixture
    def plugin_config(self):
        """Return lyrics configuration to test."""
        return {}

    @pytest.fixture
    def lyrics_plugin(self, backend_name, plugin_config):
        """Set configuration and returns the plugin's instance."""
        plugin_config["sources"] = [backend_name]
        self.config[self.plugin].set(plugin_config)

        return lyrics.LyricsPlugin()


class TestLyricsPlugin(LyricsPluginMixin):
    @pytest.fixture
    def backend_name(self):
        """Return lyrics configuration to test."""
        return "lrclib"

    @pytest.mark.parametrize(
        "request_kwargs, expected_log_match",
        [
            (
                {"status_code": HTTPStatus.BAD_GATEWAY},
                r"LRCLib: Request error: 502",
            ),
            ({"text": "invalid"}, r"LRCLib: Could not decode.*JSON"),
        ],
    )
    def test_error_handling(
        self,
        requests_mock,
        lyrics_plugin,
        caplog,
        request_kwargs,
        expected_log_match,
    ):
        """Errors are logged with the backend name."""
        requests_mock.get(lyrics.LRCLib.SEARCH_URL, **request_kwargs)

        assert lyrics_plugin.get_lyrics("", "", "", 0.0) is None
        assert caplog.messages
        last_log = caplog.messages[-1]
        assert last_log
        assert re.search(expected_log_match, last_log, re.I)


class LyricsBackendTest(LyricsPluginMixin):
    @pytest.fixture
    def backend(self, lyrics_plugin):
        """Return a lyrics backend instance."""
        return lyrics_plugin.backends[0]

    @pytest.fixture
    def lyrics_html(self, lyrics_root_dir, file_name):
        return (lyrics_root_dir / f"{file_name}.txt").read_text(
            encoding="utf-8"
        )


@pytest.mark.on_lyrics_update
class TestLyricsSources(LyricsBackendTest):
    @pytest.fixture(scope="class")
    def plugin_config(self):
        return {"google_API_key": "test", "synced": True}

    @pytest.fixture(
        params=[pytest.param(lp, marks=lp.marks) for lp in lyrics_pages],
        ids=str,
    )
    def lyrics_page(self, request):
        return request.param

    @pytest.fixture
    def backend_name(self, lyrics_page):
        return lyrics_page.backend

    @pytest.fixture(autouse=True)
    def _patch_google_search(self, requests_mock, lyrics_page):
        """Mock the Google Search API to return the lyrics page under test."""
        requests_mock.real_http = True

        data = {
            "items": [
                {
                    "title": lyrics_page.url_title,
                    "link": lyrics_page.url,
                    "displayLink": lyrics_page.root_url,
                }
            ]
        }
        requests_mock.get(lyrics.Google.SEARCH_URL, json=data)

    def test_backend_source(self, lyrics_plugin, lyrics_page: LyricsPage):
        """Test parsed lyrics from each of the configured lyrics pages."""
        lyrics_info = lyrics_plugin.get_lyrics(
            lyrics_page.artist, lyrics_page.track_title, "", 186
        )

        assert lyrics_info
        lyrics, _ = lyrics_info.split("\n\nSource: ")
        assert lyrics == lyrics_page.lyrics


class TestGoogleLyrics(LyricsBackendTest):
    """Test scraping heuristics on a fake html page."""

    @pytest.fixture(scope="class")
    def backend_name(self):
        return "google"

    @pytest.fixture
    def plugin_config(self):
        return {"google_API_key": "test"}

    @pytest.fixture(scope="class")
    def file_name(self):
        return "examplecom/beetssong"

    @pytest.fixture
    def search_item(self, url_title, url):
        return {"title": url_title, "link": url}

    @pytest.mark.parametrize("plugin_config", [{}])
    def test_disabled_without_api_key(self, lyrics_plugin):
        assert not lyrics_plugin.backends

    def test_mocked_source_ok(self, backend, lyrics_html):
        """Test that lyrics of the mocked page are correctly scraped"""
        result = backend.scrape(lyrics_html).lower()

        assert result
        assert PHRASE_BY_TITLE["Beets song"] in result

    @pytest.mark.parametrize(
        "url_title, expected_artist, expected_title",
        [
            ("Artist - beets song Lyrics", "Artist", "beets song"),
            ("www.azlyrics.com | Beats song by Artist", "Artist", "Beats song"),
            ("lyric.com | seets bong lyrics by Artist", "Artist", "seets bong"),
            ("foo", "", "foo"),
            ("Artist - Beets Song lyrics | AZLyrics", "Artist", "Beets Song"),
            ("Letra de Artist - Beets Song", "Artist", "Beets Song"),
            ("Letra de Artist - Beets ...", "Artist", "Beets"),
            ("Artist Beets Song", "Artist", "Beets Song"),
            ("BeetsSong - Artist", "Artist", "BeetsSong"),
            ("Artist - BeetsSong", "Artist", "BeetsSong"),
            ("Beets Song", "", "Beets Song"),
            ("Beets Song Artist", "Artist", "Beets Song"),
            (
                "BeetsSong (feat. Other & Another) - Artist",
                "Artist",
                "BeetsSong (feat. Other & Another)",
            ),
            (
                (
                    "Beets song lyrics by Artist - original song full text. "
                    "Official Beets song lyrics, 2024 version | LyricsMode.com"
                ),
                "Artist",
                "Beets song",
            ),
        ],
    )
    @pytest.mark.parametrize("url", ["http://doesntmatter.com"])
    def test_make_search_result(
        self, backend, search_item, expected_artist, expected_title
    ):
        result = backend.make_search_result("Artist", "Beets song", search_item)

        assert result.artist == expected_artist
        assert result.title == expected_title


class TestGeniusLyrics(LyricsBackendTest):
    @pytest.fixture(scope="class")
    def backend_name(self):
        return "genius"

    @pytest.mark.parametrize(
        "file_name, expected_line_count",
        [
            ("geniuscom/2pacalleyezonmelyrics", 131),
            ("geniuscom/Ttngchinchillalyrics", 29),
            ("geniuscom/sample", 0),  # see https://github.com/beetbox/beets/issues/3535
        ],
    )  # fmt: skip
    def test_scrape(self, backend, lyrics_html, expected_line_count):
        result = backend.scrape(lyrics_html) or ""

        assert len(result.splitlines()) == expected_line_count


class TestTekstowoLyrics(LyricsBackendTest):
    @pytest.fixture(scope="class")
    def backend_name(self):
        return "tekstowo"

    @pytest.mark.parametrize(
        "file_name, expecting_lyrics",
        [
            ("tekstowopl/piosenka24kgoldncityofangels1", True),
            (
                "tekstowopl/piosenkabeethovenbeethovenpianosonata17tempestthe3rdmovement",  # noqa: E501
                False,
            ),
        ],
    )
    def test_scrape(self, backend, lyrics_html, expecting_lyrics):
        assert bool(backend.scrape(lyrics_html)) == expecting_lyrics


LYRICS_DURATION = 950


def lyrics_match(**overrides):
    return {
        "id": 1,
        "instrumental": False,
        "duration": LYRICS_DURATION,
        "syncedLyrics": "synced",
        "plainLyrics": "plain",
        **overrides,
    }


class TestLRCLibLyrics(LyricsBackendTest):
    ITEM_DURATION = 999

    @pytest.fixture(scope="class")
    def backend_name(self):
        return "lrclib"

    @pytest.fixture
    def fetch_lyrics(self, backend, requests_mock, response_data):
        requests_mock.get(backend.GET_URL, status_code=HTTPStatus.NOT_FOUND)
        requests_mock.get(backend.SEARCH_URL, json=response_data)

        return partial(backend.fetch, "la", "la", "la", self.ITEM_DURATION)

    @pytest.mark.parametrize("response_data", [[lyrics_match()]])
    @pytest.mark.parametrize(
        "plugin_config, expected_lyrics",
        [({"synced": True}, "synced"), ({"synced": False}, "plain")],
    )
    def test_synced_config_option(self, fetch_lyrics, expected_lyrics):
        lyrics, _ = fetch_lyrics()

        assert lyrics == expected_lyrics

    @pytest.mark.parametrize(
        "response_data, expected_lyrics",
        [
            pytest.param([], None, id="handle non-matching lyrics"),
            pytest.param(
                [lyrics_match()],
                "synced",
                id="synced when available",
            ),
            pytest.param(
                [lyrics_match(duration=1)],
                None,
                id="none: duration too short",
            ),
            pytest.param(
                [lyrics_match(instrumental=True)],
                "[Instrumental]",
                id="instrumental track",
            ),
            pytest.param(
                [lyrics_match(syncedLyrics=None)],
                "plain",
                id="plain by default",
            ),
            pytest.param(
                [
                    lyrics_match(
                        duration=ITEM_DURATION,
                        syncedLyrics=None,
                        plainLyrics="plain with closer duration",
                    ),
                    lyrics_match(syncedLyrics="synced", plainLyrics="plain 2"),
                ],
                "synced",
                id="prefer synced lyrics even if plain duration is closer",
            ),
            pytest.param(
                [
                    lyrics_match(
                        duration=ITEM_DURATION,
                        syncedLyrics=None,
                        plainLyrics="valid plain",
                    ),
                    lyrics_match(
                        duration=1,
                        syncedLyrics="synced with invalid duration",
                    ),
                ],
                "valid plain",
                id="ignore synced with invalid duration",
            ),
            pytest.param(
                [lyrics_match(syncedLyrics=None), lyrics_match()],
                "synced",
                id="prefer match with synced lyrics",
            ),
        ],
    )
    @pytest.mark.parametrize("plugin_config", [{"synced": True}])
    def test_fetch_lyrics(self, fetch_lyrics, expected_lyrics):
        lyrics_info = fetch_lyrics()
        if lyrics_info is None:
            assert expected_lyrics is None
        else:
            lyrics, _ = fetch_lyrics()

            assert lyrics == expected_lyrics


class TestTranslation:
    @pytest.fixture(autouse=True)
    def _patch_bing(self, requests_mock):
        def callback(request, _):
            if b"Refrain" in request.body:
                translations = (
                    ""
                    "|[Refrain : Doja Cat]"
                    "|Difficile pour moi de te laisser partir (Te laisser partir, te laisser partir)"  # noqa: E501
                    "|Mon corps ne me laissait pas le cacher (Cachez-le)"
                    "|Quoi qu’il arrive, je ne plierais pas (Ne plierait pas, ne plierais pas)"  # noqa: E501
                    "|Chevauchant à travers le tonnerre, la foudre"
                )
            elif b"00:00.00" in request.body:
                translations = (
                    ""
                    "|[00:00.00] Quelques paroles synchronisées"
                    "|[00:01.00] Quelques paroles plus synchronisées"
                )
            else:
                translations = (
                    ""
                    "|Quelques paroles synchronisées"
                    "|Quelques paroles plus synchronisées"
                )

            return [
                {
                    "detectedLanguage": {"language": "en", "score": 1.0},
                    "translations": [{"text": translations, "to": "fr"}],
                }
            ]

        requests_mock.post(lyrics.Translator.TRANSLATE_URL, json=callback)

    @pytest.mark.parametrize(
        "initial_lyrics, expected",
        [
            pytest.param(
                """
                [Refrain: Doja Cat]
                Hard for me to let you go (Let you go, let you go)
                My body wouldn't let me hide it (Hide it)
                No matter what, I wouldn't fold (Wouldn't fold, wouldn't fold)
                Ridin' through the thunder, lightnin'""",
                """
                [Refrain: Doja Cat] / [Refrain : Doja Cat]
                Hard for me to let you go (Let you go, let you go) / Difficile pour moi de te laisser partir (Te laisser partir, te laisser partir)
                My body wouldn't let me hide it (Hide it) / Mon corps ne me laissait pas le cacher (Cachez-le)
                No matter what, I wouldn't fold (Wouldn't fold, wouldn't fold) / Quoi qu’il arrive, je ne plierais pas (Ne plierait pas, ne plierais pas)
                Ridin' through the thunder, lightnin' / Chevauchant à travers le tonnerre, la foudre""",  # noqa: E501
                id="plain",
            ),
            pytest.param(
                """
                [00:00.00] Some synced lyrics
                [00:00:50]
                [00:01.00] Some more synced lyrics

                Source: https://lrclib.net/api/123""",
                """
                [00:00.00] Some synced lyrics / Quelques paroles synchronisées
                [00:00:50]
                [00:01.00] Some more synced lyrics / Quelques paroles plus synchronisées

                Source: https://lrclib.net/api/123""",  # noqa: E501
                id="synced",
            ),
            pytest.param(
                "Quelques paroles",
                "Quelques paroles",
                id="already in the target language",
            ),
        ],
    )
    def test_translate(self, initial_lyrics, expected):
        plugin = lyrics.LyricsPlugin()
        bing = lyrics.Translator(plugin._log, "123", "FR", ["EN"])

        assert bing.translate(
            textwrap.dedent(initial_lyrics)
        ) == textwrap.dedent(expected)
