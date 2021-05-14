# -*- coding: utf-8 -*-
"""Handles land-use related stuff, especially generating new land-use where OSM data is not sufficient.
"""

import logging
import math
import pickle
import time
from typing import Dict, List, Optional, Tuple

from shapely.geometry import box, LineString, MultiPolygon, Polygon, CAP_STYLE, JOIN_STYLE
from shapely.ops import unary_union
from shapely.prepared import prep

import osm2city.static_types.enumerations as enu
from osm2city import building_lib as bl
from osm2city import buildings as bu
from osm2city.owbb import models as m
import osm2city.owbb.plotting as plotting
import osm2city.owbb.would_be_buildings as wbb
import osm2city.parameters as parameters
import osm2city.static_types.osmstrings as s
import osm2city.utils.aptdat_io as aptdat_io
import osm2city.utils.btg_io as btg
import osm2city.utils.osmparser as op

from osm2city.utils.coordinates import disjoint_bounds, Transformation
from osm2city.utils.utilities import time_logging, merge_buffers


class GridHighway:
    """A Highway optimized for handling grid_indices for faster geometric comparison."""
    __slots__ = ('geometry', 'grid_indices')

    def __init__(self, geometry: LineString) -> None:
        self.geometry = geometry
        self.grid_indices = set()


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
                                            poly, enu.BuildingZoneType.aerodrome)
        aerodrome_zones.append(new_aerodrome_zone)

    # make sure that if a building zone is overlapping with a aerodrome that it is clipped
    for building_zone in building_zones:
        for aerodrome_zone in aerodrome_zones:
            if building_zone.geometry.disjoint(aerodrome_zone.geometry) is False:
                building_zone.geometry = building_zone.geometry.difference(aerodrome_zone.geometry)

    # finally add all aerodrome_zones to the building_zones as regular zone
    building_zones.extend(aerodrome_zones)


def _reduce_building_zones_with_btg_water(building_zones: List[m.BuildingZone], btg_water_areas: List[Polygon]) -> None:
    """Adds "missing" building_zones based on land-use info outside of OSM land-use"""
    counter = 0
    for water_area in btg_water_areas:
        prep_geom = prep(water_area)

        parts = list()
        for building_zone in reversed(building_zones):
            if prep_geom.contains_properly(building_zone.geometry):
                counter += 1
                building_zones.remove(building_zone)
            elif prep_geom.intersects(building_zone.geometry):
                counter += 1
                diff = building_zone.geometry.difference(water_area)
                if isinstance(diff, Polygon):
                    if diff.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
                        building_zone.geometry = diff
                    else:
                        building_zones.remove(building_zone)
                elif isinstance(diff, MultiPolygon):
                    building_zones.remove(building_zone)
                    is_first = True
                    for poly in diff:
                        if poly.area >= parameters.OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA:
                            if is_first:
                                building_zone.geometry = poly
                                parts.append(building_zone)
                                is_first = False
                            else:
                                new_zone = m.BuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse), poly,
                                                          building_zone.type_)
                                parts.append(new_zone)
        building_zones.extend(parts)

    logging.info("Corrected %i building zones with BTG water areas", counter)


