# -*- coding: utf-8 -*-
"""
Script part of osm2city which takes OpenStreetMap data for overground power lines and aerialways
as input and generates data to be used in FlightGear sceneries.

* Cf. OSM Power: 
    http://wiki.openstreetmap.org/wiki/Map_Features#Power
    http://wiki.openstreetmap.org/wiki/Tag:power%3Dtower
* Cf. OSM Aerialway: http://wiki.openstreetmap.org/wiki/Map_Features#Aerialway

TODO:
* Calculate headings of pylons and stations
* Check for inconsistencies between pylons in same way
* For aearialways make sure there is a station at both ends
* for aerialways handle stations if represented as ways instead of nodes
* Calculate cables
* LOD

@author: vanosten
"""

import argparse
import os
import xml.sax
import logging

import calc_tile
import coordinates
import osmparser
import parameters
import stg_io
import tools
import vec2d

OUR_MAGIC = "osm2pylon"  # Used in e.g. stg files to mark edits by osm2pylon

class Pylon(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0  # 11 = electric pole, 12 = electric tower, 21 = aerialway pylon, 22 = aerialway station
        self.height = 0  # parsed as float
        self.structure = None
        self.material = None
        self.colour = None
        self.line = None  # a reference to the way - either an electrical line or an aerialway
        self.prev_pylon = None
        self.next_pylon = None
        self.lon = 0  # longitude coordinate in decimal as a float
        self.lat = 0  # latitude coordinate in decimal as a float
        self.elevation = 0  # elevation above sea level in meters
        self.heading = 0  # heading of pylon in degrees

    def make_stg_entry(self):
        """
        Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        _model = "Models/Power/generic_pylon_50m.xml"
        if self.line.is_aerialway():
            _model = "Models/Power/generic_pylon_25m.xml"
        _entry = ["OBJECT_SHARED", _model, str(self.lon), str(self.lat)
                , str(self.elevation), str(self.heading)]
        return " ".join(_entry)


class Line(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.pylons = []
        self.type_ = 0  # 11 = power line, 12 = power minor line, 21 = cable_car, 22 = chair_lift/mixed_lift, 23 = drag_lift/t-bar/platter, 24 = gondola, 25 = goods

    def make_pylons_stg_entries(self):
        """
        Returns the stg entries for the line in a string separated by linebreaks
        """
        _entries = []
        for my_pylon in self.pylons:
            _entries.append(my_pylon.make_stg_entry())
        return "\n".join(_entries)

    def is_aerialway(self):
        return self.type_ > 20

    def validate(self):
        """Validate various aspects of the line and its nodes and attempt to correct if needed. Return True if usable"""
        if len(self.pylons) < 2:
            return False
        if self.is_aerialway():
            return self._validate_aerialway()
        else:
            return self._validate_powerline()

    def _validate_aerialway(self):
        return True

    def _validate_powerline(self):
        return True

    def get_center_coordinates(self):
        """Returns the lon/lat coordinates of the line
        FIXME: needs to be calculated more properly with shapely"""
        my_pylon = self.pylons[0]
        return (my_pylon.lon, my_pylon.lat)


def process_osm_elements(nodes_dict, ways_dict, interpol):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of Line objects for electrical power
    lines and a dict of Line objects for aerialways.
    """
    my_powerlines = {}
    my_aerialways = {}
    for way in ways_dict.values():
        my_line = Line(way.osm_id)
        for key in way.tags:
            value = way.tags[key]
            if "power" == key:
                if "line" == value:
                    my_line.type_ = 11
                elif "minor_line" == value:
                    my_line.type_ = 12
            elif "aerialway" == key:
                if "cable_car" == value:
                    my_line.type_ = 21
                elif value in ["chair_lift", "mixed_lift"]:
                    my_line.type_ = 22
                elif value in ["drag_lift", "t-bar", "platter"]:
                    my_line.type_ = 23
                elif "gondola" == value:
                    my_line.type_ = 24
                elif "goods" == value:
                    my_line.type_ = 25
        if 0 != my_line.type_:
            prev_pylon = None
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_pylon = Pylon(my_node.osm_id)
                    my_pylon.lat = my_node.lat
                    my_pylon.lon = my_node.lon
                    my_pylon.line = my_line
                    my_pylon.elevation = interpol(vec2d.vec2d(my_pylon.lon, my_pylon.lat), True)
                    for key in my_node.tags:
                        value = my_node.tags[key]
                        if "power" == key:
                            if "tower" == value:
                                my_pylon.type_ = 12
                            elif "pole" == value:
                                my_pylon.type_ = 11
                        elif "aerialway" == key:
                            if "pylon" == value:
                                my_pylon.type_ = 21
                            elif "station" == value:
                                my_pylon.type_ = 22
                        elif "height" == key:
                            my_pylon.height = osmparser.parse_length(value)
                        elif "structure" == key:
                            my_pylon.structure = value
                        elif "material" == key:
                            my_pylon.material = value
                    if my_pylon.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.pylons.append(my_pylon)
                    else:
                        logging.debug('Node outside of boundaries with osm_id = %s and therefore ignored', my_node.osm_id)
                    if None != prev_pylon:
                        prev_pylon.next_pylon = my_pylon
                        my_pylon.prev_pylon = prev_pylon
                    prev_pylon = my_pylon
            if my_line.validate():
                if my_line.is_aerialway():
                    my_aerialways[my_line.osm_id] = my_line
                else:
                    my_powerlines[my_line.osm_id] = my_line
            else:
                logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)
    return (my_powerlines, my_aerialways)


