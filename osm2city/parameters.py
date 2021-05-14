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
import math
import sys
import traceback
import types
import typing
import unittest

import osm2city.textures.road
import osm2city.utils.calc_tile as ct
import osm2city.utils.coordinates as co
import osm2city.utils.log_helper as ulog
import osm2city.static_types.osmstrings as s

# default_args_start # DO NOT MODIFY THIS LINE
# -*- coding: utf-8 -*-
# The preceding line sets encoding of this file to utf-8. Needed for non-ascii
# object names. It must stay on the first or second line.

# =============================================================================
# PARAMETERS FOR ALL osm2city MODULES
# =============================================================================
# -- Scenery folder, typically a geographic name or the ICAO code of the airport
PREFIX = "LSZR"

# -- Boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
# The values are set dynamically during program execution - no need to set them manually.
BOUNDARY_WEST = 9.54
BOUNDARY_SOUTH = 47.48
BOUNDARY_EAST = 9.58
BOUNDARY_NORTH = 47.50

AREA = ''  # Not used in the code - use it in your parameters.py for conditional parameters

# -- Full path to the scenery folder without trailing slash. This is where we
#    will probe elevation and check for overlap with static objects. Most
#    likely you'll want to use your TerraSync path here.
PATH_TO_SCENERY = "/home/user/fgfs/scenery/TerraSync"

# Optional additional list of paths to scenery folders (e.g. project3000).
# Only used for overlap checking for buildings against static and shared objects
PATH_TO_SCENERY_OPT = None  # if not none, then needs to be list of strings

# -- The generated scenery (.stg, .ac, .xml) will be written to this path.
#    If empty, we'll use the correct location in PATH_TO_SCENERY. Note that
#    if you use TerraSync for PATH_TO_SCENERY, you MUST choose a different
#    path here. Otherwise, TerraSync will overwrite the generated scenery.
#    Also make sure PATH_TO_OUTPUT is included in your $FG_SCENERY.
PATH_TO_OUTPUT = "/home/user/fgfs/scenery/osm2city"

PATH_TO_OSM2CITY_DATA = "/home/user/osm2city-data"
DB_HOST = "localhost"  # The host name of the computer running PostGIS.
DB_PORT = 5432  # The port used to connect to the host
DB_NAME = "osmgis"  # The name of the database.
DB_USER = "gisuser"  # The name of the user to be used to read from the database.
DB_USER_PASSWORD = "n/a"  # The password for the DB_USER.

NO_ELEV = False             # -- skip elevation probing
FG_ELEV = '"D:/Program Files/FlightGear/bin/Win64/fgelev.exe"'
FG_ELEV_CACHE = True  # saves the elevation probing results to a file, so next rerun is faster (but uses disk space!)
PROBE_FOR_WATER = True  # only possible with FGElev version after 9th of November 2016 / FG 2016.4.1

# length/width in meters for clustering of meshes; has to be at least 3000. 4000 leads to max 5x5 meshes
CLUSTER_DIMENSION = 4000

WRITE_CLUSTER_STATS = False

FLAG_STG_BUILDING_LIST = False  # use BUILDING_LIST in stg-files in 2019.2+ format
FLAG_BUILDINGS_LIST_SKIP = False
FLAG_BUILDINGS_MESH_SKIP = False

BUILDING_LIST_ALLOW_NEIGHBOURS = True
BUILDING_LIST_AREA_DEVIATION = 0.9
BUILDING_LIST_DIST_DEVIATION = 0.8

FLAG_FAST_LANDUSE = False
FLAG_NEXT_GEN_TEXTURING = False
FLAG_AFTER_2020_3 = False
FLAG_STG_LOD_RADIUS = False  # requires FLAG_AFTER_2020_3

# Debugging by plotting with Matplotlib to pdfs. See description about its use in the appendix of the manual
DEBUG_PLOT_RECTIFY = False
DEBUG_PLOT_GENBUILDINGS = False
DEBUG_PLOT_LANDUSE = False
DEBUG_PLOT_ROADS = False
DEBUG_PLOT_BLOCKED_AREAS_DIFFERENTIATED = False  # plots airport blocked areas, static and shared stg-entries
DEBUG_PLOT_BLOCKED_AREAS_ROADS = []  # will only plot if at least one OSM id of a road in the list
DEBUG_PLOT_OFFSETS = False

