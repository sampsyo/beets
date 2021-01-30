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

"""Test module for file ui/commands.py
"""

from __future__ import division, absolute_import, print_function

import os
import shutil
import unittest

from test import _common

from beets import library
from beets import ui
from beets.ui import commands
from beets.util import syspath


class QueryTest(_common.TestCase):
    def setUp(self):
        super(QueryTest, self).setUp()

        self.libdir = os.path.join(self.temp_dir, b'testlibdir')
        os.mkdir(syspath(self.libdir))

        # Add a file to the library but don't copy it in yet.
        self.lib = library.Library(':memory:', self.libdir)

        # Alternate destination directory.
        self.otherdir = os.path.join(self.temp_dir, b'testotherdir')

    def add_item(self, filename=b'srcfile', templatefile=b'full.mp3'):
        itempath = os.path.join(self.libdir, filename)
        shutil.copy(
            syspath(os.path.join(_common.RSRC, templatefile)),
            syspath(itempath),
        )
        item = library.Item.from_path(itempath)
        self.lib.add(item)
        return item, itempath

    def add_album(self, items):
        album = self.lib.add_album(items)
        return album

    def check_do_query(self, num_items, num_albums,
                       q=(), album=False, also_items=True):
        items, albums = commands._do_query(
            self.lib, q, album, also_items)
        self.assertEqual(len(items), num_items)
        self.assertEqual(len(albums), num_albums)

    def test_query_empty(self):
        with self.assertRaises(ui.UserError):
            commands._do_query(self.lib, (), False)

    def test_query_empty_album(self):
        with self.assertRaises(ui.UserError):
            commands._do_query(self.lib, (), True)

    def test_query_item(self):
        self.add_item()
        self.check_do_query(1, 0, album=False)
        self.add_item()
        self.check_do_query(2, 0, album=False)

    def test_query_album(self):
        item, itempath = self.add_item()
        self.add_album([item])
        self.check_do_query(1, 1, album=True)
        self.check_do_query(0, 1, album=True, also_items=False)

        item, itempath = self.add_item()
        item2, itempath = self.add_item()
        self.add_album([item, item2])
        self.check_do_query(3, 2, album=True)
        self.check_do_query(0, 2, album=True, also_items=False)


class FieldsTest(_common.LibTestCase):
    def setUp(self):
        super(FieldsTest, self).setUp()

        self.io.install()

    def tearDown(self):
        self.io.restore()

    def remove_keys(self, l, text):
        for i in text:
            try:
                l.remove(i)
            except ValueError:
                pass

    def test_fields_func(self):
        commands.fields_func(self.lib, [], [])
        items = library.Item.all_keys()
        albums = library.Album.all_keys()

        output = self.io.stdout.get().split()
        self.remove_keys(items, output)
        self.remove_keys(albums, output)

        self.assertEqual(len(items), 0)
        self.assertEqual(len(albums), 0)


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
