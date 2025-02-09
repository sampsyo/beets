Using the Auto-Tagger
=====================

Beets' automatic metadata correcter is sophisticated but complicated and
cryptic. This is a guide to help you through its myriad inputs and options.

An Apology and a Brief Interlude
--------------------------------

I would like to sincerely apologize that the autotagger in beets is so fussy. It
asks you a *lot* of complicated questions, insecurely asking that you verify
nearly every assumption it makes. This means importing and correcting the tags
for a large library can be an endless, tedious process. I'm sorry for this.

Maybe it will help to think of it as a tradeoff. By carefully examining every
album you own, you get to become more familiar with your library, its extent,
its variation, and its quirks. People used to spend hours lovingly sorting and
resorting their shelves of LPs. In the iTunes age, many of us toss our music
into a heap and forget about it. This is great for some people. But there's
value in intimate, complete familiarity with your collection. So instead of a
chore, try thinking of correcting tags as quality time with your music
collection. That's what I do.

One practical piece of advice: because beets' importer runs in multiple threads,
it queues up work in the background while it's waiting for you to respond. So if
you find yourself waiting for beets for a few seconds between every question it
asks you, try walking away from the computer for a while, making some tea, and
coming back. Beets will have a chance to catch up with you and will ask you
questions much more quickly.

Back to the guide.

Overview
--------

Beets' tagger is invoked using the ``beet import`` command. Point it at a
directory and it imports the files into your library, tagging them as it goes
(unless you pass ``--noautotag``, of course). There are several assumptions
beets currently makes about the music you import. In time, we'd like to remove
all of these limitations.

* Your music should be organized by album into directories. That is, the tagger
  assumes that each album is in a single directory. These directories can be
  arbitrarily deep (like ``music/2010/hiphop/seattle/freshespresso/glamour``),
  but any directory with music files in it is interpreted as a separate album.

  There are, however, a couple of exceptions to this rule:

  First, directories that look like separate parts of a *multi-disc album* are
  tagged together as a single release. If two adjacent albums have a common
  prefix, followed by "disc," "disk," or "CD" and then a number, they are
  tagged together.

  Second, if you have jumbled directories containing more than one album, you
  can ask beets to split them apart for you based on their metadata. Use
  either the ``--group-albums`` command-line flag or the *G* interactive
  option described below.

* The music may have bad tags, but it's not completely untagged. This is
  because beets by default infers tags based on existing metadata. But this is
  not a hard and fast rule---there are a few ways to tag metadata-poor music:

    * You can use the *E* or *I* options described below to search in
      MusicBrainz for a specific album or song.
    * The :doc:`Acoustid plugin </plugins/chroma>` extends the autotagger to
      use acoustic fingerprinting to find information for arbitrary audio.
      Install that plugin if you're willing to spend a little more CPU power
      to get tags for unidentified albums. (But be aware that it does slow
      down the process.)
    * The :doc:`FromFilename plugin </plugins/fromfilename>` adds the ability
      to guess tags from the filenames. Use this plugin if your tracks have
      useful names (like "03 Call Me Maybe.mp3") but their tags don't reflect
      that.

* Currently, MP3, AAC, FLAC, ALAC, Ogg Vorbis, Monkey's Audio, WavPack,
  Musepack, Windows Media, Opus, and AIFF files are supported. (Do you use
  some other format? Please `file a feature request`_!)

.. _file a feature request:
   https://github.com/beetbox/beets/issues/new?template=feature-request.md

Now that that's out of the way, let's tag some music.

.. _import-options:

Options
-------

To import music, just say ``beet import MUSICDIR``. There are, of course, a few
command-line options you should know:

* ``beet import -A``: don't try to autotag anything; just import files (this
  goes much faster than with autotagging enabled)

