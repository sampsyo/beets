.. _writing-plugins:

Writing Plugins
---------------

A beets plugin is just a Python module or package inside the ``beetsplug``
namespace package. (Check out `this article`_ and `this Stack Overflow
question`_ if you haven't heard about namespace packages.) So, to make one,
create a directory called ``beetsplug`` and add either your plugin module::

    beetsplug/
        myawesomeplugin.py

or your plugin subpackage::

    beetsplug/
        myawesomeplugin/
            __init__.py
            myawesomeplugin.py

.. attention::

    You do not anymore need to add a ``__init__.py`` file to the ``beetsplug``
    directory. Python treats your plugin as a namespace package automatically,
    thus we do not depend on ``pkgutil``-based setup in the ``__init__.py``
    file anymore.

The meat of your plugin goes in ``myawesomeplugin.py``. There, you'll have to
import ``BeetsPlugin`` from ``beets.plugins`` and subclass it, for example

.. code-block:: python

    from beets.plugins import BeetsPlugin

    class MyAwesomePlugin(BeetsPlugin):
        pass

Once you have your ``BeetsPlugin`` subclass, there's a variety of things your
plugin can do. (Read on!)

To use your new plugin, package your plugin (see how to do this with `poetry`_
or `setuptools`_, for example) and install it into your ``beets`` virtual
environment. Then, add your plugin to beets configuration

.. code-block:: yaml

    # config.yaml
    plugins:
      - myawesomeplugin

and you're good to go!

.. _this article: https://realpython.com/python-namespace-package/#setting-up-some-namespace-packages
.. _this Stack Overflow question: https://stackoverflow.com/a/27586272/9582674
.. _poetry: https://python-poetry.org/docs/pyproject/#packages
.. _setuptools: https://setuptools.pypa.io/en/latest/userguide/package_discovery.html#finding-simple-packages

.. _add_subcommands:

Add Commands to the CLI
^^^^^^^^^^^^^^^^^^^^^^^

Plugins can add new subcommands to the ``beet`` command-line interface. Define
the plugin class' ``commands()`` method to return a list of ``Subcommand``
objects. (The ``Subcommand`` class is defined in the ``beets.ui`` module.)
Here's an example plugin that adds a simple command::

    from beets.plugins import BeetsPlugin
    from beets.ui import Subcommand

    my_super_command = Subcommand('super', help='do something super')
    def say_hi(lib, opts, args):
        print "Hello everybody! I'm a plugin!"
    my_super_command.func = say_hi

    class SuperPlug(BeetsPlugin):
        def commands(self):
            return [my_super_command]

To make a subcommand, invoke the constructor like so: ``Subcommand(name, parser,
help, aliases)``. The ``name`` parameter is the only required one and should
just be the name of your command. ``parser`` can be an `OptionParser instance`_,
but it defaults to an empty parser (you can extend it later). ``help`` is a
description of your command, and ``aliases`` is a list of shorthand versions of
your command name.

.. _OptionParser instance: https://docs.python.org/library/optparse.html

You'll need to add a function to your command by saying ``mycommand.func =
myfunction``. This function should take the following parameters: ``lib`` (a
beets ``Library`` object) and ``opts`` and ``args`` (command-line options and
arguments as returned by `OptionParser.parse_args`_).

.. _OptionParser.parse_args:
    https://docs.python.org/library/optparse.html#parsing-arguments

The function should use any of the utility functions defined in ``beets.ui``.
Try running ``pydoc beets.ui`` to see what's available.

You can add command-line options to your new command using the ``parser`` member
of the ``Subcommand`` class, which is a ``CommonOptionsParser`` instance. Just
use it like you would a normal ``OptionParser`` in an independent script. Note
that it offers several methods to add common options: ``--album``, ``--path``
and ``--format``. This feature is versatile and extensively documented, try
``pydoc beets.ui.CommonOptionsParser`` for more information.

.. _plugin_events:

Listen for Events
^^^^^^^^^^^^^^^^^

Event handlers allow plugins to run code whenever something happens in beets'
operation. For instance, a plugin could write a log message every time an album
is successfully autotagged or update MPD's index whenever the database is
changed.

You can "listen" for events using ``BeetsPlugin.register_listener``. Here's
an example::

    from beets.plugins import BeetsPlugin

    def loaded():
        print 'Plugin loaded!'

    class SomePlugin(BeetsPlugin):
      def __init__(self):
        super().__init__()
        self.register_listener('pluginload', loaded)

Note that if you want to access an attribute of your plugin (e.g. ``config`` or
``log``) you'll have to define a method and not a function. Here is the usual
registration process in this case::

    from beets.plugins import BeetsPlugin

    class SomePlugin(BeetsPlugin):
      def __init__(self):
        super().__init__()
        self.register_listener('pluginload', self.loaded)

      def loaded(self):
        self._log.info('Plugin loaded!')

The events currently available are:

* `pluginload`: called after all the plugins have been loaded after the ``beet``
  command starts

* `import`: called after a ``beet import`` command finishes (the ``lib`` keyword
  argument is a Library object; ``paths`` is a list of paths (strings) that were
  imported)

* `album_imported`: called with an ``Album`` object every time the ``import``
  command finishes adding an album to the library. Parameters: ``lib``,
  ``album``

* `album_removed`: called with an ``Album`` object every time an album is
  removed from the library (even when its file is not deleted from disk).

* `item_copied`: called with an ``Item`` object whenever its file is copied.
  Parameters: ``item``, ``source`` path, ``destination`` path

* `item_imported`: called with an ``Item`` object every time the importer adds a
  singleton to the library (not called for full-album imports). Parameters:
  ``lib``, ``item``

* `before_item_moved`: called with an ``Item`` object immediately before its
  file is moved. Parameters: ``item``, ``source`` path, ``destination`` path

* `item_moved`: called with an ``Item`` object whenever its file is moved.
  Parameters: ``item``, ``source`` path, ``destination`` path

* `item_linked`: called with an ``Item`` object whenever a symlink is created
  for a file.
  Parameters: ``item``, ``source`` path, ``destination`` path

* `item_hardlinked`: called with an ``Item`` object whenever a hardlink is
  created for a file.
  Parameters: ``item``, ``source`` path, ``destination`` path

* `item_reflinked`: called with an ``Item`` object whenever a reflink is
  created for a file.
  Parameters: ``item``, ``source`` path, ``destination`` path

* `item_removed`: called with an ``Item`` object every time an item (singleton
  or album's part) is removed from the library (even when its file is not
  deleted from disk).

* `write`: called with an ``Item`` object, a ``path``, and a ``tags``
  dictionary just before a file's metadata is written to disk (i.e.,
  just before the file on disk is opened). Event handlers may change
  the ``tags`` dictionary to customize the tags that are written to the
  media file. Event handlers may also raise a
  ``library.FileOperationError`` exception to abort the write
  operation. Beets will catch that exception, print an error message
  and continue.

