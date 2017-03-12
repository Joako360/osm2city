import argparse
from enum import IntEnum, unique
import logging
import multiprocessing as mp
import os
import parameters
import sys
import time
import traceback
from typing import List
import unittest

import buildings
import copy_data_stuff
import piers
import platforms
import pylons
import roads
import utils.aptdat_io as aptdat_io
import utils.calc_tile as calc_tile
import utils.coordinates as coordinates
import utils.stg_io2
from utils.utilities import BoundaryError, FGElev, parse_boundary


class SceneryTile(object):
    def __init__(self, my_boundary_west: float, my_boundary_south: float,
                 my_boundary_east: float, my_boundary_north: float,
                 my_tile_index: int, prefix: str) -> None:
        self.boundary_west = my_boundary_west
        self.boundary_south = my_boundary_south
        self.boundary_east = my_boundary_east
        self.boundary_north = my_boundary_north
        self.tile_index = my_tile_index
        self.prefix = prefix

    def __str__(self) -> str:
        my_string = "Tile index: " + str(self.tile_index)
        my_string += ", prefix: " + self.prefix
        my_string += "; boundary west: " + str(self.boundary_west)
        my_string += " - south: " + str(self.boundary_south)
        my_string += " - east: " + str(self.boundary_east)
        my_string += " - north: " + str(self.boundary_north)
        return my_string


@unique
class Procedures(IntEnum):
    all = 0
    buildings = 1
    piers = 2
    platforms = 3
    pylons = 4
    roads = 5


def _parse_exec_for_procedure(exec_argument: str) -> Procedures:
    """Parses a command line argument to determine which osm2city procedure to run.
    Returns KeyError if mapping cannot be done"""
    return Procedures.__members__[exec_argument.lower()]