* ``beet import -W``: when autotagging, don't write new tags to the files
  themselves (just keep the new metadata in beets' database)

* ``beet import -C``: don't copy imported files to your music directory; leave
  them where they are

* ``beet import -m``: move imported files to your music directory (overrides
  the ``-c`` option)

* ``beet import -l LOGFILE``: write a message to ``LOGFILE`` every time you skip
  an album or choose to take its tags "as-is" (see below) or the album is
  skipped as a duplicate; this lets you come back later and reexamine albums
  that weren't tagged successfully. Run ``beet import --from-logfile=LOGFILE``
  rerun the importer on such paths from the logfile.

* ``beet import -q``: quiet mode. Never prompt for input and, instead,
  conservatively skip any albums that need your opinion. The ``-ql`` combination
  is recommended.

* ``beet import -t``: timid mode, which is sort of the opposite of "quiet." The
  importer will ask your permission for everything it does, confirming even very
  good matches with a prompt.

* ``beet import -p``: automatically resume an interrupted import. The importer
  keeps track of imports that don't finish completely (either due to a crash or
  because you stop them halfway through) and, by default, prompts you to decide
  whether to resume them. The ``-p`` flag automatically says "yes" to this
  question. Relatedly, ``-P`` flag automatically says "no."

* ``beet import -s``: run in *singleton* mode, tagging individual tracks instead
  of whole albums at a time. See the "as Tracks" choice below.  This means you
  can use ``beet import -AC`` to quickly add a bunch of files to your library
  without doing anything to them.

* ``beet import -g``: assume there are multiple albums contained in each
  directory. The tracks contained a directory are grouped by album artist and
  album name and you will be asked to import each of these groups separately.
  See the "Group albums" choice below.

Similarity
----------

So you import an album into your beets library. It goes like this::

    $ beet imp witchinghour
    Tagging:
        Ladytron - Witching Hour
    (Similarity: 98.4%)
    * Last One Standing      -> The Last One Standing
    * Beauty                 -> Beauty*2
    * White Light Generation -> Whitelightgenerator
    * All the Way            -> All the Way...

Here, beets gives you a preview of the album match it has found. It shows you
which track titles will be changed if the match is applied. In this case, beets
has found a match and thinks it's a good enough match to proceed without asking
your permission. It has reported the *similarity* for the match it's found.
Similarity is a measure of how well-matched beets thinks a tagging option is.
100% similarity means a perfect match 0% indicates a truly horrible match.

In this case, beets has proceeded automatically because it found an option with
very high similarity (98.4%). But, as you'll notice, if the similarity isn't
quite so high, beets will ask you to confirm changes. This is because beets
can't be very confident about more dissimilar matches, and you (as a human) are
better at making the call than a computer. So it occasionally asks for help.

Choices
-------

When beets needs your input about a match, it says something like this::

    Tagging:
        Beirut - Lon Gisland
    (Similarity: 94.4%)
    * Scenic World (Second Version) -> Scenic World
    [A]pply, More candidates, Skip, Use as-is, as Tracks, Enter search, enter Id, or aBort?

When beets asks you this question, it wants you to enter one of the capital
letters: A, M, S, U, T, G, E, I or B. That is, you can choose one of the
following:

* *A*: Apply the suggested changes shown and move on.

* *M*: Show more options. (See the Candidates section, below.)

* *S*: Skip this album entirely and move on to the next one.

* *U*: Import the album without changing any tags. This is a good option for
  albums that aren't in the MusicBrainz database, like your friend's operatic
  faux-goth solo record that's only on two CD-Rs in the universe.

* *T*: Import the directory as *singleton* tracks, not as an album. Choose this
  if the tracks don't form a real release---you just have one or more loner
  tracks that aren't a full album. This will temporarily flip the tagger into
  *singleton* mode, which attempts to match each track individually.

* *G*: Group tracks in this directory by *album artist* and *album* and import
  groups as albums. If the album artist for a track is not set then the artist
  is used to group that track. For each group importing proceeds as for
  directories. This is helpful if a directory contains multiple albums.

* *E*: Enter an artist and album to use as a search in the database. Use this
  option if beets hasn't found any good options because the album is mistagged
  or untagged.

* *I*: Enter a metadata backend ID to use as search in the database. Use this
  option to specify a backend entity (for example, a MusicBrainz release or
  recording) directly, by pasting its ID or the full URL. You can also specify
  several IDs by separating them by a space.

