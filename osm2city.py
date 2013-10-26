#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
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

import pdb


# TODO:
# x use geometry library
# x read original .stg+.xml, don't place OSM buildings when there's a static model near/within
# - compute static_object stg's on the fly
# x put roofs into separate LOD
# x lights
# x read relations tag == fix empty backyards
# x simplify buildings
# x put tall, large buildings in LOD bare, and small buildings in LOD detail
# - more complicated roof geometries
#   x split, new roofs.py?
# x cmd line switches
# -

# - city center??

# FIXME:
# - pythonic way of i = 0; for b in refs: bla[i] = b
# - off-by-one error in building counter

# LOWI:
# - floating buildings
# - LOD?
# - rename textures
# x respect ac

# cmd line
# x skip nearby check
# x fake elev
# - log level

# development hints:
# variables
# b: a building instance
#
# coding style
# - indend 4 spaces, avoid tabulators
# - variable names: use underscores (my_long_variable), avoid CamelCase
# - capitalize class names: class Interpolator(object):
# - comments: code # -- comment

import numpy as np
import sys
import os
import random
import copy

from imposm.parser import OSMParser
import shapely.geometry as shg
import osm
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

import parameters

buildings = [] # -- master list, holds all buildings
our_magic = "osm2city"


class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ...
       Read-only access to node coordinates via self.X[node][0|1]
    """
    def __init__(self, osm_id, tags, outer_ring, name, height, levels,
                 stg_typ = None, stg_hdg = None, inner_rings_list = []):
        self.osm_id = osm_id
        self.tags = tags
        #self.outer_ring = outer_ring # (outer) local linear ring
        self.inner_rings_list = inner_rings_list
        self.name = name.encode('ascii', 'ignore')     # stg: name
        self.stg_typ = stg_typ  # stg: OBJECT_SHARED or _STATIC
        self.stg_hdg = stg_hdg
        self.height = height
        self.levels = levels
        self.vertices = 0
        self.surfaces = 0
        self.anchor = vec2d(list(outer_ring.coords[0]))
        self.facade_texture = None
        self.roof_texture = None
        self.roof_complex = False
        self.ac_name = None
        self.ceiling = 0.
        self.outer_nodes_closest = []
        if len(outer_ring.coords) > 2:
            self.set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list: self.roll_inner_nodes()


    def roll_inner_nodes(self):
        """Roll inner rings such that the node closest to an outer node goes first.

           Also, create a list of outer corresponding outer nodes.
        """
        new_inner_rings_list = []
        self.outer_nodes_closest = []
        outer_nodes_avail = range(self.nnodes_outer)
        for inner in self.polygon.interiors:
            min_r = 1e99
            for i, node_i in enumerate(list(inner.coords)[:-1]):
                node_i = vec2d(node_i)
                for o in outer_nodes_avail:
                    r = node_i.distance_to(vec2d(self.X_outer[o]))
                    if r <= min_r:
                        closest_i = node_i
                        min_r = r
                        min_i = i
                        min_o = o
#            print "\nfirst nodes", closest_i, closest_o, r
            new_inner = shg.polygon.LinearRing(np.roll(np.array(inner.coords)[:-1], -min_i, axis=0))
            new_inner_rings_list.append(new_inner)
#            print "NEW", new_inner
#            print "OLD", inner
            self.outer_nodes_closest.append(min_o)
            outer_nodes_avail.remove(min_o)
#            print self.outer_nodes_closest
#        print "---\n\n"
        # -- sort inner rings by index of closest outer node
        yx = sorted(zip(self.outer_nodes_closest, new_inner_rings_list))
        self.inner_rings_list = [x for (y,x) in yx]
        self.outer_nodes_closest = [y for (y,x) in yx]
        self.set_polygon(self.polygon.exterior, self.inner_rings_list)
#        for o in self.outer_nodes_closest:
#            assert(o < len(outer_ring.coords) - 1)

    def simplify(self, tolerance):
        original_nodes = self.nnodes_outer + len(self.X_inner)
        #print ">> outer nodes", b.nnodes_outer
        #print ">> inner nodes", len(b.X_inner)
        #print "total", total_nodes
        #print "now simply"
        self.polygon = self.polygon.simplify(tolerance)
        #print ">> outer nodes", b.nnodes_outer
        #print ">> inner nodes", len(b.X_inner)
        nnodes_simplified = original_nodes - (self.nnodes_outer + len(self.X_inner))
        # FIXME: simplifiy interiors
        #print "now", simple_nodes
        #print "--------------------"
        return nnodes_simplified


    def set_polygon(self, outer, inner = []):
        #ring = shg.polygon.LinearRing(list(outer))
        # make linear rings for inner(s)
        #inner_rings = [shg.polygon.LinearRing(list(i)) for i in inner]
        #if inner_rings:
        #    print "inner!", inner_rings
        self.polygon = shg.Polygon(outer, inner)

    @property
    def X_outer(self):
        return list(self.polygon.exterior.coords)[:-1]

    @property
    def X_inner(self):
        return [coord for interior in self.polygon.interiors for coord in list(interior.coords)[:-1]]


    @property
    def _nnodes_ground(self):  # FIXME: changed behavior. Keep _ until all bugs found
        n = len(self.polygon.exterior.coords) - 1
        for item in self.polygon.interiors:
            n += len(item.coords) - 1
        return n

    @property
    def nnodes_outer(self):
        return len(self.polygon.exterior.coords) - 1

    @property
    def area(self):
        return self.polygon.area

#    def translate(self, offset)
#        shapely.affinity.translate(geom, xoff=0.0, yoff=0.0, zoff=0.0)

        #print "tr X", self.X


#import multiprocessing
class wayExtract(object):
    def __init__(self):
        self.buildings = []
        self.coord_dict = {}
        self.way_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def refs_to_ring(self, refs, inner = False):
        """accept a list of OSM refs, return a linear ring. Also
           fixes face orientation, depending on inner/outer.
        """
        coords = []
        for ref in refs:
                c = self.coord_dict[ref]
                coords.append(tools.transform.toLocal((c.lon, c.lat)))

        #print "before inner", refs
#        print "cord", coords
        ring = shg.polygon.LinearRing(coords)
        # -- outer -> CCW, inner -> not CCW
        if ring.is_ccw == inner:
            ring.coords = list(ring.coords)[::-1]
        return ring

    def make_building_from_way(self, osm_id, tags, refs, inner_ways = []):
#       p = multiprocessing.current_process()
#       print 'running:', p.name, p.pid
        #print "got building", osm_id, tags
        #print "done\n\n"
        if refs[0] == refs[-1]: refs = refs[0:-1] # -- kick last ref if it coincides with first

        _name = ""
        _height = 0.
        _levels = 0
        _layer = 99

        # -- funny things might happen while parsing OSM
        try:
            if 'name' in tags:
                _name = tags['name']
                #print "%s" % _name
                if _name in parameters.SKIP_LIST:
                    print "SKIPPING", _name
                    return False
            if 'height' in tags:
                _height = float(tags['height'].replace('m',''))
            elif 'building:height' in tags:
                _height = float(tags['building:height'].replace('m',''))
            if 'building:levels' in tags:
                _levels = float(tags['building:levels'])
            if 'layer' in tags:
                _layer = int(tags['layer'])

            # -- simple (silly?) heuristics to 'respect' layers
            if _layer == 0: return False
            if _layer < 99 and _height == 0 and _levels == 0:
                _levels = _layer + 2

        #        if len(refs) != 4: return False# -- testing, 4 corner buildings only

            # -- all checks OK: accept building

            # -- make outer and inner rings from refs
            outer_ring = self.refs_to_ring(refs)
            inner_rings_list = []
            for way in inner_ways:
                inner_rings_list.append(self.refs_to_ring(way.refs, inner=True))
        except Exception, reason:
            print "\nFailed to parse building (%s)" % reason, osm_id, tags, refs
            tools.stats.parse_errors += 1
            return False

        self.buildings.append(Building(osm_id, tags, outer_ring, _name, _height, _levels, inner_rings_list = inner_rings_list))

        tools.stats.objects += 1
        if tools.stats.objects % 70 == 0: print tools.stats.objects
        else: sys.stdout.write(".")
        return True

    def relations(self, relations):
        for osm_id, tags, members in relations:
            if tools.stats.objects >= parameters.MAX_OBJECTS:
                return

            if 'building' in tags:
                outer_ways = []
                inner_ways = []
                #print "rel: ", osm_id, tags #, members
                for ref, typ, role in members:
#                    if typ == 'way' and role == 'inner':
                    if typ == 'way':
                        if role == 'outer':
                            for way in self.way_list:
                                if way.osm_id == ref: outer_ways.append(way)
                        elif role == 'inner':
                            for way in self.way_list:
                                if way.osm_id == ref: inner_ways.append(way)

                if outer_ways:
                    #print "len outer ways", len(outer_ways)
                    all_outer_refs = [ref for way in outer_ways for ref in way.refs]
                    all_tags = tags
                    for way in outer_ways:
                        #print "TAG", way.tags
                        all_tags = dict(way.tags.items() + all_tags.items())
                    #print "all tags", all_tags
                    #all_tags = dict([way.tags for way in outer_ways]) # + tags.items())
                    #print "all outer refs", all_outer_refs
                    #dict(outer.tags.items() + tags.items())
                    if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                        print "FIXME: ignoring all but first inner way (%i total) of ID %i" % (len(inner_ways), osm_id)
                        self.make_building_from_way(osm_id,
                                                    all_tags,
                                                    all_outer_refs, [inner_ways[0]])
                    else:
                        self.make_building_from_way(osm_id,
                                                    all_tags,
                                                    all_outer_refs, inner_ways)


                    # -- way could have a 'building' tag, too. Prevent processing this twice.
                    for way in outer_ways:
                        self.way_list.remove(way)


    def ways(self, ways):
        """callback method for ways"""
        for osm_id, tags, refs in ways:
            if tools.stats.objects >= parameters.MAX_OBJECTS: return
            self.way_list.append(osm.Way(osm_id, tags, refs))

    def process_ways(self):
        for way in self.way_list:
            if 'building' in way.tags:
                if tools.stats.objects >= parameters.MAX_OBJECTS: return
                self.make_building_from_way(way.osm_id, way.tags, way.refs)
            elif 'building:part' in way.tags:
                if tools.stats.objects >= parameters.MAX_OBJECTS: return
                self.make_building_from_way(way.osm_id, way.tags, way.refs)
#            elif 'bridge' in way.tags:
#                self.make_bridge_from_way(way.osm_id, way.tags, way.refs)

    def coords(self, coords):
        for osm_id, lon, lat in coords:
            #print '%s %.4f %.4f' % (osm_id, lon, lat)
            self.coord_dict[osm_id] = osm.Coord(lon, lat)
            if lon > self.maxlon: self.maxlon = lon
            if lon < self.minlon: self.minlon = lon
            if lat > self.maxlat: self.maxlat = lat
            if lat < self.minlat: self.minlat = lat


# -----------------------------------------------------------------------------



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
#    out.write("""MATERIAL "" rgb 1   0   0 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n""")
#    out.write("""MATERIAL "" rgb 0   1   0 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n""")
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
def write_xml(fname, LOD_lists, LM_dict, buildings):
    #  -- LOD animation
    xml = open(fname + ".xml", "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % fname)

    # -- lightmap
    #    not all textures have lightmaps yet
    LMs_avail = ['tex/DSCF9495_pow2', 'tex/DSCF9503_noroofsec_pow2', 'tex/LZ_old_bright_bc2', 'tex/DSCF9678_pow2', 'tex/DSCF9710', 'tex/wohnheime_petersburger']

    # FIXME: use Effect/Building? What's the difference?
    for texture in LM_dict.keys():
        if texture.filename in LMs_avail:
#                <lightmap-factor type="float" n="0"><use>/scenery/LOWI/garage[0]/door[0]/position-norm</use></lightmap-factor>
            xml.write(textwrap.dedent("""
            <effect>
              <inherits-from>cityLM</inherits-from>
              <parameters>
                <lightmap-enabled type="int">1</lightmap-enabled>
                <texture n="3">
                  <image>%s_LM.png</image>
                  <wrap-s>repeat</wrap-s>
                  <wrap-t>repeat</wrap-t>
                </texture>
              </parameters>
                  """ % texture.filename))

            for b in LM_dict[texture]:
        #        if name.find("roof") < 0:
                    xml.write("  <object-name>%s</object-name>\n" % b.ac_name)
    #    for name in LOD_lists[1]:
    #        if name.find("roof") < 0:
    #            xml.write("  <object-name>%s</object-name>\n" % name)
            xml.write("</effect>\n")

    # -- put obstruction lights on hi-rise buildings
    for b in buildings:
        if b.levels >= parameters.OBSTRUCTION_LIGHT_MIN_LEVELS:
            Xo = np.array(b.X_outer)
            for i in np.arange(0, b.nnodes_outer, b.nnodes_outer/4.):
                xo = Xo[int(i+0.5), 0] - offset.x
                yo = Xo[int(i+0.5), 1] - offset.y
                zo = b.ceiling + 1.5
                # <path>cursor.ac</path>
                xml.write(textwrap.dedent("""
                <model>
                  <path>Models/Effects/pos_lamp_red_light_2st.xml</path>
                  <offsets>
                    <x-m>%g</x-m>
                    <y-m>%g</y-m>
                    <z-m>%g</z-m>
                    <pitch-deg> 0.00</pitch-deg>
                    <heading-deg>0.0 </heading-deg>
                  </offsets>
                </model>""" % (-yo, xo, zo) ))  # -- I just don't get those coordinate systems.

    # -- LOD animation
    #    no longer use bare (reserved for terrain)
    #    instead use rough, detail, roof
    xml.write(textwrap.dedent("""
    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/bare</max-property>
    """))
    for name in LOD_lists[0]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """    </animation>

    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/rough</max-property>
    """))
    for name in LOD_lists[1]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """    </animation>

    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/detailed</max-property>
    """))
    for name in LOD_lists[2]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """    </animation>

    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/roof</max-property>
    """))
    for name in LOD_lists[3]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """    </animation>

    <animation>
      <type>range</type>
      <min-property>/sim/rendering/static-lod/roof</min-property>
      <max-property>/sim/rendering/static-lod/rough</max-property>
    """))
    for name in LOD_lists[4]:
        xml.write("  <object-name>%s</object-name>\n" % name)
    xml.write(textwrap.dedent(
    """    </animation>

    </PropertyList>
    """))
    xml.close()


# -----------------------------------------------------------------------------
# here we go!
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # -- Parse arguments. Command line overrides config file.
    import argparse
    parser = argparse.ArgumentParser(description="osm2city reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

    if args.e:
        parameters.NO_ELEV = True
    if args.c:
        parameters.OVERLAP_CHECK = False

    parameters.show()

    # -- initialize modules
    tex.init()

    # -- prepare transformation to local coordinates
    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center, hdg = 0))
    print tools.transform.toGlobal(cmin), tools.transform.toGlobal(cmax)

    print "reading elevation data"
    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.xml", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things
    print "height at origin", elev(vec2d(0,0))
    print "origin at ", tools.transform.toGlobal((0,0))

    #tools.write_map('dresden.png', transform, elev, vec2d(minlon, minlat), vec2d(maxlon, maxlat))

    # -- now read OSM data. Either parse OSM xml, or read a previously cached .pkl file
    #    End result is 'buildings', a list of building objects
    pkl_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE + '.pkl'
    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE
    if not parameters.USE_PKL:
        # -- parse OSM, return
        if os.path.exists(pkl_fname):
            print "Existing cache file %s will be overwritten. Continue? (y/n)" % pkl_fname
            if raw_input() != 'y': sys.exit(-1)

        way = wayExtract()
        p = OSMParser(concurrency=parameters.CONCURRENCY, coords_callback=way.coords)
        print "start parsing coords"
        p.parse(osm_fname)
        print "done parsing"
        print "ncords:", len(way.coord_dict)
        print "bounds:", way.minlon, way.minlat, way.maxlon, way.maxlat

        print "start parsing ways and relations"
        p = OSMParser(concurrency=parameters.CONCURRENCY, ways_callback=way.ways)
        p.parse(osm_fname)
        p = OSMParser(concurrency=parameters.CONCURRENCY, relations_callback=way.relations)
        p.parse(osm_fname)
        way.process_ways()
        #tools.stats.print_summary()

        print "nbuildings", len(way.buildings)
        print "done parsing"
        buildings = way.buildings

        # -- cache parsed data. To prevent accidentally overwriting,
        #    write to local dir, while we later read from $PREFIX/buildings.pkl
        fpickle = open(pkl_fname, 'wb')
        cPickle.dump(buildings, fpickle, -1)
        fpickle.close()
    else:
        # -- load list of building objects from previously cached file
        print "Loading %s" % pkl_fname
        fpickle = open(pkl_fname, 'rb')
        buildings = cPickle.load(fpickle)[:parameters.MAX_OBJECTS]
        fpickle.close()

#        newbuildings = []

        print "unpickled %g buildings " % (len(buildings))
        tools.stats.objects = len(buildings)


    # -- debug filter
#    for b in buildings:
#        if b.osm_id == 35336:
#            new_buildings = [b]
#            break
#    buildings = new_buildings

    # -- create (empty) clusters
    lmin = vec2d(tools.transform.toLocal(cmin))
    lmax = vec2d(tools.transform.toLocal(cmax))
    clusters = Clusters(lmin, lmax, parameters.TILE_SIZE)

    if parameters.OVERLAP_CHECK:
        # -- read static/shared objects in our area from .stg(s)
        #    Tiles are assumed to be much larger than clusters.
        #    Loop all clusters, find relevant tile by checking tile_index at center of each cluster.
        #    Then read objects from .stg.
        stgs = []
        static_objects = []
        for cl in clusters:
            center_global = tools.transform.toGlobal(cl.center)
            # center_global = [-4.412768, 48.4463626] # -- debug
            path = calc_tile.directory_name(center_global)
            stg = "%07i.stg" % calc_tile.tile_index(center_global)

            if stg not in stgs:
                stgs.append(stg)
                static_objects.extend(stg_io.read(path, stg, parameters.PREFIX,
                                                  parameters.PATH_TO_SCENERY,
                                                  our_magic))

        print "read %i objects from %i tiles" % (len(static_objects), len(stgs)), stgs
    else:
        static_objects = None

    tools.stats.debug1 = open("debug1.dat", "w")
    tools.stats.debug2 = open("debug2.dat", "w")

    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - TODO: analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    buildings = building_lib.analyse(buildings, static_objects, tools.transform, elev, tex.facades, tex.roofs)

    #tools.write_gp(buildings)

    tools.stats.print_summary()

    # -- now put buildings into clusters
    for b in buildings:
        clusters.append(b.anchor, b)

    building_lib.decide_LOD(buildings)
    clusters.transfer_buildings()

    clusters.write_stats()

    # -- write clusters

    stg_fp_dict = {}    # -- dictionary of stg file pointers

    for cl in clusters:
            nb = len(cl.objects)
            if nb < parameters.CLUSTER_MIN_OBJECTS: continue # skip almost empty clusters

            # -- get cluster center
            offset = cl.center

            # -- count roofs == separate objects
            nroofs = 0
            for b in cl.objects:
                if b.roof_complex: nroofs += 2  # we have 2 different LOD models for each roof

            tile_elev = elev(cl.center)
            center_global = vec2d(tools.transform.toGlobal(cl.center))
            if tile_elev == -9999:
                print "Skipping tile elev = -9999 at", center_global
                continue # skip tile with improper elev
            #print "TILE E", tile_elev

            LOD_lists = []
            LOD_lists.append([]) # bare
            LOD_lists.append([]) # rough
            LOD_lists.append([]) # detail
            LOD_lists.append([]) # roof
            LOD_lists.append([]) # roof-flat

            # -- prepare output path
            if parameters.PATH_TO_OUTPUT:
                path = parameters.PATH_TO_OUTPUT
            else:
                path = parameters.PATH_TO_SCENERY
            path += os.sep + 'Objects' + os.sep + calc_tile.directory_name(center_global) + os.sep
            try:
                os.makedirs(path)
            except OSError:
                pass

            # -- open .ac and write header
            fname = parameters.PREFIX + "city%02i%02i" % (cl.I.x, cl.I.y)
            out = open(path + fname+".ac", "w")
            write_ac_header(out, nb + nroofs)
            for b in cl.objects:
                building_lib.write(b, out, elev, tile_elev, tools.transform, offset, LOD_lists)
            out.close()

            LM_dict = building_lib.make_lightmap_dict(cl.objects)

            # -- write xml
            write_xml(path + fname, LOD_lists, LM_dict, cl.objects)

            # -- write stg
            tile_index = calc_tile.tile_index(center_global)
            stg_fname = path + "%07i.stg" % tile_index
            if not stg_fname in stg_fp_dict:
                stg_io.uninstall_ours(stg_fname, our_magic)
                stg = open(stg_fname, "a")
                stg.write("\n%s\n# do not edit below this line\n#\n" % our_magic)
                stg_fp_dict[stg_fname] = stg
            else:
                stg = stg_fp_dict[stg_fname]

            stg.write("OBJECT_STATIC %s %g %g %1.2f %g\n" % (fname+".xml", center_global.lon, center_global.lat, tile_elev, 0))

    for stg in stg_fp_dict.values():
        stg.close()

    tools.stats.debug1.close()
    tools.stats.debug2.close()
    tools.stats.print_summary()
    print "done. If program does not exit at this point, press CTRL+C."
    sys.exit(0)


# python -m cProfile -s time ./osm2city.py -f ULLL/params.ini -e -c