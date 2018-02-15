# -*- coding: utf-8 -*-
"""Objects and enumerations used as models across the owbb package.

Stored in its own module to minimize circular references and separate processing from data.
"""


import abc
from enum import IntEnum, unique
import logging
import math
from typing import Dict, List, Union

from shapely.geometry import Point, LineString, Polygon, MultiPolygon

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
    city = 10
    borough = 11
    suburb = 12
    quarter = 13
    neighbourhood = 14
    city_block = 15
    town = 20
    village = 30
    hamlet = 40
    farm = 50


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
        if value == "city":
            return PlaceType.city
        elif value == "borough":
            return PlaceType.borough
        elif value == "suburb":
            return PlaceType.suburb
        elif value == "quarter":
            return PlaceType.quarter
        elif value == "neighbourhood":
            return PlaceType.neighbourhood
        elif value == "city_block":
            return PlaceType.city_block
        elif value == "town":
            return PlaceType.town
        elif value == "village":
            return PlaceType.village
        elif value == "hamlet":
            return PlaceType.hamlet
        elif value == "farm":
            return PlaceType.farm
        else:
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
    hangar = 100

    # World-Models cases
    # agriculture = 10
    # airport = 11
    # supermarkets = 18


class Building(OSMFeatureArea):
    """A generic building.
    """
    def __init__(self, osm_id: int, geometry: MPoly, feature_type, levels: int):
        super().__init__(osm_id, geometry, feature_type)
        self.levels = levels

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        my_coord_transformator: co.Transformation) -> 'Building':
        my_geometry = way.polygon_from_osm_way(nodes_dict, my_coord_transformator)
        feature_type = cls.parse_tags(way.tags)
        if "building:levels" in way.tags:
            levels = op.parse_int(way.tags["building:levels"], 0)
        else:
            levels = 0
        obj = Building(way.osm_id, my_geometry, feature_type, levels)
        return obj

    @staticmethod
    def parse_tags(tags_dict: KeyValueDict) -> Union[None, BuildingType]:
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

    def get_building_class(self) -> BuildingClass:
        if self.type_ in [BuildingType.apartments, BuildingType.house, BuildingType.detached,
                          BuildingType.residential, BuildingType.dormitory, BuildingType.terrace]:
            return BuildingClass.residential
        elif self.type_ in [BuildingType.bungalow, BuildingType.static_caravan, BuildingType.cabin, BuildingType.hut]:
            return BuildingClass.residential_small
        elif self.type_ in [BuildingType.commercial, BuildingType.office]:
            return BuildingClass.commercial
        elif self.type_ in [BuildingType.retail]:
            return BuildingClass.retail
        elif self.type_ in [BuildingType.industrial, BuildingType.warehouse]:
            return BuildingClass.industrial
        elif self.type_ in [BuildingType.parking]:
            return BuildingClass.parking_house
        elif self.type_ in [BuildingType.cathedral, BuildingType.chapel, BuildingType.church,
                            BuildingType.mosque, BuildingType.temple, BuildingType.synagogue]:
            return BuildingClass.religion
        elif self.type_ in [BuildingType.public, BuildingType.civic, BuildingType.school, BuildingType.hospital,
                            BuildingType.hotel, BuildingType.kiosk]:
            return BuildingClass.public
        elif self.type_ in [BuildingType.farm, BuildingType.barn, BuildingType.cowshed, BuildingType.farm_auxiliary,
                            BuildingType.greenhouse, BuildingType.stable, BuildingType.sty]:
            return BuildingClass.farm
        elif self.type_ in [BuildingType.hangar]:
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

    non_osm = 100  # used for land-uses constructed with heuristics and not in original data from OSM

    # FlightGear in BTG files
    # must be in line with SUPPORTED_MATERIALS in btg_io.py (except from water)
    btg_builtupcover = 201
    btg_urban = 202
    btg_town = 211
    btg_suburban = 212
    btg_construction = 221
    btg_industrial = 222
    btg_port = 223


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
        self.generated_buildings = list()  # List og GenBuilding objects for generated non-osm buildings
        self.linked_genways = list()  # List of Highways that are available for generating buildings

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


class BTGBuildingZone(object):
    """A land-use from materials in FlightGear read from BTG-files"""
    def __init__(self, external_id, type_, geometry) -> None:
        self.id = str(external_id)  # String
        self.type_ = type_  # BuildingZoneType
        self.geometry = geometry  # Polygon


