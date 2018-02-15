import logging
import math
from typing import Dict, List

import shapely.geometry as shg

import parameters
from utils.coordinates import Transformation
import utils.osmparser as osm


class Landuse(object):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for land-uses constructed with heuristics and not in original data from OSM

    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self._polygon = None  # the polygon defining its outer boundary
        self.number_of_buildings = 0  # only set for generated TYPE_NON_OSM land-uses during generation
        self._bounds = None  # is set when the polygon is set for performance reasons (.bounds makes a new calc)

    @property
    def bounds(self):
        if self._bounds is None:
            raise AttributeError('Trying to get bounds before valid geometry has been added')
        return self._bounds

    @property
    def polygon(self):
        return self._polygon

    @polygon.setter
    def polygon(self, polygon: shg.Polygon):
        self._polygon = polygon
        self._bounds = self._polygon.bounds


def process_osm_landuse_refs(nodes_dict: Dict[int, osm.Node], ways_dict: Dict[int, osm.Way],
                             my_coord_transformator: Transformation) -> Dict[int, Landuse]:
    my_landuses = dict()  # osm_id as key, Landuse as value

    for way in list(ways_dict.values()):
        my_landuse = Landuse(way.osm_id)
        valid_landuse = False
        for key in way.tags:
            value = way.tags[key]
            if "landuse" == key:
                if value == "commercial":
                    my_landuse.type_ = Landuse.TYPE_COMMERCIAL
                    valid_landuse = True
                elif value == "industrial":
                    my_landuse.type_ = Landuse.TYPE_INDUSTRIAL
                    valid_landuse = True
                elif value == "residential":
                    my_landuse.type_ = Landuse.TYPE_RESIDENTIAL
                    valid_landuse = True
                elif value == "retail":
                    my_landuse.type_ = Landuse.TYPE_RETAIL
                    valid_landuse = True
        if valid_landuse:
            my_polygon = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
            if my_polygon is not None:
                my_landuse.polygon = my_polygon
                if my_landuse.polygon.is_valid and not my_landuse.polygon.is_empty:
                    my_landuses[my_landuse.osm_id] = my_landuse

    logging.info("OSM land-uses found: %s", len(my_landuses))
    return my_landuses


def process_osm_landuse_for_lighting(nodes_dict: Dict[int, osm.Node], ways_dict: Dict[int, osm.Way],
                                     my_coord_transformator: Transformation) -> List[Landuse]:
    """Wrapper around process_osm_landuse_refs(...) to get landuses with BUILT_UP_AREA_LIT_BUFFER."""
    landuse_refs = process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator)
    if parameters.LU_LANDUSE_GENERATE_LANDUSE:
        building_refs = _process_osm_building_refs(my_coord_transformator)
        generate_landuse_from_buildings(landuse_refs, building_refs)
    for key, landuse in landuse_refs.items():
        landuse.polygon = landuse.polygon.buffer(parameters.BUILT_UP_AREA_LIT_BUFFER)
    return list(landuse_refs.values())


def generate_landuse_from_buildings(osm_landuses: Dict[int, Landuse], building_refs: List[shg.Polygon]) -> None:
    """Generates 'missing' land-uses based on building clusters."""
    my_landuse_candidates = dict()
    index = 0
    for my_building in building_refs:
        # check whether the building already is in a land use
        within_existing_landuse = False
        for osm_landuse in list(osm_landuses.values()):
            if my_building.intersects(osm_landuse.polygon):
                within_existing_landuse = True
                break
        if not within_existing_landuse:
            # create new clusters of land uses
            buffer_distance = parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE
            if my_building.area > parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2:
                factor = math.sqrt(my_building.area / parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE**2)
                buffer_distance = min(factor*parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE,
                                      parameters.LU_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX)
            buffer_polygon = my_building.buffer(buffer_distance)
            buffer_polygon = buffer_polygon
            within_existing_landuse = False
            for key, candidate in my_landuse_candidates.items():
                if buffer_polygon.intersects(candidate.polygon):
                    candidate.polygon = candidate.polygon.union(buffer_polygon)
                    candidate.number_of_buildings += 1
                    within_existing_landuse = True
                    break
            if not within_existing_landuse:
                index -= 1
                my_candidate = Landuse(index)
                my_candidate.polygon = buffer_polygon
                my_candidate.number_of_buildings = 1
                my_candidate.type_ = Landuse.TYPE_NON_OSM
                my_landuse_candidates[my_candidate.osm_id] = my_candidate
    # add landuse candidates to landuses
    logging.debug("Candidate land-uses found: %d", len(my_landuse_candidates))
    added = 0
    for key, candidate in my_landuse_candidates.items():
        if candidate.polygon.area >= parameters.LU_LANDUSE_MIN_AREA:
            osm_landuses[key] = candidate
            added += 1
    logging.info("Candidate land-uses with sufficient area added: %d", added)


def _process_osm_building_refs(my_coord_transformator: Transformation) -> List[shg.Polygon]:
    """Takes all buildings' convex hull (but not building:part) to be used for landuse processing.
    Only valid if database is used.
    """
    my_buildings = list()
    osm_way_result = osm.fetch_osm_db_data_ways_keys(['building'])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    for way in list(osm_ways_dict.values()):
        for key in way.tags:
            if "building" == key:
                my_coordinates = list()
                for ref in way.refs:
                    if ref in osm_nodes_dict:
                        my_node = osm_nodes_dict[ref]
                        my_coordinates.append(my_coord_transformator.to_local((my_node.lon, my_node.lat)))
                if 2 < len(my_coordinates):
                    my_polygon = shg.Polygon(my_coordinates)
                    if my_polygon.is_valid and not my_polygon.is_empty:
                        my_buildings.append(my_polygon.convex_hull)
    return my_buildings



