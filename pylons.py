"""
Script part of osm2city which takes OpenStreetMap data as input and generates data to be used in FlightGear
   * overground power lines
   * aerialways
   * railway overlines
   * streetlamps

TODO:
* Remove shared objects from stg-files to avoid doubles
* Collision detection
* For aerialways make sure there is a station at both ends
* For aerialways handle stations if represented as ways instead of nodes.
* For powerlines handle power stations if represented as ways instead of nodes
* If a pylon is shared between lines but not at end points, then move one pylon a bit away

@author: vanosten
"""

import argparse
from enum import IntEnum, unique
import logging
import math
import time
from typing import Dict, List, Tuple
import unittest
import xml.sax

import cluster
import parameters
import roads
import shapely.geometry as shg
from utils import osmparser, vec2d, coordinates, stg_io2, utilities

OUR_MAGIC = "osm2pylon"  # Used in e.g. stg files to mark edits by osm2pylon
SCENERY_TYPE = "Pylons"


class CableVertex(object):
    __slots__ = ('out', 'height', 'top_cable', 'no_catenary', 'x', 'y', 'elevation')

    def __init__(self, out: float, height: float, top_cable: bool=False, no_catenary: bool=False) -> None:
        self.out = out  # the distance from the middle vertical line of the pylon
        self.height = height  # the distance above ground relative to the pylon's ground level (y-axis in ac-file)
        self.top_cable = top_cable  # for the cables at the top, which are not executing the main task
        self.no_catenary = no_catenary  # for cables which should not bend, e.g. lower cable of rail overhead line
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters

    def calc_position(self, pylon_x: float, pylon_y: float, pylon_elevation: float, pylon_heading: float) -> None:
        self.elevation = pylon_elevation + self.height
        self.x = pylon_x + math.sin(math.radians(pylon_heading + 90))*self.out
        self.y = pylon_y + math.cos(math.radians(pylon_heading + 90))*self.out

    def set_position(self, x: float, y: float, elevation: float) -> None:
        self.x = x
        self.y = y
        self.elevation = elevation


class Cable(object):
    __slots__ = ('start_cable_vertex', 'end_cable_vertex', 'vertices', 'radius', 'heading')

    def __init__(self, start_cable_vertex: CableVertex, end_cable_vertex: CableVertex, radius: float,
                 number_extra_vertices: int, catenary_a: int, distance: float, max_sagging: float) -> None:
        """
        A Cable between two vertices. The radius is approximated with a triangle with sides of length 2*radius.
        If both the number of extra_vertices and the catenary_a are > 0, then the Cable gets a sag based on
        a catenary function.
        """
        self.start_cable_vertex = start_cable_vertex
        self.end_cable_vertex = end_cable_vertex
        self.vertices = [self.start_cable_vertex, self.end_cable_vertex]
        self.radius = radius
        self.heading = coordinates.calc_angle_of_line_local(start_cable_vertex.x, start_cable_vertex.y,
                                                            end_cable_vertex.x, end_cable_vertex.y)

        if (number_extra_vertices > 0) and (catenary_a > 0) and (distance >= parameters.C2P_CATENARY_MIN_DISTANCE):
            self._make_catenary_cable(number_extra_vertices, catenary_a, max_sagging)

    def _make_catenary_cable(self, number_extra_vertices: int, catenary_a: int, max_sagging: float) -> None:
        """
        Transforms the cable into one with more vertices and some sagging based on a catenary function.
        If there is a considerable difference in elevation between the two pylons, then gravity would have to
        be taken into account https://en.wikipedia.org/wiki/File:Catenary-tension.png.
        However the elevation correction actually already helps quite a bit, because the x/y are kept constant.
        Max sagging makes sure that probability of touching the ground is lower for long distances
        """
        cable_distance = coordinates.calc_distance_local(self.start_cable_vertex.x, self.start_cable_vertex.y,
                                                         self.end_cable_vertex.x, self.end_cable_vertex.y)
        part_distance = cable_distance / (1 + number_extra_vertices)
        pylon_y = catenary_a * math.cosh((cable_distance / 2) / catenary_a)
        part_elevation = ((self.start_cable_vertex.elevation - self.end_cable_vertex.elevation) /
                          (1 + number_extra_vertices))
        for i in range(1, number_extra_vertices + 1):
            x = self.start_cable_vertex.x + i * part_distance * math.sin(math.radians(self.heading))
            y = self.start_cable_vertex.y + i * part_distance * math.cos(math.radians(self.heading))
            catenary_x = i * part_distance - (cable_distance / 2)
            elevation = catenary_a * math.cosh(catenary_x / catenary_a)  # pure catenary y-position
            elevation = self.start_cable_vertex.elevation - (pylon_y - elevation)  # relative distance to start pylon
            elevation -= i * part_elevation  # correct for elevation difference between the 2 pylons
            v = CableVertex(0, 0)
            v.set_position(x, y, elevation)
            self.vertices.insert(i, v)

    def translate_vertices_relative(self, rel_x: float, rel_y: float, rel_elevation: float) -> None:
        """
        Translates the CableVertices relatively to a reference position
        """
        for cable_vertex in self.vertices:
            cable_vertex.x -= rel_x
            cable_vertex.y -= rel_y
            cable_vertex.elevation -= rel_elevation

    def _create_numvert_lines(self, cable_vertex: CableVertex) -> str:
        """
        In the map-data x-axis is towards East and y-axis is towards North and z-axis is elevation.
        In ac-files the y-axis is pointing upwards and the z-axis points to South -
        therefore y and z are switched and z * -1
        """
        numvert_lines = str(cable_vertex.x + math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y + math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x - math.sin(math.radians(self.heading + 90))*self.radius)
        numvert_lines += " " + str(cable_vertex.elevation - self.radius)
        numvert_lines += " " + str(-1*(cable_vertex.y - math.cos(math.radians(self.heading + 90))*self.radius)) + "\n"
        numvert_lines += str(cable_vertex.x)
        numvert_lines += " " + str(cable_vertex.elevation + self.radius)
        numvert_lines += " " + str(-1*cable_vertex.y)
        return numvert_lines

    def make_ac_entry(self, material: int) -> str:
        """
        Returns an ac entry for this cable.
        """
        lines = list()
        lines.append("OBJECT group")
        lines.append("kids " + str(len(self.vertices) - 1))
        for i in range(0, len(self.vertices) - 1):
            lines.append("OBJECT poly")
            lines.append("numvert 6")
            lines.append(self._create_numvert_lines(self.vertices[i]))
            lines.append(self._create_numvert_lines(self.vertices[i + 1]))
            lines.append("numsurf 3")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("0 0 0")
            lines.append("3 0 0")
            lines.append("5 0 0")
            lines.append("2 0 0")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("0 0 0")
            lines.append("1 0 0")
            lines.append("4 0 0")
            lines.append("3 0 0")
            lines.append("SURF 0x40")
            lines.append("mat " + str(material))
            lines.append("refs 4")
            lines.append("4 0 0")
            lines.append("1 0 0")
            lines.append("2 0 0")
            lines.append("5 0 0")
            lines.append("kids 0")
        return "\n".join(lines)


@unique
class PylonDirectionType(IntEnum):
    normal = 0  # in ac-file mast is on left side, stuff on right side along x-axis
    mirror = 1
    start = 2
    end = 3


def _create_generic_pylon_25_vertices() -> List[CableVertex]:
    vertices = [CableVertex(5.0, 12.6),
                CableVertex(-5.0, 12.6),
                CableVertex(5.0, 16.8),
                CableVertex(-5.0, 16.8),
                CableVertex(5.0, 21.0),
                CableVertex(-5.0, 21.0),
                CableVertex(0.0, 25.2, top_cable=True)]
    return vertices


def _create_generic_pylon_50_vertices() -> List[CableVertex]:
    vertices = [CableVertex(10.0, 25.2),
                CableVertex(-10.0, 25.2),
                CableVertex(10.0, 33.6),
                CableVertex(-10.0, 33.6),
                CableVertex(10.0, 42.0),
                CableVertex(-10.0, 42.0),
                CableVertex(0.0, 50.4, top_cable=True)]
    return vertices


def _create_generic_pylon_100_vertices() -> List[CableVertex]:
    vertices = [CableVertex(20.0, 50.4),
                CableVertex(-20.0, 50.4),
                CableVertex(20.0, 67.2),
                CableVertex(-20.0, 67.2),
                CableVertex(20.0, 84.0),
                CableVertex(-20.0, 84.0),
                CableVertex(0.0, 100.8, top_cable=True)]
    return vertices


def _create_wooden_pole_14m_vertices() -> List[CableVertex]:
    vertices = [CableVertex(1.7, 14.4),
                CableVertex(-1.7, 14.4),
                CableVertex(2.7, 12.6),
                CableVertex(0.7, 12.6),
                CableVertex(-2.7, 12.6),
                CableVertex(-0.7, 12.6)]
    return vertices


def _create_drag_lift_pylon() -> List[CableVertex]:
    vertices = [CableVertex(2.8, 8.1),
                CableVertex(-0.8, 8.1)]
    return vertices


def _create_drag_lift_in_osm_building() -> List[CableVertex]:
    vertices = [CableVertex(2.8, 3.0),
                CableVertex(-0.8, 3.0)]
    return vertices


def _create_rail_power_vertices(direction_type) -> List[CableVertex]:
    if direction_type is PylonDirectionType.mirror:
        vertices = [CableVertex(-1.95, 5.85),
                    CableVertex(-1.95, 4.95, no_catenary=True)]
    else:
        vertices = [CableVertex(1.95, 5.85),
                    CableVertex(1.95, 4.95, no_catenary=True)]
    return vertices


def _create_rail_stop_tension() -> List[CableVertex]:
    vertices = [CableVertex(0, 5.35),
                CableVertex(0, 4.95, no_catenary=True)]
    return vertices


def _get_cable_vertices(pylon_model: str, direction_type: PylonDirectionType) -> List[CableVertex]:
    if "generic_pylon_25m" in pylon_model:
        return _create_generic_pylon_25_vertices()
    if "generic_pylon_50m" in pylon_model:
        return _create_generic_pylon_50_vertices()
    if "generic_pylon_100m" in pylon_model:
        return _create_generic_pylon_100_vertices()
    elif "drag_lift_pylon" in pylon_model:
        return _create_drag_lift_pylon()
    elif "create_drag_lift_in_osm_building" in pylon_model:
        return _create_drag_lift_in_osm_building()
    elif "wooden_pole_14m" in pylon_model:
        return _create_wooden_pole_14m_vertices()
    elif "RailPower" in pylon_model:
        return _create_rail_power_vertices(direction_type)
    elif "tension" in pylon_model:
        return _create_rail_stop_tension()
    else:
        raise Exception(msg='Pylon model not found for creating cable vertices: {}'.format(pylon_model))


