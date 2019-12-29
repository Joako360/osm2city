"""Handles reading from apt.dat airport files and read/write to pickle file for minimized representation.
See http://developer.x-plane.com/?article=airport-data-apt-dat-file-format-specification for the specification.

Flightgear 2016.4 can read multiple apt.data files - see e.g. http://wiki.flightgear.org/FFGo
and https://sourceforge.net/p/flightgear/flightgear/ci/516a5cf016a7d504b09aaac2e0e66c7e9efd42b2/.
However this module does only support reading from the apt.dat.gz in $FG_ROOT/Airports/apt.dat.gz).

"""

from abc import ABCMeta, abstractmethod
import gzip
import logging
import os
from osm2city import parameters
import time
from typing import List, Optional

from shapely.affinity import rotate
from shapely.geometry import box, CAP_STYLE, LineString, Point, Polygon

from osm2city.utils import utilities, coordinates
from osm2city.utils.vec2d import Vec2d


class Boundary:
    def __init__(self) -> None:
        self.nodes_lists = list()  # a list of list of Nodes, where a Node is a tuple (lon, lat)

    def append_nodes_list(self, nodes_list) -> None:
        self.nodes_lists.append(nodes_list)

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        """If no node within - or there are no nodes - then return False.
        That is ok, because at least the runways will be checked."""
        if len(self.nodes_lists) == 0:
            return False
        for my_list in self.nodes_lists:
            for lon_lat in my_list:
                if (min_lon <= lon_lat[0] <= max_lon) and (min_lat <= lon_lat[1] <= max_lat):
                    return True
        return False

    def create_polygon_buffer(self, transformer: coordinates.Transformation) -> Optional[List[Polygon]]:
        if self.not_empty:
            boundaries = list()
            for my_list in self.nodes_lists:
                if len(my_list) < 3:
                    continue
                my_boundary = Polygon([transformer.to_local(n) for n in my_list])
                if my_boundary.is_valid:
                    boundaries.append(my_boundary)
            return utilities.merge_buffers(boundaries)
        return None

    @property
    def not_empty(self) -> bool:
        if self.nodes_lists:
            return True
        return False