* `after_write`: called with an ``Item`` object after a file's metadata is
  written to disk (i.e., just after the file on disk is closed).

* `import_task_created`: called immediately after an import task is
  initialized. Plugins can use this to, for example, change imported files of a
  task before anything else happens. It's also possible to replace the task
  with another task by returning a list of tasks. This list can contain zero
  or more `ImportTask`s. Returning an empty list will stop the task.
  Parameters: ``task`` (an `ImportTask`) and ``session`` (an `ImportSession`).

* `import_task_start`: called when before an import task begins processing.
  Parameters: ``task`` and ``session``.

* `import_task_apply`: called after metadata changes have been applied in an
  import task. This is called on the same thread as the UI, so use this
  sparingly and only for tasks that can be done quickly. For most plugins, an
  import pipeline stage is a better choice (see :ref:`plugin-stage`).
  Parameters: ``task`` and ``session``.

* `import_task_before_choice`: called after candidate search for an import task
  before any decision is made about how/if to import or tag. Can be used to
  present information about the task or initiate interaction with the user
  before importing occurs. Return an importer action to take a specific action.
  Only one handler may return a non-None result.
  Parameters: ``task`` and ``session``

* `import_task_choice`: called after a decision has been made about an import
  task. This event can be used to initiate further interaction with the user.
  Use ``task.choice_flag`` to determine or change the action to be
  taken. Parameters: ``task`` and ``session``.

