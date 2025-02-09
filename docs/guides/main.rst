Getting Started
===============

Welcome to `beets`_! This guide will help you begin using it to make your music
collection better.

New to the CLI? Check out our :doc:`beginner friendly</guides/beginnerCLI>` getting started guide for Windows!

.. _beets: https://beets.io/

Installing
----------

You will need Python.
Beets works on Python 3.8 or later.

* **macOS** 11 (Big Sur) includes Python 3.8 out of the box.
  You can opt for a more recent Python installing it via `Homebrew`_
  (``brew install python3``).
  There's also a `MacPorts`_ port. Run ``port install beets`` or
  ``port install beets-full`` to include many third-party plugins.

* On **Debian or Ubuntu**, depending on the version, beets is available as an
  official package (`Debian details`_, `Ubuntu details`_), so try typing:
  ``apt-get install beets``. But the version in the repositories might lag
  behind, so make sure you read the right version of these docs. If you want
  the latest version, you can get everything you need to install with pip
  as described below by running:
  ``apt-get install python-dev python-pip``

* On **Arch Linux**, `beets is in [community] <Arch community_>`_, so just run ``pacman -S
  beets``. (There's also a bleeding-edge `dev package <AUR_>`_ in the AUR, which will
  probably set your computer on fire.)

* On **Alpine Linux**, `beets is in the community repository <Alpine package_>`_
  and can be installed with ``apk add beets``.

* For **Gentoo Linux**, beets is in Portage as ``media-sound/beets``. Just run
  ``emerge beets`` to install. There are several USE flags available for
  optional plugin dependencies.

* On **FreeBSD**, there's a `beets port <FreeBSD_>`_ at ``audio/beets``.

* On **OpenBSD**, there's a `beets port <OpenBSD_>`_ can be installed with ``pkg_add beets``.

* For **Slackware**, there's a `SlackBuild`_ available.

* On **Fedora** 22 or later, there's a `DNF package`_ you can install with ``sudo dnf install beets beets-plugins beets-doc``.

* On **Solus**, run ``eopkg install beets``.

* On **NixOS**, there's a `package <NixOS_>`_ you can install with ``nix-env -i beets``.

.. _DNF package: https://packages.fedoraproject.org/pkgs/beets/
.. _SlackBuild: https://slackbuilds.org/repository/14.2/multimedia/beets/
.. _FreeBSD: http://portsmon.freebsd.org/portoverview.py?category=audio&portname=beets
.. _AUR: https://aur.archlinux.org/packages/beets-git/
.. _Debian details: https://tracker.debian.org/pkg/beets
.. _Ubuntu details: https://launchpad.net/ubuntu/+source/beets
.. _OpenBSD: http://openports.se/audio/beets
.. _Arch community: https://www.archlinux.org/packages/community/any/beets/
.. _Alpine package: https://pkgs.alpinelinux.org/package/edge/community/x86_64/beets
.. _NixOS: https://github.com/NixOS/nixpkgs/tree/master/pkgs/tools/audio/beets
.. _MacPorts: https://www.macports.org

If you have `pip`_, just say ``pip install beets`` (or ``pip install --user
beets`` if you run into permissions problems).

To install without pip, download beets from `its PyPI page`_ and run ``python
setup.py install`` in the directory therein.

.. _its PyPI page: https://pypi.org/project/beets/#files
.. _pip: https://pip.pypa.io

The best way to upgrade beets to a new version is by running ``pip install -U
beets``. You may want to follow `@b33ts`_ on Twitter to hear about progress on
new versions.

.. _@b33ts: https://twitter.com/b33ts

Installing by Hand on macOS 10.11 and Higher
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Starting with version 10.11 (El Capitan), macOS has a new security feature
called `System Integrity Protection`_ (SIP) that prevents you from modifying
some parts of the system. This means that some ``pip`` commands may fail with a
permissions error. (You probably *won't* run into this if you've installed
Python yourself with `Homebrew`_ or otherwise. You can also try `MacPorts`_.)

If this happens, you can install beets for the current user only by typing
``pip install --user beets``. If you do that, you might want to add
``~/Library/Python/3.6/bin`` to your ``$PATH``.

.. _System Integrity Protection: https://support.apple.com/en-us/HT204899
.. _Homebrew: https://brew.sh

Installing on Windows
^^^^^^^^^^^^^^^^^^^^^

