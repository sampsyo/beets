Getting Started - Beginner Friendly CLI Windows Guide
===============

Welcome to `beets`_! This beginner friendly guide will help you correctly install and configure beets in Windows so you can begin using it to make your music collection better!

Note that this guide is using Windows 11, but following the same steps will also work in Windows 10. 

.. _beets: https://beets.io/

Installing
----------

You will need Python.
Beets works on Python 3.8 or later.

Installing Python 
^^^^^^^^^^^^^^^^^
1. If you don't have it, `install Python`_ (you want at least Python 3.8). If you already have Python properly installed and the path set, you may skip this step.

* Download the appropriate installer for your PC and follow the installation instructions. In this example, I am using the 64-bit installer. 

    .. image:: ../_static/Images/windowsDownload.png
        :width: 600

* Once you have downloaded and launched the installer, select the *Install Now* option, and take care to remember the path its installing to. 

    .. image:: ../_static/Images/pythonDownload.png
        :align: 600
    
* Once the installation is complete, press the Windows key and type *Environment Variables* - select the best match that comes up: Edit the System Envrionment Variables.

    .. image:: ../_static/Images/env.png
        :width: 400

* Select *Environment Variables* at the bottom of the window.

        .. image:: ../_static/Images/environmentV.png
            :width: 600

* This is where the path from earlier comes in. Under the 'User variables' section, double click the ``path`` variable. Then select *New*. Enter the path where you installed Python. Add ``\Scripts\`` at the end. After select OK in both the edit window and the Environment Variables window. 
    
    **IMPORTANT** - If you do not select OK in both windows, it will not save the update and you will have to repeate this step.

        .. image:: ../_static/Images/path.png
            :width: 800
    
Installing beets
^^^^^^^^^^^^^^^^
2.  Press the Windows key and type 'cmd', and then press enter on the Command Prompt. This will open your Command Line Interface. Type ``cd [folder name]`` that you wish to install beets into. Note that you may have to change directories a few times to get to the desired one ex. ``cd users\name\music_library``. For this example, I am saving it to my user so I do not need to change directories. 
 
* Now install beets by running: ``pip install beets``. A successful install will collect and download the included libraries.

    .. image:: ../_static/Images/install.png
        :width: 800

* You're all set! Type ``beet`` at the command prompt to make sure everything's in order. Doing so will bring up a list of helpful commands, as well as the format needed to use them.

    .. image:: ../_static/Images/command.png
        :width: 600

**Optional** - You may also want to install a context menu item for importing files into beets. Download the `beets.reg`_ file and open it in a text file to make sure the paths to Python match your system. Then double-click the file add the necessary keys to your registry. You can then right-click a directory and
choose "Import with beets".

Configuring
-----------

1. You'll want to set a few basic options before you start using beets. The
:doc:`configuration </reference/config>` is stored in a text file. You
can show its location by running ``beet config -p``, though it may not
exist yet. 

**Note:** You will need a text editor for these next steps. If you don't already have one, some popular ones are: `VS Code`_ , `Vim`_, and `Sublime`_. VS Code and Vim are free, but Sublime may come with a price tag. However, if you aren't too keen on downloading one, Windows Notepad will work in this case. 

.. _VS Code: https://code.visualstudio.com 
.. _Vim: https://www.vim.org/download.php 
.. _Sublime: https://www.sublimetext.com 

2. Locate the path to the and open the config.yaml file. You may notice that when you search, that the file does not exist, even though the path does. To fix this, we can manually create the file within the text editor. I am using VS Code in this example. Hover over *File* in the top left corner of the window and select *Open Folder* from the drop down. Select the location that the ``beet config -p`` command returned. Once there, hover over the folder name, and select the little page and plus icon next to it. This will create the new file. We will name this file *config.yaml*. Double check that the config.yaml and the library.db are in the *same* folder. 

    .. image:: ../_static/Images/config.png
        :width: 600

