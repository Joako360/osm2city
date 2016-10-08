# -*- coding: utf-8 -*-
"""
Central place to store parameters / settings / variables in osm2city.
All length, height etc. parameters are in meters, square meters (m2) etc.

The assigned values are default values. The Config files will overwrite them

Created on May 27, 2013

@author: vanosten

Ludomotico contributed a cleaner version of read_from_file().
"""

import argparse
import logging
import os
import re
import sys
import traceback
import types

import textures.road
from utils import vec2d as v

# default_args_start # DO NOT MODIFY THIS LINE
# -*- coding: utf-8 -*-
# The preceding line sets encoding of this file to utf-8. Needed for non-ascii
# object names. It must stay on the first or second line.

# =============================================================================
# PARAMETERS FOR ALL osm2city MODULES
# =============================================================================
LOGLEVEL = "INFO"

# -- Scenery folder, typically a geographic name or the ICAO code of the airport
PREFIX = "LSZR"

# -- Boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
BOUNDARY_WEST = 9.54
BOUNDARY_SOUTH = 47.48
BOUNDARY_EAST = 9.58
BOUNDARY_NORTH = 47.50
# Clip all nodes outside the bounding box
BOUNDARY_CLIPPING = True
BOUNDARY_CLIPPING_BORDER_SIZE = 0.25
BOUNDARY_CLIPPING_COMPLETE_WAYS = False

OSM_FILE = "buildings.osm"  # -- file name of the file with OSM data. Should reside in $PREFIX. No path components allowed.
USE_PKL = False             # -- instead of parsing the OSM file, read a previously created cache file $PREFIX/buildings.pkl
IGNORE_PKL_OVERWRITE = True # -- Ignore overwriting of Cache File

# -- Full path to the scenery folder without trailing slash. This is where we
#    will probe elevation and check for overlap with static objects. Most
#    likely you'll want to use your TerraSync path here.
PATH_TO_SCENERY = "/home/user/fgfs/scenery/TerraSync"

# -- The generated scenery (.stg, .ac, .xml) will be written to this path.
#    If empty, we'll use the correct location in PATH_TO_SCENERY. Note that
#    if you use TerraSync for PATH_TO_SCENERY, you MUST choose a different
#    path here. Otherwise, TerraSync will overwrite the generated scenery.
#    Also make sure PATH_TO_OUTPUT is included in your $FG_SCENERY.
PATH_TO_OUTPUT = "/home/user/fgfs/scenery/osm2city"

PATH_TO_OSM2CITY_DATA = "/home/user/osm2city-data"

NO_ELEV = False             # -- skip elevation probing
ELEV_MODE = "Fgelev"  # -- elev probing mode. Possible values are FgelevCaching (recommended), Fgelev, Manual, or Telnet
FG_ELEV = '"D:/Program Files/FlightGear/bin/Win64/fgelev.exe"'

# -- Distance between raster points for elevation map. Xx is horizontal, y is
#    vertical. Relevant only for ELEV_MODE = Manual or Telnet.
ELEV_RASTER_X = 10
ELEV_RASTER_Y = 10

TELNET_PORT = 5501  # The port FlightGear listens to. Needed for ELEV_MODE = "Telnet"

USE_NEW_STG_VERBS = False

# =============================================================================
# PARAMETERS RELATED TO BUILDINGS IN osm2city
# =============================================================================

# -- Check for static objects in the PATH_TO_SCENERY folder based on convex hull around all points
OVERLAP_CHECK_CONVEX_HULL = False
OVERLAP_CHECK_CH_BUFFER_STATIC = 0.0
OVERLAP_CHECK_CH_BUFFER_SHARED = 0.0

# -- Check for overlap with static and shared models. The scenery folder must contain an "Objects" folder
OVERLAP_CHECK = True
OVERLAP_CHECK_CONSIDER_SHARED = True
# -- Additionally check if one of the near nodes is actually inside the building
OVERLAP_CHECK_INSIDE = False
OVERLAP_RADIUS = 5
BUILDING_REMOVE_WITH_PARTS = False

TILE_SIZE = 2000            # -- tile size in meters for clustering of buildings

MAX_OBJECTS = 50000         # -- maximum number of buildings to read from OSM data
CONCURRENCY = 1             # -- number of parallel OSM parsing threads. Unused ATM.

