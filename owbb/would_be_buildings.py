# -*- coding: utf-8 -*-
"""Module analyzing OSM data and generating buildings at plausible places."""

import logging
import pickle
import random
import time
from typing import Dict, List, Optional
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
import utils.osmstrings as s
from utils.utilities import time_logging, random_value_from_ratio_dict_parameter

if speedups.available:
    speedups.enable()
else:
    speedups.disable()


def _prepare_building_zone_for_building_generation(building_zone, waterways_dict, railway_lines_dict, highways_dict,
                                                   open_spaces_dict: Dict[int, m.OpenSpace]):
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
    _prepare_building_zone_with_blocked_areas(building_zone, waterways_dict, railway_lines_dict, highways_dict_copy1,
                                              open_spaces_dict)
    _prepare_building_zone_with_highways(building_zone, highways_dict_copy2)


def _prepare_building_zone_with_blocked_areas(building_zone, waterways_dict, railway_lines_dict, highways_dict,
                                              open_spaces_dict: Dict[int, m.OpenSpace]):
    """Adds BlockedArea objects to a given BuildingZone."""
    building_zone.process_open_spaces_as_blocked_areas(open_spaces_dict)
    building_zone.process_buildings_as_blocked_areas()

    _process_linears_for_blocked_areas(building_zone, waterways_dict, m.BlockedAreaType.waterway)
    _process_linears_for_blocked_areas(building_zone, railway_lines_dict, m.BlockedAreaType.railway)
    _process_linears_for_blocked_areas(building_zone, highways_dict, m.BlockedAreaType.highway)


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


HIGHWAYS_FOR_ZONE_SPLIT = [m.HighwayType.motorway, m.HighwayType.trunk]


def _generate_extra_buildings(building_zone: m.BuildingZone, shared_models_library: m.SharedModelsLibrary,
                              bounding_box: Polygon):
    """AttributeErrors are expected because not all highways have settlement zones on both sides.
    Therefore they can get ignored."""
    for highway in building_zone.linked_genways:
        if highway.type_ in HIGHWAYS_FOR_ZONE_SPLIT:
            continue
        if building_zone.type_ is m.BuildingZoneType.residential:
            # apartment_houses_list = shared_models_library.residential_apartments
            detached_houses_list = shared_models_library.residential_detached

            # Some attribute errors are expected, because a highway might not have a city block on both sides
            caught_errors = 0
            # just use the along city_block to determine the settlement type, although the reverse could be different
            terrace_share = parameters.OWBB_RESIDENTIAL_RURAL_TERRACE_SHARE
            apartment_share = parameters.OWBB_RESIDENTIAL_RURAL_APARTMENT_SHARE
            try:
                if highway.along_city_block.settlement_type is bl.SettlementType.periphery:
                    terrace_share = parameters.OWBB_RESIDENTIAL_PERIPHERY_TERRACE_SHARE
                    apartment_share = parameters.OWBB_RESIDENTIAL_PERIPHERY_APARTMENT_SHARE
            except AttributeError:
                caught_errors += 1
                try:
                    if highway.reversed_city_block.settlement_type is not bl.SettlementType.periphery:
                        terrace_share = parameters.OWBB_RESIDENTIAL_PERIPHERY_TERRACE_SHARE
                        apartment_share = parameters.OWBB_RESIDENTIAL_PERIPHERY_APARTMENT_SHARE
                except AttributeError:
                    caught_errors += 1

            if caught_errors == 2:
                logging.warning('No city blocks on either side of highway %i in zone %i and settlement type %s',
                                highway.osm_id, building_zone.osm_id, building_zone.settlement_type)
            else:  # proceed with processing
                if highway.is_sideway() and (random.random() <= terrace_share):
                    # choose row house already now, so the same row house is potentially applied on both sides of street
                    index = random.randint(0, len(shared_models_library.residential_terraces) - 1)
                    alternatives_list = shared_models_library.residential_terraces[index:index + 1]
                elif random.random() <= apartment_share:
                    index = random.randint(0, len(shared_models_library.residential_apartments) - 1)
                    alternatives_list = shared_models_library.residential_apartments[index:index + 1]
                else:
                    alternatives_list = None

                # prepare for not rural / periphery, so we can have the same along and reverse
                primary_houses = shared_models_library.residential_attached
                try:
                    if highway.along_city_block.settlement_type is bl.SettlementType.dense:
                        building_type = random_value_from_ratio_dict_parameter(parameters.OWBB_RESIDENTIAL_DENSE_TYPE_SHARE)
                        if building_type == 'detached':
                            primary_houses = shared_models_library.residential_detached
                        elif building_type == 'terrace':
                            index = random.randint(0, len(shared_models_library.residential_terraces) - 1)
                            primary_houses = shared_models_library.residential_terraces[index:index + 1]
                        elif building_type == 'apartments':
                            index = random.randint(0, len(shared_models_library.residential_apartments) - 1)
                            primary_houses = shared_models_library.residential_apartments[index:index + 1]
                except AttributeError:
                    pass

                # along
                try:
                    if highway.along_city_block.settlement_type in [bl.SettlementType.rural,
                                                                    bl.SettlementType.periphery]:
                        _generate_extra_buildings_residential(building_zone, highway, detached_houses_list,
                                                              alternatives_list, False, bounding_box)
                    else:
                        _generate_extra_buildings_residential(building_zone, highway, primary_houses, None,
                                                              False, bounding_box)
                except AttributeError as e:
                    pass
                # reverse
                try:
                    if highway.reversed_city_block.settlement_type in [bl.SettlementType.rural,
                                                                      bl.SettlementType.periphery]:
                        _generate_extra_buildings_residential(building_zone, highway, detached_houses_list,
                                                              alternatives_list, True, bounding_box)
                    else:
                        _generate_extra_buildings_residential(building_zone, highway, primary_houses, None,
                                                              True, bounding_box)
                except AttributeError as e:
                    pass

        else:  # elif landuse.type_ is Landuse.TYPE_INDUSTRIAL:
            _generate_extra_buildings_industrial(building_zone, highway, shared_models_library, False, bounding_box)
            _generate_extra_buildings_industrial(building_zone, highway, shared_models_library, True, bounding_box)


