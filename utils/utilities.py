"""
Diverse utility methods used throughout osm2city and not having a clear other home.
"""

from collections import defaultdict
import enum
import logging
import math
import os
import os.path as osp
import pickle
import subprocess
import sys
import textwrap
from typing import Dict, List, Optional, Tuple
import unittest

import numpy as np

import parameters
from utils import coordinates, osmparser
import utils.vec2d as ve


def get_osm2city_directory() -> str:
    """Determines the absolute path of the osm2city root directory.

    Used e.g. when copying roads.eff, elev.nas and other resources.
    """
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]  # now we are in the osm2city/utils directory
    my_dir = osp.split(my_dir)[0]
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


def replace_with_os_separator(path: str) -> str:
    """Switches forward and backward slash depending on os."""
    my_string = path.replace("/", os.sep)
    my_string = my_string.replace("\\", os.sep)
    return my_string


def match_local_coords_with_global_nodes(local_list: List[Tuple[float, float]], ref_list: List[int],
                                         all_nodes: Dict[int, osmparser.Node],
                                         coords_transform: coordinates.Transformation, osm_id: int,
                                         create_node: bool=False) -> List[int]:
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
        nodes_local[node.osm_id] = coords_transform.toLocal((node.lon, node.lat))

    for local in local_list:
        closest_distance = 999999
        found_key = -1
        for key, node_local in nodes_local.items():
            distance = coordinates.calc_distance_local(local[0], local[1], node_local[0], node_local[1])
            if distance < closest_distance:
                closest_distance = distance
            if distance < parameters.BUILDING_TOLERANCE_MATCH_NODE:
                found_key = key
                break
        if found_key < 0:
            if create_node:
                lon, lat = coords_transform.toGlobal(local)
                new_node = osmparser.Node(osmparser.get_next_pseudo_osm_id(), lat, lon)
                all_nodes[new_node.osm_id] = new_node
                matched_nodes.append(new_node.osm_id)
            else:
                raise ValueError('No match for pseudo_parent with osm_id = %d. Closest: %f' % (osm_id, closest_distance))
        else:
            matched_nodes.append(found_key)

    return matched_nodes


def write_one_gp(b, filename):
    npv = np.array(b.X_outer)
    minx = min(npv[:, 0])
    maxx = max(npv[:, 0])
    miny = min(npv[:, 1])
    maxy = max(npv[:, 1])
    dx = 0.1 * (maxx - minx)
    minx -= dx
    maxx += dx
    dy = 0.1 * (maxy - miny)
    miny -= dy
    maxy += dy

    gp = open(filename + '.gp', 'w')
    term = "png"
    ext = "png"
    gp.write(textwrap.dedent("""
    set term %s
    set out '%s.%s'
    set xrange [%g:%g]
    set yrange [%g:%g]
    set title "%s"
    unset key
    """ % (term, filename, ext, minx, maxx, miny, maxy, b.osm_id)))
    i = 0
    for v in b.X_outer:
        i += 1
        gp.write('set label "%i" at %g, %g\n' % (i, v[0], v[1]))

    gp.write("plot '-' w lp\n")
    for v in b.X_outer:
        gp.write('%g %g\n' % (v[0], v[1]))
    gp.close()


