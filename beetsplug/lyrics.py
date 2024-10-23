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

"""Fetches, embeds, and displays lyrics."""

from __future__ import annotations

import atexit
import itertools
import math
import re
import textwrap
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import cached_property, partial, total_ordering
from html import unescape
from http import HTTPStatus
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Iterator, NamedTuple
from urllib.parse import quote, quote_plus, urlencode, urlparse

import langdetect
import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

import beets
from beets import plugins, ui
from beets.autotag.hooks import string_dist

if TYPE_CHECKING:
    from logging import Logger

    from beets.importer import ImportTask
    from beets.library import Item, Library

    from ._typing import (
        GeniusAPI,
        GoogleCustomSearchAPI,
        JSONDict,
        LRCLibAPI,
        TranslatorAPI,
    )

USER_AGENT = f"beets/{beets.__version__}"
INSTRUMENTAL_LYRICS = "[Instrumental]"


class NotFoundError(requests.exceptions.HTTPError):
    pass


class CaptchaError(requests.exceptions.HTTPError):
    pass


class TimeoutSession(requests.Session):
    def request(self, *args, **kwargs):
        """Wrap the request method to raise an exception on HTTP errors."""
        kwargs.setdefault("timeout", 10)
        r = super().request(*args, **kwargs)
        if r.status_code == HTTPStatus.NOT_FOUND:
            raise NotFoundError("HTTP Error: Not Found", response=r)
        if 300 <= r.status_code < 400:
            raise CaptchaError("Captcha is required", response=r)

        r.raise_for_status()

        return r


r_session = TimeoutSession()
r_session.headers.update({"User-Agent": USER_AGENT})


@atexit.register
def close_session():
    """Close the requests session on shut down."""
    r_session.close()


# Utilities.


def search_pairs(item):
    """Yield a pairs of artists and titles to search for.

    The first item in the pair is the name of the artist, the second
    item is a list of song names.

    In addition to the artist and title obtained from the `item` the
    method tries to strip extra information like paranthesized suffixes
    and featured artists from the strings and add them as candidates.
    The artist sort name is added as a fallback candidate to help in
    cases where artist name includes special characters or is in a
    non-latin script.
    The method also tries to split multiple titles separated with `/`.
    """

    def generate_alternatives(string, patterns):
        """Generate string alternatives by extracting first matching group for
        each given pattern.
        """
        alternatives = [string]
        for pattern in patterns:
            match = re.search(pattern, string, re.IGNORECASE)
            if match:
                alternatives.append(match.group(1))
        return alternatives

    title, artist, artist_sort = (
        item.title.strip(),
        item.artist.strip(),
        item.artist_sort.strip(),
    )
    if not title or not artist:
        return ()

    patterns = [
        # Remove any featuring artists from the artists name
        rf"(.*?) {plugins.feat_tokens()}"
    ]

    # Skip various artists
    artists = []
    lower_artist = artist.lower()
    if "various" not in lower_artist:
        artists.extend(generate_alternatives(artist, patterns))
    # Use the artist_sort as fallback only if it differs from artist to avoid
    # repeated remote requests with the same search terms
    artist_sort_lower = artist_sort.lower()
    if (
        artist_sort
        and lower_artist != artist_sort_lower
        and "various" not in artist_sort_lower
    ):
        artists.append(artist_sort)

    patterns = [
        # Remove a parenthesized suffix from a title string. Common
        # examples include (live), (remix), and (acoustic).
        r"(.+?)\s+[(].*[)]$",
        # Remove any featuring artists from the title
        r"(.*?) {}".format(plugins.feat_tokens(for_artist=False)),
        # Remove part of title after colon ':' for songs with subtitles
        r"(.+?)\s*:.*",
    ]
    titles = generate_alternatives(title, patterns)

    # Check for a dual song (e.g. Pink Floyd - Speak to Me / Breathe)
    # and each of them.
    multi_titles = []
    for title in titles:
        multi_titles.append([title])
        if " / " in title:
            multi_titles.append([x.strip() for x in title.split(" / ")])

    return itertools.product(artists, multi_titles)


def slug(text: str) -> str:
    """Make a URL-safe, human-readable version of the given text

    This will do the following:

    1. decode unicode characters into ASCII
    2. shift everything to lowercase
    3. strip whitespace
    4. replace other non-word characters with dashes
    5. strip extra dashes
    """
    return re.sub(r"\W+", "-", unidecode(text).lower().strip()).strip("-")


