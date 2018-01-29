# -*- coding: utf-8 -*-
"""
shamelessly translated from calc-tile.pl
"""
from math import floor
import os
from typing import List, Tuple
import unittest

import numpy as np


def bucket_span(lat: float) -> float:
    """Latitude Range -> Tile Width (deg)"""
    abs_lat = abs(lat)
    if abs_lat >= 89:
        return 360
    elif abs_lat >= 88:
        return 8
    elif abs_lat >= 86:
        return 4
    elif abs_lat >= 83:
        return 2
    elif abs_lat >= 76:
        return 1
    elif abs_lat >= 62:
        return .5
    elif abs_lat >= 22:
        return .25
    elif abs_lat >= 0:
        return .125
    return 360


def format_lon(lon):
    """Format longitude as e/w."""
    if lon < 0.:
        return "w%03d" % int(0. - lon)
    else:
        return "e%03d" % int(lon)


def format_lat(lat):
    """Format latitude as n/s."""
    if lat < 0.:
        return "s%02d" % int(0. - lat)
    else:
        return "n%02d" % int(lat)


def root_directory_name(lon_lat: Tuple[float, float]) -> str:
    """Generate the directory name for a location."""
    (lon, lat) = lon_lat
    lon_chunk = floor(lon/10.0) * 10
    lat_chunk = floor(lat/10.0) * 10
    return format_lon(lon_chunk) + format_lat(lat_chunk) + os.sep 


def directory_name(lon_lat: Tuple[float, float]) -> str:
    """Generate the directory name for a location."""
    (lon, lat) = lon_lat
    lon_floor = floor(lon)
    lat_floor = floor(lat)
    lon_chunk = floor(lon/10.0) * 10
    lat_chunk = floor(lat/10.0) * 10
    return os.path.join(format_lon(lon_chunk) + format_lat(lat_chunk), format_lon(lon_floor) + format_lat(lat_floor))


def tile_index(lon_lat: Tuple[float, float], x: int=0, y: int=0) -> int:
    """See  http://wiki.flightgear.org/Tile_Index_Scheme"""
    (lon, lat) = lon_lat
    if x == 0 and y == 0:
        y = calc_y(lat)
        x = calc_x(lon, lat)

    index = (int(floor(lon)) + 180) << 14
    index += (int(floor(lat)) + 90) << 6
    index += y << 3
    index += x
    return index


def construct_path_to_stg(base_directory: str, scenery_type: str, center_global: Tuple[float, float]) -> str:
    """Returns the path to the stg-files in a FG scenery directory hierarchy at a given global lat/lon location"""
    return os.path.join(base_directory, scenery_type, directory_name(center_global))


def construct_stg_file_name(center_global: Tuple[float, float]) -> str:
    """Returns the file name of the stg-file at a given global lat/lon location"""
    return construct_stg_file_name_from_tile_index(tile_index(center_global))


def construct_stg_file_name_from_tile_index(tile_idx: int) -> str:
    return str(tile_idx) + ".stg"


def construct_btg_file_name(center_global: Tuple[float, float]) -> str:
    """Returns the file name of the stg-file at a given global lat/lon location"""
    return str(tile_index(center_global)) + ".btg.gz"


def get_north_lat(lat, y):
    return float(floor(lat)) + y / 8.0 + .125


def get_south_lat(lat, y):
    return float(floor(lat)) + y / 8.0


def get_west_lon(lon, lat, x):
    if x == 0:
        return float(floor(lon))
    else: 
        return float(floor(lon)) + x * (bucket_span(lat))


def get_east_lon(lon, lat, x):
    if x == 0:
        return float(floor(lon)) + (bucket_span(lat))
    else: 
        return float(floor(lon)) + x * (bucket_span(lat)) + (bucket_span(lat))


def calc_x(lon: float, lat: float) -> int:
    """
    FIXME: is this correct? Also: some returns do not take calculations into account.
    """
    epsilon = 0.0000001
    span = bucket_span(lat)
    if span < epsilon:
        lon = 0
        return 0
    elif span <= 1.0:
        return int((lon - floor(lon)) / span)
    else:
        if lon >= 0:
            lon = int(int(lon/span) * span)
        else:
            lon = int(int((lon+1)/span) * span - span)
            if lon < -180:
                lon = -180
        return 0


def calc_y(lat: float) -> int:
    return int((lat - floor(lat)) * 8)
    

def get_stg_files_in_boundary(boundary_west: float, boundary_south: float, boundary_east: float, boundary_north: float,
                              path_to_scenery: str, scenery_type: str) -> List[str]:
    """Based on boundary rectangle returns a list of stg-files (incl. full path) to be found within the boundary of
    the scenery"""
    stg_files = []
    for my_lat in np.arange(boundary_south, boundary_north, 0.125):  # latitude; FIXME: why use a factor?
        for my_lon in np.arange(boundary_west, boundary_east, bucket_span(my_lat)):  # longitude
            coords = (my_lon, my_lat)
            stg_files.append(os.path.join(construct_path_to_stg(path_to_scenery, scenery_type, coords),
                             construct_stg_file_name(coords)))
    return stg_files


# ================ UNITTESTS =======================


class TestCalcTiles(unittest.TestCase):
    def test_calc_tiles(self):
        self.assertEqual(5760, tile_index((-179.9, 0.1)))
        self.assertEqual(5752, tile_index((-179.9, -0.1)))
        self.assertEqual(5887623, tile_index((179.9, 0.1)))
        self.assertEqual(5887615, tile_index((179.9, -0.1)))
        self.assertEqual(2954880, tile_index((0.0, 0.0)))
        self.assertEqual(2938495, tile_index((-0.1, -0.1)))

    def test_file_name(self):
        self.assertEqual("3088961.stg", construct_stg_file_name((8.29, 47.08)))
