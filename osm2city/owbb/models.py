"""Objects and enumerations used as models across the owbb package.

Stored in its own module to minimize circular references and separate processing from data.
"""


import abc
from enum import IntEnum, unique
import logging
import math
import random
from typing import Dict, List, Optional, Tuple, Union

from shapely.geometry import box, Point, LineString, Polygon, MultiPolygon
import shapely.affinity as saf
from shapely.prepared import prep

import osm2city.static_types.enumerations as enu
from osm2city import parameters
from osm2city import building_lib as bl
from osm2city.utils import osmparser as op
from osm2city.static_types import osmstrings as s
from osm2city.static_types import enumerations as e
from osm2city.utils import coordinates as co
from osm2city.utils import json_io as wio


# type aliases
KeyValueDict = Dict[str, str]
MPoly = Union[Polygon, MultiPolygon]


class Bounds(object):
    def __init__(self, min_point: Point, max_point: Point) -> None:
        self.min_point = min_point
        self.max_point = max_point

    @classmethod
    def create_from_parameters(cls, coord_transform: co.Transformation) -> 'Bounds':
        min_point = Point(coord_transform.to_local((parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)))
        max_point = Point(coord_transform.to_local((parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)))
        return Bounds(min_point, max_point)


class OSMFeature(abc.ABC):
    __slots__ = ('osm_id', 'type_', 'geometry')
    """The base class for OSM Map Features cf. http://wiki.openstreetmap.org/wiki/Map_Features"""
    def __init__(self, osm_id: int, geometry, feature_type) -> None:
        self.osm_id = osm_id
        self.type_ = feature_type
        self.geometry = geometry  # A Shapely geometry object (Point, LinearString, Polygon)

    def is_valid(self) -> bool:
        """Checks the attributes to make sure all fine.
        Return True, if all is ok.
        False otherwise.
        """
        if None is self.type_:
            return False
        if None is self.geometry:
            return False
        return True

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, IntEnum]:
        """Parses the raw tags (key / values) from OSM to pick the relevant and cast them to internal fields."""


class PreparedSettlementTypePoly:
    """A polygon (circle) representing a settlement type centre, block or dense.

    It is the total area and not the 'donut': e.g. dense is only the actual ring around centre/block, but here to
    ease processing it is the whole. Therefore, matching against these polygons must be done in hierarchy:
    first centre, then block, then dense.
    """
    __slots__ = ('geometry', 'prep_poly', 'grid_indices')

    def __init__(self, geometry: Polygon) -> None:
        self.geometry = geometry
        self.prep_poly = prep(geometry)
        self.grid_indices = set()


class Place(OSMFeature):
    """ A 'Places' OSM Map Feature
    A Place can either be of element type Node -> Point geometry or Way -> Area -> LinearString
    There are a few in relations, but so few that it will not be modelled.
    Cf. http://wiki.openstreetmap.org/wiki/Key:place
    Cf. http://wiki.openstreetmap.org/wiki/Map_Features#Places
    """
    __slots__ = ('is_point', 'population', 'name')

    def __init__(self, osm_id, geometry, feature_type, is_point) -> None:
        super().__init__(osm_id, geometry, feature_type)
        self.is_point = is_point
        self.population = 0  # based on OSM population tag
        self.name = None

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'Place':
        my_geometry = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
        feature_type = cls.parse_tags(way.tags)
        obj = Place(way.osm_id, my_geometry, feature_type, False)
        obj.parse_tags_additional(way.tags)
        return obj

    @classmethod
    def create_from_node(cls, node: op.Node, my_coord_transformator: co.Transformation) -> 'Place':
        x, y = my_coord_transformator.to_local((node.lon, node.lat))
        my_geometry = Point(x, y)
        feature_type = cls.parse_tags(node.tags)
        obj = Place(node.osm_id, my_geometry, feature_type, True)
        obj.parse_tags_additional(node.tags)
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, enu.PlaceType]:
        value = tags_dict[s.K_PLACE]
        for member in enu.PlaceType:
            if value == member.name:
                return member
        return None

    def parse_tags_additional(self, tags_dict: KeyValueDict) -> None:
        if s.K_POPULATION in tags_dict:
            self.population = s.parse_int(tags_dict[s.K_POPULATION], 0)
        elif s.K_WIKIDATA in tags_dict:
            my_id = tags_dict[s.K_WIKIDATA]
            my_population = wio.query_population_wikidata(my_id)
            if my_population is not None:
                self.population = my_population

        if s.K_NAME in tags_dict:
            self.name = tags_dict[s.K_NAME]
        elif s.K_PLACE_NAME in tags_dict:  # only use it if name was not included
            self.name = tags_dict[s.K_PLACE_NAME]

    def is_valid(self) -> bool:
        if None is self.type_:
            return False
        if self.is_point:
            if not isinstance(self.geometry, Point):
                return False
        else:
            if not isinstance(self.geometry, Polygon):
                return False
        return True

    def transform_to_point(self) -> None:
        """Transforms a Place defined as Way to a Point."""
        if self.is_point:
            return
        if self.type_ is enu.PlaceType.farm:
            logging.debug('Attempted to transform Place of type farm from area to point')
            return
        self.is_point = True
        self.geometry = self.geometry.centroid

    def _calculate_circle_radius(self, population: int, power: float) -> float:
        radius = math.pow(population, power)
        if self.type_ is enu.PlaceType.city:
            radius *= parameters.OWBB_PLACE_RADIUS_FACTOR_CITY
        else:
            radius *= parameters.OWBB_PLACE_RADIUS_FACTOR_TOWN
        return radius

    def create_settlement_type_circles(self) -> Tuple[Polygon, Polygon, Polygon]:
        population = self.population
        if population == 0:
            if self.type_ is enu.PlaceType.city:
                population = parameters.OWBB_PLACE_POPULATION_DEFAULT_CITY
            else:
                population = parameters.OWBB_PLACE_POPULATION_DEFAULT_TOWN
        centre_circle = Polygon()
        block_circle = Polygon()
        if self.type_ is enu.PlaceType.city:
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_CENTRE)
            centre_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_BLOCK)
            block_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_DENSE)
            dense_circle = self.geometry.buffer(radius)
        else:
            if self.population > 0 and population > parameters.OWBB_PLACE_POPULATION_MIN_BLOCK:
                radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_BLOCK)
                block_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_DENSE)
            dense_circle = self.geometry.buffer(radius)
        return centre_circle, block_circle, dense_circle

    def create_prepared_place_polys(self) -> Tuple[PreparedSettlementTypePoly, PreparedSettlementTypePoly,
                                                   PreparedSettlementTypePoly]:
        centre_circle, block_circle, dense_circle = self.create_settlement_type_circles()
        return (PreparedSettlementTypePoly(centre_circle), PreparedSettlementTypePoly(block_circle),
                PreparedSettlementTypePoly(dense_circle))


