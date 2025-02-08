ReplayGain Plugin
=================

This plugin adds support for `ReplayGain`_, a technique for normalizing audio
playback levels.

.. _ReplayGain: https://wiki.hydrogenaudio.org/index.php?title=ReplayGain


Installation
------------

This plugin can use one of many backends to compute the ReplayGain values:
GStreamer, mp3gain (and its cousin, aacgain), Python Audio Tools or ffmpeg.
ffmpeg and mp3gain can be easier to install. mp3gain supports less audio formats
than the other backend.

Once installed, this plugin analyzes all files during the import process. This
can be a slow process; to instead analyze after the fact, disable automatic
analysis and use the ``beet replaygain`` command (see below).

To speed up analysis with some of the available backends, this plugin processes
tracks or albums (when using the ``-a`` option) in parallel. By default,
a single thread is used per logical core of your CPU.

GStreamer
`````````

To use `GStreamer`_ for ReplayGain analysis, you will of course need to
install GStreamer and plugins for compatibility with your audio files.
You will need at least GStreamer 1.0 and `PyGObject 3.x`_ (a.k.a. ``python-gi``).

.. _PyGObject 3.x: https://pygobject.readthedocs.io/en/latest/
.. _GStreamer: https://gstreamer.freedesktop.org/

Then, install ``beets`` with ``replaygain`` extra which installs
``GStreamer`` bindings for Python

.. code-block:: bash

    pip install "beets[replaygain]"

Lastly, enable the ``replaygain`` plugin in your configuration (see
:ref:`using-plugins`) and specify the GStreamer backend by adding this to your
configuration file::

    replaygain:
        backend: gstreamer

The GStreamer backend does not support parallel analysis.

mp3gain and aacgain
```````````````````

In order to use this backend, you will need to install the `mp3gain`_
command-line tool or the `aacgain`_ fork thereof. Here are some hints:

* On Mac OS X, you can use `Homebrew`_. Type ``brew install aacgain``.
* On Linux, `mp3gain`_ is probably in your repositories. On Debian or Ubuntu,
  for example, you can run ``apt-get install mp3gain``.
* On Windows, download and install the original `mp3gain`_.

.. _mp3gain: http://mp3gain.sourceforge.net/download.php
.. _aacgain: https://aacgain.altosdesign.com
.. _Homebrew: https://brew.sh

Then, enable the plugin (see :ref:`using-plugins`) and specify the "command"
backend in your configuration file::

    replaygain:
        backend: command

If beets doesn't automatically find the ``mp3gain`` or ``aacgain`` executable,
you can configure the path explicitly like so::

    replaygain:
        command: /Applications/MacMP3Gain.app/Contents/Resources/aacgain

Python Audio Tools
``````````````````

This backend uses the `Python Audio Tools`_ package to compute ReplayGain for
a range of different file formats. The package is not available via PyPI; it
must be installed manually (only versions preceding 3.x are compatible).

On OS X, most of the dependencies can be installed with `Homebrew`_::

    brew install mpg123 mp3gain vorbisgain faad2 libvorbis

The Python Audio Tools backend does not support parallel analysis.

.. _Python Audio Tools: http://audiotools.sourceforge.net

ffmpeg
``````

This backend uses ffmpeg to calculate EBU R128 gain values.
To use it, install the `ffmpeg`_ command-line tool and select the
``ffmpeg`` backend in your config file.

.. _ffmpeg: https://ffmpeg.org

Configuration
-------------

To configure the plugin, make a ``replaygain:`` section in your
configuration file. The available options are:

- **auto**: Enable ReplayGain analysis during import.
  Default: ``yes``.
- **threads**: The number of parallel threads to run the analysis in. Overridden
  by ``--threads`` at the command line.
  Default: # of logical CPU cores
- **parallel_on_import**: Whether to enable parallel analysis during import.
  As of now this ReplayGain data is not written to files properly, so this option
  is disabled by default.
  If you wish to enable it, remember to run ``beet write`` after importing to
  actually write to the imported files.
  Default: ``no``
- **backend**: The analysis backend; either ``gstreamer``, ``command``, ``audiotools``
  or ``ffmpeg``.
  Default: ``command``.
- **overwrite**: On import, re-analyze files that already have ReplayGain tags.
  Note that, for historical reasons, the name of this option is somewhat
  unfortunate: It does not decide whether tags are written to the files (which
  is controlled by the :ref:`import.write <config-import-write>` option).
  Default: ``no``.
- **targetlevel**: A number of decibels for the target loudness level for files
  using ``REPLAYGAIN_`` tags.
  Default: ``89``.
- **r128_targetlevel**: The target loudness level in decibels (i.e.
  ``<loudness in LUFS> + 107``) for files using ``R128_`` tags.
  Default: 84 (Use ``83`` for ATSC A/85, ``84`` for EBU R128 or ``89`` for
  ReplayGain 2.0.)
- **r128**: A space separated list of formats that will use ``R128_`` tags with
  integer values instead of the common ``REPLAYGAIN_`` tags with floating point
  values. Requires the "ffmpeg" backend.
  Default: ``Opus``.
- **per_disc**: Calculate album ReplayGain on disc level instead of album level.
  Default: ``no``

These options only work with the "command" backend:

- **command**: The path to the ``mp3gain`` or ``aacgain`` executable (if beets
  cannot find it by itself).
  For example: ``/Applications/MacMP3Gain.app/Contents/Resources/aacgain``.
  Default: Search in your ``$PATH``.
- **noclip**: Reduce the amount of ReplayGain adjustment to whatever amount
  would keep clipping from occurring.
  Default: ``yes``.

This option only works with the "ffmpeg" backend:

- **peak**: Either ``true`` (the default) or ``sample``. ``true`` is
  more accurate but slower.

Manual Analysis
---------------

By default, the plugin will analyze all items an albums as they are implemented.
However, you can also manually analyze files that are already in your library.
Use the ``beet replaygain`` command::

    $ beet replaygain [-Waf] [QUERY]

The ``-a`` flag analyzes whole albums instead of individual tracks. Provide a
query (see :doc:`/reference/query`) to indicate which items or albums to
analyze. Files that already have ReplayGain values are skipped unless ``-f`` is
supplied. Use ``-w`` (write tags) or ``-W`` (don't write tags) to control
whether ReplayGain tags are written into the music files, or stored in the
beets database only (the default is to use :ref:`the importer's configuration
<config-import-write>`).

To execute with a different number of threads, call ``beet replaygain --threads N``::

    $ beet replaygain --threads N [-Waf] [QUERY]

with N any integer. To disable parallelism, use ``--threads 0``.

ReplayGain analysis is not fast, so you may want to disable it during import.
Use the ``auto`` config option to control this::

    replaygain:
        auto: no

