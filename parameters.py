# -*- coding: utf-8 -*-
"""
Central place to store parameters / settings / variables in osm2city.
All length, height etc. parameters are in meters, square meters (m2) etc.

The assigned values are default values. The Config files will overwrite them

Created on May 27, 2013

@author: vanosten
"""

import argparse
import sys
import types

#=============================================================================
# PARAMETERS FOR ALL osm2city MODULES
#=============================================================================

# -- Scenery folder, typically a geographic name or the ICAO code of the airport
PREFIX = "LSZR"

# -- Boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
BOUNDARY_WEST = 9.54
BOUNDARY_SOUTH = 47.48
BOUNDARY_EAST = 9.58
BOUNDARY_NORTH = 47.50

# -- Distance between raster points for the derived elevation map (x is horizontal, y is vertical)
ELEV_RASTER_X = 10
ELEV_RASTER_Y = 10

# -- Full path to the scenery folder without trailing slash. There must be
#    an OBJECTS/ folder below PATH_TO_SCENERY
PATH_TO_SCENERY = "/home/user/fgfs/scenery"

OSM_FILE = "buildings.osm"  # -- file name of the file with OSM data. Must reside in $PREFIX
USE_PKL = False             # -- instead of parsing the OSM file, read a previously created cache file $PREFIX/buildings.pkl

# -- write .stg, .ac, .xml to this path. If empty, data is automatically written to correct location
#    in $PATH_TO_SCENERY
PATH_TO_OUTPUT = ""

NO_ELEV = False             # -- skip elevation interpolation
ELEV_MODE = ''              # Either Manual, Telnet, Fgelev

#=============================================================================
# PARAMETERS RELATED TO BUILDINGS IN osm2city
#=============================================================================

# -- check for overlap with static models. The scenery folder must contain an "Objects" folder
OVERLAP_CHECK = True
OVERLAP_RADIUS = 5

TILE_SIZE = 1000            # -- tile size in meters for clustering of buildings

MAX_OBJECTS = 50000         # -- maximum number of buildings to read from OSM data
CONCURRENCY = 1             # -- number of parallel OSM parsing threads

# -- skip reading named buildings from OSM (in case there's already a static model for these, and the overlap check fails)
SKIP_LIST = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
  "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
  "Residenzschloss Dresden", "Fernsehturm", "Fernsehturm Dresden"]

# -- Parameters which influence the number of buildings from OSM taken to output
BUILDING_MIN_HEIGHT = 3.4           # -- minimum height of a building to be included in output (does not include roof)
BUILDING_MIN_AREA = 50.0            # -- minimum area for a building to be included in output
BUILDING_REDUCE_THRESHOLD = 200.0   # -- threshold area of a building below which a rate of buildings gets reduced from output
BUILDING_REDUCE_RATE = 0.5          # -- rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_REDUCE_CHECK_TOUCH = False # -- before removing a building due to area, check whether it is touching another building and therefore should be kept
BUILDING_SIMPLIFY_TOLERANCE = 1.0   # -- all points in the simplified building will be within the tolerance distance of the original geometry.
BUILDING_NEVER_SKIP_LEVELS = 6      # -- buildings that tall will never be skipped

BUILDING_COMPLEX_ROOFS = 1          # -- generate complex roofs on buildings?
BUILDING_COMPLEX_ROOFS_MAX_LEVELS = 5 # -- don't put complex roofs on buildings taller than this
BUILDING_COMPLEX_ROOFS_MAX_AREA   = 2000 # -- don't put complex roofs on buildings larger than this
# -- Parameters which influence the height of buildings if no info from OSM is available.
#    It uses a triangular distribution (see http://en.wikipedia.org/wiki/Triangular_distribution)
BUILDING_CITY_LEVELS_LOW = 2.0
BUILDING_CITY_LEVELS_MODE = 3.5
BUILDING_CITY_LEVELS_HEIGH = 5.0
BUILDING_CITY_LEVEL_HEIGHT_LOW = 3.1
BUILDING_CITY_LEVEL_HEIGHT_MODE = 3.3
BUILDING_CITY_LEVEL_HEIGHT_HEIGH = 3.6
# FIXME: same parameters for place = town, village, suburb

