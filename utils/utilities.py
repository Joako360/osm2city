"""
Diverse utility methods used throughout osm2city and not having a clear other home.
"""

import enum
import logging
import os.path as osp
import sys
import os
import textwrap
from collections import defaultdict

import numpy as np
import parameters


def get_osm2city_directory():
    """Determines the absolute path of the osm2city root directory.

    Used e.g. when copying roads.eff, elev.nas and other resources.
    """
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]  # now we are in the osm2city/utils directory
    my_dir = osp.split(my_dir)[0]
    return my_dir


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


def get_elev_in_path(home_path) -> str:
    return home_path + "elev.in"


def get_elev_out_dir(home_path) -> str:
    return home_path + "Export/"


def get_elev_out_path(home_path) -> str:
    return get_elev_out_dir(home_path) + "elev.out"


def get_original_elev_nas_path() -> str:
    my_dir = get_osm2city_directory()
    return my_dir + os.sep + "elev.nas"


def assert_trailing_slash(path):
    """Takes a path and makes sure it has an os_specific trailing slash unless the path is empty."""
    my_path = path
    if len(my_path) > 0:
        if not my_path.endswith(os.sep):
            my_path += os.sep
    return my_path


@enum.unique
class LOD(enum.IntEnum):
    bare = 0
    rough = 1
    detail = 2


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
        lodtwo = 0
        if total_written > 0:
            lodzero = 100.*self.LOD[0] / total_written
            lodone = 100.*self.LOD[1] / total_written
            lodtwo = 100.*self.LOD[2] / total_written
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
                LOD bare        %i (%2.0f %%)
                LOD rough       %i (%2.0f %%)
                LOD detail      %i (%2.0f %%)
            """ % (self.have_complex_roof, self.roof_errors,
                   self.nodes_ground, self.nodes_simplified,
                   self.vertices, self.surfaces,
                   self.LOD[0], lodzero,
                   self.LOD[1], lodone,
                   self.LOD[2], lodtwo)))
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