* `import_task_files`: called after an import task finishes manipulating the
  filesystem (copying and moving files, writing metadata tags). Parameters:
  ``task`` and ``session``.

* `library_opened`: called after beets starts up and initializes the main
  Library object. Parameter: ``lib``.

* `database_change`: a modification has been made to the library database. The
  change might not be committed yet. Parameters: ``lib`` and ``model``.

* `cli_exit`: called just before the ``beet`` command-line program exits.
  Parameter: ``lib``.

* `import_begin`: called just before a ``beet import`` session starts up.
  Parameter: ``session``.

* `trackinfo_received`: called after metadata for a track item has been
  fetched from a data source, such as MusicBrainz. You can modify the tags
  that the rest of the pipeline sees on a ``beet import`` operation or during
  later adjustments, such as ``mbsync``. Slow handlers of the event can impact
  the operation, since the event is fired for any fetched possible match
  `before` the user (or the autotagger machinery) gets to see the match.
  Parameter: ``info``.

* `albuminfo_received`: like `trackinfo_received`, the event indicates new
  metadata for album items. The parameter is an ``AlbumInfo`` object instead
  of a ``TrackInfo``.
  Parameter: ``info``.

* `before_choose_candidate`: called before the user is prompted for a decision
  during a ``beet import`` interactive session. Plugins can use this event for
  :ref:`appending choices to the prompt <append_prompt_choices>` by returning a
  list of ``PromptChoices``. Parameters: ``task`` and ``session``.

* `mb_track_extract`: called after the metadata is obtained from
  MusicBrainz. The parameter is a ``dict`` containing the tags retrieved from
  MusicBrainz for a track. Plugins must return a new (potentially empty)
  ``dict`` with additional ``field: value`` pairs, which the autotagger will
  apply to the item, as flexible attributes if ``field`` is not a hardcoded
  field. Fields already present on the track are overwritten.
  Parameter: ``data``

* `mb_album_extract`: Like `mb_track_extract`, but for album tags. Overwrites
  tags set at the track level, if they have the same ``field``.
  Parameter: ``data``

The included ``mpdupdate`` plugin provides an example use case for event listeners.

Extend the Autotagger
^^^^^^^^^^^^^^^^^^^^^

Plugins can also enhance the functionality of the autotagger. For a
comprehensive example, try looking at the ``chroma`` plugin, which is included
with beets.

A plugin can extend three parts of the autotagger's process: the track distance
function, the album distance function, and the initial MusicBrainz search. The
distance functions determine how "good" a match is at the track and album
levels; the initial search controls which candidates are presented to the
matching algorithm. Plugins implement these extensions by implementing four
methods on the plugin class:

* ``track_distance(self, item, info)``: adds a component to the distance
  function (i.e., the similarity metric) for individual tracks. ``item`` is the
  track to be matched (an Item object) and ``info`` is the TrackInfo object
  that is proposed as a match. Should return a ``(dist, dist_max)`` pair
  of floats indicating the distance.

* ``album_distance(self, items, album_info, mapping)``: like the above, but
  compares a list of items (representing an album) to an album-level MusicBrainz
  entry. ``items`` is a list of Item objects; ``album_info`` is an AlbumInfo
  object; and ``mapping`` is a dictionary that maps Items to their corresponding
  TrackInfo objects.

* ``candidates(self, items, artist, album, va_likely)``: given a list of items
  comprised by an album to be matched, return a list of ``AlbumInfo`` objects
  for candidate albums to be compared and matched.

* ``item_candidates(self, item, artist, album)``: given a *singleton* item,
  return a list of ``TrackInfo`` objects for candidate tracks to be compared and
  matched.

