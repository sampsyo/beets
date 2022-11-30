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

"""Searches for albums in the MusicBrainz database.
"""

import musicbrainzngs
import re
import traceback

from beets import logging
from beets import plugins
import beets.autotag.hooks
import beets
from beets import util
from beets import config
from collections import Counter
from urllib.parse import urljoin

VARIOUS_ARTISTS_ID = '89ad4ac3-39f7-470e-963a-56509c546377'

BASE_URL = 'https://musicbrainz.org/'

SKIPPED_TRACKS = ['[data track]']

FIELDS_TO_MB_KEYS = {
    'catalognum': 'catno',
    'country': 'country',
    'label': 'label',
    'media': 'format',
    'year': 'date',
}

musicbrainzngs.set_useragent('beets', beets.__version__,
                             'https://beets.io/')


class MusicBrainzAPIError(util.HumanReadableException):
    """An error while talking to MusicBrainz. The `query` field is the
    parameter to the action and may have any type.
    """

    def __init__(self, reason, verb, query, tb=None):
        self.query = query
        if isinstance(reason, musicbrainzngs.WebServiceError):
            reason = 'MusicBrainz not reachable'
        super().__init__(reason, verb, tb)

    def get_message(self):
        return '{} in {} with query {}'.format(
            self._reasonstr(), self.verb, repr(self.query)
        )


log = logging.getLogger('beets')

RELEASE_INCLUDES = ['artists', 'media', 'recordings', 'release-groups',
                    'labels', 'artist-credits', 'aliases',
                    'recording-level-rels', 'work-rels',
                    'work-level-rels', 'artist-rels', 'isrcs']
BROWSE_INCLUDES = ['artist-credits', 'work-rels',
                   'artist-rels', 'recording-rels', 'release-rels']
if "work-level-rels" in musicbrainzngs.VALID_BROWSE_INCLUDES['recording']:
    BROWSE_INCLUDES.append("work-level-rels")
BROWSE_CHUNKSIZE = 100
BROWSE_MAXTRACKS = 500
TRACK_INCLUDES = ['artists', 'aliases', 'isrcs']
if 'work-level-rels' in musicbrainzngs.VALID_INCLUDES['recording']:
    TRACK_INCLUDES += ['work-level-rels', 'artist-rels']
if 'genres' in musicbrainzngs.VALID_INCLUDES['recording']:
    RELEASE_INCLUDES += ['genres']


def track_url(trackid):
    return urljoin(BASE_URL, 'recording/' + trackid)


def album_url(albumid):
    return urljoin(BASE_URL, 'release/' + albumid)


def configure():
    """Set up the python-musicbrainz-ngs module according to settings
    from the beets configuration. This should be called at startup.
    """
    hostname = config['musicbrainz']['host'].as_str()
    https = config['musicbrainz']['https'].get(bool)
    # Only call set_hostname when a custom server is configured. Since
    # musicbrainz-ngs connects to musicbrainz.org with HTTPS by default
    if hostname != "musicbrainz.org":
        musicbrainzngs.set_hostname(hostname, https)
    musicbrainzngs.set_rate_limit(
        config['musicbrainz']['ratelimit_interval'].as_number(),
        config['musicbrainz']['ratelimit'].get(int),
    )


def _preferred_alias(aliases):
    """Given an list of alias structures for an artist credit, select
    and return the user's preferred alias alias or None if no matching
    alias is found.
    """
    if not aliases:
        return

    # Only consider aliases that have locales set.
    aliases = [a for a in aliases if 'locale' in a]

    # Get any ignored alias types and lower case them to prevent case issues
    ignored_alias_types = config['import']['ignored_alias_types'].as_str_seq()
    ignored_alias_types = [a.lower() for a in ignored_alias_types]

    # Search configured locales in order.
    for locale in config['import']['languages'].as_str_seq():
        # Find matching primary aliases for this locale that are not
        # being ignored
        matches = []
        for a in aliases:
            if a['locale'] == locale and 'primary' in a and \
               a.get('type', '').lower() not in ignored_alias_types:
                matches.append(a)

        # Skip to the next locale if we have no matches
        if not matches:
            continue

        return matches[0]