class RequestHandler:
    _log: beets.logging.Logger

    def debug(self, message: str, *args) -> None:
        """Log a debug message with the class name."""
        self._log.debug(f"{self.__class__.__name__}: {message}", *args)

    def info(self, message: str, *args) -> None:
        """Log an info message with the class name."""
        self._log.info(f"{self.__class__.__name__}: {message}", *args)

    def warn(self, message: str, *args) -> None:
        """Log warning with the class name."""
        self._log.warning(f"{self.__class__.__name__}: {message}", *args)

    @staticmethod
    def format_url(url: str, params: JSONDict | None) -> str:
        if not params:
            return url

        return f"{url}?{urlencode(params)}"

    def fetch_text(
        self, url: str, params: JSONDict | None = None, **kwargs
    ) -> str:
        """Return text / HTML data from the given URL.

        Set the encoding to None to let requests handle it because some sites
        set it incorrectly.
        """
        url = self.format_url(url, params)
        self.debug("Fetching HTML from {}", url)
        r = r_session.get(url, **kwargs)
        r.encoding = None
        return r.text

    def fetch_json(self, url: str, params: JSONDict | None = None, **kwargs):
        """Return JSON data from the given URL."""
        url = self.format_url(url, params)
        self.debug("Fetching JSON from {}", url)
        return r_session.get(url, **kwargs).json()

    def post_json(self, url: str, params: JSONDict | None = None, **kwargs):
        """Send POST request and return JSON response."""
        url = self.format_url(url, params)
        self.debug("Posting JSON to {}", url)
        return r_session.post(url, **kwargs).json()

    @contextmanager
    def handle_request(self) -> Iterator[None]:
        try:
            yield
        except requests.JSONDecodeError:
            self.warn("Could not decode response JSON data")
        except requests.RequestException as exc:
            self.warn("Request error: {}", exc)


class BackendClass(type):
    @property
    def name(cls) -> str:
        """Return lowercase name of the backend class."""
        return cls.__name__.lower()


class Backend(RequestHandler, metaclass=BackendClass):
    def __init__(self, config, log):
        self._log = log
        self.config = config

    def fetch(
        self, artist: str, title: str, album: str, length: int
    ) -> tuple[str, str] | None:
        raise NotImplementedError


@dataclass
@total_ordering
class LRCLyrics:
    #: Percentage tolerance for max duration difference between lyrics and item.
    DURATION_DIFF_TOLERANCE = 0.05

    target_duration: float
    id: int
    duration: float
    instrumental: bool
    plain: str
    synced: str | None

    def __le__(self, other: LRCLyrics) -> bool:
        """Compare two lyrics items by their score."""
        return self.dist < other.dist

    @classmethod
    def make(
        cls, candidate: LRCLibAPI.Item, target_duration: float
    ) -> LRCLyrics:
        return cls(
            target_duration,
            candidate["id"],
            candidate["duration"] or 0.0,
            candidate["instrumental"],
            candidate["plainLyrics"],
            candidate["syncedLyrics"],
        )

    @cached_property
    def duration_dist(self) -> float:
        """Return the absolute difference between lyrics and target duration."""
        return abs(self.duration - self.target_duration)

    @cached_property
    def is_valid(self) -> bool:
        """Return whether the lyrics item is valid.
        Lyrics duration must be within the tolerance defined by
        :attr:`DURATION_DIFF_TOLERANCE`.
        """
        return (
            self.duration_dist
            <= self.target_duration * self.DURATION_DIFF_TOLERANCE
        )

    @cached_property
    def dist(self) -> tuple[bool, float]:
        """Distance/score of the given lyrics item.

        Return a tuple with the following values:
        1. Absolute difference between lyrics and target duration
        2. Boolean telling whether synced lyrics are available.

        Best lyrics match is the one that has the closest duration to
        ``target_duration`` and has synced lyrics available.
        """
        return not self.synced, self.duration_dist

    def get_text(self, want_synced: bool) -> str:
        if self.instrumental:
            return INSTRUMENTAL_LYRICS

        if want_synced and self.synced:
            return "\n".join(map(str.strip, self.synced.splitlines()))

        return self.plain