class Stats(object):
    def __init__(self):
        self.objects = 0
        self.parse_errors = 0
        self.skipped_small = 0
        self.skipped_nearby = 0
        self.skipped_texture = 0
        self.skipped_no_elev = 0
        self.buildings_in_LOD = np.zeros(3)
        self.area_levels = np.array([1, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000])
        self.corners = np.zeros(10)
        self.area_above = np.zeros_like(self.area_levels)
        self.vertices = 0
        self.surfaces = 0
        self.roof_shapes = {}
        self.have_complex_roof = 0
        self.roof_errors = 0
        self.out = None
        self.LOD = np.zeros(3)
        self.nodes_simplified = 0
        self.nodes_ground = 0
        self.textures_total = defaultdict(int)
        self.textures_used = None

    def count(self, b):
        """update stats (vertices, surfaces, area, corners) with given building's data
        """
        if b.roof_shape.name in self.roof_shapes:
            self.roof_shapes[b.roof_shape.name] += 1
        else:
            self.roof_shapes[b.roof_shape.name] = 1

        # -- stats on number of ground nodes.
        #    Complex buildings counted in corners[0]
        if b.X_inner:
            self.corners[0] += 1
        else:
            self.corners[min(b.nnodes_outer, len(self.corners)-1)] += 1

        # --stats on area
        for i in range(len(self.area_levels))[::-1]:
            if b.area >= self.area_levels[i]:
                self.area_above[i] += 1
                return i
        self.area_above[0] += 1

        return 0

    def count_LOD(self, lod):
        self.LOD[lod] += 1

    def count_texture(self, texture):
        self.textures_total[str(texture.filename)] += 1

    def print_summary(self):
        if not parameters.log_level_info_or_lower():
            return
        out = sys.stdout
        total_written = self.LOD.sum()
        lodzero = 0
        lodone = 0
        if total_written > 0:
            lodzero = 100.*self.LOD[0] / total_written
            lodone = 100.*self.LOD[1] / total_written
        out.write(textwrap.dedent("""
            total buildings %i
            parse errors    %i
            written         %i
              four-sided    %i
            skipped
              small         %i
              nearby        %i
              no elevation  %i
              no texture    %i
            """ % (self.objects, self.parse_errors, total_written, self.corners[4],
                   self.skipped_small, self.skipped_nearby, self.skipped_no_elev, self.skipped_texture)))
        roof_line = "        roof-types"
        for roof_shape in self.roof_shapes:
            roof_line += """\n          %s\t%i""" % (roof_shape, self.roof_shapes[roof_shape])
        out.write(textwrap.dedent(roof_line))

        textures_used = {k: v for k, v in self.textures_total.items() if v > 0}
        textures_notused = {k: v for k, v in self.textures_total.items() if v == 0}
        try:
            textures_used_percent = len(textures_used) * 100. / len(self.textures_total)
        except:
            textures_used_percent = 99.9

        out.write(textwrap.dedent("""
            used tex        %i out of %i (%2.0f %%)""" % (len(textures_used), len(self.textures_total), textures_used_percent)))
        out.write(textwrap.dedent("""
            Used Textures : """))
        for item in sorted(list(textures_used.items()), key=lambda item: item[1], reverse=True):
            out.write(textwrap.dedent("""
                 %i %s""" % (item[1], item[0])))
        out.write(textwrap.dedent("""
            Unused Textures : """))
        for item in sorted(list(textures_notused.items()), key=lambda item: item[1], reverse=True):
            out.write(textwrap.dedent("""
                 %i %s""" % (item[1], item[0])))
        out.write(textwrap.dedent("""
              complex       %i
              roof_errors   %i
            ground nodes    %i
              simplified    %i
            vertices        %i
            surfaces        %i
            LOD
                LOD rough       %i (%2.0f %%)
                LOD detail      %i (%2.0f %%)
            """ % (self.have_complex_roof, self.roof_errors,
                   self.nodes_ground, self.nodes_simplified,
                   self.vertices, self.surfaces,
                   self.LOD[0], lodzero,
                   self.LOD[1], lodone)))
        out.write("\narea >=\n")
        max_area_above = max(1, self.area_above.max())
        for i in range(len(self.area_levels)):
            out.write(" %5g m^2  %5i |%s\n" % (self.area_levels[i], self.area_above[i],
                      "#" * int(56. * self.area_above[i] / max_area_above)))

        if logging.getLogger().level <= logging.VERBOSE:  # @UndefinedVariable
            for name in sorted(self.textures_used):
                out.write("%s\n" % name)

        out.write("\nnumber of corners >=\n")
        max_corners = max(1, self.corners.max())
        for i in range(3, len(self.corners)):
            out.write("     %2i %6i |%s\n" % (i, self.corners[i],
                      "#" * int(56. * self.corners[i] / max_corners)))
        out.write(" complex %5i |%s\n" % (self.corners[0],
                  "#" * int(56. * self.corners[0] / max_corners)))


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


def troubleshoot(stats):
    """Analyzes statistics from Stats objects and prints out logging information"""
    msg = ""
    t = Troubleshoot()
    if stats.skipped_no_elev:
        msg += t.skipped_no_elev()
    if stats.skipped_texture:
        msg += t.skipped_no_texture()

    if t.n_problems > 0:
        logging.warning("We've detected %i problem(s):\n\n%s" % (t.n_problems, msg))


class FGElev(object):
    """Probes elevation and ground solidness via fgelev.
       By default, queries are cached. Call save_cache() to
       save the cache to disk before freeing the object.
    """
    def __init__(self, coords_transform: coordinates.Transformation, auto_save_every: int=50000) -> None:
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
            self.pkl_fname = os.path.join(parameters.PREFIX, 'elev.pkl')
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
        if self.fgelev_pipe is not None:
            self.fgelev_pipe.kill()
        self._save_cache()

    def _save_cache(self) -> None:
        if parameters.NO_ELEV or not parameters.FG_ELEV_CACHE:
            return
        fpickle = open(self.pkl_fname, 'wb')
        pickle.dump(self._cache, fpickle, -1)
        fpickle.close()

    def probe_elev(self, position: ve.Vec2d, is_global: bool=False) -> float:
        elev_is_solid_tuple = self.probe(position, is_global)
        return elev_is_solid_tuple[0]

    def probe_solid(self, position: ve.Vec2d, is_global: bool=False) -> bool:
        elev_is_solid_tuple = self.probe(position, is_global)
        return elev_is_solid_tuple[1]

    def probe(self, position: ve.Vec2d, is_global: bool=False) -> Tuple[float, bool]:
        """Return elevation and ground solidness at (x,y). We try our cache first. Failing that, call Fgelev.
        Elevation is in meters as float. Solid is True, in water is False
        """
        def really_probe(a_position: ve.Vec2d) -> Tuple[float, bool]:
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
            position = ve.Vec2d(self.coords_transform.toGlobal(position))
        else:
            position = ve.Vec2d(position[0], position[1])

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


def progress(i, max_i):
    """progress indicator"""
    if sys.stdout.isatty() and parameters.log_level_info_or_lower():
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
