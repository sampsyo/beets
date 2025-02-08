Scrub Plugin
=============

The ``scrub`` plugin lets you remove extraneous metadata from files' tags. If
you'd prefer never to see crufty tags that come from other tools, the plugin can
automatically remove all non-beets-tracked tags whenever a file's metadata is
written to disk by removing the tag entirely before writing new data. The plugin
also provides a command that lets you manually remove files' tags.

Automatic Scrubbing
-------------------

To automatically remove files' tags before writing new ones, enable ``scrub``
plugin in your configuration (see :ref:`using-plugins`) and install ``beets``
with ``scrub`` extra

.. code-block:: bash

    pip install "beets[scrub]"

When importing new files (with ``import.write`` turned on) or modifying files'
tags with the ``beet modify`` command, beets will first strip all types of tags
entirely and then write the database-tracked metadata to the file.

This behavior can be disabled with the ``auto`` config option (see below).

Manual Scrubbing
----------------

The ``scrub`` command provided by this plugin removes tags from files and then
rewrites their database-tracked metadata. To run it, just type ``beet scrub
QUERY`` where ``QUERY`` matches the tracks to be scrubbed. Use this command with
caution, however, because any information in the tags that is out of sync with
the database will be lost.

The ``-W`` (or ``--nowrite``) option causes the command to just remove tags but
not restore any information. This will leave the files with no metadata
whatsoever.

Configuration
-------------

To configure the plugin, make a ``scrub:`` section in your
configuration file. There is one option:

- **auto**: Enable metadata stripping during import.
  Default: ``yes``.
