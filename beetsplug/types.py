# This file is part of beets.
# Copyright 2016, Thomas Scholtes.
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


from confuse import ConfigValueError

from beets import library
from beets.dbcore import types
from beets.plugins import BeetsPlugin


class TypesPlugin(BeetsPlugin):
    @property
    def item_types(self):
        return self._types()

    @property
    def album_types(self):
        return self._types()

    def _types(self):
        if not self.config.exists():
            return {}

        mytypes = {}
        for key, value in self.config.items():
            if value.get() == "int":
                mytypes[key] = types.INTEGER
            elif value.get() == "float":
                mytypes[key] = types.FLOAT
            elif value.get() == "bool":
                mytypes[key] = types.BOOLEAN
            elif value.get() == "date":
                mytypes[key] = library.DateType()
            else:
                raise ConfigValueError(
                    f"unknown type '{value}' for the '{key}' field"
                )
        return mytypes
