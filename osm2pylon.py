#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script part of osm2city which takes OpenStreetMap data as input and generates data to be used in FlightGear
   * overground power lines
   * aerialways
   * railway overlines
   * streetlamps

TODO:
* Remove shared objects from stg-files to avoid doubles
* Collision detection
* For aerialways make sure there is a station at both ends
* For aerialways handle stations if represented as ways instead of nodes.
* For powerlines handle power stations if represented as ways instead of nodes
* If a pylon is shared between lines but not at end points, then move one pylon a bit away

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
import osmparser_wrapper
import parameters
import stg_io2
import tools
import vec2d
import re

from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import Point
from shapely.geometry import Polygon

OUR_MAGIC = "osm2pylon"  # Used in e.g. stg files to mark edits by osm2pylon


class Cable(object):
    def __init__(self, start_cable_vertex, end_cable_vertex, radius, number_extra_vertices, catenary_a, distance):
        """
        A Cable between two vertices. The radius is approximated with a triangle with sides of length 2*radius.
        If both the number of extra_vertices and the catenary_a are > 0, then the Cable gets a sag based on
        a catenary function.
        """
        self.start_cable_vertex = start_cable_vertex
        self.end_cable_vertex = end_cable_vertex
        self.vertices = [self.start_cable_vertex, self.end_cable_vertex]
        self.radius = radius
        self.heading = calc_angle_of_line(start_cable_vertex.x, start_cable_vertex.y
                                          , end_cable_vertex.x, end_cable_vertex.y)

        if (number_extra_vertices > 0) and (catenary_a > 0) and (distance >= parameters.C2P_CATENARY_MIN_DISTANCE):
            self._make_catenary_cable(number_extra_vertices, catenary_a)

    def _make_catenary_cable(self, number_extra_vertices, catenary_a):
        """
        Transforms the cable into one with more vertices and some sagging based on a catenary function.
        If there is a considerable difference in elevation between the two pylons, then gravity would have to
        be taken into account https://en.wikipedia.org/wiki/File:Catenary-tension.png.
        However the elevation correction actually already helps quite a bit, because the x/y are kept constant.
        """
        cable_distance = calc_distance(self.start_cable_vertex.x, self.start_cable_vertex.y
                                       , self.end_cable_vertex.x, self.end_cable_vertex.y)
        part_distance = cable_distance / (1 + number_extra_vertices)
        pylon_y = catenary_a * math.cosh((cable_distance / 2) / catenary_a)
        part_elevation = ((self.start_cable_vertex.elevation - self.end_cable_vertex.elevation) /
                          (1 + number_extra_vertices))
        for i in xrange(1, number_extra_vertices + 1):
            x = self.start_cable_vertex.x + i * part_distance * math.sin(math.radians(self.heading))
            y = self.start_cable_vertex.y + i * part_distance * math.cos(math.radians(self.heading))
            catenary_x = i * part_distance - (cable_distance / 2)
            elevation = catenary_a * math.cosh(catenary_x / catenary_a)  # pure catenary y-position
            elevation = self.start_cable_vertex.elevation - (pylon_y - elevation)  # relative distance to start pylon
            elevation -= i * part_elevation  # correct for elevation difference between the 2 pylons
            v = CableVertex(0, 0)
            v.set_position(x, y, elevation)
            self.vertices.insert(i, v)

    def translate_vertices_relative(self, rel_x, rel_y, rel_elevation):
        """
        Translates the CableVertices relatively to a reference position
        """
        for cable_vertex in self.vertices:
            cable_vertex.x -= rel_x
            cable_vertex.y -= rel_y
            cable_vertex.elevation -= rel_elevation

    def _create_numvert_lines(self, cable_vertex):
        """
        In the map-data x-axis is towards East and y-axis is towards North and z-axis is elevation.
        In ac-files the y-axis is pointing upwards and the z-axis points to South -
        therefore y and z are switched and z * -1
        """
        numvert_lines = str(cable_vertex.x + math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y + math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x - math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y - math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x)
        numvert_lines += " " + str(cable_vertex.elevation + self.radius)
        numvert_lines += " " + str(-1*cable_vertex.y)
        return numvert_lines

    def make_ac_entry(self, material):
        """
        Returns an ac entry for this cable.
        """
        lines = []
        lines.append("OBJECT group")
        lines.append("kids " + str(len(self.vertices) - 1))
        for i in xrange(0, len(self.vertices) - 1):
            lines.append("OBJECT poly")
            lines.append("numvert 6")
            lines.append(self._create_numvert_lines(self.vertices[i]))
            lines.append(self._create_numvert_lines(self.vertices[i + 1]))
            lines.append("numsurf 3")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("0 0 0")
            lines.append("3 0 0")
            lines.append("5 0 0")
            lines.append("2 0 0")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("0 0 0")
            lines.append("1 0 0")
            lines.append("4 0 0")
            lines.append("3 0 0")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("4 0 0")
            lines.append("1 0 0")
            lines.append("2 0 0")
            lines.append("5 0 0")
            lines.append("kids 0")
        return "\n".join(lines)


class CableVertex(object):
    def __init__(self, out, height, top_cable=False, no_catenary=False):
        self.out = out  # the distance from the middle vertical line of the pylon
        self.height = height  # the distance above ground relative to the pylon's ground level (y-axis in ac-file)
        self.top_cable = top_cable  # for the cables at the top, which are not executing the main task
        self.no_catenary = no_catenary  # for cables which should not bend, e.g. lower cable of rail overhead line
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters

    def calc_position(self, pylon_x, pylon_y, pylon_elevation, pylon_heading):
        self.elevation = pylon_elevation + self.height
        self.x = pylon_x + math.sin(math.radians(pylon_heading + 90))*self.out
        self.y = pylon_y + math.cos(math.radians(pylon_heading + 90))*self.out

    def set_position(self, x, y, elevation):
        self.x = x
        self.y = y
        self.elevation = elevation


def create_generic_pylon_25_vertices():
    vertices = [CableVertex(5.0, 12.6)
                , CableVertex(-5.0, 12.6)
                , CableVertex(5.0, 16.8)
                , CableVertex(-5.0, 16.8)
                , CableVertex(5.0, 21.0)
                , CableVertex(-5.0, 21.0)
                , CableVertex(0.0, 25.2, top_cable=True)]
    return vertices


def create_generic_pylon_50_vertices():
    vertices = [CableVertex(10.0, 25.2)
                , CableVertex(-10.0, 25.2)
                , CableVertex(10.0, 33.6)
                , CableVertex(-10.0, 33.6)
                , CableVertex(10.0, 42.0)
                , CableVertex(-10.0, 42.0)
                , CableVertex(0.0, 50.4, top_cable=True)]
    return vertices


def create_generic_pylon_100_vertices():
    vertices = [CableVertex(20.0, 50.4)
                , CableVertex(-20.0, 50.4)
                , CableVertex(20.0, 67.2)
                , CableVertex(-20.0, 67.2)
                , CableVertex(20.0, 84.0)
                , CableVertex(-20.0, 84.0)
                , CableVertex(0.0, 100.8, top_cable=True)]
    return vertices


def create_wooden_pole_14m_vertices():
    vertices = [CableVertex(1.7, 14.4)
                , CableVertex(-1.7, 14.4)
                , CableVertex(2.7, 12.6)
                , CableVertex(0.7, 12.6)
                , CableVertex(-2.7, 12.6)
                , CableVertex(-0.7, 12.6)]
    return vertices


def create_drag_lift_pylon():
    vertices = [CableVertex(2.8, 8.1)
                , CableVertex(-0.8, 8.1)]
    return vertices


def create_drag_lift_in_osm_building():
    vertices = [CableVertex(2.8, 3.0)
                , CableVertex(-0.8, 3.0)]
    return vertices


def create_rail_power_vertices(direction_type):
    if direction_type == SharedPylon.DIRECTION_TYPE_MIRROR:
        vertices = [CableVertex(-1.95, 5.85)
                    , CableVertex(-1.95, 4.95, no_catenary=True)]
    else:
        vertices = [CableVertex(1.95, 5.85)
                    , CableVertex(1.95, 4.95, no_catenary=True)]
    return vertices


def create_rail_stop_tension():
    vertices = [CableVertex(0, 5.35)
                , CableVertex(0, 4.95, no_catenary=True)]
    return vertices


