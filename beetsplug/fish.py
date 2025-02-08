# This file is part of beets.
# Copyright 2015, winters jean-marie.
# Copyright 2020, Justin Mayer <https://justinmayer.com>
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

"""This plugin generates tab completions for Beets commands for the Fish shell
<https://fishshell.com/>, including completions for Beets commands, plugin
commands, and option flags. Also generated are completions for all the album
and track fields, suggesting for example `genre:` or `album:` when querying the
Beets database. Completions for the *values* of those fields are not generated
by default but can be added via the `-e` / `--extravalues` flag. For example:
`beet fish -e genre -e albumartist`
"""

import os
from operator import attrgetter

from beets import library, ui
from beets.plugins import BeetsPlugin
from beets.ui import commands

BL_NEED2 = """complete -c beet -n '__fish_beet_needs_command' {} {}\n"""
BL_USE3 = """complete -c beet -n '__fish_beet_using_command {}' {} {}\n"""
BL_SUBS = """complete -c beet -n '__fish_at_level {} ""' {}  {}\n"""
BL_EXTRA3 = """complete -c beet -n '__fish_beet_use_extra {}' {} {}\n"""

HEAD = """
function __fish_beet_needs_command
    set cmd (commandline -opc)
    if test (count $cmd) -eq 1
        return 0
    end
    return 1
end

function __fish_beet_using_command
    set cmd (commandline -opc)
    set needle (count $cmd)
    if test $needle -gt 1
        if begin test $argv[1] = $cmd[2];
            and not contains -- $cmd[$needle] $FIELDS; end
                return 0
        end
    end
    return 1
end

function __fish_beet_use_extra
    set cmd (commandline -opc)
    set needle (count $cmd)
    if test $argv[2]  = $cmd[$needle]
        return 0
    end
    return 1
end
"""


class FishPlugin(BeetsPlugin):
    def commands(self):
        cmd = ui.Subcommand("fish", help="generate Fish shell tab completions")
        cmd.func = self.run
        cmd.parser.add_option(
            "-f",
            "--noFields",
            action="store_true",
            default=False,
            help="omit album/track field completions",
        )
        cmd.parser.add_option(
            "-e",
            "--extravalues",
            action="append",
            type="choice",
            choices=library.Item.all_keys() + library.Album.all_keys(),
            help="include specified field *values* in completions",
        )
        cmd.parser.add_option(
            "-o",
            "--output",
            default="~/.config/fish/completions/beet.fish",
            help="where to save the script. default: "
            "~/.config/fish/completions",
        )
        return [cmd]

    def run(self, lib, opts, args):
        # Gather the commands from Beets core and its plugins.
        # Collect the album and track fields.
        # If specified, also collect the values for these fields.
        # Make a giant string of all the above, formatted in a way that
        # allows Fish to do tab completion for the `beet` command.

        completion_file_path = os.path.expanduser(opts.output)
        completion_dir = os.path.dirname(completion_file_path)

        if completion_dir != "":
            os.makedirs(completion_dir, exist_ok=True)

        nobasicfields = opts.noFields  # Do not complete for album/track fields
        extravalues = opts.extravalues  # e.g., Also complete artists names
        beetcmds = sorted(
            (commands.default_commands + commands.plugins.commands()),
            key=attrgetter("name"),
        )
        fields = sorted(set(library.Album.all_keys() + library.Item.all_keys()))
        # Collect commands, their aliases, and their help text
        cmd_names_help = []
        for cmd in beetcmds:
            names = list(cmd.aliases)
            names.append(cmd.name)
            for name in names:
                cmd_names_help.append((name, cmd.help))
        # Concatenate the string
        totstring = HEAD + "\n"
        totstring += get_cmds_list([name[0] for name in cmd_names_help])
        totstring += "" if nobasicfields else get_standard_fields(fields)
        totstring += get_extravalues(lib, extravalues) if extravalues else ""
        totstring += (
            "\n"
            + "# ====== {} =====".format("setup basic beet completion")
            + "\n" * 2
        )
        totstring += get_basic_beet_options()
        totstring += (
            "\n"
            + "# ====== {} =====".format(
                "setup field completion for subcommands"
            )
            + "\n"
        )
        totstring += get_subcommands(cmd_names_help, nobasicfields, extravalues)
        # Set up completion for all the command options
        totstring += get_all_commands(beetcmds)

        with open(completion_file_path, "w") as fish_file:
            fish_file.write(totstring)


def _escape(name):
    # Escape ? in fish
    if name == "?":
        name = "\\" + name
    return name


def get_cmds_list(cmds_names):
    # Make a list of all Beets core & plugin commands
    substr = ""
    substr += "set CMDS " + " ".join(cmds_names) + ("\n" * 2)
    return substr