* ``album_for_id(self, album_id)``: given an ID from user input or an album's
  tags, return a candidate AlbumInfo object (or None).

* ``track_for_id(self, track_id)``: given an ID from user input or a file's
  tags, return a candidate TrackInfo object (or None).

When implementing these functions, you may want to use the functions from the
``beets.autotag`` and ``beets.autotag.mb`` modules, both of which have
somewhat helpful docstrings.

Read Configuration Options
^^^^^^^^^^^^^^^^^^^^^^^^^^

Plugins can configure themselves using the ``config.yaml`` file. You can read
configuration values in two ways. The first is to use `self.config` within
your plugin class. This gives you a view onto the configuration values in a
section with the same name as your plugin's module. For example, if your plugin
is in ``greatplugin.py``, then `self.config` will refer to options under the
``greatplugin:`` section of the config file.

For example, if you have a configuration value called "foo", then users can put
this in their ``config.yaml``::

    greatplugin:
        foo: bar

To access this value, say ``self.config['foo'].get()`` at any point in your
plugin's code. The `self.config` object is a *view* as defined by the `Confuse`_
library.

.. _Confuse: https://confuse.readthedocs.io/en/latest/

If you want to access configuration values *outside* of your plugin's section,
import the `config` object from the `beets` module. That is, just put ``from
beets import config`` at the top of your plugin and access values from there.

If your plugin provides configuration values for sensitive data (e.g.,
passwords, API keys, ...), you should add these to the config so they can be
redacted automatically when users dump their config. This can be done by
setting each value's `redact` flag, like so::

    self.config['password'].redact = True


Add Path Format Functions and Fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Beets supports *function calls* in its path format syntax (see
:doc:`/reference/pathformat`). Beets includes a few built-in functions, but
plugins can register new functions by adding them to the ``template_funcs``
dictionary.

Here's an example::

    class MyPlugin(BeetsPlugin):
        def __init__(self):
            super().__init__()
            self.template_funcs['initial'] = _tmpl_initial

    def _tmpl_initial(text):
        if text:
            return text[0].upper()
        else:
            return u''

This plugin provides a function ``%initial`` to path templates where
``%initial{$artist}`` expands to the artist's initial (its capitalized first
character).

Plugins can also add template *fields*, which are computed values referenced
as ``$name`` in templates. To add a new field, add a function that takes an
``Item`` object to the ``template_fields`` dictionary on the plugin object.
Here's an example that adds a ``$disc_and_track`` field::

    class MyPlugin(BeetsPlugin):
        def __init__(self):
            super().__init__()
            self.template_fields['disc_and_track'] = _tmpl_disc_and_track

    def _tmpl_disc_and_track(item):
        """Expand to the disc number and track number if this is a
        multi-disc release. Otherwise, just expands to the track
        number.
        """
        if item.disctotal > 1:
            return u'%02i.%02i' % (item.disc, item.track)
        else:
            return u'%02i' % (item.track)

With this plugin enabled, templates can reference ``$disc_and_track`` as they
can any standard metadata field.

This field works for *item* templates. Similarly, you can register *album*
template fields by adding a function accepting an ``Album`` argument to the
``album_template_fields`` dict.

Extend MediaFile
^^^^^^^^^^^^^^^^

`MediaFile`_ is the file tag abstraction layer that beets uses to make
cross-format metadata manipulation simple. Plugins can add fields to MediaFile
to extend the kinds of metadata that they can easily manage.

The ``MediaFile`` class uses ``MediaField`` descriptors to provide
access to file tags. If you have created a descriptor you can add it through
your plugins ``add_media_field()`` method.

.. automethod:: beets.plugins.BeetsPlugin.add_media_field
.. _MediaFile: https://mediafile.readthedocs.io/en/latest/