@unique
class PylonType(IntEnum):
    unspecified = 0
    power_tower = 11  # OSM-key = "power", value = "tower"
    power_pole = 12  # OSM-key = "power", value = "pole"
    aerialway_pylon = 21  # OSM-key = "aerialway", value = "pylon"
    aerialway_station = 22  # OSM-key = "aerialway", value = "station"

    railway_virtual = 30  # only used at endpoints of RailLine for calcs - not used for visual masts
    railway_single = 31
    railway_double = 32
    railway_stop = 33


class SharedPylon(object):
    def __init__(self):
        self.osm_id = 0
        self.type_ = PylonType.unspecified
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters
        self.heading = 0.0  # heading of pylon in degrees
        self.pylon_model = None  # the path to the ac/xml model
        self.needs_stg_entry = True
        self.direction_type = PylonDirectionType.normal  # correction for which direction mast looks at

    def calc_global_coordinates(self, fg_elev: utilities.FGElev, my_coord_transformator) -> None:
        self.lon, self.lat = my_coord_transformator.toGlobal((self.x, self.y))
        self.elevation = fg_elev.probe_elev(vec2d.Vec2d(self.lon, self.lat), True)

    def make_stg_entry(self, my_stg_mgr):
        """
        Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        if not self.needs_stg_entry:
            return " "  # no need to write a shared object

        direction_correction = 0
        if self.direction_type is PylonDirectionType.mirror:
            direction_correction = 180
        elif self.direction_type is PylonDirectionType.end:
            direction_correction = 0
        elif self.direction_type is PylonDirectionType.start:
            direction_correction = 180

        # 90 less because arms are in x-direction in ac-file
        my_stg_mgr.add_object_shared(self.pylon_model, vec2d.Vec2d(self.lon, self.lat),
                                     self.elevation,
                                     _stg_angle(self.heading - 90 + direction_correction))


class StorageTank(SharedPylon):
    def __init__(self, osm_id: int, lon: float, lat: float, tags: Dict[str, str], radius: float,
                 elevation: float) -> None:
        super().__init__()
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat
        self.elevation = elevation
        diameter = radius * 2

        # try to guess a suitable shared model
        # in general we take the .ac models, even though some small detail ight be shown from far away
        if 'content' in tags and tags['content'] == 'gas':
            self.pylon_model = 'GenericPressureVessel10m.ac'
            if 15 <= diameter < 25:
                self.pylon_model = 'GenericPressureVessel20m.ac'
            if 25 <= diameter < 35:
                self.pylon_model = 'GenericPressureVessel30m.ac'
            if 35 <= diameter < 41:
                self.pylon_model = 'GenericPressureVessel40m.ac'
            if 41 <= diameter < 75:
                self.pylon_model = 'Gasometer.ac'
            if diameter >= 75:
                self.pylon_model = 'HC-Tank.ac'
        else:  # assuming fuel or oil
            if diameter < 11:
                self.pylon_model = 'KOFF_Tank_10M.ac'
            if 11 <= diameter < 13:
                self.pylon_model = 'KOFF_Tank_12M.ac'
            if 13 <= diameter < 18:
                self.pylon_model = 'KOFF_Tank_13M.ac'
            if 18 <= diameter < 25:
                self.pylon_model = 'KOFF_Tank_20M.ac'
            if 25 <= diameter < 35:
                self.pylon_model = 'KOFF_Tank_30M.ac'
            if 35 <= diameter < 45:
                self.pylon_model = 'generic_tank_040m_grey.ac'
                self.elevation -= 73
            if 45 <= diameter < 70:
                self.pylon_model = 'generic_tank_050m_grey.ac'
                self.elevation -= 70
            if 70 <= diameter < 95:
                self.pylon_model = 'generic_tank_075m_grey.ac'
                self.elevation -= 65
            if diameter >= 95:
                self.pylon_model = 'GenericStorageTank100m.ac'
                self.elevation -= 62
        self.pylon_model = 'Models/Industrial/' + self.pylon_model

    def make_stg_entry(self, my_stg_mgr) -> None:
        my_stg_mgr.add_object_shared(self.pylon_model, vec2d.Vec2d(self.lon, self.lat), self.elevation, 0)


class WindTurbine(SharedPylon):
    def __init__(self, osm_id: int, lon: float, lat: float, generator_output: float, tags: Dict[str, str]) -> None:
        super().__init__()
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat
        self.generator_output = generator_output
        self.generator_type_horizontal = True
        if "generator:type" in tags and tags["generator:type"].lower() == "vertical_axis":
            self.generator_type_horizontal = False
        self.offshore = "offshore" in tags and tags["offshore"].lower() == "yes"
        self.height = 0.
        if "height" in tags:
            self.height = osmparser.parse_length(tags["height"])
        elif "seamark:landmark:height" in tags:
            self.height = osmparser.parse_length(tags["seamark:landmark:height"])
        self.rotor_diameter = 0.0
        if "rotor_diameter" in tags:
            self.rotor_diameter = osmparser.parse_length(tags["rotor_diameter"])
        self.manufacturer = None
        if "manufacturer" in tags:
            self.manufacturer = tags["manufacturer"]
        self.manufacturer_type = None
        if "manufacturer_type" in tags:
            self.manufacturer_type = tags["manufacturer_type"]
        # illumination
        self.illuminated = "seamark:landmark:status" in tags and tags["seamark:landmark:status"] == "illuminated"
        if not self.illuminated:
            self.illuminated = "seamark:status" in tags and tags["seamark:status"] == "illuminated"
        # wind farm id (artificial - see process_osm_wind_turbines)
        self.wind_farm = None

    def set_offshore_from_probe(self, is_solid: bool):
        """Offshore can be set from OSM tags and be challenged through elevation/water probing."""
        if self.offshore and is_solid:
            logging.debug("Overriding offshore to onshore based on probing for osm_id = {}.".format(self.osm_id))
            self.offshore = False
        if not self.offshore and not is_solid:
            logging.debug("Overriding onshore to offshore based on probing for osm_id = {}.".format(self.osm_id))
            self.offshore = True

    @staticmethod
    def determine_shared_model(height: float, generator_output: float, is_offshore: bool, is_illuminated: bool) -> str:
        """The relation between height and generator_output are pure guesses and some randomness.
        More intelligent heuristics could also take into account distance between turbines in a farm as indicator."""
        common_path = "Models/Power/"
        if is_offshore:
            shared_model = "vestas-v80-sea.xml"
            if height > 70 or generator_output > 3000000:
                shared_model = "Vestas_Off_Shore140M.xml"

        else:
            if height == 0 and generator_output == 0:
                if is_illuminated:
                    shared_model = "windturbine_flash.xml"
                else:
                    shared_model = "windturbine.xml"
            elif height > 50 or generator_output > 1000000:
                shared_model = "windturbine_e82_78m.xml"
                if height > 84 or generator_output > 3000000:
                    shared_model = "windturbine_e82_85m.xml"
                if height > 97 or generator_output > 3200000:
                    shared_model = "windturbine_e82_98m.xml"
                if height > 107 or generator_output > 3500000:
                    shared_model = "windturbine_e82_98m.xml"
                if height > 137 or generator_output > 4000000:
                    shared_model = "windturbine_e82_98m.xml"
            else:
                shared_model = "18m"
                if height >= 24 or generator_output > 20000:
                    shared_model = "24m"
                if height >= 30 or generator_output > 30000:
                    shared_model = "30m"
                if height >= 39 or generator_output > 40000:
                    shared_model = "39m"
                if is_illuminated:
                    shared_model += "_obst"
                shared_model = "windturbine_LAG18_" + shared_model
        logging.debug("Wind turbine shared model chosen: {}".format(shared_model))
        return common_path + shared_model

    def make_stg_entry(self, my_stg_mgr) -> None:
        # special for Vestas_Off_Shore140M.xml
        if self.pylon_model.endswith("140M.xml"):
            my_stg_mgr.add_object_shared("Models/Power/Vestas_Base.ac", vec2d.Vec2d(self.lon, self.lat),
                                         self.elevation, 0)
            # no need to add 12m to elevation for Vestas_Off_Shore140M.xml - ac-model already takes care
        my_stg_mgr.add_object_shared(self.pylon_model, vec2d.Vec2d(self.lon, self.lat), self.elevation, 0)


class WindFarm(object):
    def __init__(self) -> None:
        self.turbines = set()

    def add_turbine(self, turbine: WindTurbine) -> None:
        self.turbines.add(turbine)

    def determine_shared_model(self):
        """Stupidly assumes that all turbines actually belong to same farm and have same type.
        In the end assignes shared model to all turbines in the farm"""

        # first do some statistics
        max_height = 0
        max_generator_output = 0
        number_offshore = 0
        number_illuminated = 0
        for turbine in self.turbines:
            max_height = max(max_height, turbine.height)
            max_generator_output = max(max_generator_output, turbine.generator_output)
            if turbine.offshore:
                number_offshore += 1
            if turbine.illuminated:
                number_illuminated += 1
        is_offshore = number_offshore > len(self.turbines) / 2
        is_illuminated = number_illuminated > 0

        # then determine model based on "average"
        shared_model = WindTurbine.determine_shared_model(max_height, max_generator_output, is_offshore, is_illuminated)
        for turbine in self.turbines:
            turbine.pylon_model = shared_model


def _process_osm_wind_turbines(osm_nodes_dict: Dict[int, osmparser.Node], coords_transform: coordinates.Transformation,
                               fg_elev: utilities.FGElev) -> List[WindTurbine]:
    my_wind_turbines = list()
    wind_farms = list()

    # make sure no existing shared objects are duplicated. Do not care what shared obejct within distance
    stg_entries = stg_io2.read_stg_entries_in_boundary()

    # find relevant / valid wind turbines
    for key, node in osm_nodes_dict.items():
        if "generator:source" in node.tags and node.tags["generator:source"] == "wind":
            if "generator:output:electricity" in node.tags:
                # first check against existing
                shared_within_distance = False
                for entry in stg_entries:
                    if entry.verb_type is stg_io2.STGVerbType.object_shared:
                        if coordinates.calc_distance_global(entry.lon, entry.lat, node.lon, node.lat) < parameters.C2P_WIND_TURBINE_MIN_DISTANCE_SHARED_OBJECT:
                            logging.debug("Excluding turbine osm_id = {} due to overlap shared object.".format(node.osm_id))
                            shared_within_distance = True
                            break
                if shared_within_distance:
                    continue
                generator_output = osmparser.parse_generator_output(node.tags["generator:output:electricity"])
                turbine = WindTurbine(key, node.lon, node.lat, generator_output, node.tags)
                turbine.x, turbine.y = coords_transform.toLocal((node.lon, node.lat))
                probe_tuple = fg_elev.probe(vec2d.Vec2d(node.lon, node.lat), True)
                turbine.elevation = probe_tuple[0]
                turbine.set_offshore_from_probe(probe_tuple[1])
                my_wind_turbines.append(turbine)
            else:
                logging.debug("Skipped wind turbine osm_id = {}: need tag 'generator:output:electricity'".format(key))
                continue

    # Create wind farms to help determine model, illumination etc.
    # http://wiki.openstreetmap.org/wiki/Relations/Proposed/Site site=wind_farm is not used a lot
    # Therefore brute force based on distance
    for i in range(1, len(my_wind_turbines)):
        for j in range(i + 1, len(my_wind_turbines)):
            if coordinates.calc_distance_local(my_wind_turbines[i].x, my_wind_turbines[i].y,
                                               my_wind_turbines[j].x, my_wind_turbines[j].y) \
                    <= parameters.C2P_WIND_TURBINE_MAX_DISTANCE_WITHIN_WIND_FARM:
                my_wind_farm = my_wind_turbines[i].wind_farm
                if my_wind_farm is None:
                    my_wind_farm = WindFarm()
                    wind_farms.append(my_wind_farm)
                    my_wind_farm.add_turbine(my_wind_turbines[i])
                    my_wind_turbines[i].wind_farm = my_wind_farm
                my_wind_farm.add_turbine(my_wind_turbines[j])
                my_wind_turbines[j].wind_farm = my_wind_farm

    logging.debug("Found {} wind farms".format(len(wind_farms)))

    # assign models in farms
    for farm in wind_farms:
        farm.determine_shared_model()
    # assign to those outside of a farm
    for turbine in my_wind_turbines:
        if turbine.wind_farm is None:
            turbine.pylon_model = WindTurbine.determine_shared_model(turbine.height, turbine.generator_output,
                                                                     turbine.offshore, turbine.illuminated)

    return my_wind_turbines


class Pylon(SharedPylon):
    def __init__(self, osm_id):
        super().__init__()
        self.osm_id = osm_id
        self.height = 0.0  # parsed as float
        self.structure = None
        self.material = None
        self.colour = None
        self.prev_pylon = None
        self.next_pylon = None
        self.in_osm_building = False  # a pylon can be in a OSM Way/building, in which case it should not be drawn

    def calc_pylon_model(self, pylon_model):
        if self.type_ is PylonType.aerialway_station:
            if self.in_osm_building:
                self.needs_stg_entry = False
                self.pylon_model = pylon_model + "_in_osm_building"
            else:
                if not self.prev_pylon:
                    self.pylon_model = pylon_model + "_start_station"
                else:
                    self.pylon_model = pylon_model + "_end_station"
        else:
            self.pylon_model = pylon_model


class LineWithoutCables(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.shared_pylons = []  # SharedPylons

    def make_shared_pylons_stg_entries(self, my_stg_mgr):
        """
        Adds the stg entries for the pylons of this WayLine
        """
        for my_pylon in self.shared_pylons:
            my_pylon.make_stg_entry(my_stg_mgr)

    def get_center_coordinates(self):
        """Returns the lon/lat coordinates of the line"""
        if not self.shared_pylons:  # FIXME
            return 0, 0
        else:  # FIXME: needs to be calculated more properly with shapely
            if len(self.shared_pylons) == 1:
                my_shared_pylon = self.shared_pylons[0]
            else:
                my_shared_pylon = self.shared_pylons[1]
            return my_shared_pylon.lon, my_shared_pylon.lat


class StreetlampWay(LineWithoutCables):
    def __init__(self, osm_id, highway):
        super().__init__(osm_id)
        self.highway = highway

    @staticmethod
    def has_lamps(highway_type):
        if highway_type is roads.HighwayType.slow:
            return False
        return True

    def calc_and_map(self, fg_elev: utilities.FGElev, my_coord_transformator):
        if self.highway.is_roundabout:
            shared_pylon = SharedPylon()
            shared_pylon.pylon_model = "Models/StreetFurniture/Streetlamp3.xml"
            p = shg.Polygon(self.highway.linear)
            shared_pylon.x = p.centroid.x
            shared_pylon.y = p.centroid.y
            self.shared_pylons.append(shared_pylon)
        else:
            model = "Models/StreetFurniture/Streetlamp2.xml"
            default_distance = parameters.C2P_STREETLAMPS_OTHER_DISTANCE
            parallel_offset = self.highway.get_width()/2
            if self.highway.type_ in [roads.HighwayType.service, roads.HighwayType.residential,
                                      roads.HighwayType.living_street, roads.HighwayType.pedestrian]:
                model = "Models/StreetFurniture/Streetlamp1.xml"
                default_distance = parameters.C2P_STREETLAMPS_RESIDENTIAL_DISTANCE

            self.shared_pylons = []  # list of SharedPylon
            x, y = self.highway.linear.coords[0]
            shared_pylon = SharedPylon()
            shared_pylon.x = x
            shared_pylon.y = y
            shared_pylon.needs_stg_entry = False
            shared_pylon.calc_global_coordinates(fg_elev, my_coord_transformator)
            self.shared_pylons.append(shared_pylon)  # used for calculating heading - especially if only one lamp

            my_right_parallel = self.highway.linear.parallel_offset(parallel_offset, 'right', join_style=1)
            my_right_parallel_length = my_right_parallel.length
            current_distance = 10  # the distance from the origin of the current streetlamp

            while True:
                if current_distance > my_right_parallel_length:
                    break
                point_on_line = my_right_parallel.interpolate(my_right_parallel_length - current_distance)
                shared_pylon = SharedPylon()
                shared_pylon.x = point_on_line.x
                shared_pylon.y = point_on_line.y
                shared_pylon.pylon_model = model
                shared_pylon.direction_type = PylonDirectionType.mirror
                shared_pylon.calc_global_coordinates(fg_elev, my_coord_transformator)
                self.shared_pylons.append(shared_pylon)
                current_distance += default_distance

            # calculate heading
            _calc_heading_nodes(self.shared_pylons)


class WaySegment(object):
    """Represents the part between the pylons and is a container for the cables"""
    __slots__ = ('start_pylon', 'end_pylon', 'cables', 'length', 'heading')

    def __init__(self, start_pylon: SharedPylon, end_pylon: SharedPylon):
        self.start_pylon = start_pylon
        self.end_pylon = end_pylon
        self.cables = []
        self.length = coordinates.calc_distance_local(start_pylon.x, start_pylon.y, end_pylon.x, end_pylon.y)
        self.heading = coordinates.calc_angle_of_line_local(start_pylon.x, start_pylon.y,
                                                            end_pylon.x, end_pylon.y)


class Line(LineWithoutCables):
    def __init__(self, osm_id: int) -> None:
        super().__init__(osm_id)
        self.way_segments = []
        self.length = 0.0  # the total length of all segments
        self.original_osm_way = None

    def _calc_segments(self) -> float:
        """Creates the segments of this WayLine and calculates the total length.
        Returns the maximum length of segments"""
        max_length = 0.0
        total_length = 0.0
        self.way_segments = []  # if this method would be called twice by mistake
        for x in range(0, len(self.shared_pylons) - 1):
            segment = WaySegment(self.shared_pylons[x], self.shared_pylons[x + 1])
            self.way_segments.append(segment)
            if segment.length > max_length:
                max_length = segment.length
            total_length += segment.length
        self.length = total_length
        return max_length

    def _calc_cables(self, radius: float, number_extra_vertices: int, catenary_a: int) -> None:
        """
        Creates the cables per WaySegment. First find the start and end points depending on pylon model.
        Then calculate the local positions of all start and end points.
        Afterwards use the start and end points to create all cables for a given WaySegment
        """
        for segment in self.way_segments:
            start_cable_vertices = _get_cable_vertices(segment.start_pylon.pylon_model,
                                                       segment.start_pylon.direction_type)
            end_cable_vertices = _get_cable_vertices(segment.end_pylon.pylon_model,
                                                     segment.end_pylon.direction_type)

            # make sure sagging is not too much -> correct catenary_a if needed
            min_cable_height = 9999
            max_sagging = 1
            for vertex in start_cable_vertices:
                min_cable_height = min(min_cable_height, vertex.height)
                max_sagging = parameters.C2P_CATENARY_A_MAX_SAGGING * min_cable_height

            max_sagging_catenary_a, b = _optimize_catenary(segment.length/2, 100 * catenary_a, max_sagging, 0.01)
            corrected_catenary_a = catenary_a
            if max_sagging_catenary_a > catenary_a:  # the larger the catenary_a, the less sagging
                corrected_catenary_a = max_sagging_catenary_a
                logging.debug("Changed catenary_a from {} to {}".format(catenary_a, max_sagging_catenary_a))

            # now create cables with acceptable sagging
            for i in range(0, len(start_cable_vertices)):
                my_radius = radius
                my_number_extra_vertices = number_extra_vertices
                start_cable_vertices[i].calc_position(segment.start_pylon.x, segment.start_pylon.y,
                                                      segment.start_pylon.elevation, segment.start_pylon.heading)
                end_cable_vertices[i].calc_position(segment.end_pylon.x, segment.end_pylon.y,
                                                    segment.end_pylon.elevation, segment.end_pylon.heading)
                if start_cable_vertices[i].top_cable:
                    my_radius = parameters.C2P_RADIUS_TOP_LINE
                if start_cable_vertices[i].no_catenary:
                    my_number_extra_vertices = 0
                cable = Cable(start_cable_vertices[i], end_cable_vertices[i], my_radius, my_number_extra_vertices,
                              corrected_catenary_a, segment.length, max_sagging)
                segment.cables.append(cable)


@unique
class WayLineType(IntEnum):
    unspecified = 0
    power_line = 11  # OSM-key = "power", value = "line"
    power_minor = 12  # OSM-key = "power", value = "minor_line"
    aerialway_cable_car = 21  # OSM-key = "aerialway", value = "cable_car"
    aerialway_chair_lift = 22  # OSM-key = "aerialway", value = "chair_lift" or "mixed_lift"
    aerialway_drag_lift = 23  # OSM-key = "aerialway", value = "drag_lift" or "t-bar" or "j-bar" or "platter"
    aerialway_gondola = 24  # OSM-key = "aerialway", value = "gondola"
    aerialway_goods = 25  # OSM-key = "aerialway", value = "goods"


class WayLine(Line):  # The name "Line" is also used in e.g. SymPy

    def __init__(self, osm_id: int) -> None:
        super().__init__(osm_id)
        self.type_ = WayLineType.unspecified  # cf. class constants TYPE_*
        self.voltage = 0  # from osm-tag "voltage"
        self.cables = 0  # from osm-tag "cables"
        self.wires = None  # from osm-tag "wires"

    def is_aerialway(self) -> bool:
        return self.type_ not in (WayLineType.power_line, WayLineType.power_minor)

    def calc_and_map(self) -> None:
        """Calculates various aspects of the line and its nodes and attempt to correct if needed. """
        max_length = self._calc_segments()
        if self.is_aerialway():
            pylon_model = self._calc_and_map_aerialway()
        else:
            pylon_model = self._calc_and_map_powerline(max_length)
        for my_pylon in self.shared_pylons:
            my_pylon.pylon_model = pylon_model

        _calc_heading_nodes(self.shared_pylons)

        # calc cables
        radius = parameters.C2P_RADIUS_POWER_LINE
        number_extra_vertices = parameters.C2P_EXTRA_VERTICES_POWER_LINE
        catenary_a = parameters.C2P_CATENARY_A_POWER_LINE
        if self.type_ is WayLineType.power_minor:
            radius = parameters.C2P_RADIUS_POWER_MINOR_LINE
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_POWER_MINOR_LINE
            catenary_a = parameters.C2P_CATENARY_A_POWER_MINOR_LINE
        elif self.type_ is WayLineType.aerialway_cable_car:
            radius = parameters.C2P_RADIUS_AERIALWAY_CABLE_CAR
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_CABLE_CAR
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_CABLE_CAR
        elif self.type_ is WayLineType.aerialway_chair_lift:
            radius = parameters.C2P_RADIUS_AERIALWAY_CHAIR_LIFT
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_CHAIR_LIFT
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_CHAIR_LIFT
        elif self.type_ is WayLineType.aerialway_drag_lift:
            radius = parameters.C2P_RADIUS_AERIALWAY_DRAG_LIFT
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_DRAG_LIFT
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_DRAG_LIFT
        elif self.type_ is WayLineType.aerialway_gondola:
            radius = parameters.C2P_RADIUS_AERIALWAY_GONDOLA
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_GONDOLA
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_GONDOLA
        elif self.type_ is WayLineType.aerialway_goods:
            radius = parameters.C2P_RADIUS_AERIALWAY_GOODS
            number_extra_vertices = parameters.C2P_EXTRA_VERTICES_AERIALWAY_GOODS
            catenary_a = parameters.C2P_CATENARY_A_AERIALWAY_GOODS
        self._calc_cables(radius, number_extra_vertices, catenary_a)

    def _calc_and_map_aerialway(self) -> str:
        pylon_model = "Models/Transport/drag_lift_pylon.xml"  # FIXME: make real implementation
        return pylon_model

    def _calc_and_map_powerline(self, max_length: float) -> str:
        """
        Danish rules of thumb:
        400KV: height 30-42 meter, distance 200-420 meter, sagging 4.5-13 meter, a_value 1110-1698
        150KV: height 25-32 meter, distance 180-350 meter, sagging 2.5-9 meter, a_value 1614-1702
        60KV: height 15-25 meter, distance 100-250 meter, sagging 1-5 meter, a_value 1238-1561
        The a_value for the catenary function has been calculated with osm2pylon.optimize_catenary().
        """
        # calculate min, max, averages etc.
        max_height = 0.0
        average_height = 0.0
        found = 0
        nbr_poles = 0
        nbr_towers = 0
        for my_pylon in self.shared_pylons:
            if my_pylon.type_ is PylonType.power_tower:
                nbr_towers += 1
            elif my_pylon.type_ is PylonType.power_pole:
                nbr_poles += 1
            if my_pylon.height > 0:
                average_height += my_pylon.height
                found += 1
            if my_pylon.height > max_height:
                max_height = my_pylon.height
        if found > 0:
            average_height /= found

        # use statistics to determine type_ and pylon_model
        if (self.type_ is WayLineType.power_minor and nbr_towers <= nbr_poles
                and max_height <= 25.0 and max_length <= 250.0) \
                or (self.type_ is WayLineType.power_line and max_length <= 150):
            self.type_ = WayLineType.power_minor
            pylon_model = "Models/Power/wooden_pole_14m.ac"
        else:
            self.type_ = WayLineType.power_line
            if average_height < 35.0 and max_length < 300.0:
                pylon_model = "Models/Power/generic_pylon_25m.xml"
            elif average_height < 75.0 and max_length < 500.0:
                pylon_model = "Models/Power/generic_pylon_50m.xml"
            elif parameters.C2P_POWER_LINE_ALLOW_100M:
                pylon_model = "Models/Power/generic_pylon_100m.xml"
            else:
                pylon_model = "Models/Power/generic_pylon_50m.xml"

        return pylon_model


class RailNode(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.switch = False
        self.buffer_stop = False
        self.lon = 0.0  # longitude coordinate in decimal as a float
        self.lat = 0.0  # latitude coordinate in decimal as a float
        self.x = 0.0  # local position x
        self.y = 0.0  # local position y
        self.elevation = 0.0  # elevation above sea level in meters


class RailMast(SharedPylon):
    def __init__(self, type_: PylonType, point_on_line, mast_point, direction_type: PylonDirectionType):
        super().__init__()
        self.type_ = type_
        self.point_on_line = point_on_line
        self.x = mast_point.x
        self.y = mast_point.y
        self.pylon_model = "Models/StreetFurniture/RailPower.ac"
        if self.type_ is PylonType.railway_virtual:
            self.needs_stg_entry = False
        elif self.type_ is PylonType.railway_stop:
            self.pylon_model = "Models/StreetFurniture/rail_stop_tension.ac"
        self.direction_type = direction_type


class RailLine(Line):
    TYPE_RAILWAY_GAUGE_NARROW = 11
    TYPE_RAILWAY_GAUGE_NORMAL = 12

    DEFAULT_MAST_DISTANCE = 60  # if this is changed then mast algorithm for radius below must be adapted
    OFFSET = 20  # the offset from end points
    MAX_DEVIATION = 1  # The distance the overhead line can be off from the center
    MAST_BUFFER = 3.0

    def __init__(self, osm_id):
        super().__init__(osm_id)
        self.type_ = 0
        self.nodes = []  # RailNodes
        self.linear = None  # The LineaString of the line

    def calc_and_map(self, fg_elev: utilities.FGElev, my_coord_transformator, rail_lines_list):
        self.shared_pylons = []  # array of RailMasts
        current_distance = 0  # the distance from the origin of the current mast
        my_length = self.linear.length  # omit recalculating length all the time
        # offset must be same as create_rail_power_vertices()
        my_right_parallel = self.linear.parallel_offset(1.95, 'right', join_style=1)
        my_right_parallel_length = my_right_parallel.length
        my_left_parallel = self.linear.parallel_offset(1.95, 'left', join_style=1)
        my_left_parallel_length = my_left_parallel.length

        # virtual start point
        point_on_line = self.linear.interpolate(0)
        mast_point = my_right_parallel.interpolate(my_right_parallel_length)
        if self.nodes[0].buffer_stop:
            self.shared_pylons.append(RailMast(PylonType.railway_stop, point_on_line, point_on_line,
                                               PylonDirectionType.start))
        else:
            self.shared_pylons.append(RailMast(PylonType.railway_virtual, point_on_line, mast_point,
                                               PylonDirectionType.mirror))
        prev_point = point_on_line

        # get the first mast point
        if my_length < RailLine.DEFAULT_MAST_DISTANCE:
            current_distance += (my_length / 2)
            point_on_line = self.linear.interpolate(current_distance)
            mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
            is_right = self.check_mast_left_right(mast_point, rail_lines_list)
            if is_right:
                direction_type = PylonDirectionType.mirror
            else:
                direction_type = PylonDirectionType.normal
                mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
            self.shared_pylons.append(RailMast(PylonType.railway_single, point_on_line, mast_point, direction_type))
        else:
            current_distance += RailLine.OFFSET
            point_on_line = self.linear.interpolate(current_distance)
            mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
            is_right = self.check_mast_left_right(mast_point, rail_lines_list)
            if is_right:
                direction_type = PylonDirectionType.mirror
            else:
                direction_type = PylonDirectionType.normal
                mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
            self.shared_pylons.append(RailMast(PylonType.railway_single, point_on_line, mast_point, direction_type))
            prev_angle = coordinates.calc_angle_of_line_local(prev_point.x, prev_point.y, point_on_line.x, point_on_line.y)
            prev_point = point_on_line
            # find new masts along the line with a simple approximation for less distance between masts
            # if the radius gets tighter
            while True:
                if (my_length - current_distance) <= RailLine.OFFSET:
                    break
                min_distance = my_length - current_distance - RailLine.OFFSET
                if min_distance < RailLine.DEFAULT_MAST_DISTANCE:
                    current_distance += min_distance
                else:
                    test_distance = current_distance + RailLine.DEFAULT_MAST_DISTANCE
                    point_on_line = self.linear.interpolate(test_distance)
                    new_angle = coordinates.calc_angle_of_line_local(prev_point.x, prev_point.y,
                                                                     point_on_line.x, point_on_line.y)
                    difference = abs(new_angle - prev_angle)
                    if difference >= 25:
                        current_distance += 10
                    elif difference >= 20:
                        current_distance += 20
                    elif difference >= 15:
                        current_distance += 30
                    elif difference >= 10:
                        current_distance += 40
                    elif difference >= 5:
                        current_distance += 50
                    else:
                        current_distance += RailLine.DEFAULT_MAST_DISTANCE
                point_on_line = self.linear.interpolate(current_distance)
                mast_point = my_right_parallel.interpolate(my_right_parallel_length - current_distance * (my_right_parallel_length / my_length))
                is_right = self.check_mast_left_right(mast_point, rail_lines_list)
                if is_right:
                    direction_type = PylonDirectionType.mirror
                else:
                    direction_type = PylonDirectionType.normal
                    mast_point = my_left_parallel.interpolate(current_distance * (my_left_parallel_length / my_length))
                self.shared_pylons.append(RailMast(PylonType.railway_single, point_on_line, mast_point, direction_type))
                prev_angle = coordinates.calc_angle_of_line_local(prev_point.x, prev_point.y,
                                                                  point_on_line.x, point_on_line.y)
                prev_point = point_on_line

        # virtual end point
        point_on_line = self.linear.interpolate(my_length)
        mast_point = my_right_parallel.interpolate(0)
        if self.nodes[-1].buffer_stop:
            self.shared_pylons.append(RailMast(PylonType.railway_stop, point_on_line, point_on_line,
                                               PylonDirectionType.end))
        else:
            self.shared_pylons.append(RailMast(PylonType.railway_virtual, point_on_line, mast_point,
                                               PylonDirectionType.mirror))

        # calculate heading
        _calc_heading_nodes(self.shared_pylons)

        # segments
        self._calc_segments()

        # calculate global coordinates
        for my_mast in self.shared_pylons:
            my_mast.calc_global_coordinates(fg_elev, my_coord_transformator)

        # cables
        self._calc_cables(parameters.C2P_RADIUS_OVERHEAD_LINE, parameters.C2P_EXTRA_VERTICES_OVERHEAD_LINE,
                          parameters.C2P_CATENARY_A_OVERHEAD_LINE)

    def check_mast_left_right(self, mast_point, rail_lines_list):
        mast_buffer = mast_point.buffer(RailLine.MAST_BUFFER)
        is_right = True
        for my_line in rail_lines_list:
            if (my_line.osm_id != self.osm_id) and mast_buffer.intersects(my_line.linear):
                is_right = False
                break
        return is_right


def _process_osm_rail_overhead(nodes_dict, ways_dict, fg_elev: utilities.FGElev, my_coord_transformator) \
        -> List[RailLine]:
    my_railways = list()
    my_shared_nodes = {}  # node osm_id as key, list of WayLine objects as value
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    railway_candidates = list()
    for way_key, way in ways_dict.items():
        if "railway" in way.tags:
            split_ways = osmparser.split_way_at_boundary(nodes_dict, way, clipping_border)
            if split_ways:
                railway_candidates.extend(split_ways)

    for way in railway_candidates:
        my_line = RailLine(way.osm_id)
        is_railway = False
        is_electrified = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "railway" == key:
                if value == "rail":
                    is_railway = True
                    my_line.type_ = RailLine.TYPE_RAILWAY_GAUGE_NORMAL
                elif value == "narrow_gauge":
                    is_railway = True
                    my_line.type_ = RailLine.TYPE_RAILWAY_GAUGE_NARROW
                elif value == "abandoned":
                    is_challenged = True
            elif "electrified" == key:
                if value in ("contact_line", "yes"):
                    is_electrified = True
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
        if is_railway and is_electrified and (not is_challenged):
            # Process the Nodes
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_rail_node = RailNode(my_node.osm_id)
                    my_rail_node.lat = my_node.lat
                    my_rail_node.lon = my_node.lon
                    my_rail_node.x, my_rail_node.y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_rail_node.elevation = fg_elev.probe_elev(vec2d.Vec2d(my_rail_node.lon, my_rail_node.lat), True)
                    for key in my_node.tags:
                        value = my_node.tags[key]
                        if "railway" == key and "switch" == value:
                            my_rail_node.switch = True
                        if "railway" == key and "buffer_stop" == value:
                            my_rail_node.buffer_stop = True
                    if my_rail_node.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                        my_line.nodes.append(my_rail_node)
                    else:
                        logging.debug('Node outside of boundaries and therefore ignored: osm_id = %s ', my_node.osm_id)
            if len(my_line.nodes) > 1:
                my_railways.append(my_line)
                if my_line.nodes[0].osm_id in list(my_shared_nodes.keys()):
                    my_shared_nodes[my_line.nodes[0].osm_id].append(my_line)
                else:
                    my_shared_nodes[my_line.nodes[0].osm_id] = [my_line]
                if my_line.nodes[-1].osm_id in list(my_shared_nodes.keys()):
                    my_shared_nodes[my_line.nodes[-1].osm_id].append(my_line)
                else:
                    my_shared_nodes[my_line.nodes[-1].osm_id] = [my_line]
            else:
                logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)

    # Attempt to merge lines
    for key in list(my_shared_nodes.keys()):
        shared_node = my_shared_nodes[key]
        if len(shared_node) >= 2:
            pos1, pos2 = _find_connecting_line(key, shared_node, 60)
            second_line = shared_node[pos2]
            if pos1 >= 0:
                try:
                    _merge_lines(key, shared_node[pos1], shared_node[pos2], my_shared_nodes)
                    my_railways.remove(second_line)
                    del my_shared_nodes[key]
                    logging.debug("Merged two lines with node osm_id: %s", key)
                except Exception as e:
                    logging.error(e)

    # get LineStrings and remove those lines, which are less than the minimal requirement
    for the_railway in my_railways:
        my_coordinates = list()
        for node in the_railway.nodes:
            my_coordinates.append((node.x, node.y))
        my_linear = shg.LineString(my_coordinates)
        the_railway.linear = my_linear

    return my_railways


def _process_highways_for_streetlamps(my_highways, landuse_buffers) -> List[StreetlampWay]:
    """
    Test whether the highway is within appropriate land use or intersects with appropriate land use
    No attempt to merge lines because most probably the lines are split at crossing.
    No attempt to guess whether there there is a division in the center, where a street lamp with two lamps could be
    placed - e.g. using a combination of highway type, one-way, number of lanes etc
    """
    my_streetlamps = dict()
    for key in list(my_highways.keys()):
        my_highway = my_highways[key]
        if not StreetlampWay.has_lamps(my_highway.type_):
            continue
        is_within = False
        intersections = []
        for lu_buffer in landuse_buffers:
            if my_highway.linear.within(lu_buffer):
                is_within = True
                break
            elif my_highway.linear.intersects(lu_buffer):
                intersections.append(my_highway.linear.intersection(lu_buffer))
        if is_within:
            my_streetlamps[my_highway.osm_id] = StreetlampWay(my_highway.osm_id, my_highway)
        else:
            if intersections:
                index = 10000000000
                for intersection in intersections:
                    if isinstance(intersection, shg.MultiLineString):
                        for my_line in intersection:
                            if isinstance(my_line, shg.LineString):
                                intersections.append(my_line)
                        continue
                    elif isinstance(intersection, shg.LineString):
                        index += 1
                        new_highway = Highway(index + key)
                        new_highway.type_ = my_highway.type_
                        new_highway.linear = intersection
                        my_streetlamps[new_highway.osm_id] = StreetlampWay(new_highway.osm_id, new_highway)
                del my_highways[key]

    # Remove the too short lines
    for key in list(my_streetlamps.keys()):
        my_streetlamp = my_streetlamps[key]
        if not isinstance(my_streetlamp.highway.linear, shg.LineString):
            del my_streetlamps[key]
        elif my_streetlamp.highway.is_roundabout and\
                (50 > my_streetlamp.highway.linear.length or 300 < my_streetlamp.highway.linear.length):
            del my_streetlamps[key]
        elif my_streetlamp.highway.linear.length < parameters.C2P_STREETLAMPS_MIN_STREET_LENGTH:
            del my_streetlamps[key]

    return list(my_streetlamps.values())


def _merge_streetlamp_buffers(landuse_refs):
    """Based on existing landuses applies extra buffer and then unions as many as possible"""
    landuse_buffers = []
    for landuse_ref in list(landuse_refs.values()):
        streetlamp_buffer = landuse_ref.polygon.buffer(parameters.C2P_STREETLAMPS_MAX_DISTANCE_LANDUSE)
        if 0 == len(landuse_buffers):
            landuse_buffers.append(streetlamp_buffer)
        else:
            is_found = False
            for i in range(len(landuse_buffers)):
                merged_buffer = landuse_buffers[i]
                if streetlamp_buffer.intersects(merged_buffer):
                    landuse_buffers[i] = merged_buffer.union(streetlamp_buffer)
                    is_found = True
                    break
            if not is_found:
                landuse_buffers.append(streetlamp_buffer)
    return landuse_buffers


def _process_osm_power_aerialway(nodes_dict, ways_dict, fg_elev: utilities.FGElev, my_coord_transformator,
                                 building_refs: List[shg.Polygon]) -> Tuple[List[WayLine], List[WayLine]]:
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of WayLine objects for
    electrical power lines and a dict of WayLine objects for aerialways. Nodes are transformed to Pylons.
    The elevation of the pylons is calculated as part of this process.
    """
    my_powerlines = {}  # osm_id as key, WayLine object as value
    my_aerialways = {}  # osm_id as key, WayLine object as value
    my_shared_nodes = {}  # node osm_id as key, list of WayLine objects as value
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    way_lines = list()

    for way in list(ways_dict.values()):
        my_line = WayLine(way.osm_id)
        for key in way.tags:
            value = way.tags[key]
            if "power" == key:
                if "line" == value:
                    my_line.type_ = WayLineType.power_line
                elif "minor_line" == value:
                    my_line.type_ = WayLineType.power_minor
            elif "aerialway" == key:
                if "cable_car" == value:
                    my_line.type_ = WayLineType.aerialway_cable_car
                elif value in ["chair_lift", "mixed_lift"]:
                    my_line.type_ = WayLineType.aerialway_chair_lift
                elif value in ["drag_lift", "t-bar", "j-bar", "platter"]:
                    my_line.type_ = WayLineType.aerialway_drag_lift
                elif "gondola" == value:
                    my_line.type_ = WayLineType.aerialway_gondola
                elif "goods" == value:
                    my_line.type_ = WayLineType.aerialway_goods
            #  special values
            elif "cables" == key:
                my_line.cables = int(value)
            elif "voltage" == key:
                try:
                    my_line.voltage = int(value)
                except ValueError:
                    pass  # principally only substations may have values like "100000;25000", but only principally ...
            elif "wires" == key:
                my_line.wires = value
        if my_line.type_ == 0:
            continue
        if my_line.is_aerialway():
            first_node = nodes_dict[way.refs[0]]
            if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
                continue
            else:
                my_line.original_osm_way = way
                way_lines.append(my_line)
        else:
            split_ways = osmparser.split_way_at_boundary(nodes_dict, way, clipping_border)
            if not split_ways:
                continue
            else:
                for split_way in split_ways:
                    split_line = WayLine(way.osm_id)
                    if split_way.pseudo_osm_id != 0:
                        split_line.osm_id = way.pseudo_osm_id
                    split_line.original_osm_way = split_way
                    split_line.type_ = my_line.type_
                    split_line.cables = my_line.cables
                    split_line.voltage = my_line.voltage
                    if my_line.wires is not None:
                        split_line.wires = my_line.wires
                    way_lines.append(split_line)

    for my_line in way_lines:
        prev_pylon = None
        for ref in my_line.original_osm_way.refs:
            if ref in nodes_dict:
                my_node = nodes_dict[ref]
                my_pylon = Pylon(my_node.osm_id)
                my_pylon.lat = my_node.lat
                my_pylon.lon = my_node.lon
                my_pylon.x, my_pylon.y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                my_pylon.elevation = fg_elev.probe_elev(vec2d.Vec2d(my_pylon.lon, my_pylon.lat), True)
                for key in my_node.tags:
                    value = my_node.tags[key]
                    if "power" == key:
                        if "tower" == value:
                            my_pylon.type_ = PylonType.power_tower
                        elif "pole" == value:
                            my_pylon.type_ = PylonType.power_pole
                    elif "aerialway" == key:
                        if "pylon" == value:
                            my_pylon.type_ = PylonType.aerialway_pylon
                        elif "station" == value:
                            my_pylon.type_ = PylonType.aerialway_station
                            my_point = shg.Point(my_pylon.x, my_pylon.y)
                            for building_ref in building_refs:
                                if building_ref.contains(my_point):
                                    my_pylon.in_osm_building = True
                                    logging.debug('Station with osm_id = %s found within building reference',
                                                  my_pylon.osm_id)
                                    break
                    elif "height" == key:
                        my_pylon.height = osmparser.parse_length(value)
                    elif "structure" == key:
                        my_pylon.structure = value
                    elif "material" == key:
                        my_pylon.material = value
                if my_pylon.elevation != -9999:  # if elevation is -9999, then point is outside of boundaries
                    my_line.shared_pylons.append(my_pylon)
                else:
                    logging.debug('Node outside of boundaries and therefore ignored: osm_id = %s', my_node.osm_id)
                if prev_pylon is not None:
                    prev_pylon.next_pylon = my_pylon
                    my_pylon.prev_pylon = prev_pylon
                prev_pylon = my_pylon
        if len(my_line.shared_pylons) > 1:
            for the_node in [my_line.shared_pylons[0], my_line.shared_pylons[-1]]:
                if the_node.osm_id in list(my_shared_nodes.keys()):
                    my_shared_nodes[the_node.osm_id].append(my_line)
                else:
                    my_shared_nodes[the_node.osm_id] = [my_line]
            if my_line.is_aerialway():
                my_aerialways[my_line.osm_id] = my_line
            else:
                my_powerlines[my_line.osm_id] = my_line
        else:
            logging.warning('Line could not be validated or corrected. osm_id = %s', my_line.osm_id)

    for key in list(my_shared_nodes.keys()):
        shared_node = my_shared_nodes[key]
        if shared_node[0].is_aerialway():  # only attempt to merge power lines
            continue
        if (len(shared_node) == 2) and (shared_node[0].type_ == shared_node[1].type_):
            my_osm_id = shared_node[1].osm_id
            try:
                _merge_lines(key, shared_node[0], shared_node[1], my_shared_nodes)
                del my_powerlines[my_osm_id]
                del my_shared_nodes[key]
                logging.debug("Merged two lines with node osm_id: %s", key)
            except Exception as e:
                logging.error(e)
        elif len(shared_node) > 2:
            logging.debug("WARNING: A node is referenced in more than two ways. Most likely OSM problem. Node osm_id: %s", key)

    return list(my_powerlines.values()), list(my_aerialways.values())


