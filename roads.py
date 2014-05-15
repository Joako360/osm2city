#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
"""
import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
from pdb import pm
#import osm
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os


import logging
import osmparser

# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y

class Road(object):
    def __init__(self, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.nodes = []
        for r in refs:
            node = nodes_dict[r]
            self.nodes.append(node)

class Roads(object):
    valid_node_keys = []

    #req_and_valid_keys = {"valid_way_keys" : ["highway"], "req_way_keys" : ["highway"]}
    req_keys = ['highway', 'railway']

    def __init__(self):
        self.roads = []

    def create_from_way(self, way, nodes_dict):
        print "got", way.osm_id,
        for t in way.tags.keys():
            print (t), "=", (way.tags[t])+" ",

        col = None
        if way.tags.has_key('highway'):
            road_type = way.tags['highway']
            if road_type == 'motorway' or road_type == 'motorway_link':
                col = 0
            elif road_type == 'primary':
                col = 1
            elif road_type == 'secondary':
                col = 2
            elif road_type == 'tertiary':
                col = 3
            elif road_type == 'residential':
                col = 4
            elif road_type == 'service':
                col = 5
        elif way.tags.has_key('railway'):
            if way.tags['railway'] == 'rail':
                col = 6

        if col == None:
            print "(rejected)"
            return

        print "(accepted)"
        road = Road(way.osm_id, way.tags, way.refs, nodes_dict)
        road.typ = col
        self.roads.append(road)

    def __len__(self):
        return len(self.roads)

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
    tools.init(transform)

    roads = Roads()

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.create_from_way, **roads.req_and_valid_keys)
    handler.register_way_callback(roads.create_from_way, req_keys=roads.req_keys)
    handler.parse(source)

    logging.info("done.")
    logging.info("Transforming OSM objects to roads")

    logging.info("done.")
    logging.info("ways: %i", len(roads))

    # -- quick test output
    col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
    lw  = [2, 1.5, 1.2, 1, 1, 1, 1]
    if 1:
        for r in roads.roads:
            a = np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:,0], a[:,1], color=col[r.typ], linewidth=lw[r.typ])
            plt.plot(a[:,0], a[:,1], color='w', linewidth=0.2, ls=":")

        plt.axes().set_aspect('equal')
        #plt.show()
        plt.savefig('roads.eps')

    #elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things

class AA(object):
    arglist = {"a":123, "b":22}
    def __init__(self):

        print "per"

def func(e, a=0, b=99):
    print e, a, b

if __name__ == "__main__":
    main()
    if 0:
        a = AA()
        func(1)
        func(1,a=50, b=50)
        func(2, **a.arglist)
