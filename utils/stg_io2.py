# -*- coding: utf-8 -*-
"""
Manage I/O for .stg files. There are two classes, STGManager and STGFile.

STGManager is the main interface for writing OBJECT_STATIC (_SHARED will
follow) to .stg files. It knows about the scenery path, tile indices etc. You
only need to provide the actual ac_file_name, position, elevation, hdg.
See __main__ for usage.

STG_file represents an .stg file. Usually you don't deal with them directly,

@author: tom
"""
import enum
import logging
import multiprocessing as mp
import os
import time
from typing import List, Optional

from shapely import affinity
import shapely.geometry as shg

import parameters
from utils import calc_tile
from utils.coordinates import Transformation
from utils.vec2d import Vec2d


@enum.unique
class LOD(enum.IntEnum):
    rough = 0
    detail = 1


@enum.unique
class STGVerbType(enum.IntEnum):  # must be the same as actual string in lowercase in FGFS
    object_shared = 1
    object_static = 2
    object_building_mesh_rough = 3
    object_building_mesh_detailed = 4
    object_road_rough = 5
    object_road_detailed = 6
    object_railway_rough = 7
    object_railway_detailed = 8


@enum.unique
class SceneryType(enum.IntEnum):
    buildings = 1
    roads = 2
    pylons = 3
    details = 4


def scenery_directory_name(scenery_type: SceneryType) -> str:
    """Return a capitalized version to be used in directory naming"""
    return scenery_type.name.title()


def parse_for_scenery_type(type_argument: str) -> SceneryType:
    """Parses a command line argument to determine which osm2city procedure to run.
    Returns KeyError if mapping cannot be done"""
    return SceneryType.__members__[type_argument.lower()]


class STGFile(object):
    """represents an .stg file.
       takes care of writing/reading/uninstalling OBJECT_* lines
    """
    
    def __init__(self, lon_lat: Vec2d, tile_index: int, path_to_scenery: str, scenery_type: SceneryType,
                 magic: str, prefix: str) -> None:
        """Read all lines from stg to memory.
           Store our/other lines in two separate lists."""
        scenery_name = scenery_directory_name(scenery_type)
        self.path_to_stg = calc_tile.construct_path_to_stg(path_to_scenery, scenery_name, (lon_lat.lon, lon_lat.lat))
        self.file_name = os.path.join(self.path_to_stg, calc_tile.construct_stg_file_name_from_tile_index(tile_index))
        self.other_list = []
        self.our_list = []
        self.our_ac_file_name_list = []
        self.prefix = prefix
        self.our_magic_start = _make_delimiter_string(magic, prefix, True)
        self.our_magic_end = _make_delimiter_string(magic, prefix, False)

    def _read(self) -> None:
        """read others and ours from file"""
        try:
            stg = open(self.file_name, 'r')
            lines = stg.readlines()
            stg.close()
        except IOError as ioe:
            logging.debug("Error reading %s as it might not exist yet: %s", self.file_name, ioe)
            return

        self.other_list = []
        # if our magic is not present, then use the whole file content
        if lines.count(self.our_magic_start) == 0:
            self.other_list = lines
            return
        # otherwise handle the possibility for several sections
        while lines.count(self.our_magic_start) > 0:
            try:
                ours_start = lines.index(self.our_magic_start)
            except ValueError:
                self.other_list = lines
                break

            try:
                ours_end = lines.index(self.our_magic_end)
            except ValueError:
                ours_end = len(lines)

            self.other_list = self.other_list + lines[:ours_start]
            lines = lines[ours_end + 1:]

    def add_object(self, stg_verb: str, ac_file_name: str, lon_lat, elev: float, hdg: float, once=False) -> str:
        """add OBJECT_XXXXX line to our_list. Returns path to stg."""
        line = "%s %s %1.5f %1.5f %1.2f %g\n" % (stg_verb.upper(),
                                                 ac_file_name, lon_lat.lon, lon_lat.lat, elev, hdg)
        if once is False or (ac_file_name not in self.our_ac_file_name_list):
            self.our_list.append(line)
            self.our_ac_file_name_list.append(ac_file_name)
            logging.debug(self.file_name + ':' + line)
        # Make sure the path exists. Needs to be done already now, because e.g. ac-files might be written to the path
        _make_path_to_stg(self.path_to_stg)
        return self.path_to_stg

    def write(self) -> None:
        """write stg-objects from other procedures (e.g. piers.py) and our procedure (e.g. pylons.py) to file.
        Other stuff is read if the file already exists.
        Our stuff was added through the add_object(...) method.
        """
        # Read the current content if it already exists
        self._read()
        # Write the content
        stg = open(self.file_name, 'w')
        logging.info("Writing %d other lines" % len(self.other_list))
        for line in self.other_list:
            stg.write(line)

        if self.our_list:
            logging.info("Writing %d lines" % len(self.our_list))
            stg.write(self.our_magic_start)
            stg.write("# do not edit below this line\n")
            stg.write("# Last Written %s\n#\n" % time.strftime("%c"))
            for line in self.our_list:
                logging.debug(line.strip())
                stg.write(line)
            stg.write(self.our_magic_end)

        stg.close()


