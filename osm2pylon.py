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
* For aerialways make sure there is a station at both ends
* For aerialways handle stations if represented as ways instead of nodes.
* For powerlines handle power stations if represented as ways instead of nodes
* If a pylon is shared between lines but not at end points, then move one pylon a bit away
* Calculate cables
* LOD

@author: vanosten
"""

import argparse
import logging
import math
import os
import unittest
import xml.sax

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
        self.x = 0  # local position x
        self.y = 0  # local position y
        self.elevation = 0  # elevation above sea level in meters
        self.heading = 0  # heading of pylon in degrees

    def make_stg_entry(self):
        """
        Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        _model = "Models/Power/generic_pylon_50m.xml"
        if self.line.is_aerialway():
            _model = "Models/StreetFurniture/RailPower.xml"
        elif self.line.type_ > 11:
            _model = "Models/StreetFurniture/streetlamp3.xml"
        _entry = ["OBJECT_SHARED", _model, str(self.lon), str(self.lat), str(self.elevation), str(stg_angle(self.heading))]
        return " ".join(_entry)


class WayLine(object):  # The name "Line" is also used in e.g. SymPy
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
        return True  # FIXME: make real implementation

    def _validate_powerline(self):
        return True  # FIXME: make real implementation

    def get_center_coordinates(self):
        """Returns the lon/lat coordinates of the line"""
        my_pylon = self.pylons[0]
        return (my_pylon.lon, my_pylon.lat)  # FIXME: needs to be calculated more properly with shapely

    def calc_heading_pylons(self):
        _current_pylon = self.pylons[0]
        _next_pylon = self.pylons[1]
        _current_angle = angle_of_line(_current_pylon.x, _current_pylon.y, _next_pylon.x, _next_pylon.y)
        _current_pylon.heading = _current_angle
        for x in range(1, len(self.pylons) - 1):
            _prev_angle = _current_angle
            _current_pylon = self.pylons[x]
            _next_pylon = self.pylons[x + 1]
            _current_angle = angle_of_line(_current_pylon.x, _current_pylon.y, _next_pylon.x, _next_pylon.y)
            _current_pylon.heading = middle_angle(_prev_angle, _current_angle)
        self.pylons[-1].heading = _current_angle - 90  # 90 more because hangers are in x-direction