def process_scenery_tile(scenery_tile: SceneryTile, params_file_name: str, log_level: str,
                         exec_argument: Procedures, my_airports: List[aptdat_io.Airport]) -> None:
    parameters.read_from_file(params_file_name)
    parameters.set_loglevel(log_level)
    parameters.USE_DATABASE = True  # just to be sure
    # adapt boundary
    parameters.BOUNDARY_WEST = scenery_tile.boundary_west
    parameters.BOUNDARY_SOUTH = scenery_tile.boundary_south
    parameters.BOUNDARY_EAST = scenery_tile.boundary_east
    parameters.BOUNDARY_NORTH = scenery_tile.boundary_north
    parameters.PREFIX = scenery_tile.prefix
    logging.info("Processing tile {} in prefix {} with process id = {}".format(scenery_tile.tile_index,
                                                                               parameters.PREFIX,
                                                                               os.getpid()))
    try:
        # prepare shared resources
        the_coords_transform = coordinates.Transformation(parameters.get_center_global())
        my_fg_elev = FGElev(the_coords_transform)
        my_stg_entries = utils.stg_io2.read_stg_entries_in_boundary(True, the_coords_transform)

        # cannot be read once for all
        my_blocked_areas = None
        if exec_argument in (Procedures.all, Procedures.buildings, Procedures.roads):
            my_blocked_areas = aptdat_io.get_apt_dat_blocked_areas_from_airports(the_coords_transform, my_airports)

        # run programs
        if exec_argument is Procedures.all:
            buildings.process(the_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)
            roads.process(the_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)
            pylons.process(the_coords_transform, my_fg_elev, my_stg_entries)
            platforms.process(the_coords_transform, my_fg_elev)
            piers.process(the_coords_transform, my_fg_elev)
        elif exec_argument is Procedures.buildings:
            buildings.process(the_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)
        elif exec_argument is Procedures.roads:
            roads.process(the_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)
        elif exec_argument is Procedures.pylons:
            pylons.process(the_coords_transform, my_fg_elev, my_stg_entries)
        elif exec_argument is Procedures.platforms:
            platforms.process(the_coords_transform, my_fg_elev)
        elif exec_argument is Procedures.piers:
            # piers.process(the_coords_transform, my_fg_elev)
            pass

        # clean-up
        my_fg_elev.close()

    except:
        logging.exception('Exception occurred while processing tile {}.'.format(scenery_tile.tile_index))
        msg = "******* Exception with tile {} to reprocess use boundaries: {}_{}_{}_{} *******".format(
            scenery_tile.tile_index, scenery_tile.boundary_west, scenery_tile.boundary_south,
            scenery_tile.boundary_east, scenery_tile.boundary_north)
        logging.exception(msg)

        f = open("osm2city-exceptions.log", "a")
        # print info
        print(msg, file=f)
        # print exception
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)), file=f)
        f.close()

    logging.info("******* Finished tile {} *******".format(scenery_tile.tile_index))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles DB generates a whole scenery of osm2city objects \
    based on a lon/lat defined area")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-b", "--boundary", dest="boundary",
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (. as decimal)",
                        required=True)
    parser.add_argument("-p", "--processes", dest="processes", type=int,
                        help="number of parallel processes (should not be more than number of cores/CPUs)",
                        required=True, )
    parser.add_argument("-e", "--execute", dest="exec",
                        help="execute only the given osm2city procedure (buildings, piers, platforms, pylons, roads)",
                        required=False)
    parser.add_argument("-l", "--loglevel", dest="loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)

    args = parser.parse_args()

    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

    exec_procedure = Procedures.all
    if (args.exec):
        try:
            exec_procedure = _parse_exec_for_procedure(args.exec)
        except KeyError:
            logging.error('Cannot parse --execute argument: {}'.format(args.exec))
            sys.exit(1)

    try:
        boundary_floats = parse_boundary(args.boundary)
    except BoundaryError as be:
        logging.error(be.message)
        sys.exit(1)

    boundary_west = boundary_floats[0]
    boundary_south = boundary_floats[1]
    boundary_east = boundary_floats[2]
    boundary_north = boundary_floats[3]
    logging.info("Overall boundary {}, {}, {}, {}".format(boundary_west, boundary_south, boundary_east, boundary_north))

    # list of sceneries tiles (might have smaller boundaries). Each entry has a list with the 4 boundary points
    scenery_tiles_list = list()

    # loop west-east and south north on full degrees
    epsilon = 0.00000001  # to make sure that top right boundary not x.0
    for full_lon in range(int(boundary_west) - 1, int(boundary_east - epsilon) + 1):  # -1 for west if negative west
        for full_lat in range(int(boundary_south) - 1, int(boundary_north - epsilon) + 1):
            logging.debug("lon: {}, lat:{}".format(full_lon, full_lat))
            if calc_tile.bucket_span(full_lat) > 1:
                num_lon_parts = 1
            else:
                num_lon_parts = int(1 / calc_tile.bucket_span(full_lat))
            num_lat_parts = 8  # always the same no matter the lon
            for lon_index in range(num_lon_parts):
                for lat_index in range(num_lat_parts):
                    tile_boundary_west = full_lon + lon_index / num_lon_parts
                    tile_boundary_east = full_lon + (lon_index + 1) / num_lon_parts
                    tile_boundary_south = full_lat + lat_index / num_lat_parts
                    tile_boundary_north = full_lat + (lat_index + 1) / num_lat_parts
                    if tile_boundary_east <= boundary_west or tile_boundary_west >= boundary_east:
                        continue
                    if tile_boundary_north <= boundary_south or tile_boundary_south >= boundary_north:
                        continue
                    if boundary_west > tile_boundary_west:
                        tile_boundary_west = boundary_west
                    if tile_boundary_east > boundary_east:
                        tile_boundary_east = boundary_east
                    if boundary_south > tile_boundary_south:
                        tile_boundary_south = boundary_south
                    if tile_boundary_north > boundary_north:
                        tile_boundary_north = boundary_north

                    tile_index = calc_tile.tile_index((tile_boundary_west, tile_boundary_south))
                    tile_prefix = ("%s%s%s" % (calc_tile.directory_name((full_lon, full_lat)), os.sep, tile_index))
                    a_scenery_tile = SceneryTile(tile_boundary_west, tile_boundary_south,
                                                 tile_boundary_east, tile_boundary_north,
                                                 tile_index, tile_prefix)
                    scenery_tiles_list.append(a_scenery_tile)
                    logging.info("Added new scenery tile: {}".format(a_scenery_tile))

    # get airports from apt_dat. Transformation to blocked areas can only be done in sub-process due to local
    # coordinate system
    airports = aptdat_io.read_apt_dat_gz_file(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                              parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)

    start_time = time.time()
    mp.set_start_method('spawn')  # use safe approach to make sure e.g. parameters module is initialized separately
    pool = mp.Pool(processes=args.processes, maxtasksperchild=1)
    for my_scenery_tile in scenery_tiles_list:
        pool.apply_async(process_scenery_tile, (my_scenery_tile, args.filename, args.loglevel,
                                                exec_procedure, airports))
    pool.close()
    pool.join()

    # At the very end copy static data stuff in one process
    if exec_procedure is Procedures.all:
        copy_data_stuff.process(False, "Buildings")
        copy_data_stuff.process(False, "Roads")
        copy_data_stuff.process(False, "Pylons")
    elif exec_procedure is Procedures.pylons:
        copy_data_stuff.process(False, "Pylons")
    elif exec_procedure is Procedures.roads:
        copy_data_stuff.process(False, "Roads")
    else:
        copy_data_stuff.process(False, "Buildings")

    logging.info("Total time used {}".format(time.time() - start_time))


# ================ UNITTESTS =======================


class TestProcedures(unittest.TestCase):
    def test_middle_angle(self):
        self.assertTrue(_parse_exec_for_procedure('PyloNs') is Procedures.pylons)
        self.assertRaises(KeyError, _parse_exec_for_procedure, 'Hello')