def _preferred_release_event(release):
    """Given a release, select and return the user's preferred release
    event as a tuple of (country, release_date). Fall back to the
    default release event if a preferred event is not found.
    """
    countries = config['match']['preferred']['countries'].as_str_seq()

    for country in countries:
        for event in release.get('release-event-list', {}):
            try:
                if country in event['area']['iso-3166-1-code-list']:
                    return country, event['date']
            except KeyError:
                pass

    return release.get('country'), release.get('date')


def _flatten_artist_credit(credit):
    """Given a list representing an ``artist-credit`` block, flatten the
    data into a triple of joined artist name strings: canonical, sort, and
    credit.
    """
    artist_parts = []
    artist_sort_parts = []
    artist_credit_parts = []
    for el in credit:
        if isinstance(el, str):
            # Join phrase.
            artist_parts.append(el)
            artist_credit_parts.append(el)
            artist_sort_parts.append(el)

        else:
            alias = _preferred_alias(el['artist'].get('alias-list', ()))

            # An artist.
            if alias:
                cur_artist_name = alias['alias']
            else:
                cur_artist_name = el['artist']['name']
            artist_parts.append(cur_artist_name)

            # Artist sort name.
            if alias:
                artist_sort_parts.append(alias['sort-name'])
            elif 'sort-name' in el['artist']:
                artist_sort_parts.append(el['artist']['sort-name'])
            else:
                artist_sort_parts.append(cur_artist_name)

            # Artist credit.
            if 'name' in el:
                artist_credit_parts.append(el['name'])
            else:
                artist_credit_parts.append(cur_artist_name)

    return (
        ''.join(artist_parts),
        ''.join(artist_sort_parts),
        ''.join(artist_credit_parts),
    )


def _get_related_artist_names(relations, relation_type):
    """Given a list representing the artist relationships extract the names of
    the remixers and concatenate them.
    """
    related_artists = []

    for relation in relations:
        if relation['type'] == relation_type:
            related_artists.append(relation['artist']['name'])

    return ', '.join(related_artists)


def track_info(recording, index=None, medium=None, medium_index=None,
               medium_total=None):
    """Translates a MusicBrainz recording result dictionary into a beets
    ``TrackInfo`` object. Three parameters are optional and are used
    only for tracks that appear on releases (non-singletons): ``index``,
    the overall track number; ``medium``, the disc number;
    ``medium_index``, the track's index on its medium; ``medium_total``,
    the number of tracks on the medium. Each number is a 1-based index.
    """
    info = beets.autotag.hooks.TrackInfo(
        title=recording['title'],
        track_id=recording['id'],
        index=index,
        medium=medium,
        medium_index=medium_index,
        medium_total=medium_total,
        data_source='MusicBrainz',
        data_url=track_url(recording['id']),
    )

    if recording.get('artist-credit'):
        # Get the artist names.
        info.artist, info.artist_sort, info.artist_credit = \
            _flatten_artist_credit(recording['artist-credit'])

        # Get the ID and sort name of the first artist.
        artist = recording['artist-credit'][0]['artist']
        info.artist_id = artist['id']

    if recording.get('artist-relation-list'):
        info.remixer = _get_related_artist_names(
            recording['artist-relation-list'],
            relation_type='remixer'
        )

    if recording.get('length'):
        info.length = int(recording['length']) / (1000.0)

    info.trackdisambig = recording.get('disambiguation')

    if recording.get('isrc-list'):
        info.isrc = ';'.join(recording['isrc-list'])

    lyricist = []
    composer = []
    composer_sort = []
    for work_relation in recording.get('work-relation-list', ()):
        if work_relation['type'] != 'performance':
            continue
        info.work = work_relation['work']['title']
        info.mb_workid = work_relation['work']['id']
        if 'disambiguation' in work_relation['work']:
            info.work_disambig = work_relation['work']['disambiguation']

        for artist_relation in work_relation['work'].get(
                'artist-relation-list', ()):
            if 'type' in artist_relation:
                type = artist_relation['type']
                if type == 'lyricist':
                    lyricist.append(artist_relation['artist']['name'])
                elif type == 'composer':
                    composer.append(artist_relation['artist']['name'])
                    composer_sort.append(
                        artist_relation['artist']['sort-name'])
    if lyricist:
        info.lyricist = ', '.join(lyricist)
    if composer:
        info.composer = ', '.join(composer)
        info.composer_sort = ', '.join(composer_sort)

    arranger = []
    for artist_relation in recording.get('artist-relation-list', ()):
        if 'type' in artist_relation:
            type = artist_relation['type']
            if type == 'arranger':
                arranger.append(artist_relation['artist']['name'])
    if arranger:
        info.arranger = ', '.join(arranger)

    # Supplementary fields provided by plugins
    extra_trackdatas = plugins.send('mb_track_extract', data=recording)
    for extra_trackdata in extra_trackdatas:
        info.update(extra_trackdata)

    info.decode()
    return info