def get_standard_fields(fields):
    # Make a list of album/track fields and append with ':'
    fields = (field + ":" for field in fields)
    substr = ""
    substr += "set FIELDS " + " ".join(fields) + ("\n" * 2)
    return substr


def get_extravalues(lib, extravalues):
    # Make a list of all values from an album/track field.
    # 'beet ls albumartist: <TAB>' yields completions for ABBA, Beatles, etc.
    word = ""
    values_set = get_set_of_values_for_field(lib, extravalues)
    for fld in extravalues:
        extraname = fld.upper() + "S"
        word += (
            "set  "
            + extraname
            + " "
            + " ".join(sorted(values_set[fld]))
            + ("\n" * 2)
        )
    return word


def get_set_of_values_for_field(lib, fields):
    # Get unique values from a specified album/track field
    fields_dict = {}
    for each in fields:
        fields_dict[each] = set()
    for item in lib.items():
        for field in fields:
            fields_dict[field].add(wrap(item[field]))
    return fields_dict


def get_basic_beet_options():
    word = (
        BL_NEED2.format("-l format-item", "-f -d 'print with custom format'")
        + BL_NEED2.format("-l format-album", "-f -d 'print with custom format'")
        + BL_NEED2.format(
            "-s  l  -l library", "-f -r -d 'library database file to use'"
        )
        + BL_NEED2.format(
            "-s  d  -l directory", "-f -r -d 'destination music directory'"
        )
        + BL_NEED2.format(
            "-s  v  -l verbose", "-f -d 'print debugging information'"
        )
        + BL_NEED2.format(
            "-s  c  -l config", "-f -r -d 'path to configuration file'"
        )
        + BL_NEED2.format(
            "-s  h  -l help", "-f -d 'print this help message and exit'"
        )
    )
    return word


def get_subcommands(cmd_name_and_help, nobasicfields, extravalues):
    # Formatting for Fish to complete our fields/values
    word = ""
    for cmdname, cmdhelp in cmd_name_and_help:
        cmdname = _escape(cmdname)

        word += (
            "\n"
            + "# ------ {} -------".format("fieldsetups for  " + cmdname)
            + "\n"
        )
        word += BL_NEED2.format(
            ("-a " + cmdname), ("-f " + "-d " + wrap(clean_whitespace(cmdhelp)))
        )

        if nobasicfields is False:
            word += BL_USE3.format(
                cmdname,
                ("-a " + wrap("$FIELDS")),
                ("-f " + "-d " + wrap("fieldname")),
            )

        if extravalues:
            for f in extravalues:
                setvar = wrap("$" + f.upper() + "S")
                word += (
                    " ".join(
                        BL_EXTRA3.format(
                            (cmdname + " " + f + ":"),
                            ("-f " + "-A " + "-a " + setvar),
                            ("-d " + wrap(f)),
                        ).split()
                    )
                    + "\n"
                )
    return word


def get_all_commands(beetcmds):
    # Formatting for Fish to complete command options
    word = ""
    for cmd in beetcmds:
        names = list(cmd.aliases)
        names.append(cmd.name)
        for name in names:
            name = _escape(name)

            word += "\n"
            word += (
                ("\n" * 2)
                + "# ====== {} =====".format("completions for  " + name)
                + "\n"
            )

            for option in cmd.parser._get_all_options()[1:]:
                cmd_l = (
                    (" -l " + option._long_opts[0].replace("--", ""))
                    if option._long_opts
                    else ""
                )
                cmd_s = (
                    (" -s " + option._short_opts[0].replace("-", ""))
                    if option._short_opts
                    else ""
                )
                cmd_need_arg = " -r " if option.nargs in [1] else ""
                cmd_helpstr = (
                    (" -d " + wrap(" ".join(option.help.split())))
                    if option.help
                    else ""
                )
                cmd_arglist = (
                    (" -a " + wrap(" ".join(option.choices)))
                    if option.choices
                    else ""
                )

                word += (
                    " ".join(
                        BL_USE3.format(
                            name,
                            (
                                cmd_need_arg
                                + cmd_s
                                + cmd_l
                                + " -f "
                                + cmd_arglist
                            ),
                            cmd_helpstr,
                        ).split()
                    )
                    + "\n"
                )

            word = word + " ".join(
                BL_USE3.format(
                    name,
                    ("-s " + "h " + "-l " + "help" + " -f "),
                    ("-d " + wrap("print help") + "\n"),
                ).split()
            )
    return word


def clean_whitespace(word):
    # Remove excess whitespace and tabs in a string
    return " ".join(word.split())


def wrap(word):
    # Need " or ' around strings but watch out if they're in the string
    sptoken = '"'
    if ('"') in word and ("'") in word:
        word.replace('"', sptoken)
        return '"' + word + '"'

    tok = '"' if "'" in word else "'"
    return tok + word + tok