# =============================================================================
# PARAMETERS RELATED TO BUILDINGS IN osm2city
# =============================================================================

# -- Check for objects in the PATH_TO_SCENERY folder based on convex hull around all points
OVERLAP_CHECK_CONVEX_HULL = True
OVERLAP_CHECK_CH_BUFFER_STATIC = 0.0
OVERLAP_CHECK_CH_BUFFER_SHARED = 0.0

OVERLAP_CHECK_CONSIDER_SHARED = True

OVERLAP_CHECK_APT_PAVEMENT_BUILDINGS_INCLUDE = None  # At apts in list include overlap check with pavement for buildings
OVERLAP_CHECK_APT_PAVEMENT_ROADS_INCLUDE = None  # At airports in list include overlap check with pavement for roads
OVERLAP_CHECK_APT_USE_BTG_ROADS = []
OVERLAP_CHECK_APT_USE_OSM_APRON_ROADS = False  # Add OSM APRON polygons for overlap checking with roads

OVERLAP_CHECK_EXCLUDE_AREAS_BUILDINGS = None  # Exclude placing buildings in this area: list of list of lon/lat tuples
OVERLAP_CHECK_EXCLUDE_AREAS_ROADS = None  # ditto

# -- Skip buildings based on their OSM name tag or OSM ID, e.g. in case there's already
#    a static model for these, and the overlap check fails.
#    Use unicode strings as in the first example if there are non-ASCII characters.
#    E.g. SKIP_LIST = ["Theologische Fakultät", "Rhombergpassage", 55875208]
#    For roads/railways OSM ID is checked.
SKIP_LIST = []
SKIP_LIST_OVERLAP = []  # list of .ac or .xml file names which should not be used for overlap tests

# -- Parameters which influence the number of buildings from OSM taken to output
BUILDING_MIN_HEIGHT = 0.0           # -- minimum height from bottom to top without roof height of a building to be included in output (does not include roof). Different from OSM tag "min_height", which states that the bottom of the building hovers min_height over the ground
# If set to 0.0, then not taken into consideration (default)
BUILDING_MIN_AREA = 50.0            # -- minimum area for a building to be included in output (not used for buildings with parent)
BUILDING_PART_MIN_AREA = 10.0  # minimum area for building:parts
BUILDING_REDUCE_THRESHOLD = 200.0   # -- threshold area of a building below which a rate of buildings gets reduced from output
BUILDING_REDUCE_RATE = 0.5          # -- rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_NEVER_REDUCE_LEVELS = 6      # -- buildings that tall will never be skipped
BUILDING_SIMPLIFY_TOLERANCE_LINE = 1.0
BUILDING_SIMPLIFY_TOLERANCE_AWAY = 2.5

BUILDING_COMPLEX_ROOFS = True       # -- generate complex roofs on buildings? I.e. other shapes than horizontal and flat
BUILDING_COMPLEX_ROOFS_MIN_LEVELS = 1  # don't put complex roof on buildings smaller than the specified value unless there is an explicit roof:shape flag
BUILDING_COMPLEX_ROOFS_MAX_LEVELS = 5   # don't put complex roofs on buildings taller than the specified value unless there is an explicit roof:shape flag
BUILDING_COMPLEX_ROOFS_MAX_AREA = 1600  # -- don't put complex roofs on buildings larger than this
BUILDING_COMPLEX_ROOFS_MIN_RATIO_AREA = 600  # if larger than this then ratio of length vs. area must be fulfilled
BUILDING_SKEL_ROOFS_MIN_ANGLE = 10  # -- pySkeleton based complex roofs will
BUILDING_SKEL_ROOFS_MAX_ANGLE = 50  #    have a random angle between MIN and MAX
BUILDING_SKEL_MAX_NODES = 10        # -- max number of nodes for which we generate pySkeleton roofs
BUILDING_SKEL_ROOF_MAX_HEIGHT = 6.  # -- skip skeleton roofs (gabled, pyramidal, ..) if the roof height is larger than this
BUILDING_SKEL_MAX_DIST_FROM_CENTROID = 400  # Hack to make sure skeleton residuals are not causing FG to crash in rendering
BUILDING_ROOF_SIMPLIFY_TOLERANCE = .5
BUILDING_SKILLION_ROOF_MAX_HEIGHT = 2.

