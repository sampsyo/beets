.. _queries:

Queries
=======

Many of beets' :doc:`commands <cli>` are built around **query strings:**
searches that select tracks and albums from your library. This page explains the
query string syntax, which is meant to vaguely resemble the syntax used by Web
search engines.

.. _keywordquery:

Keyword
-------

This command::

    $ beet list love

will show all tracks matching the query string ``love``. By default any
unadorned word like this matches in a track's title, artist, album name, album
artist, genre and comments. See below on how to search other fields.

For example, this is what I might see when I run the command above::

    Against Me! - Reinventing Axl Rose - I Still Love You Julie
    Air - Love 2 - Do the Joy
    Bag Raiders - Turbo Love - Shooting Stars
    Bat for Lashes - Two Suns - Good Love
    ...

.. _combiningqueries:

Combining Keywords
------------------

Multiple keywords are implicitly joined with a Boolean "and." That is, if a
query has two keywords, it only matches tracks that contain *both* keywords. For
example, this command::

    $ beet ls magnetic tomorrow

matches songs from the album "The House of Tomorrow" by The Magnetic Fields in
my library. It *doesn't* match other songs by the Magnetic Fields, nor does it
match "Tomorrowland" by Walter Meego---those songs only have *one* of the two
keywords I specified.

Keywords can also be joined with a Boolean "or" using a comma. For example,
the command::

    $ beet ls magnetic tomorrow , beatles yesterday

will match both "The House of Tomorrow" by the Magnetic Fields, as well as
"Yesterday" by The Beatles. Note that the comma has to be followed by a space
(e.g., ``foo,bar`` will be treated as a single keyword, *not* as an OR-query).

.. _fieldsquery:

Specific Fields
---------------

Sometimes, a broad keyword match isn't enough. Beets supports a syntax that lets
you query a specific field---only the artist, only the track title, and so on.
Just say ``field:value``, where ``field`` is the name of the thing you're trying
to match (such as ``artist``, ``album``, or ``title``) and ``value`` is the
keyword you're searching for.

For example, while this query::

    $ beet list dream

matches a lot of songs in my library, this more-specific query::

    $ beet list artist:dream

only matches songs by the artist The-Dream. One query I especially appreciate is
one that matches albums by year::

    $ beet list -a year:2012

Recall that ``-a`` makes the ``list`` command show albums instead of individual
tracks, so this command shows me all the releases I have from this year.

For multi-valued tags (such as ``artists`` or ``albumartists``), a regular
expression search must be used to search for a single value within the
multi-valued tag.

Note that you can filter albums by querying tracks fields and vice versa::

    $ beet list -a title:love

and vice versa::

    $ beet list art_path::love

Phrases
-------

You can query for strings with spaces in them by quoting or escaping them using
your shell's argument syntax. For example, this command::

    $ beet list the rebel

shows several tracks in my library, but these (equivalent) commands::

    $ beet list "the rebel"
    $ beet list the\ rebel

only match the track "The Rebel" by Buck 65. Note that the quotes and
backslashes are not part of beets' syntax; I'm just using the escaping
functionality of my shell (bash or zsh, for instance) to pass ``the rebel`` as a
single argument instead of two.

.. _exact-match:

Exact Matches
-------------

While ordinary queries perform *substring* matches, beets can also match whole
strings by adding either ``=`` (case-sensitive) or ``=~`` (ignore case) after
the field name's colon and before the expression::

    $ beet list artist:air
    $ beet list artist:=~air
    $ beet list artist:=AIR

The first query is a simple substring one that returns tracks by Air, AIR, and
Air Supply. The second query returns tracks by Air and AIR, since both are a
case-insensitive match for the entire expression, but does not return anything
by Air Supply. The third query, which requires a case-sensitive exact match,
returns tracks by AIR only.

Exact matches may be performed on phrases as well::

    $ beet list artist:=~"dave matthews"
    $ beet list artist:="Dave Matthews"

Both of these queries return tracks by Dave Matthews, but not by Dave Matthews
Band.

To search for exact matches across *all* fields, just prefix the expression with
a single ``=`` or ``=~``::

    $ beet list =~crash
    $ beet list ="American Football"

.. _regex:

Regular Expressions
-------------------

In addition to simple substring and exact matches, beets also supports regular
expression matching for more advanced queries. To run a regex query, use an
additional ``:`` between the field name and the expression::

    $ beet list "artist::Ann(a|ie)"

That query finds songs by Anna Calvi and Annie but not Annuals. Similarly, this
query prints the path to any file in my library that's missing a track title::

    $ beet list -p title::^$

To search *all* fields using a regular expression, just prefix the expression
with a single ``:``, like so::

    $ beet list ":Ho[pm]eless"

Regular expressions are case-sensitive and build on `Python's built-in
implementation`_. See Python's documentation for specifics on regex syntax.

Most command-line shells will try to interpret common characters in regular
expressions, such as ``()[]|``. To type those characters, you'll need to
escape them (e.g., with backslashes or quotation marks, depending on your
shell).

.. _Python's built-in implementation: https://docs.python.org/library/re.html


.. _numericquery:

Numeric Range Queries
---------------------

For numeric fields, such as year, bitrate, and track, you can query using one-
or two-sided intervals. That is, you can find music that falls within a
*range* of values. To use ranges, write a query that has two dots (``..``) at
the beginning, middle, or end of a string of numbers. Dots in the beginning
let you specify a maximum (e.g., ``..7``); dots at the end mean a minimum
(``4..``); dots in the middle mean a range (``4..7``).

For example, this command finds all your albums that were released in the
'90s::

    $ beet list -a year:1990..1999

