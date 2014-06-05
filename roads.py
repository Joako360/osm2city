#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
- handle intersections
"""
import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
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


        if prio == None:
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return

        #print "(accepted)"
        road = LineObject(self.transform, way.osm_id, way.tags, way.refs, nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.2+0.02*prio+AGL_ofs)
        road.typ = prio
        self.roads.append(road)

    def __len__(self):
        return len(self.roads)

    def write(self, elev):
        ac = ac3d.Writer(tools.stats)

        # -- debug: write individual .ac for every road
        if 0:
            for i, rd in enumerate(self.roads[:]):
                if rd.osm_id != 205546090: continue
                ac = ac3d.Writer(tools.stats)
                obj = ac.new_object('roads_%s' % rd.osm_id, 'bridge.png')

                if not rd.write_to(obj, elev, ac): continue
                #print "write", rd.osm_id
                #ac.center()
                f = open('roads_%i_%03i.ac' % (rd.osm_id, i), 'w')
                f.write(str(ac))
                f.close()
            return

        # -- write roads to ac object, then write obj to file
        obj = ac.new_object('roads', 'bridge.png')
        for rd in self.roads:
            rd.write_to(obj, elev, ac)
        f = open('roads.ac', 'w')
        f.write(str(ac))
        f.close()


def join_ways():
    """join ways that
       - don't make an intersection and
       - are of compatible type
    """
    pass

def find_intersections():
    cand_intersections = []
    for way in ways:
        for ref in way.refs:
            cand_node = nodes[ref]
            if len(cand_node.ways) == 1:
                cand_intersections.append(ref)

def main():
    logging.basicConfig(level=logging.INFO)
    #logging.basicConfig(level=logging.DEBUG)

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

    parameters.show()

    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE

    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center_global = (cmin + cmax)*0.5
    transform = coordinates.Transformation(center_global, hdg = 0)
#    center_global = vec2d(11.38, 47.26)
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
    print "OBJECT_STATIC %s %1.5f %1.5f %1.2f %g\n" % ("road.ac", center_global.lon, center_global.lat, 0, 0)
    if parameters.PATH_TO_OUTPUT:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, center_global)
    else:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)
    stg_fname = calc_tile.construct_stg_file_name(center_global)
    print path+stg_fname


    if 0:
        # -- quick test output
        col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
        lw    = [2, 1.5, 1.2, 1, 1, 1, 1]
        lw_w  = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 1]
        for r in roads.roads:
            a = np.array(r.center.coords)
            #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:,0], a[:,1], color=col[r.typ], linewidth=lw[r.typ])
            plt.plot(a[:,0], a[:,1], color='w', linewidth=lw_w[r.typ], ls=":")

        plt.axes().set_aspect('equal')
        #plt.show()
        plt.savefig('roads.eps')

    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things
    roads.write(elev)

if __name__ == "__main__":
    main()