Installing beets on Windows can be tricky. Following these steps might help you
get it right:

1. If you don't have it, `install Python`_ (you want at least Python 3.8). The
   installer should give you the option to "add Python to PATH." Check this
   box. If you do that, you can skip the next step.

2. If you haven't done so already, set your ``PATH`` environment variable to
   include Python and its scripts. To do so, open the "Settings" application, 
   then access the "System" screen, then access the "About" tab, and then hit 
   "Advanced system settings" located on the right side of the screen. This 
   should open the "System Properties" screen, then select the "Advanced" tab, 
   then hit the "Environmental Variables..." button, and then look for the PATH 
   variable in the table. Add the following to the end of the variable's value: 
   ``;C:\Python38;C:\Python38\Scripts``. You may need to adjust these paths to 
   point to your Python installation.

3. Now install beets by running: ``pip install beets``

4. You're all set! Type ``beet`` at the command prompt to make sure everything's
   in order.

Windows users may also want to install a context menu item for importing files
into beets. Download the `beets.reg`_ file and open it in a text file to make
sure the paths to Python match your system. Then double-click the file add the
necessary keys to your registry. You can then right-click a directory and
choose "Import with beets".

Because I don't use Windows myself, I may have missed something. If you have
trouble or you have more detail to contribute here, please direct it to
`the mailing list`_.

.. _install Python: https://python.org/download/
.. _beets.reg: https://github.com/beetbox/beets/blob/master/extra/beets.reg
.. _install pip: https://pip.pypa.io/en/stable/installing/
.. _get-pip.py: https://bootstrap.pypa.io/get-pip.py

Installing on ARM (Raspberry Pi and similar)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Beets on ARM devices is not recommended for Linux novices. If you are
comfortable with light troubleshooting in tools like ``pip``, ``make``,
and beets' command-line binary dependencies (e.g. ``ffmpeg`` and
``ImageMagick``), you will probably be okay on ARM devices like the
Raspberry Pi. We have `notes for ARM`_ and an `older ARM reference`_.
Beets is generally developed on x86-64 based devices, and most plugins
target that platform as well.

.. _notes for ARM: https://github.com/beetbox/beets/discussions/4910
.. _older ARM reference: https://discourse.beets.io/t/diary-of-beets-on-arm-odroid-hc4-armbian/1993

Configuring
-----------

You'll want to set a few basic options before you start using beets. The
:doc:`configuration </reference/config>` is stored in a text file. You
can show its location by running ``beet config -p``, though it may not
exist yet. Run ``beet config -e`` to edit the configuration in your
favorite text editor. The file will start out empty, but here's good
place to start::

    directory: ~/music
    library: ~/data/musiclibrary.db

Change that first path to a directory where you'd like to keep your music. Then,
for ``library``, choose a good place to keep a database file that keeps an index
of your music. (The config's format is `YAML`_. You'll want to configure your
text editor to use spaces, not real tabs, for indentation. Also, ``~`` means
your home directory in these paths, even on Windows.)

The default configuration assumes you want to start a new organized music folder
(that ``directory`` above) and that you'll *copy* cleaned-up music into that
empty folder using beets' ``import`` command (see below). But you can configure
beets to behave many other ways:

* Start with a new empty directory, but *move* new music in instead of copying
  it (saving disk space). Put this in your config file::

        import:
            move: yes

* Keep your current directory structure; importing should never move or copy
  files but instead just correct the tags on music. Put the line ``copy: no``
  under the ``import:`` heading in your config file to disable any copying or
  renaming. Make sure to point ``directory`` at the place where your music is
  currently stored.