def _find_connecting_line(key, lines, max_allowed_angle=360):
    """
    In the array of lines checks which 2 lines have an angle closest to 180 degrees at end node key.
    Looked at second last node and end node (key).
    If the found angle is larger than the max_allowed_angle at the end, then -1 is returned for pos1
    """
    angles = []
    # Get the angle of each line
    for line in lines:
        if line.nodes[0].osm_id == key:
            angle = coordinates.calc_angle_of_line_local(line.nodes[0].x, line.nodes[0].y,
                                                         line.nodes[1].x, line.nodes[1].y)
        elif line.nodes[-1].osm_id == key:
            angle = coordinates.calc_angle_of_line_local(line.nodes[-1].x, line.nodes[-1].y,
                                                         line.nodes[-2].x, line.nodes[-2].y)
        else:
            raise Exception("The referenced node is not at the beginning or end of line0")
        angles.append(angle)
    # Get the angles between all line pairs and find the one closest to 180 degrees
    pos1 = 0
    pos2 = 1
    max_angle = 500
    for i in range(0, len(angles) - 1):
        for j in range(i + 1, len(angles)):
            angle_between = abs(abs(angles[i] - angles[j]) - 180)
            if angle_between < max_angle:
                max_angle = angle_between
                pos1 = i
                pos2 = j
    if max_angle > max_allowed_angle:
        pos1 = -1
    return pos1, pos2


