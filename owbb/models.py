# -*- coding: utf-8 -*-
"""Objects and enumerations used as models across the owbb package.

Stored in its own module to minimize circular references and separate processing from data.
"""


import abc
from enum import IntEnum, unique
import logging
import math
from typing import Dict, List, Optional, Tuple, Union

from shapely.geometry import box, Point, LineString, Polygon, MultiPolygon
import shapely.affinity as saf

import building_lib
import parameters
import utils.osmparser as op
import utils.coordinates as co


# type aliases
KeyValueDict = Dict[str, str]
MPoly = Union[Polygon, MultiPolygon]

BUILDING_KEY = 'building'
BUILDING_PART_KEY = 'building:part'
LANDUSE_KEY = 'landuse'
PLACE_KEY = 'place'
RAILWAY_KEY = 'railway'
HIGHWAY_KEY = 'highway'
WATERWAY_KEY = 'waterway'


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


@unique
class PlaceType(IntEnum):
    """See https://wiki.openstreetmap.org/wiki/Key:place - only used for city and town as well as farm.
    Rest is ignored - including:
    * isolated_dwelling and allotments -> too small
    * borough: administrative and very few mappings
    * quarter; not used much in OSM and might be better off just using neighbourhood in osm2city
    * city_block and plot: too small
    """
    city = 10
    town = 20
    farm = 50  # only type allowed to remain as area as it is used to recognize land-use type


class Place(OSMFeature):
    """ A 'Places' OSM Map Feature
    A Place can either be of element type Node -> Point geometry or Way -> Area -> LinearString
    There are a few in relations, but so few that it will not be modelled.
    Cf. http://wiki.openstreetmap.org/wiki/Key:place
    Cf. http://wiki.openstreetmap.org/wiki/Map_Features#Places
    """

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

    def parse_tags_additional(self, tags_dict: KeyValueDict) -> None:
        if "population" in tags_dict:
            self.population = op.parse_int(tags_dict["population"], 0)
        if "name" in tags_dict:
            self.name = tags_dict["name"]
        elif "place_name" in tags_dict:  # only use it if name was not included
            self.name = tags_dict["place_name"]

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, PlaceType]:
        value = tags_dict["place"]
        for member in PlaceType:
            if value == member.name:
                return member
        return None

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
        if self.type_ is PlaceType.farm:
            logging.debug('Attempted to transform Place of type farm from area to point')
            return
        self.is_point = True
        self.geometry = self.geometry.centroid

    def _calculate_circle_radius(self, population: int, power: float) -> float:
        radius = math.pow(population, power)
        if self.type_ is PlaceType.city:
            radius *= parameters.OWBB_PLACE_RADIUS_FACTOR_CITY
        else:
            radius *= parameters.OWBB_PLACE_RADIUS_FACTOR_TOWN
        return radius

    def create_settlement_type_circles(self) -> Tuple[Polygon, Polygon, Polygon]:
        population = self.population
        if population == 0:
            if self.type_ is PlaceType.city:
                population = parameters.OWBB_PLACE_POPULATION_DEFAULT_CITY
            else:
                population = parameters.OWBB_PLACE_POPULATION_DEFAULT_TOWN
        centre_circle = Polygon()
        if self.type_ is PlaceType.city:
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_CENTRE)
            centre_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_BLOCK)
            block_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_DENSE)
            dense_circle = self.geometry.buffer(radius)
        else:
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_BLOCK)
            block_circle = self.geometry.buffer(radius)
            radius = self._calculate_circle_radius(population, parameters.OWBB_PLACE_RADIUS_EXPONENT_DENSE)
            dense_circle = self.geometry.buffer(radius)
        return centre_circle, block_circle, dense_circle


@unique
class SettlementType(IntEnum):
    """Only assigned to city blocks, not building zones."""
    centre = 1
    block = 2
    dense = 3
    periphery = 4  # default within lit area
    rural = 5  # only implicitly used for building zones without city blocks.


class SettlementCluster:
    """A polygon based on lit_area representing a settlement cluster.
    Built-up areas can sprawl and a coherent area can contain several cities and towns."""
    def __init__(self, linked_places: List[Place], geometry: Polygon) -> None:
        self.linked_places = linked_places
        self.geometry = geometry


