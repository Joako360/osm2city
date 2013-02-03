#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""read osm file, print 2d view in ac3d format to stdout"""


import numpy as np
import sys
import random
#import imposm.parser as pa

from imposm.parser import OSMParser
import coordinates

default_height=10
level_height = 3
ground_height = -20
nb = 0
nobjects = 0
first = True

tile_size_x=500 # -- our tile size in meters
tile_size_y=500
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

def write_building(b):
    global first
    if len(b.refs) < 3: return
    mat = random.randint(0,3)

    nnodes_ground = len(b.refs)
    print nnodes_ground #, b.refs[0].lat, b.refs[0].lon

#for building in allbuildings:
    global nb
    nb += 1
    global nobjects
    nobjects += 1
    global elev
#  if building[0] == 332:
#    if first: first = False
#    else:     out.write("kids 1\n")

    out.write("OBJECT poly\n")
    out.write("name \"b%i\"\n" % nb)
    if nnodes_ground == 4:
        have_roof_texture = True
    else: have_roof_texture = False

    if have_roof_texture:
        out.write('texture "roof.png"\n')

    out.write("loc 0 0 0\n")
    out.write("numvert %i\n" % (2*nnodes_ground))
    X = np.zeros((nnodes_ground+1,2))
    i = 0
    for r in b.refs:
        X[i,0], X[i,1] = transform.toLocal((r.lat, r.lon))
        i += 1
    X[-1] = X[0]

    # -- check for inverted faces
    crossX = 0.
    for i in range(nnodes_ground):
        crossX += X[i,0]*X[i+1,1] - X[i+1,0]*X[i,1]
    if crossX < 0: X = X[::-1]

    ground_elev = elev(X[0,0], X[0,1])

    for x in X[:-1]:
        z = ground_elev - 1
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], z, x[0]))

    try:
        height = float(b.height)
    except:
        height = 0.
    if height < 1. and float(b.levels) > 0:
        height = float(b.levels) * level_height
    if height < 1.:
        height = default_height
    # -- try height or levels
#    if height > 1.: z = height
#    elif float(b.levels) > 0:
#        z = float(b.levels) * level_height
        #print "LEVEL", z

    for x in X[:-1]:
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))

#    for r in b.refs:
#        x, y = transform.toLocal((r.lat, r.lon))
#        out.write("%g %g %g\n" % (y, z, x))

    nsurf = nnodes_ground + 1
    out.write("numsurf %i\n" % nsurf)
    # -- walls
    for i in range(nnodes_ground - 1):
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (i, 0, 0))
        out.write("%i %g %g\n" % (i + 1, 0, 0))
        out.write("%i %g %g\n" % (i + 1 + nnodes_ground, 0, 0))
        out.write("%i %g %g\n" % (i + nnodes_ground, 0, 0))

    # -- closing wall
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % mat)
    out.write("refs %i\n" % 4)
    out.write("%i %i %i\n" % (nnodes_ground - 1, 0, 0))
    out.write("%i %i %i\n" % (0, 0, 0))
    out.write("%i %i %i\n" % (nnodes_ground, 0, 0))
    out.write("%i %i %i\n" % (2*nnodes_ground-1, 0, 0))

    # -- roof
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % mat)
    out.write("refs %i\n" % nnodes_ground)

    if have_roof_texture:
        # -- textured roof
        out.write("%i %g %g\n" % (nnodes_ground,   0, 0))
        out.write("%i %g %g\n" % (nnodes_ground+1, 1, 0))
        out.write("%i %g %g\n" % (nnodes_ground+2, 1, 1))
        out.write("%i %g %g\n" % (nnodes_ground+3, 0, 1))
    else:
        for i in range(nnodes_ground):
            out.write("%i %g %g\n" % (i+nnodes_ground, 0, 0))

    out.write("kids 0\n")
    #if nb == 250: break


# simple class that handles the parsed OSM data.

class Building(object):
    def __init__(self, osm_id, tags, refs, name, height, levels):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.name = name
        self.height = height
        self.levels = levels

class Coords(object):
    def __init__(self, osm_id, lon, lat):
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat

class wayExtract(object):
    buildings = 0
    building_list = []
    coords_list = []


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
                self.building_list.append(building)
                write_building(building)

    def coords(self, coords):
	for osm_id, lon, lat in coords:
	    #print '%s %.4f %.4f' % (osm_id, lon, lat)
	    self.coords_list.append(Coords(osm_id, lon, lat))

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

# -- origin
#lat = 0.5*(minlat + maxlat)
#lon = 0.5*(minlon + maxlon)

lon = 13.7467
lat = 51.0377

transform = coordinates.Transformation((lat, lon), hdg = 0)
#origin = coordinates.Position(transform, [], lat, lon)

if 0:
    raster(transform, 'elev.in', -5000, -5000, size_x=10000, size_y=10000, step_x=20, step_y=20)
    sys.exit(0)

class interpolator(object):
    def __init__(self, filename):
        elev = np.loadtxt(filename)[:,2:]
        self.x = elev[:,0]
        self.y = elev[:,1]
        self.h = elev[:,2]
        self.min_x = min(self.x)
        self.max_x = max(self.x)
        self.min_y = min(self.y)
        self.max_y = max(self.y)
        self.h = self.h.reshape(500,500)
        self.x = self.x.reshape(500,500)
        self.y = self.y.reshape(500,500)
        #print self.h[0,0], self.h[0,1], self.h[0,2]
        #self.dx = self.h[0,0] - self.x[0,1]
        self.dx = 20.
        self.dy = 20.

    def __call__(self, x, y):
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

elev = interpolator("elev.xml")
elev.shift(-elev(0,0)) # -- shift to zero height at origin


minx, miny = transform.toLocal((minlat, minlon))
maxx, maxy = transform.toLocal((maxlat, maxlon))

out = open("city.ac", "w")

out.write("""AC3Db
MATERIAL "" rgb 0.7  0.7  0.7  amb 0.2 0.2 0.2  emis 0.5 0.5 0.5  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.9  0.9  0.9  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.8  0.8  0.8  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.8  0.7  0.7  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
""")

if 1:
    map_z0 = -1
    out.write("""OBJECT world
    kids 10
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

# instantiate counter and parser and start parsing
way = wayExtract()
p = OSMParser(concurrency=4, ways_callback=way.ways, coords_callback=way.coords )
print "start parsing"
#p.parse('dd.osm')
#p.parse('map-dd-neustadt.osm')
#p.parse('dd-neustadt.osm')
#p.parse('altstadt.osm') # 1500
#p.parse('xapi.osm') # fails
p.parse('xapi-buildings.osm') # huge!
#p.parse('xapi-small.osm')
print "done"
#sys.exit(0)
#p.parse('dd-altstadt.osm') # 158 buildings
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

out.write("kids 0\n")
out.close()
#    sys.exit(0)
#numvert 9
#
sys.stderr.write("# origin %15g %15g\n" % (lat, lon))
sys.stderr.write("# nbuildings %i\n" % nb)
