#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
from pdb import pm
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os
import ac3d
import stg_io

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
        self.is_area = tags.has_key('area')

#    def transform(self, nodes_dict, transform):
        osm_nodes = [nodes_dict[r] for r in refs]
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        #self.nodes = np.array([(n.lon, n.lat) for n in osm_nodes])
        self.line_string = shg.LineString(self.nodes)


class Platforms(object):
    valid_node_keys = []

    #req_and_valid_keys = {"valid_way_keys" : ["highway"], "req_way_keys" : ["highway"]}
    req_keys = ['railway']
    valid_keys = ['area']

    def __init__(self, transform):
        self.platforms = []
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
#Processes one way into a platform
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
        if way.tags.has_key('railway'):
            if way.tags['railway'] == 'platform':
                col = 6

        if col == None:
#            print "got", way.osm_id,
#            for t in way.tags.keys():
#                print (t), "=", (way.tags[t])+" ",
#            print "(rejected)"
            return

        #print "(accepted)"
        platform = Platform(self.transform, way.osm_id, way.tags, way.refs, nodes_dict)
        self.platforms.append(platform)

    def __len__(self):
        return len(self.platforms)

    def write(self, elev):
        ac = ac3d.Writer(tools.stats)
        obj = ac.new_object('platforms', "Textures/Terrain/asphalt.png")
        for platform in self.platforms[:]:
            if(platform.is_area):
                self.writeArea(platform,elev,ac,obj)
                None
            else:
                self.writeLine(platform,elev,ac,obj)
        return ac

            #obj.node()

    def writeArea(self,platform,elev,ac,obj):
    #Writes a platform mapped as an area
        o = obj.next_node_index()        
        for p in platform.nodes:
            e = elev(vec2d(p[0], p[1]))+1
            obj.node(-p[1], e, -p[0])
        top_nodes = np.arange(len(platform.nodes))
        platform.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
        rd_len = len(platform.line_string.coords)
        platform.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            platform.dist[i] = platform.dist[i-1] + platform.segment_len[i]
        face = []
        x = 0.
        #reversed(list(enumerate(a)))
#Top Face        
        for i, n in enumerate(top_nodes):
            face.append((n+o, x, 0.5))
        obj.face(face, mat=0)
# Build bottom ring    
        for p in platform.nodes:
            e = elev(vec2d(p[0], p[1])) -1
            obj.node(-p[1], e, -p[0])    
