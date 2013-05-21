#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Sat Mar 23 18:32:18 2013

@author: tom
"""

import os
import string
from osm2city import Building, Coords

#    def __str__(self):
#        return "%s %s %g %g %g %g" % (self.typ, self.path, self.lon, self.lat, self.alt, self.hdg)

class Stg:
    def __init__(self, stgs_with_path):
        self.objs = []
        for path, stg in stgs_with_path:
            #print "stg read", path, stg
            fgscenery = "/mnt/home/tom/fgfs/Scenery"
            self.objs += self.read(fgscenery + os.sep + "Objects" + os.sep + path, stg)

    def read(self, path, stg):
        objs = []
        print "stg read", path + stg

        f = open(path + stg)
        for line in f.readlines():
            if line.startswith('#') or line.lstrip() == "": continue
            splitted = line.split()
            typ, ac_path  = splitted[0:2]
            print "stg:", typ, path + ac_path
            lon = float(splitted[2])
            lat = float(splitted[3])
            alt = float(splitted[4])
            r = Coords(-1, lon, lat)
            hdg = float(splitted[5])
            objs.append(Building(osm_id=-1, tags=-1, refs=[r], name=path + ac_path, height=0, levels=0, stg_typ = typ, stg_hdg = hdg))
        f.close()
        return objs




#a = stg(inf)
#for o in a.objs:
#    print o