def _generate_extra_buildings_residential(building_zone: m.BuildingZone, highway: m.Highway,
                                          primary_houses_list: List[m.SharedModel],
                                          alternatives_list: Optional[List[m.SharedModel]],
                                          is_reverse: bool, bounding_box: m.Polygon):
    my_settlement_type = highway.along_city_block.settlement_type
    if is_reverse:
        my_settlement_type = highway.reversed_city_block.settlement_type
    if alternatives_list:
        temp_buildings = m.TempGenBuildings(bounding_box)
        _generate_buildings_along_highway(building_zone, my_settlement_type,
                                          highway, alternatives_list, is_reverse, temp_buildings)
        if 0 < temp_buildings.validate_uninterrupted_sequence(parameters.OWBB_RESIDENTIAL_HIGHWAY_MIN_GEN_SHARE,
                                                              parameters.OWBB_RESIDENTIAL_TERRACE_MIN_NUMBER):
            building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)
            return  # we do not want to spoil row houses with other houses to fill up

    # start from scratch - either because terrace not chosen or not successfully validated
    temp_buildings = m.TempGenBuildings(bounding_box)
    _generate_buildings_along_highway(building_zone, my_settlement_type,
                                      highway, primary_houses_list, is_reverse, temp_buildings)
    if temp_buildings.validate_min_share_generated(parameters.OWBB_RESIDENTIAL_HIGHWAY_MIN_GEN_SHARE):
        building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)


def _generate_extra_buildings_industrial(building_zone: m.BuildingZone, highway: m.Highway,
                                         shared_models_library: m.SharedModelsLibrary,
                                         is_reverse: bool, bounding_box: Polygon):
    temp_buildings = m.TempGenBuildings(bounding_box)
    if random.random() <= parameters.OWBB_INDUSTRIAL_LARGE_SHARE:
        shared_models_list = shared_models_library.industrial_buildings_large
        _generate_buildings_along_highway(building_zone, building_zone.settlement_type,
                                          highway, shared_models_list, is_reverse, temp_buildings)

    shared_models_list = shared_models_library.industrial_buildings_small
    _generate_buildings_along_highway(building_zone, building_zone.settlement_type,
                                      highway, shared_models_list, is_reverse, temp_buildings)
    building_zone.commit_temp_gen_buildings(temp_buildings, highway, is_reverse)


