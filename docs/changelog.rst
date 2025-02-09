Changelog
=========

Changelog goes here! Please add your entry to the bottom of one of the lists below!

Unreleased
----------

Beets now requires Python 3.9 or later since support for EOL Python 3.8 has
been dropped.

New features:

* :doc:`plugins/lastgenre`: The new configuration option, ``keep_existing``,
  provides more fine-grained control over how pre-populated genre tags are
  handled. The ``force`` option now behaves in a more conventional manner.
  :bug:`4982`
* :doc:`plugins/lyrics`: Add new configuration option ``dist_thresh`` to
  control the maximum allowed distance between the lyrics search result and the
  tagged item's artist and title. This is useful for preventing false positives
  when fetching lyrics.

Bug fixes:

* :doc:`plugins/fetchart`: Fix fetchart bug where a tempfile could not be deleted due to never being
  properly closed.
  :bug:`5521`
* :doc:`plugins/lyrics`: LRCLib will fallback to plain lyrics if synced lyrics
  are not found and `synced` flag is set to `yes`.
* Synchronise files included in the source distribution with what we used to
  have before the introduction of Poetry.
  :bug:`5531`
  :bug:`5526`
* :ref:`write-cmd`: Fix the issue where for certain files differences in
  ``mb_artistid``, ``mb_albumartistid`` and ``albumtype`` fields are shown on
  every attempt to write tags. Note: your music needs to be reimported with
  ``beet import -LI`` or synchronised with ``beet mbsync`` in order to fix
  this!
  :bug:`5265`
  :bug:`5371`
  :bug:`4715`
* :ref:`import-cmd`: Fix ``MemoryError`` and improve performance tagging large
  albums by replacing ``munkres`` library with ``lap.lapjv``.
  :bug:`5207`
* :ref:`query-sort`: Fix a bug that would raise an exception when sorting on
  a non-string field that is not populated in all items.
  :bug:`5512`
* :doc:`plugins/lastgenre`: Fix track-level genre handling. Now when an album-level
  genre is set already, single tracks don't fall back to the album's genre and
  request their own last.fm genre. Also log messages regarding what's been
  tagged are now more polished.
  :bug:`5582`
* Fix ambiguous column name ``sqlite3.OperationalError`` that occured in album
  queries that filtered album track titles, for example ``beet list -a keyword
  title:foo``.
* :doc:`plugins/lyrics`: Rewrite lyrics tests using pytest to provide isolated
  configuration for each test case. This fixes the issue where some tests
  failed because they read developers' local lyrics configuration.
  :bug:`5133`
* :doc:`plugins/lyrics`: Do not attempt to search for lyrics if either the
  artist or title is missing and ignore ``artist_sort`` value if it is empty.
  :bug:`2635`
* :doc:`plugins/lyrics`: Fix fetching lyrics from ``lrclib`` source. If we
  cannot find lyrics for a specific album, artist, title combination, the
  plugin now tries to search for the artist and title and picks the most
  relevant result. Update the default ``sources`` configuration to prioritize
  ``lrclib`` over other sources since it returns reliable results quicker than
  others.
  :bug:`5102`
* :doc:`plugins/lyrics`: Fix the issue with ``genius`` backend not being able
  to match lyrics when there is a slight variation in the artist name.
  :bug:`4791`
* :doc:`plugins/lyrics`: Fix plugin crash when ``genius`` backend returns empty
  lyrics.
  :bug:`5583`

For packagers:

* The minimum supported Python version is now 3.9.
* External plugin developers: ``beetsplug/__init__.py`` file can be removed
  from your plugin as beets now uses native/implicit namespace package setup.

Other changes:

* Release workflow: fix the issue where the new release tag is created for the
  wrong (outdated) commit. Now the tag is created in the same workflow step
  right after committing the version update.
  :bug:`5539`

2.2.0 (December 02, 2024)
-------------------------

New features:

* :doc:`/plugins/substitute`: Allow the replacement string to use capture groups
  from the match. It is thus possible to create more general rules, applying to
  many different artists at once.

* Ability to use relative_to as "m3u" to set playlist files as relative to where each playlist is at, including subdirectories.
Bug fixes:

* Check if running python from the Microsoft Store and provide feedback to install
  from python.org.
  :bug:`5467`
* Fix bug where matcher doesn't consider medium number when importing. This makes
  it difficult to import hybrid SACDs and other releases with duplicate tracks.
  :bug:`5148`
* Bring back test files and the manual to the source distribution tarball.
  :bug:`5513`

Other changes:

* Changed `bitesize` label to `good first issue`. Our `contribute`_ page is now
  automatically populated with these issues. :bug:`4855`

.. _contribute: https://github.com/beetbox/beets/contribute

2.1.0 (November 22, 2024)
-------------------------

New features:

* New template function added: ``%capitalize``. Converts the first letter of
  the text to uppercase and the rest to lowercase.
* Ability to query albums with track db fields and vice-versa, for example
  ``beet list -a title:something`` or ``beet list artpath:cover``. Consequently
  album queries involving ``path`` field have been sped up, like ``beet list -a
  path:/path/``.
* :doc:`plugins/ftintitle`: New ``keep_in_artist`` option for the plugin, which
  allows keeping the "feat." part in the artist metadata while still changing
  the title.
* :doc:`plugins/autobpm`: Add new configuration option ``beat_track_kwargs``
  which enables adjusting keyword arguments supplied to librosa's
  ``beat_track`` function call.
* Beets now uses ``platformdirs`` to determine the default music directory.
  This location varies between systems -- for example, users can configure it
  on Unix systems via ``user-dirs.dirs(5)``.

Bug fixes:

* :doc:`plugins/ftintitle`: The detection of a "feat. X" part in a song title does not produce any false
  positives caused by words like "and" or "with" anymore. :bug:`5441`
* :doc:`plugins/ftintitle`: The detection of a "feat. X" part now also matches such parts if they are in
  parentheses or brackets. :bug:`5436`
* Improve naming of temporary files by separating the random part with the file extension.
* Fix the ``auto`` value for the :ref:`reflink` config option.
* Fix lyrics plugin only getting part of the lyrics from ``Genius.com`` :bug:`4815`
* Album flexible fields are now correctly saved. For instance MusicBrainz external links
  such as `bandcamp_album_id` will be available on albums in addition to tracks.
  For albums already in your library, a re-import is required for the fields to be added.
  Such a re-import can be done with, in this case, `beet import -L data_source:=MusicBrainz`.
* :doc:`plugins/autobpm`: Fix the ``TypeError`` where tempo was being returned
  as a numpy array. Update ``librosa`` dependency constraint to prevent similar
  issues in the future.
  :bug:`5289`
* :doc:`plugins/discogs`: Fix the ``TypeError`` when there is no description.
* Use single quotes in all SQL queries
  :bug:`4709`
* :doc:`plugins/lyrics`: Update ``tekstowo`` backend to fetch lyrics directly
  since recent updates to their website made it unsearchable.
  :bug:`5456`
* :doc:`plugins/convert`: Fixed the convert plugin ``no_convert`` option so
  that it no longer treats "and" and "or" queries the same. To maintain
  previous behaviour add commas between your query keywords. For help see
  :ref:`combiningqueries`.
* Fix the ``TypeError`` when :ref:`set_fields` is provided non-string values. :bug:`4840`

For packagers:

* The minimum supported Python version is now 3.8.
* The ``beet`` script has been removed from the repository.
* The ``typing_extensions`` is required for Python 3.10 and below.

Other changes:

* :doc:`contributing`: The project now uses ``poetry`` for packaging and
  dependency management. This change affects project management and mostly
  affects beets developers. Please see updates in :ref:`getting-the-source` and
  :ref:`testing` for more information.
* :doc:`contributing`: Since ``poetry`` now manages local virtual environments,
  `tox` has been replaced by a task runner ``poethepoet``. This change affects
  beets developers and contributors. Please see updates in the
  :ref:`development-tools` section for more details. Type ``poe`` while in
  the project directory to see the available commands.
* Installation instructions have been made consistent across plugins
  documentation. Users should simply install ``beets`` with an ``extra`` of the
  corresponding plugin name in order to install extra dependencies for that
  plugin.
* GitHub workflows have been reorganised for clarity: style, linting, type and
  docs checks now live in separate jobs and are named accordingly.
* Added caching for dependency installation in all CI jobs which speeds them up
  a bit, especially the tests.
* The linting workflow has been made to run only when Python files or
  documentation is changed, and they only check the changed files. When
  dependencies are updated (``poetry.lock``), then the entire code base is
  checked.
* The long-deprecated ``beets.util.confit`` module has been removed.  This may
  cause extremely outdated external plugins to fail to load.
* :doc:`plugins/autobpm`: Add plugin dependencies to ``pyproject.toml`` under
  the ``autobpm`` extra and update the plugin installation instructions in the
  docs.
  Since importing the bpm calculation functionality from ``librosa`` takes
  around 4 seconds, update the plugin to only do so when it actually needs to
  calculate the bpm. Previously this import was being done immediately, so
  every ``beet`` invocation was being delayed by a couple of seconds.
  :bug:`5185`

2.0.0 (May 30, 2024)
--------------------

With this release, beets now requires Python 3.7 or later (it removes support
for Python 3.6).

Major new features:

* The beets importer UI received a major overhaul. Several new configuration
  options are available for customizing layout and colors: :ref:`ui_options`.
  :bug:`3721` :bug:`5028`

New features:

* :doc:`/plugins/edit`: Prefer editor from ``VISUAL`` environment variable over ``EDITOR``.
* :ref:`config-cmd`: Prefer editor from ``VISUAL`` environment variable over ``EDITOR``.
* :doc:`/plugins/listenbrainz`: Add initial support for importing history and playlists from `ListenBrainz`
  :bug:`1719`
* :doc:`plugins/mbsubmit`: add new prompt choices helping further to submit unmatched tracks to MusicBrainz faster.
* :doc:`plugins/spotify`: We now fetch track's ISRC, EAN, and UPC identifiers from Spotify when using the ``spotifysync`` command.
  :bug:`4992`
* :doc:`plugins/discogs`: supply a value for the `cover_art_url` attribute, for use by `fetchart`.
  :bug:`429`
* :ref:`update-cmd`: added ```-e``` flag for excluding fields from being updated.
* :doc:`/plugins/deezer`: Import rank and other attributes from Deezer during import and add a function to update the rank of existing items.
  :bug:`4841`
* resolve transl-tracklisting relations for pseudo releases and merge data with the actual release
  :bug:`654`
* Fetchart: Use the right field (`spotify_album_id`) to obtain the Spotify album id
  :bug:`4803`
* Prevent reimporting album if it is permanently removed from Spotify
  :bug:`4800`
* Added option to use `cover_art_url` as an album art source in the `fetchart` plugin.
  :bug:`4707`
* :doc:`/plugins/fetchart`: The plugin can now get album art from `spotify`.
* Added option to specify a URL in the `embedart` plugin.
  :bug:`83`
* :ref:`list-cmd` `singleton:true` queries have been made faster
* :ref:`list-cmd` `singleton:1` and `singleton:0` can now alternatively be used in queries, same as `comp`
* --from-logfile now parses log files using a UTF-8 encoding in `beets/beets/ui/commands.py`.
  :bug:`4693`
* :doc:`/plugins/bareasc` lookups have been made faster
* :ref:`list-cmd` lookups using the pattern operator `::` have been made faster
* Added additional error handling for `spotify` plugin.
  :bug:`4686`
* We now import the remixer field from Musicbrainz into the library.
  :bug:`4428`
* :doc:`/plugins/mbsubmit`: Added a new `mbsubmit` command to print track information to be submitted to MusicBrainz after initial import.
  :bug:`4455`
* Added `spotify_updated` field to track when the information was last updated.
* We now import and tag the `album` information when importing singletons using Spotify source.
  :bug:`4398`
* :doc:`/plugins/spotify`: The plugin now provides an additional command
  `spotifysync` that allows getting track popularity and audio features
  information from Spotify.
  :bug:`4094`
* :doc:`/plugins/spotify`: The plugin now records Spotify-specific IDs in the
  `spotify_album_id`, `spotify_artist_id`, and `spotify_track_id` fields.
  :bug:`4348`
* Create the parental directories for database if they do not exist.
  :bug:`3808` :bug:`4327`
* :ref:`musicbrainz-config`: a new :ref:`musicbrainz.enabled` option allows disabling
  the MusicBrainz metadata source during the autotagging process
* :doc:`/plugins/kodiupdate`: Now supports multiple kodi instances
  :bug:`4101`
* Add the item fields ``bitrate_mode``, ``encoder_info`` and ``encoder_settings``.
* Add query prefixes ``=`` and ``~``.
* A new configuration option, :ref:`duplicate_keys`, lets you change which
  fields the beets importer uses to identify duplicates.
  :bug:`1133` :bug:`4199`
* Add :ref:`exact match <exact-match>` queries, using the prefixes ``=`` and
  ``=~``.
  :bug:`4251`
* :doc:`/plugins/discogs`: Permit appending style to genre.
* :doc:`plugins/discogs`: Implement item_candidates for matching singletons.
* :doc:`plugins/discogs`: Check for compliant discogs_client module.
* :doc:`/plugins/convert`: Add a new `auto_keep` option that automatically
  converts files but keeps the *originals* in the library.
  :bug:`1840` :bug:`4302`
* Added a ``-P`` (or ``--disable-plugins``) flag to specify one/multiple plugin(s) to be
  disabled at startup.
* :ref:`import-options`: Add support for re-running the importer on paths in
  log files that were created with the ``-l`` (or ``--logfile``) argument.
  :bug:`4379` :bug:`4387`
* Preserve mtimes from archives
  :bug:`4392`
* Add :ref:`%sunique{} <sunique>` template to disambiguate between singletons.
  :bug:`4438`
* Add a new ``import.ignored_alias_types`` config option to allow for
  specific alias types to be skipped over when importing items/albums.
* :doc:`/plugins/smartplaylist`: A new ``--pretend`` option lets the user see
  what a new or changed smart playlist saved in the config is actually
  returning.
  :bug:`4573`
* :doc:`/plugins/fromfilename`:  Add debug log messages that inform when the
  plugin replaced bad (missing) artist, title or tracknumber metadata.
  :bug:`4561` :bug:`4600`
* :ref:`musicbrainz-config`: MusicBrainz release pages often link to related
  metadata sources like Discogs, Bandcamp, Spotify, Deezer and Beatport. When
  enabled via the :ref:`musicbrainz.external_ids` options, release ID's will be
  extracted from those URL's and imported to the library.
  :bug:`4220`
* :doc:`/plugins/convert`: Add support for generating m3u8 playlists together
  with converted media files.
  :bug:`4373`
* Fetch the ``release_group_title`` field from MusicBrainz.
  :bug: `4809`
* :doc:`plugins/discogs`: Add support for applying album information on
  singleton imports.
  :bug: `4716`
* :doc:`/plugins/smartplaylist`: During explicit runs of the ``splupdate``
  command, the log message "Creating playlist ..."" is now displayed instead of
  hidden in the debug log, which states some form of progress through the UI.
  :bug:`4861`
* :doc:`plugins/subsonicupdate`: Updates are now triggered whenever either the
  beets database is changed or a smart playlist is created/updated.
  :bug: `4862`
* :doc:`plugins/importfeeds`: Add a new output format allowing to save a
  playlist once per import session.
  :bug: `4863`
* Make ArtResizer work with :pypi:`PIL`/:pypi:`pillow` 10.0.0 removals.
  :bug:`4869`
* A new configuration option, :ref:`duplicate_verbose_prompt`, allows changing
  how duplicates are presented during import.
  :bug: `4866`
* :doc:`/plugins/embyupdate`: Add handling for private users by adding
  ``userid`` config option.
  :bug:`4402`
* :doc:`/plugins/substitute`: Add the new plugin `substitute` as an alternative
  to the `rewrite` plugin. The main difference between them being that
  `rewrite` modifies files' metadata and `substitute` does not.
  :bug:`2786`
* Add support for ``artists`` and ``albumartists`` multi-valued tags.
  :bug:`505`
* :doc:`/plugins/autobpm`: Add the `autobpm` plugin which uses Librosa to
  calculate the BPM of the audio.
  :bug:`3856`
* :doc:`/plugins/fetchart`: Fix the error with CoverArtArchive where the
  `maxwidth` option would not be used to download a pre-sized thumbnail for
  release groups, as is already done with releases.
* :doc:`/plugins/fetchart`: Fix the error with CoverArtArchive where no cover
  would be found when the `maxwidth` option matches a pre-sized thumbnail size,
  but no thumbnail is provided by CAA. We now fallback to the raw image.
* :doc:`/plugins/advancedrewrite`: Add an advanced version of the `rewrite`
  plugin which allows to replace fields based on a given library query.
* :doc:`/plugins/lyrics`: Add LRCLIB as a new lyrics provider and a new
  `synced` option to prefer synced lyrics over plain lyrics.
* :ref:`import-cmd`: Expose import.quiet_fallback as CLI option.
* :ref:`import-cmd`: Expose `import.incremental_skip_later` as CLI option.
* :doc:`/plugins/smartplaylist`: Expose config options as CLI options.
* :doc:`/plugins/smartplaylist`: Add new option `smartplaylist.output`.
* :doc:`/plugins/smartplaylist`: Add new option `smartplaylist.uri_format`.
* Sorted the default configuration file into categories.
  :bug:`4987`
* :doc:`/plugins/convert`: Don't treat WAVE (`.wav`) files as lossy anymore
  when using the `never_convert_lossy_files` option. They will get transcoded
  like the other lossless formats.
* Add support for `barcode` field.
  :bug:`3172`
* :doc:`/plugins/smartplaylist`: Add new config option `smartplaylist.fields`.
* :doc:`/plugins/fetchart`: Defer source removal config option evaluation to
  the point where they are used really, supporting temporary config changes.

Bug fixes:

* Improve ListenBrainz error handling.
  :bug:`5459`
* :doc:`/plugins/deezer`: Improve requests error handling.
* :doc:`/plugins/lastimport`: Improve error handling in the `process_tracks` function and enable it to be used with other plugins.
* :doc:`/plugins/spotify`: Improve handling of ConnectionError.
* :doc:`/plugins/deezer`: Improve Deezer plugin error handling and set requests timeout to 10 seconds.
  :bug:`4983`
* :doc:`/plugins/spotify`: Add bad gateway (502) error handling.
* :doc:`/plugins/spotify`: Add a limit of 3 retries, instead of retrying endlessly when the API is not available.
* Fix a crash when the Spotify API timeouts or does not return a `Retry-After` interval.
  :bug:`4942`
* :doc:`/plugins/scrub`: Fixed the import behavior where scrubbed database tags
  were restored to newly imported tracks with config settings ``scrub.auto: yes``
  and ``import.write: no``.
  :bug:`4326`
* :doc:`/plugins/deezer`: Fixed the error where Deezer plugin would crash if non-Deezer id is passed during import.
* :doc:`/plugins/fetchart`: Fix fetching from Cover Art Archive when the
  `maxwidth` option is set to one of the supported Cover Art Archive widths.
* :doc:`/plugins/discogs`: Fix "Discogs plugin replacing Feat. or Ft. with
  a comma" by fixing an oversight that removed a functionality from the code
  base when the MetadataSourcePlugin abstract class was introduced in PR's
  #3335 and #3371.
  :bug:`4401`
* :doc:`/plugins/convert`: Set default ``max_bitrate`` value to ``None`` to
  avoid transcoding when this parameter is not set. :bug:`4472`
* :doc:`/plugins/replaygain`: Avoid a crash when errors occur in the analysis
  backend.
  :bug:`4506`
* We now use Python's defaults for command-line argument encoding, which
  should reduce the chance for errors and "file not found" failures when
  invoking other command-line tools, especially on Windows.
  :bug:`4507`
* We now respect the Spotify API's rate limiting, which avoids crashing when the API reports code 429 (too many requests).
  :bug:`4370`
* Fix implicit paths OR queries (e.g. ``beet list /path/ , /other-path/``)
  which have previously been returning the entire library.
  :bug:`1865`
* The Discogs release ID is now populated correctly to the discogs_albumid
  field again (it was no longer working after Discogs changed their release URL
  format).
  :bug:`4225`
* The autotagger no longer considers all matches without a MusicBrainz ID as
  duplicates of each other.
  :bug:`4299`
* :doc:`/plugins/convert`: Resize album art when embedding
  :bug:`2116`
* :doc:`/plugins/deezer`: Fix auto tagger pagination issues (fetch beyond the
  first 25 tracks of a release).
* :doc:`/plugins/spotify`: Fix auto tagger pagination issues (fetch beyond the
  first 50 tracks of a release).
* :doc:`/plugins/lyrics`: Fix Genius search by using query params instead of body.
* :doc:`/plugins/unimported`: The new ``ignore_subdirectories`` configuration
  option added in 1.6.0 now has a default value if it hasn't been set.
* :doc:`/plugins/deezer`: Tolerate missing fields when searching for singleton
  tracks.
  :bug:`4116`
* :doc:`/plugins/replaygain`: The type of the internal ``r128_track_gain`` and
  ``r128_album_gain`` fields was changed from integer to float to fix loss of
  precision due to truncation.
  :bug:`4169`
* Fix a regression in the previous release that caused a `TypeError` when
  moving files across filesystems.
  :bug:`4168`
* :doc:`/plugins/convert`: Deleting the original files during conversion no
  longer logs output when the ``quiet`` flag is enabled.
* :doc:`plugins/web`: Fix handling of "query" requests. Previously queries
  consisting of more than one token (separated by a slash) always returned an
  empty result.
* :doc:`/plugins/discogs`: Skip Discogs query on insufficiently tagged files
  (artist and album tags missing) to prevent arbitrary candidate results.
  :bug:`4227`
* :doc:`plugins/lyrics`: Fixed issues with the Tekstowo.pl and Genius
  backends where some non-lyrics content got included in the lyrics
* :doc:`plugins/limit`: Better header formatting to improve index
* :doc:`plugins/replaygain`: Correctly handle the ``overwrite`` config option,
  which forces recomputing ReplayGain values on import even for tracks
  that already have the tags.
* :doc:`plugins/embedart`: Fix a crash when using recent versions of
  ImageMagick and the ``compare_threshold`` option.
  :bug:`4272`
* :doc:`plugins/lyrics`: Fixed issue with Genius header being included in lyrics,
  added test case of up-to-date Genius html
* :doc:`plugins/importadded`: Fix a bug with recently added reflink import option
  that causes a crash when ImportAdded plugin enabled.
  :bug:`4389`
* :doc:`plugins/convert`: Fix a bug with the `wma` format alias.
* :doc:`/plugins/web`: Fix get file from item.
* :doc:`/plugins/lastgenre`: Fix a duplicated entry for trip hop in the
  default genre list.
  :bug:`4510`
* :doc:`plugins/lyrics`: Fixed issue with Tekstowo backend not actually checking
  if the found song matches.
  :bug:`4406`
* :doc:`plugins/embedart`: Add support for ImageMagick 7.1.1-12
  :bug:`4836`
* :doc:`/plugins/fromfilename`: Fix failed detection of <track> <title>
  filename patterns.
  :bug:`4561` :bug:`4600`
* Fix issue where deletion of flexible fields on an album doesn't cascade to items
  :bug:`4662`
* Fix issue where ``beet write`` continuously retags the ``albumtypes`` metadata
  field in files. Additionally broken data could have been added to the library
  when the tag was read from file back into the library using ``beet update``.
  It is required for all users to **check if such broken data is present in the
  library**. Following the instructions `described here
  <https://github.com/beetbox/beets/pull/4582#issuecomment-1445023493>`_, a
  sanity check and potential fix is easily possible. :bug:`4528`
* Fix updating "data_source" on re-imports and improve logging when flexible
  attributes are being re-imported.
  :bug:`4726`
* :doc:`/plugins/fetchart`: Correctly select the cover art from fanart.tv with
  the highest number of likes
* :doc:`/plugins/lyrics`: Fix a crash with the Google backend when processing
  some web pages. :bug:`4875`
* Modifying flexible attributes of albums now cascade to the individual album
  tracks, similar to how fixed album attributes have been cascading to tracks
  already. A new option ``--noinherit/-I`` to :ref:`modify <modify-cmd>`
  allows changing this behaviour.
  :bug:`4822`
* Fix bug where an interrupted import process poisons the database, causing
  a null path that can't be removed.
  :bug:`4906`
* :doc:`/plugins/discogs`: Fix bug where empty artist and title fields would
  return None instead of an empty list.
  :bug:`4973`
* Fix bug regarding displaying tracks that have been changed not being
  displayed unless the detail configuration is enabled.
* :doc:`/plugins/web`: Fix range request support, allowing to play large audio/
  opus files using e.g. a browser/firefox or gstreamer/mopidy directly.
* Fix bug where `zsh` completion script made assumptions about the specific
  variant of `awk` installed and required specific settings for `sqlite3`
  and caching in `zsh`.
  :bug:`3546`
* Remove unused functions :bug:`5103`
* Fix bug where all media types are reported as the first media type when
  importing with MusicBrainz as the data source
  :bug:`4947`
* Fix bug where unimported plugin would not ignore children directories of
  ignored directories.
  :bug:`5130`
* Fix bug where some plugin commands hang indefinitely due to a missing
  `requests` timeout.
* Fix cover art resizing logic to support multiple steps of resizing
  :bug:`5151`

For plugin developers:

* beets now explicitly prevents multiple plugins to define replacement
  functions for the same field. When previously defining `template_fields`
  for the same field in two plugins, the last loaded plugin would silently
  overwrite the function defined by the other plugin.
  Now, beets will raise an exception when this happens.
  :bug:`5002`
* Allow reuse of some parts of beets' testing components. This may ease the
  work for externally developed plugins or related software (e.g. the beets
  plugin for Mopidy), if they need to create an in-memory instance of a beets
  music library for their tests.

For packagers:

* As noted above, the minimum Python version is now 3.7.
* We fixed a version for the dependency on the `Confuse`_ library.
  :bug:`4167`
* The minimum required version of :pypi:`mediafile` is now 0.9.0.

Other changes:

* Add ``sphinx`` and ``sphinx_rtd_theme`` as dependencies for a new ``docs`` extra
  :bug:`4643`
* :doc:`/plugins/absubmit`: Deprecate the ``absubmit`` plugin since
  AcousticBrainz has stopped accepting new submissions.
  :bug:`4627`
* :doc:`/plugins/acousticbrainz`: Deprecate the ``acousticbrainz`` plugin
  since the AcousticBrainz project has shut down.
  :bug:`4627`
* :doc:`/plugins/limit`: Limit query results to head or tail (``lslimit``
  command only)
* :doc:`/plugins/fish`: Add ``--output`` option.
* :doc:`/plugins/lyrics`: Remove Musixmatch from default enabled sources as
  they are currently blocking requests from the beets user agent.
  :bug:`4585`
* :doc:`/faq`: :ref:`multidisc`: Elaborated the multi-disc FAQ :bug:`4806`
* :doc:`/faq`: :ref:`src`: Removed some long lines.
* Refactor the test cases to avoid test smells.

1.6.0 (November 27, 2021)
-------------------------

This release is our first experiment with time-based releases! We are aiming
to publish a new release of beets every 3 months. We therefore have a healthy
but not dizzyingly long list of new features and fixes.

With this release, beets now requires Python 3.6 or later (it removes support
for Python 2.7, 3.4, and 3.5). There are also a few other dependency
changes---if you're a maintainer of a beets package for a package manager,
thank you for your ongoing efforts, and please see the list of notes below.

Major new features:

* When fetching genres from MusicBrainz, we now include genres from the
  release group (in addition to the release). We also prioritize genres based
  on the number of votes.
  Thanks to :user:`aereaux`.
* Primary and secondary release types from MusicBrainz are now stored in a new
  ``albumtypes`` field.
  Thanks to :user:`edgars-supe`.
  :bug:`2200`
* An accompanying new :doc:`/plugins/albumtypes` includes some options for
  formatting this new ``albumtypes`` field.
  Thanks to :user:`edgars-supe`.
* The :ref:`modify-cmd` and :ref:`import-cmd` can now use
  :doc:`/reference/pathformat` formats when setting fields.
  For example, you can now do ``beet modify title='$track $title'`` to put
  track numbers into songs' titles.
  :bug:`488`

Other new things:

* :doc:`/plugins/permissions`: The plugin now sets cover art permissions to
  match the audio file permissions.
* :doc:`/plugins/unimported`: A new configuration option supports excluding
  specific subdirectories in library.
* :doc:`/plugins/info`: Add support for an ``--album`` flag.
* :doc:`/plugins/export`: Similarly add support for an ``--album`` flag.
* ``beet move`` now highlights path differences in color (when enabled).
* When moving files and a direct rename of a file is not possible (for
  example, when crossing filesystems), beets now copies to a temporary file in
  the target folder first and then moves to the destination instead of
  directly copying the target path. This gets us closer to always updating
  files atomically.
  Thanks to :user:`catap`.
  :bug:`4060`
* :doc:`/plugins/fetchart`: Add a new option to store cover art as
  non-progressive image. This is useful for DAPs that do not support
  progressive images. Set ``deinterlace: yes`` in your configuration to enable
  this conversion.
* :doc:`/plugins/fetchart`: Add a new option to change the file format of
  cover art images. This may also be useful for DAPs that only support some
  image formats.
* Support flexible attributes in ``%aunique``.
  :bug:`2678` :bug:`3553`
* Make ``%aunique`` faster, especially when using inline fields.
  :bug:`4145`

Bug fixes:

* :doc:`/plugins/lyrics`: Fix a crash when Beautiful Soup is not installed.
  :bug:`4027`
* :doc:`/plugins/discogs`: Support a new Discogs URL format for IDs.
  :bug:`4080`
* :doc:`/plugins/discogs`: Remove built-in rate-limiting because the Discogs
  Python library we use now has its own rate-limiting.
  :bug:`4108`
* :doc:`/plugins/export`: Fix some duplicated output.
* :doc:`/plugins/aura`: Fix a potential security hole when serving image
  files.
  :bug:`4160`

For plugin developers:

* :py:meth:`beets.library.Item.destination` now accepts a `replacements`
  argument to be used in favor of the default.
* The `pluginload` event is now sent after plugin types and queries are
  available, not before.
* A new plugin event, `album_removed`, is called when an album is removed from
  the library (even when its file is not deleted from disk).

Here are some notes for packagers:

* As noted above, the minimum Python version is now 3.6.
* We fixed a flaky test, named `test_album_art` in the `test_zero.py` file,
  that some distributions had disabled. Disabling this test should no longer
  be necessary.
  :bug:`4037` :bug:`4038`
* This version of beets no longer depends on the `six`_ library.
  :bug:`4030`
* The `gmusic` plugin was removed since Google Play Music has been shut down.
  Thus, the optional dependency on `gmusicapi` does not exist anymore.
  :bug:`4089`

1.5.0 (August 19, 2021)
-----------------------

This long overdue release of beets includes far too many exciting and useful
features than could ever be satisfactorily enumerated.
As a technical detail, it also introduces two new external libraries:
`MediaFile`_ and `Confuse`_ used to be part of beets but are now reusable
dependencies---packagers, please take note.
Finally, this is the last version of beets where we intend to support Python
2.x and 3.5; future releases will soon require Python 3.6.

One non-technical change is that we moved our official ``#beets`` home
on IRC from freenode to `Libera.Chat`_.

.. _Libera.Chat: https://libera.chat/

Major new features:

* Fields in queries now fall back to an item's album and check its fields too.
  Notably, this allows querying items by an album's attribute: in other words,
  ``beet list foo:bar`` will not only find tracks with the `foo` attribute; it
  will also find tracks *on albums* that have the `foo` attribute. This may be
  particularly useful in the :ref:`path-format-config`, which matches
  individual items to decide which path to use.
  Thanks to :user:`FichteFoll`.
  :bug:`2797` :bug:`2988`
* A new :ref:`reflink` config option instructs the importer to create fast,
  copy-on-write file clones on filesystems that support them. Thanks to
  :user:`rubdos`.
* A new :doc:`/plugins/unimported` lets you find untracked files in your
  library directory.
* The :doc:`/plugins/aura` has arrived! Try out the future of remote music
  library access today.
* We now fetch information about `works`_ from MusicBrainz.
  MusicBrainz matches provide the fields ``work`` (the title), ``mb_workid``
  (the MBID), and ``work_disambig`` (the disambiguation string).
  Thanks to :user:`dosoe`.
  :bug:`2580` :bug:`3272`
* A new :doc:`/plugins/parentwork` gets information about the original work,
  which is useful for classical music.
  Thanks to :user:`dosoe`.
  :bug:`2580` :bug:`3279`
* :doc:`/plugins/bpd`: BPD now supports most of the features of version 0.16
  of the MPD protocol. This is enough to get it talking to more complicated
  clients like ncmpcpp, but there are still some incompatibilities, largely due
  to MPD commands we don't support yet. (Let us know if you find an MPD client
  that doesn't get along with BPD!)
  :bug:`3214` :bug:`800`
* A new :doc:`/plugins/deezer` can autotag tracks and albums using the
  `Deezer`_ database.
  Thanks to :user:`rhlahuja`.
  :bug:`3355`
* A new :doc:`/plugins/bareasc` provides a new query type: "bare ASCII"
  queries that ignore accented characters, treating them as though they
  were plain ASCII characters. Use the ``#`` prefix with :ref:`list-cmd` or
  other commands. :bug:`3882`
* :doc:`/plugins/fetchart`: The plugin can now get album art from `last.fm`_.
  :bug:`3530`
* :doc:`/plugins/web`: The API now supports the HTTP `DELETE` and `PATCH`
  methods for modifying items.
  They are disabled by default; set ``readonly: no`` in your configuration
  file to enable modification via the API.
  :bug:`3870`

Other new things:

* ``beet remove`` now also allows interactive selection of items from the query,
  similar to ``beet modify``.
* Enable HTTPS for MusicBrainz by default and add configuration option
  `https` for custom servers. See :ref:`musicbrainz-config` for more details.
* :doc:`/plugins/mpdstats`: Add a new `strip_path` option to help build the
  right local path from MPD information.
* :doc:`/plugins/convert`: Conversion can now parallelize conversion jobs on
  Python 3.
* :doc:`/plugins/lastgenre`: Add a new `title_case` config option to make
  title-case formatting optional.
* There's a new message when running ``beet config`` when there's no available
  configuration file.
  :bug:`3779`
* When importing a duplicate album, the prompt now says "keep all" instead of
  "keep both" to reflect that there may be more than two albums involved.
  :bug:`3569`
* :doc:`/plugins/chroma`: The plugin now updates file metadata after
  generating fingerprints through the `submit` command.
* :doc:`/plugins/lastgenre`: Added more heavy metal genres to the built-in
  genre filter lists.
* A new :doc:`/plugins/subsonicplaylist` can import playlists from a Subsonic
  server.
* :doc:`/plugins/subsonicupdate`: The plugin now automatically chooses between
  token- and password-based authentication based on the server version.
* A new :ref:`extra_tags` configuration option lets you use more metadata in
  MusicBrainz queries to further narrow the search.
* A new :doc:`/plugins/fish` adds `Fish shell`_ tab autocompletion to beets.
* :doc:`plugins/fetchart` and :doc:`plugins/embedart`: Added a new ``quality``
  option that controls the quality of the image output when the image is
  resized.
* :doc:`plugins/keyfinder`: Added support for `keyfinder-cli`_.
  Thanks to :user:`BrainDamage`.
* :doc:`plugins/fetchart`: Added a new ``high_resolution`` config option to
  allow downloading of higher resolution iTunes artwork (at the expense of
  file size).
  :bug:`3391`
* :doc:`plugins/discogs`: The plugin applies two new fields: `discogs_labelid`
  and `discogs_artistid`.
  :bug:`3413`
* :doc:`/plugins/export`: Added a new ``-f`` (``--format``) flag,
  which can export your data as JSON, JSON lines, CSV, or XML.
  Thanks to :user:`austinmm`.
  :bug:`3402`
* :doc:`/plugins/convert`: Added a new ``-l`` (``--link``) flag and ``link``
  option as well as the ``-H`` (``--hardlink``) flag and ``hardlink``
  option, which symlink or hardlink files that do not need to
  be converted (instead of copying them).
  :bug:`2324`
* :doc:`/plugins/replaygain`: The plugin now supports a ``per_disc`` option
  that enables calculation of album ReplayGain on disc level instead of album
  level.
  Thanks to :user:`samuelnilsson`.
  :bug:`293`
* :doc:`/plugins/replaygain`: The new ``ffmpeg`` ReplayGain backend supports
  ``R128_`` tags.
  :bug:`3056`
* :doc:`plugins/replaygain`: A new ``r128_targetlevel`` configuration option
  defines the reference volume for files using ``R128_`` tags. ``targetlevel``
  only configures the reference volume for ``REPLAYGAIN_`` files.
  :bug:`3065`
* :doc:`/plugins/discogs`: The plugin now collects the "style" field.
  Thanks to :user:`thedevilisinthedetails`.
  :bug:`2579` :bug:`3251`
* :doc:`/plugins/absubmit`: By default, the plugin now avoids re-analyzing
  files that already have AcousticBrainz data.
  There are new ``force`` and ``pretend`` options to help control this new
  behavior.
  Thanks to :user:`SusannaMaria`.
  :bug:`3318`
* :doc:`/plugins/discogs`: The plugin now also gets genre information and a
  new ``discogs_albumid`` field from the Discogs API.
  Thanks to :user:`thedevilisinthedetails`.
  :bug:`465` :bug:`3322`
* :doc:`/plugins/acousticbrainz`: The plugin now fetches two more additional
  fields: ``moods_mirex`` and ``timbre``.
  Thanks to :user:`malcops`.
  :bug:`2860`
* :doc:`/plugins/playlist` and :doc:`/plugins/smartplaylist`: A new
  ``forward_slash`` config option facilitates compatibility with MPD on
  Windows.
  Thanks to :user:`MartyLake`.
  :bug:`3331` :bug:`3334`
* The `data_source` field, which indicates which metadata source was used
  during an autotagging import, is now also applied as an album-level flexible
  attribute.
  :bug:`3350` :bug:`1693`
* :doc:`/plugins/beatport`: The plugin now gets the musical key, BPM, and
  genre for each track.
  :bug:`2080`
* A new :doc:`/plugins/bpsync` can synchronize metadata changes from the
  Beatport database (like the existing :doc:`/plugins/mbsync` for MusicBrainz).
* :doc:`/plugins/hook`: The plugin now treats non-zero exit codes as errors.
  :bug:`3409`
* :doc:`/plugins/subsonicupdate`: A new ``url`` configuration replaces the
  older (and now deprecated) separate ``host``, ``port``, and ``contextpath``
  config options. As a consequence, the plugin can now talk to Subsonic over
  HTTPS.
  Thanks to :user:`jef`.
  :bug:`3449`
* :doc:`/plugins/discogs`: The new ``index_tracks`` option enables
  incorporation of work names and intra-work divisions into imported track
  titles.
  Thanks to :user:`cole-miller`.
  :bug:`3459`
* :doc:`/plugins/web`: The query API now interprets backslashes as path
  separators to support path queries.
  Thanks to :user:`nmeum`.
  :bug:`3567`
* ``beet import`` now handles tar archives with bzip2 or gzip compression.
  :bug:`3606`
* ``beet import`` *also* now handles 7z archives, via the `py7zr`_ library.
  Thanks to :user:`arogl`.
  :bug:`3906`
* :doc:`/plugins/plexupdate`: Added an option to use a secure connection to
  Plex server, and to ignore certificate validation errors if necessary.
  :bug:`2871`
* :doc:`/plugins/convert`: A new ``delete_originals`` configuration option can
  delete the source files after conversion during import.
  Thanks to :user:`logan-arens`.
  :bug:`2947`
* There is a new ``--plugins`` (or ``-p``) CLI flag to specify a list of
  plugins to load.
* A new :ref:`genres` option fetches genre information from MusicBrainz. This
  functionality depends on functionality that is currently unreleased in the
  `python-musicbrainzngs`_ library: see PR `#266
  <https://github.com/alastair/python-musicbrainzngs/pull/266>`_.
  Thanks to :user:`aereaux`.
* :doc:`/plugins/replaygain`: Analysis now happens in parallel using the
  ``command`` and ``ffmpeg`` backends.
  :bug:`3478`
* :doc:`plugins/replaygain`: The bs1770gain backend is removed.
  Thanks to :user:`SamuelCook`.
* Added ``trackdisambig`` which stores the recording disambiguation from
  MusicBrainz for each track.
  :bug:`1904`
* :doc:`plugins/fetchart`: The new ``max_filesize`` configuration sets a
  maximum target image file size.
* :doc:`/plugins/badfiles`: Checkers can now run during import with the
  ``check_on_import`` config option.
* :doc:`/plugins/export`: The plugin is now much faster when using the
  `--include-keys` option is used.
  Thanks to :user:`ssssam`.
* The importer's :ref:`set_fields` option now saves all updated fields to
  on-disk metadata.
  :bug:`3925` :bug:`3927`
* We now fetch ISRC identifiers from MusicBrainz.
  Thanks to :user:`aereaux`.
* :doc:`/plugins/metasync`: The plugin now also fetches the "Date Added" field
  from iTunes databases and stores it in the ``itunes_dateadded`` field.
  Thanks to :user:`sandersantema`.
* :doc:`/plugins/lyrics`: Added a new Tekstowo.pl lyrics provider. Thanks to
  various people for the implementation and for reporting issues with the
  initial version.
  :bug:`3344` :bug:`3904` :bug:`3905` :bug:`3994`
* ``beet update`` will now confirm that the user still wants to update if
  their library folder cannot be found, preventing the user from accidentally
  wiping out their beets database.
  Thanks to user: `logan-arens`.
  :bug:`1934`

Fixes:

* Adapt to breaking changes in Python's ``ast`` module in Python 3.8.
* :doc:`/plugins/beatport`: Fix the assignment of the `genre` field, and
  rename `musical_key` to `initial_key`.
  :bug:`3387`
* :doc:`/plugins/lyrics`: Fixed the Musixmatch backend for lyrics pages when
  lyrics are divided into multiple elements on the webpage, and when the
  lyrics are missing.
* :doc:`/plugins/web`: Allow use of the backslash character in regex queries.
  :bug:`3867`
* :doc:`/plugins/web`: Fixed a small bug that caused the album art path to be
  redacted even when ``include_paths`` option is set.
  :bug:`3866`
* :doc:`/plugins/discogs`: Fixed a bug with the ``index_tracks`` option that
  sometimes caused the index to be discarded. Also, remove the extra semicolon
  that was added when there is no index track.
* :doc:`/plugins/subsonicupdate`: The API client was using the `POST` method
  rather the `GET` method.
  Also includes better exception handling, response parsing, and tests.
* :doc:`/plugins/the`: Fixed incorrect regex for "the" that matched any
  3-letter combination of the letters t, h, e.
  :bug:`3701`
* :doc:`/plugins/fetchart`: Fixed a bug that caused the plugin to not take
  environment variables, such as proxy servers, into account when making
  requests.
  :bug:`3450`
* :doc:`/plugins/fetchart`: Temporary files for fetched album art that fail
  validation are now removed.
* :doc:`/plugins/inline`: In function-style field definitions that refer to
  flexible attributes, values could stick around from one function invocation
  to the next. This meant that, when displaying a list of objects, later
  objects could seem to reuse values from earlier objects when they were
  missing a value for a given field. These values are now properly undefined.
  :bug:`2406`
* :doc:`/plugins/bpd`: Seeking by fractions of a second now works as intended,
  fixing crashes in MPD clients like mpDris2 on seek.
  The ``playlistid`` command now works properly in its zero-argument form.
  :bug:`3214`
* :doc:`/plugins/replaygain`: Fix a Python 3 incompatibility in the Python
  Audio Tools backend.
  :bug:`3305`
* :doc:`/plugins/importadded`: Fixed a crash that occurred when the
  ``after_write`` signal was emitted.
  :bug:`3301`
* :doc:`plugins/replaygain`: Fix the storage format for R128 gain tags.
  :bug:`3311` :bug:`3314`
* :doc:`/plugins/discogs`: Fixed a crash that occurred when the master URI
  isn't set in the API response.
  :bug:`2965` :bug:`3239`
* :doc:`/plugins/spotify`: Fix handling of year-only release dates
  returned by the Spotify albums API.
  Thanks to :user:`rhlahuja`.
  :bug:`3343`
* Fixed a bug that caused the UI to display incorrect track numbers for tracks
  with index 0 when the ``per_disc_numbering`` option was set.
  :bug:`3346`
* ``none_rec_action`` does not import automatically when ``timid`` is enabled.
  Thanks to :user:`RollingStar`.
  :bug:`3242`
* Fix a bug that caused a crash when tagging items with the beatport plugin.
  :bug:`3374`
* ``beet import`` now logs which files are ignored when in debug mode.
  :bug:`3764`
* :doc:`/plugins/bpd`: Fix the transition to next track when in consume mode.
  Thanks to :user:`aereaux`.
  :bug:`3437`
* :doc:`/plugins/lyrics`: Fix a corner-case with Genius lowercase artist names
  :bug:`3446`
* :doc:`/plugins/parentwork`: Don't save tracks when nothing has changed.
  :bug:`3492`
* Added a warning when configuration files defined in the `include` directive
  of the configuration file fail to be imported.
  :bug:`3498`
* Added normalization to integer values in the database, which should avoid
  problems where fields like ``bpm`` would sometimes store non-integer values.
  :bug:`762` :bug:`3507` :bug:`3508`
* Fix a crash when querying for null values.
  :bug:`3516` :bug:`3517`
* :doc:`/plugins/lyrics`: Tolerate a missing lyrics div in the Genius scraper.
  Thanks to :user:`thejli21`.
  :bug:`3535` :bug:`3554`
* :doc:`/plugins/lyrics`: Use the artist sort name to search for lyrics, which
  can help find matches when the artist name has special characters.
  Thanks to :user:`hashhar`.
  :bug:`3340` :bug:`3558`
* :doc:`/plugins/replaygain`: Trying to calculate volume gain for an album
  consisting of some formats using ``ReplayGain`` and some using ``R128``
  will no longer crash; instead it is skipped and and a message is logged.
  The log message has also been rewritten for to improve clarity.
  Thanks to :user:`autrimpo`.
  :bug:`3533`
* :doc:`/plugins/lyrics`: Adapt the Genius backend to changes in markup to
  reduce the scraping failure rate.
  :bug:`3535` :bug:`3594`
* :doc:`/plugins/lyrics`: Fix a crash when writing ReST files for a query
  without results or fetched lyrics.
  :bug:`2805`
* :doc:`/plugins/fetchart`: Attempt to fetch pre-resized thumbnails from Cover
  Art Archive if the ``maxwidth`` option matches one of the sizes supported by
  the Cover Art Archive API.
  Thanks to :user:`trolley`.
  :bug:`3637`
* :doc:`/plugins/ipfs`: Fix Python 3 compatibility.
  Thanks to :user:`musoke`.
  :bug:`2554`
* Fix a bug that caused metadata starting with something resembling a drive
  letter to be incorrectly split into an extra directory after the colon.
  :bug:`3685`
* :doc:`/plugins/mpdstats`: Don't record a skip when stopping MPD, as MPD keeps
  the current track in the queue.
  Thanks to :user:`aereaux`.
  :bug:`3722`
* String-typed fields are now normalized to string values, avoiding an
  occasional crash when using both the :doc:`/plugins/fetchart` and the
  :doc:`/plugins/discogs` together.
  :bug:`3773` :bug:`3774`
* Fix a bug causing PIL to generate poor quality JPEGs when resizing artwork.
  :bug:`3743`
* :doc:`plugins/keyfinder`: Catch output from ``keyfinder-cli`` that is missing key.
  :bug:`2242`
* :doc:`plugins/replaygain`: Disable parallel analysis on import by default.
  :bug:`3819`
* :doc:`/plugins/mpdstats`: Fix Python 2/3 compatibility
  :bug:`3798`
* :doc:`/plugins/discogs`: Replace the deprecated official `discogs-client`
  library with the community supported `python3-discogs-client`_ library.
  :bug:`3608`
* :doc:`/plugins/chroma`: Fixed submitting AcoustID information for tracks
  that already have a fingerprint.
  :bug:`3834`
* Allow equals within the value part of the ``--set`` option to the ``beet
  import`` command.
  :bug:`2984`
* Duplicates can now generate checksums. Thanks :user:`wisp3rwind`
  for the pointer to how to solve. Thanks to :user:`arogl`.
  :bug:`2873`
* Templates that use ``%ifdef`` now produce the expected behavior when used in
  conjunction with non-string fields from the :doc:`/plugins/types`.
  :bug:`3852`
* :doc:`/plugins/lyrics`: Fix crashes when a website could not be retrieved,
  affecting at least the Genius source.
  :bug:`3970`
* :doc:`/plugins/duplicates`: Fix a crash when running the ``dup`` command with
  a query that returns no results.
  :bug:`3943`
* :doc:`/plugins/beatport`: Fix the default assignment of the musical key.
  :bug:`3377`
* :doc:`/plugins/lyrics`: Improved searching on the Genius backend when the
  artist contains special characters.
  :bug:`3634`
* :doc:`/plugins/parentwork`: Also get the composition date of the parent work,
  instead of just the child work.
  Thanks to :user:`aereaux`.
  :bug:`3650`
* :doc:`/plugins/lyrics`: Fix a bug in the heuristic for detecting valid
  lyrics in the Google source.
  :bug:`2969`
* :doc:`/plugins/thumbnails`: Fix a crash due to an incorrect string type on
  Python 3.
  :bug:`3360`
* :doc:`/plugins/fetchart`: The Cover Art Archive source now iterates over
  all front images instead of blindly selecting the first one.
* :doc:`/plugins/lyrics`: Removed the LyricWiki source (the site shut down on
  21/09/2020).
* :doc:`/plugins/subsonicupdate`: The plugin is now functional again. A new
  `auth` configuration option is required in the configuration to specify the
  flavor of authentication to use.
  :bug:`4002`

For plugin developers:

* `MediaFile`_ has been split into a standalone project. Where you used to do
  ``from beets import mediafile``, now just do ``import mediafile``. Beets
  re-exports MediaFile at the old location for backwards-compatibility, but a
  deprecation warning is raised if you do this since we might drop this wrapper
  in a future release.
* Similarly, we've replaced beets' configuration library (previously called
  Confit) with a standalone version called `Confuse`_. Where you used to do
  ``from beets.util import confit``, now just do ``import confuse``. The code
  is almost identical apart from the name change. Again, we'll re-export at the
  old location (with a deprecation warning) for backwards compatibility, but
  we might stop doing this in a future release.
* ``beets.util.command_output`` now returns a named tuple containing both the
  standard output and the standard error data instead of just stdout alone.
  Client code will need to access the ``stdout`` attribute on the return
  value.
  Thanks to :user:`zsinskri`.
  :bug:`3329`
* There were sporadic failures in ``test.test_player``. Hopefully these are
  fixed. If they resurface, please reopen the relevant issue.
  :bug:`3309` :bug:`3330`
* The ``beets.plugins.MetadataSourcePlugin`` base class has been added to
  simplify development of plugins which query album, track, and search
  APIs to provide metadata matches for the importer. Refer to the
  :doc:`/plugins/spotify` and the :doc:`/plugins/deezer` for examples of using
  this template class.
  :bug:`3355`
* Accessing fields on an `Item` now falls back to the album's
  attributes. So, for example, ``item.foo`` will first look for a field `foo` on
  `item` and, if it doesn't exist, next tries looking for a field named `foo`
  on the album that contains `item`. If you specifically want to access an
  item's attributes, use ``Item.get(key, with_album=False)``. :bug:`2988`
* ``Item.keys`` also has a ``with_album`` argument now, defaulting to ``True``.
* A ``revision`` attribute has been added to ``Database``. It is increased on
  every transaction that mutates it. :bug:`2988`
* The classes ``AlbumInfo`` and ``TrackInfo`` now convey arbitrary attributes
  instead of a fixed, built-in set of field names (which was important to
  address :bug:`1547`).
  Thanks to :user:`dosoe`.
* Two new events, ``mb_album_extract`` and ``mb_track_extract``, let plugins
  add new fields based on MusicBrainz data. Thanks to :user:`dosoe`.

For packagers:

* Beets' library for manipulating media file metadata has now been split to a
  standalone project called `MediaFile`_, released as :pypi:`mediafile`. Beets
  now depends on this new package. Beets now depends on Mutagen transitively
  through MediaFile rather than directly, except in the case of one of beets'
  plugins (in particular, the :doc:`/plugins/scrub`).
* Beets' library for configuration has been split into a standalone project
  called `Confuse`_, released as :pypi:`confuse`. Beets now depends on this
  package. Confuse has existed separately for some time and is used by
  unrelated projects, but until now we've been bundling a copy within beets.
* We attempted to fix an unreliable test, so a patch to `skip <https://sources.debian.org/src/beets/1.4.7-2/debian/patches/skip-broken-test/>`_
  or `repair <https://build.opensuse.org/package/view_file/openSUSE:Factory/beets/fix_test_command_line_option_relative_to_working_dir.diff?expand=1>`_
  the test may no longer be necessary.
* This version drops support for Python 3.4.
* We have removed an optional dependency on bs1770gain.

.. _Fish shell: https://fishshell.com/
.. _MediaFile: https://github.com/beetbox/mediafile
.. _Confuse: https://github.com/beetbox/confuse
.. _works: https://musicbrainz.org/doc/Work
.. _Deezer: https://www.deezer.com
.. _keyfinder-cli: https://github.com/EvanPurkhiser/keyfinder-cli
.. _last.fm: https://last.fm
.. _python3-discogs-client: https://github.com/joalla/discogs_client
.. _py7zr: https://pypi.org/project/py7zr/

1.4.9 (May 30, 2019)
--------------------

This small update is part of our attempt to release new versions more often!
There are a few important fixes, and we're clearing the deck for a change to
beets' dependencies in the next version.

The new feature is:

* You can use the `NO_COLOR`_ environment variable to disable terminal colors.
  :bug:`3273`

There are some fixes in this release:

* Fix a regression in the last release that made the image resizer fail to
  detect older versions of ImageMagick.
  :bug:`3269`
* :doc:`/plugins/gmusic`: The ``oauth_file`` config option now supports more
  flexible path values, including ``~`` for the home directory.
  :bug:`3270`
* :doc:`/plugins/gmusic`: Fix a crash when using version 12.0.0 or later of
  the ``gmusicapi`` module.
  :bug:`3270`
* Fix an incompatibility with Python 3.8's AST changes.
  :bug:`3278`

Here's a note for packagers:

* ``pathlib`` is now an optional test dependency on Python 3.4+, removing the
  need for `a Debian patch <https://sources.debian.org/src/beets/1.4.7-2/debian/patches/pathlib-is-stdlib/>`_.
  :bug:`3275`

.. _NO_COLOR: https://no-color.org

1.4.8 (May 16, 2019)
--------------------

This release is far too long in coming, but it's a good one. There is the
usual torrent of new features and a ridiculously long line of fixes, but there
are also some crucial maintenance changes.
We officially support Python 3.7 and 3.8, and some performance optimizations
can (anecdotally) make listing your library more than three times faster than
in the previous version.

The new core features are:

* A new :ref:`config-aunique` configuration option allows setting default
  options for the :ref:`aunique` template function.
* The ``albumdisambig`` field no longer includes the MusicBrainz release group
  disambiguation comment. A new ``releasegroupdisambig`` field has been added.
  :bug:`3024`
* The :ref:`modify-cmd` command now allows resetting fixed attributes. For
  example, ``beet modify -a artist:beatles artpath!`` resets ``artpath``
  attribute from matching albums back to the default value.
  :bug:`2497`
* A new importer option, :ref:`ignore_data_tracks`, lets you skip audio tracks
  contained in data files. :bug:`3021`

There are some new plugins:

* The :doc:`/plugins/playlist` can query the beets library using M3U playlists.
  Thanks to :user:`Holzhaus` and :user:`Xenopathic`.
  :bug:`123` :bug:`3145`
* The :doc:`/plugins/loadext` allows loading of SQLite extensions, primarily
  for use with the ICU SQLite extension for internationalization.
  :bug:`3160` :bug:`3226`
* The :doc:`/plugins/subsonicupdate` can automatically update your Subsonic
  library.
  Thanks to :user:`maffo999`.
  :bug:`3001`

And many improvements to existing plugins:

* :doc:`/plugins/lastgenre`: Added option ``-A`` to match individual tracks
  and singletons.
  :bug:`3220` :bug:`3219`
* :doc:`/plugins/play`: The plugin can now emit a UTF-8 BOM, fixing some
  issues with foobar2000 and Winamp.
  Thanks to :user:`mz2212`.
  :bug:`2944`
* :doc:`/plugins/gmusic`:
   * Add a new option to automatically upload to Google Play Music library on
     track import.
     Thanks to :user:`shuaiscott`.
   * Add new options for Google Play Music authentication.
     Thanks to :user:`thetarkus`.
     :bug:`3002`
* :doc:`/plugins/replaygain`: ``albumpeak`` on large collections is calculated
  as the average, not the maximum.
  :bug:`3008` :bug:`3009`
* :doc:`/plugins/chroma`:
   * Now optionally has a bias toward looking up more relevant releases
     according to the :ref:`preferred` configuration options.
     Thanks to :user:`archer4499`.
     :bug:`3017`
   * Fingerprint values are now properly stored as strings, which prevents
     strange repeated output when running ``beet write``.
     Thanks to :user:`Holzhaus`.
     :bug:`3097` :bug:`2942`
* :doc:`/plugins/convert`: The plugin now has an ``id3v23`` option that allows
  you to override the global ``id3v23`` option.
  Thanks to :user:`Holzhaus`.
  :bug:`3104`
* :doc:`/plugins/spotify`:
   * The plugin now uses OAuth for authentication to the Spotify API.
     Thanks to :user:`rhlahuja`.
     :bug:`2694` :bug:`3123`
   * The plugin now works as an import metadata
     provider: you can match tracks and albums using the Spotify database.
     Thanks to :user:`rhlahuja`.
     :bug:`3123`
* :doc:`/plugins/ipfs`: The plugin now supports a ``nocopy`` option which
  passes that flag to ipfs.
  Thanks to :user:`wildthyme`.
* :doc:`/plugins/discogs`: The plugin now has rate limiting for the Discogs API.
  :bug:`3081`
* :doc:`/plugins/mpdstats`, :doc:`/plugins/mpdupdate`: These plugins now use
  the ``MPD_PORT`` environment variable if no port is specified in the
  configuration file.
  :bug:`3223`
* :doc:`/plugins/bpd`:
   * MPD protocol commands ``consume`` and ``single`` are now supported along
     with updated semantics for ``repeat`` and ``previous`` and new fields for
     ``status``. The bpd server now understands and ignores some additional
     commands.
     :bug:`3200` :bug:`800`
   * MPD protocol command ``idle`` is now supported, allowing the MPD version
     to be bumped to 0.14.
     :bug:`3205` :bug:`800`
   * MPD protocol command ``decoders`` is now supported.
     :bug:`3222`
   * The plugin now uses the main beets logging system.
     The special-purpose ``--debug`` flag has been removed.
     Thanks to :user:`arcresu`.
     :bug:`3196`
* :doc:`/plugins/mbsync`: The plugin no longer queries MusicBrainz when either
  the ``mb_albumid`` or ``mb_trackid`` field is invalid.
  See also the discussion on `Google Groups`_
  Thanks to :user:`arogl`.
* :doc:`/plugins/export`: The plugin now also exports ``path`` field if the user
  explicitly specifies it with ``-i`` parameter. This only works when exporting
  library fields.
  :bug:`3084`
* :doc:`/plugins/acousticbrainz`: The plugin now declares types for all its
  fields, which enables easier querying and avoids a problem where very small
  numbers would be stored as strings.
  Thanks to :user:`rain0r`.
  :bug:`2790` :bug:`3238`

.. _Google Groups: https://groups.google.com/forum/#!searchin/beets-users/mbsync|sort:date/beets-users/iwCF6bNdh9A/i1xl4Gx8BQAJ

Some improvements have been focused on improving beets' performance:

* Querying the library is now faster:
    * We only convert fields that need to be displayed.
      Thanks to :user:`pprkut`.
      :bug:`3089`
    * We now compile templates once and reuse them instead of recompiling them
      to print out each matching object.
      Thanks to :user:`SimonPersson`.
      :bug:`3258`
    * Querying the library for items is now faster, for all queries that do not
      need to access album level properties. This was implemented by lazily
      fetching the album only when needed.
      Thanks to :user:`SimonPersson`.
      :bug:`3260`
* :doc:`/plugins/absubmit`, :doc:`/plugins/badfiles`: Analysis now works in
  parallel (on Python 3 only).
  Thanks to :user:`bemeurer`.
  :bug:`2442` :bug:`3003`
* :doc:`/plugins/mpdstats`: Use the ``currentsong`` MPD command instead of
  ``playlist`` to get the current song, improving performance when the playlist
  is long.
  Thanks to :user:`ray66`.
  :bug:`3207` :bug:`2752`

Several improvements are related to usability:

* The disambiguation string for identifying albums in the importer now shows
  the catalog number.
  Thanks to :user:`8h2a`.
  :bug:`2951`
* Added whitespace padding to missing tracks dialog to improve readability.
  Thanks to :user:`jams2`.
  :bug:`2962`
* The :ref:`move-cmd` command now lists the number of items already in-place.
  Thanks to :user:`RollingStar`.
  :bug:`3117`
* Modify selection can now be applied early without selecting every item.
  :bug:`3083`
* Beets now emits more useful messages during startup if SQLite returns an error. The
  SQLite error message is now attached to the beets message.
  :bug:`3005`
* Fixed a confusing typo when the :doc:`/plugins/convert` plugin copies the art
  covers.
  :bug:`3063`

Many fixes have been focused on issues where beets would previously crash:

* Avoid a crash when archive extraction fails during import.
  :bug:`3041`
* Missing album art file during an update no longer causes a fatal exception
  (instead, an error is logged and the missing file path is removed from the
  library).
  :bug:`3030`
* When updating the database, beets no longer tries to move album art twice.
  :bug:`3189`
* Fix an unhandled exception when pruning empty directories.
  :bug:`1996` :bug:`3209`
* :doc:`/plugins/fetchart`: Added network connection error handling to backends
  so that beets won't crash if a request fails.
  Thanks to :user:`Holzhaus`.
  :bug:`1579`
* :doc:`/plugins/badfiles`: Avoid a crash when the underlying tool emits
  undecodable output.
  :bug:`3165`
* :doc:`/plugins/beatport`: Avoid a crash when the server produces an error.
  :bug:`3184`
* :doc:`/plugins/bpd`: Fix crashes in the bpd server during exception handling.
  :bug:`3200`
