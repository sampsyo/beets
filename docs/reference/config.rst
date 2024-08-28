Configuration
=============

Beets has an extensive configuration system that lets you customize nearly
every aspect of its operation. To configure beets, you create a file called
``config.yaml``. The location of the file depends on your platform (type ``beet
config -p`` to see the path on your system):

* On Unix-like OSes, write ``~/.config/beets/config.yaml``.
* On Windows, use ``%APPDATA%\beets\config.yaml``. This is usually in a
  directory like ``C:\Users\You\AppData\Roaming``.
* On OS X, you can use either the Unix location or ``~/Library/Application
  Support/beets/config.yaml``.

You can launch your text editor to create or update your configuration by
typing ``beet config -e``. (See the :ref:`config-cmd` command for details.) It
is also possible to customize the location of the configuration file and even
use multiple layers of configuration. See `Configuration Location`_, below.

The config file uses `YAML`_ syntax. You can use the full power of YAML, but
most configuration options are simple key/value pairs. This means your config
file will look like this::

    option: value
    another_option: foo
    bigger_option:
        key: value
        foo: bar

In YAML, you will need to use spaces (not tabs!) to indent some lines. If you
have questions about more sophisticated syntax, take a look at the `YAML`_
documentation.

.. _YAML: https://yaml.org/

The rest of this page enumerates the dizzying litany of configuration options
available in beets. You might also want to see an
:ref:`example <config-example>`.

.. contents::
    :local:
    :depth: 2

Global Options
--------------

These options control beets' global operation.

library
~~~~~~~

Path to the beets library file. By default, beets will use a file called
``library.db`` alongside your configuration file.

directory
~~~~~~~~~

The directory to which files will be copied/moved when adding them to the
library. Defaults to a folder called ``Music`` in your home directory.

plugins
~~~~~~~

A space-separated list of plugin module names to load. See
:ref:`using-plugins`.

include
~~~~~~~

A space-separated list of extra configuration files to include.
Filenames are relative to the directory containing ``config.yaml``.

pluginpath
~~~~~~~~~~

Directories to search for plugins.  Each Python file or directory in a plugin
path represents a plugin and should define a subclass of :class:`BeetsPlugin`.
A plugin can then be loaded by adding the filename to the `plugins` configuration.
The plugin path can either be a single string or a list of strings---so, if you
have multiple paths, format them as a YAML list like so::

    pluginpath:
        - /path/one
        - /path/two

.. _ignore:

ignore
~~~~~~

A list of glob patterns specifying file and directory names to be ignored when
importing. By default, this consists of ``.*``,  ``*~``,  ``System Volume
Information``, ``lost+found`` (i.e., beets ignores Unix-style hidden files,
backup files, and directories that appears at the root of some Linux and Windows
filesystems).

.. _ignore_hidden:

ignore_hidden
~~~~~~~~~~~~~

Either ``yes`` or ``no``; whether to ignore hidden files when importing. On
Windows, the "Hidden" property of files is used to detect whether or not a file
is hidden. On OS X, the file's "IsHidden" flag is used to detect whether or not
a file is hidden. On both OS X and other platforms (excluding Windows), files
(and directories) starting with a dot are detected as hidden files.

.. _replace:

replace
~~~~~~~

A set of regular expression/replacement pairs to be applied to all filenames
created by beets. Typically, these replacements are used to avoid confusing
problems or errors with the filesystem (for example, leading dots, which hide
files on Unix, and trailing whitespace, which is illegal on Windows). To
override these substitutions, specify a mapping from regular expression to
replacement strings. For example, ``[xy]: z`` will make beets replace all
instances of the characters ``x`` or ``y`` with the character ``z``.

If you do change this value, be certain that you include at least enough
substitutions to avoid causing errors on your operating system. Here are
the default substitutions used by beets, which are sufficient to avoid
unexpected behavior on all popular platforms::

    replace:
        '[\\/]': _
        '^\.': _
        '[\x00-\x1f]': _
        '[<>:"\?\*\|]': _
        '\.$': _
        '\s+$': ''
        '^\s+': ''
        '^-': _

These substitutions remove forward and back slashes, leading dots, and
control characters—all of which is a good idea on any OS. The fourth line
removes the Windows "reserved characters" (useful even on Unix for
compatibility with Windows-influenced network filesystems like Samba).
Trailing dots and trailing whitespace, which can cause problems on Windows
clients, are also removed.

When replacements other than the defaults are used, it is possible that they
will increase the length of the path. In the scenario where this leads to a
conflict with the maximum filename length, the default replacements will be
used to resolve the conflict and beets will display a warning.