BUILDING_TEXTURE_GROUP_RADIUS_M = 0  # For BUILDING_LIST buildings, distance within which buildings will tend to have the same texture

# If the roof_type is missing, what shall be the distribution of roof_types (must sum up to 1.0)
# The keys are the shapes and must correspond to valid RoofShape values in roofs.py
BUILDING_ROOF_SHAPE_RATIO = {s.V_FLAT: 0.1, s.V_GABLED: 0.8, s.V_HIPPED: 0.1}

# ==================== RECTIFY BUILDINGS ============
RECTIFY_ENABLED = True
RECTIFY_MAX_DRAW_SAMPLE = 20
RECTIFY_SEED_SAMPLE = True
RECTIFY_MAX_90_DEVIATION = 7
RECTIFY_90_TOLERANCE = 0.1

# Force European style inner cities with gables and red tiles
BUILDING_FORCE_EUROPEAN_INNER_CITY_STYLE = False

BUILDING_FAKE_AMBIENT_OCCLUSION = True      # -- fake AO by darkening facade textures towards the ground, using
BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT = 6.  # 1 - VALUE * exp(- AGL / HEIGHT )
BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE = 0.6

# Parameters which influence the height of buildings if no info from OSM is available.
BUILDING_NUMBER_LEVELS_CENTRE = {4: 0.2, 5: 0.7, 6: 0.1}
BUILDING_NUMBER_LEVELS_BLOCK = {4: 0.4, 5: 0.6}
BUILDING_NUMBER_LEVELS_DENSE = {3: 0.25, 4: 0.75}
BUILDING_NUMBER_LEVELS_PERIPHERY = {1: 0.3, 2: 0.65, 3: 0.05}
BUILDING_NUMBER_LEVELS_RURAL = {1: 0.3, 2: 0.7}
# the following are used if settlement type is not centre or block and building class is not residential
BUILDING_NUMBER_LEVELS_APARTMENTS = {2: 0.05, 3: 0.45, 4: 0.4, 5: 0.08, 6: 0.02}
BUILDING_NUMBER_LEVELS_INDUSTRIAL = {1: 0.3, 2: 0.6, 3: 0.1}  # for both industrial and warehouse
BUILDING_NUMBER_LEVELS_OTHER = {1: 0.2, 2: 0.4, 3: 0.3, 4: 0.1}  # e.g. commercial, public, retail

# make sure not visible buildings or building parts are excluded
BUILDING_UNDERGROUND_LOCATION = True
BUILDING_UNDERGROUND_INDOOR = True
BUILDING_UNDERGROUND_TUNNEL = True
BUILDING_UNDERGROUND_LEVEL_NEGATIVE = True

BUILDING_USE_SHARED_WORSHIP = False  # try to use shared models for worship buildings

# a hex value for the colour to be used if the colour value in OSM is missing or cannot be interpreted
BUILDING_FACADE_DEFAULT_COLOUR = '#D3D3D3'  # e.g. #d3d3d3 - light grey
BUILDING_ROOF_DEFAULT_COLOUR = '#B22222'  # e.g. #b22222 - firebrick

BUILDING_NUMBER_LEVELS_AEROWAY = 2
BUILDING_LEVEL_HEIGHT_AEROWAY = 3.5