* *B*: Cancel this import task altogether. No further albums will be tagged;
  beets shuts down immediately. The next time you attempt to import the same
  directory, though, beets will ask you if you want to resume tagging where you
  left off.

Note that the option with ``[B]rackets`` is the default---so if you want to
apply the changes, you can just hit return without entering anything.

Candidates
----------

If you choose the M option, or if beets isn't very confident about any of the
choices it found, it will present you with a list of choices (called
candidates), like so::

    Finding tags for "Panther - Panther".
    Candidates:
    1. Panther - Yourself (66.8%)
    2. Tav Falco's Panther Burns - Return of the Blue Panther (30.4%)
    # selection (default 1), Skip, Use as-is, or Enter search, or aBort?

Here, you have many of the same options as before, but you can also enter a
number to choose one of the options that beets has found. Don't worry about
guessing---beets will show you the proposed changes and ask you to confirm
them, just like the earlier example. As the prompt suggests, you can just hit
return to select the first candidate.

.. _guide-duplicates:

Duplicates
----------

If beets finds an album or item in your library that seems to be the same as the
one you're importing, you may see a prompt like this::

    This album is already in the library!
    [S]kip new, Keep all, Remove old, Merge all?

Beets wants to keep you safe from duplicates, which can be a real pain, so you
have four choices in this situation. You can skip importing the new music,
choosing to keep the stuff you already have in your library; you can keep both
the old and the new music; you can remove the existing music and choose the
new stuff; or you can merge all the new and old tracks into a single album.
If you choose that "remove" option, any duplicates will be
removed from your library database---and, if the corresponding files are located
inside of your beets library directory, the files themselves will be deleted as
well.

If you choose "merge", beets will try re-importing the existing and new tracks
as one bundle together.
This is particularly helpful when you have an album that's missing some tracks
and then want to import the remaining songs.
The importer will ask you the same questions as it would if you were importing
all tracks at once.

If you choose to keep two identically-named albums, beets can avoid storing both
in the same directory. See :ref:`aunique` for details.

Fingerprinting
--------------

You may have noticed by now that beets' autotagger works pretty well for most
files, but can get confused when files don't have any metadata (or have wildly
incorrect metadata). In this case, you need *acoustic fingerprinting*, a
technology that identifies songs from the audio itself. With fingerprinting,
beets can autotag files that have very bad or missing tags. The :doc:`"chroma"
plugin </plugins/chroma>`, distributed with beets, uses the `Chromaprint`_ open-source fingerprinting technology, but it's disabled by default. That's because
it's sort of tricky to install. See the :doc:`/plugins/chroma` page for a guide
to getting it set up.

Before you jump into acoustic fingerprinting with both feet, though, give beets
a try without it. You may be surprised at how well metadata-based matching
works.

.. _Chromaprint: https://acoustid.org/chromaprint

Album Art, Lyrics, Genres and Such
----------------------------------

Aside from the basic stuff, beets can optionally fetch more specialized
metadata. As a rule, plugins are responsible for getting information that
doesn't come directly from the MusicBrainz database. This includes :doc:`album
cover art </plugins/fetchart>`, :doc:`song lyrics </plugins/lyrics>`, and
:doc:`musical genres </plugins/lastgenre>`. Check out the :doc:`list of plugins
</plugins/index>` to pick and choose the data you want.

Missing Albums?
---------------

If you're having trouble tagging a particular album with beets, check to make
sure the album is present in `the MusicBrainz database`_.  You can search on
their site to make sure it's cataloged there. If not, anyone can edit
MusicBrainz---so consider adding the data yourself.

.. _the MusicBrainz database: https://musicbrainz.org/

If you think beets is ignoring an album that's listed in MusicBrainz, please
`file a bug report`_.

.. _file a bug report: https://github.com/beetbox/beets/issues

I Hope That Makes Sense
-----------------------

If we haven't made the process clear, please post on `the discussion
board`_ and we'll try to improve this guide.

.. _the mailing list: https://groups.google.com/group/beets-users
.. _the discussion board: https://github.com/beetbox/beets/discussions/
