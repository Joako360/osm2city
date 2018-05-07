# -*- coding: utf-8 -*-
"""Handles land-use related stuff, especially generating new land-use where OSM data is not sufficient.
"""

import logging
import math
import pickle
import time
from typing import Dict, List, Tuple

from shapely.geometry import MultiPolygon, Polygon, CAP_STYLE, JOIN_STYLE
from shapely.ops import unary_union

import parameters
import owbb.models as m
import owbb.plotting as plotting
import utils.osmparser as op
from utils.coordinates import disjoint_bounds, Transformation
from utils.utilities import time_logging


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


def _test_highway_intersecting_area(area: Polygon, highways_dict: Dict[int, m.Highway]) -> List[m.Highway]:
    """Returns highways that are within an area or intersecting with an area.

    Highways_dict gets reduced by those highways, which were within, such that searching in other
    areas gets quicker due to reduced volume.
    """
    linked_highways = list()
    to_be_removed = list()
    for my_highway in highways_dict.values():
        if not my_highway.populate_buildings_along():
            continue
        if not disjoint_bounds(my_highway.geometry.bounds, area.bounds):  # a bit speed up
            if my_highway.geometry.within(area):
                linked_highways.append(my_highway)
                to_be_removed.append(my_highway.osm_id)

            elif my_highway.geometry.intersects(area):
                linked_highways.append(my_highway)

    for key in to_be_removed:
        del highways_dict[key]

    return linked_highways


def _assign_city_blocks(building_zone: m.BuildingZone, highways_dict: Dict[int, m.Highway]) -> None:
    """Splits the land-use into (city) blocks, i.e. areas surrounded by streets.
    Brute force by buffering all highways, then take the geometry difference, which splits the zone into
    multiple polygons. Some of the polygons will be real city blocks, others will be border areas.

    Could also be done by using e.g. networkx.algorithms.cycles.cycle_basis.html. However is a bit more complicated
    logic and programming wise, but might be faster.
    """
    highways_dict_copy1 = highways_dict.copy()  # otherwise when using highways_dict in plotting it will be "used"

    polygons = list()
    intersecting_highways = _test_highway_intersecting_area(building_zone.geometry, highways_dict_copy1)
    if intersecting_highways:
        buffers = list()
        for highway in intersecting_highways:
            buffers.append(highway.geometry.buffer(2, cap_style=CAP_STYLE.square,
                                                   join_style=JOIN_STYLE.bevel))
        geometry_difference = building_zone.geometry.difference(unary_union(buffers))
        if isinstance(geometry_difference, Polygon) and geometry_difference.is_valid and \
                geometry_difference.area >= parameters.OWBB_MIN_CITY_BLOCK_AREA:
            polygons.append(geometry_difference)
        elif isinstance(geometry_difference, MultiPolygon):
            my_polygons = geometry_difference.geoms
            for my_poly in my_polygons:
                if isinstance(my_poly, Polygon) and my_poly.is_valid and \
                        my_poly.area >= parameters.OWBB_MIN_CITY_BLOCK_AREA:
                    polygons.append(my_poly)

    logging.debug('Found %i city blocks in building zone osm_ID=%i', len(polygons), building_zone.osm_id)

    for polygon in polygons:
        my_city_block = m.CityBlock(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse), polygon,
                                    building_zone.type_)
        building_zone.add_city_block(my_city_block)

    # now assign the osm_buildings to the city blocks
    building_zone.reassign_osm_buildings_to_city_blocks()


def _process_landuse_for_lighting(building_zones: List[m.BuildingZone]) -> List[Polygon]:
    """Uses BUILT_UP_AREA_LIT_BUFFER to produce polygons for lighting of streets."""
    buffered_polygons = list()
    for zone in building_zones:
        buffered_polygons.append(zone.geometry.buffer(parameters.OWBB_BUILT_UP_BUFFER))

    merged_polygons = _merge_buffers(buffered_polygons)

    lit_areas = list()
    # check for minimal area of inner holes and create final list of polygons
    for zone in merged_polygons:
        if zone.interiors:
            inner_rings = list()
            total_inner = 0
            survived_inner = 0
            for ring in zone.interiors:
                total_inner += 1
                my_polygon = Polygon(ring)
                if my_polygon.area > parameters.OWBB_BUILT_UP_AREA_HOLES_MIN_AREA:
                    survived_inner += 1
                    inner_rings.append(ring)
            corrected_poly = Polygon(zone.exterior, inner_rings)
            lit_areas.append(corrected_poly)
            logging.debug('Removed %i holes from lit area. Number of holes left: %i', total_inner - survived_inner,
                          survived_inner)
        else:
            lit_areas.append(zone)

    return lit_areas


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
    if isinstance(multi_polygon, Polygon):
        return [multi_polygon]

    handled_list = list()
    for polygon in multi_polygon.geoms:
        if isinstance(polygon, Polygon):
            handled_list.append(polygon)
        else:
            logging.debug("Unary union of transport buffers resulted in an object of type %s instead of Polygon",
                          type(polygon))
    return handled_list


def _create_settlement_clusters(lit_areas: List[Polygon], urban_places: List[m.Place]) -> List[m.SettlementCluster]:
    clusters = list()
    for polygon in lit_areas:
        candidate_places = list()
        towns = 0
        cities = 0
        for place in urban_places:
            if place.geometry.within(polygon):
                candidate_places.append(place)
                if place.type_ is m.PlaceType.city:
                    cities += 1
                else:
                    towns += 1
        if candidate_places:
            logging.debug('New settlement cluster with %i cities and %i towns', cities, towns)
            clusters.append(m.SettlementCluster(candidate_places, polygon))
    return clusters


