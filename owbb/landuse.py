# -*- coding: utf-8 -*-
"""Handles land-use related stuff, especially generating new land-use where OSM data is not sufficient.
"""

import logging
import math
import os.path
import time
from typing import List, Tuple

import shapely.affinity as saf
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union

import parameters
import owbb.models as m
import owbb.plotting as plotting
import utils.btg_io as btg
import utils.calc_tile as ct
import utils.osmparser as op
from utils.coordinates import disjoint_bounds, Transformation
from utils.stg_io2 import scenery_directory_name, SceneryType
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


def _process_btg_building_zones(transformer: Transformation) -> Tuple[List[m.BTGBuildingZone],
                                                                      List[m.BTGBuildingZone]]:
    """There is a need to do a local coordinate transformation, as BTG also has a local coordinate
    transformation, but there the center will be in the middle of the tile, whereas here is can be
     another place if the boundary is not a whole tile."""
    lon_lat = parameters.get_center_global()
    path_to_btg = ct.construct_path_to_files(parameters.PATH_TO_SCENERY, scenery_directory_name(SceneryType.terrain),
                                             (lon_lat.lon, lon_lat.lat))
    tile_index = parameters.get_tile_index()
    btg_file_name = os.path.join(path_to_btg, ct.construct_btg_file_name_from_tile_index(tile_index))
    logging.debug('Reading btg file: %s', btg_file_name)
    btg_reader = btg.BTGReader(btg_file_name)
    btg_zones = list()
    vertices = btg_reader.vertices
    v_max_x = 0
    v_max_y = 0
    v_max_z = 0
    v_min_x = 0
    v_min_y = 0
    v_min_z = 0
    for vertex in vertices:
        if vertex.x >= 0:
            v_max_x = max(v_max_x, vertex.x)
        else:
            v_min_x = min(v_min_x, vertex.x)
        if vertex.y >= 0:
            v_max_y = max(v_max_y, vertex.y)
        else:
            v_min_y = min(v_min_y, vertex.y)
        if vertex.z >= 0:
            v_max_z = max(v_max_z, vertex.z)
        else:
            v_min_z = min(v_min_z, vertex.z)
        rotated_point = saf.rotate(Point(vertex.x, vertex.y), 90, (0, 0))
        vertex.x = rotated_point.x * transformer.cos_lat_factor
        vertex.y = rotated_point.y / transformer.cos_lat_factor

    btg_lon, btg_lat = btg_reader.gbs_lon_lat
    btg_x, btg_y = transformer.to_local((btg_lon, btg_lat))
    logging.debug('Difference between BTG and transformer: x = %d, y = %d', btg_x, btg_y)

    min_x, min_y = transformer.to_local((parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH))
    max_x, max_y = transformer.to_local((parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH))
    bounds = (min_x, min_y, max_x, max_y)

    disjoint = 0
    accepted = 0
    counter = 0

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
                counter += 1
                v0 = vertices[face.vertices[0]]
                v1 = vertices[face.vertices[1]]
                v2 = vertices[face.vertices[2]]
                # create the triangle polygon
                my_geometry = Polygon([(v0.x - btg_x, v0.y - btg_y), (v1.x - btg_x, v1.y - btg_y),
                                       (v2.x - btg_x, v2.y - btg_y), (v0.x - btg_x, v0.y - btg_y)])
                if not my_geometry.is_valid:  # it might be self-touching or self-crossing polygons
                    clean = my_geometry.buffer(0)  # cf. http://toblerity.org/shapely/manual.html#constructive-methods
                    if clean.is_valid:
                        my_geometry = clean  # it is now a Polygon or a MultiPolygon
                    else:  # lets try with a different sequence of points
                        my_geometry = Polygon([(v0.x - btg_x, v0.y - btg_y), (v2.x - btg_x, v2.y - btg_y),
                                               (v1.x - btg_x, v1.y - btg_y), (v0.x - btg_x, v0.y - btg_y)])
                        if not my_geometry.is_valid:
                            clean = my_geometry.buffer(0)
                            if clean.is_valid:
                                my_geometry = clean
                if my_geometry.is_valid and not my_geometry.is_empty:
                    if not disjoint_bounds(bounds, my_geometry.bounds):
                        my_zone = m.BTGBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                    type_, my_geometry)
                        btg_zones.append(my_zone)
                        accepted += 1
                    else:
                        disjoint += 1
                else:
                    foo = 1  # FIXME
    logging.debug('Out of %i faces %i were disjoint and %i were accepted with the bounds.',
                  counter, disjoint, accepted)
    return btg_zones, btg_reader.faces[btg.WATER_PROXY]