def _make_path_to_stg(path_to_stg: str) -> None:
    try:
        os.makedirs(path_to_stg)
    except OSError as e:
        if e.errno != 17:
            logging.exception('Unable to create path to output %s', path_to_stg)
            raise e


class STGManager(object):
    """manages STG objects. Knows about scenery path.
       prefix separates different writers to work around two PREFIX areas interleaving 
    """
    def __init__(self, path_to_scenery: str, scenery_type: SceneryType, magic: str, prefix: str=None) -> None:
        self.stg_dict = dict()  # key: tile index, value: STGFile
        self.path_to_scenery = path_to_scenery
        self.magic = magic
        self.prefix = prefix
        self.scenery_type = scenery_type

    def _find_create_stg_file(self, lon_lat: Vec2d) -> STGFile:
        """Finds an STGFile for a given coordinate. If not yet registered, then new one created."""
        tile_index = calc_tile.tile_index((lon_lat.lon, lon_lat.lat))
        try:
            return self.stg_dict[tile_index]
        except KeyError:
            the_stg_file = STGFile(lon_lat, tile_index, self.path_to_scenery, self.scenery_type, self.magic,
                                   self.prefix)
            self.stg_dict[tile_index] = the_stg_file
        return the_stg_file

    def add_object_static(self, ac_file_name: str, lon_lat: Vec2d, elev: float, hdg: float,
                          stg_verb_type: STGVerbType=STGVerbType.object_static, once=False) -> str:
        """Adds OBJECT_STATIC line. Returns path to stg."""
        the_stg_file = self._find_create_stg_file(lon_lat)
        return the_stg_file.add_object(stg_verb_type.name.upper(), ac_file_name, lon_lat, elev, hdg, once)

    def add_object_shared(self, ac_file_name: str, lon_lat: Vec2d, elev:float , hdg: float) -> None:
        """Adds OBJECT_SHARED line."""
        the_stg_file = self._find_create_stg_file(lon_lat)
        the_stg_file.add_object('OBJECT_SHARED', ac_file_name, lon_lat, elev, hdg)

    def write(self, file_lock: mp.Lock=None):
        """Writes all new scenery objects including the already existing back to stg-files.
        The file_lock object makes sure that only the current process is reading and writing stg-files in order
        to avoid conflicts.
        """
        if file_lock is not None:
            file_lock.acquire()
        for key, the_stg in self.stg_dict.items():
            the_stg.write()
        if file_lock is not None:
            file_lock.release()


class STGEntry(object):
    def __init__(self, type_string: str, obj_filename: str, stg_path: str,
                 lon: float, lat: float, elev: float, hdg: float) -> None:
        self.verb_type = STGVerbType.object_shared
        self._translate_verb_type(type_string)
        self.obj_filename = obj_filename
        self.stg_path = stg_path  # the path of the stg_file without file name and trailing path-separator
        self.lon = lon
        self.lat = lat
        self.elev = elev
        self.hdg = hdg
        self.convex_hull = None  # a Polygon object set by parse_stg_entries_for_convex_hull(...) in local coordinates

    def _translate_verb_type(self, type_string: str) -> None:
        """Translates from a string in FGFS to an enumeration.
        If nothing is found, then the default in __init__ is used."""
        for verb in STGVerbType:
            if verb.name == type_string.lower():
                self.verb_type = verb
                return

    def overwrite_filename(self, new_name: str) -> None:
        if self.verb_type is STGVerbType.object_static:
            self.obj_filename = new_name
        else:
            slash_index = self.obj_filename.rfind("/")
            backslash_index = self.obj_filename.rfind("\\")
            chosen_index = max([slash_index, backslash_index])
            self.obj_filename = self.obj_filename[:chosen_index + 1] + new_name

    def get_obj_path_and_name(self, scenery_path: str=None) -> str:
        """Parameter scenery_path is most probably parameters.SCENERY_PATH.
        It can be useful to try a different path for shared_objects, which might be from Terrasync."""
        if self.verb_type is STGVerbType.object_shared:
            if scenery_path is not None:
                return os.path.join(scenery_path, self.obj_filename)

            p = os.path.abspath(self.stg_path + os.sep + '..' + os.sep + '..' + os.sep + '..')
            return os.path.abspath(os.path.join(p, self.obj_filename))
        else:
            return os.path.join(self.stg_path, self.obj_filename)


