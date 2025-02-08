AutoBPM Plugin
==============

The `autobpm` plugin uses the `Librosa`_ library to calculate the BPM
of a track from its audio data and store it in the `bpm` field of your
database. It does so automatically when importing music or through
the ``beet autobpm [QUERY]`` command.

Install
-------

To use the ``autobpm`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``autobpm`` extra

.. code-block:: bash

    pip install "beets[autobpm]"

Configuration
-------------

To configure the plugin, make a ``autobpm:`` section in your
configuration file. The available options are:

- **auto**: Analyze every file on import.
  Otherwise, you need to use the ``beet autobpm`` command explicitly.
  Default: ``yes``
- **overwrite**: Calculate a BPM even for files that already have a
  `bpm` value.
  Default: ``no``.
- **beat_track_kwargs**: Any extra keyword arguments that you would like to
  provide to librosa's `beat_track`_ function call, for example:

.. code-block:: yaml

    autobpm:
      beat_track_kwargs:
        start_bpm: 160

.. _Librosa: https://github.com/librosa/librosa/
.. _beat_track: https://librosa.org/doc/latest/generated/librosa.beat.beat_track.html