class SettlementCluster:
    __slots__ = ('linked_places', 'geometry', 'grid_indices')

    """A polygon based on lit_area representing a settlement cluster.
    Built-up areas can sprawl and a coherent area can contain several cities and towns.
    Must contain at least one place recognized as city or town - 'contain' here means that the dense circle
    around the place somehow intersects with the lit_area. 
    All other lit areas or not Settlement clusters but simple rural areas."""
    def __init__(self, linked_places: List[Place], geometry: Polygon) -> None:
        self.linked_places = linked_places
        self.geometry = geometry
        self.grid_indices = set()


class OSMFeatureArea(OSMFeature):
    def __init__(self, osm_id: int, geometry: MPoly, feature_type: Union[None, IntEnum]) -> None:
        super().__init__(osm_id, geometry, feature_type)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'OSMFeatureArea':
        raise NotImplementedError("Please implement this method")


@unique
class BlockedAreaType(IntEnum):
    osm_building = 1
    gen_building = 2
    open_space = 3
    highway = 11
    waterway = 12
    railway = 13


class BlockedArea:
    __slots__ = ('type_', 'polygon', 'original_type')

    """An object representing a specific type of blocked area - blocked for new generated buildings"""
    def __init__(self, type_: BlockedAreaType, polygon: Polygon, original_type=None) -> None:
        self.type_ = type_
        self.polygon = polygon
        self.original_type = original_type


@unique
class OpenSpaceType(IntEnum):
    default = 10
    landuse = 20
    amenity = 30
    leisure = 40
    natural = 50
    transport = 60
    pedestrian = 70


class OpenSpace(OSMFeatureArea):
    """Different OSM map features representing an open space, where no building can be placed.
    It is important to keep parsing of these tags in synch (i.e. opposite) with the other parsed OSM map features.
    """
    # must be in line with method parse_tags
    REQUESTED_TAGS = ['public_transport', 'railway', 'amenity', 'leisure', 'natural', 'highway']

    def __init__(self, osm_id: int, geometry: MPoly, feature_type: Union[None, OpenSpaceType]) -> None:
        super().__init__(osm_id, geometry, feature_type)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> Union[None, 'OpenSpace']:
        my_geometry = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
        feature_type = cls.parse_tags(way.tags)
        if None is feature_type:
            return None
        obj = OpenSpace(way.osm_id, my_geometry, feature_type)
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[OpenSpaceType, None]:
        if enu.parse_building_tags_for_type(tags_dict) is not None:
            return None
        elif s.K_PUBLIC_TRANSPORT in tags_dict:
            return OpenSpaceType.transport
        elif (s.K_RAILWAY in tags_dict) and (tags_dict[s.K_RAILWAY] == s.V_STATION):
            return OpenSpaceType.transport
        elif s.K_LANDUSE in tags_dict:  # must be in sync with BuildingZone
            if tags_dict[s.K_LANDUSE] == s.V_RAILWAY:
                return OpenSpaceType.transport
            elif BuildingZone.is_building_zone_value(tags_dict[s.K_LANDUSE]):
                return None
            else:
                return OpenSpaceType.landuse
        elif s.K_AMENITY in tags_dict:
            if tags_dict[s.K_AMENITY] in [s.V_GRAVE_YARD, s.V_PARKING]:
                return OpenSpaceType.amenity
        elif s.K_LEISURE in tags_dict:
            if tags_dict[s.K_LEISURE] in [s.V_BEACH_RESORT, s.V_COMMON, s.V_DOG_PARK, s.V_GARDEN, s.V_HORSE_RIDING,
                                          s.V_MARINA, s.V_NATURE_RESERVE, s.V_PARK, s.V_PITCH, s.V_PLAYGROUND,
                                          s.V_SWIMMING_AREA, s.V_TRACK]:
                return OpenSpaceType.leisure
        elif s.K_NATURAL in tags_dict:
            return OpenSpaceType.natural
        elif s.K_HIGHWAY in tags_dict:
            if tags_dict[s.K_HIGHWAY] == "pedestrian":
                if (s.K_AREA in tags_dict) and (tags_dict[s.K_AREA] == "yes"):
                    return OpenSpaceType.pedestrian
        return None


class CityBlock:
    """A special land-use derived from many kinds of land-use info and enclosed by streets (kind of)."""
    __slots__ = ('osm_id', 'geometry', 'prep_geom', 'type_', 'osm_buildings',
                 '__settlement_type', '__building_levels')

    def __init__(self, osm_id: int, geometry: Polygon, feature_type: Union[None, enu.BuildingZoneType]) -> None:
        self.osm_id = osm_id
        self.geometry = geometry
        self.prep_geom = None  # temp Shapely PreparedGeometry - only valid in a specific context, where it is set
        self.type_ = feature_type
        self.osm_buildings = list()  # List of already existing osm buildings
        self.__settlement_type = None
        self.settlement_type = enu.SettlementType.periphery
        self.__building_levels = 0

    def relate_building(self, building: bl.Building) -> None:
        """Link the building to this zone and link this zone to the building."""
        self.osm_buildings.append(building)
        building.zone = self

    @property
    def building_levels(self) -> int:
        return self.__building_levels

    @property
    def settlement_type(self) -> enu.SettlementType:
        return self.__settlement_type

    @settlement_type.setter
    def settlement_type(self, value):
        self.__settlement_type = value
        self.__building_levels = bl.calc_levels_for_settlement_type(value, enu.BuildingClass.residential)


