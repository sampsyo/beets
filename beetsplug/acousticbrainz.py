# This file is part of beets.
# Copyright 2015-2016, Ohm Patel.
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

"""Fetch various AcousticBrainz metadata using MBID."""

from collections import defaultdict

import requests

from beets import plugins, ui
from beets.dbcore import types

LEVELS = ["/low-level", "/high-level"]
ABSCHEME = {
    "highlevel": {
        "danceability": {"all": {"danceable": "danceable"}},
        "gender": {"value": "gender"},
        "genre_rosamerica": {"value": "genre_rosamerica"},
        "mood_acoustic": {"all": {"acoustic": "mood_acoustic"}},
        "mood_aggressive": {"all": {"aggressive": "mood_aggressive"}},
        "mood_electronic": {"all": {"electronic": "mood_electronic"}},
        "mood_happy": {"all": {"happy": "mood_happy"}},
        "mood_party": {"all": {"party": "mood_party"}},
        "mood_relaxed": {"all": {"relaxed": "mood_relaxed"}},
        "mood_sad": {"all": {"sad": "mood_sad"}},
        "moods_mirex": {"value": "moods_mirex"},
        "ismir04_rhythm": {"value": "rhythm"},
        "tonal_atonal": {"all": {"tonal": "tonal"}},
        "timbre": {"value": "timbre"},
        "voice_instrumental": {"value": "voice_instrumental"},
    },
    "lowlevel": {"average_loudness": "average_loudness"},
    "rhythm": {"bpm": "bpm"},
    "tonal": {
        "chords_changes_rate": "chords_changes_rate",
        "chords_key": "chords_key",
        "chords_number_rate": "chords_number_rate",
        "chords_scale": "chords_scale",
        "key_key": ("initial_key", 0),
        "key_scale": ("initial_key", 1),
        "key_strength": "key_strength",
    },
}


