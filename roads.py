#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
- clusterize
- LOD
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

required graph functions:
- find neighbours
-
"""

import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import textwrap
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os
import ac3d
from linear import LinearObject
from linear_bridge import LinearBridge

import logging
import osmparser
import stg_io2
import objectlist

# debug stuff
from pdb import pm

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark edits by osm2platforms

# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y

class Road(LinearObject):
    """ATM unused"""
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        super(Road, self).__init__(transform, osm_id, tags, refs, nodes_dict)
        self.railway = False
        if tags.has_key('railway'):
            self.railway = tags['railway'] in ['rail', 'tram']

class Roads(objectlist.ObjectList):
    valid_node_keys = []

    #req_and_valid_keys = {"valid_way_keys" : ["highway"], "req_way_keys" : ["highway"]}
    req_keys = ['highway', 'railway']

    def __init__(self, transform, elev):
        super(Roads, self).__init__(transform)
        self.elev = elev
        self.bridges = []

    def store_uncategorized(self, way, nodes_dict):
        pass

    def create_from_way(self, way, nodes_dict):
        """take one osm way, create a linear object"""
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)
            logging.info("len of nodes_dict %i" % len(nodes_dict))
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

        width = 9
        tex_y0 = 0.5
        tex_y1 = 0.75
        AGL_ofs = 0.
        #if way.tags.has_key('layer'):
        #    AGL_ofs = 20.*float(way.tags['layer'])
        #print way.tags
        #bla

        if 'highway' in way.tags:
            road_type = way.tags['highway']
            if road_type == 'motorway' or road_type == 'motorway_link':
                prio = 5
            elif road_type == 'primary' or road_type == 'trunk':
                prio = 4
            elif road_type == 'secondary':
                prio = 3
            elif road_type == 'tertiary' or road_type == 'unclassified':
                prio = 2
            elif road_type == 'residential':
                prio = 1
            elif road_type == 'service' and access:
                prio = None
        elif 'railway' in way.tags:
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
        is_bridge = "bridge" in way.tags
        if is_bridge:
            road = LinearBridge(self.transform, self.elev, way.osm_id, way.tags, way.refs, nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
            self.bridges.append(road)
        else:
            road = LinearObject(self.transform, way.osm_id, way.tags, way.refs, nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)

        road.typ = prio
        self.objects.append(road)

    def create_ac(self):
        ac = ac3d.Writer(tools.stats, show_labels=False)

        # -- debug: write individual .ac for every road
        if 0:
            for i, rd in enumerate(self.objects[:]):
                if rd.osm_id != 205546090: continue
                ac = ac3d.Writer(tools.stats, show_labels=False)
                obj = ac.new_object('roads_%s' % rd.osm_id, 'tex/roads.png')

                if not rd.write_to(obj, self.elev, ac): continue
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
        for rd in self.objects:
            rd.write_to(obj, self.elev, ac)

        if 0:
            for ref in self.intersections:
                node = self.nodes_dict[ref]
                x, y = self.transform.toLocal((node.lon, node.lat))
                e = self.elev(vec2d(x, y)) + 5
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
        self.attached_ways = {} # a dict: for each node hold a list of attached ways
        for road in self.objects:
            for ref in road.refs:
                try:
                    self.attached_ways[ref].append(road)
                    if len(self.attached_ways[ref]) == 2:
                        # -- check if ways are actually distinct before declaring
                        #    an intersection?
                        # not an intersection if
                        # - only 2 ways && one ends && other starts
                        # easier?: only 2 ways, at least one node is middle node
                        self.intersections.append(ref)
                except KeyError:
                    self.attached_ways[ref] = [road]  # initialize node
        logging.info('Done.')

        if 0:
            for key, value in self.attached_ways.items():
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
    p0 = vec2d(transform.toGlobal((0, 0)))
    p100 = vec2d(transform.toGlobal((100, 0)))
    p1k = vec2d(transform.toGlobal((1000, 0)))
    p10k = vec2d(transform.toGlobal((10000, 0)))
#    BLA
    e0 = elev(p0, is_global=True)
    e100 = elev(p100, is_global=True)
    e1k = elev(p1k, is_global=True)
    e10k = elev(p10k, is_global=True)
    stg_io2.quick_stg_line('cursor/cursor_blue.ac', p0, e0, 0, show=3)
    stg_io2.quick_stg_line('cursor/cursor_red.ac', p100, e100, 0, show=2)
    stg_io2.quick_stg_line('cursor/cursor_red.ac', p1k, e1k, 0, show=2)
    stg_io2.quick_stg_line('cursor/cursor_red.ac', p10k, e10k, 0, show=2)

    p0 = vec2d(transform.toGlobal((0, 0)))
    p1 = vec2d(transform.toGlobal((1., 0)))
    print p0, p1


def write_xml(path_to_stg, file_name, object_name):
    xml = open(path_to_stg + file_name + '.xml', "w")
    if parameters.TRAFFIC_SHADER_ENABLE:
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
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

    if args.e:
        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    #parameters.show()

    center_global = parameters.get_center_global()
    osm_fname = parameters.get_OSM_file_name()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    elev = tools.get_interpolator(fake=parameters.NO_ELEV)
    roads = Roads(transform, elev)
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
        path_to_output = parameters.PATH_TO_OUTPUT
    else:
        path_to_output = parameters.PATH_TO_SCENERY

    if 0:
        # -- quick test output
        col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
        col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
        lw    = [1, 1, 1, 1.2, 1.5, 2, 1]
        lw_w  = [1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
        for r in roads:
            a = np.array(r.center.coords)
            #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:,0], a[:,1], color=col[r.typ], linewidth=lw[r.typ])
            plt.plot(a[:,0], a[:,1], color='w', linewidth=lw_w[r.typ], ls=":")

        plt.axes().set_aspect('equal')
        #plt.show()
        plt.savefig('roads.eps')
        plt.clf()

    #roads.objects = roads.objects[0:10000]

    #roads.find_intersections()
    #roads.cleanup_intersections()
#    roads.objects = [roads.objects[0]]

#    scale_test(transform, elev)

    logging.info("done.")
    logging.info("ways: %i", len(roads))

    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, overwrite=True)

    # -- write stg
    ac = roads.create_ac()

    file_name = 'roads%07i' % calc_tile.tile_index(center_global)
    path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, 0, 0)
    stg_manager.write()

    # TODO: write roads xml
#    f = open(path_to_stg + ac_file_name + '.ac', 'w')
#    f.write(str(ac))
#    f.close()
    ac.write_to_file(path_to_stg + file_name)
    write_xml(path_to_stg, file_name, 'roads')
    logging.info('Done.')
#     elev.save_cache()


if __name__ == "__main__":
    main()