class BuildingZone(OSMFeatureArea):
    """ A 'Landuse' OSM map feature
    A Landuse can either be of element type Node -> Point geometry or Way -> Area -> LinearString.
    However only areas are of interest.
    Also only those land-uses are mapped here, which specify a zoning type used in town planning for buildings.
    Other landuse OSM map features are handled in class BlockedArea.
    Cf. http://wiki.openstreetmap.org/wiki/Landuse
    Cf. http://wiki.openstreetmap.org/wiki/Map_Features#Landuse
    """
    __slots__ = ('linked_blocked_areas', 'osm_buildings', 'generated_buildings', 'linked_genways',
                 'linked_city_blocks', '__settlement_type', 'grid_indices')

    def __init__(self, osm_id: int, geometry: MPoly, feature_type: Union[None, enu.BuildingZoneType]) -> None:
        super().__init__(osm_id, geometry, feature_type)

        # the following fields are only used for generating would be buildings
        # i.e. they are not directly based on OSM data
        self.linked_blocked_areas = list()  # List of BlockedArea objects for blocked areas.
        self.osm_buildings = list()  # List of already existing osm buildings
        self.generated_buildings = list()  # List of GenBuilding objects for generated non-osm buildings
        self.linked_genways = list()  # List of Highways that are available for generating buildings
        self.linked_city_blocks = list()
        self.__settlement_type = enu.SettlementType.rural
        self.grid_indices = set()  # used to accelerate spatial calculations

    @property
    def settlement_type(self) -> enu.SettlementType:
        return self.__settlement_type

    @settlement_type.setter
    def settlement_type(self, value):
        self.__settlement_type = value

    def set_max_settlement_type(self, new_type: enu.SettlementType) -> None:
        """Make sure that a settlement type set previously does not get overwritten by a lower type."""
        if new_type.value > self.settlement_type.value:
            self.__settlement_type = new_type

    @property
    def density(self) -> float:
        """The density of an area here is calculated as the ratio between the zone density and the total area
        of all floor plans of buildings.
        In land-use planning normally it is the floor plans on all levels, but we do not have it here.)
        In order to approximate a bit better, therefore the 'geometry' instead of the 'polygon' attribute
        of the building is taken, i.e. all inner ring area is also counted."""
        total_floor_plans = 0.
        for building in self.osm_buildings:
            total_floor_plans += building.geometry.area

        return total_floor_plans / self.geometry.area

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'BuildingZone':
        my_geometry = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
        feature_type = cls.parse_tags(way.tags)
        obj = BuildingZone(way.osm_id, my_geometry, feature_type)
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, enu.BuildingZoneType]:
        if s.K_AEROWAY in tags_dict and tags_dict[s.K_AEROWAY] == s.V_AERODROME:
            return enu.BuildingZoneType.aerodrome
        value = tags_dict[s.K_LANDUSE]
        for member in enu.BuildingZoneType:
            if value == member.name:
                return member
        return None

    @staticmethod
    def is_building_zone_value(value: str) -> bool:
        for member in enu.BuildingZoneType:
            if value == member.name:
                return True
        return False

    def get_osm_value(self) -> str:
        return self.type_.name

    def commit_temp_gen_buildings(self, temp_buildings, highway, is_reverse) -> None:
        """Commits a set of generated buildings to be definitively be part of a BuildingZone"""
        self.linked_blocked_areas.extend(temp_buildings.generated_blocked_areas)
        for gen_building in temp_buildings.generated_buildings:
            # relate to zone
            self.generated_buildings.append(gen_building)
            gen_building.zone = self
            # relate to city block if available (we do not need to relate GenBuilding to CityBlock
            if is_reverse:
                if highway.reversed_city_block:
                    gen_building.zone = highway.reversed_city_block
            else:
                if highway.along_city_block:
                    gen_building.zone = highway.along_city_block

    def relate_building(self, building: bl.Building) -> None:
        """Link the building to this zone and link this zone to the building."""
        self.osm_buildings.append(building)
        building.zone = self

    def reset_city_blocks(self) -> None:
        self.linked_city_blocks = list()

    def add_city_block(self, city_block: CityBlock) -> None:
        self.linked_city_blocks.append(city_block)

    def reassign_osm_buildings_to_city_blocks(self) -> None:
        """AS far as possible buildings are related to city_blocks.
        If there is none, then the existing relation to the zone is kept also from the building."""
        for city_block in self.linked_city_blocks:
            city_block.prep_geom = prep(city_block.geometry)

        for osm_building in self.osm_buildings:
            for city_block in self.linked_city_blocks:
                if city_block.prep_geom.contains_properly(osm_building.geometry) or city_block.prep_geom.intersects(
                        osm_building.geometry):
                    city_block.relate_building(osm_building)
                    break

        # need to set back again - otherwise cannot pickle
        for city_block in self.linked_city_blocks:
            city_block.prep_geom = None

    def link_city_blocks_to_highways(self) -> None:
        """Tries to link city blocks to highways for building generation.

        Using the middle point of the highway and just the overall angle should give correct result in most of the
        cases. And if not then no big harm, as city blocks close to each other will have similar types."""
        linked = 0
        for highway in self.linked_genways:
            half_length = highway.geometry.length / 2
            middle_point = highway.geometry.interpolate(half_length)
            before_point = highway.geometry.interpolate(half_length - 1)
            after_point = highway.geometry.interpolate(half_length + 1)
            angle = co.calc_angle_of_line_local(before_point.x, before_point.y, after_point.x, after_point.y)
            # one side
            my_point = Point(co.calc_point_angle_away(middle_point.x, middle_point.y,
                                                      2 * parameters.OWBB_CITY_BLOCK_HIGHWAY_BUFFER, angle + 90))
            for city_block in self.linked_city_blocks:
                if my_point.within(city_block.geometry):
                    highway.along_city_block = city_block
                    linked += 1
                    break
            # opposite side
            my_point = Point(co.calc_point_angle_away(middle_point.x, middle_point.y,
                                                      2 * parameters.OWBB_CITY_BLOCK_HIGHWAY_BUFFER, angle - 90))
            for city_block in self.linked_city_blocks:
                if my_point.within(city_block.geometry):
                    highway.reversed_city_block = city_block
                    linked += 1
                    break

        logging.debug('Linked around &i out of %i high ways to city blocks in building zone %i', linked,
                      len(self.linked_genways), self.osm_id)

    def process_buildings_as_blocked_areas(self):
        for building in self.osm_buildings:
            blocked = BlockedArea(BlockedAreaType.osm_building, building.geometry,
                                  enu.parse_building_tags_for_type(building.tags))
            self.linked_blocked_areas.append(blocked)

    def process_open_spaces_as_blocked_areas(self, open_spaces_dict: Dict[int, OpenSpace]) -> None:
        """Adds open spaces (mostly leisure) to this zone as a blocked area.
        All open_spaces, which are within the building_zone, will be removed from open_spaces
        to speed up processing."""
        to_be_removed = list()
        for candidate in open_spaces_dict.values():
            is_blocked = False
            if candidate.geometry.within(self.geometry):
                is_blocked = True
                to_be_removed.append(candidate.osm_id)
            elif candidate.geometry.intersects(self.geometry):
                is_blocked = True
            if is_blocked:
                blocked = BlockedArea(BlockedAreaType.open_space, candidate.geometry, candidate.type_)
                self.linked_blocked_areas.append(blocked)
        for key in to_be_removed:
            del open_spaces_dict[key]

    @property
    def is_aerodrome(self) -> bool:
        return self.type_ is enu.BuildingZoneType.aerodrome


