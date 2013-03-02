#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""read osm file, print 2d view in ac3d format to stdout"""


import numpy as np
import sys
import random
import copy
#import imposm.parser as pa

from imposm.parser import OSMParser
import coordinates
import itertools
from cluster import Clusters
from building_writer import write_building, random_number
from vec2d import vec2d


ground_height = -20
nb = 0
nobjects = 0
first = True
tile_size_x=500 # -- our tile size in meters
tile_size_y=500
#infile = 'dd-altstadt.osm'; total_objects = 158
#infile = 'altstadt.osm'; total_objects = 2172
infile = 'xapi-buildings.osm'; total_objects = 1000 # huge!
#infile = 'map.osm'; total_objects = 216 #



#center_lon=
#center_lat=

def raster(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    # check $FGDATA/Nasal/IOrules
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in range(y0, y0+size_y, step_y):
        for x in range(x0, x0+size_x, step_x):
            lat, lon = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()

def dist(a,b):
    pass




#    if nb == 40: break


# simple class that handles the parsed OSM data.

class Building(object):
    def __init__(self, osm_id, tags, refs, name, height, levels):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.name = name
        self.height = height
        self.levels = levels
        global transform
        r = self.refs[0]
        self.X = vec2d(transform.toLocal((r.lat, r.lon)))
        #print "tr X", self.X


class Coords(object):
    def __init__(self, osm_id, lon, lat):
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat

class wayExtract(object):
    def __init__(self):
        self.buildings = 0
        self.building_list = []
        self.coords_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def ways(self, ways):
        # callback method for ways
        #print "-"*80
        for osm_id, tags, refs in ways:
            #print nb
            #print "-"*10
            #print tags, refs
            if 'building' in tags:
                self.buildings += 1
                #print "got building", osm_id, tags, refs
                #print "done\n\n"
                _name = ""
                _height = 0
                _levels = 0
                if 'name' in tags:
				_name = tags['name']
                if 'height' in tags:
                    _height = tags['height']
                if 'building:levels' in tags:
                    _levels = tags['building:levels']

                if refs[0] == refs[-1]: refs = refs[0:-1] # -- kick last ref if it coincides with first

                # -- find ref in coords
                _refs = []
                for ref in refs:
                    for coord in self.coords_list:
                        if coord.osm_id == ref:
                            _refs.append(coord)
                            break
                building = Building(osm_id, tags, _refs, _name, _height, _levels)
                if len(building.refs) < 3: return

                self.building_list.append(building)
                global nobjects
                if nobjects == total_objects: raise ValueError
                nobjects += 1
                print nobjects
                global clusters
                clusters.append(building.X, building)

    def coords(self, coords):
        for osm_id, lon, lat in coords:
            #print '%s %.4f %.4f' % (osm_id, lon, lat)
            self.coords_list.append(Coords(osm_id, lon, lat))
            if lon > self.maxlon: self.maxlon = lon
            if lon < self.minlon: self.minlon = lon
            if lat > self.maxlat: self.maxlat = lat
            if lat < self.minlat: self.minlat = lat


# -----------------------------------------------------------------------------
# -- map
# <bounds minlat="51.0599350" minlon="13.7415360" maxlat="51.0632660" maxlon="13.7452480"/>
#minlat=51.0599350
#minlon=13.7415360
#maxlat=51.0632660
#maxlon=13.7452480

# -- altstadt
# <bounds minlat="51.0317900" minlon="13.7149300" maxlat="51.0583100" maxlon="13.7551800"/>
#minlat=51.0317900
#minlon=13.7149300
#maxlat=51.0583100
#maxlon=13.7551800

# -- dd-altstadt
# <bounds minlat="51.0459700" minlon="13.7325800" maxlat="51.0564600" maxlon="13.7467600"/>
#minlat=51.0459700
#minlon=13.7325800
#maxlat=51.0564600
#maxlon=13.7467600

# -- xapi.osm
minlat=50.96
minlon=13.63
maxlat=51.17
maxlon=13.88
#
## -- neustadt.osm
#minlat=51.0628700
#minlon=13.7436400
#maxlat=51.0715500
#maxlon=13.7563400
#
# -- origin
#lat = 0.5*(minlat + maxlat)
#lon = 0.5*(minlon + maxlon)

lon = 13.7467
lat = 51.0377

transform = coordinates.Transformation((lat, lon), hdg = 0)
#origin = coordinates.Position(transform, [], lat, lon)

if 0:
    raster(transform, 'elev.in', -10000, -10000, size_x=20000, size_y=20000, step_x=20, step_y=20)
    sys.exit(0)

class Interpolator(object):
    """load elevation data from file, interpolate"""
    def __init__(self, filename, fake=False):
        # FIXME: use values from header in filename
        if fake:
            self.fake = True
            self.h = 0.
            return
        else:
            self.fake = False
        elev = np.loadtxt(filename)[:,2:]
        self.x = elev[:,0]
        self.y = elev[:,1]
        self.h = elev[:,2]
        self.min_x = min(self.x)
        self.max_x = max(self.x)
        self.min_y = min(self.y)
        self.max_y = max(self.y)
        self.h = self.h.reshape(1000,1000)
        self.x = self.x.reshape(1000,1000)
        self.y = self.y.reshape(1000,1000)
        #print self.h[0,0], self.h[0,1], self.h[0,2]
        #self.dx = self.h[0,0] - self.x[0,1]
        self.dx = 20.
        self.dy = 20.

    def __call__(self, x, y):
        """compute elevation at (x,y) by linear interpolation"""
        if self.fake: return 0.
        if x <= self.min_x or x >= self.max_x or \
           y <= self.min_y or y >= self.max_y: return -9999
        i = int((x - self.min_x)/self.dx)
        j = int((y - self.min_y)/self.dy)
        fx = (x - self.x[j,i])/self.dx
        fy = (y - self.y[j,i])/self.dy
        #print fx, fy, i, j
        h =  (1-fx) * (1-fy) * self.h[j,i] \
           +    fx  * (1-fy) * self.h[j,i+1] \
           + (1-fx) *    fy  * self.h[j+1,i] \
           +    fx  *    fy  * self.h[j+1,i+1]
        return h

    def shift(self, h):
        self.h += h

class Texture(object):
#    def __init__(self, filename, h_min, h_max, h_size, h_splits, \
#                                 v_min, v_max, v_size, v_splits, \
#                                 has_roof_section):
    def __init__(self, filename, h_size_meters, h_splits, h_repeat, \
                                 v_size_meters, v_splits, v_repeat, \
                                 has_roof_section):
        self.filename = filename
        self.has_roof_section = has_roof_section
        # roof type, color
#        self.v_min = v_min
#        self.v_max = v_max
        self.v_size_meters = v_size_meters
        self.v_splits = np.array(v_splits, dtype=np.float)
        if len(self.v_splits) > 1:
# FIXME            test for not type list
            self.v_splits /= self.v_splits[-1]
        self.v_splits_meters = self.v_splits * self.v_size_meters
        self.v_repeat = v_repeat

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
        self.h_repeat = h_repeat

        # self.type = type
        # commercial-
        # - warehouse
        # - skyscraper
        # industrial
        # residential
        # - old
        # - modern
        # european, north_american, south_american, mediterreanian, african, asian

textures = []
textures.append(Texture('DSCF9495_pow2', 14, (585, 873, 1179, 1480, 2048), True,
                                         19.4, (1094, 1531, 2048), False, True))
textures.append(Texture('DSCF9496_pow2', 4.44, None, True,
                                         17.93, (1099, 1521, 2048), False, True))

textures.append(Texture('facade_modern36x36_12', 36., (None), True,
                                         36., (158, 234, 312, 388, 465, 542, 619, 697, 773, 870, 1024), True, True))

textures.append(Texture('DSCF9503_pow2', 12.85, None, True,
                                         17.66, (1168, 1560, 2048), False, True))
textures.append(Texture('wohnheime_petersburger_pow2', 15.6, (215, 414, 614, 814, 1024), True,
                                                       15.6, (112, 295, 477, 660, 843, 1024), True, True))
print textures[0].v_splits_meters

#sys.exit(0)
elev = Interpolator("elev.xml", fake=False)
print "height at origin", elev(0,0)
#sys.exit()
elev.shift(-elev(0,0)) # -- shift to zero height at origin



min_ = vec2d(transform.toLocal((minlat, minlon)))
max_ = vec2d(transform.toLocal((maxlat, maxlon)))

# RGB mat for LOD testing
#MATERIAL "" rgb 1.0  0.0  0.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#MATERIAL "" rgb 0.0  1.0  0.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#MATERIAL "" rgb 0.0  0.0  1.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0

#MATERIAL "" rgb 0.9  0.9  0.9  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#MATERIAL "" rgb 0.85 0.85 0.85 amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#MATERIAL "" rgb 0.8  0.8  0.8  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#MATERIAL "" rgb 0.75 0.75 0.75 amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0

mats = ['MATERIAL "" rgb 1.0  0.0  0.0  amb 0.2 0.2 0.2  emis 1 0 0  spec 0.5 0.5 0.5  shi 10  trans 0',
        'MATERIAL "" rgb 0.0  1.0  0.0  amb 0.2 0.2 0.2  emis 0 1 0  spec 0.5 0.5 0.5  shi 10  trans 0',
        'MATERIAL "" rgb 0.0  0.0  1.0  amb 0.2 0.2 0.2  emis 0 0 1  spec 0.5 0.5 0.5  shi 10  trans 0']

def write_ac_header(out, nb):

#    out.write("""AC3Db
#    MATERIAL "" rgb 1.0  1.0  1.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#    MATERIAL "" rgb 1.0  1.0  1.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#    MATERIAL "" rgb 1.0  1.0  1.0  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#    OBJECT world
#    """)
    out.write("AC3Db\n%s\nOBJECT world\n" % mats[random.randint(0,2)])
    out.write("kids %i\n" % nb)

    if 0:
        map_z0 = -1
        out.write("""
        OBJECT poly
        name "rect"
        texture "xapi.png"
        numvert 4
        """)
        out.write("%g %g %g\n" % (miny, map_z0, minx))
        out.write("%g %g %g\n" % (miny, map_z0, maxx))
        out.write("%g %g %g\n" % (maxy, map_z0, maxx))
        out.write("%g %g %g\n" % (maxy, map_z0, minx))
        out.write("""numsurf 1
        SURF 0x0
        mat 0
        refs 4
        0 0 0
        1 1 0
        2 1 1
        3 0 1
        kids 0
        """)

# -----------------------------------------------------------------------------

clusters = Clusters(min_, max_, vec2d(2000.,2000.))
#print clusters.list
# instantiate counter and parser and start parsing
way = wayExtract()

#p = OSMParser(concurrency=4, ways_callback=way.ways, coords_callback=way.coords )
p = OSMParser(concurrency=4, coords_callback=way.coords )
print "start parsing coords"
p.parse(infile)
print "done parsing"
print "ncords:", len(way.coords_list)
print "bounds:", way.minlon, way.maxlon, way.minlat, way.maxlat

p = OSMParser(concurrency=4, ways_callback=way.ways)
print "start parsing ways"
try:
    p.parse(infile)
except ValueError:
    pass
#p.parse('xapi.osm') # fails
#p.parse('xapi-small.osm')

print "nbuildings", len(way.building_list)
print "done parsing"
clusters.stats()

stg = open("city.stg", "w")
for l in clusters._clusters:
    for cl in l:
        nb = len(cl.objects)
        if not nb: continue

        # -- get cluster center
        offset = cl.center

        transform.setOffset((-offset).list())
        center_lat, center_lon = transform.toGlobal((0,0))

        # -- open ac and write header
        fname_ac = "city-%04i%04i.ac" % (cl.I.x, cl.I.y)
        out = open(fname_ac, "w")
        write_ac_header(out, nb)
        for building in cl.objects:
            write_building(building, out, elev, transform, textures)
        out.close()
        transform.setOffset((0,0))

        # -- write stg
        stg.write("OBJECT_STATIC %s %g %g %g %g\n" % (fname_ac, center_lon, center_lat, 114.687, 180))
stg.close()

print "done writing ac's"


sys.exit(0)
#p.parse('map.osm')
# done
#print way.buildings
#print way.building_list


#lat = way.building_list[0].refs[0].lat
#lon = way.building_list[0].refs[0].lon

# -- use transform from above
#transform = coordinates.Transformation((lat, lon), hdg = 0)
#origin = coordinates.Position(transform, [], lat, lon)

# -- get ground nodes for each building

#print """AC3Db
#MATERIAL "" rgb 1 1 1  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
#OBJECT world
#kids 1
#"""

#    print
#    if b.name == 'Frauenkirche':
#        print "FK"
#        print thisbuilding
#        for v in thisbuilding:
#            print vertices[v][0], vertices[v][1]
#        sys.exit(0)

#print vertices

#for b in way.building_list:
#    write_building(b)

#out.write("kids 0\n")
out.close()
#    sys.exit(0)
#numvert 9
#
sys.stderr.write("# origin %15g %15g\n" % (lat, lon))
sys.stderr.write("# nbuildings %i\n" % nb)

# -- write xml
#    - LOD animation
xml = open("city.xml", "w")
xml.write("""<?xml version="1.0"?>

<PropertyList>

 <path>city.ac</path>

 <animation>
  <type>range</type>
""")
for name in LOD_lists[0]:
    xml.write("<object-name>%s</object-name>\n" % name)
xml.write("""
  <min-m>0</min-m>
  <max-property>/sim/rendering/static-lod/detailed</max-property>
 </animation>

 <animation>
  <type>range</type>
""")
for name in LOD_lists[1]:
    xml.write("<object-name>%s</object-name>\n" % name)
xml.write("""
  <min-m>0</min-m>
  <max-property>/sim/rendering/static-lod/rough</max-property>
 </animation>

  <animation>
  <type>range</type>
""")
for name in LOD_lists[2]:
    xml.write("<object-name>%s</object-name>\n" % name)
xml.write("""
  <min-m>0</min-m>
  <max-property>/sim/rendering/static-lod/bare</max-property>
 </animation>

</PropertyList>
""")

xml.close()
print "done writing xml"
