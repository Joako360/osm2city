# -*- coding: utf-8 -*-
"""Handles land-use related stuff, especially generating new land-use where OSM data is not sufficient.
"""

import logging
import math
import time
from typing import Dict, List, Tuple

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

import parameters
import owbb.models as m
import owbb.plotting as plotting
import utils.osmparser as op
import utils.btg_io as btg
from utils.coordinates import Transformation
from utils.utilities import time_logging


def _generate_building_zones_from_external(building_zones: List[m.BuildingZone],
                                           external_landuses: List[m.BTGBuildingZone]) -> None:
    """Adds "missing" building_zones based on land-use info outside of OSM land-use"""
    counter = 0
    for external_landuse in external_landuses:
        my_geoms = list()
        my_geoms.append(external_landuse.geometry)

        for building_zone in building_zones:
            parts = list()
            for geom in my_geoms:
                if geom.within(building_zone.geometry) \
                        or geom.touches(building_zone.geometry):
                    continue
                elif geom.intersects(building_zone.geometry):
                    diff = geom.difference(building_zone.geometry)
                    if isinstance(diff, Polygon):
                        if diff.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
                            parts.append(diff)
                    elif isinstance(diff, MultiPolygon):
                        for poly in diff:
                            if poly.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
                                parts.append(poly)
                else:
                    if geom.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
                        parts.append(geom)
            my_geoms = parts

        for geom in my_geoms:
            generated = m.GeneratedBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                geom, external_landuse.type_)
            building_zones.append(generated)
            counter += 1
    logging.debug("Generated building zones from external land-use: %d", counter)


def _generate_building_zones_from_buildings(building_zones: List[m.BuildingZone],
                                            buildings_outside: List[m.Building]) -> None:
    """Adds "missing" building_zones based on building clusters outside of OSM land-use.
    The calculated values are implicitly updated in the referenced parameter building_zones"""
    zones_candidates = dict()
    for my_building in buildings_outside:
        buffer_distance = parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE
        if my_building.geometry.area > parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
            factor = math.sqrt(my_building.geometry.area / parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
            buffer_distance = min(factor*parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE,
                                  parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
        buffer_polygon = my_building.geometry.buffer(buffer_distance)
        within_existing_building_zone = False
        for candidate in zones_candidates.values():
            if buffer_polygon.intersects(candidate.geometry):
                candidate.geometry = candidate.geometry.union(buffer_polygon)
                candidate.osm_buildings.append(my_building)
                within_existing_building_zone = True
                break
        if not within_existing_building_zone:
            my_candidate = m.GeneratedBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                   buffer_polygon, m.BuildingZoneType.non_osm,
                                                   True)
            my_candidate.osm_buildings.append(my_building)
            zones_candidates[my_candidate.osm_id] = my_candidate
    logging.debug("Candidate land-uses found: %s", len(zones_candidates))
    # Search once again for intersections in order to account for randomness in checks
    merged_candidate_ids = list()
    keys = list(zones_candidates.keys())
    for i in range(0, len(zones_candidates)-2):
        for j in range(i+1, len(zones_candidates)-1):
            if zones_candidates[keys[i]].geometry.intersects(zones_candidates[keys[j]].geometry):
                merged_candidate_ids.append(keys[i])
                zones_candidates[keys[j]].geometry = zones_candidates[keys[j]].geometry.union(
                    zones_candidates[keys[i]].geometry)
                zones_candidates[keys[j]].osm_buildings.extend(zones_candidates[keys[i]].osm_buildings)
                break
    logging.debug("Candidate land-uses merged into others: %d", len(merged_candidate_ids))
    # check for minimum size and then simplify geometry
    kept_candidates = list()
    for candidate in zones_candidates.values():
        if candidate.osm_id in merged_candidate_ids:
            continue
        if candidate.geometry.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
            candidate.geometry = candidate.geometry.simplify(parameters.OWBB_GENERATE_LANDUSE_SIMPLIFICATION_TOLERANCE)
            # remove interior holes, which are too small
            if len(candidate.geometry.interiors) > 0:
                new_interiors = list()
                for interior in candidate.geometry.interiors:
                    interior_polygon = Polygon(interior)
                    logging.debug("Hole area: %f", interior_polygon.area)
                    if interior_polygon.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_HOLES_MIN_AREA:
                        new_interiors.append(interior)
                logging.debug("Number of holes reduced: from %d to %d",
                              len(candidate.geometry.interiors), len(new_interiors))
                replacement_polygon = Polygon(shell=candidate.geometry.exterior, holes=new_interiors)
                candidate.geometry = replacement_polygon
            kept_candidates.append(candidate)
    logging.debug("Candidate land-uses with sufficient area found: %d", len(kept_candidates))

    # make sure that new generated buildings zones do not intersect with other building zones
    for generated in kept_candidates:
        for building_zone in building_zones:  # can be from OSM or external
            if generated.geometry.intersects(building_zone.geometry):
                generated.geometry = generated.geometry.difference(building_zone.geometry)

    # now make sure that there are no MultiPolygons
    logging.debug("Candidate land-uses before multi-polygon split: %d", len(kept_candidates))
    polygon_candidates = list()
    for zone in kept_candidates:
        if isinstance(zone.geometry, MultiPolygon):
            polygon_candidates.extend(_split_multipolygon_generated_building_zone(zone))
        else:
            polygon_candidates.append(zone)
    logging.debug("Candidate land-uses after multi-polygon split: %d", len(polygon_candidates))

    building_zones.extend(polygon_candidates)


def _split_multipolygon_generated_building_zone(zone: m.GeneratedBuildingZone) -> List[m.GeneratedBuildingZone]:
    """Checks whether a generated building zone's geometry is Multipolygon. If yes, then split into polygons.
    Algorithm distributes buildings and checks that minimal size and buildings are respected."""
    split_zones = list()
    if isinstance(zone.geometry, MultiPolygon):  # just to be sure if methods would be called by mistake on polygon
        new_generated = list()
        logging.debug("Handling a generated land-use Multipolygon with %d polygons", len(zone.geometry.geoms))
        for split_polygon in zone.geometry.geoms:
            my_split_generated = m.GeneratedBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                         split_polygon,
                                                         zone.type_, zone.from_buildings)
            new_generated.append(my_split_generated)
        while len(zone.osm_buildings) > 0:
            my_building = zone.osm_buildings.pop()
            for my_split_generated in new_generated:
                if my_building.geometry.intersects(my_split_generated.geometry):
                    my_split_generated.osm_buildings.append(my_building)
                    continue
        for my_split_generated in new_generated:
            if my_split_generated.from_buildings and len(my_split_generated.osm_buildings) == 0:
                continue
            if my_split_generated.geometry.area < parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA/2:
                continue
            split_zones.append(my_split_generated)
            logging.debug("Added sub-polygon with area %d and %d buildings", my_split_generated.geometry.area,
                          len(my_split_generated.osm_buildings))
    else:
        split_zones.append(zone)
    return split_zones


