# -*- coding: utf-8 -*-
# This file is part of beets.
# Copyright 2017, Dorian Soergel.
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

"""Gets work title, disambiguation, parent work and its disambiguation, composer, composer sort name and performers
"""

from __future__ import division, absolute_import, print_function

import subprocess

from beets import ui
from beets import util
from beets.plugins import BeetsPlugin
from beets.dbcore import types

import musicbrainzngs

class ParentWorkPlugin(BeetsPlugin):

    def __init__(self):
        super(ParentWorkPlugin, self).__init__()
        self.import_stages = [self.imported]
    # possible options
    #        self.config.add({
    #            u'bin': u'KeyFinder',
    #            u'auto': True,
    #            u'overwrite': False,
    #        })
    
    def commands(self):
        cmd = ui.Subcommand('parentwork',
                            help=u'fetches parent works, composers and performers')
        cmd.func = self.command
        return [cmd]
        
    def command(self, lib, opts, args):
        self.find_key(lib.items(ui.decargs(args)))
           
    item_types = {
        'parent_work':          types.STRING,
        'parent_work_disambig': types.STRING,
        'work':                 types.STRING,
        'work_disambig':        types.STRING,
        'performer':            types.STRING,
        'performer_sort':       types.STRING,
        'parent_composer':      types.STRING,
        'parent_composer_sort': types.STRING}
        
    def imported(self, session, task):
        self.find_work(task.items)        
    
    def find_work(self, items):
        
        for item in items:
            performer            = []
            performer_sort       = []
            work                 = []
            work_disambig        = []
            parent_work          = []
            parent_work_disambig = []
            parent_composer      = []
            parent_composer_sort = []
            item.read()
            recording_id=item['mb_trackid']
            i=0
            while i<5:
                try: 
                    performer_types=['performer','instrument','vocals','conductor','orchestra','chorus master','concertmaster']
                    rec_rels=musicbrainzngs.get_recording_by_id(recording_id, includes=['work-rels', 'artist-rels'])
                    if 'artist-relation-list' in rec_rels['recording']:
                        for dudes in rec_rels['recording']['artist-relation-list']:
                            if dudes['type'] in performer_types:
                                performer.append(dudes['artist']['name'])
                                performer_sort.append(dudes['artist']['sort-name'])
                    if 'work-relation-list' in rec_rels['recording']:
                        for work_relation in rec_rels['recording']['work-relation-list']:
                            work_id=work_relation['work']['id']
                            work_info=musicbrainzngs.get_work_by_id(work_id, includes=["work-rels", "artist-rels"])
                            work.append(work_info['work']['title'])
                            if 'disambiguation' in work_info['work']:
                                work_disambig.append(work_info['work']['disambiguation'])
                            partof=True
                            while partof:
                                partof=False
                                if 'work-relation-list' in work_info['work']:
                                    for work_father in work_info['work']['work-relation-list']:
                                        if work_father['type'] == 'parts': 
                                            if 'direction' in work_father:
                                                if work_father['direction'] == 'backward':
                                                    father_id=work_father['work']['id']
                                                    partof=True
                                                    work_info=musicbrainzngs.get_work_by_id(father_id, includes=["work-rels", "artist-rels"])
                            if 'artist-relation-list' in work_info['work']:
                                for artist in work_info['work']['artist-relation-list']:
                                    if artist['type']=='composer':
                                        if artist['artist']['name'] in parent_composer:
                                            pass
                                        else: 
                                            parent_composer.append(artist['artist']['name'])
                                            parent_composer_sort.append(artist['artist']['sort-name'])
                            else:
                                print('no composer')
                                print('add one at')
                                print('https://musicbrainz.org/work/'+ work_info['work']['id'])
                            if work_info['work']['title'] in parent_work:
                                pass
                            else: 
                                parent_work.append(work_info['work']['title'])
                                if 'disambiguation' in work_info['work']:
                                    parent_work_disambig.append(work_info['work']['disambiguation'])
                except musicbrainzngs.musicbrainz.NetworkError:
                    continue
                    i=i+1
                break    
            
            item['parent_work']          = u', '.join(parent_work)
            item['parent_work_disambig'] = u', '.join(parent_work_disambig)
            item['work']                 = u', '.join(work)
            item['work_disambig']        = u', '.join(work_disambig)
            item['performer']            = u', '.join(performer)
            item['performer_sort']       = u', '.join(performer_sort)
            item['parent_composer']      = u', '.join(parent_composer)
            item['parent_composer_sort'] = u', '.join(parent_composer_sort)
            
            item.store()
            
            
            
            
            
            
            
