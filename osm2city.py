#!/usr/bin/env python2.7 
# -*- coding: utf-8 -*-
"""
osm2city.py aims at generating 3D city models for FG, using OSM data.
Currently, it generates 3D textured buildings.
However, it has a somewhat more advanced texture manager, and comes with a
number of facade/roof textures.

- cluster a number of buildings into a single .ac files
- LOD animation based on building height and area
- terrain elevation probing: places buildings at correct elevation

You should disable random buildings.
"""

# TODO:
# - FIXME: texture size meters works reversed??
# x one object per tile only. Now drawables 1072 -> 30fps
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

import sys
import os
import re
import xml.sax
import argparse
import logging


import numpy as np
import shapely.geometry as shg

import coordinates
import building_lib
from vec2d import vec2d
import textwrap
import cPickle
import textures as tex
import stg_io2
import tools
import calc_tile
import osmparser
import parameters
import troubleshoot
from pdb import pm
from cluster import Clusters
from numpy.core.numeric import True_
from shapely.geometry.multipoint import MultiPoint
from shapely.geos import TopologicalError, PredicateError
from tools import transform


buildings = []  # -- master list, holds all buildings
OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city


class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ...
       Read-only access to node coordinates via self.X[node][0|1]
    """
    def __init__(self, osm_id, tags, outer_ring, name, height, levels,
                 stg_typ = None, stg_hdg = None, inner_rings_list = [], building_type = 'unknown', roof_type = 'flat'):
        self.osm_id = osm_id
        self.tags = tags
        #self.outer_ring = outer_ring # (outer) local linear ring
        self.inner_rings_list = inner_rings_list
        self.name = name.encode('ascii', 'ignore')     # stg: name
        self.stg_typ = stg_typ  # stg: OBJECT_SHARED or _STATIC
        self.stg_hdg = stg_hdg
        self.height = height
        self.longest_edge_len = 0.
        self.levels = levels
        self.first_node = 0  # index of first node in final OBJECT node list
        #self._nnodes_ground = 0 # number of nodes on ground
        self.anchor = vec2d(list(outer_ring.coords[0]))
        self.facade_texture = None
        self.roof_texture = None
        self.roof_complex = False
        self.roof_separate_LOD = False # May or may not be faster
        self.ac_name = None
        self.ceiling = 0.
        self.LOD = None
        self.outer_nodes_closest = []
        if len(outer_ring.coords) > 2:
            self.set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list: self.roll_inner_nodes()
        self.building_type = building_type
        self.roof_type = roof_type
        self.parent = None


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


class Buildings(object):
    """holds buildings list. Interfaces with OSM hanlder"""
    valid_node_keys = []
#    valid_way_keys = ["building", "building:part", "building:height", "height", "building:levels", "layer"]
    req_way_keys = ["building", "building:part"]
    valid_relation_keys = ["building"]
    req_relation_keys = ["building"]

    def __init__(self):
        self.buildings = []
        self.nodes_dict = {}
        self.node_way_dict = {}
        self.way_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def register_callbacks_with(self, handler):
        handler.register_way_callback(self.process_way, self.req_way_keys)
        handler.register_uncategorized_way_callback(self.store_uncategorzied_way)
        handler.register_relation_callback(self.process_relation, self.req_relation_keys)

#            valid_relation_keys, req_relation_keys)
    def _refs_to_ring(self, refs, inner=False):
        """accept a list of OSM refs, return a linear ring. Also
           fixes face orientation, depending on inner/outer.
        """
        coords = []
        for ref in refs:
                c = self.nodes_dict[ref]
                coords.append(tools.transform.toLocal((c.lon, c.lat)))

        #print "before inner", refs
#        print "cord", coords
        ring = shg.polygon.LinearRing(coords)
        # -- outer -> CCW, inner -> not CCW
        if ring.is_ccw == inner:
            ring.coords = list(ring.coords)[::-1]
        return ring

    def make_way_buildings(self):
        #Converts all the ways into buildings
        def tag_matches(tags, req_tags):
            for tag in tags:
                if tag in req_tags:
                    return True
            return False

        for way in self.way_list:
            if tag_matches(way.tags, self.req_way_keys) and len(way.refs) > 3:
                self._make_building_from_way(way.osm_id, way.tags, way.refs)

    def _make_building_from_way(self, osm_id, tags, refs, inner_ways=[]):
        #Creates a building object from a way
        if refs[0] == refs[-1]:
            refs = refs[0:-1]  # -- kick last ref if it coincides with first

        name = ""
        height = 0.
        levels = 0
        layer = 99
        _building_type = 'unknown'

        # -- funny things might happen while parsing OSM
        try:
            if osm_id in parameters.SKIP_LIST:
                logging.info("SKIPPING OSM_ID %i" % osm_id)
                return False
            if 'name' in tags:
                name = tags['name']
                #print "%s" % _name
                if name in parameters.SKIP_LIST:
                    logging.info("SKIPPING " + name)
                    return False
            if 'height' in tags:
                height = osmparser.parse_length(tags['height'])
            elif 'building:height' in tags:
                height = osmparser.parse_length(tags['building:height'])
            if 'building:levels' in tags:
                levels = float(tags['building:levels'])
            if 'layer' in tags:
                layer = int(tags['layer'])
            if 'roof:shape' in tags:
                _roof_type = tags['roof:shape']
            else:
                _roof_type = parameters.BUILDING_UNKNOWN_ROOF_TYPE
            _building_type = building_lib.mapType(tags)

            # -- simple (silly?) heuristics to 'respect' layers
            if layer == 0: return False
            if layer < 99 and height == 0 and levels == 0:
                levels = layer + 2

        #        if len(refs) != 4: return False# -- testing, 4 corner buildings only

            # -- all checks OK: accept building

            # -- make outer and inner rings from refs
            outer_ring = self._refs_to_ring(refs)
            inner_rings_list = []
            for _way in inner_ways:
                inner_rings_list.append(self._refs_to_ring(_way.refs, inner=True))
        except KeyError, reason:
            logging.error("Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (reason, osm_id, tags, refs))
            tools.stats.parse_errors += 1
            return False
        except Exception, reason:
            logging.error("Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, osm_id, tags, refs))
            tools.stats.parse_errors += 1
            return False

        building = Building(osm_id, tags, outer_ring, name, height, levels, inner_rings_list=inner_rings_list, building_type=_building_type, roof_type=_roof_type)
#        if building.osm_id == 3825399:
#            print building
#
        if parameters.BUILDING_REMOVE_WITH_PARTS:
            for ref in refs:
                # Build a lookup table
                if ref not in self.node_way_dict:
                    way_list_by_ref = []
                else:
                    way_list_by_ref = self.node_way_dict[ref]
                    for cand_building in way_list_by_ref:
                        try:
                            if building.osm_id == cand_building.osm_id:
                                continue
                            if 'building:part' in building.tags and cand_building.polygon.intersection(building.polygon).equals(building.polygon):
                                # Our building:part belongs to the building
                                if(cand_building in self.buildings):
                                    # We don't need it since it'll be replaced by its parts
                                    self.buildings.remove(cand_building)
                                logging.info('Found Building for removing %d' % cand_building.osm_id)
                                building.parent = cand_building
        #                         print cand_building.name
                                break
                        except TopologicalError, reason:
                            logging.warn("Error while checking for intersection %s. This might lead to double buildings ID1 : %d ID2 : %d "%(reason, building.osm_id, cand_building.osm_id))
                        except PredicateError, reason:
                            logging.warn("Error while checking for intersection %s. This might lead to double buildings ID1 : %d ID2 : %d "%(reason, building.osm_id, cand_building.osm_id))
            
                        
    #                     if 'building' in building.tags and building.polygon.intersection(cand_building.polygon).equals(cand_building.polygon):
    #                         print 'Found Building:part'
                way_list_by_ref.append(building)
                self.node_way_dict[ref] = way_list_by_ref
        self.buildings.append(building)

        tools.stats.objects += 1
        # show progress here?
        # if tools.stats.objects % 50 == 0:
        #    logging.info(tools.stats.objects)
        return True

    def store_uncategorzied_way(self, way, nodes_dict):
        """We need uncategorized ways (those without tags) too. They could
           be part of a relation building."""
        self.way_list.append(way)

    def process_way(self, way, nodes_dict):
        """Store ways. These simple buildings will be created only after
           relations have been parsed, to prevent double buildings. Our way
           could be part of a relation building and still have a 'building' tag attached.
        """
        if not self.nodes_dict:
            self.nodes_dict = nodes_dict
        if tools.stats.objects >= parameters.MAX_OBJECTS:
            return
        self.way_list.append(way)

    def process_relation(self, relation):
        """Build relation buildings right after parsing."""
#        print "__________- got relation", relation
#        bla = 0
#        if int(relation.osm_id) == 5789:
#            print "::::::::::::: name", relation.tags['name']
#            bla = 1
        if tools.stats.objects >= parameters.MAX_OBJECTS:
            return

        if 'building' in relation.tags:
            outer_ways = []
            inner_ways = []
#            print "rel: ", relation.osm_id, relation.tags #, members
            for m in relation.members:
#                print "  member", m, m.type_, m.role
#                    if typ == 'way' and role == 'inner':
                if m.type_ == 'way':
                    if m.role == 'outer':
                        for way in self.way_list:
                            if way.osm_id == m.ref: outer_ways.append(way)
                    elif m.role == 'inner':
                        for way in self.way_list:
                            if way.osm_id == m.ref: inner_ways.append(way)

            if outer_ways:
                #print "len outer ways", len(outer_ways)
                all_outer_refs = [ref for way in outer_ways for ref in way.refs]
                all_tags = relation.tags
                for way in outer_ways:
                    #print "TAG", way.tags
                    all_tags = dict(way.tags.items() + all_tags.items())
                #print "all tags", all_tags
                #all_tags = dict([way.tags for way in outer_ways]) # + tags.items())
                #print "all outer refs", all_outer_refs
                #dict(outer.tags.items() + tags.items())
                if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                    print "FIXME: ignoring all but first inner way (%i total) of ID %i" % (len(inner_ways), relation.osm_id)
                    res = self._make_building_from_way(relation.osm_id,
                                                all_tags,
                                                all_outer_refs, [inner_ways[0]])
                else:
                    res = self._make_building_from_way(relation.osm_id,
                                                all_tags,
                                                all_outer_refs, inner_ways)
#                print ":::::mk_build returns", res,
#                if bla:
#                    print relation.tags['name']
                # -- way could have a 'building' tag, too. Prevent processing this twice.
                for _way in outer_ways:
                    if _way in self.way_list:
                        self.way_list.remove(_way)
                    else:
                        logging.error("Outer way (%d) not in list of ways. Building type missing?"%_way.osm_id)
            else:
                logging.info("Skipping relation %i: no outer way." % relation.osm_id)

    def _get_min_max_coords(self):
        for node in self.nodes_dict.values():
            #logging.debug('%s %.4f %.4f', _node.osm_id, _node.lon, _node.lat)
            if node.lon > self.maxlon:
                self.maxlon = node.lon
            if node.lon < self.minlon:
                self.minlon = node.lon
            if node.lat > self.maxlat:
                self.maxlat = node.lat
            if node.lat < self.minlat:
                self.minlat = node.lat

#        cmin = vec2d(self.minlon, self.minlat)
#        cmax = vec2d(self.maxlon, self.maxlat)
#        logging.info("min/max coord" + str(cmin) + " " + str(cmax))

# -----------------------------------------------------------------------------
# -- write xml
def write_xml(path, fname, buildings):
    #  -- LOD animation
    xml = open(path + fname + ".xml", "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % fname)

    # -- lightmap
    #    not all textures have lightmaps yet
    #LMs_avail = ['tex/DSCF9495_pow2', 'tex/DSCF9503_noroofsec_pow2', 'tex/LZ_old_bright_bc2', 'tex/DSCF9678_pow2', 'tex/DSCF9710', 'tex/wohnheime_petersburger']

    # FIXME: use Effect/Building? What's the difference?
    #                <lightmap-factor type="float" n="0"><use>/scenery/LOWI/garage[0]/door[0]/position-norm</use></lightmap-factor>
    if parameters.LIGHTMAP_ENABLE:
        xml.write(textwrap.dedent("""
        <effect>
          <inherits-from>cityLM</inherits-from>
          """))
#                    <parameters>
#            <lightmap-enabled type="int">1</lightmap-enabled>
#            <texture n="3">
#              <image>%s_LM.png</image>
#              <wrap-s>repeat</wrap-s>
#              <wrap-t>repeat</wrap-t>
#            </texture>
#          </parameters>
#              """ % 'tex/atlas_facades
        xml.write("  <object-name>LOD_detail</object-name>\n")
        xml.write("  <object-name>LOD_rough</object-name>\n")
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
      <object-name>LOD_bare</object-name>
    </animation>

    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/rough</max-property>
      <object-name>LOD_rough</object-name>
    </animation>

    <animation>
      <type>range</type>
      <min-m>0</min-m>
      <max-property>/sim/rendering/static-lod/detailed</max-property>
      <object-name>LOD_detail</object-name>
    </animation>


    </PropertyList>
    """))
    xml.close()

#    <animation>
#      <type>range</type>
#      <min-m>0</min-m>
#      <max-property>/sim/rendering/static-lod/roof</max-property>
#      <object-name>LOD_roof</object-name>
#    </animation>

#    <animation>
#      <type>range</type>
#      <min-property>/sim/rendering/static-lod/roof</min-property>
#      <max-property>/sim/rendering/static-lod/rough</max-property>
#      <object-name>LOD_roof_flat</object-name>
#    </animation>



# -----------------------------------------------------------------------------
# here we go!
# -----------------------------------------------------------------------------

if __name__ == "__main__":

    # -- Parse arguments. Command line overrides config file.
    parser = argparse.ArgumentParser(description="osm2city reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    parser.add_argument("-A", "--create-atlas-only", action="store_true", help="create texture atlas and exit")
    parser.add_argument("-a", "--create-atlas", action="store_true", help="create texture atlas")
    parser.add_argument("-u", dest="uninstall", action="store_true", help="uninstall ours from .stg")
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL")
    args = parser.parse_args()

    # -- command line args override paramters

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    
    if args.e:
        parameters.NO_ELEV = True
    if args.c:
        parameters.OVERLAP_CHECK = False

    if args.uninstall:
        logging.info("Uninstalling.")
        files_to_remove = []
        parameters.NO_ELEV = True
        parameters.OVERLAP_CHECK = False

    if args.create_atlas or args.create_atlas_only:
        parameters.CREATE_ATLAS = True

    parameters.show()


    # -- initialize modules

    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()
    center = parameters.get_center_global()

    tools.init(coordinates.Transformation(center, hdg = 0))

    tex.manager.init(create_atlas=parameters.CREATE_ATLAS)
    
    if args.create_atlas_only:
        sys.exit(0)


    logging.info("reading elevation data")
    elev = tools.get_interpolator(fake=parameters.NO_ELEV)
    #elev.write("elev.out.small", 4)
    #sys.exit(0)
    logging.debug("height at origin" + str(elev(vec2d(0,0))))
    logging.debug("origin at " + str(tools.transform.toGlobal((0,0))))

    #tools.write_map('dresden.png', transform, elev, vec2d(minlon, minlat), vec2d(maxlon, maxlat))

    # -- now read OSM data. Either parse OSM xml, or read a previously cached .pkl file
    #    End result is 'buildings', a list of building objects
    pkl_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE + '.pkl'
    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE

    if parameters.USE_PKL and not os.path.exists(pkl_fname):
        logging.warn("pkl file %s not found, will parse OSM file %s instead." % (pkl_fname, osm_fname))
        parameters.USE_PKL = False

    if not parameters.USE_PKL:
        # -- parse OSM, return
        if not parameters.IGNORE_PKL_OVERWRITE and os.path.exists(pkl_fname):
            print "Existing cache file %s will be overwritten. Continue? (y/n)" % pkl_fname
            if raw_input().lower() != 'y':
                sys.exit(-1)

        if parameters.BOUNDARY_CLIPPING:
            border = shg.Polygon(parameters.get_clipping_extent())
        else:
            border = None
        handler = osmparser.OSMContentHandler(valid_node_keys=[], border=border)
        buildings = Buildings()
        buildings.register_callbacks_with(handler)
        source = open(osm_fname)
        logging.info("Reading the OSM file might take some time ...")
        handler.parse(source)

        #tools.stats.print_summary()
        buildings.make_way_buildings()
        buildings._get_min_max_coords()
        cmin = vec2d(buildings.minlon, buildings.minlat)
        cmax = vec2d(buildings.maxlon, buildings.maxlat)
        logging.info("min/max " + str(cmin) + " " + str(cmax))
        buildings = buildings.buildings
        logging.info("parsed %i buildings." % len(buildings))

        # -- cache parsed data. To prevent accidentally overwriting,
        #    write to local dir, while we later read from $PREFIX/buildings.pkl
        fpickle = open(pkl_fname, 'wb')
        cPickle.dump(buildings, fpickle, -1)
        fpickle.close()
    else:
        # -- load list of building objects from previously cached file
        logging.info("Loading %s", pkl_fname)
        fpickle = open(pkl_fname, 'rb')
        buildings = cPickle.load(fpickle)[:parameters.MAX_OBJECTS]
        fpickle.close()

#        newbuildings = []

        logging.info("unpickled %g buildings ", len(buildings))
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
    clusters = Clusters(lmin, lmax, parameters.TILE_SIZE, parameters.PREFIX)

    if parameters.OVERLAP_CHECK:
        # -- read static/shared objects in our area from .stg(s)
        #    FG tiles are assumed to be much larger than our clusters.
        #    Loop all clusters, find relevant tile by checking tile_index at center of each cluster.
        #    Then read objects from .stg.
        stgs = []
        static_objects = []
        for cl in clusters:
            center_global = tools.transform.toGlobal(cl.center)
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)
            stg_fname = calc_tile.construct_stg_file_name(center_global)

            if stg_fname not in stgs:
                stgs.append(stg_fname)
                static_objects.extend(stg_io2.read(path, stg_fname, OUR_MAGIC))

        logging.info("read %i objects from %i tiles", len(static_objects), len(stgs))
    else:
        static_objects = None


    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - TODO: analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    buildings = building_lib.analyse(buildings, static_objects, tools.transform, elev, tex.manager.facades, tex.manager.roofs)
        

    # -- initialize STG_Manager
    if parameters.PATH_TO_OUTPUT:
        path_to_output = parameters.PATH_TO_OUTPUT
    else:
        path_to_output = parameters.PATH_TO_SCENERY
    replacement_prefix = re.sub('[\/]', '_', parameters.PREFIX)        
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)
#     for node in ac_nodes:
#         print node
#         lon, lat = tools.transform.toGlobal(node)
#         e = elev((lon,lat), is_global=True)
#         stg_manager.add_object_shared("Models/Communications/cell-monopole1-75m.xml", vec2d(lon, lat), e, 0)

    #tools.write_gp(buildings)

    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    for b in buildings:
        clusters.append(b.anchor, b)
    building_lib.decide_LOD(buildings)
    clusters.transfer_buildings()

    # -- write clusters
    clusters.write_stats()
    stg_fp_dict = {}    # -- dictionary of stg file pointers
    stg = None  # stg-file object

    for ic, cl in enumerate(clusters):
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
            logging.warning("Skipping tile elev = -9999 at lat %.3f and lon %.3f", center_global.lat, center_global.lon)
            continue # skip tile with improper elev

        #LOD_lists = []
        #LOD_lists.append([])  # bare
        #LOD_lists.append([])  # rough
        #LOD_lists.append([])  # detail
        #LOD_lists.append([])  # roof
        #LOD_lists.append([])  # roof-flat

        # -- incase PREFIX is a path (batch processing)
        replacement_prefix = re.sub('[\/]','_', parameters.PREFIX)
        file_name = replacement_prefix + "city%02i%02i" % (cl.I.x, cl.I.y)
        logging.info("writing cluster %s (%i/%i)" % (file_name, ic, len(clusters)))

        path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, tile_elev, 0)

#        if cl.I.x == 0 and cl.I.y == 0:
        stg_manager.add_object_static('lightmap-switch.xml', center_global, tile_elev, 0)

        if args.uninstall:
            files_to_remove.append(path_to_stg + file_name + ".ac")
            files_to_remove.append(path_to_stg + file_name + ".xml")
        else:
            # -- write .ac and .xml
            building_lib.write(path_to_stg + file_name + ".ac", cl.objects, elev, tile_elev, tools.transform, offset)
            write_xml(path_to_stg, file_name, cl.objects)
            tools.install_files(['cityLM.eff', 'lightmap-switch.xml'], path_to_stg)

    if args.uninstall:
        for f in files_to_remove:
            try:
                os.remove(f)
            except:
                pass
        stg_manager.drop_ours()
        stg_manager.write()
        logging.info("uninstall done.")
        sys.exit(0)

    elev.save_cache()
    stg_manager.write()
    tools.stats.print_summary()
    troubleshoot.troubleshoot(tools.stats)
    logging.info("done.")
    sys.exit(0)


# python -m cProfile -s time ./osm2city.py -f ULLL/params.ini -e -c
