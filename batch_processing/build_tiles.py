'''
Created on 25.04.2014

@author: keith.paterson
'''
import logging
import argparse
import sys
import calc_tile
import re
import os
from _io import open

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="build-tiles generates a directory structure capable of generating complete tiles of scenery")
    parser.add_argument("-t", "--tile", dest="tilename",
                      help="The name of the tile")
    parser.add_argument("-f", "--properties", dest="properties",
                      help="The name of the property file to be copied")
    args = parser.parse_args()
    
    if( args.tilename is None):
        logging.error("Tilename is required")
        parser.print_usage()
        exit(1)
    if( args.properties is None):
        logging.error("Properties is required")
        parser.print_usage()
        exit(1)
    logging.info( 'Generating directory structure for %s ', args.tilename)
    matched = re.match("([ew])([0-9]{3})([ns])([0-9]{2})", args.tilename)
    lon = int(matched.group(2))
    lat = int(matched.group(4))
    if( matched.group(1) == 'w' ):
        lon *= -1
    if( matched.group(3) == 's' ):
        lat *= -1
    if( calc_tile.bucket_span(lat) > 1):
        num_rows = 1
    else:    
        num_rows = int(1 / calc_tile.bucket_span(lat))
    #int(1/calc_tile.bucket_span(lat))
    num_cols = 8
    try:
        os.makedirs(calc_tile.root_directory_name((lon, lat)))
    except OSError, e:
        if e.errno != 17:
            logging.exception("Unable to create path to output")
    
    if "nt" in os.name:
        download_name = "download_" + args.tilename + ".cmd"
        osm_name = "osm2city_" + args.tilename + ".cmd"
        osm_pylons = "osm2pylon_" + args.tilename + ".cmd"
        tools_name = "tools_" + args.tilename + ".cmd"
    else:
        download_name = "download_" + args.tilename
        osm_name = "osm2city_" + args.tilename
        osm_pylons = "osm2pylon_" + args.tilename
        tools_name = "tools_" + args.tilename
        
    downloadfile = open(calc_tile.root_directory_name((lon, lat)) + os.sep + download_name, "wb") 
    osm2city = open(calc_tile.root_directory_name((lon, lat)) + os.sep + osm_name, "wb")
    osm2pylon = open(calc_tile.root_directory_name((lon, lat)) + os.sep + osm_pylons, "wb")
    tools = open(calc_tile.root_directory_name((lon, lat)) + os.sep + tools_name, "wb") 
    for dy in range(0, num_cols):
        for dx in range(0, num_rows):
            index = calc_tile.tile_index((lon, lat), dx, dy)
            path =("%s%s%s" % (calc_tile.directory_name((lon, lat)), os.sep,  index ) )
            print path
            try:
                os.makedirs(path)
            except OSError, e:
                if e.errno != 17:
                    logging.exception("Unable to create path to output")
            if( path.count('\\') ):
                replacement_path = re.sub('\\\\','/', path)
            with open(args.properties, "r") as sources:
                lines = sources.readlines()
            with open(path + os.sep + args.properties, "w") as sources:
                replacement = '\\1 ' + replacement_path
                for line in lines:
                    line = re.sub('^\s*(PREFIX\s*=)([ A-Za-z0-9]*)', replacement, line)
                    line = re.sub('^\s*(BOUNDARY_EAST\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_east_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_WEST\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_west_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_NORTH\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_north_lat(lat, dy)), line)
                    line = re.sub('^\s*(BOUNDARY_SOUTH\s*=)([ A-Za-z0-9.,]*)', '\\1 %f' % (calc_tile.get_south_lat(lat, dy)), line)
                    sources.write(line)            
            download_command = 'wget -O %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep
            #wget -O FT_WILLIAM/buildings.osm http://overpass-api.de/api/map?bbox=-5.2,56.8,-5.,56.9
            downloadfile.write(download_command%(replacement_path,calc_tile.get_west_lon(lon, lat, dx),calc_tile.get_south_lat(lat, dy),calc_tile.get_east_lon(lon, lat, dx),calc_tile.get_north_lat(lat, dy)))
            osm2city.write('python osm2city.py -f %s/params.ini' % (replacement_path) + os.linesep)
            osm2pylon.write('python osm2pylon.py -f %s/params.ini' % (replacement_path) + os.linesep)
            tools.write('python tools.py -f %s/params.ini' % (replacement_path) + os.linesep)

    sys.exit(0)