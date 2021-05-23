"""
Diverse utility methods used throughout osm2city and not having a clear other home.
"""

import datetime
import enum
import logging
import math
import os
import os.path as osp
import pickle
import random
import subprocess
import sys
import textwrap
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import unittest

from shapely import affinity
import shapely.geometry as shg
from shapely.geometry import Polygon
from shapely.ops import unary_union

import osm2city.utils.coordinates as co
import osm2city.utils.log_helper as ulog
import osm2city.utils.osmparser as op
from osm2city import parameters


def get_osm2city_directory() -> str:
    """Determines the absolute path of the osm2city root directory.

    Used e.g. when copying roads.eff, elev.nas and other resources.
    """
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]  # now we are in the osm2city/osm2city/utils directory
    my_dir = osp.split(my_dir)[0]  # now we are in the osm2city/osm2city directory
    my_dir = osp.split(my_dir)[0]  # now we are in the root osm2city directory
    return my_dir


def get_fg_root() -> str:
    """Reads the path to FG_ROOT based on environment variable.
    If it is not set, then exit.
    """
    my_fg_root = os.getenv("FG_ROOT")
    if my_fg_root is None:
        logging.error("$FG_ROOT must be set as an environment variable on operating system level")
        sys.exit(1)
    my_fg_root = my_fg_root.strip()
    logging.debug("FG_ROOT is set to value '{}'".format(my_fg_root))
    return my_fg_root


def get_fg_home() -> Optional[str]:
    """Constructs the path to FGHome.

    See also http://wiki.flightgear.org/$FG_HOME
    If the operating system cannot be determined the function returns None.
    Otherwise a platform specific path.
    """
    home_dir = osp.expanduser("~")
    my_os_type = get_os_type()
    if my_os_type is OSType.windows:
        home = os.getenv("APPDATA", "APPDATA_NOT_FOUND") + os.sep + "flightgear.org" + os.sep
        return home.replace("\\", "/")
    elif my_os_type is OSType.linux:
        return home_dir + "/.fgfs/"
    elif my_os_type is OSType.mac:
        return home_dir + "/Library/Application Support/FlightGear/"
    else:
        return None


@enum.unique
class OSType(enum.IntEnum):
    windows = 1
    linux = 2
    mac = 3
    other = 4


def get_os_type() -> OSType:
    if sys.platform.startswith("win"):
        return OSType.windows
    elif sys.platform.startswith("linux"):
        return OSType.linux
    elif sys.platform.startswith("darwin"):
        return OSType.mac
    else:
        return OSType.other


def is_linux_or_mac() -> bool:
    my_os_type = get_os_type()
    if my_os_type is OSType.linux or my_os_type is OSType.mac:
        return True
    return False


def date_time_now() -> str:
    """Date and time as of now formatted as a string incl. seconds."""
    today = datetime.datetime.now()
    return today.strftime("%Y-%m-%d_%H%M%S")


def replace_with_os_separator(path: str) -> str:
    """Switches forward and backward slash depending on os."""
    my_string = path.replace("/", os.sep)
    my_string = my_string.replace("\\", os.sep)
    return my_string


def match_local_coords_with_global_nodes(local_list: List[Tuple[float, float]], ref_list: List[int],
                                         all_nodes: Dict[int, op.Node],
                                         coords_transform: co.Transformation, osm_id: int,
                                         create_node: bool = False) -> List[int]:
    """Given a set of coordinates in local space find matching Node objects in global space.
    Matching is using a bit of tolerance (cf. parameter), which should be enough to account for conversion precision
    resp. float precision.
    If a node cannot be matched: if parameter create_node is False, then a ValueError is thrown - else a new
    Node is created and added to the all_nodes dict.
    """
    matched_nodes = list()
    nodes_local = dict()  # key is osm_id from Node, value is Tuple[float, float]
    for ref in ref_list:
        node = all_nodes[ref]
        nodes_local[node.osm_id] = coords_transform.to_local((node.lon, node.lat))

    for local in local_list:
        closest_distance = 999999
        found_key = -1
        for key, node_local in nodes_local.items():
            distance = co.calc_distance_local(local[0], local[1], node_local[0], node_local[1])
            if distance < closest_distance:
                closest_distance = distance
            if distance < parameters.TOLERANCE_MATCH_NODE:
                found_key = key
                break
        if found_key < 0:
            if create_node:
                lon, lat = coords_transform.to_global(local)
                new_node = op.Node(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_relation), lat, lon)
                all_nodes[new_node.osm_id] = new_node
                matched_nodes.append(new_node.osm_id)
            else:
                raise ValueError('No match for parent with osm_id = %d. Closest: %f' % (osm_id, closest_distance))
        else:
            matched_nodes.append(found_key)

    return matched_nodes


