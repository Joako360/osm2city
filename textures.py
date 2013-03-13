# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
import numpy as np
import random

def find_matching_texture(cls, textures):
    candidates = []
    for t in textures:
        if t.cls == cls: candidates.append(t)
    if len(candidates) == 0: return None
    return candidates[random.randint(0, len(candidates)-1)]

class Texture(object):
#    def __init__(self, filename, h_min, h_max, h_size, h_splits, \
#                                 v_min, v_max, v_size, v_splits, \
#                                 has_roof_section):
    """
    possible texture types:
        - facade
        - roof

    facade:
      provides
        - shape:skyscraper
        - shape:residential
        - shape:commercial/business
        - shape:industrial
        - age:modern/old
        - color: white
        - region: europe-middle
        - region: europe-north
        - minlevels: 2
        - maxlevels: 4
      requires
        - roof:shape:flat
        - roof:color:red|black

    roof:
      provides
        - color:black (red, ..)
        - shape:flat  (gable, ..)

    """
    def __init__(self, cls, filename,
                 h_size_meters, h_splits, h_can_repeat, \
                 v_size_meters, v_splits, v_can_repeat, \
                 has_roof_section = False, \
                 provides = {}, requires = {}):
        self.cls = cls
        self.filename = filename
        self.provides = provides
        self.requires = requires
        self.has_roof_section = has_roof_section
        # roof type, color
#        self.v_min = v_min
#        self.v_max = v_max
        self.v_size_meters = v_size_meters
        self.v_splits = np.array(v_splits, dtype=np.float)
        if v_splits == None:
            self.v_splits = 1.
        elif len(self.v_splits) > 1:
# FIXME            test for not type list
            self.v_splits /= self.v_splits[-1]
        self.v_splits_meters = self.v_splits * self.v_size_meters
        self.v_can_repeat = v_can_repeat

#        self.h_min = h_min
#        self.h_max = h_max
        self.h_size_meters = h_size_meters
        self.h_splits = np.array(h_splits, dtype=np.float)
        print "h1", self.h_splits
        print "h2", h_splits

        if h_splits == None:
            self.h_splits = 1.
        elif len(self.h_splits) > 1:
            self.h_splits /= self.h_splits[-1]
        self.h_splits_meters = self.h_splits * self.h_size_meters
        self.h_can_repeat = h_can_repeat

        # self.type = type
        # commercial-
        # - warehouse
        # - skyscraper
        # industrial
        # residential
        # - old
        # - modern
        # european, north_american, south_american, mediterreanian, african, asian