and this command finds MP3 files with bitrates of 128k or lower::

    $ beet list format:MP3 bitrate:..128000

The ``length`` field also lets you use a "M:SS" format. For example, this
query finds tracks that are less than four and a half minutes in length::

    $ beet list length:..4:30


.. _datequery:

Date and Date Range Queries
---------------------------

Date-valued fields, such as *added* and *mtime*, have a special query syntax
that lets you specify years, months, and days as well as ranges between dates.

Dates are written separated by hyphens, like ``year-month-day``, but the month
and day are optional. If you leave out the day, for example, you will get
matches for the whole month.

Date *intervals*, like the numeric intervals described above, are separated by
two dots (``..``). You can specify a start, an end, or both.

Here is an example that finds all the albums added in 2008::

    $ beet ls -a 'added:2008'

Find all items added in the years 2008, 2009 and 2010::

    $ beet ls 'added:2008..2010'

Find all items added before the year 2010::

    $ beet ls 'added:..2009'

Find all items added on or after 2008-12-01 but before 2009-10-12::

    $ beet ls 'added:2008-12..2009-10-11'

Find all items with a file modification time between 2008-12-01 and
2008-12-03::

    $ beet ls 'mtime:2008-12-01..2008-12-02'

You can also add an optional time value to date queries, specifying hours,
minutes, and seconds.

Times are separated from dates by a space, an uppercase 'T' or a lowercase
't', for example: ``2008-12-01T23:59:59``. If you specify a time, then the
date must contain a year, month, and day. The minutes and seconds are
optional.

Here is an example that finds all items added on 2008-12-01 at or after 22:00
but before 23:00::

    $ beet ls 'added:2008-12-01T22'

To find all items added on or after 2008-12-01 at 22:45::

    $ beet ls 'added:2008-12-01T22:45..'

To find all items added on 2008-12-01, at or after 22:45:20 but before
22:45:41::

    $ beet ls 'added:2008-12-01T22:45:20..2008-12-01T22:45:40'

Here are example of the three ways to separate dates from times. All of these
queries do the same thing::

    $ beet ls 'added:2008-12-01T22:45:20'
    $ beet ls 'added:2008-12-01t22:45:20'
    $ beet ls 'added:2008-12-01 22:45:20'

You can also use *relative* dates. For example, ``-3w`` means three weeks ago,
and ``+4d`` means four days in the future. A relative date has three parts:

- Either ``+`` or ``-``, to indicate the past or the future. The sign is
  optional; if you leave this off, it defaults to the future.
- A number.
- A letter indicating the unit: ``d``, ``w``, ``m`` or ``y``, meaning days,
  weeks, months or years. (A "month" is always 30 days and a "year" is always
  365 days.)

Here's an example that finds all the albums added since last week::

    $ beet ls -a 'added:-1w..'

And here's an example that lists items added in a two-week period starting
four weeks ago::

    $ beet ls 'added:-6w..-4w'

.. _not_query:

Query Term Negation
-------------------

Query terms can also be negated, acting like a Boolean "not," by prefixing
them with ``-`` or ``^``. This has the effect of returning all the items that
do **not** match the query term. For example, this command::

    $ beet list ^love

matches all the songs in the library that do not have "love" in any of their
fields.

Negation can be combined with the rest of the query mechanisms, so you can
negate specific fields, regular expressions, etc. For example, this command::

    $ beet list -a artist:dylan ^year:1980..1989 "^album::the(y)?"

matches all the albums with an artist containing "dylan", but excluding those
released in the eighties and those that have "the" or "they" on the title.

The syntax supports both ``^`` and ``-`` as synonyms because the latter
indicates flags on the command line. To use a minus sign in a command-line
query, use a double dash ``--`` to separate the options from the query::

    $ beet list -a -- artist:dylan -year:1980..1990 "-album::the(y)?"

.. _pathquery:

Path Queries
------------

Sometimes it's useful to find all the items in your library that are
(recursively) inside a certain directory. Use the ``path:`` field to do this::

    $ beet list path:/my/music/directory

In fact, beets automatically recognizes any query term containing a path
separator (``/`` on POSIX systems) as a path query if that path exists, so this
command is equivalent as long as ``/my/music/directory`` exist::

    $ beet list /my/music/directory

Note that this only matches items that are *already in your library*, so a path
query won't necessarily find *all* the audio files in a directory---just the
ones you've already added to your beets library.

Path queries are case sensitive if the queried path is on a case-sensitive
filesystem.

.. _query-sort:

Sort Order
----------

Queries can specify a sort order. Use the name of the `field` you want to sort
on, followed by a ``+`` or ``-`` sign to indicate ascending or descending
sort. For example, this command::

    $ beet list -a year+

will list all albums in chronological order. You can also specify several sort
orders, which will be used in the same order as they appear in your query::

    $ beet list -a genre+ year+

This command will sort all albums by genre and, in each genre, in chronological
order.

The ``artist`` and ``albumartist`` keys are special: they attempt to use their
corresponding ``artist_sort`` and ``albumartist_sort`` fields for sorting
transparently (but fall back to the ordinary fields when those are empty).

Lexicographic sorts are case insensitive by default, resulting in the following
sort order: ``Bar foo Qux``. This behavior can be changed with the
:ref:`sort_case_insensitive` configuration option. Case sensitive sort will
result in lower-case values being placed after upper-case values, e.g.,
``Bar Qux foo``.

Note that when sorting by fields that are not present on all items (such as
flexible fields, or those defined by plugins) in *ascending* order, the items
that lack that particular field will be listed at the *beginning* of the list.

You can set the default sorting behavior with the :ref:`sort_item` and
:ref:`sort_album` configuration options.
