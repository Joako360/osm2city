#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
import coordinates
import tools
import parameters
import calc_tile
import os
import ac3d
import stg_io2
from objectlist import ObjectList
from random import randint


import logging
import osmparser
from shapely.geometry.base import CAP_STYLE, JOIN_STYLE
from tools import transform
from shapely.geometry.polygon import Polygon
import math
from shapely.geometry.linestring import LineString
from random import random

OUR_MAGIC = "osm2piers"  # Used in e.g. stg files to mark edits by osm2Piers


class Pier(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.is_area = 'area' in tags

#    def transform(self, nodes_dict, transform):
        self.osm_nodes = [nodes_dict[r] for r in refs]
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in self.osm_nodes])


class Piers(ObjectList):
    valid_node_keys = []
    req_keys = ['man_made']
    valid_keys = ['area']

    def create_from_way(self, way, nodes_dict):
# Processes one way into a Pier
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)
            cmin = vec2d(self.minlon, self.minlat)
            cmax = vec2d(self.maxlon, self.maxlat)
            logging.info("min/max " + str(cmin) + " " + str(cmax))
#            center_global = (cmin + cmax)*0.5
            # center_global = vec2d(1.135e1+0.03, 0.02+4.724e1)
            # self.transform = coordinates.Transformation(center_global, hdg = 0)
            # tools.init(self.transform) # FIXME. Not a nice design.

        col = None
        if 'man_made' in way.tags:
            if way.tags['man_made'] == 'pier':
                col = 6

        if col == None:
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return

        # print "(accepted)"
        pier = Pier(self.transform, way.osm_id, way.tags, way.refs, nodes_dict)
        self.objects.append(pier)

    def write(self, elev):
        ac = ac3d.Writer(tools.stats)
        obj = ac.new_object('Piers', "Textures/Terrain/asphalt.png")
        for pier in self.objects[:]:
            length = len(pier.nodes)
            if(length > 3 and pier.nodes[0][0] == pier.nodes[(length - 1)][0] and pier.nodes[0][1] == pier.nodes[(length - 1)][1]):
                self.write_area(pier, elev, ac, obj)
            else:
                self.write_line(pier, elev, ac, obj)
        return ac

    def write_boats(self, elev, stg_manager):
        for pier in self.objects[:]:
            length = len(pier.nodes)
            if(length > 3 and pier.nodes[0][0] == pier.nodes[(length - 1)][0] and pier.nodes[0][1] == pier.nodes[(length - 1)][1]):
                self.write_boat_area(pier, elev, stg_manager)
            else:
                self.write_boat_line(pier, elev, stg_manager)

    def write_boat_area(self, pier, elev, stg_manager):
        if(len(pier.nodes) < 3):
            return
        # Guess a possible position for realistic boat placement
        linear_ring = shg.LinearRing(pier.nodes)
        centroid = linear_ring.centroid
        # Simplyfy
        ring = linear_ring.convex_hull.buffer(40, cap_style=CAP_STYLE.square, join_style=JOIN_STYLE.bevel).simplify(20)
        min_elev = 0.5
        for p in ring.exterior.coords:
            coord = vec2d(p[0], p[1])
            p_elev = elev(coord)
            if(p_elev < min_elev):
                #Seems to be water
                print p_elev
                line_coords = [[centroid.x, centroid.y], p]
                target_vector = shg.LineString(line_coords)
                boat_position = linear_ring.intersection(target_vector)
                coords = linear_ring.coords
                direction = None
                for i in range(len(coords) - 1):
                    segment = LineString(coords[i:i + 2])
                    if segment.length > 20 and segment.intersects(target_vector):
                        direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0], segment.coords[0][1] - segment.coords[1][1]))
                        parallel = segment.parallel_offset(10, 'right')
                        boat_position = parallel.interpolate(segment.length / 2)
                        # Ok now we've got the direction and position
                        # OBJECT_SHARED Models/Maritime/Civilian/Pilot_Boat.ac -0.188 54.07603 -0.24 0
                        print direction
                        print "Boat"
                        print boat_position
                        print tools.transform.toGlobal(coord)
                        try:
                            pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
                            self.write_model(segment.length, stg_manager, pos_global, direction)
                        except AttributeError, reason:
                            logging.error(reason)

    def write_boat_line(self, pier, elev, stg_manager):
        line_string = LineString(pier.nodes)
        right_line = line_string.parallel_offset(4, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        coords = right_line.coords
        for i in range(len(coords) - 1):
            segment = LineString(coords[i:i + 2])
            boat_position = segment.interpolate(segment.length / 2)
            try:
                pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
                direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0], segment.coords[0][1] - segment.coords[1][1]))
                if(segment.length > 5):
                    self.write_model(segment.length, stg_manager, pos_global, direction)
            except AttributeError, reason:
                logging.error(reason)

    def write_model(self, length, stg_manager, pos_global, direction):
        if length < 20:
            models = [('Models/Maritime/Civilian/wooden_boat.ac', 120),
                      ('Models/Maritime/Civilian/wooden_blue_boat.ac', 120),
                      ('Models/Maritime/Civilian/wooden_green_boat.ac', 120)]
            choice = randint(0, len(models) - 1)
            model = models[choice]
        elif length < 70:
            models = [('Models/Maritime/Civilian/small-red-yacht.ac', 110),
                      ('Models/Maritime/Civilian/small-black-yacht.ac', 110),
                      ('Models/Maritime/Civilian/small-clear-yacht.ac', 110),
                      ('Models/Maritime/Civilian/blue-sailing-boat-20m.ac', 120),
                      ('Models/Maritime/Civilian/red-sailing-boat-11m.ac', 120),
                      ('Models/Maritime/Civilian/red-sailing-boat-20m.ac', 120)]
            choice = randint(0, len(models) - 1)
            model = models[choice]
        elif length < 300:
            #('Models/Maritime/Civilian/Trawler.xml', 300),
            models = [('Models/Maritime/Civilian/MediumFerry.xml', 100)]
            choice = randint(0, len(models) - 1)
            model = models[choice]
        elif length < 400:
            models = [('Models/Maritime/Civilian/LargeTrawler.xml', 10), ('Models/Maritime/Civilian/LargeFerry.xml', 100), ('Models/Maritime/Civilian/barge.xml', 60)]
            choice = randint(0, len(models) - 1)
            model = models[choice]
        else:
            models = [('Models/Maritime/Civilian/SimpleFreighter.ac', 20), ('Models/Maritime/Civilian/FerryBoat1.ac', 70)]
            choice = randint(0, len(models) - 1)
            model = models[choice]
        stg_path = stg_manager.add_object_shared(model[0], vec2d(pos_global), 0, direction + model[1])
