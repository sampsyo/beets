# This file is part of beets.
# Copyright 2016, Pieter Mulder.
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

"""Calculate acoustic information and submit to AcousticBrainz."""

import errno
import hashlib
import json
import os
import subprocess
import tempfile
from distutils.spawn import find_executable

import requests

from beets import plugins, ui, util

# We use this field to check whether AcousticBrainz info is present.
PROBE_FIELD = "mood_acoustic"


class ABSubmitError(Exception):
    """Raised when failing to analyse file with extractor."""


def call(args):
    """Execute the command and return its output.

    Raise a AnalysisABSubmitError on failure.
    """
    try:
        return util.command_output(args).stdout
    except subprocess.CalledProcessError as e:
        raise ABSubmitError(
            "{} exited with status {}".format(args[0], e.returncode)
        )


class AcousticBrainzSubmitPlugin(plugins.BeetsPlugin):
    def __init__(self):
        super().__init__()

        self._log.warning("This plugin is deprecated.")

        self.config.add(
            {"extractor": "", "force": False, "pretend": False, "base_url": ""}
        )

        self.extractor = self.config["extractor"].as_str()
        if self.extractor:
            self.extractor = util.normpath(self.extractor)
            # Explicit path to extractor
            if not os.path.isfile(self.extractor):
                raise ui.UserError(
                    "Extractor command does not exist: {0}.".format(
                        self.extractor
                    )
                )
        else:
            # Implicit path to extractor, search for it in path
            self.extractor = "streaming_extractor_music"
            try:
                call([self.extractor])
            except OSError:
                raise ui.UserError(
                    "No extractor command found: please install the extractor"
                    " binary from https://essentia.upf.edu/"
                )
            except ABSubmitError:
                # Extractor found, will exit with an error if not called with
                # the correct amount of arguments.
                pass

            # Get the executable location on the system, which we need
            # to calculate the SHA-1 hash.
            self.extractor = find_executable(self.extractor)

        # Calculate extractor hash.
        self.extractor_sha = hashlib.sha1()
        with open(self.extractor, "rb") as extractor:
            self.extractor_sha.update(extractor.read())
        self.extractor_sha = self.extractor_sha.hexdigest()

        self.url = ""
        base_url = self.config["base_url"].as_str()
        if base_url:
            if not base_url.startswith("http"):
                raise ui.UserError(
                    "AcousticBrainz server base URL must start "
                    "with an HTTP scheme"
                )
            elif base_url[-1] != "/":
                base_url = base_url + "/"
            self.url = base_url + "{mbid}/low-level"

    def commands(self):
        cmd = ui.Subcommand(
            "absubmit", help="calculate and submit AcousticBrainz analysis"
        )
        cmd.parser.add_option(
            "-f",
            "--force",
            dest="force_refetch",
            action="store_true",
            default=False,
            help="re-download data when already present",
        )
        cmd.parser.add_option(
            "-p",
            "--pretend",
            dest="pretend_fetch",
            action="store_true",
            default=False,
            help="pretend to perform action, but show \
only files which would be processed",
        )
        cmd.func = self.command
        return [cmd]

    def command(self, lib, opts, args):
        if not self.url:
            raise ui.UserError(
                "This plugin is deprecated since AcousticBrainz no longer "
                "accepts new submissions. See the base_url configuration "
                "option."
            )
        else:
            # Get items from arguments
            items = lib.items(ui.decargs(args))
            self.opts = opts
            util.par_map(self.analyze_submit, items)

    def analyze_submit(self, item):
        analysis = self._get_analysis(item)
        if analysis:
            self._submit_data(item, analysis)

    def _get_analysis(self, item):
        mbid = item["mb_trackid"]

        # Avoid re-analyzing files that already have AB data.
        if not self.opts.force_refetch and not self.config["force"]:
            if item.get(PROBE_FIELD):
                return None

        # If file has no MBID, skip it.
        if not mbid:
            self._log.info(
                "Not analysing {}, missing " "musicbrainz track id.", item
            )
            return None

        if self.opts.pretend_fetch or self.config["pretend"]:
            self._log.info("pretend action - extract item: {}", item)
            return None

        # Temporary file to save extractor output to, extractor only works
        # if an output file is given. Here we use a temporary file to copy
        # the data into a python object and then remove the file from the
        # system.
        tmp_file, filename = tempfile.mkstemp(suffix=".json")
        try:
            # Close the file, so the extractor can overwrite it.
            os.close(tmp_file)
            try:
                call([self.extractor, util.syspath(item.path), filename])
            except ABSubmitError as e:
                self._log.warning(
                    "Failed to analyse {item} for AcousticBrainz: {error}",
                    item=item,
                    error=e,
                )
                return None
            with open(filename) as tmp_file:
                analysis = json.load(tmp_file)
            # Add the hash to the output.
            analysis["metadata"]["version"]["essentia_build_sha"] = (
                self.extractor_sha
            )
            return analysis
        finally:
            try:
                os.remove(filename)
            except OSError as e:
                # ENOENT means file does not exist, just ignore this error.
                if e.errno != errno.ENOENT:
                    raise

    def _submit_data(self, item, data):
        mbid = item["mb_trackid"]
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            self.url.format(mbid=mbid),
            json=data,
            headers=headers,
            timeout=10,
        )
        # Test that request was successful and raise an error on failure.
        if response.status_code != 200:
            try:
                message = response.json()["message"]
            except (ValueError, KeyError) as e:
                message = f"unable to get error message: {e}"
            self._log.error(
                "Failed to submit AcousticBrainz analysis of {item}: "
                "{message}).",
                item=item,
                message=message,
            )
        else:
            self._log.debug(
                "Successfully submitted AcousticBrainz analysis " "for {}.",
                item,
            )