class GeneratedBuildingZone(BuildingZone):
    """A fake OSM Land-use for buildings based on heuristics"""
    def __init__(self, generated_id, geometry, building_zone_type, from_buildings=False) -> None:
        super().__init__(generated_id, geometry, building_zone_type)
        self.from_buildings = from_buildings  # False for e.g. external land-use

    def guess_building_zone_type(self, places: List[Place]):
        """Based on some heuristics of linked buildings guess the building zone type"""
        residential_buildings = 0
        commercial_buildings = 0
        industrial_buildings = 0
        retail_buildings = 0
        farm_buildings = 0
        for building in self.osm_buildings:
            building_class = building.get_building_class()
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
                logging.debug("Checking generated land-use for place=farm based on %d place tags", len(places))
                for my_place in places:
                    if my_place.type_ is PlaceType.farm:
                        if my_place.is_point:
                            if my_place.geometry.within(self.geometry):
                                self.type_ = BuildingZoneType.farmyard
                                places.remove(my_place)
                                logging.debug("Found one based on node place")
                                return
                        else:
                            if my_place.geometry.intersects(self.geometry):
                                self.type_ = BuildingZoneType.farmyard
                                places.remove(my_place)
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
    def __init__(self, osm_id: int, geometry: LineString, tags_dict: KeyValueDict) -> None:
        super().__init__(osm_id, geometry, tags_dict)
        self.is_roundabout = self._parse_tags_roundabout(tags_dict)
        self.is_oneway = self._parse_tags_oneway(tags_dict)
        self.lanes = self._parse_tags_lanes(tags_dict)

    @classmethod
    def create_from_scratch(cls, pseudo_id: int, existing_highway: 'Highway', linear: LineString) -> 'Highway':
        obj = Highway(pseudo_id, linear, dict())
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
        return self.type_ > HighwayType.road

    def populate_buildings_along(self) -> bool:
        """The type of highway determines where buildings are built. E.g. motorway would be false"""
        return self.type_ not in (HighwayType.motorway, HighwayType.trunk)

    @classmethod
    def create_from_way(cls, way: op.Way, nodes_dict: Dict[int, op.Node],
                        transformer: co.Transformation) -> 'Highway':
        my_geometry = cls.create_line_string_from_way(way, nodes_dict, transformer)
        obj = Highway(way.osm_id, my_geometry, way.tags)
        return obj


@unique
class BlockedAreaType(IntEnum):
    osm_building = 1
    gen_building = 2
    open_space = 3
    highway = 11
    waterway = 12
    railway = 13


@unique
class RectifyBlockedType(IntEnum):
    """Some nodes (RectifyNodes) shall be blocked from changing their angle / position during processing.
    multiple_buildings: if the node is part of more than one building
    ninety_degrees: if the node already is 90 degrees
    corner_to_bow: if the next node(s) is between 180 and 180 - 2*MAX_90_DEVIATIOM, then probably the node
    is part of a curved wall in at least two parts - the more parts the closer the angles in the curve are
    to 180 degrees."""
    multiple_buildings = 10
    ninety_degrees = 20
    corner_to_bow = 30


class RectifyNode(object):
    """Represents a OSM Node feature used for rectifying building angles."""
    def __init__(self, osm_id: int, key_value_dict: KeyValueDict, original_point: Point) -> None:
        self.osm_id = osm_id
        self.key_value_dict = key_value_dict
        self.x = original_point.x  # in local coordinates
        self.original_x = self.x  # should not get updated -> for reference/comparison
        self.y = original_point.y
        self.original_y = self.y
        self.is_updated = False
        self.rectify_building_refs = list()  # osm_ids

    @property
    def has_related_buildings(self) -> bool:
        return len(self.rectify_building_refs) > 0

    def relates_to_several_buildings(self) -> bool:
        return len(self.rectify_building_refs) > 1

    def update_point(self, new_x: float, new_y: float) -> False:
        self.x = new_x
        self.y = new_y
        self.is_updated = True

    def append_building_ref(self, osm_id: int) -> None:
        self.rectify_building_refs.append(osm_id)


class NodeInRectifyBuilding(object):
    """Links RectifyNode and RectifyBuilding because a RectifyNode can be linked to multiple buildings."""
    def __init__(self, rectify_node: RectifyNode) -> None:
        self.angle = 0.0  # in degrees. Not guaranteed to be up to date
        self.my_node = rectify_node  # directly linked RectifyNode in this building context (nodes can be shared)
        self.prev_node = None  # type NodeInRectifyBuilding
        self.next_node = None  # type NodeInRectifyBuilding
        self.blocked_types = list()  # list of RectifyBlockedType

    def within_rectify_deviation(self) -> bool:
        return math.fabs(self.angle - 90) <= parameters.OWBB_RECTIFY_MAX_90_DEVIATION

    def within_rectify_90_tolerance(self) -> bool:
        return math.fabs(self.angle - 90) <= parameters.OWBB_RECTIFY_90_TOLERANCE

    def append_blocked_type(self, append_type: RectifyBlockedType) -> None:
        needs_append = True
        for my_type in self.blocked_types:
            if my_type is append_type:
                needs_append = False
                break
        if needs_append:
            self.blocked_types.append(append_type)

    def is_blocked(self) -> bool:
        return len(self.blocked_types) > 0

    def node_needs_change(self) -> bool:
        if not self.is_blocked():
            if self.within_rectify_deviation():
                if not (self.prev_node.is_blocked() and self.next_node.is_blocked()):
                    return True
        return False

    def update_angle(self) ->None:
        self.angle = co.calc_angle_of_corner_local(self.prev_node.my_node.x, self.prev_node.my_node.y,
                                                   self.my_node.x, self.my_node.y,
                                                   self.next_node.my_node.x, self.next_node.my_node.y)


