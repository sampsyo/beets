Advanced Awesomeness
====================

So you have beets up and running and you've started :doc:`importing your
music </guides/tagger>`. There's a lot more that beets can do now that it has
cataloged your collection. Here's a few features to get you started.

Most of these tips involve :doc:`plugins </plugins/index>` and fiddling with
beets' :doc:`configuration </reference/config>`. So use your favorite text
editor to create a config file before you continue.


Fetch album art, genres, and lyrics
-----------------------------------

Beets can help you fill in more than just the basic taxonomy metadata that
comes from MusicBrainz. Plugins can provide :doc:`album art
</plugins/fetchart>`, :doc:`lyrics </plugins/lyrics>`, and
:doc:`genres </plugins/lastgenre>` from databases around the Web.

If you want beets to get any of this data automatically during the import
process, just enable any of the three relevant plugins (see
:doc:`/plugins/index`). For example, put this line in your :doc:`config file
</reference/config>` to enable all three::

    plugins: fetchart lyrics lastgenre

Each plugin also has a command you can run to fetch data manually. For
example, if you want to get lyrics for all the Beatles tracks in your
collection, just type ``beet lyrics beatles`` after enabling the plugin.

Read more about using each of these plugins:

* :doc:`/plugins/fetchart` (and its accompanying :doc:`/plugins/embedart`)
* :doc:`/plugins/lyrics`
* :doc:`/plugins/lastgenre`


Customize your file and folder names
------------------------------------

Beets uses an extremely flexible template system to name the folders and files
that organize your music in your filesystem. Take a look at
:ref:`path-format-config` for the basics: use fields like ``$year`` and
``$title`` to build up a naming scheme. But if you need more flexibility,
there are two features you need to know about:

* :ref:`Template functions <template-functions>` are simple expressions you
  can use in your path formats to add logic to your names. For example, you
  can get an artist's first initial using ``%upper{%left{$albumartist,1}}``.
* If you need more flexibility, the :doc:`/plugins/inline` lets you write
  snippets of Python code that generate parts of your filenames. The
  equivalent code for getting an artist initial with the *inline* plugin looks
  like ``initial: albumartist[0].upper()``.

If you already have music in your library and want to update their names
according to a new scheme, just run the :ref:`move-cmd` command to rename
everything.


Stream your music to another computer
-------------------------------------

Sometimes it can be really convenient to store your music on one machine and
play it on another. For example, I like to keep my music on a server at home,
but play it at work (without copying my whole library locally). The
:doc:`/plugins/web` makes streaming your music easy---it's sort of like having
your own personal Spotify.

First, enable the ``web`` plugin (see :doc:`/plugins/index`). Run the server by
typing ``beet web`` and head to http://localhost:8337 in a browser. You can
browse your collection with queries and, if your browser supports it, play
music using HTML5 audio.

Transcode music files for media players
---------------------------------------

Do you ever find yourself transcoding high-quality rips to a lower-bitrate,
lossy format for your phone or music player? Beets can help with that.

You'll first need to install `ffmpeg`_. Then, enable beets'
:doc:`/plugins/convert`. Set a destination directory in your
:doc:`config file </reference/config>` like so::

    convert:
        dest: ~/converted_music

Then, use the command ``beet convert QUERY`` to transcode everything matching
the query and drop the resulting files in that directory, named according to
your path formats. For example, ``beet convert long winters`` will move over
everything by the Long Winters for listening on the go.

The plugin has many more dials you can fiddle with to get your conversions how
you like them. Check out :doc:`its documentation </plugins/convert>`.

.. _ffmpeg: https://www.ffmpeg.org


Store any data you like
-----------------------

The beets database keeps track of a long list of :ref:`built-in fields
<itemfields>`, but you're not limited to just that list. Say, for example,
that you like to categorize your music by the setting where it should be
played. You can invent a new ``context`` attribute to store this. Set the field
using the :ref:`modify-cmd` command::

    beet modify context=party artist:'beastie boys'

By default, beets will show you the changes that are about to be applied and ask
if you really want to apply them to all, some or none of the items or albums.
You can type y for "yes", n for "no", or s for "select". If you choose the latter,
the command will prompt you for each individual matching item or album.

Then :doc:`query </reference/query>` your music just as you would with any
other field::

    beet ls context:mope

You can even use these fields in your filenames (see
:ref:`path-format-config`).

And, unlike :ref:`built-in fields <itemfields>`, such fields can be removed::

    beet modify context! artist:'beastie boys'

Read more than you ever wanted to know about the *flexible attributes*
feature `on the beets blog`_.

.. _on the beets blog: https://beets.io/blog/flexattr.html


Choose a path style manually for some music
-------------------------------------------

Sometimes, you need to categorize some songs differently in your file system.
For example, you might want to group together all the music you don't really
like, but keep around to play for friends and family. This is, of course,
impossible to determine automatically using metadata from MusicBrainz.

Instead, use a flexible attribute (see above) to store a flag on the music you
want to categorize, like so::

    beet modify bad=1 christmas

Then, you can query on this field in your path formats to sort this music
differently. Put something like this in your configuration file::

    paths:
        bad:1: Bad/$artist/$title

Used together, flexible attributes and path format conditions let you sort
your music by any criteria you can imagine.


Automatically add new music to your library
-------------------------------------------

As a command-line tool, beets is perfect for automated operation via a cron job
or the like. To use it this way, you might want to use these options in your
:doc:`config file </reference/config>`:

.. code-block:: yaml

    import:
        incremental: yes
        quiet: yes
        log: /path/to/log.txt

The :ref:`incremental` option will skip importing any directories that have
been imported in the past.
:ref:`quiet` avoids asking you any questions (since this will be run
automatically, no input is possible).
You might also want to use the :ref:`quiet_fallback` options to configure
what should happen when no near-perfect match is found -- this option depends
on your level of paranoia.
Finally, :ref:`import_log` will make beets record its decisions so you can come
back later and see what you need to handle manually.

The last step is to set up cron or some other automation system to run
``beet import /path/to/incoming/music``.


Useful reports
--------------

Since beets has a quite powerful query tool, this list contains some useful and
powerful queries to run on your library.

* See a list of all albums which have files which are 128 bit rate::

      beet list bitrate:128000

* See a list of all albums with the tracks listed in order of bit rate::

      beet ls -f '$bitrate $artist - $title' bitrate+

* See a list of albums and their formats::

      beet ls -f '$albumartist $album $format' | sort | uniq

  Note that ``beet ls --album -f '... $format'`` doesn't do what you want,
  because ``format`` is an item-level field, not an album-level one.
  If an album's tracks exist in multiple formats, the album will appear in the
  list once for each format.