class BTGBuildingZone(object):
    __slots__ = ('id', 'type_', 'geometry')

    """A land-use from materials in FlightGear read from BTG-files"""
    def __init__(self, external_id, type_, geometry) -> None:
        self.id = str(external_id)  # String
        self.type_ = type_  # BuildingZoneType
        self.geometry = geometry  # Polygon


class GeneratedBuildingZone(BuildingZone):
    """A fake OSM Land-use for buildings based on heuristics"""
    __slots__ = 'from_buildings'

    def __init__(self, generated_id, geometry, building_zone_type) -> None:
        super().__init__(generated_id, geometry, building_zone_type)
        self.from_buildings = self.type_ is enu.BuildingZoneType.non_osm

    def guess_building_zone_type(self, farm_places: List[Place]):
        """Based on some heuristics of linked buildings guess the building zone type"""
        # first we try to map directly BTG zones to OSM zones
        if self.type_ in [enu.BuildingZoneType.btg_suburban, enu.BuildingZoneType.btg_town,
                          enu.BuildingZoneType.btg_urban, enu.BuildingZoneType.btg_builtupcover]:
            self.type_ = enu.BuildingZoneType.residential
            return

        if self.type_ in [enu.BuildingZoneType.btg_port, enu.BuildingZoneType.btg_industrial,
                          enu.BuildingZoneType.btg_construction]:
            self.type_ = enu.BuildingZoneType.industrial
            return

        # now we should only have non_osm based on lonely buildings
        assert self.type_ is enu.BuildingZoneType.non_osm, 'Needs type "non_osm", but actually is "{}"'.format(
            self.type_.name)
        residential_buildings = 0
        commercial_buildings = 0
        industrial_buildings = 0
        retail_buildings = 0
        farm_buildings = 0
        for building in self.osm_buildings:
            building_class = enu.get_building_class(building.tags)
            if building_class in [enu.BuildingClass.residential_small, enu.BuildingClass.residential,
                                  enu.BuildingClass.terrace, enu.BuildingClass.public]:
                residential_buildings += 1
            elif building_class is enu.BuildingClass.commercial:
                commercial_buildings += 1
            elif building_class in [enu.BuildingClass.industrial, enu.BuildingClass.warehouse]:
                industrial_buildings += 1
            elif building_class in [enu.BuildingClass.retail, enu.BuildingClass.parking_house]:
                retail_buildings += 1
            elif building_class is enu.BuildingClass.farm:
                farm_buildings += 1

        guessed_type = enu.BuildingZoneType.residential  # default
        max_value = max([residential_buildings, commercial_buildings, industrial_buildings, retail_buildings,
                         farm_buildings])
        if 0 < max_value:
            if len(self.osm_buildings) < 10:
                logging.debug("Checking generated land-use for place=farm based on %d place tags", len(farm_places))
                for my_place in farm_places:
                    if my_place.is_point:
                        if my_place.geometry.within(self.geometry):
                            self.type_ = enu.BuildingZoneType.farmyard
                            farm_places.remove(my_place)
                            logging.debug("Found one based on node place")
                            return
                    else:
                        if my_place.geometry.intersects(self.geometry):
                            self.type_ = enu.BuildingZoneType.farmyard
                            farm_places.remove(my_place)
                            logging.debug("Found one based on area place")
                            return
            if farm_buildings == max_value:  # in small villages farm houses might be tagged, but rest just ="yes"
                if (len(self.osm_buildings) >= 10) and (farm_buildings < int(0.5*len(self.osm_buildings))):
                    guessed_type = enu.BuildingZoneType.residential
                else:
                    guessed_type = enu.BuildingZoneType.farmyard
            elif commercial_buildings == max_value:
                guessed_type = enu.BuildingZoneType.commercial
            elif industrial_buildings == max_value:
                guessed_type = enu.BuildingZoneType.industrial
            elif retail_buildings == max_value:
                guessed_type = enu.BuildingZoneType.retail

        self.type_ = guessed_type


class OSMFeatureLinear(OSMFeature):
    __slots__ = 'has_embankment'

    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        feature_type = self.parse_tags(tags_dict)
        super().__init__(osm_id, geometry, feature_type)
        if self._parse_tags_tunnel(tags_dict):
            self.type_ = None
        self.has_embankment = self._parse_tags_embankment(tags_dict)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'OSMFeatureLinear':
        raise NotImplementedError("Please implement this method")

    @staticmethod
    def create_line_string_from_way(way: op.Way, nodes_dict: Dict[int, op.Node],
                                    transformer: co.Transformation) -> LineString:
        return way.line_string_from_osm_way(nodes_dict, transformer)

    @staticmethod
    def _parse_tags_embankment(tags_dict: KeyValueDict) -> bool:
        return s.K_EMBANKMENT in tags_dict or s.K_CUTTING in tags_dict

    @staticmethod
    def _parse_tags_tunnel(tags_dict: KeyValueDict) -> bool:
        """If this is tagged with tunnel, then _type = None.
        Thereby the object is invalid and will not be added. Because tunnels do not interfere with buildings.
        """
        if (s.K_TUNNEL in tags_dict) and (tags_dict[s.K_TUNNEL] == s.V_YES):
            return True
        return False


@unique
class WaterwayType(IntEnum):
    large = 10  # river, canal
    narrow = 20  #


class Waterway(OSMFeatureLinear):
    """A 'Waterway' OSM map feature.
     Cf. http://wiki.openstreetmap.org/wiki/Map_Features#Waterway
     """
    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        super().__init__(osm_id, geometry, tags_dict)

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[WaterwayType, None]:
        value = tags_dict[s.K_WATERWAY]
        if value in [s.V_RIVER, s.V_CANAL]:
            return WaterwayType.large
        elif value in [s.V_STREAM, s.V_WADI, s.V_DRAIN, s.V_DITCH]:
            return WaterwayType.narrow
        return None

    def get_width(self) -> float:
        if self.type_ == WaterwayType.large:
            my_width = 15.0
        else:
            my_width = 5.0
        if self.has_embankment:
            my_width *= 3.0
        return my_width

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'Waterway':
        my_geometry = cls.create_line_string_from_way(way, nodes_dict, transformer)
        obj = Waterway(way.osm_id, my_geometry, way.tags)
        return obj


class OSMFeatureLinearWithTunnel(OSMFeatureLinear):
    __slots__ = 'is_tunnel'

    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.is_tunnel = self._parse_tags_tunnel(tags_dict)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'OSMFeatureLinear':
        raise NotImplementedError("Please implement this method")