class RectifyBuilding(object):
    def __init__(self, osm_id: int, node_refs: List[RectifyNode]) -> None:
        self.osm_id = osm_id
        self.node_refs = list()  # NodeInRectifyBuilding objects
        for ref in node_refs:
            self._append_node_ref(ref)

    def _append_node_ref(self, node: RectifyNode) -> None:
        """Appends a RectifyNode to the node references of this building - and vice versa.
        However do not process last node in way, which is the same as the first one."""
        my_node = NodeInRectifyBuilding(node)
        if not ((len(self.node_refs) > 0) and (node.osm_id == self.node_refs[0].my_node.osm_id)):
            self.node_refs.append(my_node)
            node.append_building_ref(self.osm_id)

    def is_relevant(self) -> bool:
        """Only relevant for rectify processing if at least 4 corners."""
        return len(self.node_refs) > 3

    def classify_and_relate_unchanged_nodes(self) -> bool:
        """Returns True if at least one node is not blocked and falls within deviation."""
        # relate nodes and calculate angle
        for position in range(len(self.node_refs)):
            prev_node = self.node_refs[position - 1]
            corner_node = self.node_refs[position]
            if len(self.node_refs) - 1 == position:
                next_node = self.node_refs[0]
            else:
                next_node = self.node_refs[position + 1]
            corner_node.prev_node = prev_node
            corner_node.next_node = next_node
            corner_node.update_angle()

        # classify nodes
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            if corner_node.my_node.relates_to_several_buildings():
                corner_node.append_blocked_type(RectifyBlockedType.multiple_buildings)
            if corner_node.within_rectify_90_tolerance():
                corner_node.append_blocked_type(RectifyBlockedType.ninety_degrees)
            elif corner_node.within_rectify_deviation():
                max_angle = 180 - 2 * parameters.OWBB_RECTIFY_MAX_90_DEVIATION
                if corner_node.prev_node.angle >= max_angle or corner_node.next_node.angle >= max_angle:
                    corner_node.append_blocked_type(RectifyBlockedType.corner_to_bow)

        # finally find out whether there is something to change at all
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            if corner_node.node_needs_change():
                return True
        return False

    def rectify_nodes(self):
        """Rectifies all those nodes, which can and shall be changed.

        The algorithm looks at the current node angle and the blocked type of the next node.
        If the next node is blocked, then the current node is moved along the line prev_node-current_node until there
        are 90 degrees.
        If the next node is not blocked then in order to keep as much of the area/geometry similar,
        both the current and the next node are moved a bit. The current node is only moved half the distance,
        and the next node is moved the same distance in the opposite direction.
        Basically a triangle with prev_node (a), current_node (b) and next_node (c)."""
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            my_next_node = corner_node.next_node
            my_prev_node = corner_node.prev_node
            corner_node.update_angle()
            if corner_node.node_needs_change():
                dist_bc = co.calc_distance_local(corner_node.my_node.x, corner_node.my_node.y,
                                                 my_next_node.my_node.x, my_next_node.my_node.y)
                my_angle = corner_node.angle
                angle_ab = co.calc_angle_of_line_local(my_prev_node.my_node.x, my_prev_node.my_node.y,
                                                       corner_node.my_node.x, corner_node.my_node.y)
                is_add = False  # whether the distance from prev_node (a) to corner_node (b) shall be longer
                if my_angle > 90:
                    my_angle = 180 - my_angle
                    is_add = True
                dist_add = dist_bc * math.cos(math.radians(my_angle))
                if not my_next_node.is_blocked():
                    dist_add /= 2
                if not is_add:
                    dist_add *= -1
                new_x, new_y = co.calc_point_angle_away(corner_node.my_node.x, corner_node.my_node.y,
                                                        dist_add, angle_ab)
                corner_node.my_node.update_point(new_x, new_y)
                if not my_next_node.is_blocked():
                    dist_add *= -1
                    new_x, new_y = co.calc_point_angle_away(my_next_node.my_node.x, my_next_node.my_node.y,
                                                            dist_add, angle_ab)
                    my_next_node.my_node.update_point(new_x, new_y)
