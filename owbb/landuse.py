# -*- coding: utf-8 -*-
"""Handles land-use related stuff, especially generating new land-use where OSM data is not sufficient.
"""

import logging
import math
import os.path
import pickle
import time
from typing import Dict, List, Optional, Tuple

import pyproj
from shapely.geometry import box, MultiPolygon, Polygon, CAP_STYLE, JOIN_STYLE
from shapely.ops import unary_union
from shapely.prepared import prep

import buildings as bu
import building_lib as bl
import parameters
import owbb.models as m
import owbb.plotting as plotting
import owbb.would_be_buildings as wbb
import utils.aptdat_io as aptdat_io
import utils.btg_io as btg
import utils.calc_tile as ct
import utils.osmparser as op
from utils.coordinates import disjoint_bounds, Transformation
from utils.stg_io2 import scenery_directory_name, SceneryType
from utils.utilities import time_logging, merge_buffers


def _process_aerodromes(building_zones: List[m.BuildingZone], aerodrome_zones: List[m.BuildingZone],
                        airports: List[aptdat_io.Airport], transformer: Transformation) -> None:
    """Merges aerodromes from OSM and apt.dat and then cuts the areas from buildings zones.
    Aerodromes might be missing in apt.dat or OSM (or both - which we cannot correct)"""
    apt_dat_polygons = list()

    # get polygons from apt.dat in local coordinates
    for airport in airports:
        if airport.within_boundary(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                   parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH):
            my_polys = airport.create_boundary_polygons(transformer)
            if my_polys is not None:
                apt_dat_polygons.extend(my_polys)
    # see whether some polygons can be merged to reduce the list
    apt_dat_polygons = merge_buffers(apt_dat_polygons)

    # merge these polygons with existing aerodrome_zones
    for aerodrome_zone in aerodrome_zones:
        for poly in reversed(apt_dat_polygons):
            if poly.disjoint(aerodrome_zone.geometry) is False:
                aerodrome_zone.geometry = aerodrome_zone.geometry.union(poly)
                apt_dat_polygons.remove(poly)

    # for the remaining polygons create new aerodrome_zones
    for poly in apt_dat_polygons:
        new_aerodrome_zone = m.BuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                            poly, m.BuildingZoneType.aerodrome)
        aerodrome_zones.append(new_aerodrome_zone)

    # make sure that if a building zone is overlapping with a aerodrome that it is clipped
    for building_zone in building_zones:
        for aerodrome_zone in aerodrome_zones:
            if building_zone.geometry.disjoint(aerodrome_zone.geometry) is False:
                building_zone.geometry = building_zone.geometry.difference(aerodrome_zone.geometry)

    # finally add all aerodrome_zones to the building_zones as regular zone
    building_zones.extend(aerodrome_zones)


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
    logging.debug("Generated building zones from external land-use: %i", counter)


def _generate_building_zones_from_buildings(building_zones: List[m.BuildingZone],
                                            buildings_outside: List[bl.Building]) -> None:
    """Adds "missing" building_zones based on building clusters outside of OSM land-use.
    The calculated values are implicitly updated in the referenced parameter building_zones"""
    zones_candidates = dict()
    for my_building in buildings_outside:
        buffer_distance = parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE
        if my_building.area > parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
            factor = math.sqrt(my_building.area / parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
            buffer_distance = min(factor*parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE,
                                  parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
        buffer_polygon = my_building.geometry.buffer(buffer_distance)
        within_existing_building_zone = False
        for candidate in zones_candidates.values():
            if buffer_polygon.intersects(candidate.geometry):
                candidate.geometry = candidate.geometry.union(buffer_polygon)
                candidate.relate_building(my_building)
                within_existing_building_zone = True
                break
        if not within_existing_building_zone:
            my_candidate = m.GeneratedBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                                   buffer_polygon, m.BuildingZoneType.non_osm)
            my_candidate.relate_building(my_building)
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
                for building in zones_candidates[keys[i]].osm_buildings:
                    zones_candidates[keys[j]].relate_building(building)
                break
    logging.debug("Candidate land-uses merged into others: %d", len(merged_candidate_ids))
    # check for minimum size and then simplify geometry
    kept_candidates = list()
    for candidate in zones_candidates.values():
        if candidate.osm_id in merged_candidate_ids:
            continue  # do not keep merged candidates
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
                                                         split_polygon, zone.type_)
            new_generated.append(my_split_generated)
        while len(zone.osm_buildings) > 0:
            my_building = zone.osm_buildings.pop()
            for my_split_generated in new_generated:
                if my_building.geometry.intersects(my_split_generated.geometry):
                    my_split_generated.relate_building(my_building)
                    continue
        for my_split_generated in new_generated:
            if my_split_generated.from_buildings and len(my_split_generated.osm_buildings) == 0:
                continue
            split_zones.append(my_split_generated)
            logging.debug("Added sub-polygon with area %d and %d buildings", my_split_generated.geometry.area,
                          len(my_split_generated.osm_buildings))
    else:
        split_zones.append(zone)
    return split_zones


