# This file is part of beets.
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

"""Exports data from beets"""

import codecs
import csv
import json
import sys
from datetime import date, datetime
from xml.etree import ElementTree

import mediafile

from beets import ui, util
from beets.plugins import BeetsPlugin
from beetsplug.info import library_data, tag_data


class ExportEncoder(json.JSONEncoder):
    """Deals with dates because JSON doesn't have a standard"""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


class ExportPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()

        self.config.add(
            {
                "default_format": "json",
                "json": {
                    # JSON module formatting options.
                    "formatting": {
                        "ensure_ascii": False,
                        "indent": 4,
                        "separators": (",", ": "),
                        "sort_keys": True,
                    }
                },
                "jsonlines": {
                    # JSON Lines formatting options.
                    "formatting": {
                        "ensure_ascii": False,
                        "separators": (",", ": "),
                        "sort_keys": True,
                    }
                },
                "csv": {
                    # CSV module formatting options.
                    "formatting": {
                        # The delimiter used to separate columns.
                        "delimiter": ",",
                        # The dialect to use when formatting the file output.
                        "dialect": "excel",
                    }
                },
                "xml": {
                    # XML module formatting options.
                    "formatting": {}
                },
                # TODO: Use something like the edit plugin
                # 'item_fields': []
            }
        )

    def commands(self):
        cmd = ui.Subcommand("export", help="export data from beets")
        cmd.func = self.run
        cmd.parser.add_option(
            "-l",
            "--library",
            action="store_true",
            help="show library fields instead of tags",
        )
        cmd.parser.add_option(
            "-a",
            "--album",
            action="store_true",
            help='show album fields instead of tracks (implies "--library")',
        )
        cmd.parser.add_option(
            "--append",
            action="store_true",
            default=False,
            help="if should append data to the file",
        )
        cmd.parser.add_option(
            "-i",
            "--include-keys",
            default=[],
            action="append",
            dest="included_keys",
            help="comma separated list of keys to show",
        )
        cmd.parser.add_option(
            "-o",
            "--output",
            help="path for the output file. If not given, will print the data",
        )
        cmd.parser.add_option(
            "-f",
            "--format",
            default="json",
            help="the output format: json (default), jsonlines, csv, or xml",
        )
        return [cmd]

    def run(self, lib, opts, args):
        file_path = opts.output
        file_mode = "a" if opts.append else "w"
        file_format = opts.format or self.config["default_format"].get(str)
        file_format_is_line_based = file_format == "jsonlines"
        format_options = self.config[file_format]["formatting"].get(dict)

        export_format = ExportFormat.factory(
            file_type=file_format,
            **{"file_path": file_path, "file_mode": file_mode},
        )

        if opts.library or opts.album:
            data_collector = library_data
        else:
            data_collector = tag_data

        included_keys = []
        for keys in opts.included_keys:
            included_keys.extend(keys.split(","))

        items = []
        for data_emitter in data_collector(
            lib,
            ui.decargs(args),
            album=opts.album,
        ):
            try:
                data, item = data_emitter(included_keys or "*")
            except (mediafile.UnreadableFileError, OSError) as ex:
                self._log.error("cannot read file: {0}", ex)
                continue

            for key, value in data.items():
                if isinstance(value, bytes):
                    data[key] = util.displayable_path(value)

            if file_format_is_line_based:
                export_format.export(data, **format_options)
            else:
                items += [data]

        if not file_format_is_line_based:
            export_format.export(items, **format_options)


class ExportFormat:
    """The output format type"""

    def __init__(self, file_path, file_mode="w", encoding="utf-8"):
        self.path = file_path
        self.mode = file_mode
        self.encoding = encoding
        # creates a file object to write/append or sets to stdout
        self.out_stream = (
            codecs.open(self.path, self.mode, self.encoding)
            if self.path
            else sys.stdout
        )

    @classmethod
    def factory(cls, file_type, **kwargs):
        if file_type in ["json", "jsonlines"]:
            return JsonFormat(**kwargs)
        elif file_type == "csv":
            return CSVFormat(**kwargs)
        elif file_type == "xml":
            return XMLFormat(**kwargs)
        else:
            raise NotImplementedError()

    def export(self, data, **kwargs):
        raise NotImplementedError()


class JsonFormat(ExportFormat):
    """Saves in a json file"""

    def __init__(self, file_path, file_mode="w", encoding="utf-8"):
        super().__init__(file_path, file_mode, encoding)

    def export(self, data, **kwargs):
        json.dump(data, self.out_stream, cls=ExportEncoder, **kwargs)
        self.out_stream.write("\n")


class CSVFormat(ExportFormat):
    """Saves in a csv file"""

    def __init__(self, file_path, file_mode="w", encoding="utf-8"):
        super().__init__(file_path, file_mode, encoding)

    def export(self, data, **kwargs):
        header = list(data[0].keys()) if data else []
        writer = csv.DictWriter(self.out_stream, fieldnames=header, **kwargs)
        writer.writeheader()
        writer.writerows(data)


class XMLFormat(ExportFormat):
    """Saves in a xml file"""

    def __init__(self, file_path, file_mode="w", encoding="utf-8"):
        super().__init__(file_path, file_mode, encoding)

    def export(self, data, **kwargs):
        # Creates the XML file structure.
        library = ElementTree.Element("library")
        tracks = ElementTree.SubElement(library, "tracks")
        if data and isinstance(data[0], dict):
            for index, item in enumerate(data):
                track = ElementTree.SubElement(tracks, "track")
                for key, value in item.items():
                    track_details = ElementTree.SubElement(track, key)
                    track_details.text = value
        # Depending on the version of python the encoding needs to change
        try:
            data = ElementTree.tostring(library, encoding="unicode", **kwargs)
        except LookupError:
            data = ElementTree.tostring(library, encoding="utf-8", **kwargs)

        self.out_stream.write(data)
