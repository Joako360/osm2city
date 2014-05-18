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
import ac3d

import logging
import osmparser

# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y

class Road(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.nodes = []

#    def transform(self, nodes_dict, transform):
        osm_nodes = [nodes_dict[r] for r in refs]
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        #self.nodes = np.array([(n.lon, n.lat) for n in osm_nodes])
        self.line_string = shg.LineString(self.nodes)


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

    def create_from_way(self, way, nodes_dict):

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
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return

        #print "(accepted)"
        road = Road(self.transform, way.osm_id, way.tags, way.refs, nodes_dict)
        road.typ = col
        self.roads.append(road)

    def __len__(self):
        return len(self.roads)

    def write(self, elev):
        ac = ac3d.Writer(tools.stats)
        obj = ac.new_object('roads', 'bridge.png')
        for rd in self.roads[:]:
            left  = rd.line_string.parallel_offset(3, 'left', resolution=16, join_style=1, mitre_limit=10.0)
            right = rd.line_string.parallel_offset(3, 'right', resolution=16, join_style=1, mitre_limit=10.0)
            o = obj.next_node_index()
            #face = np.zeros((len(left.coords) + len(right.coords)))
            try:
                do_tex = True
                len_left = len(left.coords)
                len_right = len(right.coords)

                if len_left != len_right:
                    print "different lengths not yet implemented ", rd.osm_id
                    do_tex = False
                    #continue
                if len_left != len(rd.line_string.coords):
                    print "WTF? ", rd.osm_id
                    do_tex = False
                    #continue
                #if len_left != 3: continue


                for p in left.coords:
                    e = elev(vec2d(p[0], p[1])) + 1
                    obj.node(-p[1], e, -p[0])
                for p in right.coords:
                    e = elev(vec2d(p[0], p[1])) + 1
                    obj.node(-p[1], e, -p[0])
                #refs = np.arange(len_left + len_right) + o
                nodes_l = np.arange(len(left.coords))
                nodes_r = np.arange(len(right.coords))
                rd.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(rd.line_string.coords[i])) for i, coord in enumerate(rd.line_string.coords[1:])])
                rd_len = len(rd.line_string.coords)
                rd.dist = np.zeros((rd_len))
                for i in range(1, rd_len):
                    rd.dist[i] = rd.dist[i-1] + rd.segment_len[i]

                face = []
                scale = 20.
                x = 0.
                for i, n in enumerate(nodes_l):
                    #face.append((r+o, 0, 0))
                    if do_tex: x = rd.dist[i]/scale
                    face.append((n+o, x, 0.5))
                o += len(left.coords)

                for i, n in enumerate(nodes_r):
                    if do_tex: x = rd.dist[-i-1]/scale
                    #x = 0
                    #face.append((r+o, 0, 0))
                    face.append((n+o, x, 0.75))
                #face = [(r, 0, 0) for r in refs[0:len_left]]
                obj.face(face[::-1], mat=1)
            except NotImplementedError:
                print "error in osm_id", rd.osm_id

#            print rd.dist
#            print rd.segment_len
#            break

        f = open('roads.ac', 'w')

        f.write(str(ac))
        f.close()

            #obj.node()


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

#    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
#    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
#    center_global = (cmin + cmax)*0.5
#    transform = coordinates.Transformation(center_global, hdg = 0)
    center_global = vec2d(11.38, 47.26)
    transform = coordinates.Transformation(center_global, hdg = 0)
    tools.init(transform)
    roads = Roads(transform)

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.create_from_way, **roads.req_and_valid_keys)
#    roads.register_callbacks_in(handler)
    handler.register_way_callback(roads.create_from_way, req_keys=roads.req_keys)
    handler.parse(source)

    #transform = tools.transform
    #center_global =  vec2d(transform.toGlobal(vec2d(0,0)))
    logging.info("done.")
    logging.info("ways: %i", len(roads))
    print "OBJECT_STATIC %s %g %g %1.2f %g\n" % ("road.ac", center_global.lon, center_global.lat, 0, 0)
    if parameters.PATH_TO_OUTPUT:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, center_global)
    else:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)
    stg_fname = calc_tile.construct_stg_file_name(center_global)
    print path+stg_fname

    # -- quick test output
    col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
    lw    = [2, 1.5, 1.2, 1, 1, 1, 1]
    lw_w  = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 1]

    if 1:
        for r in roads.roads:
            a = r.nodes
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