class OSMFeatureArea(OSMFeature):
    def __init__(self, osm_id: int, geometry: MPoly, feature_type: Union[None, IntEnum]) -> None:
        super().__init__(osm_id, geometry, feature_type)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'OSMFeatureArea':
        raise NotImplementedError("Please implement this method")


@unique
class BuildingClass(IntEnum):
    """Used to classify buildings for processing on zone level"""
    default = 10
    residential = 100
    residential_small = 110
    commercial = 200
    industrial = 300
    retail = 400
    parking_house = 1000
    religion = 2000
    public = 3000
    farm = 4000
    airport = 5000


@unique
class BuildingType(IntEnum):
    """Mostly match value of a tag with k=building"""
    yes = 1  # default
    parking = 10  # k="parking" v="multi-storey"
    apartments = 21
    house = 22
    detached = 23
    residential = 24
    dormitory = 25
    terrace = 26
    bungalow = 31
    static_caravan = 32
    cabin = 33
    hut = 34
    commercial = 41
    office = 42
    retail = 51
    industrial = 61
    warehouse = 62
    cathedral = 71
    chapel = 72
    church = 73
    mosque = 74
    temple = 75
    synagogue = 76
    public = 81
    civic = 82
    school = 83
    hospital = 84
    hotel = 85
    kiosk = 86
    farm = 91
    barn = 92
    cowshed = 93
    farm_auxiliary = 94
    greenhouse = 95
    stable = 96
    sty = 97
    riding_hall = 98
    hangar = 100


def parse_building_tags_for_type(tags_dict: KeyValueDict) -> Union[None, BuildingType]:
    if ("parking" in tags_dict) and (tags_dict["parking"] == "multi-storey"):
        return BuildingType.parking
    else:
        value = None
        if BUILDING_KEY in tags_dict:
            value = tags_dict[BUILDING_KEY]
        elif BUILDING_PART_KEY in tags_dict:
            value = tags_dict[BUILDING_PART_KEY]
        if value is not None:
            for member in BuildingType:
                if value == member.name:
                    return member
            return BuildingType.yes
    return None


def get_building_class(building: building_lib.Building) -> BuildingClass:
    type_ = parse_building_tags_for_type(building.tags)
    if type_ in [BuildingType.apartments, BuildingType.house, BuildingType.detached,
                      BuildingType.residential, BuildingType.dormitory, BuildingType.terrace]:
        return BuildingClass.residential
    elif type_ in [BuildingType.bungalow, BuildingType.static_caravan, BuildingType.cabin, BuildingType.hut]:
        return BuildingClass.residential_small
    elif type_ in [BuildingType.commercial, BuildingType.office]:
        return BuildingClass.commercial
    elif type_ in [BuildingType.retail]:
        return BuildingClass.retail
    elif type_ in [BuildingType.industrial, BuildingType.warehouse]:
        return BuildingClass.industrial
    elif type_ in [BuildingType.parking]:
        return BuildingClass.parking_house
    elif type_ in [BuildingType.cathedral, BuildingType.chapel, BuildingType.church,
                        BuildingType.mosque, BuildingType.temple, BuildingType.synagogue]:
        return BuildingClass.religion
    elif type_ in [BuildingType.public, BuildingType.civic, BuildingType.school, BuildingType.hospital,
                        BuildingType.hotel, BuildingType.kiosk]:
        return BuildingClass.public
    elif type_ in [BuildingType.farm, BuildingType.barn, BuildingType.cowshed, BuildingType.farm_auxiliary,
                        BuildingType.greenhouse, BuildingType.stable, BuildingType.sty, BuildingType.riding_hall]:
        return BuildingClass.farm
    elif type_ in [BuildingType.hangar]:
        return BuildingClass.airport
    return BuildingClass.default


@unique
class BuildingZoneType(IntEnum):  # element names must match OSM values apart from non_osm
    residential = 10
    commercial = 20
    industrial = 30
    retail = 40
    farmyard = 50  # for generated land-use zones this is not correctly applied, as several farmyards might be
    # interpreted as one. See GeneratedBuildingZone.guess_building_zone_type
    port = 60

    non_osm = 100  # used for land-uses constructed with heuristics and not in original data from OSM