def _set_date_str(info, date_str, original=False):
    """Given a (possibly partial) YYYY-MM-DD string and an AlbumInfo
    object, set the object's release date fields appropriately. If
    `original`, then set the original_year, etc., fields.
    """
    if date_str:
        date_parts = date_str.split('-')
        for key in ('year', 'month', 'day'):
            if date_parts:
                date_part = date_parts.pop(0)
                try:
                    date_num = int(date_part)
                except ValueError:
                    continue

                if original:
                    key = 'original_' + key
                setattr(info, key, date_num)


def album_info(release):
    """Takes a MusicBrainz release result dictionary and returns a beets
    AlbumInfo object containing the interesting data about that release.
    """
    # Get artist name using join phrases.
    artist_name, artist_sort_name, artist_credit_name = \
        _flatten_artist_credit(release['artist-credit'])

    ntracks = sum(len(m['track-list']) for m in release['medium-list'])

    # The MusicBrainz API omits 'artist-relation-list' and 'work-relation-list'
    # when the release has more than 500 tracks. So we use browse_recordings
    # on chunks of tracks to recover the same information in this case.
    if ntracks > BROWSE_MAXTRACKS:
        log.debug('Album {} has too many tracks', release['id'])
        recording_list = []
        for i in range(0, ntracks, BROWSE_CHUNKSIZE):
            log.debug('Retrieving tracks starting at {}', i)
            recording_list.extend(musicbrainzngs.browse_recordings(
                release=release['id'], limit=BROWSE_CHUNKSIZE,
                includes=BROWSE_INCLUDES,
                offset=i)['recording-list'])
        track_map = {r['id']: r for r in recording_list}
        for medium in release['medium-list']:
            for recording in medium['track-list']:
                recording_info = track_map[recording['recording']['id']]
                recording['recording'] = recording_info

    # Basic info.
    track_infos = []
    index = 0
    for medium in release['medium-list']:
        disctitle = medium.get('title')
        format = medium.get('format')

        if format in config['match']['ignored_media'].as_str_seq():
            continue

        all_tracks = medium['track-list']
        if ('data-track-list' in medium
                and not config['match']['ignore_data_tracks']):
            all_tracks += medium['data-track-list']
        track_count = len(all_tracks)

        if 'pregap' in medium:
            all_tracks.insert(0, medium['pregap'])

        for track in all_tracks:

            if ('title' in track['recording'] and
                    track['recording']['title'] in SKIPPED_TRACKS):
                continue

            if ('video' in track['recording'] and
                    track['recording']['video'] == 'true' and
                    config['match']['ignore_video_tracks']):
                continue

            # Basic information from the recording.
            index += 1
            ti = track_info(
                track['recording'],
                index,
                int(medium['position']),
                int(track['position']),
                track_count,
            )
            ti.release_track_id = track['id']
            ti.disctitle = disctitle
            ti.media = format
            ti.track_alt = track['number']

            # Prefer track data, where present, over recording data.
            if track.get('title'):
                ti.title = track['title']
            if track.get('artist-credit'):
                # Get the artist names.
                ti.artist, ti.artist_sort, ti.artist_credit = \
                    _flatten_artist_credit(track['artist-credit'])
                ti.artist_id = track['artist-credit'][0]['artist']['id']
            if track.get('length'):
                ti.length = int(track['length']) / (1000.0)

            track_infos.append(ti)

    info = beets.autotag.hooks.AlbumInfo(
        album=release['title'],
        album_id=release['id'],
        artist=artist_name,
        artist_id=release['artist-credit'][0]['artist']['id'],
        tracks=track_infos,
        mediums=len(release['medium-list']),
        artist_sort=artist_sort_name,
        artist_credit=artist_credit_name,
        data_source='MusicBrainz',
        data_url=album_url(release['id']),
    )
    info.va = info.artist_id == VARIOUS_ARTISTS_ID
    if info.va:
        info.artist = config['va_name'].as_str()
    info.asin = release.get('asin')
    info.releasegroup_id = release['release-group']['id']
    info.albumstatus = release.get('status')

    # Get the disambiguation strings at the release and release group level.
    if release['release-group'].get('disambiguation'):
        info.releasegroupdisambig = \
            release['release-group'].get('disambiguation')
    if release.get('disambiguation'):
        info.albumdisambig = release.get('disambiguation')

    # Get the "classic" Release type. This data comes from a legacy API
    # feature before MusicBrainz supported multiple release types.
    if 'type' in release['release-group']:
        reltype = release['release-group']['type']
        if reltype:
            info.albumtype = reltype.lower()

    # Set the new-style "primary" and "secondary" release types.
    albumtypes = []
    if 'primary-type' in release['release-group']:
        rel_primarytype = release['release-group']['primary-type']
        if rel_primarytype:
            albumtypes.append(rel_primarytype.lower())
    if 'secondary-type-list' in release['release-group']:
        if release['release-group']['secondary-type-list']:
            for sec_type in release['release-group']['secondary-type-list']:
                albumtypes.append(sec_type.lower())
    info.albumtypes = '; '.join(albumtypes)

    # Release events.
    info.country, release_date = _preferred_release_event(release)
    release_group_date = release['release-group'].get('first-release-date')
    if not release_date:
        # Fall back if release-specific date is not available.
        release_date = release_group_date
    _set_date_str(info, release_date, False)
    _set_date_str(info, release_group_date, True)

    # Label name.
    if release.get('label-info-list'):
        label_info = release['label-info-list'][0]
        if label_info.get('label'):
            label = label_info['label']['name']
            if label != '[no label]':
                info.label = label
        info.catalognum = label_info.get('catalog-number')

    # Text representation data.
    if release.get('text-representation'):
        rep = release['text-representation']
        info.script = rep.get('script')
        info.language = rep.get('language')

    # Media (format).
    if release['medium-list']:
        first_medium = release['medium-list'][0]
        info.media = first_medium.get('format')

    if config['musicbrainz']['genres']:
        sources = [
            release['release-group'].get('genre-list', []),
            release.get('genre-list', []),
        ]
        genres = Counter()
        for source in sources:
            for genreitem in source:
                genres[genreitem['name']] += int(genreitem['count'])
        info.genre = '; '.join(g[0] for g in sorted(genres.items(),
                                                    key=lambda g: -g[1]))

    extra_albumdatas = plugins.send('mb_album_extract', data=release)
    for extra_albumdata in extra_albumdatas:
        info.update(extra_albumdata)

    info.decode()
    return info


