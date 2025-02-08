"""Tests for the 'subsonic' plugin."""

from urllib.parse import parse_qs, urlparse

import responses

from beets import config
from beets.test.helper import BeetsTestCase
from beetsplug import subsonicupdate


class ArgumentsMock:
    """Argument mocks for tests."""

    def __init__(self, mode, show_failures):
        """Constructs ArgumentsMock."""
        self.mode = mode
        self.show_failures = show_failures
        self.verbose = 1


def _params(url):
    """Get the query parameters from a URL."""
    return parse_qs(urlparse(url).query)


class SubsonicPluginTest(BeetsTestCase):
    """Test class for subsonicupdate."""

    @responses.activate
    def setUp(self):
        """Sets up config and plugin for test."""
        super().setUp()

        config["subsonic"]["user"] = "admin"
        config["subsonic"]["pass"] = "admin"
        config["subsonic"]["url"] = "http://localhost:4040"
        responses.add(
            responses.GET,
            "http://localhost:4040/rest/ping.view",
            status=200,
            body=self.PING_BODY,
        )
        self.subsonicupdate = subsonicupdate.SubsonicUpdate()

    PING_BODY = """
{
    "subsonic-response": {
        "status": "failed",
        "version": "1.15.0"
    }
}
"""
    SUCCESS_BODY = """
{
    "subsonic-response": {
        "status": "ok",
        "version": "1.15.0",
        "scanStatus": {
            "scanning": true,
            "count": 1000
        }
    }
}
"""

    FAILED_BODY = """
{
    "subsonic-response": {
        "status": "failed",
        "version": "1.15.0",
        "error": {
            "code": 40,
            "message": "Wrong username or password."
        }
    }
}
"""

    ERROR_BODY = """
{
    "timestamp": 1599185854498,
    "status": 404,
    "error": "Not Found",
    "message": "No message available",
    "path": "/rest/startScn"
}
"""

    @responses.activate
    def test_start_scan(self):
        """Tests success path based on best case scenario."""
        responses.add(
            responses.GET,
            "http://localhost:4040/rest/startScan",
            status=200,
            body=self.SUCCESS_BODY,
        )

        self.subsonicupdate.start_scan()

    @responses.activate
    def test_start_scan_failed_bad_credentials(self):
        """Tests failed path based on bad credentials."""
        responses.add(
            responses.GET,
            "http://localhost:4040/rest/startScan",
            status=200,
            body=self.FAILED_BODY,
        )

        self.subsonicupdate.start_scan()

    @responses.activate
    def test_start_scan_failed_not_found(self):
        """Tests failed path based on resource not found."""
        responses.add(
            responses.GET,
            "http://localhost:4040/rest/startScan",
            status=404,
            body=self.ERROR_BODY,
        )

        self.subsonicupdate.start_scan()

    def test_start_scan_failed_unreachable(self):
        """Tests failed path based on service not available."""
        self.subsonicupdate.start_scan()

    @responses.activate
    def test_url_with_context_path(self):
        """Tests success for included with contextPath."""
        config["subsonic"]["url"] = "http://localhost:4040/contextPath/"

        responses.add(
            responses.GET,
            "http://localhost:4040/contextPath/rest/startScan",
            status=200,
            body=self.SUCCESS_BODY,
        )

        self.subsonicupdate.start_scan()

    @responses.activate
    def test_url_with_trailing_forward_slash_url(self):
        """Tests success path based on trailing forward slash."""
        config["subsonic"]["url"] = "http://localhost:4040/"

        responses.add(
            responses.GET,
            "http://localhost:4040/rest/startScan",
            status=200,
            body=self.SUCCESS_BODY,
        )

        self.subsonicupdate.start_scan()

    @responses.activate
    def test_url_with_missing_port(self):
        """Tests failed path based on missing port."""
        config["subsonic"]["url"] = "http://localhost/airsonic"

        responses.add(
            responses.GET,
            "http://localhost/airsonic/rest/startScan",
            status=200,
            body=self.SUCCESS_BODY,
        )

        self.subsonicupdate.start_scan()

    @responses.activate
    def test_url_with_missing_schema(self):
        """Tests failed path based on missing schema."""
        config["subsonic"]["url"] = "localhost:4040/airsonic"

        responses.add(
            responses.GET,
            "http://localhost:4040/rest/startScan",
            status=200,
            body=self.SUCCESS_BODY,
        )

        self.subsonicupdate.start_scan()