def get_cable_vertices(pylon_model, direction_type):
    if "generic_pylon_25m" in pylon_model:
        return create_generic_pylon_25_vertices()
    if "generic_pylon_50m" in pylon_model:
        return create_generic_pylon_50_vertices()
    if "generic_pylon_100m" in pylon_model:
        return create_generic_pylon_100_vertices()
    elif "drag_lift_pylon" in pylon_model:
        return create_drag_lift_pylon()
    elif "create_drag_lift_in_osm_building" in pylon_model:
        return create_drag_lift_in_osm_building()
    elif "wooden_pole_14m" in pylon_model:
        return create_wooden_pole_14m_vertices()
    elif "RailPower" in pylon_model:
        return create_rail_power_vertices(direction_type)
    elif "tension" in pylon_model:
        return create_rail_stop_tension()
    else:
        return None


class WaySegment(object):
    """Represents the part between the pylons and is a container for the cables"""

    def __init__(self, start_pylon, end_pylon):
        self.start_pylon = start_pylon
        self.end_pylon = end_pylon
        self.cables = []
        self.length = calc_distance(start_pylon.x, start_pylon.y, end_pylon.x, end_pylon.y)
        self.heading = calc_angle_of_line(start_pylon.x, start_pylon.y
                                          , end_pylon.x, end_pylon.y)