def _split_generated_building_zones_by_major_lines(before_list: List[m.BuildingZone],
                                                   highways: Dict[int, m.Highway],
                                                   railways: Dict[int, m.RailwayLine],
                                                   waterways: Dict[int, m.Waterway]) -> List[m.BuildingZone]:
    """Splits generated building zones into several sub-zones along major transport lines and waterways.
    Major transport lines are motorways, trunks as well as certain railway lines.
    Using buffers (= polygons) instead of lines because Shapely cannot do it natively.
    Using buffers directly instead of trying to entangle line strings of highways/railways due to
    easiness plus performance wise most probably same or better."""

    # create buffers around major transport
    line_buffers = list()
    for highway in highways.values():
        if highway.type_ in [m.HighwayType.motorway, m.HighwayType.trunk] and not highway.is_tunnel:
            line_buffers.append(highway.geometry.buffer(highway.get_width()/2))

    for railway in railways.values():
        if railway.type_ in [m.RailwayLineType.rail, m.RailwayLineType.light_rail, m.RailwayLineType.subway,
                             m.RailwayLineType.narrow_gauge] and not (railway.is_tunnel or railway.is_service_spur):
            line_buffers.append(railway.geometry.buffer(railway.get_width() / 2))

    for waterway in waterways.values():
        if waterway.type_ is m.WaterwayType.large:
            line_buffers.append(waterway.geometry.buffer(10))

    merged_buffers = _merge_buffers(line_buffers)
    if len(merged_buffers) == 0:
        return before_list

    # walk through all buffers and where intersecting get the difference with zone geometry as new zone polygon(s).
    unhandled_list = before_list[:]
    after_list = None
    for buffer in merged_buffers:
        after_list = list()
        while len(unhandled_list) > 0:
            zone = unhandled_list.pop()
            if isinstance(zone, m.GeneratedBuildingZone) and zone.geometry.intersects(buffer):
                zone.geometry = zone.geometry.difference(buffer)
                if isinstance(zone.geometry, MultiPolygon):
                    after_list.extend(_split_multipolygon_generated_building_zone(zone))
                    # it could be that the returned list is empty because all parts are below size criteria for
                    # generated zones, which is ok
                else:
                    after_list.append(zone)
            else:  # just keep as is if not GeneratedBuildingZone or not intersecting
                after_list.append(zone)
        unhandled_list = after_list

    return after_list