def _process_btg_building_zones(transformer: Transformation) -> List[m.BTGBuildingZone]:
    """There is a need to do a local coordinate transformation, as BTG also has a local coordinate
    transformation, but there the center will be in the middle of the tile, whereas here is can be
     another place if the boundary is not a whole tile."""
    lon_lat = parameters.get_center_global()
    path_to_btg = ct.construct_path_to_files(parameters.PATH_TO_SCENERY, scenery_directory_name(SceneryType.terrain),
                                             (lon_lat.lon, lon_lat.lat))
    tile_index = parameters.get_tile_index()

    # cartesian ellipsoid
    in_proj = pyproj.Proj(proj='geocent', ellps='WGS84', datum='WGS84')
    # geodetic flat
    out_proj = pyproj.Proj(init='epsg:4326', ellps='WGS84', datum='WGS84')

    btg_file_name = os.path.join(path_to_btg, ct.construct_btg_file_name_from_tile_index(tile_index))
    if not os.path.isfile(btg_file_name):
        logging.warning('File %s does not exist. Ocean or missing in Terrasync?', btg_file_name)
        return list()
    logging.debug('Reading btg file: %s', btg_file_name)
    btg_reader = btg.BTGReader(btg_file_name)
    btg_lon, btg_lat = btg_reader.gbs_lon_lat
    btg_x, btg_y = transformer.to_local((btg_lon, btg_lat))
    logging.debug('Difference between BTG and transformer: x = %f, y = %f', btg_x, btg_y)

    gbs_center = btg_reader.gbs_center

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

        # translate to lon_lat and then to local coordinates
        lon, lat, _alt = pyproj.transform(in_proj, out_proj,
                                          vertex.x + gbs_center.x,
                                          vertex.y + gbs_center.y,
                                          vertex.z + gbs_center.z,
                                          radians=False)

        vertex.x, vertex.y = transformer.to_local((lon, lat))
        vertex.z = _alt

    min_x, min_y = transformer.to_local((parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH))
    max_x, max_y = transformer.to_local((parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH))
    bounds = (min_x, min_y, max_x, max_y)

    disjoint = 0
    accepted = 0
    counter = 0

    for key, faces_list in btg_reader.faces.items():
        if key in btg.URBAN_MATERIALS:
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
            temp_polys = list()
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
                if isinstance(my_geometry, Polygon) and my_geometry.is_valid and not my_geometry.is_empty:
                    if not disjoint_bounds(bounds, my_geometry.bounds):
                        temp_polys.append(my_geometry)
                        accepted += 1
                    else:
                        disjoint += 1
                else:
                    pass  # just discard the triangle

            # merge polygons as much as possible in order to reduce processing and not having polygons
            # smaller than parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA
            merged_list = merge_buffers(temp_polys)
            for merged_poly in merged_list:
                my_zone = m.BTGBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                            type_, merged_poly)
                btg_zones.append(my_zone)

    logging.debug('Out of %i faces %i were disjoint and %i were accepted with the bounds.',
                  counter, disjoint, accepted)
    logging.debug('Created a total of %i zones from BTG', len(btg_zones))
    return btg_zones


