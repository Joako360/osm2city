#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""read osm file, print 2d view in ac3d format to stdout"""


# TODO:
# - use geometry library
# - read original .stg, don't place OSM buildings when there's a static model near/within
# - fix empty backyards
# - simplify buildings
# - lights
# - put tall, large buildings in LOD bare, and small buildings in LOD detail
# - more complicated roof geometries
# -
# for release
# - respect static models
# - correct stg id
# -

"""
osm2city.py aims at generating 3D city models for FG, using OSM data.
Currently, it generates 3D textured buildings, much like bob.pl.
However, it has a somewhat more advanced texture manager, and comes with a
number of facade/roof textures.

- cluster a number of buildings into a single .ac files
- LOD animation based on building height and area
- terrain elevation probing: places buildings at correct elevation

You should disable random buildings.
"""

# -- new design:
# - parse OSM -> return a list of building objects
# - read relevant stgs
# - analyze buildings
#   - calculate area
#   - location clash with stg static models? drop building
#   - analyze surrounding: similar shaped buildings nearby? will get same texture
#   - set building type, roof type etc
#   - decide LOD
# - write clusters

import pdb

import numpy as np
import sys
import random
import copy

from imposm.parser import OSMParser
import coordinates
import itertools
from cluster import Clusters
import building_lib
#from building_writer import write_building, random_number
from vec2d import vec2d
import textwrap

import textures as tex
import stg_io
import tools

# -- defaults
ground_height = -20

buildings = [] # -- master list, holds all buildings

first = True
tile_size_x=500 # -- our tile size in meters
tile_size_y=500
#infile = 'dd-altstadt.osm'; total_objects = 158
#infile = 'altstadt.osm'; total_objects = 100 # 2172
infile = 'xapi-buildings.osm'; total_objects = 2000 # huge!
#p.parse('xapi.osm') # fails
#p.parse('xapi-small.osm')

#infile = 'map.osm'; total_objects = 216 #
skiplist = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
          "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
          "Residenzschloss Dresden"]


def dist(a,b):
    pass

class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ..."""
    def __init__(self, osm_id, tags, refs, name, height, levels):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.name = name
        self.height = height
        self.levels = levels
        self.area = 0
        global transform
        r = self.refs[0]
        self.anchor = vec2d(transform.toLocal((r.lat, r.lon)))
        self.roof_texture = None

        #print "tr X", self.X

class Coords(object):
    def __init__(self, osm_id, lon, lat):
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat

class wayExtract(object):
    def __init__(self):
        self.buildings = []
        self.coords_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def ways(self, ways):
        """callback method for ways"""
        for osm_id, tags, refs in ways:
            #print nb
            #print "-"*10
            #print tags, refs
            if 'building' in tags:

                #print "got building", osm_id, tags, refs
                #print "done\n\n"
                _name = ""
                _height = 0
                _levels = 0
                if 'name' in tags:
                    _name = tags['name']
                    if _name in skiplist:
                        print "SKIPPING", _name
                        return
                if 'height' in tags:
                    _height = tags['height'].replace('m','')
                elif 'building:height' in tags:
                    _height = tags['building:height'].replace('m','')
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

                #if len(building.refs) != 4: return # -- testing, 4 corner buildings only

                self.buildings.append(building)
#                global stats
                if tools.stats.objects == total_objects: raise ValueError
                tools.stats.objects += 1
                print tools.stats.objects
                #global clusters
                #clusters.append(building.X, building)

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
    # --- need $FGDATA/Nasal/elev.nas and elev.in
    #     hide scenery/Objects/e.... folder
    #     in Nasal console: elev.get()
    #     data gets written to /tmp/elev.xml
    raster(transform, 'elev.in', -20000, -20000, size_x=40000, size_y=40000, step_x=20, step_y=20)
    sys.exit(0)


#sys.exit(0)

def write_map(filename, transform, elev, gmin, gmax):
    lmin = vec2d(transform.toLocal((gmin.x, gmin.y)))
    lmax = vec2d(transform.toLocal((gmax.x, gmax.y)))
    map_z0 = 0.
    elev_offset = elev(vec2d(0,0))

    nx, ny = ((lmax - lmin)/25.).int().list() # 100m raster

    x = np.linspace(lmin.x, lmax.x, nx)
    y = np.linspace(lmin.y, lmax.y, ny)

    u = np.linspace(0., 1., nx)
    v = np.linspace(0., 1., ny)


    out = open("surface.ac", "w")
    out.write(textwrap.dedent("""\
    AC3Db
    MATERIAL "" rgb 1   1    1 amb 1 1 1  emis 0 0 0  spec 0.5 0.5 0.5  shi 64  trans 0
    OBJECT world
    kids 1
    OBJECT poly
    name "surface"
    texture "%s"
    numvert %i
    """ % (filename, nx*ny)))

    for j in range(ny):
        for i in range(nx):
            out.write("%g %g %g\n" % (y[j], (elev(vec2d(x[i],y[j])) - elev_offset), x[i]))

    out.write("numsurf %i\n" % ((nx-1)*(ny-1)))
    for j in range(ny-1):
        for i in range(nx-1):
            out.write(textwrap.dedent("""\
            SURF 0x0
            mat 0
            refs 4
            """))
            out.write("%i %g %g\n" % (i  +j*(nx),     u[i],   v[j]))
            out.write("%i %g %g\n" % (i+1+j*(nx),     u[i+1], v[j]))
            out.write("%i %g %g\n" % (i+1+(j+1)*(nx), u[i+1], v[j+1]))
            out.write("%i %g %g\n" % (i  +(j+1)*(nx), u[i],   v[j+1]))
#            0 0 0
#            1 1 0
#            2 1 1
#            3 0 1
    out.write("kids 0\n")
    out.close()
    #print "OBJECT_STATIC surface.ac"

#write_map('dresden.png', transform, elev, vec2d(50.9697, 13.667), vec2d(51.1285, 13.8936))
#write_map('dresden_fine.png', transform, elev, vec2d(51.029, 13.7061), vec2d(51.0891, 13.7861))

#write_map('altstadt.png', transform, elev, vec2d(51.0317900, 13.7149300), vec2d(51.0583100, 13.7551800))
#sys.exit()
#elev.shift(-elev(vec2d(0,0))) # -- shift to zero height at origin


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

    out.write("AC3Db\n")
#    out.write("%s\n" % mats[random.randint(0,2)])
    out.write(textwrap.dedent(
 """MATERIAL "" rgb 1   1   1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0
    MATERIAL "" rgb 1   0   0 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0
 """))
#    MATERIAL "" rgb 1   1    1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0
#    MATERIAL "" rgb .95 1    1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0
#    MATERIAL "" rgb 1   0.95 1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0
#    MATERIAL "" rgb 1   1    0.95 amb 1 1 1 emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0

    out.write("OBJECT world\nkids %i\n" % nb)

    if 0:
        map_z0 = -1
        out.write(textwrap.dedent("""
        OBJECT poly
        name "rect"
        texture "xapi.png"
        numvert 4
        """))
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
# -- write xml
def write_xml(fname, LOD_lists):
    #    - LOD animation
    xml = open(fname + ".xml", "w")
    xml.write("""<?xml version="1.0"?>

    <PropertyList>
    """)

    xml.write("<path>%s.ac</path>" % fname)
    xml.write("""
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

