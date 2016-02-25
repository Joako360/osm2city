"""
Created on 15.06.2014

@author: keith.paterson
"""

import logging
import vec2d

from __builtin__ import max


class ObjectList(object):
    '''
    Class for storing a List OSM Objects
    '''

    def __init__(self, transform=None, clusters=None, boundary_clipping_complete_way=None):
        '''
        Constructor
        '''
        self.objects = []
        self.transform = transform
        self.clusters = clusters
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.
        self.min_max_scanned = False
        self.boundary_clipping_complete_way = boundary_clipping_complete_way

    def _process_nodes(self, nodes_dict):
        self.nodes_dict = nodes_dict
        logging.debug("len of nodes_dict %i", len(nodes_dict))

        for node in nodes_dict.values():
            self.maxlon = max(self.maxlon, node.lon)
            self.minlon = min(self.minlon, node.lon)
            self.maxlat = max(self.maxlat, node.lat)
            self.minlat = min(self.minlat, node.lat)
        self.min_max_scanned = True

        cmin = vec2d.vec2d(self.minlon, self.minlat)
        cmax = vec2d.vec2d(self.maxlon, self.maxlat)
        logging.info("min/max " + str(cmin) + " " + str(cmax))

    def __len__(self):
        return len(self.objects)

    def __iter__(self):
        for the_object in self.objects:
            yield the_object
