# This file is part of beets.
# Copyright 2022, dvcky <https://col.ee/>
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
"""Moves "featured" artists to the title from the artist field.

Works similarly to regular ftintitle, but uses data from
MusicBrainz to produce potentially better results.
"""

from beets import plugins
import musicbrainzngs

mb_candidates = []


class FtInTitleMBPlugin(plugins.BeetsPlugin):
    """Class for ftintitle_mb plugin."""

    def __init__(self):
        """Initialize plugin."""
        super().__init__()

        self.config.add({
            'feat_format': "(feat. {0})",
            'collab_cases': [", ", " & ", " vs ", " x ", " × "],
        })

        self.register_listener('matchinfo_received', self.ftintitle_mb)
        self.register_listener('mb_album_by_id_received', self.collect)
        self.register_listener('mb_track_by_id_received', self.collect)
        self.register_listener('mb_track_by_search_received', self.collect)

    def collect(self, info):
        """Append information to the array to be used by find_mb_match."""
        mb_candidates.append(info)

    # finds the "raw" MusicBrainz data for the user's selection by iterating
    # through an array of possible candidates until one is found that has an
    # identical ID to the Match object passed
    def find_mb_match(self, match):
        """Find "raw" MusicBrainz data for user's selection."""
        found = {}
        # iterate through each possible match
        for candidate in mb_candidates:
            # if it has the attribute "album_id", it is an album.
            if hasattr(match.info, "album_id") and \
                        (match.info.album_id == candidate['id']):
                found = candidate
                break
            elif hasattr(match.info, "track_id") and \
                        (match.info.track_id == candidate['id']):
                found = candidate
                break
        # somehow beets saves results (even if they aren't used in the current
        # import) and will use them if a match comes up later. I have no idea
        # how they do that without using loads of memory, so we will just
        # manually fetch the data if it ends up being a repeated result. in
        # most cases this shouldn't be an issue
        if not found:
            if hasattr(match.info, "album_id"):
                found = musicbrainzngs.get_release_by_id(
                    match.info.album_id,
                    ['recordings', 'artist-credits'])['release']
            elif hasattr(match.info, "track_id"):
                found = musicbrainzngs.get_recording_by_id(
                    match.info.track_id, ['artist-credits'])['recording']
        # wipe array to save memory
        mb_candidates.clear()
        return found

    # iterates through the `collab_cases` array to see if the current
    # featuretype is one of them
    def is_collab_case(self, featuretype):
        """Check if current case is one of the collab cases."""
        for case in self.config['collab_cases'].as_str_seq():
            if featuretype == case:
                return True
        return False

    # this is technically a misinformative title, but it ends up with the same
    # effect. this is the meat of the ftintitle, and translates the MusicBrainz
    # data into something that can be put into our Match object. later on the
    # Match object will create a file based on info stored in it.
    def update_metadata(self, match, mb_track):
        """Update metadata for Match based on information found."""
        # initializing some variables:
        # artistbuilder: our artist building variable
        # featurebuilder: our feature building variable
        # featuretypes: stores all the feature types in-between artists
        # featureartists: stores the artists that will be placed in the feature
        # multiartist: are we still be appending artists to the artistbuilder?
        artistbuilder = ""
        featurebuilder = ""
        featuretypes = []
        featureartists = []
        multiartist = True

        # iterate through each credit (can be artist, feat type, or feat
        # artist) this will distribute items to their respective arrays
        for credit in mb_track['artist-credit']:
            if not isinstance(credit, str):
                if multiartist:
                    artistbuilder += credit['artist']['name']
                else:
                    featureartists.append(credit['artist']['name'])
            elif multiartist and self.is_collab_case(credit):
                artistbuilder += credit
            else:
                multiartist = False
                featuretypes.append(credit)
        # time to build our feature!
        for x in range(len(featuretypes)):
            # we dont include first feature type, user defines that
            if x != 0:
                featurebuilder += featuretypes[x]
            featurebuilder += featureartists[x]
        # we dont want to add a space and formatting if there is no feature!
        if len(featuretypes) > 0:
            featurebuilder = " " + \
                self.config['feat_format'].get(str).format(featurebuilder)
        # apply our changes to the Match object
        match['title'] = mb_track['title'] + featurebuilder
        match['artist'] = artistbuilder

    def ftintitle_mb(self, match):
        """Get MusicBrainz data for respective Match object."""
        mb_match = self.find_mb_match(match)
        # if it is an album, make sure we iterate through bits of the data like
        # a track, rather than the whole thing
        if hasattr(match.info, "album_id"):
            for track, mb_track \
                              in zip(match.info['tracks'],
                                     mb_match['medium-list'][0]['track-list']):
                self.update_metadata(track, mb_track['recording'])
        else:
            self.update_metadata(match.info, mb_match)