def _merge_lines(osm_id, line0, line1, shared_nodes):
    """
    Takes two Line objects and attempts to merge them at a given node.
    The added/merged pylons are in line0 in correct sequence.
    Makes sure that line1 is replaced by line0 in shared_nodes.
    Raises Exception if the referenced node is not at beginning or end of the two lines.
    """
    # Little trick to work with both WayLines and RailLines
    line0_nodes = line0.shared_pylons
    line1_nodes = line1.shared_pylons
    if isinstance(line0, RailLine):
        line0_nodes = line0.nodes
        line1_nodes = line1.nodes

    if line0_nodes[0].osm_id == osm_id:
        line0_first = True
    elif line0_nodes[-1].osm_id == osm_id:
        line0_first = False
    else:
        raise Exception("The referenced node is not at the beginning or end of line0")
    if line1_nodes[0].osm_id == osm_id:
        line1_first = True
    elif line1_nodes[-1].osm_id == osm_id:
        line1_first = False
    else:
        raise Exception("The referenced node is not at the beginning or end of line1")

    # combine line1 into line0 in correct sequence (e.g. line0(A,B) + line1(C,B) -> line0(A,B,C)
    if (line0_first is False) and (line1_first is True):
        for x in range(1, len(line1_nodes)):
            line0_nodes.append(line1_nodes[x])
    elif (line0_first is False) and (line1_first is False):
        for x in range(0, len(line1_nodes) - 1):
            line0_nodes.append(line1_nodes[len(line1_nodes) - x - 2])
    elif (line0_first is True) and (line1_first is True):
        for x in range(1, len(line1_nodes)):
            line0_nodes.insert(0, line1_nodes[x])
    else:
        for x in range(0, len(line1_nodes) - 1):
            line0_nodes.insert(0, line1_nodes[len(line1_nodes) - x - 2])

    # set back little trick
    if isinstance(line0, RailLine):
        line0.nodes = line0_nodes
        line1.nodes = line1_nodes
    else:
        line0.shared_pylons = line0_nodes
        line1.shared_pylons = line1_nodes

    # in shared_nodes replace line1 with line2
    for shared_node in list(shared_nodes.values()):
        has_line0 = False
        pos_line1 = -1
        for i in range(0, len(shared_node)):
            if shared_node[i].osm_id == line0.osm_id:
                has_line0 = True
            if shared_node[i].osm_id == line1.osm_id:
                pos_line1 = i
        if pos_line1 >= 0:
            del shared_node[pos_line1]
            if not has_line0:
                shared_node.append(line0)


