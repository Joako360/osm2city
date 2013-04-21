#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""read osm file, print 2d view in ac3d format to stdout"""
#import pdb


# TODO:
# x use geometry library
# x read original .stg+.xml, don't place OSM buildings when there's a static model near/within
# - put roofs into separate LOD
# - lights
# - read relations tag == fix empty backyards
# - simplify buildings
# x put tall, large buildings in LOD bare, and small buildings in LOD detail
# - more complicated roof geometries
# - cmd line switches

# - city center??

# FIXME:
# - pythonic way of i = 0; for b in refs: bla[i] = b
# x x,y = transform(lon, lat)
# x why need hdg=180 in transform? If hdg=0, cluster is broken

# LOWI:
# - floating buildings
# - LOD?
# - rename textures
# x respect ac

# cmd line
# - skip nearby check
# - fake elev
# - log level

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
# development hints:
# variables
# b: a building instance


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
import cPickle

import textures as tex
import stg_io
import tools
import calc_tile

# -- defaults
no_elev = False # -- skip elevation interpolation
#no_elev = True # -- skip elevation interpolation
check_overlap = True # -- check for overlap with static models

if len(sys.argv) > 1:
    no_elev = int(sys.argv[1])
use_pkl = True
#use_pkl = False
buildings = [] # -- master list, holds all buildings

tile_size=1000 # -- our tile size in meters

#infile = 'xapi-buildings.osm'; total_objects = 100000 # huge!
#infile = 'eddc-all.osm'; total_objects = 100000 # huge!
#infile = 'map.osm'; total_objects = 216 #
prefix="LOWI"
infile = prefix + '/buidings-xapi.osm'; total_objects = 5000 # huge!

# devel
check_overlap = False
if False:
    use_pkl = False    #infile = 'dd-altstadt.osm'; total_objects = 158
    #infile = 'map.osm'; total_objects = 216 #
    infile = "dd-altstadt.osm"
    #infile = 'altstadt.osm'; total_objects = 10000 # 2172
    tile_size=2000 # -- our tile size in meters
    #no_elev = True
    prefix = "EDDC"
    check_overlap = False

skiplist = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
          "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
          "Residenzschloss Dresden", "Fernsehturm", "Fernsehturm Dresden"]
#skiplist = []

