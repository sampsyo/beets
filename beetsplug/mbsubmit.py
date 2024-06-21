# This file is part of beets.
# Copyright 2016, Adrian Sampson and Diego Moreda.
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

"""Aid in submitting information to MusicBrainz.

This plugin allows the user to print track information in a format that is
parseable by the MusicBrainz track parser [1]. Programmatic submitting is not
implemented by MusicBrainz yet.

The plugin also allows the user to open the tracks in MusicBrainz Picard [2].

Another option this plugin provides is to help with creating a new release
on MusicBrainz by seeding the MusicBrainz release editor [3]. This works in
the following way:

- Host a small web server that serves a web page. When loaded by the user,
  this page will automatically POST data to MusicBrainz as described in [3].
- The same web server also listens for a callback from MusicBrainz, see
  redirect_uri [3] and will try to import an album using the newly created
  release.
- jwt tokens with random keys are used to prevent using this web server in
  unintended ways.

This feature is loosely based on how browser integration is implemented in
Picard [4].

[1] https://wiki.musicbrainz.org/History:How_To_Parse_Track_Listings
[2] https://picard.musicbrainz.org/
[3] https://musicbrainz.org/doc/Development/Seeding/Release_Editor
[4] https://github.com/metabrainz/picard/blob/master/picard/browser/browser.py
"""
import socket
import subprocess
import threading
import time
import uuid
import webbrowser
from collections import defaultdict
from dataclasses import dataclass
from secrets import token_bytes
from typing import Callable, Dict, List, Optional

import waitress
from flask import Flask, render_template, request
from jwt import InvalidTokenError
from werkzeug.exceptions import BadRequest

from beets import autotag, ui
from beets.autotag import Recommendation
from beets.importer import ImportSession, ImportTask
from beets.library import Item
from beets.plugins import BeetsPlugin
from beets.ui import print_
from beets.ui.commands import PromptChoice
from beets.util import displayable_path
from beets.util.pipeline import PipelineThread
from beetsplug.info import print_data

try:
    import jwt
except ImportError:
    jwt = None


@dataclass
class CreateReleaseTask:
    """
    Represents a task for creating a single release on MusicBrainz and its current
    status.
    """

    formdata: Dict[str, str]
    """
    Form data to be submitted to MB.
    """

    browser_opened: bool = False
    """
    True when the user has opened the link for this task in the browser.
    """

    result_release_mbid: Optional[str] = None
    """
    Contains the release ID returned by MusicBrainz after the release was created.
    """


def join_phrase(i, total):
    if i < total - 2:
        return ", "
    elif i < total - 1:
        return " & "
    else:
        return ""


class MBSubmitPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        if jwt is None:
            self._log.warn(
                "Cannot import PyJWT, disabling 'Create release on musicbrainz' "
                "functionality"
            )

        self.config.add(
            {
                "format": "$track. $title - $artist ($length)",
                "threshold": "medium",
                "picard_path": "picard",
                "create_release_server_hostname": "127.0.0.1",
                "create_release_server_port": 0,
                "create_release_method": "show_link",
                "create_release_await_mbid": True,
                "create_release_default_type": None,
                "create_release_default_language": None,
                "create_release_default_script": None,
                "create_release_default_status": None,
                "create_release_default_packaging": None,
                "create_release_default_edit_note": None,
            }
        )

        self.create_release_server_hostname = self.config[
            "create_release_server_hostname"
        ].as_str()
        self.create_release_server_port = self.config[
            "create_release_server_port"
        ].as_number()
        self.create_release_method = self.config[
            "create_release_method"
        ].as_choice(["open_browser", "show_link"])
        self.create_release_await_mbid = self.config[
            "create_release_await_mbid"
        ].as_choice([True, False])

        # Validate and store threshold.
        self.threshold = self.config["threshold"].as_choice(
            {
                "none": Recommendation.none,
                "low": Recommendation.low,
                "medium": Recommendation.medium,
                "strong": Recommendation.strong,
            }
        )

        self.register_listener(
            "before_choose_candidate", self.before_choose_candidate_event
        )

        self.flask_app = Flask(__name__, template_folder="mbsubmit/templates")
        self.flask_app.add_url_rule(
            "/add", "add", view_func=self._create_release_add
        )
        self.flask_app.add_url_rule(
            "/complete_add",
            "complete_add",
            view_func=self._create_release_complete_add,
        )

        self._server = None
        self._server_port = None
        self._jwt_key = token_bytes()
        self._jwt_algorithm = "HS256"

        # When the user selects "Create release on musicbrainz", the data that is going
        #  to get POSTed to MusicBrainz is stored in this dict using a randomly
        #  generated key. The token in the URL opened by the user contains this key. The
        #  web server looks up the data in this dictionary using the key, and generates
        #  the page to be displayed.
        self._create_release_tasks = dict()

    def _build_formdata(self, items: List[Item], redirect_uri: Optional[str]):
        formdata = dict()

        labels = set()
        album_artists = set()

        track_counter = defaultdict(int)

        all_track_names = ""

        for track in items:
            if "name" not in formdata and track.album:
                formdata["name"] = track.album
            if "type" not in formdata and track.albumtype:
                formdata["type"] = track.albumtype
            if "barcode" not in formdata and track.barcode:
                formdata["barcode"] = track.barcode
            if "events.0.date.year" not in formdata and track.year:
                formdata["events.0.date.year"] = track.year
            if "events.0.date.month" not in formdata and track.month:
                formdata["events.0.date.month"] = track.month
            if "events.0.date.day" not in formdata and track.day:
                formdata["events.0.date.day"] = track.day

            if track.label:
                labels.add(track.label)

            if track.albumartists:
                for artist in track.albumartists:
                    album_artists.add(artist)
            elif track.albumartist:
                album_artists.add(track.albumartist)

            if track.disc:
                medium_index = track.disc - 1
            else:
                medium_index = 0

            track_index = track_counter[medium_index]

            if f"mediums.{medium_index}.format" not in formdata and track.media:
                formdata[f"mediums.{medium_index}.format"] = track.media

            formdata[f"mediums.{medium_index}.track.{track_index}.name"] = (
                track.title
            )
            formdata[f"mediums.{medium_index}.track.{track_index}.number"] = (
                track.track
            )
            formdata[f"mediums.{medium_index}.track.{track_index}.length"] = (
                int(track.length * 1000)
            )  # in milliseconds

            all_track_names += f"{track.title}\n"

            if track.artists:
                track_artists = track.artists
            elif track.artist:
                track_artists = [track.artist]
            else:
                track_artists = []

            for i, artist in enumerate(track_artists):
                formdata[
                    (
                        f"mediums.{medium_index}.track.{track_index}."
                        f"artist_credit.names.{i}.artist.name"
                    )
                ] = artist
                if join_phrase(i, len(track_artists)):
                    formdata[
                        (
                            f"mediums.{medium_index}.track.{track_index}."
                            f"artist_credit.names.{i}.join_phrase"
                        )
                    ] = join_phrase(i, len(track_artists))

            track_counter[medium_index] += 1

        for i, label in enumerate(labels):
            formdata[f"labels.{i}.name"] = label

        for i, artist in enumerate(album_artists):
            formdata[f"artist_credit.names.{i}.artist.name"] = artist
            if join_phrase(i, len(album_artists)):
                formdata[f"artist_credit.names.{i}.join_phrase"] = join_phrase(
                    i, len(album_artists)
                )

        if redirect_uri:
            formdata["redirect_uri"] = redirect_uri

        for default_field in [
            "type",
            "language",
            "script",
            "status",
            "packaging",
            "edit_note",
        ]:
            if (
                default_field not in formdata
                and self.config[f"create_release_default_{default_field}"]
            ):
                formdata[default_field] = self.config[
                    f"create_release_default_{default_field}"
                ].get()

        return formdata

    def _get_task_from_token(self, token: str) -> CreateReleaseTask:
        # Try to get the token from query args, try to decode it, and try to find the
        #  associated CreateReleaseTask.
        try:
            payload = jwt.decode(
                token,
                self._jwt_key,
                algorithms=self._jwt_algorithm,
            )
        except InvalidTokenError as e:
            self._log.error(f"Invalid token: {str(e)}")
            raise BadRequest()

        if (
            "task_key" in payload
            and payload["task_key"] in self._create_release_tasks
        ):
            return self._create_release_tasks[payload["task_key"]]
        else:
            self._log.error("task_key does not exist")
            raise BadRequest()

    def _create_release_add(self):
        token = request.args.get("token")
        if token is None:
            self._log.error("Missing token in request")
            raise BadRequest()

        task = self._get_task_from_token(token)
        task.browser_opened = True
        return render_template("create_release_add.html", task=task)

    def _create_release_complete_add(self):
        token = request.args.get("token")
        release_mbid = request.args.get("release_mbid")
        if token is None or release_mbid is None:
            self._log.error("Missing token or release_mbid in request")
            raise BadRequest()

        task = self._get_task_from_token(token)
        task.result_release_mbid = release_mbid
        return render_template("create_release_complete_add.html", task=task)

    def _start_server(self) -> bool:
        if self._server:
            return True

        if (port := self.create_release_server_port) == 0:
            # Find a free port for us to use. The OS will select a random available one.
            # We can't pass 0 to waitress.create_server directly, this won't work when
            #  using hostnames instead of IP addresses for
            #  create_release_server_hostname, waitress will then bind to multiple
            #  sockets, with different ports for each.
            with socket.socket() as s:
                s.bind((self.create_release_server_hostname, 0))
                port = s.getsockname()[1]

        try:
            self._server = waitress.create_server(
                self.flask_app,
                host=self.create_release_server_hostname,
                port=port,
            )
            threading.Thread(target=self._server.run, daemon=True).start()
            self._server_port = port
            return True
        except (PermissionError, ValueError, OSError) as e:
            self._log.error(
                f"Failed to start internal web server on "
                f"{self.create_release_server_hostname}:{port}: {str(e)}"
            )
            self._server = None
            return False

    def _stop_server(self):
        if self._server:
            self._server.close()
            self._server = None
            self._server_port = None

    def _wait_for_condition(self, condition: Callable):
        t = threading.current_thread()
        while not condition():
            time.sleep(0.5)
            # When running in multithreaded mode, wait for either condition to be true
            #  or until the executing thread wants to abort (such as when the user
            #  presses CTRL+c).
            if isinstance(t, PipelineThread) and t.abort_flag:
                raise KeyboardInterrupt()

            # When not running in multithreaded mode, KeyboardInterrupt will get
            #  propagated to this plugin as usual

    def before_choose_candidate_event(
        self, session: ImportSession, task: ImportTask
    ):
        if task.rec <= self.threshold:
            choices = [
                PromptChoice("p", "Print tracks", self.print_tracks),
                PromptChoice("o", "Open files with Picard", self.picard),
            ]
            if jwt is not None and task.is_album:
                choices += [
                    PromptChoice(
                        "c",
                        "Create release on musicbrainz",
                        self.create_release_on_musicbrainz,
                    ),
                ]
            return choices

    def picard(self, session: ImportSession, task: ImportTask):
        paths = []
        for p in task.paths:
            paths.append(displayable_path(p))
        try:
            picard_path = self.config["picard_path"].as_str()
            subprocess.Popen([picard_path] + paths)
            self._log.info("launched picard from\n{}", picard_path)
        except OSError as exc:
            self._log.error(f"Could not open picard, got error:\n{exc}")

    def print_tracks(self, session: ImportSession, task: ImportTask):
        self._print_tracks(task.items)

    def _print_tracks(self, items: List[Item]):
        for i in sorted(items, key=lambda i: i.track):
            print_data(None, i, self.config["format"].as_str())

    def create_release_on_musicbrainz(
        self, session: ImportSession, task: ImportTask
    ):
        return self._create_release_on_musicbrainz(task.items)

    def _create_release_on_musicbrainz(self, items: List[Item]):
        if not self._start_server():
            return
        task_key = str(uuid.uuid4())
        token = jwt.encode(
            {"task_key": task_key}, self._jwt_key, algorithm=self._jwt_algorithm
        )

        url = (
            f"http://{self.create_release_server_hostname}:"
            f"{self._server_port}/add?token={token}"
        )
        redirect_uri = (
            f"http://{self.create_release_server_hostname}:"
            f"{self._server_port}/complete_add?token={token}"
        )

        self._log.debug(
            f"New create release task with task_key {task_key}, serving at {url}"
        )

        self._create_release_tasks[task_key] = CreateReleaseTask(
            formdata=self._build_formdata(
                items=items,
                redirect_uri=(
                    redirect_uri if self.create_release_await_mbid else None
                ),
            ),
        )

        if self.create_release_method == "open_browser":
            webbrowser.open(url)
        elif self.create_release_method == "show_link":
            print_(f"Open the following URL in your browser: {url}")
        else:
            return

        self._wait_for_condition(
            lambda: self._create_release_tasks[task_key].browser_opened
        )

        if not self.create_release_await_mbid:
            return

        print_("Waiting for MusicBrainz release ID...")

        self._wait_for_condition(
            lambda: self._create_release_tasks[task_key].result_release_mbid
        )
        mbid = self._create_release_tasks[task_key].result_release_mbid

        self._log.debug(f"Got release_mbid {mbid} for task_key {task_key}")

        _, _, prop = autotag.tag_album(items, search_ids=[mbid])
        return prop

    def commands(self):
        """Add beet UI commands for mbsubmit."""
        mbsubmit_cmd = ui.Subcommand(
            "mbsubmit", help="submit tracks to MusicBrainz"
        )

        def mbsubmit_cmd_func(lib, opts, args):
            items = lib.items(ui.decargs(args))
            self._print_tracks(items)

        mbsubmit_cmd.func = mbsubmit_cmd_func

        mbcreate_cmd = ui.Subcommand(
            "mbsubmit-create", help="create release on MusicBrainz"
        )

        def mbcreate_cmd_func(lib, ops, args):
            items = lib.items(ui.decargs(args))
            print_(f"{len(items)} matching item(s) found.")
            if len(items) == 0:
                return
            self._print_tracks(items)
            self.create_release_await_mbid = False
            self._create_release_on_musicbrainz(items)

        mbcreate_cmd.func = mbcreate_cmd_func

        return [mbsubmit_cmd, mbcreate_cmd]