# -- The more buildings end up in LOD rough, the more work for your GPU.
#    Increasing any of the following parameters will decrease GPU load.
LOD_ALWAYS_DETAIL_BELOW_AREA = 150  # -- below this area, buildings will always be LOD detail
LOD_ALWAYS_ROUGH_ABOVE_AREA = 500   # -- above this area, buildings will always be LOD rough
LOD_ALWAYS_ROUGH_ABOVE_LEVELS = 6   # -- above this number of levels, buildings will always be LOD rough
LOD_ALWAYS_DETAIL_BELOW_LEVELS = 3  # -- below this number of levels, buildings will always be LOD detail
LOD_PERCENTAGE_DETAIL = 0.5         # -- of the remaining buildings, this percentage will be LOD detail,
                                    #    the rest will be LOD rough.

OBSTRUCTION_LIGHT_MIN_HEIGHT = 150   # -- put obstruction lights on buildings with >= height. 0 for no lights.

# discard cluster if too few objects. Do not go below 1, otherwise lots of empty ac-objects and useless STG entries.
CLUSTER_MIN_OBJECTS = 5

# When searching for an existing OSM node based on distance: what is the allowed tolerance.
# Also used in roads.py to make sure blocked areas do not generate tiny differences.
TOLERANCE_MATCH_NODE = 0.5

DETAILS_PROCESS_PIERS = True
DETAILS_PROCESS_PLATFORMS = True

# =============================================================================
# PARAMETERS RELATED TO PYLONS, POWERLINES, AERIALWAYS IN pylons.py
# =============================================================================

C2P_PROCESS_POWERLINES = True
C2P_PROCESS_POWERLINES_MINOR = False  # only considered if C2P_PROCESS_POWERLINES is True
C2P_PROCESS_AERIALWAYS = False
C2P_PROCESS_OVERHEAD_LINES = False
C2P_PROCESS_WIND_TURBINES = True
C2P_PROCESS_STREETLAMPS = False  # experimental and unsupported
C2P_PROCESS_STORAGE_TANKS = True
C2P_PROCESS_CHIMNEYS = True
C2P_PROCESS_TREES = False  # Requires FLAG_AFTER_2020_3

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
C2P_CATENARY_A_MAX_SAGGING = 0.3  # the maximum sagging allowed no matter the catenary a relative to lowest cable height

C2P_CATENARY_MIN_DISTANCE = 30

C2P_POWER_LINE_ALLOW_100M = False

C2P_STREETLAMPS_MAX_DISTANCE_LANDUSE = 100
C2P_STREETLAMPS_RESIDENTIAL_DISTANCE = 40
C2P_STREETLAMPS_OTHER_DISTANCE = 70
C2P_STREETLAMPS_MIN_STREET_LENGTH = 20

C2P_WIND_TURBINE_MAX_DISTANCE_WITHIN_WIND_FARM = 700
C2P_WIND_TURBINE_MIN_DISTANCE_SHARED_OBJECT = 10

C2P_CHIMNEY_BRICK_RATION = 0.2  # the ratio of chimneys being made of bricks (rest is cement etc.)
C2P_CHIMNEY_MIN_HEIGHT = 20  # the minimum height a Chimney needs to have to be taken into account
C2P_CHIMNEY_DEFAULT_HEIGHT = 30  # the default height of chimneys, where the height is not specified in OSM
C2P_CHIMNEY_DEFAULT_HEIGHT_VARIATION = 10  # a random variation on top of the default height between 0 and value

C2P_TREES_DIST_BETWEEN_TREES_PARK = 15  # the average distance between trees in a park
C2P_TREES_SKIP_RATE_TREES_PARK = 0.7  # the rate at which trees are skipped of generated (0.7 means 7 out of 10 skipped)
C2P_TREES_DIST_BETWEEN_TREES_PARK_MAPPED = 100  # the average distance between trees in a park for testing manual
C2P_TREES_PARK_MIN_SIZE = 600  # the minimal size of a park to be taken into account

C2P_TREES_DIST_BETWEEN_TREES_GARDEN = 10  # the average distance between trees in a garden
C2P_TREES_SKIP_RATE_TREES_GARDEN = 0.5  # the rate at which trees are skipped of generated

C2P_TREES_MAX_AVG_DIST_TREES_ROW = 20  # if average distance between mapped trees smaller, then replace with calculated
C2P_TREES_DIST_TREES_ROW_CALCULATED = 15  # the distance used between trees in a row/line if calculated manually
C2P_TREES_DIST_MINIMAL = 10  # minimal distance between trees unless mapped manually

