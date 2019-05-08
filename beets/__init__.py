# -*- coding: utf-8 -*-
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

from __future__ import division, absolute_import, print_function

import os

from beets.util import confit

__version__ = u'1.4.8'
__author__ = u'Adrian Sampson <adrian@radbox.org>'


class IncludeLazyConfig(confit.LazyConfig):
    """A version of Confit's LazyConfig that also merges in data from
    YAML files specified in an `include` setting.
    """
    def __init__(self, *args, **kwargs):
        super(IncludeLazyConfig, self).__init__(*args, **kwargs)

        self._included_files = []

    def user_config_paths(self):
        """Points to a list of locations making up the user configuration.

        The files may not exist.
        """
        return [self.user_config_path()] + self._included_files

    def read(self, user=True, defaults=True):
        super(IncludeLazyConfig, self).read(user, defaults)

        try:
            for view in self['include']:
                filename = view.as_filename()
                self._included_files.append(filename)

                if os.path.isfile(filename):
                    self.set_file(filename)
        except confit.NotFoundError:
            pass


config = IncludeLazyConfig('beets', __name__)