def match_album(artist, album, tracks=None, extra_tags=None):
    """Searches for a single album ("release" in MusicBrainz parlance)
    and returns an iterator over AlbumInfo objects. May raise a
    MusicBrainzAPIError.

    The query consists of an artist name, an album name, and,
    optionally, a number of tracks on the album and any other extra tags.
    """
    # Build search criteria.
    criteria = {'release': album.lower().strip()}
    if artist is not None:
        criteria['artist'] = artist.lower().strip()
    else:
        # Various Artists search.
        criteria['arid'] = VARIOUS_ARTISTS_ID
    if tracks is not None:
        criteria['tracks'] = str(tracks)

    # Additional search cues from existing metadata.
    if extra_tags:
        for tag in extra_tags:
            key = FIELDS_TO_MB_KEYS[tag]
            value = str(extra_tags.get(tag, '')).lower().strip()
            if key == 'catno':
                value = value.replace(' ', '')
            if value:
                criteria[key] = value

    # Abort if we have no search terms.
    if not any(criteria.values()):
        return

    try:
        log.debug('Searching for MusicBrainz releases with: {!r}', criteria)
        res = musicbrainzngs.search_releases(
            limit=config['musicbrainz']['searchlimit'].get(int), **criteria)
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(exc, 'release search', criteria,
                                  traceback.format_exc())
    for release in res['release-list']:
        # The search result is missing some data (namely, the tracks),
        # so we just use the ID and fetch the rest of the information.
        albuminfo = album_for_id(release['id'])
        if albuminfo is not None:
            plugins.send('mb_album_by_search_received', info=release)
            yield albuminfo


