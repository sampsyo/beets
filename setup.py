#!/usr/bin/env python
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
import sys
import subprocess
import shutil
from setuptools import setup


def _read(fn):
    path = os.path.join(os.path.dirname(__file__), fn)
    return open(path).read()


def build_manpages():
    # Go into the docs directory and build the manpage.
    docdir = os.path.join(os.path.dirname(__file__), 'docs')
    curdir = os.getcwd()
    os.chdir(docdir)
    try:
        subprocess.check_call(['make', 'man'])
    except OSError:
        print("Could not build manpages (make man failed)!", file=sys.stderr)
        return
    finally:
        os.chdir(curdir)

    # Copy resulting manpages.
    mandir = os.path.join(os.path.dirname(__file__), 'man')
    if os.path.exists(mandir):
        shutil.rmtree(mandir)
    shutil.copytree(os.path.join(docdir, '_build', 'man'), mandir)


# Build manpages if we're making a source distribution tarball.
if 'sdist' in sys.argv:
    build_manpages()


setup(
    name='beets',
    version='1.5.0',
    description='music tagger and library organizer',
    author='Adrian Sampson',
    author_email='adrian@radbox.org',
    url='https://beets.io/',
    license='MIT',
    platforms='ALL',
    long_description=_read('README.rst'),
    test_suite='test.testall.suite',
    zip_safe=False,
    include_package_data=True,  # Install plugin resources.

    packages=[
        'beets',
        'beets.ui',
        'beets.autotag',
        'beets.util',
        'beets.dbcore',
        'beetsplug',
        'beetsplug.bpd',
        'beetsplug.web',
        'beetsplug.lastgenre',
        'beetsplug.metasync',
    ],
    entry_points={
        'console_scripts': [
            'beet = beets.ui:main',
        ],
    },

    install_requires=[
        'six>=1.9',
        'unidecode',
        'musicbrainzngs>=0.4',
        'pyyaml',
        'mediafile>=0.2.0',
        'confuse>=1.0.0',
    ] + [
        # Avoid a version of munkres incompatible with Python 3.
        'munkres~=1.0.0' if sys.version_info < (3, 5, 0) else
        'munkres!=1.1.0,!=1.1.1' if sys.version_info < (3, 6, 0) else
        'munkres>=1.0.0',
    ] + (
        # Use the backport of Python 3.4's `enum` module.
        ['enum34>=1.0.4'] if sys.version_info < (3, 4, 0) else []
    ) + (
        # Pin a Python 2-compatible version of Jellyfish.
        ['jellyfish==0.6.0'] if sys.version_info < (3, 4, 0) else ['jellyfish']
    ) + (
        # Support for ANSI console colors on Windows.
        ['colorama'] if (sys.platform == 'win32') else []
    ) + (
            ['futures'] if sys.version_info[:2] == (2, 7) else []
    ),

    extras_require={
        'test': [
            'beautifulsoup4',
            'coverage',
            'flask',
            'mock',
            'pylast',
            'pytest',
            'pytest-timeout',
            'python-mpd2',
            'pyxdg',
            'responses>=0.3.0',
            'requests_oauthlib',
            'reflink',
        ] + (
            # Tests for the thumbnails plugin need pathlib on Python 2 too.
            ['pathlib'] if (sys.version_info < (3, 4, 0)) else []
        ) + [
            'rarfile<4' if sys.version_info < (3, 6, 0) else 'rarfile',
        ] + [
            'discogs-client' if (sys.version_info < (3, 0, 0))
            else 'python3-discogs-client'
        ],
        'lint': [
            'flake8',
            'flake8-coding',
            'flake8-docstrings',
            'flake8-future-import',
            'pep8-naming',
        ],

        # Plugin (optional) dependencies:
        'absubmit': ['requests'],
        'fetchart': ['requests', 'Pillow'],
        'embedart': ['Pillow'],
        'embyupdate': ['requests'],
        'chroma': ['pyacoustid'],
        'gmusic': ['gmusicapi'],
        'discogs': (
            ['discogs-client' if (sys.version_info < (3, 0, 0))
                else 'python3-discogs-client']
        ),
        'beatport': ['requests-oauthlib>=0.6.1'],
        'kodiupdate': ['requests'],
        'lastgenre': ['pylast'],
        'lastimport': ['pylast'],
        'lyrics': ['requests', 'beautifulsoup4', 'langdetect'],
        'mpdstats': ['python-mpd2>=0.4.2'],
        'plexupdate': ['requests'],
        'web': ['flask', 'flask-cors'],
        'import': (
            ['rarfile<4' if (sys.version_info < (3, 6, 0)) else 'rarfile']
        ),
        'thumbnails': ['pyxdg', 'Pillow'] +
        (['pathlib'] if (sys.version_info < (3, 4, 0)) else []),
        'metasync': ['dbus-python'],
        'sonosupdate': ['soco'],
        'scrub': ['mutagen>=1.33'],
        'bpd': ['PyGObject'],
        'replaygain': ['PyGObject'],
        'reflink': ['reflink'],
    },
    # Non-Python/non-PyPI plugin dependencies:
    #   chroma: chromaprint or fpcalc
    #   convert: ffmpeg
    #   badfiles: mp3val and flac
    #   bpd: python-gi and GStreamer 1.0+
    #   embedart: ImageMagick
    #   absubmit: extractor binary from https://acousticbrainz.org/download
    #   keyfinder: KeyFinder
    #   replaygain: python-gi and GStreamer 1.0+
    #               or mp3gain/aacgain
    #               or Python Audio Tools
    #               or ffmpeg
    #   ipfs: go-ipfs

    classifiers=[
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Multimedia :: Sound/Audio :: Players :: MP3',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
)