# =============================================================================
# PARAMETERS RELATED TO roads.py
# =============================================================================

MAX_SLOPE_RAILWAY = 0.04
MAX_SLOPE_TRAM = 0.14
MAX_SLOPE_RACK = 0.49
MAX_SLOPE_MOTORWAY = 0.07       # max slope for motorways
MAX_SLOPE_ROAD = 0.15
MAX_TRANSVERSE_GRADIENT = 0.1   #
BRIDGE_MIN_LENGTH = 20.         # discard short bridges, draw road instead
CREATE_BRIDGES_ONLY = False         # create only bridges and embankments
BRIDGE_LAYER_HEIGHT = 4.         # bridge height per layer
BRIDGE_BODY_HEIGHT = 0.9         # height of bridge body
EMBANKMENT_TEXTURE = osm2city.textures.road.EMBANKMENT_1  # Texture for the embankment
MIN_EMBANKMENT_HEIGHT = 0.4     # the min height of an embankment before it actually is written
MIN_ABOVE_GROUND_LEVEL = 0.1    # how much a highway / railway is at least hovering above ground
DISTANCE_BETWEEN_LAYERS = 0.2  # how much different layers of roads/railways at the same node are separated
HIGHWAY_TYPE_MIN = 4  # The lower the number, the more ways are added. See roads.HighwayType
HIGHWAY_TYPE_MIN_ROUGH_LOD = 6  # the minimum type to be added to the rough LOD clusters
POINTS_ON_LINE_DISTANCE_MAX = 1000  # the max dist between two points on a line. If longer, then new points are added
MIN_ROAD_SEGMENT_LENGTH = 1.0         # if segment length is smaller than this, then remove point

USE_TRAM_LINES = False  # whether to build tram lines (OSM railway=tram). Often they do not merge well with roads

# when a static bridge model or another blocked area (e.g. on airport) intersect with a way,
# how much must at least be left so the way is kept after intersection
OVERLAP_CHECK_ROAD_MIN_REMAINING = 10


# =============================================================================
# PARAMETERS RELATED TO TEXTURES
# =============================================================================

ATLAS_SUFFIX = ''   # -- add a suffix to the atlas/atlas_LM file name
TEXTURES_ROOFS_NAME_EXCLUDE = []  # list of roof file names to exclude, e.g. ["roof_red3.png", "roof_orange.png"]
TEXTURES_FACADES_NAME_EXCLUDE = []  # e.g. ["de/commercial/facade_modern_21x42m.jpg"]
TEXTURES_ROOFS_PROVIDE_EXCLUDE = []  # list of roof provides features to exclude, e.g. ["colour:red"]
TEXTURES_FACADES_PROVIDE_EXCLUDE = []  # ditto for facade provides features, e.g. ["age:modern"]
TEXTURES_REGIONS_EXPLICIT = []  # list of exclusive regions to accept. All if empty
TEXTURES_EMPTY_LM_RGB_VALUE = 35


# =============================================================================
# PARAMETERS RELATED TO OWBB
# =============================================================================

# ==================== BUILD-ZONES GENERATION ============

OWBB_LANDUSE_CACHE = False
OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE = 30
OWBB_GENERATE_LANDUSE_BUILDING_BUFFER_DISTANCE_MAX = 50
OWBB_GENERATE_LANDUSE_LANDUSE_MIN_AREA = 5000
OWBB_GENERATE_LANDUSE_LANDUSE_HOLES_MIN_AREA = 20000
OWBB_GENERATE_LANDUSE_SIMPLIFICATION_TOLERANCE = 20

OWBB_USE_BTG_LANDUSE = False  # does not work currently

OWBB_SPLIT_MADE_UP_LANDUSE_BY_MAJOR_LINES = True  # for external and generated

