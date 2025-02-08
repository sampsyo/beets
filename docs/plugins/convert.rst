Convert Plugin
==============

The ``convert`` plugin lets you convert parts of your collection to a
directory of your choice, transcoding audio and embedding album art along the
way. It can transcode to and from any format using a configurable command
line. Optionally an m3u playlist file containing all the converted files can be
saved to the destination path.


Installation
------------

To use the ``convert`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). By default, the plugin depends on `FFmpeg`_ to
transcode the audio, so you might want to install it.

.. _FFmpeg: https://ffmpeg.org


Usage
-----

To convert a part of your collection, run ``beet convert QUERY``. The
command will transcode all the files matching the query to the
destination directory given by the ``-d`` (``--dest``) option or the
``dest`` configuration. The path layout mirrors that of your library,
but it may be customized through the ``paths`` configuration. Files
that have been previously converted---and thus already exist in the
destination directory---will be skipped.

The plugin uses a command-line program to transcode the audio. With the
``-f`` (``--format``) option you can choose the transcoding command
and customize the available commands
:ref:`through the configuration <convert-format-config>`.

Unless the ``-y`` (``--yes``) flag is set, the command will list all
the items to be converted and ask for your confirmation.

The ``-a`` (or ``--album``) option causes the command
to match albums instead of tracks.

By default, the command places converted files into the destination directory
and leaves your library pristine. To instead back up your original files into
the destination directory and keep converted files in your library, use the
``-k`` (or ``--keep-new``) option.

To test your configuration without taking any actions, use the ``--pretend``
flag. The plugin will print out the commands it will run instead of executing
them.

By default, files that do not need to be transcoded will be copied to their
destination. Passing the ``-l`` (``--link``) flag creates symbolic links
instead, passing ``-H`` (``--hardlink``) creates hard links.
Note that album art embedding is disabled for files that are linked.
Refer to the ``link`` and ``hardlink`` options below.

The ``-m`` (or ``--playlist``) option enables the plugin to create an m3u8
playlist file in the destination folder given by the ``-d`` (``--dest``) option
or the ``dest`` configuration. The path to the playlist file can either be
absolute or relative to the ``dest`` directory. The contents will always be
relative paths to media files, which tries to ensure compatibility when read
from external drives or on computers other than the one used for the
conversion. There is one caveat though: A list generated on Unix/macOS can't be
read on Windows and vice versa. Depending on the beets user's settings a
generated playlist potentially could contain unicode characters. This is
supported, playlists are written in `M3U8 format`_.

The ``-r`` (or ``--refresh``) option allows to refresh the converted files if
the originals ones are modified. It instructs the plugin to compare the
timestamps of the latest modification for both the originals and the converted
files. If an original file is newer than a converted file, the converted file
will be removed from the filesystem, and the original file will be converted
once again.

Configuration
-------------

To configure the plugin, make a ``convert:`` section in your configuration
file. The available options are:

- **auto**: Import transcoded versions of your files automatically during
  imports. With this option enabled, the importer will transcode all (in the
  default configuration) non-MP3 files over the maximum bitrate before adding
  them to your library.
  Default: ``no``.
- **auto_keep**: Convert your files automatically on import to **dest** but
  import the non transcoded version. It uses the default format you have
  defined in your config file.
  Default: ``no``.

  .. note:: You probably want to use only one of the `auto` and `auto_keep`
     options, not both. Enabling both will convert your files twice on import,
     which you probably don't want.

- **tmpdir**: The directory where temporary files will be stored during import.
  Default: none (system default),
- **copy_album_art**: Copy album art when copying or transcoding albums matched
  using the ``-a`` option. Default: ``no``.
- **album_art_maxwidth**: Downscale album art if it's too big. The resize
  operation reduces image width to at most ``maxwidth`` pixels while
  preserving the aspect ratio. The specified image size will apply to both
  embedded album art and external image files.
- **dest**: The directory where the files will be converted (or copied) to.
  Default: none.
- **embed**: Embed album art in converted items. Default: ``yes``.
- **id3v23**: Can be used to override the global ``id3v23`` option. Default:
  ``inherit``.
- **max_bitrate**: By default, the plugin does not transcode files that are
  already in the destination format. This option instead also transcodes files
  with high bitrates, even if they are already in the same format as the
  output.  Note that this does not guarantee that all converted files will have
  a lower bitrate---that depends on the encoder and its configuration.
  Default: none.
- **no_convert**: Does not transcode items matching the query string provided
  (see :doc:`/reference/query`). For example, to not convert AAC or WMA formats, you can use ``format:AAC, format:WMA`` or
  ``path::\.(m4a|wma)$``. If you only want to transcode WMA format, you can use a negative query, e.g., ``^path::\.(wma)$``, to not convert any other format except WMA.
- **never_convert_lossy_files**: Cross-conversions between lossy codecs---such
  as mp3, ogg vorbis, etc.---makes little sense as they will decrease quality
  even further. If set to ``yes``, lossy files are always copied.
  Default: ``no``.
- **paths**: The directory structure and naming scheme for the converted
  files. Uses the same format as the top-level ``paths`` section (see
  :ref:`path-format-config`).
  Default: Reuse your top-level path format settings.
- **quiet**: Prevent the plugin from announcing every file it processes.
  Default: ``false``.
- **threads**: The number of threads to use for parallel encoding.
  By default, the plugin will detect the number of processors available and use
  them all.
- **link**: By default, files that do not need to be transcoded will be copied
  to their destination. This option creates symbolic links instead. Note that
  options such as ``embed`` that modify the output files after the transcoding
  step will cause the original files to be modified as well if ``link`` is
  enabled. For this reason, album-art embedding is disabled
  for files that are linked.
  Default: ``false``.
- **hardlink**: This options works similar to ``link``, but it creates
  hard links instead of symlinks.
  This option overrides ``link``. Only works when converting to a directory
  on the same filesystem as the library.
  Default: ``false``.
- **delete_originals**: Transcoded files will be copied or moved to their destination, depending on the import configuration. By default, the original files are not modified by the plugin. This option deletes the original files after the transcoding step has completed.
  Default: ``false``.
- **playlist**: The name of a playlist file that should be written on each run
  of the plugin. A relative file path (e.g `playlists/mylist.m3u8`) is allowed
  as well. The final destination of the playlist file will always be relative
  to the destination path (``dest``, ``--dest``, ``-d``). This configuration is
  overridden by the ``-m`` (``--playlist``) command line option.
  Default: none.
- **refresh**: Refresh the converted files if needed by re-converting modified
  original files. This configuration is overridden by the ``-r``
  (``--refresh``) command line option.
  Default: ``false``.

You can also configure the format to use for transcoding (see the next
section):

- **format**: The name of the format to transcode to when none is specified on
  the command line.
  Default: ``mp3``.
- **formats**: A set of formats and associated command lines for transcoding
  each.

.. _convert-format-config:

Configuring the transcoding command
```````````````````````````````````

