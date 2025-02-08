BPD Plugin
==========

BPD is a music player using music from a beets library. It runs as a daemon and
implements the MPD protocol, so it's compatible with all the great MPD clients
out there. I'm using `Theremin`_, `gmpc`_, `Sonata`_, and `Ario`_ successfully.

.. _Theremin: https://github.com/TheStalwart/Theremin
.. _gmpc: https://gmpc.wikia.com/wiki/Gnome_Music_Player_Client
.. _Sonata: http://sonata.berlios.de/
.. _Ario: http://ario-player.sourceforge.net/

Dependencies
------------

Before you can use BPD, you'll need the media library called `GStreamer`_ (along
with its Python bindings) on your system.

* On Mac OS X, you can use `Homebrew`_. Run ``brew install gstreamer
  gst-plugins-base pygobject3``.

* On Linux, you need to install GStreamer 1.0 and the GObject bindings for
  python. Under Ubuntu, they are called ``python-gi`` and ``gstreamer1.0``.

You will also need the various GStreamer plugin packages to make everything
work. See the :doc:`/plugins/chroma` documentation for more information on
installing GStreamer plugins.

Once you have system dependencies installed, install ``beets`` with ``bpd``
extra which installs Python bindings for ``GStreamer``:

.. code-block:: console

    pip install "beets[bpd]"

.. _GStreamer: https://gstreamer.freedesktop.org/download
.. _Homebrew: https://brew.sh

Usage
-----

To use the ``bpd`` plugin, first enable it in your configuration (see
:ref:`using-plugins`).
Then, you can run BPD by invoking::

    $ beet bpd

Fire up your favorite MPD client to start playing music. The MPD site has `a
long list of available clients`_. Here are my favorites:

.. _a long list of available clients: https://mpd.wikia.com/wiki/Clients

* Linux: `gmpc`_, `Sonata`_

* Mac: `Theremin`_

* Windows: I don't know. Get in touch if you have a recommendation.

* iPhone/iPod touch: `Rigelian`_

.. _Rigelian: https://www.rigelian.net/

One nice thing about MPD's (and thus BPD's) client-server architecture is that
the client can just as easily on a different computer from the server as it can
be run locally. Control your music from your laptop (or phone!) while it plays
on your headless server box. Rad!

Configuration
-------------

To configure the plugin, make a ``bpd:`` section in your configuration file.
The available options are:

- **host**:
  Default: Bind to all interfaces.
- **port**:
  Default: 6600
- **password**:
  Default: No password.
- **volume**: Initial volume, as a percentage.
  Default: 100
- **control_port**: Port for the internal control socket.
  Default: 6601

Here's an example::

    bpd:
        host: 127.0.0.1
        port: 6600
        password: seekrit
        volume: 100

Implementation Notes
--------------------

In the real MPD, the user can browse a music directory as it appears on disk.
In beets, we like to abstract away from the directory structure. Therefore, BPD
creates a "virtual" directory structure (artist/album/track) to present to
clients. This is static for now and cannot be reconfigured like the real
on-disk directory structure can. (Note that an obvious solution to this is just
string matching on items' destination, but this requires examining the entire
library Python-side for every query.)

BPD plays music using GStreamer's ``playbin`` player, which has a simple API
but doesn't support many advanced playback features.

Differences from the real MPD
-----------------------------

BPD currently supports version 0.16 of `the MPD protocol`_, but several of the
commands and features are "pretend" implementations or have slightly different
behaviour to their MPD equivalents. BPD aims to look enough like MPD that it
can interact with the ecosystem of clients, but doesn't try to be
a fully-fledged MPD replacement in terms of its playback capabilities.

.. _the MPD protocol: https://www.musicpd.org/doc/protocol/

These are some of the known differences between BPD and MPD:

* BPD doesn't currently support versioned playlists. Many clients, however, use
  plchanges instead of playlistinfo to get the current playlist, so plchanges
  contains a dummy implementation that just calls playlistinfo.
* Stored playlists aren't supported (BPD understands the commands though).
* The ``stats`` command always send zero for ``playtime``, which is supposed to
  indicate the amount of time the server has spent playing music. BPD doesn't
  currently keep track of this.
* The ``update`` command regenerates the directory tree from the beets database
  synchronously, whereas MPD does this in the background.
* Advanced playback features like cross-fade, ReplayGain and MixRamp are not
  supported due to BPD's simple audio player backend.
* Advanced query syntax is not currently supported.
* Clients can't use the ``tagtypes`` mask to hide fields.
* BPD's ``random`` mode is not deterministic and doesn't support priorities.
* Mounts and streams are not supported. BPD can only play files from disk.
* Stickers are not supported (although this is basically a flexattr in beets
  nomenclature so this is feasible to add).
* There is only a single password, and is enabled it grants access to all
  features rather than having permissions-based granularity.
* Partitions and alternative outputs are not supported; BPD can only play one
  song at a time.
* Client channels are not implemented.
