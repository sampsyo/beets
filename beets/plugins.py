# This file is part of beets.
# Copyright 2016, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Support for beets plugins."""

import abc
import inspect
import re
import traceback
from collections import defaultdict
from functools import wraps

import mediafile

import beets
from beets import logging

PLUGIN_NAMESPACE = "beetsplug"

# Plugins using the Last.fm API can share the same API key.
LASTFM_KEY = "2dc3914abf35f0d9c92d97d8f8e42b43"

# Global logger.
log = logging.getLogger("beets")


class PluginConflictError(Exception):
    """Indicates that the services provided by one plugin conflict with
    those of another.

    For example two plugins may define different types for flexible fields.
    """


class PluginLogFilter(logging.Filter):
    """A logging filter that identifies the plugin that emitted a log
    message.
    """

    def __init__(self, plugin):
        self.prefix = f"{plugin.name}: "

    def filter(self, record):
        if hasattr(record.msg, "msg") and isinstance(record.msg.msg, str):
            # A _LogMessage from our hacked-up Logging replacement.
            record.msg.msg = self.prefix + record.msg.msg
        elif isinstance(record.msg, str):
            record.msg = self.prefix + record.msg
        return True


# Managing the plugins themselves.


class BeetsPlugin:
    """The base class for all beets plugins. Plugins provide
    functionality by defining a subclass of BeetsPlugin and overriding
    the abstract methods defined here.
    """

    def __init__(self, name=None):
        """Perform one-time plugin setup."""
        self.name = name or self.__module__.split(".")[-1]
        self.config = beets.config[self.name]
        if not self.template_funcs:
            self.template_funcs = {}
        if not self.template_fields:
            self.template_fields = {}
        if not self.album_template_fields:
            self.album_template_fields = {}
        self.early_import_stages = []
        self.import_stages = []

        self._log = log.getChild(self.name)
        self._log.setLevel(logging.NOTSET)  # Use `beets` logger level.
        if not any(isinstance(f, PluginLogFilter) for f in self._log.filters):
            self._log.addFilter(PluginLogFilter(self))

    def commands(self):
        """Should return a list of beets.ui.Subcommand objects for
        commands that should be added to beets' CLI.
        """
        return ()

    def _set_stage_log_level(self, stages):
        """Adjust all the stages in `stages` to WARNING logging level."""
        return [
            self._set_log_level_and_params(logging.WARNING, stage)
            for stage in stages
        ]

    def get_early_import_stages(self):
        """Return a list of functions that should be called as importer
        pipelines stages early in the pipeline.

        The callables are wrapped versions of the functions in
        `self.early_import_stages`. Wrapping provides some bookkeeping for the
        plugin: specifically, the logging level is adjusted to WARNING.
        """
        return self._set_stage_log_level(self.early_import_stages)

    def get_import_stages(self):
        """Return a list of functions that should be called as importer
        pipelines stages.

        The callables are wrapped versions of the functions in
        `self.import_stages`. Wrapping provides some bookkeeping for the
        plugin: specifically, the logging level is adjusted to WARNING.
        """
        return self._set_stage_log_level(self.import_stages)

    def _set_log_level_and_params(self, base_log_level, func):
        """Wrap `func` to temporarily set this plugin's logger level to
        `base_log_level` + config options (and restore it to its previous
        value after the function returns). Also determines which params may not
        be sent for backwards-compatibility.
        """
        argspec = inspect.getfullargspec(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            assert self._log.level == logging.NOTSET

            verbosity = beets.config["verbose"].get(int)
            log_level = max(logging.DEBUG, base_log_level - 10 * verbosity)
            self._log.setLevel(log_level)
            if argspec.varkw is None:
                kwargs = {k: v for k, v in kwargs.items() if k in argspec.args}

            try:
                return func(*args, **kwargs)
            finally:
                self._log.setLevel(logging.NOTSET)

        return wrapper

    def queries(self):
        """Return a dict mapping prefixes to Query subclasses."""
        return {}

    def track_distance(self, item, info):
        """Should return a Distance object to be added to the
        distance for every track comparison.
        """
        return beets.autotag.hooks.Distance()

    def album_distance(self, items, album_info, mapping):
        """Should return a Distance object to be added to the
        distance for every album-level comparison.
        """
        return beets.autotag.hooks.Distance()

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Should return a sequence of AlbumInfo objects that match the
        album whose items are provided.
        """
        return ()

    def item_candidates(self, item, artist, title):
        """Should return a sequence of TrackInfo objects that match the
        item provided.
        """
        return ()

    def album_for_id(self, album_id):
        """Return an AlbumInfo object or None if no matching release was
        found.
        """
        return None

    def track_for_id(self, track_id):
        """Return a TrackInfo object or None if no matching release was
        found.
        """
        return None

    def add_media_field(self, name, descriptor):
        """Add a field that is synchronized between media files and items.

        When a media field is added ``item.write()`` will set the name
        property of the item's MediaFile to ``item[name]`` and save the
        changes. Similarly ``item.read()`` will set ``item[name]`` to
        the value of the name property of the media file.

        ``descriptor`` must be an instance of ``mediafile.MediaField``.
        """
        # Defer import to prevent circular dependency
        from beets import library

        mediafile.MediaFile.add_field(name, descriptor)
        library.Item._media_fields.add(name)

    _raw_listeners = None
    listeners = None

    def register_listener(self, event, func):
        """Add a function as a listener for the specified event."""
        wrapped_func = self._set_log_level_and_params(logging.WARNING, func)

        cls = self.__class__
        if cls.listeners is None or cls._raw_listeners is None:
            cls._raw_listeners = defaultdict(list)
            cls.listeners = defaultdict(list)
        if func not in cls._raw_listeners[event]:
            cls._raw_listeners[event].append(func)
            cls.listeners[event].append(wrapped_func)

    template_funcs = None
    template_fields = None
    album_template_fields = None

    @classmethod
    def template_func(cls, name):
        """Decorator that registers a path template function. The
        function will be invoked as ``%name{}`` from path format
        strings.
        """

        def helper(func):
            if cls.template_funcs is None:
                cls.template_funcs = {}
            cls.template_funcs[name] = func
            return func

        return helper

    @classmethod
    def template_field(cls, name):
        """Decorator that registers a path template field computation.
        The value will be referenced as ``$name`` from path format
        strings. The function must accept a single parameter, the Item
        being formatted.
        """

        def helper(func):
            if cls.template_fields is None:
                cls.template_fields = {}
            cls.template_fields[name] = func
            return func

        return helper


_classes = set()


def load_plugins(names=()):
    """Imports the modules for a sequence of plugin names. Each name
    must be the name of a Python module under the "beetsplug" namespace
    package in sys.path; the module indicated should contain the
    BeetsPlugin subclasses desired.
    """
    for name in names:
        modname = f"{PLUGIN_NAMESPACE}.{name}"
        try:
            try:
                namespace = __import__(modname, None, None)
            except ImportError as exc:
                # Again, this is hacky:
                if exc.args[0].endswith(" " + name):
                    log.warning("** plugin {0} not found", name)
                else:
                    raise
            else:
                for obj in getattr(namespace, name).__dict__.values():
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, BeetsPlugin)
                        and obj != BeetsPlugin
                        and obj not in _classes
                    ):
                        _classes.add(obj)

        except Exception:
            log.warning(
                "** error loading plugin {}:\n{}",
                name,
                traceback.format_exc(),
            )


_instances = {}


def find_plugins():
    """Returns a list of BeetsPlugin subclass instances from all
    currently loaded beets plugins. Loads the default plugin set
    first.
    """
    if _instances:
        # After the first call, use cached instances for performance reasons.
        # See https://github.com/beetbox/beets/pull/3810
        return list(_instances.values())

    load_plugins()
    plugins = []
    for cls in _classes:
        # Only instantiate each plugin class once.
        if cls not in _instances:
            _instances[cls] = cls()
        plugins.append(_instances[cls])
    return plugins


# Communication with plugins.


def commands():
    """Returns a list of Subcommand objects from all loaded plugins."""
    out = []
    for plugin in find_plugins():
        out += plugin.commands()
    return out


def queries():
    """Returns a dict mapping prefix strings to Query subclasses all loaded
    plugins.
    """
    out = {}
    for plugin in find_plugins():
        out.update(plugin.queries())
    return out


def types(model_cls):
    # Gives us `item_types` and `album_types`
    attr_name = f"{model_cls.__name__.lower()}_types"
    types = {}
    for plugin in find_plugins():
        plugin_types = getattr(plugin, attr_name, {})
        for field in plugin_types:
            if field in types and plugin_types[field] != types[field]:
                raise PluginConflictError(
                    f"Plugin {plugin.name} defines flexible field "
                    f"{field} which has already been defined with "
                    "another type."
                )
        types.update(plugin_types)
    return types


def named_queries(model_cls):
    # Gather `item_queries` and `album_queries` from the plugins.
    attr_name = f"{model_cls.__name__.lower()}_queries"
    queries = {}
    for plugin in find_plugins():
        plugin_queries = getattr(plugin, attr_name, {})
        queries.update(plugin_queries)
    return queries


def track_distance(item, info):
    """Gets the track distance calculated by all loaded plugins.
    Returns a Distance object.
    """
    from beets.autotag.hooks import Distance

    dist = Distance()
    for plugin in find_plugins():
        dist.update(plugin.track_distance(item, info))
    return dist


def album_distance(items, album_info, mapping):
    """Returns the album distance calculated by plugins."""
    from beets.autotag.hooks import Distance

    dist = Distance()
    for plugin in find_plugins():
        dist.update(plugin.album_distance(items, album_info, mapping))
    return dist


def candidates(items, artist, album, va_likely, extra_tags=None):
    """Gets MusicBrainz candidates for an album from each plugin."""
    for plugin in find_plugins():
        yield from plugin.candidates(
            items, artist, album, va_likely, extra_tags
        )


def item_candidates(item, artist, title):
    """Gets MusicBrainz candidates for an item from the plugins."""
    for plugin in find_plugins():
        yield from plugin.item_candidates(item, artist, title)


def album_for_id(album_id):
    """Get AlbumInfo objects for a given ID string."""
    for plugin in find_plugins():
        album = plugin.album_for_id(album_id)
        if album:
            yield album


def track_for_id(track_id):
    """Get TrackInfo objects for a given ID string."""
    for plugin in find_plugins():
        track = plugin.track_for_id(track_id)
        if track:
            yield track


def template_funcs():
    """Get all the template functions declared by plugins as a
    dictionary.
    """
    funcs = {}
    for plugin in find_plugins():
        if plugin.template_funcs:
            funcs.update(plugin.template_funcs)
    return funcs


def early_import_stages():
    """Get a list of early import stage functions defined by plugins."""
    stages = []
    for plugin in find_plugins():
        stages += plugin.get_early_import_stages()
    return stages


def import_stages():
    """Get a list of import stage functions defined by plugins."""
    stages = []
    for plugin in find_plugins():
        stages += plugin.get_import_stages()
    return stages


# New-style (lazy) plugin-provided fields.


def _check_conflicts_and_merge(plugin, plugin_funcs, funcs):
    """Check the provided template functions for conflicts and merge into funcs.

    Raises a `PluginConflictError` if a plugin defines template functions
    for fields that another plugin has already defined template functions for.
    """
    if plugin_funcs:
        if not plugin_funcs.keys().isdisjoint(funcs.keys()):
            conflicted_fields = ", ".join(plugin_funcs.keys() & funcs.keys())
            raise PluginConflictError(
                f"Plugin {plugin.name} defines template functions for "
                f"{conflicted_fields} that conflict with another plugin."
            )
        funcs.update(plugin_funcs)


def item_field_getters():
    """Get a dictionary mapping field names to unary functions that
    compute the field's value.
    """
    funcs = {}
    for plugin in find_plugins():
        _check_conflicts_and_merge(plugin, plugin.template_fields, funcs)
    return funcs


def album_field_getters():
    """As above, for album fields."""
    funcs = {}
    for plugin in find_plugins():
        _check_conflicts_and_merge(plugin, plugin.album_template_fields, funcs)
    return funcs


# Event dispatch.


def event_handlers():
    """Find all event handlers from plugins as a dictionary mapping
    event names to sequences of callables.
    """
    all_handlers = defaultdict(list)
    for plugin in find_plugins():
        if plugin.listeners:
            for event, handlers in plugin.listeners.items():
                all_handlers[event] += handlers
    return all_handlers


def send(event, **arguments):
    """Send an event to all assigned event listeners.

    `event` is the name of  the event to send, all other named arguments
    are passed along to the handlers.

    Return a list of non-None values returned from the handlers.
    """
    log.debug("Sending event: {0}", event)
    results = []
    for handler in event_handlers()[event]:
        result = handler(**arguments)
        if result is not None:
            results.append(result)
    return results


def feat_tokens(for_artist=True):
    """Return a regular expression that matches phrases like "featuring"
    that separate a main artist or a song title from secondary artists.
    The `for_artist` option determines whether the regex should be
    suitable for matching artist fields (the default) or title fields.
    """
    feat_words = ["ft", "featuring", "feat", "feat.", "ft."]
    if for_artist:
        feat_words += ["with", "vs", "and", "con", "&"]
    matcher = "|".join(re.escape(x) for x in feat_words)
    return rf"(?<=\s)(?:{matcher})(?=\s)"


def sanitize_choices(choices, choices_all):
    """Clean up a stringlist configuration attribute: keep only choices
    elements present in choices_all, remove duplicate elements, expand '*'
    wildcard while keeping original stringlist order.
    """
    seen = set()
    others = [x for x in choices_all if x not in choices]
    res = []
    for s in choices:
        if s not in seen:
            if s in list(choices_all):
                res.append(s)
            elif s == "*":
                res.extend(others)
        seen.add(s)
    return res


def sanitize_pairs(pairs, pairs_all):
    """Clean up a single-element mapping configuration attribute as returned
    by Confuse's `Pairs` template: keep only two-element tuples present in
    pairs_all, remove duplicate elements, expand ('str', '*') and ('*', '*')
    wildcards while keeping the original order. Note that ('*', '*') and
    ('*', 'whatever') have the same effect.

    For example,

    >>> sanitize_pairs(
    ...     [('foo', 'baz bar'), ('key', '*'), ('*', '*')],
    ...     [('foo', 'bar'), ('foo', 'baz'), ('foo', 'foobar'),
    ...      ('key', 'value')]
    ...     )
    [('foo', 'baz'), ('foo', 'bar'), ('key', 'value'), ('foo', 'foobar')]
    """
    pairs_all = list(pairs_all)
    seen = set()
    others = [x for x in pairs_all if x not in pairs]
    res = []
    for k, values in pairs:
        for v in values.split():
            x = (k, v)
            if x in pairs_all:
                if x not in seen:
                    seen.add(x)
                    res.append(x)
            elif k == "*":
                new = [o for o in others if o not in seen]
                seen.update(new)
                res.extend(new)
            elif v == "*":
                new = [o for o in others if o not in seen and o[0] == k]
                seen.update(new)
                res.extend(new)
    return res


def notify_info_yielded(event):
    """Makes a generator send the event 'event' every time it yields.
    This decorator is supposed to decorate a generator, but any function
    returning an iterable should work.
    Each yielded value is passed to plugins using the 'info' parameter of
    'send'.
    """

    def decorator(generator):
        def decorated(*args, **kwargs):
            for v in generator(*args, **kwargs):
                send(event, info=v)
                yield v

        return decorated

    return decorator


def get_distance(config, data_source, info):
    """Returns the ``data_source`` weight and the maximum source weight
    for albums or individual tracks.
    """
    dist = beets.autotag.Distance()
    if info.data_source == data_source:
        dist.add("source", config["source_weight"].as_number())
    return dist


def apply_item_changes(lib, item, move, pretend, write):
    """Store, move, and write the item according to the arguments.

    :param lib: beets library.
    :type lib: beets.library.Library
    :param item: Item whose changes to apply.
    :type item: beets.library.Item
    :param move: Move the item if it's in the library.
    :type move: bool
    :param pretend: Return without moving, writing, or storing the item's
        metadata.
    :type pretend: bool
    :param write: Write the item's metadata to its media file.
    :type write: bool
    """
    if pretend:
        return

    from beets import util

    # Move the item if it's in the library.
    if move and lib.directory in util.ancestry(item.path):
        item.move(with_album=False)

    if write:
        item.try_write()

    item.store()


class MetadataSourcePlugin(metaclass=abc.ABCMeta):
    def __init__(self):
        super().__init__()
        self.config.add({"source_weight": 0.5})

    @abc.abstractproperty
    def id_regex(self):
        raise NotImplementedError

    @abc.abstractproperty
    def data_source(self):
        raise NotImplementedError

    @abc.abstractproperty
    def search_url(self):
        raise NotImplementedError

    @abc.abstractproperty
    def album_url(self):
        raise NotImplementedError

    @abc.abstractproperty
    def track_url(self):
        raise NotImplementedError

    @abc.abstractmethod
    def _search_api(self, query_type, filters, keywords=""):
        raise NotImplementedError

    @abc.abstractmethod
    def album_for_id(self, album_id):
        raise NotImplementedError

    @abc.abstractmethod
    def track_for_id(self, track_id=None, track_data=None):
        raise NotImplementedError

    @staticmethod
    def get_artist(artists, id_key="id", name_key="name", join_key=None):
        """Returns an artist string (all artists) and an artist_id (the main
        artist) for a list of artist object dicts.

        For each artist, this function moves articles (such as 'a', 'an',
        and 'the') to the front and strips trailing disambiguation numbers. It
        returns a tuple containing the comma-separated string of all
        normalized artists and the ``id`` of the main/first artist.
        Alternatively a keyword can be used to combine artists together into a
        single string by passing the join_key argument.

        :param artists: Iterable of artist dicts or lists returned by API.
        :type artists: list[dict] or list[list]
        :param id_key: Key or index corresponding to the value of ``id`` for
            the main/first artist. Defaults to 'id'.
        :type id_key: str or int
        :param name_key: Key or index corresponding to values of names
            to concatenate for the artist string (containing all artists).
            Defaults to 'name'.
        :type name_key: str or int
        :param join_key: Key or index corresponding to a field containing a
            keyword to use for combining artists into a single string, for
            example "Feat.", "Vs.", "And" or similar. The default is None
            which keeps the default behaviour (comma-separated).
        :type join_key: str or int
        :return: Normalized artist string.
        :rtype: str
        """
        artist_id = None
        artist_string = ""
        artists = list(artists)  # In case a generator was passed.
        total = len(artists)
        for idx, artist in enumerate(artists):
            if not artist_id:
                artist_id = artist[id_key]
            name = artist[name_key]
            # Strip disambiguation number.
            name = re.sub(r" \(\d+\)$", "", name)
            # Move articles to the front.
            name = re.sub(r"^(.*?), (a|an|the)$", r"\2 \1", name, flags=re.I)
            # Use a join keyword if requested and available.
            if idx < (total - 1):  # Skip joining on last.
                if join_key and artist.get(join_key, None):
                    name += f" {artist[join_key]} "
                else:
                    name += ", "
            artist_string += name

        return artist_string, artist_id

    @staticmethod
    def _get_id(url_type, id_, id_regex):
        """Parse an ID from its URL if necessary.

        :param url_type: Type of URL. Either 'album' or 'track'.
        :type url_type: str
        :param id_: Album/track ID or URL.
        :type id_: str
        :param id_regex: A dictionary containing a regular expression
            extracting an ID from an URL (if it's not an ID already) in
            'pattern' and the number of the match group in 'match_group'.
        :type id_regex: dict
        :return: Album/track ID.
        :rtype: str
        """
        log.debug("Extracting {} ID from '{}'", url_type, id_)
        match = re.search(id_regex["pattern"].format(url_type), str(id_))
        if match:
            id_ = match.group(id_regex["match_group"])
            if id_:
                return id_
        return None

    def candidates(self, items, artist, album, va_likely, extra_tags=None):
        """Returns a list of AlbumInfo objects for Search API results
        matching an ``album`` and ``artist`` (if not various).

        :param items: List of items comprised by an album to be matched.
        :type items: list[beets.library.Item]
        :param artist: The artist of the album to be matched.
        :type artist: str
        :param album: The name of the album to be matched.
        :type album: str
        :param va_likely: True if the album to be matched likely has
            Various Artists.
        :type va_likely: bool
        :return: Candidate AlbumInfo objects.
        :rtype: list[beets.autotag.hooks.AlbumInfo]
        """
        query_filters = {"album": album}
        if not va_likely:
            query_filters["artist"] = artist
        results = self._search_api(query_type="album", filters=query_filters)
        albums = [self.album_for_id(album_id=r["id"]) for r in results]
        return [a for a in albums if a is not None]

    def item_candidates(self, item, artist, title):
        """Returns a list of TrackInfo objects for Search API results
        matching ``title`` and ``artist``.

        :param item: Singleton item to be matched.
        :type item: beets.library.Item
        :param artist: The artist of the track to be matched.
        :type artist: str
        :param title: The title of the track to be matched.
        :type title: str
        :return: Candidate TrackInfo objects.
        :rtype: list[beets.autotag.hooks.TrackInfo]
        """
        tracks = self._search_api(
            query_type="track", keywords=title, filters={"artist": artist}
        )
        return [self.track_for_id(track_data=track) for track in tracks]

    def album_distance(self, items, album_info, mapping):
        return get_distance(
            data_source=self.data_source, info=album_info, config=self.config
        )

    def track_distance(self, item, track_info):
        return get_distance(
            data_source=self.data_source, info=track_info, config=self.config
        )