class CityBlock:
    """A special land-use derived from many kinds of land-use info and enclosed by streets (kind of)."""
    def __init__(self, osm_id: int, geometry: Polygon, feature_type: Union[None, BuildingZoneType]) -> None:
        self.osm_id = osm_id
        self.geometry = geometry
        self.building_zone_type = feature_type
        self.osm_buildings = list()  # List of already existing osm buildings
        self.settlement_type = SettlementType.periphery


class BuildingZone(OSMFeatureArea):
    """ A 'Landuse' OSM map feature
    A Landuse can either be of element type Node -> Point geometry or Way -> Area -> LinearString.
    However only areas are of interest.
    Also only those land-uses are mapped here, which specify a zoning type used in town planning for buildings.
    Other landuse OSM map features are handled in class BlockedArea.
    Cf. http://wiki.openstreetmap.org/wiki/Landuse
    Cf. http://wiki.openstreetmap.org/wiki/Map_Features#Landuse
    """
    def __init__(self, osm_id: int, geometry: MPoly, feature_type: Union[None, BuildingZoneType]) -> None:
        super().__init__(osm_id, geometry, feature_type)

        # the following fields are only used for generating would be buildings
        # i.e. they are not directly based on OSM data
        self.linked_blocked_areas = list()  # List of BlockedArea objects for blocked areas.
        self.osm_buildings = list()  # List of already existing osm buildings
        self.generated_buildings = list()  # List of GenBuilding objects for generated non-osm buildings
        self.linked_genways = list()  # List of Highways that are available for generating buildings
        self.linked_city_blocks = list()

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'BuildingZone':
        my_geometry = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
        feature_type = cls.parse_tags(way.tags)
        obj = BuildingZone(way.osm_id, my_geometry, feature_type)
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, BuildingZoneType]:
        value = tags_dict[LANDUSE_KEY]
        for member in BuildingZoneType:
            if value == member.name:
                return member
        return None

    @staticmethod
    def is_building_zone_value(value: str) -> bool:
        for member in BuildingZoneType:
            if value == member.name:
                return True
        return False

    def get_osm_value(self) -> str:
        return self.type_.name

    def commit_temp_gen_buildings(self, temp_buildings) -> None:  # temp_buildings: TempGenBuildings circular
        """Commits a set of generated buildings to be definitively be part of a BuildingZone"""
        self.linked_blocked_areas.extend(temp_buildings.generated_blocked_areas)
        self.generated_buildings.extend(temp_buildings.generated_buildings)

    def add_city_block(self, city_block: CityBlock) -> None:
        self.linked_city_blocks.append(city_block)

    def reassign_osm_buildings_to_city_blocks(self) -> None:
        for osm_building in self.osm_buildings:
            for city_block in self.linked_city_blocks:
                if osm_building.geometry.within(city_block.geometry) or osm_building.geometry.intersects(
                        city_block.geometry):
                    city_block.osm_buildings.append(osm_building)


