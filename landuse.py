#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import math

from shapely.geometry import LineString
from shapely.geometry import Polygon

import parameters


def process_osm_building_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_buildings = dict()  # osm_id as key, Polygon
    for way in ways_dict.values():
        for key in way.tags:
            if "building" == key:
                coordinates = list()
                for ref in way.refs:
                    if ref in nodes_dict:
                        my_node = nodes_dict[ref]
                        coordinates.append(my_coord_transformator.toLocal((my_node.lon, my_node.lat)))
                if 2 < len(coordinates):
                    my_polygon = Polygon(coordinates)
                    if my_polygon.is_valid and not my_polygon.is_empty:
                        my_buildings[way.osm_id] = my_polygon.convex_hull
    return my_buildings


class LinearOSMFeature(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.linear = None  # The LinearString of the line

    def get_width(self):
        """The width incl. border as a float in meters"""
        raise NotImplementedError("Please implement this method")


class Highway(LinearOSMFeature):
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
    TYPE_PEDESTRIAN = 21
    TYPE_SLOW = 30  # cycle ways, tracks, footpaths etc

    def __init__(self, osm_id):
        super(Highway, self).__init__(osm_id)
        self.is_roundabout = False

    def get_width(self):  # FIXME: replace with parameters and a bit of logic including number of lanes
        my_width = 3.0  # TYPE_SLOW
        if self.type_ in [Highway.TYPE_SERVICE, Highway.TYPE_RESIDENTIAL, Highway.TYPE_LIVING_STREET
                          , Highway.TYPE_PEDESTRIAN]:
            my_width = 5.0
        elif self.type_ in [Highway.TYPE_ROAD, Highway.TYPE_UNCLASSIFIED, Highway.TYPE_TERTIARY]:
            my_width = 6.0
        elif self.type_ in [Highway.TYPE_SECONDARY, Highway.TYPE_PRIMARY, Highway.TYPE_TRUNK]:
            my_width = 7.0
        else:  # MOTORWAY
            my_width = 14.0
        return my_width


def process_osm_highway(nodes_dict, ways_dict, my_coord_transformator):
    my_highways = dict()  # osm_id as key, Highway

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
                elif value == "pedestrian":
                    my_highway.type_ = Highway.TYPE_PEDESTRIAN
                elif value in ["tack", "footway", "cycleway", "bridleway", "steps", "path"]:
                    my_highway.type_ = Highway.TYPE_SLOW
                else:
                    valid_highway = False
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
            elif ("junction" == key) and ("roundabout" == value):
                my_highway.is_roundabout = True
        if valid_highway and not is_challenged:
            # Process the Nodes
            my_coordinates = list()
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_highway.linear = LineString(my_coordinates)
                my_highways[my_highway.osm_id] = my_highway

    return my_highways


class Landuse(object):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for land-uses constructed with heuristics and not in original data from OSM

    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.polygon = None  # the polygon defining its outer boundary
        self.number_of_buildings = 0  # only set for generated TYPE_NON_OSM land-uses during generation


def process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator):
    my_landuses = dict()  # osm_id as key, Landuse as value

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
            my_coordinates = list()
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
    return my_landuses


def generate_landuse_from_buildings(osm_landuses, building_refs):
    """Adds "missing" landuses based on building clusters"""
    my_landuse_candidates = dict()
    index = 10000000000
    for my_building in building_refs.values():
        # check whether the building already is in a land use
        within_existing_landuse = False
        for osm_landuse in osm_landuses.values():
            if my_building.intersects(osm_landuse.polygon):
                within_existing_landuse = True
                break
        if not within_existing_landuse:
            # create new clusters of land uses
            buffer_distance = parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE
            if my_building.area > parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
                factor = math.sqrt(my_building.area / parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
                buffer_distance = min(factor*parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE
                                      , parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
            buffer_polygon = my_building.buffer(buffer_distance)
            buffer_polygon = buffer_polygon
            within_existing_landuse = False
            for candidate in my_landuse_candidates.values():
                if buffer_polygon.intersects(candidate.polygon):
                    candidate.polygon = candidate.polygon.union(buffer_polygon)
                    candidate.number_of_buildings += 1
                    within_existing_landuse = True
                    break
            if not within_existing_landuse:
                index += 1
                my_candidate = Landuse(index)
                my_candidate.polygon = buffer_polygon
                my_candidate.number_of_buildings = 1
                my_candidate.type_ = Landuse.TYPE_NON_OSM
                my_landuse_candidates[my_candidate.osm_id] = my_candidate
    # add landuse candidates to landuses
    logging.debug("Candidate land-uses found: %s", len(my_landuse_candidates))
    for candidate in my_landuse_candidates.values():
        if candidate.polygon.area < parameters.LU_LANDUSE_MIN_AREA:
            del my_landuse_candidates[candidate.osm_id]
    logging.debug("Candidate land-uses with sufficient area found: %s", len(my_landuse_candidates))

    return my_landuse_candidates


def main():
    pass


if __name__ == "__main__":
    main()