# -- skip buildings based on their OSM name tag or OSM ID, in case there's already
#    a static model for these, and the overlap check fails.
#    Use unicode strings as in the first example if there are non-ASCII characters.
#    E.g. SKIP_LIST = ["Theologische Fakultät", "Rhombergpassage", 55875208]
SKIP_LIST = []
# -- keep buildings based on their OSM name tag or OSM ID.
#    keeps also, building:part of buildings
KEEP_LIST = []

# -- Parameters which influence the number of buildings from OSM taken to output
BUILDING_MIN_HEIGHT = 3.4           # -- minimum height of a building to be included in output (does not include roof)
BUILDING_MIN_AREA = 50.0            # -- minimum area for a building to be included in output
BUILDING_REDUCE_THRESHOLD = 200.0   # -- threshold area of a building below which a rate of buildings gets reduced from output
BUILDING_REDUCE_RATE = 0.5          # -- rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_REDUCE_CHECK_TOUCH = False # -- before removing a building due to area, check whether it is touching another building and therefore should be kept
BUILDING_SIMPLIFY_TOLERANCE = 1.0   # -- all points in the simplified building will be within the tolerance distance of the original geometry.
BUILDING_NEVER_SKIP_LEVELS = 6      # -- buildings that tall will never be skipped

BUILDING_UNKNOWN_ROOF_TYPE = "flat" # -- If the roof type isn't given use this type
BUILDING_COMPLEX_ROOFS = 1          # -- generate complex roofs on buildings?
BUILDING_COMPLEX_MIN_HEIGHT = 2     # -- don't put complex roof on buildings smallers than value without roof:shape flag
BUILDING_COMPLEX_ROOFS_MAX_LEVELS = 5 # -- don't put complex roofs on buildings taller than this
BUILDING_COMPLEX_ROOFS_MAX_AREA   = 2000 # -- don't put complex roofs on buildings larger than this
BUILDING_SKEL_ROOFS = 1             # -- generate complex roofs with pySkeleton? Used to be EXPERIMENTAL_USE_SKEL
BUILDING_SKEL_ROOFS_MIN_ANGLE = 20  # -- pySkeleton based complex roofs will
BUILDING_SKEL_ROOFS_MAX_ANGLE = 50  #    have a random angle between MIN and MAX
BUILDING_SKEL_MAX_NODES = 10        # -- max number of nodes for which we generate pySkeleton roofs
BUILDING_SKEL_MAX_HEIGHT_RATIO = 0.7 # -- skip skel roofs if ratio of roof height to base building height is larger than this

BUILDING_FAKE_AMBIENT_OCCLUSION = True      # -- fake AO by darkening facade textures towards the ground, using
BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT = 6. #    1 - VALUE * exp(- AGL / HEIGHT )
BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE = 0.6

EXPERIMENTAL_INNER = 0              # -- do we still need this?

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

LIGHTMAP_ENABLE = True                 # -- include lightmap in xml
OBSTRUCTION_LIGHT_MIN_LEVELS = 15   # -- put obstruction lights on buildings with >= given levels

CLUSTER_MIN_OBJECTS = 5             # -- discard cluster if too little objects


# =============================================================================
# PARAMETERS RELATED TO PYLONS, POWERLINES, AERIALWAYS IN osm2pylons.py
# =============================================================================

C2P_PROCESS_POWERLINES = True
C2P_PROCESS_AERIALWAYS = True
C2P_PROCESS_OVERHEAD_LINES = True
C2P_PROCESS_STREETLAMPS = True

# Each powerline and aerialway has segments delimited by pylons. The longer the value the better clustering and
# the better the performance. However due to rounding errors the longer the length per cluster the larger the
# error.
C2P_CLUSTER_POWER_LINE_MAX_LENGTH = 300
C2P_CLUSTER_AERIALWAY_MAX_LENGTH = 300
C2P_CLUSTER_OVERHEAD_LINE_MAX_LENGTH = 130
C2P_CABLES_NO_SHADOW = True

# The radius for the cable. The cable will be a triangle with side length 2*radius.
# In order to be better visible the radius might be chosen larger than in real life
C2P_RADIUS_POWER_LINE = 0.1
C2P_RADIUS_POWER_MINOR_LINE = 0.05
C2P_RADIUS_AERIALWAY_CABLE_CAR = 0.05
C2P_RADIUS_AERIALWAY_CHAIR_LIFT = 0.05
C2P_RADIUS_AERIALWAY_DRAG_LIFT = 0.03
C2P_RADIUS_AERIALWAY_GONDOLA = 0.05
C2P_RADIUS_AERIALWAY_GOODS = 0.03
C2P_RADIUS_TOP_LINE = 0.02
C2P_RADIUS_OVERHEAD_LINE = 0.02

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
C2P_EXTRA_VERTICES_OVERHEAD_LINE = 2