def process_osm_elements(nodes_dict, ways_dict, _elev_interpolator, _coord_transformator):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of WayLine objects for electrical power
    lines and a dict of WayLine objects for aerialways. Nodes are transformed to Pylons.
    The elevation of the pylons is calculated as part of this process.
    """
    my_powerlines = {}  # osm_id as key, Line object as value
    my_aerialways = {}  # osm_id as key, Line object as value
    my_shared_nodes = {}  # node osm_id as key, list of Line objects as value
    for way in ways_dict.values():
        my_line = WayLine(way.osm_id)
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
                    my_pylon.x, my_pylon.y = _coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_pylon.line = my_line
                    my_pylon.elevation = _elev_interpolator(vec2d.vec2d(my_pylon.lon, my_pylon.lat), True)
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
                        if my_node.osm_id in my_shared_nodes.keys():
                            my_shared_nodes[my_node.osm_id].append(my_line)
                        else:
                            my_shared_nodes[my_node.osm_id] = [my_line]
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

    for key in my_shared_nodes.keys():
        _shared_node = my_shared_nodes[key]
        if len(_shared_node) == 2:
            return_code = merge_lines(key, _shared_node[0], _shared_node[1])
            if 0 == return_code:  # remove the merged line
                if _shared_node[0].is_aerialway() and (_shared_node[1].osm_id in my_aerialways):
                    del my_aerialways[_shared_node[1].osm_id]
                elif _shared_node[1].osm_id in my_powerlines:
                    del my_powerlines[_shared_node[1].osm_id]
                logging.info("Merged two lines with node osm_id: %s", key)
            elif 1 == return_code:
                logging.warning("A node is referenced in two ways, but the lines have not same type. Node osm_id: %s; %s; %s"
                                , key, _shared_node[0].type_, _shared_node[1].type_)
            else:
                logging.warning("A node is referenced in two ways, but the common node is not at start/end. Node osm_id: %s; %s"
                                , key, _shared_node[0].type_)
        if len(_shared_node) > 2:
            logging.warning("A node is referenced in more than two ways. Most likely OSM problem. Node osm_id: %s", key)

    return my_powerlines, my_aerialways


def merge_lines(osm_id, line0, line1):
    """Takes two Line objects and attempts to merge them at a given node.
    Returns 1 if the Line objects are not of same type.
    Returns 2 if the node is not first or last node in both Line objects
    in a given Line object.
    Returns 0 if the added/merged pylons are in line0"""
    if line0.type_ != line1.type_:
        return 1
    if line0.pylons[0].osm_id == osm_id:
        line0_first = True
    elif line0.pylons[-1].osm_id == osm_id:
        line0_first = False
    else:
        return 2
    if line1.pylons[0].osm_id == osm_id:
        line1_first = True
    elif line1.pylons[-1].osm_id == osm_id:
        line1_first = False
    else:
        return 2

    if (False == line0_first) and (True == line1_first):
        for x in range(1, len(line1.pylons), 1):
            line0.pylons.append(line1.pylons[x])
    elif (False == line0_first) and (False == line1_first):
        for x in range(len(line1.pylons)-2, 0, -1):
            line0.pylons.append(line1.pylons[x])
    elif (True == line0_first) and (True == line1_first):
        for x in range(1, len(line1.pylons), 1):
            line0.pylons.insert(0, line1.pylons[x])
    else:
        for x in range(len(line1.pylons)-2, 0, -1):
            line0.pylons.insert(0, line1.pylons[x])
    return 0


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


def angle_of_line(x1, y1, x2, y2):
    """Returns the angle in degrees of a line relative to North"""
    _angle = math.atan2(x2 - x1, y2 - y1)
    _degree = math.degrees(_angle)
    if _degree < 0:
        _degree += 360
    return _degree


def middle_angle(angle_line1, angle_line2):
    """Returns the angle halfway between two lines"""
    if angle_line1 == angle_line2:
        _middle = angle_line1
    elif angle_line1 > angle_line2:
        _middle = angle_line1 - (angle_line1 - angle_line2)/2
    else:
        if math.fabs(angle_line2 - angle_line1) > 180:
            _middle = middle_angle(angle_line1 + 360, angle_line2)
        else:
            _middle = angle_line2 - (angle_line2 - angle_line1)/2
    if 360 <= _middle:
        _middle -= 360
    return _middle


def stg_angle(angle_normal):
    """Returns the input angle in degrees to an angle for the stg-file in degrees.
    stg-files use angles counter-clockwise starting with 0 in North."""
    if 0 == angle_normal:
        return 0
    else:
        return 360 - angle_normal


def do_calculations(waylines_dict):
    """Calculates the headings of the pylons for all WayLines in the dictionary"""
    for _wayline in waylines_dict.values():
        _wayline.calc_heading_pylons()

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

    # Initializing tools for global/local coordinate transformations
    cmin = vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax)*0.5
    coord_transformator = coordinates.Transformation(center, hdg=0)
    tools.init(coord_transformator)
    # Reading elevation data
    logging.info("Reading ground elevation data might take some time ...")
    elev_interpolator = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV)

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    powerlines, aerialways = process_osm_elements(handler.nodes_dict, handler.ways_dict, elev_interpolator, coord_transformator)
    handler = None  # free memory
    logging.info('Number of power lines: %s', len(powerlines))
    logging.info('Number of aerialways: %s', len(aerialways))

    # Work on objects
    do_calculations(powerlines)
    do_calculations(aerialways)

    # Write to Flightgear
    stg_file_pointers = {}  # -- dictionary of stg file pointers
    write_stg_entries(stg_file_pointers, powerlines)
    write_stg_entries(stg_file_pointers, aerialways)

    for stg in stg_file_pointers.values():
        stg.write(stg_io.delimiter_string(OUR_MAGIC, False) + "\n")
        stg.close()

    logging.info("******* Finished *******")


# ================ UNITTESTS =======================


class TestOSMPylons(unittest.TestCase):
    def test_angle_of_line(self):
        self.assertEqual(0, angle_of_line(0, 0, 0, 1), "North")
        self.assertEqual(90, angle_of_line(0, 0, 1, 0), "East")
        self.assertEqual(180, angle_of_line(0, 1, 0, 0), "South")
        self.assertEqual(270, angle_of_line(1, 0, 0, 0), "West")
        self.assertEqual(45, angle_of_line(0, 0, 1, 1), "North East")
        self.assertEqual(315, angle_of_line(1, 0, 0, 1), "North West")
        self.assertEqual(225, angle_of_line(1, 1, 0, 0), "South West")

    def test_middle_angle(self):
        self.assertEqual(0, middle_angle(0, 0), "North North")
        self.assertEqual(45, middle_angle(0, 90), "North East")
        self.assertEqual(130, middle_angle(90, 170), "East Almost_South")
        self.assertEqual(90, middle_angle(135, 45), "South_East North_East")
        self.assertEqual(0, middle_angle(45, 315), "South_East North_East")
        self.assertEqual(260, middle_angle(170, 350), "Almost_South Almost_North")

    def test_headings(self):
        pylon1 = Pylon(1)
        pylon1.x = -1
        pylon1.y = -1
        pylon2 = Pylon(2)
        pylon2.x = 1
        pylon2.y = 1
        wayline1 = WayLine(100)
        wayline1.pylons.append(pylon1)
        wayline1.pylons.append(pylon2)
        wayline1.calc_heading_pylons()
        self.assertAlmostEqual(45, pylon1.heading, 2)
        self.assertAlmostEqual(45, pylon2.heading, 2)
        pylon3 = Pylon(3)
        pylon3.x = 0
        pylon3.y = 1
        pylon4 = Pylon(4)
        pylon4.x = -1
        pylon4.y = 2
        wayline1.pylons.append(pylon3)
        wayline1.pylons.append(pylon4)
        wayline1.calc_heading_pylons()
        self.assertAlmostEqual(337.5, pylon2.heading, 2)
        self.assertAlmostEqual(292.5, pylon3.heading, 2)
        self.assertAlmostEqual(315, pylon4.heading, 2)