@unique
class RailwayLineType(IntEnum):
    rail = 10
    subway = 11
    monorail = 12
    light_rail = 13
    funicular = 14
    narrow_gauge = 15
    tram = 16
    other = 30


class RailwayLine(OSMFeatureLinearWithTunnel):
    """A 'Railway' OSM map feature (only tracks, not land-use etc)"""
    __slots__ = ('tracks', 'is_service_spur')

    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.tracks = self._parse_tags_tracks(tags_dict)
        self.is_service_spur = self._parse_tags_service_spur(tags_dict)

    @staticmethod
    def _parse_tags_tracks(tags_dict: KeyValueDict) -> int:
        my_tracks = 1
        if s.K_TRACKS in tags_dict:
            my_tracks = s.parse_int(tags_dict[s.K_TRACKS], 1)
        return my_tracks

    @staticmethod
    def _parse_tags_service_spur(tags_dict: KeyValueDict) -> bool:
        if s.K_SERVICE in tags_dict and tags_dict[s.K_SERVICE] == s.V_SPUR:
            return True
        return False

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[RailwayLineType, None]:
        value = tags_dict[s.K_RAILWAY]
        if value == s.V_RAIL:
            return RailwayLineType.rail
        elif value == s.V_SUBWAY:
            return RailwayLineType.subway
        elif value == s.V_MONORAIL:
            return RailwayLineType.monorail
        elif value == s.V_LIGHT_RAIL:
            return RailwayLineType.light_rail
        elif value == s.V_FUNICULAR:
            return RailwayLineType.funicular
        elif value == s.V_NARROW_GAUGE:
            return RailwayLineType.narrow_gauge
        elif value == s.V_TRAM:
            return RailwayLineType.tram
        elif value in [s.V_ABANDONED, s.V_CONSTRUCTION, s.V_DISUSED, s.V_PRESERVED]:
            return RailwayLineType.other
        return None

    def get_width(self) -> float:
        if self.type_ in [RailwayLineType.narrow_gauge, RailwayLineType.tram, RailwayLineType.funicular]:
            my_width = 5.0
        elif self.type_ in [RailwayLineType.rail, RailwayLineType.light_rail, RailwayLineType.monorail,
                            RailwayLineType.subway]:
            my_width = 7.0
        else:
            my_width = 6.0
        if self.tracks > 1:
            my_width += 0.8*(self.tracks-1)*my_width
        if self.has_embankment:
            my_width += 6.0
        return my_width

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'RailwayLine':
        my_geometry = cls.create_line_string_from_way(way, nodes_dict, transformer)
        obj = RailwayLine(way.osm_id, my_geometry, way.tags)
        return obj


class Highway(OSMFeatureLinearWithTunnel):
    __slots__ = ('is_roundabout', 'is_oneway', 'lanes', 'refs', 'along_city_block', 'reversed_city_block')

    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict, refs: List[int]) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.is_roundabout = s.is_roundabout(tags_dict)
        self.is_oneway = s.is_oneway(tags_dict)
        self.lanes = s.parse_tags_lanes(tags_dict)
        self.refs = refs
        self.along_city_block = None  # for building generation city block along line on right side
        self.reversed_city_block = None  # ditto reversed line

    @classmethod
    def create_from_scratch(cls, pseudo_id: int, existing_highway: 'Highway', linear: LineString) -> 'Highway':
        obj = Highway(pseudo_id, linear, dict(), existing_highway.refs)
        obj.type_ = existing_highway.type_
        obj.is_roundabout = existing_highway.is_roundabout
        obj.is_oneway = existing_highway.is_oneway
        obj.lanes = existing_highway.lanes
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, e.HighwayType]:
        return e.highway_type_from_osm_tags(tags_dict)

    def get_width(self) -> float:
        """Assumed width of highway to do diverse calculations like buffer etc.
        This is not the same as roads.get_highway_attributes, because there it is about the real texture
        mapping, which has different dimensions - amongst others due to a limited set of textures.
        Must be kept in line with enumerations.HighwayType.
        """
        if self.type_ in [e.HighwayType.service, e.HighwayType.residential, e.HighwayType.living_street,
                          e.HighwayType.pedestrian]:
            my_width = 5.0
        elif self.type_ in [e.HighwayType.road, e.HighwayType.unclassified, e.HighwayType.tertiary]:
            my_width = 6.0
        elif self.type_ in [e.HighwayType.secondary, e.HighwayType.primary, e.HighwayType.trunk]:
            my_width = 7.0
        elif self.type_ in [e.HighwayType.motorway]:
            my_width = 12.0  # motorway is tagged for each direction. Assuming 2 lanes plus emergency lane
        elif self.type_ in [e.HighwayType.one_way_multi_lane]:
            my_width = 3.5  # will be enhanced with more lanes below
        elif self.type_ in [e.HighwayType.one_way_large]:
            my_width = 4.
        elif self.type_ in [e.HighwayType.one_way_normal]:
            my_width = 3.
        else:  # HighwayType.slow
            my_width = 3.0

        if self.type_ == e.HighwayType.motorway:
            if self.lanes > 2:
                my_width += 3.5*(self.lanes-2)
            if not self.is_oneway:
                my_width *= 1.5  # assuming no hard shoulders, not much middle stuff
        else:
            if self.lanes > 1:
                my_width += 0.8*(self.lanes-1) * my_width
        if self.has_embankment:
            my_width += 4.0
        return my_width

    def is_sideway(self) -> bool:
        """Not a main street in an urban area. I.e. residential, walking or service"""
        return self.type_ <= e.HighwayType.residential

    def populate_buildings_along(self) -> bool:
        """The type of highway determines where buildings are built. E.g. motorway would be false"""
        return self.type_ not in (e.HighwayType.motorway, e.HighwayType.trunk)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'Highway':
        my_geometry = cls.create_line_string_from_way(way, nodes_dict, transformer)
        obj = Highway(way.osm_id, my_geometry, way.tags, way.refs)
        return obj