class SharedPylon(object):
    DIRECTION_TYPE_NORMAL = 0  # in ac-file mast is on left side, stuff on right side along x-axis
    DIRECTION_TYPE_MIRROR = 1
    DIRECTION_TYPE_START = 2
    DIRECTION_TYPE_END = 3

    def __init__(self):
        self.type_ = 0  # cf. class constants TYPE_*
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters
        self.heading = 0.0  # heading of pylon in degrees
        self.pylon_model = None  # the path to the ac/xml model
        self.needs_stg_entry = True
        self.direction_type = SharedPylon.DIRECTION_TYPE_NORMAL  # correction for which direction mast looks at

    def calc_global_coordinates(self, my_elev_interpolator, my_coord_transformator):
        self.lon, self.lat = my_coord_transformator.toGlobal((self.x, self.y))
        self.elevation = my_elev_interpolator(vec2d.vec2d(self.lon, self.lat), True)

    def make_stg_entry(self):
        """
        Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        if not self.needs_stg_entry:
            return " "  # no need to write a shared object

        direction_correction = 0
        if self.direction_type == SharedPylon.DIRECTION_TYPE_MIRROR:
            direction_correction = 180
        elif self.direction_type == SharedPylon.DIRECTION_TYPE_END:
            direction_correction = 0
        elif self.direction_type == SharedPylon.DIRECTION_TYPE_START:
            direction_correction = 180

        entry = ["OBJECT_SHARED", self.pylon_model, str(self.lon), str(self.lat), str(self.elevation)
                 , str(stg_angle(self.heading - 90 + direction_correction))]  # 90 less because arms are in x-direction in ac-file
        return " ".join(entry)


class Pylon(SharedPylon):
    TYPE_POWER_TOWER = 11  # OSM-key = "power", value = "tower"
    TYPE_POWER_POLE = 12  # OSM-key = "power", value = "pole"
    TYPE_AERIALWAY_PYLON = 21  # OSM-key = "aerialway", value = "pylon"
    TYPE_AERIALWAY_STATION = 22  # OSM-key = "aerialway", value = "station"

    def __init__(self, osm_id):
        super(Pylon, self).__init__()
        self.osm_id = osm_id
        self.height = 0.0  # parsed as float
        self.structure = None
        self.material = None
        self.colour = None
        self.prev_pylon = None
        self.next_pylon = None
        self.in_osm_building = False  # a pylon can be in a OSM Way/building, in which case it should not be drawn

    def calc_pylon_model(self, pylon_model):
        if self.type_ == Pylon.TYPE_AERIALWAY_STATION:
            if self.in_osm_building:
                self.needs_stg_entry = False
                self.pylon_model = pylon_model + "_in_osm_building"
            else:
                if not self.prev_pylon:
                    self.pylon_model = pylon_model + "_start_station"
                else:
                    self.pylon_model = pylon_model + "_end_station"
        else:
            self.pylon_model = pylon_model


class LineWithoutCables(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.shared_pylons = []  # SharedPylons

    def make_shared_pylons_stg_entries(self):
        """
        Returns the stg entries for the pylons of this WayLine in a string separated by linebreaks
        """
        entries = []
        for my_pylon in self.shared_pylons:
            entries.append(my_pylon.make_stg_entry())
        return "\n".join(entries)

    def get_center_coordinates(self):
        """Returns the lon/lat coordinates of the line"""
        if len(self.shared_pylons) == 0:  # FIXME
            return 0, 0
        else:  # FIXME: needs to be calculated more properly with shapely
            if len(self.shared_pylons) == 1:
                my_shared_pylon = self.shared_pylons[0]
            else:
                my_shared_pylon = self.shared_pylons[1]
            return my_shared_pylon.lon, my_shared_pylon.lat


class Landuse(LineWithoutCables):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for landuses constructed by osm2pylons and not in original data from OSM

    def __init__(self, osm_id):
        super(Landuse, self).__init__(osm_id)
        self.type_ = 0
        self.polygon = None
        self.number_of_buildings = 0


class Highway(LineWithoutCables):
    TYPE_MOTORWAY = 11
    TYPE_TRUNK = 12
    TYPE_PRIMARY = 13
    TYPE_SECONDARY = 14
    TYPE_TERTIARY = 15
    TYPE_UNCLASSIFIED = 16
    TYPE_ROAD = 17
    TYPE_RESIDENTIAL = 18
    TYPE_LIVING_STREET = 19
    TYPE_SERVICE = 20

    OFFSET = 5
    DEFAULT_DISTANCE = 50

    def __init__(self, osm_id):
        super(Highway, self).__init__(osm_id)
        self.type_ = 0
        self.linear = None  # The LineaString of the line
        self.is_roundabout = False

    def calc_and_map(self, my_elev_interpolator, my_coord_transformator):
        if self.is_roundabout:
            shared_pylon = SharedPylon()
            shared_pylon.pylon_model = "Models/StreetFurniture/Streetlamp3.xml"
            p = Polygon(self.linear)
            shared_pylon.x = p.centroid.x
            shared_pylon.y = p.centroid.y
            self.shared_pylons.append(shared_pylon)
        else:
            model = "Models/StreetFurniture/Streetlamp2.xml"
            parallel_offset = 2.5
            if self.type_ in [Highway.TYPE_SERVICE, Highway.TYPE_RESIDENTIAL, Highway.TYPE_LIVING_STREET]:
                model = "Models/StreetFurniture/Streetlamp1.xml"
            elif self.type_ in [Highway.TYPE_ROAD, Highway.TYPE_UNCLASSIFIED, Highway.TYPE_TERTIARY]:
                parallel_offset = 3.0
            elif self.type_ in [Highway.TYPE_SECONDARY, Highway.TYPE_PRIMARY, Highway.TYPE_TRUNK]:
                parallel_offset = 3.5
            else:  # MOTORWAY
                parallel_offset = 7
            # FIXME: calculate parallel_offset based on lanes

            self.shared_pylons = []  # list of SharedPylon
            x, y = self.linear.coords[0]
            shared_pylon = SharedPylon()
            shared_pylon.x = x
            shared_pylon.y = y
            shared_pylon.needs_stg_entry = False
            shared_pylon.calc_global_coordinates(my_elev_interpolator, my_coord_transformator)
            self.shared_pylons.append(shared_pylon)  # used for calculating heading - especially if only one lamp

            my_length = self.linear.length  # omit recalculating length all the time
            my_right_parallel = self.linear.parallel_offset(parallel_offset, 'right', join_style=1)
            my_right_parallel_length = my_right_parallel.length
            current_distance = Highway.OFFSET  # the distance from the origin of the current streetlamp

            while True:
                if current_distance > my_length:
                    break
                point_on_line = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
                shared_pylon = SharedPylon()
                shared_pylon.x = point_on_line.x
                shared_pylon.y = point_on_line.y
                shared_pylon.pylon_model = model
                shared_pylon.direction_type = SharedPylon.DIRECTION_TYPE_MIRROR
                shared_pylon.calc_global_coordinates(my_elev_interpolator, my_coord_transformator)
                self.shared_pylons.append(shared_pylon)
                current_distance += Highway.DEFAULT_DISTANCE

            # calculate heading
            calc_heading_nodes(self.shared_pylons)


class Line(LineWithoutCables):
    def __init__(self, osm_id):
        super(Line, self).__init__(osm_id)
        self.way_segments = []
        self.length = 0.0  # the total length of all segments

    def _calc_segments(self):
        """Creates the segments of this WayLine and calculates the total length.
        Returns the maximum length of segments"""
        max_length = 0.0
        total_length = 0.0
        self.way_segments = []  # if this method would be called twice by mistake
        for x in range(0, len(self.shared_pylons) - 1):
            segment = WaySegment(self.shared_pylons[x], self.shared_pylons[x + 1])
            self.way_segments.append(segment)
            if segment.length > max_length:
                max_length = segment.length
            total_length += segment.length
        self.length = total_length
        return max_length

    def _calc_cables(self, radius, number_extra_vertices, catenary_a):
        """
        Creates the cables per WaySegment. First find the start and end points depending on pylon model.
        Then calculate the local positions of all start and end points.
        Afterwards use the start and end points to create all cables for a given WaySegment
        """
        for segment in self.way_segments:
            start_cable_vertices = get_cable_vertices(segment.start_pylon.pylon_model
                                                      , segment.start_pylon.direction_type)
            end_cable_vertices = get_cable_vertices(segment.end_pylon.pylon_model
                                                    , segment.end_pylon.direction_type)
            for i in xrange(0, len(start_cable_vertices)):
                my_radius = radius
                my_number_extra_vertices = number_extra_vertices
                start_cable_vertices[i].calc_position(segment.start_pylon.x, segment.start_pylon.y
                                                      , segment.start_pylon.elevation, segment.start_pylon.heading)
                end_cable_vertices[i].calc_position(segment.end_pylon.x, segment.end_pylon.y
                                                    , segment.end_pylon.elevation, segment.end_pylon.heading)
                if start_cable_vertices[i].top_cable:
                    my_radius = parameters.C2P_RADIUS_TOP_LINE
                if start_cable_vertices[i].no_catenary:
                    my_number_extra_vertices = 0
                cable = Cable(start_cable_vertices[i], end_cable_vertices[i], my_radius, my_number_extra_vertices
                              , catenary_a, segment.length)
                segment.cables.append(cable)

    def make_cables_ac_xml_stg_entries(self, filename, path, cluster_max_length):
        """
        Returns the stg entries for the cables of this WayLine in a string separated by linebreaks
        E.g. OBJECT_STATIC LSZSpylons1901.xml 9.75516 46.4135 2000.48 0
        Before this it creates the xml-file and ac-file containing the cables.
        Each WaySegment is represented as an object group in ac with each cable of the WaySegment as a kid

        In order to reduce rounding errors clusters of WaySegments are used instead of a whole WayLine per file.
        """
        stg_entries = []
        cluster_segments = []
        cluster_length = 0.0
        cluster_index = 1
        start_pylon = None
        for i in xrange(0, len(self.way_segments)):
            way_segment = self.way_segments[i]
            if start_pylon is None:
                start_pylon = way_segment.start_pylon
            cluster_segments.append(way_segment)
            cluster_length += way_segment.length
            if (cluster_length >= cluster_max_length) or (len(self.way_segments) - 1 == i):
                cluster_filename = filename + '_' + str(cluster_index)
                ac_file_lines = []
                ac_file_lines.append("AC3Db")
                ac_file_lines.append('MATERIAL "cable" rgb 0.3 0.3 0.3 amb 0.3 0.3 0.3 emis 0.0 0.0 0.0 spec 0.3 0.3 0.3 shi 1 trans 0')
                ac_file_lines.append("OBJECT world")
                ac_file_lines.append("kids " + str(len(cluster_segments)))
                cluster_segment_index = 0
                for cluster_segment in cluster_segments:
                    cluster_segment_index += 1
                    ac_file_lines.append("OBJECT group")
                    ac_file_lines.append('name "segment%05d"' % cluster_segment_index)
                    ac_file_lines.append("kids " + str(len(cluster_segment.cables)))
                    for cable in cluster_segment.cables:
                        cable.translate_vertices_relative(start_pylon.x, start_pylon.y, start_pylon.elevation)
                        ac_file_lines.append(cable.make_ac_entry(0))  # material is 0-indexed
                with open(path + cluster_filename + ".ac", 'w') as f:
                    f.write("\n".join(ac_file_lines))

                xml_file_lines = []
                xml_file_lines.append('<?xml version="1.0"?>')
                xml_file_lines.append('<PropertyList>')
                xml_file_lines.append('<path>' + cluster_filename + '.ac</path>')  # the ac-file is in the same directory
                xml_file_lines.append('<animation>')
                xml_file_lines.append('<type>range</type>')
                xml_file_lines.append('<min-m>0</min-m>')
                xml_file_lines.append('<max-property>/sim/rendering/static-lod/rough</max-property>')
                for j in xrange(1, len(cluster_segments) + 1):
                    xml_file_lines.append('<object-name>segment%05d</object-name>' % j)
                xml_file_lines.append('</animation>')
                if parameters.C2P_CABLES_NO_SHADOW:
                    xml_file_lines.append('<animation>')
                    xml_file_lines.append('<type>noshadow</type>')
                    for j in xrange(1, len(cluster_segments) + 1):
                        xml_file_lines.append('<object-name>segment%05d</object-name>' % j)
                    xml_file_lines.append('</animation>')
                xml_file_lines.append('</PropertyList>')
                with open(path + cluster_filename + ".xml", 'w') as f:
                    f.write("\n".join(xml_file_lines))

                entry = ["OBJECT_STATIC", cluster_filename + ".xml", str(start_pylon.lon)
                         , str(start_pylon.lat), str(start_pylon.elevation), "90"]
                stg_entries.append(" ".join(entry))

                cluster_length = 0.0
                cluster_segments = []
                cluster_index += 1
                start_pylon = None

        return "\n".join(stg_entries)


class WayLine(Line):  # The name "Line" is also used in e.g. SymPy
    TYPE_POWER_LINE = 11  # OSM-key = "power", value = "line"
    TYPE_POWER_MINOR_LINE = 12  # OSM-key = "power", value = "minor_line"
    TYPE_AERIALWAY_CABLE_CAR = 21  # OSM-key = "aerialway", value = "cable_car"
    TYPE_AERIALWAY_CHAIR_LIFT = 22  # OSM-key = "aerialway", value = "chair_lift" or "mixed_lift"
    TYPE_AERIALWAY_DRAG_LIFT = 23  # OSM-key = "aerialway", value = "drag_lift" or "t-bar" or "j-bar" or "platter"
    TYPE_AERIALWAY_GONDOLA = 24  # OSM-key = "aerialway", value = "gondola"
    TYPE_AERIALWAY_GOODS = 25  # OSM-key = "aerialway", value = "goods"

    def __init__(self, osm_id):
        super(WayLine, self).__init__(osm_id)
        self.type_ = 0  # cf. class constants TYPE_*
        self.voltage = 0  # from osm-tag "voltage"
        self.cables = 0  # from osm-tag "cables"
        self.wires = None  # from osm-tag "wires"

    def is_aerialway(self):
        return (self.type_ != self.TYPE_POWER_LINE) and (self.type_ != self.TYPE_POWER_MINOR_LINE)

    def calc_and_map(self):
        """Calculates various aspects of the line and its nodes and attempt to correct if needed. """
        max_length = self._calc_segments()
        if self.is_aerialway():
            pylon_model = self._calc_and_map_aerialway()
        else:
            pylon_model = self._calc_and_map_powerline(max_length)
        for my_pylon in self.shared_pylons:
            my_pylon.pylon_model = pylon_model

        calc_heading_nodes(self.shared_pylons)

        # calc cables
        radius = parameters.C2P_RADIUS_POWER_LINE
        number_extra_vertices = parameters.C2P_EXTRA_VERTICES_POWER_LINE
        catenary_a = parameters.C2P_CATENARY_A_POWER_LINE
        if self.type_ == self.TYPE_POWER_MINOR_LINE:
            radius = parameters.C2P_RADIUS_POWER_MINOR_LINE
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_POWER_MINOR_LINE
            catenary_a = parameters.C2P_CATENARY_A_POWER_MINOR_LINE
        elif self.type_ == self.TYPE_AERIALWAY_CABLE_CAR:
            radius = parameters.C2P_RADIUS_AERIALWAY_CABLE_CAR
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_CABLE_CAR
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_CABLE_CAR
        elif self.type_ == self.TYPE_AERIALWAY_CHAIR_LIFT:
            radius = parameters.C2P_RADIUS_AERIALWAY_CHAIR_LIFT
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_CHAIR_LIFT
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_CHAIR_LIFT
        elif self.type_ == self.TYPE_AERIALWAY_DRAG_LIFT:
            radius = parameters.C2P_RADIUS_AERIALWAY_DRAG_LIFT
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_DRAG_LIFT
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_DRAG_LIFT
        elif self.type_ == self.TYPE_AERIALWAY_GONDOLA:
            radius = parameters.C2P_RADIUS_AERIALWAY_GONDOLA
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_GONDOLA
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_GONDOLA
        elif self.type_ == self.TYPE_AERIALWAY_GOODS:
            radius = parameters.C2P_RADIUS_AERIALWAY_GOODS
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_GOODS
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_GOODS
        self._calc_cables(radius, number_extra_vertices, catenary_a)

    def _calc_and_map_aerialway(self):
        pylon_model = "Models/Transport/drag_lift_pylon.xml"  # FIXME: make real implementation
        return pylon_model

    def _calc_and_map_powerline(self, max_length):
        """
        Danish rules of thumb:
        400KV: height 30-42 meter, distance 200-420 meter, sagging 4.5-13 meter, a_value 1110-1698
        150KV: height 25-32 meter, distance 180-350 meter, sagging 2.5-9 meter, a_value 1614-1702
        60KV: height 15-25 meter, distance 100-250 meter, sagging 1-5 meter, a_value 1238-1561
        The a_value for the catenary function has been calculated with osm2pylon.optimize_catenary().
        """
        # calculate min, max, averages etc.
        max_height = 0.0
        average_height = 0.0
        found = 0
        nbr_poles = 0
        nbr_towers = 0
        for my_pylon in self.shared_pylons:
            if my_pylon.type_ == Pylon.TYPE_POWER_TOWER:
                nbr_towers += 1
            elif my_pylon.type_ == Pylon.TYPE_POWER_POLE:
                nbr_poles += 1
            if my_pylon.height > 0:
                average_height += my_pylon.height
                found += 1
            if my_pylon.height > max_height:
                max_height = my_pylon.height
        if found > 0:
            average_height /= found

        # use statistics to determine type_ and pylon_model
        if (self.type_ == self.TYPE_POWER_MINOR_LINE and nbr_towers <= nbr_poles
           and max_height <= 25.0 and max_length <= 250.0) or (self.type_ == self.TYPE_POWER_LINE and max_length <= 150):
            self.type_ = self.TYPE_POWER_MINOR_LINE
            pylon_model = "Models/Power/wooden_pole_14m.xml"
        else:
            self.type_ = self.TYPE_POWER_LINE
            if average_height < 35.0 and max_length < 300.0:
                pylon_model = "Models/Power/generic_pylon_25m.xml"
            elif average_height < 75.0 and max_length < 500.0:
                pylon_model = "Models/Power/generic_pylon_50m.xml"
            elif parameters.C2P_POWER_LINE_ALLOW_100M:
                pylon_model = "Models/Power/generic_pylon_100m.xml"
            else:
                pylon_model = "Models/Power/generic_pylon_50m.xml"

        return pylon_model


class RailNode(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.switch = False
        self.buffer_stop = False
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters


class RailMast(SharedPylon):
    TYPE_VIRTUAL_MAST = 10  # only used at endpoints of RailLine for calcs - not used for visual masts
    TYPE_SINGLE_MAST = 11
    TYPE_DOUBLE_MAST = 12
    TYPE_STOP_MAST = 20

    def __init__(self, type_, point_on_line, mast_point, direction_type):
        super(RailMast, self).__init__()
        self.type_ = type_
        self.point_on_line = point_on_line
        self.x = mast_point.x
        self.y = mast_point.y
        self.pylon_model = "Models/StreetFurniture/RailPower.xml"
        if self.type_ == RailMast.TYPE_VIRTUAL_MAST:
            self.needs_stg_entry = False
        elif self.type_ == RailMast.TYPE_STOP_MAST:
            self.pylon_model = "Models/StreetFurniture/rail_stop_tension.xml"
        self.direction_type = direction_type


class RailLine(Line):
    TYPE_RAILWAY_GAUGE_NARROW = 11
    TYPE_RAILWAY_GAUGE_NORMAL = 12

    DEFAULT_MAST_DISTANCE = 60  # if this is changed then mast algorithm for radius below must be adapted
    OFFSET = 20  # the offset from end points
    MAX_DEVIATION = 1  # The distance the overhead line can be off from the center
    MAST_BUFFER = 3.0

    def __init__(self, osm_id):
        super(RailLine, self).__init__(osm_id)
        self.type_ = 0
        self.nodes = []  # RailNodes
        self.linear = None  # The LineaString of the line

    def calc_and_map(self, my_elev_interpolator, my_coord_transformator, rail_lines_list):
        self.shared_pylons = []  # array of RailMasts
        current_distance = 0  # the distance from the origin of the current mast
        my_length = self.linear.length  # omit recalculating length all the time
        # offset must be same as create_rail_power_vertices()
        my_right_parallel = self.linear.parallel_offset(1.95, 'right', join_style=1)
        my_right_parallel_length = my_right_parallel.length
        my_left_parallel = self.linear.parallel_offset(1.95, 'left', join_style=1)
        my_left_parallel_length = my_left_parallel.length

        # virtual start point
        point_on_line = self.linear.interpolate(0)
        mast_point = my_right_parallel.interpolate(my_right_parallel_length)
        if self.nodes[0].buffer_stop:
            self.shared_pylons.append(RailMast(RailMast.TYPE_STOP_MAST, point_on_line, point_on_line
                                               , SharedPylon.DIRECTION_TYPE_START))
        else:
            self.shared_pylons.append(RailMast(RailMast.TYPE_VIRTUAL_MAST, point_on_line, mast_point
                                               , SharedPylon.DIRECTION_TYPE_MIRROR))
        prev_point = point_on_line

        # get the first mast point
        if my_length < RailLine.DEFAULT_MAST_DISTANCE:
            current_distance += (my_length / 2)
            point_on_line = self.linear.interpolate(current_distance)
            mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
            is_right = self.check_mast_left_right(mast_point, rail_lines_list)
            if not is_right:
                mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
            self.shared_pylons.append(RailMast(RailMast.TYPE_SINGLE_MAST, point_on_line, mast_point, is_right))
        else:
            current_distance += RailLine.OFFSET
            point_on_line = self.linear.interpolate(current_distance)
            mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
            is_right = self.check_mast_left_right(mast_point, rail_lines_list)
            if is_right:
                direction_type = SharedPylon.DIRECTION_TYPE_MIRROR
            else:
                direction_type = SharedPylon.DIRECTION_TYPE_NORMAL
                mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
            self.shared_pylons.append(RailMast(RailMast.TYPE_SINGLE_MAST, point_on_line, mast_point, direction_type))
            prev_angle = calc_angle_of_line(prev_point.x, prev_point.y, point_on_line.x, point_on_line.y)
            prev_point = point_on_line
            # find new masts along the line with a simple approximation for less distance between masts
            # if the radius gets tighter
            while True:
                if (my_length - current_distance) <= RailLine.OFFSET:
                    break
                min_distance = my_length - current_distance - RailLine.OFFSET
                if min_distance < RailLine.DEFAULT_MAST_DISTANCE:
                    current_distance += min_distance
                else:
                    test_distance = current_distance + RailLine.DEFAULT_MAST_DISTANCE
                    point_on_line = self.linear.interpolate(test_distance)
                    new_angle = calc_angle_of_line(prev_point.x, prev_point.y, point_on_line.x, point_on_line.y)
                    difference = abs(new_angle - prev_angle)
                    if difference >= 25:
                        current_distance += 10
                    elif difference >= 20:
                        current_distance += 20
                    elif difference >= 15:
                        current_distance += 30
                    elif difference >= 10:
                        current_distance += 40
                    elif difference >= 5:
                        current_distance += 50
                    else:
                        current_distance += RailLine.DEFAULT_MAST_DISTANCE
                point_on_line = self.linear.interpolate(current_distance)
                mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
                is_right = self.check_mast_left_right(mast_point, rail_lines_list)
                if is_right:
                    direction_type = SharedPylon.DIRECTION_TYPE_MIRROR
                else:
                    direction_type = SharedPylon.DIRECTION_TYPE_NORMAL
                    mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
                self.shared_pylons.append(RailMast(RailMast.TYPE_SINGLE_MAST, point_on_line, mast_point, direction_type))
                prev_angle = calc_angle_of_line(prev_point.x, prev_point.y, point_on_line.x, point_on_line.y)
                prev_point = point_on_line

        # virtual end point
        point_on_line = self.linear.interpolate(my_length)
        mast_point = my_right_parallel.interpolate(0)
        if self.nodes[-1].buffer_stop:
            self.shared_pylons.append(RailMast(RailMast.TYPE_STOP_MAST, point_on_line, point_on_line
                                               , SharedPylon.DIRECTION_TYPE_END))
        else:
            self.shared_pylons.append(RailMast(RailMast.TYPE_VIRTUAL_MAST, point_on_line, mast_point
                                               , SharedPylon.DIRECTION_TYPE_MIRROR))

        # calculate heading
        calc_heading_nodes(self.shared_pylons)

        # segments
        self._calc_segments()

        # calculate global coordinates
        for my_mast in self.shared_pylons:
            my_mast.calc_global_coordinates(my_elev_interpolator, my_coord_transformator)

        # cables
        self._calc_cables(parameters.C2P_RADIUS_OVERHEAD_LINE, parameters.C2P_EXTRA_VERTICES_OVERHEAD_LINE
                          , parameters.C2P_CATENARY_A_OVERHEAD_LINE)

    def check_mast_left_right(self, mast_point, rail_lines_list):
        mast_buffer = mast_point.buffer(RailLine.MAST_BUFFER)
        is_right = True
        for my_line in rail_lines_list:
            if (my_line.osm_id != self.osm_id) and mast_buffer.intersects(my_line.linear):
                is_right = False
                break
        return is_right


def process_osm_building_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_buildings = {}  # osm_id as key, Polygon
    for way in ways_dict.values():
        coordinates = []
        for ref in way.refs:
            if ref in nodes_dict:
                my_node = nodes_dict[ref]
                coordinates.append(my_coord_transformator.toLocal((my_node.lon, my_node.lat)))
        if 2 < len(coordinates):
            my_polygon = Polygon(coordinates)
            if my_polygon.is_valid and not my_polygon.is_empty:
                my_buildings[way.osm_id] = my_polygon.convex_hull
    return my_buildings


def process_osm_rail_overhead(nodes_dict, ways_dict, my_elev_interpolator, my_coord_transformator):
    my_railways = {}  # osm_id as key, RailLine
    my_shared_nodes = {}  # node osm_id as key, list of WayLine objects as value

    # First reduce to electrified narrow_gauge or rail, no tunnels and no abandoned
    for way in ways_dict.values():
        my_line = RailLine(way.osm_id)
        is_railway = False
        is_electrified = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "railway" == key:
                if value == "rail":
                    is_railway = True
                    my_line.type_ = RailLine.TYPE_RAILWAY_GAUGE_NORMAL
                elif value == "narrow_gauge":
                    is_railway = True
                    my_line.type_ = RailLine.TYPE_RAILWAY_GAUGE_NARROW
                elif value == "abandoned":
                    is_challenged = True
            elif "electrified" == key:
                if value in ("contact_line", "yes"):
                    is_electrified = True
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
        if is_railway and is_electrified and (not is_challenged):
            # Process the Nodes
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_rail_node = RailNode(my_node.osm_id)
                    my_rail_node.lat = my_node.lat
                    my_rail_node.lon = my_node.lon
                    my_rail_node.x, my_rail_node.y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_rail_node.elevation = my_elev_interpolator(vec2d.vec2d(my_rail_node.lon, my_rail_node.lat), True)
                    for key in my_node.tags:
                        value = my_node.tags[key]
                        if "railway" == key and "switch" == value:
                            my_rail_node.switch = True
                        if "railway" == key and "buffer_stop" == value:
                            my_rail_node.buffer_stop = True
                    if my_rail_node.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.nodes.append(my_rail_node)
                    else:
                        logging.debug('Node outside of boundaries and therefore ignored: osm_id = %s ', my_node.osm_id)
            if len(my_line.nodes) > 1:
                my_railways[my_line.osm_id] = my_line
                if my_line.nodes[0].osm_id in my_shared_nodes.keys():
                    my_shared_nodes[my_line.nodes[0].osm_id].append(my_line)
                else:
                    my_shared_nodes[my_line.nodes[0].osm_id] = [my_line]
                if my_line.nodes[-1].osm_id in my_shared_nodes.keys():
                    my_shared_nodes[my_line.nodes[-1].osm_id].append(my_line)
                else:
                    my_shared_nodes[my_line.nodes[-1].osm_id] = [my_line]
            else:
                logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)

    # Attempt to merge lines
    for key in my_shared_nodes.keys():
        shared_node = my_shared_nodes[key]
        if len(shared_node) >= 2:
            pos1, pos2 = find_connecting_line(key, shared_node, 60)
            if pos1 >= 0:
                my_osm_id = shared_node[pos2].osm_id
                try:
                    merge_lines(key, shared_node[pos1], shared_node[pos2], my_shared_nodes)
                    del my_railways[my_osm_id]
                    del my_shared_nodes[key]
                    logging.debug("Merged two lines with node osm_id: %s", key)
                except Exception as e:
                    logging.error(e)

    #get LineStrings and remove those lines, which are less than the minimal requirement
    for the_railway in my_railways.values():
        my_coordinates = []
        for node in the_railway.nodes:
            my_coordinates.append((node.x, node.y))
        my_linear = LineString(my_coordinates)
        the_railway.linear = my_linear

    return my_railways


def process_osm_highway(nodes_dict, ways_dict, my_coord_transformator, landuse_refs):
    """
    No attempt to merge lines because most probably the lines are split at corssing.
    No attempt to guess whether there there is a division in the conter, where a street lamp with two lamps could be
    placed - e.g. using a combination of highway type, oneway, number of lanes etc
    """
    my_highways = {}  # osm_id as key, RailLine

    # First reduce to electrified narrow_gauge or rail, no tunnels and no abandoned
    for way in ways_dict.values():
        my_highway = Highway(way.osm_id)
        valid_highway = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "highway" == key:
                valid_highway = True
                if value in ["motorway", "motorway_link"]:
                    my_highway.type_ = Highway.TYPE_MOTORWAY
                elif value in ["trunk", "trunk_link"]:
                    my_highway.type_ = Highway.TYPE_TRUNK
                elif value in ["primary", "primary_link"]:
                    my_highway.type_ = Highway.TYPE_PRIMARY
                elif value in ["secondary", "secondary_link"]:
                    my_highway.type_ = Highway.TYPE_SECONDARY
                elif value in ["tertiary", "tertiary_link"]:
                    my_highway.type_ = Highway.TYPE_TERTIARY
                elif value == "unclassified":
                    my_highway.type_ = Highway.TYPE_UNCLASSIFIED
                elif value == "road":
                    my_highway.type_ = Highway.TYPE_ROAD
                elif value == "residential":
                    my_highway.type_ = Highway.TYPE_RESIDENTIAL
                elif value == "living_street":
                    my_highway.type_ = Highway.TYPE_LIVING_STREET
                elif value == "service":
                    my_highway.type_ = Highway.TYPE_SERVICE
                else:
                    valid_highway = False
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
            elif ("junction" == key) and ("roundabout" == value):
                my_highway.is_roundabout = True
        if valid_highway and not is_challenged:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_highway.linear = LineString(my_coordinates)
                my_highways[my_highway.osm_id] = my_highway

    # Test whether the highway is within appropriate land use or intersects with appropriate land use
    for key in my_highways.keys():
        my_highway = my_highways[key]
        is_within = False
        intersections = []
        for landuse_ref in landuse_refs.values():
            if my_highway.linear.within(landuse_ref.polygon):
                is_within = True
                break
            elif my_highway.linear.intersects(landuse_ref.polygon):
                intersections.append(my_highway.linear.intersection(landuse_ref.polygon))
        if not is_within:
            if len(intersections) == 0:
                del my_highways[key]
            else:
                index = 10000000000
                for intersection in intersections:
                    if isinstance(intersection, MultiLineString):
                        for my_line in intersection:
                            if isinstance(my_line, LineString):
                                intersections.append(my_line)
                        continue
                    index += 1
                    new_highway = Highway(index + key)
                    new_highway.type_ = my_highway.type_
                    new_highway.linear = intersection
                    my_highways[new_highway.osm_id] = new_highway
                del my_highways[key]

    # Remove the too short lines
    for key in my_highways.keys():
        my_highway = my_highways[key]
        if not isinstance(my_highway.linear, LineString):
            del my_highways[key]
        elif my_highway.is_roundabout and (50 > my_highway.linear.length or 300 < my_highway.linear.length):
            del my_highways[key]
        elif my_highway.linear.length < (2 * Highway.OFFSET):
            del my_highways[key]

    return my_highways


def process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator, building_refs):
    my_landuses = {}  # osm_id as key, Landuse

    # First reduce to electrified narrow_gauge or rail, no tunnels and no abandoned
    for way in ways_dict.values():
        my_landuse = Landuse(way.osm_id)
        valid_landuse = True
        for key in way.tags:
            value = way.tags[key]
            if "landuse" == key:
                if value == "commercial":
                    my_landuse.type_ = Landuse.TYPE_COMMERCIAL
                elif value == "industrial":
                    my_landuse.type_ = Landuse.TYPE_INDUSTRIAL
                elif value == "residential":
                    my_landuse.type_ = Landuse.TYPE_RESIDENTIAL
                elif value == "retail":
                    my_landuse.type_ = Landuse.TYPE_RETAIL
                else:
                    valid_landuse = False
            else:
                valid_landuse = False
        if valid_landuse:
            # Process the Nodes
            my_coordinates = []
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_landuse.polygon = Polygon(my_coordinates)
                if my_landuse.polygon.is_valid and not my_landuse.polygon.is_empty:
                    my_landuses[my_landuse.osm_id] = my_landuse

    logging.debug("OSM land-uses found: %s", len(my_landuses))
    if parameters.C2P_LANDUSE_GENERATE_LANDUSE:
        # Add "missing" landuses based on building clusters
        my_landuse_candidates = []
        index = 10000000000
        for my_building in building_refs.values():
            # check whether the building already is in a land use
            within_existing_landuse = False
            for my_landuse in my_landuses.values():
                if my_building.intersects(my_landuse.polygon):
                    within_existing_landuse = True
                    break
            if not within_existing_landuse:
                # create new clusters of land uses
                buffer_distance = parameters.C2P_LANDUSE_BUILDING_BUFFER_DISTANCE
                if my_building.area > parameters.C2P_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
                    factor = math.sqrt(my_building.area / parameters.C2P_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
                    buffer_distance = min(factor*parameters.C2P_LANDUSE_BUILDING_BUFFER_DISTANCE
                                          , parameters.C2P_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
                buffer_polygon = my_building.buffer(buffer_distance)
                buffer_polygon = buffer_polygon.convex_hull
                within_existing_landuse = False
                for candidate in my_landuse_candidates:
                    if buffer_polygon.intersects(candidate.polygon):
                        candidate.polygon = candidate.polygon.union(buffer_polygon).convex_hull
                        candidate.number_of_buildings += 1
                        within_existing_landuse = True
                        break
                if not within_existing_landuse:
                    index += 1
                    my_candidate = Landuse(index)
                    my_candidate.polygon = buffer_polygon
                    my_candidate.number_of_buildings = 1
                    my_candidate.type_ = Landuse.TYPE_NON_OSM
                    my_landuse_candidates.append(my_candidate)
        # add landuse candidates to landuses
        logging.debug("Candidate land-uses found: %s", len(my_landuses))
        for candidate in my_landuse_candidates:
            if candidate.number_of_buildings >= parameters.C2P_LANDUSE_MIN_BUILDINGS:
                my_landuses[candidate.osm_id] = candidate

    return my_landuses


def process_osm_power_aerialway(nodes_dict, ways_dict, my_elev_interpolator, my_coord_transformator, building_refs):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of WayLine objects for
    electrical power lines and a dict of WayLine objects for aerialways. Nodes are transformed to Pylons.
    The elevation of the pylons is calculated as part of this process.
    """
    my_powerlines = {}  # osm_id as key, WayLine object as value
    my_aerialways = {}  # osm_id as key, WayLine object as value
    my_shared_nodes = {}  # node osm_id as key, list of WayLine objects as value
    for way in ways_dict.values():
        my_line = WayLine(way.osm_id)
        for key in way.tags:
            value = way.tags[key]
            if "power" == key:
                if "line" == value:
                    my_line.type_ = WayLine.TYPE_POWER_LINE
                elif "minor_line" == value:
                    my_line.type_ = WayLine.TYPE_POWER_MINOR_LINE
            elif "aerialway" == key:
                if "cable_car" == value:
                    my_line.type_ = WayLine.TYPE_AERIALWAY_CABLE_CAR
                elif value in ["chair_lift", "mixed_lift"]:
                    my_line.type_ = WayLine.TYPE_AERIALWAY_CHAIR_LIFT
                elif value in ["drag_lift", "t-bar", "j-bar", "platter"]:
                    my_line.type_ = WayLine.TYPE_AERIALWAY_DRAG_LIFT
                elif "gondola" == value:
                    my_line.type_ = WayLine.TYPE_AERIALWAY_GONDOLA
                elif "goods" == value:
                    my_line.type_ = WayLine.TYPE_AERIALWAY_GOODS
            #  special values
            elif "cables" == key:
                my_line.cables = int(value)
            elif "voltage" == key:
                try:
                    my_line.voltage = int(value)
                except ValueError:
                    pass  # principally only substations may have values like "100000;25000", but only principally ...
            elif "wires" == key:
                my_line.wires = value
        if 0 != my_line.type_:
            prev_pylon = None
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_pylon = Pylon(my_node.osm_id)
                    my_pylon.lat = my_node.lat
                    my_pylon.lon = my_node.lon
                    my_pylon.x, my_pylon.y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_pylon.elevation = my_elev_interpolator(vec2d.vec2d(my_pylon.lon, my_pylon.lat), True)
                    for key in my_node.tags:
                        value = my_node.tags[key]
                        if "power" == key:
                            if "tower" == value:
                                my_pylon.type_ = Pylon.TYPE_POWER_TOWER
                            elif "pole" == value:
                                my_pylon.type_ = Pylon.TYPE_POWER_POLE
                        elif "aerialway" == key:
                            if "pylon" == value:
                                my_pylon.type_ = Pylon.TYPE_AERIALWAY_PYLON
                            elif "station" == value:
                                my_pylon.type_ = Pylon.TYPE_AERIALWAY_STATION
                                my_point = Point(my_pylon.x, my_pylon.y)
                                for osm_id in building_refs.keys():
                                    building_ref = building_refs[osm_id]
                                    if building_ref.contains(my_point):
                                        my_pylon.in_osm_building = True
                                        logging.debug('Station with osm_id = %s found within building reference', my_pylon.osm_id)
                                        break
                        elif "height" == key:
                            my_pylon.height = osmparser.parse_length(value)
                        elif "structure" == key:
                            my_pylon.structure = value
                        elif "material" == key:
                            my_pylon.material = value
                    if my_pylon.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.shared_pylons.append(my_pylon)
                    else:
                        logging.debug('Node outside of boundaries and therefore ignored: osm_id = %s', my_node.osm_id)
                    if None != prev_pylon:
                        prev_pylon.next_pylon = my_pylon
                        my_pylon.prev_pylon = prev_pylon
                    prev_pylon = my_pylon
            if len(my_line.shared_pylons) > 1:
                for the_node in [my_line.shared_pylons[0], my_line.shared_pylons[-1]]:
                    if the_node.osm_id in my_shared_nodes.keys():
                        my_shared_nodes[the_node.osm_id].append(my_line)
                    else:
                        my_shared_nodes[the_node.osm_id] = [my_line]
                if my_line.is_aerialway():
                    my_aerialways[my_line.osm_id] = my_line
                else:
                    my_powerlines[my_line.osm_id] = my_line
            else:
                logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)

    for key in my_shared_nodes.keys():
        shared_node = my_shared_nodes[key]
        if (len(shared_node) == 2) and (shared_node[0].type_ == shared_node[1].type_):
            my_osm_id = shared_node[1].osm_id
            try:
                merge_lines(key, shared_node[0], shared_node[1], my_shared_nodes)
                if shared_node[0].is_aerialway():
                    del my_aerialways[my_osm_id]
                else:
                    del my_powerlines[my_osm_id]
                del my_shared_nodes[key]
                logging.debug("Merged two lines with node osm_id: %s", key)
            except Exception as e:
                logging.error(e)
        elif len(shared_node) > 2:
            logging.warning("A node is referenced in more than two ways. Most likely OSM problem. Node osm_id: %s", key)

    return my_powerlines, my_aerialways


