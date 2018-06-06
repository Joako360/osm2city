# -*- coding: utf-8 -*-
"""Module analyzing OSM data and generating buildings at plausible places."""

import logging
import pickle
import random
import time
from typing import Dict, List
import sys

from shapely import speedups
from shapely.geometry import box
from shapely.geometry import LineString, MultiLineString, Polygon

import building_lib as bl
import owbb.models as m
import owbb.plotting as plotting
import utils.coordinates as co
import parameters
import utils.osmparser as op
from utils.utilities import time_logging

if speedups.available:
    speedups.enable()
else:
    speedups.disable()


def _prepare_building_zone_for_building_generation(building_zone, open_spaces_dict,
                                                   waterways_dict, railway_lines_dict, highways_dict):
    """Prepares a building zone with blocked areas and highway parts.
    As soon as an element is entirely within a building zone, it is removed
    from the lists in order to speedup by reducing the number of stuff to compare in the next
    building zone (the lists area shared / passed by reference).
    In order to make these removals fast the data structures must be dicts instead of lists.

    Another possibility would be parallel processing, but that would lead to big
    memory consumption due to copies of data structures in each process
    or overhead due to shared data structure (e.g. Manager.dict()).
    A last possibility would be a global variable in the module, which on at least Linux
    would be shared by all."""
    highways_dict_copy1 = highways_dict.copy()  # otherwise when using highways_dict in plotting it will be "used"
    highways_dict_copy2 = highways_dict.copy()
    _prepare_building_zone_with_blocked_areas(building_zone, open_spaces_dict,
                                              waterways_dict, railway_lines_dict, highways_dict_copy1)
    _prepare_building_zone_with_highways(building_zone, highways_dict_copy2)


def _prepare_building_zone_with_blocked_areas(building_zone, open_spaces_dict,
                                              waterways_dict, railway_lines_dict, highways_dict):
    """Adds BlockedArea objects to a given BuildingZone."""
    _process_open_spaces_as_blocked_areas(building_zone, open_spaces_dict)
    _process_buildings_as_blocked_areas(building_zone)

    _process_linears_for_blocked_areas(building_zone, waterways_dict, m.BlockedAreaType.waterway)
    _process_linears_for_blocked_areas(building_zone, railway_lines_dict, m.BlockedAreaType.railway)
    _process_linears_for_blocked_areas(building_zone, highways_dict, m.BlockedAreaType.highway)


def _process_open_spaces_as_blocked_areas(building_zone, open_spaces_dict):
    to_be_removed = list()  # All open_spaces, which are within the building_zone, will be removed from open_spaces
    for candidate in open_spaces_dict.values():
        is_blocked = False
        if candidate.geometry.within(building_zone.geometry):
            is_blocked = True
            to_be_removed.append(candidate.osm_id)
        elif candidate.geometry.intersects(building_zone.geometry):
                is_blocked = True
        if is_blocked:
            blocked = m.BlockedArea(m.BlockedAreaType.open_space, candidate.geometry, candidate.type_)
            building_zone.linked_blocked_areas.append(blocked)
    for key in to_be_removed:
        del open_spaces_dict[key]


def _process_buildings_as_blocked_areas(building_zone):
    for building in building_zone.osm_buildings:
        blocked = m.BlockedArea(m.BlockedAreaType.osm_building, building.geometry,
                                bl.parse_building_tags_for_type(building.tags))
        building_zone.linked_blocked_areas.append(blocked)


def _process_linears_for_blocked_areas(building_zone, linears_dict, blocked_area_type):
    """Only to be used for OSMFeatureLinears"""
    to_be_removed = list()
    for candidate in linears_dict.values():
        if candidate.geometry.within(building_zone.geometry):
            building_zone.linked_blocked_areas.append(m.BlockedArea(blocked_area_type,
                                                                    candidate.geometry.buffer(candidate.get_width()/2)))
            to_be_removed.append(candidate.osm_id)
            continue
        intersection = candidate.geometry.intersection(building_zone.geometry)
        if not intersection.is_empty:
            if isinstance(intersection, LineString):
                building_zone.linked_blocked_areas.append(m.BlockedArea(blocked_area_type,
                                                                        intersection.buffer(candidate.get_width()/2)))
            elif isinstance(intersection, MultiLineString):
                for my_line in intersection:
                    if isinstance(my_line, LineString):
                        building_zone.linked_blocked_areas.append(m.BlockedArea(blocked_area_type,
                                                                                my_line.buffer(
                                                                                    candidate.get_width()/2)))
    for key in to_be_removed:
        del linears_dict[key]