def _generate_buildings_along_highway(building_zone: m.BuildingZone, settlement_type: bl.SettlementType,
                                      highway: m.Highway,
                                      shared_models_list: List[m.SharedModel], is_reverse: bool,
                                      temp_buildings: m.TempGenBuildings):
    """
    The central assumption is that existing blocked areas incl. buildings du not need a buffer.
    The to be populated buildings all bring their own constraints with regards to distance to road, distance to other
    buildings etc.

    Returns a TempGenBuildings object with all potential new generated buildings
    """
    travelled_along = 0
    highway_length = highway.geometry.length
    my_gen_building = m.GenBuilding(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_owbb),
                                    random.choice(shared_models_list), highway.get_width(), settlement_type)
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
        buffer_polygon = my_gen_building.get_a_polygon(True, point_on_line, angle)
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
                area_polygon = my_gen_building.get_a_polygon(False, point_on_line, angle)
                my_gen_building.set_location(point_on_line, angle, area_polygon, buffer_polygon)
                temp_buildings.add_generated(my_gen_building, m.BlockedArea(m.BlockedAreaType.gen_building,
                                                                            area_polygon))
                # prepare a new building, which might get added in the next loop
                my_gen_building = m.GenBuilding(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_owbb),
                                                random.choice(shared_models_list), highway.get_width(), settlement_type)