The file will start out empty, but here's a good place to start::

    directory: ~/music
    library: ~/data/musiclibrary.db

3. Change that first path to a directory where you'd like to keep your music. Then,
for ``library``, choose a good place to keep a database file that keeps an index
of your music library. (The config's format is `YAML`_. You'll want to configure your
text editor to use spaces, not real tabs, for indentation. Also, ``~`` means
your home directory in these paths)

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

By following this base config set up, your config file should
look similarly to this.

    .. image:: ../_static/Images/configBase.png
        :width: 800

There are approximately six million other configuration options you can set
here, including the directory and file naming scheme. See
:doc:`/reference/config` for a full reference.

.. _YAML: https://yaml.org/

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

If you've got time and want to tag all your music right once and for all (option b), do
this::

    beet import /path/to/my/music

For this command to work, you must input the full path name. 

(Note that by default, this command will *copy music into the directory you
specified above*. If you want to use your current directory structure, set the
``import.copy`` config option.) 

A successful import will look as follows:

    .. image:: ../_static/Images/firstImport.png
        :width: 600

Once imported, follow the prompts in the CLI to tag the music as you see fit. 

To take the fast, un-autotagged path (option a), just say::

    beet import -A /my/huge/mp3/library

Note that you just need to add ``-A`` for "don't autotag" option.

Adding More Music
-----------------

If you've ripped or... otherwise obtained some new music, you can add it with
the ``beet import`` command, the same way you imported your library. Like so::

    beet import ~/some_great_album

This will attempt to autotag the new album (interactively) and add it to your
library. There are, of course, more options for this command---just type ``beet help import`` to see what's available.

Seeing Your Music
-----------------

If you want to query your music library, the ``beet list`` (shortened to ``beet
ls``) command is for you. You give it a :doc:`query string </reference/query>`,
which is formatted something like a Google search, and it gives you a list of
songs.  Thus::

    beet ls the magnetic fields
    The Magnetic Fields - Distortion - Three-Way
    The Magnetic Fields - Distortion - California Girls
    The Magnetic Fields - Distortion - Old Fools
    beet ls hissing gronlandic
    of Montreal - Hissing Fauna, Are You the Destroyer? - Gronlandic Edit
    beet ls bird
    The Knife - The Knife - Bird
    The Mae Shi - Terrorbird - Revelation Six
    beet ls album:bird
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

    beet ls -a forever
    Bon Iver - For Emma, Forever Ago
    Freezepop - Freezepop Forever

There's also an ``-f`` option (for *format*) that lets you specify what gets displayed in the results of a search::

    beet ls -a forever -f "[format] album (year) - artist - title"
    [MP3] For Emma, Forever Ago (2009) - Bon Iver - Flume
    [AAC] Freezepop Forever (2011) - Freezepop - Harebrained Scheme

In the format option, field references like `$format` and `$year` are filled
in with data from each result. You can see a full list of available fields by
running ``beet fields``.

Beets also has a ``stats`` command, just in case you want to see how much music
you have::

    beet stats
    Tracks: 13019
    Total time: 4.9 weeks
    Total size: 71.1 GB
    Artists: 548
    Albums: 1094

An example of some of these commands will look like this:

    .. image:: ../_static/Images/extraCommands.png
        :width: 600

If you need more of a walkthrough on configuring and importing libraries, you can read a more in depth and illustrated one `on the
beets blog <https://beets.io/blog/walkthrough.html>`_.

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
command lists all the available commands; then, for example, ``beet help import`` gives more specific help about the ``import`` command.

Want to stay updated on beets? Follow `@b33ts`_ on Twitter to hear about progress on
new versions.

.. _@b33ts: https://twitter.com/b33ts

Please let us know what you think of beets via `the discussion board`_ or
`Mastodon`_.

.. _the mailing list: https://groups.google.com/group/beets-users
.. _the discussion board: https://github.com/beetbox/beets/discussions
.. _mastodon: https://fosstodon.org/@beets