* :doc:`/plugins/bpd`: Fix a crash triggered when certain clients tried to list
  the albums belonging to a particular artist.
  :bug:`3007` :bug:`3215`
* :doc:`/plugins/replaygain`: Avoid a crash when the ``bs1770gain`` tool emits
  malformed XML.
  :bug:`2983` :bug:`3247`

There are many fixes related to compatibility with our dependencies including
addressing changes interfaces:

* On Python 2, pin the :pypi:`jellyfish` requirement to version 0.6.0 for
  compatibility.
* Fix compatibility with Python 3.7 and its change to a name in the
  :stdlib:`re` module.
  :bug:`2978`
* Fix several uses of deprecated standard-library features on Python 3.7.
  Thanks to :user:`arcresu`.
  :bug:`3197`
* Fix compatibility with pre-release versions of Python 3.8.
  :bug:`3201` :bug:`3202`
* :doc:`/plugins/web`: Fix an error when using more recent versions of Flask
  with CORS enabled.
  Thanks to :user:`rveachkc`.
  :bug:`2979`: :bug:`2980`
* Avoid some deprecation warnings with certain versions of the MusicBrainz
  library.
  Thanks to :user:`zhelezov`.
  :bug:`2826` :bug:`3092`
* Restore iTunes Store album art source, and remove the dependency on
  :pypi:`python-itunes`, which had gone unmaintained and was not
  Python-3-compatible.
  Thanks to :user:`ocelma` for creating :pypi:`python-itunes` in the first place.
  Thanks to :user:`nathdwek`.
  :bug:`2371` :bug:`2551` :bug:`2718`
* :doc:`/plugins/lastgenre`, :doc:`/plugins/edit`: Avoid a deprecation warnings
  from the :pypi:`PyYAML` library by switching to the safe loader.
  Thanks to :user:`translit` and :user:`sbraz`.
  :bug:`3192` :bug:`3225`
* Fix a problem when resizing images with :pypi:`PIL`/:pypi:`pillow` on Python 3.
  Thanks to :user:`architek`.
  :bug:`2504` :bug:`3029`

And there are many other fixes:

* R128 normalization tags are now properly deleted from files when the values
  are missing.
  Thanks to :user:`autrimpo`.
  :bug:`2757`
* Display the artist credit when matching albums if the :ref:`artist_credit`
  configuration option is set.
  :bug:`2953`
* With the :ref:`from_scratch` configuration option set, only writable fields
  are cleared. Beets now no longer ignores the format your music is saved in.
  :bug:`2972`
* The ``%aunique`` template function now works correctly with the
  ``-f/--format`` option.
  :bug:`3043`
* Fixed the ordering of items when manually selecting changes while updating
  tags
  Thanks to :user:`TaizoSimpson`.
  :bug:`3501`
* The ``%title`` template function now works correctly with apostrophes.
  Thanks to :user:`GuilhermeHideki`.
  :bug:`3033`
* :doc:`/plugins/lastgenre`: It's now possible to set the ``prefer_specific``
  option without also setting ``canonical``.
  :bug:`2973`
* :doc:`/plugins/fetchart`: The plugin now respects the ``ignore`` and
  ``ignore_hidden`` settings.
  :bug:`1632`
* :doc:`/plugins/hook`: Fix byte string interpolation in hook commands.
  :bug:`2967` :bug:`3167`
* :doc:`/plugins/the`: Log a message when something has changed, not when it
  hasn't.
  Thanks to :user:`arcresu`.
  :bug:`3195`
* :doc:`/plugins/lastgenre`: The ``force`` config option now actually works.
  :bug:`2704` :bug:`3054`
* Resizing image files with ImageMagick now avoids problems on systems where
  there is a ``convert`` command that is *not* ImageMagick's by using the
  ``magick`` executable when it is available.
  Thanks to :user:`ababyduck`.
  :bug:`2093` :bug:`3236`

There is one new thing for plugin developers to know about:

* In addition to prefix-based field queries, plugins can now define *named
  queries* that are not associated with any specific field.
  For example, the new :doc:`/plugins/playlist` supports queries like
  ``playlist:name`` although there is no field named ``playlist``.
  See :ref:`extend-query` for details.

And some messages for packagers:

* Note the changes to the dependencies on :pypi:`jellyfish` and :pypi:`munkres`.
* The optional :pypi:`python-itunes` dependency has been removed.
* Python versions 3.7 and 3.8 are now supported.

1.4.7 (May 29, 2018)
--------------------

This new release includes lots of new features in the importer and the
metadata source backends that it uses.
We've changed how the beets importer handles non-audio tracks listed in
metadata sources like MusicBrainz:

* The importer now ignores non-audio tracks (namely, data and video tracks)
  listed in MusicBrainz. Also, a new option, :ref:`ignore_video_tracks`, lets
  you return to the old behavior and include these video tracks.
  :bug:`1210`
* A new importer option, :ref:`ignored_media`, can let you skip certain media
  formats.
  :bug:`2688`

There are other subtle improvements to metadata handling in the importer:

* In the MusicBrainz backend, beets now imports the
  ``musicbrainz_releasetrackid`` field. This is a first step toward
  :bug:`406`.
  Thanks to :user:`Rawrmonkeys`.
* A new importer configuration option, :ref:`artist_credit`, will tell beets
  to prefer the artist credit over the artist when autotagging.
  :bug:`1249`

And there are even more new features:

* :doc:`/plugins/replaygain`: The ``beet replaygain`` command now has
  ``--force``, ``--write`` and ``--nowrite`` options. :bug:`2778`
* A new importer configuration option, :ref:`incremental_skip_later`, lets you
  avoid recording skipped directories to the list of "processed" directories
  in :ref:`incremental` mode. This way, you can revisit them later with
  another import.
  Thanks to :user:`sekjun9878`.
  :bug:`2773`
* :doc:`/plugins/fetchart`: The configuration options now support
  finer-grained control via the ``sources`` option. You can now specify the
  search order for different *matching strategies* within different backends.
* :doc:`/plugins/web`: A new ``cors_supports_credentials`` configuration
  option lets in-browser clients communicate with the server even when it is
  protected by an authorization mechanism (a proxy with HTTP authentication
  enabled, for example).
* A new :doc:`/plugins/sonosupdate` plugin automatically notifies Sonos
  controllers to update the music library when the beets library changes.
  Thanks to :user:`cgtobi`.
* :doc:`/plugins/discogs`: The plugin now stores master release IDs into
  ``mb_releasegroupid``. It also "simulates" track IDs using the release ID
  and the track list position.
  Thanks to :user:`dbogdanov`.
  :bug:`2336`
* :doc:`/plugins/discogs`: Fetch the original year from master releases.
  :bug:`1122`

There are lots and lots of fixes:

* :doc:`/plugins/replaygain`: Fix a corner-case with the ``bs1770gain`` backend
  where ReplayGain values were assigned to the wrong files. The plugin now
  requires version 0.4.6 or later of the ``bs1770gain`` tool.
  :bug:`2777`
* :doc:`/plugins/lyrics`: The plugin no longer crashes in the Genius source
  when BeautifulSoup is not found. Instead, it just logs a message and
  disables the source.
  :bug:`2911`
* :doc:`/plugins/lyrics`: Handle network and API errors when communicating
  with Genius. :bug:`2771`
* :doc:`/plugins/lyrics`: The ``lyrics`` command previously wrote ReST files
  by default, even when you didn't ask for them. This default has been fixed.
* :doc:`/plugins/lyrics`: When writing ReST files, the ``lyrics`` command
  now groups lyrics by the ``albumartist`` field, rather than ``artist``.
  :bug:`2924`
* Plugins can now see updated import task state, such as when rejecting the
  initial candidates and finding new ones via a manual search. Notably, this
  means that the importer prompt options that the :doc:`/plugins/edit`
  provides show up more reliably after doing a secondary import search.
  :bug:`2441` :bug:`2731`
* :doc:`/plugins/importadded`: Fix a crash on non-autotagged imports.
  Thanks to :user:`m42i`.
  :bug:`2601` :bug:`1918`
* :doc:`/plugins/plexupdate`: The Plex token is now redacted in configuration
  output.
  Thanks to :user:`Kovrinic`.
  :bug:`2804`
* Avoid a crash when importing a non-ASCII filename when using an ASCII locale
  on Unix under Python 3.
  :bug:`2793` :bug:`2803`
* Fix a problem caused by time zone misalignment that could make date queries
  fail to match certain dates that are near the edges of a range. For example,
  querying for dates within a certain month would fail to match dates within
  hours of the end of that month.
  :bug:`2652`
* :doc:`/plugins/convert`: The plugin now runs before other plugin-provided
  import stages, which addresses an issue with generating ReplayGain data
  incompatible between the source and target file formats.
  Thanks to :user:`autrimpo`.
  :bug:`2814`
* :doc:`/plugins/ftintitle`: The ``drop`` config option had no effect; it now
  does what it says it should do.
  :bug:`2817`
* Importing a release with multiple release events now selects the
  event based on the order of your :ref:`preferred` countries rather than
  the order of release events in MusicBrainz. :bug:`2816`
* :doc:`/plugins/web`: The time display in the web interface would incorrectly jump
  at the 30-second mark of every minute. Now, it correctly changes over at zero
  seconds. :bug:`2822`
* :doc:`/plugins/web`: Fetching album art now works (instead of throwing an
  exception) under Python 3.
  Additionally, the server will now return a 404 response when the album ID
  is unknown (instead of throwing an exception and producing a 500 response).
  :bug:`2823`
* :doc:`/plugins/web`: Fix an exception on Python 3 for filenames with
  non-Latin1 characters. (These characters are now converted to their ASCII
  equivalents.)
  :bug:`2815`
* Partially fix bash completion for subcommand names that contain hyphens.
  Thanks to :user:`jhermann`.
  :bug:`2836` :bug:`2837`
* :doc:`/plugins/replaygain`: Really fix album gain calculation using the
  GStreamer backend. :bug:`2846`
* Avoid an error when doing a "no-op" move on non-existent files (i.e., moving
  a file onto itself). :bug:`2863`
* :doc:`/plugins/discogs`: Fix the ``medium`` and ``medium_index`` values, which
  were occasionally incorrect for releases with two-sided mediums such as
  vinyl. Also fix the ``medium_total`` value, which now contains total number
  of tracks on the medium to which a track belongs, not the total number of
  different mediums present on the release.
  Thanks to :user:`dbogdanov`.
  :bug:`2887`
* The importer now supports audio files contained in data tracks when they are
  listed in MusicBrainz: the corresponding audio tracks are now merged into the
  main track list. Thanks to :user:`jdetrey`. :bug:`1638`
* :doc:`/plugins/keyfinder`: Avoid a crash when trying to process unmatched
  tracks. :bug:`2537`
* :doc:`/plugins/mbsync`: Support MusicBrainz recording ID changes, relying
  on release track IDs instead. Thanks to :user:`jdetrey`. :bug:`1234`
* :doc:`/plugins/mbsync`: We can now successfully update albums even when the
  first track has a missing MusicBrainz recording ID. :bug:`2920`

There are a couple of changes for developers:

* Plugins can now run their import stages *early*, before other plugins. Use
  the ``early_import_stages`` list instead of plain ``import_stages`` to
  request this behavior.
  :bug:`2814`
* We again properly send ``albuminfo_received`` and ``trackinfo_received`` in
  all cases, most notably when using the ``mbsync`` plugin. This was a
  regression since version 1.4.1.
  :bug:`2921`

1.4.6 (December 21, 2017)
-------------------------

The highlight of this release is "album merging," an oft-requested option in
the importer to add new tracks to an existing album you already have in your
library. This way, you no longer need to resort to removing the partial album
from your library, combining the files manually, and importing again.

Here are the larger new features in this release:

* When the importer finds duplicate albums, you can now merge all the
  tracks---old and new---together and try importing them as a single, combined
  album.
  Thanks to :user:`udiboy1209`.
  :bug:`112` :bug:`2725`
* :doc:`/plugins/lyrics`: The plugin can now produce reStructuredText files
  for beautiful, readable books of lyrics. Thanks to :user:`anarcat`.
  :bug:`2628`
* A new :ref:`from_scratch` configuration option makes the importer remove old
  metadata before applying new metadata. This new feature complements the
  :doc:`zero </plugins/zero>` and :doc:`scrub </plugins/scrub>` plugins but is
  slightly different: beets clears out all the old tags it knows about and
  only keeps the new data it gets from the remote metadata source.
  Thanks to :user:`tummychow`.
  :bug:`934` :bug:`2755`

There are also somewhat littler, but still great, new features:

* :doc:`/plugins/convert`: A new ``no_convert`` option lets you skip
  transcoding items matching a query. Instead, the files are just copied
  as-is.  Thanks to :user:`Stunner`.
  :bug:`2732` :bug:`2751`
* :doc:`/plugins/fetchart`: A new quiet switch that only prints out messages
  when album art is missing.
  Thanks to :user:`euri10`.
  :bug:`2683`
* :doc:`/plugins/mbcollection`: You can configure a custom MusicBrainz
  collection via the new ``collection`` configuration option.
  :bug:`2685`
* :doc:`/plugins/mbcollection`: The collection update command can now remove
  albums from collections that are longer in the beets library.
* :doc:`/plugins/fetchart`: The ``clearart`` command now asks for confirmation
  before touching your files.
  Thanks to :user:`konman2`.
  :bug:`2708` :bug:`2427`
* :doc:`/plugins/mpdstats`: The plugin now correctly updates song statistics
  when MPD switches from a song to a stream and when it plays the same song
  multiple times consecutively.
  :bug:`2707`
* :doc:`/plugins/acousticbrainz`: The plugin can now be configured to write only
  a specific list of tags.
  Thanks to :user:`woparry`.

There are lots and lots of bug fixes:

* :doc:`/plugins/hook`: Fixed a problem where accessing non-string properties
  of ``item`` or ``album`` (e.g., ``item.track``) would cause a crash.
  Thanks to :user:`broddo`.
  :bug:`2740`
* :doc:`/plugins/play`: When ``relative_to`` is set, the plugin correctly
  emits relative paths even when querying for albums rather than tracks.
  Thanks to :user:`j000`.
  :bug:`2702`
* We suppress a spurious Python warning about a ``BrokenPipeError`` being
  ignored. This was an issue when using beets in simple shell scripts.
  Thanks to :user:`Azphreal`.
  :bug:`2622` :bug:`2631`
* :doc:`/plugins/replaygain`: Fix a regression in the previous release related
  to the new R128 tags. :bug:`2615` :bug:`2623`
* :doc:`/plugins/lyrics`: The MusixMatch backend now detects and warns
  when the server has blocked the client.
  Thanks to :user:`anarcat`. :bug:`2634` :bug:`2632`
* :doc:`/plugins/importfeeds`: Fix an error on Python 3 in certain
  configurations. Thanks to :user:`djl`. :bug:`2467` :bug:`2658`
* :doc:`/plugins/edit`: Fix a bug when editing items during a re-import with
  the ``-L`` flag. Previously, diffs against against unrelated items could be
  shown or beets could crash. :bug:`2659`
* :doc:`/plugins/kodiupdate`: Fix the server URL and add better error
  reporting.
  :bug:`2662`
* Fixed a problem where "no-op" modifications would reset files' mtimes,
  resulting in unnecessary writes. This most prominently affected the
  :doc:`/plugins/edit` when saving the text file without making changes to some
  music. :bug:`2667`
* :doc:`/plugins/chroma`: Fix a crash when running the ``submit`` command on
  Python 3 on Windows with non-ASCII filenames. :bug:`2671`
* :doc:`/plugins/absubmit`: Fix an occasional crash on Python 3 when the AB
  analysis tool produced non-ASCII metadata. :bug:`2673`
* :doc:`/plugins/duplicates`: Use the default tiebreak for items or albums
  when the configuration only specifies a tiebreak for the other kind of
  entity.
  Thanks to :user:`cgevans`.
  :bug:`2758`
* :doc:`/plugins/duplicates`: Fix the ``--key`` command line option, which was
  ignored.
* :doc:`/plugins/replaygain`: Fix album ReplayGain calculation with the
  GStreamer backend. :bug:`2636`
* :doc:`/plugins/scrub`: Handle errors when manipulating files using newer
  versions of Mutagen. :bug:`2716`
* :doc:`/plugins/fetchart`: The plugin no longer gets skipped during import
  when the "Edit Candidates" option is used from the :doc:`/plugins/edit`.
  :bug:`2734`
* Fix a crash when numeric metadata fields contain just a minus or plus sign
  with no following numbers. Thanks to :user:`eigengrau`. :bug:`2741`
* :doc:`/plugins/fromfilename`: Recognize file names that contain *only* a
  track number, such as `01.mp3`. Also, the plugin now allows underscores as a
  separator between fields.
  Thanks to :user:`Vrihub`.
  :bug:`2738` :bug:`2759`
* Fixed an issue where images would be resized according to their longest
  edge, instead of their width, when using the ``maxwidth`` config option in
  the :doc:`/plugins/fetchart` and :doc:`/plugins/embedart`. Thanks to
  :user:`sekjun9878`. :bug:`2729`

There are some changes for developers:

* "Fixed fields" in Album and Item objects are now more strict about translating
  missing values into type-specific null-like values. This should help in
  cases where a string field is unexpectedly `None` sometimes instead of just
  showing up as an empty string. :bug:`2605`
* Refactored the move functions the `beets.library` module and the
  `manipulate_files` function in `beets.importer` to use a single parameter
  describing the file operation instead of multiple Boolean flags.
  There is a new numerated type describing how to move, copy, or link files.
  :bug:`2682`

1.4.5 (June 20, 2017)
---------------------

Version 1.4.5 adds some oft-requested features. When you're importing files,
you can now manually set fields on the new music. Date queries have gotten
much more powerful: you can write precise queries down to the second, and we
now have *relative* queries like ``-1w``, which means *one week ago*.

Here are the new features:

* You can now set fields to certain values during :ref:`import-cmd`, using
  either a ``--set field=value`` command-line flag or a new :ref:`set_fields`
  configuration option under the `importer` section.
  Thanks to :user:`bartkl`. :bug:`1881` :bug:`2581`
* :ref:`Date queries <datequery>` can now include times, so you can filter
  your music down to the second. Thanks to :user:`discopatrick`. :bug:`2506`
  :bug:`2528`
* :ref:`Date queries <datequery>` can also be *relative*. You can say
  ``added:-1w..`` to match music added in the last week, for example. Thanks
  to :user:`euri10`. :bug:`2598`
* A new :doc:`/plugins/gmusic` lets you interact with your Google Play Music
  library. Thanks to :user:`tigranl`. :bug:`2553` :bug:`2586`
* :doc:`/plugins/replaygain`: We now keep R128 data in separate tags from
  classic ReplayGain data for formats that need it (namely, Ogg Opus). A new
  `r128` configuration option enables this behavior for specific formats.
  Thanks to :user:`autrimpo`. :bug:`2557` :bug:`2560`
* The :ref:`move-cmd` command gained a new ``--export`` flag, which copies
  files to an external location without changing their paths in the library
  database. Thanks to :user:`SpirosChadoulos`. :bug:`435` :bug:`2510`

There are also some bug fixes:

* :doc:`/plugins/lastgenre`: Fix a crash when using the `prefer_specific` and
  `canonical` options together. Thanks to :user:`yacoob`. :bug:`2459`
  :bug:`2583`
* :doc:`/plugins/web`: Fix a crash on Windows under Python 2 when serving
  non-ASCII filenames. Thanks to :user:`robot3498712`. :bug:`2592` :bug:`2593`
* :doc:`/plugins/metasync`: Fix a crash in the Amarok backend when filenames
  contain quotes. Thanks to :user:`aranc23`. :bug:`2595` :bug:`2596`
* More informative error messages are displayed when the file format is not
  recognized. :bug:`2599`

1.4.4 (June 10, 2017)
---------------------

This release built up a longer-than-normal list of nifty new features. We now
support DSF audio files and the importer can hard-link your files, for
example.

Here's a full list of new features:

* Added support for DSF files, once a future version of Mutagen is released
  that supports them. Thanks to :user:`docbobo`. :bug:`459` :bug:`2379`
* A new :ref:`hardlink` config option instructs the importer to create hard
  links on filesystems that support them. Thanks to :user:`jacobwgillespie`.
  :bug:`2445`
* A new :doc:`/plugins/kodiupdate` lets you keep your Kodi library in sync
  with beets. Thanks to :user:`Pauligrinder`. :bug:`2411`
* A new :ref:`bell` configuration option under the ``import`` section enables
  a terminal bell when input is required. Thanks to :user:`SpirosChadoulos`.
  :bug:`2366` :bug:`2495`
* A new field, ``composer_sort``, is now supported and fetched from
  MusicBrainz.
  Thanks to :user:`dosoe`.
  :bug:`2519` :bug:`2529`
* The MusicBrainz backend and  :doc:`/plugins/discogs` now both provide a new
  attribute called ``track_alt`` that stores more nuanced, possibly
  non-numeric track index data. For example, some vinyl or tape media will
  report the side of the record using a letter instead of a number in that
  field. :bug:`1831` :bug:`2363`
* :doc:`/plugins/web`: Added a new endpoint, ``/item/path/foo``, which will
  return the item info for the file at the given path, or 404.
* :doc:`/plugins/web`: Added a new config option, ``include_paths``,
  which will cause paths to be included in item API responses if set to true.
* The ``%aunique`` template function for :ref:`aunique` now takes a third
  argument that specifies which brackets to use around the disambiguator
  value.  The argument can be any two characters that represent the left and
  right brackets. It defaults to `[]` and can also be blank to turn off
  bracketing. :bug:`2397` :bug:`2399`
* Added a ``--move`` or ``-m`` option to the importer so that the files can be
  moved to the library instead of being copied or added "in place."
  :bug:`2252` :bug:`2429`
* :doc:`/plugins/badfiles`: Added a ``--verbose`` or ``-v`` option. Results are
  now displayed only for corrupted files by default and for all the files when
  the verbose option is set. :bug:`1654` :bug:`2434`
* :doc:`/plugins/embedart`: The explicit ``embedart`` command now asks for
  confirmation before embedding art into music files. Thanks to
  :user:`Stunner`. :bug:`1999`
* You can now run beets by typing `python -m beets`. :bug:`2453`
* :doc:`/plugins/smartplaylist`: Different playlist specifications that
  generate identically-named playlist files no longer conflict; instead, the
  resulting lists of tracks are concatenated. :bug:`2468`
* :doc:`/plugins/missing`: A new mode lets you see missing albums from artists
  you have in your library. Thanks to :user:`qlyoung`. :bug:`2481`
* :doc:`/plugins/web` : Add new `reverse_proxy` config option to allow serving
  the web plugins under a reverse proxy.
* Importing a release with multiple release events now selects the
  event based on your :ref:`preferred` countries. :bug:`2501`
* :doc:`/plugins/play`: A new ``-y`` or ``--yes`` parameter lets you skip
  the warning message if you enqueue more items than the warning threshold
  usually allows.
* Fix a bug where commands which forked subprocesses would sometimes prevent
  further inputs. This bug mainly affected :doc:`/plugins/convert`.
  Thanks to :user:`jansol`.
  :bug:`2488`
  :bug:`2524`

There are also quite a few fixes:

* In the :ref:`replace` configuration option, we now replace a leading hyphen
  (-) with an underscore. :bug:`549` :bug:`2509`
* :doc:`/plugins/absubmit`: We no longer filter audio files for specific
  formats---we will attempt the submission process for all formats. :bug:`2471`
* :doc:`/plugins/mpdupdate`: Fix Python 3 compatibility. :bug:`2381`
* :doc:`/plugins/replaygain`: Fix Python 3 compatibility in the ``bs1770gain``
  backend. :bug:`2382`
* :doc:`/plugins/bpd`: Report playback times as integers. :bug:`2394`
* :doc:`/plugins/mpdstats`: Fix Python 3 compatibility. The plugin also now
  requires version 0.4.2 or later of the ``python-mpd2`` library. :bug:`2405`
* :doc:`/plugins/mpdstats`: Improve handling of MPD status queries.
* :doc:`/plugins/badfiles`: Fix Python 3 compatibility.
* Fix some cases where album-level ReplayGain/SoundCheck metadata would be
  written to files incorrectly. :bug:`2426`
* :doc:`/plugins/badfiles`: The command no longer bails out if the validator
  command is not found or exits with an error. :bug:`2430` :bug:`2433`
* :doc:`/plugins/lyrics`: The Google search backend no longer crashes when the
  server responds with an error. :bug:`2437`
* :doc:`/plugins/discogs`: You can now authenticate with Discogs using a
  personal access token. :bug:`2447`
* Fix Python 3 compatibility when extracting rar archives in the importer.
  Thanks to :user:`Lompik`. :bug:`2443` :bug:`2448`
* :doc:`/plugins/duplicates`: Fix Python 3 compatibility when using the
  ``copy`` and ``move`` options. :bug:`2444`
* :doc:`/plugins/mbsubmit`: The tracks are now sorted properly. Thanks to
  :user:`awesomer`. :bug:`2457`
* :doc:`/plugins/thumbnails`: Fix a string-related crash on Python 3.
  :bug:`2466`
* :doc:`/plugins/beatport`: More than just 10 songs are now fetched per album.
  :bug:`2469`
* On Python 3, the :ref:`terminal_encoding` setting is respected again for
  output and printing will no longer crash on systems configured with a
  limited encoding.
* :doc:`/plugins/convert`: The default configuration uses FFmpeg's built-in
  AAC codec instead of faac. Thanks to :user:`jansol`. :bug:`2484`
* Fix the importer's detection of multi-disc albums when other subdirectories
  are present. :bug:`2493`
* Invalid date queries now print an error message instead of being silently
  ignored. Thanks to :user:`discopatrick`. :bug:`2513` :bug:`2517`
* When the SQLite database stops being accessible, we now print a friendly
  error message. Thanks to :user:`Mary011196`. :bug:`1676` :bug:`2508`
* :doc:`/plugins/web`: Avoid a crash when sending binary data, such as
  Chromaprint fingerprints, in music attributes. :bug:`2542` :bug:`2532`
* Fix a hang when parsing templates that end in newlines. :bug:`2562`
* Fix a crash when reading non-ASCII characters in configuration files on
  Windows under Python 3. :bug:`2456` :bug:`2565` :bug:`2566`

We removed backends from two metadata plugins because of bitrot:

* :doc:`/plugins/lyrics`: The Lyrics.com backend has been removed. (It stopped
  working because of changes to the site's URL structure.)
  :bug:`2548` :bug:`2549`
* :doc:`/plugins/fetchart`: The documentation no longer recommends iTunes
  Store artwork lookup because the unmaintained `python-itunes`_ is broken.
  Want to adopt it? :bug:`2371` :bug:`1610`

.. _python-itunes: https://github.com/ocelma/python-itunes

1.4.3 (January 9, 2017)
-----------------------

Happy new year! This new version includes a cornucopia of new features from
contributors, including new tags related to classical music and a new
:doc:`/plugins/absubmit` for performing acoustic analysis on your music. The
:doc:`/plugins/random` has a new mode that lets you generate time-limited
music---for example, you might generate a random playlist that lasts the
perfect length for your walk to work. We also access as many Web services as
possible over secure connections now---HTTPS everywhere!

The most visible new features are:

* We now support the composer, lyricist, and arranger tags. The MusicBrainz
  data source will fetch data for these fields when the next version of
  `python-musicbrainzngs`_ is released. Thanks to :user:`ibmibmibm`.
  :bug:`506` :bug:`507` :bug:`1547` :bug:`2333`
* A new :doc:`/plugins/absubmit` lets you run acoustic analysis software and
  upload the results for others to use. Thanks to :user:`inytar`. :bug:`2253`
  :bug:`2342`
* :doc:`/plugins/play`: The plugin now provides an importer prompt choice to
  play the music you're about to import. Thanks to :user:`diomekes`.
  :bug:`2008` :bug:`2360`
* We now use SSL to access Web services whenever possible. That includes
  MusicBrainz itself, several album art sources, some lyrics sources, and
  other servers. Thanks to :user:`tigranl`. :bug:`2307`
* :doc:`/plugins/random`: A new ``--time`` option lets you generate a random
  playlist that takes a given amount of time. Thanks to :user:`diomekes`.
  :bug:`2305` :bug:`2322`

Some smaller new features:

* :doc:`/plugins/zero`: A new ``zero`` command manually triggers the zero
  plugin. Thanks to :user:`SJoshBrown`. :bug:`2274` :bug:`2329`
* :doc:`/plugins/acousticbrainz`: The plugin will avoid re-downloading data
  for files that already have it by default. You can override this behavior
  using a new ``force`` option. Thanks to :user:`SusannaMaria`. :bug:`2347`
  :bug:`2349`
* :doc:`/plugins/bpm`: The ``import.write`` configuration option now
  decides whether or not to write tracks after updating their BPM. :bug:`1992`

And the fixes:

* :doc:`/plugins/bpd`: Fix a crash on non-ASCII MPD commands. :bug:`2332`
* :doc:`/plugins/scrub`: Avoid a crash when files cannot be read or written.
  :bug:`2351`
* :doc:`/plugins/scrub`: The image type values on scrubbed files are preserved
  instead of being reset to "other." :bug:`2339`
* :doc:`/plugins/web`: Fix a crash on Python 3 when serving files from the
  filesystem. :bug:`2353`
* :doc:`/plugins/discogs`: Improve the handling of releases that contain
  subtracks. :bug:`2318`
* :doc:`/plugins/discogs`: Fix a crash when a release does not contain format
  information, and increase robustness when other fields are missing.
  :bug:`2302`
* :doc:`/plugins/lyrics`: The plugin now reports a beets-specific User-Agent
  header when requesting lyrics. :bug:`2357`
* :doc:`/plugins/embyupdate`: The plugin now checks whether an API key or a
  password is provided in the configuration.
* :doc:`/plugins/play`: The misspelled configuration option
  ``warning_treshold`` is no longer supported.

For plugin developers: when providing new importer prompt choices (see
:ref:`append_prompt_choices`), you can now provide new candidates for the user
to consider. For example, you might provide an alternative strategy for
picking between the available alternatives or for looking up a release on
MusicBrainz.

1.4.2 (December 16, 2016)
-------------------------

This is just a little bug fix release. With 1.4.2, we're also confident enough
to recommend that anyone who's interested give Python 3 a try: bugs may still
lurk, but we've deemed things safe enough for broad adoption. If you can,
please install beets with ``pip3`` instead of ``pip2`` this time and let us
know how it goes!

Here are the fixes:

* :doc:`/plugins/badfiles`: Fix a crash on non-ASCII filenames. :bug:`2299`
* The ``%asciify{}`` path formatting function and the :ref:`asciify-paths`
  setting properly substitute path separators generated by converting some
  Unicode characters, such as ½ and ¢, into ASCII.
* :doc:`/plugins/convert`: Fix a logging-related crash when filenames contain
  curly braces. Thanks to :user:`kierdavis`. :bug:`2323`
* We've rolled back some changes to the included zsh completion script that
  were causing problems for some users. :bug:`2266`

Also, we've removed some special handling for logging in the
:doc:`/plugins/discogs` that we believe was unnecessary. If spurious log
messages appear in this version, please let us know by filing a bug.

1.4.1 (November 25, 2016)
-------------------------

Version 1.4 has **alpha-level** Python 3 support. Thanks to the heroic efforts
of :user:`jrobeson`, beets should run both under Python 2.7, as before, and
now under Python 3.4 and above. The support is still new: it undoubtedly
contains bugs, so it may replace all your music with Limp Bizkit---but if
you're brave and you have backups, please try installing on Python 3. Let us
know how it goes.

If you package beets for distribution, here's what you'll want to know:

* This version of beets now depends on the `six`_ library.
* We also bumped our minimum required version of `Mutagen`_ to 1.33 (from
  1.27).
* Please don't package beets as a Python 3 application *yet*, even though most
  things work under Python 3.4 and later.

This version also makes a few changes to the command-line interface and
configuration that you may need to know about:

* :doc:`/plugins/duplicates`: The ``duplicates`` command no longer accepts
  multiple field arguments in the form ``-k title albumartist album``. Each
  argument must be prefixed with ``-k``, as in ``-k title -k albumartist -k
  album``.
* The old top-level ``colors`` configuration option has been removed (the
  setting is now under ``ui``).
* The deprecated ``list_format_album`` and ``list_format_item``
  configuration options have been removed (see :ref:`format_album` and
  :ref:`format_item`).

The are a few new features:

* :doc:`/plugins/mpdupdate`, :doc:`/plugins/mpdstats`: When the ``host`` option
  is not set, these plugins will now look for the ``$MPD_HOST`` environment
  variable before falling back to ``localhost``. Thanks to :user:`tarruda`.
  :bug:`2175`
* :doc:`/plugins/web`: Added an ``expand`` option to show the items of an
  album. :bug:`2050`
* :doc:`/plugins/embyupdate`: The plugin can now use an API key instead of a
  password to authenticate with Emby. :bug:`2045` :bug:`2117`
* :doc:`/plugins/acousticbrainz`: The plugin now adds a ``bpm`` field.
* ``beet --version`` now includes the Python version used to run beets.
* :doc:`/reference/pathformat` can now include unescaped commas (``,``) when
  they are not part of a function call. :bug:`2166` :bug:`2213`
* The :ref:`update-cmd` command takes a new ``-F`` flag to specify the fields
  to update. Thanks to :user:`dangmai`. :bug:`2229` :bug:`2231`

And there are a few bug fixes too:

* :doc:`/plugins/convert`: The plugin no longer asks for confirmation if the
  query did not return anything to convert. :bug:`2260` :bug:`2262`
* :doc:`/plugins/embedart`: The plugin now uses ``jpg`` as an extension rather
  than ``jpeg``, to ensure consistency with the :doc:`plugins/fetchart`.
  Thanks to :user:`tweitzel`. :bug:`2254` :bug:`2255`
* :doc:`/plugins/embedart`: The plugin now works for all jpeg files, including
  those that are only recognizable by their magic bytes.
  :bug:`1545` :bug:`2255`
* :doc:`/plugins/web`: The JSON output is no longer pretty-printed (for a
  space savings). :bug:`2050`
* :doc:`/plugins/permissions`: Fix a regression in the previous release where
  the plugin would always fail to set permissions (and log a warning).
  :bug:`2089`
* :doc:`/plugins/beatport`: Use track numbers from Beatport (instead of
  determining them from the order of tracks) and set the `medium_index`
  value.
* With :ref:`per_disc_numbering` enabled, some metadata sources (notably, the
  :doc:`/plugins/beatport`) would not set the track number at all. This is
  fixed. :bug:`2085`
* :doc:`/plugins/play`: Fix ``$args`` getting passed verbatim to the play
  command if it was set in the configuration but ``-A`` or ``--args`` was
  omitted.
* With :ref:`ignore_hidden` enabled, non-UTF-8 filenames would cause a crash.
  This is fixed. :bug:`2168`
* :doc:`/plugins/embyupdate`: Fixes authentication header problem that caused
  a problem that it was not possible to get tokens from the Emby API.
* :doc:`/plugins/lyrics`: Some titles use a colon to separate the main title
  from a subtitle. To find more matches, the plugin now also searches for
  lyrics using the part part preceding the colon character. :bug:`2206`
* Fix a crash when a query uses a date field and some items are missing that
  field. :bug:`1938`
* :doc:`/plugins/discogs`: Subtracks are now detected and combined into a
  single track, two-sided mediums are treated as single discs, and tracks
  have ``media``, ``medium_total`` and ``medium`` set correctly. :bug:`2222`
  :bug:`2228`.
* :doc:`/plugins/missing`: ``missing`` is now treated as an integer, allowing
  the use of (for example) ranges in queries.
* :doc:`/plugins/smartplaylist`: Playlist names will be sanitized to
  ensure valid filenames. :bug:`2258`
* The ID3 APIC tag now uses the Latin-1 encoding when possible instead of a
  Unicode encoding. This should increase compatibility with other software,
  especially with iTunes and when using ID3v2.3. Thanks to :user:`lazka`.
  :bug:`899` :bug:`2264` :bug:`2270`

The last release, 1.3.19, also erroneously reported its version as "1.3.18"
when you typed ``beet version``. This has been corrected.

.. _six: https://pypi.org/project/six/

1.3.19 (June 25, 2016)
----------------------

This is primarily a bug fix release: it cleans up a couple of regressions that
appeared in the last version. But it also features the triumphant return of the
:doc:`/plugins/beatport` and a modernized :doc:`/plugins/bpd`.

It's also the first version where beets passes all its tests on Windows! May
this herald a new age of cross-platform reliability for beets.

New features:

* :doc:`/plugins/beatport`: This metadata source plugin has arisen from the
  dead! It now works with Beatport's new OAuth-based API. Thanks to
  :user:`jbaiter`. :bug:`1989` :bug:`2067`
* :doc:`/plugins/bpd`: The plugin now uses the modern GStreamer 1.0 instead of
  the old 0.10. Thanks to :user:`philippbeckmann`. :bug:`2057` :bug:`2062`
* A new ``--force`` option for the :ref:`remove-cmd` command allows removal of
  items without prompting beforehand. :bug:`2042`
* A new :ref:`duplicate_action` importer config option controls how duplicate
  albums or tracks treated in import task. :bug:`185`

Some fixes for Windows:

* Queries are now detected as paths when they contain backslashes (in
  addition to forward slashes). This only applies on Windows.
* :doc:`/plugins/embedart`: Image similarity comparison with ImageMagick
  should now work on Windows.
* :doc:`/plugins/fetchart`: The plugin should work more reliably with
  non-ASCII paths.

And other fixes:

* :doc:`/plugins/replaygain`: The ``bs1770gain`` backend now correctly
  calculates sample peak instead of true peak. This comes with a major
  speed increase. :bug:`2031`
* :doc:`/plugins/lyrics`: Avoid a crash and a spurious warning introduced in
  the last version about a Google API key, which appeared even when you hadn't
  enabled the Google lyrics source.
* Fix a hard-coded path to ``bash-completion`` to work better with Homebrew
  installations. Thanks to :user:`bismark`. :bug:`2038`
* Fix a crash introduced in the previous version when the standard input was
  connected to a Unix pipe. :bug:`2041`
* Fix a crash when specifying non-ASCII format strings on the command line
  with the ``-f`` option for many commands. :bug:`2063`
* :doc:`/plugins/fetchart`: Determine the file extension for downloaded images
  based on the image's magic bytes. The plugin prints a warning if result is
  not consistent with the server-supplied ``Content-Type`` header. In previous
  versions, the plugin would use a ``.jpg`` extension for all images.
  :bug:`2053`

1.3.18 (May 31, 2016)
---------------------

This update adds a new :doc:`/plugins/hook` that lets you integrate beets with
command-line tools and an :doc:`/plugins/export` that can dump data from the
beets database as JSON. You can also automatically translate lyrics using a
machine translation service.

The ``echonest`` plugin has been removed in this version because the API it
used is `shutting down`_. You might want to try the
:doc:`/plugins/acousticbrainz` instead.

.. _shutting down: https://developer.spotify.com/news-stories/2016/03/29/api-improvements-update/

Some of the larger new features:

* The new :doc:`/plugins/hook` lets you execute commands in response to beets
  events.
* The new :doc:`/plugins/export` can export data from beets' database as
  JSON. Thanks to :user:`GuilhermeHideki`.
* :doc:`/plugins/lyrics`: The plugin can now translate the fetched lyrics to
  your native language using the Bing translation API. Thanks to
  :user:`Kraymer`.
* :doc:`/plugins/fetchart`: Album art can now be fetched from `fanart.tv`_.

Smaller new things:

* There are two new functions available in templates: ``%first`` and ``%ifdef``.
  See :ref:`template-functions`.
* :doc:`/plugins/convert`: A new `album_art_maxwidth` setting lets you resize
  album art while copying it.
* :doc:`/plugins/convert`: The `extension` setting is now optional for
  conversion formats. By default, the extension is the same as the name of the
  configured format.
* :doc:`/plugins/importadded`: A new `preserve_write_mtimes` option
  lets you preserve mtime of files even when beets updates their metadata.
* :doc:`/plugins/fetchart`: The `enforce_ratio` option now lets you tolerate
  images that are *almost* square but differ slightly from an exact 1:1
  aspect ratio.
* :doc:`/plugins/fetchart`: The plugin can now optionally save the artwork's
  source in an attribute in the database.
* The :ref:`terminal_encoding` configuration option can now also override the
  *input* encoding. (Previously, it only affected the encoding of the standard
  *output* stream.)
* A new :ref:`ignore_hidden` configuration option lets you ignore files that
  your OS marks as invisible.
* :doc:`/plugins/web`: A new `values` endpoint lets you get the distinct values
  of a field. Thanks to :user:`sumpfralle`. :bug:`2010`

.. _fanart.tv: https://fanart.tv/

Fixes:

* Fix a problem with the :ref:`stats-cmd` command in exact mode when filenames
  on Windows use non-ASCII characters. :bug:`1891`
* Fix a crash when iTunes Sound Check tags contained invalid data. :bug:`1895`
* :doc:`/plugins/mbcollection`: The plugin now redacts your MusicBrainz
  password in the ``beet config`` output. :bug:`1907`
* :doc:`/plugins/scrub`: Fix an occasional problem where scrubbing on import
  could undo the :ref:`id3v23` setting. :bug:`1903`
* :doc:`/plugins/lyrics`: Add compatibility with some changes to the
  LyricsWiki page markup. :bug:`1912` :bug:`1909`
* :doc:`/plugins/lyrics`: Fix retrieval from Musixmatch by improving the way
  we guess the URL for lyrics on that service. :bug:`1880`
* :doc:`/plugins/edit`: Fail gracefully when the configured text editor
  command can't be invoked. :bug:`1927`
* :doc:`/plugins/fetchart`: Fix a crash in the Wikipedia backend on non-ASCII
  artist and album names. :bug:`1960`
* :doc:`/plugins/convert`: Change the default `ogg` encoding quality from 2 to
  3 (to fit the default from the `oggenc(1)` manpage). :bug:`1982`
* :doc:`/plugins/convert`: The `never_convert_lossy_files` option now
  considers AIFF a lossless format. :bug:`2005`
* :doc:`/plugins/web`: A proper 404 error, instead of an internal exception,
  is returned when missing album art is requested. Thanks to
  :user:`sumpfralle`. :bug:`2011`
* Tolerate more malformed floating-point numbers in metadata tags. :bug:`2014`
* The :ref:`ignore` configuration option now includes the ``lost+found``
  directory by default.
* :doc:`/plugins/acousticbrainz`: AcousticBrainz lookups are now done over
  HTTPS. Thanks to :user:`Freso`. :bug:`2007`

1.3.17 (February 7, 2016)
-------------------------

This release introduces one new plugin to fetch audio information from the
`AcousticBrainz`_ project and another plugin to make it easier to submit your
handcrafted metadata back to MusicBrainz.
The importer also gained two oft-requested features: a way to skip the initial
search process by specifying an ID ahead of time, and a way to *manually*
provide metadata in the middle of the import process (via the
:doc:`/plugins/edit`).

Also, as of this release, the beets project has some new Internet homes! Our
new domain name is `beets.io`_, and we have a shiny new GitHub organization:
`beetbox`_.

Here are the big new features:

* A new :doc:`/plugins/acousticbrainz` fetches acoustic-analysis information
  from the `AcousticBrainz`_ project. Thanks to :user:`opatel99`, and thanks
  to `Google Code-In`_! :bug:`1784`
* A new :doc:`/plugins/mbsubmit` lets you print music's current metadata in a
  format that the MusicBrainz data parser can understand. You can trigger it
  during an interactive import session. :bug:`1779`
* A new ``--search-id`` importer option lets you manually specify
  IDs (i.e., MBIDs or Discogs IDs) for imported music. Doing this skips the
  initial candidate search, which can be important for huge albums where this
  initial lookup is slow.
  Also, the ``enter Id`` prompt choice now accepts several IDs, separated by
  spaces. :bug:`1808`
* :doc:`/plugins/edit`: You can now edit metadata *on the fly* during the
  import process. The plugin provides two new interactive options: one to edit
  *your music's* metadata, and one to edit the *matched metadata* retrieved
  from MusicBrainz (or another data source). This feature is still in its
  early stages, so please send feedback if you find anything missing.
  :bug:`1846` :bug:`396`

There are even more new features:

* :doc:`/plugins/fetchart`: The Google Images backend has been restored. It
  now requires an API key from Google. Thanks to :user:`lcharlick`.
  :bug:`1778`
* :doc:`/plugins/info`: A new option will print only fields' names and not
  their values. Thanks to :user:`GuilhermeHideki`. :bug:`1812`
* The :ref:`fields-cmd` command now displays flexible attributes.
  Thanks to :user:`GuilhermeHideki`. :bug:`1818`
* The :ref:`modify-cmd` command lets you interactively select which albums or
  items you want to change. :bug:`1843`
* The :ref:`move-cmd` command gained a new ``--timid`` flag to print and
  confirm which files you want to move. :bug:`1843`
* The :ref:`move-cmd` command no longer prints filenames for files that
  don't actually need to be moved. :bug:`1583`

.. _Google Code-In: https://codein.withgoogle.com/
.. _AcousticBrainz: https://acousticbrainz.org/

Fixes:

* :doc:`/plugins/play`: Fix a regression in the last version where there was
  no default command. :bug:`1793`
* :doc:`/plugins/lastimport`: The plugin now works again after being broken by
  some unannounced changes to the Last.fm API. :bug:`1574`
* :doc:`/plugins/play`: Fixed a typo in a configuration option. The option is
  now ``warning_threshold`` instead of ``warning_treshold``, but we kept the
  old name around for compatibility. Thanks to :user:`JesseWeinstein`.
  :bug:`1802` :bug:`1803`
* :doc:`/plugins/edit`: Editing metadata now moves files, when appropriate
  (like the :ref:`modify-cmd` command). :bug:`1804`
* The :ref:`stats-cmd` command no longer crashes when files are missing or
  inaccessible. :bug:`1806`
* :doc:`/plugins/fetchart`: Possibly fix a Unicode-related crash when using
  some versions of pyOpenSSL. :bug:`1805`
* :doc:`/plugins/replaygain`: Fix an intermittent crash with the GStreamer
  backend. :bug:`1855`
* :doc:`/plugins/lastimport`: The plugin now works with the beets API key by
  default. You can still provide a different key the configuration.
* :doc:`/plugins/replaygain`: Fix a crash using the Python Audio Tools
  backend. :bug:`1873`

.. _beets.io: https://beets.io/
.. _Beetbox: https://github.com/beetbox

1.3.16 (December 28, 2015)
--------------------------

The big news in this release is a new :doc:`interactive editor plugin
</plugins/edit>`. It's really nifty: you can now change your music's metadata
by making changes in a visual text editor, which can sometimes be far more
efficient than the built-in :ref:`modify-cmd` command. No more carefully
retyping the same artist name with slight capitalization changes.

This version also adds an oft-requested "not" operator to beets' queries, so
you can exclude music from any operation. It also brings friendlier formatting
(and querying!) of song durations.

The big new stuff:

* A new :doc:`/plugins/edit` lets you manually edit your music's metadata
  using your favorite text editor. :bug:`164` :bug:`1706`
* Queries can now use "not" logic. Type a ``^`` before part of a query to
  *exclude* matching music from the results. For example, ``beet list -a
  beatles ^album:1`` will find all your albums by the Beatles except for their
  singles compilation, "1." See :ref:`not_query`. :bug:`819` :bug:`1728`
* A new :doc:`/plugins/embyupdate` can trigger a library refresh on an `Emby`_
  server when your beets database changes.
* Track length is now displayed as "M:SS" rather than a raw number of seconds.
  Queries on track length also accept this format: for example, ``beet list
  length:5:30..`` will find all your tracks that have a duration over 5
  minutes and 30 seconds. You can turn off this new behavior using the
  ``format_raw_length`` configuration option. :bug:`1749`

Smaller changes:

* Three commands, ``modify``, ``update``, and ``mbsync``, would previously
  move files by default after changing their metadata. Now, these commands
  will only move files if you have the :ref:`config-import-copy` or
  :ref:`config-import-move` options enabled in your importer configuration.
  This way, if you configure the importer not to touch your filenames, other
  commands will respect that decision by default too. Each command also
  sprouted a ``--move`` command-line option to override this default (in
  addition to the ``--nomove`` flag they already had). :bug:`1697`
* A new configuration option, ``va_name``, controls the album artist name for
  various-artists albums. The setting defaults to "Various Artists," the
  MusicBrainz standard. In order to match MusicBrainz, the
  :doc:`/plugins/discogs` also adopts the same setting.
* :doc:`/plugins/info`: The ``info`` command now accepts a ``-f/--format``
  option for customizing how items are displayed, just like the built-in
  ``list`` command. :bug:`1737`

Some changes for developers:

* Two new :ref:`plugin hooks <plugin_events>`, ``albuminfo_received`` and
  ``trackinfo_received``, let plugins intercept metadata as soon as it is
  received, before it is applied to music in the database. :bug:`872`
* Plugins can now add options to the interactive importer prompts. See
  :ref:`append_prompt_choices`. :bug:`1758`

Fixes:

* :doc:`/plugins/plexupdate`: Fix a crash when Plex libraries use non-ASCII
  collection names. :bug:`1649`
* :doc:`/plugins/discogs`: Maybe fix a crash when using some versions of the
  ``requests`` library. :bug:`1656`
* Fix a race in the importer when importing two albums with the same artist
  and name in quick succession. The importer would fail to detect them as
  duplicates, claiming that there were "empty albums" in the database even
  when there were not. :bug:`1652`
* :doc:`plugins/lastgenre`: Clean up the reggae-related genres somewhat.
  Thanks to :user:`Freso`. :bug:`1661`
* The importer now correctly moves album art files when re-importing.
  :bug:`314`
* :doc:`/plugins/fetchart`: In auto mode, the plugin now skips albums that
  already have art attached to them so as not to interfere with re-imports.
  :bug:`314`
* :doc:`plugins/fetchart`: The plugin now only resizes album art if necessary,
  rather than always by default. :bug:`1264`
* :doc:`plugins/fetchart`: Fix a bug where a database reference to a
  non-existent album art file would prevent the command from fetching new art.
  :bug:`1126`
* :doc:`/plugins/thumbnails`: Fix a crash with Unicode paths. :bug:`1686`
* :doc:`/plugins/embedart`: The ``remove_art_file`` option now works on import
  (as well as with the explicit command). :bug:`1662` :bug:`1675`
* :doc:`/plugins/metasync`: Fix a crash when syncing with recent versions of
  iTunes. :bug:`1700`
* :doc:`/plugins/duplicates`: Fix a crash when merging items. :bug:`1699`
* :doc:`/plugins/smartplaylist`: More gracefully handle malformed queries and
  missing configuration.
* Fix a crash with some files with unreadable iTunes SoundCheck metadata.
  :bug:`1666`
* :doc:`/plugins/thumbnails`: Fix a nasty segmentation fault crash that arose
  with some library versions. :bug:`1433`
* :doc:`/plugins/convert`: Fix a crash with Unicode paths in ``--pretend``
  mode. :bug:`1735`
* Fix a crash when sorting by nonexistent fields on queries. :bug:`1734`
* Probably fix some mysterious errors when dealing with images using
  ImageMagick on Windows. :bug:`1721`
* Fix a crash when writing some Unicode comment strings to MP3s that used
  older encodings. The encoding is now always updated to UTF-8. :bug:`879`
* :doc:`/plugins/fetchart`: The Google Images backend has been removed. It
  used an API that has been shut down. :bug:`1760`
* :doc:`/plugins/lyrics`: Fix a crash in the Google backend when searching for
  bands with regular-expression characters in their names, like Sunn O))).
  :bug:`1673`
* :doc:`/plugins/scrub`: In ``auto`` mode, the plugin now *actually* only
  scrubs files on import, as the documentation always claimed it did---not
  every time files were written, as it previously did. :bug:`1657`
* :doc:`/plugins/scrub`: Also in ``auto`` mode, album art is now correctly
  restored. :bug:`1657`
* Possibly allow flexible attributes to be used with the ``%aunique`` template
  function. :bug:`1775`
* :doc:`/plugins/lyrics`: The Genius backend is now more robust to
  communication errors. The backend has also been disabled by default, since
  the API it depends on is currently down. :bug:`1770`

.. _Emby: https://emby.media

1.3.15 (October 17, 2015)
-------------------------

This release adds a new plugin for checking file quality and a new source for
lyrics. The larger features are:

* A new :doc:`/plugins/badfiles` helps you scan for corruption in your music
  collection. Thanks to :user:`fxthomas`. :bug:`1568`
* :doc:`/plugins/lyrics`: You can now fetch lyrics from Genius.com.
  Thanks to :user:`sadatay`. :bug:`1626` :bug:`1639`
* :doc:`/plugins/zero`: The plugin can now use a "whitelist" policy as an
  alternative to the (default) "blacklist" mode. Thanks to :user:`adkow`.
  :bug:`1621` :bug:`1641`

And there are smaller new features too:

* Add new color aliases for standard terminal color names (e.g., cyan and
  magenta). Thanks to :user:`mathstuf`. :bug:`1548`
* :doc:`/plugins/play`: A new ``--args`` option lets you specify options for
  the player command. :bug:`1532`
* :doc:`/plugins/play`: A new ``raw`` configuration option lets the command
  work with players (such as VLC) that expect music filenames as arguments,
  rather than in a playlist. Thanks to :user:`nathdwek`. :bug:`1578`
* :doc:`/plugins/play`: You can now configure the number of tracks that
  trigger a "lots of music" warning. :bug:`1577`
* :doc:`/plugins/embedart`: A new ``remove_art_file`` option lets you clean up
  if you prefer *only* embedded album art. Thanks to :user:`jackwilsdon`.
  :bug:`1591` :bug:`733`
* :doc:`/plugins/plexupdate`: A new ``library_name`` option allows you to select
  which Plex library to update. :bug:`1572` :bug:`1595`
* A new ``include`` option lets you import external configuration files.

This release has plenty of fixes:

* :doc:`/plugins/lastgenre`: Fix a bug that prevented tag popularity from
  being considered. Thanks to :user:`svoos`. :bug:`1559`
* Fixed a bug where plugins wouldn't be notified of the deletion of an item's
  art, for example with the ``clearart`` command from the
  :doc:`/plugins/embedart`. Thanks to :user:`nathdwek`. :bug:`1565`
* :doc:`/plugins/fetchart`: The Google Images source is disabled by default
  (as it was before beets 1.3.9), as is the Wikipedia source (which was
  causing lots of unnecessary delays due to DBpedia downtime). To re-enable
  these sources, add ``wikipedia google`` to your ``sources`` configuration
  option.
* The :ref:`list-cmd` command's help output now has a small query and format
  string example. Thanks to :user:`pkess`. :bug:`1582`
* :doc:`/plugins/fetchart`: The plugin now fetches PNGs but not GIFs. (It
  still fetches JPEGs.) This avoids an error when trying to embed images,
  since not all formats support GIFs. :bug:`1588`
* Date fields are now written in the correct order (year-month-day), which
  eliminates an intermittent bug where the latter two fields would not get
  written to files. Thanks to :user:`jdetrey`. :bug:`1303` :bug:`1589`
* :doc:`/plugins/replaygain`: Avoid a crash when the PyAudioTools backend
  encounters an error. :bug:`1592`
* The case sensitivity of path queries is more useful now: rather than just
  guessing based on the platform, we now check the case sensitivity of your
  filesystem. :bug:`1586`
* Case-insensitive path queries might have returned nothing because of a
  wrong SQL query.
* Fix a crash when a query contains a "+" or "-" alone in a component.
  :bug:`1605`
* Fixed unit of file size to powers of two (MiB, GiB, etc.) instead of powers
  of ten (MB, GB, etc.). :bug:`1623`

1.3.14 (August 2, 2015)
-----------------------

This is mainly a bugfix release, but we also have a nifty new plugin for
`ipfs`_ and a bunch of new configuration options.

The new features:

* A new :doc:`/plugins/ipfs` lets you share music via a new, global,
  decentralized filesystem. :bug:`1397`
* :doc:`/plugins/duplicates`: You can now merge duplicate
  track metadata (when detecting duplicate items), or duplicate album
  tracks (when detecting duplicate albums).
* :doc:`/plugins/duplicates`: Duplicate resolution now uses an ordering to
  prioritize duplicates. By default, it prefers music with more complete
  metadata, but you can configure it to use any list of attributes.
* :doc:`/plugins/metasync`: Added a new backend to fetch metadata from iTunes.
  This plugin is still in an experimental phase. :bug:`1450`
* The `move` command has a new ``--pretend`` option, making the command show
  how the items will be moved without actually changing anything.
* The importer now supports matching of "pregap" or HTOA (hidden track-one
  audio) tracks when they are listed in MusicBrainz. (This feature depends on a
  new version of the `python-musicbrainzngs`_ library that is not yet released, but
  will start working when it is available.) Thanks to :user:`ruippeixotog`.
  :bug:`1104` :bug:`1493`
* :doc:`/plugins/plexupdate`: A new ``token`` configuration option lets you
  specify a key for Plex Home setups. Thanks to :user:`edcarroll`. :bug:`1494`

Fixes:

* :doc:`/plugins/fetchart`: Complain when the `enforce_ratio`
  or `min_width` options are enabled but no local imaging backend is available
  to carry them out. :bug:`1460`
* :doc:`/plugins/importfeeds`: Avoid generating incorrect m3u filename when
  both of the `m3u` and `m3u_multi` options are enabled. :bug:`1490`
* :doc:`/plugins/duplicates`: Avoid a crash when misconfigured. :bug:`1457`
* :doc:`/plugins/mpdstats`: Avoid a crash when the music played is not in the
  beets library. Thanks to :user:`CodyReichert`. :bug:`1443`
* Fix a crash with ArtResizer on Windows systems (affecting
  :doc:`/plugins/embedart`, :doc:`/plugins/fetchart`,
  and :doc:`/plugins/thumbnails`). :bug:`1448`
* :doc:`/plugins/permissions`: Fix an error with non-ASCII paths. :bug:`1449`
* Fix sorting by paths when the :ref:`sort_case_insensitive` option is
  enabled. :bug:`1451`
* :doc:`/plugins/embedart`: Avoid an error when trying to embed invalid images
  into MPEG-4 files.
* :doc:`/plugins/fetchart`: The Wikipedia source can now better deal artists
  that use non-standard capitalization (e.g., alt-J, dEUS).
* :doc:`/plugins/web`: Fix searching for non-ASCII queries. Thanks to
  :user:`oldtopman`. :bug:`1470`
* :doc:`/plugins/mpdupdate`: We now recommend the newer ``python-mpd2``
  library instead of its unmaintained parent. Thanks to :user:`Somasis`.
  :bug:`1472`
* The importer interface and log file now output a useful list of files
  (instead of the word "None") when in album-grouping mode. :bug:`1475`
  :bug:`825`
* Fix some logging errors when filenames and other user-provided strings
  contain curly braces. :bug:`1481`
* Regular expression queries over paths now work more reliably with non-ASCII
  characters in filenames. :bug:`1482`
* Fix a bug where the autotagger's :ref:`ignored` setting was sometimes, well,
  ignored. :bug:`1487`
* Fix a bug with Unicode strings when generating image thumbnails. :bug:`1485`
* :doc:`/plugins/keyfinder`: Fix handling of Unicode paths. :bug:`1502`
* :doc:`/plugins/fetchart`: When album art is already present, the message is
  now printed in the ``text_highlight_minor`` color (light gray). Thanks to
  :user:`Somasis`. :bug:`1512`
* Some messages in the console UI now use plural nouns correctly. Thanks to
  :user:`JesseWeinstein`. :bug:`1521`
* Sorting numerical fields (such as track) now works again. :bug:`1511`
* :doc:`/plugins/replaygain`: Missing GStreamer plugins now cause a helpful
  error message instead of a crash. :bug:`1518`
* Fix an edge case when producing sanitized filenames where the maximum path
  length conflicted with the :ref:`replace` rules. Thanks to Ben Ockmore.
  :bug:`496` :bug:`1361`