def _merge_buffers(original_list: List[Polygon]) -> List[Polygon]:
    """Attempts to merge as many polygon buffers with each other as possible to return a reduced list."""
    multi_polygon = unary_union(original_list)
    handled_list = list()
    for polygon in multi_polygon.geoms:
        if isinstance(polygon, Polygon):
            handled_list.append(polygon)
        else:
            logging.debug("Unary union of transport buffers resulted in an object of type %s instead of Polygon",
                          type(polygon))
    return handled_list


def _process_osm_building_zone_refs(my_coord_transformator: Transformation) -> List[m.BuildingZone]:
    osm_result = op.fetch_osm_db_data_ways_keys([m.LANDUSE_KEY])
    my_ways = list()
    for way in list(osm_result.ways_dict.values()):
        my_way = m.BuildingZone.create_from_way(way, osm_result.nodes_dict, my_coord_transformator)
        if my_way.is_valid():
            my_ways.append(my_way)
    logging.info("OSM land-uses found: %s", len(my_ways))
    return my_ways


def _process_osm_building_refs(my_coord_transformator: Transformation) -> List[m.Building]:
    osm_result = op.fetch_osm_db_data_ways_keys([m.BUILDING_KEY])
    my_ways = list()
    for way in list(osm_result.ways_dict.values()):
        my_way = m.Building.create_from_way(way, osm_result.nodes_dict, my_coord_transformator)
        if my_way.is_valid():
            my_ways.append(my_way)
    logging.info("OSM buildings found: %s", len(my_ways))
    return my_ways