# -----------------------------------------------------------------------------
# here we go!
# -----------------------------------------------------------------------------

if __name__ == "__main__":

#    global stats
    tools.init()
    tools.stats.print_summary()

    tex.init()
    #print tex.facades
    #print tex.roofs

    elev = tools.Interpolator("elev.xml", fake=False) # -- fake skips actually reading the file, speeding up things
    print "height at origin", elev(vec2d(0,0))
    print "origin at ", transform.toGlobal((0,0))



    # - parse OSM -> return a list of building objects

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

    print "nbuildings", len(way.buildings)
    print "done parsing"
    buildings = way.buildings

    # - read relevant stgs
    static_objects = stg_io.Stg("e013n51/3171138.stg")

    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    #   - decide LOD
    buildings = building_lib.analyse(buildings, static_objects, transform, elev, tex.facades, tex.roofs)

    # -- now put buildings into clusters
    clusters = Clusters(min_, max_, vec2d(2000.,2000.))
    for b in buildings:
        clusters.append(b.anchor, b)
    clusters.stats()
    # - write clusters
    stg = open("city.stg", "w")
    for l in clusters._clusters:
        for cl in l:
            nb = len(cl.objects)
            if not nb: continue

            # -- get cluster center
            offset = cl.center

            tile_elev = elev(cl.center)

            #transform.setOffset((-offset).list())
            center_lat, center_lon = transform.toGlobal((cl.center.x, cl.center.y))

            LOD_lists = []
            LOD_lists.append([])
            LOD_lists.append([])
            LOD_lists.append([])


            # -- open ac and write header
            fname = "city-%04i%04i" % (cl.I.x, cl.I.y)
            out = open(fname+".ac", "w")
            write_ac_header(out, nb)
            for building in cl.objects:
                building_lib.write(building, out, elev, tile_elev, transform, offset, LOD_lists)
            out.close()
            #transform.setOffset((0,0))

            # -- write xml
            write_xml(fname, LOD_lists)

            # -- write stg
            stg.write("OBJECT_STATIC %s %g %g %g %g\n" % (fname+".xml", center_lon, center_lat, tile_elev, 180))
    stg.close()

    print "done writing ac's"

    tools.stats.print_summary()
    tools.stats.out.close()
    sys.exit(0)
