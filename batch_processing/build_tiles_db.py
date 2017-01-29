import argparse
import logging
import os
import parameters
import sys

import buildings
import copy_data_stuff
import platforms
import pylons
import roads
import utils.aptdat_io as aptdat_io
import utils.calc_tile as calc_tile
import utils.coordinates as coordinates
from utils.utilities import BoundaryError, FGElev, parse_boundary


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles DB generates a whole scenery of osm2city objects \
    based on a lon/lat defined area")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel", dest="loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument("-b", "--boundary", dest="boundary",
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (. as decimal)",
                        required=True)

    args = parser.parse_args()

    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    parameters.USE_DATABASE = True  # just to be sure

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
    for full_lon in range(int(boundary_west), int(boundary_east - epsilon) + 1):
        for full_lat in range(int(boundary_south), int(boundary_north - epsilon) + 1):
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
                    scenery_tiles_list.append([tile_boundary_west, tile_boundary_south,
                                               tile_boundary_east, tile_boundary_north,
                                               tile_prefix])
                    logging.info("Added scenery tile {} with boundary {}, {}, {}, {}".format(tile_index,
                                                                                             tile_boundary_west,
                                                                                             tile_boundary_south,
                                                                                             tile_boundary_east,
                                                                                             tile_boundary_north))

    for scenery_tile in scenery_tiles_list:
        # adapt boundary
        parameters.BOUNDARY_WEST = scenery_tile[0]
        parameters.BOUNDARY_SOUTH = scenery_tile[1]
        parameters.BOUNDARY_EAST = scenery_tile[2]
        parameters.BOUNDARY_NORTH = scenery_tile[3]
        parameters.PREFIX = scenery_tile[4]

        # prepare shared resources
        my_coords_transform = coordinates.Transformation(parameters.get_center_global())
        my_fg_elev = FGElev(my_coords_transform)
        my_blocked_areas = aptdat_io.get_apt_dat_blocked_areas(my_coords_transform,
                                                               parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                               parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)

        # run programs
        buildings.process(my_coords_transform, my_fg_elev, my_blocked_areas)
        roads.process(my_coords_transform, my_fg_elev, my_blocked_areas)
        pylons.process(my_coords_transform, my_fg_elev)
        platforms.process(my_coords_transform, my_fg_elev)

        # clean-up
        my_fg_elev.close()

        logging.info("******* Finished one tile *******")

    if parameters.USE_NEW_STG_VERBS:
        copy_data_stuff.process(False, "Buildings")
        copy_data_stuff.process(False, "Roads")
        copy_data_stuff.process(False, "Pylons")
    else:
        copy_data_stuff.process(False, "Objects")
