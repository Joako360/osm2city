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
from typing import Tuple

import numpy as np
import parameters

from utils import calc_tile
from utils import coordinates
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
    return my_fg_root


def get_fg_home() -> str:
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


def assert_trailing_slash(path: str) -> str:
    """Takes a path and makes sure it has an os_specific trailing slash unless the path is empty."""
    my_path = path
    if len(my_path) > 0:
        if not my_path.endswith(os.sep):
            my_path += os.sep
    return my_path


def replace_with_os_separator(path: str) -> str:
    """Switches forward and backward slash depending on os."""
    my_string = path.replace("/", os.sep)
    my_string = my_string.replace("\\", os.sep)
    return my_string


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
        self.roof_types = {}
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
        if b.roof_type in self.roof_types:
            self.roof_types[b.roof_type] += 1
        else:
            self.roof_types[b.roof_type] = 1

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
        for roof_type in self.roof_types:
            roof_line += """\n          %s\t%i""" % (roof_type, self.roof_types[roof_type])
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
    def __init__(self, coords_transform: coordinates.Transformation,
                 fake: bool=False, use_cache: bool=True, auto_save_every: int=50000) -> None:
        """Open pipe to fgelev.
           Unless disabled by cache=False, initialize the cache and try to read
           it from disk. Automatically save the cache to disk every auto_save_every misses.
           If fake=True, never do any probing and return 0 on all queries.
        """
        if fake:
            self.h = fake
            self.fake = True
            return
        else:
            self.fake = False

        self.auto_save_every = auto_save_every
        self.h_offset = 0
        self.fgelev_pipe = None
        self.record = 0
        self.coords_transform = coords_transform

        self._cache = None  # dictionary of tuple of float for elevation and boolean for is_solid

        if use_cache:
            self.pkl_fname = parameters.PREFIX + os.sep + 'elev.pkl'
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
        path_to_fgelev = parameters.FG_ELEV

        fgelev_cmd = path_to_fgelev
        if parameters.PROBE_FOR_WATER:
            fgelev_cmd += ' --print-solidness'
        fgelev_cmd += ' --expire 1000000 --fg-scenery ' + parameters.PATH_TO_SCENERY
        logging.info("cmd line: " + fgelev_cmd)
        self.fgelev_pipe = subprocess.Popen(fgelev_cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            bufsize=1, universal_newlines=True)

    def save_cache(self) -> None:
        """save cache to disk"""
        if self.fake:
            return
        fpickle = open(self.pkl_fname, 'wb')
        pickle.dump(self._cache, fpickle, -1)
        fpickle.close()

    def probe_elev(self, position: ve.Vec2d, is_global: bool=False, check_btg: bool=False) -> float:
        elev_is_solid_tuple = self.probe(position, is_global, check_btg)
        return elev_is_solid_tuple[0]

    def probe(self, position: ve.Vec2d, is_global: bool=False, check_btg: bool=False) -> Tuple[float, bool]:
        """Return elevation and ground solidness at (x,y). We try our cache first. Failing that, call fgelev.
        """
        def really_probe(position: ve.Vec2d) -> Tuple[float, bool]:
            if check_btg:
                btg_file = parameters.PATH_TO_SCENERY + os.sep + "Terrain" \
                           + os.sep + calc_tile.directory_name(position) + os.sep \
                           + calc_tile.construct_btg_file_name(position)
                print(calc_tile.construct_btg_file_name(position))
                if not os.path.exists(btg_file):
                    logging.error("Terrain File " + btg_file + " does not exist. Set scenery path correctly or fly there with TerraSync enabled")
                    sys.exit(2)

            if not self.fgelev_pipe:
                self._open_fgelev()
            if math.isnan(position.lon) or math.isnan(position.lat):
                logging.error("Nan encountered while probing elevation")
                return -9999, True

            try:
                self.fgelev_pipe.stdin.write("%i %1.10f %1.10f\r\n" % (self.record, position.lon, position.lat))
            except IOError as reason:
                logging.error(reason)

            empty_lines = 0
            line = ""
            try:
                while line == "" and empty_lines < 20:
                    empty_lines += 1
                    line = self.fgelev_pipe.stdout.readline().strip()
                elev = float(line.split()[1]) + self.h_offset
                is_solid = True
                if parameters.PROBE_FOR_WATER and line.split()[2] == '-':
                    is_solid = False
            except IndexError as reason:
                self.save_cache()
                if empty_lines > 1:
                    logging.fatal("Skipped %i lines" % empty_lines)
                logging.fatal("%i %g %g" % (self.record, position.lon, position.lat))
                logging.fatal("fgelev returned <%s>, resulting in %s. Did fgelev start OK (Record : %i)?",
                              line, reason, self.record)
                raise RuntimeError("fgelev errors are fatal.")
            return elev, is_solid

        if self.fake:
            return self.h, True

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
                self.save_cache()
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