class LRCLib(Backend):
    """Fetch lyrics from the LRCLib API."""

    BASE_URL = "https://lrclib.net/api"
    GET_URL = f"{BASE_URL}/get"
    SEARCH_URL = f"{BASE_URL}/search"

    def fetch_candidates(
        self, artist: str, title: str, album: str, length: int
    ) -> Iterator[list[LRCLibAPI.Item]]:
        """Yield lyrics candidates for the given song data.

        I found that the ``/get`` endpoint sometimes returns inaccurate or
        unsynced lyrics, while ``search`` yields more suitable candidates.
        Therefore, we prioritize the latter and rank the results using our own
        algorithm. If the search does not give suitable lyrics, we fall back to
        the ``/get`` endpoint.

        Return an iterator over lists of candidates.
        """
        base_params = {"artist_name": artist, "track_name": title}
        get_params = {**base_params, "duration": length}
        if album:
            get_params["album_name"] = album

        yield self.fetch_json(self.SEARCH_URL, params=base_params)

        with suppress(NotFoundError):
            yield [self.fetch_json(self.GET_URL, params=get_params)]

    @classmethod
    def pick_best_match(cls, lyrics: Iterable[LRCLyrics]) -> LRCLyrics | None:
        """Return best matching lyrics item from the given list."""
        return min((li for li in lyrics if li.is_valid), default=None)

    def fetch(
        self, artist: str, title: str, album: str, length: int
    ) -> tuple[str, str] | None:
        """Fetch lyrics text for the given song data."""
        evaluate_item = partial(LRCLyrics.make, target_duration=length)

        for group in self.fetch_candidates(artist, title, album, length):
            candidates = [evaluate_item(item) for item in group]
            if item := self.pick_best_match(candidates):
                lyrics = item.get_text(self.config["synced"])
                return lyrics, f"{self.GET_URL}/{item.id}"

        return None


class MusiXmatch(Backend):
    URL_TEMPLATE = "https://www.musixmatch.com/lyrics/{}/{}"

    REPLACEMENTS = {
        r"\s+": "-",
        "<": "Less_Than",
        ">": "Greater_Than",
        "#": "Number_",
        r"[\[\{]": "(",
        r"[\]\}]": ")",
    }

    @classmethod
    def encode(cls, text: str) -> str:
        for old, new in cls.REPLACEMENTS.items():
            text = re.sub(old, new, text)

        return quote(unidecode(text))

    @classmethod
    def build_url(cls, *args: str) -> str:
        return cls.URL_TEMPLATE.format(*map(cls.encode, args))

    def fetch(self, artist: str, title: str, *_) -> tuple[str, str] | None:
        url = self.build_url(artist, title)

        html = self.fetch_text(url)
        if "We detected that your IP is blocked" in html:
            self.warn("Failed: Blocked IP address")
            return None
        html_parts = html.split('<p class="mxm-lyrics__content')
        # Sometimes lyrics come in 2 or more parts
        lyrics_parts = []
        for html_part in html_parts:
            lyrics_parts.append(re.sub(r"^[^>]+>|</p>.*", "", html_part))
        lyrics = "\n".join(lyrics_parts)
        lyrics = lyrics.strip(',"').replace("\\n", "\n")
        # another odd case: sometimes only that string remains, for
        # missing songs. this seems to happen after being blocked
        # above, when filling in the CAPTCHA.
        if "Instant lyrics for all your music." in lyrics:
            return None
        # sometimes there are non-existent lyrics with some content
        if "Lyrics | Musixmatch" in lyrics:
            return None
        return lyrics, url