# The value for catenary_a can be experimentally determined by using osm2pylon.test_catenary
C2P_CATENARY_A_POWER_LINE = 1500
C2P_CATENARY_A_POWER_MINOR_LINE = 1200
C2P_CATENARY_A_AERIALWAY_CABLE_CAR = 1500
C2P_CATENARY_A_AERIALWAY_CHAIR_LIFT = 1500
C2P_CATENARY_A_AERIALWAY_DRAG_LIFT = 1500
C2P_CATENARY_A_AERIALWAY_GONDOLA = 1500
C2P_CATENARY_A_AERIALWAY_GOODS = 1500
C2P_CATENARY_A_OVERHEAD_LINE = 600

C2P_CATENARY_MIN_DISTANCE = 30

C2P_POWER_LINE_ALLOW_100M = False

C2P_STREETLAMPS_MAX_DISTANCE_LANDUSE = 100
C2P_STREETLAMPS_RESIDENTIAL_DISTANCE = 40
C2P_STREETLAMPS_OTHER_DISTANCE = 70
C2P_STREETLAMPS_MIN_STREET_LENGTH = 20

# =============================================================================
# PARAMETERS RELATED TO landuse.py - might be replaced by another library
# =============================================================================
LU_LANDUSE_GENERATE_LANDUSE = True
LU_LANDUSE_BUILDING_BUFFER_DISTANCE = 25
LU_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX = 50
LU_LANDUSE_MIN_AREA = 5000

# =============================================================================
# PARAMETERS RELATED TO roads.py
# =============================================================================

TRAFFIC_SHADER_ENABLE = False
MAX_SLOPE_RAILWAY = 0.04
MAX_SLOPE_MOTORWAY = 0.03       # max slope for motorways
MAX_SLOPE_ROAD = 0.08
MAX_TRANSVERSE_GRADIENT = 0.1   #
BRIDGE_MIN_LENGTH = 20.         # discard short bridges, draw road instead
DEBUG_PLOT = 0
CREATE_BRIDGES_ONLY = 0         # create only bridges and embankments
BRIDGE_LAYER_HEIGHT = 4.         # bridge height per layer
BRIDGE_BODY_HEIGHT = 0.9         # height of bridge body
EMBANKMENT_TEXTURE = textures.road.EMBANKMENT_1  # Texture for the embankment
MIN_ABOVE_GROUND_LEVEL = 0.01    # how much a highway / railway is at least hovering above ground
HIGHWAY_TYPE_MIN = 4  # The lower the number, the more ways are added. See roads.HighwayType
POINTS_ON_LINE_DISTANCE_MAX = 1000  # the maximum distance between two points on a line. If longer, then new points are added


# =============================================================================
# PARAMETERS RELATED TO TEXTURES
# =============================================================================

ATLAS_SUFFIX_DATE = False   # -- add timestamp to file name
TEXTURES_ROOFS_NAME_EXCLUDE = []  # list of roof file names to exclude, e.g. ["roof_red3.png", "roof_orange.png"]
TEXTURES_FACADES_NAME_EXCLUDE = []  # e.g. ["de/commercial/facade_modern_21x42m.jpg"]
TEXTURES_ROOFS_PROVIDE_EXCLUDE = []  # list of roof provides features to exclude, e.g. ["colour:red"]
TEXTURES_FACADES_PROVIDE_EXCLUDE = []  # ditto for facade provides features, e.g. ["age:modern"]


# default_args_end # DO NOT MODIFY THIS LINE


def get_output_path():
    if PATH_TO_OUTPUT:
        return PATH_TO_OUTPUT
    return PATH_TO_SCENERY


def get_OSM_file_name():
    """
    Returns the path to the OSM File
    """
    return PREFIX + os.sep + OSM_FILE


def get_repl_prefix():
    """FIXME: what does the REGEXP actually mean?"""
    return re.sub('[\/]', '_', PREFIX)


def get_center_global():
    cmin = v.Vec2d(BOUNDARY_WEST, BOUNDARY_SOUTH)
    cmax = v.Vec2d(BOUNDARY_EAST, BOUNDARY_NORTH)
    return (cmin + cmax) * 0.5