def write_stg_entries(stg_fp_dict, lines_dict):
    for line in lines_dict.values():
        _center = line.get_center_coordinates()
        stg_fname = calc_tile.construct_stg_file_name(_center)
        if not stg_fname in stg_fp_dict:
            if parameters.PATH_TO_OUTPUT:
                path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, _center)
            else:
                path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, _center)
            try:
                os.makedirs(path)
            except OSError:
                logging.exception("Path to output already exists or unable to create")
                pass
            stg_io.uninstall_ours(path, stg_fname, OUR_MAGIC)
            stg_file = open(path + stg_fname, "a")
            stg_file.write(stg_io.delimiter_string(OUR_MAGIC, True) + "\n# do not edit below this line\n#\n")
            stg_fp_dict[stg_fname] = stg_file
        else:
            stg_file = stg_fp_dict[stg_fname]
        stg_file.write(line.make_pylons_stg_entries() + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(description="osm2city reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)

    # Reading OSM-file and transform to Pylons / Lines objects
    valid_node_keys = ["power", "structure", "material", "height", "colour", "aerialway"]
    valid_way_keys = ["power", "aerialway"]
    req_way_keys = ["power", "aerialway"]
    valid_relation_keys = []
    req_relation_keys = []
    handler = osmparser.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys)
    source = open(parameters.PREFIX + os.sep + parameters.OSM_FILE)
    logging.info("Reading the OSM file might take some time ...")
    xml.sax.parse(source, handler)

    # Reading elevation data
    cmin = vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center, hdg=0))
    logging.info("Reading ground elevation data might take some time ...")
    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    powerlines, aerialways = process_osm_elements(handler.nodes_dict, handler.ways_dict, elev)
    handler = None
    logging.info('Number of power lines: %s', len(powerlines))
    logging.info('Number of aerialways: %s', len(aerialways))

    stg_file_pointers = {}  # -- dictionary of stg file pointers
    write_stg_entries(stg_file_pointers, powerlines)
    write_stg_entries(stg_file_pointers, aerialways)

    for stg in stg_file_pointers.values():
        stg.write(stg_io.delimiter_string(OUR_MAGIC, False) + "\n")
        stg.close()

    logging.info("******* Finished *******")
