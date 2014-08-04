'''
Created on 15.06.2014

@author: keith.paterson
'''
import logging
from __builtin__ import max


class ObjectList(object):
    '''
    Class for storing a List OSM Objects
    '''

    def __init__(self, transform):
        '''
        Constructor
        '''
        self.objects = []
        self.transform = transform
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.
        self.min_max_scanned = False

    def _process_nodes(self, nodes):
        self.nodes_dict = nodes
        self.min_max_scanned = True
        for node in nodes.values():
            #logging.debug('%s %.4f %.4f', node.osm_id, node.lon, node.lat)
                self.maxlon = max(self.maxlon, node.lon)
                self.minlon = min(self.minlon, node.lon)
                self.maxlat = max(self.maxlat, node.lat)
                self.minlat = min(self.minlat, node.lat)
        logging.debug("")

    def __len__(self):
        return len(self.objects)

    def __iter__(self):
        for the_object in self.objects:
            yield the_object