class Html:
    collapse_space = partial(re.compile(r"(^| ) +", re.M).sub, r"\1")
    expand_br = partial(re.compile(r"\s*<br[^>]*>\s*", re.I).sub, "\n")
    #: two newlines between paragraphs on the same line (musica, letras.mus.br)
    merge_blocks = partial(re.compile(r"(?<!>)</p><p[^>]*>").sub, "\n\n")
    #: a single new line between paragraphs on separate lines
    #: (paroles.net, sweetslyrics.com, lacoccinelle.net)
    merge_lines = partial(re.compile(r"</p>\s+<p[^>]*>(?!___)").sub, "\n")
    #: remove empty divs (lacoccinelle.net)
    remove_empty_tags = partial(
        re.compile(r"(<(div|span)[^>]*>\s*</\2>)").sub, ""
    )
    #: remove Google Ads tags (musica.com)
    remove_aside = partial(re.compile("<aside .+?</aside>").sub, "")
    #: remove adslot-Content_1 div from the lyrics text (paroles.net)
    remove_adslot = partial(
        re.compile(r"\n</div>[^\n]+-- Content_\d+ --.*?\n<div>", re.S).sub,
        "\n",
    )
    #: remove text formatting (azlyrics.com, lacocinelle.net)
    remove_formatting = partial(
        re.compile(r" *</?(i|em|pre|strong)[^>]*>").sub, ""
    )

    @classmethod
    def normalize_space(cls, text: str) -> str:
        text = unescape(text).replace("\r", "").replace("\xa0", " ")
        return cls.collapse_space(cls.expand_br(text))

    @classmethod
    def remove_ads(cls, text: str) -> str:
        return cls.remove_adslot(cls.remove_aside(text))

    @classmethod
    def merge_paragraphs(cls, text: str) -> str:
        return cls.merge_blocks(cls.merge_lines(cls.remove_empty_tags(text)))


class SoupMixin:
    @classmethod
    def pre_process_html(cls, html: str) -> str:
        """Pre-process the HTML content before scraping."""
        return Html.normalize_space(html)

    @classmethod
    def get_soup(cls, html: str) -> BeautifulSoup:
        return BeautifulSoup(cls.pre_process_html(html), "html.parser")


class SearchResult(NamedTuple):
    artist: str
    title: str
    url: str

    @property
    def source(self) -> str:
        return urlparse(self.url).netloc


class SearchBackend(SoupMixin, Backend):
    @cached_property
    def dist_thresh(self) -> float:
        return self.config["dist_thresh"].get(float)

    def check_match(
        self, target_artist: str, target_title: str, result: SearchResult
    ) -> bool:
        """Check if the given search result is a 'good enough' match."""
        max_dist = max(
            string_dist(target_artist, result.artist),
            string_dist(target_title, result.title),
        )

        if (max_dist := round(max_dist, 2)) <= self.dist_thresh:
            return True

        if math.isclose(max_dist, self.dist_thresh, abs_tol=0.4):
            # log out the candidate that did not make it but was close.
            # This may show a matching candidate with some noise in the name
            self.debug(
                "({}, {}) does not match ({}, {}) but dist was close: {:.2f}",
                result.artist,
                result.title,
                target_artist,
                target_title,
                max_dist,
            )

        return False

    def search(self, artist: str, title: str) -> Iterable[SearchResult]:
        """Search for the given query and yield search results."""
        raise NotImplementedError

    def get_results(self, artist: str, title: str) -> Iterable[SearchResult]:
        check_match = partial(self.check_match, artist, title)
        for candidate in self.search(artist, title):
            if check_match(candidate):
                yield candidate

    def fetch(self, artist: str, title: str, *_) -> tuple[str, str] | None:
        """Fetch lyrics for the given artist and title."""
        for result in self.get_results(artist, title):
            if (html := self.fetch_text(result.url)) and (
                lyrics := self.scrape(html)
            ):
                return lyrics, result.url

        return None

    @classmethod
    def scrape(cls, html: str) -> str | None:
        """Scrape the lyrics from the given HTML."""
        raise NotImplementedError


class Genius(SearchBackend):
    """Fetch lyrics from Genius via genius-api.

    Because genius doesn't allow accessing lyrics via the api, we first query
    the api for a url matching our artist & title, then scrape the HTML text
    for the JSON data containing the lyrics.
    """

    SEARCH_URL = "https://api.genius.com/search"
    LYRICS_IN_JSON_RE = re.compile(r'(?<=.\\"html\\":\\").*?(?=(?<!\\)\\")')
    remove_backslash = partial(re.compile(r"\\(?=[^\\])").sub, "")

    @cached_property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f'Bearer {self.config["genius_api_key"]}'}

    def search(self, artist: str, title: str) -> Iterable[SearchResult]:
        search_data: GeniusAPI.Search = self.fetch_json(
            self.SEARCH_URL,
            params={"q": f"{artist} {title}"},
            headers=self.headers,
        )
        for r in (hit["result"] for hit in search_data["response"]["hits"]):
            yield SearchResult(r["artist_names"], r["title"], r["url"])

    @classmethod
    def scrape(cls, html: str) -> str | None:
        if m := cls.LYRICS_IN_JSON_RE.search(html):
            html_text = cls.remove_backslash(m[0]).replace(r"\n", "\n")
            return cls.get_soup(html_text).get_text().strip()

        return None