def _distribute_way_segments_to_clusters(lines: List[Line], cluster_container: cluster.ClusterContainer) -> None:
    for line in lines:
        for way_segment in line.way_segments:
            anchor = vec2d.Vec2d(way_segment.start_pylon.x, way_segment.start_pylon.y)
            cluster_container.append(anchor, way_segment)


def _write_cable_clusters(cluster_container: cluster.ClusterContainer, coords_transform: coordinates.Transformation,
                          my_stg_mgr: stg_io2.STGManager) -> None:
    cluster_index = 0
    for ic, cl in enumerate(cluster_container):
        cluster_index += 1
        if not cl.objects:
            continue

        # first do some min/max calculation to be able to center the mesh
        elevation_min = 10000
        elevation_max = -10000
        x_min = 1000000000
        x_max = -1000000000
        y_min = 1000000000
        y_max = -1000000000
        for way_segment in cl.objects:
            elevation_min = min(elevation_min, way_segment.start_pylon.elevation, way_segment.end_pylon.elevation)
            elevation_max = max(elevation_max, way_segment.start_pylon.elevation, way_segment.end_pylon.elevation)
            x_min = min(x_min, way_segment.start_pylon.x, way_segment.end_pylon.x)
            x_max = max(x_max, way_segment.start_pylon.x, way_segment.end_pylon.x)
            y_min = min(y_min, way_segment.start_pylon.y, way_segment.end_pylon.y)
            y_max = max(y_max, way_segment.start_pylon.y, way_segment.end_pylon.y)

        # now write the mesh into files
        cluster_x = x_max - (x_max - x_min)/2.0
        cluster_y = y_max - (y_max - y_min)/2.0
        cluster_elevation = elevation_max - (elevation_max - elevation_min)/2.0
        center_global = coords_transform.toGlobal((cluster_x, cluster_y))
        cluster_filename = parameters.get_repl_prefix() + "cables%05d" % cluster_index
        path_to_stg = my_stg_mgr.add_object_static(cluster_filename + '.ac', vec2d.Vec2d(center_global[0],
                                                                                         center_global[1]),
                                                   cluster_elevation, 90, cluster_container.stg_verb_type)

        ac_file_lines = list()
        ac_file_lines.append("AC3Db")
        ac_file_lines.append(
            'MATERIAL "cable" rgb 0.3 0.3 0.3 amb 0.3 0.3 0.3 emis 0.0 0.0 0.0 spec 0.3 0.3 0.3 shi 1 trans 0')
        ac_file_lines.append("OBJECT world")
        ac_file_lines.append("kids " + str(len(cl.objects)))
        segment_index = 0
        for way_segment in cl.objects:
            segment_index += 1
            ac_file_lines.append("OBJECT group")
            ac_file_lines.append('name "segment%05d"' % segment_index)
            ac_file_lines.append("kids " + str(len(way_segment.cables)))
            for cable in way_segment.cables:
                cable.translate_vertices_relative(cluster_x, cluster_y, cluster_elevation)
                ac_file_lines.append(cable.make_ac_entry(0))  # material is 0-indexed

                with open(path_to_stg + cluster_filename + ".ac", 'w') as f:
                    f.write("\n".join(ac_file_lines))