# the buffer around built-up land-use areas to be used for lighting of streets
# also used for buffering around water areas in cities
OWBB_BUILT_UP_BUFFER = 50
OWBB_BUILT_UP_AREA_HOLES_MIN_AREA = 100000
OWBB_BUILT_UP_MIN_LIT_AREA = 100000

OWBB_PLACE_POPULATION_DEFAULT_CITY = 200000
OWBB_PLACE_POPULATION_DEFAULT_TOWN = 20000
OWBB_PLACE_POPULATION_MIN_BLOCK = 15000
OWBB_PLACE_RADIUS_EXPONENT_CENTRE = 0.5  # 1/2
OWBB_PLACE_RADIUS_EXPONENT_BLOCK = 0.6  # 5/8
OWBB_PLACE_RADIUS_EXPONENT_DENSE = 0.666  # 2/3
OWBB_PLACE_RADIUS_FACTOR_CITY = 1.
OWBB_PLACE_RADIUS_FACTOR_TOWN = 1.

OWBB_PLACE_TILE_BORDER_EXTENSION = 10000

OWBB_PLACE_CHECK_DENSITY = False
OWBB_PLACE_SANITY_DENSITY = 0.15

OWBB_GRID_SIZE = 2000

# ==================== BUILDING GENERATION ============

OWBB_GENERATED_BUILDINGS_CACHE = False  # has only effect if OWBB_LANDUSE_CACHE = False
OWBB_GENERATE_BUILDINGS = False
OWBB_STEP_DISTANCE = 2  # in meters
OWBB_MIN_STREET_LENGTH = 10  # in meters
OWBB_MIN_CITY_BLOCK_AREA = 200  # square meters
OWBB_CITY_BLOCK_HIGHWAY_BUFFER = 3  # in metres buffer around highways to find city blocks

OWBB_RESIDENTIAL_HIGHWAY_MIN_GEN_SHARE = 0.3
OWBB_INDUSTRIAL_HIGHWAY_MIN_GEN_SHARE = 0.3  # FIXME: not yet used

OWBB_ZONE_AREA_MAX_GEN = 0.1  # FIXME: needs to be zone type specific and maybe village vs. town

OWBB_USE_GENERATED_LANDUSE_FOR_BUILDING_GENERATION = False
OWBB_USE_EXTERNAL_LANDUSE_FOR_BUILDING_GENERATION = True

OWBB_HIGHWAY_WIDTH_FACTOR = 1.3

OWBB_RESIDENTIAL_RURAL_TERRACE_SHARE = 0.1
OWBB_RESIDENTIAL_PERIPHERY_TERRACE_SHARE = 0.25
OWBB_RESIDENTIAL_RURAL_APARTMENT_SHARE = 0.1
OWBB_RESIDENTIAL_PERIPHERY_APARTMENT_SHARE = 0.3
OWBB_RESIDENTIAL_DENSE_TYPE_SHARE = {s.V_DETACHED: 0.1, s.V_TERRACE: 0.1, s.V_APARTMENTS: 0.3, s.V_ATTACHED: 0.5}

OWBB_RESIDENTIAL_TERRACE_MIN_NUMBER = 4
OWBB_RESIDENTIAL_TERRACE_TYPICAL_NUMBER = 5

OWBB_RESIDENTIAL_SIDE_FACTOR_PERIPHERY = 1.0
OWBB_RESIDENTIAL_SIDE_FACTOR_DENSE = 0.8
OWBB_RESIDENTIAL_BACK_FACTOR_PERIPHERY = 2.0
OWBB_RESIDENTIAL_FRONT_FACTOR_PERIPHERY = 1.0
OWBB_FRONT_DENSE = 3.0  # same for BLOCK and CENTRE

OWBB_INDUSTRIAL_LARGE_MIN_AREA = 500
OWBB_INDUSTRIAL_LARGE_SHARE = 0.4
OWBB_INDUSTRIAL_BUILDING_SIDE_MIN = 2.0
OWBB_INDUSTRIAL_BUILDING_SIDE_MAX = 5.0


# ==================== BUILDINGS LIBRARY ============
ALLOW_EMPTY_REGIONS = True
ACCEPTED_REGIONS = ['DE', 'DK']


