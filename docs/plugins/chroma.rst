Chromaprint/Acoustid Plugin
===========================

Acoustic fingerprinting is a technique for identifying songs from the way they
"sound" rather from their existing metadata. That means that beets' autotagger
can theoretically use fingerprinting to tag files that don't have any ID3
information at all (or have completely incorrect data).  This plugin uses an
open-source fingerprinting technology called `Chromaprint`_ and its associated
Web service, called `Acoustid`_.

.. _Chromaprint: https://acoustid.org/chromaprint
.. _acoustid: https://acoustid.org/

Turning on fingerprinting can increase the accuracy of the
autotagger---especially on files with very poor metadata---but it comes at a
cost. First, it can be trickier to set up than beets itself (you need to set up
the native fingerprinting library, whereas all of the beets core is written in
pure Python).  Also, fingerprinting takes significantly more CPU and memory than
ordinary tagging---which means that imports will go substantially slower.

If you're willing to pay the performance cost for fingerprinting, read on!

Installing Dependencies
-----------------------

To get fingerprinting working, you'll need to install three things: 

1. `pyacoustid`_ Python library (version 0.6 or later). You can install it by
   installing ``beets`` with ``chroma`` extra

.. code-block:: bash

    pip install "beets[chroma]"

2. the `Chromaprint`_ library_ or |command-line-tool|_
3. an |audio-decoder|_

.. |command-line-tool| replace:: command line tool
.. |audio-decoder| replace:: audio decoder


.. _command-line-tool:

Installing the Binary Command-Line Tool
'''''''''''''''''''''''''''''''''''''''

The simplest way to get up and running, especially on Windows, is to
`download`_ the appropriate Chromaprint binary package and place the
``fpcalc`` (or ``fpcalc.exe``) on your shell search path. On Windows, this
means something like ``C:\\Program Files``. On OS X or Linux, put the
executable somewhere like ``/usr/local/bin``.

.. _download: https://acoustid.org/chromaprint

.. _library:

Installing the Library
''''''''''''''''''''''

On OS X and Linux, you can also use a library installed by your package
manager, which has some advantages (automatic upgrades, etc.). The Chromaprint
site has links to packages for major Linux distributions. If you use
`Homebrew`_ on Mac OS X, you can install the library with ``brew install
chromaprint``.

.. _Homebrew: https://brew.sh/

.. _audio-decoder:

Audio Decoder
'''''''''''''

You will also need a mechanism for decoding audio files supported by the
`audioread`_ library:

* OS X has a number of decoders already built into Core Audio, so there's no
  need to install anything.

* On Linux, you can install `GStreamer`_ with `PyGObject`_, `FFmpeg`_, or
  `MAD`_ with `pymad`_. How you install these will depend on your
  distribution.
  For example, on Ubuntu, run ``apt-get install gstreamer1.0 python-gi``. On
  Arch Linux, you want ``pacman -S gstreamer python2-gobject``. If you use
  GStreamer, be sure to install its codec plugins also (``gst-plugins-good``,
  etc.).

  Note that if you install beets in a virtualenv, you'll need it to have
  ``--system-site-packages`` enabled for Python to see the GStreamer bindings.

* On Windows, builds are provided by `GStreamer`_

.. _audioread: https://github.com/beetbox/audioread
.. _pyacoustid: https://github.com/beetbox/pyacoustid
.. _FFmpeg: https://ffmpeg.org/
.. _pymad: https://spacepants.org/src/pymad/
.. _MAD: https://www.underbit.com/products/mad/
.. _Core Audio: https://developer.apple.com/technologies/mac/audio-and-video.html
.. _Gstreamer: https://gstreamer.freedesktop.org/
.. _PyGObject: https://wiki.gnome.org/Projects/PyGObject

To decode audio formats (MP3, FLAC, etc.) with GStreamer, you'll need the
standard set of Gstreamer plugins. For example, on Ubuntu, install the packages
``gstreamer1.0-plugins-good``, ``gstreamer1.0-plugins-bad``, and
``gstreamer1.0-plugins-ugly``.

Usage
-----

Once you have all the dependencies sorted out, enable the ``chroma`` plugin in
your configuration (see :ref:`using-plugins`) to benefit from fingerprinting
the next time you run ``beet import``. (The plugin doesn't produce any obvious
output by default. If you want to confirm that it's enabled, you can try
running in verbose mode once with ``beet -v import``.)

You can also use the ``beet fingerprint`` command to generate fingerprints for
items already in your library. (Provide a query to fingerprint a subset of your
library.) The generated fingerprints will be stored in the library database.
If you have the ``import.write`` config option enabled, they will also be
written to files' metadata.

.. _submitfp:

Configuration
-------------

There is one configuration option in the ``chroma:`` section, ``auto``, which
controls whether to fingerprint files during the import process. To disable
fingerprint-based autotagging, set it to ``no``, like so::

    chroma:
        auto: no

Submitting Fingerprints
-----------------------

You can help expand the `Acoustid`_ database by submitting fingerprints for the
music in your collection. To do this, first `get an API key`_ from the Acoustid
service. Just use an OpenID or MusicBrainz account to log in and you'll get a
short token string. Then, add the key to your ``config.yaml`` as the
value ``apikey`` in a section called ``acoustid`` like so::

    acoustid:
        apikey: AbCd1234

Then, run ``beet submit``. (You can also provide a query to submit a subset of
your library.) The command will use stored fingerprints if they're available;
otherwise it will fingerprint each file before submitting it.

.. _get an API key: https://acoustid.org/api-key
