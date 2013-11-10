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
* Calculate cables
* LOD

@author: vanosten
"""

import argparse
import os
import xml.sax
import logging

import coordinates
import osmparser
import parameters
import tools
import vec2d


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
        _entry = ["OBJECT_SHARED", "Models/Power/generic_pylon_25m.xml", str(self.lon), str(self.lat)
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
                    my_pylon.elevation = interpol(vec2d.vec2d(my_pylon.lon, my_pylon.lat))
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
    tools.init(coordinates.Transformation(center, hdg = 0))
    logging.info("Reading ground elevation data might take some time ...")
    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    powerlines, aerialways = process_osm_elements(handler.nodes_dict, handler.ways_dict, elev)
    handler = None


    logging.info('Number of power lines: %s', len(powerlines))
    for line in powerlines.values():
        print line.make_pylons_stg_entries()

    logging.info('Number of aerialways: %s', len(aerialways))
    for line in aerialways.values():
        print line.make_pylons_stg_entries()

    logging.info("Finished")