class Troubleshoot:
    def __init__(self):
        self.msg = ""
        self.n_problems = 0

    def skipped_no_elev(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not obtain their elevation.\n" % self.n_problems
        msg += textwrap.dedent("""
        Make sure
        - you have FG's scenery tiles for your area installed
        - PATH_TO_SCENERY is correct\n
        """)
        return msg

    def skipped_no_texture(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not find a matching texture.\n\n" % self.n_problems
        return msg


class FGElev(object):
    """Probes elevation and ground solidness via fgelev.
       By default, queries are cached. Call save_cache() to
       save the cache to disk before freeing the object.
    """
    def __init__(self, coords_transform: Optional[co.Transformation], tile_index: int,
                 auto_save_every: int = 50000) -> None:
        """Open pipe to fgelev.
           Unless disabled by cache=False, initialize the cache and try to read
           it from disk. Automatically save the cache to disk every auto_save_every misses.
           If fake=True, never do any probing and return 0 on all queries.
        """
        self.auto_save_every = auto_save_every
        self.h_offset = 0
        self.fgelev_pipe = None
        self.record = 0
        self.coords_transform = coords_transform

        self._cache = None  # dictionary of tuple of float for elevation and boolean for is_solid

        self.pkl_fname = None
        if parameters.FG_ELEV_CACHE and not parameters.NO_ELEV:
            self.pkl_fname = str(tile_index) + '_elev.pkl'
            try:
                logging.info("Loading %s", self.pkl_fname)
                fpickle = open(self.pkl_fname, 'rb')
                self._cache = pickle.load(fpickle)
                fpickle.close()
                logging.info("OK")
            except (IOError, EOFError) as reason:
                logging.info("Loading elev cache failed (%s)", reason)
                self._cache = {}

    def _open_fgelev(self) -> None:
        logging.info("Spawning fgelev")
        fgelev_args = [parameters.FG_ELEV]
        if parameters.PROBE_FOR_WATER:
            fgelev_args.append('--print-solidness')
        fgelev_args.append('--expire')
        fgelev_args.append(str(1000000))
        fgelev_args.append('--fg-scenery')
        fgelev_args.append(parameters.PATH_TO_SCENERY)
        self.fgelev_pipe = subprocess.Popen(fgelev_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            bufsize=1, universal_newlines=True)

    def close(self) -> None:
        try:
            if self.fgelev_pipe is not None:
                self.fgelev_pipe.kill()
            self._save_cache()
        except:
            logging.warning('Unable to close FGElev process. You might have to kill it manually at the very end.')

    def _save_cache(self) -> None:
        if parameters.NO_ELEV or not parameters.FG_ELEV_CACHE:
            return
        fpickle = open(self.pkl_fname, 'wb')
        pickle.dump(self._cache, fpickle, -1)
        fpickle.close()

    def probe_elev(self, position: Tuple[float, float], is_global: bool = False) -> float:
        elev_is_solid_tuple = self.probe(position, is_global)
        return elev_is_solid_tuple[0]

    def probe_solid(self, position: Tuple[float, float], is_global: bool = False) -> bool:
        elev_is_solid_tuple = self.probe(position, is_global)
        return elev_is_solid_tuple[1]

    def probe(self, position: Tuple[float, float], is_global: bool = False) -> Tuple[float, bool]:
        """Return elevation and ground solidness at (x,y). We try our cache first. Failing that, call Fgelev.
        Elevation is in meters as float. Solid is True, in water is False
        """
        def really_probe(a_position: co.Vec2d) -> Tuple[float, bool]:
            if not self.fgelev_pipe:
                self._open_fgelev()
            if math.isnan(a_position.lon) or math.isnan(a_position.lat):
                logging.error("Nan encountered while probing elevation")
                return -9999, True

            try:
                self.fgelev_pipe.stdin.write("%i %1.10f %1.10f\r\n" % (self.record, a_position.lon, a_position.lat))
            except IOError as reason:
                logging.error(reason)

            empty_lines = 0
            line = ""
            try:
                while line == "" and empty_lines < 20:
                    empty_lines += 1
                    line = self.fgelev_pipe.stdout.readline().strip()
                    if line.startswith('Now checking') or line.startswith('osg::Registry::addImageProcessor') or \
                            line.startswith('Loaded plug-in'):  # New in FG Git version end of Dec 20188
                        line = ""
                parts = line.split()
                elev = float(parts[1]) + self.h_offset
                is_solid = True
                if parameters.PROBE_FOR_WATER:
                    if len(parts) == 3:
                        if parts[2] == '-':
                            is_solid = False
                    else:
                        logging.debug('ERROR: Probing for water with fgelev missed to return value for water: %s', line)
            except IndexError as reason:
                self.close()
                if empty_lines > 1:
                    logging.fatal("Skipped %i lines" % empty_lines)
                logging.fatal("%i %g %g" % (self.record, a_position.lon, a_position.lat))
                logging.fatal("fgelev returned <%s>, resulting in %s. Did fgelev start OK (Record : %i)?",
                              line, reason, self.record)
                raise RuntimeError("fgelev errors are fatal.")
            return elev, is_solid

        if parameters.NO_ELEV:
            return 0, True

        if not is_global:
            position = co.Vec2d(self.coords_transform.to_global(position))
        else:
            position = co.Vec2d(position[0], position[1])

        self.record += 1
        if self._cache is None:
            return really_probe(position)

        key = (position.lon, position.lat)
        try:
            elev_is_solid_tuple = self._cache[key]
            return elev_is_solid_tuple
        except KeyError:
            elev_is_solid_tuple = really_probe(position)
            self._cache[key] = elev_is_solid_tuple

            if self.auto_save_every and len(self._cache) % self.auto_save_every == 0:
                self._save_cache()
            return elev_is_solid_tuple

    def probe_list_of_points(self, points: List[Tuple[float, float]]) -> (float, float):
        """Get the elevation of the node lowest node of a list of points.
        If a node is in water or at -9999, then return -9999
        Second returned value is the difference between the highest and the lowest point.
        """
        elev_water_ok = True
        min_ground_elev = 9999
        max_ground_elev = -999
        for point in points:
            elev_is_solid_tuple = self.probe(point)
            if elev_is_solid_tuple[0] == -9999:
                logging.debug("-9999")
                elev_water_ok = False
                break
            elif not elev_is_solid_tuple[1]:
                logging.debug("in water")
                elev_water_ok = False
                break
            if min_ground_elev > elev_is_solid_tuple[0]:
                min_ground_elev = elev_is_solid_tuple[0]
            if max_ground_elev < elev_is_solid_tuple[0]:
                max_ground_elev = elev_is_solid_tuple[0]
        if not elev_water_ok:
            return -9999, 0
        return min_ground_elev, max_ground_elev - min_ground_elev


def progress(i, max_i):
    """progress indicator"""
    if sys.stdout.isatty() and ulog.log_level_info_or_lower():
        try:
            if i % (max_i / 100) > 0:
                return
        except ZeroDivisionError:
            pass
        print("%i %i %5.1f%%     \r" % (i+1, max_i, (float(i+1)/max_i) * 100), end='')
        if i > max_i - 2:
            print()


class BoundaryError(Exception):
    """Indicates wrong values to define the boundary of the scenery."""
    def __init__(self, message: str) -> None:
        self.message = message


def parse_boundary(boundary_string: str) -> Optional[List[float]]:
    """Parses the boundary argument provided as an underscore delimited string into 4 floats for lon/lat.

    Raises BoundaryError if cannot be parsed into 4 floats.
    """
    boundary_parts = boundary_string.replace("*", "").split("_")
    if len(boundary_parts) != 4:
        message = "Boundary must have four elements separated by '_': {} has only {} element(s) \
        -> aborting!".format(boundary_string, len(boundary_parts))
        raise BoundaryError(message)

    boundary_float_list = list()
    for i in range(len(boundary_parts)):
        try:
            boundary_float_list.append(float(boundary_parts[i]))
        except ValueError as my_value_error:
            message = "Boundary part {} cannot be parsed as float (decimal)".format(boundary_parts[i])
            raise BoundaryError(message) from my_value_error
    return boundary_float_list


def check_boundary(boundary_west: float, boundary_south: float,
                   boundary_east: float, boundary_north: float) -> None:
    """Check whether the boundary values actually make sense.

    Raise BoundaryError if there is a problem.
    """
    if boundary_west >= boundary_east:
        raise BoundaryError("Boundary West {} must be smaller than East {} -> aborting!".format(boundary_west,
                                                                                                boundary_east))
    if boundary_south >= boundary_north:
        raise BoundaryError("Boundary South {} must be smaller than North {} -> aborting!".format(boundary_south,
                                                                                                  boundary_north))
    # make sure that we are within safe latitude for calculations
    # in FG when tile span more than 1 deg it can get tricky -> http://wiki.flightgear.org/Tile_Index_Scheme
    # For most map projection the farther to the north the more tricky.
    if boundary_north > 83 or math.fabs(boundary_south) > 83:
        raise BoundaryError('Latitudes must be less than 83 N / 83 S')


def bounds_from_list(bounds_list: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    """Finds the bounds (min_x, min_y, max_x, max_y) from a list of bounds.

    If the list of bounds is None or empty, then (0,0,0,0) is returned."""
    if not bounds_list:
        return 0, 0, 0, 0

    min_x = sys.float_info.max
    min_y = sys.float_info.max
    max_x = sys.float_info.min
    max_y = sys.float_info.min

    for bounds in bounds_list:
        min_x = min(min_x, bounds[0])
        min_y = min(min_y, bounds[1])
        max_x = max(max_x, bounds[2])
        max_y = max(max_y, bounds[3])

    return min_x, min_y, max_x, max_y


def random_value_from_ratio_dict_parameter(ratio_parameter: Dict[Any, float]):
    target_ratio = random.random()
    return value_from_ratio_dict_parameter(target_ratio, ratio_parameter)


def value_from_ratio_dict_parameter(target_ratio: float, ratio_parameter: Dict[Any, float]):
    """Finds the key value closet to and below the target ratio."""
    total_ratio = 0.
    return_value = None
    for key, ratio in ratio_parameter.items():
        if target_ratio <= total_ratio:
            return return_value
        return_value = key
        total_ratio += ratio
    return return_value


def time_logging(message: str, last_time: float) -> float:
    current_time = time.time()
    logging.info(message + ": %f", current_time - last_time)
    return current_time


def minimum_circumference_rectangle_for_polygon(hull: shg.Polygon) -> Tuple[float, float, float]:
    """Constructs a minimum circumference rectangle around a polygon and returns its angle, length and width
    There is no check whether length is longer than width - or that length is closer to e.g. the x-axis.

    This is different from a bounding box, which just uses min/max along axis.
    See https://gis.stackexchange.com/questions/22895/finding-minimum-area-rectangle-for-given-points

    Circumference is used as opposed to typically area because often buildings tend to be less quadratic.

    The general idea is that at least one edge of the polygon will be aligned with an edge of the rectangle.
    Therefore Go through all edges of the polygon, rotate it down to normal axis, create a bounding box and
    save the dimensions incl. angle. Then compare with others obtained.

    Often the polygon is a convex hull for points. In osm2city it might be the convex hull of a building.

    A different algorithm also discussed in the article referenced above is using m matrix multiplication instead
    of trigonometrics.

    For an overview see also: David Eberly, 2015: Minimum-Area Rectangle Containing A Set of Points.
    www.geometrictools.com
    """
    min_angle = 0.
    min_length = 0.
    min_width = 0.
    min_circumference = 99999999.
    hull_coords = hull.exterior.coords[:]  # list of x,y tuples
    for index in range(len(hull_coords) - 1):
        angle = co.calc_angle_of_line_local(hull_coords[index][0], hull_coords[index][1],
                                            hull_coords[index + 1][0], hull_coords[index + 1][1])
        rotated_hull = affinity.rotate(hull, - angle, (0, 0))
        bounding_box = rotated_hull.bounds  # tuple x_min, y_min, x_max, y_max
        bb_length = math.fabs(bounding_box[2] - bounding_box[0])
        bb_width = math.fabs(bounding_box[3] - bounding_box[1])
        circumference = 2 * (bb_length + bb_width)
        if circumference < min_circumference:
            min_angle = angle
            if bb_length >= bb_width:
                min_length = bb_length
                min_width = bb_width
                min_angle += 90  # it happens to be such that the angle is against the y-axis
            else:
                min_length = bb_width
                min_width = bb_length
            min_circumference = circumference

    return min_angle, min_length, min_width


def fit_offsets_for_rectangle_with_hull(angle: float, hull: shg.Polygon, model_length: float, model_width: float,
                                        model_length_offset: float, model_width_offset: float,
                                        model_length_largest: bool,
                                        model_name: str, osm_id: int) -> Tuple[float, float]:
    """Makes sure that a rectangle (bounding box) on a convex hull fits as good as possible and returns centroid.

    This is necessary because the angle out of function minimum_circumference_rectangle_for_polygon(...) cannot be
    known whether it should have been +/- 180 degrees (depends on which point in hull gets started with at least
    if the hull was a rectangle to begin with).

    NB: length_largest could also be calculated on the fly, but is chosen to be consistent with caller in building_lib.
    """
    # if both the length and width offsets are null, then the centroid will always be the hull's centroid
    if model_length_offset == 0 and model_width_offset == 0:
        return hull.centroid.x, hull.centroid.y

    # need to correct the offsets based on whether the model has longer length or width
    my_length = model_length
    my_width = model_width
    my_length_offset = model_length_offset
    my_width_offset = model_width_offset
    if not model_length_largest:
        my_length = model_width
        my_width = model_length
        my_length_offset = model_width_offset
        my_width_offset = model_length_offset

    box = shg.box(-my_length/2, -my_width/2, my_length/2, my_width/2)
    box = affinity.rotate(box, angle)
    box = affinity.translate(box, hull.centroid.x, hull.centroid.y)

    # need to correct along x-axis and y-axis due to offsets in the ac-model
    correction_x = math.sin(angle) * my_length_offset
    correction_x += math.cos(angle) * my_width_offset
    correction_y = math.cos(angle) * my_length_offset
    correction_y += math.sin(angle) * my_width_offset

    box_minus = affinity.translate(box, -correction_x, -correction_y)
    difference_minus = box_minus.difference(hull)
    box_plus = affinity.translate(box, correction_x, correction_y)
    difference_plus = box_plus.difference(hull)

    new_x = hull.centroid.x - correction_x
    new_y = hull.centroid.y - correction_y
    if difference_minus.area > difference_plus.area:
        new_x = hull.centroid.x + correction_x
        new_y = hull.centroid.y + correction_y

    if parameters.DEBUG_PLOT_OFFSETS:
        plot_fit_offsets(hull, box_minus, box_plus, angle, model_length_largest,
                         new_x, new_y, model_name, osm_id)

    return new_x, new_y


def _safe_index(index: int, number_of_elements: int) -> int:
    """Makes sure that if index flows over it continues at start"""
    if index > number_of_elements - 1:
        return index - number_of_elements
    else:
        return index


def simplify_balconies(original: shg.Polygon, distance_tolerance_line: float,
                       distance_tolerance_away: float, refs_shared: Dict[Any, Set[int]]) -> Set[int]:
    """Removes edges from polygons, which look like balconies on a building.
    Removes always 4 points at a time.

    Let us assume a building front with nodes 0, 1, .., 5 - where nodes [1, 2, 3, 4] would form a balcony. Then
    after removing these four points the new front would be [0, 5]. To make sure that it was a balcony and we do
    not remove e.g. something that looks like a staircase, we make sure that neither point 1 or 4 is very distant
    from the new front -> parameter distance_tolerance_line.
    Also to make sure it is not a too distinguishing feature by not letting the outer points 2 and 3 be too far
    away from the new front.

    The refs_shared dictionary makes sure that no shared references (with other buildings) are simplified away.
    The dictionary might get updated if points are taken away.

    Does one simplification at a time and should therefore be called until None is returned.
    """
    to_remove_points = set()  # index positions
    counter = 0
    my_coords = list(original.exterior.coords)
    del my_coords[-1]  # we do not need the repeated first point closing the polygon
    num_coords = len(my_coords)
    while counter < len(my_coords):
        # check that there would be at least 3 nodes left
        if num_coords - len(to_remove_points) < 7:
            break
        all_positions = list()
        for pos_lists in refs_shared.values():
            all_positions.extend(pos_lists)
        set_positions = set(all_positions)
        if not (_safe_index(counter + 1, num_coords) in set_positions
                or _safe_index(counter + 2, num_coords) in set_positions
                or _safe_index(counter + 3, num_coords) in set_positions
                or _safe_index(counter + 4, num_coords) in set_positions):
            valid_removal = False
            base_line = shg.LineString([my_coords[counter], my_coords[_safe_index(counter + 5, num_coords)]])
            my_point = shg.Point(my_coords[_safe_index(counter + 1, num_coords)])
            if base_line.distance(my_point) < distance_tolerance_line:
                my_point = shg.Point(my_coords[_safe_index(counter + 4, num_coords)])
                if base_line.distance(my_point) < distance_tolerance_line:
                    my_point = shg.Point(my_coords[_safe_index(counter + 2, num_coords)])
                    if base_line.distance(my_point) < distance_tolerance_away:
                        my_point = shg.Point(my_coords[_safe_index(counter + 3, num_coords)])
                        if base_line.distance(my_point) < distance_tolerance_away:
                            valid_removal = True
            if valid_removal:
                for i in range(1, 5):
                    to_remove_points.add(_safe_index(counter + i, num_coords))

                for key, pos_list in refs_shared.items():
                    new_pos_set = set()
                    for pos in pos_list:
                        to_remove_smaller_than_pos = 0
                        for i in range(1, 5):
                            if _safe_index(counter + i, num_coords) < pos:
                                to_remove_smaller_than_pos += 1
                        new_pos_set.add(pos - to_remove_smaller_than_pos)
                    refs_shared[key] = new_pos_set
                break  # do not continue the while loop once we have found one balcony to remove
        counter += 1
    return to_remove_points


def merge_buffers(original_list: List[Polygon]) -> List[Polygon]:
    """Attempts to merge as many polygon buffers with each other as possible to return a reduced list.
    The try/catch are needed due to maybe issues in Shapely with huge amounts of polys.
    See https://github.com/Toblerity/Shapely/issues/47. Seen problems with BTG-data, but then in the slow method
    actually no poly got discarded."""
    # first make sure that the polygons merged are actually good polygons
    cleaned_list = list()
    for poly in original_list:
        if poly is None or poly.is_empty or poly.is_valid is False:
            continue
        cleaned_list.append(poly)

    if len(cleaned_list) < 2:
        return cleaned_list

    multi_polygon = cleaned_list[0]
    try:
        multi_polygon = unary_union(cleaned_list)
    except ValueError:  # No Shapely geometry can be created from null value
        for other_poly in cleaned_list[1:]:  # lets do it slowly one at a time
            try:
                new_multi_polygon = unary_union(other_poly)
                multi_polygon = new_multi_polygon
            except ValueError:
                pass  # just forget about this one polygon
    if isinstance(multi_polygon, Polygon):
        return [multi_polygon]

    handled_list = list()
    if multi_polygon is not None:
        for polygon in multi_polygon.geoms:
            if isinstance(polygon, Polygon):
                handled_list.append(polygon)
            else:
                logging.debug("Unary union of transport buffers resulted in an object of type %s instead of Polygon",
                              type(polygon))
    return handled_list


# ================ PLOTTING FOR VISUAL TESTING =====

import osm2city.utils.plot_utilities as pu
from descartes import PolygonPatch
from matplotlib import patches as pat
from matplotlib import pyplot as plt

from time import sleep


def plot_fit_offsets(hull: shg.Polygon, box_minus: shg.Polygon, box_plus: shg.Polygon,
                     angle: float,
                     model_length_largest: bool,
                     centroid_x: float, centroid_y: float,
                     model_name: str, osm_id: int) -> None:
    pdf_pages = pu.create_pdf_pages('fit_offset_' + str(osm_id))

    my_figure = pu.create_a4_landscape_figure()
    title = 'osm_id={},\n model={},\n angle={},\n length_largest={}'.format(osm_id, model_name, angle,
                                                                            model_length_largest)
    my_figure.suptitle(title)

    ax = my_figure.add_subplot(111)

    patch = PolygonPatch(hull, facecolor='none', edgecolor="black")
    ax.add_patch(patch)
    patch = PolygonPatch(box_minus, facecolor='none', edgecolor="green")
    ax.add_patch(patch)
    patch = PolygonPatch(box_plus, facecolor='none', edgecolor="red")
    ax.add_patch(patch)
    ax.add_patch(pat.Circle((centroid_x, centroid_y), radius=0.4, linewidth=2,
                            color='blue', fill=False))
    bounds = bounds_from_list([box_minus.bounds, box_plus.bounds])
    pu.set_ax_limits_bounds(ax, bounds)

    pdf_pages.savefig(my_figure)

    pdf_pages.close()

    sleep(2)  # to make sure we have not several files in same second


def plot_blocked_areas_roads(blocked_areas: List[shg.Polygon], ways: List[shg.LineString],
                             transform: co.Transformation) -> None:
    pdf_pages = pu.create_pdf_pages('blocked_areas_roads')

    # Generated buildings
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Blocked Areas")
    ax = my_figure.add_subplot(111)

    # first blocked areas
    pu.add_list_of_polygons(ax, blocked_areas, 'magenta', 'black')

    # then the lines
    for line in ways:
        pu.plot_line(ax, line, 'green', 1)

    pu.set_ax_limits_from_tile(ax, transform)
    pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")


def plot_blocked_areas_and_stg_entries(blocked_areas: List[shg.Polygon], static_objects: List[shg.Polygon],
                                       shared_objects: List[shg.Polygon], before: List[shg.Polygon],
                                       after: List[shg.Polygon], transform: co.Transformation) -> None:
    pdf_pages = pu.create_pdf_pages('blocked_apt_areas_incl_stg_objects')

    # Blocked areas
    my_figure = pu.create_large_figure()
    my_figure.suptitle('Blocked Areas for airports (magenta) as well as static (green) and shared (cyan) stg entries\
and buildings (yellow)')
    ax = my_figure.add_subplot(111)

    # first blocked areas
    pu.add_list_of_polygons(ax, blocked_areas, 'magenta', 'magenta')
    # then the static stg entries
    pu.add_list_of_polygons(ax, static_objects, 'green', 'green')
    # then the shared stg entries
    pu.add_list_of_polygons(ax, shared_objects, 'cyan', 'cyan')
    # and finally the shared stg entries
    pu.add_list_of_polygons(ax, before, 'yellow', 'yellow')
    pu.set_ax_limits_from_tile(ax, transform)
    pdf_pages.savefig(my_figure)

    my_figure = pu.create_large_figure()
    my_figure.suptitle('Before buildings (red) and after buildings (yellow)')
    ax = my_figure.add_subplot(111)
    pu.add_list_of_polygons(ax, before, 'red', 'red')
    pu.add_list_of_polygons(ax, after, 'yellow', 'yellow')
    pu.set_ax_limits_from_tile(ax, transform)
    pdf_pages.savefig(my_figure)

    my_figure = pu.create_large_figure()
    my_figure.suptitle('Only blocked areas')
    ax = my_figure.add_subplot(111)
    pu.add_list_of_polygons(ax, blocked_areas, 'magenta', 'magenta')
    pu.add_list_of_polygons(ax, static_objects, 'green', 'green')
    pu.add_list_of_polygons(ax, shared_objects, 'cyan', 'cyan')
    pu.set_ax_limits_from_tile(ax, transform)
    pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")


# ================ UNITTESTS =======================

class TestUtilities(unittest.TestCase):
    def test_parse_boundary_empty_string(self):
        with self.assertRaises(BoundaryError):
            parse_boundary("")

    def test_parse_boundary_three_floats(self):
        with self.assertRaises(BoundaryError):
            parse_boundary("1.1_1.2_1.2")

    def test_parse_boundary_one_not_float(self):
        with self.assertRaises(BoundaryError):
            parse_boundary("1.1_1.2_1.2_a")

    def test_parse_boundary_pass(self):
        self.assertEqual(parse_boundary("1.1_1.2_1.2_-1.2"), [1.1, 1.2, 1.2, -1.2])

    def check_boundary_east_west_wrong(self):
        with self.assertRaises(BoundaryError):
            check_boundary(2, 1, 1, 2)

    def check_boundary_south_north_wrong(self):
        with self.assertRaises(BoundaryError):
            check_boundary(-2, 1, 1, -2)

    def check_boundary_pass(self):
        self.assertEqual(None, check_boundary(-2, -3, 1, -2))

    def test_value_from_ratio_dict_parameter(self):
        ratio_parameter = {1: 0.2, 2: 0.3, 3: 0.5}
        self.assertEqual(1, value_from_ratio_dict_parameter(0.1, ratio_parameter))
        self.assertEqual(1, value_from_ratio_dict_parameter(0.2, ratio_parameter))
        self.assertEqual(2, value_from_ratio_dict_parameter(0.3, ratio_parameter))
        self.assertEqual(2, value_from_ratio_dict_parameter(0.5, ratio_parameter))
        self.assertEqual(3, value_from_ratio_dict_parameter(1., ratio_parameter))

    def test_simplify_balconies(self):
        # too few nodes
        refs_shared = dict()
        six_node_polygon = shg.Polygon([(0, 0), (10, 0), (10, 5), (9, 5), (9, 6), (0, 6)])
        simplified_poly = simplify_balconies(six_node_polygon, 0.5, 2., refs_shared)
        self.assertIsNone(simplified_poly)
        # balcony to remove
        eight_node_polygon = shg.Polygon([(0, 0), (10, 0), (10, 5), (9, 5), (9, 6), (4, 6), (4, 5), (0, 5)])
        simplified_poly = simplify_balconies(eight_node_polygon, 0.5, 2., refs_shared)
        self.assertIsNotNone(simplified_poly)
        self.assertEqual(4 + 1, len(simplified_poly.exterior.coords))
        # balcony too far away (also checking inward)
        eight_node_polygon = shg.Polygon([(0, 0), (1, 0), (1, 3), (3, 3), (3, 0), (10, 0), (10, 5), (0, 5)])
        simplified_poly = simplify_balconies(eight_node_polygon, 0.5, 2., refs_shared)
        self.assertIsNone(simplified_poly)
        # balcony base not close to line (and testing index=0 in the balcony)
        eight_node_polygon = shg.Polygon([(4, 6), (0, 5), (0, 0), (10, 0), (10, 5), (9, 6), (9, 7), (4, 7)])
        simplified_poly = simplify_balconies(eight_node_polygon, 0.5, 2., refs_shared)
        self.assertIsNone(simplified_poly)
        # two balconies to remove
        twelve_node_polygon = shg.Polygon([(0, 0), (1, 0), (1, 1), (3, 1), (3, 0), (10, 0), (10, 5), (9, 5), (9, 6),
                                           (4, 6), (4, 5), (0, 5)])
        simplified_poly = simplify_balconies(twelve_node_polygon, 0.5, 2., refs_shared)
        self.assertIsNotNone(simplified_poly)
        self.assertEqual(8 + 1, len(simplified_poly.exterior.coords))
        simplified_poly = simplify_balconies(simplified_poly, 0.5, 2., refs_shared)
        self.assertIsNotNone(simplified_poly)
        self.assertEqual(4 + 1, len(simplified_poly.exterior.coords))

        # balcony to remove not locked by refs_shared
        refs_shared = {11111: {0, 7}}
        eight_node_polygon = shg.Polygon([(0, 0), (10, 0), (10, 5), (9, 5), (9, 6), (4, 6), (4, 5), (0, 5)])
        simplified_poly = simplify_balconies(eight_node_polygon, 0.5, 2., refs_shared)
        self.assertEqual(4 + 1, len(simplified_poly.exterior.coords))
        self.assertEqual(2, len(refs_shared[11111]))
        self.assertTrue(3 in refs_shared[11111])
