"""Adds Listenbrainz support to Beets."""

import datetime

import musicbrainzngs
import requests

from beets import config, ui
from beets.plugins import BeetsPlugin
from beetsplug.lastimport import process_tracks


class ListenBrainzPlugin(BeetsPlugin):
    """A Beets plugin for interacting with ListenBrainz."""

    data_source = "ListenBrainz"
    ROOT = "http://api.listenbrainz.org/1/"

    def __init__(self):
        """Initialize the plugin."""
        super().__init__()
        self.token = self.config["token"].get()
        self.username = self.config["username"].get()
        self.AUTH_HEADER = {"Authorization": f"Token {self.token}"}
        config["listenbrainz"]["token"].redact = True

    def commands(self):
        """Add beet UI commands to interact with ListenBrainz."""
        lbupdate_cmd = ui.Subcommand(
            "lbimport", help=f"Import {self.data_source} history"
        )

        def func(lib, opts, args):
            self._lbupdate(lib, self._log)

        lbupdate_cmd.func = func
        return [lbupdate_cmd]

    def _lbupdate(self, lib, log):
        """Obtain view count from Listenbrainz."""
        found_total = 0
        unknown_total = 0
        ls = self.get_listens()
        tracks = self.get_tracks_from_listens(ls)
        log.info(f"Found {len(ls)} listens")
        if tracks:
            found, unknown = process_tracks(lib, tracks, log)
            found_total += found
            unknown_total += unknown
        log.info("... done!")
        log.info("{0} unknown play-counts", unknown_total)
        log.info("{0} play-counts imported", found_total)

    def _make_request(self, url, params=None):
        """Makes a request to the ListenBrainz API."""
        try:
            response = requests.get(
                url=url,
                headers=self.AUTH_HEADER,
                timeout=10,
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self._log.debug(f"Invalid Search Error: {e}")
            return None

    def get_listens(self, min_ts=None, max_ts=None, count=None):
        """Gets the listen history of a given user.

        Args:
            username: User to get listen history of.
            min_ts: History before this timestamp will not be returned.
                    DO NOT USE WITH max_ts.
            max_ts: History after this timestamp will not be returned.
                    DO NOT USE WITH min_ts.
            count: How many listens to return. If not specified,
                uses a default from the server.

        Returns:
            A list of listen info dictionaries if there's an OK status.

        Raises:
            An HTTPError if there's a failure.
            A ValueError if the JSON in the response is invalid.
            An IndexError if the JSON is not structured as expected.
        """
        url = f"{self.ROOT}/user/{self.username}/listens"
        params = {
            k: v
            for k, v in {
                "min_ts": min_ts,
                "max_ts": max_ts,
                "count": count,
            }.items()
            if v is not None
        }
        response = self._make_request(url, params)

        if response is not None:
            return response["payload"]["listens"]
        else:
            return None

    def get_tracks_from_listens(self, listens):
        """Returns a list of tracks from a list of listens."""
        tracks = []
        for track in listens:
            if track["track_metadata"].get("release_name") is None:
                continue
            mbid_mapping = track["track_metadata"].get("mbid_mapping", {})
            # print(json.dumps(track, indent=4, sort_keys=True))
            if mbid_mapping.get("recording_mbid") is None:
                # search for the track using title and release
                mbid = self.get_mb_recording_id(track)
            tracks.append(
                {
                    "album": {
                        "name": track["track_metadata"].get("release_name")
                    },
                    "name": track["track_metadata"].get("track_name"),
                    "artist": {
                        "name": track["track_metadata"].get("artist_name")
                    },
                    "mbid": mbid,
                    "release_mbid": mbid_mapping.get("release_mbid"),
                    "listened_at": track.get("listened_at"),
                }
            )
        return tracks

    def get_mb_recording_id(self, track):
        """Returns the MusicBrainz recording ID for a track."""
        resp = musicbrainzngs.search_recordings(
            query=track["track_metadata"].get("track_name"),
            release=track["track_metadata"].get("release_name"),
            strict=True,
        )
        if resp.get("recording-count") == "1":
            return resp.get("recording-list")[0].get("id")
        else:
            return None

    def get_playlists_createdfor(self, username):
        """Returns a list of playlists created by a user."""
        url = f"{self.ROOT}/user/{username}/playlists/createdfor"
        return self._make_request(url)

    def get_listenbrainz_playlists(self):
        resp = self.get_playlists_createdfor(self.username)
        playlists = resp.get("playlists")
        listenbrainz_playlists = []

        for playlist in playlists:
            playlist_info = playlist.get("playlist")
            if playlist_info.get("creator") == "listenbrainz":
                title = playlist_info.get("title")
                self._log.debug(f"Playlist title: {title}")
                playlist_type = (
                    "Exploration" if "Exploration" in title else "Jams"
                )
                if "week of" in title:
                    date_str = title.split("week of ")[1].split(" ")[0]
                    date = datetime.datetime.strptime(
                        date_str, "%Y-%m-%d"
                    ).date()
                else:
                    continue
                identifier = playlist_info.get("identifier")
                id = identifier.split("/")[-1]
                listenbrainz_playlists.append(
                    {"type": playlist_type, "date": date, "identifier": id}
                )
        listenbrainz_playlists = sorted(
            listenbrainz_playlists, key=lambda x: x["type"]
        )
        listenbrainz_playlists = sorted(
            listenbrainz_playlists, key=lambda x: x["date"], reverse=True
        )
        for playlist in listenbrainz_playlists:
            self._log.debug(
                f'Playlist: {playlist["type"]} - {playlist["date"]}'
            )
        return listenbrainz_playlists

    def get_playlist(self, identifier):
        """Returns a playlist."""
        url = f"{self.ROOT}/playlist/{identifier}"
        return self._make_request(url)

    def get_tracks_from_playlist(self, playlist):
        """This function returns a list of tracks in the playlist."""
        tracks = []
        for track in playlist.get("playlist").get("track"):
            identifier = track.get("identifier")
            if isinstance(identifier, list):
                identifier = identifier[0]

            tracks.append(
                {
                    "artist": track.get("creator", "Unknown artist"),
                    "identifier": identifier.split("/")[-1],
                    "title": track.get("title"),
                }
            )
        return self.get_track_info(tracks)

    def get_track_info(self, tracks):
        track_info = []
        for track in tracks:
            identifier = track.get("identifier")
            resp = musicbrainzngs.get_recording_by_id(
                identifier, includes=["releases", "artist-credits"]
            )
            recording = resp.get("recording")
            title = recording.get("title")
            artist_credit = recording.get("artist-credit", [])
            if artist_credit:
                artist = artist_credit[0].get("artist", {}).get("name")
            else:
                artist = None
            releases = recording.get("release-list", [])
            if releases:
                album = releases[0].get("title")
                date = releases[0].get("date")
                year = date.split("-")[0] if date else None
            else:
                album = None
                year = None
            track_info.append(
                {
                    "identifier": identifier,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "year": year,
                }
            )
        return track_info

    def get_weekly_playlist(self, playlist_type, most_recent=True):
        # Fetch all playlists
        playlists = self.get_listenbrainz_playlists()
        # Filter playlists by type
        filtered_playlists = [
            p for p in playlists if p["type"] == playlist_type
        ]
        # Sort playlists by date in descending order
        sorted_playlists = sorted(
            filtered_playlists, key=lambda x: x["date"], reverse=True
        )
        # Select the most recent or older playlist based on the most_recent flag
        selected_playlist = (
            sorted_playlists[0] if most_recent else sorted_playlists[1]
        )
        self._log.debug(
            f"Selected playlist: {selected_playlist['type']} "
            f"- {selected_playlist['date']}"
        )
        # Fetch and return tracks from the selected playlist
        playlist = self.get_playlist(selected_playlist.get("identifier"))
        return self.get_tracks_from_playlist(playlist)

    def get_weekly_exploration(self):
        return self.get_weekly_playlist("Exploration", most_recent=True)

    def get_weekly_jams(self):
        return self.get_weekly_playlist("Jams", most_recent=True)

    def get_last_weekly_exploration(self):
        return self.get_weekly_playlist("Exploration", most_recent=False)

    def get_last_weekly_jams(self):
        return self.get_weekly_playlist("Jams", most_recent=False)