def _prepare_building_zone_with_highways(building_zone, highways_dict):
    """Link highways to BuildingZones to prepare for building generation.
    Either as whole if entirely within or as a set of intersections if intersecting
    """
    to_be_removed = list()
    for my_highway in highways_dict.values():
        if not my_highway.populate_buildings_along():
            continue
        if my_highway.geometry.length < parameters.OWBB_MIN_STREET_LENGTH:
            continue
        if my_highway.geometry.within(building_zone.geometry):
            building_zone.linked_genways.append(my_highway)
            to_be_removed.append(my_highway.osm_id)
            continue
        # process intersections
        if my_highway.geometry.intersects(building_zone.geometry):
            intersections = list()
            intersections.append(my_highway.geometry.intersection(building_zone.geometry))
            if len(intersections) > 0:
                for intersection in intersections:
                    if isinstance(intersection, MultiLineString):
                        for my_line in intersection:
                            if isinstance(my_line, LineString):
                                intersections.append(my_line)
                    elif isinstance(intersection, LineString):
                        if intersection.length >= parameters.OWBB_MIN_STREET_LENGTH:
                            new_highway = m.Highway.create_from_scratch(op.get_next_pseudo_osm_id(
                                op.OSMFeatureType.road), my_highway, intersection)
                            building_zone.linked_genways.append(new_highway)
    for key in to_be_removed:
        del highways_dict[key]


def _generate_extra_buildings(building_zone: m.BuildingZone, shared_models_library: m.SharedModelsLibrary,
                              bounding_box: Polygon):
    for highway in building_zone.linked_genways:
        if building_zone.type_ is m.BuildingZoneType.residential:
            detached_houses_list = shared_models_library.residential_detached
            # choose row house already now, so the same row house is potentially applied on both sides of street
            index = random.randint(0, len(shared_models_library.residential_terraces) - 1)
            row_houses_list = shared_models_library.residential_terraces[index:index + 1]
            if highway.is_sideway() and (random.random() <= parameters.OWBB_RESIDENTIAL_TERRACE_SHARE):
                try_terrace = True
            else:
                try_terrace = False
            _generate_extra_buildings_residential(building_zone, highway, detached_houses_list, row_houses_list,
                                                  False, try_terrace, bounding_box)
            _generate_extra_buildings_residential(building_zone, highway, detached_houses_list, row_houses_list,
                                                  True, try_terrace, bounding_box)

        else:  # elif landuse.type_ is Landuse.TYPE_INDUSTRIAL:
            _generate_extra_buildings_industrial(building_zone, highway, shared_models_library, False, bounding_box)
            _generate_extra_buildings_industrial(building_zone, highway, shared_models_library, True, bounding_box)


def _generate_extra_buildings_residential(building_zone: m.BuildingZone, highway: m.Highway,
                                          detached_houses_list: List[m.SharedModel],
                                          row_houses_list: List[m.SharedModel],
                                          is_reverse: bool, try_terrace: bool, bounding_box: m.Polygon):
    if try_terrace:
        temp_buildings = m.TempGenBuildings(bounding_box)
        _generate_buildings_along_highway(building_zone, highway, row_houses_list, is_reverse, temp_buildings)
        if 0 < temp_buildings.validate_uninterrupted_sequence(parameters.OWBB_RESIDENTIAL_HIGHWAY_MIN_GEN_SHARE,
                                                              parameters.OWBB_RESIDENTIAL_TERRACE_MIN_NUMBER):
            building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)
            return  # we do not want to spoil row houses with other houses to fill up

    # start from scratch - either because terrace not chosen or not successfully validated
    temp_buildings = m.TempGenBuildings(bounding_box)
    _generate_buildings_along_highway(building_zone, highway, detached_houses_list, is_reverse, temp_buildings)
    if temp_buildings.validate_min_share_generated(parameters.OWBB_RESIDENTIAL_HIGHWAY_MIN_GEN_SHARE):
        building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)


def _generate_extra_buildings_industrial(building_zone: m.BuildingZone, highway: m.Highway,
                                         shared_models_library: m.SharedModelsLibrary,
                                         is_reverse: bool, bounding_box: Polygon):
    temp_buildings = m.TempGenBuildings(bounding_box)
    if random.random() <= parameters.OWBB_INDUSTRIAL_LARGE_SHARE:
        shared_models_list = shared_models_library.industrial_buildings_large
        _generate_buildings_along_highway(building_zone, highway, shared_models_list, is_reverse, temp_buildings)

    shared_models_list = shared_models_library.industrial_buildings_small
    _generate_buildings_along_highway(building_zone, highway, shared_models_list, is_reverse, temp_buildings)
    building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)