* Keep your current directory structure and *do not* correct files' tags: leave
  files completely unmodified on your disk. (Corrected tags will still be stored
  in beets' database, and you can use them to do renaming or tag changes later.)
  Put this in your config file::

        import:
            copy: no
            write: no

  to disable renaming and tag-writing.

There are approximately six million other configuration options you can set
here, including the directory and file naming scheme. See
:doc:`/reference/config` for a full reference.

.. _YAML: https://yaml.org/

To check that you've set up your configuration how you want it, you can type
``beet version`` to see a list of enabled plugins or ``beet config`` to get a
complete listing of your current configuration.


Importing Your Library
----------------------

The next step is to import your music files into the beets library database.
Because this can involve modifying files and moving them around, data loss is
always a possibility, so now would be a good time to make sure you have a
recent backup of all your music. We'll wait.

There are two good ways to bring your existing library into beets. You can
either: (a) quickly bring all your files with all their current metadata into
beets' database, or (b) use beets' highly-refined autotagger to find canonical
metadata for every album you import. Option (a) is really fast, but option (b)
makes sure all your songs' tags are exactly right from the get-go. The point
about speed bears repeating: using the autotagger on a large library can take a
very long time, and it's an interactive process. So set aside a good chunk of
time if you're going to go that route. For more on the interactive
tagging process, see :doc:`tagger`.

If you've got time and want to tag all your music right once and for all, do
this::

    $ beet import /path/to/my/music

(Note that by default, this command will *copy music into the directory you
specified above*. If you want to use your current directory structure, set the
``import.copy`` config option.) To take the fast,
un-autotagged path, just say::

    $ beet import -A /my/huge/mp3/library

Note that you just need to add ``-A`` for "don't autotag".

Adding More Music
-----------------

If you've ripped or... otherwise obtained some new music, you can add it with
the ``beet import`` command, the same way you imported your library. Like so::

    $ beet import ~/some_great_album

This will attempt to autotag the new album (interactively) and add it to your
library. There are, of course, more options for this command---just type ``beet
help import`` to see what's available.

Seeing Your Music
-----------------

If you want to query your music library, the ``beet list`` (shortened to ``beet
ls``) command is for you. You give it a :doc:`query string </reference/query>`,
which is formatted something like a Google search, and it gives you a list of
songs.  Thus::

    $ beet ls the magnetic fields
    The Magnetic Fields - Distortion - Three-Way
    The Magnetic Fields - Distortion - California Girls
    The Magnetic Fields - Distortion - Old Fools
    $ beet ls hissing gronlandic
    of Montreal - Hissing Fauna, Are You the Destroyer? - Gronlandic Edit
    $ beet ls bird
    The Knife - The Knife - Bird
    The Mae Shi - Terrorbird - Revelation Six
    $ beet ls album:bird
    The Mae Shi - Terrorbird - Revelation Six

By default, a search term will match any of a handful of :ref:`common
attributes <keywordquery>` of songs.
(They're
also implicitly joined by ANDs: a track must match *all* criteria in order to
match the query.) To narrow a search term to a particular metadata field, just
put the field before the term, separated by a : character. So ``album:bird``
only looks for ``bird`` in the "album" field of your songs. (Need to know more?
:doc:`/reference/query/` will answer all your questions.)

The ``beet list`` command also has an ``-a`` option, which searches for albums instead of songs::

    $ beet ls -a forever
    Bon Iver - For Emma, Forever Ago
    Freezepop - Freezepop Forever

There's also an ``-f`` option (for *format*) that lets you specify what gets displayed in the results of a search::

    $ beet ls -a forever -f "[$format] $album ($year) - $artist - $title"
    [MP3] For Emma, Forever Ago (2009) - Bon Iver - Flume
    [AAC] Freezepop Forever (2011) - Freezepop - Harebrained Scheme

In the format option, field references like `$format` and `$year` are filled
in with data from each result. You can see a full list of available fields by
running ``beet fields``.

Beets also has a ``stats`` command, just in case you want to see how much music
you have::

    $ beet stats
    Tracks: 13019
    Total time: 4.9 weeks
    Total size: 71.1 GB
    Artists: 548
    Albums: 1094

Keep Playing
------------

This is only the beginning of your long and prosperous journey with beets. To
keep learning, take a look at :doc:`advanced` for a sampling of what else
is possible. You'll also want to glance over the :doc:`/reference/cli` page
for a more detailed description of all of beets' functionality.  (Like
deleting music! That's important.)

Also, check out :doc:`beets' plugins </plugins/index>`.  The
real power of beets is in its extensibility---with plugins, beets can do almost
anything for your music collection.

You can always get help using the ``beet help`` command. The plain ``beet help``
command lists all the available commands; then, for example, ``beet help
import`` gives more specific help about the ``import`` command.

If you need more of a walkthrough, you can read an illustrated one `on the
beets blog <https://beets.io/blog/walkthrough.html>`_.

Please let us know what you think of beets via `the discussion board`_ or
`Mastodon`_.

.. _the mailing list: https://groups.google.com/group/beets-users
.. _the discussion board: https://github.com/beetbox/beets/discussions
.. _mastodon: https://fosstodon.org/@beets