def _link_building_zones_with_settlements(settlement_clusters: List[m.SettlementCluster],
                                          building_zones: List[m.BuildingZone],
                                          highways_dict: Dict[int, m.Highway]) -> None:
    for settlement in settlement_clusters:
        # create the settlement type circles
        centre_circles = list()
        block_circles = list()
        dense_circles = list()
        for place in settlement.linked_places:
            centre_circle, block_circle, dense_circle = place.create_settlement_type_circles()
            if not centre_circle.is_empty:
                centre_circles.append(centre_circle)
            block_circles.append(block_circle)
            dense_circles.append(dense_circle)
        for zone in building_zones:
            # within because lit-areas are always
            if zone.geometry.within(settlement.geometry):
                # create city blocks
                _assign_city_blocks(zone, highways_dict)
                # Test for being within a settlement type circle beginning with the highest ranking circles.
                # If yes, then assign settlement type to city block
                for city_block in zone.linked_city_blocks:
                    intersecting = False
                    for circle in centre_circles:
                        if not city_block.geometry.disjoint(circle):
                            intersecting = True
                            city_block.settlement_type = m.SettlementType.centre
                            break
                    if not intersecting:
                        for circle in block_circles:
                            if not city_block.geometry.disjoint(circle):
                                intersecting = True
                                city_block.settlement_type = m.SettlementType.block
                                break
                    if not intersecting:
                        for circle in dense_circles:
                            if not city_block.geometry.disjoint(circle):
                                city_block.settlement_type = m.SettlementType.dense
                                break


def process(transformer: Transformation) -> Tuple[List[Polygon], List[m.BuildingZone]]:
    last_time = time.time()

    # =========== TRY TO READ CACHED DATA FIRST =======
    tile_index = parameters.get_tile_index()
    cache_file_la = str(tile_index) + '_lit_areas.pkl'
    cache_file_bz = str(tile_index) + '_building_zones.pkl'
    if parameters.OWBB_LANDUSE_CACHE:
        try:
            with open(cache_file_la, 'rb') as file_pickle:
                lit_areas = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(lit_areas), cache_file_la)

            with open(cache_file_bz, 'rb') as file_pickle:
                building_zones = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(building_zones), cache_file_bz)
            return lit_areas, building_zones
        except (IOError, EOFError) as reason:
            logging.info("Loading of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    # =========== READ OSM DATA =============
    building_zones = m.process_osm_building_zone_refs(transformer)
    urban_places, farm_places = m.process_osm_place_refs(transformer)
    osm_buildings = m.process_osm_building_refs(transformer)
    highways_dict, nodes_dict = m.process_osm_highway_refs(transformer)
    railways_dict = m.process_osm_railway_refs(transformer)
    waterways_dict = m.process_osm_waterway_refs(transformer)

    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    # =========== GENERATE ADDITIONAL LAND-USE ZONES FOR AND/OR FROM BUILDINGS =============
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

    # =========== CREATE POLYGONS FOR LIGHTING OF STREETS ================================
    # Needs to be before finding city blocks as we need the boundary
    lit_areas = _process_landuse_for_lighting(building_zones)
    last_time = time_logging("Time used in seconds for finding lit areas", last_time)

    # =========== MAKE SURE GENERATED LAND-USE DOES NOT CROSS MAJOR LINEAR OBJECTS =======
    if parameters.OWBB_SPLIT_MADE_UP_LANDUSE_BY_MAJOR_LINES:
        # finally split generated zones by major transport lines
        building_zones = _split_generated_building_zones_by_major_lines(building_zones, highways_dict,
                                                                        railways_dict, waterways_dict)
    last_time = time_logging("Time used in seconds for splitting building zones by major lines", last_time)

    # =========== Link urban places with lit_area buffers ==================================
    if parameters.FLAG_2018_2:
        settlement_clusters = _create_settlement_clusters(lit_areas, urban_places)
        last_time = time_logging('Time used in seconds for creating settlement_clusters', last_time)

        _link_building_zones_with_settlements(settlement_clusters, building_zones, highways_dict)
        last_time = time_logging('Time used in seconds for linking building zones with settlement_clusters', last_time)

    # ============finally guess the land-use type ========================================
    for my_zone in building_zones:
        if isinstance(my_zone, m.GeneratedBuildingZone):
            my_zone.guess_building_zone_type(farm_places)
    last_time = time_logging("Time used in seconds for guessing zone types", last_time)

    # =========== FINALIZE PROCESSING ====================================================
    if parameters.DEBUG_PLOT:
        bounds = m.Bounds.create_from_parameters(transformer)
        plotting.draw_zones(osm_buildings, building_zones, lit_areas, bounds)
        time_logging("Time used in seconds for plotting", last_time)

    # =========== WRITE TO CACHE AND RETURN
    if parameters.OWBB_LANDUSE_CACHE:
        try:

            with open(cache_file_la, 'wb') as file_pickle:
                pickle.dump(lit_areas, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(lit_areas), cache_file_la)

            with open(cache_file_bz, 'wb') as file_pickle:
                pickle.dump(building_zones, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(building_zones), cache_file_bz)
        except (IOError, EOFError) as reason:
            logging.info("Saving of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    return lit_areas, building_zones
