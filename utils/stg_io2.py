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
import os
import time
from typing import List, Optional

import parameters
from utils import calc_tile
from utils.vec2d import Vec2d
from utils.utilities import assert_trailing_slash


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


class STGFile(object):
    """represents an .stg file.
       takes care of writing/reading/uninstalling OBJECT_* lines
    """
    
    def __init__(self, lon_lat: Vec2d, tile_index: int, path_to_scenery: str, scenery_type: str,
                 magic: str, prefix: str) -> None:
        """Read all lines from stg to memory.
           Store our/other lines in two separate lists."""
        self.path_to_stg = calc_tile.construct_path_to_stg(path_to_scenery, scenery_type, (lon_lat.lon, lon_lat.lat))
        self.file_name = self.path_to_stg + calc_tile.construct_stg_file_name_from_tile_index(tile_index)
        self.other_list = []
        self.our_list = []
        self.our_ac_file_name_list = []
        self.magic = magic
        self.prefix = prefix
        # deprecated usage
        self.our_magic_start = _make_delimiter_string(self.magic, None, True)
        self.our_magic_end = _make_delimiter_string(self.magic, None, False)
        self.our_magic_start_new = _make_delimiter_string(self.magic, prefix, True)
        self.our_magic_end_new = _make_delimiter_string(self.magic, prefix, False)
        self.read()

    def read(self) -> None:
        """read others and ours from file"""
        try:
            stg = open(self.file_name, 'r')
            lines = stg.readlines()
            stg.close()
        except IOError as reason:
            logging.info("Error reading %s as it might not exist yet: %s", self.file_name, reason)
            return

        temp_other_list = []
        # deal with broken files containing several sections (old version)
        while lines.count(self.our_magic_start) > 0:
            try:
                ours_start = lines.index(self.our_magic_start)
            except ValueError:
                temp_other_list = lines
                break
    
            try:
                ours_end = lines.index(self.our_magic_end)
            except ValueError:
                ours_end = len(lines)

            temp_other_list = temp_other_list + lines[:ours_start]
            lines = lines[ours_end+1:]
        temp_other_list = temp_other_list + lines
        
        self.other_list = []
        # deal with broken files containing several sections (new version)
        while temp_other_list.count(self.our_magic_start_new) > 0:
            try:
                ours_start = temp_other_list.index(self.our_magic_start_new)
            except ValueError:
                self.other_list = temp_other_list
                return
    
            try:
                ours_end = temp_other_list.index(self.our_magic_end_new)
            except ValueError:
                ours_end = len(temp_other_list)

            self.other_list = self.other_list + lines[:ours_start]
            temp_other_list = temp_other_list[ours_end+1:]
        self.other_list = self.other_list + temp_other_list

    def drop_ours(self) -> None:
        """Clear our list. Call write() afterwards to finish uninstall"""
        self.our_list = []
        self.our_ac_file_name_list = []

    def add_object(self, stg_verb: str, ac_file_name: str, lon_lat, elev: float, hdg: float, once=False) -> str:
        """add OBJECT_XXXXX line to our_list. Returns path to stg."""
        line = "%s %s %1.5f %1.5f %1.2f %g\n" % (stg_verb.upper(),
                                                 ac_file_name, lon_lat.lon, lon_lat.lat, elev, hdg)
        if once is False or (ac_file_name not in self.our_ac_file_name_list):
            self.our_list.append(line)
            self.our_ac_file_name_list.append(ac_file_name)
            logging.debug(self.file_name + ':' + line)
        self._make_path_to_stg()
        return self.path_to_stg

    def _make_path_to_stg(self) -> str:
        try:
            os.makedirs(self.path_to_stg)
        except OSError as e:
            if e.errno != 17:
                logging.exception("Unable to create path to output %s", self.path_to_stg)

    def write(self) -> None:
        """write others and ours to file"""
        # read directly before write to
        self.read()
        self._make_path_to_stg()
        stg = open(self.file_name, 'w')
        logging.info("Writing %d other lines" % len(self.other_list))
        for line in self.other_list:
            stg.write(line)

        if self.our_list:
            logging.info("Writing %d lines" % len(self.our_list))
            stg.write(self.our_magic_start_new)
            stg.write("# do not edit below this line\n")
            stg.write("# Last Written %s\n#\n" % time.strftime("%c"))
            for line in self.our_list:
                logging.debug(line.strip())
                stg.write(line)
            stg.write(self.our_magic_end_new)

        stg.close()


class STGManager(object):
    """manages STG objects. Knows about scenery path.
       prefix separates different writers to work around two PREFIX areas interleaving 
    """
    def __init__(self, path_to_scenery: str, scenery_type: str, magic: str, prefix=None, overwrite=False) -> None:
        self.stg_dict = dict()  # maps tile index to stg object
        self.path_to_scenery = path_to_scenery
        self.overwrite = overwrite
        self.magic = magic
        self.prefix = prefix
        if parameters.USE_NEW_STG_VERBS:
            self.scenery_type = scenery_type
        else:
            self.scenery_type = "Objects"

    def __call__(self, lon_lat: Vec2d, overwrite=None) -> STGFile:
        """return STG object. If overwrite is given, it overrides default"""
        tile_index = calc_tile.tile_index((lon_lat.lon, lon_lat.lat))
        try:
            return self.stg_dict[tile_index]
        except KeyError:
            the_stg = STGFile(lon_lat, tile_index, self.path_to_scenery, self.scenery_type, self.magic, self.prefix)
            self.stg_dict[tile_index] = the_stg
            if overwrite is None:
                overwrite = self.overwrite
            if overwrite:
                # this will only drop the section we previously wrote ()
                the_stg.drop_ours()
        return the_stg

    def add_object_static(self, ac_file_name, lon_lat: Vec2d, elev, hdg,
                          stg_verb_type: STGVerbType=STGVerbType.object_static, once=False):
        """Adds OBJECT_STATIC line. Returns path to stg."""
        the_stg = self(lon_lat)
        return the_stg.add_object(stg_verb_type.name.upper(), ac_file_name, lon_lat, elev, hdg, once)

    def add_object_shared(self, ac_file_name, lon_lat, elev, hdg):
        """Adds OBJECT_SHARED line. Returns path to stg it was added to."""
        the_stg = self(lon_lat)
        return the_stg.add_object('OBJECT_SHARED', ac_file_name, lon_lat, elev, hdg)

    def drop_ours(self):
        for the_stg in list(self.stg_dict.values()):
            the_stg.drop_ours()

    def write(self):
        for the_stg in list(self.stg_dict.values()):
            the_stg.write()


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
                return assert_trailing_slash(scenery_path) + self.obj_filename

            p = os.path.abspath(self.stg_path + os.sep + '..' + os.sep + '..' + os.sep + '..')
            return os.path.abspath(p + os.sep + self.obj_filename)
        else:
            return self.stg_path + os.sep + self.obj_filename


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
                    logging.debug("stg: %s %s", type_, entry.get_obj_path_and_name())
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