def read_stg_entries(stg_path_and_name: str, consider_shared: bool = True, our_magic: str = "",
                     ignore_bad_lines: bool = False) -> List[STGEntry]:
    """Reads an stg-file and extracts STGEntry objects outside of marked areas for our_magic.
    TODO: In the future, take care of multiple scenery paths here.
    TODO: should be able to take a list of our_magic"""
    entries = []  # list of STGEntry objects

    our_magic_start = _make_delimiter_string(our_magic, None, True)
    our_magic_end = _make_delimiter_string(our_magic, None, False)
    ours = False
    try:
        with open(stg_path_and_name, 'r') as my_file:
            path, stg_name = os.path.split(stg_path_and_name)
            for line in my_file:
                if len(our_magic) > 0:
                    if line.startswith(our_magic_start):
                        ours = True
                        continue
                    if line.startswith(our_magic_end):
                        ours = False
                        continue
                    if ours:
                        continue

                if line.startswith('#') or line.lstrip() == "":
                    continue
                if consider_shared is False and line.startswith("OBJECT_SHARED"):
                    continue
                try:
                    splitted = line.split()
                    type_ = splitted[0]
                    obj_filename = splitted[1]
                    lon = float(splitted[2])
                    lat = float(splitted[3])
                    elev = float(splitted[4])
                    hdg = float(splitted[5])
                    entry = STGEntry(type_, obj_filename, path, lon, lat, elev, hdg)
                    entries.append(entry)                
                except ValueError as reason:
                    if not ignore_bad_lines:
                        logging.warning("stg_io:read: Damaged file %s", reason)
                        logging.warning("Damaged line: %s", line.strip())
                        return []
                    else:
                        logging.warning("Damaged line: %s", line.strip())
                except IndexError as reason:
                    if not ignore_bad_lines:
                        logging.warning("stg_io:read: Ignoring unreadable file %s", reason)
                        logging.warning("Offending line: %s", line.strip())
                        return []
                    else:
                        logging.warning("Damaged line: %s", line.strip())
    except IOError as reason:
        logging.warning("stg_io:read: Ignoring unreadable file %s", reason)
        return []
    return entries


def read_stg_entries_in_boundary(consider_shared: bool=True, my_coord_transform: Transformation=None) -> List[STGEntry]:
    """Returns a list of all STGEntries within the boundary according to parameters.
    It uses the PATH_TO_SCENERY and PATH_TO_SCENERY_OPT (which are static), not PATH_TO_OUTPUT.
    If my_cord_transform is set, then for each entry the convex hull is calculated in local coordinates.
    """
    stg_entries = list()
    stg_files = calc_tile.get_stg_files_in_boundary(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                    parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH,
                                                    parameters.PATH_TO_SCENERY, "Objects")

    if parameters.PATH_TO_SCENERY_OPT:
        for my_path in parameters.PATH_TO_SCENERY_OPT:
            stg_files_opt = calc_tile.get_stg_files_in_boundary(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                                parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH,
                                                                my_path, "Objects")
            stg_files.extend(stg_files_opt)

    for filename in stg_files:
        stg_entries.extend(read_stg_entries(filename, consider_shared))

    if my_coord_transform is not None:
        _parse_stg_entries_for_convex_hull(stg_entries, my_coord_transform)
    return stg_entries