def _test_highway_intersecting_area(area: Polygon, highways_dict: Dict[int, m.Highway]) -> List[m.Highway]:
    """Returns highways that are within an area or intersecting with an area.

    Highways_dict gets reduced by those highways, which were within, such that searching in other
    areas gets quicker due to reduced volume.
    """
    prep_area = prep(area)
    linked_highways = list()
    to_be_removed = list()
    for my_highway in highways_dict.values():
        if not my_highway.populate_buildings_along():
            continue
        # a bit speed up by looking at bounds first
        is_disjoint = disjoint_bounds(my_highway.geometry.bounds, area.bounds)
        if not is_disjoint:
            if prep_area.contains_properly(my_highway.geometry):
                linked_highways.append(my_highway)
                to_be_removed.append(my_highway.osm_id)

            elif prep_area.intersects(my_highway.geometry):
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
    building_zone.reset_city_blocks()
    highways_dict_copy1 = highways_dict.copy()  # otherwise when using highways_dict in plotting it will be "used"

    polygons = list()
    intersecting_highways = _test_highway_intersecting_area(building_zone.geometry, highways_dict_copy1)
    if intersecting_highways:
        buffers = list()
        for highway in intersecting_highways:
            buffers.append(highway.geometry.buffer(parameters.OWBB_CITY_BLOCK_HIGHWAY_BUFFER,
                                                   cap_style=CAP_STYLE.square,
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

    merged_polygons = merge_buffers(buffered_polygons)

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


def _process_landuse_for_settlement_areas(lit_areas: List[Polygon], water_areas: List[Polygon]) -> List[Polygon]:
    """Combines lit areas with water areas to get a proxy for settlement areas"""
    all_areas = lit_areas + water_areas
    return merge_buffers(all_areas)


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
        if highway.type_ in [wbb.HIGHWAYS_FOR_ZONE_SPLIT] and not highway.is_tunnel:
            line_buffers.append(highway.geometry.buffer(highway.get_width()/2))

    for railway in railways.values():
        if railway.type_ in [m.RailwayLineType.rail, m.RailwayLineType.light_rail, m.RailwayLineType.subway,
                             m.RailwayLineType.narrow_gauge] and not (railway.is_tunnel or railway.is_service_spur):
            line_buffers.append(railway.geometry.buffer(railway.get_width() / 2))

    for waterway in waterways.values():
        if waterway.type_ is m.WaterwayType.large:
            line_buffers.append(waterway.geometry.buffer(10))

    merged_buffers = merge_buffers(line_buffers)
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


def _fetch_water_areas(transformer: Transformation) -> List[Polygon]:
    """Fetches specific water areas from OSM and then applies a buffer."""
    water_areas = list()

    # get riverbanks from relations
    osm_relations_result = op.fetch_osm_db_data_relations_riverbanks(op.OSMReadResult(dict(), dict(), dict(), dict(),
                                                                                      dict()))
    osm_relations_dict = osm_relations_result.relations_dict
    osm_nodes_dict = osm_relations_result.rel_nodes_dict
    osm_rel_ways_dict = osm_relations_result.rel_ways_dict

    for _, relation in osm_relations_dict.items():
        outer_ways = list()
        for member in relation.members:
            if member.type_ == 'way' and member.role == 'outer' and member.ref in osm_rel_ways_dict:
                way = osm_rel_ways_dict[member.ref]
                outer_ways.append(way)

        outer_ways = op.closed_ways_from_multiple_ways(outer_ways)
        for way in outer_ways:
            polygon = way.polygon_from_osm_way(osm_nodes_dict, transformer)
            if polygon.is_valid and not polygon.is_empty:
                water_areas.append(polygon.buffer(parameters.OWBB_BUILT_UP_BUFFER))

    # then add water areas (mostly when natural=water, but not always consistent
    osm_way_result = op.fetch_osm_db_data_ways_key_values(['water=>moat', 'water=>river', 'water=>canal',
                                                           'waterway=>riverbank'])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict
    for key, way in osm_ways_dict.items():
        my_geometry = way.polygon_from_osm_way(osm_nodes_dict, transformer)
        if my_geometry is not None and isinstance(my_geometry, Polygon):
            if my_geometry.is_valid and not my_geometry.is_empty:
                water_areas.append(my_geometry.buffer(parameters.OWBB_BUILT_UP_BUFFER))

    logging.info('Fetched %i water areas from OSM', len(water_areas))
    return water_areas


def _create_settlement_clusters(lit_areas: List[Polygon], water_areas: List[Polygon],
                                urban_places: List[m.Place]) -> List[m.SettlementCluster]:
    clusters = list()

    candidate_settlements = _process_landuse_for_settlement_areas(lit_areas, water_areas)
    for polygon in candidate_settlements:
        candidate_places = list()
        towns = 0
        cities = 0
        for place in urban_places:
            centre_circle, block_circle, dense_circle = place.create_settlement_type_circles()
            if not dense_circle.disjoint(polygon):
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
    """As the name says. Plus also creates city blocks.
    A building zone can only be in one settlement cluster.
    Per default a building zone has SettlementType = rural."""
    zones_processed_in_settlement = list()
    x = 0
    x_number = len(settlement_clusters)
    for settlement in settlement_clusters:
        x += 1
        logging.info('Processing %i out of %i settlement clusters', x, x_number)
        # create the settlement type circles
        centre_circles = list()
        block_circles = list()
        dense_circles = list()
        for place in settlement.linked_places:
            centre_circle, block_circle, dense_circle = place.create_settlement_type_circles()
            if not centre_circle.is_empty:
                centre_circles.append(centre_circle)
            if not block_circle.is_empty:
                block_circles.append(block_circle)
            dense_circles.append(dense_circle)
        z = 0
        z_number = len(building_zones)
        for zone in building_zones:
            if zone.type_ is m.BuildingZoneType.aerodrome:
                continue
            z += 1
            if z % 20 == 0:
                logging.debug('Processing %i out of %i building_zones', z, z_number)
            if zone not in zones_processed_in_settlement:
                # using "within" instead of "intersect" because lit-areas are always larger than zones due to buffering
                # and therefore a zone can always only be within one lit-area/settlement and not another
                if zone.geometry.within(settlement.geometry):
                    zones_processed_in_settlement.append(zone)
                    zone.settlement_type = bl.SettlementType.periphery
                    # create city blocks
                    _assign_city_blocks(zone, highways_dict)
                    # Test for being within a settlement type circle beginning with the highest ranking circles.
                    # Make sure not to overwrite higher rankings, if already set from different cluster
                    # If yes, then assign settlement type to city block
                    for city_block in zone.linked_city_blocks:
                        prep_geom = prep(city_block.geometry)
                        if city_block.settlement_type.value < bl.SettlementType.centre.value:
                            for circle in centre_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = bl.SettlementType.centre
                                    zone.settlement_type = bl.SettlementType.centre
                                    break
                        if city_block.settlement_type.value < bl.SettlementType.block.value:
                            for circle in block_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = bl.SettlementType.block
                                    zone.settlement_type = bl.SettlementType.block
                                    break
                        if city_block.settlement_type.value < bl.SettlementType.dense.value:
                            for circle in dense_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = bl.SettlementType.dense
                                    zone.settlement_type = bl.SettlementType.dense
                                    break

    # now make sure that also zones outside of settlements get city blocks
    for zone in building_zones:
        if zone not in zones_processed_in_settlement and zone.type_ is not m.BuildingZoneType.aerodrome:
            _assign_city_blocks(zone, highways_dict)


def _sanity_check_settlement_types(building_zones: List[m.BuildingZone], highways_dict: Dict[int, m.Highway]) -> None:
    upgraded = 0
    downgraded = 0
    for zone in building_zones:
        if zone.type_ is m.BuildingZoneType.aerodrome:
            continue
        my_density = zone.density
        if my_density < parameters.OWBB_PLACE_SANITY_DENSITY:
            if zone.settlement_type in [bl.SettlementType.dense, bl.SettlementType.block]:
                zone.settlement_type = bl.SettlementType.periphery
                downgraded += 1
                for city_block in zone.linked_city_blocks:
                    city_block.settlement_type = bl.SettlementType.periphery
                    city_block.settlement_type_changed = True
        else:
            if zone.settlement_type in [bl.SettlementType.rural, bl.SettlementType.periphery]:
                zone.settlement_type = bl.SettlementType.dense
                upgraded += 1
                # now also make sure we actually have city blocks
                _assign_city_blocks(zone, highways_dict)
                for city_block in zone.linked_city_blocks:
                    city_block.settlement_type = bl.SettlementType.dense
                    city_block.settlement_type_changed = True
    logging.debug('Upgraded %i and downgraded %i settlement types for %i total building zones', upgraded, downgraded,
                  len(building_zones))


def _check_clipping_border(building_zones: List[m.BuildingZone], bounds: m.Bounds) -> List[m.BuildingZone]:
    kept_zones = list()
    clipping_border = box(bounds.min_point.x, bounds.min_point.y, bounds.max_point.x, bounds.max_point.y)
    for zone in building_zones:
        if zone.geometry.within(clipping_border):
            kept_zones.append(zone)
        else:
            clipped_geometry = clipping_border.intersection(zone.geometry)
            if isinstance(clipped_geometry, Polygon) and clipped_geometry.is_valid and not clipped_geometry.is_empty:
                zone.geometry = clipped_geometry
            else:
                # warn about it, but also keep it as is
                logging.warning('Building zone %i could not be clipped to boundary', zone.osm_id)
            # for now we keep them all
            kept_zones.append(zone)
    return kept_zones


def _count_zones_related_buildings(buildings: List[bl.Building], text: str, check_block: bool = False) -> None:
    total_related = 0
    total_not_block = 0

    for building in buildings:
        if building.zone:
            total_related += 1
            if check_block and not isinstance(building.zone, m.CityBlock):
                total_not_block += 1
                logging.debug('type = %s, settlement type = %s', building.zone, building.zone.settlement_type)
        else:
            raise SystemExit('Building with osm_id=%d has no associated zone - %s', building.osm_id, text)

    logging.info('%i out of %i buildings are related to zone %s - %i not in block', total_related, len(buildings),
                 text, total_not_block)


def _sanitize_building_zones(building_zones: List[m.BuildingZone], text: str) -> None:
    """Make sure that the geometry of the BuildingZones is valid."""
    number_deleted = 0
    for zone in reversed(building_zones):
        if zone.geometry is None:
            logging.info('Geometry is None')
        elif not zone.geometry.is_valid:
            logging.info('Geometry is not valid')
        elif zone.geometry.is_empty:
            logging.info('Geometry is not valid')
        elif len(zone.geometry.bounds) < 4:
            logging.info('Bounds is only len %i', len(zone.geometry.bounds))
        else:
            continue
        # now collect info
        logging.info('REMOVED: type = %s, osm_id = %i, buildings = %i', zone, zone.osm_id, len(zone.osm_buildings))
        building_zones.remove(zone)
        number_deleted += 1
    logging.info('Sanitize %s has deleted %i building zones', text, number_deleted)


def process(transformer: Transformation, airports: List[aptdat_io.Airport]) -> Tuple[Optional[List[Polygon]],
                                                                                     Optional[List[bl.Building]]]:
    last_time = time.time()

    bounds = m.Bounds.create_from_parameters(transformer)

    # =========== TRY TO READ CACHED DATA FIRST =======
    tile_index = parameters.get_tile_index()
    cache_file_la = str(tile_index) + '_lit_areas.pkl'
    cache_file_bz = str(tile_index) + '_buildings.pkl'
    if parameters.OWBB_LANDUSE_CACHE:
        try:
            with open(cache_file_la, 'rb') as file_pickle:
                lit_areas = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(lit_areas), cache_file_la)

            with open(cache_file_bz, 'rb') as file_pickle:
                osm_buildings = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(osm_buildings), cache_file_bz)
            return lit_areas, osm_buildings
        except (IOError, EOFError) as reason:
            logging.info("Loading of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    # =========== READ OSM DATA =============
    aerodrome_zones = m.process_aerodrome_refs(transformer)
    building_zones = m.process_osm_building_zone_refs(transformer)
    urban_places, farm_places = m.process_osm_place_refs(transformer)
    osm_buildings = bu.construct_buildings_from_osm(transformer)
    highways_dict = m.process_osm_highway_refs(transformer)
    railways_dict = m.process_osm_railway_refs(transformer)
    waterways_dict = m.process_osm_waterway_refs(transformer)
    water_areas = _fetch_water_areas(transformer)

    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    # =========== PROCESS AERODROME INFORMATION ============================
    _process_aerodromes(building_zones, aerodrome_zones, airports, transformer)
    last_time = time_logging("Time used in seconds for processing aerodromes", last_time)

    # =========== READ LAND-USE DATA FROM FLIGHTGEAR BTG-FILES =============
    btg_building_zones = list()
    if parameters.OWBB_USE_BTG_LANDUSE:
        btg_building_zones = _process_btg_building_zones(transformer)
        last_time = time_logging("Time used in seconds for reading BTG zones", last_time)

    if len(btg_building_zones) > 0:
        _generate_building_zones_from_external(building_zones, btg_building_zones)
    last_time = time_logging("Time used in seconds for processing external zones", last_time)

    # =========== CHECK WHETHER WE ARE IN A BUILT-UP AREA AT ALL ===========================
    if len(building_zones) == 0 and len(osm_buildings) == 0 and len(highways_dict) == 0 and len(railways_dict) == 0:
        logging.info('No zones, buildings and highways/railways in tile = %i', tile_index)
        # there is no need to save a cache, so just do nothing
        return None, None

    # =========== GENERATE ADDITIONAL LAND-USE ZONES FOR AND/OR FROM BUILDINGS =============
    buildings_outside = list()  # buildings outside of OSM buildings zones
    for candidate in osm_buildings:
        found = False
        for building_zone in building_zones:
            if candidate.geometry.within(building_zone.geometry) or candidate.geometry.intersects(
                    building_zone.geometry):
                building_zone.relate_building(candidate)
                found = True
                break
        if not found:
            buildings_outside.append(candidate)
    last_time = time_logging("Time used in seconds for assigning buildings to OSM zones", last_time)

    _generate_building_zones_from_buildings(building_zones, buildings_outside)
    del buildings_outside
    last_time = time_logging("Time used in seconds for generating building zones", last_time)

    _count_zones_related_buildings(osm_buildings, 'after generating zones from buildings')

    # =========== CREATE POLYGONS FOR LIGHTING OF STREETS ================================
    # Needs to be before finding city blocks as we need the boundary
    lit_areas = _process_landuse_for_lighting(building_zones)
    last_time = time_logging("Time used in seconds for finding lit areas", last_time)

    _count_zones_related_buildings(osm_buildings, 'after lighting')

    # =========== REDUCE THE BUILDING_ZONES TO BE WITHIN BOUNDS ==========================
    # This is needed such that no additional buildings would be generated outside of the tile boundary.
    building_zones = _check_clipping_border(building_zones, bounds)
    last_time = time_logging("Time used in seconds for clipping to boundary", last_time)

    # =========== MAKE SURE GENERATED LAND-USE DOES NOT CROSS MAJOR LINEAR OBJECTS =======
    if parameters.OWBB_SPLIT_MADE_UP_LANDUSE_BY_MAJOR_LINES:
        # finally split generated zones by major transport lines
        building_zones = _split_generated_building_zones_by_major_lines(building_zones, highways_dict,
                                                                        railways_dict, waterways_dict)
    last_time = time_logging("Time used in seconds for splitting building zones by major lines", last_time)

    _count_zones_related_buildings(osm_buildings, 'after split major lines')
    _sanitize_building_zones(building_zones, 'after split major lines')

    # =========== Link urban places with settlement_area buffers ==================================
    settlement_clusters = _create_settlement_clusters(lit_areas, water_areas, urban_places)
    last_time = time_logging('Time used in seconds for creating settlement_clusters', last_time)

    _count_zones_related_buildings(osm_buildings, 'after settlement clusters')

    _link_building_zones_with_settlements(settlement_clusters, building_zones, highways_dict)
    last_time = time_logging('Time used in seconds for linking building zones with settlement_clusters', last_time)

    if parameters.OWBB_PLACE_CHECK_DENSITY:
        _sanity_check_settlement_types(building_zones, highways_dict)
        last_time = time_logging('Time used in seconds for sanity checking settlement types', last_time)

    _count_zones_related_buildings(osm_buildings, 'after settlement linking', True)

    # now that settlement areas etc. are done, we can reduce the lit areas to those having a minimum area
    before_lit = len(lit_areas)
    for lit_area in reversed(lit_areas):
        if lit_area.area < parameters.OWBB_BUILT_UP_MIN_LIT_AREA:
            lit_areas.remove(lit_area)
    logging.info('Reduced the number of lit areas from %i to %i.', before_lit, len(lit_areas))

    # ============ Finally guess the land-use type ========================================
    for my_zone in building_zones:
        if isinstance(my_zone, m.GeneratedBuildingZone):
            my_zone.guess_building_zone_type(farm_places)
    last_time = time_logging("Time used in seconds for guessing zone types", last_time)

    # =========== FINALIZE Land-use PROCESSING =============================================
    if parameters.DEBUG_PLOT_LANDUSE:
        logging.info('Start of plotting zones')
        plotting.draw_zones(osm_buildings, building_zones, btg_building_zones, lit_areas, bounds)
        time_logging("Time used in seconds for plotting", last_time)

    # =========== Now generate buildings if asked for ======================================
    if parameters.OWBB_GENERATE_BUILDINGS:
        generated_buildings = wbb.process(transformer, building_zones, highways_dict, railways_dict,
                                          waterways_dict)
        osm_buildings.extend(generated_buildings)

    _count_zones_related_buildings(osm_buildings, 'after generating buildings')

    # =========== WRITE TO CACHE AND RETURN
    if parameters.OWBB_LANDUSE_CACHE:
        try:

            with open(cache_file_la, 'wb') as file_pickle:
                pickle.dump(lit_areas, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(lit_areas), cache_file_la)

            with open(cache_file_bz, 'wb') as file_pickle:
                pickle.dump(osm_buildings, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(osm_buildings), cache_file_bz)
        except (IOError, EOFError) as reason:
            logging.info("Saving of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    return lit_areas, osm_buildings