class BuildingModel(object):
    """A model of a building used to replace OSM buildings or create buildings where there could be a building.

    The center of the building is strictly in the middle of width/depth.
    All geometry information is either in the AC3D model or in tags.

    Tags contains e.g. roof type, number of levels etc. according to OSM tagging."""
    __slots__ = ('width', 'depth', 'model_type', 'regions', 'model', 'facade_id', 'roof_id', 'tags')

    def __init__(self, width: float, depth: float, model_type: enu.BuildingType, regions: List[str],
                 model: Optional[str], facade_id: int, roof_id: int, tags: KeyValueDict) -> None:
        self.width = width  # if you look at the building from its front, then you see the width between the sides
        self.depth = depth  # from the front to the back
        self.model_type = model_type
        self.regions = regions  # list of strings, e.g. GB, IE
        self.model = model  # a relative path / identifier to the AC3D information if available
        self.facade_id = facade_id
        self.roof_id = roof_id
        self.tags = tags

    @property
    def area(self) -> float:
        return self.width * self.depth

    @staticmethod
    def _parse_regions(region_string: str) -> List[str]:
        """Parses a string as a semi-colon separated list of regions"""
        my_regions = list()
        if region_string is None:
            return my_regions
        elif len(region_string.strip()) == 0:
            return my_regions
        else:
            split_regions = region_string.split(";")
            for reg in split_regions:
                my_regions.append(reg.strip())
        return my_regions


class SharedModel(object):
    __slots__ = ('building_model', '_front_buffer', '_back_buffer', '_side_buffer')

    def __init__(self, building_model: BuildingModel) -> None:
        self.building_model = building_model
        self._front_buffer = 0
        self._back_buffer = 0
        self._side_buffer = 0

    def calc_buffers(self, settlement_type: enu.SettlementType) -> None:
        # industrial
        if self.building_model.model_type is enu.BuildingType.industrial:
            my_rand = random.random()
            self._side_buffer = parameters.OWBB_INDUSTRIAL_BUILDING_SIDE_MIN + my_rand * (
                    parameters.OWBB_INDUSTRIAL_BUILDING_SIDE_MAX - parameters.OWBB_INDUSTRIAL_BUILDING_SIDE_MIN
            )
            self._back_buffer = self._side_buffer
            self._front_buffer = self._side_buffer
            if settlement_type in [enu.SettlementType.dense, enu.SettlementType.block, enu.SettlementType.centre]:
                self._front_buffer = parameters.OWBB_FRONT_DENSE
        else:
            self._side_buffer = math.sqrt(self.width) * parameters.OWBB_RESIDENTIAL_SIDE_FACTOR_PERIPHERY
            self._back_buffer = math.sqrt(self.depth) * parameters.OWBB_RESIDENTIAL_BACK_FACTOR_PERIPHERY
            self._front_buffer = math.sqrt(self.width) * parameters.OWBB_RESIDENTIAL_FRONT_FACTOR_PERIPHERY
            # terraces
            if self.building_model.model_type is enu.BuildingType.terrace:
                self._side_buffer = 0.0
                # however we want to have some breaks in the continuous line of houses
                if random.random() < (1 / parameters.OWBB_RESIDENTIAL_TERRACE_TYPICAL_NUMBER):
                    self._side_buffer = math.sqrt(self.width) * parameters.OWBB_RESIDENTIAL_SIDE_FACTOR_PERIPHERY
            # dense areas
            if settlement_type in [enu.SettlementType.dense, enu.SettlementType.block, enu.SettlementType.centre]:
                self._front_buffer = parameters.OWBB_FRONT_DENSE
                self._side_buffer = 0.0
                self._back_buffer = parameters.OWBB_FRONT_DENSE  # yes, it is small
                if settlement_type is enu.SettlementType.dense:
                    if self.building_model.model_type is enu.BuildingType.terrace:
                        # however we want to have some breaks in the continuous line of houses
                        if random.random() < (1 / parameters.OWBB_RESIDENTIAL_TERRACE_TYPICAL_NUMBER):
                            self._side_buffer = math.sqrt(
                                self.width) * parameters.OWBB_RESIDENTIAL_SIDE_FACTOR_DENSE
                    elif self.building_model.model_type in [enu.BuildingType.apartments, enu.BuildingType.detached]:
                        self._side_buffer = math.sqrt(self.width) * parameters.OWBB_RESIDENTIAL_SIDE_FACTOR_DENSE
                        self._front_buffer = self._side_buffer

    @property
    def type_(self) -> enu.BuildingType:
        return self.building_model.model_type

    @property
    def width(self) -> float:
        return self.building_model.width

    @property
    def depth(self) -> float:
        return self.building_model.depth

    @property
    def front_buffer(self) -> float:
        return self._front_buffer

    @property
    def min_front_buffer(self) -> float:
        """The absolute minimal distance tolerable, e.g. in a curve at the edges of the lot.
        The front_buffer will be used to place the building relative to the middle of the house along the street.
        The min_front_buffer is a bit smaller and allows in a concave curve that the building still is placed,
        because the buffer in the front of the house is only min_front_buffer and therefore smaller."""
        return math.sqrt(self._front_buffer)

    @property
    def back_buffer(self) -> float:
        return self._back_buffer

    @property
    def side_buffer(self) -> float:
        return self._side_buffer

    @property
    def building_type(self):
        return self.type_


class SharedModelsLibrary(object):
    def __init__(self, building_models: List[BuildingModel]):
        self._residential_detached = list()
        self._residential_terraces = list()
        self._residential_apartments = list()
        self._residential_attached = list()
        self._industrial_buildings_large = list()
        self._industrial_buildings_small = list()
        self._populate_models_library(building_models)

    @property
    def residential_detached(self):
        return self._residential_detached

    @property
    def residential_terraces(self):
        return self._residential_terraces

    @property
    def residential_apartments(self):
        return self._residential_apartments

    @property
    def residential_attached(self):
        return self._residential_attached

    @property
    def industrial_buildings_large(self):
        return self._industrial_buildings_large

    @property
    def industrial_buildings_small(self):
        return self._industrial_buildings_small

    def _populate_models_library(self, building_models: List[BuildingModel]) -> None:
        for building_model in building_models:
            if building_model.model_type is enu.BuildingType.apartments:
                a_model = SharedModel(building_model)
                self._residential_apartments.append(a_model)
            elif building_model.model_type is enu.BuildingType.attached:
                a_model = SharedModel(building_model)
                self._residential_attached.append(a_model)
            elif building_model.model_type is enu.BuildingType.detached:
                a_model = SharedModel(building_model)
                self._residential_detached.append(a_model)
            elif building_model.model_type is enu.BuildingType.terrace:
                a_model = SharedModel(building_model)
                self._residential_terraces.append(a_model)
            elif building_model.model_type is enu.BuildingType.industrial:
                a_model = SharedModel(building_model)
                if building_model.area > parameters.OWBB_INDUSTRIAL_LARGE_MIN_AREA:
                    self._industrial_buildings_large.append(a_model)
                else:
                    self._industrial_buildings_small.append(a_model)

    def is_valid(self) -> bool:
        if 0 == len(self._residential_detached):
            logging.warning("No residential detached buildings found")
            return False
        if 0 == len(self._residential_terraces):
            logging.warning("No residential terrace buildings found")
            return False
        if 0 == len(self._residential_apartments):
            logging.warning("No residential apartment buildings found")
            return False
        if 0 == len(self._residential_attached):
            logging.warning("No residential attached buildings found")
            return False
        if 0 == len(self._industrial_buildings_large):
            logging.warning("No large industrial buildings found")
            return False
        if 0 == len(self._industrial_buildings_small):
            logging.warning("No small industrial buildings found")
            return False
        return True