def _parse_stg_entries_for_convex_hull(stg_entries: List[STGEntry], my_coord_transformation: Transformation) -> None:
    """
    Parses the ac-file content for a set of STGEntry objects and sets their boundary attribute
    to be the convex hull of all points in the ac-file in the specified local coordinate system.
    If there is a problem creating the convex hull, then the stg_entry will be removed.
    """
    ac_filename = ""
    for entry in reversed(stg_entries):
        if entry.verb_type in [STGVerbType.object_static, STGVerbType.object_shared]:
            try:
                ac_filename = entry.obj_filename
                if ac_filename.endswith(".xml"):
                    entry.overwrite_filename(_extract_ac_from_xml(entry.get_obj_path_and_name(),
                                                                  entry.get_obj_path_and_name(
                                                                      parameters.PATH_TO_SCENERY)))
                boundary_polygon = _extract_boundary(entry.get_obj_path_and_name(),
                                                     entry.get_obj_path_and_name(parameters.PATH_TO_SCENERY))
                rotated_polygon = affinity.rotate(boundary_polygon, entry.hdg - 90, (0, 0))
                x_y_point = my_coord_transformation.toLocal((entry.lon, entry.lat))
                translated_polygon = affinity.translate(rotated_polygon, x_y_point[0], x_y_point[1])
                if entry.verb_type is STGVerbType.object_static and parameters.OVERLAP_CHECK_CH_BUFFER_STATIC > 0.01:
                    entry.convex_hull = translated_polygon.buffer(
                        parameters.OVERLAP_CHECK_CH_BUFFER_STATIC, shg.CAP_STYLE.square)
                elif entry.verb_type is STGVerbType.object_shared and parameters.OVERLAP_CHECK_CH_BUFFER_SHARED > 0.01:
                    entry.convex_hull = translated_polygon.buffer(
                        parameters.OVERLAP_CHECK_CH_BUFFER_SHARED, shg.CAP_STYLE.square)
                else:
                    entry.convex_hull = translated_polygon
            except IOError as reason:
                logging.warning("Ignoring unreadable stg_entry %s", reason)
            except ValueError as e:
                # Happens e.g. for waterfalls, where the xml-file only references a <particlesystem>
                logging.debug("AC-filename could be wrong in xml-file %s - or just no ac-file referenced", ac_filename)
            if entry.convex_hull is None:
                stg_entries.remove(entry)


def _extract_boundary(ac_filename: str, alternative_ac_filename: str=None) -> shg.Polygon:
    """Reads an ac-file and constructs a convex hull as a proxy to the real boundary.
    No attempt is made to follow rotations and translations.
    Returns a tuple (x_min, y_min, x_max, y_max) in meters.
    An alternative path is tried, if the first path is not successful"""
    numvert = 0
    points = list()
    try:
        checked_filename = ac_filename
        if not os.path.isfile(checked_filename) and alternative_ac_filename is not None:
            checked_filename = alternative_ac_filename
        with open(checked_filename, 'r') as my_file:
            for my_line in my_file:
                if 0 == my_line.find("numvert"):
                    numvert = int(my_line.split()[1])
                elif numvert > 0:
                    vertex_values = my_line.split()
                    # minus factor in y-axis due to ac3d coordinate system. Switch of y_min and y_max for same reason
                    points.append((float(vertex_values[0]), -1 * float(vertex_values[2])))
                    numvert -= 1
    except IOError as e:
        raise e

    hull_polygon = shg.MultiPoint(points).convex_hull
    return hull_polygon


def _parse_ac_file_name(xml_string: str) -> str:
    """Finds the corresponding ac-file in an xml-file"""
    try:
        x1 = xml_string.index("<path>")
        x2 = xml_string.index("</path>", x1)
    except ValueError as e:
        raise e
    ac_file_name = (xml_string[x1+6:x2]).strip()
    return ac_file_name


def _extract_ac_from_xml(xml_filename: str, alternative_xml_filename: str=None) -> str:
    """Reads the *.ac filename out of an xml-file"""
    checked_filename = xml_filename
    if not os.path.isfile(checked_filename) and alternative_xml_filename is not None:
        checked_filename = alternative_xml_filename
    with open(checked_filename, 'r') as f:
        xml_data = f.read()
        ac_filename = _parse_ac_file_name(xml_data)
        return ac_filename


def _make_delimiter_string(our_magic: Optional[str], prefix: Optional[str], is_start: bool) -> str:
    if our_magic is None:
        magic = ""
    else:
        magic = our_magic
    delimiter = '# '
    if not is_start:
        delimiter += 'END '
    if prefix is None:
        return delimiter + magic + '\n'
    else:
        return delimiter + magic + '_' + prefix + '\n'