def find_connecting_line(key, lines, max_allowed_angle=360):
    """
    In the array of lines checks which 2 lines have an angle closest to 180 degrees at end node key.
    Looked at second last node and end node (key).
    If the found angle is larger than the max_allowed_angle at the end, then -1 is returned for pos1
    """
    angles = []
    # Get the angle of each line
    for line in lines:
        if line.nodes[0].osm_id == key:
            angle = calc_angle_of_line(line.nodes[0].x, line.nodes[0].y, line.nodes[1].x, line.nodes[1].y)
        elif line.nodes[-1].osm_id == key:
            angle = calc_angle_of_line(line.nodes[-1].x, line.nodes[-1].y, line.nodes[-2].x, line.nodes[-2].y)
        else:
            raise Exception("The referenced node is not at the beginning or end of line0")
        angles.append(angle)
    # Get the angles between all line pairs and find the one closest to 180 degrees
    pos1 = 0
    pos2 = 1
    max_angle = 500
    for i in xrange(0, len(angles) - 1):
        for j in xrange(i + 1, len(angles)):
            angle_between = abs(abs(angles[i] - angles[j]) - 180)
            if angle_between < max_angle:
                max_angle = angle_between
                pos1 = i
                pos2 = j
    if max_angle > max_allowed_angle:
        pos1 = -1
    return pos1, pos2