class GeneratedBuildingZone(BuildingZone):
    """A fake OSM Land-use for buildings based on heuristics"""
    def __init__(self, generated_id, geometry, building_zone_type, from_buildings=False) -> None:
        super().__init__(generated_id, geometry, building_zone_type)
        self.from_buildings = from_buildings  # False for e.g. external land-use

    def guess_building_zone_type(self, farm_places: List[Place]):
        """Based on some heuristics of linked buildings guess the building zone type"""
        residential_buildings = 0
        commercial_buildings = 0
        industrial_buildings = 0
        retail_buildings = 0
        farm_buildings = 0
        for building in self.osm_buildings:
            building_class = get_building_class(building)
            if building_class in [BuildingClass.residential_small or BuildingClass.residential]:
                residential_buildings += 1
            elif building_class == BuildingClass.commercial:
                commercial_buildings += 1
            elif building_class == BuildingClass.industrial:
                industrial_buildings += 1
            elif building_class == BuildingClass.retail:
                retail_buildings += 1
            elif building_class == BuildingClass.farm:
                farm_buildings += 1

        guessed_type = BuildingZoneType.residential  # default
        max_value = max([residential_buildings, commercial_buildings, industrial_buildings, retail_buildings,
                         farm_buildings])
        if 0 < max_value:
            if len(self.osm_buildings) < 10:
                logging.debug("Checking generated land-use for place=farm based on %d place tags", len(farm_places))
                for my_place in farm_places:
                    if my_place.is_point:
                        if my_place.geometry.within(self.geometry):
                            self.type_ = BuildingZoneType.farmyard
                            farm_places.remove(my_place)
                            logging.debug("Found one based on node place")
                            return
                    else:
                        if my_place.geometry.intersects(self.geometry):
                            self.type_ = BuildingZoneType.farmyard
                            farm_places.remove(my_place)
                            logging.debug("Found one based on area place")
                            return
            if farm_buildings == max_value:  # in small villages farm houses might be tagged, but rest just ="yes"
                if (len(self.osm_buildings) >= 10) and (farm_buildings < int(0.5*len(self.osm_buildings))):
                    guessed_type = BuildingZoneType.residential
                else:
                    guessed_type = BuildingZoneType.farmyard
            elif commercial_buildings == max_value:
                guessed_type = BuildingZoneType.commercial
            elif industrial_buildings == max_value:
                guessed_type = BuildingZoneType.industrial
            elif retail_buildings == max_value:
                guessed_type = BuildingZoneType.retail

        self.type_ = guessed_type


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
        if parse_building_tags_for_type(tags_dict) is not None:
            return None
        elif "public_transport" in tags_dict:
            return OpenSpaceType.transport
        elif ("railway" in tags_dict) and (tags_dict["railway"] == "station"):
            return OpenSpaceType.transport
        elif LANDUSE_KEY in tags_dict:  # must be in sync with BuildingZone
            if tags_dict[LANDUSE_KEY] == "railway":
                return OpenSpaceType.transport
            elif BuildingZone.is_building_zone_value(tags_dict[LANDUSE_KEY]):
                return None
            else:
                return OpenSpaceType.landuse
        elif "amenity" in tags_dict:
            if tags_dict["amenity"] in ["grave_yard", "parking"]:
                return OpenSpaceType.amenity
        elif "leisure" in tags_dict:
            return OpenSpaceType.leisure
        elif "natural" in tags_dict:
            return OpenSpaceType.natural
        elif "highway" in tags_dict:
            if tags_dict["highway"] == "pedestrian":
                if ("area" in tags_dict) and (tags_dict["area"] == "yes"):
                    return OpenSpaceType.pedestrian
        return None


class OSMFeatureLinear(OSMFeature):
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
        return "embankment" in tags_dict or "cutting" in tags_dict

    @staticmethod
    def _parse_tags_tunnel(tags_dict: KeyValueDict) -> bool:
        """If this is tagged with tunnel, then _type = None.
        Thereby the object is invalid and will not be added. Because tunnels do not interfere with buildings.
        """
        if ("tunnel" in tags_dict) and (tags_dict["tunnel"] == "yes"):
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
        value = tags_dict[WATERWAY_KEY]
        if value in ["river", "canal"]:
            return WaterwayType.large
        elif value in ["stream", "wadi", "drain", "ditch"]:
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
    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.tracks = self._parse_tags_tracks(tags_dict)
        self.is_service_spur = self._parse_tags_service_spur(tags_dict)

    @staticmethod
    def _parse_tags_tracks(tags_dict: KeyValueDict) -> int:
        my_tracks = 1
        if "tracks" in tags_dict:
            my_tracks = op.parse_int(tags_dict["tracks"], 1)
        return my_tracks

    @staticmethod
    def _parse_tags_service_spur(tags_dict: KeyValueDict) -> bool:
        if "service" in tags_dict and tags_dict["service"] == "spur":
            return True
        return False

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[RailwayLineType, None]:
        value = tags_dict[RAILWAY_KEY]
        if value == "rail":
            return RailwayLineType.rail
        elif value == "subway":
            return RailwayLineType.subway
        elif value == "monorail":
            return RailwayLineType.monorail
        elif value == "light_rail":
            return RailwayLineType.light_rail
        elif value == "funicular":
            return RailwayLineType.funicular
        elif value == "narrow_gauge":
            return RailwayLineType.narrow_gauge
        elif value == "tram":
            return RailwayLineType.tram
        elif value in ["abandoned", "construction", "disused", "preserved"]:
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