# default_args_end # DO NOT MODIFY THIS LINE

def get_output_path():
    if PATH_TO_OUTPUT:
        return PATH_TO_OUTPUT
    return PATH_TO_SCENERY


def get_center_global():
    cmin = co.Vec2d(BOUNDARY_WEST, BOUNDARY_SOUTH)
    cmax = co.Vec2d(BOUNDARY_EAST, BOUNDARY_NORTH)
    return (cmin + cmax) * 0.5


def get_extent_local(transformer: co.Transformation) -> typing.Tuple[co.Vec2d, co.Vec2d]:
    cmin = co.Vec2d(BOUNDARY_WEST, BOUNDARY_SOUTH)
    cmax = co.Vec2d(BOUNDARY_EAST, BOUNDARY_NORTH)
    logging.info("min/max " + str(cmin) + " " + str(cmax))
    lmin = co.Vec2d(transformer.to_local((cmin.x, cmin.y)))
    lmax = co.Vec2d(transformer.to_local((cmax.x, cmax.y)))
    return lmin, lmax


def get_tile_radius() -> float:
    return co.calc_distance_global(BOUNDARY_WEST, BOUNDARY_SOUTH, BOUNDARY_EAST, BOUNDARY_NORTH) * 0.5


def get_cluster_dimension_radius() -> float:
    return math.sqrt(2) * CLUSTER_DIMENSION * 0.5


def get_tile_index() -> int:
    lon_lat = get_center_global()
    return ct.calc_tile_index((lon_lat.lon, lon_lat.lat))


def get_clipping_border():
    rect = [(BOUNDARY_WEST, BOUNDARY_SOUTH),
            (BOUNDARY_EAST, BOUNDARY_SOUTH),
            (BOUNDARY_EAST, BOUNDARY_NORTH),
            (BOUNDARY_WEST, BOUNDARY_NORTH)]
    return rect


def _check_ratio_dict_parameter(ratio_dict: typing.Optional[typing.Dict], name: str, is_int: bool = True) -> None:
    if ratio_dict is None:
        raise ValueError('Parameter {} must not be None'.format(name))
    if not isinstance(ratio_dict, dict):
        raise ValueError('Parameter {} must be a dict'.format(name))
    if len(ratio_dict) == 0:
        raise ValueError('Parameter %s must not be an empty dict'.format(name))
    total = 0.
    prev_key = -9999
    for key, ratio in ratio_dict.items():
        if is_int:
            if not isinstance(key, int):
                raise ValueError('key {} in parameter {} must be an int'.format(str(key), name))
            if prev_key > key:
                raise ValueError('key {} in parameter {} must be larger than previous key'.format(str(key), name))
            prev_key = key
        else:
            if not isinstance(key, str):
                raise ValueError('key {} in parameter {} must be a string'.format(str(key), name))
        if not isinstance(ratio, float):
            raise ValueError('ratio {} for key {} in param {} must be a float'.format(str(ratio), str(key), name))
        total += ratio
    if abs(total - 1) > 0.001:
        raise ValueError('The total of all ratios in param {} must be 1'.format(name))