* Fix an incompatibility with OS X 10.11 (where ``/usr/sbin`` seems not to be
  on the user's path by default).
* Fix an incompatibility with certain JPEG files. Here's a relevant `Python
  bug`_. Thanks to :user:`nathdwek`. :bug:`1545`
* Fix the :ref:`group_albums` importer mode so that it works correctly when
  files are not already in order by album. :bug:`1550`
* The ``fields`` command no longer separates built-in fields from
  plugin-provided ones. This distinction was becoming increasingly unreliable.
* :doc:`/plugins/duplicates`: Fix a Unicode warning when paths contained
  non-ASCII characters. :bug:`1551`
* :doc:`/plugins/fetchart`: Work around a urllib3 bug that could cause a
  crash. :bug:`1555` :bug:`1556`
* When you edit the configuration file with ``beet config -e`` and the file
  does not exist, beets creates an empty file before editing it. This fixes an
  error on OS X, where the ``open`` command does not work with non-existent
  files. :bug:`1480`
* :doc:`/plugins/convert`: Fix a problem with filename encoding on Windows
  under Python 3. :bug:`2515` :bug:`2516`

.. _Python bug: https://bugs.python.org/issue16512
.. _ipfs: https://ipfs.io

1.3.13 (April 24, 2015)
-----------------------

This is a tiny bug-fix release. It copes with a dependency upgrade that broke
beets. There are just two fixes:

* Fix compatibility with `Jellyfish`_ version 0.5.0.
* :doc:`/plugins/embedart`: In ``auto`` mode (the import hook), the plugin now
  respects the ``write`` config option under ``import``. If this is disabled,
  album art is no longer embedded on import in order to leave files
  untouched---in effect, ``auto`` is implicitly disabled. :bug:`1427`

1.3.12 (April 18, 2015)
-----------------------

This little update makes queries more powerful, sorts music more
intelligently, and removes a performance bottleneck. There's an experimental
new plugin for synchronizing metadata with music players.

Packagers should also note a new dependency in this version: the `Jellyfish`_
Python library makes our text comparisons (a big part of the auto-tagging
process) go much faster.

New features:

* Queries can now use **"or" logic**: if you use a comma to separate parts of a
  query, items and albums will match *either* side of the comma. For example,
  ``beet ls foo , bar`` will get all the items matching `foo` or matching
  `bar`. See :ref:`combiningqueries`. :bug:`1423`
* The autotagger's **matching algorithm is faster**. We now use the
  `Jellyfish`_ library to compute string similarity, which is better optimized
  than our hand-rolled edit distance implementation. :bug:`1389`
* Sorting is now **case insensitive** by default. This means that artists will
  be sorted lexicographically regardless of case. For example, the artist
  alt-J will now properly sort before YACHT. (Previously, it would have ended
  up at the end of the list, after all the capital-letter artists.)
  You can turn this new behavior off using the :ref:`sort_case_insensitive`
  configuration option. See :ref:`query-sort`. :bug:`1429`
* An experimental new :doc:`/plugins/metasync` lets you get metadata from your
  favorite music players, starting with Amarok. :bug:`1386`
* :doc:`/plugins/fetchart`: There are new settings to control what constitutes
  "acceptable" images. The `minwidth` option constrains the minimum image
  width in pixels and the `enforce_ratio` option requires that images be
  square. :bug:`1394`

Little fixes and improvements:

* :doc:`/plugins/fetchart`: Remove a hard size limit when fetching from the
  Cover Art Archive.
* The output of the :ref:`fields-cmd` command is now sorted. Thanks to
  :user:`multikatt`. :bug:`1402`
* :doc:`/plugins/replaygain`: Fix a number of issues with the new
  ``bs1770gain`` backend on Windows. Also, fix missing debug output in import
  mode. :bug:`1398`
* Beets should now be better at guessing the appropriate output encoding on
  Windows. (Specifically, the console output encoding is guessed separately
  from the encoding for command-line arguments.) A bug was also fixed where
  beets would ignore the locale settings and use UTF-8 by default. :bug:`1419`
* :doc:`/plugins/discogs`: Better error handling when we can't communicate
  with Discogs on setup. :bug:`1417`
* :doc:`/plugins/importadded`: Fix a crash when importing singletons in-place.
  :bug:`1416`
* :doc:`/plugins/fuzzy`: Fix a regression causing a crash in the last release.
  :bug:`1422`
* Fix a crash when the importer cannot open its log file. Thanks to
  :user:`barsanuphe`. :bug:`1426`
* Fix an error when trying to write tags for items with flexible fields called
  `date` and `original_date` (which are not built-in beets fields).
  :bug:`1404`

.. _Jellyfish: https://github.com/sunlightlabs/jellyfish

1.3.11 (April 5, 2015)
----------------------

In this release, we refactored the logging system to be more flexible and more
useful. There are more granular levels of verbosity, the output from plugins
should be more consistent, and several kinds of logging bugs should be
impossible in the future.

There are also two new plugins: one for filtering the files you import and an
evolved plugin for using album art as directory thumbnails in file managers.
There's a new source for album art, and the importer now records the source of
match data. This is a particularly huge release---there's lots more below.

There's one big change with this release: **Python 2.6 is no longer
supported**. You'll need Python 2.7. Please trust us when we say this let us
remove a surprising number of ugly hacks throughout the code.

Major new features and bigger changes:

* There are now **multiple levels of output verbosity**. On the command line,
  you can make beets somewhat verbose with ``-v`` or very verbose with
  ``-vv``. For the importer especially, this makes the first verbose mode much
  more manageable, while still preserving an option for overwhelmingly verbose
  debug output. :bug:`1244`
* A new :doc:`/plugins/filefilter` lets you write regular expressions to
  automatically **avoid importing** certain files. Thanks to :user:`mried`.
  :bug:`1186`
* A new :doc:`/plugins/thumbnails` generates cover-art **thumbnails for
  album folders** for Freedesktop.org-compliant file managers. (This replaces
  the :doc:`/plugins/freedesktop`, which only worked with the Dolphin file
  manager.)
* :doc:`/plugins/replaygain`: There is a new backend that uses the
  `bs1770gain`_ analysis tool. Thanks to :user:`jmwatte`. :bug:`1343`
* A new ``filesize`` field on items indicates the number of bytes in the file.
  :bug:`1291`
* A new :ref:`searchlimit` configuration option allows you to specify how many
  search results you wish to see when looking up releases at MusicBrainz
  during import. :bug:`1245`
* The importer now records the data source for a match in a new
  flexible attribute ``data_source`` on items and albums. :bug:`1311`
* The colors used in the terminal interface are now configurable via the new
  config option ``colors``, nested under the option ``ui``. (Also, the `color`
  config option has been moved from top-level to under ``ui``. Beets will
  respect the old color setting, but will warn the user with a deprecation
  message.) :bug:`1238`
* :doc:`/plugins/fetchart`: There's a new Wikipedia image source that uses
  DBpedia to find albums. Thanks to Tom Jaspers. :bug:`1194`
* In the :ref:`config-cmd` command, the output is now redacted by default.
  Sensitive information like passwords and API keys is not included. The new
  ``--clear`` option disables redaction. :bug:`1376`

You should probably also know about these core changes to the way beets works:

* As mentioned above, Python 2.6 is no longer supported.
* The ``tracktotal`` attribute is now a *track-level field* instead of an
  album-level one. This field stores the total number of tracks on the
  album, or if the :ref:`per_disc_numbering` config option is set, the total
  number of tracks on a particular medium (i.e., disc). The field was causing
  problems with that :ref:`per_disc_numbering` mode: different discs on the
  same album needed different track totals. The field can now work correctly
  in either mode.
* To replace ``tracktotal`` as an album-level field, there is a new
  ``albumtotal`` computed attribute that provides the total number of tracks
  on the album. (The :ref:`per_disc_numbering` option has no influence on this
  field.)
* The `list_format_album` and `list_format_item` configuration keys
  now affect (almost) every place where objects are printed and logged.
  (Previously, they only controlled the :ref:`list-cmd` command and a few
  other scattered pieces.) :bug:`1269`
* Relatedly, the ``beet`` program now accept top-level options
  ``--format-item`` and ``--format-album`` before any subcommand to control
  how items and albums are displayed. :bug:`1271`
* `list_format_album` and `list_format_album` have respectively been
  renamed :ref:`format_album` and :ref:`format_item`. The old names still work
  but each triggers a warning message. :bug:`1271`
* :ref:`Path queries <pathquery>` are automatically triggered only if the
  path targeted by the query exists. Previously, just having a slash somewhere
  in the query was enough, so ``beet ls AC/DC`` wouldn't work to refer to the
  artist.

There are also lots of medium-sized features in this update:

* :doc:`/plugins/duplicates`: The command has a new ``--strict`` option
  that will only report duplicates if all attributes are explicitly set.
  :bug:`1000`
* :doc:`/plugins/smartplaylist`: Playlist updating should now be faster: the
  plugin detects, for each playlist, whether it needs to be regenerated,
  instead of obliviously regenerating all of them. The ``splupdate`` command
  can now also take additional parameters that indicate the names of the
  playlists to regenerate.
* :doc:`/plugins/play`: The command shows the output of the underlying player
  command and lets you interact with it. :bug:`1321`
* The summary shown to compare duplicate albums during import now displays
  the old and new filesizes. :bug:`1291`
* :doc:`/plugins/lastgenre`: Add *comedy*, *humor*, and *stand-up* as well as
  a longer list of classical music genre tags to the built-in whitelist and
  canonicalization tree. :bug:`1206` :bug:`1239` :bug:`1240`
* :doc:`/plugins/web`: Add support for *cross-origin resource sharing* for
  more flexible in-browser clients. Thanks to Andre Miller. :bug:`1236`
  :bug:`1237`
* :doc:`plugins/mbsync`: A new ``-f/--format`` option controls the output
  format when listing unrecognized items. The output is also now more helpful
  by default. :bug:`1246`
* :doc:`/plugins/fetchart`: A new option, ``-n``, extracts the cover art of
  all matched albums into their respective directories. Another new flag,
  ``-a``, associates the extracted files with the albums in the database.
  :bug:`1261`
* :doc:`/plugins/info`: A new option, ``-i``, can display only a specified
  subset of properties. :bug:`1287`
* The number of missing/unmatched tracks is shown during import. :bug:`1088`
* :doc:`/plugins/permissions`: The plugin now also adjusts the permissions of
  the directories. (Previously, it only affected files.) :bug:`1308` :bug:`1324`
* :doc:`/plugins/ftintitle`: You can now configure the format that the plugin
  uses to add the artist to the title. Thanks to :user:`amishb`. :bug:`1377`

And many little fixes and improvements:

* :doc:`/plugins/replaygain`: Stop applying replaygain directly to source files
  when using the mp3gain backend. :bug:`1316`
* Path queries are case-sensitive on non-Windows OSes. :bug:`1165`
* :doc:`/plugins/lyrics`: Silence a warning about insecure requests in the new
  MusixMatch backend. :bug:`1204`
* Fix a crash when ``beet`` is invoked without arguments. :bug:`1205`
  :bug:`1207`
* :doc:`/plugins/fetchart`: Do not attempt to import directories as album art.
  :bug:`1177` :bug:`1211`
* :doc:`/plugins/mpdstats`: Avoid double-counting some play events. :bug:`773`
  :bug:`1212`
* Fix a crash when the importer deals with Unicode metadata in ``--pretend``
  mode. :bug:`1214`
* :doc:`/plugins/smartplaylist`: Fix ``album_query`` so that individual files
  are added to the playlist instead of directories. :bug:`1225`
* Remove the ``beatport`` plugin. `Beatport`_ has shut off public access to
  their API and denied our request for an account. We have not heard from the
  company since 2013, so we are assuming access will not be restored.
* Incremental imports now (once again) show a "skipped N directories" message.
* :doc:`/plugins/embedart`: Handle errors in ImageMagick's output. :bug:`1241`
* :doc:`/plugins/keyfinder`: Parse the underlying tool's output more robustly.
  :bug:`1248`
* :doc:`/plugins/embedart`: We now show a comprehensible error message when
  ``beet embedart -f FILE`` is given a non-existent path. :bug:`1252`
* Fix a crash when a file has an unrecognized image type tag. Thanks to
  Matthias Kiefer. :bug:`1260`
* :doc:`/plugins/importfeeds` and :doc:`/plugins/smartplaylist`: Automatically
  create parent directories for playlist files (instead of crashing when the
  parent directory does not exist). :bug:`1266`
* The :ref:`write-cmd` command no longer tries to "write" non-writable fields,
  such as the bitrate. :bug:`1268`
* The error message when MusicBrainz is not reachable on the network is now
  much clearer. Thanks to Tom Jaspers. :bug:`1190` :bug:`1272`
* Improve error messages when parsing query strings with shlex. :bug:`1290`
* :doc:`/plugins/embedart`: Fix a crash that occurred when used together
  with the *check* plugin. :bug:`1241`
* :doc:`/plugins/scrub`: Log an error instead of stopping when the ``beet
  scrub`` command cannot write a file. Also, avoid problems on Windows with
  Unicode filenames. :bug:`1297`
* :doc:`/plugins/discogs`: Handle and log more kinds of communication
  errors. :bug:`1299` :bug:`1305`
* :doc:`/plugins/lastgenre`: Bugs in the `pylast` library can no longer crash
  beets.
* :doc:`/plugins/convert`: You can now configure the temporary directory for
  conversions. Thanks to :user:`autochthe`. :bug:`1382` :bug:`1383`
* :doc:`/plugins/rewrite`: Fix a regression that prevented the plugin's
  rewriting from applying to album-level fields like ``$albumartist``.
  :bug:`1393`
* :doc:`/plugins/play`: The plugin now sorts items according to the
  configuration in album mode.
* :doc:`/plugins/fetchart`: The name for extracted art files is taken from the
  ``art_filename`` configuration option. :bug:`1258`
* When there's a parse error in a query (for example, when you type a
  malformed date in a :ref:`date query <datequery>`), beets now stops with an
  error instead of silently ignoring the query component.
* :doc:`/plugins/smartplaylist`: Stream-friendly smart playlists.
  The ``splupdate`` command can now also add a URL-encodable prefix to every
  path in the playlist file.

For developers:

* The ``database_change`` event now sends the item or album that is subject to
  a change.
* The ``OptionParser`` is now a ``CommonOptionsParser`` that offers facilities
  for adding usual options (``--album``, ``--path`` and ``--format``). See
  :ref:`add_subcommands`. :bug:`1271`
* The logging system in beets has been overhauled. Plugins now each have their
  own logger, which helps by automatically adjusting the verbosity level in
  import mode and by prefixing the plugin's name.  Logging levels are
  dynamically set when a plugin is called, depending on how it is called
  (import stage, event or direct command).  Finally, logging calls can (and
  should!) use modern ``{}``-style string formatting lazily. See
  :ref:`plugin-logging` in the plugin API docs.
* A new ``import_task_created`` event lets you manipulate import tasks
  immediately after they are initialized. It's also possible to replace the
  originally created tasks by returning new ones using this event.

.. _bs1770gain: http://bs1770gain.sourceforge.net

1.3.10 (January 5, 2015)
------------------------

This version adds a healthy helping of new features and fixes a critical
MPEG-4--related bug. There are more lyrics sources, there new plugins for
managing permissions and integrating with `Plex`_, and the importer has a new
``--pretend`` flag that shows which music *would* be imported.

One backwards-compatibility note: the :doc:`/plugins/lyrics` now requires the
`requests`_ library. If you use this plugin, you will need to install the
library by typing ``pip install requests`` or the equivalent for your OS.

Also, as an advance warning, this will be one of the last releases to support
Python 2.6. If you have a system that cannot run Python 2.7, please consider
upgrading soon.

The new features are:

* A new :doc:`/plugins/permissions` makes it easy to fix permissions on music
  files as they are imported. Thanks to :user:`xsteadfastx`. :bug:`1098`
* A new :doc:`/plugins/plexupdate` lets you notify a `Plex`_ server when the
  database changes. Thanks again to xsteadfastx. :bug:`1120`
* The :ref:`import-cmd` command now has a ``--pretend`` flag that lists the
  files that will be imported. Thanks to :user:`mried`. :bug:`1162`
* :doc:`/plugins/lyrics`: Add `Musixmatch`_ source and introduce a new
  ``sources`` config option that lets you choose exactly where to look for
  lyrics and in which order.
* :doc:`/plugins/lyrics`: Add Brazilian and Spanish sources to Google custom
  search engine.
* Add a warning when importing a directory that contains no music. :bug:`1116`
  :bug:`1127`
* :doc:`/plugins/zero`: Can now remove embedded images. :bug:`1129` :bug:`1100`
* The :ref:`config-cmd` command can now be used to edit the configuration even
  when it has syntax errors. :bug:`1123` :bug:`1128`
* :doc:`/plugins/lyrics`: Added a new ``force`` config option. :bug:`1150`

As usual, there are loads of little fixes and improvements:

* Fix a new crash with the latest version of Mutagen (1.26).
* :doc:`/plugins/lyrics`: Avoid fetching truncated lyrics from the Google
  backed by merging text blocks separated by empty ``<div>`` tags before
  scraping.
* We now print a better error message when the database file is corrupted.
* :doc:`/plugins/discogs`: Only prompt for authentication when running the
  :ref:`import-cmd` command. :bug:`1123`
* When deleting fields with the :ref:`modify-cmd` command, do not crash when
  the field cannot be removed (i.e., when it does not exist, when it is a
  built-in field, or when it is a computed field). :bug:`1124`
* The deprecated ``echonest_tempo`` plugin has been removed. Please use the
  ``echonest`` plugin instead.
* ``echonest`` plugin: Fingerprint-based lookup has been removed in
  accordance with `API changes`_. :bug:`1121`
* ``echonest`` plugin: Avoid a crash when the song has no duration
  information. :bug:`896`
* :doc:`/plugins/lyrics`: Avoid a crash when retrieving non-ASCII lyrics from
  the Google backend. :bug:`1135` :bug:`1136`
* :doc:`/plugins/smartplaylist`: Sort specifiers are now respected in queries.
  Thanks to :user:`djl`. :bug:`1138` :bug:`1137`
* :doc:`/plugins/ftintitle` and :doc:`/plugins/lyrics`: Featuring artists can
  now be detected when they use the Spanish word *con*. :bug:`1060`
  :bug:`1143`
* :doc:`/plugins/mbcollection`: Fix an "HTTP 400" error caused by a change in
  the MusicBrainz API. :bug:`1152`
* The ``%`` and ``_`` characters in path queries do not invoke their
  special SQL meaning anymore. :bug:`1146`
* :doc:`/plugins/convert`: Command-line argument construction now works
  on Windows. Thanks to :user:`mluds`. :bug:`1026` :bug:`1157` :bug:`1158`
* :doc:`/plugins/embedart`: Fix an erroneous missing-art error on Windows.
  Thanks to :user:`mluds`. :bug:`1163`
* :doc:`/plugins/importadded`: Now works with in-place and symlinked imports.
  :bug:`1170`
* :doc:`/plugins/ftintitle`: The plugin is now quiet when it runs as part of
  the import process. Thanks to :user:`Freso`. :bug:`1176` :bug:`1172`
* :doc:`/plugins/ftintitle`: Fix weird behavior when the same artist appears
  twice in the artist string. Thanks to Marc Addeo. :bug:`1179` :bug:`1181`
* :doc:`/plugins/lastgenre`: Match songs more robustly when they contain
  dashes. Thanks to :user:`djl`. :bug:`1156`
* The :ref:`config-cmd` command can now use ``$EDITOR`` variables with
  arguments.

.. _API changes: https://web.archive.org/web/20160814092627/https://developer.echonest.com/forums/thread/3650
.. _Plex: https://plex.tv/
.. _musixmatch: https://www.musixmatch.com/

1.3.9 (November 17, 2014)
-------------------------

This release adds two new standard plugins to beets: one for synchronizing
Last.fm listening data and one for integrating with Linux desktops. And at
long last, imports can now create symbolic links to music files instead of
copying or moving them. We also gained the ability to search for album art on
the iTunes Store and a new way to compute ReplayGain levels.

The major new features are:

* A new :doc:`/plugins/lastimport` lets you download your play count data from
  Last.fm into a flexible attribute. Thanks to Rafael Bodill.
* A new :doc:`/plugins/freedesktop` creates metadata files for
  Freedesktop.org--compliant file managers. Thanks to :user:`kerobaros`.
  :bug:`1056`, :bug:`707`
* A new :ref:`link` option in the ``import`` section creates symbolic links
  during import instead of moving or copying. Thanks to Rovanion Luckey.
  :bug:`710`, :bug:`114`
* :doc:`/plugins/fetchart`: You can now search for art on the iTunes Store.
  There's also a new ``sources`` config option that lets you choose exactly
  where to look for images and in which order.
* :doc:`/plugins/replaygain`: A new Python Audio Tools backend was added.
  Thanks to Francesco Rubino. :bug:`1070`
* :doc:`/plugins/embedart`: You can now automatically check that new art looks
  similar to existing art---ensuring that you only get a better "version" of
  the art you already have. See :ref:`image-similarity-check`.
* :doc:`/plugins/ftintitle`: The plugin now runs automatically on import. To
  disable this, unset the ``auto`` config flag.

There are also core improvements and other substantial additions:

* The ``media`` attribute is now a *track-level field* instead of an
  album-level one. This field stores the delivery mechanism for the music, so
  in its album-level incarnation, it could not represent heterogeneous
  releases---for example, an album consisting of a CD and a DVD. Now, tracks
  accurately indicate the media they appear on. Thanks to Heinz Wiesinger.
* Re-imports of your existing music (see :ref:`reimport`) now preserve its
  added date and flexible attributes. Thanks to Stig Inge Lea Bjørnsen.
* Slow queries, such as those over flexible attributes, should now be much
  faster when used with certain commands---notably, the :doc:`/plugins/play`.
* :doc:`/plugins/bpd`: Add a new configuration option for setting the default
  volume. Thanks to IndiGit.
* :doc:`/plugins/embedart`: A new ``ifempty`` config option lets you only
  embed album art when no album art is present. Thanks to kerobaros.
* :doc:`/plugins/discogs`: Authenticate with the Discogs server. The plugin
  now requires a Discogs account due to new API restrictions. Thanks to
  :user:`multikatt`. :bug:`1027`, :bug:`1040`

And countless little improvements and fixes:

* Standard cover art in APEv2 metadata is now supported. Thanks to Matthias
  Kiefer. :bug:`1042`
* :doc:`/plugins/convert`: Avoid a crash when embedding cover art
  fails.
* :doc:`/plugins/mpdstats`: Fix an error on start (introduced in the previous
  version). Thanks to Zach Denton.
* :doc:`/plugins/convert`: The ``--yes`` command-line flag no longer expects
  an argument.
* :doc:`/plugins/play`: Remove the temporary .m3u file after sending it to
  the player.
* The importer no longer tries to highlight partial differences in numeric
  quantities (track numbers and durations), which was often confusing.
* Date-based queries that are malformed (not parse-able) no longer crash
  beets and instead fail silently.
* :doc:`/plugins/duplicates`: Emit an error when the ``checksum`` config
  option is set incorrectly.
* The migration from pre-1.1, non-YAML configuration files has been removed.
  If you need to upgrade an old config file, use an older version of beets
  temporarily.
* :doc:`/plugins/discogs`: Recover from HTTP errors when communicating with
  the Discogs servers. Thanks to Dustin Rodriguez.
* :doc:`/plugins/embedart`: Do not log "embedding album art into..." messages
  during the import process.
* Fix a crash in the autotagger when files had only whitespace in their
  metadata.
* :doc:`/plugins/play`: Fix a potential crash when the command outputs special
  characters. :bug:`1041`
* :doc:`/plugins/web`: Queries typed into the search field are now treated as
  separate query components. :bug:`1045`
* Date tags that use slashes instead of dashes as separators are now
  interpreted correctly. And WMA (ASF) files now map the ``comments`` field to
  the "Description" tag (in addition to "WM/Comments"). Thanks to Matthias
  Kiefer. :bug:`1043`
* :doc:`/plugins/embedart`: Avoid resizing the image multiple times when
  embedding into an album. Thanks to :user:`kerobaros`. :bug:`1028`,
  :bug:`1036`
* :doc:`/plugins/discogs`: Avoid a situation where a trailing comma could be
  appended to some artist names. :bug:`1049`
* The output of the :ref:`stats-cmd` command is slightly different: the
  approximate size is now marked as such, and the total number of seconds only
  appears in exact mode.
* :doc:`/plugins/convert`: A new ``copy_album_art`` option puts images
  alongside converted files. Thanks to Ángel Alonso. :bug:`1050`, :bug:`1055`
* There is no longer a "conflict" between two plugins that declare the same
  field with the same type. Thanks to Peter Schnebel. :bug:`1059` :bug:`1061`
* :doc:`/plugins/chroma`: Limit the number of releases and recordings fetched
  as the result of an Acoustid match to avoid extremely long processing times
  for very popular music. :bug:`1068`
* Fix an issue where modifying an album's field without actually changing it
  would not update the corresponding tracks to bring differing tracks back in
  line with the album. :bug:`856`
* ``echonest`` plugin: When communicating with the Echo Nest servers
  fails repeatedly, log an error instead of exiting. :bug:`1096`
* :doc:`/plugins/lyrics`: Avoid an error when the Google source returns a
  result without a title. Thanks to Alberto Leal. :bug:`1097`
* Importing an archive will no longer leave temporary files behind in
  ``/tmp``. Thanks to :user:`multikatt`. :bug:`1067`, :bug:`1091`

1.3.8 (September 17, 2014)
--------------------------

This release has two big new chunks of functionality. Queries now support
**sorting** and user-defined fields can now have **types**.

If you want to see all your songs in reverse chronological order, just type
``beet list year-``. It couldn't be easier. For details, see
:ref:`query-sort`.

Flexible field types mean that some functionality that has previously only
worked for built-in fields, like range queries, can now work with plugin- and
user-defined fields too. For starters, the ``echonest`` plugin and
:doc:`/plugins/mpdstats` now mark the types of the fields they provide---so
you can now say, for example, ``beet ls liveness:0.5..1.5`` for the Echo Nest
"liveness" attribute. The :doc:`/plugins/types` makes it easy to specify field
types in your config file.

One upgrade note: if you use the :doc:`/plugins/discogs`, you will need to
upgrade the Discogs client library to use this version. Just type
``pip install -U discogs-client``.

Other new features:

* :doc:`/plugins/info`: Target files can now be specified through library
  queries (in addition to filenames). The ``--library`` option prints library
  fields instead of tags. Multiple files can be summarized together with the
  new ``--summarize`` option.
* :doc:`/plugins/mbcollection`: A new option lets you automatically update
  your collection on import. Thanks to Olin Gay.
* :doc:`/plugins/convert`: A new ``never_convert_lossy_files`` option can
  prevent lossy transcoding. Thanks to Simon Kohlmeyer.
* :doc:`/plugins/convert`: A new ``--yes`` command-line flag skips the
  confirmation.

Still more fixes and little improvements:

* Invalid state files don't crash the importer.
* :doc:`/plugins/lyrics`: Only strip featured artists and
  parenthesized title suffixes if no lyrics for the original artist and
  title were found.
* Fix a crash when reading some files with missing tags.
* :doc:`/plugins/discogs`: Compatibility with the new 2.0 version of the
  `discogs_client`_ Python library. If you were using the old version, you will
  need to upgrade to the latest version of the library to use the
  correspondingly new version of the plugin (e.g., with
  ``pip install -U discogs-client``). Thanks to Andriy Kohut.
* Fix a crash when writing files that can't be read. Thanks to Jocelyn De La
  Rosa.
* The :ref:`stats-cmd` command now counts album artists. The album count also
  more accurately reflects the number of albums in the database.
* :doc:`/plugins/convert`: Avoid crashes when tags cannot be written to newly
  converted files.
* Formatting templates with item data no longer confusingly shows album-level
  data when the two are inconsistent.
* Resuming imports and beginning incremental imports should now be much faster
  when there is a lot of previously-imported music to skip.
* :doc:`/plugins/lyrics`: Remove ``<script>`` tags from scraped lyrics. Thanks
  to Bombardment.
* :doc:`/plugins/play`: Add a ``relative_to`` config option. Thanks to
  BrainDamage.
* Fix a crash when a MusicBrainz release has zero tracks.
* The ``--version`` flag now works as an alias for the ``version`` command.
* :doc:`/plugins/lastgenre`: Remove some unhelpful genres from the default
  whitelist. Thanks to gwern.
* :doc:`/plugins/importfeeds`: A new ``echo`` output mode prints files' paths
  to standard error. Thanks to robotanarchy.
* :doc:`/plugins/replaygain`: Restore some error handling when ``mp3gain``
  output cannot be parsed. The verbose log now contains the bad tool output in
  this case.
* :doc:`/plugins/convert`: Fix filename extensions when converting
  automatically.
* The ``write`` plugin event allows plugins to change the tags that are
  written to a media file.
* :doc:`/plugins/zero`: Do not delete database values; only media file
  tags are affected.

.. _discogs_client: https://github.com/discogs/discogs_client

1.3.7 (August 22, 2014)
-----------------------

This release of beets fixes all the bugs, and you can be confident that you
will never again find any bugs in beets, ever.
It also adds support for plain old AIFF files and adds three more plugins,
including a nifty one that lets you measure a song's tempo by tapping out the
beat on your keyboard.
The importer deals more elegantly with duplicates and you can broaden your
cover art search to the entire web with Google Image Search.

The big new features are:

* Support for AIFF files. Tags are stored as ID3 frames in one of the file's
  IFF chunks. Thanks to Evan Purkhiser for contributing support to `Mutagen`_.
* The new :doc:`/plugins/importadded` reads files' modification times to set
  their "added" date. Thanks to Stig Inge Lea Bjørnsen.
* The new :doc:`/plugins/bpm` lets you manually measure the tempo of a playing
  song. Thanks to aroquen.
* The new :doc:`/plugins/spotify` generates playlists for your `Spotify`_
  account. Thanks to Olin Gay.
* A new :ref:`required` configuration option for the importer skips matches
  that are missing certain data. Thanks to oprietop.
* When the importer detects duplicates, it now shows you some details about
  the potentially-replaced music so you can make an informed decision. Thanks
  to Howard Jones.
* :doc:`/plugins/fetchart`: You can now optionally search for cover art on
  Google Image Search. Thanks to Lemutar.
* A new :ref:`asciify-paths` configuration option replaces all non-ASCII
  characters in paths.

.. _Mutagen: https://github.com/quodlibet/mutagen
.. _Spotify: https://www.spotify.com/

And the multitude of little improvements and fixes:

* Compatibility with the latest version of `Mutagen`_, 1.23.
* :doc:`/plugins/web`: Lyrics now display readably with correct line breaks.
  Also, the detail view scrolls to reveal all of the lyrics. Thanks to Meet
  Udeshi.
* :doc:`/plugins/play`: The ``command`` config option can now contain
  arguments (rather than just an executable). Thanks to Alessandro Ghedini.
* Fix an error when using the :ref:`modify-cmd` command to remove a flexible
  attribute. Thanks to Pierre Rust.
* :doc:`/plugins/info`: The command now shows audio properties (e.g., bitrate)
  in addition to metadata. Thanks Alessandro Ghedini.
* Avoid a crash on Windows when writing to files with special characters in
  their names.
* :doc:`/plugins/play`: Playing albums now generates filenames by default (as
  opposed to directories) for better compatibility. The ``use_folders`` option
  restores the old behavior. Thanks to Lucas Duailibe.
* Fix an error when importing an empty directory with the ``--flat`` option.
* :doc:`/plugins/mpdstats`: The last song in a playlist is now correctly
  counted as played. Thanks to Johann Klähn.
* :doc:`/plugins/zero`: Prevent accidental nulling of dangerous fields (IDs
  and paths). Thanks to brunal.
* The :ref:`remove-cmd` command now shows the paths of files that will be
  deleted. Thanks again to brunal.
* Don't display changes for fields that are not in the restricted field set.
  This fixes :ref:`write-cmd` showing changes for fields that are not written
  to the file.
* The :ref:`write-cmd` command avoids displaying the item name if there are
  no changes for it.
* When using both the :doc:`/plugins/convert` and the :doc:`/plugins/scrub`,
  avoid scrubbing the source file of conversions. (Fix a regression introduced
  in the previous release.)
* :doc:`/plugins/replaygain`: Logging is now quieter during import. Thanks to
  Yevgeny Bezman.
* :doc:`/plugins/fetchart`: When loading art from the filesystem, we now
  prioritize covers with more keywords in them. This means that
  ``cover-front.jpg`` will now be taken before ``cover-back.jpg`` because it
  contains two keywords rather than one. Thanks to Fabrice Laporte.
* :doc:`/plugins/lastgenre`: Remove duplicates from canonicalized genre lists.
  Thanks again to Fabrice Laporte.
* The importer now records its progress when skipping albums. This means that
  incremental imports will no longer try to import albums again after you've
  chosen to skip them, and erroneous invitations to resume "interrupted"
  imports should be reduced. Thanks to jcassette.
* :doc:`/plugins/bucket`: You can now customize the definition of alphanumeric
  "ranges" using regular expressions. And the heuristic for detecting years
  has been improved. Thanks to sotho.
* Already-imported singleton tracks are skipped when resuming an
  import.
* :doc:`/plugins/chroma`: A new ``auto`` configuration option disables
  fingerprinting on import. Thanks to ddettrittus.
* :doc:`/plugins/convert`: A new ``--format`` option to can select the
  transcoding preset from the command-line.
* :doc:`/plugins/convert`: Transcoding presets can now omit their filename
  extensions (extensions default to the name of the preset).
* :doc:`/plugins/convert`: A new ``--pretend`` option lets you preview the
  commands the plugin will execute without actually taking any action. Thanks
  to Dietrich Daroch.
* Fix a crash when a float-valued tag field only contained a ``+`` or ``-``
  character.
* Fixed a regression in the core that caused the :doc:`/plugins/scrub` not to
  work in ``auto`` mode. Thanks to Harry Khanna.
* The :ref:`write-cmd` command now has a ``--force`` flag. Thanks again to
  Harry Khanna.
* :doc:`/plugins/mbsync`: Track alignment now works with albums that have
  multiple copies of the same recording. Thanks to Rui Gonçalves.

1.3.6 (May 10, 2014)
--------------------

This is primarily a bugfix release, but it also brings two new plugins: one
for playing music in desktop players and another for organizing your
directories into "buckets." It also brings huge performance optimizations to
queries---your ``beet ls`` commands will now go much faster.

New features:

* The new :doc:`/plugins/play` lets you start your desktop music player with
  the songs that match a query. Thanks to David Hamp-Gonsalves.
* The new :doc:`/plugins/bucket` provides a ``%bucket{}`` function for path
  formatting to generate folder names representing ranges of years or initial
  letter. Thanks to Fabrice Laporte.
* Item and album queries are much faster.
* :doc:`/plugins/ftintitle`: A new option lets you remove featured artists
  entirely instead of moving them to the title. Thanks to SUTJael.

And those all-important bug fixes:

* :doc:`/plugins/mbsync`: Fix a regression in 1.3.5 that broke the plugin
  entirely.
* :ref:`Shell completion <completion>` now searches more common paths for its
  ``bash_completion`` dependency.
* Fix encoding-related logging errors in :doc:`/plugins/convert` and
  :doc:`/plugins/replaygain`.
* :doc:`/plugins/replaygain`: Suppress a deprecation warning emitted by later
  versions of PyGI.
* Fix a crash when reading files whose iTunes SoundCheck tags contain
  non-ASCII characters.
* The ``%if{}`` template function now appropriately interprets the condition
  as false when it contains the string "false". Thanks to Ayberk Yilmaz.
* :doc:`/plugins/convert`: Fix conversion for files that include a video
  stream by ignoring it. Thanks to brunal.
* :doc:`/plugins/fetchart`: Log an error instead of crashing when tag
  manipulation fails.
* :doc:`/plugins/convert`: Log an error instead of crashing when
  embedding album art fails.
* :doc:`/plugins/convert`: Embed cover art into converted files.
  Previously they were embedded into the source files.
* New plugin event: `before_item_moved`. Thanks to Robert Speicher.

1.3.5 (April 15, 2014)
----------------------

This is a short-term release that adds some great new stuff to beets. There's
support for tracking and calculating musical keys, the ReplayGain plugin was
expanded to work with more music formats via GStreamer, we can now import
directly from compressed archives, and the lyrics plugin is more robust.

One note for upgraders and packagers: this version of beets has a new
dependency in `enum34`_, which is a backport of the new `enum`_ standard
library module.

The major new features are:

* Beets can now import `zip`, `tar`, and `rar` archives. Just type ``beet
  import music.zip`` to have beets transparently extract the files to import.
* :doc:`/plugins/replaygain`: Added support for calculating ReplayGain values
  with GStreamer as well the mp3gain program. This enables ReplayGain
  calculation for any audio format. Thanks to Yevgeny Bezman.
* :doc:`/plugins/lyrics`: Lyrics should now be found for more songs. Searching
  is now sensitive to featured artists and parenthesized title suffixes.
  When a song has multiple titles, lyrics from all the named songs are now
  concatenated. Thanks to Fabrice Laporte and Paul Phillips.

In particular, a full complement of features for supporting musical keys are
new in this release:

* A new `initial_key` field is available in the database and files' tags. You
  can set the field manually using a command like ``beet modify
  initial_key=Am``.
* The ``echonest`` plugin sets the `initial_key` field if the data is
  available.
* A new :doc:`/plugins/keyfinder` runs a command-line tool to get the key from
  audio data and store it in the `initial_key` field.

There are also many bug fixes and little enhancements:

* ``echonest`` plugin: Truncate files larger than 50MB before uploading for
  analysis.
* :doc:`/plugins/fetchart`: Fix a crash when the server does not specify a
  content type. Thanks to Lee Reinhardt.
* :doc:`/plugins/convert`: The ``--keep-new`` flag now works correctly
  and the library includes the converted item.
* The importer now logs a message instead of crashing when errors occur while
  opening the files to be imported.
* :doc:`/plugins/embedart`: Better error messages in exceptional conditions.
* Silenced some confusing error messages when searching for a non-MusicBrainz
  ID. Using an invalid ID (of any kind---Discogs IDs can be used there too) at
  the "Enter ID:" importer prompt now just silently returns no results. More
  info is in the verbose logs.
* :doc:`/plugins/mbsync`: Fix application of album-level metadata. Due to a
  regression a few releases ago, only track-level metadata was being updated.
* On Windows, paths on network shares (UNC paths) no longer cause "invalid
  filename" errors.
* :doc:`/plugins/replaygain`: Fix crashes when attempting to log errors.
* The :ref:`modify-cmd` command can now accept query arguments that contain =
  signs. An argument is considered a query part when a : appears before any
  =s. Thanks to mook.

.. _enum34: https://pypi.python.org/pypi/enum34
.. _enum: https://docs.python.org/3.4/library/enum.html

1.3.4 (April 5, 2014)
---------------------

This release brings a hodgepodge of medium-sized conveniences to beets. A new
:ref:`config-cmd` command manages your configuration, we now have :ref:`bash
completion <completion>`, and the :ref:`modify-cmd` command can delete
attributes. There are also some significant performance optimizations to the
autotagger's matching logic.

One note for upgraders: if you use the :doc:`/plugins/fetchart`, it has a new
dependency, the `requests`_ module.

New stuff:

* Added a :ref:`config-cmd` command to manage your configuration. It can show
  you what you currently have in your config file, point you at where the file
  should be, or launch your text editor to let you modify the file. Thanks to
  geigerzaehler.
* Beets now ships with a shell command completion script! See
  :ref:`completion`. Thanks to geigerzaehler.
* The :ref:`modify-cmd` command now allows removing flexible attributes. For
  example, ``beet modify artist:beatles oldies!`` deletes the ``oldies``
  attribute from matching items. Thanks to brilnius.
* Internally, beets has laid the groundwork for supporting multi-valued
  fields. Thanks to geigerzaehler.
* The importer interface now shows the URL for MusicBrainz matches. Thanks to
  johtso.
* :doc:`/plugins/smartplaylist`: Playlists can now be generated from multiple
  queries (combined with "or" logic). Album-level queries are also now
  possible and automatic playlist regeneration can now be disabled. Thanks to
  brilnius.
* ``echonest`` plugin: Echo Nest similarity now weights the tempo in
  better proportion to other metrics. Also, options were added to specify
  custom thresholds and output formats. Thanks to Adam M.
* Added the :ref:`after_write <plugin_events>` plugin event.
* :doc:`/plugins/lastgenre`: Separator in genre lists can now be
  configured. Thanks to brilnius.
* We now only use "primary" aliases for artist names from MusicBrainz. This
  eliminates some strange naming that could occur when the `languages` config
  option was set. Thanks to Filipe Fortes.
* The performance of the autotagger's matching mechanism is vastly improved.
  This should be noticeable when matching against very large releases such as
  box sets.
* The :ref:`import-cmd` command can now accept individual files as arguments
  even in non-singleton mode. Files are imported as one-track albums.

Fixes:

* Error messages involving paths no longer escape non-ASCII characters (for
  legibility).
* Fixed a regression that made it impossible to use the :ref:`modify-cmd`
  command to add new flexible fields. Thanks to brilnius.
* ``echonest`` plugin: Avoid crashing when the audio analysis fails.
  Thanks to Pedro Silva.
* :doc:`/plugins/duplicates`: Fix checksumming command execution for files
  with quotation marks in their names. Thanks again to Pedro Silva.
* Fix a crash when importing with both of the :ref:`group_albums` and
  :ref:`incremental` options enabled. Thanks to geigerzaehler.
* Give a sensible error message when ``BEETSDIR`` points to a file. Thanks
  again to geigerzaehler.
* Fix a crash when reading WMA files whose boolean-valued fields contain
  strings. Thanks to johtso.
* :doc:`/plugins/fetchart`: The plugin now sends "beets" as the User-Agent
  when making scraping requests. This helps resolve some blocked requests. The
  plugin now also depends on the `requests`_ Python library.
* The :ref:`write-cmd` command now only shows the changes to fields that will
  actually be written to a file.
* :doc:`/plugins/duplicates`: Spurious reports are now avoided for tracks with
  missing values (e.g., no MBIDs). Thanks to Pedro Silva.
* The default :ref:`replace` sanitation options now remove leading whitespace
  by default. Thanks to brilnius.
* :doc:`/plugins/importfeeds`: Fix crash when importing albums
  containing ``/`` with the ``m3u_multi`` format.
* Avoid crashing on Mutagen bugs while writing files' tags.
* :doc:`/plugins/convert`: Display a useful error message when the FFmpeg
  executable can't be found.

.. _requests: https://requests.readthedocs.io/en/master/

1.3.3 (February 26, 2014)
-------------------------

Version 1.3.3 brings a bunch changes to how item and album fields work
internally. Along with laying the groundwork for some great things in the
future, this brings a number of improvements to how you interact with beets.
Here's what's new with fields in particular:

* Plugin-provided fields can now be used in queries. For example, if you use
  the :doc:`/plugins/inline` to define a field called ``era``, you can now
  filter your library based on that field by typing something like
  ``beet list era:goldenage``.
* Album-level flexible attributes and plugin-provided attributes can now be
  used in path formats (and other item-level templates).
* :ref:`Date-based queries <datequery>` are now possible. Try getting every
  track you added in February 2014 with ``beet ls added:2014-02`` or in the
  whole decade with ``added:2010..``. Thanks to Stig Inge Lea Bjørnsen.
* The :ref:`modify-cmd` command is now better at parsing and formatting
  fields. You can assign to boolean fields like ``comp``, for example, using
  either the words "true" or "false" or the numerals 1 and 0. Any
  boolean-esque value is normalized to a real boolean. The :ref:`update-cmd`
  and :ref:`write-cmd` commands also got smarter at formatting and colorizing
  changes.

For developers, the short version of the story is that Item and Album objects
provide *uniform access* across fixed, flexible, and computed attributes. You
can write ``item.foo`` to access the ``foo`` field without worrying about
where the data comes from.

Unrelated new stuff:

* The importer has a new interactive option (*G* for "Group albums"),
  command-line flag (``--group-albums``), and config option
  (:ref:`group_albums`) that lets you split apart albums that are mixed
  together in a single directory. Thanks to geigerzaehler.
* A new ``--config`` command-line option lets you specify an additional
  configuration file. This option *combines* config settings with your default
  config file. (As part of this change, the ``BEETSDIR`` environment variable
  no longer combines---it *replaces* your default config file.) Thanks again
  to geigerzaehler.
* :doc:`/plugins/ihate`: The plugin's configuration interface was overhauled.
  Its configuration is now much simpler---it uses beets queries instead of an
  ad-hoc per-field configuration. This is *backwards-incompatible*---if you
  use this plugin, you will need to update your configuration. Thanks to
  BrainDamage.

Other little fixes:

* ``echonest`` plugin: Tempo (BPM) is now always stored as an integer.
  Thanks to Heinz Wiesinger.
* Fix Python 2.6 compatibility in some logging statements in
  :doc:`/plugins/chroma` and :doc:`/plugins/lastgenre`.
* Prevent some crashes when things go really wrong when writing file metadata
  at the end of the import process.
* New plugin events: ``item_removed`` (thanks to Romuald Conty) and
  ``item_copied`` (thanks to Stig Inge Lea Bjørnsen).
* The ``pluginpath`` config option can now point to the directory containing
  plugin code. (Previously, it awkwardly needed to point at a directory
  containing a ``beetsplug`` directory, which would then contain your code.
  This is preserved as an option for backwards compatibility.) This change
  should also work around a long-standing issue when using ``pluginpath`` when
  beets is installed using pip. Many thanks to geigerzaehler.
* :doc:`/plugins/web`: The ``/item/`` and ``/album/`` API endpoints now
  produce full details about albums and items, not just lists of IDs. Thanks
  to geigerzaehler.
* Fix a potential crash when using image resizing with the
  :doc:`/plugins/fetchart` or :doc:`/plugins/embedart` without ImageMagick
  installed.
* Also, when invoking ``convert`` for image resizing fails, we now log an
  error instead of crashing.
* :doc:`/plugins/fetchart`: The ``beet fetchart`` command can now associate
  local images with albums (unless ``--force`` is provided). Thanks to
  brilnius.
* :doc:`/plugins/fetchart`: Command output is now colorized. Thanks again to
  brilnius.
* The :ref:`modify-cmd` command avoids writing files and committing to the
  database when nothing has changed. Thanks once more to brilnius.
* The importer now uses the album artist field when guessing existing
  metadata for albums (rather than just the track artist field). Thanks to
  geigerzaehler.
* :doc:`/plugins/fromfilename`: Fix a crash when a filename contained only a
  track number (e.g., ``02.mp3``).
* :doc:`/plugins/convert`: Transcoding should now work on Windows.
* :doc:`/plugins/duplicates`: The ``move`` and ``copy`` destination arguments
  are now treated as directories. Thanks to Pedro Silva.
* The :ref:`modify-cmd` command now skips confirmation and prints a message if
  no changes are necessary. Thanks to brilnius.
* :doc:`/plugins/fetchart`: When using the ``remote_priority`` config option,
  local image files are no longer completely ignored.
* ``echonest`` plugin: Fix an issue causing the plugin to appear twice in
  the output of the ``beet version`` command.
* :doc:`/plugins/lastgenre`: Fix an occasional crash when no tag weight was
  returned by Last.fm.
* :doc:`/plugins/mpdstats`: Restore the ``last_played`` field. Thanks to
  Johann Klähn.
* The :ref:`modify-cmd` command's output now clearly shows when a file has
  been deleted.
* Album art in files with Vorbis Comments is now marked with the "front cover"
  type. Thanks to Jason Lefley.

1.3.2 (December 22, 2013)
-------------------------

This update brings new plugins for fetching acoustic metrics and listening
statistics, many more options for the duplicate detection plugin, and flexible
options for fetching multiple genres.

The "core" of beets gained a new built-in command: :ref:`beet write
<write-cmd>` updates the metadata tags for files, bringing them back
into sync with your database. Thanks to Heinz Wiesinger.

We added some plugins and overhauled some existing ones:

* The new ``echonest`` plugin plugin can fetch a wide range of `acoustic
  attributes`_ from `The Echo Nest`_, including the "speechiness" and
  "liveness" of each track. The new plugin supersedes an older version
  (``echonest_tempo``) that only fetched the BPM field. Thanks to Pedro Silva
  and Peter Schnebel.

* The :doc:`/plugins/duplicates` got a number of new features, thanks to Pedro
  Silva:

  * The ``keys`` option lets you specify the fields used detect duplicates.
  * You can now use checksumming (via an external command) to find
    duplicates instead of metadata via the ``checksum`` option.
  * The plugin can perform actions on the duplicates it find. The new
    ``copy``, ``move``, ``delete``, ``delete_file``, and ``tag`` options
    perform those actions.

* The new :doc:`/plugins/mpdstats` collects statistics about your
  listening habits from `MPD`_. Thanks to Peter Schnebel and Johann Klähn.

* :doc:`/plugins/lastgenre`: The new ``multiple`` option has been replaced
  with the ``count`` option, which lets you limit the number of genres added
  to your music. (No more thousand-character genre fields!) Also, the
  ``min_weight`` field filters out nonsense tags to make your genres more
  relevant. Thanks to Peter Schnebel and rashley60.

* :doc:`/plugins/lyrics`: A new ``--force`` option optionally re-downloads
  lyrics even when files already have them. Thanks to Bitdemon.

As usual, there are also innumerable little fixes and improvements:

* When writing ID3 tags for ReplayGain normalization, tags are written with
  both upper-case and lower-case TXXX frame descriptions. Previous versions of
  beets used only the upper-case style, which seems to be more standard, but
  some players (namely, Quod Libet and foobar2000) seem to only use lower-case
  names.
* :doc:`/plugins/missing`: Avoid a possible error when an album's
  ``tracktotal`` field is missing.
* :doc:`/plugins/ftintitle`: Fix an error when the sort artist is missing.
* ``echonest_tempo``: The plugin should now match songs more
  reliably (i.e., fewer "no tempo found" messages). Thanks to Peter Schnebel.
* :doc:`/plugins/convert`: Fix an "Item has no library" error when using the
  ``auto`` config option.
* :doc:`/plugins/convert`: Fix an issue where files of the wrong format would
  have their transcoding skipped (and files with the right format would be
  needlessly transcoded). Thanks to Jakob Schnitzer.
* Fix an issue that caused the :ref:`id3v23` option to work only occasionally.
* Also fix using :ref:`id3v23` in conjunction with the ``scrub`` and
  ``embedart`` plugins. Thanks to Chris Cogburn.
* :doc:`/plugins/ihate`: Fix an error when importing singletons. Thanks to
  Mathijs de Bruin.
* The :ref:`clutter` option can now be a whitespace-separated list in addition
  to a YAML list.
* Values for the :ref:`replace` option can now be empty (i.e., null is
  equivalent to the empty string).
* :doc:`/plugins/lastgenre`: Fix a conflict between canonicalization and
  multiple genres.
* When a match has a year but not a month or day, the autotagger now "zeros
  out" the month and day fields after applying the year.
* For plugin developers: added an ``optparse`` callback utility function for
  performing actions based on arguments. Thanks to Pedro Silva.
* :doc:`/plugins/scrub`: Fix scrubbing of MPEG-4 files. Thanks to Yevgeny
  Bezman.

.. _Acoustic Attributes: https://web.archive.org/web/20160701063109/http://developer.echonest.com/acoustic-attributes.html
.. _MPD: https://www.musicpd.org/

1.3.1 (October 12, 2013)
------------------------

This release boasts a host of new little features, many of them contributed by
beets' amazing and prolific community. It adds support for `Opus`_ files,
transcoding to any format, and two new plugins: one that guesses metadata for
"blank" files based on their filenames and one that moves featured artists
into the title field.

Here's the new stuff:

* Add `Opus`_ audio support. Thanks to Rowan Lewis.
* :doc:`/plugins/convert`: You can now transcode files to any audio format,
  rather than just MP3. Thanks again to Rowan Lewis.
* The new :doc:`/plugins/fromfilename` guesses tags from the filenames during
  import when metadata tags themselves are missing. Thanks to Jan-Erik Dahlin.
* The :doc:`/plugins/ftintitle`, by `@Verrus`_, is now distributed with beets.
  It helps you rewrite tags to move "featured" artists from the artist field
  to the title field.
* The MusicBrainz data source now uses track artists over recording
  artists. This leads to better metadata when tagging classical music. Thanks
  to Henrique Ferreiro.
* :doc:`/plugins/lastgenre`: You can now get multiple genres per album or
  track using the ``multiple`` config option. Thanks to rashley60 on GitHub.
* A new :ref:`id3v23` config option makes beets write MP3 files' tags using
  the older ID3v2.3 metadata standard. Use this if you want your tags to be
  visible to Windows and some older players.

And some fixes:

* :doc:`/plugins/fetchart`: Better error message when the image file has an
  unrecognized type.
* :doc:`/plugins/mbcollection`: Detect, log, and skip invalid MusicBrainz IDs
  (instead of failing with an API error).
* :doc:`/plugins/info`: Fail gracefully when used erroneously with a
  directory.
* ``echonest_tempo``: Fix an issue where the plugin could use the
  tempo from the wrong song when the API did not contain the requested song.
* Fix a crash when a file's metadata included a very large number (one wider
  than 64 bits). These huge numbers are now replaced with zeroes in the
  database.
* When a track on a MusicBrainz release has a different length from the
  underlying recording's length, the track length is now used instead.
* With :ref:`per_disc_numbering` enabled, the ``tracktotal`` field is now set
  correctly (i.e., to the number of tracks on the disc).
* :doc:`/plugins/scrub`: The ``scrub`` command now restores album art in
  addition to other (database-backed) tags.
* :doc:`/plugins/mpdupdate`: Domain sockets can now begin with a tilde (which
  is correctly expanded to ``$HOME``) as well as a slash. Thanks to Johann
  Klähn.
* :doc:`/plugins/lastgenre`: Fix a regression that could cause new genres
  found during import not to be persisted.
* Fixed a crash when imported album art was also marked as "clutter" where the
  art would be deleted before it could be moved into place. This led to a
  "image.jpg not found during copy" error. Now clutter is removed (and
  directories pruned) much later in the process, after the
  ``import_task_files`` hook.
* :doc:`/plugins/missing`: Fix an error when printing missing track names.
  Thanks to Pedro Silva.
* Fix an occasional KeyError in the :ref:`update-cmd` command introduced in
  1.3.0.
* :doc:`/plugins/scrub`: Avoid preserving certain non-standard ID3 tags such
  as NCON.

.. _Opus: https://www.opus-codec.org/
.. _@Verrus: https://github.com/Verrus

1.3.0 (September 11, 2013)
--------------------------

Albums and items now have **flexible attributes**. This means that, when you
want to store information about your music in the beets database, you're no
longer constrained to the set of fields it supports out of the box (title,
artist, track, etc.). Instead, you can use any field name you can think of and
treat it just like the built-in fields.

For example, you can use the :ref:`modify-cmd` command to set a new field on a
track::

    $ beet modify mood=sexy artist:miguel

and then query your music based on that field::

    $ beet ls mood:sunny

or use templates to see the value of the field::

    $ beet ls -f '$title: $mood'

While this feature is nifty when used directly with the usual command-line
suspects, it's especially useful for plugin authors and for future beets
features. Stay tuned for great things built on this flexible attribute
infrastructure.

One side effect of this change: queries that include unknown fields will now
match *nothing* instead of *everything*. So if you type ``beet ls
fieldThatDoesNotExist:foo``, beets will now return no results, whereas
previous versions would spit out a warning and then list your entire library.

There's more detail than you could ever need `on the beets blog`_.

.. _on the beets blog: https://beets.io/blog/flexattr.html

1.2.2 (August 27, 2013)
-----------------------

This is a bugfix release. We're in the midst of preparing for a large change
in beets 1.3, so 1.2.2 resolves some issues that came up over the last few
weeks. Stay tuned!

The improvements in this release are:

* A new plugin event, ``item_moved``, is sent when files are moved on disk.
  Thanks to dsedivec.
* :doc:`/plugins/lyrics`: More improvements to the Google backend by Fabrice
  Laporte.
* :doc:`/plugins/bpd`: Fix for a crash when searching, thanks to Simon Chopin.
* Regular expression queries (and other query types) over paths now work.
  (Previously, special query types were ignored for the ``path`` field.)
* :doc:`/plugins/fetchart`: Look for images in the Cover Art Archive for
  the release group in addition to the specific release. Thanks to Filipe
  Fortes.
* Fix a race in the importer that could cause files to be deleted before they
  were imported. This happened when importing one album, importing a duplicate
  album, and then asking for the first album to be replaced with the second.
  The situation could only arise when importing music from the library
  directory and when the two albums are imported close in time.

1.2.1 (June 22, 2013)
---------------------

This release introduces a major internal change in the way that similarity
scores are handled. It means that the importer interface can now show you
exactly why a match is assigned its score and that the autotagger gained a few
new options that let you customize how matches are prioritized and
recommended.

The refactoring work is due to the continued efforts of Tai Lee. The
changes you'll notice while using the autotagger are:

* The top 3 distance penalties are now displayed on the release listing,
  and all album and track penalties are now displayed on the track changes
  list. This should make it clear exactly which metadata is contributing to a
  low similarity score.
* When displaying differences, the colorization has been made more consistent
  and helpful: red for an actual difference, yellow to indicate that a
  distance penalty is being applied, and light gray for no penalty (e.g., case
  changes) or disambiguation data.

There are also three new (or overhauled) configuration options that let you
customize the way that matches are selected:

* The :ref:`ignored` setting lets you instruct the importer not to show you
  matches that have a certain penalty applied.
* The :ref:`preferred` collection of settings specifies a sorted list of
  preferred countries and media types, or prioritizes releases closest to the
  original year for an album.
* The :ref:`max_rec` settings can now be used for any distance penalty
  component. The recommendation will be downgraded if a non-zero penalty is
  being applied to the specified field.

And some little enhancements and bug fixes:

* Multi-disc directory names can now contain "disk" (in addition to "disc").
  Thanks to John Hawthorn.
* :doc:`/plugins/web`: Item and album counts are now exposed through the API
  for use with the Tomahawk resolver. Thanks to Uwe L. Korn.
* Python 2.6 compatibility for ``beatport``,
  :doc:`/plugins/missing`, and :doc:`/plugins/duplicates`. Thanks to Wesley
  Bitter and Pedro Silva.
* Don't move the config file during a null migration. Thanks to Theofilos
  Intzoglou.
* Fix an occasional crash in the ``beatport`` when a length
  field was missing from the API response. Thanks to Timothy Appnel.
* :doc:`/plugins/scrub`: Handle and log I/O errors.
* :doc:`/plugins/lyrics`: The Google backend should now turn up more results.
  Thanks to Fabrice Laporte.
* :doc:`/plugins/random`: Fix compatibility with Python 2.6. Thanks to
  Matthias Drochner.

1.2.0 (June 5, 2013)
--------------------

There's a *lot* of new stuff in this release: new data sources for the
autotagger, new plugins to look for problems in your library, tracking the
date that you acquired new music, an awesome new syntax for doing queries over
numeric fields, support for ALAC files, and major enhancements to the
importer's UI and distance calculations. A special thanks goes out to all the
contributors who helped make this release awesome.

For the first time, beets can now tag your music using additional **data
sources** to augment the matches from MusicBrainz. When you enable either of
these plugins, the importer will start showing you new kinds of matches:

* New :doc:`/plugins/discogs`: Get matches from the `Discogs`_ database.
  Thanks to Artem Ponomarenko and Tai Lee.
* New ``beatport`` plugin: Get matches from the `Beatport`_ database.
  Thanks to Johannes Baiter.

We also have two other new plugins that can scan your library to check for
common problems, both by Pedro Silva:

* New :doc:`/plugins/duplicates`: Find tracks or albums in your
  library that are **duplicated**.
* New :doc:`/plugins/missing`: Find albums in your library that are **missing
  tracks**.

There are also three more big features added to beets core:

* Your library now keeps track of **when music was added** to it. The new
  ``added`` field is a timestamp reflecting when each item and album was
  imported and the new ``%time{}`` template function lets you format this
  timestamp for humans. Thanks to Lucas Duailibe.
* When using queries to match on quantitative fields, you can now use
  **numeric ranges**. For example, you can get a list of albums from the '90s
  by typing ``beet ls year:1990..1999`` or find high-bitrate music with
  ``bitrate:128000..``. See :ref:`numericquery`. Thanks to Michael Schuerig.
* **ALAC files** are now marked as ALAC instead of being conflated with AAC
  audio. Thanks to Simon Luijk.

In addition, the importer saw various UI enhancements, thanks to Tai Lee:

* More consistent format and colorization of album and track metadata.
* Display data source URL for matches from the new data source plugins. This
  should make it easier to migrate data from Discogs or Beatport into
  MusicBrainz.
* Display album disambiguation and disc titles in the track listing, when
  available.
* Track changes are highlighted in yellow when they indicate a change in
  format to or from the style of :ref:`per_disc_numbering`. (As before, no
  penalty is applied because the track number is still "correct", just in a
  different format.)
* Sort missing and unmatched tracks by index and title and group them
  together for better readability.
* Indicate MusicBrainz ID mismatches.

The calculation of the similarity score for autotagger matches was also
improved, again thanks to Tai Lee. These changes, in general, help deal with
the new metadata sources and help disambiguate between similar releases in the
same MusicBrainz release group:

* Strongly prefer releases with a matching MusicBrainz album ID. This helps
  beets re-identify the same release when re-importing existing files.
* Prefer releases that are closest to the tagged ``year``. Tolerate files
  tagged with release or original year.
* The new ``preferred_media`` config option lets you prefer a certain media
  type when the ``media`` field is unset on an album.
* Apply minor penalties across a range of fields to differentiate between
  nearly identical releases: ``disctotal``, ``label``, ``catalognum``,
  ``country`` and ``albumdisambig``.

As usual, there were also lots of other great littler enhancements:

* :doc:`/plugins/random`: A new ``-e`` option gives an equal chance to each
  artist in your collection to avoid biasing random samples to prolific
  artists. Thanks to Georges Dubus.
* The :ref:`modify-cmd` now correctly converts types when modifying non-string
  fields. You can now safely modify the "comp" flag and the "year" field, for
  example. Thanks to Lucas Duailibe.
* :doc:`/plugins/convert`: You can now configure the path formats for
  converted files separately from your main library. Thanks again to Lucas
  Duailibe.
* The importer output now shows the number of audio files in each album.
  Thanks to jayme on GitHub.
* Plugins can now provide fields for both Album and Item templates, thanks
  to Pedro Silva. Accordingly, the :doc:`/plugins/inline` can also now define
  album fields. For consistency, the ``pathfields`` configuration section has
  been renamed ``item_fields`` (although the old name will still work for
  compatibility).
* Plugins can also provide metadata matches for ID searches. For example, the
  new Discogs plugin lets you search for an album by its Discogs ID from the
  same prompt that previously just accepted MusicBrainz IDs. Thanks to
  Johannes Baiter.
* The :ref:`fields-cmd` command shows template fields provided by plugins.
  Thanks again to Pedro Silva.
* :doc:`/plugins/mpdupdate`: You can now communicate with MPD over a Unix
  domain socket. Thanks to John Hawthorn.

And a batch of fixes:

* Album art filenames now respect the :ref:`replace` configuration.
* Friendly error messages are now printed when trying to read or write files
  that go missing.
* The :ref:`modify-cmd` command can now change albums' album art paths (i.e.,
  ``beet modify artpath=...`` works). Thanks to Lucas Duailibe.
* :doc:`/plugins/zero`: Fix a crash when nulling out a field that contains
  None.
* Templates can now refer to non-tag item fields (e.g., ``$id`` and
  ``$album_id``).
* :doc:`/plugins/lyrics`: Lyrics searches should now turn up more results due
  to some fixes in dealing with special characters.

.. _Discogs: https://discogs.com/
.. _Beatport: https://www.beatport.com/

1.1.0 (April 29, 2013)
----------------------

This final release of 1.1 brings a little polish to the betas that introduced
the new configuration system. The album art and lyrics plugins also got a
little love.

If you're upgrading from 1.0.0 or earlier, this release (like the 1.1 betas)
will automatically migrate your configuration to the new system.

* :doc:`/plugins/embedart`: The ``embedart`` command now embeds each album's
  associated art by default. The ``--file`` option invokes the old behavior,
  in which a specific image file is used.
* :doc:`/plugins/lyrics`: A new (optional) Google Custom Search backend was
  added for finding lyrics on a wide array of sites. Thanks to Fabrice
  Laporte.
* When automatically detecting the filesystem's maximum filename length, never
  guess more than 200 characters. This prevents errors on systems where the
  maximum length was misreported. You can, of course, override this default
  with the :ref:`max_filename_length` option.
* :doc:`/plugins/fetchart`: Two new configuration options were added:
  ``cover_names``, the list of keywords used to identify preferred images, and
  ``cautious``, which lets you avoid falling back to images that don't contain
  those keywords. Thanks to Fabrice Laporte.
* Avoid some error cases in the ``update`` command and the ``embedart`` and
  ``mbsync`` plugins. Invalid or missing files now cause error logs instead of
  crashing beets. Thanks to Lucas Duailibe.
* :doc:`/plugins/lyrics`: Searches now strip "featuring" artists when
  searching for lyrics, which should increase the hit rate for these tracks.
  Thanks to Fabrice Laporte.
* When listing the items in an album, the items are now always in track-number
  order. This should lead to more predictable listings from the
  :doc:`/plugins/importfeeds`.
* :doc:`/plugins/smartplaylist`: Queries are now split using shell-like syntax
  instead of just whitespace, so you can now construct terms that contain
  spaces.
* :doc:`/plugins/lastgenre`: The ``force`` config option now defaults to true
  and controls the behavior of the import hook. (Previously, new genres were
  always forced during import.)
* :doc:`/plugins/web`: Fix an error when specifying the hostname on the
  command line.
* :doc:`/plugins/web`: The underlying API was expanded slightly to support
  `Tomahawk`_ collections. And file transfers now have a "Content-Length"
  header. Thanks to Uwe L. Korn.
* :doc:`/plugins/lastgenre`: Fix an error when using genre canonicalization.

.. _Tomahawk: https://github.com/tomahawk-player/tomahawk

1.1b3 (March 16, 2013)
----------------------

This third beta of beets 1.1 brings a hodgepodge of little new features (and
internal overhauls that will make improvements easier in the future). There
are new options for getting metadata in a particular language and seeing more
detail during the import process. There's also a new plugin for synchronizing
your metadata with MusicBrainz. Under the hood, plugins can now extend the
query syntax.

New configuration options:

* :ref:`languages` controls the preferred languages when selecting an alias
  from MusicBrainz. This feature requires `python-musicbrainzngs`_ 0.3 or
  later. Thanks to Sam Doshi.
* :ref:`detail` enables a mode where all tracks are listed in the importer UI,
  as opposed to only changed tracks.
* The ``--flat`` option to the ``beet import`` command treats an entire
  directory tree of music files as a single album. This can help in situations
  where a multi-disc album is split across multiple directories.
* :doc:`/plugins/importfeeds`: An option was added to use absolute, rather
  than relative, paths. Thanks to Lucas Duailibe.

Other stuff:

* A new :doc:`/plugins/mbsync` provides a command that looks up each item and
  track in MusicBrainz and updates your library to reflect it. This can help
  you easily correct errors that have been fixed in the MB database. Thanks to
  Jakob Schnitzer.
* :doc:`/plugins/fuzzy`: The ``fuzzy`` command was removed and replaced with a
  new query type. To perform fuzzy searches, use the ``~`` prefix with
  :ref:`list-cmd` or other commands. Thanks to Philippe Mongeau.
* As part of the above, plugins can now extend the query syntax and new kinds
  of matching capabilities to beets. See :ref:`extend-query`. Thanks again to
  Philippe Mongeau.
* :doc:`/plugins/convert`: A new ``--keep-new`` option lets you store
  transcoded files in your library while backing up the originals (instead of
  vice-versa). Thanks to Lucas Duailibe.
* :doc:`/plugins/convert`: Also, a new ``auto`` config option will transcode
  audio files automatically during import. Thanks again to Lucas Duailibe.
* :doc:`/plugins/chroma`: A new ``fingerprint`` command lets you generate and
  store fingerprints for items that don't yet have them. One more round of
  applause for Lucas Duailibe.
* ``echonest_tempo``: API errors now issue a warning instead of
  exiting with an exception. We also avoid an error when track metadata
  contains newlines.
* When the importer encounters an error (insufficient permissions, for
  example) when walking a directory tree, it now logs an error instead of
  crashing.
* In path formats, null database values now expand to the empty string instead
  of the string "None".
* Add "System Volume Information" (an internal directory found on some
  Windows filesystems) to the default ignore list.
* Fix a crash when ReplayGain values were set to null.
* Fix a crash when iTunes Sound Check tags contained invalid data.
* Fix an error when the configuration file (``config.yaml``) is completely
  empty.
* Fix an error introduced in 1.1b1 when importing using timid mode. Thanks to
  Sam Doshi.
* :doc:`/plugins/convert`: Fix a bug when creating files with Unicode
  pathnames.
* Fix a spurious warning from the Unidecode module when matching albums that
  are missing all metadata.
* Fix Unicode errors when a directory or file doesn't exist when invoking the
  import command. Thanks to Lucas Duailibe.
* :doc:`/plugins/mbcollection`: Show friendly, human-readable errors when
  MusicBrainz exceptions occur.
* ``echonest_tempo``: Catch socket errors that are not handled by
  the Echo Nest library.
* :doc:`/plugins/chroma`: Catch Acoustid Web service errors when submitting
  fingerprints.

1.1b2 (February 16, 2013)
-------------------------

The second beta of beets 1.1 uses the fancy new configuration infrastructure to
add many, many new config options. The import process is more flexible;
filenames can be customized in more detail; and more. This release also
supports Windows Media (ASF) files and iTunes Sound Check volume normalization.

This version introduces one **change to the default behavior** that you should
be aware of. Previously, when importing new albums matched in MusicBrainz, the
date fields (``year``, ``month``, and ``day``) would be set to the release date
of the *original* version of the album, as opposed to the specific date of the
release selected. Now, these fields reflect the specific release and
``original_year``, etc., reflect the earlier release date. If you want the old
behavior, just set :ref:`original_date` to true in your config file.

New configuration options:

* :ref:`default_action` lets you determine the default (just-hit-return) option
  is when considering a candidate.
* :ref:`none_rec_action` lets you skip the prompt, and automatically choose an
  action, when there is no good candidate. Thanks to Tai Lee.
* :ref:`max_rec` lets you define a maximum recommendation for albums with
  missing/extra tracks or differing track lengths/numbers. Thanks again to Tai
  Lee.
* :ref:`original_date` determines whether, when importing new albums, the
  ``year``, ``month``, and ``day`` fields should reflect the specific (e.g.,
  reissue) release date or the original release date. Note that the original
  release date is always available as ``original_year``, etc.
* :ref:`clutter` controls which files should be ignored when cleaning up empty
  directories. Thanks to Steinþór Pálsson.
* :doc:`/plugins/lastgenre`: A new configuration option lets you choose to
  retrieve artist-level tags as genres instead of album- or track-level tags.
  Thanks to Peter Fern and Peter Schnebel.
* :ref:`max_filename_length` controls truncation of long filenames. Also, beets
  now tries to determine the filesystem's maximum length automatically if you
  leave this option unset.
* :doc:`/plugins/fetchart`: The ``remote_priority`` option searches remote
  (Web) art sources even when local art is present.
* You can now customize the character substituted for path separators (e.g., /)
  in filenames via ``path_sep_replace``. The default is an underscore. Use this
  setting with caution.

Other new stuff:

* Support for Windows Media/ASF audio files. Thanks to Dave Hayes.
* New :doc:`/plugins/smartplaylist`: generate and maintain m3u playlist files
  based on beets queries. Thanks to Dang Mai Hai.
* ReplayGain tags on MPEG-4/AAC files are now supported. And, even more
  astonishingly, ReplayGain values in MP3 and AAC files are now compatible with
  `iTunes Sound Check`_. Thanks to Dave Hayes.
* Track titles in the importer UI's difference display are now either aligned
  vertically or broken across two lines for readability. Thanks to Tai Lee.
* Albums and items have new fields reflecting the *original* release date
  (``original_year``, ``original_month``, and ``original_day``). Previously,
  when tagging from MusicBrainz, *only* the original date was stored; now, the
  old fields refer to the *specific* release date (e.g., when the album was
  reissued).
* Some changes to the way candidates are recommended for selection, thanks to
  Tai Lee:

  * According to the new :ref:`max_rec` configuration option, partial album
    matches are downgraded to a "low" recommendation by default.
  * When a match isn't great but is either better than all the others or the
    only match, it is given a "low" (rather than "medium") recommendation.
  * There is no prompt default (i.e., input is required) when matches are
    bad: "low" or "none" recommendations or when choosing a candidate
    other than the first.

* The importer's heuristic for coalescing the directories in a multi-disc album
  has been improved. It can now detect when two directories alongside each
  other share a similar prefix but a different number (e.g., "Album Disc 1" and
  "Album Disc 2") even when they are not alone in a common parent directory.
  Thanks once again to Tai Lee.
* Album listings in the importer UI now show the release medium (CD, Vinyl,
  3xCD, etc.) as well as the disambiguation string. Thanks to Peter Schnebel.
* :doc:`/plugins/lastgenre`: The plugin can now get different genres for
  individual tracks on an album. Thanks to Peter Schnebel.
* When getting data from MusicBrainz, the album disambiguation string
  (``albumdisambig``) now reflects both the release and the release group.
* :doc:`/plugins/mpdupdate`: Sends an update message whenever *anything* in the
  database changes---not just when importing. Thanks to Dang Mai Hai.
* When the importer UI shows a difference in track numbers or durations, they
  are now colorized based on the *suffixes* that differ. For example, when
  showing the difference between 2:01 and 2:09, only the last digit will be
  highlighted.
* The importer UI no longer shows a change when the track length difference is
  less than 10 seconds. (This threshold was previously 2 seconds.)
* Two new plugin events were added: *database_change* and *cli_exit*. Thanks
  again to Dang Mai Hai.
* Plugins are now loaded in the order they appear in the config file. Thanks to
  Dang Mai Hai.
* :doc:`/plugins/bpd`: Browse by album artist and album artist sort name.
  Thanks to Steinþór Pálsson.
* ``echonest_tempo``: Don't attempt a lookup when the artist or
  track title is missing.
* Fix an error when migrating the ``.beetsstate`` file on Windows.
* A nicer error message is now given when the configuration file contains tabs.
  (YAML doesn't like tabs.)
* Fix the ``-l`` (log path) command-line option for the ``import`` command.

.. _iTunes Sound Check: https://support.apple.com/kb/HT2425

1.1b1 (January 29, 2013)
------------------------

This release entirely revamps beets' configuration system. The configuration
file is now a `YAML`_ document and is located, along with other support files,
in a common directory (e.g., ``~/.config/beets`` on Unix-like systems).

.. _YAML: https://en.wikipedia.org/wiki/YAML

* Renamed plugins: The ``rdm`` plugin has been renamed to ``random`` and
  ``fuzzy_search`` has been renamed to ``fuzzy``.
* Renamed config options: Many plugins have a flag dictating whether their
  action runs at import time. This option had many names (``autofetch``,
  ``autoembed``, etc.) but is now consistently called ``auto``.
* Reorganized import config options: The various ``import_*`` options are now
  organized under an ``import:`` heading and their prefixes have been removed.
* New default file locations: The default filename of the library database is
  now ``library.db`` in the same directory as the config file, as opposed to
  ``~/.beetsmusic.blb`` previously. Similarly, the runtime state file is now
  called ``state.pickle`` in the same directory instead of ``~/.beetsstate``.

It also adds some new features:

* :doc:`/plugins/inline`: Inline definitions can now contain statements or
  blocks in addition to just expressions. Thanks to Florent Thoumie.
* Add a configuration option, :ref:`terminal_encoding`, controlling the text
  encoding used to print messages to standard output.
* The MusicBrainz hostname (and rate limiting) are now configurable. See
  :ref:`musicbrainz-config`.
* You can now configure the similarity thresholds used to determine when the
  autotagger automatically accepts a metadata match. See :ref:`match-config`.
* :doc:`/plugins/importfeeds`: Added a new configuration option that controls
  the base for relative paths used in m3u files. Thanks to Philippe Mongeau.

1.0.0 (January 29, 2013)
------------------------

After fifteen betas and two release candidates, beets has finally hit
one-point-oh. Congratulations to everybody involved. This version of beets will
remain stable and receive only bug fixes from here on out. New development is
ongoing in the betas of version 1.1.

* :doc:`/plugins/scrub`: Fix an incompatibility with Python 2.6.
* :doc:`/plugins/lyrics`: Fix an issue that failed to find lyrics when metadata
  contained "real" apostrophes.
* :doc:`/plugins/replaygain`: On Windows, emit a warning instead of
  crashing when analyzing non-ASCII filenames.
* Silence a spurious warning from version 0.04.12 of the Unidecode module.

1.0rc2 (December 31, 2012)
--------------------------

This second release candidate follows quickly after rc1 and fixes a few small
bugs found since that release. There were a couple of regressions and some bugs
in a newly added plugin.

* ``echonest_tempo``: If the Echo Nest API limit is exceeded or a
  communication error occurs, the plugin now waits and tries again instead of
  crashing. Thanks to Zach Denton.
* :doc:`/plugins/fetchart`: Fix a regression that caused crashes when art was
  not available from some sources.
* Fix a regression on Windows that caused all relative paths to be "not found".

1.0rc1 (December 17, 2012)
--------------------------

The first release candidate for beets 1.0 includes a deluge of new features
contributed by beets users. The vast majority of the credit for this release
goes to the growing and vibrant beets community. A million thanks to everybody
who contributed to this release.

There are new plugins for transcoding music, fuzzy searches, tempo collection,
and fiddling with metadata. The ReplayGain plugin has been rebuilt from
scratch. Album art images can now be resized automatically. Many other smaller
refinements make things "just work" as smoothly as possible.

With this release candidate, beets 1.0 is feature-complete. We'll be fixing
bugs on the road to 1.0 but no new features will be added. Concurrently, work
begins today on features for version 1.1.

* New plugin: :doc:`/plugins/convert` **transcodes** music and embeds album art
  while copying to a separate directory. Thanks to Jakob Schnitzer and Andrew G.
  Dunn.
* New plugin: :doc:`/plugins/fuzzy` lets you find albums and tracks
  using **fuzzy string matching** so you don't have to type (or even remember)
  their exact names. Thanks to Philippe Mongeau.
* New plugin: ``echonest_tempo`` fetches **tempo** (BPM) information
  from `The Echo Nest`_. Thanks to David Brenner.
* New plugin: :doc:`/plugins/the` adds a template function that helps format
  text for nicely-sorted directory listings. Thanks to Blemjhoo Tezoulbr.
* New plugin: :doc:`/plugins/zero` **filters out undesirable fields** before
  they are written to your tags. Thanks again to Blemjhoo Tezoulbr.
* New plugin: :doc:`/plugins/ihate` automatically skips (or warns you about)
  importing albums that match certain criteria. Thanks once again to Blemjhoo
  Tezoulbr.
* :doc:`/plugins/replaygain`: This plugin has been completely overhauled to use
  the `mp3gain`_ or `aacgain`_ command-line tools instead of the failure-prone
  Gstreamer ReplayGain implementation. Thanks to Fabrice Laporte.
* :doc:`/plugins/fetchart` and :doc:`/plugins/embedart`: Both plugins can now
  **resize album art** to avoid excessively large images. Use the ``maxwidth``
  config option with either plugin. Thanks to Fabrice Laporte.
* :doc:`/plugins/scrub`: Scrubbing now removes *all* types of tags from a file
  rather than just one. For example, if your FLAC file has both ordinary FLAC
  tags and ID3 tags, the ID3 tags are now also removed.
* :ref:`stats-cmd` command: New ``--exact`` switch to make the file size
  calculation more accurate (thanks to Jakob Schnitzer).
* :ref:`list-cmd` command: Templates given with ``-f`` can now show items' and
  albums' paths (using ``$path``).
* The output of the :ref:`update-cmd`, :ref:`remove-cmd`, and :ref:`modify-cmd`
  commands now respects the :ref:`list_format_album` and
  :ref:`list_format_item` config options. Thanks to Mike Kazantsev.
* The :ref:`art-filename` option can now be a template rather than a simple
  string. Thanks to Jarrod Beardwood.
* Fix album queries for ``artpath`` and other non-item fields.
* Null values in the database can now be matched with the empty-string regular
  expression, ``^$``.
* Queries now correctly match non-string values in path format predicates.
* When autotagging a various-artists album, the album artist field is now
  used instead of the majority track artist.
* :doc:`/plugins/lastgenre`: Use the albums' existing genre tags if they pass
  the whitelist (thanks to Fabrice Laporte).
* :doc:`/plugins/lastgenre`: Add a ``lastgenre`` command for fetching genres
  post facto (thanks to Jakob Schnitzer).
* :doc:`/plugins/fetchart`: Local image filenames are now used in alphabetical
  order.
* :doc:`/plugins/fetchart`: Fix a bug where cover art filenames could lack
  a ``.jpg`` extension.
* :doc:`/plugins/lyrics`: Fix an exception with non-ASCII lyrics.
* :doc:`/plugins/web`: The API now reports file sizes (for use with the
  `Tomahawk resolver`_).
* :doc:`/plugins/web`: Files now download with a reasonable filename rather
  than just being called "file" (thanks to Zach Denton).
* :doc:`/plugins/importfeeds`: Fix error in symlink mode with non-ASCII
  filenames.
* :doc:`/plugins/mbcollection`: Fix an error when submitting a large number of
  releases (we now submit only 200 releases at a time instead of 350). Thanks
  to Jonathan Towne.
* :doc:`/plugins/embedart`: Made the method for embedding art into FLAC files
  `standard
  <https://wiki.xiph.org/VorbisComment#METADATA_BLOCK_PICTURE>`_-compliant.
  Thanks to Daniele Sluijters.
* Add the track mapping dictionary to the ``album_distance`` plugin function.
* When an exception is raised while reading a file, the path of the file in
  question is now logged (thanks to Mike Kazantsev).
* Truncate long filenames based on their *bytes* rather than their Unicode
  *characters*, fixing situations where encoded names could be too long.
* Filename truncation now incorporates the length of the extension.
* Fix an assertion failure when the MusicBrainz main database and search server
  disagree.
* Fix a bug that caused the :doc:`/plugins/lastgenre` and other plugins not to
  modify files' tags even when they successfully change the database.
* Fix a VFS bug leading to a crash in the :doc:`/plugins/bpd` when files had
  non-ASCII extensions.
* Fix for changing date fields (like "year") with the :ref:`modify-cmd`
  command.
* Fix a crash when input is read from a pipe without a specified encoding.
* Fix some problem with identifying files on Windows with Unicode directory
  names in their path.
* Fix a crash when Unicode queries were used with ``import -L`` re-imports.
* Fix an error when fingerprinting files with Unicode filenames on Windows.
* Warn instead of crashing when importing a specific file in singleton mode.
* Add human-readable error messages when writing files' tags fails or when a
  directory can't be created.
* Changed plugin loading so that modules can be imported without
  unintentionally loading the plugins they contain.

.. _The Echo Nest: https://web.archive.org/web/20180329103558/http://the.echonest.com/
.. _Tomahawk resolver: https://beets.io/blog/tomahawk-resolver.html
.. _mp3gain: http://mp3gain.sourceforge.net/download.php
.. _aacgain: https://aacgain.altosdesign.com

1.0b15 (July 26, 2012)
----------------------

The fifteenth (!) beta of beets is compendium of small fixes and features, most
of which represent long-standing requests. The improvements include matching
albums with extra tracks, per-disc track numbering in multi-disc albums, an
overhaul of the album art downloader, and robustness enhancements that should
keep beets running even when things go wrong. All these smaller changes should
help us focus on some larger changes coming before 1.0.

Please note that this release contains one backwards-incompatible change: album
art fetching, which was previously baked into the import workflow, is now
encapsulated in a plugin (the :doc:`/plugins/fetchart`). If you want to continue
fetching cover art for your music, enable this plugin after upgrading to beets
1.0b15.

* The autotagger can now find matches for albums when you have **extra tracks**
  on your filesystem that aren't present in the MusicBrainz catalog. Previously,
  if you tried to match album with 15 audio files but the MusicBrainz entry had
  only 14 tracks, beets would ignore this match. Now, beets will show you
  matches even when they are "too short" and indicate which tracks from your
  disk are unmatched.
* Tracks on multi-disc albums can now be **numbered per-disc** instead of
  per-album via the :ref:`per_disc_numbering` config option.
* The default output format for the ``beet list`` command is now configurable
  via the :ref:`list_format_item` and :ref:`list_format_album` config options.
  Thanks to Fabrice Laporte.
* Album **cover art fetching** is now encapsulated in the
  :doc:`/plugins/fetchart`. Be sure to enable this plugin if you're using this
  functionality. As a result of this new organization, the new plugin has gained
  a few new features:

  * "As-is" and non-autotagged imports can now have album art imported from
    the local filesystem (although Web repositories are still not searched in
    these cases).
  * A new command, ``beet fetchart``, allows you to download album art
    post-import. If you only want to fetch art manually, not automatically
    during import, set the new plugin's ``autofetch`` option to ``no``.
  * New album art sources have been added.

* Errors when communicating with MusicBrainz now log an error message instead of
  halting the importer.
* Similarly, filesystem manipulation errors now print helpful error messages
  instead of a messy traceback. They still interrupt beets, but they should now
  be easier for users to understand. Tracebacks are still available in verbose
  mode.
* New metadata fields for `artist credits`_: ``artist_credit`` and
  ``albumartist_credit`` can now contain release- and recording-specific
  variations of the artist's name. See :ref:`itemfields`.
* Revamped the way beets handles concurrent database access to avoid
  nondeterministic SQLite-related crashes when using the multithreaded importer.
  On systems where SQLite was compiled without ``usleep(3)`` support,
  multithreaded database access could cause an internal error (with the message
  "database is locked"). This release synchronizes access to the database to
  avoid internal SQLite contention, which should avoid this error.
* Plugins can now add parallel stages to the import pipeline. See
  :ref:`writing-plugins`.
* Beets now prints out an error when you use an unrecognized field name in a
  query: for example, when running ``beet ls -a artist:foo`` (because ``artist``
  is an item-level field).
* New plugin events:

  * ``import_task_choice`` is called after an import task has an action
    assigned.
  * ``import_task_files`` is called after a task's file manipulation has
    finished (copying or moving files, writing metadata tags).
  * ``library_opened`` is called when beets starts up and opens the library
    database.

* :doc:`/plugins/lastgenre`: Fixed a problem where path formats containing
  ``$genre`` would use the old genre instead of the newly discovered one.
* Fix a crash when moving files to a Samba share.
* :doc:`/plugins/mpdupdate`: Fix TypeError crash (thanks to Philippe Mongeau).
* When re-importing files with ``import_copy`` enabled, only files inside the
  library directory are moved. Files outside the library directory are still
  copied. This solves a problem (introduced in 1.0b14) where beets could crash
  after adding files to the library but before finishing copying them; during
  the next import, the (external) files would be moved instead of copied.
* Artist sort names are now populated correctly for multi-artist tracks and
  releases. (Previously, they only reflected the first artist.)
* When previewing changes during import, differences in track duration are now
  shown as "2:50 vs. 3:10" rather than separated with ``->`` like track numbers.
  This should clarify that beets isn't doing anything to modify lengths.
* Fix a problem with query-based path format matching where a field-qualified
  pattern, like ``albumtype_soundtrack``, would match everything.
* :doc:`/plugins/chroma`: Fix matching with ambiguous Acoustids. Some Acoustids
  are identified with multiple recordings; beets now considers any associated
  recording a valid match. This should reduce some cases of errant track
  reordering when using chroma.
* Fix the ID3 tag name for the catalog number field.
* :doc:`/plugins/chroma`: Fix occasional crash at end of fingerprint submission
  and give more context to "failed fingerprint generation" errors.
* Interactive prompts are sent to stdout instead of stderr.
* :doc:`/plugins/embedart`: Fix crash when audio files are unreadable.
* :doc:`/plugins/bpd`: Fix crash when sockets disconnect (thanks to Matteo
  Mecucci).
* Fix an assertion failure while importing with moving enabled when the file was
  already at its destination.
* Fix Unicode values in the ``replace`` config option (thanks to Jakob Borg).
* Use a nicer error message when input is requested but stdin is closed.
* Fix errors on Windows for certain Unicode characters that can't be represented
  in the MBCS encoding. This required a change to the way that paths are
  represented in the database on Windows; if you find that beets' paths are out
  of sync with your filesystem with this release, delete and recreate your
  database with ``beet import -AWC /path/to/music``.
* Fix ``import`` with relative path arguments on Windows.

.. _artist credits: https://wiki.musicbrainz.org/Artist_Credit

1.0b14 (May 12, 2012)
---------------------

The centerpiece of this beets release is the graceful handling of
similarly-named albums. It's now possible to import two albums with the same
artist and title and to keep them from conflicting in the filesystem. Many other
awesome new features were contributed by the beets community, including regular
expression queries, artist sort names, moving files on import. There are three
new plugins: random song/album selection; MusicBrainz "collection" integration;
and a plugin for interoperability with other music library systems.

A million thanks to the (growing) beets community for making this a huge
release.

* The importer now gives you **choices when duplicates are detected**.
  Previously, when beets found an existing album or item in your library
  matching the metadata on a newly-imported one, it would just skip the new
  music to avoid introducing duplicates into your library. Now, you have three
  choices: skip the new music (the previous behavior), keep both, or remove the
  old music. See the :ref:`guide-duplicates` section in the autotagging guide
  for details.
* Beets can now avoid storing identically-named albums in the same directory.
  The new ``%aunique{}`` template function, which is included in the default
  path formats, ensures that Crystal Castles' albums will be placed into
  different directories. See :ref:`aunique` for details.
* Beets queries can now use **regular expressions**. Use an additional ``:`` in
  your query to enable regex matching. See :ref:`regex` for the full details.
  Thanks to Matteo Mecucci.
* Artist **sort names** are now fetched from MusicBrainz. There are two new data
  fields, ``artist_sort`` and ``albumartist_sort``, that contain sortable artist
  names like "Beatles, The". These fields are also used to sort albums and items
  when using the ``list`` command. Thanks to Paul Provost.
* Many other **new metadata fields** were added, including ASIN, label catalog
  number, disc title, encoder, and MusicBrainz release group ID. For a full list
  of fields, see :ref:`itemfields`.
* :doc:`/plugins/chroma`: A new command, ``beet submit``, will **submit
  fingerprints** to the Acoustid database. Submitting your library helps
  increase the coverage and accuracy of Acoustid fingerprinting. The Chromaprint
  fingerprint and Acoustid ID are also now stored for all fingerprinted tracks.
  This version of beets *requires* at least version 0.6 of `pyacoustid`_ for
  fingerprinting to work.
* The importer can now **move files**. Previously, beets could only copy files
  and delete the originals, which is inefficient if the source and destination
  are on the same filesystem. Use the ``import_move`` configuration option and
  see :doc:`/reference/config` for more details. Thanks to Domen Kožar.
* New :doc:`/plugins/random`: Randomly select albums and tracks from your library.
  Thanks to Philippe Mongeau.
* The :doc:`/plugins/mbcollection` by Jeffrey Aylesworth was added to the core
  beets distribution.
* New :doc:`/plugins/importfeeds`: Catalog imported files in ``m3u`` playlist
  files or as symlinks for easy importing to other systems. Thanks to Fabrice
  Laporte.
* The ``-f`` (output format) option to the ``beet list`` command can now contain
  template functions as well as field references. Thanks to Steve Dougherty.
* A new command ``beet fields`` displays the available metadata fields (thanks
  to Matteo Mecucci).
* The ``import`` command now has a ``--noincremental`` or ``-I`` flag to disable
  incremental imports (thanks to Matteo Mecucci).
* When the autotagger fails to find a match, it now displays the number of
  tracks on the album (to help you guess what might be going wrong) and a link
  to the FAQ.
* The default filename character substitutions were changed to be more
  conservative. The Windows "reserved characters" are substituted by default
  even on Unix platforms (this causes less surprise when using Samba shares to
  store music). To customize your character substitutions, see :ref:`the replace
  config option <replace>`.
* :doc:`/plugins/lastgenre`: Added a "fallback" option when no suitable genre
  can be found (thanks to Fabrice Laporte).
* :doc:`/plugins/rewrite`: Unicode rewriting rules are now allowed (thanks to
  Nicolas Dietrich).
* Filename collisions are now avoided when moving album art.
* :doc:`/plugins/bpd`: Print messages to show when directory tree is being
  constructed.
* :doc:`/plugins/bpd`: Use Gstreamer's ``playbin2`` element instead of the
  deprecated ``playbin``.
* :doc:`/plugins/bpd`: Random and repeat modes are now supported (thanks to
  Matteo Mecucci).
* :doc:`/plugins/bpd`: Listings are now sorted (thanks once again to Matteo
  Mecucci).
* Filenames are normalized with Unicode Normal Form D (NFD) on Mac OS X and NFC
  on all other platforms.
* Significant internal restructuring to avoid SQLite locking errors. As part of
  these changes, the not-very-useful "save" plugin event has been removed.

.. _pyacoustid: https://github.com/beetbox/pyacoustid

1.0b13 (March 16, 2012)
-----------------------

Beets 1.0b13 consists of a plethora of small but important fixes and
refinements. A lyrics plugin is now included with beets; new audio properties
are catalogged; the ``list`` command has been made more powerful; the autotagger
is more tolerant of different tagging styles; and importing with original file
deletion now cleans up after itself more thoroughly. Many, many bugs—including
several crashers—were fixed. This release lays the foundation for more features
to come in the next couple of releases.

* The :doc:`/plugins/lyrics`, originally by `Peter Brunner`_, is revamped and
  included with beets, making it easy to fetch **song lyrics**.
* Items now expose their audio **sample rate**, number of **channels**, and
  **bits per sample** (bitdepth). See :doc:`/reference/pathformat` for a list of
  all available audio properties. Thanks to Andrew Dunn.
* The ``beet list`` command now accepts a "format" argument that lets you **show
  specific information about each album or track**. For example, run ``beet ls
  -af '$album: $tracktotal' beatles`` to see how long each Beatles album is.
  Thanks to Philippe Mongeau.
* The autotagger now tolerates tracks on multi-disc albums that are numbered
  per-disc. For example, if track 24 on a release is the first track on the
  second disc, then it is not penalized for having its track number set to 1
  instead of 24.
* The autotagger sets the disc number and disc total fields on autotagged
  albums.
* The autotagger now also tolerates tracks whose track artists tags are set
  to "Various Artists".
* Terminal colors are now supported on Windows via `Colorama`_ (thanks to Karl).
* When previewing metadata differences, the importer now shows discrepancies in
  track length.
* Importing with ``import_delete`` enabled now cleans up empty directories that
  contained deleting imported music files.
* Similarly, ``import_delete`` now causes original album art imported from the
  disk to be deleted.
* Plugin-supplied template values, such as those created by ``rewrite``, are now
  properly sanitized (for example, ``AC/DC`` properly becomes ``AC_DC``).
* Filename extensions are now always lower-cased when copying and moving files.
* The ``inline`` plugin now prints a more comprehensible error when exceptions
  occur in Python snippets.
* The ``replace`` configuration option can now remove characters entirely (in
  addition to replacing them) if the special string ``<strip>`` is specified as
  the replacement.
* New plugin API: plugins can now add fields to the MediaFile tag abstraction
  layer. See :ref:`writing-plugins`.
* A reasonable error message is now shown when the import log file cannot be
  opened.
* The import log file is now flushed and closed properly so that it can be used
  to monitor import progress, even when the import crashes.
* Duplicate track matches are no longer shown when autotagging singletons.
* The ``chroma`` plugin now logs errors when fingerprinting fails.
* The ``lastgenre`` plugin suppresses more errors when dealing with the Last.fm
  API.
* Fix a bug in the ``rewrite`` plugin that broke the use of multiple rules for
  a single field.
* Fix a crash with non-ASCII characters in bytestring metadata fields (e.g.,
  MusicBrainz IDs).
* Fix another crash with non-ASCII characters in the configuration paths.
* Fix a divide-by-zero crash on zero-length audio files.
* Fix a crash in the ``chroma`` plugin when the Acoustid database had no
  recording associated with a fingerprint.
* Fix a crash when an autotagging with an artist or album containing "AND" or
  "OR" (upper case).
* Fix an error in the ``rewrite`` and ``inline`` plugins when the corresponding
  config sections did not exist.
* Fix bitrate estimation for AAC files whose headers are missing the relevant
  data.
* Fix the ``list`` command in BPD (thanks to Simon Chopin).

.. _Colorama: https://pypi.python.org/pypi/colorama

1.0b12 (January 16, 2012)
-------------------------

This release focuses on making beets' path formatting vastly more powerful. It
adds a function syntax for transforming text. Via a new plugin, arbitrary Python
code can also be used to define new path format fields. Each path format
template can now be activated conditionally based on a query. Character set
substitutions are also now configurable.

In addition, beets avoids problematic filename conflicts by appending numbers to
filenames that would otherwise conflict. Three new plugins (``inline``,
``scrub``, and ``rewrite``) are included in this release.

* **Functions in path formats** provide a simple way to write complex file
  naming rules: for example, ``%upper{%left{$artist,1}}`` will insert the
  capitalized first letter of the track's artist. For more details, see
  :doc:`/reference/pathformat`. If you're interested in adding your own template
  functions via a plugin, see :ref:`writing-plugins`.
* Plugins can also now define new path *fields* in addition to functions.
* The new :doc:`/plugins/inline` lets you **use Python expressions to customize
  path formats** by defining new fields in the config file.
* The configuration can **condition path formats based on queries**. That is,
  you can write a path format that is only used if an item matches a given
  query. (This supersedes the earlier functionality that only allowed
  conditioning on album type; if you used this feature in a previous version,
  you will need to replace, for example, ``soundtrack:`` with
  ``albumtype_soundtrack:``.) See :ref:`path-format-config`.
* **Filename substitutions are now configurable** via the ``replace`` config
  value. You can choose which characters you think should be allowed in your
  directory and music file names.  See :doc:`/reference/config`.
* Beets now ensures that files have **unique filenames** by appending a number
  to any filename that would otherwise conflict with an existing file.
* The new :doc:`/plugins/scrub` can remove extraneous metadata either manually
  or automatically.
* The new :doc:`/plugins/rewrite` can canonicalize names for path formats.
* The autotagging heuristics have been tweaked in situations where the
  MusicBrainz database did not contain track lengths. Previously, beets
  penalized matches where this was the case, leading to situations where
  seemingly good matches would have poor similarity. This penalty has been
  removed.
* Fix an incompatibility in BPD with libmpc (the library that powers mpc and
  ncmpc).
* Fix a crash when importing a partial match whose first track was missing.
* The ``lastgenre`` plugin now correctly writes discovered genres to imported
  files (when tag-writing is enabled).
* Add a message when skipping directories during an incremental import.
* The default ignore settings now ignore all files beginning with a dot.
* Date values in path formats (``$year``, ``$month``, and ``$day``) are now
  appropriately zero-padded.
* Removed the ``--path-format`` global flag for ``beet``.
* Removed the ``lastid`` plugin, which was deprecated in the previous version.

1.0b11 (December 12, 2011)
--------------------------

This version of beets focuses on transitioning the autotagger to the new version
of the MusicBrainz database (called NGS). This transition brings with it a
number of long-overdue improvements: most notably, predictable behavior when
tagging multi-disc albums and integration with the new `Acoustid`_ acoustic
fingerprinting technology.

The importer can also now tag *incomplete* albums when you're missing a few
tracks from a given release. Two other new plugins are also included with this
release: one for assigning genres and another for ReplayGain analysis.

* Beets now communicates with MusicBrainz via the new `Next Generation Schema`_
  (NGS) service via `python-musicbrainzngs`_. The bindings are included with
  this version of beets, but a future version will make them an external
  dependency.
* The importer now detects **multi-disc albums** and tags them together. Using a
  heuristic based on the names of directories, certain structures are classified
  as multi-disc albums: for example, if a directory contains subdirectories
  labeled "disc 1" and "disc 2", these subdirectories will be coalesced into a
  single album for tagging.
* The new :doc:`/plugins/chroma` uses the `Acoustid`_ **open-source acoustic
  fingerprinting** service. This replaces the old ``lastid`` plugin, which used
  Last.fm fingerprinting and is now deprecated. Fingerprinting with this library
  should be faster and more reliable.
* The importer can now perform **partial matches**. This means that, if you're
  missing a few tracks from an album, beets can still tag the remaining tracks
  as a single album. (Thanks to `Simon Chopin`_.)
* The new :doc:`/plugins/lastgenre` automatically **assigns genres to imported
  albums** and items based on Last.fm tags and an internal whitelist. (Thanks to
  `KraYmer`_.)
* The :doc:`/plugins/replaygain`, written by `Peter Brunner`_, has been merged
  into the core beets distribution. Use it to analyze audio and **adjust
  playback levels** in ReplayGain-aware music players.
* Albums are now tagged with their *original* release date rather than the date
  of any reissue, remaster, "special edition", or the like.
* The config file and library databases are now given better names and locations
  on Windows. Namely, both files now reside in ``%APPDATA%``; the config file is
  named ``beetsconfig.ini`` and the database is called ``beetslibrary.blb``
  (neither has a leading dot as on Unix). For backwards compatibility, beets
  will check the old locations first.
* When entering an ID manually during tagging, beets now searches for anything
  that looks like an MBID in the entered string. This means that full
  MusicBrainz URLs now work as IDs at the prompt. (Thanks to derwin.)
* The importer now ignores certain "clutter" files like ``.AppleDouble``
  directories and ``._*`` files. The list of ignored patterns is configurable
  via the ``ignore`` setting; see :doc:`/reference/config`.
* The database now keeps track of files' modification times so that, during
  an ``update``, unmodified files can be skipped. (Thanks to Jos van der Til.)
* The album art fetcher now uses `albumart.org`_ as a fallback when the Amazon
  art downloader fails.
* A new ``timeout`` config value avoids database locking errors on slow systems.
* Fix a crash after using the "as Tracks" option during import.
* Fix a Unicode error when tagging items with missing titles.
* Fix a crash when the state file (``~/.beetsstate``) became emptied or
  corrupted.

.. _KraYmer: https://github.com/KraYmer
.. _Next Generation Schema: https://musicbrainz.org/doc/XML_Web_Service/Version_2
.. _python-musicbrainzngs: https://github.com/alastair/python-musicbrainzngs
.. _acoustid: https://acoustid.org/
.. _Peter Brunner: https://github.com/Lugoues
.. _Simon Chopin: https://github.com/laarmen
.. _albumart.org: https://www.albumart.org/

1.0b10 (September 22, 2011)
---------------------------

This version of beets focuses on making it easier to manage your metadata
*after* you've imported it. A bumper crop of new commands has been added: a
manual tag editor (``modify``), a tool to pick up out-of-band deletions and
modifications (``update``), and functionality for moving and copying files
around (``move``). Furthermore, the concept of "re-importing" is new: you can
choose to re-run beets' advanced autotagger on any files you already have in
your library if you change your mind after you finish the initial import.

As a couple of added bonuses, imports can now automatically skip
previously-imported directories (with the ``-i`` flag) and there's an
:doc:`experimental Web interface </plugins/web>` to beets in a new standard
plugin.

* A new ``beet modify`` command enables **manual, command-line-based
  modification** of music metadata. Pass it a query along with ``field=value``
  pairs that specify the changes you want to make.

* A new ``beet update`` command updates the database to reflect **changes in the
  on-disk metadata**. You can now use an external program to edit tags on files,
  remove files and directories, etc., and then run ``beet update`` to make sure
  your beets library is in sync. This will also rename files to reflect their
  new metadata.

* A new ``beet move`` command can **copy or move files** into your library
  directory or to another specified directory.

* When importing files that are already in the library database, the items are
  no longer duplicated---instead, the library is updated to reflect the new
  metadata. This way, the import command can be transparently used as a
  **re-import**.

* Relatedly, the ``-L`` flag to the "import" command makes it take a query as
  its argument instead of a list of directories. The matched albums (or items,
  depending on the ``-s`` flag) are then re-imported.

* A new flag ``-i`` to the import command runs **incremental imports**, keeping
  track of and skipping previously-imported directories. This has the effect of
  making repeated import commands pick up only newly-added directories. The
  ``import_incremental`` config option makes this the default.

* When pruning directories, "clutter" files such as ``.DS_Store`` and
  ``Thumbs.db`` are ignored (and removed with otherwise-empty directories).

* The :doc:`/plugins/web` encapsulates a simple **Web-based GUI for beets**. The
  current iteration can browse the library and play music in browsers that
  support HTML5 Audio.

* When moving items that are part of an album, the album art implicitly moves
  too.

* Files are no longer silently overwritten when moving and copying files.

* Handle exceptions thrown when running Mutagen.

* Fix a missing ``__future__`` import in ``embed art`` on Python 2.5.

* Fix ID3 and MPEG-4 tag names for the album-artist field.

* Fix Unicode encoding of album artist, album type, and label.

* Fix crash when "copying" an art file that's already in place.

1.0b9 (July 9, 2011)
--------------------

This release focuses on a large number of small fixes and improvements that turn
beets into a well-oiled, music-devouring machine. See the full release notes,
below, for a plethora of new features.

* **Queries can now contain whitespace.** Spaces passed as shell arguments are
  now preserved, so you can use your shell's escaping syntax (quotes or
  backslashes, for instance) to include spaces in queries. For example,
  typing``beet ls "the knife"`` or ``beet ls the\ knife``. Read more in
  :doc:`/reference/query`.

