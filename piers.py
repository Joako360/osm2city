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


import logging
import osmparser

OUR_MAGIC = "osm2piers"  # Used in e.g. stg files to mark edits by osm2Piers


class Pier(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.is_area = tags.has_key('area')

#    def transform(self, nodes_dict, transform):
        osm_nodes = [nodes_dict[r] for r in refs]
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        # self.nodes = np.array([(n.lon, n.lat) for n in osm_nodes])
        self.line_string = shg.LineString(self.nodes)


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
        if way.tags.has_key('man_made'):
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
                self.writeArea(pier, elev, ac, obj)
            else:
                self.writeLine(pier, elev, ac, obj)
        return ac

            # obj.node()
    def testCCW(self, list):
        ret = 0
        previous = None
        for index, node in enumerate(list[1:]):
            previous = list[index]
            ret += (node[0] - previous[0]) * (node[1] + previous[1])
        return ret


    def writeArea(self, pier, elev, ac, obj):
    # Writes a Pier mapped as an area
        o = obj.next_node_index()
        if self.testCCW(pier.nodes) > 0 :
            logging.info("Clockwise")
            pier.nodes = pier.nodes[::-1]
        else:
            logging.info('Anti-Clockwise')
        for p in pier.nodes:
            e = elev(vec2d(p[0], p[1])) + 1
            obj.node(-p[1], e, -p[0])
        top_nodes = np.arange(len(pier.nodes))
        pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(pier.line_string.coords[i])) for i, coord in enumerate(pier.line_string.coords[1:])])
        rd_len = len(pier.line_string.coords)
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



    def writeLine(self, Pier, elev, ac, obj):
    # Writes a Pier as a area which only is mapped as a line
        o = obj.next_node_index()
        left = Pier.line_string.parallel_offset(2, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = Pier.line_string.parallel_offset(2, 'right', resolution=8, join_style=1, mitre_limit=10.0)
        e = 10000;
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
        Pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(Pier.line_string.coords[i])) for i, coord in enumerate(Pier.line_string.coords[1:])])
        rd_len = len(Pier.line_string.coords)
        Pier.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            Pier.dist[i] = Pier.dist[i - 1] + Pier.segment_len[i]
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
    center_global = parameters.get_OSM_file_name()
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
    stg_fname = calc_tile.construct_stg_file_name(center_global)

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

    elev = tools.getInterpolator()

    ac = piers.write(elev)
    ac_fname = 'Piers%07i.ac' % calc_tile.tile_index(center_global)
    logging.info("done.")

    fname = path + os.sep + ac_fname
    f = open(fname, 'w')
    f.write(str(ac))
    f.close()

    stg_manager = stg_io2.STG_Manager(path, OUR_MAGIC, overwrite=True)

    # -- write stg
    path_to_stg = stg_manager.add_object_static(ac_fname, center_global, 0, 0)
    stg_manager.write()
    elev.save_cache()

    logging.info("Done")


if __name__ == "__main__":
    main()