#         print stg_path

    def write_area(self, pier, elev, ac, obj):
    # Writes a Pier mapped as an area
        linear_ring = shg.LinearRing(pier.nodes)
#         print ring_lat_lon
        # TODO shg.LinearRing().is_ccw
        o = obj.next_node_index()
        if linear_ring.is_ccw:
            logging.info('CounterClockWise')
        else:
            # normalize to CCW
            logging.info("Clockwise")
            pier.nodes = pier.nodes[::-1]
        # top ring
        for p in pier.nodes:
            e = elev(vec2d(p[0], p[1])) + 1
            obj.node(-p[1], e, -p[0])
        top_nodes = np.arange(len(pier.nodes))
        pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(linear_ring.coords[i])) for i, coord in enumerate(linear_ring.coords[1:])])
        rd_len = len(linear_ring.coords)
        pier.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
        face = []
        x = 0.
        # reversed(list(enumerate(a)))
# Top Face
        for i, n in enumerate(top_nodes):
            face.append((n + o, x, 0.5))
        obj.face(face, mat=0)
# Build bottom ring
        for p in pier.nodes:
            e = elev(vec2d(p[0], p[1])) - 5
            obj.node(-p[1], e, -p[0])
# Build Sides
        height = 2
        for i, n in enumerate(top_nodes[1:]):
            sideface = []
            sideface.append((n + o + rd_len - 1, x, 0.5))
            sideface.append((n + o + rd_len, x, 0.5))
            sideface.append((n + o, x, 0.5))
            sideface.append((n + o - 1, x, 0.5))
            obj.face(sideface, mat=0)

    def write_line(self, pier, elev, ac, obj):
    # Writes a Pier as a area which only is mapped as a line
        line_string = shg.LineString(pier.nodes)
        o = obj.next_node_index()
        left = line_string.parallel_offset(1, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = line_string.parallel_offset(1, 'right', resolution=8, join_style=1, mitre_limit=10.0)
        e = 10000
        idx_left = obj.next_node_index()
        for p in left.coords:
            e = elev(vec2d(p[0], p[1])) + 1
            obj.node(-p[1], e, -p[0])
        idx_right = obj.next_node_index()
        for p in right.coords:
            e = elev(vec2d(p[0], p[1])) + 1
            obj.node(-p[1], e, -p[0])
        nodes_l = np.arange(len(left.coords))
        nodes_r = np.arange(len(right.coords))
        pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(line_string.coords[i])) for i, coord in enumerate(line_string.coords[1:])])
        rd_len = len(line_string.coords)
        pier.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