def _write_stg_entries_pylons_for_line(my_stg_mgr, lines_list: List[Line]) -> None:
    line_index = 0
    for line in lines_list:
        line_index += 1
        line.make_shared_pylons_stg_entries(my_stg_mgr)


def _calc_heading_nodes(nodes_array: List[SharedPylon]) -> None:
    """Calculates the headings of nodes in a line based on medium angle. nodes must have a heading, x and y attribute"""
    current_pylon = nodes_array[0]
    next_pylon = nodes_array[1]
    current_angle = coordinates.calc_angle_of_line_local(current_pylon.x, current_pylon.y, next_pylon.x, next_pylon.y)
    current_pylon.heading = current_angle
    for x in range(1, len(nodes_array) - 1):
        prev_angle = current_angle
        current_pylon = nodes_array[x]
        next_pylon = nodes_array[x + 1]
        current_angle = coordinates.calc_angle_of_line_local(current_pylon.x, current_pylon.y,
                                                             next_pylon.x, next_pylon.y)
        current_pylon.heading = _calc_middle_angle(prev_angle, current_angle)
    nodes_array[-1].heading = current_angle


def _calc_middle_angle(angle_line1, angle_line2):
    """Returns the angle halfway between two lines"""
    if angle_line1 == angle_line2:
        middle = angle_line1
    elif angle_line1 > angle_line2:
        if 0 == angle_line2:
            middle = _calc_middle_angle(angle_line1, 360)
        else:
            middle = angle_line1 - (angle_line1 - angle_line2) / 2
    else:
        if math.fabs(angle_line2 - angle_line1) > 180:
            middle = _calc_middle_angle(angle_line1 + 360, angle_line2)
        else:
            middle = angle_line2 - (angle_line2 - angle_line1) / 2
    if 360 <= middle:
        middle -= 360
    return middle


