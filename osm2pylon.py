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

import os
import xml.sax

import coordinates
import osmparser
import parameters
import tools
import vec2d


class Pylon(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.p_type = 0  # 11 = electric pole, 12 = electric tower, 21 = aerialway pylon, 22 = aerialway station
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
        self.l_type = 0  # 11 = power line, 12 = power minor line, 21 = cable_car, 22 = chair_lift/mixed_lift, 23 = drag_lift/t-bar/platter, 24 = gondola, 25 = goods

    def make_pylons_stg_entries(self):
        """
        Returns the stg entries for the line in a string separated by linebreaks
        """
        _entries = []
        for my_pylon in self.pylons:
            _entries.append(my_pylon.make_stg_entry())
        return "\n".join(_entries)


def transform_osm_elements(nodes_dict, ways_dict, interpol):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of Line objects for electrical power
    lines and a dict of Line objects for aerialways.
    """
    my_powerlines = {}
    my_aerialways = {}
    for way in ways_dict.values():
        my_line = Line(way.osm_id)
        for tag in way.tags:
            if "power" == tag.key:
                if "line" == tag.value:
                    my_line.l_type = 11
                elif "minor_line" == tag.value:
                    my_line.l_type = 12
            elif "aerialway" == tag.key:
                if "cable_car" == tag.value:
                    my_line.l_type = 21
                elif tag.value in ["chair_lift", "mixed_lift"]:
                    my_line.l_type = 22
                elif tag.value in ["drag_lift", "t-bar", "platter"]:
                    my_line.l_type = 23
                elif "gondola" == tag.value:
                    my_line.l_type = 24
                elif "goods" == tag.value:
                    my_line.l_type = 25
        if 0 != my_line.l_type:
            prev_pylon = None
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_pylon = Pylon(my_node.osm_id)
                    my_pylon.lat = my_node.lat
                    my_pylon.lon = my_node.lon
                    my_pylon.line = my_line
                    my_pylon.elevation = interpol(vec2d.vec2d(my_pylon.lon, my_pylon.lat))
                    for tag in my_node.tags:
                        if "power" == tag.key:
                            if "tower" == tag.value:
                                my_pylon.p_type = 12
                            elif "pole" == tag.value:
                                my_pylon.p_type = 11
                        elif "aerialway" == tag.key:
                            if "pylon" == tag.value:
                                my_pylon.p_type = 21
                            elif "station" == tag.value:
                                my_pylon.p_type = 22
                        elif "height" == tag.key:
                            my_pylon.height = osmparser.parse_length(tag.value)
                        elif "structure" == tag.key:
                            my_pylon.structure = tag.value
                        elif "material" == tag.key:
                            my_pylon.material = tag.value
                    if my_pylon.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.pylons.append(my_pylon)
                    else:
                        print "Node outside of boundaries with osm_id =", my_node.osm_id
                    if None != prev_pylon:
                        prev_pylon.next_pylon = my_pylon
                        my_pylon.prev_pylon = prev_pylon
                    prev_pylon = my_pylon
            if 1 < len(my_line.pylons):
                if my_line.l_type < 20:
                    my_powerlines[my_line.osm_id] = my_line
                else:
                    my_aerialways[my_line.osm_id] = my_line
    return (my_powerlines, my_aerialways)

if __name__ == "__main__":
    # Handling arguments and parameters
    import argparse
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
    source = open(parameters.PATH_TO_SCENERY + os.sep + parameters.OSM_FILE)
    print "Reading the OSM file might take some time ..."
    xml.sax.parse(source, handler)

    # Reading elevation data
    cmin = vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center, hdg = 0))
    print "Reading ground elevation data might take some time ..."
    elev = tools.Interpolator(parameters.PATH_TO_SCENERY + os.sep + "elev.xml", fake=parameters.NO_ELEV)

    # Transform to real objects
    powerlines, aerialways = transform_osm_elements(handler.nodes_dict, handler.ways_dict, elev)
    handler = None


    print "powerlines: ", len(powerlines)
    for line in powerlines.values():
        print line.make_pylons_stg_entries()

    print "aerialways: ", len(aerialways)
    for line in aerialways.values():
        print line.make_pylons_stg_entries()