Here's an example plugin that provides a meaningless new field "foo"::

    class FooPlugin(BeetsPlugin):
        def __init__(self):
            field = mediafile.MediaField(
                mediafile.MP3DescStorageStyle(u'foo'),
                mediafile.StorageStyle(u'foo')
            )
            self.add_media_field('foo', field)

    FooPlugin()
    item = Item.from_path('/path/to/foo/tag.mp3')
    assert item['foo'] == 'spam'

    item['foo'] == 'ham'
    item.write()
    # The "foo" tag of the file is now "ham"


.. _plugin-stage:

Add Import Pipeline Stages
^^^^^^^^^^^^^^^^^^^^^^^^^^

Many plugins need to add high-latency operations to the import workflow. For
example, a plugin that fetches lyrics from the Web would, ideally, not block the
progress of the rest of the importer. Beets allows plugins to add stages to the
parallel import pipeline.

Each stage is run in its own thread. Plugin stages run after metadata changes
have been applied to a unit of music (album or track) and before file
manipulation has occurred (copying and moving files, writing tags to disk).
Multiple stages run in parallel but each stage processes only one task at a time
and each task is processed by only one stage at a time.

Plugins provide stages as functions that take two arguments: ``config`` and
``task``, which are ``ImportSession`` and ``ImportTask`` objects (both defined in
``beets.importer``). Add such a function to the plugin's ``import_stages`` field
to register it::

    from beets.plugins import BeetsPlugin
    class ExamplePlugin(BeetsPlugin):
        def __init__(self):
            super().__init__()
            self.import_stages = [self.stage]
        def stage(self, session, task):
            print('Importing something!')

It is also possible to request your function to run early in the pipeline by
adding the function to the plugin's ``early_import_stages`` field instead::

    self.early_import_stages = [self.stage]

.. _extend-query:

Extend the Query Syntax
^^^^^^^^^^^^^^^^^^^^^^^

