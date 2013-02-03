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

default_height=12
level_height = 3
ground_height = -20
nb = 0
nobjects = 0
first = True
tile_size_x=500 # -- our tile size in meters
tile_size_y=500
#infile = 'dd-altstadt.osm'; total_objects = 158
#infile = 'altstadt.osm'; total_objects = 2172
infile = 'xapi-buildings.osm'; total_objects = 20000 # huge!

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

def check_height(building_height, t):
    if t.v_repeat:
        tex_y1 = 1.
        tex_y0 = 1-building_height / t.v_size_meters
        return True, tex_y0, tex_y1
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error
        # - error acceptable?
        if building_height >= t.v_splits_meters[0] and building_height <= t.v_size_meters:
            for i in range(len(t.v_splits_meters)):
                if t.v_splits_meters[i] >= building_height:
                    tex_y0 = 1-t.v_splits[i]
                    print "# height %g storey %i" % (building_height, i)
                    break
            tex_y1 = 1.
            #tex_filename = t.filename + '.png'
            return True, tex_y0, tex_y1
        else:
            return False, 0, 0


def write_building(b):
    global first
    if len(b.refs) < 3: return
    mat = random.randint(0,3)

    nnodes_ground = len(b.refs)
#    print nnodes_ground #, b.refs[0].lat, b.refs[0].lon

#for building in allbuildings:
    global nb
    nb += 1
    print nb

    global nobjects
    nobjects += 1
    global elev
#  if building[0] == 332:
#    if first: first = False
#    else:     out.write("kids 1\n")

    out.write("OBJECT poly\n")
    out.write("name \"b%i\"\n" % nb)
    if nnodes_ground == 4:
        include_roof = False
    else: include_roof = True

#    if separate_roof:
#    out.write('texture "facade_modern1.png"\n')
#    out.write('texture "facade_modern36x36_12.png"\n')

    X = np.zeros((nnodes_ground+1,2))
    lenX = np.zeros((nnodes_ground))
    i = 0
    for r in b.refs:
        X[i,0], X[i,1] = transform.toLocal((r.lat, r.lon))
        i += 1
    X[-1] = X[0]

    # -- check for inverted faces
    crossX = 0.
    for i in range(nnodes_ground):
        crossX += X[i,0]*X[i+1,1] - X[i+1,0]*X[i,1]
        lenX[i] = ((X[i+1,0]-X[i,0])**2 + (X[i+1,1]-X[i,1])**2)**0.5

    if crossX < 0:
        X = X[::-1]
        lenX = lenX[::-1]

    ground_elev = elev(X[0,0], X[0,1])


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

#    for r in b.refs:
#        x, y = transform.toLocal((r.lat, r.lon))
#        out.write("%g %g %g\n" % (y, z, x))

    nsurf = nnodes_ground
    if include_roof: nsurf += 1

    #repeat_vert = int(height/3)

    # -- texturing facade
    # - check all walls -- min length?
    global textures
    # loop all textures
    # award points for good matches
    # pick best match?
    building_height = height
    # -- check v: height

    shuffled_t = copy.copy(textures)
    random.shuffle(shuffled_t)
    have_texture = False
    for t in shuffled_t:
        ok, tex_y0, tex_y1 = check_height(building_height, t)
        if ok:
            have_texture = True
            break

    if have_texture:
        out.write('texture "%s"\n' % (t.filename+'.png'))
    else:
        print "WARNING: no texture height", building_height

    # -- check h: width

    # building shorter than facade texture
    # layers > facade_min_layers
    # layers < facade_max_layers