def _extend_osm_building_zones_with_btg_zones(building_zones: List[m.BuildingZone],
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
            factor = math.sqrt(my_building.area / parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE ** 2)
            buffer_distance = min(factor * parameters.OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE,
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
                                                   buffer_polygon, enu.BuildingZoneType.non_osm)
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
            my_building.zone = None
            for my_split_generated in new_generated:
                if my_building.geometry.intersects(my_split_generated.geometry):
                    my_split_generated.relate_building(my_building)
                    break
            if my_building.zone is None:  # maybe no intersection -> fall back as each building needs a zone
                new_generated[0].relate_building(my_building)
        for my_split_generated in new_generated:
            if my_split_generated.from_buildings and len(my_split_generated.osm_buildings) == 0:
                continue
            split_zones.append(my_split_generated)
            logging.debug("Added sub-polygon with area %d and %d buildings", my_split_generated.geometry.area,
                          len(my_split_generated.osm_buildings))
    else:
        split_zones.append(zone)
    return split_zones


def _create_btg_buildings_zones(btg_polys: Dict[str, List[Polygon]]) -> List[m.BTGBuildingZone]:
    btg_zones = list()

    for key, polys in btg_polys.items():
        # find the corresponding BuildingZoneType
        type_ = None
        for member in enu.BuildingZoneType:
            btg_key = 'btg_' + key
            if btg_key == member.name:
                type_ = member
                break
        if type_ is None:
            raise Exception('Unknown BTG material: {}. Most probably a programming mismatch.'.format(key))

        for poly in polys:
            my_zone = m.BTGBuildingZone(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse),
                                        type_, poly)
            btg_zones.append(my_zone)

    logging.debug('Created a total of %i zones from BTG', len(btg_zones))
    return btg_zones


def _merge_btg_transport_in_water(water_polys: Dict[str, List[Polygon]],
                                  transport_polys: Dict[str, List[Polygon]]) -> List[Polygon]:
    """Tests whether a BTG transport face intersects mostly with water and merges as many as possible.

    This amongst others to prevent that probing for water would find a non-water place - just because the land-use
    is actually transport from a bridge.

    Not merging the geometries across materials in order to keep the polygons' geometry simple.
    """
    # get all water (Italian = acqua) polygons into one list - after processing we are not interested
    # in the specific materials anymore
    acqua_list = list()
    for poly_list in water_polys.values():
        for poly in poly_list:
            acqua_list.append(poly)

    # get all faces of different transport materials into on list of prepared geometries
    for poly_list in transport_polys.values():
        for poly in poly_list:
            prep_poly = prep(poly)

            merged_poly = None
            acqua_poly = None
            for acqua_poly in acqua_list:
                if prep_poly.intersects(acqua_poly):
                    geom = acqua_poly.intersection(poly)
                    if isinstance(geom, LineString):
                        merged_poly = acqua_poly.union(poly)
                        break
            if merged_poly:
                acqua_list.remove(acqua_poly)
                acqua_list.append(merged_poly)
    return acqua_list


def _remove_osm_buildings_in_water(osm_buildings: List[bl.Building], btg_water_areas: List[Polygon]) -> None:
    counter = 0
    for water_area in btg_water_areas:
        prep_geom = prep(water_area)
        for building in reversed(osm_buildings):
            if prep_geom.contains_properly(building.geometry) or prep_geom.intersects(building.geometry):
                counter += 1
                osm_buildings.remove(building)
                if building.has_parent:
                    parent = building.parent
                    parent.make_sure_lone_building_in_parent_stands_alone()
                break
    logging.info('Removed %i buildings based on BTG water', counter)


def _test_highway_intersecting_area(area: Polygon, highways_dict: Dict[int, m.Highway]) -> List[LineString]:
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
                linked_highways.append(my_highway.geometry)
                to_be_removed.append(my_highway.osm_id)

            elif prep_area.intersects(my_highway.geometry):
                linked_highways.append(my_highway.geometry)

    for key in to_be_removed:
        del highways_dict[key]

    return linked_highways


def _test_highway_intersection_area(building_zone: m.BuildingZone,
                                    grid_highways: List[GridHighway]) -> List[LineString]:
    """Returns highways that are within a building_zone or intersecting with a building_zone.

    Highways_dict gets reduced by those highways, which were within, such that searching in other
    areas gets quicker due to reduced volume.
    """
    prep_area = prep(building_zone.geometry)
    linked_highways = list()
    for grid_highway in grid_highways:
        if grid_highway.grid_indices.intersection(building_zone.grid_indices):
            if prep_area.contains_properly(grid_highway.geometry) or prep_area.intersects(grid_highway.geometry):
                linked_highways.append(grid_highway.geometry)
    return linked_highways


