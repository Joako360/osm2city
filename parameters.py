# -*- coding: utf-8 -*-
'''
Central place to store parameters / settings / variables in osm2city.
All lenght, height etc. parameters are in meters, square meters (m2) etc.

Created on May 27, 2013

@author: vanosten
'''

import sys
import types

# -- default parameters. Config file overrides these.

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

# -- write .stg, .ac, .xml to this path. If empty, data is automatically written to correct location
#    in $PATH_TO_SCENERY
PATH_TO_OUTPUT = ""

NO_ELEV = False             # -- skip elevation interpolation

# -- check for overlap with static models. The scenery folder must contain an "Objects" folder
OVERLAP_CHECK = True
OVERLAP_RADIUS = 5

TILE_SIZE = 1000            # -- tile size in meters for clustering of buildings

OSM_FILE = "buildings.osm"  # -- file name of the file with OSM data. Must reside in $PREFIX
MAX_OBJECTS = 50000         # -- maximum number of buildings to read from OSM data
CONCURRENCY = 1             # -- number of parallel OSM parsing threads
USE_PKL = False             # -- instead of parsing the OSM file, read a previously created cache file $PREFIX/buildings.pkl

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

def set_parameters(paramDict):
    for k in paramDict:
        if k in globals():
            if isinstance(globals()[k], types.BooleanType):
                globals()[k] = parse_bool(k, paramDict[k])
            elif isinstance(globals()[k], types.FloatType):
                floatValue = parse_float(k, paramDict[k])
                if None is not floatValue:
                    globals()[k] = floatValue
            elif isinstance(globals()[k], types.IntType):
                intValue = parse_int(k, paramDict[k])
                if None is not intValue:
                    globals()[k] = intValue
            elif isinstance(globals()[k], types.StringType):
                if None is not paramDict[k]:
                    globals()[k] = paramDict[k]
            elif isinstance(globals()[k], types.ListType):
                globals()[k] = parse_list(paramDict[k])
            else:
                print "Parameter", k, "has an unknown type/value:" , paramDict[k]
        else:
            print "Ignoring unknown parameter", k

def show():
    '''
    Prints all parameters as key = value
    '''
    print '--- Using the following parameters: ---'
    myGlobals = globals()
    for k in sorted(myGlobals.iterkeys()):
        if k.startswith('__'):
            continue
        if isinstance(myGlobals[k], types.ClassType) or isinstance(myGlobals[k], types.FunctionType) or isinstance(myGlobals[k], types.ModuleType):
            continue
        if isinstance(myGlobals[k], types.ListType):
            value = ', '.join(myGlobals[k])
            print k, '=', value
        else:
            print k, '=', myGlobals[k]
    print '------'


def parse_list(stringValue):
    '''
    Tries to parse a string containing comma separated values and returns a list
    '''
    myList = []
    if None is not stringValue:
        myList = stringValue.split(',')
        for index in range(len(myList)):
            myList[index] = myList[index].strip().strip('"\'')
    return myList

def parse_float(key, stringValue):
    '''
    Tries to parse a string and get a float. If it is not possible, then None is returned.
    On parse exception the key and the value are printed to console
    '''
    floatValue = None
    try:
        floatValue = float(stringValue)
    except ValueError:
        print 'Unable to convert', stringValue, 'to decimal number. Relates to key', key
    return floatValue

def parse_int(key, stringValue):
    '''
    Tries to parse a string and get an int. If it is not possible, then None is returned.
    On parse exception the key and the value are printed to console
    '''
    intValue = None
    try:
        intValue = int(stringValue)
    except ValueError:
        print 'Unable to convert', stringValue, 'to number. Relates to key', key
    return intValue

def parse_bool(key, stringValue):
    '''
    Tries to parse a string and get a boolean. If it is not possible, then False is returned.
    '''
    if stringValue.lower() in ("yes", "true", "on", "1"):
        return True
    if stringValue.lower() in ("no", "false", "off", "0"):
        return False
    print "Boolean value %s for %s not understood. Assuming False." % (stringValue, key)
    # FIXME: bail out if not understood!
    return False

def read_from_file(filename):
    print 'Reading parameters from file:', filename
    try:
        f = open(filename, 'r')
        paramDict = {}
        full_line = ""
        for line in f:
            # -- ignore comments and empty lines
            line = line.split('#')[0].strip()
            if line == "": continue

            full_line += line  # -- allow for multi-line lists
            if line.endswith(","): continue

            pair = full_line.split("=", 1)
            key = pair[0].strip().upper()
            value = None
            if 2 == len(pair):
                value = pair[1].strip()
            paramDict[key] = value
            full_line = ""

        set_parameters(paramDict)
        f.close()
    except IOError, reason:
        print "Error processing file with parameters:", reason
        sys.exit(1)

