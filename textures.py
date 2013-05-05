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
        self.__cls = cls # -- class (roof, facade, ...)

    def append(self, t):
        # -- prepend each item in t.provides with class name,
        #    except for class-independent keywords: age,region,compat
        new_provides = []
        for item in t.provides:
            if item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(item)
            else:
                new_provides.append(self.__cls + ':' + item)
        #t.provides = [self.__cls + ':' + i for i in t.provides]
        t.provides = new_provides
        self.__l.append(t)

    def find_matching(self, requires = []):
        candidates = self.find_candidates(requires)
        if len(candidates) == 0:
            print "WARNING: no matching texture for <%s>", requires
            return None
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
    def find_matching(self, requires, building_height):
        candidates = self.find_candidates(requires, building_height)
        if len(candidates) == 0:
            print "WARNING: no matching texture for <%s>", requires
            return None
        return candidates[random.randint(0, len(candidates)-1)]

    def find_candidates(self, requires, building_height):
        candidates = TextureManager.find_candidates(self, requires)
#        print "\ncands", [str(t.filename) for t in candidates]
        # -- check height
#        print " Candidates:"
        new_candidates = []
        for t in candidates:
#            print "  <<<", t.filename
#            print "     building_height", building_height
#            print "     min/max", t.height_min, t.height_max
            if building_height < t.height_min or building_height > t.height_max:
#                print "  KICKED"
                continue
            new_candidates.append(t)

#                candidates.remove(t)
#        print "remaining cands", [str(t.filename) for t in new_candidates]
        return new_candidates


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
                 height_min = 0, height_max = 9999, \
                 v_split_from_bottom = False, \
                 provides = {}, requires = {}):
        self.filename = filename
        self.provides = provides
        self.requires = requires
        self.has_roof_section = has_roof_section
        self.height_min = height_min
        self.height_max = height_max
        self.v_split_from_bottom = v_split_from_bottom
        # roof type, color
#        self.v_min = v_min
#        self.v_max = v_max
        self.v_size_meters = v_size_meters
        if v_splits != None:
            v_splits.insert(0,0)
            self.v_splits = np.array(v_splits, dtype=np.float)
            if len(self.v_splits) > 1:
                # FIXME            test for not type list
                self.v_splits /= self.v_splits[-1]
#                print self.v_splits
                # -- Gimp origin is upper left, convert to OpenGL lower left
                self.v_splits = (1. - self.v_splits)[::-1]
#                print self.v_splits
        else:
            self.v_splits = 1.
        self.v_splits_meters = self.v_splits * self.v_size_meters

        self.v_can_repeat = v_can_repeat

        if not self.v_can_repeat:
            self.height_min = self.v_splits_meters[0]
            self.height_max = self.v_size_meters

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

    if True:
        facades.append(Texture('tex/DSCF9495_pow2',
                                14, [585, 873, 1179, 1480, 2048], True,
                                19.4, [274, 676, 1114, 1542, 2048], False, True,
                                requires=['roof:color:black'],
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))

#                                19.4, [1094, 1531, 2048], False, True,

        facades.append(Texture('tex/DSCF9495_pow2',
                                14, [585, 873, 1179, 1480, 2048], True,
                                19.4, [274, 676, 1114, 1542, 2048], False, True,
                                height_max = 13.,
                                v_split_from_bottom = True,
                                requires=['roof:color:red'],
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))
    if True:

        # -- just two windows. Looks rather boring. But maybe we need a very narrow texture?
    #    facades.append(Texture('tex/DSCF9496_pow2',
    #                            4.44, None, True,
    #                            17.93, (1099, 1521, 2048), False, True,
    #                            requires=['roof:color:black'],
    #                            provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))

        facades.append(Texture('tex/LZ_old_bright_bc2',
                                17.9, [345,807,1023,1236,1452,1686,2048], True,
                                14.8, [558,1005,1446,2048], False, True,
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))


        facades.append(Texture('tex/facade_modern36x36_12',
                                36., [None], True,
                                36., [158, 234, 312, 388, 465, 542, 619, 697, 773, 870, 1024], True, True,
                                provides=['shape:urban','shape:residential','age:modern',
                                         'compat:roof-flat']))

    #    facades.append(Texture('tex/DSCF9503_pow2',
    #                            12.85, None, True,
    #                            17.66, (1168, 1560, 2048), False, True,
    #                            requires=['roof:color:black'],
    #                            provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))
        facades.append(Texture('tex/DSCF9503_noroofsec_pow2',
                                12.85, None, True,
                                17.66, [556,1015,1474,2048], False, True,
                                requires=['roof:color:black'],
                                provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))

    # -- this just looks ugly
    #    facades.append(Texture('tex/facade_modern1',
    #                           2.5, None, True,
    #                           2.8, None, True,
    #                           height_min = 15.,
    #                           provides=['shape:urban','shape:residential','age:modern',
    #                                     'compat:roof-flat']))

    #    facades.append(Texture('tex/DSCF9710_pow2',
    #                           29.9, (284,556,874,1180,1512,1780,2048), True,
    #                           19.8, (173,329,490,645,791,1024), False, True,
    #                           provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))

        facades.append(Texture('tex/DSCF9710',
                               29.9, [142,278,437,590,756,890,1024], True,
                               19.8, [130,216,297,387,512], False, True,
                               provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))


        facades.append(Texture('tex/DSCF9678_pow2',
                               10.4, [97,152,210,299,355,411,512], True,
                               15.5, [132,211,310,512], False, True,
                               provides=['shape:residential','shape:commercial','age:modern','compat:roof-flat']))

        facades.append(Texture('tex/DSCF9726_noroofsec_pow2',
                               15.1, [321,703,1024], True,
                               9.6, [227,512], False, True,
                               provides=['shape:residential','age:old','compat:roof-flat','compat:roof-gable']))

        facades.append(Texture('tex/wohnheime_petersburger',
                                15.6, [215, 414, 614, 814, 1024], True,
                                15.6, [112, 295, 477, 660, 843, 1024], True, True,
                                height_min = 15.,
                                provides=['shape:urban','shape:residential','age:modern',
                                         'compat:roof-flat']))
    #                            provides=['shape:urban','shape:residential','age:modern','age:old',
    #                                     'compat:roof-flat','compat:roof-gable']))




    roofs = TextureManager('roof')
    roofs.append(Texture('tex/roof_tiled_black',
                             1.20, None, True, 0.60, None, True, provides=['color:black']))
    roofs.append(Texture('tex/roof_tiled_red',
                             1.0, None, True, 0.88, None, True, provides=['color:red']))
#    roofs.append(Texture('tex/roof_black2',
#                             1.39, None, True, 0.89, None, True, provides=['color:black']))
#    roofs.append(Texture('tex/roof_black3',
#                             0.6, None, True, 0.41, None, True, provides=['color:black']))

#    roofs.append(Texture('tex/roof_black3_small_256x128',
#                             0.25, None, True, 0.12, None, True, provides=['color:black']))

    print roofs[0].provides
    print "black roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:black'])]
    print "red   roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:red'])]
    print "old facades: "
    for i in facades.find_candidates(['facade:shape:residential','age:old'], 10):
        print i, i.v_splits * i.v_size_meters
    #print facades[0].provides

if __name__ == "__main__":
    init()
    cands = facades.find_candidates([], 14)
    print "cands ar", cands
    for t in cands:
        print "%5.2g  %s" % (t.height_min, t.filename)

