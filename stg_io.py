#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Sat Mar 23 18:32:18 2013

@author: tom
"""

#def read():
#    return None

from osm2city import Building, Coords

inf="/usr/share/games/FlightGear/Scenery/Objects/w130n30/w122n37/958440.stg"


#    def __str__(self):
#        return "%s %s %g %g %g %g" % (self.typ, self.path, self.lon, self.lat, self.alt, self.hdg)

class Stg:
    def __init__(self, filenames):
        self.objs = []
        for filename in filenames:
            print "stg read", filename
            self.objs += self.read(filename)

    def read(self, filename):
        objs = []
        f = open(filename)
        for line in f.readlines():
            if line.startswith('#'): continue
            splitted = line.split()
            typ, path  = splitted[0:2]
            lon = float(splitted[2])
            lat = float(splitted[3])
            alt = float(splitted[4])
            r = Coords(-1, lon, lat)
            hdg = float(splitted[5])
            objs.append(Building(osm_id=-1, tags=-1, refs=[r], name=path, height=0, levels=0, stg_typ = typ, stg_hdg = hdg))
        f.close()
        return objs




#a = stg(inf)
#for o in a.objs:
#    print o
