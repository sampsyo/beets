Path Formats
============

The ``paths:`` section of the config file (see :doc:`config`) lets
you specify the directory and file naming scheme for your music library.
Templates substitute symbols like ``$title`` (any field value prefixed by ``$``)
with the appropriate value from the track's metadata. Beets adds the filename
extension automatically.

For example, consider this path format string:
``$albumartist/$album/$track $title``

Here are some paths this format will generate:

* ``Yeah Yeah Yeahs/It's Blitz!/01 Zero.mp3``

* ``Spank Rock/YoYoYoYoYo/11 Competition.mp3``

* ``The Magnetic Fields/Realism/01 You Must Be Out of Your Mind.mp3``

Because ``$`` is used to delineate a field reference, you can use ``$$`` to emit
a dollars sign. As with `Python template strings`_, ``${title}`` is equivalent
to ``$title``; you can use this if you need to separate a field name from the
text that follows it.

.. _Python template strings: https://docs.python.org/library/string.html#template-strings


A Note About Artists
--------------------

Note that in path formats, you almost certainly want to use ``$albumartist`` and
not ``$artist``. The latter refers to the "track artist" when it is present,
which means that albums that have tracks from different artists on them (like
`Stop Making Sense`_, for example) will be placed into different folders!
Continuing with the Stop Making Sense example, you'll end up with most of the
tracks in a "Talking Heads" directory and one in a "Tom Tom Club" directory. You
probably don't want that! So use ``$albumartist``.

.. _Stop Making Sense:
    https://musicbrainz.org/release/798dcaab-0f1a-4f02-a9cb-61d5b0ddfd36.html

As a convenience, however, beets allows ``$albumartist`` to fall back to the value for ``$artist`` and vice-versa if one tag is present but the other is not.


.. _template-functions:

Template Functions
------------------

Beets path formats also support *function calls*, which can be used to transform
text and perform logical manipulations. The syntax for function calls is like
this: ``%func{arg,arg}``. For example, the ``upper`` function makes its argument
upper-case, so ``%upper{beets rocks}`` will be replaced with ``BEETS ROCKS``.
You can, of course, nest function calls and place variable references in
function arguments, so ``%upper{$artist}`` becomes the upper-case version of the
track's artists.

These functions are built in to beets:

* ``%lower{text}``: Convert ``text`` to lowercase.
* ``%upper{text}``: Convert ``text`` to UPPERCASE.
* ``%capitalize{text}``: Make the first letter of ``text`` UPPERCASE and the rest lowercase.
* ``%title{text}``: Convert ``text`` to Title Case.
* ``%left{text,n}``: Return the first ``n`` characters of ``text``.
* ``%right{text,n}``: Return the last ``n`` characters of  ``text``.
* ``%if{condition,text}`` or ``%if{condition,truetext,falsetext}``: If
  ``condition`` is nonempty (or nonzero, if it's a number), then returns
  the second argument. Otherwise, returns the third argument if specified (or
  nothing if ``falsetext`` is left off).
* ``%asciify{text}``: Convert non-ASCII characters to their ASCII equivalents.
  For example, "café" becomes "cafe". Uses the mapping provided by the
  `unidecode module`_. See the :ref:`asciify-paths` configuration
  option.
* ``%aunique{identifiers,disambiguators,brackets}``: Provides a unique string
  to disambiguate similar albums in the database. See :ref:`aunique`, below.
* ``%sunique{identifiers,disambiguators,brackets}``: Similarly, a unique string
  to disambiguate similar singletons in the database. See :ref:`sunique`, below.
* ``%time{date_time,format}``: Return the date and time in any format accepted
  by `strftime`_. For example, to get the year some music was added to your
  library, use ``%time{$added,%Y}``.
* ``%first{text}``: Returns the first item, separated by ``;`` (a semicolon
  followed by a space).
  You can use ``%first{text,count,skip}``, where ``count`` is the number of
  items (default 1) and ``skip`` is number to skip (default 0). You can also use
  ``%first{text,count,skip,sep,join}`` where ``sep`` is the separator, like
  ``;`` or ``/`` and join is the text to concatenate the items.
* ``%ifdef{field}``, ``%ifdef{field,truetext}`` or
  ``%ifdef{field,truetext,falsetext}``: Checks if an flexible attribute
  ``field`` is defined. If it exists, then return ``truetext`` or ``field``
  (default). Otherwise, returns ``falsetext``. The ``field`` should be entered
  without ``$``. Note that this doesn't work with built-in :ref:`itemfields`, as
  they are always defined.

.. _unidecode module: https://pypi.org/project/Unidecode
.. _strftime: https://docs.python.org/3/library/time.html#time.strftime

Plugins can extend beets with more template functions (see
:ref:`templ_plugins`).


.. _aunique:

Album Disambiguation
--------------------

Occasionally, bands release two albums with the same name (c.f. Crystal Castles,
Weezer, and any situation where a single has the same name as an album or EP).
Beets ships with special support, in the form of the ``%aunique{}`` template
function, to avoid placing two identically-named albums in the same directory on
disk.

The ``aunique`` function detects situations where two albums have some identical
fields and emits text from additional fields to disambiguate the albums. For
example, if you have both Crystal Castles albums in your library, ``%aunique{}``
will expand to "[2008]" for one album and "[2010]" for the other. The
function detects that you have two albums with the same artist and title but
that they have different release years.

For full flexibility, the ``%aunique`` function takes three arguments. The
first two are whitespace-separated lists of album field names: a set of
*identifiers* and a set of *disambiguators*. The third argument is a pair of
characters used to surround the disambiguator.

Any group of albums with identical values for all the identifiers will be
considered "duplicates". Then, the function tries each disambiguator field,
looking for one that distinguishes each of the duplicate albums from each
other. The first such field is used as the result for ``%aunique``. If no field
suffices, an arbitrary number is used to distinguish the two albums.

The default identifiers are ``albumartist album`` and the default
disambiguators are ``albumtype year label catalognum albumdisambig
releasegroupdisambig``. So you can get reasonable disambiguation
behavior if you just use ``%aunique{}`` with no parameters in your
path forms (as in the default path formats), but you can customize the
disambiguation if, for example, you include the year by default in
path formats.

The default characters used as brackets are ``[]``. To change this, provide a
third argument to the ``%aunique`` function consisting of two characters: the left
and right brackets. Or, to turn off bracketing entirely, leave argument blank.

One caveat: When you import an album that is named identically to one already in
your library, the *first* album—the one already in your library— will not
consider itself a duplicate at import time. This means that ``%aunique{}`` will
expand to nothing for this album and no disambiguation string will be used at
its import time. Only the second album will receive a disambiguation string. If
you want to add the disambiguation string to both albums, just run ``beet move``
(possibly restricted by a query) to update the paths for the albums.

.. _sunique:

Singleton Disambiguation
------------------------

It is also possible to have singleton tracks with the same name and the same
artist. Beets provides the ``%sunique{}`` template to avoid giving these
tracks the same file path.

It has the same arguments as the :ref:`%aunique <aunique>` template, but the default
values are different. The default identifiers are ``artist title`` and the
default disambiguators are ``year trackdisambig``.

Syntax Details
--------------

The characters ``$``, ``%``, ``{``, ``}``, and ``,`` are "special" in the path
template syntax. This means that, for example, if you want a ``%`` character to
appear in your paths, you'll need to be careful that you don't accidentally
write a function call. To escape any of these characters (except ``{``, and
``,`` outside a function argument), prefix it with a ``$``.  For example,
``$$`` becomes ``$``; ``$%`` becomes ``%``, etc. The only exceptions are:

* ``${``, which is ambiguous with the variable reference syntax (like
  ``${title}``). To insert a ``{`` alone, it's always sufficient to just type
  ``{``.
* commas are used as argument separators in function calls. Inside of a
  function's argument, use ``$,`` to get a literal ``,`` character. Outside of
  any function argument, escaping is not necessary: ``,`` by itself will
  produce ``,`` in the output.

If a value or function is undefined, the syntax is simply left unreplaced. For
example, if you write ``$foo`` in a path template, this will yield ``$foo`` in
the resulting paths because "foo" is not a valid field name. The same is true of
syntax errors like unclosed ``{}`` pairs; if you ever see template syntax
constructs leaking into your paths, check your template for errors.

If an error occurs in the Python code that implements a function, the function
call will be expanded to a string that describes the exception so you can debug
your template. For example, the second parameter to ``%left`` must be an
integer; if you write ``%left{foo,bar}``, this will be expanded to something
like ``<ValueError: invalid literal for int()>``.


.. _itemfields:

Available Values
----------------

Here's a list of the different values available to path formats. The current
list can be found definitively by running the command ``beet fields``. Note that
plugins can add new (or replace existing) template values (see
:ref:`templ_plugins`).

Ordinary metadata:

* title
* artist
* artist_sort: The "sort name" of the track artist (e.g., "Beatles, The" or
  "White, Jack").
* artist_credit: The track-specific `artist credit`_ name, which may be a
  variation of the artist's "canonical" name.
* album
* albumartist: The artist for the entire album, which may be different from the
  artists for the individual tracks.
* albumartist_sort
* albumartist_credit
* genre
* composer
* grouping
* year, month, day: The release date of the specific release.
* original_year, original_month, original_day: The release date of the original
  version of the album.
* track
* tracktotal
* disc
* disctotal
* lyrics
* comments
* bpm
* comp: Compilation flag.
* albumtype: The MusicBrainz album type; the MusicBrainz wiki has a `list of
  type names`_.
* label
* asin
* catalognum
* script
* language
* country
* albumstatus
* media
* albumdisambig
* disctitle
* encoder

.. _artist credit: https://wiki.musicbrainz.org/Artist_Credit
.. _list of type names: https://musicbrainz.org/doc/Release_Group/Type

Audio information:

* length (in seconds)
* bitrate (in kilobits per second, with units: e.g., "192kbps")
* bitrate_mode (e.g., "CBR", "VBR" or "ABR", only available for the MP3 format)
* encoder_info (e.g., "LAME 3.97.0", only available for some formats)
* encoder_settings (e.g., "-V2", only available for the MP3 format)
* format (e.g., "MP3" or "FLAC")
* channels
* bitdepth (only available for some formats)
* samplerate (in kilohertz, with units: e.g., "48kHz")

MusicBrainz and fingerprint information:

* mb_trackid
* mb_releasetrackid
* mb_albumid
* mb_artistid
* mb_albumartistid
* mb_releasegroupid
* acoustid_fingerprint
* acoustid_id

Library metadata:

* mtime: The modification time of the audio file.
* added: The date and time that the music was added to your library.
* path: The item's filename.


.. _templ_plugins:

Template functions and values provided by plugins
-------------------------------------------------

Beets plugins can provide additional fields and functions to templates. See
the :doc:`/plugins/index` page for a full list of plugins. Some plugin-provided
constructs include:

* ``$missing`` by :doc:`/plugins/missing`: The number of missing tracks per
  album.
* ``%bucket{text}`` by :doc:`/plugins/bucket`: Substitute a string by the
  range it belongs to.
* ``%the{text}`` by :doc:`/plugins/the`: Moves English articles to ends of
  strings.

The :doc:`/plugins/inline` lets you define template fields in your beets
configuration file using Python snippets. And for more advanced processing,
you can go all-in and write a dedicated plugin to register your own fields and
functions (see :ref:`writing-plugins`).