* Queries can **match items from the library by directory**. A ``path:`` prefix
  is optional; any query containing a path separator (/ on POSIX systems) is
  assumed to be a path query. Running ``beet ls path/to/music`` will show all
  the music in your library under the specified directory. The
  :doc:`/reference/query` reference again has more details.

* **Local album art** is now automatically discovered and copied from the
  imported directories when available.

* When choosing the "as-is" import album (or doing a non-autotagged import),
  **every album either has an "album artist" set or is marked as a compilation
  (Various Artists)**. The choice is made based on the homogeneity of the
  tracks' artists. This prevents compilations that are imported as-is from being
  scattered across many directories after they are imported.

* The release **label** for albums and tracks is now fetched from !MusicBrainz,
  written to files, and stored in the database.

* The "list" command now accepts a ``-p`` switch that causes it to **show
  paths** instead of titles. This makes the output of ``beet ls -p`` suitable
  for piping into another command such as `xargs`_.

* Release year and label are now shown in the candidate selection list to help
  disambiguate different releases of the same album.

* Prompts in the importer interface are now colorized for easy reading. The
  default option is always highlighted.

* The importer now provides the option to specify a MusicBrainz ID manually if
  the built-in searching isn't working for a particular album or track.

* ``$bitrate`` in path formats is now formatted as a human-readable kbps value
  instead of as a raw integer.