@unique
class HighwayType(IntEnum):
    motorway = 11
    trunk = 12
    primary = 13
    secondary = 14
    tertiary = 15
    unclassified = 16
    road = 17
    residential = 18
    living_street = 19
    service = 20
    pedestrian = 21
    slow = 30  # cycle ways, tracks, footpaths etc


class Highway(OSMFeatureLinearWithTunnel):
    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict, refs: List[int]) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.is_roundabout = self._parse_tags_roundabout(tags_dict)
        self.is_oneway = self._parse_tags_oneway(tags_dict)
        self.lanes = self._parse_tags_lanes(tags_dict)
        self.refs = refs

    @classmethod
    def create_from_scratch(cls, pseudo_id: int, existing_highway: 'Highway', linear: LineString) -> 'Highway':
        obj = Highway(pseudo_id, linear, dict(), existing_highway.refs)
        obj.type_ = existing_highway.type_
        obj.is_roundabout = existing_highway.is_roundabout
        obj.is_oneway = existing_highway.is_oneway
        obj.lanes = existing_highway.lanes
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, HighwayType]:
        if HIGHWAY_KEY in tags_dict:
            value = tags_dict[HIGHWAY_KEY]
            if value in ["motorway", "motorway_link"]:
                return HighwayType.motorway
            elif value in ["trunk", "trunk_link"]:
                return HighwayType.trunk
            elif value in ["primary", "primary_link"]:
                return HighwayType.primary
            elif value in ["secondary", "secondary_link"]:
                return HighwayType.secondary
            elif value in ["tertiary", "tertiary_link"]:
                return HighwayType.tertiary
            elif value == "unclassified":
                return HighwayType.unclassified
            elif value == "road":
                return HighwayType.road
            elif value == "residential":
                return HighwayType.residential
            elif value == "living_street":
                return HighwayType.living_street
            elif value == "service":
                return HighwayType.service
            elif value == "pedestrian":
                return HighwayType.pedestrian
            elif value in ["tack", "footway", "cycleway", "bridleway", "steps", "path"]:
                return HighwayType.slow
            return None

    @staticmethod
    def _parse_tags_roundabout(tags_dict: KeyValueDict) -> bool:
        if ("junction" in tags_dict) and (tags_dict["junction"] == "roundabout"):
            return True
        return False

    def _parse_tags_oneway(self, tags_dict: KeyValueDict) -> bool:
        if self.type_ == HighwayType.motorway:
            if ("oneway" in tags_dict) and (tags_dict["oneway"] == "no"):
                return False
            else:
                return True  # in motorways oneway is implied
        elif ("oneway" in tags_dict) and (tags_dict["oneway"] == "yes"):
            return True
        return False

    @staticmethod
    def _parse_tags_lanes(tags_dict: KeyValueDict) -> int:
        my_lanes = 1
        if "lanes" in tags_dict:
            my_lanes = op.parse_int(tags_dict["lanes"], 1)
        return my_lanes

    def get_width(self) -> float:  # FIXME: replace with parameters
        if self.type_ in [HighwayType.service, HighwayType.residential, HighwayType.living_street,
                          HighwayType.pedestrian]:
            my_width = 5.0
        elif self.type_ in [HighwayType.road, HighwayType.unclassified, HighwayType.tertiary]:
            my_width = 6.0
        elif self.type_ in [HighwayType.secondary, HighwayType.primary, HighwayType.trunk]:
            my_width = 7.0
        elif self.type_ in [HighwayType.motorway]:
            my_width = 12.0  # motorway is tagged for each direction. Assuming 2 lanes plus emergency lane
        else:  # HighwayType.slow
            my_width = 3.0

        if self.type_ == HighwayType.motorway:
            if self.lanes > 2:
                my_width += 3.5*(self.lanes-2)
            if not self.is_oneway:
                my_width *= 1.75
        else:
            if self.lanes > 1:
                my_width += 0.8*(self.lanes-1)*my_width
            if self.is_oneway:
                my_width *= 0.6
        if self.has_embankment:
            my_width += 6.0
        # FIXME: has sidewalk (K=sidewalk, v=both / left / right / no)
        return my_width

    def is_sideway(self) -> bool:
        """Not a main street in an urban area. I.e. residential, walking or service"""
        return self.type_ < HighwayType.road

    def populate_buildings_along(self) -> bool:
        """The type of highway determines where buildings are built. E.g. motorway would be false"""
        return self.type_ not in (HighwayType.motorway, HighwayType.trunk)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'Highway':
        my_geometry = cls.create_line_string_from_way(way, nodes_dict, transformer)
        obj = Highway(way.osm_id, my_geometry, way.tags, way.refs)
        return obj


