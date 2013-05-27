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
