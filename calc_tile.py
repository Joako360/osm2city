#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
shamelessly translated from calc-tile.pl
"""
import os
from math import floor, trunc

def bucket_span(lat):
    """Latitude Range -> Tile Width (deg)"""
    alat = abs(lat)
    if alat >= 89: return 360
    if alat >= 88: return 8
    if alat >= 86: return 4
    if alat >= 83: return 2
    if alat >= 76: return 1
    if alat >= 62: return .5
    if alat >= 22: return .25
    return .125

def format_lon (lon):
    """Format longitude as e/w."""
    if lon < 0.:
        return "w%03d" % int(0. - lon)
    else:
        return "e%03d" % int(lon)

def format_lat (lat):
    """Format latitude as n/s."""
    if lat < 0.:
        return "s%02d" % int(0. - lat)
    else:
        return "n%02d" % int(lat)

def directory_name ((lon, lat)):
    """Generate the directory name for a location."""
    lon_floor = floor(lon)
    lat_floor = floor(lat)
    lon_chunk = floor(lon/10.0) * 10
    lat_chunk = floor(lat/10.0) * 10
    return format_lon(lon_chunk) + format_lat(lat_chunk) + os.sep \
         + format_lon(lon_floor) + format_lat(lat_floor)

def tile_index((lon, lat)):
    tile_width = bucket_span(lat)

    EPSILON = 0.0000001

    lon_floor = floor(lon)
    lat_floor = floor(lat)
    span = bucket_span(lat)

    if span < EPSILON:
        lon = 0
        x = 0
    elif span <= 1.0:
        x = int((lon - lon_floor) / span)
    else:
        if lon >= 0:
          lon = int(int(lon/span) * span)
        else:
          lon = int(int((lon+1)/span) * span - span)
          if lon < -180:
            lon = -180
        x = 0

    y = int((lat - lat_floor) * 8)

    index = (int(lon_floor) + 180) << 14
    index += (int(lat_floor) + 90) << 6
    index += y << 3
    index += x
    return index


if __name__ == "__main__":
    for lon, lat, idx in ((13.687944, 51.074664, 3171138),
                          (13.9041667, 51.1072222, 3171139),
                          (13.775, 51.9638889, 3171195),
                          (0.258094, 29.226081, 2956745),
                          (-2.216667, 30.008333, 2907651)):
        print tile_index([lon, lat]) - idx
        print directory_name([lon, lat])
