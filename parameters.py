# -*- coding: utf-8 -*-
'''
Central place to store parameters / settings / variables in osm2city.
All lenght, height etc. parameters are in meters, square meters (m2) etc.

Created on May 27, 2013

@author: vanosten
'''

import sys
import types

# The boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
BOUNDARY_WEST = 9.54
BOUNDARY_SOUTH = 47.48
BOUNDARY_EAST = 9.58
BOUNDARY_NORTH = 47.50

# The distance between raster points for the derived elevation map (x is horizontal, y is vertical)
ELEV_RASTER_X = 10
ELEV_RASTER_Y = 10

# The scenery folder (typically a geographic name or the ICAO code of the airport
PREFIX = "LSZR"
# the full path to the scenery folder without trailing slash. Last folder should be equal to PREFIX
PATH_TO_SCENERY = "/home/vanosten/bin/fgfs_scenery/customscenery/LSZR"

# skip elevation interpolation
NO_ELEV = False
# check for overlap with static models. The scenery folder needs to contain a "Objects" folder
CHECK_OVERLAP = False
# read from already existing converted OSM building data in file system for faster load
USE_PKL = False
# the tile size in meters for clustering of buildings
TILE_SIZE = 1000
# the maximum number of buildings to read from osm data
TOTAL_OBJECTS = 50000
# the file name of the file with osm data. Should reside in PATH_TO_SCENERY
OSM_FILE = "mylszr.osm"
# the buildings in OSM to skip
SKIP_LIST = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
  "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
  "Residenzschloss Dresden", "Fernsehturm", "Fernsehturm Dresden"]

# Parameters which influence the number of buildings from OSM taken to output
BUILDING_MIN_HEIGHT = 3.4 # The minimum height of a building to be included in output (does not include roof)
BUILDING_MIN_AREA = 50.0 # The minimum area for a building to be included in output
BUILDING_REDUCE_THRESHOLD = 200.0 # The threshold area of a building below which a rate of buildings get reduced from output
BUILDING_REDUCE_RATE = 0.5 # The rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_REDUCE_CHECK_TOUCH = False # Before removing a building due to area check whether it is touching another building and therefore should be kept
BUILDING_SIMPLIFY_TOLERANCE = 1.0 # All points in the simplified building will be within the tolerance distance of the original geometry.

# Parameters which influence the height of buildings in info in OSM not available.
# It uses a triangular distribution (see http://en.wikipedia.org/wiki/Triangular_distribution)
BUILDING_CITY_LEVELS_LOW = 2.0
BUILDING_CITY_LEVELS_MODE = 3.5
BUILDING_CITY_LEVELS_HEIGH = 5.0
BUILDING_CITY_LEVEL_HEIGHT_LOW = 3.1
BUILDING_CITY_LEVEL_HEIGHT_MODE = 3.3
BUILDING_CITY_LEVEL_HEIGHT_HEIGH = 3.6
# FIXME: same parameters for place = town, village, suburb

def setParameters(paramDict):
    for k in paramDict:
        if k in globals():
            if isinstance(globals()[k], types.BooleanType):
                globals()[k] = paramDict[k]
            elif isinstance(globals()[k], types.FloatType):
                floatValue = parseFloat(k, paramDict[k])
                if None is not floatValue:
                    globals()[k] = floatValue
            elif isinstance(globals()[k], types.IntType):
                intValue = parseInt(k, paramDict[k])
                if None is not intValue:
                    globals()[k] = intValue
            elif isinstance(globals()[k], types.StringType):
                if None is not paramDict[k]:
                    globals()[k] = paramDict[k]
            elif isinstance(globals()[k], types.ListType):
                globals()[k] = parseList(paramDict[k])
            else:
                print "Parameter", k, "has an unknown type/value:" , paramDict[k]
        else:
            print "The following parameter does not exist:", k

def printParams():
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


def parseList(stringValue):
    '''
    Tries to parse a string containing comma separated values and returns a list
    '''
    myList = []
    if None is not stringValue:
        myList = stringValue.split(',')
        for index in range(len(myList)):
            myList[index] = myList[index].strip()
    return myList

def parseFloat(key, stringValue):
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

def parseInt(key, stringValue):
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

def parseBool(stringValue):
    '''
    Tries to parse a string and get a boolean. If it is not possible, then False is returned.
    '''
    if stringValue.lower() in ("yes", "true"):
        return True
    return False

def readFromFile(filename):
    print 'Reading parameters from file:', filename
    try:
        file_object = open(filename, 'r')
        paramDict = {}
        for line in file_object:
            if 0 == len(line.strip()) or line.startswith('#'): # lines starting with # are treated as comments
                continue
            else:
                pair = line.split('=',1)
                key = pair[0].strip()
                value = None
                if 2 == len(pair):
                    value = pair[1].strip()
                paramDict[key] = value
        setParameters(paramDict)
        file_object.close()
    except IOError, reason:
        print "Error processing file with parameters:", reason
        sys.exit(1)

