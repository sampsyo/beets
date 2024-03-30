Bad Files Plugin
================

The ``badfiles`` plugin adds a ``beet bad`` command to check for missing and
corrupt files.

Configuring
-----------

First, enable the ``badfiles`` plugin (see :ref:`using-plugins`). The default
configuration defines the following default checkers, which you may need to
install yourself:

* `mp3val`_ for MP3 files
* `FLAC`_ command-line tools for FLAC files
* `wvunpack`_ for wavpack files

You can also add custom commands for a specific extension, like this::

    badfiles:
        check_on_import: yes
        commands:
            ogg: myoggchecker --opt1 --opt2
            flac: flac --test --warnings-as-errors --silent

Custom commands will be run once for each file of the specified type, with the
path to the file as the last argument. Commands must return a status code
greater than zero for a file to be considered corrupt.

You can run the checkers when importing files by using the `check_on_import`
option. When on, checkers will be run against every imported file and warnings
and errors will be presented when selecting a tagging option.

.. _mp3val: http://mp3val.sourceforge.net/
.. _flac: https://xiph.org/flac/
.. _wvunpack: https://www.wavpack.com/index.html

Using
-----

Type ``beet bad`` with a query according to beets' usual query syntax. For
instance, this will run a check on all songs containing the word "wolf"::

    beet bad wolf

This one will run checks on a specific album::

    beet bad album_id:1234

Here is an example where the FLAC decoder signals a corrupt file::

    beet bad title::^$
    /tank/Music/__/00.flac: command exited with status 1
      00.flac: *** Got error code 2:FLAC__STREAM_DECODER_ERROR_STATUS_FRAME_CRC_MISMATCH
      00.flac: ERROR while decoding data
                 state = FLAC__STREAM_DECODER_READ_FRAME

Note that the default ``mp3val`` checker is a bit verbose and can output a lot
of "stream error" messages, even for files that play perfectly well.
Generally, if more than one stream error happens, or if a stream error happens
in the middle of a file, this is a bad sign.

By default, only errors for the bad files will be shown. In order for the
results for all of the checked files to be seen, including the uncorrupted
ones, use the ``-v`` or ``--verbose`` option.