def merge_lines(osm_id, line0, line1, shared_nodes):
    """
    Takes two Line objects and attempts to merge them at a given node.
    The added/merged pylons are in line0 in correct sequence.
    Makes sure that line1 is replaced by line0 in shared_nodes.
    Raises Exception if the referenced node is not at beginning or end of the two lines.
    """
    if line0.nodes[0].osm_id == osm_id:
        line0_first = True
    elif line0.nodes[-1].osm_id == osm_id:
        line0_first = False
    else:
        raise Exception("The referenced node is not at the beginning or end of line0")
    if line1.nodes[0].osm_id == osm_id:
        line1_first = True
    elif line1.nodes[-1].osm_id == osm_id:
        line1_first = False
    else:
        raise Exception("The referenced node is not at the beginning or end of line1")

    # combine line1 into line0 in correct sequence (e.g. line0(A,B) + line1(C,B) -> line0(A,B,C)
    if (False == line0_first) and (True == line1_first):
        for x in range(1, len(line1.nodes)):
            line0.nodes.append(line1.nodes[x])
    elif (False == line0_first) and (False == line1_first):
        for x in range(0, len(line1.nodes) - 1):
            line0.nodes.append(line1.nodes[len(line1.nodes) - x - 2])
    elif (True == line0_first) and (True == line1_first):
        for x in range(1, len(line1.nodes)):
            line0.nodes.insert(0, line1.nodes[x])
    else:
        for x in range(0, len(line1.nodes) - 1):
            line0.nodes.insert(0, line1.nodes[len(line1.nodes) - x - 2])

    # in shared_nodes replace line1 with line2
    for shared_node in shared_nodes.values():
        has_line0 = False
        pos_line1 = -1
        for i in xrange(0, len(shared_node)):
            if shared_node[i].osm_id == line0.osm_id:
                has_line0 = True
            if shared_node[i].osm_id == line1.osm_id:
                pos_line1 = i
        if pos_line1 >= 0:
            del shared_node[pos_line1]
            if not has_line0:
                shared_node.append(line0)