@unique
class BlockedAreaType(IntEnum):
    osm_building = 1
    gen_building = 2
    open_space = 3
    highway = 11
    waterway = 12
    railway = 13


class BlockedArea(object):
    """An object representing a specific type of blocked area - blocked for new generated buildings"""
    def __init__(self, type_: BlockedAreaType, polygon: Polygon, original_type=None) -> None:
        self.type_ = type_
        self.polygon = polygon
        self.original_type = original_type


class BuildingModel(object):
    """A model of a building used to replace OSM buildings or create buildings where there could be a building.

    The center of the building is strictly in the middle of width/depth.
    All geometry information is either in the AC3D model or in tags.

    Tags contains e.g. roof type, number of levels etc. according to OSM tagging."""

    def __init__(self, width: float, depth: float, model_type: BuildingType, regions: List[str], model: Optional[str],
                 facade_id: int, roof_id: int, tags: KeyValueDict) -> None:
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
    def __init__(self, building_model: BuildingModel, building_type: BuildingType) -> None:
        self.building_model = building_model
        self.type_ = building_type
        self._front_buffer = 0
        self._back_buffer = 0
        self._side_buffer = 0
        self._calc_buffers()

    def _calc_buffers(self) -> None:
        if self.type_ is BuildingType.detached:
            front_min = parameters.OWBB_RESIDENTIAL_HOUSE_FRONT_MIN
            front_max = parameters.OWBB_RESIDENTIAL_HOUSE_FRONT_MAX
            back_min = parameters.OWBB_RESIDENTIAL_HOUSE_BACK_MIN
            back_max = parameters.OWBB_RESIDENTIAL_HOUSE_BACK_MAX
            side_min = parameters.OWBB_RESIDENTIAL_HOUSE_SIDE_MIN
            side_max = parameters.OWBB_RESIDENTIAL_HOUSE_SIDE_MAX
        elif self.type_ is BuildingType.terrace:
            front_min = parameters.OWBB_RESIDENTIAL_TERRACE_FRONT_MIN
            front_max = parameters.OWBB_RESIDENTIAL_TERRACE_FRONT_MAX
            back_min = parameters.OWBB_RESIDENTIAL_TERRACE_BACK_MIN
            back_max = parameters.OWBB_RESIDENTIAL_TERRACE_BACK_MAX
            side_min = parameters.OWBB_RESIDENTIAL_TERRACE_SIDE_MIN
            side_max = parameters.OWBB_RESIDENTIAL_TERRACE_SIDE_MAX
        else:
            front_min = parameters.OWBB_INDUSTRIAL_BUILDING_FRONT_MIN
            front_max = parameters.OWBB_INDUSTRIAL_BUILDING_FRONT_MIN
            back_min = parameters.OWBB_INDUSTRIAL_BUILDING_BACK_MIN
            back_max = parameters.OWBB_INDUSTRIAL_BUILDING_BACK_MIN
            side_min = parameters.OWBB_INDUSTRIAL_BUILDING_SIDE_MIN
            side_max = parameters.OWBB_INDUSTRIAL_BUILDING_SIDE_MIN
        my_buffer = self.width/2 + math.sqrt(self.width)
        if my_buffer < front_min:
            my_buffer = front_min
        if my_buffer > front_max:
            my_buffer = front_max
        self._front_buffer = my_buffer

        my_buffer = self.width/2 + math.sqrt(self.width)
        if my_buffer < back_min:
            my_buffer = back_min
        if my_buffer > back_max:
            my_buffer = back_max
        self._back_buffer = my_buffer

        my_buffer = self.width/2 + math.sqrt(self.width)
        if my_buffer < side_min:
            my_buffer = side_min
        if my_buffer > side_max:
            my_buffer = side_max
        self._side_buffer = my_buffer

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
        """The absolute minimal distance tolerable, e.g. in a curve at the edges of the lot"""
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

    @property
    def world_model(self):
        return self.building_model.model