def _stg_angle(angle_normal):
    """Returns the input angle in degrees to an angle for the stg-file in degrees.
    stg-files use angles counter-clockwise starting with 0 in North."""
    if 0 == angle_normal:
        return 0
    else:
        return 360 - angle_normal


def _optimize_catenary(half_distance_pylons: float, max_value: float, sag: float, max_variation: float):
    """
    Calculates the parameter _a_ for a catenary with a given sag between the pylons and a max_variation.
    See http://www.mathdemos.org/mathdemos/catenary/catenary.html and https://en.wikipedia.org/wiki/Catenary
    Max variation is factor applied to sag.
    """
    my_variation = sag * max_variation
    for a in range(1, max_value):
        value = a * math.cosh(float(half_distance_pylons)/a) - a  # float() needed to make sure result is float
        if (value >= (sag - my_variation)) and (value <= (sag + my_variation)):
            return a, value
    return -1, -1


def _process_osm_building_refs(nodes_dict, ways_dict, my_coord_transformator, fg_elev: utilities.FGElev,
                               storage_tanks: List[StorageTank]) -> List[shg.Polygon]:
    """Takes all buildings to be used as potential blocking areas. At the same time processes storage tanks.
    Storage tanks are in OSM mapped as buildings, but with special tags. In FG use shared model.
    Storage tanks get updated by passed as reference list.
    http://wiki.openstreetmap.org/wiki/Tag:man%20made=storage%20tank?uselang=en-US.
    """
    my_buildings = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for way in list(ways_dict.values()):
        for key in way.tags:
            if "building" == key:
                my_coordinates = list()
                for ref in way.refs:
                    if ref in nodes_dict:
                        my_node = nodes_dict[ref]
                        my_coordinates.append(my_coord_transformator.toLocal((my_node.lon, my_node.lat)))
                if 2 < len(my_coordinates):
                    my_polygon = shg.Polygon(my_coordinates)
                    if my_polygon.is_valid and not my_polygon.is_empty:
                        my_buildings.append(my_polygon.convex_hull)
                        # process storage tanks
                        if way.tags['building'] in ['storage_tank', 'tank'] or (
                                    'man_made' in way.tags and way.tags['man_made'] in ['storage_tank', 'tank']):
                            my_centroid = my_polygon.centroid
                            lon, lat = my_coord_transformator.toGlobal((my_centroid.x, my_centroid.y))
                            if not clipping_border.contains(shg.Point(lon, lat)):
                                continue
                            radius = coordinates.calc_distance_global(lon, lat, my_node.lon, my_node.lat)
                            if radius < 5:  # do not want very small objects
                                continue
                            elev = fg_elev.probe_elev(vec2d.Vec2d(lon, lat), True)
                            storage_tanks.append(StorageTank(way.osm_id, lon, lat, way.tags, radius, elev))
    logging.info("Found {} storage tanks".format(len(storage_tanks)))
    return my_buildings


class LinearOSMFeature(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.linear = None  # The LinearString of the line

    def get_width(self):
        """The width incl. border as a float in meters"""
        raise NotImplementedError("Please implement this method")


class Highway(LinearOSMFeature):

    def __init__(self, osm_id):
        super().__init__(osm_id)
        self.is_roundabout = False

    def get_width(self):
        highway_attributes = roads.get_highway_attributes(self.type_)
        return highway_attributes[2]


def _process_osm_highway(nodes_dict, ways_dict, my_coord_transformator):
    my_highways = dict()  # osm_id as key, Highway

    for way in list(ways_dict.values()):
        my_highway = Highway(way.osm_id)
        valid_highway = False
        is_challenged = False
        for key in way.tags:
            value = way.tags[key]
            if "highway" == key:
                valid_highway = True
                my_highway.type_ = roads.highway_type_from_osm_tags(value)
                if None is my_highway.type_:
                    valid_highway = False
            elif ("tunnel" == key) and ("yes" == value):
                is_challenged = True
            elif ("junction" == key) and ("roundabout" == value):
                my_highway.is_roundabout = True
        if valid_highway and not is_challenged:
            # Process the Nodes
            my_coordinates = list()
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 2:
                my_highway.linear = shg.LineString(my_coordinates)
                my_highways[my_highway.osm_id] = my_highway

    return my_highways


class Landuse(object):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for land-uses constructed with heuristics and not in original data from OSM

    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.polygon = None  # the polygon defining its outer boundary
        self.number_of_buildings = 0  # only set for generated TYPE_NON_OSM land-uses during generation


def _process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator):
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
            # Process the Nodes
            my_coordinates = list()
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_landuse.polygon = shg.Polygon(my_coordinates)
                if my_landuse.polygon.is_valid and not my_landuse.polygon.is_empty:
                    my_landuses[my_landuse.osm_id] = my_landuse

    logging.debug("OSM land-uses found: %s", len(my_landuses))
    return my_landuses


def _generate_landuse_from_buildings(osm_landuses, building_refs: List[shg.Polygon]):
    """Adds "missing" landuses based on building clusters"""
    my_landuse_candidates = dict()
    index = 10000000000
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
            for candidate in list(my_landuse_candidates.values()):
                if buffer_polygon.intersects(candidate.polygon):
                    candidate.polygon = candidate.polygon.union(buffer_polygon)
                    candidate.number_of_buildings += 1
                    within_existing_landuse = True
                    break
            if not within_existing_landuse:
                index += 1
                my_candidate = Landuse(index)
                my_candidate.polygon = buffer_polygon
                my_candidate.number_of_buildings = 1
                my_candidate.type_ = Landuse.TYPE_NON_OSM
                my_landuse_candidates[my_candidate.osm_id] = my_candidate
    # add landuse candidates to landuses
    logging.debug("Candidate land-uses found: %s", len(my_landuse_candidates))
    for candidate in list(my_landuse_candidates.values()):
        if candidate.polygon.area < parameters.LU_LANDUSE_MIN_AREA:
            del my_landuse_candidates[candidate.osm_id]
    logging.debug("Candidate land-uses with sufficient area found: %s", len(my_landuse_candidates))

    return my_landuse_candidates


def _fetch_osm_file_data() -> Tuple[Dict[int, osmparser.Node], Dict[int, osmparser.Way]]:
    start_time = time.time()
    # the lists below are in sequence: buildings references, power/aerialway, railway overhead, landuse and highway
    valid_node_keys = ["power", "structure", "material", "height", "colour", "aerialway",
                       "railway",
                       "power=generator", "generator:output:electricity", "generator:type", "generator:source",
                       "offshore", "rotor:diameter", "manufacturer", "manufacturer:type",
                       "seamark:landmark:height", "seamark:landmark:status", "seamark:status"]
    valid_way_keys = ["building",
                      "power", "aerialway", "voltage", "cables", "wires",
                      "railway", "electrified", "tunnel",
                      "landuse",
                      "highway", "junction"]
    valid_relation_keys = []
    req_relation_keys = []
    req_way_keys = ["building", "power", "aerialway", "railway", "landuse", "highway"]
    handler = osmparser.OSMContentHandlerOld(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                             req_relation_keys)
    osm_file_name = parameters.get_OSM_file_name()
    source = open(osm_file_name, encoding="utf8")
    xml.sax.parse(source, handler)
    logging.info("Reading OSM data from xml took {0:.4f} seconds.".format(time.time() - start_time))
    return handler.nodes_dict, handler.ways_dict


