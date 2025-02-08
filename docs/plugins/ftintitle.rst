FtInTitle Plugin
================

The ``ftintitle`` plugin automatically moves "featured" artists from the
``artist`` field to the ``title`` field.

According to `MusicBrainz style`_, featured artists are part of the artist
field. That means that, if you tag your music using MusicBrainz, you'll have
tracks in your library like "Tellin' Me Things" by the artist "Blakroc feat.
RZA". If you prefer to tag this as "Tellin' Me Things feat. RZA" by "Blakroc",
then this plugin is for you.

To use the ``ftintitle`` plugin, enable it in your configuration
(see :ref:`using-plugins`).

Configuration
-------------

To configure the plugin, make a ``ftintitle:`` section in your configuration
file. The available options are:

- **auto**: Enable metadata rewriting during import.
  Default: ``yes``.
- **drop**: Remove featured artists entirely instead of adding them to the
  title field.
  Default: ``no``.
- **format**: Defines the format for the featuring X  part of the new title field.
  In this format the ``{0}`` is used to define where the featured artists are placed.
  Default: ``feat. {0}``
- **keep_in_artist**: Keep the featuring X part in the artist field. This can
  be useful if you still want to be able to search for features in the artist
  field.
  Default: ``no``.

Running Manually
----------------

From the command line, type::

    $ beet ftintitle [QUERY]

The query is optional; if it's left off, the transformation will be applied to
your entire collection.

Use the ``-d`` flag to remove featured artists (equivalent of the ``drop``
config option).

.. _MusicBrainz style: https://musicbrainz.org/doc/Style