class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ..."""
    def __init__(self, osm_id, tags, refs, name, height, levels, stg_typ = None, stg_hdg = None):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.name = name.encode('ascii', 'ignore')     # stg: name
        self.stg_typ = stg_typ  # stg: OBJECT_SHARED or _STATIC
        self.stg_hdg = stg_hdg
        self.height = height
        self.levels = levels
        self.area = 0
        self.vertices = 0
        self.surfaces = 0
        global transform
        r = self.refs[0]
        self.anchor = vec2d(transform.toLocal((r.lon, r.lat)))
        self.facade_texture = None
        self.roof_texture = None
        self.ac_name = None

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

                if tools.stats.objects % 70 == 0: print tools.stats.objects
                else: sys.stdout.write(".")
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

if prefix == "EDDC":
    cmin=vec2d(13.63, 50.96)
    cmax=vec2d(13.88, 51.17)
    center = vec2d(13.7467, 51.0377) # -- EDDC

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

if prefix == "LOWI":
    cmin = vec2d(11.16898,47.20837) # -- LOWI
    cmax = vec2d(11.79108,47.38161)
    center = (cmin + cmax)*0.5
#minlon, minlat = 11.32109513, 47.22690253
#maxlon, maxlat = 11.45363857, 47.29885247

transform = coordinates.Transformation(center.list(), hdg = 0)

#min_ = vec2d(transform.toLocal((minlon, minlat)))
#max_ = vec2d(transform.toLocal((maxlon, maxlat)))

#min_ = vec2d(-5000,-4000)
#max_ = vec2d( 5000, 4000)
#origin = coordinates.Position(transform, [], lon, lat)

if 0:
    # --- need $FGDATA/Nasal/elev.nas and elev.in
    #     hide scenery/Objects/e.... folder
    #     in Nasal console: elev.get()
    #     data gets written to /tmp/elev.xml
    raster(transform, 'elev.in', -20000, -20000, size_x=40000, size_y=40000, step_x=20, step_y=20)
    sys.exit(0)

print transform.toGlobal(cmin.list()), transform.toGlobal(cmax.list())


#write_map('dresden.png', transform, elev, vec2d(50.9697, 13.667), vec2d(51.1285, 13.8936))
#write_map('dresden_fine.png', transform, elev, vec2d(51.029, 13.7061), vec2d(51.0891, 13.7861))

#write_map('altstadt.png', transform, elev, vec2d(51.0317900, 13.7149300), vec2d(51.0583100, 13.7551800))
#sys.exit()
#elev.shift(-elev(vec2d(0,0))) # -- shift to zero height at origin



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
    out.write("""MATERIAL "" rgb 1   1   1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n""")
    out.write("""MATERIAL "" rgb 1   0   0 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n""")
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
def write_xml(fname, LOD_lists, LM_dict):
    #  -- LOD animation
    xml = open(fname + ".xml", "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % fname)

    # -- lightmap
    #    not all textures have lightmaps yet
    LMs_avail = ['tex/DSCF9495_pow2', 'tex/DSCF9503_noroofsec_pow2', 'tex/LZ_old_bright_bc2']

    # FIXME: use Effect/Building? What's the difference?
    for texture in LM_dict.keys():
#        print texture.filename
#        print LMs_avail
        if texture.filename in LMs_avail:
            xml.write(textwrap.dedent("""
            <effect>
              <inherits-from>Effects/model-combined-deferred</inherits-from>
              <parameters>
                <lightmap-enabled type="int">1</lightmap-enabled>
                <texture n="3">
                  <image>%s_LM.png</image>
                  <wrap-s>repeat</wrap-s>
                </texture>
                <lightmap-factor type="float" n="0">1.0</lightmap-factor>
              </parameters>
                  """ % texture.filename))
    #          <image>tex/LZ_old_bright_bc2_LM.png</image>
    #          <image>tex/DSCF9495_rect_seamless_LM.png</image>
    #          <image>LOWI_studenthouse_panorama_LM.png</image>
    #        <lightmap-color type="vec3d" n="0"> 0.3 0.3 0.3 </lightmap-color>
    #        <lightmap-color type="vec3d" n="1"> 1.0 1.0 1.0 </lightmap-color>
    #        <lightmap-factor type="float" n="0"><use>/scenery/LOWI/garage[0]/door[0]/position-norm</use></lightmap-factor>
    #        <lightmap-factor type="float" n="0">1.0</lightmap-factor>
    #        <lightmap-factor type="float" n="1">1.0</lightmap-factor>
    #        <lightmap-factor type="float" n="2">1.0</lightmap-factor>
    #

            for b in LM_dict[texture]:
        #        if name.find("roof") < 0:
                    xml.write("  <object-name>%s</object-name>\n" % b.ac_name)
    #    for name in LOD_lists[1]:
    #        if name.find("roof") < 0:
    #            xml.write("  <object-name>%s</object-name>\n" % name)
            xml.write("</effect>\n")


    # -- LOD animation
    xml.write(textwrap.dedent("""
    <animation>
      <type>range</type>
    """))
    for name in LOD_lists[0]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/bare</max-property>
    </animation>

    <animation>
      <type>range</type>
    """))
    for name in LOD_lists[1]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/rough</max-property>
    </animation>

    <!--
    <animation>
      <type>range</type>
    """))
    for name in LOD_lists[2]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent("""
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/detailed</max-property>
    </animation>
    -->
    </PropertyList>
    """))
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

    print "reading elevation data"
    elev = tools.Interpolator(prefix + "/elev.xml", fake=no_elev) # -- fake skips actually reading the file, speeding up things
    print "height at origin", elev(vec2d(0,0))
    print "origin at ", transform.toGlobal((0,0))

    #tools.write_map('dresden.png', transform, elev, vec2d(minlon, minlat), vec2d(maxlon, maxlat))


    if not use_pkl:
        # - parse OSM -> return a list of building objects
        way = wayExtract()
        #p = OSMParser(concurrency=4, ways_callback=way.ways, coords_callback=way.coords )
        p = OSMParser(concurrency=1, coords_callback=way.coords)
        print "start parsing coords"
        p.parse(infile)
        print "done parsing"
        print "ncords:", len(way.coords_list)
        print "bounds:", way.minlon, way.minlat, way.maxlon, way.maxlat

        p = OSMParser(concurrency=1, ways_callback=way.ways)
        print "start parsing ways"
        try:
            p.parse(infile)
        except ValueError:
            pass

        tools.stats.print_summary()

        print "nbuildings", len(way.buildings)
        print "done parsing"
        buildings = way.buildings

        # -- pickle here
        fpickle = open('data.pkl', 'wb')
        cPickle.dump(buildings, fpickle, -1)
        fpickle.close()
    else:
        fpickle = open(prefix + '/buildings.pkl', 'rb')
        buildings = cPickle.load(fpickle)[:total_objects]
        fpickle.close()
        print "unpickled %g buildings " % (len(buildings))
        tools.stats.objects = len(buildings)


    # - read relevant stgs
    #static_objects = stg_io.Stg(["e013n51/3171138.stg", "e013n51/3171139.stg"])
    if check_overlap:
        static_objects = stg_io.Stg(["e011n47/3138129.stg"])
    else:
        static_objects = None
    tools.stats.debug1 = open("debug1.dat", "w")
    tools.stats.debug2 = open("debug2.dat", "w")

    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    #   - decide LOD
    buildings = building_lib.analyse(buildings, static_objects, transform, elev, tex.facades, tex.roofs, prefix+"city")

    tools.stats.print_summary()

    # -- now put buildings into clusters
    lmin = vec2d(transform.toLocal(cmin.list()))
    lmax = vec2d(transform.toLocal(cmax.list()))
    clusters = Clusters(lmin, lmax, tile_size)
    for b in buildings:
        #print "an ", b.anchor
        clusters.append(b.anchor, b)

    building_lib.decide_LOD(buildings)
    clusters.transfer_buildings()

    clusters.write_stats()
    # - write clusters

    stg_fp_dict = {}    # -- dictionary of stg file pointers

    for l in clusters._clusters:  # two loops here because '2d-array': list of lists
        for cl in l:
            nb = len(cl.objects)
            if nb < 5: continue # skip almost empty clusters

            # -- get cluster center
            offset = cl.center

#            print "\ncl offset", offset
#            for b in cl.objects:
                #print (b.anchor - offset), "    ", b.anchor


            tile_elev = elev(cl.center)
            if tile_elev == -9999:
                print "Skipping tile elev = -9999"
                continue # skip tile with improper elev
            #print "TILE E", tile_elev

            center_lon, center_lat = transform.toGlobal((cl.center.x, cl.center.y))

            LOD_lists = []
            LOD_lists.append([])
            LOD_lists.append([])
            LOD_lists.append([])

            # -- open ac and write header
            fname = prefix+"city%02i%02i" % (cl.I.x, cl.I.y)
            out = open(fname+".ac", "w")
            write_ac_header(out, nb)
            for b in cl.objects:
                building_lib.write(b, out, elev, tile_elev, transform, offset, LOD_lists)
            out.close()

            LM_dict = building_lib.make_lightmap_dict(cl.objects)

            # -- write xml
            write_xml(fname, LOD_lists, LM_dict)

            # -- write stg
            tile_index = calc_tile.tile_index(center_lon, center_lat)
            stg_fname = "%07i.stg" % tile_index
            if not stg_fname in stg_fp_dict:
                stg = open(stg_fname, "w")
                stg.write("# osm2city\n#\n")
                stg_fp_dict[stg_fname] = stg
            else:
                stg = stg_fp_dict[stg_fname]

            stg.write("OBJECT_STATIC %s %g %g %g %g\n" % (fname+".xml", center_lon, center_lat, tile_elev, 0))

    for stg in stg_fp_dict.values():
        stg.close()

    tools.stats.debug1.close()
    tools.stats.debug2.close()
    tools.stats.print_summary()
    print "done."
    sys.exit(0)
