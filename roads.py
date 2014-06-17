#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
- handle intersections
- handle layers/bridges

Intersections:
- currently, we get false positives: one road ends, another one begins.
- loop intersections:
    for the_node in nodes:
    if the_node is not endpoint: put way into splitting list
    #if only 2 nodes, and both end nodes, and road types compatible:
    #put way into joining list

Render intersection:
  if 2 ways:
    simply join here. Or ignore for now.
  else:
      for the_way in ways:
        left_neighbor = compute from angles and width
        store end nodes coords separately
        add to object, get node index
        - store end nodes index in way
        - way does not write end node coords, central method does it
      write intersection face

Splitting:
  find all intersections for the_way
  normally a way would have exactly two intersections (at the ends)
  sort intersections in way's node order:
    add intersection node index to dict
    sort list
  split into nintersections-1 ways
Now each way's end node is either intersection or dead-end.

Joining:

"""

import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
import textwrap
from pdb import pm
#import pdb
#import osm
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os
import ac3d
from linear import LineObject

import logging
import osmparser
import stg_io2

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark edits by osm2platforms

# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y

class Road(LineObject):
    """ATM unused"""
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        super(Road, self).__init__(transform, osm_id, tags, refs, nodes_dict)
        self.railway = False
        if tags.has_key('railway'):
            self.railway = tags['railway'] in ['rail', 'tram']

class Roads(object):
    valid_node_keys = []

    #req_and_valid_keys = {"valid_way_keys" : ["highway"], "req_way_keys" : ["highway"]}
    req_keys = ['highway', 'railway']

    def __init__(self, transform):
        self.roads = []
        self.transform = transform
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.
        self.min_max_scanned = False

    def _process_nodes(self, nodes):
        self.nodes_dict = nodes
        for node in nodes.values():
            #logging.debug('%s %.4f %.4f', node.osm_id, node.lon, node.lat)
            #self.coord_dict[node.osm_id] = node
            if node.lon > self.maxlon:
                self.maxlon = node.lon
            if node.lon < self.minlon:
                self.minlon = node.lon
            if node.lat > self.maxlat:
                self.maxlat = node.lat
            if node.lat < self.minlat:
                self.minlat = node.lat
        logging.debug("")

    def store_uncategorized(self, way, nodes_dict):
        pass

    def create_from_way(self, way, nodes_dict):
        """take one osm way, create a linear object"""
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)
            self.min_max_scanned = True
            cmin = vec2d(self.minlon, self.minlat)
            cmax = vec2d(self.maxlon, self.maxlat)
            logging.info("min/max " + str(cmin) + " " + str(cmax))
#            center_global = (cmin + cmax)*0.5
            #center_global = vec2d(1.135e1+0.03, 0.02+4.724e1)
            #self.transform = coordinates.Transformation(center_global, hdg = 0)
            #tools.init(self.transform) # FIXME. Not a nice design.

        prio = None
        try:
            access = not (way.tags['access'] == 'no')
        except:
            access = 'yes'

        width=9
        tex_y0=0.5
        tex_y1=0.75
        AGL_ofs = 0.
        #if way.tags.has_key('layer'):
        #    AGL_ofs = 20.*float(way.tags['layer'])
        if way.tags.has_key('highway'):
            road_type = way.tags['highway']
            if road_type == 'motorway' or road_type == 'motorway_link':
                prio = 5
            elif road_type == 'primary':
                prio = 4
            elif road_type == 'secondary':
                prio = 3
            elif road_type == 'tertiary':
                prio = 2
            elif road_type == 'residential':
                prio = 1
            elif road_type == 'service' and access:
                prio = None
        elif way.tags.has_key('railway'):
            if way.tags['railway'] in ['rail']:
                prio = 6
                width = 2.87
                tex_y0 = 0
                tex_y1 = 0.25

        if prio in [1, 2]:
            tex_y0 = 0.25
            tex_y1 = 0.5
            width=6

        if prio == None:
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return

        #print "(accepted)"
        road = LineObject(self.transform, way.osm_id, way.tags, way.refs, nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
        road.typ = prio
        self.roads.append(road)

    def __len__(self):
        return len(self.roads)

    def create_ac(self, elev):
        ac = ac3d.Writer(tools.stats, show_labels=False)

        # -- debug: write individual .ac for every road
        if 0:
            for i, rd in enumerate(self.roads[:]):
                if rd.osm_id != 205546090: continue
                ac = ac3d.Writer(tools.stats)
                obj = ac.new_object('roads_%s' % rd.osm_id, 'tex/roads.png')

                if not rd.write_to(obj, elev, ac): continue
                #print "write", rd.osm_id
                #ac.center()
                f = open('roads_%i_%03i.ac' % (rd.osm_id, i), 'w')
                f.write(str(ac))
                f.close()
            return

        # -- create ac object, then write obj to file
        # TODO: try emis for night lighting? Didnt look too bad, and gave better range
        # MATERIAL "" rgb 1 1 1 amb 1 1 1 emis 0.4 0.2 0.05 spec 0.5 0.5 0.5 shi 64 trans 0

        obj = ac.new_object('roads', 'tex/roads.png', default_swap_uv=True)
        for rd in self.roads:
            rd.write_to(obj, elev, ac)

        for ref in self.intersections:
            node = self.nodes_dict[ref]
            x, y = self.transform.toLocal((node.lon, node.lat))
            e = elev(vec2d(x, y)) + 5
            ac.add_label('I', -y, e, -x, scale=10)

        return ac

    def find_intersections(self):
        """
        find intersections by brute force:
        - for each node, store attached ways in a dict
        - if a node has 2 ways, store that node as a candidate
        FIXME: use quadtree/kdtree
        """
        logging.info('Finding intersections...')
        self.intersections = []
        attached_ways = {} # a dict: for each node hold a list of attached ways
        for road in self.roads:
            for ref in road.refs:
                try:
                    attached_ways[ref].append(road)
                    if len(attached_ways[ref]) == 2:
                        # -- check if ways are actually distinct before declaring
                        #    an intersection?
                        # not an intersection if
                        # - only 2 ways && one ends && other starts
                        # easier?: only 2 ways, at least one node is middle node
                        self.intersections.append(ref)
                except KeyError:
                    attached_ways[ref] = [road]  # initialize node
        logging.info('Done.')

        if 0:
            for key, value in attached_ways.items():
                if len(value) > 1:
                    print key
                    for way in value:
                        try:
                            print "  ", way.tags['name']
                        except:
                            print "  ", way

    def cleanup_intersections(self):
        """Remove intersections that
           - have less than 3 ways attached
        """
        pass


    def join_ways(self):
        """join ways that
           - don't make an intersection and
           - are of compatible type
        """
        pass

def quick_stg_line(ac_fname, position, elevation, heading, show=True):
    stg_path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, position)
    stg_fname = calc_tile.construct_stg_file_name(position)
    stg_line = "OBJECT_STATIC %s %1.7f %1.7f %1.2f %g\n" % (ac_fname, position.lon, position.lat, elevation, heading)
    if show == 1 or show == 3:
        print stg_path + stg_fname
    if show == 2 or show == 3:
         print stg_line
#        print "%s\n%s" % (stg_path + stg_fname, stg_line)
    return stg_path, stg_fname, stg_line

def scale_test(transform, elev):
    pass
    """
    put 4 objects into scenery
    2 poles 1000m apart. Two ac, origin same, but one is offset in ac. Put both
    at same location in stg
    2 acs, at different stg location
    Result: at 100m 35 cm difference
            at 1000m 3.5m
            0.35%
    """
    p0 = vec2d(transform.toGlobal((0,0)))
    p100 = vec2d(transform.toGlobal((100,0)))
    p1k = vec2d(transform.toGlobal((1000,0)))
    p10k = vec2d(transform.toGlobal((10000,0)))
#    BLA
    e0 = elev(p0, is_global=True)
    e100 = elev(p100, is_global=True)
    e1k = elev(p1k, is_global=True)
    e10k = elev(p10k, is_global=True)
    quick_stg_line('cursor/cursor_blue.ac', p0, e0, 0, show=3)
    quick_stg_line('cursor/cursor_red.ac', p100, e100, 0, show=2)
    quick_stg_line('cursor/cursor_red.ac', p1k, e1k, 0, show=2)
    quick_stg_line('cursor/cursor_red.ac', p10k, e10k, 0, show=2)

    p0 = vec2d(transform.toGlobal((0, 0)))
    p1 = vec2d(transform.toGlobal((1., 0)))
    print p0, p1


def write_xml(path_to_stg, file_name, object_name):
    xml = open(path_to_stg + file_name + '.xml', "w")
    if 0:  # parameters.TRAFFIC_SHADER_ENABLE:
        shader_str = "<inherits-from>Effects/road-high</inherits-from>"
    else:
        shader_str = "<inherits-from>roads</inherits-from>"
    xml.write(textwrap.dedent("""        <?xml version="1.0"?>
        <PropertyList>
        <path>%s.ac</path>
        <effect>
        <!--
            EITHER enable the traffic shader
                <inherits-from>Effects/road-high</inherits-from>
            OR the lightmap shader
                <inherits-from>roads</inherits-from>
        -->
                %s
                <object-name>%s</object-name>
        </effect>
        </PropertyList>
    """  % (file_name, shader_str, object_name)))


def main():
    #logging.basicConfig(level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser(description="bridge.py reads OSM data and creates bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
#    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

#    if args.e:
#        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    #parameters.show()

    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE

    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center_global = (cmin + cmax)*0.5
    center_global = vec2d(11.38, 47.26)
    transform = coordinates.Transformation(center_global, hdg = 0)
    tools.init(transform)
    roads = Roads(transform)

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.from_way, **roads.req_and_valid_keys)
#    roads.register_callbacks_in(handler)
    handler.register_way_callback(roads.create_from_way, req_keys=roads.req_keys)
    handler.register_uncategorized_way_callback(roads.store_uncategorized)
    handler.parse(source)

    logging.info("done.")
    logging.info("ways: %i", len(roads))

    if parameters.PATH_TO_OUTPUT:
        path_to_scenery = parameters.PATH_TO_OUTPUT
    else:
        path_to_scenery = parameters.PATH_TO_SCENERY

    if 1:
        # -- quick test output
        col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
        col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
        lw    = [1, 1, 1, 1.2, 1.5, 2, 1]
        lw_w  = [1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
        for r in roads.roads:
            a = np.array(r.center.coords)
            #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:,0], a[:,1], color=col[r.typ], linewidth=lw[r.typ])
            plt.plot(a[:,0], a[:,1], color='w', linewidth=lw_w[r.typ], ls=":")

        plt.axes().set_aspect('equal')
        #plt.show()
        plt.savefig('roads.eps')

    roads.find_intersections()
    roads.cleanup_intersections()

    #elev = tools.Probe_fgelev(fake=False, auto_save_every=1000)
    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things
#    scale_test(transform, elev)

    logging.info("done.")
    logging.info("ways: %i", len(roads))

    stg_manager = stg_io2.STG_Manager(path_to_scenery, OUR_MAGIC, uninstall=True)

    # -- write stg
    ac = roads.create_ac(elev)
    file_name = 'roads%07i' % calc_tile.tile_index(center_global)
    path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, 0, 0)
    stg_manager.write()

    # TODO: write roads xml
#    f = open(path_to_stg + ac_file_name + '.ac', 'w')
#    f.write(str(ac))
#    f.close()
    ac.write_to_file(path_to_stg + file_name)
    write_xml(path_to_stg, file_name, 'roads')
    #elev.save_cache()


if __name__ == "__main__":
    main()
