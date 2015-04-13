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
import platform
import stat
from _io import open


def get_file_name(name, tilename, lon, lat):
    """
    Returns a command file (Extension cmd for windows)
    """
    
    if "nt" in os.name:
        extension =".cmd"
    elif re.search('linux', platform.system().lower()):
        extension = ".sh" 
    else:
        extension = ""
    return name + tilename + extension

def open_file(name):
    return open(calc_tile.root_directory_name((lon, lat)) + os.sep + name, "wb")

def write_to_file( command, file_handle):
    file_handle.write('python %s -f %s/params.ini' % (command, replacement_path) + os.linesep)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles generates a directory structure capable of generating complete tiles of scenery")
    parser.add_argument("-t", "--tile", dest="tilename",
                      help="The name of the tile")
    parser.add_argument("-f", "--properties", dest="properties",
                      help="The name of the property file to be copied")
    parser.add_argument("-o", "--out", dest="out",
                      help="The name of the property file to be generated")
    parser.add_argument(      "--url"  , 
                       help='Address of the api'        ,
                       default="http://overpass-api.de/api/xapi?",
                       choices=["http://jxapi.osm.rambler.ru/xapi/api/0.6/",
                                "http://open.mapquestapi.com/xapi/api/0.6/",
                                "http://jxapi.openstreetmap.org/xapi/api/0.6/",
                                "http://www.overpass-api.de/api/xapi?",] ,
                       type=str, required=False  )

    args = parser.parse_args()

    if(args.tilename is None):
        logging.error("Tilename is required")
        parser.print_usage()
        exit(1)
    if(args.properties is None):
        logging.error("Input properties are required")
        parser.print_usage()
        exit(1)
    if(args.out is None):
        logging.error("Output properties are required")
        parser.print_usage()
        exit(1)
    logging.info('Generating directory structure for %s ', args.tilename)
    matched = re.match("([ew])([0-9]{3})([ns])([0-9]{2})", args.tilename)
    lon = int(matched.group(2))
    lat = int(matched.group(4))
    if(matched.group(1) == 'w'):
        lon *= -1
    if(matched.group(3) == 's'):
        lat *= -1
    if(calc_tile.bucket_span(lat) > 1):
        num_rows = 1
    else:
        num_rows = int(1 / calc_tile.bucket_span(lat))
    # int(1/calc_tile.bucket_span(lat))
    num_cols = 8
    try:
        os.makedirs(calc_tile.root_directory_name((lon, lat)))
    except OSError, e:
        if e.errno != 17:
            logging.exception("Unable to create path to output")
  
    downloadfile = open_file(get_file_name("download_", args.tilename, lon, lat))
    files = []
    utils = [ 'osm2city', 'osm2pylon', 'tools', 'platforms', 'roads', 'piers', 'landuse', ]
    for util in utils :
        files.append((util+'.py',
                      open_file(get_file_name( util+"_", args.tilename, lon, lat)),
                    ))

    #header if necessary 
    if re.search('linux', platform.system().lower()):
        downloadfile.write('#!/bin/bash\n')
        for command in files :
            command[1].write('#!/bin/bash\n')

    for dy in range(0, num_cols):
        for dx in range(0, num_rows):
            index = calc_tile.tile_index((lon, lat), dx, dy)
            path = ("%s%s%s" % (calc_tile.directory_name((lon, lat)), os.sep, index))
            logging.info(path)
            print(path)
            try:
                os.makedirs(path)
            except OSError, e:
                if e.errno != 17:
                    logging.exception("Unable to create path to output")
            #if(path.count('\\')):
            replacement_path = re.sub('\\\\', '/', path) if(path.count('\\')) else path
            
            with open(args.properties, "r") as sources:
                lines = sources.readlines()
            with open(path + os.sep + args.out, "w") as sources:
                replacement = '\\1 "' + replacement_path + '"'
                for line in lines:
                    line = re.sub('^\s*(PREFIX\s*=)(.*)', replacement, line)
                    line = re.sub('^\s*(BOUNDARY_EAST\s*=)(.*)', '\\1 %f' % (calc_tile.get_east_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_WEST\s*=)(.*)', '\\1 %f' % (calc_tile.get_west_lon(lon, lat, dx)), line)
                    line = re.sub('^\s*(BOUNDARY_NORTH\s*=)(.*)', '\\1 %f' % (calc_tile.get_north_lat(lat, dy)), line)
                    line = re.sub('^\s*(BOUNDARY_SOUTH\s*=)(.*)', '\\1 %f' % (calc_tile.get_south_lat(lat, dy)), line)
                    sources.write(line)
            download_command = 'wget -O %s/buildings.osm ' + args.url + 'map?bbox=%f,%f,%f,%f   ' + os.linesep
#            download_command = 'curl --proxy-ntlm -o %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep            
#             download_command = 'wget -O %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep
            
            # wget -O FT_WILLIAM/buildings.osm http://overpass-api.de/api/map?bbox=-5.2,56.8,-5.,56.9
            downloadfile.write(download_command % (replacement_path, calc_tile.get_west_lon(lon, lat, dx), calc_tile.get_south_lat(lat, dy), calc_tile.get_east_lon(lon, lat, dx), calc_tile.get_north_lat(lat, dy)))
            for command in files:
                write_to_file(command[0], command[1])
    for command in files:
        command[1].close()

    # chmod u+x on created scripts for linux
    if re.search('linux', platform.system().lower()):
        for util in utils + ['download',] :
            f=calc_tile.root_directory_name((lon, lat)) + os.sep + get_file_name( util+"_", args.tilename, lon, lat)
            try :
                st=os.stat(f)
                os.chmod( f, st.st_mode | stat.S_IEXEC)
            except :
                print( '[ WARNING ] could not add exec rights to ' + f )
            
    sys.exit(0)