def write_stg_entries(stg_fp_dict, lines_dict, wayname, cluster_max_length):
    line_index = 0
    for line in lines_dict.values():
        line_index += 1
        line_center = line.get_center_coordinates()
        stg_fname = calc_tile.construct_stg_file_name(line_center)
        if parameters.PATH_TO_OUTPUT:
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_OUTPUT, line_center)
        else:
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, line_center)
        if not stg_fname in stg_fp_dict:
            if not os.path.exists(path):
                try:
                    os.makedirs(path)
                except OSError:
                    logging.exception("Unable to create path to output directory")
                    pass
            stg_io.uninstall_ours(path, stg_fname, OUR_MAGIC)
            stg_file = open(path + stg_fname, "a")
            logging.info('Opening new stg-file for append: ' + path + stg_fname)
            stg_file.write(stg_io.delimiter_string(OUR_MAGIC, True) + "\n# do not edit below this line\n#\n")
            stg_fp_dict[stg_fname] = stg_file
        else:
            stg_file = stg_fp_dict[stg_fname]
        stg_file.write(line.make_shared_pylons_stg_entries() + "\n")
        if None is not wayname:
             #incase Prefix is a path (batch processing)
            replacement_prefix = re.sub('[\/]','_', parameters.PREFIX)
            filename = replacement_prefix + wayname + "%05d" % line_index
            stg_file.write(line.make_cables_ac_xml_stg_entries(filename, path, cluster_max_length) + "\n")