class SharedModelsLibrary(object):

    INDUSTRIAL_LARGE_MIN_AREA = 500  # FIXME: should be a parameter

    def __init__(self, building_models: List[BuildingModel]):
        self._residential_detached = list()
        self._residential_terraces = list()
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
    def industrial_buildings_large(self):
        return self._industrial_buildings_large

    @property
    def industrial_buildings_small(self):
        return self._industrial_buildings_small

    def _populate_models_library(self, building_models: List[BuildingModel]) -> None:
        for building_model in building_models:
            if building_model.model_type is BuildingType.residential:
                pass  # FIXME: should somehow be translated based on parameters to apartments, detached, terrace, etc.
            elif building_model.model_type is BuildingType.detached:
                my_model = SharedModel(building_model, BuildingType.detached)
                self._residential_detached.append(my_model)

            elif building_model.model_type is BuildingType.terrace:
                my_model = SharedModel(building_model, BuildingType.terrace)
                self._residential_terraces.append(my_model)
            elif building_model.model_type is BuildingType.industrial:
                my_model = SharedModel(building_model, BuildingType.industrial)
                if building_model.area > self.INDUSTRIAL_LARGE_MIN_AREA:
                    self._industrial_buildings_large.append(my_model)
                else:
                    self._industrial_buildings_small.append(my_model)

    def is_valid(self) -> bool:
        if 0 == len(self._residential_detached):
            logging.warning("No residential detached buildings found")
            return False
        if 0 == len(self._residential_terraces):
            logging.warning("No residential terrace buildings found")
            return False
        if 0 == len(self._industrial_buildings_large):
            logging.warning("No large industrial buildings found")
            return False
        if 0 == len(self._industrial_buildings_small):
            logging.warning("No small industrial buildings found")
            return False
        return True


class GenBuilding(object):
    """An object representing a generated non-OSM building"""
    def __init__(self, gen_id: int, shared_model: SharedModel, highway_width: float) -> None:
        self.gen_id = gen_id
        self.shared_model = shared_model
        # takes into account that ideal buffer_front is challenged in curve
        self.area_polygon = None  # A polygon representing only the building, not the buffer around
        self.buffer_polygon = None  # A polygon representing the building incl. front/back/side buffers
        self.distance_to_street = 0  # The distance from the building's midpoint to the middle of the street
        self._create_area_polygons(highway_width)
        # below location attributes are set after population
        self.x = 0  # the x coordinate of the mid-point in relation to the local coordinate system
        self.y = 0  # the y coordinate of the mid-point in relation to the local coordinate system
        self.angle = 0  # the angle in degrees from North (y-axis) in the local coordinate system for the building's
                        # static object local x-axis

    def _create_area_polygons(self, highway_width: float) -> None:
        """Creates polygons at (0,0) and no angle"""
        buffer_front = self.shared_model.front_buffer
        min_buffer_front = self.shared_model.min_front_buffer
        buffer_side = self.shared_model.side_buffer
        buffer_back = self.shared_model.back_buffer

        self.buffer_polygon = box(-1*(self.shared_model.width/2 + buffer_side),
                                  highway_width/2 + (buffer_front - min_buffer_front),
                                  self.shared_model.width/2 + buffer_side,
                                  highway_width/2 + buffer_front + self.shared_model.depth + buffer_back)
        self.area_polygon = box(-1*(self.shared_model.width/2),
                                highway_width/2 + buffer_front,
                                self.shared_model.width/2,
                                highway_width/2 + buffer_front + self.shared_model.depth)

        self.distance_to_street = highway_width/2 + buffer_front + self.shared_model.depth/2

    def get_area_polygon(self, has_buffer, highway_point, highway_angle):
        """
        Create a polygon for the building and place it in relation to the point and angle of the highway.
        """
        if has_buffer:
            my_box = self.buffer_polygon
        else:
            my_box = self.area_polygon
        rotated_box = saf.rotate(my_box, -1 * (90 + highway_angle), (0, 0))  # plus 90 degrees because right side of
                                                                             # street along; -1 to go clockwise
        return saf.translate(rotated_box, highway_point.x, highway_point.y)

    def set_location(self, point_on_line, angle, area_polygon, buffer_polygon):
        self.area_polygon = area_polygon
        self.buffer_polygon = buffer_polygon
        self.angle = angle
        my_angle = math.radians(angle+90)  # angle plus 90 because the angle is along the street, not square from street
        self.x = point_on_line.x + self.distance_to_street*math.sin(my_angle)
        self.y = point_on_line.y + self.distance_to_street*math.cos(my_angle)

    def create_building_lib_building(self) -> building_lib.Building:
        """Creates a building_lib building to be used in actually creating the FG scenery object"""
        floor_plan = box(-1 * self.shared_model.width / 2, -1 * self.shared_model.depth / 2,
                         self.shared_model.width / 2, self.shared_model.depth / 2)
        rotated = saf.rotate(floor_plan, -1 * self.angle, origin=(0, 0))
        moved = saf.translate(rotated, self.x, self.y)
        my_building = building_lib.Building(self.gen_id, self.shared_model.building_model.tags,
                                            moved.exterior, '')
        return my_building


