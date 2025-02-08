# This file is part of beets.
# Copyright 2023, Daniele Ferone.
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

"""The substitute plugin module.

Uses user-specified substitution rules to canonicalize names for path formats.
"""

import re

from beets.plugins import BeetsPlugin


class Substitute(BeetsPlugin):
    """The substitute plugin class.

    Create a template field function that substitute the given field with the
    given substitution rules. ``rules`` must be a list of (pattern,
    replacement) pairs.
    """

    def tmpl_substitute(self, text):
        """Do the actual replacing."""
        if text:
            for pattern, replacement in self.substitute_rules:
                text = pattern.sub(replacement, text)
            return text
        else:
            return ""

    def __init__(self):
        """Initialize the substitute plugin.

        Get the configuration, register template function and create list of
        substitute rules.
        """
        super().__init__()
        self.template_funcs["substitute"] = self.tmpl_substitute
        self.substitute_rules = [
            (re.compile(key, flags=re.IGNORECASE), value)
            for key, value in self.config.flatten().items()
        ]