# Top Surface
        face = []
        x = 0.
        for i, n in enumerate(nodes_l):
            face.append((n + o, x, 0.5))
        o += len(left.coords)
        for i, n in enumerate(nodes_r):
            face.append((n + o, x, 0.75))
        obj.face(face[::-1], mat=0)
# Build bottom left line
        idx_bottom_left = obj.next_node_index()
        for p in left.coords:
            e = elev(vec2d(p[0], p[1])) - 1
            obj.node(-p[1], e, -p[0])
# Build bottom right line
        idx_bottom_right = obj.next_node_index()
        for p in right.coords:
            e = elev(vec2d(p[0], p[1])) - 1
            obj.node(-p[1], e, -p[0])
        idx_end = obj.next_node_index() - 1
# Build Sides
        for i, n in enumerate(nodes_l[1:]):
            # Start with Second point looking back
            sideface = []
            sideface.append((n + idx_bottom_left, x, 0.5))
            sideface.append((n + idx_bottom_left - 1, x, 0.5))
            sideface.append((n + idx_left - 1, x, 0.5))
            sideface.append((n + idx_left, x, 0.5))
            obj.face(sideface, mat=0)
        for i, n in enumerate(nodes_r[1:]):
            # Start with Second point looking back
            sideface = []
            sideface.append((n + idx_bottom_right, x, 0.5))
            sideface.append((n + idx_bottom_right - 1, x, 0.5))
            sideface.append((n + idx_right - 1, x, 0.5))
            sideface.append((n + idx_right, x, 0.5))
            obj.face(sideface, mat=0)
# Build Front&Back
        sideface = []
        sideface.append((idx_left, x, 0.5))
        sideface.append((idx_bottom_left, x, 0.5))
        sideface.append((idx_end, x, 0.5))
        sideface.append((idx_bottom_left - 1, x, 0.5))
        obj.face(sideface, mat=0)
        sideface = []
        sideface.append((idx_bottom_right, x, 0.5))
        sideface.append((idx_bottom_right - 1, x, 0.5))
        sideface.append((idx_right - 1, x, 0.5))
        sideface.append((idx_right, x, 0.5))
        obj.face(sideface, mat=0)


def main():
    logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser(description="Pier.py reads OSM data and creates Pier models for use with FlightGear")
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

    osm_fname = parameters.get_OSM_file_name()
    center_global = parameters.get_center_global()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    piers = Piers(transform)

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

    handler.register_way_callback(piers.create_from_way, req_keys=piers.req_keys)
    handler.parse(source)
    logging.info("ways: %i", len(piers))
    if(len(piers) == 0):
        logging.info("No piers found ignoring")
        return

    # transform = tools.transform
    # center_global =  vec2d(transform.toGlobal(vec2d(0,0)))
    if parameters.PATH_TO_OUTPUT:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, center_global)
    else:
        path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)

    # -- quick test output
    col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k']
    lw = [2, 1.5, 1.2, 1, 1, 1, 1]
    lw_w = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 1]

    if 0:
        for p in piers.piers:
            a = p.nodes
            # np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:, 0], a[:, 1], color=col[p.typ], linewidth=lw[p.typ])
            plt.plot(a[:, 0], a[:, 1], color='w', linewidth=lw_w[p.typ], ls=":")

        plt.axes().set_aspect('equal')
        # plt.show()
        plt.savefig('Piers.eps')

    elev = tools.get_interpolator()

    ac = piers.write(elev)
    ac_fname = 'Piers%07i.ac' % calc_tile.tile_index(center_global)
    logging.info("done.")

    fname = path + os.sep + ac_fname
    f = open(fname, 'w')
    f.write(str(ac))
    f.close()

    # -- initialize STG_Manager
    if parameters.PATH_TO_OUTPUT:
        path_to_output = parameters.PATH_TO_OUTPUT
    else:
        path_to_output = parameters.PATH_TO_SCENERY
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, overwrite=True)

    piers.write_boats(elev, stg_manager)
    # -- write stg
    stg_manager.add_object_static(ac_fname, center_global, 0, 0)
    stg_manager.write()
    elev.save_cache()

    logging.info("Done")


if __name__ == "__main__":
    main()