def get_extent_global():
    cmin = v.Vec2d(BOUNDARY_WEST, BOUNDARY_SOUTH)
    cmax = v.Vec2d(BOUNDARY_EAST, BOUNDARY_NORTH)
    return cmin, cmax


def get_clipping_extent(use_border=True):
    if use_border:
        rect = [(BOUNDARY_WEST-BOUNDARY_CLIPPING_BORDER_SIZE, BOUNDARY_SOUTH-BOUNDARY_CLIPPING_BORDER_SIZE),
                (BOUNDARY_EAST+BOUNDARY_CLIPPING_BORDER_SIZE, BOUNDARY_SOUTH-BOUNDARY_CLIPPING_BORDER_SIZE),
                (BOUNDARY_EAST+BOUNDARY_CLIPPING_BORDER_SIZE, BOUNDARY_NORTH+BOUNDARY_CLIPPING_BORDER_SIZE),
                (BOUNDARY_WEST-BOUNDARY_CLIPPING_BORDER_SIZE, BOUNDARY_NORTH+BOUNDARY_CLIPPING_BORDER_SIZE)]
    else:
        rect = [(BOUNDARY_WEST, BOUNDARY_SOUTH),
                (BOUNDARY_EAST, BOUNDARY_SOUTH),
                (BOUNDARY_EAST, BOUNDARY_NORTH),
                (BOUNDARY_WEST, BOUNDARY_NORTH)]
    return rect


def show():
    """
    Prints all parameters as key = value if log level is INFO or lower
    """
    if log_level_info_or_lower():
        print('--- Using the following parameters: ---')
        my_globals = globals()
        for k in sorted(my_globals.keys()):
            if k.startswith('__'):
                continue
            elif k == "args":
                continue
            elif k == "parser":
                continue
            elif isinstance(my_globals[k], type) or \
                    isinstance(my_globals[k], types.FunctionType) or \
                    isinstance(my_globals[k], types.ModuleType):
                continue
            else:
                print('%s = %s' % (k, my_globals[k]))
        print('------')


def read_from_file(filename):
    logging.info('Reading parameters from file: %s' % filename)
    default_globals = globals()
    file_globals = dict()
    try:
        exec(compile(open(filename).read(), filename, 'exec'), file_globals)
    except IOError as reason:
        logging.error("Error processing file with parameters: %s", reason)
        sys.exit(1)
    except NameError:
        logging.error(traceback.format_exc())
        logging.error("Error while reading " + filename + ". Perhaps an unquoted string in your parameters file?")
        sys.exit(1)

    for k, v in file_globals.items():
        if k.startswith('_'):
            continue
        k = k.upper()
        if k in default_globals:
            default_globals[k] = v
        else:
            logging.warning('Unknown parameter: %s=%s' % (k, v))


def show_default():
    """show default parameters by printing all params defined above between
        # default_args_start and # default_args_end to screen.
    """
    f = open(sys.argv[0], 'r')
    do_print = False
    for line in f.readlines():
        if line.startswith('# default_args_start'):
            do_print = True
            continue
        elif line.startswith('# default_args_end'):
            return
        if do_print:
            print(line, end='')


def set_loglevel(args_loglevel=None):
    """Set loglevel from parameters or command line."""
    global LOGLEVEL
    if args_loglevel is not None:
        LOGLEVEL = args_loglevel
    LOGLEVEL = LOGLEVEL.upper()
    # -- add another log level VERBOSE. Use this when logging stuff in loops, e.g. per-OSM-object,
    #    potentially flooding the screen
    logging.VERBOSE = 5
    logging.addLevelName(logging.VERBOSE, "VERBOSE")
    logging.Logger.verbose = lambda inst, msg, *args, **kwargs: inst.log(logging.VERBOSE, msg, *args, **kwargs)
    logging.verbose = lambda msg, *args, **kwargs: logging.log(logging.VERBOSE, msg, *args, **kwargs)

    numeric_level = getattr(logging, LOGLEVEL, None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % LOGLEVEL)
    logging.basicConfig(level=numeric_level)
    logging.getLogger().setLevel(LOGLEVEL)


def log_level_info_or_lower():
    return logging.getLogger().level <= logging.INFO


if __name__ == "__main__":
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="The parameters module provides parameters to osm2city - used as main it shows the parameters used.")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-d", "--show-default", action="store_true", help="show default parameters")
    args = parser.parse_args()
    if args.filename is not None:
        read_from_file(args.filename)
        show()
    if args.show_default:
        show_default()