class Tekstowo(SearchBackend):
    """Fetch lyrics from Tekstowo.pl."""

    BASE_URL = "https://www.tekstowo.pl"
    SEARCH_URL = BASE_URL + "/szukaj,{}.html"

    def build_url(self, artist, title):
        artistitle = f"{artist.title()} {title.title()}"

        return self.SEARCH_URL.format(quote_plus(unidecode(artistitle)))

    def search(self, artist: str, title: str) -> Iterable[SearchResult]:
        if html := self.fetch_text(self.build_url(title, artist)):
            soup = self.get_soup(html)
            for tag in soup.select("div[class=flex-group] > a[title*=' - ']"):
                artist, title = str(tag["title"]).split(" - ", 1)
                yield SearchResult(
                    artist, title, f"{self.BASE_URL}{tag['href']}"
                )

        return None

    @classmethod
    def scrape(cls, html: str) -> str | None:
        soup = cls.get_soup(html)

        if lyrics_div := soup.select_one("div.song-text > div.inner-text"):
            return lyrics_div.get_text()

        return None


class Google(SearchBackend):
    """Fetch lyrics from Google search results."""

    SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

    #: Exclude some letras.mus.br pages which do not contain lyrics.
    EXCLUDE_PAGES = [
        "significado.html",
        "traduccion.html",
        "traducao.html",
        "significados.html",
    ]

    #: Regular expression to match noise in the URL title.
    URL_TITLE_NOISE_RE = re.compile(
        r"""
\b
(
      paroles(\ et\ traduction|\ de\ chanson)?
    | letras?(\ de)?
    | liedtexte
    | dainų\ žodžiai
    | original\ song\ full\ text\.
    | official
    | 20[12]\d\ version
    | (absolute\ |az)?lyrics(\ complete)?
    | www\S+
    | \S+\.(com|net|mus\.br)
)
([^\w.]|$)
""",
        re.IGNORECASE | re.VERBOSE,
    )
    #: Split cleaned up URL title into artist and title parts.
    URL_TITLE_PARTS_RE = re.compile(r" +(?:[ :|-]+|par|by) +")

    SOURCE_DIST_FACTOR = {"www.azlyrics.com": 0.5, "www.songlyrics.com": 0.6}

    ignored_domains: set[str] = set()

    @classmethod
    def pre_process_html(cls, html: str) -> str:
        """Pre-process the HTML content before scraping."""
        html = Html.remove_ads(super().pre_process_html(html))
        return Html.remove_formatting(Html.merge_paragraphs(html))

    def fetch_text(self, *args, **kwargs) -> str:
        """Handle an error so that we can continue with the next URL."""
        kwargs.setdefault("allow_redirects", False)
        with self.handle_request():
            try:
                return super().fetch_text(*args, **kwargs)
            except CaptchaError:
                self.ignored_domains.add(urlparse(args[0]).netloc)
                raise

    @staticmethod
    def get_part_dist(artist: str, title: str, part: str) -> float:
        """Return the distance between the given part and the artist and title.

        A number between -1 and 1 is returned, where -1 means the part is
        closer to the artist and 1 means it is closer to the title.
        """
        return string_dist(artist, part) - string_dist(title, part)

    @classmethod
    def make_search_result(
        cls, artist: str, title: str, item: GoogleCustomSearchAPI.Item
    ) -> SearchResult:
        """Parse artist and title from the URL title and return a search result."""
        url_title = (
            # get full title from metatags if available
            item.get("pagemap", {}).get("metatags", [{}])[0].get("og:title")
            # default to the dispolay title
            or item["title"]
        )
        clean_title = cls.URL_TITLE_NOISE_RE.sub("", url_title).strip(" .-|")
        # split it into parts which may be part of the artist or the title
        # `dict.fromkeys` removes duplicates keeping the order
        parts = list(dict.fromkeys(cls.URL_TITLE_PARTS_RE.split(clean_title)))

        if len(parts) == 1:
            part = parts[0]
            if m := re.search(rf"(?i)\W*({re.escape(title)})\W*", part):
                # artist and title may not have a separator
                result_title = m[1]
                result_artist = part.replace(m[0], "")
            else:
                # assume that this is the title
                result_artist, result_title = "", parts[0]
        else:
            # sort parts by their similarity to the artist
            parts.sort(key=lambda p: cls.get_part_dist(artist, title, p))
            result_artist, result_title = parts[0], " ".join(parts[1:])

        return SearchResult(result_artist, result_title, item["link"])

    def search(self, artist: str, title: str) -> Iterable[SearchResult]:
        params = {
            "key": self.config["google_API_key"].as_str(),
            "cx": self.config["google_engine_ID"].as_str(),
            "q": f"{artist} {title}",
            "siteSearch": "www.musixmatch.com",
            "siteSearchFilter": "e",
            "excludeTerms": ", ".join(self.EXCLUDE_PAGES),
        }

        data: GoogleCustomSearchAPI.Response = self.fetch_json(
            self.SEARCH_URL, params=params
        )
        for item in data.get("items", []):
            yield self.make_search_result(artist, title, item)

    def get_results(self, *args) -> Iterable[SearchResult]:
        """Try results from preferred sources first."""
        for result in sorted(
            super().get_results(*args),
            key=lambda r: self.SOURCE_DIST_FACTOR.get(r.source, 1),
        ):
            if result.source not in self.ignored_domains:
                yield result

    @classmethod
    def scrape(cls, html: str) -> str | None:
        # Get the longest text element (if any).
        if strings := sorted(cls.get_soup(html).stripped_strings, key=len):
            return strings[-1]

        return None