You can add new kinds of queries to beets' :doc:`query syntax
</reference/query>`. There are two ways to add custom queries: using a prefix
and using a name. Prefix-based query extension can apply to *any* field, while
named queries are not associated with any field. For example, beets already
supports regular expression queries, which are indicated by a colon
prefix---plugins can do the same.

For either kind of query extension, define a subclass of the ``Query`` type
from the ``beets.dbcore.query`` module. Then:

- To define a prefix-based query, define a ``queries`` method in your plugin
  class. Return from this method a dictionary mapping prefix strings to query
  classes.
- To define a named query, defined dictionaries named either ``item_queries``
  or ``album_queries``. These should map names to query types. So if you
  use ``{ "foo": FooQuery }``, then the query ``foo:bar`` will construct a
  query like ``FooQuery("bar")``.

For prefix-based queries, you will want to extend ``FieldQuery``, which
implements string comparisons on fields. To use it, create a subclass
inheriting from that class and override the ``value_match`` class method.
(Remember the ``@classmethod`` decorator!) The following example plugin
declares a query using the ``@`` prefix to delimit exact string matches. The
plugin will be used if we issue a command like ``beet ls @something`` or
``beet ls artist:@something``::

    from beets.plugins import BeetsPlugin
    from beets.dbcore import FieldQuery

    class ExactMatchQuery(FieldQuery):
        @classmethod
        def value_match(self, pattern, val):
            return pattern == val

    class ExactMatchPlugin(BeetsPlugin):
        def queries(self):
            return {
                '@': ExactMatchQuery
            }


Flexible Field Types
^^^^^^^^^^^^^^^^^^^^

If your plugin uses flexible fields to store numbers or other
non-string values, you can specify the types of those fields. A rating
plugin, for example, might want to declare that the ``rating`` field
should have an integer type::

    from beets.plugins import BeetsPlugin
    from beets.dbcore import types

    class RatingPlugin(BeetsPlugin):
        item_types = {'rating': types.INTEGER}

        @property
        def album_types(self):
            return {'rating': types.INTEGER}

A plugin may define two attributes: `item_types` and `album_types`.
Each of those attributes is a dictionary mapping a flexible field name
to a type instance. You can find the built-in types in the
`beets.dbcore.types` and `beets.library` modules or implement your own
type by inheriting from the `Type` class.

Specifying types has several advantages:

* Code that accesses the field like ``item['my_field']`` gets the right
  type (instead of just a string).

* You can use advanced queries (like :ref:`ranges <numericquery>`)
  from the command line.

* User input for flexible fields may be validated and converted.

* Items missing the given field can use an appropriate null value for
  querying and sorting purposes.


.. _plugin-logging:

Logging
^^^^^^^

Each plugin object has a ``_log`` attribute, which is a ``Logger`` from the
`standard Python logging module`_. The logger is set up to `PEP 3101`_,
str.format-style string formatting. So you can write logging calls like this::

    self._log.debug(u'Processing {0.title} by {0.artist}', item)

.. _PEP 3101: https://www.python.org/dev/peps/pep-3101/
.. _standard Python logging module: https://docs.python.org/2/library/logging.html

When beets is in verbose mode, plugin messages are prefixed with the plugin
name to make them easier to see.

Which messages will be logged depends on the logging level and the action
performed:

* Inside import stages and event handlers, the default is ``WARNING`` messages
  and above.
* Everywhere else, the default is ``INFO`` or above.

The verbosity can be increased with ``--verbose`` (``-v``) flags: each flags
lowers the level by a notch. That means that, with a single ``-v`` flag, event
handlers won't have their ``DEBUG`` messages displayed, but command functions
(for example) will. With ``-vv`` on the command line, ``DEBUG`` messages will
be displayed everywhere.

This addresses a common pattern where plugins need to use the same code for a
command and an import stage, but the command needs to print more messages than
the import stage. (For example, you'll want to log "found lyrics for this song"
when you're run explicitly as a command, but you don't want to noisily
interrupt the importer interface when running automatically.)

.. _append_prompt_choices:

Append Prompt Choices
^^^^^^^^^^^^^^^^^^^^^

Plugins can also append choices to the prompt presented to the user during
an import session.

To do so, add a listener for the ``before_choose_candidate`` event, and return
a list of ``PromptChoices`` that represent the additional choices that your
plugin shall expose to the user::

    from beets.plugins import BeetsPlugin
    from beets.ui.commands import PromptChoice

    class ExamplePlugin(BeetsPlugin):
        def __init__(self):
            super().__init__()
            self.register_listener('before_choose_candidate',
                                   self.before_choose_candidate_event)

        def before_choose_candidate_event(self, session, task):
            return [PromptChoice('p', 'Print foo', self.foo),
                    PromptChoice('d', 'Do bar', self.bar)]

        def foo(self, session, task):
            print('User has chosen "Print foo"!')

        def bar(self, session, task):
            print('User has chosen "Do bar"!')

The previous example modifies the standard prompt::

    # selection (default 1), Skip, Use as-is, as Tracks, Group albums,
    Enter search, enter Id, aBort?

by appending two additional options (``Print foo`` and ``Do bar``)::

    # selection (default 1), Skip, Use as-is, as Tracks, Group albums,
    Enter search, enter Id, aBort, Print foo, Do bar?

If the user selects a choice, the ``callback`` attribute of the corresponding
``PromptChoice`` will be called. It is the responsibility of the plugin to
check for the status of the import session and decide the choices to be
appended: for example, if a particular choice should only be presented if the
album has no candidates, the relevant checks against ``task.candidates`` should
be performed inside the plugin's ``before_choose_candidate_event`` accordingly.

Please make sure that the short letter for each of the choices provided by the
plugin is not already in use: the importer will emit a warning and discard
all but one of the choices using the same letter, giving priority to the
core importer prompt choices. As a reference, the following characters are used
by the choices on the core importer prompt, and hence should not be used:
``a``, ``s``, ``u``, ``t``, ``g``, ``e``, ``i``, ``b``.

Additionally, the callback function can optionally specify the next action to
be performed by returning a ``importer.action`` value. It may also return a
``autotag.Proposal`` value to update the set of current proposals to be
considered.
