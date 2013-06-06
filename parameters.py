# -*- coding: utf-8 -*-
'''
Created on May 27, 2013

@author: vanosten
'''

import sys
import types

class Parameters(object):
    '''
    Central place to store parameters / settings / variables in osm2city.
    All lenght, height etc. parameters are in meters, square meters (m2) etc.
    '''

    def __init__(self):
        '''
        Constructor. For the time being replace the default values with your own before running the modules in osm2city.
        '''
        # The boundary of the scenery in degrees (use "." not ","). The example below is from LSZR.
        self.boundary_west = 9.54
        self.boundary_south = 47.48
        self.boundary_east = 9.58
        self.boundary_north = 47.50
        
        # The distance between raster points for the derived elevation map (x is horizontal, y is vertical)
        self.elev_raster_x = 10
        self.elev_raster_y = 10
        
        # The scenery folder (typically a geographic name or the ICAO code of the airport
        self.prefix = "LSZR"
        self.path_to_scenery = "/home/vanosten/bin/fgfs_scenery/customscenery/LSZR" # the full path to the scenery folder without trailing slash. Last folder should be equal to prefix
        
        self.no_elev = False # -- skip elevation interpolation
        self.check_overlap = False # -- check for overlap with static models. The scenery folder needs to contain a "Objects" folder
        self.use_pkl = False # -- read from already existing converted OSM building data in file system for faster load
        self.tile_size = 1000 # -- the tile size in meters for clustering of buildings
        self.total_objects = 50000 # the maximum number of buildings to read from osm data
        self.osmfile = "lszr.osm" # -- the file name of the file with osm data. Should reside in path_to_scenery
        
        self.skiplist = ["Dresden Hauptbahnhof", "Semperoper", "Zwinger", "Hofkirche",
          "Frauenkirche", "Coselpalais", "Palais im Großen Garten",
          "Residenzschloss Dresden", "Fernsehturm", "Fernsehturm Dresden"] # the buildings in OSM to skip
        
        # Parameters which influence the number of buildings from OSM taken to output
        self.building_min_height = 3.4 # The minimum height of a building to be included in output
        self.building_min_area = 50.0 # The minimum area for a building to be included in output
        self.building_reduce_threshhold = 200.0 # The threshold area of a building below which a rate of buildings get reduced from output
        self.building_reduce_rate = 0.5 # The rate (between 0 and 1) of buildings below a threshold which get reduced randomly in output
        self.building_simplify_tolerance = 1.0 # All points in the simplified building will be within the tolerance distance of the original geometry. 

    def printParams(self):
        '''
        Prints all parameters as key = value
        '''
        print '--- Using the following parameters: ---'
        for k in sorted(self.__dict__.iterkeys()):
            if isinstance(self.__dict__[k], types.ListType):
                value = ', '.join(self.__dict__[k])
                print k, '=', value
            else:
                print k, '=', self.__dict__[k]
        print '------'

    def setParameters(self, paramDict):
        '''
        Sets the parameter values from a dictionary read by function readFromFile.
        If a parameter is not in the dictionary or cannot be parsed, then a default is chosen.
        '''
        if 'boundary_west' in paramDict:
            floatValue = parseFloat('boundary_west', paramDict['boundary_west'])
            if None is not floatValue:
                self.boundary_west = floatValue
        if 'boundary_south' in paramDict:
            floatValue = parseFloat('boundary_south', paramDict['boundary_south'])
            if None is not floatValue:
                self.boundary_south = floatValue
        if 'boundary_east' in paramDict:
            floatValue = parseFloat('boundary_east', paramDict['boundary_east'])
            if None is not floatValue:
                self.boundary_east = floatValue
        if 'boundary_north' in paramDict:
            floatValue = parseFloat('boundary_north', paramDict['boundary_north'])
            if None is not floatValue:
                self.boundary_north = floatValue
        if 'elev_raster_x' in paramDict:
            intValue = parseInt('elev_raster_x', paramDict['elev_raster_x'])
            if None is not intValue:
                self.elev_raster_x = intValue
        if 'elev_raster_y' in paramDict:
            intValue = parseInt('elev_raster_y', paramDict['elev_raster_y'])
            if None is not intValue:
                self.elev_raster_y = intValue
        if 'prefix' in paramDict:
            if None is not paramDict['prefix']:
                self.prefix = paramDict['prefix']
        if 'path_to_scenery' in paramDict:
            if None is not paramDict['path_to_scenery']:
                self.path_to_scenery = paramDict['path_to_scenery']
        if 'no_elev' in paramDict:
            self.no_elev = parseBool(paramDict['no_elev'])
        if 'check_overlap' in paramDict:
            self.check_overlap = parseBool(paramDict['check_overlap'])
        if 'use_pkl' in paramDict:
            self.use_pkl = parseBool(paramDict['use_pkl'])
        if 'tile_size' in paramDict:
            intValue = parseInt('tile_size', paramDict['tile_size'])
            if None is not intValue:
                self.tile_size = intValue
        if 'total_objects' in paramDict:
            intValue = parseInt('total_objects', paramDict['total_objects'])
            if None is not intValue:
                self.total_objects = intValue
        if 'osmfile' in paramDict:
            if None is not paramDict['osmfile']:
                self.osmfile = paramDict['osmfile']
        if 'skiplist' in paramDict:
            self.skiplist = parseList(paramDict['skiplist'])
        if 'building_min_height' in paramDict:
            floatValue = parseFloat('building_min_height', paramDict['building_min_height'])
            if None is not floatValue:
                self.building_min_height = floatValue
        if 'building_min_area' in paramDict:
            floatValue = parseFloat('building_min_area', paramDict['building_min_area'])
            if None is not floatValue:
                self.building_min_area = floatValue
        if 'building_reduce_threshhold' in paramDict:
            floatValue = parseFloat('building_reduce_threshhold', paramDict['building_reduce_threshhold'])
            if None is not floatValue:
                self.building_reduce_threshhold = floatValue
        if 'building_reduce_rate' in paramDict:
            floatValue = parseFloat('building_reduce_rate', paramDict['building_reduce_rate'])
            if None is not floatValue:
                self.building_reduce_rate = floatValue
        if 'building_simplify_tolerance' in paramDict:
            floatValue = parseFloat('building_simplify_tolerance', paramDict['building_simplify_tolerance'])
            if None is not floatValue:
                self.building_simplify_tolerance = floatValue

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
    params = Parameters()
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
        params.setParameters(paramDict)
        file_object.close()
    except IOError, reason:
        print "Error processing file with parameters:", reason
        sys.exit(1)
    return params