* The import logger has been improved for "always-on" use. First, it is now
  possible to specify a log file in .beetsconfig. Also, logs are now appended
  rather than overwritten and contain timestamps.

* Album art fetching and plugin events are each now run in separate pipeline
  stages during imports. This should bring additional performance when using
  album art plugins like embedart or beets-lyrics.

* Accents and other Unicode decorators on characters are now treated more fairly
  by the autotagger. For example, if you're missing the acute accent on the "e"
  in "café", that change won't be penalized.  This introduces a new dependency
  on the `unidecode`_ Python module.

* When tagging a track with no title set, the track's filename is now shown
  (instead of nothing at all).

* The bitrate of lossless files is now calculated from their file size (rather
  than being fixed at 0 or reflecting the uncompressed audio bitrate).

* Fixed a problem where duplicate albums or items imported at the same time
  would fail to be detected.

* BPD now uses a persistent "virtual filesystem" in order to fake a directory
  structure. This means that your path format settings are respected in BPD's
  browsing hierarchy. This may come at a performance cost, however. The virtual
  filesystem used by BPD is available for reuse by plugins (e.g., the FUSE
  plugin).

* Singleton imports (``beet import -s``) can now take individual files as
  arguments as well as directories.

* Fix Unicode queries given on the command line.

* Fix crasher in quiet singleton imports (``import -qs``).