def _generate_buildings_along_highway(building_zone: m.BuildingZone, highway: m.Highway,
                                      shared_models_list: List[m.SharedModel], is_reverse: bool,
                                      temp_buildings: m.TempGenBuildings):
    """
    The central assumption is that existing blocked areas incl. buildings du not need a buffer.
    The to be populated buildings all bring their own constraints with regards to distance to road, distance to other
    buildings etc.

    Returns a LanduseTempGenBuildings object with all potential new generated buildings
    """
    travelled_along = 0
    highway_length = highway.geometry.length
    my_gen_building = m.GenBuilding(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_owbb),
                                    random.choice(shared_models_list), highway.get_width())
    if not is_reverse:
        point_on_line = highway.geometry.interpolate(0)
    else:
        point_on_line = highway.geometry.interpolate(highway_length)
    while travelled_along < highway_length:
        travelled_along += parameters.OWBB_STEP_DISTANCE
        prev_point_on_line = point_on_line
        if not is_reverse:
            point_on_line = highway.geometry.interpolate(travelled_along)
        else:
            point_on_line = highway.geometry.interpolate(highway_length - travelled_along)
        angle = co.calc_angle_of_line_local(prev_point_on_line.x, prev_point_on_line.y,
                                            point_on_line.x, point_on_line.y)
        buffer_polygon = my_gen_building.get_area_polygon(True, point_on_line, angle)
        if buffer_polygon.within(building_zone.geometry):
            valid_new_gen_building = True
            for blocked_area in building_zone.linked_blocked_areas:
                if buffer_polygon.intersects(blocked_area.polygon):
                    valid_new_gen_building = False
                    break
            if valid_new_gen_building:
                for blocked_area in temp_buildings.generated_blocked_areas:
                    if buffer_polygon.intersects(blocked_area.polygon):
                        valid_new_gen_building = False
                        break
            if valid_new_gen_building:
                area_polygon = my_gen_building.get_area_polygon(False, point_on_line, angle)
                my_gen_building.set_location(point_on_line, angle, area_polygon, buffer_polygon)
                temp_buildings.add_generated(my_gen_building, m.BlockedArea(m.BlockedAreaType.gen_building,
                                                                            area_polygon))
                # prepare a new building, which might get added in the next loop
                my_gen_building = m.GenBuilding(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_owbb),
                                                random.choice(shared_models_list), highway.get_width())


def _read_building_models_library() -> List[m.BuildingModel]:
    # FIXME: hard-coded to be replaced
    # The correct BUILDING_KEY has to be given
    # always define the building:levels - and do NOT specify height
    models = list()

    # residential
    detached_1_tags = {bl.BUILDING_KEY: 'detached',
                       'building:colour': 'white', 'building:levels': '2',
                       'roof:colour': 'red', 'roof:shape': 'hipped', 'roof:height': '2',
                       bl.OWBB_GENERATED_KEY: 'yes'}
    detached_1 = m.BuildingModel(15., 8., bl.BuildingType.detached, list(), None, 0, 0, detached_1_tags)
    models.append(detached_1)
    detached_2_tags = {bl.BUILDING_KEY: 'detached',
                       'building:colour': 'yellow', 'building:levels': '1',
                       'roof:colour': 'firebrick', 'roof:shape': 'gabled', 'roof:height': '3',
                       bl.OWBB_GENERATED_KEY: 'yes'}
    detached_2 = m.BuildingModel(10., 10., bl.BuildingType.detached, list(), None, 0, 0, detached_2_tags)
    models.append(detached_2)

    # terrace
    terrace_1_tags = {bl.BUILDING_KEY: 'terrace',
                      'building:colour': 'aqua', 'building:levels': '2',
                      'roof:colour': 'darksalmon', 'roof:shape': 'skillion', 'roof:height': '1.5',
                      bl.OWBB_GENERATED_KEY: 'yes'}
    terrace_1 = m.BuildingModel(5., 3., bl.BuildingType.terrace, list(), None, 0, 0, terrace_1_tags)
    models.append(terrace_1)

    # industrial
    industry_1_tags = {bl.BUILDING_KEY: 'industrial',
                       'building:colour': 'silver',  'building:levels': '4',
                       'roof:colour': 'darkgray', 'roof:shape': 'flat', 'roof:height': '0',
                       bl.OWBB_GENERATED_KEY: 'yes'}
    industry_1 = m.BuildingModel(20., 30., bl.BuildingType.industrial, list(), None, 0, 0, industry_1_tags)
    models.append(industry_1)
    industry_1_tags = {bl.BUILDING_KEY: 'industrial',
                       'building:colour': 'navy', 'building:levels': '3',
                       'roof:colour': 'darkgray', 'roof:shape': 'gabled', 'roof:height': '3',
                       bl.OWBB_GENERATED_KEY: 'yes'}
    industry_1 = m.BuildingModel(20., 15., bl.BuildingType.industrial, list(), None, 0, 0, industry_1_tags)
    models.append(industry_1)

    return models