class Runway(metaclass=ABCMeta):
    @abstractmethod
    def within_boundary(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> bool:
        pass

    @abstractmethod
    def create_blocked_area(self, coords_transform: coordinates.Transformation) -> Polygon:
        pass


class LandRunway(Runway):
    def __init__(self, width: float, start: Vec2d, end: Vec2d) -> None:
        self.width = width
        self.start = start  # global coordinates
        self.end = end  # global coordinates

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        if (min_lon <= self.start.x <= max_lon) and (min_lat <= self.start.y <= max_lat):
            return True
        if (min_lon <= self.end.x <= max_lon) and (min_lat <= self.end.y <= max_lat):
            return True
        return False

    def create_blocked_area(self, coords_transform):
        line = LineString([coords_transform.to_local((self.start.x, self.start.y)),
                           coords_transform.to_local((self.end.x, self.end.y))])
        return line.buffer(self.width / 2.0, cap_style=CAP_STYLE.flat)


class Helipad(Runway):
    def __init__(self, length: float, width: float, center: Vec2d, orientation: float) -> None:
        self.length = length
        self.width = width
        self.center = center  # global coordinates
        self.orientation = orientation

    def within_boundary(self, min_lon, min_lat, max_lon, max_lat):
        if (min_lon <= self.center.x <= max_lon) and (min_lat <= self.center.y <= max_lat):
            return True
        return False

    def create_blocked_area(self, coords_transform):
        my_point = Point(coords_transform.to_local((self.center.x, self.center.y)))
        my_box = box(my_point.x - self.length / 2, my_point.y - self.width / 2,
                     my_point.x + self.length / 2, my_point.y + self.width / 2)
        return rotate(my_box, self.orientation)


class Airport(object):
    def __init__(self, code: str) -> None:
        self.code = code
        self.runways = list()  # LandRunways, Helipads
        self.airport_boundary = None
        self.pavements = list()  # Pavement of type Boundary

    def append_runway(self, runway: Runway) -> None:
        self.runways.append(runway)

    def append_airport_boundary(self, airport_boundary: Boundary) -> None:
        self.airport_boundary = airport_boundary

    def append_pavement(self, pavement_boundary: Boundary) -> None:
        self.pavements.append(pavement_boundary)

    def within_boundary(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> bool:
        for runway in self.runways:
            if runway.within_boundary(min_lon, min_lat, max_lon, max_lat):
                return True
        if self.airport_boundary is not None \
                and self.airport_boundary.within_boundary(min_lon, min_lat, max_lon, max_lat):
            return True
        return False

    def create_blocked_areas(self, coords_transform: coordinates.Transformation,
                             for_buildings: bool) -> List[Polygon]:
        blocked_areas = list()
        for runway in self.runways:
            blocked_areas.append(runway.create_blocked_area(coords_transform))
        pavement_include_list = parameters.OVERLAP_CHECK_PAVEMENT_ROADS_INCLUDE
        if for_buildings:
            pavement_include_list = parameters.OVERLAP_CHECK_PAVEMENT_BUILDINGS_INCLUDE
        if self.code in pavement_include_list:
            for pavement in self.pavements:
                pavement_buffers = pavement.create_polygon_buffer(coords_transform)
                for pb in pavement_buffers:
                    blocked_areas.append(pb)
        return blocked_areas

    def create_boundary_polygons(self, coords_transform: coordinates.Transformation) -> Optional[List[Polygon]]:
        if self.airport_boundary is None:
            return None
        else:
            return self.airport_boundary.create_polygon_buffer(coords_transform)


def read_apt_dat_gz_file(min_lon: float, min_lat: float,
                         max_lon: float, max_lat: float) -> List[Airport]:
    apt_dat_gz_file = os.path.join(utilities.get_fg_root(), 'Airports', 'apt.dat.gz')
    start_time = time.time()
    airports = list()
    total_airports = 0
    with gzip.open(apt_dat_gz_file, 'rt', encoding="latin-1") as f:
        my_airport = None
        boundary = None
        current_boundary_nodes = list()
        in_boundary = False
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if in_boundary:
                if parts[0] not in ['111', '112', '113', '114', '115', '116']:
                    in_boundary = False
                else:
                    current_boundary_nodes.append((float(parts[2]), float(parts[1])))
                    if parts[0] in ['113', '114']:  # closed loop
                        boundary.append_nodes_list(current_boundary_nodes)
                        current_boundary_nodes = list()
            if parts[0] in ['1', '16', '17', '99']:
                # first actually append the previously read airport data to the collection if within bounds
                if (my_airport is not None) and (my_airport.within_boundary(min_lon, min_lat, max_lon, max_lat)):
                    airports.append(my_airport)
                # and then create a new empty airport
                if not parts[0] == '99':
                    my_airport = Airport(parts[4])
                    total_airports += 1
            elif parts[0] == '100':
                my_runway = LandRunway(float(parts[1]), Vec2d(float(parts[10]), float(parts[9])),
                                       Vec2d(float(parts[19]), float(parts[18])))
                my_airport.append_runway(my_runway)
            elif parts[0] == '102':
                my_helipad = Helipad(float(parts[5]), float(parts[6]), Vec2d(float(parts[3]), float(parts[2])),
                                     float(parts[4]))
                my_airport.append_runway(my_helipad)
            elif parts[0] == '110':  # Pavement
                boundary = Boundary()
                in_boundary = True
                my_airport.append_pavement(boundary)
            elif parts[0] == '130':  # Airport boundary header
                boundary = Boundary()
                in_boundary = True
                my_airport.append_airport_boundary(boundary)

    logging.info("Read %d airports, %d having runways/helipads within the boundary", total_airports, len(airports))
    utilities.time_logging("Execution time", start_time)
    return airports


def get_apt_dat_blocked_areas_from_airports(coords_transform: coordinates.Transformation,
                                            min_lon: float, min_lat: float, max_lon: float, max_lat: float,
                                            airports: List[Airport], for_buildings: bool) -> List[Polygon]:
    """Transforms runways in airports to polygons.
    Even though get_apt_dat_blocked_areas(...) already checks for boundary it is checked here again because if used
    from batch, then first boundary of whole batch area is used - and first then reduced to tile boundary.

    If include_pavement is False, then only runways/helipads are considered"""
    blocked_areas = list()
    for airport in airports:
        if airport.within_boundary(min_lon, min_lat, max_lon, max_lat):
            blocked_areas.extend(airport.create_blocked_areas(coords_transform, for_buildings))
    return blocked_areas