@dataclass
class Translator(RequestHandler):
    TRANSLATE_URL = "https://api.cognitive.microsofttranslator.com/translate"
    LINE_PARTS_RE = re.compile(r"^(\[\d\d:\d\d.\d\d\]|) *(.*)$")

    _log: Logger
    api_key: str
    to_language: str
    from_languages: list[str]

    @classmethod
    def from_config(
        cls,
        log: Logger,
        api_key: str,
        to_language: str,
        from_languages: list[str] | None = None,
    ) -> Translator:
        return cls(
            log,
            api_key,
            to_language.upper(),
            [x.upper() for x in from_languages or []],
        )

    def get_translations(self, texts: Iterable[str]) -> list[tuple[str, str]]:
        """Return translations for the given texts.

        To reduce the translation 'cost', we translate unique texts, and then
        map the translations back to the original texts.
        """
        unique_texts = list(dict.fromkeys(texts))
        data: list[TranslatorAPI.Response] = self.post_json(
            self.TRANSLATE_URL,
            headers={"Ocp-Apim-Subscription-Key": self.api_key},
            json=[{"text": "|".join(unique_texts)}],
            params={"api-version": "3.0", "to": self.to_language},
        )

        translations = data[0]["translations"][0]["text"].split("|")
        trans_by_text = dict(zip(unique_texts, translations))
        return list(zip(texts, (trans_by_text.get(t, "") for t in texts)))

    @classmethod
    def split_line(cls, line: str) -> tuple[str, str]:
        """Split line to (timestamp, text)."""
        if m := cls.LINE_PARTS_RE.match(line):
            return m[1], m[2]

        return "", ""

    def append_translations(self, lines: Iterable[str]) -> list[str]:
        """Append translations to the given lyrics texts.

        Lines may contain timestamps from LRCLib which need to be temporarily
        removed for the translation. They can take any of these forms:
                        - empty
        Text            - text only
        [00:00:00]      - timestamp only
        [00:00:00] Text - timestamp with text
        """
        # split into [(timestamp, text), ...]]
        ts_and_text = list(map(self.split_line, lines))
        timestamps = [ts for ts, _ in ts_and_text]
        text_pairs = self.get_translations([ln for _, ln in ts_and_text])

        # only add the separator for non-empty translations
        texts = [" / ".join(filter(None, p)) for p in text_pairs]
        # only add the space between non-empty timestamps and texts
        return [" ".join(filter(None, p)) for p in zip(timestamps, texts)]

    def translate(self, lyrics: str) -> str:
        """Translate the given lyrics to the target language.

        If the lyrics are already in the target language or not in any of
        of the source languages (if configured), they are returned as is.

        The footer with the source URL is preserved, if present.
        """
        lyrics_language = langdetect.detect(lyrics).upper()
        if lyrics_language == self.to_language or (
            self.from_languages and lyrics_language not in self.from_languages
        ):
            return lyrics

        lyrics, *url = lyrics.split("\n\nSource: ")
        with self.handle_request():
            translated_lines = self.append_translations(lyrics.splitlines())
            return "\n\nSource: ".join(["\n".join(translated_lines), *url])