def process(transformer: co.Transformation, building_zones: List[m.BuildingZone],
            highways_dict: Dict[int, m.Highway], railways_dict: Dict[int, m.RailwayLine],
            waterways_dict: Dict[int, m.Waterway]) -> List[bl.Building]:
    last_time = time.time()

    # =========== TRY TO READ CACHED DATA FIRST =======
    tile_index = parameters.get_tile_index()
    cache_file = str(tile_index) + '_generated_buildings.pkl'
    if parameters.OWBB_GENERATED_BUILDINGS_CACHE:
        try:
            with open(cache_file, 'rb') as file_pickle:
                generated_buildings = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(generated_buildings), cache_file)
            return generated_buildings
        except (IOError, EOFError) as reason:
            logging.info("Loading of cache %s failed (%s)", cache_file, reason)

    # =========== READ OSM DATA =============

    open_spaces_dict = m.process_osm_open_space_refs(transformer)
    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    bounds = m.Bounds.create_from_parameters(transformer)
    bounding_box = box(bounds.min_point.x, bounds.min_point.y, bounds.max_point.x, bounds.max_point.y)

    # =========== READ BUILDING MODEL DATA =============
    try:
        building_models = _read_building_models_library()

        shared_models_library = m.SharedModelsLibrary(building_models)
        if not shared_models_library.is_valid():
            logging.critical("The building model library cannot get transformed into a valid shared models library.")
            sys.exit(1)
    except IOError as reason:
        logging.critical("Building model library is not readable: %s", reason)
        sys.exit(1)

    last_time = time_logging("Time used in seconds for reading building model data", last_time)

    # =========== SELECT ZONES FOR GENERATION OF BUILDINGS =============
    not_used_zones = list()  # not used for generation of new buildings
    used_zones = list()  # used for generation of new buildings
    for b_zone in building_zones:
        use_me = True  # default for OSM zones
        # check based on parameters whether building zone should be used at all
        if isinstance(b_zone, m.GeneratedBuildingZone):
            if b_zone.from_buildings:
                use_me = parameters.OWBB_USE_GENERATED_LANDUSE_FOR_BUILDING_GENERATION
            else:
                use_me = parameters.OWBB_USE_EXTERNAL_LANDUSE_FOR_BUILDING_GENERATION

        # check whether density is already all right
        if use_me:
            total_building_area = 0
            for building in b_zone.osm_buildings:
                total_building_area += building.area

            if total_building_area > b_zone.geometry.area * parameters.OWBB_ZONE_AREA_MAX_GEN:
                use_me = False
            logging.debug("Zone %d: total area buildings = %d, total area zone = %d -> used = %s",
                          b_zone.osm_id, total_building_area, int(b_zone.geometry.area), str(use_me))

        # finally do the assignments
        if use_me:
            used_zones.append(b_zone)
        else:
            not_used_zones.append(b_zone)

    logging.debug("Number of selected building zones for generation of buildings: %d out of %d",
                  len(used_zones), len(building_zones))
    last_time = time_logging("Time used in seconds for selecting building zones for generation", last_time)

    # =========== START GENERATION OF BUILDINGS =============

    for b_zone in used_zones:
        _prepare_building_zone_for_building_generation(b_zone, open_spaces_dict,
                                                       waterways_dict, railways_dict, highways_dict)
        b_zone.link_city_blocks_to_highways()
    last_time = time_logging("Time used in seconds for preparing building zones for building generation", last_time)

    building_zones = list()  # will be filled again with used_zones out of the parallel processes
    preliminary_buildings = list()
    for b_zone in used_zones:
        _generate_extra_buildings(b_zone, shared_models_library, bounding_box)
        building_zones.append(b_zone)
        logging.debug("Generated %d buildings for building zone %d", len(b_zone.generated_buildings),
                      b_zone.osm_id)
        preliminary_buildings.extend(b_zone.generated_buildings)
    last_time = time_logging("Time used in seconds for generating buildings", last_time)
    logging.info("Total number of buildings generated: %d", len(preliminary_buildings))

    building_zones.extend(not_used_zones)  # lets add the not_used_zones again, so we have everything again

    if parameters.DEBUG_PLOT_GENBUILDINGS:
        logging.info('Start of plotting buildings')
        plotting.draw_buildings(building_zones, bounds)
        time_logging("Time used in seconds for plotting", last_time)

    # ============== Create buildings for building_lib processing ==
    generated_buildings = list()
    for pre_building in preliminary_buildings:
        generated_buildings.append(pre_building.create_building_lib_building())

    # =========== WRITE TO CACHE AND RETURN
    if parameters.OWBB_GENERATED_BUILDINGS_CACHE:
        try:

            with open(cache_file, 'wb') as file_pickle:
                pickle.dump(generated_buildings, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(generated_buildings), cache_file)
        except (IOError, EOFError) as reason:
            logging.info("Saving of cache %s failed (%s)", cache_file, reason)

    return generated_buildings