# -- The more buildings end up in LOD rough or bare, the more work for your GPU.
#    Increasing any of the following parameters will decrease GPU load.
LOD_ALWAYS_DETAIL_BELOW_AREA = 150  # -- below this area, buildings will always be LOD detail
LOD_ALWAYS_ROUGH_ABOVE_AREA = 500   # -- above this area, buildings will always be LOD rough
LOD_ALWAYS_ROUGH_ABOVE_LEVELS = 6   # -- above this number of levels, buildings will always be LOD rough
LOD_ALWAYS_BARE_ABOVE_LEVELS = 10   # -- really tall buildings will be LOD bare
LOD_ALWAYS_DETAIL_BELOW_LEVELS = 3  # -- below this number of levels, buildings will always be LOD detail
LOD_PERCENTAGE_DETAIL = 0.5         # -- of the remaining buildings, this percentage will be LOD detail,
                                    #    the rest will be LOD rough.

OBSTRUCTION_LIGHT_MIN_LEVELS = 15   # -- put obstruction lights on buildings with >= given levels

EXPERIMENTAL_USE_SKEL = 0           # -- generate complex roofs with pySkeleton?
SKEL_MAX_NODES = 10                 # -- max number of nodes for which we generate complex roofs
SKEL_MAX_HEIGHT_RATIO = 0.7         # --
EXPERIMENTAL_INNER = 0

CLUSTER_MIN_OBJECTS = 5             # -- discard cluster if to little objects


#=============================================================================
# PARAMETERS RELATED TO PYLONS, POWERLINES, AERIALWAYS IN osm2pylons.py
#=============================================================================

C2P_PROCESS_POWERLINES = True
C2P_PROCESS_AERIALWAYS = True

# Each powerline and aerialway has segments delimited by pylons. The longer the value the better clustering and
# the better the performance. However due to rounding errors the longer the length per cluster the larger the
# error.
C2P_CLUSTER_LINE_MAX_LENGTH = 300
C2P_CABLES_NO_SHADOW = True

# The radius for the cable. The cable will be a triangle with side length 2*radius.
# In order to be better visible the radius might be chosen larger than in real life
C2P_RADIUS_POWER_LINE = 0.1
C2P_RADIUS_POWER_MINOR_LINE = 0.1
C2P_RADIUS_AERIALWAY_CABLE_CAR = 0.1
C2P_RADIUS_AERIALWAY_CHAIR_LIFT = 0.1
C2P_RADIUS_AERIALWAY_DRAG_LIFT = 0.05
C2P_RADIUS_AERIALWAY_GONDOLA = 0.1
C2P_RADIUS_AERIALWAY_GOODS = 0.05
C2P_RADIUS_TOP_LINE = 0.05

# The number of extra points between 2 pylons to simulate sagging of the cable.
# If 0 is chosen or if CATENARY_A is 0 then no sagging is calculated, which is better for performances (less realistic)
# 3 is normally a good compromise - for cable cars or major power lines with very long distances a value of 5
# or higher might be suitable
C2P_EXTRA_VERTICES_POWER_LINE = 3
C2P_EXTRA_VERTICES_POWER_MINOR_LINE = 3
C2P_EXTRA_VERTICES_AERIALWAY_CABLE_CAR = 5
C2P_EXTRA_VERTICES_AERIALWAY_CHAIR_LIFT = 3
C2P_EXTRA_VERTICES_AERIALWAY_DRAG_LIFT = 0
C2P_EXTRA_VERTICES_AERIALWAY_GONDOLA = 3
C2P_EXTRA_VERTICES_AERIALWAY_GOODS = 5

# The value for catenary_a can be experimentally determined by using osm2pylon.test_catenary
C2P_CATENARY_A_POWER_LINE = 1500
C2P_CATENARY_A_POWER_MINOR_LINE = 1200
C2P_CATENARY_A_AERIALWAY_CABLE_CAR = 1500
C2P_CATENARY_A_AERIALWAY_CHAIR_LIFT = 1500
C2P_CATENARY_A_AERIALWAY_DRAG_LIFT = 1500
C2P_CATENARY_A_AERIALWAY_GONDOLA = 1500
C2P_CATENARY_A_AERIALWAY_GOODS = 1500