class TempGenBuildings(object):
    """Stores generated buildings temporarily before validations shows that they can be committed"""
    def __init__(self, bounding_box) -> None:
        self.bounding_box = bounding_box
        self.generated_blocked_areas = list()  # List of BlockedArea objects from temp generated buildings
        self.generated_buildings = list()  # List of GenBuildings
        self.blocked_areas_along_objects = dict()  # key=BlockedArea value=None found during generation along specific highway
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


def process_osm_building_zone_refs(transformer: co.Transformation) -> List[BuildingZone]:
    osm_result = op.fetch_osm_db_data_ways_keys([LANDUSE_KEY])
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
    osm_result = op.fetch_osm_db_data_ways_keys([RAILWAY_KEY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = RailwayLine.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM railway lines found: %s", len(my_ways))
    return my_ways


def process_osm_highway_refs(transformer: co.Transformation) -> Tuple[Dict[int, Highway], Dict[int, op.Node]]:
    osm_result = op.fetch_osm_db_data_ways_keys([HIGHWAY_KEY])
    my_ways = dict()
    for way in list(osm_result.ways_dict.values()):
        my_way = Highway.create_from_way(way, osm_result.nodes_dict, transformer)
        if my_way.is_valid():
            my_ways[my_way.osm_id] = my_way
    logging.info("OSM highways found: %s", len(my_ways))
    return my_ways, osm_result.nodes_dict


def process_osm_waterway_refs(transformer: co.Transformation) -> Dict[int, Waterway]:
    osm_result = op.fetch_osm_db_data_ways_keys([WATERWAY_KEY])
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
    """
    urban_places = list()
    farm_places = list()

    key_value_pairs = list()
    for member in PlaceType:
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
            if place.type_ is PlaceType.farm:
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
            if place.type_ is PlaceType.farm:
                farm_places.append(place)
            else:
                place.transform_to_point()
                urban_places.append(place)

    # relations
    osm_relations_result = op.fetch_osm_db_data_relations_keys(osm_way_result, True)
    osm_relations_dict = osm_relations_result.relations_dict
    osm_nodes_dict = osm_relations_result.rel_nodes_dict
    osm_rel_ways_dict = osm_relations_result.rel_ways_dict

    for _, relation in osm_relations_dict.items():
        largest_area = None  # in case there are several polygons in the relation, we just keep the largest
        outer_ways = list()
        for member in relation.members:
            if member.type_ == 'way' and member.role == 'outer' and member.ref in osm_rel_ways_dict:
                way = osm_rel_ways_dict[member.ref]
                outer_ways.append(way)

        outer_ways = op.closed_ways_from_multiple_ways(outer_ways)
        for way in outer_ways:
            polygon = way.polygon_from_osm_way(osm_nodes_dict, transformer)
            if polygon.is_valid and not polygon.is_empty:
                if largest_area is None:
                    largest_area = polygon
                else:
                    if largest_area.area < polygon.area:
                        largest_area = polygon

        if largest_area is not None:
            my_place = Place(op.get_next_pseudo_osm_id(op.OSMFeatureType.landuse), largest_area.centroid,
                             PlaceType.city, True)
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