def process(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev) -> None:
    # Transform to real objects
    logging.info("Transforming OSM data to Line and Pylon objects")

    osm_nodes_dict = dict()  # key = osm_id, value = Node
    osm_ways_dict = dict()  # key = osm_id, value = Way
    if not parameters.USE_DATABASE:
        osm_nodes_dict, osm_ways_dict = _fetch_osm_file_data()

    # References for buildings
    building_refs = list()
    storage_tanks = list()
    if parameters.C2P_PROCESS_POWERLINES or parameters.C2P_PROCESS_AERIALWAYS or parameters.C2P_PROCESS_STREETLAMPS \
            or parameters.C2P_PROCESS_STORAGE_TANKS:
        if parameters.USE_DATABASE:
            osm_way_result = osmparser.fetch_osm_db_data_ways_keys(['building'])
            osm_nodes_dict = osm_way_result.nodes_dict
            osm_ways_dict = osm_way_result.ways_dict
        building_refs = _process_osm_building_refs(osm_nodes_dict, osm_ways_dict, coords_transform, fg_elev,
                                                   storage_tanks)
        logging.info('Number of reference buildings: %s', len(building_refs))
    # Power lines and aerialways
    powerlines = list()
    aerialways = list()
    if parameters.C2P_PROCESS_POWERLINES or parameters.C2P_PROCESS_AERIALWAYS:
        if parameters.USE_DATABASE:
            req_keys = list()
            if parameters.C2P_PROCESS_POWERLINES:
                req_keys.append("power")
            if parameters.C2P_PROCESS_POWERLINES:
                req_keys.append("aerialway")
            osm_way_result = osmparser.fetch_osm_db_data_ways_keys(req_keys)
            osm_nodes_dict = osm_way_result.nodes_dict
            osm_ways_dict = osm_way_result.ways_dict

        powerlines, aerialways = _process_osm_power_aerialway(osm_nodes_dict, osm_ways_dict, fg_elev,
                                                              coords_transform, building_refs)
        if not parameters.C2P_PROCESS_POWERLINES:
            powerlines = list()
        if not parameters.C2P_PROCESS_AERIALWAYS:
            aerialways = list()
        logging.info('Number of power lines to process: %s', len(powerlines))
        logging.info('Number of aerialways to process: %s', len(aerialways))
        for wayline in reversed(powerlines):
            wayline.calc_and_map()
            if (wayline.type_ is WayLineType.power_minor) and (not parameters.C2P_PROCESS_POWERLINES_MINOR):
                powerlines.remove(wayline)
        for wayline in aerialways:
            wayline.calc_and_map()
    # railway overhead lines
    rail_lines = list()
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        if parameters.USE_DATABASE:
            osm_way_result = osmparser.fetch_osm_db_data_ways_keys(['railway'])
            osm_nodes_dict = osm_way_result.nodes_dict
            osm_ways_dict = osm_way_result.ways_dict
        rail_lines = _process_osm_rail_overhead(osm_nodes_dict, osm_ways_dict, fg_elev,
                                                coords_transform)
        logging.info('Reduced number of rail lines: %s', len(rail_lines))
        for rail_line in rail_lines:
            rail_line.calc_and_map(fg_elev, coords_transform, rail_lines)
    # street lamps
    streetlamp_ways = list()
    if parameters.C2P_PROCESS_STREETLAMPS:
        if parameters.USE_DATABASE:
            osm_way_result = osmparser.fetch_osm_db_data_ways_keys(["landuse", "highway"])
            osm_nodes_dict = osm_way_result.nodes_dict
            osm_ways_dict = osm_way_result.ways_dict

        landuse_refs = _process_osm_landuse_refs(osm_nodes_dict, osm_ways_dict, coords_transform)
        if parameters.LU_LANDUSE_GENERATE_LANDUSE:
            generated_landuses = _generate_landuse_from_buildings(landuse_refs, building_refs)
            for generated in list(generated_landuses.values()):
                landuse_refs[generated.osm_id] = generated
        logging.info('Number of landuse references: %s', len(landuse_refs))
        streetlamp_buffers = _merge_streetlamp_buffers(landuse_refs)
        logging.info('Number of streetlamp buffers: %s', len(streetlamp_buffers))
        highways = _process_osm_highway(osm_nodes_dict, osm_ways_dict, coords_transform)
        streetlamp_ways = _process_highways_for_streetlamps(highways, streetlamp_buffers)
        logging.info('Reduced number of streetlamp ways: %s', len(streetlamp_ways))
        for highway in streetlamp_ways:
            highway.calc_and_map(fg_elev, coords_transform)
        del landuse_refs
    # wind turbines
    wind_turbines = list()
    if parameters.C2P_PROCESS_WIND_TURBINES:
        if parameters.USE_DATABASE:
            osm_nodes_dict = osmparser.fetch_db_nodes_isolated(["generator:source=>wind"])
        wind_turbines = _process_osm_wind_turbines(osm_nodes_dict, coords_transform, fg_elev)
        logging.info("Number of valid wind turbines found: {}".format(len(wind_turbines)))

    # free some memory
    del building_refs

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    stg_manager = stg_io2.STGManager(path_to_output, SCENERY_TYPE, OUR_MAGIC, parameters.get_repl_prefix())

    # Write to Flightgear
    cmin, cmax = parameters.get_extent_global()
    logging.info("min/max " + str(cmin) + " " + str(cmax))
    lmin = vec2d.Vec2d(coords_transform.toLocal(cmin))
    lmax = vec2d.Vec2d(coords_transform.toLocal(cmax))
    cluster_container = cluster.ClusterContainer(lmin, lmax, stg_io2.STGVerbType.object_building_mesh_detailed)

    if parameters.C2P_PROCESS_POWERLINES:
        _distribute_way_segments_to_clusters(powerlines, cluster_container)
        _write_stg_entries_pylons_for_line(stg_manager, powerlines)
    if parameters.C2P_PROCESS_AERIALWAYS:
        _distribute_way_segments_to_clusters(aerialways, cluster_container)
        _write_stg_entries_pylons_for_line(stg_manager, aerialways)
    if parameters.C2P_PROCESS_OVERHEAD_LINES:
        _distribute_way_segments_to_clusters(rail_lines, cluster_container)
        _write_stg_entries_pylons_for_line(stg_manager, rail_lines)

    _write_cable_clusters(cluster_container, coords_transform, stg_manager)

    if parameters.C2P_PROCESS_STREETLAMPS:
        _write_stg_entries_pylons_for_line(stg_manager, streetlamp_ways)
    if parameters.C2P_PROCESS_WIND_TURBINES:
        for turbine in wind_turbines:
            turbine.make_stg_entry(stg_manager)
    if parameters.C2P_PROCESS_STORAGE_TANKS:
        for tank in storage_tanks:
            tank.make_stg_entry(stg_manager)

    stg_manager.write()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="pylons.py reads OSM data and creates pylons, powerlines and aerialways for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel", dest="loglevel",
                        help="Set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument("-e", dest="skip_elev", action="store_true",
                        help="skip elevation interpolation", required=False)
    args = parser.parse_args()
    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    if args.skip_elev:
        parameters.NO_ELEV = True
    parameters.show()

    my_coords_transform = coordinates.Transformation(parameters.get_center_global())
    my_fg_elev = utilities.FGElev(my_coords_transform)

    process(my_coords_transform, my_fg_elev)

    my_fg_elev.close()

    logging.info("******* Finished *******")


# ================ UNITTESTS =======================


class TestOSMPylons(unittest.TestCase):
    def test_middle_angle(self):
        self.assertEqual(0, _calc_middle_angle(0, 0), "North North")
        self.assertEqual(45, _calc_middle_angle(0, 90), "North East")
        self.assertEqual(130, _calc_middle_angle(90, 170), "East Almost_South")
        self.assertEqual(90, _calc_middle_angle(135, 45), "South_East North_East")
        self.assertEqual(0, _calc_middle_angle(45, 315), "South_East North_East")
        self.assertEqual(260, _calc_middle_angle(170, 350), "Almost_South Almost_North")

    def test_wayline_calculate_and_map(self):
        # first test headings
        pylon1 = Pylon(1)
        pylon1.x = -100
        pylon1.y = -100
        pylon2 = Pylon(2)
        pylon2.x = 100
        pylon2.y = 100
        wayline1 = WayLine(100)
        wayline1.type_ = WayLineType.power_line
        wayline1.shared_pylons.append(pylon1)
        wayline1.shared_pylons.append(pylon2)
        wayline1.calc_and_map()
        self.assertAlmostEqual(45, pylon1.heading, 2)
        self.assertAlmostEqual(45, pylon2.heading, 2)
        pylon3 = Pylon(3)
        pylon3.x = 0
        pylon3.y = 100
        pylon4 = Pylon(4)
        pylon4.x = -100
        pylon4.y = 200
        wayline1.shared_pylons.append(pylon3)
        wayline1.shared_pylons.append(pylon4)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon2.heading, 2)
        self.assertAlmostEqual(292.5, pylon3.heading, 2)
        self.assertAlmostEqual(315, pylon4.heading, 2)
        pylon5 = Pylon(5)
        pylon5.x = -100
        pylon5.y = 300
        wayline1.shared_pylons.append(pylon5)
        wayline1.calc_and_map()
        self.assertAlmostEqual(337.5, pylon4.heading, 2)
        self.assertAlmostEqual(0, pylon5.heading, 2)
        # then test other stuff
        self.assertEqual(4, len(wayline1.way_segments))

    def test_cable_vertex_calc_position(self):
        vertex = CableVertex(10, 5)
        vertex.calc_position(0, 0, 20, 0)
        self.assertAlmostEqual(25, vertex.elevation, 2)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(0, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 90)
        self.assertAlmostEqual(0, vertex.x, 2)
        self.assertAlmostEqual(-10, vertex.y, 2)
        vertex.calc_position(0, 0, 20, 210)
        self.assertAlmostEqual(-8.660, vertex.x, 2)
        self.assertAlmostEqual(5, vertex.y, 2)
        vertex.calc_position(20, 50, 20, 180)
        self.assertAlmostEqual(10, vertex.x, 2)
        self.assertAlmostEqual(50, vertex.y, 2)

    def test_catenary(self):
        #  Values taken form example 2 in http://www.mathdemos.org/mathdemos/catenary/catenary.html
        a, value = _optimize_catenary(170, 5000, 14, 0.001)
        print(a, value)
        self.assertAlmostEqual(1034/100, a/100, 2)

    def test_merge_lines(self):
        line_u = RailLine("u")
        line_v = RailLine("v")
        line_w = RailLine("w")
        line_x = RailLine("x")
        line_y = RailLine("y")
        node1 = RailNode("1")
        node2 = RailNode("2")
        node3 = RailNode("3")
        node4 = RailNode("4")
        node5 = RailNode("5")
        node6 = RailNode("6")
        node7 = RailNode("7")
        shared_nodes = {}

        line_u.nodes.append(node1)
        line_u.nodes.append(node2)
        line_v.nodes.append(node2)
        line_v.nodes.append(node3)
        _merge_lines("2", line_u, line_v, shared_nodes)
        self.assertEqual(3, len(line_u.nodes))
        line_w.nodes.append(node1)
        line_w.nodes.append(node4)
        _merge_lines("1", line_u, line_w, shared_nodes)
        self.assertEqual(4, len(line_u.nodes))
        line_x.nodes.append(node5)
        line_x.nodes.append(node3)
        _merge_lines("3", line_u, line_x, shared_nodes)
        self.assertEqual(5, len(line_u.nodes))
        line_y.nodes.append(node7)
        line_y.nodes.append(node6)
        line_y.nodes.append(node4)
        _merge_lines("4", line_u, line_y, shared_nodes)
        self.assertEqual(7, len(line_u.nodes))

    def find_connecting_line(self):
        node1 = RailNode("1")
        node1.x = 5
        node1.y = 10
        node2 = RailNode("2")
        node2.x = 10
        node2.y = 10
        node3 = RailNode("3")
        node3.x = 20
        node3.y = 5
        node4 = RailNode("4")
        node4.x = 20
        node4.y = 20

        line_u = RailLine("u")
        line_u.nodes.append(node1)
        line_u.nodes.append(node2)
        line_v = RailLine("v")
        line_v.nodes.append(node2)
        line_v.nodes.append(node3)
        line_w = RailLine("w")
        line_w.nodes.append(node4)
        line_w.nodes.append(node2)

        lines = [line_u, line_v, line_w]
        pos1, pos2 = _find_connecting_line("2", lines)
        self.assertEqual(0, pos1)
        self.assertEqual(1, pos2)