#    building_height = height
#    texture_height = 12*3.
#    if building_height < texture_height:
#    if 1:
#        tex_y0 = 1 - building_height / texture_height
#        tex_y1 = 1
#    else:
#        tex_y0 = 0
#        tex_y1 = building_height / texture_height # FIXME

    #out.write("loc 0 0 0\n")
    out.write("numvert %i\n" % (2*nnodes_ground))

    for x in X[:-1]:
        z = ground_elev - 1
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], z, x[0]))

    for x in X[:-1]:
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))

    out.write("numsurf %i\n" % nsurf)
    # -- walls

    for i in range(nnodes_ground - 1):
        tex_x1 = lenX[i] / t.h_size_meters

        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (i,                     0,          tex_y0))
        out.write("%i %g %g\n" % (i + 1,                 tex_x1, tex_y0))
        out.write("%i %g %g\n" % (i + 1 + nnodes_ground, tex_x1, tex_y1))
        out.write("%i %g %g\n" % (i + nnodes_ground,     0,          tex_y1))

    # -- closing wall
    tex_x1 = lenX[nnodes_ground-1] /  t.h_size_meters
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % mat)
    out.write("refs %i\n" % 4)
    out.write("%i %g %g\n" % (nnodes_ground - 1, 0,          tex_y0))
    out.write("%i %g %g\n" % (0,                 tex_x1, tex_y0))
    out.write("%i %g %g\n" % (nnodes_ground,     tex_x1, tex_y1))
    out.write("%i %g %g\n" % (2*nnodes_ground-1, 0,          tex_y1))

    # -- roof
    if include_roof:
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % nnodes_ground)
        for i in range(nnodes_ground):
            out.write("%i %g %g\n" % (i+nnodes_ground, 0, 0))
        out.write("kids 0\n")
    else:
        # -- textured roof, a separate object
        out.write("kids 0\n")
        out.write("OBJECT poly\n")
        nb += 1
        out.write("name \"b%i\"\n" % nb)
        out.write('texture "roof.png"\n')

        #out.write("loc 0 0 0\n")
        out.write("numvert %i\n" % (nnodes_ground))
        for x in X[:-1]:
            z = ground_elev - 1
            #out.write("%g %g %g\n" % (y, z, x))
            out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))
        out.write("numsurf %i\n" % 1)
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % nnodes_ground)
        out.write("%i %g %g\n" % (0, 0, 0))
        out.write("%i %g %g\n" % (1, 1, 0))
        out.write("%i %g %g\n" % (2, 1, 1))
        out.write("%i %g %g\n" % (3, 0, 1))

        out.write("kids 0\n")
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
    raster(transform, 'elev.in', -10000, -10000, size_x=20000, size_y=20000, step_x=20, step_y=20)
    sys.exit(0)

class Interpolator(object):
    def __init__(self, filename):
        # FIXME: use values from header in filename
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
        self.v_splits = np.array(v_splits)
        self.v_splits_meters = self.v_splits * self.v_size_meters
        self.v_repeat = v_repeat

#        self.h_min = h_min
#        self.h_max = h_max
        self.h_size_meters = h_size_meters
        self.h_splits = np.array(h_splits)
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
textures.append(Texture('DSCF9495_pow2', 14, (585/2048., 873/2048., 1179/2048., 1480/2048., 1.), True,
                                         19.4, (1094/2048., 1531/2048., 1.), False, True))
textures.append(Texture('DSCF9496_pow2', 4.44, (1.), True,
                                         17.93, (1099/2048., 1521/2048., 1.), False, True))

textures.append(Texture('facade_modern36x36_12', 36., (1.), True,
                                         36., (158/1024., 234/1024, 312/1024., 388/1024., 465/1024., 542/1024., 619/1024., 697/1024., 773/1024., 870/1024., 1.), True, True))

textures.append(Texture('DSCF9503_pow2', 12.85, (1.), True,
                                         17.66, (1168/2048., 1560/2048., 1.), False, True))

print textures[0].v_splits_meters

#sys.exit(0)
elev = Interpolator("elev.xml")
elev.shift(-elev(0,0)) # -- shift to zero height at origin

minx, miny = transform.toLocal((minlat, minlon))
maxx, maxy = transform.toLocal((maxlat, maxlon))

out = open("city.ac", "w")

out.write("""AC3Db
MATERIAL "" rgb 0.7  0.7  0.7  amb 0.2 0.2 0.2  emis 0.5 0.5 0.5  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.9  0.9  0.9  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.8  0.8  0.8  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
MATERIAL "" rgb 0.8  0.7  0.7  amb 0.2 0.2 0.2  emis 0 0 0  spec 0.5 0.5 0.5  shi 10  trans 0
OBJECT world
""")
out.write("kids %i\n" % total_objects)

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

# instantiate counter and parser and start parsing
way = wayExtract()
p = OSMParser(concurrency=4, ways_callback=way.ways, coords_callback=way.coords )
print "start parsing"
#p.parse('dd.osm')
#p.parse('map-dd-neustadt.osm')
#p.parse('dd-neustadt.osm')
p.parse(infile) # 1500
#p.parse('xapi.osm') # fails
#p.parse('xapi-small.osm')
print "done"
#sys.exit(0)
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