Note that paths might contain special characters such as typographical
quotes (``“”``). With the configuration above, those will not be
replaced as they don't match the typewriter quote (``"``). To also strip these
special characters, you can either add them to the replacement list or use the
:ref:`asciify-paths` configuration option below.

.. _path-sep-replace:

path_sep_replace
~~~~~~~~~~~~~~~~

A string that replaces the path separator (for example, the forward slash
``/`` on Linux and MacOS, and the backward slash ``\\`` on Windows) when
generating filenames with beets.
This option is related to :ref:`replace`, but is distinct from it for
technical reasons.

.. warning::
   Changing this option is potentially dangerous. For example, setting
   it to the actual path separator could create directories in unexpected
   locations. Use caution when changing it and always try it out on a small
   number of files before applying it to your whole library.

Default: ``_``.

.. _asciify-paths:

asciify_paths
~~~~~~~~~~~~~

Convert all non-ASCII characters in paths to ASCII equivalents.

For example, if your path template for
singletons is ``singletons/$title`` and the title of a track is "Café",
then the track will be saved as ``singletons/Cafe.mp3``.  The changes
take place before applying the :ref:`replace` configuration and are roughly
equivalent to wrapping all your path templates in the ``%asciify{}``
:ref:`template function <template-functions>`.

This uses the `unidecode module`_ which is language agnostic, so some 
characters may be transliterated from a different language than expected. 
For example, Japanese kanji will usually use their Chinese readings.

Default: ``no``.

.. _unidecode module: https://pypi.org/project/Unidecode


.. _art-filename:

art_filename
~~~~~~~~~~~~