def calc_heading_nodes(nodes_array):
    """Calculates the headings of nodes in a line based on medium angle. nodes must have a heading, x and y attribute"""
    current_pylon = nodes_array[0]
    next_pylon = nodes_array[1]
    current_angle = calc_angle_of_line(current_pylon.x, current_pylon.y, next_pylon.x, next_pylon.y)
    current_pylon.heading = current_angle
    for x in range(1, len(nodes_array) - 1):
        prev_angle = current_angle
        current_pylon = nodes_array[x]
        next_pylon = nodes_array[x + 1]
        current_angle = calc_angle_of_line(current_pylon.x, current_pylon.y, next_pylon.x, next_pylon.y)
        current_pylon.heading = calc_middle_angle(prev_angle, current_angle)
    nodes_array[-1].heading = current_angle


def calc_angle_of_line(x1, y1, x2, y2):
    """Returns the angle in degrees of a line relative to North"""
    angle = math.atan2(x2 - x1, y2 - y1)
    degree = math.degrees(angle)
    if degree < 0:
        degree += 360
    return degree


def calc_middle_angle(angle_line1, angle_line2):
    """Returns the angle halfway between two lines"""
    if angle_line1 == angle_line2:
        middle = angle_line1
    elif angle_line1 > angle_line2:
        if 0 == angle_line2:
            middle = calc_middle_angle(angle_line1, 360)
        else:
            middle = angle_line1 - (angle_line1 - angle_line2) / 2
    else:
        if math.fabs(angle_line2 - angle_line1) > 180:
            middle = calc_middle_angle(angle_line1 + 360, angle_line2)
        else:
            middle = angle_line2 - (angle_line2 - angle_line1) / 2
    if 360 <= middle:
        middle -= 360
    return middle


def stg_angle(angle_normal):
    """Returns the input angle in degrees to an angle for the stg-file in degrees.
    stg-files use angles counter-clockwise starting with 0 in North."""
    if 0 == angle_normal:
        return 0
    else:
        return 360 - angle_normal


def calc_distance(x1, y1, x2, y2):
    return math.sqrt(math.pow(x1 - x2, 2) + math.pow(y1 - y2, 2))


