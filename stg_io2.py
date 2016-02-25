#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Manage I/O for .stg files. There are two classes, STG_Manager and STG_File.

STG_Manager is the main interface for writing OBJECT_STATIC (_SHARED will
follow) to .stg files. It knows about the scenery path, tile indices etc. You
only need to provide the actual ac_file_name, position, elevation, hdg.
See __main__ for usage.

STG_file represents an .stg file. Usually you don't deal with them directly,

@author: tom
"""

import logging

import shapely.geometry as shg
import os
import osm2city
import tools
from vec2d import vec2d
import calc_tile
from pdb import pm
import time


class STG_File(object):
    """represents an .stg file.
       takes care of writing/reading/uninstalling OBJECT_* lines
    """
    
    def __init__(self, lon_lat, tile_index, path_to_scenery, magic, prefix):
        """Read all lines from stg to memory.
           Store our/other lines in two separate lists."""
        self.path_to_stg = calc_tile.construct_path_to_stg(path_to_scenery, lon_lat)
        self.file_name = self.path_to_stg + "%07i.stg" % tile_index
        self.other_list = []
        self.our_list = []
        self.our_ac_file_name_list = []
        self.magic = magic
        self.prefix = prefix
        #deprecated usage
        self.our_magic_start = delimiter_string(self.magic, None, True)
        self.our_magic_end = delimiter_string(self.magic, None, False)
        self.our_magic_start_new = delimiter_string(self.magic, prefix , True)
        self.our_magic_end_new = delimiter_string(self.magic, prefix, False)
        self.read()

    def read(self):
        """read others and ours from file"""
        try:
            stg = open(self.file_name, 'r')
            lines = stg.readlines()
            stg.close()
        except IOError, reason:
            logging.warning("error reading %s: %s", self.file_name, reason)
            return


        temp_other_list = []
        #deal with broken files containing several sections (old version) 
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
#            self.our_list = lines[ours_start+1:ours_end]
            lines = lines[ours_end+1:]
        temp_other_list = temp_other_list + lines
        
        self.other_list = []
        #deal with broken files containing several sections (new version) 
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
#            self.our_list = lines[ours_start+1:ours_end]
            temp_other_list = temp_other_list[ours_end+1:]
        self.other_list = self.other_list + temp_other_list


    def drop_ours(self):
        """Clear our list. Call write() afterwards to finish uninstall"""
        self.our_list = []
        self.our_ac_file_name_list = []

    def _add_object(self, obj_prefix, ac_file_name, lon_lat, elev, hdg, once=False):
        """add OBJECT_XXXXX line to our_list. Returns path to stg."""
        line = "OBJECT_%s %s %1.5f %1.5f %1.2f %g\n" % (obj_prefix.upper(), ac_file_name, lon_lat.lon, lon_lat.lat, elev, hdg)
        if once is False or (ac_file_name not in self.our_ac_file_name_list):
            self.our_list.append(line)
            self.our_ac_file_name_list.append(ac_file_name)
            logging.debug(self.file_name + ':' + line)
        else:
            logging.debug(self.file_name + ': not writing (once=True) ' + line)
        self.make_path_to_stg()
        return self.path_to_stg

    def add_object_static(self, ac_file_name, lon_lat, elev, hdg, once=False):
        """add OBJECT_STATIC line to our_list. Returns path to stg."""
        return self._add_object('STATIC', ac_file_name, lon_lat, elev, hdg, once)

    def add_object_shared(self, ac_file_name, lon_lat, elev, hdg, once=False):
        """add OBJECT_SHARED line to our_list. Returns path to stg."""
        return self._add_object('SHARED', ac_file_name, lon_lat, elev, hdg, once)

    def make_path_to_stg(self):
        try:
            os.makedirs(self.path_to_stg)
        except OSError, e:
            if e.errno != 17:
                logging.exception("Unable to create path to output %s", self.path_to_stg)

    def write(self):
        """write others and ours to file"""
        #read directly before write to 
        self.read()
        self.make_path_to_stg()
        stg = open(self.file_name, 'w')
        logging.info("Writing %d other lines"%len(self.other_list))
        for line in self.other_list:
            stg.write(line)

        if self.our_list:
            logging.info("Writing %d lines"%len(self.our_list))
            stg.write(self.our_magic_start_new)
            stg.write("# do not edit below this line\n")
            stg.write("# Last Written %s\n#\n"%time.strftime("%c"))
            for line in self.our_list:
                logging.info(line.strip())
                stg.write(line)
            stg.write(self.our_magic_end_new)

        stg.close()


class STG_Manager(object):
    """manages STG objects. Knows about scenery path.
       prefix separates different writers to work around two PREFIX areas interleaving 
    """
    def __init__(self, path_to_scenery, magic, prefix=None, overwrite=False):
        self.stg_dict = {} # maps tile index to stg object
        self.path_to_scenery = path_to_scenery
        self.overwrite = overwrite
        self.magic = magic
        self.prefix = prefix

    def __call__(self, lon_lat, overwrite=None):
        """return STG object. If overwrite is given, it overrides default"""
        tile_index = calc_tile.tile_index(lon_lat)
        try:
            return self.stg_dict[tile_index]
        except KeyError:
            the_stg = STG_File(lon_lat, tile_index, self.path_to_scenery, self.magic, self.prefix)
            self.stg_dict[tile_index] = the_stg
            if overwrite == None:
                overwrite = self.overwrite
            if overwrite:
                # this will only drop the section we previously wrote ()
                the_stg.drop_ours()
        return the_stg

    def add_object_static(self, ac_file_name, lon_lat, elev, hdg, once=False):
        """Adds OBJECT_STATIC line. Returns path to stg."""
        the_stg = self(lon_lat)
        return the_stg.add_object_static(ac_file_name, lon_lat, elev, hdg, once)

    def add_object_shared(self, ac_file_name, lon_lat, elev, hdg):
        """Adds OBJECT_SHARED line. Returns path to stg it was added to."""
        the_stg = self(lon_lat)
        return the_stg.add_object_shared(ac_file_name, lon_lat, elev, hdg)

    def drop_ours(self):
        for the_stg in self.stg_dict.values():
            the_stg.drop_ours()

    def write(self):
        for the_stg in self.stg_dict.values():
            the_stg.write()


class STGEntry(object):
    SHARED_OBJECT = "OBJECT_SHARED"
    STATIC_OBJECT = "OBJECT_STATIC"

    def __init__(self, type_string, obj_filename, stg_path, lon, lat, elev, hdg):
        self.is_static = True
        if type_string == STGEntry.SHARED_OBJECT:
            self.is_static = False
        self.obj_filename = obj_filename
        self.stg_path = stg_path  # the path of the stg_file without file name and trailing path-separator
        self.lon = lon
        self.lat = lat
        self.elev = elev
        self.hdg = hdg

    def get_object_type_as_string(self):
        if self.is_static:
            return STGEntry.STATIC_OBJECT
        return STGEntry.SHARED_OBJECT

    def get_obj_path_and_name(self):
        if self.is_static:
            return self.stg_path + os.sep + self.obj_filename
        else:
            p = os.path.abspath(self.stg_path + os.sep + '..' + os.sep + '..' + os.sep + '..')
            return os.path.abspath(p + os.sep + self.obj_filename)


def read_stg_entries(stg_path_and_name, our_magic, ignore_bad_lines=False):
    """Reads an stg-file and extracts STGEntry objects outside of marked areas for our_magic.
    TODO: In the future, take care of multiple scenery paths here.
    TODO: should be able to take a list of our_magic"""
    entries = []  # list of STGEntry objects
    
    logger = logging.getLogger("stgio2")

    if None is not our_magic:
        our_magic_start = delimiter_string(our_magic, None, True)
        our_magic_end = delimiter_string(our_magic, None, False)
        ours = False
    try:
        with open(stg_path_and_name, 'r') as my_file:
            path, stg_name = os.path.split(stg_path_and_name)
            for line in my_file:
                if None is not our_magic:
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
                    logger.debug("stg: %s %s", type_, entry.get_obj_path_and_name())
                except ValueError, reason:
                    if not ignore_bad_lines:
                        logger.warning("stg_io:read: Damaged file %s", reason)
                        logger.warning("Damaged line: %s", line.strip())
                        return []
                    else:
                        logger.warning("Damaged line: %s", line.strip())
                except IndexError, reason:
                    if not ignore_bad_lines:
                        logger.warning("stg_io:read: Ignoring unreadable file %s", reason)
                        logger.warning("Offending line: %s", line.strip())
                        return []
                    else:
                        logger.warning("Damaged line: %s", line.strip())
    except IOError, reason:
        logger.warning("stg_io:read: Ignoring unreadable file %s", reason)
        return []
    return entries


def read(path, stg_fname, our_magic):
    """Same as read_stg_entries, but returns osm2city.Building objects"""
    stg_entries = read_stg_entries(path + stg_fname, our_magic)
    building_objs = []
    for entry in stg_entries:
        point = shg.Point(tools.transform.toLocal((entry.lon, entry.lat)))
        building_objs.append(osm2city.Building(osm_id=-1, tags=-1, outer_ring=point
                                               , name=entry.get_obj_path_and_name()
                                               , height=0, levels=0, stg_typ=entry.get_object_type_as_string()
                                               , stg_hdg=entry.hdg))

    return building_objs


def delimiter_string(our_magic, prefix, is_start):
    delimiter = '# '
    if not is_start:
        delimiter += 'END '
    if prefix is None:
        return delimiter + our_magic + '\n'
    else:
        return delimiter + our_magic + '_' + prefix + '\n'


def quick_stg_line(path_to_scenery, ac_fname, position, elevation, heading, show=True):
    """debug."""
    stg_path = calc_tile.construct_path_to_stg(path_to_scenery, position)
    stg_fname = calc_tile.construct_stg_file_name(position)
    stg_line = "OBJECT_STATIC %s %1.7f %1.7f %1.2f %g\n" % (ac_fname, position.lon, position.lat, elevation, heading)
    if show == 1 or show == 3:
        print stg_path + stg_fname
    if show == 2 or show == 3:
        print stg_line
#        print "%s\n%s" % (stg_path + stg_fname, stg_line)
    return stg_path, stg_fname, stg_line


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    OUR_MAGIC = "osm2test"
    center_global = vec2d(13.7, 51)

    # 1. Init STG_Manager
    stg_manager = STG_Manager("/home/albrecht/fgfs/my/osm2city/EDDC", OUR_MAGIC, overwrite=True)

    # 2. add object(s) to it, will return path_to_stg. If the .stg in question
    #    is encountered for the first time, read it into an STG_File object and
    #    separate "our" lines from "other" lines.
    path_to_stg = stg_manager.add_object_static("test.ac", center_global, 0, 0)

    # 3. write your .ac to path_to_stg + ac_file_name (then add more objects)

    # 4. finally write all cached lines to .stg files.
    stg_manager.write()

    # 5. If you want to uninstall, do 1. - 3. Then remove our lines from cache:l
    #   stg_manager.drop_ours()
    # And write other lines to disk:
    #   stg_manager.write()