def _process_osm_railway_refs(my_coord_transformator: Transformation) -> Dict[int, m.RailwayLine]:
    # TODO: it must be possible to do this for highways and waterways abstract, as only logging, object
    # and key is different
    osm_result = op.fetch_osm_db_data_ways_keys([m.RAILWAY_KEY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = m.RailwayLine.create_from_way(way, osm_result.nodes_dict, my_coord_transformator)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = way
    logging.info("OSM railway lines found: %s", len(my_ways))
    return my_ways


def _process_osm_highway_refs(my_coord_transformator: Transformation) -> Dict[int, m.Highway]:
    osm_result = op.fetch_osm_db_data_ways_keys([m.HIGHWAY_KEY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_hway = m.Highway.create_from_way(way, osm_result.nodes_dict, my_coord_transformator)
        if my_hway.is_valid():
            my_ways[my_hway.osm_id] = my_hway
    logging.info("OSM highways found: %s", len(my_ways))
    return my_ways


def _process_osm_waterway_refs(my_coord_transformator: Transformation) -> Dict[int, m.Waterway]:
    osm_result = op.fetch_osm_db_data_ways_keys([m.WATERWAY_KEY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = m.Waterway.create_from_way(way, osm_result.nodes_dict, my_coord_transformator)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM waterways found: %s", len(my_ways))
    return my_ways


def _process_osm_place_refs(my_coord_transformator: Transformation) -> List[m.Place]:
    my_places = list()
    # points
    osm_nodes_dict = op.fetch_db_nodes_isolated([m.PLACE_KEY], list())
    for key, node in osm_nodes_dict.items():
        place = m.Place.create_from_node(node, my_coord_transformator)
        if place.is_valid():
            my_places.append(place)
    # areas
    osm_way_result = op.fetch_osm_db_data_ways_keys([m.PLACE_KEY])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict
    for key, way in osm_ways_dict.items():
        place = m.Place.create_from_way(way, osm_nodes_dict, my_coord_transformator)
        if place.is_valid():
            my_places.append(place)
    logging.info("Number of valid places found: {}".format(len(my_places)))

    return my_places


def _process_btg_building_zones(my_coord_transformator: Transformation) -> Tuple[List[m.BTGBuildingZone],
                                                                                 List[m.BTGBuildingZone]]:
    btg_reader = btg.BTGReader('/home/vanosten/bin/terrasync/Terrain/e000n40/e008n47/3088962.btg.gz')
    btg_zones = list()
    vertices = btg_reader.vertices
    for key, faces_list in btg_reader.faces.items():
        if key != btg.WATER_PROXY:
            # find the corresponding BuildingZoneType
            type_ = None
            for member in m.BuildingZoneType:
                btg_key = 'btg_' + key
                if btg_key == member.name:
                    type_ = member
                    break
            if type_ is None:
                raise Exception('Unknown BTG material: {}. Most probably a programming mismatch.'.format(key))
            # create building zones
            for face in faces_list:
                v0 = vertices[face.vertices[0]]
                v1 = vertices[face.vertices[1]]
                v2 = vertices[face.vertices[2]]
                my_geometry = Polygon([my_coord_transformator.toLocal((v0.x, v0.y)),
                                       my_coord_transformator.toLocal((v1.x, v1.y)),
                                       my_coord_transformator.toLocal((v2.x, v2.y))])
                if not my_geometry.is_valid:  # it might be self-touching or self-crossing polygons
                    clean = my_geometry.buffer(0)  # cf. http://toblerity.org/shapely/manual.html#constructive-methods
                    if clean.is_valid:
                        my_geometry = clean  # it is now a Polygon or a MultiPolygon
                if my_geometry.is_valid:
                    my_zone = m.BTGBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                type_, my_geometry)
                    btg_zones.append(my_zone)
    return btg_zones, btg_reader.faces[btg.WATER_PROXY]


def process(coords_transform: Transformation) -> None:
    last_time = time.time()

    # =========== READ OSM DATA =============
    building_zones = _process_osm_building_zone_refs(coords_transform)
    places = _process_osm_place_refs(coords_transform)
    osm_buildings = _process_osm_building_refs(coords_transform)
    highways_dict = _process_osm_highway_refs(coords_transform)
    railways_dict = _process_osm_railway_refs(coords_transform)
    waterways_dict = _process_osm_waterway_refs(coords_transform)

    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    # =========== READ LAND-USE DATA FROM FLIGHTGEAR BTG-FILES =============
    btg_building_zones = list()
    if parameters.OWBB_USE_BTG_LANDUSE:
        btg_building_zones, btg_water = _process_btg_building_zones(coords_transform)
        last_time = time_logging("Time used in seconds for reading BTG zones", last_time)

    # =========== GENERATE ADDITIONAL LAND-USE ZONES FOR AND/OR FROM BUILDINGS =============
    if len(btg_building_zones) > 0:
        pass
        # FIXME _generate_building_zones_from_external(building_zones, btg_building_zones)
    last_time = time_logging("Time used in seconds for processing external zones", last_time)

    buildings_outside = list()  # buildings outside of OSM buildings zones
    for candidate in osm_buildings:
        found = False
        for building_zone in building_zones:
            if candidate.geometry.within(building_zone.geometry) or candidate.geometry.intersects(
                    building_zone.geometry):
                building_zone.osm_buildings.append(candidate)
                found = True
                break
        if not found:
            buildings_outside.append(candidate)
    last_time = time_logging("Time used in seconds for assigning buildings to OSM zones", last_time)

    if parameters.OWBB_GENERATE_LANDUSE:
        _generate_building_zones_from_buildings(building_zones, buildings_outside)
    del buildings_outside
    last_time = time_logging("Time used in seconds for generating building zones", last_time)

    # =========== MAKE SURE GENERATED LAND-USE DOES NOT CROSS MAJOR LINEAR OBJECTS =======
    if parameters.OWBB_SPLIT_MADE_UP_LANDUSE_BY_MAJOR_LINES:
        # finally split generated zones by major transport lines
        building_zones = _split_generated_building_zones_by_major_lines(building_zones, highways_dict,
                                                                        railways_dict, waterways_dict)

    # ============finally guess the land-use type ========================================
    for my_zone in building_zones:
        if isinstance(my_zone, m.GeneratedBuildingZone):
            my_zone.guess_building_zone_type(places)

    # =========== FINALIZE PROCESSING ====================================================
    if parameters.DEBUG_PLOT:
        bounds = m.Bounds.create_from_parameters(coords_transform)
        plotting.draw_zones(highways_dict, osm_buildings, building_zones, btg_building_zones, bounds)
        time_logging("Time used in seconds for plotting", last_time)