def _read_building_models_library() -> List[m.BuildingModel]:
    # FIXME: hard-coded to be replaced
    # The correct BUILDING_KEY has to be given
    # Define the building:levels - and do NOT specify height
    # TODO: the list of building types must correspond to models.SharedModelsLibrary
    models = list()

    # residential detached
    detached_1_tags = {s.K_BUILDING: 'detached',
                       'building:colour': 'white', 'building:levels': '2',
                       'roof:colour': 'red', 'roof:shape': 'hipped', 'roof:height': '2',
                       s.K_OWBB_GENERATED: 'yes'}
    detached_1 = m.BuildingModel(15., 8., bl.BuildingType.detached, list(), None, 0, 0, detached_1_tags)
    models.append(detached_1)
    detached_2_tags = {s.K_BUILDING: 'detached',
                       'building:colour': 'tan', 'building:levels': '1',
                       'roof:colour': 'firebrick', 'roof:shape': 'gabled', 'roof:height': '2',
                       s.K_OWBB_GENERATED: 'yes'}
    detached_2 = m.BuildingModel(10., 10., bl.BuildingType.detached, list(), None, 0, 0, detached_2_tags)
    models.append(detached_2)
    detached_3_tags = {s.K_BUILDING: 'detached',
                       'building:colour': 'pink', 'building:levels': '2',
                       'roof:colour': 'firebrick', 'roof:shape': 'gabled', 'roof:height': '2',
                       s.K_OWBB_GENERATED: 'yes'}
    detached_3 = m.BuildingModel(16., 12., bl.BuildingType.detached, list(), None, 0, 0, detached_3_tags)
    models.append(detached_3)
    detached_4_tags = {s.K_BUILDING: 'detached',
                       'building:colour': 'beige', 'building:levels': '2',
                       'roof:colour': 'black', 'roof:shape': 'gambrel', 'roof:height': '2',
                       s.K_OWBB_GENERATED: 'yes'}
    detached_4 = m.BuildingModel(12., 9., bl.BuildingType.detached, list(), None, 0, 0, detached_4_tags)
    models.append(detached_4)

    # residential apartments (for rural, periphery and dense)
    apartment_1_tags = {s.K_BUILDING: 'apartments',
                        'building:colour': 'white', 'building:levels': '3',
                        'roof:colour': 'firebrick', 'roof:shape': 'gabled', 'roof:height': '2',
                        s.K_OWBB_GENERATED: 'yes'}
    apartment_1 = m.BuildingModel(30., 20, bl.BuildingType.apartments, list(), None, 0, 0, apartment_1_tags)
    models.append(apartment_1)
    apartment_2_tags = {s.K_BUILDING: 'apartments',
                        'building:colour': 'beige', 'building:levels': '3',
                        'roof:colour': 'red', 'roof:shape': 'gabled', 'roof:height': '2',
                        s.K_OWBB_GENERATED: 'yes'}
    apartment_2 = m.BuildingModel(35., 14, bl.BuildingType.apartments, list(), None, 0, 0, apartment_2_tags)
    models.append(apartment_2)
    apartment_3_tags = {s.K_BUILDING: 'apartments',
                        'building:colour': 'tan', 'building:levels': '4',
                        'roof:colour': 'red', 'roof:shape': 'gabled', 'roof:height': '2',
                        s.K_OWBB_GENERATED: 'yes'}
    apartment_3 = m.BuildingModel(26., 22, bl.BuildingType.apartments, list(), None, 0, 0, apartment_3_tags)
    models.append(apartment_3)

    # residential attached (for dense, block and centre)
    # Will get roof type, number of levels etc. assigned automatically based on SettlementType and
    # other parameters
    attached_1_tags = {s.K_BUILDING: 'attached', 'building:colour': 'white', s.K_OWBB_GENERATED: 'yes'}
    attached_1 = m.BuildingModel(30., 15, bl.BuildingType.attached, list(), None, 0, 0, attached_1_tags)
    models.append(attached_1)
    attached_2_tags = {s.K_BUILDING: 'attached', 'building:colour': 'tan', s.K_OWBB_GENERATED: 'yes'}
    attached_2 = m.BuildingModel(35., 14, bl.BuildingType.attached, list(), None, 0, 0, attached_2_tags)
    models.append(attached_2)
    attached_3_tags = {s.K_BUILDING: 'attached', 'building:colour': 'snow', s.K_OWBB_GENERATED: 'yes'}
    attached_3 = m.BuildingModel(26., 14, bl.BuildingType.attached, list(), None, 0, 0, attached_3_tags)
    models.append(attached_3)

    # terrace
    terrace_1_tags = {s.K_BUILDING: 'terrace',
                      'building:colour': 'beige', 'building:levels': '2',
                      'roof:colour': 'darksalmon', 'roof:shape': 'skillion', 'roof:height': '1.5',
                      s.K_OWBB_GENERATED: 'yes'}
    terrace_1 = m.BuildingModel(8., 8., bl.BuildingType.terrace, list(), None, 0, 0, terrace_1_tags)
    models.append(terrace_1)
    terrace_2_tags = {s.K_BUILDING: 'terrace',
                      'building:colour': 'snow', 'building:levels': '2',
                      'roof:colour': 'firebrick', 'roof:shape': 'gabled', 'roof:height': '1.5',
                      s.K_OWBB_GENERATED: 'yes'}
    terrace_2 = m.BuildingModel(10., 8., bl.BuildingType.terrace, list(), None, 0, 0, terrace_2_tags)
    models.append(terrace_2)

    # industrial large
    industry_1_tags = {s.K_BUILDING: 'industrial',
                       'building:colour': 'silver',  'building:levels': '4',
                       'roof:colour': 'darkgray', 'roof:shape': 'flat', 'roof:height': '0',
                       s.K_OWBB_GENERATED: 'yes'}
    industry_1 = m.BuildingModel(20., 30., bl.BuildingType.industrial, list(), None, 0, 0, industry_1_tags)
    models.append(industry_1)
    industry_2_tags = {s.K_BUILDING: 'industrial',
                       'building:colour': 'silver',  'building:levels': '3',
                       'roof:colour': 'gray', 'roof:shape': 'flat', 'roof:height': '0',
                       s.K_OWBB_GENERATED: 'yes'}
    industry_2 = m.BuildingModel(40., 20., bl.BuildingType.industrial, list(), None, 0, 0, industry_2_tags)
    models.append(industry_2)
    industry_3_tags = {s.K_BUILDING: 'industrial',
                       'building:colour': 'lightyellow',  'building:levels': '2',
                       'roof:colour': 'darkgray', 'roof:gabled': 'flat', 'roof:height': '0',
                       s.K_OWBB_GENERATED: 'yes'}
    industry_3 = m.BuildingModel(26., 20., bl.BuildingType.industrial, list(), None, 0, 0, industry_3_tags)
    models.append(industry_3)
    # industrial small
    industry_4_tags = {s.K_BUILDING: 'industrial',
                       'building:colour': 'lightgreen', 'building:levels': '3',
                       'roof:colour': 'red', 'roof:shape': 'gabled', 'roof:height': '2',
                       s.K_OWBB_GENERATED: 'yes'}
    industry_4 = m.BuildingModel(20., 15., bl.BuildingType.industrial, list(), None, 0, 0, industry_4_tags)
    models.append(industry_4)
    industry_5_tags = {s.K_BUILDING: 'industrial',
                       'building:colour': 'white', 'building:levels': '2',
                       'roof:colour': 'black', 'roof:shape': 'flat', 'roof:height': '0',
                       s.K_OWBB_GENERATED: 'yes'}
    industry_5 = m.BuildingModel(25., 10., bl.BuildingType.industrial, list(), None, 0, 0, industry_5_tags)
    models.append(industry_5)

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
        _prepare_building_zone_for_building_generation(b_zone, waterways_dict, railways_dict, highways_dict,
                                                       open_spaces_dict)
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