* Fix crash when autotagging files with no metadata.

* Fix a rare deadlock when finishing the import pipeline.

* Fix an issue that was causing mpdupdate to run twice for every album.

* Fix a bug that caused release dates/years not to be fetched.

* Fix a crasher when setting MBIDs on MP3s file metadata.

* Fix a "broken pipe" error when piping beets' standard output.

* A better error message is given when the database file is unopenable.

* Suppress errors due to timeouts and bad responses from MusicBrainz.

* Fix a crash on album queries with item-only field names.

.. _xargs: https://en.wikipedia.org/wiki/xargs
.. _unidecode: https://pypi.python.org/pypi/Unidecode/0.04.1

1.0b8 (April 28, 2011)
----------------------

This release of beets brings two significant new features. First, beets now has
first-class support for "singleton" tracks. Previously, it was only really meant
to manage whole albums, but many of us have lots of non-album tracks to keep
track of alongside our collections of albums. So now beets makes it easy to tag,
catalog, and manipulate your individual tracks. Second, beets can now
(optionally) embed album art directly into file metadata rather than only
storing it in a "file on the side." Check out the :doc:`/plugins/embedart` for
that functionality.

* Better support for **singleton (non-album) tracks**. Whereas beets previously
  only really supported full albums, now it can also keep track of individual,
  off-album songs. The "singleton" path format can be used to customize where
  these tracks are stored. To import singleton tracks, provide the -s switch to
  the import command or, while doing a normal full-album import, choose the "as
  Tracks" (T) option to add singletons to your library.  To list only singleton
  or only album tracks, use the new ``singleton:`` query term: the query
  ``singleton:true`` matches only singleton tracks; ``singleton:false`` matches
  only album tracks. The ``lastid`` plugin has been extended to support
  matching individual items as well.

* The importer/autotagger system has been heavily refactored in this release.
  If anything breaks as a result, please get in touch or just file a bug.

* Support for **album art embedded in files**. A new :doc:`/plugins/embedart`
  implements this functionality. Enable the plugin to automatically embed
  downloaded album art into your music files' metadata. The plugin also provides
  the "embedart" and "extractart" commands for moving image files in and out of
  metadata. See the wiki for more details. (Thanks, daenney!)

* The "distance" number, which quantifies how different an album's current and
  proposed metadata are, is now displayed as "similarity" instead. This should
  be less noisy and confusing; you'll now see 99.5% instead of 0.00489323.

* A new "timid mode" in the importer asks the user every time, even when it
  makes a match with very high confidence. The ``-t`` flag on the command line
  and the ``import_timid`` config option control this mode. (Thanks to mdecker
  on GitHub!)

* The multithreaded importer should now abort (either by selecting aBort or by
  typing ^C) much more quickly. Previously, it would try to get a lot of work
  done before quitting; now it gives up as soon as it can.

* Added a new plugin event, ``album_imported``, which is called every time an
  album is added to the library. (Thanks, Lugoues!)

* A new plugin method, ``register_listener``, is an imperative alternative to
  the ``@listen`` decorator (Thanks again, Lugoues!)

* In path formats, ``$albumartist`` now falls back to ``$artist`` (as well as
  the other way around).

* The importer now prints "(unknown album)" when no tags are present.

* When autotagging, "and" is considered equal to "&".

* Fix some crashes when deleting files that don't exist.

* Fix adding individual tracks in BPD.

* Fix crash when ``~/.beetsconfig`` does not exist.

1.0b7 (April 5, 2011)
---------------------

Beta 7's focus is on better support for "various artists" releases. These albums
can be treated differently via the new ``[paths]`` config section and the
autotagger is better at handling them. It also includes a number of
oft-requested improvements to the ``beet`` command-line tool, including several
new configuration options and the ability to clean up empty directory subtrees.

* **"Various artists" releases** are handled much more gracefully. The
  autotagger now sets the ``comp`` flag on albums whenever the album is
  identified as a "various artists" release by !MusicBrainz. Also, there is now
  a distinction between the "album artist" and the "track artist", the latter of
  which is never "Various Artists" or other such bogus stand-in. *(Thanks to
  Jonathan for the bulk of the implementation work on this feature!)*

* The directory hierarchy can now be **customized based on release type**. In
  particular, the ``path_format`` setting in .beetsconfig has been replaced with
  a new ``[paths]`` section, which allows you to specify different path formats
  for normal and "compilation" (various artists) releases as well as for each
  album type (see below). The default path formats have been changed to use
  ``$albumartist`` instead of ``$artist``.

* A **new ``albumtype`` field** reflects the release type `as specified by
  MusicBrainz`_.

* When deleting files, beets now appropriately "prunes" the directory
  tree---empty directories are automatically cleaned up. *(Thanks to
  wlof on GitHub for this!)*

* The tagger's output now always shows the album directory that is currently
  being tagged. This should help in situations where files' current tags are
  missing or useless.

* The logging option (``-l``) to the ``import`` command now logs duplicate
  albums.

* A new ``import_resume`` configuration option can be used to disable the
  importer's resuming feature or force it to resume without asking. This option
  may be either ``yes``, ``no``, or ``ask``, with the obvious meanings. The
  ``-p`` and ``-P`` command-line flags override this setting and correspond to
  the "yes" and "no" settings.

* Resuming is automatically disabled when the importer is in quiet (``-q``)
  mode. Progress is still saved, however, and the ``-p`` flag (above) can be
  used to force resuming.

* The ``BEETSCONFIG`` environment variable can now be used to specify the
  location of the config file that is at ~/.beetsconfig by default.

* A new ``import_quiet_fallback`` config option specifies what should
  happen in quiet mode when there is no strong recommendation. The options are
  ``skip`` (the default) and "asis".

* When importing with the "delete" option and importing files that are already
  at their destination, files could be deleted (leaving zero copies afterward).
  This is fixed.

* The ``version`` command now lists all the loaded plugins.

* A new plugin, called ``info``, just prints out audio file metadata.

* Fix a bug where some files would be erroneously interpreted as MPEG-4 audio.

* Fix permission bits applied to album art files.

* Fix malformed !MusicBrainz queries caused by null characters.

* Fix a bug with old versions of the Monkey's Audio format.

* Fix a crash on broken symbolic links.

* Retry in more cases when !MusicBrainz servers are slow/overloaded.

* The old "albumify" plugin for upgrading databases was removed.

.. _as specified by MusicBrainz: https://wiki.musicbrainz.org/ReleaseType

1.0b6 (January 20, 2011)
------------------------

This version consists primarily of bug fixes and other small improvements. It's
in preparation for a more feature-ful release in beta 7. The most important
issue involves correct ordering of autotagged albums.

* **Quiet import:** a new "-q" command line switch for the import command
  suppresses all prompts for input; it pessimistically skips all albums that the
  importer is not completely confident about.

* Added support for the **WavPack** and **Musepack** formats. Unfortunately, due
  to a limitation in the Mutagen library (used by beets for metadata
  manipulation), Musepack SV8 is not yet supported. Here's the `upstream bug`_
  in question.

* BPD now uses a pure-Python socket library and no longer requires
  eventlet/greenlet (the latter of which is a C extension). For the curious, the
  socket library in question is called `Bluelet`_.

* Non-autotagged imports are now resumable (just like autotagged imports).

* Fix a terrible and long-standing bug where track orderings were never applied.
  This manifested when the tagger appeared to be applying a reasonable ordering
  to the tracks but, later, the database reflects a completely wrong association
  of track names to files. The order applied was always just alphabetical by
  filename, which is frequently but not always what you want.

* We now use Windows' "long filename" support. This API is fairly tricky,
  though, so some instability may still be present---please file a bug if you
  run into pathname weirdness on Windows. Also, filenames on Windows now never
  end in spaces.

* Fix crash in lastid when the artist name is not available.

* Fixed a spurious crash when ``LANG`` or a related environment variable is set
  to an invalid value (such as ``'UTF-8'`` on some installations of Mac OS X).

* Fixed an error when trying to copy a file that is already at its destination.

* When copying read-only files, the importer now tries to make the copy
  writable. (Previously, this would just crash the import.)

* Fixed an ``UnboundLocalError`` when no matches are found during autotag.

* Fixed a Unicode encoding error when entering special characters into the
  "manual search" prompt.

* Added `` beet version`` command that just shows the current release version.

.. _upstream bug: https://github.com/quodlibet/mutagen/issues/7
.. _Bluelet: https://github.com/sampsyo/bluelet

1.0b5 (September 28, 2010)
--------------------------

This version of beets focuses on increasing the accuracy of the autotagger. The
main addition is an included plugin that uses acoustic fingerprinting to match
based on the audio content (rather than existing metadata). Additional
heuristics were also added to the metadata-based tagger as well that should make
it more reliable. This release also greatly expands the capabilities of beets'
:doc:`plugin API </plugins/index>`. A host of other little features and fixes
are also rolled into this release.

* The ``lastid`` plugin adds Last.fm **acoustic fingerprinting
  support** to the autotagger. Similar to the PUIDs used by !MusicBrainz Picard,
  this system allows beets to recognize files that don't have any metadata at
  all. You'll need to install some dependencies for this plugin to work.

* To support the above, there's also a new system for **extending the autotagger
  via plugins**. Plugins can currently add components to the track and album
  distance functions as well as augment the MusicBrainz search. The new API is
  documented at :doc:`/plugins/index`.

* **String comparisons** in the autotagger have been augmented to act more
  intuitively. Previously, if your album had the title "Something (EP)" and it
  was officially called "Something", then beets would think this was a fairly
  significant change. It now checks for and appropriately reweights certain
  parts of each string. As another example, the title "The Great Album" is
  considered equal to "Great Album, The".

* New **event system for plugins** (thanks, Jeff!). Plugins can now get
  callbacks from beets when certain events occur in the core. Again, the API is
  documented in :doc:`/plugins/index`.

* The BPD plugin is now disabled by default. This greatly simplifies
  installation of the beets core, which is now 100% pure Python. To use BPD,
  though, you'll need to set ``plugins: bpd`` in your .beetsconfig.

* The ``import`` command can now remove original files when it copies items into
  your library. (This might be useful if you're low on disk space.) Set the
  ``import_delete`` option in your .beetsconfig to ``yes``.

* Importing without autotagging (``beet import -A``) now prints out album names
  as it imports them to indicate progress.

* The new :doc:`/plugins/mpdupdate` will automatically update your MPD server's
  index whenever your beets library changes.

* Efficiency tweak should reduce the number of !MusicBrainz queries per
  autotagged album.

* A new ``-v`` command line switch enables debugging output.

* Fixed bug that completely broke non-autotagged imports (``import -A``).

* Fixed bug that logged the wrong paths when using ``import -l``.

* Fixed autotagging for the creatively-named band `!!!`_.

* Fixed normalization of relative paths.

* Fixed escaping of ``/`` characters in paths on Windows.

.. _!!!: https://musicbrainz.org/artist/f26c72d3-e52c-467b-b651-679c73d8e1a7.html

1.0b4 (August 9, 2010)
----------------------

This thrilling new release of beets focuses on making the tagger more usable in
a variety of ways. First and foremost, it should now be much faster: the tagger
now uses a multithreaded algorithm by default (although, because the new tagger
is experimental, a single-threaded version is still available via a config
option). Second, the tagger output now uses a little bit of ANSI terminal
coloring to make changes stand out. This way, it should be faster to decide what
to do with a proposed match: the more red you see, the worse the match is.
Finally, the tagger can be safely interrupted (paused) and restarted later at
the same point. Just enter ``b`` for aBort at any prompt to stop the tagging
process and save its progress. (The progress-saving also works in the
unthinkable event that beets crashes while tagging.)

Among the under-the-hood changes in 1.0b4 is a major change to the way beets
handles paths (filenames). This should make the whole system more tolerant to
special characters in filenames, but it may break things (especially databases
created with older versions of beets). As always, let me know if you run into
weird problems with this release.

Finally, this release's ``setup.py`` should install a ``beet.exe`` startup stub
for Windows users. This should make running beets much easier: just type
``beet`` if you have your ``PATH`` environment variable set up correctly. The
:doc:`/guides/main` guide has some tips on installing beets on Windows.

Here's the detailed list of changes:

* **Parallel tagger.** The autotagger has been reimplemented to use multiple
  threads. This means that it can concurrently read files from disk, talk to the
  user, communicate with MusicBrainz, and write data back to disk. Not only does
  this make the tagger much faster because independent work may be performed in
  parallel, but it makes the tagging process much more pleasant for large
  imports. The user can let albums queue up in the background while making a
  decision rather than waiting for beets between each question it asks.  The
  parallel tagger is on by default but a sequential (single- threaded) version
  is still available by setting the ``threaded`` config value to ``no`` (because
  the parallel version is still quite experimental).

* **Colorized tagger output.** The autotagger interface now makes it a little
  easier to see what's going on at a glance by highlighting changes with
  terminal colors. This feature is on by default, but you can turn it off by
  setting ``color`` to ``no`` in your ``.beetsconfig`` (if, for example, your
  terminal doesn't understand colors and garbles the output).

* **Pause and resume imports.** The ``import`` command now keeps track of its
  progress, so if you're interrupted (beets crashes, you abort the process, an
  alien devours your motherboard, etc.), beets will try to resume from the point
  where you left off. The next time you run ``import`` on the same directory, it
  will ask if you want to resume. It accomplishes this by "fast-forwarding"
  through the albums in the directory until it encounters the last one it saw.
  (This means it might fail if that album can't be found.) Also, you can now
  abort the tagging process by entering ``b`` (for aBort) at any of the prompts.

* Overhauled methods for handling filesystem paths to allow filenames that have
  badly encoded special characters. These changes are pretty fragile, so please
  report any bugs involving ``UnicodeError`` or SQLite ``ProgrammingError``
  messages in this version.

* The destination paths (the library directory structure) now respect
  album-level metadata. This means that if you have an album in which two tracks
  have different album-level attributes (like year, for instance), they will
  still wind up in the same directory together.  (There's currently not a very
  smart method for picking the "correct" album-level metadata, but we'll fix
  that later.)

* Fixed a bug where the CLI would fail completely if the ``LANG`` environment
  variable was not set.

* Fixed removal of albums (``beet remove -a``): previously, the album record
  would stay around although the items were deleted.

* The setup script now makes a ``beet.exe`` startup stub on Windows; Windows
  users can now just type ``beet`` at the prompt to run beets.

* Fixed an occasional bug where Mutagen would complain that a tag was already
  present.

* Fixed a bug with reading invalid integers from ID3 tags.

* The tagger should now be a little more reluctant to reorder tracks that
  already have indices.

1.0b3 (July 22, 2010)
---------------------

This release features two major additions to the autotagger's functionality:
album art fetching and MusicBrainz ID tags. It also contains some important
under-the-hood improvements: a new plugin architecture is introduced
and the database schema is extended with explicit support for albums.

This release has one major backwards-incompatibility. Because of the new way
beets handles albums in the library, databases created with an old version of
beets might have trouble with operations that deal with albums (like the ``-a``
switch to ``beet list`` and ``beet remove``, as well as the file browser for
BPD). To "upgrade" an old database, you can use the included ``albumify`` plugin
(see the fourth bullet point below).

* **Album art.** The tagger now, by default, downloads album art from Amazon
  that is referenced in the MusicBrainz database. It places the album art
  alongside the audio files in a file called (for example) ``cover.jpg``. The
  ``import_art`` config option controls this behavior, as do the ``-r`` and
  ``-R`` options to the import command. You can set the name (minus extension)
  of the album art file with the ``art_filename`` config option. (See
  :doc:`/reference/config` for more information about how to configure the album
  art downloader.)

* **Support for MusicBrainz ID tags.** The autotagger now keeps track of the
  MusicBrainz track, album, and artist IDs it matched for each file. It also
  looks for album IDs in new files it's importing and uses those to look up data
  in MusicBrainz. Furthermore, track IDs are used as a component of the tagger's
  distance metric now. (This obviously lays the groundwork for a utility that
  can update tags if the MB database changes, but that's `for the future`_.)
  Tangentially, this change required the database code to support a lightweight
  form of migrations so that new columns could be added to old databases--this
  is a delicate feature, so it would be very wise to make a backup of your
  database before upgrading to this version.

* **Plugin architecture.** Add-on modules can now add new commands to the beets
  command-line interface. The ``bpd`` and ``dadd`` commands were removed from
  the beets core and turned into plugins; BPD is loaded by default. To load the
  non-default plugins, use the config options ``plugins`` (a space-separated
  list of plugin names) and ``pluginpath`` (a colon-separated list of
  directories to search beyond ``sys.path``). Plugins are just Python modules
  under the ``beetsplug`` namespace package containing subclasses of
  ``beets.plugins.BeetsPlugin``. See `the beetsplug directory`_ for examples or
  :doc:`/plugins/index` for instructions.

* As a consequence of adding album art, the database was significantly
  refactored to keep track of some information at an album (rather than item)
  granularity. Databases created with earlier versions of beets should work
  fine, but they won't have any "albums" in them--they'll just be a bag of
  items. This means that commands like ``beet ls -a`` and ``beet rm -a`` won't
  match anything. To "upgrade" your database, you can use the included
  ``albumify`` plugin. Running ``beets albumify`` with the plugin activated (set
  ``plugins=albumify`` in your config file) will group all your items into
  albums, making beets behave more or less as it did before.

* Fixed some bugs with encoding paths on Windows. Also, ``:`` is now replaced
  with ``-`` in path names (instead of ``_``) for readability.

* ``MediaFile``s now have a ``format`` attribute, so you can use ``$format`` in
  your library path format strings like ``$artist - $album ($format)`` to get
  directories with names like ``Paul Simon - Graceland (FLAC)``.

.. _for the future: https://github.com/google-code-export/beets/issues/69
.. _the beetsplug directory:
   https://github.com/beetbox/beets/tree/master/beetsplug

Beets also now has its first third-party plugin: `beetfs`_, by Martin Eve! It
exposes your music in a FUSE filesystem using a custom directory structure. Even
cooler: it lets you keep your files intact on-disk while correcting their tags
when accessed through FUSE. Check it out!

.. _beetfs: https://github.com/jbaiter/beetfs

1.0b2 (July 7, 2010)
--------------------

This release focuses on high-priority fixes and conspicuously missing features.
Highlights include support for two new audio formats (Monkey's Audio and Ogg
Vorbis) and an option to log untaggable albums during import.

* **Support for Ogg Vorbis and Monkey's Audio** files and their tags. (This
  support should be considered preliminary: I haven't tested it heavily because
  I don't use either of these formats regularly.)

* An option to the ``beet import`` command for **logging albums that are
  untaggable** (i.e., are skipped or taken "as-is"). Use ``beet import -l
  LOGFILE PATHS``. The log format is very simple: it's just a status (either
  "skip" or "asis") followed by the path to the album in question. The idea is
  that you can tag a large collection and automatically keep track of the albums
  that weren't found in MusicBrainz so you can come back and look at them later.

* Fixed a ``UnicodeEncodeError`` on terminals that don't (or don't claim to)
  support UTF-8.

* Importing without autotagging (``beet import -A``) is now faster and doesn't
  print out a bunch of whitespace. It also lets you specify single files on the
  command line (rather than just directories).

* Fixed importer crash when attempting to read a corrupt file.

* Reorganized code for CLI in preparation for adding pluggable subcommands. Also
  removed dependency on the aging ``cmdln`` module in favor of `a hand-rolled
  solution`_.

.. _a hand-rolled solution: https://gist.github.com/462717

1.0b1 (June 17, 2010)
---------------------

Initial release.
