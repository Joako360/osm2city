#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle
import re
from locale import atoi

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
from objectlist import ObjectList
import stg_io2

import logging
import osmparser

OUR_MAGIC = "osm2platforms"  # Used in e.g. stg files to mark edits by osm2platforms
# -----------------------------------------------------------------------------


def no_transform((x, y)):
    return x, y


class Platform(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.is_area = 'area' in tags
        self.logger = logging.getLogger("platforms")
        
        if 'layer' in tags:
            self.logger.warn("layer %s %d"%(tags['layer'],osm_id))

#    def transform(self, nodes_dict, transform):
        osm_nodes = [nodes_dict[r] for r in refs]
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        # self.nodes = np.array([(n.lon, n.lat) for n in osm_nodes])
        self.line_string = shg.LineString(self.nodes)


class Platforms(ObjectList):
    valid_node_keys = []
    req_keys = ['railway']
    valid_keys = ['area', 'layer']

    def __init__(self, transform):
        ObjectList.__init__(self, transform)
        self.logger = logging.getLogger("platforms")

    def create_from_way(self, way, nodes_dict):
# Processes one way into a platform
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)
            self.min_max_scanned = True
            cmin = vec2d(self.minlon, self.minlat)
            cmax = vec2d(self.maxlon, self.maxlat)
            self.logger.info("min/max " + str(cmin) + " " + str(cmax))
#            center_global = (cmin + cmax)*0.5
            # center_global = vec2d(1.135e1+0.03, 0.02+4.724e1)
            # self.transform = coordinates.Transformation(center_global, hdg = 0)
            # tools.init(self.transform) # FIXME. Not a nice design.

        col = None
        if 'railway' in way.tags:
            if way.tags['railway'] == 'platform':
                col = 6

        if col == None:
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return
        if 'layer' in way.tags and atoi(way.tags['layer']) < 0:
            return

        # print "(accepted)"
        platform = Platform(self.transform, way.osm_id, way.tags, way.refs, nodes_dict)
        self.objects.append(platform)

    def write(self, elev):
        ac = ac3d.File(stats=tools.stats)
        obj = ac.new_object('platforms', "Textures/Terrain/asphalt.png")
        for platform in self.objects[:]:
            if(platform.is_area):
                self.writeArea(platform, elev, ac, obj)
                None
            else:
                self.writeLine(platform, elev, ac, obj)
        return ac

    def writeArea(self, platform, elev, ac, obj):
    # Writes a platform mapped as an area
        linear_ring = shg.LinearRing(platform.nodes)

        o = obj.next_node_index()
        if linear_ring.is_ccw:
            self.logger.info('Anti-Clockwise')
        else:
            self.logger.info("Clockwise")
            platform.nodes = platform.nodes[::-1]
        for p in platform.nodes:
            e = elev(vec2d(p[0], p[1])) + 1
            obj.node(-p[1], e, -p[0])
        top_nodes = np.arange(len(platform.nodes))
        platform.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
        rd_len = len(platform.line_string.coords)
        platform.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            platform.dist[i] = platform.dist[i - 1] + platform.segment_len[i]
        face = []
        x = 0.
        # reversed(list(enumerate(a)))
# Top Face
        for i, n in enumerate(top_nodes):
            face.append((n + o, x, 0.5))
        obj.face(face, mat=0)
# Build bottom ring
        for p in platform.nodes:
            e = elev(vec2d(p[0], p[1])) - 1
            obj.node(-p[1], e, -p[0])
# Build Sides
        for i, n in enumerate(top_nodes[1:]):
            sideface = []
            sideface.append((n + o + rd_len - 1, x, 0.5))
            sideface.append((n + o + rd_len, x, 0.5))
            sideface.append((n + o, x, 0.5))
            sideface.append((n + o - 1, x, 0.5))
            obj.face(sideface, mat=0)

    def writeLine(self, platform, elev, ac, obj):
    # Writes a platform as a area which only is mapped as a line
        o = obj.next_node_index()
        left = platform.line_string.parallel_offset(2, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = platform.line_string.parallel_offset(2, 'right', resolution=8, join_style=1, mitre_limit=10.0)
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
        platform.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
        rd_len = len(platform.line_string.coords)
        platform.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            platform.dist[i] = platform.dist[i - 1] + platform.segment_len[i]
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
    import argparse
    parser = argparse.ArgumentParser(description="platform.py reads OSM data and creates platform models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL")
#    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

#    if args.e:
#        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    parameters.show()

    center_global = parameters.get_center_global()
    osm_fname = parameters.get_OSM_file_name()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    platforms = Platforms(transform)

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

    handler.register_way_callback(platforms.create_from_way, req_keys=platforms.req_keys)
    handler.parse(source)

    logging.info("ways: %i", len(platforms))
    if(len(platforms) == 0):
        logging.info("No platforms found ignoring")
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

    if 1:
        for p in platforms.objects:
            a = p.nodes
            # np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:, 0], a[:, 1], color=col[p.typ], linewidth=lw[p.typ])
            plt.plot(a[:, 0], a[:, 1], color='w', linewidth=lw_w[p.typ], ls=":")

        plt.axes().set_aspect('equal')
        # plt.show()
        plt.savefig('platforms.eps')

    elev = tools.get_interpolator()
    ac = platforms.write(elev)
    ac_fname = 'platforms%07i.ac' % calc_tile.tile_index(center_global)
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
    replacement_prefix = re.sub('[\/]', '_', parameters.PREFIX)        
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)

    # -- write stg
    path_to_stg = stg_manager.add_object_static(ac_fname, center_global, 0, 0)
    stg_manager.write()
    elev.save_cache()

    logging.info("Done")


if __name__ == "__main__":
    main()