@dataclass
class RestFiles:
    # The content for the base index.rst generated in ReST mode.
    REST_INDEX_TEMPLATE = textwrap.dedent("""
        Lyrics
        ======

        * :ref:`Song index <genindex>`
        * :ref:`search`

        Artist index:

        .. toctree::
           :maxdepth: 1
           :glob:

           artists/*
        """).strip()

    # The content for the base conf.py generated.
    REST_CONF_TEMPLATE = textwrap.dedent("""
        master_doc = "index"
        project = "Lyrics"
        copyright = "none"
        author = "Various Authors"
        latex_documents = [
            (master_doc, "Lyrics.tex", project, author, "manual"),
        ]
        epub_exclude_files = ["search.html"]
        epub_tocdepth = 1
        epub_tocdup = False
        """).strip()

    directory: Path

    @cached_property
    def artists_dir(self) -> Path:
        dir = self.directory / "artists"
        dir.mkdir(parents=True, exist_ok=True)
        return dir

    def write_indexes(self) -> None:
        """Write conf.py and index.rst files necessary for Sphinx

        We write minimal configurations that are necessary for Sphinx
        to operate. We do not overwrite existing files so that
        customizations are respected."""
        index_file = self.directory / "index.rst"
        if not index_file.exists():
            index_file.write_text(self.REST_INDEX_TEMPLATE)
        conf_file = self.directory / "conf.py"
        if not conf_file.exists():
            conf_file.write_text(self.REST_CONF_TEMPLATE)

    def write_artist(self, artist: str, items: Iterable[Item]) -> None:
        parts = [
            f'{artist}\n{"=" * len(artist)}',
            ".. contents::\n   :local:",
        ]
        for album, items in groupby(items, key=lambda i: i.album):
            parts.append(f'{album}\n{"-" * len(album)}')
            parts.extend(
                part
                for i in items
                if (title := f":index:`{i.title.strip()}`")
                for part in (
                    f'{title}\n{"~" * len(title)}',
                    textwrap.indent(i.lyrics, "| "),
                )
            )
        file = self.artists_dir / f"{slug(artist)}.rst"
        file.write_text("\n\n".join(parts).strip())

    def write(self, items: list[Item]) -> None:
        self.directory.mkdir(exist_ok=True, parents=True)
        self.write_indexes()

        items.sort(key=lambda i: i.albumartist)
        for artist, artist_items in groupby(items, key=lambda i: i.albumartist):
            self.write_artist(artist.strip(), artist_items)

        d = self.directory
        text = f"""
        ReST files generated. to build, use one of:
          sphinx-build -b html  {d} {d/"html"}
          sphinx-build -b epub  {d} {d/"epub"}
          sphinx-build -b latex {d} {d/"latex"} && make -C {d/"latex"} all-pdf
        """
        ui.print_(textwrap.dedent(text))