C2P_CATENARY_MIN_DISTANCE = 50

C2P_POWER_LINE_ALLOW_100M = False


def set_parameters(param_dict):
    for k in param_dict:
        if k in globals():
            if isinstance(globals()[k], types.BooleanType):
                globals()[k] = parse_bool(k, param_dict[k])
            elif isinstance(globals()[k], types.FloatType):
                float_value = parse_float(k, param_dict[k])
                if None is not float_value:
                    globals()[k] = float_value
            elif isinstance(globals()[k], types.IntType):
                int_value = parse_int(k, param_dict[k])
                if None is not int_value:
                    globals()[k] = int_value
            elif isinstance(globals()[k], types.StringType):
                if None is not param_dict[k]:
                    globals()[k] = param_dict[k]
            elif isinstance(globals()[k], types.ListType):
                globals()[k] = parse_list(param_dict[k])
            else:
                print "Parameter", k, "has an unknown type/value:", param_dict[k]
        else:
            print "Ignoring unknown parameter", k


def show():
    """
    Prints all parameters as key = value
    """
    print '--- Using the following parameters: ---'
    my_globals = globals()
    for k in sorted(my_globals.iterkeys()):
        if k.startswith('__'):
            continue
        elif k == "args":
            continue
        elif k == "parser":
            continue
        elif isinstance(my_globals[k], types.ClassType) or \
                isinstance(my_globals[k], types.FunctionType) or \
                isinstance(my_globals[k], types.ModuleType):
            continue
        elif isinstance(my_globals[k], types.ListType):
            value = ', '.join(my_globals[k])
            print k, '=', value
        else:
            print k, '=', my_globals[k]
    print '------'


def parse_list(string_value):
    """
    Tries to parse a string containing comma separated values and returns a list
    """
    my_list = []
    if None is not string_value:
        my_list = string_value.split(',')
        for index in range(len(my_list)):
            my_list[index] = my_list[index].strip().strip('"\'')
    return my_list


def parse_float(key, string_value):
    """
    Tries to parse a string and get a float. If it is not possible, then None is returned.
    On parse exception the key and the value are printed to console
    """
    float_value = None
    try:
        float_value = float(string_value)
    except ValueError:
        print 'Unable to convert', string_value, 'to decimal number. Relates to key', key
    return float_value


def parse_int(key, string_value):
    """
    Tries to parse a string and get an int. If it is not possible, then None is returned.
    On parse exception the key and the value are printed to console
    """
    int_value = None
    try:
        int_value = int(string_value)
    except ValueError:
        print 'Unable to convert', string_value, 'to number. Relates to key', key
    return int_value


def parse_bool(key, string_value):
    """
    Tries to parse a string and get a boolean. If it is not possible, then False is returned.
    """
    if string_value.lower() in ("yes", "true", "on", "1"):
        return True
    if string_value.lower() in ("no", "false", "off", "0"):
        return False
    print "Boolean value %s for %s not understood. Assuming False." % (string_value, key)
    # FIXME: bail out if not understood!
    return False


def read_from_file(filename):
    print 'Reading parameters from file:', filename
    try:
        f = open(filename, 'r')
        param_dict = {}
        full_line = ""
        for line in f:
            # -- ignore comments and empty lines
            line = line.split('#')[0].strip()
            if line == "":
                continue

            full_line += line  # -- allow for multi-line lists
            if line.endswith(","):
                continue

            pair = full_line.split("=", 1)
            key = pair[0].strip().upper()
            value = None
            if 2 == len(pair):
                value = pair[1].strip()
            param_dict[key] = value
            full_line = ""

        set_parameters(param_dict)
        f.close()
    except IOError, reason:
        print "Error processing file with parameters:", reason
        sys.exit(1)


if __name__ == "__main__":
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="The parameters module provides parameters to osm2city - used as main it shows the parameters used.")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        read_from_file(args.filename)
        show()
