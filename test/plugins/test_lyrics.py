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

import itertools
import os
import re
import unittest
from unittest.mock import MagicMock, patch

import confuse
import pytest
import requests

from beets import logging
from beets.library import Item
from beets.test import _common
from beets.util import bytestring_path
from beetsplug import lyrics

log = logging.getLogger("beets.test_lyrics")
raw_backend = lyrics.Backend({}, log)
google = lyrics.Google(MagicMock(), log)
genius = lyrics.Genius(MagicMock(), log)
tekstowo = lyrics.Tekstowo(MagicMock(), log)
lrclib = lyrics.LRCLib(MagicMock(), log)


class LyricsPluginTest(unittest.TestCase):
    def setUp(self):
        """Set up configuration."""
        lyrics.LyricsPlugin()

    def test_search_artist(self):
        item = Item(artist="Alice ft. Bob", title="song")
        assert ("Alice ft. Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice feat Bob", title="song")
        assert ("Alice feat Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice feat. Bob", title="song")
        assert ("Alice feat. Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice feats Bob", title="song")
        assert ("Alice feats Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) not in lyrics.search_pairs(item)

        item = Item(artist="Alice featuring Bob", title="song")
        assert ("Alice featuring Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice & Bob", title="song")
        assert ("Alice & Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice and Bob", title="song")
        assert ("Alice and Bob", ["song"]) in lyrics.search_pairs(item)
        assert ("Alice", ["song"]) in lyrics.search_pairs(item)

        item = Item(artist="Alice and Bob", title="song")
        assert ("Alice and Bob", ["song"]) == list(lyrics.search_pairs(item))[0]

    def test_search_artist_sort(self):
        item = Item(artist="CHVRCHΞS", title="song", artist_sort="CHVRCHES")
        assert ("CHVRCHΞS", ["song"]) in lyrics.search_pairs(item)
        assert ("CHVRCHES", ["song"]) in lyrics.search_pairs(item)

        # Make sure that the original artist name is still the first entry
        assert ("CHVRCHΞS", ["song"]) == list(lyrics.search_pairs(item))[0]

        item = Item(
            artist="横山克", title="song", artist_sort="Masaru Yokoyama"
        )
        assert ("横山克", ["song"]) in lyrics.search_pairs(item)
        assert ("Masaru Yokoyama", ["song"]) in lyrics.search_pairs(item)

        # Make sure that the original artist name is still the first entry
        assert ("横山克", ["song"]) == list(lyrics.search_pairs(item))[0]

    def test_search_pairs_multi_titles(self):
        item = Item(title="1 / 2", artist="A")
        assert ("A", ["1 / 2"]) in lyrics.search_pairs(item)
        assert ("A", ["1", "2"]) in lyrics.search_pairs(item)

        item = Item(title="1/2", artist="A")
        assert ("A", ["1/2"]) in lyrics.search_pairs(item)
        assert ("A", ["1", "2"]) in lyrics.search_pairs(item)

    def test_search_pairs_titles(self):
        item = Item(title="Song (live)", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song (live)"]) in lyrics.search_pairs(item)

        item = Item(title="Song (live) (new)", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song (live) (new)"]) in lyrics.search_pairs(item)

        item = Item(title="Song (live (new))", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song (live (new))"]) in lyrics.search_pairs(item)

        item = Item(title="Song ft. B", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song ft. B"]) in lyrics.search_pairs(item)

        item = Item(title="Song featuring B", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song featuring B"]) in lyrics.search_pairs(item)

        item = Item(title="Song and B", artist="A")
        assert ("A", ["Song and B"]) in lyrics.search_pairs(item)
        assert ("A", ["Song"]) not in lyrics.search_pairs(item)

        item = Item(title="Song: B", artist="A")
        assert ("A", ["Song"]) in lyrics.search_pairs(item)
        assert ("A", ["Song: B"]) in lyrics.search_pairs(item)

    def test_remove_credits(self):
        assert (
            lyrics.remove_credits(
                """It's close to midnight
                                     Lyrics brought by example.com"""
            )
            == "It's close to midnight"
        )
        assert lyrics.remove_credits("""Lyrics brought by example.com""") == ""

        # don't remove 2nd verse for the only reason it contains 'lyrics' word
        text = """Look at all the shit that i done bought her
                  See lyrics ain't nothin
                  if the beat aint crackin"""
        assert lyrics.remove_credits(text) == text

    def test_is_lyrics(self):
        texts = ["LyricsMania.com - Copyright (c) 2013 - All Rights Reserved"]
        texts += [
            """All material found on this site is property\n
                     of mywickedsongtext brand"""
        ]
        for t in texts:
            assert not google.is_lyrics(t)

    def test_slugify(self):
        text = "http://site.com/\xe7afe-au_lait(boisson)"
        assert google.slugify(text) == "http://site.com/cafe_au_lait"

    def test_scrape_strip_cruft(self):
        text = """<!--lyrics below-->
                  &nbsp;one
                  <br class='myclass'>
                  two  !
                  <br><br \\>
                  <blink>four</blink>"""
        assert lyrics._scrape_strip_cruft(text, True) == "one\ntwo !\n\nfour"

    def test_scrape_strip_scripts(self):
        text = """foo<script>bar</script>baz"""
        assert lyrics._scrape_strip_cruft(text, True) == "foobaz"

    def test_scrape_strip_tag_in_comment(self):
        text = """foo<!--<bar>-->qux"""
        assert lyrics._scrape_strip_cruft(text, True) == "fooqux"

    def test_scrape_merge_paragraphs(self):
        text = "one</p>   <p class='myclass'>two</p><p>three"
        assert lyrics._scrape_merge_paragraphs(text) == "one\ntwo\nthree"

    def test_missing_lyrics(self):
        assert not google.is_lyrics(LYRICS_TEXTS["missing_texts"])


def url_to_filename(url):
    url = re.sub(r"https?://|www.", "", url)
    url = re.sub(r".html", "", url)
    fn = "".join(x for x in url if (x.isalnum() or x == "/"))
    fn = fn.split("/")
    fn = os.path.join(
        LYRICS_ROOT_DIR,
        bytestring_path(fn[0]),
        bytestring_path(fn[-1] + ".txt"),
    )
    return fn


class MockFetchUrl:
    def __init__(self, pathval="fetched_path"):
        self.pathval = pathval
        self.fetched = None

    def __call__(self, url, filename=None):
        self.fetched = url
        fn = url_to_filename(url)
        with open(fn, encoding="utf8") as f:
            content = f.read()
        return content


class LyricsAssertions:
    """A mixin with lyrics-specific assertions."""

    def assertLyricsContentOk(self, title, text, msg=""):  # noqa: N802
        """Compare lyrics text to expected lyrics for given title."""
        if not text:
            return

        keywords = set(LYRICS_TEXTS[google.slugify(title)].split())
        words = {x.strip(".?, ()") for x in text.lower().split()}

        if not keywords <= words:
            details = (
                f"{repr(keywords)} is not a subset of {repr(words)}."
                f" Words only in expected set {repr(keywords - words)},"
                f" Words only in result set {repr(words - keywords)}."
            )
            self.fail(f"{details} : {msg}")


LYRICS_ROOT_DIR = os.path.join(_common.RSRC, b"lyrics")
yaml_path = os.path.join(_common.RSRC, b"lyricstext.yaml")
LYRICS_TEXTS = confuse.load_yaml(yaml_path)


class LyricsGoogleBaseTest(unittest.TestCase):
    def setUp(self):
        """Set up configuration."""
        try:
            __import__("bs4")
        except ImportError:
            self.skipTest("Beautiful Soup 4 not available")


class LyricsPluginSourcesTest(LyricsGoogleBaseTest, LyricsAssertions):
    """Check that beets google custom search engine sources are correctly
    scraped.
    """

    DEFAULT_SONG = dict(artist="The Beatles", title="Lady Madonna")

    DEFAULT_SOURCES = [
        # dict(artist=u'Santana', title=u'Black magic woman',
        #      backend=lyrics.MusiXmatch),
        dict(
            DEFAULT_SONG,
            backend=lyrics.Genius,
            # GitHub actions is on some form of Cloudflare blacklist.
            skip=os.environ.get("GITHUB_ACTIONS") == "true",
        ),
        dict(artist="Boy In Space", title="u n eye", backend=lyrics.Tekstowo),
    ]

    GOOGLE_SOURCES = [
        dict(
            DEFAULT_SONG,
            url="http://www.absolutelyrics.com",
            path="/lyrics/view/the_beatles/lady_madonna",
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.azlyrics.com",
            path="/lyrics/beatles/ladymadonna.html",
            # AZLyrics returns a 403 on GitHub actions.
            skip=os.environ.get("GITHUB_ACTIONS") == "true",
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.chartlyrics.com",
            path="/_LsLsZ7P4EK-F-LD4dJgDQ/Lady+Madonna.aspx",
        ),
        # dict(DEFAULT_SONG,
        #      url=u'http://www.elyricsworld.com',
        #      path=u'/lady_madonna_lyrics_beatles.html'),
        dict(
            url="http://www.lacoccinelle.net",
            artist="Jacques Brel",
            title="Amsterdam",
            path="/paroles-officielles/275679.html",
        ),
        dict(
            DEFAULT_SONG, url="http://letras.mus.br/", path="the-beatles/275/"
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.lyricsmania.com/",
            path="lady_madonna_lyrics_the_beatles.html",
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.lyricsmode.com",
            path="/lyrics/b/beatles/lady_madonna.html",
        ),
        dict(
            url="http://www.lyricsontop.com",
            artist="Amy Winehouse",
            title="Jazz'n'blues",
            path="/amy-winehouse-songs/jazz-n-blues-lyrics.html",
        ),
        # dict(DEFAULT_SONG,
        #      url='http://www.metrolyrics.com/',
        #      path='lady-madonna-lyrics-beatles.html'),
        # dict(url='http://www.musica.com/', path='letras.asp?letra=2738',
        #      artist=u'Santana', title=u'Black magic woman'),
        dict(
            url="http://www.paroles.net/",
            artist="Lilly Wood & the prick",
            title="Hey it's ok",
            path="lilly-wood-the-prick/paroles-hey-it-s-ok",
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.songlyrics.com",
            path="/the-beatles/lady-madonna-lyrics",
        ),
        dict(
            DEFAULT_SONG,
            url="http://www.sweetslyrics.com",
            path="/761696.The%20Beatles%20-%20Lady%20Madonna.html",
        ),
    ]

    def setUp(self):
        LyricsGoogleBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()

    @pytest.mark.integration_test
    def test_backend_sources_ok(self):
        """Test default backends with songs known to exist in respective
        databases.
        """
        # Don't test any sources marked as skipped.
        sources = [s for s in self.DEFAULT_SOURCES if not s.get("skip", False)]
        for s in sources:
            with self.subTest(s["backend"].__name__):
                backend = s["backend"](self.plugin.config, self.plugin._log)
                res = backend.fetch(s["artist"], s["title"])
                self.assertLyricsContentOk(s["title"], res)

    @pytest.mark.integration_test
    def test_google_sources_ok(self):
        """Test if lyrics present on websites registered in beets google custom
        search engine are correctly scraped.
        """
        # Don't test any sources marked as skipped.
        sources = [s for s in self.GOOGLE_SOURCES if not s.get("skip", False)]
        for s in sources:
            url = s["url"] + s["path"]
            res = lyrics.scrape_lyrics_from_html(raw_backend.fetch_url(url))
            assert google.is_lyrics(res), url
            self.assertLyricsContentOk(s["title"], res, url)


class LyricsGooglePluginMachineryTest(LyricsGoogleBaseTest, LyricsAssertions):
    """Test scraping heuristics on a fake html page."""

    source = dict(
        url="http://www.example.com",
        artist="John Doe",
        title="Beets song",
        path="/lyrics/beetssong",
    )

    def setUp(self):
        """Set up configuration"""
        LyricsGoogleBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()

    @patch.object(lyrics.Backend, "fetch_url", MockFetchUrl())
    def test_mocked_source_ok(self):
        """Test that lyrics of the mocked page are correctly scraped"""
        url = self.source["url"] + self.source["path"]
        res = lyrics.scrape_lyrics_from_html(raw_backend.fetch_url(url))
        assert google.is_lyrics(res), url
        self.assertLyricsContentOk(self.source["title"], res, url)

    @patch.object(lyrics.Backend, "fetch_url", MockFetchUrl())
    def test_is_page_candidate_exact_match(self):
        """Test matching html page title with song infos -- when song infos are
        present in the title.
        """
        from bs4 import BeautifulSoup, SoupStrainer

        s = self.source
        url = str(s["url"] + s["path"])
        html = raw_backend.fetch_url(url)
        soup = BeautifulSoup(
            html, "html.parser", parse_only=SoupStrainer("title")
        )
        assert google.is_page_candidate(
            url, soup.title.string, s["title"], s["artist"]
        ), url

    def test_is_page_candidate_fuzzy_match(self):
        """Test matching html page title with song infos -- when song infos are
        not present in the title.
        """
        s = self.source
        url = s["url"] + s["path"]
        url_title = "example.com | Beats song by John doe"

        # very small diffs (typo) are ok eg 'beats' vs 'beets' with same artist
        assert google.is_page_candidate(
            url, url_title, s["title"], s["artist"]
        ), url
        # reject different title
        url_title = "example.com | seets bong lyrics by John doe"
        assert not google.is_page_candidate(
            url, url_title, s["title"], s["artist"]
        ), url

    def test_is_page_candidate_special_chars(self):
        """Ensure that `is_page_candidate` doesn't crash when the artist
        and such contain special regular expression characters.
        """
        # https://github.com/beetbox/beets/issues/1673
        s = self.source
        url = s["url"] + s["path"]
        url_title = "foo"

        google.is_page_candidate(url, url_title, s["title"], "Sunn O)))")


# test Genius backend


class GeniusBaseTest(unittest.TestCase):
    def setUp(self):
        """Set up configuration."""
        try:
            __import__("bs4")
        except ImportError:
            self.skipTest("Beautiful Soup 4 not available")


class GeniusScrapeLyricsFromHtmlTest(GeniusBaseTest):
    """tests Genius._scrape_lyrics_from_html()"""

    def setUp(self):
        """Set up configuration"""
        GeniusBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()

    def test_no_lyrics_div(self):
        """Ensure we don't crash when the scraping the html for a genius page
        doesn't contain <div class="lyrics"></div>
        """
        # https://github.com/beetbox/beets/issues/3535
        # expected return value None
        url = "https://genius.com/sample"
        mock = MockFetchUrl()
        assert genius._scrape_lyrics_from_html(mock(url)) is None

    def test_good_lyrics(self):
        """Ensure we are able to scrape a page with lyrics"""
        url = "https://genius.com/Ttng-chinchilla-lyrics"
        mock = MockFetchUrl()
        lyrics = genius._scrape_lyrics_from_html(mock(url))
        assert lyrics is not None
        assert lyrics.count("\n") == 28

    def test_good_lyrics_multiple_divs(self):
        """Ensure we are able to scrape a page with lyrics"""
        url = "https://genius.com/2pac-all-eyez-on-me-lyrics"
        mock = MockFetchUrl()
        lyrics = genius._scrape_lyrics_from_html(mock(url))
        assert lyrics is not None
        assert lyrics.count("\n") == 133

    # TODO: find an example of a lyrics page with multiple divs and test it


class GeniusFetchTest(GeniusBaseTest):
    """tests Genius.fetch()"""

    def setUp(self):
        """Set up configuration"""
        GeniusBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()

    @patch.object(lyrics.Genius, "_scrape_lyrics_from_html")
    @patch.object(lyrics.Backend, "fetch_url", return_value=True)
    def test_json(self, mock_fetch_url, mock_scrape):
        """Ensure we're finding artist matches"""
        with patch.object(
            lyrics.Genius,
            "_search",
            return_value={
                "response": {
                    "hits": [
                        {
                            "result": {
                                "primary_artist": {
                                    "name": "\u200bblackbear",
                                },
                                "url": "blackbear_url",
                            }
                        },
                        {
                            "result": {
                                "primary_artist": {"name": "El\u002dp"},
                                "url": "El-p_url",
                            }
                        },
                    ]
                }
            },
        ) as mock_json:
            # genius uses zero-width-spaces (\u200B) for lowercase
            # artists so we make sure we can match those
            assert genius.fetch("blackbear", "Idfc") is not None
            mock_fetch_url.assert_called_once_with("blackbear_url")
            mock_scrape.assert_called_once_with(True)

            # genius uses the hyphen minus (\u002D) as their dash
            assert genius.fetch("El-p", "Idfc") is not None
            mock_fetch_url.assert_called_with("El-p_url")
            mock_scrape.assert_called_with(True)

            # test no matching artist
            assert genius.fetch("doesntexist", "none") is None

            # test invalid json
            mock_json.return_value = None
            assert genius.fetch("blackbear", "Idfc") is None

    # TODO: add integration test hitting real api


# test Tekstowo


class TekstowoBaseTest(unittest.TestCase):
    def setUp(self):
        """Set up configuration."""
        try:
            __import__("bs4")
        except ImportError:
            self.skipTest("Beautiful Soup 4 not available")


class TekstowoExtractLyricsTest(TekstowoBaseTest):
    """tests Tekstowo.extract_lyrics()"""

    def setUp(self):
        """Set up configuration"""
        TekstowoBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()
        tekstowo.config = self.plugin.config

    def test_good_lyrics(self):
        """Ensure we are able to scrape a page with lyrics"""
        url = "https://www.tekstowo.pl/piosenka,24kgoldn,city_of_angels_1.html"
        mock = MockFetchUrl()
        assert (
            tekstowo.extract_lyrics(mock(url), "24kGoldn", "City of Angels")
            is not None
        )

    def test_no_lyrics(self):
        """Ensure we don't crash when the scraping the html for a Tekstowo page
        doesn't contain lyrics
        """
        url = (
            "https://www.tekstowo.pl/piosenka,beethoven,"
            "beethoven_piano_sonata_17_tempest_the_3rd_movement.html"
        )
        mock = MockFetchUrl()
        assert (
            tekstowo.extract_lyrics(
                mock(url),
                "Beethoven",
                "Beethoven Piano Sonata 17" "Tempest The 3rd Movement",
            )
            is None
        )

    def test_song_no_match(self):
        """Ensure we return None when a song does not match the search query"""
        # https://github.com/beetbox/beets/issues/4406
        # expected return value None
        url = (
            "https://www.tekstowo.pl/piosenka,bailey_bigger"
            ",black_eyed_susan.html"
        )
        mock = MockFetchUrl()
        assert (
            tekstowo.extract_lyrics(
                mock(url), "Kelly Bailey", "Black Mesa Inbound"
            )
            is None
        )


class TekstowoParseSearchResultsTest(TekstowoBaseTest):
    """tests Tekstowo.parse_search_results()"""

    def setUp(self):
        """Set up configuration"""
        TekstowoBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()

    def test_multiple_results(self):
        """Ensure we are able to scrape a page with multiple search results"""
        url = (
            "https://www.tekstowo.pl/szukaj,wykonawca,juice+wrld"
            ",tytul,lucid+dreams.html"
        )
        mock = MockFetchUrl()
        assert (
            tekstowo.parse_search_results(mock(url))
            == "http://www.tekstowo.pl/piosenka,juice_wrld,"
            "lucid_dreams__remix__ft__lil_uzi_vert.html"
        )

    def test_no_results(self):
        """Ensure we are able to scrape a page with no search results"""
        url = (
            "https://www.tekstowo.pl/szukaj,wykonawca,"
            "agfdgja,tytul,agfdgafg.html"
        )
        mock = MockFetchUrl()
        assert tekstowo.parse_search_results(mock(url)) is None


class TekstowoIntegrationTest(TekstowoBaseTest, LyricsAssertions):
    """Tests Tekstowo lyric source with real requests"""

    def setUp(self):
        """Set up configuration"""
        TekstowoBaseTest.setUp(self)
        self.plugin = lyrics.LyricsPlugin()
        tekstowo.config = self.plugin.config

    @pytest.mark.integration_test
    def test_normal(self):
        """Ensure we can fetch a song's lyrics in the ordinary case"""
        lyrics = tekstowo.fetch("Boy in Space", "u n eye")
        self.assertLyricsContentOk("u n eye", lyrics)

    @pytest.mark.integration_test
    def test_no_matching_results(self):
        """Ensure we fetch nothing if there are search results
        returned but no matches"""
        # https://github.com/beetbox/beets/issues/4406
        # expected return value None
        lyrics = tekstowo.fetch("Kelly Bailey", "Black Mesa Inbound")
        assert lyrics is None


# test LRCLib backend


class LRCLibLyricsTest(unittest.TestCase):
    def setUp(self):
        self.plugin = lyrics.LyricsPlugin()
        lrclib.config = self.plugin.config

    @patch("beetsplug.lyrics.requests.get")
    def test_fetch_synced_lyrics(self, mock_get):
        mock_response = {
            "syncedLyrics": "[00:00.00] la la la",
            "plainLyrics": "la la la",
        }
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.status_code = 200

        lyrics = lrclib.fetch("la", "la", "la", 999)
        assert lyrics == mock_response["plainLyrics"]

        self.plugin.config["synced"] = True
        lyrics = lrclib.fetch("la", "la", "la", 999)
        assert lyrics == mock_response["syncedLyrics"]

    @patch("beetsplug.lyrics.requests.get")
    def test_fetch_plain_lyrics(self, mock_get):
        mock_response = {
            "syncedLyrics": "",
            "plainLyrics": "la la la",
        }
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.status_code = 200

        lyrics = lrclib.fetch("la", "la", "la", 999)

        assert lyrics == mock_response["plainLyrics"]

    @patch("beetsplug.lyrics.requests.get")
    def test_fetch_not_found(self, mock_get):
        mock_response = {
            "statusCode": 404,
            "error": "Not Found",
            "message": "Failed to find specified track",
        }
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.status_code = 404

        lyrics = lrclib.fetch("la", "la", "la", 999)

        assert lyrics is None

    @patch("beetsplug.lyrics.requests.get")
    def test_fetch_exception(self, mock_get):
        mock_get.side_effect = requests.RequestException

        lyrics = lrclib.fetch("la", "la", "la", 999)

        assert lyrics is None


class LRCLibIntegrationTest(LyricsAssertions):
    def setUp(self):
        self.plugin = lyrics.LyricsPlugin()
        lrclib.config = self.plugin.config

    @pytest.mark.integration_test
    def test_track_with_lyrics(self):
        lyrics = lrclib.fetch("Boy in Space", "u n eye", "Live EP", 160)
        self.assertLyricsContentOk("u n eye", lyrics)

    @pytest.mark.integration_test
    def test_instrumental_track(self):
        lyrics = lrclib.fetch(
            "Kelly Bailey", "Black Mesa Inbound", "Half Life 2 Soundtrack", 134
        )
        assert lyrics is None

    @pytest.mark.integration_test
    def test_nonexistent_track(self):
        lyrics = lrclib.fetch("blah", "blah", "blah", 999)
        assert lyrics is None


# test utilities


class SlugTests(unittest.TestCase):
    def test_slug(self):
        # plain ascii passthrough
        text = "test"
        assert lyrics.slug(text) == "test"

        # german unicode and capitals
        text = "Mørdag"
        assert lyrics.slug(text) == "mordag"

        # more accents and quotes
        text = "l'été c'est fait pour jouer"
        assert lyrics.slug(text) == "l-ete-c-est-fait-pour-jouer"

        # accents, parens and spaces
        text = "\xe7afe au lait (boisson)"
        assert lyrics.slug(text) == "cafe-au-lait-boisson"
        text = "Multiple  spaces -- and symbols! -- merged"
        assert lyrics.slug(text) == "multiple-spaces-and-symbols-merged"
        text = "\u200bno-width-space"
        assert lyrics.slug(text) == "no-width-space"

        # variations of dashes should get standardized
        dashes = ["\u200d", "\u2010"]
        for dash1, dash2 in itertools.combinations(dashes, 2):
            assert lyrics.slug(dash1) == lyrics.slug(dash2)