You can customize the transcoding command through the ``formats`` map
and select a command with the ``--format`` command-line option or the
``format`` configuration.

::

    convert:
        format: speex
        formats:
            speex:
                command: ffmpeg -i $source -y -acodec speex $dest
                extension: spx
            wav: ffmpeg -i $source -y -acodec pcm_s16le $dest

In this example ``beet convert`` will use the *speex* command by
default. To convert the audio to `wav`, run ``beet convert -f wav``.
This will also use the format key (``wav``) as the file extension.

Each entry in the ``formats`` map consists of a key (the name of the
format) as well as the command and optionally the file extension.
``extension`` is the filename extension to be used for newly transcoded
files.  If only the command is given as a string or the extension is not
provided, the file extension defaults to the format's name. ``command`` is the
command to use to transcode audio. The tokens ``$source`` and ``$dest`` in the
command are replaced with the paths to the existing and new file.

The plugin in comes with default commands for the most common audio
formats: `mp3`, `alac`, `flac`, `aac`, `opus`, `ogg`, `wma`. For
details have a look at the output of ``beet config -d``.

For a one-command-fits-all solution use the ``convert.command`` and
``convert.extension`` options. If these are set, the formats are ignored
and the given command is used for all conversions.

::

    convert:
        command: ffmpeg -i $source -y -vn -aq 2 $dest
        extension: mp3


Gapless MP3 encoding
````````````````````

While FFmpeg cannot produce "`gapless`_" MP3s by itself, you can create them
by using `LAME`_ directly. Use a shell script like this to pipe the output of
FFmpeg into the LAME tool::

    #!/bin/sh
    ffmpeg -i "$1" -f wav - | lame -V 2 --noreplaygain - "$2"

Then configure the ``convert`` plugin to use the script::

    convert:
        command: /path/to/script.sh $source $dest
        extension: mp3

This strategy configures FFmpeg to produce a WAV file with an accurate length
header for LAME to use. Using ``--noreplaygain`` disables gain analysis; you
can use the :doc:`/plugins/replaygain` to do this analysis. See the LAME
`documentation`_ and the `HydrogenAudio wiki`_ for other LAME configuration
options and a thorough discussion of MP3 encoding.

.. _documentation: https://lame.sourceforge.io/index.php
.. _HydrogenAudio wiki: https://wiki.hydrogenaud.io/index.php?title=LAME
.. _gapless: https://wiki.hydrogenaud.io/index.php?title=Gapless_playback
.. _LAME: https://lame.sourceforge.io/index.php
.. _M3U8 format: https://en.wikipedia.org/wiki/M3U#M3U8