class AcousticPlugin(plugins.BeetsPlugin):
    item_types = {
        "average_loudness": types.Float(6),
        "chords_changes_rate": types.Float(6),
        "chords_key": types.STRING,
        "chords_number_rate": types.Float(6),
        "chords_scale": types.STRING,
        "danceable": types.Float(6),
        "gender": types.STRING,
        "genre_rosamerica": types.STRING,
        "initial_key": types.STRING,
        "key_strength": types.Float(6),
        "mood_acoustic": types.Float(6),
        "mood_aggressive": types.Float(6),
        "mood_electronic": types.Float(6),
        "mood_happy": types.Float(6),
        "mood_party": types.Float(6),
        "mood_relaxed": types.Float(6),
        "mood_sad": types.Float(6),
        "moods_mirex": types.STRING,
        "rhythm": types.Float(6),
        "timbre": types.STRING,
        "tonal": types.Float(6),
        "voice_instrumental": types.STRING,
    }

    def __init__(self):
        super().__init__()

        self._log.warning("This plugin is deprecated.")

        self.config.add(
            {"auto": True, "force": False, "tags": [], "base_url": ""}
        )

        self.base_url = self.config["base_url"].as_str()
        if self.base_url:
            if not self.base_url.startswith("http"):
                raise ui.UserError(
                    "AcousticBrainz server base URL must start "
                    "with an HTTP scheme"
                )
            elif self.base_url[-1] != "/":
                self.base_url = self.base_url + "/"

        if self.config["auto"]:
            self.register_listener("import_task_files", self.import_task_files)

    def commands(self):
        cmd = ui.Subcommand(
            "acousticbrainz", help="fetch metadata from AcousticBrainz"
        )
        cmd.parser.add_option(
            "-f",
            "--force",
            dest="force_refetch",
            action="store_true",
            default=False,
            help="re-download data when already present",
        )

        def func(lib, opts, args):
            items = lib.items(ui.decargs(args))
            self._fetch_info(
                items,
                ui.should_write(),
                opts.force_refetch or self.config["force"],
            )

        cmd.func = func
        return [cmd]

    def import_task_files(self, session, task):
        """Function is called upon beet import."""
        self._fetch_info(task.imported_items(), False, True)

    def _get_data(self, mbid):
        if not self.base_url:
            raise ui.UserError(
                "This plugin is deprecated since AcousticBrainz has shut "
                "down. See the base_url configuration option."
            )
        data = {}
        for url in _generate_urls(self.base_url, mbid):
            self._log.debug("fetching URL: {}", url)

            try:
                res = requests.get(url, timeout=10)
            except requests.RequestException as exc:
                self._log.info("request error: {}", exc)
                return {}

            if res.status_code == 404:
                self._log.info("recording ID {} not found", mbid)
                return {}

            try:
                data.update(res.json())
            except ValueError:
                self._log.debug("Invalid Response: {}", res.text)
                return {}

        return data

    def _fetch_info(self, items, write, force):
        """Fetch additional information from AcousticBrainz for the `item`s."""
        tags = self.config["tags"].as_str_seq()
        for item in items:
            # If we're not forcing re-downloading for all tracks, check
            # whether the data is already present. We use one
            # representative field name to check for previously fetched
            # data.
            if not force:
                mood_str = item.get("mood_acoustic", "")
                if mood_str:
                    self._log.info("data already present for: {}", item)
                    continue

            # We can only fetch data for tracks with MBIDs.
            if not item.mb_trackid:
                continue

            self._log.info("getting data for: {}", item)
            data = self._get_data(item.mb_trackid)
            if data:
                for attr, val in self._map_data_to_scheme(data, ABSCHEME):
                    if not tags or attr in tags:
                        self._log.debug(
                            "attribute {} of {} set to {}", attr, item, val
                        )
                        setattr(item, attr, val)
                    else:
                        self._log.debug(
                            "skipping attribute {} of {}"
                            " (value {}) due to config",
                            attr,
                            item,
                            val,
                        )
                item.store()
                if write:
                    item.try_write()

    def _map_data_to_scheme(self, data, scheme):
        """Given `data` as a structure of nested dictionaries, and
        `scheme` as a structure of nested dictionaries , `yield` tuples
        `(attr, val)` where `attr` and `val` are corresponding leaf
        nodes in `scheme` and `data`.

        As its name indicates, `scheme` defines how the data is structured,
        so this function tries to find leaf nodes in `data` that correspond
        to the leafs nodes of `scheme`, and not the other way around.
        Leaf nodes of `data` that do not exist in the `scheme` do not matter.
        If a leaf node of `scheme` is not present in `data`,
        no value is yielded for that attribute and a simple warning is issued.

        Finally, to account for attributes of which the value is split between
        several leaf nodes in `data`, leaf nodes of `scheme` can be tuples
        `(attr, order)` where `attr` is the attribute to which the leaf node
        belongs, and `order` is the place at which it should appear in the
        value. The different `value`s belonging to the same `attr` are simply
        joined with `' '`. This is hardcoded and not very flexible, but it gets
        the job done.

        For example:

        >>> scheme = {
            'key1': 'attribute',
            'key group': {
                'subkey1': 'subattribute',
                'subkey2': ('composite attribute', 0)
            },
            'key2': ('composite attribute', 1)
        }
        >>> data = {
            'key1': 'value',
            'key group': {
                'subkey1': 'subvalue',
                'subkey2': 'part 1 of composite attr'
            },
            'key2': 'part 2'
        }
        >>> print(list(_map_data_to_scheme(data, scheme)))
        [('subattribute', 'subvalue'),
         ('attribute', 'value'),
         ('composite attribute', 'part 1 of composite attr part 2')]
        """
        # First, we traverse `scheme` and `data`, `yield`ing all the non
        # composites attributes straight away and populating the dictionary
        # `composites` with the composite attributes.

        # When we are finished traversing `scheme`, `composites` should
        # map each composite attribute to an ordered list of the values
        # belonging to the attribute, for example:
        # `composites = {'initial_key': ['B', 'minor']}`.

        # The recursive traversal.
        composites = defaultdict(list)
        yield from self._data_to_scheme_child(data, scheme, composites)

        # When composites has been populated, yield the composite attributes
        # by joining their parts.
        for composite_attr, value_parts in composites.items():
            yield composite_attr, " ".join(value_parts)

    def _data_to_scheme_child(self, subdata, subscheme, composites):
        """The recursive business logic of :meth:`_map_data_to_scheme`:
        Traverse two structures of nested dictionaries in parallel and `yield`
        tuples of corresponding leaf nodes.

        If a leaf node belongs to a composite attribute (is a `tuple`),
        populate `composites` rather than yielding straight away.
        All the child functions for a single traversal share the same
        `composites` instance, which is passed along.
        """
        for k, v in subscheme.items():
            if k in subdata:
                if isinstance(v, dict):
                    yield from self._data_to_scheme_child(
                        subdata[k], v, composites
                    )
                elif isinstance(v, tuple):
                    composite_attribute, part_number = v
                    attribute_parts = composites[composite_attribute]
                    # Parts are not guaranteed to be inserted in order
                    while len(attribute_parts) <= part_number:
                        attribute_parts.append("")
                    attribute_parts[part_number] = subdata[k]
                else:
                    yield v, subdata[k]
            else:
                self._log.warning(
                    "Acousticbrainz did not provide info " "about {}", k
                )
                self._log.debug(
                    "Data {} could not be mapped to scheme {} "
                    "because key {} was not found",
                    subdata,
                    v,
                    k,
                )


def _generate_urls(base_url, mbid):
    """Generates AcousticBrainz end point urls for given `mbid`."""
    for level in LEVELS:
        yield base_url + mbid + level