def show():
    """
    Prints all parameters as key = value if log level is INFO or lower
    """
    if ulog.log_level_info_or_lower():
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

    has_unknown_parameters = False
    for k, v in file_globals.items():
        if k.startswith('_'):
            continue
        k = k.upper()
        if k in default_globals:
            default_globals[k] = v
        else:
            logging.error('Unknown parameter: %s=%s' % (k, v))
            has_unknown_parameters = True
    if has_unknown_parameters:
        sys.exit(1)

    # correct use of parameter PATH_TO_SCENERY_OPT: earlier only string, now list of strings (or None)
    global PATH_TO_SCENERY_OPT
    if PATH_TO_SCENERY_OPT:
        if isinstance(PATH_TO_SCENERY_OPT, str):
            if PATH_TO_SCENERY_OPT == "":
                PATH_TO_SCENERY_OPT = None
            else:
                PATH_TO_SCENERY_OPT = [PATH_TO_SCENERY_OPT]

    # check the ratios in specific parameters
    global BUILDING_NUMBER_LEVELS_CENTRE
    global BUILDING_NUMBER_LEVELS_BLOCK
    global BUILDING_NUMBER_LEVELS_DENSE
    global BUILDING_NUMBER_LEVELS_PERIPHERY
    global BUILDING_NUMBER_LEVELS_RURAL
    global BUILDING_NUMBER_LEVELS_APARTMENTS
    global BUILDING_NUMBER_LEVELS_INDUSTRIAL
    global BUILDING_NUMBER_LEVELS_OTHER

    global BUILDING_ROOF_SHAPE_RATIO
    global OWBB_RESIDENTIAL_DENSE_TYPE_SHARE

    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_CENTRE, 'BUILDING_NUMBER_LEVELS_CENTRE')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_BLOCK, 'BUILDING_NUMBER_LEVELS_BLOCK')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_DENSE, 'BUILDING_NUMBER_LEVELS_DENSE')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_PERIPHERY, 'BUILDING_NUMBER_LEVELS_PERIPHERY')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_RURAL, 'BUILDING_NUMBER_LEVELS_RURAL')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_APARTMENTS, 'BUILDING_NUMBER_LEVELS_APARTMENTS')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_INDUSTRIAL, 'BUILDING_NUMBER_LEVELS_INDUSTRIAL')
    _check_ratio_dict_parameter(BUILDING_NUMBER_LEVELS_OTHER, 'BUILDING_NUMBER_LEVELS_OTHER')
    _check_ratio_dict_parameter(BUILDING_ROOF_SHAPE_RATIO, 'BUILDING_ROOF_SHAPE_RATIO', False)
    _check_ratio_dict_parameter(OWBB_RESIDENTIAL_DENSE_TYPE_SHARE, 'OWBB_RESIDENTIAL_DENSE_TYPE_SHARE', False)

    # check minimal tile size - otherwise there might be problems with naming of files within same tile
    # in clustering. Each tiles has max ca. 20 km length/width. There may only be one digit for x/y naming
    global CLUSTER_DIMENSION
    if CLUSTER_DIMENSION is None or CLUSTER_DIMENSION < 3000:
        raise ValueError('Parameter CLUSTER_DIMENSION needs to be at least 3000')


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


def set_boundary(boundary_west: float, boundary_south: float,
                 boundary_east: float, boundary_north: float) -> None:
    """Overrides the geographical boundary values (either default values or read from file).
    In most situations should be called after method read_from_file().
    """
    import osm2city.utils.utilities as uu
    try:
        uu.check_boundary(boundary_west, boundary_south, boundary_east, boundary_north)
    except uu.BoundaryError as be:
        logging.error(be.message)
        sys.exit(1)

    global BOUNDARY_WEST
    BOUNDARY_WEST = boundary_west
    global BOUNDARY_SOUTH
    BOUNDARY_SOUTH = boundary_south
    global BOUNDARY_EAST
    BOUNDARY_EAST = boundary_east
    global BOUNDARY_NORTH
    BOUNDARY_NORTH = boundary_north


if __name__ == "__main__":
    # Handling arguments and parameters
    parser = argparse.ArgumentParser(
        description="The parameters module provides parameters to osm2city - run as main it shows the parameters used.")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-d", "--show-default", action="store_true", help="show default parameters")
    args = parser.parse_args()
    if args.filename is not None:
        read_from_file(args.filename)
        show()
    if args.show_default:
        show_default()


# ================ UNITTESTS =======================


class TestParameters(unittest.TestCase):
    def test_check_ratio_dict_parameter(self):
        my_ratio_dict = None
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = list()
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = dict()
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = {'A': 'B'}
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = {1: 'b'}
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = {1: 0.01, 2: 1.}
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = {2: 0.01, 1: .99}
        with self.assertRaises(ValueError):
            _check_ratio_dict_parameter(my_ratio_dict, 'my_ratio_dict')
        my_ratio_dict = {1: 0.01, 2: 0.99}
        self.assertEqual(2, len(my_ratio_dict), 'Length correct and no exception')
