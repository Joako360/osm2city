# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
import numpy as np
import random

class TextureManager(object):
    def __init__(self,cls):
        self.__l = []
        self.__cls = cls

    def append(self, t):
        # -- prepend each item in t.provides with class name
        t.provides = [self.__cls + ':' + i for i in t.provides]
        self.__l.append(t)

    def find_matching(self, requires = []):
        candidates = self.find_candidates(requires)
        if len(candidates) == 0: return None
        return candidates[random.randint(0, len(candidates)-1)]

    def find_candidates(self, requires = []):
        candidates = []
        for cand in self.__l:
            if set(requires).issubset(cand.provides):
                candidates.append(cand)
        return candidates

    def __str__(self):
        return str(["<%s>" % i.filename for i in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

class FacadeManager(TextureManager):
    def find_candidates(self, requires = [], building_height = 10.):
        return TextureManager.find_candidates(self, requires)

    def find_matching(self, requires = [], building_height = 10.):
        return TextureManager.find_matching(self, requires)
        # FIXME: check height
#
#
#tex_facade = facades.find_matching(building_height, ["shape:residential", "age:modern"])
#tex_roof = roofs.find_matching(tex_facade.requires+["shape:flat"])



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
    def __init__(self, filename,
                 h_size_meters, h_splits, h_can_repeat, \
                 v_size_meters, v_splits, v_can_repeat, \
                 has_roof_section = False, \
                 provides = {}, requires = {}):
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

    def __str__(self):
        return "<%s>" % self.filename
        # self.type = type
        # commercial-
        # - warehouse
        # - skyscraper
        # industrial
        # residential
        # - old
        # - modern
        # european, north_american, south_american, mediterreanian, african, asian

# gable roof: requires = facade:age:old

def init():
    print "textures: init"
    global facades
    global roofs
    facades = FacadeManager('facade')

    facades.append(Texture('DSCF9495_pow2',
                            14, (585, 873, 1179, 1480, 2048), True,
                            19.4, (1094, 1531, 2048), False, True,
                            requires=['roof:color:black'],
                            provides=['shape:residential','age:old']))

    facades.append(Texture('DSCF9496_pow2',
                            4.44, None, True,
                            17.93, (1099, 1521, 2048), False, True,
                            requires=['roof:color:black'],
                            provides=['shape:residential','age:old']))

    facades.append(Texture('facade_modern36x36_12',
                            36., (None), True,
                            36., (158, 234, 312, 388, 465, 542, 619, 697, 773, 870, 1024), True, True,
                            provides=['shape:urban','shape:residential','age:modern']))

    facades.append(Texture('DSCF9503_pow2',
                            12.85, None, True,
                            17.66, (1168, 1560, 2048), False, True,
                            requires=['roof:color:black'],
                            provides=['shape:residential','age:old']))

    facades.append(Texture('wohnheime_petersburger_pow2',
                            15.6, (215, 414, 614, 814, 1024), True,
                            15.6, (112, 295, 477, 660, 843, 1024), True, True,
                            provides=['shape:urban','shape:residential','age:modern']))

    facades.append(Texture('facade_modern1',
                           2.5, None, True,
                           2.8, None, True,
                           provides=['shape:urban','shape:residential','age:modern','age:old']))


    roofs = TextureManager('roof')
    roofs.append(Texture('roof_tiled_black',
                             1.20, None, True, 0.60, None, True, provides=['color:black']))
    roofs.append(Texture('roof_tiled_red',
                             1.0, None, True, 0.88, None, True, provides=['color:red']))
    roofs.append(Texture('roof_black2',
                             1.07, None, True, 0.69, None, True, provides=['color:black']))
    roofs.append(Texture('roof_black3_small_256x128',
                             0.25, None, True, 0.12, None, True, provides=['color:black']))
    roofs.append(Texture('roof_black3',
                             0.6, None, True, 0.41, None, True, provides=['color:black']))

    print roofs[0].provides
    print "black roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:black'])]
    print "red   roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:red'])]
    print "old facades: ", [str(i) for i in facades.find_candidates(['facade:shape:residential','facade:age:old'])]

if __name__ == "__main__":
    init()