def split_to_city_blocks() -> None:
    """Splits all land-use into (city) blocks, i.e. areas surrounded by streets.
    Creates a 'virtual' street at land-use boundary to also have blocks at outside of land-use zones.

    See https://networkx.github.io/documentation/stable/reference/algorithms/generated/networkx.algorithms.cycles.cycle_basis.html#networkx.algorithms.cycles.cycle_basis
    https://stackoverflow.com/questions/24021840/find-edges-in-a-cycle-networkx-python

    https://stackoverflow.com/questions/12367801/finding-all-cycles-in-undirected-graphs#18388696
    """

    return


def _process_landuse_for_lighting(building_zones: List[m.BuildingZone]) -> List[Polygon]:
    """Uses BUILT_UP_AREA_LIT_BUFFER to produce polygons for lighting of streets."""
    buffered_polygons = list()
    for zone in building_zones:
        buffered_polygons.append(zone.geometry.buffer(parameters.BUILT_UP_AREA_LIT_BUFFER))

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
                if my_polygon.area > parameters.BUILT_UP_AREA_LIT_HOLES_MIN_AREA:
                    survived_inner += 1
                    inner_rings.append(ring)
            corrected_poly = Polygon(zone.exterior, inner_rings)
            lit_areas.append(corrected_poly)
            logging.debug('Removed %i holes from lit area. Number of holes left: %i', total_inner - survived_inner,
                          survived_inner)
        else:
            lit_areas.append(zone)

    return lit_areas


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


def process(transformer: Transformation) -> None:
    last_time = time.time()

    # =========== READ OSM DATA =============
    building_zones = m.process_osm_building_zone_refs(transformer)
    places = m.process_osm_place_refs(transformer)
    osm_buildings = m.process_osm_building_refs(transformer)
    highways_dict = m.process_osm_highway_refs(transformer)
    railways_dict = m.process_osm_railway_refs(transformer)
    waterways_dict = m.process_osm_waterway_refs(transformer)

    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    # =========== READ LAND-USE DATA FROM FLIGHTGEAR BTG-FILES =============
    btg_building_zones = list()
    if parameters.OWBB_USE_BTG_LANDUSE:
        btg_building_zones, btg_water = _process_btg_building_zones(transformer)
        last_time = time_logging("Time used in seconds for reading BTG zones", last_time)

    if len(btg_building_zones) > 0:
        _generate_building_zones_from_external(building_zones, btg_building_zones)
    last_time = time_logging("Time used in seconds for processing external zones", last_time)

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

    # =========== CREATE POLYGONS FOR LIGTHING OF STREETS ================================
    lit_areas = _process_landuse_for_lighting(building_zones)
    last_time = time_logging("Time used in seconds for finding lit areas", last_time)

    # =========== FIND CITY BLOCKS ==========
    # using an algorithm in a undirected graph finding simple cycles
    # TODO

    # ============finally guess the land-use type ========================================
    for my_zone in building_zones:
        if isinstance(my_zone, m.GeneratedBuildingZone):
            my_zone.guess_building_zone_type(places)
    last_time = time_logging("Time used in seconds for guessing zone types", last_time)

    # =========== FINALIZE PROCESSING ====================================================
    if parameters.DEBUG_PLOT:
        bounds = m.Bounds.create_from_parameters(transformer)
        plotting.draw_zones(highways_dict, osm_buildings, building_zones, btg_building_zones, lit_areas, bounds)
        time_logging("Time used in seconds for plotting", last_time)
