# -*- coding: utf-8 -*-
"""
Script part of osm2city which takes OpenStreetMap data as input and generates data to be used in FlightGear
   * isolated trees

@author: rogue-spectre
"""

import argparse
import logging
import math
import os
import sys
import xml.sax

import parameters
import stg_io2
import tools
from utils import osmparser, vec2d, coordinates

OUR_MAGIC = "osm2nature"  # Used in e.g. stg files to mark edits by osm2nature.py


class TreeNode(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.switch = False
        self.buffer_stop = False
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 500.0  # elevation above sea level in meters
        self.tree_model = "Models/Trees/platanus_acerifolia_15m.xml"

    def calc_global_coordinates(self, my_elev_interpolator, my_coord_transformator):
        self.lon, self.lat = my_coord_transformator.toGlobal((self.x, self.y))
        self.elevation = my_elev_interpolator(vec2d.Vec2d(self.lon, self.lat), True)

    def make_stg_entry(self, my_stg_mgr):
        """
        Returns a stg entry for this tree.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        my_stg_mgr.add_object_shared(self.tree_model, vec2d.Vec2d(self.lon, self.lat)
                                     , self.elevation
                                     , stg_angle(0))  # 90 less because arms are in x-direction in ac-file 


def process_osm_tree(nodes_dict, ways_dict, my_elev_interpolator, my_coord_transformator):
    my_trees = {}
    for node in list(nodes_dict.values()):
        for key in node.tags :
            if node.tags[key] == "tree":
                my_node = node
                my_tree_node = TreeNode(my_node.osm_id)
                my_tree_node.lat = my_node.lat
                my_tree_node.lon = my_node.lon
                # try to get a suitable model
                print((node.tags))
                try:
                    if "type" in node.tags:
                        if node.tags["type"] == "conifer":
                            print("found conifer")
                            my_tree_node.tree_model = "Models/Trees/coniferous-tree.xml"
                        if node.tags["type"] == "palm":
                            print("found palm")
                            my_tree_node.tree_model = "Models/Trees/palm02.xml"
                except:
                    my_tree_node.tree_model = "Models/Trees/platanus_acerifolia_15m.xml"

                my_tree_node.tree_model = "Models/Trees/egkk_woods.xml"

                my_tree_node.x, my_tree_node.y = my_coord_transformator.toLocal((my_tree_node.lon, my_tree_node.lat))
                my_tree_node.elevation = my_elev_interpolator(vec2d.Vec2d(my_tree_node.lon, my_tree_node.lat), True)
                print(("adding entry to trees", my_node.osm_id, " ", my_tree_node.x, " ", my_tree_node.y, " ", my_tree_node.elevation))
                my_trees[my_tree_node.osm_id] = my_tree_node

    return my_trees


def process_osm_forest(nodes_dict, ways_dict, my_elev_interpolator, my_coord_transformator):
    """ fist stage put trees on contour """
    my_trees = {}
    for way in list(ways_dict.values()):
        for key in way.tags:
            if way.tags[key] == "forest":
                print("found forest")
                for ref in way.refs:
                    if ref in nodes_dict:
                        my_node = nodes_dict[ref]
                        my_tree_node = TreeNode(my_node.osm_id)
                        my_tree_node.lat = my_node.lat
                        my_tree_node.lon = my_node.lon
                        my_tree_node.x, my_tree_node.y = my_coord_transformator.toLocal((my_tree_node.lon, my_tree_node.lat))
                        my_tree_node.elevation = my_elev_interpolator(vec2d.Vec2d(my_tree_node.lon, my_tree_node.lat), True)
                        print(("adding entry to trees", my_tree_node.x, my_tree_node.y, my_tree_node.elevation))
                        my_trees[my_tree_node.osm_id] = my_tree_node
    return my_trees


def write_stg_entries(my_stg_mgr, my_files_to_remove, lines_dict, wayname, cluster_max_length):
    line_index = 0
    for line in list(lines_dict.values()):
        line_index += 1
        line.make_shared_pylons_stg_entries(my_stg_mgr)
        if None is not wayname:
            line.make_cables_ac_xml_stg_entries(my_stg_mgr, line_index, wayname, cluster_max_length, my_files_to_remove)


def stg_angle(angle_normal):
    """Returns the input angle in degrees to an angle for the stg-file in degrees.
    stg-files use angles counter-clockwise starting with 0 in North."""
    if 0 == angle_normal:
        return 0
    else:
        return 360 - angle_normal


def calc_distance(x1, y1, x2, y2):
    return math.sqrt(math.pow(x1 - x2, 2) + math.pow(y1 - y2, 2))


def main():
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="osm2nature reads OSM data and creates single trees for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
    parser.add_argument("-u", dest="uninstall", action="store_true", help="uninstall ours from .stg")
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    if args.e:
        parameters.NO_ELEV = True
    files_to_remove = None
    if args.uninstall:
        logging.info("Uninstalling.")
        files_to_remove = []
        parameters.NO_ELEV = True

    # Initializing tools for global/local coordinate transformations
    center_global = parameters.get_center_global()
    osm_fname = parameters.get_OSM_file_name()
    coord_transformator = coordinates.Transformation(center_global, hdg=0)
    tools.init(coord_transformator)

    # Reading elevation data
    logging.info("Reading ground elevation data might take some time ...")
    elev_interpolator = tools.get_interpolator(fake=parameters.NO_ELEV)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    valid_node_keys = ["natural", "landuse", "type"]
    valid_way_keys = ["landuse"]
    valid_relation_keys = []
    req_relation_keys = []
    req_way_keys = ["natural", "landuse"]
    handler = osmparser.OSMContentHandlerOld(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                             req_relation_keys)
    source = open(osm_fname, encoding="utf8")
    xml.sax.parse(source, handler)

    trees = {}
    forest_trees = {}
    if True :  # parameters.PROCESS_TREES :
        trees = process_osm_tree(handler.nodes_dict, handler.ways_dict, elev_interpolator
                                 , coord_transformator)
        logging.info('Number of trees to process: %s', len(trees))
    #if True :
    #    forest_trees = process_osm_forest(handler.nodes_dict, handler.ways_dict, elev_interpolator
    #                                                         , coord_transformator)
    #    logging.info('Number of forest to process: %s', len(trees))
    #    # -- initialize STG_Manager
    path_to_output = parameters.get_output_path()
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, parameters.get_repl_prefix(), overwrite=True)

    #write_stg_entries(stg_manager, files_to_remove, trees, "trees", 2000)
    for tree in list(trees.values()) :
        print((tree.elevation))
        tree.make_stg_entry(stg_manager)
        #write_stg_entries(stg_manager, files_to_remove, trees, "trees", 2000)
    for forest_tree in list(forest_trees.values()) :
        print((forest_tree.elevation))
        forest_tree.make_stg_entry(stg_manager)

    # -- initialize STG_Manager
    if args.uninstall:
        for f in files_to_remove:
            try:
                os.remove(f)
            except IOError:
                pass
        stg_manager.drop_ours()
        stg_manager.write()
        logging.info("uninstall done.")
        sys.exit(0)

    stg_manager.write()
    elev_interpolator.save_cache()

    logging.info("******* Finished *******")


if __name__ == "__main__":
    main()
