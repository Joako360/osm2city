# -*- coding: utf-8 -*-
'''
Created on May 27, 2013

@author: vanosten
'''

class Parameters(object):
    '''
    Central place to store parameters / settings / variables in osm2city.
    TODO: load from file and write to file
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


