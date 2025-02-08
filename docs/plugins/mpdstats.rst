MPDStats Plugin
================

``mpdstats`` is a plugin for beets that collects statistics about your listening
habits from `MPD`_.  It collects the following information about tracks:

* ``play_count``: The number of times you *fully* listened to this track.
* ``skip_count``: The number of times you *skipped* this track.
* ``last_played``:  UNIX timestamp when you last played this track.
* ``rating``: A rating based on ``play_count`` and ``skip_count``.

To gather these statistics it runs as an MPD client and watches the current state
of MPD. This means that ``mpdstats`` needs to be running continuously for it to
work.

.. _MPD: https://www.musicpd.org/

Installing Dependencies
-----------------------

This plugin requires the python-mpd2 library in order to talk to the MPD
server.

To use the ``mpdstats`` plugin, first enable it in your configuration (see
:ref:`using-plugins`). Then, install ``beets`` with ``mpdstats`` extra

    pip install "beets[mpdstats]"

Usage
-----

Use the ``mpdstats`` command to fire it up::

    $ beet mpdstats

Configuration
-------------

To configure the plugin, make an ``mpd:`` section in your
configuration file. The available options are:

- **host**: The MPD server hostname.
  Default: The ``$MPD_HOST`` environment variable if set,
  falling back to ``localhost`` otherwise.
- **port**: The MPD server port.
  Default: The ``$MPD_PORT`` environment variable if set,
  falling back to 6600 otherwise.
- **password**: The MPD server password.
  Default: None.
- **music_directory**: If your MPD library is at a different location from the
  beets library (e.g., because one is mounted on a NFS share), specify the path
  here.
- **strip_path**: If your MPD library contains local path, specify the part to remove
  here. Combining this with **music_directory** you can mangle MPD path to match the 
  beets library one.
  Default: The beets library directory.
- **rating**: Enable rating updates.
  Default: ``yes``.
- **rating_mix**: Tune the way rating is calculated (see below).
  Default: 0.75.

A Word on Ratings
-----------------

Ratings are calculated based on the *play_count*, *skip_count* and the last
*action* (play or skip).  It consists in one part of a *stable_rating* and in
another part on a *rolling_rating*.  The *stable_rating* is calculated like
this::

    stable_rating = (play_count + 1.0) / (play_count + skip_count + 2.0)

So if the *play_count* equals the *skip_count*, the *stable_rating* is always
0.5.  More *play_counts* adjust the rating up to 1.0.  More *skip_counts*
adjust it down to 0.0.  One of the disadvantages of this rating system, is
that it doesn't really cover *recent developments*.  e.g. a song that you
loved last year and played over 50 times will keep a high rating even if you
skipped it the last 10 times.  That's were the *rolling_rating* comes in.

If a song has been fully played, the *rolling_rating* is calculated like
this::

    rolling_rating = old_rating + (1.0 - old_rating) / 2.0

If a song has been skipped, like this::

    rolling_rating = old_rating - old_rating / 2.0

So *rolling_rating* adapts pretty fast to *recent developments*.  But it's too
fast.  Taking the example from above, your old favorite with 50 plays will get
a negative rating (<0.5) the first time you skip it.  Also not good.

To take the best of both worlds, we mix the ratings together with the
``rating_mix`` factor.  A ``rating_mix`` of 0.0 means all
*rolling* and 1.0 means all *stable*.  We found 0.75 to be a good compromise,
but fell free to play with that.


Warning
-------

This has only been tested with MPD versions >= 0.16.  It may not work
on older versions.  If that is the case, please report an `issue`_.

.. _issue: https://github.com/beetbox/beets/issues