class GenBuilding:
    """An object representing a generated non-OSM building"""
    __slots__ = ('gen_id', 'shared_model', 'area_polygon', 'buffer_polygon', 'distance_to_street',
                 'x', 'y', 'angle', 'zone')

    def __init__(self, gen_id: int, shared_model: SharedModel, highway_width: float,
                 settlement_type: enu.SettlementType) -> None:
        self.gen_id = gen_id
        self.shared_model = shared_model
        self.shared_model.calc_buffers(settlement_type)
        # takes into account that ideal buffer_front is challenged in curve
        self.area_polygon = None  # A polygon representing only the building, not the buffer around
        self.buffer_polygon = None  # A polygon representing the building incl. front/back/side buffers
        self.distance_to_street = 0  # The distance from the building's midpoint to the middle of the street
        self._create_my_polygons(highway_width)
        # below location attributes are set after population
        # x/y; see building_lib.calculate_anchor -> mid-point of the front facade seen from street in local coords
        self.x = 0
        self.y = 0
        # the angle in degrees from North (y-axis) in the local coordinate system for the building's
        # static object local x-axis
        self.angle = 0
        self.zone = None  # either a BuildingZone or a CityBlock

    def _create_my_polygons(self, highway_width: float) -> None:
        """Creates buffer and area polygons at (0,0) and no angle"""
        distance_from_highway = math.pow(highway_width / 2, parameters.OWBB_HIGHWAY_WIDTH_FACTOR)
        buffer_front = self.shared_model.front_buffer
        min_buffer_front = self.shared_model.min_front_buffer
        buffer_side = self.shared_model.side_buffer
        buffer_back = self.shared_model.back_buffer

        self.buffer_polygon = box(-1*(self.shared_model.width/2 + buffer_side),
                                  distance_from_highway + (buffer_front - min_buffer_front),
                                  self.shared_model.width/2 + buffer_side,
                                  distance_from_highway + buffer_front + self.shared_model.depth + buffer_back)
        self.area_polygon = box(-1*(self.shared_model.width/2),
                                distance_from_highway + buffer_front,
                                self.shared_model.width/2,
                                distance_from_highway + buffer_front + self.shared_model.depth)

        self.distance_to_street = distance_from_highway + buffer_front

    def get_a_polygon(self, has_buffer: bool, highway_point, highway_angle):
        """
        Gets a polygon for the building and place it in relation to the point and angle of the highway.
        Depending on parameter it takes the buffer or area polygon.
        """
        if has_buffer:
            my_box = self.buffer_polygon
        else:
            my_box = self.area_polygon
        # plus 90 degrees because right side street, street along; -1 to go clockwise
        rotated_box = saf.rotate(my_box, -1 * (90 + highway_angle), (0, -1*self.shared_model.depth))

        return saf.translate(rotated_box, highway_point.x, highway_point.y)

    def set_location(self, point_on_line, angle, area_polygon, buffer_polygon):
        self.area_polygon = area_polygon
        self.buffer_polygon = buffer_polygon
        self.angle = angle + 90
        my_angle = math.radians(self.angle)
        self.x = point_on_line.x + self.distance_to_street*math.sin(my_angle)
        self.y = point_on_line.y + self.distance_to_street*math.cos(my_angle)

    def create_building_lib_building(self) -> bl.Building:
        """Creates a building_lib building to be used in actually creating the FG scenery object"""
        floor_plan = box(-1 * self.shared_model.width / 2, 0,
                         self.shared_model.width / 2, self.shared_model.depth)
        rotated = saf.rotate(floor_plan, -1 * self.angle, origin=(0, 0))
        moved = saf.translate(rotated, self.x, self.y)
        my_building = bl.Building(self.gen_id, self.shared_model.building_model.tags, moved.exterior,
                                  co.Vec2d(self.x, self.y),
                                  street_angle=self.angle, is_owbb_model=True,
                                  width=self.shared_model.width, depth=self.shared_model.depth)
        my_building.zone = self.zone
        return my_building


class TempGenBuildings:
    """Stores generated buildings temporarily before validations shows that they can be committed"""
    __slots__ = ('bounding_box', 'generated_blocked_areas', 'generated_buildings',
                 'blocked_areas_along_objects', 'blocked_areas_along_sequence')

    def __init__(self, bounding_box) -> None:
        self.bounding_box = bounding_box
        self.generated_blocked_areas = list()  # List of BlockedArea objects from temp generated buildings
        self.generated_buildings = list()  # List of GenBuildings
        # found at generation along specific highway
        self.blocked_areas_along_objects = dict()  # key=BlockedArea value=None
        self.blocked_areas_along_sequence = list()  # BlockedArea objects

    def add_generated(self, building, blocked_area):
        self.generated_blocked_areas.append(blocked_area)
        if building.area_polygon.within(self.bounding_box):
            self.generated_buildings.append(building)
        self.blocked_areas_along_objects[blocked_area] = True
        self.blocked_areas_along_sequence.append(blocked_area)

    def validate_uninterrupted_sequence(self, min_share, min_number):
        """
        First validates that the min_share is fulfilled.
        Then validates if there either only are temp. generated buildings or all generated buildings are in just
        one sequence.
        E.g. for row houses all houses should be the same - but at the street start/end there might be other houses.
        Finally validate if the number of generated buildings is at least min_number."""
        if not self.validate_min_share_generated(min_share):
            return False

        seq_started = False
        seq_stopped = False
        counter = 0
        for blocked_area in self.blocked_areas_along_sequence:
            is_temp_generated = self.blocked_areas_along_objects[blocked_area]
            if is_temp_generated:
                if not seq_started:
                    seq_started = True
                    counter += 1
                    continue
                elif seq_started:
                    counter += 1
                elif seq_stopped:
                    return 0
            elif not is_temp_generated:
                if seq_started and not seq_stopped:
                    seq_stopped = True
                    continue
        if counter < min_number:
            return False
        return True

    def validate_min_share_generated(self, min_share):
        """Returns true if the share of generated buildings is at least as large as the min_share parameter"""
        count_temp_generated = 0.0
        count_others = 0.0
        for my_bool in self.blocked_areas_along_objects.values():
            if my_bool:
                count_temp_generated += 1.0
            else:
                count_others += 1.0
        my_share = count_temp_generated + count_others
        if my_share > 0 and (count_temp_generated / my_share) >= min_share:
            return True
        return False


