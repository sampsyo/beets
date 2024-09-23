ImportHistory Plugin
====================

The ``importhistory`` plugin adds a `source_path` field to every item imported
to the library which stores the original media files' paths. Using this plugin
makes most sense when the general importing workflow is to use ``beet import
--copy``.

Another feature of the plugin is suggesting to delete those original source
files as well whenever items are removed from the Beets library.

To use the ``importhistory`` plugin, enable it in your configuration (see
:ref:`using-plugins`).

`source_path` Usage
-------------------

The first use case of the `source_path` field is in the following scenario: You
imported all of the directories in your current `$PWD`::

    beet import --flat --copy */

Then, something went wrong, and you need to rerun this command. But, you don't
want to tell beets to read again the already successfully imported directories
again. So, you can view which files were successfully imported, using::

    beet ls source_path:$PWD --format='$source_path'

You can of course pipe this command to other standard UNIX utilities::

    # The following prints the directories without the l
    beet ls source_path:$PWD --format='$source_path' | \
      sed "s#$(dirname $PWD)/\([^/]*\)/.*#\1#" | \
      sort -u

The above will print only the directories you successfully finished importing
with `beet import --flat --copy */`.

Removal Suggestion Usage
------------------------

A second use case of the plugin is described in the following scenario: Imagine
you imported an album using::

    beet import --copy --flat ~/Desktop/interesting-album-to-check/

Then you listened to that album and decided it wasn't good and you want to
delete it from your library, and from your `~/Desktop`, so you run::

    beet remove --delete source_path:$HOME/Desktop/interesting-album-to-check

After you'll approve the deletion, this plugin will ask you::

    The item:
    <music-library>/Interesting Album/01 Interesting Song.flac
    is originated from:
    <HOME>/Desktop/interesting-album-to-check/01-interesting-song.flac
    What would you like to do?
    Delete the item's source, Recursively delete the source's directory,
    do Nothing,
    do nothing and Stop suggesting to delete items from this album?

Thus the plugin helps you delete the files from the beets library and from
their source as one.

Configuration
-------------

To configure the plugin, make an ``importhistory:`` section in your
configuration file. There is one option available:

- **suggest_removal**: By default ``importhistory`` suggests to remove the
    original directories / files from which the items were imported whenever
    library items (and files) are removed. To disable these prompts set this
    option to ``no``.
  Default: ``yes``.