def _assign_city_blocks(building_zone: m.BuildingZone, highways_dict: Dict[int, m.Highway],
                        grid_highways: Optional[List[GridHighway]]) -> None:
    """Splits the land-use into (city) blocks, i.e. areas surrounded by streets.
    Brute force by buffering all highways, then take the geometry difference, which splits the zone into
    multiple polygons. Some of the polygons will be real city blocks, others will be border areas.

    Could also be done by using e.g. networkx.algorithms.cycles.cycle_basis.html. However is a bit more complicated
    logic and programming wise, but might be faster.
    """
    building_zone.reset_city_blocks()
    highways_dict_copy1 = highways_dict.copy()  # otherwise when using highways_dict in plotting it will be "used"

    polygons = list()
    if grid_highways:
        intersecting_highways = _test_highway_intersection_area(building_zone, grid_highways)
    else:
        intersecting_highways = _test_highway_intersecting_area(building_zone.geometry, highways_dict_copy1)
    if intersecting_highways:
        buffers = list()
        for highway_geometry in intersecting_highways:
            buffers.append(highway_geometry.buffer(parameters.OWBB_CITY_BLOCK_HIGHWAY_BUFFER,
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
        my_city_block.settlement_type = building_zone.settlement_type

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


def _process_landuse_for_settlement_areas(lit_areas: List[Polygon], osm_water_areas: List[Polygon]) -> List[Polygon]:
    """Combines lit areas with water areas to get a proxy for settlement areas"""
    all_areas = lit_areas + osm_water_areas
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


def _fetch_osm_water_areas(transformer: Transformation) -> List[Polygon]:
    """Fetches specific water areas from OSM and then applies a buffer."""
    osm_water_areas = list()

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
                osm_water_areas.append(polygon.buffer(parameters.OWBB_BUILT_UP_BUFFER))

    # then add water areas (mostly when natural=water, but not always consistent
    osm_way_result = op.fetch_osm_db_data_ways_key_values(['water=>moat', 'water=>river', 'water=>canal',
                                                           'waterway=>riverbank'])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict
    for key, way in osm_ways_dict.items():
        my_geometry = way.polygon_from_osm_way(osm_nodes_dict, transformer)
        if my_geometry is not None and isinstance(my_geometry, Polygon):
            if my_geometry.is_valid and not my_geometry.is_empty:
                osm_water_areas.append(my_geometry.buffer(parameters.OWBB_BUILT_UP_BUFFER))

    logging.info('Fetched %i water areas from OSM', len(osm_water_areas))
    return osm_water_areas


def _create_settlement_clusters(lit_areas: List[Polygon], osm_water_areas: List[Polygon],
                                urban_places: List[m.Place]) -> List[m.SettlementCluster]:
    """Settlement clusters based lit areas and specific water areas.

    The reason for using specific water areas is that in cities with much water (e.g. Stockholm) otherwise
    the parts of the city would get too isolated and less density - often there is only one clear city center
    from OSM data, but the city stretches longer.
    The reason to use OSM water data instead of BTG data is that the OSM data has better tagging."""
    clusters = list()

    candidate_settlements = _process_landuse_for_settlement_areas(lit_areas, osm_water_areas)
    for polygon in candidate_settlements:
        candidate_places = list()
        towns = 0
        cities = 0
        for place in urban_places:
            centre_circle, block_circle, dense_circle = place.create_settlement_type_circles()
            if not dense_circle.disjoint(polygon):
                candidate_places.append(place)
                if place.type_ is enu.PlaceType.city:
                    cities += 1
                else:
                    towns += 1
        if candidate_places:
            logging.debug('New settlement cluster with %i cities and %i towns', cities, towns)
            clusters.append(m.SettlementCluster(candidate_places, polygon))
    return clusters


def _create_clusters_of_settlements(lit_areas: List[Polygon], osm_water_areas: List[Polygon],
                                    dense_circles: List[m.PreparedSettlementTypePoly]) -> List[m.SettlementCluster]:
    """Settlement clusters based lit areas and specific water areas.

    The reason for using specific water areas is that in cities with much water (e.g. Stockholm) otherwise
    the parts of the city would get too isolated and less density - often there is only one clear city center
    from OSM data, but the city stretches longer.
    The reason to use OSM water data instead of BTG data is that the OSM data has better tagging."""
    clusters = list()

    candidate_settlements = _process_landuse_for_settlement_areas(lit_areas, osm_water_areas)
    for polygon in candidate_settlements:
        candidate_places = list()
        for dense_circle in dense_circles:
            if not dense_circle.geometry.disjoint(polygon):
                clusters.append(m.SettlementCluster(candidate_places, polygon))
    return clusters


def _assign_grid_indices(building_zones: List[m.BuildingZone], settlement_clusters: List[m.SettlementCluster],
                         centre_circles: List[m.PreparedSettlementTypePoly],
                         block_circles: List[m.PreparedSettlementTypePoly],
                         dense_circles: List[m.PreparedSettlementTypePoly],
                         grid_highways: List[GridHighway],
                         transformer: Transformation) -> None:
    """Based on a grid assign the objects those grid indices, which the intersect with.
    Is used to do some fast filtering / partitioning, such that fewer slower geometric tests need to be done."""
    min_point, max_point = parameters.get_extent_local(transformer)
    delta = max_point - min_point  # Vec2d
    grids_x = int(delta.x / parameters.OWBB_GRID_SIZE) + 1
    grids_y = int(delta.y / parameters.OWBB_GRID_SIZE) + 1
    index = 0
    for x in range(grids_x):
        for y in range(grids_y):
            index += 1
            my_box = box(min_point.x + x * parameters.OWBB_GRID_SIZE,
                         min_point.y + y * parameters.OWBB_GRID_SIZE,
                         min_point.x + (x+1) * parameters.OWBB_GRID_SIZE,
                         min_point.y + (y+1) * parameters.OWBB_GRID_SIZE)
            for building_zone in building_zones:
                if not my_box.disjoint(building_zone.geometry):
                    building_zone.grid_indices.add(index)
            for settlement_cluster in settlement_clusters:
                if not my_box.disjoint(settlement_cluster.geometry):
                    settlement_cluster.grid_indices.add(index)
            for circle in centre_circles:
                if not my_box.disjoint(circle.geometry):
                    circle.grid_indices.add(index)
            for circle in block_circles:
                if not my_box.disjoint(circle.geometry):
                    circle.grid_indices.add(index)
            for circle in dense_circles:
                if not my_box.disjoint(circle.geometry):
                    circle.grid_indices.add(index)
            for grid_highway in grid_highways:
                if not my_box.disjoint(grid_highway.geometry):
                    grid_highway.grid_indices.add(index)


def _assign_minimum_settlement_type_to_zones(building_zones: List[m.BuildingZone],
                                             settlement_clusters: List[m.SettlementCluster]) -> None:
    """Assign settlement type periphery to zones if they belong to a settlement cluster.
    Otherwise they remain rural as default."""
    for zone in building_zones:
        if zone.is_aerodrome:
            continue
        for settlement in settlement_clusters:
            if zone.grid_indices.intersection(settlement.grid_indices):  # it makes sense to do a computational test
                if zone.geometry.within(settlement.geometry):  # due to lighting buffer a zone is always within or not
                    zone.set_max_settlement_type(enu.SettlementType.periphery)
                    break


def _assign_city_blocks_to_zones(building_zones: List[m.BuildingZone], highways_dict: Dict[int, m.Highway],
                                 grid_highways: List[GridHighway]) -> None:
    for zone in building_zones:
        if not zone.is_aerodrome:
            _assign_city_blocks(zone, highways_dict, grid_highways)


def _assign_urban_settlement_type(building_zones: List[m.BuildingZone], current_settlement_type: enu.SettlementType,
                                  urban_settlements: List[m.PreparedSettlementTypePoly]) -> None:
    """Assign a urban (centre, block, dense) settlement type to a zone, if the zone is within or intersects."""
    for urban_settlement in urban_settlements:
        for zone in building_zones:
            if zone.is_aerodrome:
                continue
            elif zone.settlement_type is enu.SettlementType.rural:
                continue
            if zone.grid_indices.intersection(urban_settlement.grid_indices):
                if urban_settlement.prep_poly.contains(zone.geometry) or urban_settlement.prep_poly.intersects(
                        zone.geometry):
                    zone.set_max_settlement_type(current_settlement_type)
                    for city_block in zone.linked_city_blocks:
                        if city_block.settlement_type.value < current_settlement_type:
                            if urban_settlement.prep_poly.contains(city_block.geometry) or (
                                    urban_settlement.prep_poly.intersects(city_block.geometry)):
                                city_block.settlement_type = current_settlement_type


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
            z += 1
            if z % 20 == 0:
                logging.debug('Processing %i out of %i building_zones', z, z_number)
            if zone.type_ is enu.BuildingZoneType.aerodrome:
                continue

            if zone not in zones_processed_in_settlement:
                # using "within" instead of "intersect" because lit-areas are always larger than zones due to buffering
                # and therefore a zone can always only be within one lit-area/settlement and not another
                if zone.geometry.within(settlement.geometry):
                    zones_processed_in_settlement.append(zone)
                    zone.set_max_settlement_type(enu.SettlementType.periphery)
                    # create city blocks
                    _assign_city_blocks(zone, highways_dict, None)
                    # Test for being within a settlement type circle beginning with the highest ranking circles.
                    # Make sure not to overwrite higher rankings, if already set from different cluster
                    # If yes, then assign settlement type to city block
                    for city_block in zone.linked_city_blocks:
                        prep_geom = prep(city_block.geometry)
                        if city_block.settlement_type.value < enu.SettlementType.centre.value:
                            for circle in centre_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = enu.SettlementType.centre
                                    zone.set_max_settlement_type(enu.SettlementType.centre)
                                    break
                        if city_block.settlement_type.value < enu.SettlementType.block.value:
                            for circle in block_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = enu.SettlementType.block
                                    zone.set_max_settlement_type(enu.SettlementType.block)
                                    break
                        if city_block.settlement_type.value < enu.SettlementType.dense.value:
                            for circle in dense_circles:
                                if prep_geom.intersects(circle):
                                    city_block.settlement_type = enu.SettlementType.dense
                                    zone.set_max_settlement_type(enu.SettlementType.dense)
                                    break

    # now make sure that also zones outside of settlements get city blocks
    for zone in building_zones:
        if zone not in zones_processed_in_settlement and zone.type_ is not enu.BuildingZoneType.aerodrome:
            _assign_city_blocks(zone, highways_dict, None)


def _sanity_check_settlement_types(building_zones: List[m.BuildingZone], highways_dict: Dict[int, m.Highway],
                                   grid_highways: Optional[List[GridHighway]]) -> None:
    upgraded = 0
    downgraded = 0
    for zone in building_zones:
        if zone.type_ is enu.BuildingZoneType.aerodrome:
            continue
        my_density = zone.density
        if my_density < parameters.OWBB_PLACE_SANITY_DENSITY:
            if zone.settlement_type in [enu.SettlementType.dense, enu.SettlementType.block]:
                zone.settlement_type = enu.SettlementType.periphery
                downgraded += 1
                for city_block in zone.linked_city_blocks:
                    city_block.settlement_type = enu.SettlementType.periphery
        else:  # we are at parameters.OWBB_PLACE_SANITY_DENSITY
            if zone.settlement_type in [enu.SettlementType.rural, enu.SettlementType.periphery]:
                zone.settlement_type = enu.SettlementType.dense
                upgraded += 1
                # now also make sure we actually have city blocks
                _assign_city_blocks(zone, highways_dict, grid_highways)
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

    for building in reversed(buildings):
        if building.zone:
            total_related += 1
            if check_block and not isinstance(building.zone, m.CityBlock):
                total_not_block += 1
                logging.debug('type = %s, settlement type = %s', building.zone, building.zone.settlement_type)
            if isinstance(building.zone.geometry, MultiPolygon):
                logging.warning('Building with osm_id=%i has MultiPolygon of type = %s, zone osm_id = %i - %s',
                                building.osm_id, building.zone.type_.name, building.zone.osm_id, text)
                building.zone.geometry = building.zone.geometry.geoms[0]  # just use the first polygon
        else:
            logging.warning('Building with osm_id=%i has no associated zone - %s', building.osm_id, text)
            buildings.remove(building)  # make sure we do not get conflicts

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
    logging.info('Sanitize %s has deleted %i building zones. Now there are %i building zones',
                 text, number_deleted, len(building_zones))


def _relate_neighbours(buildings: List[bl.Building]) -> None:
    """Relates neighbour buildings based on shared references."""
    neighbours = 0
    len_buildings = len(buildings)
    for i, first_building in enumerate(buildings, 1):
        if i % 10000 == 0:
            logging.info('Checked building relations for %i out of %i buildings', i, len_buildings)
        potential_attached = first_building.zone.osm_buildings
        ref_set_first = set(first_building.refs)
        for second_building in potential_attached:
            if first_building.osm_id == second_building.osm_id:  # do not compare with self
                continue
            ref_set_second = set(second_building.refs)
            if ref_set_first.isdisjoint(ref_set_second) is False:
                for pos_i in range(len(first_building.refs)):
                    for pos_j in range(len(second_building.refs)):
                        if first_building.refs[pos_i] == second_building.refs[pos_j]:
                            if second_building not in first_building.refs_shared:
                                first_building.refs_shared[second_building] = set()
                            first_building.refs_shared[second_building].add(pos_i)
                            if first_building not in second_building.refs_shared:
                                second_building.refs_shared[first_building] = set()
                            second_building.refs_shared[first_building].add(pos_j)

    for b in buildings:
        if b.has_neighbours:
            neighbours += 1
    logging.info('%i out of %i buildings have neighbour relations ', neighbours, len(buildings))


def process(transformer: Transformation, airports: List[aptdat_io.Airport]) -> Tuple[Optional[List[Polygon]],
                                                                                     Optional[List[Polygon]],
                                                                                     Optional[List[bl.Building]]]:
    last_time = time.time()

    bounds = m.Bounds.create_from_parameters(transformer)

    # =========== TRY TO READ CACHED DATA FIRST =======
    tile_index = parameters.get_tile_index()
    cache_file_la = str(tile_index) + '_lit_areas.pkl'
    cache_file_wa = str(tile_index) + '_water_areas.pkl'
    cache_file_bz = str(tile_index) + '_buildings.pkl'
    if parameters.OWBB_LANDUSE_CACHE:
        try:
            with open(cache_file_la, 'rb') as file_pickle:
                lit_areas = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(lit_areas), cache_file_la)

            with open(cache_file_wa, 'rb') as file_pickle:
                water_areas = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(water_areas), cache_file_wa)

            with open(cache_file_bz, 'rb') as file_pickle:
                osm_buildings = pickle.load(file_pickle)
            logging.info('Successfully loaded %i objects from %s', len(osm_buildings), cache_file_bz)
            return lit_areas, water_areas, osm_buildings
        except (IOError, EOFError) as reason:
            logging.info("Loading of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    # =========== READ OSM DATA =============
    aerodrome_zones = m.process_aerodrome_refs(transformer)
    building_zones = m.process_osm_building_zone_refs(transformer)
    urban_places, farm_places = m.process_osm_place_refs(transformer)
    osm_buildings, building_nodes_dict = bu.construct_buildings_from_osm(transformer)
    highways_dict = m.process_osm_highway_refs(transformer)
    railways_dict = m.process_osm_railway_refs(transformer)
    waterways_dict = m.process_osm_waterway_refs(transformer)
    osm_water_areas = _fetch_osm_water_areas(transformer)

    last_time = time_logging("Time used in seconds for parsing OSM data", last_time)

    # =========== PROCESS AERODROME INFORMATION ============================
    _process_aerodromes(building_zones, aerodrome_zones, airports, transformer)
    last_time = time_logging("Time used in seconds for processing aerodromes", last_time)

    # =========== READ LAND-USE DATA FROM FLIGHTGEAR BTG-FILES =============
    btg_reader = btg.read_btg_file(transformer, None)
    btg_building_zones = list()
    water_areas = list()

    if btg_reader is None:
        if len(osm_buildings) + len(highways_dict) + len(railways_dict) > 0:
            logging.warning('No BTG available in area, where there are OSM buildings or roads/rails')
    else:
        if parameters.OWBB_USE_BTG_LANDUSE:
            btg_polygons = btg.process_polygons_from_btg_faces(btg_reader, btg.URBAN_MATERIALS, False, transformer)
            btg_building_zones = _create_btg_buildings_zones(btg_polygons)
            last_time = time_logging("Time used in seconds for processing BTG building zones", last_time)

        btg_polygons = btg.process_polygons_from_btg_faces(btg_reader, btg.WATER_MATERIALS, False, transformer)
        last_time = time_logging("Time used in seconds for getting raw BTG water polygons", last_time)
        btg_transport = btg.process_polygons_from_btg_faces(btg_reader, btg.TRANSPORT_MATERIALS, False, transformer,
                                                            False)
        last_time = time_logging("Time used in seconds for getting raw BTG transport polygons", last_time)

        water_areas = _merge_btg_transport_in_water(btg_polygons, btg_transport)
        last_time = time_logging("Time used in seconds for processing BTG water polygons", last_time)
        logging.info('Final count of BTG water polygons is: %i', len(water_areas))

    if water_areas:
        _remove_osm_buildings_in_water(osm_buildings, water_areas)

    if btg_building_zones:
        _extend_osm_building_zones_with_btg_zones(building_zones, btg_building_zones)
    last_time = time_logging("Time used in seconds for processing external zones", last_time)

    # =========== CHECK WHETHER WE ARE IN A BUILT-UP AREA AT ALL ===========================
    if len(building_zones) == 0 and len(osm_buildings) == 0 and len(highways_dict) == 0 and len(railways_dict) == 0:
        logging.info('No zones, buildings and highways/railways in tile = %i', tile_index)
        # there is no need to save a cache, so just do nothing
        return None, None, None

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

    # =========== Finally make sure that no land-use is in water ========================
    if water_areas:
        _reduce_building_zones_with_btg_water(building_zones, water_areas)

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
    if parameters.FLAG_FAST_LANDUSE:
        highways_dict_copy1 = highways_dict.copy()
        grid_highways = list()
        for highway in highways_dict_copy1.values():
            if not highway.populate_buildings_along():
                continue
            grid_highways.append(GridHighway(highway.geometry))
        centre_circles = list()
        block_circles = list()
        dense_circles = list()
        for place in urban_places:
            centre_circle, block_circle, dense_circle = place.create_prepared_place_polys()
            centre_circles.append(centre_circle)
            block_circles.append(block_circle)
            dense_circles.append(dense_circle)

        settlement_clusters = _create_clusters_of_settlements(lit_areas, osm_water_areas, dense_circles)
        last_time = time_logging('Time used in seconds for creating settlement_clusters', last_time)
        _count_zones_related_buildings(osm_buildings, 'after settlement clusters')
        _assign_grid_indices(building_zones, settlement_clusters, centre_circles, block_circles, dense_circles,
                             grid_highways, transformer)
        last_time = time_logging('Time used in seconds assigning grid indices', last_time)
        _assign_minimum_settlement_type_to_zones(building_zones, settlement_clusters)
        last_time = time_logging('Time used in seconds assigning minimum settlement type', last_time)
        _assign_city_blocks_to_zones(building_zones, highways_dict, grid_highways)
        _assign_urban_settlement_type(building_zones, enu.SettlementType.centre, centre_circles)
        last_time = time_logging('Time used in seconds assigning centre settlement type', last_time)
        _assign_urban_settlement_type(building_zones, enu.SettlementType.block, block_circles)
        last_time = time_logging('Time used in seconds assigning block settlement type', last_time)
        _assign_urban_settlement_type(building_zones, enu.SettlementType.dense, dense_circles)
        last_time = time_logging('Time used in seconds assigning dense settlement type', last_time)
        if parameters.OWBB_PLACE_CHECK_DENSITY:
            _sanity_check_settlement_types(building_zones, highways_dict, grid_highways)
            last_time = time_logging('Time used in seconds for sanity checking settlement types', last_time)
    else:
        settlement_clusters = _create_settlement_clusters(lit_areas, osm_water_areas, urban_places)
        last_time = time_logging('Time used in seconds for creating settlement_clusters', last_time)
        _count_zones_related_buildings(osm_buildings, 'after settlement clusters')
        _link_building_zones_with_settlements(settlement_clusters, building_zones, highways_dict)
        last_time = time_logging('Time used in seconds for linking building zones with settlement_clusters', last_time)
        if parameters.OWBB_PLACE_CHECK_DENSITY:
            _sanity_check_settlement_types(building_zones, highways_dict, None)
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

    # ============ Exclude buildings not processed in buildings now that we have the zones and guessed their type ===
    remove_unused = set()
    for building in reversed(osm_buildings):
        if s.is_small_building_land_use(building.tags, True) or s.is_small_building_land_use(building.tags, False):
            remove_unused.add(building)
        elif building.is_too_small_building():
            remove_unused.add(building)
    for building in remove_unused:
        if building.has_parent:
            building.parent.remove_child(building)
        osm_buildings.remove(building)
    logging.info('Removed %i small buildings used in land-use', len(remove_unused))

    # ============ Now let us do final calculations and relations as long as we have the nodes dict =================
    # See whether we can do more building relations
    # This is done as late as possible to reduce exec time by only looking in the building's same zone
    bu.process_building_loose_parts(building_nodes_dict, osm_buildings)
    last_time = time_logging('Time used in seconds for processing building loose parts', last_time)

    # run a neighbour analysis -> building.refs_shared
    _relate_neighbours(osm_buildings)
    last_time = time_logging('Time used in seconds for relating neighbours', last_time)
    # simplify the geometry
    count = 0
    for building in osm_buildings:
        if not building.has_parent:  # do not simplify if in parent/child relationship
            count += building.simplify(building_nodes_dict, transformer)
    logging.info('Made %i simplifications in total (there can be more than 1 simplification in a building',
                 count)
    # now we can calculate the roof ridge orientation and L-shaped roofs
    count = 0
    for building in osm_buildings:
        building.calc_roof_hints(building_nodes_dict, transformer)
        if building.roof_hint and building.roof_hint.inner_node:
            count += 1
    last_time = time_logging('Time used in seconds for simplifying and calculating roof hints', last_time)
    logging.info('%i L-shaped roofs with inner-nodes.', count)
    # update the geometry a final time based on node references before we loose it
    for building in osm_buildings:
        building.update_geometry_from_refs(building_nodes_dict, transformer)
    last_time = time_logging('Time used in seconds for calculating the roof ridge orientation', last_time)

    # =========== FINALIZE Land-use PROCESSING =============================================
    if parameters.DEBUG_PLOT_LANDUSE:
        logging.info('Start of plotting zones')
        plotting.draw_zones(osm_buildings, building_zones, btg_building_zones, water_areas, lit_areas, bounds)
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

            with open(cache_file_wa, 'wb') as file_pickle:
                pickle.dump(water_areas, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(water_areas), cache_file_wa)

            with open(cache_file_bz, 'wb') as file_pickle:
                pickle.dump(osm_buildings, file_pickle)
            logging.info('Successfully saved %i objects to %s', len(osm_buildings), cache_file_bz)
        except (IOError, EOFError) as reason:
            logging.info("Saving of cache %s or %s failed (%s)", cache_file_la, cache_file_bz, reason)

    return lit_areas, water_areas, osm_buildings
