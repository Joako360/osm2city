# -*- coding: utf-8 -*-
'''
Central place to store parameters / settings / variables in osm2city.
All lenght, height etc. parameters are in meters, square meters (m2) etc.

Created on May 27, 2013

@author: vanosten
'''

import sys
import types

# -- Boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
BOUNDARY_WEST = 9.54
BOUNDARY_SOUTH = 47.48
BOUNDARY_EAST = 9.58
BOUNDARY_NORTH = 47.50

# -- Distance between raster points for the derived elevation map (x is horizontal, y is vertical)
ELEV_RASTER_X = 10
ELEV_RASTER_Y = 10

# -- Scenery folder (typically a geographic name or the ICAO code of the airport
PREFIX = "LSZR"


# -- Full path to the scenery folder without trailing slash. There should be 
#    an OBJECTS/ folder below PATH_TO_SCENERY
PATH_TO_SCENERY = "/home/user/fgfs/scenery/"

# -- skip elevation interpolation
NO_ELEV = False
# -- check for overlap with static models. The scenery folder needs to contain an "Objects" folder
OVERLAP_CHECK = False
OVERLAP_RADIUS = 5

# -- instead of parsing the OSM file, read a previously created cache file $PREFIX/buildings.pkl
USE_PKL = False
# -- tile size in meters for clustering of buildings
TILE_SIZE = 1000
# -- maximum number of buildings to read from OSM data
MAX_OBJECTS = 50000
# -- file name of the file with OSM data. Should reside in PATH_TO_SCENERY
OSM_FILE = "mylszr.osm"
CONCURRENCY = 1 # -- number of parallel OSM parsing threads
# -- skip reading names buildings from OSM
SKIP_LIST = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
  "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
  "Residenzschloss Dresden", "Fernsehturm", "Fernsehturm Dresden"]

# -- Parameters which influence the number of buildings from OSM taken to output
BUILDING_MIN_HEIGHT = 3.4 # -- minimum height of a building to be included in output (does not include roof)
BUILDING_MIN_AREA = 50.0 # -- minimum area for a building to be included in output
BUILDING_REDUCE_THRESHOLD = 200.0 # -- threshold area of a building below which a rate of buildings gets reduced from output
BUILDING_REDUCE_RATE = 0.5 # -- rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_REDUCE_CHECK_TOUCH = False # -- before removing a building due to area, check whether it is touching another building and therefore should be kept
BUILDING_SIMPLIFY_TOLERANCE = 1.0 # -- all points in the simplified building will be within the tolerance distance of the original geometry.

# -- Parameters which influence the height of buildings if no info from OSM is available.
#    It uses a triangular distribution (see http://en.wikipedia.org/wiki/Triangular_distribution)
BUILDING_CITY_LEVELS_LOW = 2.0
BUILDING_CITY_LEVELS_MODE = 3.5
BUILDING_CITY_LEVELS_HEIGH = 5.0
BUILDING_CITY_LEVEL_HEIGHT_LOW = 3.1
BUILDING_CITY_LEVEL_HEIGHT_MODE = 3.3
BUILDING_CITY_LEVEL_HEIGHT_HEIGH = 3.6
# FIXME: same parameters for place = town, village, suburb

LOD_PERCENTAGE_ROUGH = 0.7

OBSTRUCTION_LIGHT_MIN_LEVELS = 15 # -- put obstruction lights on buildings with >= given levels

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
            myList[index] = myList[index].strip()
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
            line = line.strip()
            # -- ignore empty lines and lines starting with #
            if line == "" or line.startswith("#"): continue

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