def process_aerodrome_refs(transformer: co.Transformation) -> List[BuildingZone]:
    osm_result = op.fetch_osm_db_data_ways_key_values([op.create_key_value_pair(s.K_AEROWAY, s.V_AERODROME)])
    my_ways = list()
    for way in list(osm_result.ways_dict.values()):
        my_way = BuildingZone.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways.append(my_way)
    logging.info("Aerodrome land-uses found: %s", len(my_ways))
    return my_ways


def process_osm_building_zone_refs(transformer: co.Transformation) -> List[BuildingZone]:
    osm_result = op.fetch_osm_db_data_ways_keys([s.K_LANDUSE])
    my_ways = list()
    for way in list(osm_result.ways_dict.values()):
        my_way = BuildingZone.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways.append(my_way)
    logging.info("OSM land-uses found: %s", len(my_ways))
    return my_ways


def process_osm_open_space_refs(transformer: co.Transformation) -> Dict[int, OpenSpace]:
    osm_result = op.fetch_osm_db_data_ways_keys(OpenSpace.REQUESTED_TAGS)
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = OpenSpace.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way is not None and my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM open spaces found: %s", len(my_ways))
    return my_ways


def process_osm_railway_refs(transformer: co.Transformation) -> Dict[int, RailwayLine]:
    # TODO: it must be possible to do this for highways and waterways abstract, as only logging, object
    # and key is different
    osm_result = op.fetch_osm_db_data_ways_keys([s.K_RAILWAY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = RailwayLine.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM railway lines found: %s", len(my_ways))
    return my_ways


def process_osm_highway_refs(transformer: co.Transformation) -> Dict[int, Highway]:
    osm_result = op.fetch_osm_db_data_ways_keys([s.K_HIGHWAY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = Highway.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM highways found: %s", len(my_ways))
    return my_ways


def process_osm_waterway_refs(transformer: co.Transformation) -> Dict[int, Waterway]:
    osm_result = op.fetch_osm_db_data_ways_keys([s.K_WATERWAY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = Waterway.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM waterways found: %s", len(my_ways))
    return my_ways


def _add_extension_to_tile_border(transformer: co.Transformation) -> None:
    x, y = transformer.to_local((parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH))
    lon, lat = transformer.to_global((x - parameters.OWBB_PLACE_TILE_BORDER_EXTENSION,
                                      y - parameters.OWBB_PLACE_TILE_BORDER_EXTENSION))
    parameters.BOUNDARY_WEST = lon
    parameters.BOUNDARY_SOUTH = lat

    x, y = transformer.to_local((parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH))
    lon, lat = transformer.to_global((x + parameters.OWBB_PLACE_TILE_BORDER_EXTENSION,
                                      y + parameters.OWBB_PLACE_TILE_BORDER_EXTENSION))
    parameters.BOUNDARY_EAST = lon
    parameters.BOUNDARY_NORTH = lat


def process_osm_place_refs(transformer: co.Transformation) -> Tuple[List[Place], List[Place]]:
    """Reads both nodes and areas from OSM, but then transforms areas to nodes.
    We trust that there is no double tagging of a place as both node and area.

    Only urban places (city, town) and farms are looked at. The rest in between (e.g. villages)
    are not taken as places.
    """
    urban_places = list()
    farm_places = list()

    key_value_pairs = list()
    for member in enu.PlaceType:
        key_value_pairs.append('place=>{}'.format(member.name))

    # temporarily change the tile border to get more places
    temp_east = parameters.BOUNDARY_EAST
    temp_west = parameters.BOUNDARY_WEST
    temp_north = parameters.BOUNDARY_NORTH
    temp_south = parameters.BOUNDARY_SOUTH

    _add_extension_to_tile_border(transformer)

    # points
    osm_nodes_dict = op.fetch_db_nodes_isolated(list(), key_value_pairs)
    for key, node in osm_nodes_dict.items():
        place = Place.create_from_node(node, transformer)
        if place.is_valid():
            if place.type_ is enu.PlaceType.farm:
                farm_places.append(place)
            else:
                urban_places.append(place)
    # areas
    osm_way_result = op.fetch_osm_db_data_ways_key_values(key_value_pairs)
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict
    for key, way in osm_ways_dict.items():
        place = Place.create_from_way(way, osm_nodes_dict, transformer)
        if place.is_valid():
            if place.type_ is enu.PlaceType.farm:
                farm_places.append(place)
            else:
                place.transform_to_point()
                urban_places.append(place)

    # relations
    osm_relations_result = op.fetch_osm_db_data_relations_places(osm_way_result)
    osm_relations_dict = osm_relations_result.relations_dict
    osm_nodes_dict = osm_relations_result.rel_nodes_dict
    osm_rel_ways_dict = osm_relations_result.rel_ways_dict

    for _, relation in osm_relations_dict.items():
        largest_area = None  # in case there are several polygons in the relation, we just keep the largest
        outer_ways = list()
        for member in relation.members:
            if member.type_ == s.V_WAY and member.role == s.V_OUTER and member.ref in osm_rel_ways_dict:
                way = osm_rel_ways_dict[member.ref]
                outer_ways.append(way)

        outer_ways = op.closed_ways_from_multiple_ways(outer_ways)
        for way in outer_ways:
            polygon = way.polygon_from_osm_way(osm_nodes_dict, transformer)
            if polygon is not None and polygon.is_valid and not polygon.is_empty:
                if largest_area is None:
                    largest_area = polygon
                else:
                    if largest_area.area < polygon.area:
                        largest_area = polygon

        if largest_area is not None:
            my_place = Place(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse), largest_area.centroid,
                             enu.PlaceType.city, True)
            my_place.parse_tags(relation.tags)
            my_place.parse_tags_additional(relation.tags)
            if my_place.is_valid():
                urban_places.append(my_place)

    logging.info("Number of valid places found: urban={}, farm={}".format(len(urban_places), len(farm_places)))

    # change the tile border back
    parameters.BOUNDARY_EAST = temp_east
    parameters.BOUNDARY_WEST = temp_west
    parameters.BOUNDARY_NORTH = temp_north
    parameters.BOUNDARY_SOUTH = temp_south

    return urban_places, farm_places
