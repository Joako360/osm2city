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
BUILDING_MIN_HEIGHT = 3.4 # The minimum height of a building to be included in output
BUILDING_MIN_AREA = 50.0 # The minimum area for a building to be included in output
BUILDING_REDUCE_THRESHOLD = 200.0 # The threshold area of a building below which a rate of buildings get reduced from output
BUILDING_REDUCE_RATE = 0.5 # The rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
BUILDING_SIMPLIFY_TOLERANCE = 1.0 # All points in the simplified building will be within the tolerance distance of the original geometry. 

def setParameters(paramDict):
    '''
    Sets the parameter values from a dictionary read by function readFromFile.
    If a parameter is not in the dictionary or cannot be parsed, then a default is chosen.
    '''
    global BOUNDARY_WEST
    if 'BOUNDARY_WEST' in paramDict:
        floatValue = parseFloat('BOUNDARY_WEST', paramDict['BOUNDARY_WEST'])
        if None is not floatValue:
            BOUNDARY_WEST = floatValue
    global BOUNDARY_SOUTH
    if 'BOUNDARY_SOUTH' in paramDict:
        floatValue = parseFloat('BOUNDARY_SOUTH', paramDict['BOUNDARY_SOUTH'])
        if None is not floatValue:
            BOUNDARY_SOUTH = floatValue
    global BOUNDARY_EAST
    if 'BOUNDARY_EAST' in paramDict:
        floatValue = parseFloat('BOUNDARY_EAST', paramDict['BOUNDARY_EAST'])
        if None is not floatValue:
            BOUNDARY_EAST = floatValue
    global BOUNDARY_NORTH
    if 'BOUNDARY_NORTH' in paramDict:
        floatValue = parseFloat('BOUNDARY_NORTH', paramDict['BOUNDARY_NORTH'])
        if None is not floatValue:
            BOUNDARY_NORTH = floatValue
    global ELEV_RASTER_X
    if 'ELEV_RASTER_X' in paramDict:
        intValue = parseInt('ELEV_RASTER_X', paramDict['ELEV_RASTER_X'])
        if None is not intValue:
            ELEV_RASTER_X = intValue
    global ELEV_RASTER_Y
    if 'ELEV_RASTER_Y' in paramDict:
        intValue = parseInt('ELEV_RASTER_Y', paramDict['ELEV_RASTER_Y'])
        if None is not intValue:
            ELEV_RASTER_Y = intValue
    global PREFIX
    if 'PREFIX' in paramDict:
        if None is not paramDict['PREFIX']:
            PREFIX = paramDict['PREFIX']
    global PATH_TO_SCENERY
    if 'PATH_TO_SCENERY' in paramDict:
        if None is not paramDict['PATH_TO_SCENERY']:
            PATH_TO_SCENERY = paramDict['PATH_TO_SCENERY']
    global NO_ELEV
    if 'NO_ELEV' in paramDict:
        NO_ELEV = parseBool(paramDict['NO_ELEV'])
    global CHECK_OVERLAP
    if 'CHECK_OVERLAP' in paramDict:
        CHECK_OVERLAP = parseBool(paramDict['CHECK_OVERLAP'])
    global USE_PKL
    if 'USE_PKL' in paramDict:
        USE_PKL = parseBool(paramDict['USE_PKL'])
    global TILE_SIZE
    if 'TILE_SIZE' in paramDict:
        intValue = parseInt('TILE_SIZE', paramDict['TILE_SIZE'])
        if None is not intValue:
            TILE_SIZE = intValue
    global TOTAL_OBJECTS
    if 'TOTAL_OBJECTS' in paramDict:
        intValue = parseInt('TOTAL_OBJECTS', paramDict['TOTAL_OBJECTS'])
        if None is not intValue:
            TOTAL_OBJECTS = intValue
    global OSM_FILE
    if 'OSM_FILE' in paramDict:
        if None is not paramDict['OSM_FILE']:
            OSM_FILE = paramDict['OSM_FILE']
    global SKIP_LIST
    if 'SKIP_LIST' in paramDict:
        SKIP_LIST = parseList(paramDict['SKIP_LIST'])
    global BUILDING_MIN_HEIGHT
    if 'BUILDING_MIN_HEIGHT' in paramDict:
        floatValue = parseFloat('BUILDING_MIN_HEIGHT', paramDict['BUILDING_MIN_HEIGHT'])
        if None is not floatValue:
            BUILDING_MIN_HEIGHT = floatValue
    global BUILDING_MIN_AREA
    if 'BUILDING_MIN_AREA' in paramDict:
        floatValue = parseFloat('BUILDING_MIN_AREA', paramDict['BUILDING_MIN_AREA'])
        if None is not floatValue:
            BUILDING_MIN_AREA = floatValue
    global BUILDING_REDUCE_THRESHOLD
    if 'BUILDING_REDUCE_THRESHOLD' in paramDict:
        floatValue = parseFloat('BUILDING_REDUCE_THRESHOLD', paramDict['BUILDING_REDUCE_THRESHOLD'])
        if None is not floatValue:
            BUILDING_REDUCE_THRESHOLD = floatValue
    global BUILDING_REDUCE_RATE
    if 'BUILDING_REDUCE_RATE' in paramDict:
        floatValue = parseFloat('BUILDING_REDUCE_RATE', paramDict['BUILDING_REDUCE_RATE'])
        if None is not floatValue:
            BUILDING_REDUCE_RATE = floatValue
    global BUILDING_SIMPLIFY_TOLERANCE
    if 'BUILDING_SIMPLIFY_TOLERANCE' in paramDict:
        floatValue = parseFloat('BUILDING_SIMPLIFY_TOLERANCE', paramDict['BUILDING_SIMPLIFY_TOLERANCE'])
        if None is not floatValue:
            BUILDING_SIMPLIFY_TOLERANCE = floatValue

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