def match_track(artist, title):
    """Searches for a single track and returns an iterable of TrackInfo
    objects. May raise a MusicBrainzAPIError.
    """
    criteria = {
        'artist': artist.lower().strip(),
        'recording': title.lower().strip(),
    }

    if not any(criteria.values()):
        return

    try:
        res = musicbrainzngs.search_recordings(
            limit=config['musicbrainz']['searchlimit'].get(int), **criteria)
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(exc, 'recording search', criteria,
                                  traceback.format_exc())
    for recording in res['recording-list']:
        plugins.send('mb_track_by_search_received', info=recording)
        yield track_info(recording)


def _parse_id(s):
    """Search for a MusicBrainz ID in the given string and return it. If
    no ID can be found, return None.
    """
    # Find the first thing that looks like a UUID/MBID.
    match = re.search('[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}', s)
    if match:
        return match.group()


def album_for_id(releaseid):
    """Fetches an album by its MusicBrainz ID and returns an AlbumInfo
    object or None if the album is not found. May raise a
    MusicBrainzAPIError.
    """
    log.debug('Requesting MusicBrainz release {}', releaseid)
    albumid = _parse_id(releaseid)
    if not albumid:
        log.debug('Invalid MBID ({0}).', releaseid)
        return
    try:
        res = musicbrainzngs.get_release_by_id(albumid,
                                               RELEASE_INCLUDES)
    except musicbrainzngs.ResponseError:
        log.debug('Album ID match failed.')
        return None
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(exc, 'get release by ID', albumid,
                                  traceback.format_exc())
    plugins.send('mb_album_by_id_received', info=res['release'])
    return album_info(res['release'])


def track_for_id(releaseid):
    """Fetches a track by its MusicBrainz ID. Returns a TrackInfo object
    or None if no track is found. May raise a MusicBrainzAPIError.
    """
    trackid = _parse_id(releaseid)
    if not trackid:
        log.debug('Invalid MBID ({0}).', releaseid)
        return
    try:
        res = musicbrainzngs.get_recording_by_id(trackid, TRACK_INCLUDES)
    except musicbrainzngs.ResponseError:
        log.debug('Track ID match failed.')
        return None
    except musicbrainzngs.MusicBrainzError as exc:
        raise MusicBrainzAPIError(exc, 'get recording by ID', trackid,
                                  traceback.format_exc())
    plugins.send('mb_track_by_id_received', info=res['recording'])
    return track_info(res['recording'])
