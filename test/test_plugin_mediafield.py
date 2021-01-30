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

"""Tests the facility that lets plugins add custom field to MediaFile.
"""
from __future__ import division, absolute_import, print_function

import os
import six
import shutil
import unittest

from test import _common
from beets.library import Item
import mediafile
from beets.plugins import BeetsPlugin
from beets.util import bytestring_path, syspath


field_extension = mediafile.MediaField(
    mediafile.MP3DescStorageStyle(u'customtag'),
    mediafile.MP4StorageStyle('----:com.apple.iTunes:customtag'),
    mediafile.StorageStyle('customtag'),
    mediafile.ASFStorageStyle('customtag'),
)


class ExtendedFieldTestMixin(_common.TestCase):

    def _mediafile_fixture(self, name, extension='mp3'):
        name = bytestring_path(name + '.' + extension)
        src = os.path.join(_common.RSRC, name)
        target = os.path.join(self.temp_dir, name)
        shutil.copy(syspath(src), syspath(target))
        return mediafile.MediaFile(target)

    def test_extended_field_write(self):
        plugin = BeetsPlugin()
        plugin.add_media_field('customtag', field_extension)

        try:
            mf = self._mediafile_fixture('empty')
            mf.customtag = u'F#'
            mf.save()

            mf = mediafile.MediaFile(mf.path)
            self.assertEqual(mf.customtag, u'F#')

        finally:
            delattr(mediafile.MediaFile, 'customtag')
            Item._media_fields.remove('customtag')

    def test_write_extended_tag_from_item(self):
        plugin = BeetsPlugin()
        plugin.add_media_field('customtag', field_extension)

        try:
            mf = self._mediafile_fixture('empty')
            self.assertIsNone(mf.customtag)

            item = Item(path=mf.path, customtag=u'Gb')
            item.write()
            mf = mediafile.MediaFile(mf.path)
            self.assertEqual(mf.customtag, u'Gb')

        finally:
            delattr(mediafile.MediaFile, 'customtag')
            Item._media_fields.remove('customtag')

    def test_read_flexible_attribute_from_file(self):
        plugin = BeetsPlugin()
        plugin.add_media_field('customtag', field_extension)

        try:
            mf = self._mediafile_fixture('empty')
            mf.update({'customtag': u'F#'})
            mf.save()

            item = Item.from_path(mf.path)
            self.assertEqual(item['customtag'], u'F#')

        finally:
            delattr(mediafile.MediaFile, 'customtag')
            Item._media_fields.remove('customtag')

    def test_invalid_descriptor(self):
        with self.assertRaises(ValueError) as cm:
            mediafile.MediaFile.add_field('somekey', True)
        self.assertIn(u'must be an instance of MediaField',
                      six.text_type(cm.exception))

    def test_overwrite_property(self):
        with self.assertRaises(ValueError) as cm:
            mediafile.MediaFile.add_field('artist', mediafile.MediaField())
        self.assertIn(u'property "artist" already exists',
                      six.text_type(cm.exception))


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