# Build Sides                       
        for i, n in enumerate(top_nodes[1:]):
            sideface=[]
            sideface.append((n+o+rd_len-1, x, 0.5))
            sideface.append((n+o+rd_len, x, 0.5))
            sideface.append((n+o, x, 0.5))
            sideface.append((n+o-1, x, 0.5))
            obj.face(sideface, mat=0)
            
        

    def writeLine(self,platform,elev,ac,obj):
    #Writes a platform as a area which only is mapped as a line
        o = obj.next_node_index()        
        left  = platform.line_string.parallel_offset(2, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = platform.line_string.parallel_offset(2, 'right', resolution=8, join_style=1, mitre_limit=10.0)
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
        platform.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
        rd_len = len(platform.line_string.coords)
        platform.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            platform.dist[i] = platform.dist[i-1] + platform.segment_len[i]
#Top Surface
        face = []
        x = 0.
        for i, n in enumerate(nodes_l):
            face.append((n+o, x, 0.5))
        o += len(left.coords)
        for i, n in enumerate(nodes_r):
            face.append((n+o, x, 0.75))
        obj.face(face[::-1], mat=0)
# Build bottom left line
        idx_bottom_left = obj.next_node_index()    
        for p in left.coords:
            e = elev(vec2d(p[0], p[1])) -1
            obj.node(-p[1], e, -p[0])    
# Build bottom right line    
        idx_bottom_right = obj.next_node_index()    
        for p in right.coords:
            e = elev(vec2d(p[0], p[1])) -1
            obj.node(-p[1], e, -p[0])    
        idx_end = obj.next_node_index() -1
# Build Sides                       
        for i, n in enumerate(nodes_l[1:]):
            #Start with Second point looking back
            sideface=[]
            sideface.append((n+idx_bottom_left, x, 0.5))
            sideface.append((n+idx_bottom_left-1, x, 0.5))
            sideface.append((n+idx_left-1, x, 0.5))
            sideface.append((n+idx_left, x, 0.5))
            obj.face(sideface, mat=0)
        for i, n in enumerate(nodes_r[1:]):
            #Start with Second point looking back
            sideface=[]
            sideface.append((n+idx_bottom_right, x, 0.5))
            sideface.append((n+idx_bottom_right-1, x, 0.5))
            sideface.append((n+idx_right-1, x, 0.5))
            sideface.append((n+idx_right, x, 0.5))
            obj.face(sideface, mat=0)
# Build Front&Back
        sideface=[]
        sideface.append((idx_left, x, 0.5))
        sideface.append((idx_bottom_left, x, 0.5))
        sideface.append((idx_end, x, 0.5))
        sideface.append((idx_bottom_left-1, x, 0.5))
        obj.face(sideface, mat=0)
        sideface=[]
        sideface.append((idx_bottom_right, x, 0.5))
        sideface.append((idx_bottom_right-1, x, 0.5))
        sideface.append((idx_right-1, x, 0.5))
        sideface.append((idx_right, x, 0.5))
        obj.face(sideface, mat=0)
    
def main():
    logging.basicConfig(level=logging.INFO)
    #logging.basicConfig(level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser(description="platform.py reads OSM data and creates platform models for use with FlightGear")
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
#     center_global = vec2d(11.38, 47.26)
#     transform = coordinates.Transformation(center_global, hdg = 0)
    tools.init(transform)
    platforms = Platforms(transform)

    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.create_from_way, **roads.req_and_valid_keys)
#    roads.register_callbacks_in(handler)
    handler.register_way_callback(platforms.create_from_way, req_keys=platforms.req_keys)
    handler.parse(source)

    #transform = tools.transform
    #center_global =  vec2d(transform.toGlobal(vec2d(0,0)))
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
        for p in platforms.platforms:
            a = p.nodes
            #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
            plt.plot(a[:,0], a[:,1], color=col[p.typ], linewidth=lw[p.typ])
            plt.plot(a[:,0], a[:,1], color='w', linewidth=lw_w[p.typ], ls=":")

        plt.axes().set_aspect('equal')
        #plt.show()
        plt.savefig('platforms.eps')

#    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things
    elev = tools.Probe_fgelev()
    ac = platforms.write(elev)
    ac_fname = 'platforms%07i.ac'%calc_tile.tile_index(center_global)
    logging.info("done.")
    logging.info("ways: %i", len(platforms))
    print "OBJECT_STATIC %s %g %g %1.2f %g\n" % (ac_fname, center_global.lon, center_global.lat, 0, 0)
    fname = path + os.sep + ac_fname
    f = open(fname, 'w')
    f.write(str(ac))
    f.close()
    
    # -- write stg
    stg_fname = calc_tile.construct_stg_file_name(center_global)
    stg_io.uninstall_ours(path, stg_fname, OUR_MAGIC)
    stg = open(path + stg_fname, "a")
    stg.write(stg_io.delimiter_string(OUR_MAGIC, True) + "\n# do not edit below this line\n#\n")

    stg.write("OBJECT_STATIC %s %1.5f %1.5f %1.2f %g\n" % (ac_fname, center_global.lon, center_global.lat, 0, 0))

    stg.write(stg_io.delimiter_string(OUR_MAGIC, False) + "\n")
    stg.close()
    elev.save_cache()

    logging.info("Done")



if __name__ == "__main__":
    main()