class LyricsPlugin(RequestHandler, plugins.BeetsPlugin):
    BACKEND_BY_NAME = {
        b.name: b for b in [LRCLib, Google, Genius, Tekstowo, MusiXmatch]
    }

    @cached_property
    def backends(self) -> list[Backend]:
        user_sources = self.config["sources"].get()

        chosen = plugins.sanitize_choices(user_sources, self.BACKEND_BY_NAME)
        if "google" in chosen and not self.config["google_API_key"].get():
            self.warn("Disabling Google source: no API key configured.")
            chosen.remove("google")

        return [self.BACKEND_BY_NAME[c](self.config, self._log) for c in chosen]

    @cached_property
    def translator(self) -> Translator | None:
        config = self.config["translate"]
        if config["api_key"].get() and config["to_language"].get():
            return Translator.from_config(self._log, **config.flatten())
        return None

    def __init__(self):
        super().__init__()
        self.config.add(
            {
                "auto": True,
                "translate": {
                    "api_key": None,
                    "from_languages": [],
                    "to_language": None,
                },
                "dist_thresh": 0.11,
                "google_API_key": None,
                "google_engine_ID": "009217259823014548361:lndtuqkycfu",
                "genius_api_key": (
                    "Ryq93pUGm8bM6eUWwD_M3NOFFDAtp2yEE7W"
                    "76V-uFL5jks5dNvcGCdarqFjDhP9c"
                ),
                "fallback": None,
                "force": False,
                "local": False,
                "print": False,
                "synced": False,
                # Musixmatch is disabled by default as they are currently blocking
                # requests with the beets user agent.
                "sources": [
                    n for n in self.BACKEND_BY_NAME if n != "musixmatch"
                ],
            }
        )
        self.config["translate"]["api_key"].redact = True
        self.config["google_API_key"].redact = True
        self.config["google_engine_ID"].redact = True
        self.config["genius_api_key"].redact = True

        if self.config["auto"]:
            self.import_stages = [self.imported]

    def commands(self):
        cmd = ui.Subcommand("lyrics", help="fetch song lyrics")
        cmd.parser.add_option(
            "-p",
            "--print",
            action="store_true",
            default=self.config["print"].get(),
            help="print lyrics to console",
        )
        cmd.parser.add_option(
            "-r",
            "--write-rest",
            dest="rest_directory",
            action="store",
            default=None,
            metavar="dir",
            help="write lyrics to given directory as ReST files",
        )
        cmd.parser.add_option(
            "-f",
            "--force",
            action="store_true",
            default=self.config["force"].get(),
            help="always re-download lyrics",
        )
        cmd.parser.add_option(
            "-l",
            "--local",
            action="store_true",
            default=self.config["local"].get(),
            help="do not fetch missing lyrics",
        )

        def func(lib: Library, opts, args) -> None:
            # The "write to files" option corresponds to the
            # import_write config value.
            self.config.set(vars(opts))
            items = list(lib.items(args))
            for item in items:
                self.add_item_lyrics(item, ui.should_write())
                if item.lyrics and opts.print:
                    ui.print_(item.lyrics)

            if opts.rest_directory and (
                items := [i for i in items if i.lyrics]
            ):
                RestFiles(Path(opts.rest_directory)).write(items)

        cmd.func = func
        return [cmd]

    def imported(self, _, task: ImportTask) -> None:
        """Import hook for fetching lyrics automatically."""
        for item in task.imported_items():
            self.add_item_lyrics(item, False)

    def find_lyrics(self, item: Item) -> str:
        album, length = item.album, round(item.length)
        matches = (
            [
                lyrics
                for t in titles
                if (lyrics := self.get_lyrics(a, t, album, length))
            ]
            for a, titles in search_pairs(item)
        )

        return "\n\n---\n\n".join(next(filter(None, matches), []))

    def add_item_lyrics(self, item: Item, write: bool) -> None:
        """Fetch and store lyrics for a single item. If ``write``, then the
        lyrics will also be written to the file itself.
        """
        if self.config["local"]:
            return

        if not self.config["force"] and item.lyrics:
            self.info("🔵 Lyrics already present: {}", item)
            return

        if lyrics := self.find_lyrics(item):
            self.info("🟢 Found lyrics: {0}", item)
            if translator := self.translator:
                initial_lyrics = lyrics
                if (lyrics := translator.translate(lyrics)) != initial_lyrics:
                    self.info(
                        "🟢 Added translation to {}",
                        self.config["translate_to"].get().upper(),
                    )
        else:
            self.info("🔴 Lyrics not found: {}", item)
            lyrics = self.config["fallback"].get()

        if lyrics not in {None, item.lyrics}:
            item.lyrics = lyrics
            if write:
                item.try_write()
            item.store()

    def get_lyrics(self, artist: str, title: str, *args) -> str | None:
        """Fetch lyrics, trying each source in turn. Return a string or
        None if no lyrics were found.
        """
        self.info("Fetching lyrics for {} - {}", artist, title)
        for backend in self.backends:
            with backend.handle_request():
                if lyrics_info := backend.fetch(artist, title, *args):
                    lyrics, url = lyrics_info
                    return f"{lyrics}\n\nSource: {url}"

        return None