def optimize_catenary(half_distance_pylons, max_value, sag, max_variation):
    """
    Calculates the parameter _a_ for a catenary with a given sag between the pylons and a mx_variation.
    See http://www.mathdemos.org/mathdemos/catenary/catenary.html and https://en.wikipedia.org/wiki/Catenary
    """
    for a in xrange(1, max_value):
        value = a * math.cosh(float(half_distance_pylons)/a) - a  # float() needed to make sure result is float
        if (value >= (sag - max_variation)) and (value <= (sag + max_variation)):
            return a, value
    return -1, -1


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="osm2pylon reads OSM data and creates pylons, powerlines and aerialways for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)

    # Initializing tools for global/local coordinate transformations
    center_global = parameters.get_OSM_file_name()
    osm_fname = parameters.get_OSM_file_name()
    coord_transformator = coordinates.Transformation(center_global, hdg=0)
    tools.init(coord_transformator)

    # Reading elevation data
    logging.info("Reading ground elevation data might take some time ...")
    elev_interpolator = tools.get_interpolator()

    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")
    # the lists below are in sequence: buildings references, power/aerialway, railway overhead, landuse and highway
    valid_node_keys = ["power", "structure", "material", "height", "colour", "aerialway"
                       , "railway"
    ]
    valid_way_keys = ["building"
                      , "power", "aerialway", "voltage", "cables", "wires"
                      , "railway", "electrified", "tunnel"
                      , "landuse"
                      , "highway", "junction"
    ]
    valid_relation_keys = []
    req_relation_keys = []
    req_way_keys = ["building", "power", "aerialway", "railway", "landuse", "highway"]
    handler = osmparser_wrapper.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                                  req_relation_keys)
    source = open(osm_fname)
    xml.sax.parse(source, handler)
    # References for buildings
    building_refs = {}
    if parameters.C2P_PROCESS_POWERLINES or parameters.C2P_PROCESS_AERIALWAYS or parameters.C2P_PROCESS_STREETLAMPS:
        building_refs = process_osm_building_refs(handler.nodes_dict, handler.ways_dict, coord_transformator)
        logging.info('Number of reference buildings: %s', len(building_refs))
    # Power lines and aerialways
    powerlines = {}
    aerialways = {}
    if parameters.C2P_PROCESS_POWERLINES or parameters.C2P_PROCESS_AERIALWAYS:
        powerlines, aerialways = process_osm_power_aerialway(handler.nodes_dict, handler.ways_dict, elev_interpolator
                                                             , coord_transformator, building_refs)
        if not parameters.C2P_PROCESS_POWERLINES:
            powerlines.clear()
        if not parameters.C2P_PROCESS_AERIALWAYS:
            aerialways.clear()
        logging.info('Number of power lines to process: %s', len(powerlines))
        logging.info('Number of aerialways to process: %s', len(aerialways))
        for wayline in powerlines.values():
            wayline.calc_and_map()
        for wayline in aerialways.values():
            wayline.calc_and_map()
    # railway overhead lines
    rail_lines = {}
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        rail_lines = process_osm_rail_overhead(handler.nodes_dict, handler.ways_dict, elev_interpolator
                                               , coord_transformator)
        logging.info('Reduced number of rail lines: %s', len(rail_lines))
        for rail_line in rail_lines.values():
            rail_line.calc_and_map(elev_interpolator, coord_transformator, rail_lines.values())
    # street lamps
    highways = {}
    if parameters.C2P_PROCESS_STREETLAMPS:
        landuse_refs = process_osm_landuse_refs(handler.nodes_dict, handler.ways_dict, coord_transformator, building_refs)
        logging.info('Number of landuse references: %s', len(landuse_refs))
        highways = process_osm_highway(handler.nodes_dict, handler.ways_dict, coord_transformator, landuse_refs)
        logging.info('Reduced number of highways: %s', len(highways))
        for highway in highways.values():
            highway.calc_and_map(elev_interpolator, coord_transformator)
        landuse_refs = None

    # free some memory
    building_refs = None
    handler = None

    # Write to Flightgear
    stg_file_pointers = {}  # -- dictionary of stg file pointers
    if parameters.C2P_PROCESS_POWERLINES:
        write_stg_entries(stg_file_pointers, powerlines, "powerline", parameters.C2P_CLUSTER_POWER_LINE_MAX_LENGTH)
    if parameters.C2P_PROCESS_AERIALWAYS:
        write_stg_entries(stg_file_pointers, aerialways, "aerialway", parameters.C2P_CLUSTER_AERIALWAY_MAX_LENGTH)
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        write_stg_entries(stg_file_pointers, rail_lines, "overhead", parameters.C2P_CLUSTER_OVERHEAD_LINE_MAX_LENGTH)
    if parameters.C2P_PROCESS_STREETLAMPS:
        write_stg_entries(stg_file_pointers, highways, None, None)

    for stg in stg_file_pointers.values():
        stg.write(stg_io.delimiter_string(OUR_MAGIC, False) + "\n")
        stg.close()

    logging.info("******* Finished *******")
    elev_interpolator.save_cache()


# ================ UNITTESTS =======================


class TestOSMPylons(unittest.TestCase):
    def test_angle_of_line(self):
        self.assertEqual(0, calc_angle_of_line(0, 0, 0, 1), "North")
        self.assertEqual(90, calc_angle_of_line(0, 0, 1, 0), "East")
        self.assertEqual(180, calc_angle_of_line(0, 1, 0, 0), "South")
        self.assertEqual(270, calc_angle_of_line(1, 0, 0, 0), "West")
        self.assertEqual(45, calc_angle_of_line(0, 0, 1, 1), "North East")
        self.assertEqual(315, calc_angle_of_line(1, 0, 0, 1), "North West")
        self.assertEqual(225, calc_angle_of_line(1, 1, 0, 0), "South West")

    def test_middle_angle(self):
        self.assertEqual(0, calc_middle_angle(0, 0), "North North")
        self.assertEqual(45, calc_middle_angle(0, 90), "North East")
        self.assertEqual(130, calc_middle_angle(90, 170), "East Almost_South")
        self.assertEqual(90, calc_middle_angle(135, 45), "South_East North_East")
        self.assertEqual(0, calc_middle_angle(45, 315), "South_East North_East")
        self.assertEqual(260, calc_middle_angle(170, 350), "Almost_South Almost_North")

    def test_distance(self):
        self.assertEqual(5, calc_distance(0, -1, -4, 2))

    def test_wayline_calculate_and_map(self):
        # first test headings
        pylon1 = Pylon(1)
        pylon1.x = -100
        pylon1.y = -100
        pylon2 = Pylon(2)
        pylon2.x = 100
        pylon2.y = 100
        wayline1 = WayLine(100)
        wayline1.type_ = WayLine.TYPE_POWER_LINE
        wayline1.shared_pylons.append(pylon1)
        wayline1.shared_pylons.append(pylon2)
        wayline1.calc_and_map()
        self.assertAlmostEqual(45, pylon1.heading, 2)
        self.assertAlmostEqual(45, pylon2.heading, 2)
        pylon3 = Pylon(3)
        pylon3.x = 0
        pylon3.y = 100
        pylon4 = Pylon(4)
        pylon4.x = -100
        pylon4.y = 200
        wayline1.shared_pylons.append(pylon3)
        wayline1.shared_pylons.append(pylon4)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon2.heading, 2)
        self.assertAlmostEqual(292.5, pylon3.heading, 2)
        self.assertAlmostEqual(315, pylon4.heading, 2)
        pylon5 = Pylon(5)
        pylon5.x = -100
        pylon5.y = 300
        wayline1.shared_pylons.append(pylon5)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon4.heading, 2)
        self.assertAlmostEqual(0, pylon5.heading, 2)
        # then test other stuff
        self.assertEqual(4, len(wayline1.way_segments))
        wayline1.make_cables_ac_xml_stg_entries("foo", "foo", parameters.C2P_CLUSTER_POWER_LINE_MAX_LENGTH)

    def test_cable_vertex_calc_position(self):
        vertex = CableVertex(10, 5)
        vertex.calc_position(0, 0, 20, 0)
        self.assertAlmostEqual(25, vertex.elevation, 2)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(0, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 90)
        self.assertAlmostEqual(0, vertex.x, 2)
        self.assertAlmostEqual(-10, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 210)
        self.assertAlmostEqual(-8.660, vertex.x, 2)
        self.assertAlmostEqual(5, vertex.y, 2)
        vertex.calc_position(20, 50, 20, 180)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(50, vertex.y, 2)

    def test_catenary(self):
        #  Values taken form example 2 in http://www.mathdemos.org/mathdemos/catenary/catenary.html
        a, value = optimize_catenary(170, 5000, 14, 0.01)
        print a, value
        self.assertAlmostEqual(1034/100, a/100, 2)

    def test_merge_lines(self):
        line_u = RailLine("u")
        line_v = RailLine("v")
        line_w = RailLine("w")
        line_x = RailLine("x")
        line_y = RailLine("y")
        node1 = RailNode("1")
        node2 = RailNode("2")
        node3 = RailNode("3")
        node4 = RailNode("4")
        node5 = RailNode("5")
        node6 = RailNode("6")
        node7 = RailNode("7")
        shared_nodes = {}

        line_u.nodes.append(node1)
        line_u.nodes.append(node2)
        line_v.nodes.append(node2)
        line_v.nodes.append(node3)
        merge_lines("2", line_u, line_v, shared_nodes)
        self.assertEqual(3, len(line_u.nodes))
        line_w.nodes.append(node1)
        line_w.nodes.append(node4)
        merge_lines("1", line_u, line_w, shared_nodes)
        self.assertEqual(4, len(line_u.nodes))
        line_x.nodes.append(node5)
        line_x.nodes.append(node3)
        merge_lines("3", line_u, line_x, shared_nodes)
        self.assertEqual(5, len(line_u.nodes))
        line_y.nodes.append(node7)
        line_y.nodes.append(node6)
        line_y.nodes.append(node4)
        merge_lines("4", line_u, line_y, shared_nodes)
        self.assertEqual(7, len(line_u.nodes))

    def find_connecting_line(self):
        node1 = RailNode("1")
        node1.x = 5
        node1.y = 10
        node2 = RailNode("2")
        node2.x = 10
        node2.y = 10
        node3 = RailNode("3")
        node3.x = 20
        node3.y = 5
        node4 = RailNode("4")
        node4.x = 20
        node4.y = 20

        line_u = RailLine("u")
        line_u.nodes.append(node1)
        line_u.nodes.append(node2)
        line_v = RailLine("v")
        line_v.nodes.append(node2)
        line_v.nodes.append(node3)
        line_w = RailLine("w")
        line_w.nodes.append(node4)
        line_w.nodes.append(node2)

        lines = [line_u, line_v, line_w]
        pos1, pos2 = find_connecting_line("2", lines)
        self.assertEqual(0, pos1)
        self.assertEqual(1, pos2)