When importing album art, the name of the file (without extension) where the
cover art image should be placed. This is a template string, so you can use any
of the syntax available to :doc:`/reference/pathformat`. Defaults to ``cover``
(i.e., images will be named ``cover.jpg`` or ``cover.png`` and placed in the
album's directory).

threaded
~~~~~~~~

Either ``yes`` or ``no``, indicating whether the autotagger should use
multiple threads. This makes things substantially faster by overlapping work:
for example, it can copy files for one album in parallel with looking up data
in MusicBrainz for a different album. You may want to disable this when
debugging problems with the autotagger.
Defaults to ``yes``.


.. _list_format_item:
.. _format_item:

format_item
~~~~~~~~~~~

Format to use when listing *individual items* with the :ref:`list-cmd`
command and other commands that need to print out items. Defaults to
``$artist - $album - $title``. The ``-f`` command-line option overrides
this setting.

It used to be named `list_format_item`.

.. _list_format_album:
.. _format_album:

format_album
~~~~~~~~~~~~

Format to use when listing *albums* with :ref:`list-cmd` and other
commands. Defaults to ``$albumartist - $album``. The ``-f`` command-line
option overrides this setting.

It used to be named `list_format_album`.

.. _sort_item:

sort_item
~~~~~~~~~

Default sort order to use when fetching items from the database. Defaults to
``artist+ album+ disc+ track+``. Explicit sort orders override this default.

.. _sort_album:

sort_album
~~~~~~~~~~

Default sort order to use when fetching albums from the database. Defaults to
``albumartist+ album+``. Explicit sort orders override this default.

.. _sort_case_insensitive:

sort_case_insensitive
~~~~~~~~~~~~~~~~~~~~~
Either ``yes`` or ``no``, indicating whether the case should be ignored when
sorting lexicographic fields. When set to ``no``, lower-case values will be
placed after upper-case values (e.g., *Bar Qux foo*), while ``yes`` would
result in the more expected *Bar foo Qux*. Default: ``yes``.

.. _original_date:

original_date
~~~~~~~~~~~~~

Either ``yes`` or ``no``, indicating whether matched albums should have their
``year``, ``month``, and ``day`` fields set to the release date of the
*original* version of an album rather than the selected version of the release.
That is, if this option is turned on, then ``year`` will always equal
``original_year`` and so on. Default: ``no``.

.. _artist_credit:

artist_credit
~~~~~~~~~~~~~

Either ``yes`` or ``no``, indicating whether matched tracks and albums should
use the artist credit, rather than the artist. That is, if this option is turned
on, then ``artist`` will contain the artist as credited on the release.

.. _per_disc_numbering:

per_disc_numbering
~~~~~~~~~~~~~~~~~~

A boolean controlling the track numbering style on multi-disc releases. By
default (``per_disc_numbering: no``), tracks are numbered per-release, so the
first track on the second disc has track number N+1 where N is the number of
tracks on the first disc. If this ``per_disc_numbering`` is enabled, then the
first (non-pregap) track on each disc always has track number 1.

If you enable ``per_disc_numbering``, you will likely want to change your
:ref:`path-format-config` also to include ``$disc`` before ``$track`` to make
filenames sort correctly in album directories. For example, you might want to
use a path format like this::

    paths:
        default: $albumartist/$album%aunique{}/$disc-$track $title

When this option is off (the default), even "pregap" hidden tracks are
numbered from one, not zero, so other track numbers may appear to be bumped up
by one. When it is on, the pregap track for each disc can be numbered zero.


.. _config-aunique:

aunique
~~~~~~~

These options are used to generate a string that is guaranteed to be unique
among all albums in the library who share the same set of keys.

The defaults look like this::

    aunique:
        keys: albumartist album
        disambiguators: albumtype year label catalognum albumdisambig releasegroupdisambig
        bracket: '[]'

See :ref:`aunique` for more details.


.. _config-sunique:

sunique
~~~~~~~

Like :ref:`config-aunique` above for albums, these options control the
generation of a unique string to disambiguate *singletons* that share similar
metadata.

The defaults look like this::

    sunique:
        keys: artist title
        disambiguators: year trackdisambig
        bracket: '[]'

See :ref:`sunique` for more details.


.. _terminal_encoding:

terminal_encoding
~~~~~~~~~~~~~~~~~

The text encoding, as `known to Python`_, to use for messages printed to the
standard output. It's also used to read messages from the standard input.
By default, this is determined automatically from the locale
environment variables.

.. _known to python: https://docs.python.org/2/library/codecs.html#standard-encodings

.. _clutter:

clutter
~~~~~~~

When beets imports all the files in a directory, it tries to remove the
directory if it's empty. A directory is considered empty if it only contains
files whose names match the glob patterns in `clutter`, which should be a list
of strings. The default list consists of "Thumbs.DB" and ".DS_Store".

The importer only removes recursively searched subdirectories---the top-level
directory you specify on the command line is never deleted.

.. _max_filename_length:

max_filename_length
~~~~~~~~~~~~~~~~~~~

Set the maximum number of characters in a filename, after which names will be
truncated. By default, beets tries to ask the filesystem for the correct
maximum.

.. _id3v23:

id3v23
~~~~~~

By default, beets writes MP3 tags using the ID3v2.4 standard, the latest
version of ID3. Enable this option to instead use the older ID3v2.3 standard,
which is preferred by certain older software such as Windows Media Player.

.. _va_name:

va_name
~~~~~~~

Sets the albumartist for various-artist compilations. Defaults to ``'Various
Artists'`` (the MusicBrainz standard). Affects other sources, such as
:doc:`/plugins/discogs`, too.

.. _ui_options:

UI Options
----------

The options that allow for customization of the visual appearance
of the console interface.

These options are available in this section:

color
~~~~~

Either ``yes`` or ``no``; whether to use color in console output (currently
only in the ``import`` command). Turn this off if your terminal doesn't
support ANSI colors.

.. note::

    The `color` option was previously a top-level configuration. This is
    still respected, but a deprecation message will be shown until your
    top-level `color` configuration has been nested under `ui`.

.. _colors:

colors
~~~~~~

The colors that are used throughout the user interface. These are only used if
the ``color`` option is set to ``yes``. For example, you might have a section
in your configuration file that looks like this::

    ui:
        colors:
            text_success: ['bold', 'green']
            text_warning: ['bold', 'yellow']
            text_error: ['bold', 'red']
            text_highlight: ['bold', 'red']
            text_highlight_minor: ['white']
            action_default: ['bold', 'cyan']
            action: ['bold', 'cyan']
            # New colors after UI overhaul
            text: ['normal']
            text_faint: ['faint']
            import_path: ['bold', 'blue']
            import_path_items: ['bold', 'blue']
            added:   ['green']
            removed: ['red']
            changed: ['yellow']
            added_highlight:   ['bold', 'green']
            removed_highlight: ['bold', 'red']
            changed_highlight: ['bold', 'yellow']
            text_diff_added:   ['bold', 'red']
            text_diff_removed: ['bold', 'red']
            text_diff_changed: ['bold', 'red']
            action_description: ['white']

Available colors: black, darkred, darkgreen, brown (darkyellow), darkblue,
purple (darkmagenta), teal (darkcyan), lightgray, darkgray, red, green,
yellow, blue, fuchsia (magenta), turquoise (cyan), white

Legacy UI colors config directive used strings. If any colors value is still a
string instead of a list, it will be translated to list automatically. For
example ``blue`` will become ``['blue']``.

terminal_width
~~~~~~~~~~~~~~

Controls line wrapping on non-Unix systems. On Unix systems, the width of the
terminal is detected automatically. If this fails, or on non-Unix systems, the
specified value is used as a fallback. Defaults to ``80`` characters::

    ui:
        terminal_width: 80

length_diff_thresh
~~~~~~~~~~~~~~~~~~

Beets compares the length of the imported track with the length the metadata
source provides. If any tracks differ by at least ``length_diff_thresh``
seconds, they will be colored with ``text_highlight``. Below this threshold,
different track lengths are colored with ``text_highlight_minor``.
``length_diff_thresh`` does not impact which releases are selected in
autotagger matching or distance score calculation (see :ref:`match-config`,
``distance_weights`` and :ref:`colors`)::

    ui:
        length_diff_thresh: 10.0

import
~~~~~~

When importing, beets will read several options to configure the visuals of the
import dialogue. There are two layouts controlling how horizontal space and
line wrapping is dealt with: ``column`` and ``newline``. The indentation of the
respective elements of the import UI can also be configured. For example
setting ``4``  for ``match_header`` will indent the very first block of a
proposed match by five characters in the terminal::

    ui:
        import:
            indentation:
                match_header: 4
                match_details: 4
                match_tracklist: 7
            layout: newline

Importer Options
----------------

The options that control the :ref:`import-cmd` command are indented under the
``import:`` key. For example, you might have a section in your configuration
file that looks like this::

    import:
        write: yes
        copy: yes
        resume: no

These options are available in this section:

.. _config-import-write:

write
~~~~~

Either ``yes`` or ``no``, controlling whether metadata (e.g., ID3) tags are
written to files when using ``beet import``. Defaults to ``yes``. The ``-w``
and ``-W`` command-line options override this setting.

.. _config-import-copy:

copy
~~~~

Either ``yes`` or ``no``, indicating whether to **copy** files into the
library directory when using ``beet import``. Defaults to ``yes``.  Can be
overridden with the ``-c`` and ``-C`` command-line options.

The option is ignored if ``move`` is enabled (i.e., beets can move or
copy files but it doesn't make sense to do both).

.. _config-import-move:

move
~~~~

Either ``yes`` or ``no``, indicating whether to **move** files into the
library directory when using ``beet import``.
Defaults to ``no``.

The effect is similar to the ``copy`` option but you end up with only
one copy of the imported file. ("Moving" works even across filesystems; if
necessary, beets will copy and then delete when a simple rename is
impossible.) Moving files can be risky—it's a good idea to keep a backup in
case beets doesn't do what you expect with your files.

This option *overrides* ``copy``, so enabling it will always move
(and not copy) files. The ``-c`` switch to the ``beet import`` command,
however, still takes precedence.

.. _config-import-verify:

verify
~~~~~~

Either ``yes`` or ``no``, indicating whether **copy** and **move** should
verify copy and move operations when using ``beet import``.
Defaults to ``no``.

Files are being compared when doing either a copy or move operation and will
fail because of it. Usually this indicates problems with physical storage, but
we wouldn't want to be responsible for corrupting files.

The ``--verify`` switch to the ``beet import`` command overrides the config
file.

.. _link:

link
~~~~

Either ``yes`` or ``no``, indicating whether to use symbolic links instead of
moving or copying files. (It conflicts with the ``move``, ``copy`` and
``hardlink`` options.) Defaults to ``no``.

This option only works on platforms that support symbolic links: i.e., Unixes.
It will fail on Windows.

It's likely that you'll also want to set ``write`` to ``no`` if you use this
option to preserve the metadata on the linked files.

.. _hardlink:

hardlink
~~~~~~~~

Either ``yes`` or ``no``, indicating whether to use hard links instead of
moving, copying, or symlinking files. (It conflicts with the ``move``,
``copy``, and ``link`` options.) Defaults to ``no``.

As with symbolic links (see :ref:`link`, above), this will not work on Windows
and you will want to set ``write`` to ``no``.  Otherwise, metadata on the
original file will be modified.

.. _reflink:

reflink
~~~~~~~

Either ``yes``, ``no``, or ``auto``, indicating whether to use copy-on-write
`file clones`_ (a.k.a. "reflinks") instead of copying or moving files.
The ``auto`` option uses reflinks when possible and falls back to plain
copying when necessary.
Defaults to ``no``.

This kind of clone is only available on certain filesystems: for example,
btrfs and APFS. For more details on filesystem support, see the `pyreflink`_
documentation.  Note that you need to install ``pyreflink``, either through
``python -m pip install beets[reflink]`` or ``python -m pip install reflink``.

The option is ignored if ``move`` is enabled (i.e., beets can move or
copy files but it doesn't make sense to do both).

.. _file clones: https://blogs.oracle.com/otn/save-disk-space-on-linux-by-cloning-files-on-btrfs-and-ocfs2
.. _pyreflink: https://reflink.readthedocs.io/en/latest/

resume
~~~~~~

Either ``yes``, ``no``, or ``ask``. Controls whether interrupted imports
should be resumed. "Yes" means that imports are always resumed when
possible; "no" means resuming is disabled entirely; "ask" (the default)
means that the user should be prompted when resuming is possible. The ``-p``
and ``-P`` flags correspond to the "yes" and "no" settings and override this
option.

.. _incremental:

incremental
~~~~~~~~~~~

Either ``yes`` or ``no``, controlling whether imported directories are
recorded and whether these recorded directories are skipped.  This
corresponds to the ``-i`` flag to ``beet import``.

.. _incremental_skip_later:

incremental_skip_later
~~~~~~~~~~~~~~~~~~~~~~

Either ``yes`` or ``no``, controlling whether skipped directories are
recorded in the incremental list. When set to ``yes``, skipped
directories won't be recorded, and beets will try to import them again
later. When set to ``no``, skipped directories will be recorded, and
skipped later. Defaults to ``no``.

.. _from_scratch:

from_scratch
~~~~~~~~~~~~

Either ``yes`` or ``no`` (default), controlling whether existing metadata is
discarded when a match is applied. This corresponds to the ``--from-scratch``
flag to ``beet import``.

.. _quiet:

quiet
~~~~~

Either ``yes`` or ``no`` (default), controlling whether to ask for a manual
decision from the user when the importer is unsure how to proceed. This
corresponds to the ``--quiet`` flag to ``beet import``.

.. _quiet_fallback:

quiet_fallback
~~~~~~~~~~~~~~

Either ``skip`` (default) or ``asis``, specifying what should happen in
quiet mode (see the ``-q`` flag to ``import``, above) when there is no
strong recommendation.

.. _none_rec_action:

none_rec_action
~~~~~~~~~~~~~~~

Either ``ask`` (default), ``asis`` or ``skip``. Specifies what should happen
during an interactive import session when there is no recommendation. Useful
when you are only interested in processing medium and strong recommendations
interactively.

timid
~~~~~

Either ``yes`` or ``no``, controlling whether the importer runs in *timid*
mode, in which it asks for confirmation on every autotagging match, even the
ones that seem very close. Defaults to ``no``. The ``-t`` command-line flag
controls the same setting.

.. _import_log:

log
~~~

Specifies a filename where the importer's log should be kept.  By default,
no log is written. This can be overridden with the ``-l`` flag to
``import``.

.. _default_action:

default_action
~~~~~~~~~~~~~~

One of ``apply``, ``skip``, ``asis``, or ``none``, indicating which option
should be the *default* when selecting an action for a given match. This is the
action that will be taken when you type return without an option letter. The
default is ``apply``.

.. _languages:

languages
~~~~~~~~~

A list of locale names to search for preferred aliases. For example, setting
this to ``en`` uses the transliterated artist name "Pyotr Ilyich Tchaikovsky"
instead of the Cyrillic script for the composer's name when tagging from
MusicBrainz. You can use a space-separated list of language abbreviations, like 
``en jp es``, to specify a preference order. Defaults to an empty list, meaning 
that no language is preferred.

.. _ignored_alias_types:

ignored_alias_types
~~~~~~~~~~~~~~~~~~~

A list of alias types to be ignored when importing new items.

See the `MusicBrainz Documentation` for more information on aliases.

.._MusicBrainz Documentation: https://musicbrainz.org/doc/Aliases

.. _detail:

detail
~~~~~~

Whether the importer UI should show detailed information about each match it
finds. When enabled, this mode prints out the title of every track, regardless
of whether it matches the original metadata. (The default behavior only shows
changes.) Default: ``no``.

.. _group_albums:

group_albums
~~~~~~~~~~~~

By default, the beets importer groups tracks into albums based on the
directories they reside in. This option instead uses files' metadata to
partition albums. Enable this option if you have directories that contain
tracks from many albums mixed together.

The ``--group-albums`` or ``-g`` option to the :ref:`import-cmd` command is
equivalent, and the *G* interactive option invokes the same workflow.

Default: ``no``.

.. _autotag:

autotag
~~~~~~~

By default, the beets importer always attempts to autotag new music. If
most of your collection consists of obscure music, you may be interested in
disabling autotagging by setting this option to ``no``. (You can re-enable it
with the ``-a`` flag to the :ref:`import-cmd` command.)

Default: ``yes``.

.. _duplicate_keys:

duplicate_keys
~~~~~~~~~~~~~~

The fields used to find duplicates when importing.
There are two sub-values here: ``album`` and ``item``.
Each one is a list of field names; if an existing object (album or item) in
the library matches the new object on all of these fields, the importer will
consider it a duplicate.

Default::

    album: albumartist album
    item: artist title

.. _duplicate_action:

duplicate_action
~~~~~~~~~~~~~~~~

Either ``skip``, ``keep``, ``remove``, ``merge`` or ``ask``. 
Controls how duplicates are treated in import task. 
"skip" means that new item(album or track) will be skipped; 
"keep" means keep both old and new items; "remove" means remove old
item; "merge" means merge into one album; "ask" means the user 
should be prompted for the action each time. The default is ``ask``.

.. _duplicate_verbose_prompt:

duplicate_verbose_prompt
~~~~~~~~~~~~~~~~~~~~~~~~

Usually when duplicates are detected during import, information about the
existing and the newly imported album is summarized. Enabling this option also
lists details on individual tracks. The :ref:`format_item setting
<format_item>` is applied, which would, considering the default, look like
this:

.. code-block:: console

    This item is already in the library!
    Old: 1 items, MP3, 320kbps, 5:56, 13.6 MiB
      Artist Name - Album Name - Third Track Title
    New: 2 items, MP3, 320kbps, 7:18, 17.1 MiB
      Artist Name - Album Name - First Track Title
      Artist Name - Album Name - Second Track Title
    [S]kip new, Keep all, Remove old, Merge all?

Default: ``no``.

.. _bell:

bell
~~~~

Ring the terminal bell to get your attention when the importer needs your input.

Default: ``no``.

.. _set_fields:

set_fields
~~~~~~~~~~

A dictionary indicating fields to set to values for newly imported music.
Here's an example::

    set_fields:
        genre: 'To Listen'
        collection: 'Unordered'

Other field/value pairs supplied via the ``--set`` option on the command-line
override any settings here for fields with the same name.

Values support the same template syntax as beets'
:doc:`path formats <pathformat>`.

Fields are set on both the album and each individual track of the album.
Fields are persisted to the media files of each track.

Default: ``{}`` (empty).

.. _singleton_album_disambig:

singleton_album_disambig
~~~~~~~~~~~~~~~~~~~~~~~~

During singleton imports and if the metadata source provides it, album names
are appended to the disambiguation string of matching track candidates. For
example: ``The Artist - The Title (Discogs, Index 3, Track B1, [The Album]``.
This feature is currently supported by the :doc:`/plugins/discogs` and the
:doc:`/plugins/spotify`.

Default: ``yes``.

.. _musicbrainz-config:

MusicBrainz Options
-------------------

You can instruct beets to use `your own MusicBrainz database`_ instead of
the `main server`_. Use the ``host``, ``https`` and ``ratelimit`` options
under a ``musicbrainz:`` header, like so::

    musicbrainz:
        host: localhost:5000
        https: no
        ratelimit: 100

The ``host`` key, of course, controls the Web server hostname (and port,
optionally) that will be contacted by beets (default: musicbrainz.org).
The ``https`` key makes the client use HTTPS instead of HTTP. This setting applies
only to custom servers. The official MusicBrainz server always uses HTTPS. (Default: no.)
The server must have search indices enabled (see `Building search indexes`_).

The ``ratelimit`` option, an integer, controls the number of Web service requests
per second (default: 1). **Do not change the rate limit setting** if you're
using the main MusicBrainz server---on this public server, you're `limited`_
to one request per second.

.. _your own MusicBrainz database: https://musicbrainz.org/doc/MusicBrainz_Server/Setup
.. _main server: https://musicbrainz.org/
.. _limited: https://musicbrainz.org/doc/XML_Web_Service/Rate_Limiting
.. _Building search indexes: https://musicbrainz.org/doc/Development/Search_server_setup

.. _musicbrainz.enabled:

enabled
~~~~~~~

This option allows you to disable using MusicBrainz as a metadata source. This applies
if you use plugins that fetch data from alternative sources and should make the import
process quicker.

Default: ``yes``.

.. _searchlimit:

searchlimit
~~~~~~~~~~~

The number of matches returned when sending search queries to the
MusicBrainz server.

Default: ``5``.

.. _extra_tags:

extra_tags
~~~~~~~~~~

By default, beets will use only the artist, album, and track count to query
MusicBrainz. Additional tags to be queried can be supplied with the
``extra_tags`` setting. For example::

    musicbrainz:
        extra_tags: [year, catalognum, country, media, label]

This setting should improve the autotagger results if the metadata with the
given tags match the metadata returned by MusicBrainz.

Note that the only tags supported by this setting are the ones listed in the
above example.

Default: ``[]``

.. _genres:

genres
~~~~~~

Use MusicBrainz genre tags to populate (and replace if it's already set) the
``genre`` tag.  This will make it a list of all the genres tagged for the
release and the release-group on MusicBrainz, separated by "; " and sorted by
the total number of votes.
Default: ``no``

.. _musicbrainz.external_ids:

external_ids
~~~~~~~~~~~~

Set any of the ``external_ids`` options to ``yes`` to enable the MusicBrainz
importer to look for links to related metadata sources. If such a link is
available the release ID will be extracted from the URL provided and imported
to the beets library::

    musicbrainz:
        external_ids:
            discogs: yes
            spotify: yes
            bandcamp: yes
            beatport: yes
            deezer: yes
            tidal: yes


The library fields of the corresponding :ref:`autotagger_extensions` are used
to save the data (``discogs_albumid``, ``bandcamp_album_id``,
``spotify_album_id``, ``beatport_album_id``, ``deezer_album_id``,
``tidal_album_id``). On re-imports existing data will be overwritten.

The default of all options is ``no``.

.. _match-config:

Autotagger Matching Options
---------------------------

You can configure some aspects of the logic beets uses when automatically
matching MusicBrainz results under the ``match:`` section. To control how
*tolerant* the autotagger is of differences, use the ``strong_rec_thresh``
option, which reflects the distance threshold below which beets will make a
"strong recommendation" that the metadata be used. Strong recommendations
are accepted automatically (except in "timid" mode), so you can use this to
make beets ask your opinion more or less often.

The threshold is a *distance* value between 0.0 and 1.0, so you can think of it
as the opposite of a *similarity* value. For example, if you want to
automatically accept any matches above 90% similarity, use::

    match:
        strong_rec_thresh: 0.10

The default strong recommendation threshold is 0.04.

The ``medium_rec_thresh`` and ``rec_gap_thresh`` options work similarly. When a
match is below the *medium* recommendation threshold or the distance between it
and the next-best match is above the *gap* threshold, the importer will suggest
that match but not automatically confirm it. Otherwise, you'll see a list of
options to choose from.

.. _max_rec:

max_rec
~~~~~~~

As mentioned above, autotagger matches have *recommendations* that control how
the UI behaves for a certain quality of match. The recommendation for a certain
match is based on the overall distance calculation. But you can also control
the recommendation when a specific distance penalty is applied by defining
*maximum* recommendations for each field:

To define maxima, use keys under ``max_rec:`` in the ``match`` section. The
defaults are "medium" for missing and unmatched tracks and "strong" (i.e., no
maximum) for everything else::

    match:
        max_rec:
            missing_tracks: medium
            unmatched_tracks: medium

If a recommendation is higher than the configured maximum and the indicated
penalty is applied, the recommendation is downgraded. The setting for
each field can be one of ``none``, ``low``, ``medium`` or ``strong``. When the
maximum recommendation is ``strong``, no "downgrading" occurs. The available
penalty names here are:

* source
* artist
* album
* media
* mediums
* year
* country
* label
* catalognum
* albumdisambig
* album_id
* tracks
* missing_tracks
* unmatched_tracks
* track_title
* track_artist
* track_index
* track_length
* track_id

.. _preferred:

preferred
~~~~~~~~~

In addition to comparing the tagged metadata with the match metadata for
similarity, you can also specify an ordered list of preferred countries and
media types.

A distance penalty will be applied if the country or media type from the match
metadata doesn't match. The specified values are preferred in descending order
(i.e., the first item will be most preferred). Each item may be a regular
expression, and will be matched case insensitively. The number of media will
be stripped when matching preferred media (e.g. "2x" in "2xCD").

You can also tell the autotagger to prefer matches that have a release year
closest to the original year for an album.

Here's an example::

    match:
        preferred:
            countries: ['US', 'GB|UK']
            media: ['CD', 'Digital Media|File']
            original_year: yes

By default, none of these options are enabled.

.. _ignored:

ignored
~~~~~~~

You can completely avoid matches that have certain penalties applied by adding
the penalty name to the ``ignored`` setting::

    match:
        ignored: missing_tracks unmatched_tracks

The available penalties are the same as those for the :ref:`max_rec` setting.

For example, setting ``ignored: missing_tracks`` will skip any album matches where your audio files are missing some of the tracks. The importer will not attempt to display these matches. It does not ignore the fact that the album is missing tracks, which would allow these matches to apply more easily. To do that, you'll want to adjust the penalty for missing tracks.

.. _required:

required
~~~~~~~~

You can avoid matches that lack certain required information. Add the tags you
want to enforce to the ``required`` setting::

    match:
        required: year label catalognum country

No tags are required by default.

.. _ignored_media:

ignored_media
~~~~~~~~~~~~~

A list of media (i.e., formats) in metadata databases to ignore when matching
music. You can use this to ignore all media that usually contain video instead
of audio, for example::

    match:
        ignored_media: ['Data CD', 'DVD', 'DVD-Video', 'Blu-ray', 'HD-DVD',
                        'VCD', 'SVCD', 'UMD', 'VHS']

No formats are ignored by default.


.. _ignore_data_tracks:

ignore_data_tracks
~~~~~~~~~~~~~~~~~~~

By default, audio files contained in data tracks within a release are included
in the album's tracklist. If you want them to be included, set it ``no``.

Default: ``yes``.

.. _ignore_video_tracks:

ignore_video_tracks
~~~~~~~~~~~~~~~~~~~

By default, video tracks within a release will be ignored. If you want them to
be included (for example if you would like to track the audio-only versions of
the video tracks), set it to ``no``.

Default: ``yes``.

.. _path-format-config:

Path Format Configuration
-------------------------

You can also configure the directory hierarchy beets uses to store music.
These settings appear under the ``paths:`` key. Each string is a template
string that can refer to metadata fields like ``$artist`` or ``$title``. The
filename extension is added automatically. At the moment, you can specify three
special paths: ``default`` for most releases, ``comp`` for "various artist"
releases with no dominant artist, and ``singleton`` for non-album tracks. The
defaults look like this::

    paths:
        default: $albumartist/$album%aunique{}/$track $title
        singleton: Non-Album/$artist/$title
        comp: Compilations/$album%aunique{}/$track $title

Note the use of ``$albumartist`` instead of ``$artist``; this ensures that albums
will be well-organized. For more about these format strings, see
:doc:`pathformat`. The ``aunique{}`` function ensures that identically-named
albums are placed in different directories; see :ref:`aunique` for details.

In addition to ``default``, ``comp``, and ``singleton``, you can condition path
queries based on beets queries (see :doc:`/reference/query`). This means that a
config file like this::

    paths:
        albumtype:soundtrack: Soundtracks/$album/$track $title

will place soundtrack albums in a separate directory. The queries are tested in
the order they appear in the configuration file, meaning that if an item matches
multiple queries, beets will use the path format for the *first* matching query.

Note that the special ``singleton`` and ``comp`` path format conditions are, in
fact, just shorthand for the explicit queries ``singleton:true`` and
``comp:true``. In contrast, ``default`` is special and has no query equivalent:
the ``default`` format is only used if no queries match.


Configuration Location
----------------------

The beets configuration file is usually located in a standard location that
depends on your OS, but there are a couple of ways you can tell beets where to
look.

Environment Variable
~~~~~~~~~~~~~~~~~~~~

First, you can set the ``BEETSDIR`` environment variable to a directory
containing a ``config.yaml`` file. This replaces your configuration in the
default location. This also affects where auxiliary files, like the library
database, are stored by default (that's where relative paths are resolved to).
This environment variable is useful if you need to manage multiple beets
libraries with separate configurations.

Command-Line Option
~~~~~~~~~~~~~~~~~~~

Alternatively, you can use the ``--config`` command-line option to indicate a
YAML file containing options that will then be merged with your existing
options (from ``BEETSDIR`` or the default locations). This is useful if you
want to keep your configuration mostly the same but modify a few options as a
batch. For example, you might have different strategies for importing files,
each with a different set of importer options.

Default Location
~~~~~~~~~~~~~~~~

In the absence of a ``BEETSDIR`` variable, beets searches a few places for
your configuration, depending on the platform:

- On Unix platforms, including OS X:``~/.config/beets`` and then
  ``$XDG_CONFIG_DIR/beets``, if the environment variable is set.
- On OS X, we also search ``~/Library/Application Support/beets`` before the
  Unixy locations.
- On Windows: ``~\AppData\Roaming\beets``, and then ``%APPDATA%\beets``, if
  the environment variable is set.

Beets uses the first directory in your platform's list that contains
``config.yaml``. If no config file exists, the last path in the list is used.


.. _config-example:

Example
-------

Here's an example file::

    directory: /var/mp3
    import:
        copy: yes
        write: yes
        log: beetslog.txt
    art_filename: albumart
    plugins: bpd
    pluginpath: ~/beets/myplugins
    ui:
        color: yes

    paths:
        default: $genre/$albumartist/$album/$track $title
        singleton: Singletons/$artist - $title
        comp: $genre/$album/$track $title
        albumtype:soundtrack: Soundtracks/$album/$track $title

.. only:: man

    See Also
    --------

    ``https://beets.readthedocs.org/``

    :manpage:`beet(1)`
