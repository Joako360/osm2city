"""
Created on 25.04.2014

@author: keith.paterson
"""
import argparse
import logging
import sys
import re
import os
import stat
from _io import open

import calc_tile
import setup


def _get_file_name(name, tile_name):
    """
    Returns a command file (Extension cmd for windows)
    """
    my_os_type = setup.get_os_type()
    if my_os_type is setup.OSType.windows:
        extension = ".cmd"
    elif my_os_type is setup.OSType.linux or my_os_type is setup.OSType.mac:
        extension = ".sh" 
    else:
        extension = ""
    return name + tile_name + extension


def _open_file(name, directory):
    return open(directory + name, "wb")


def _write_to_file(command, file_handle, python_exe):
    file_handle.write(python_exe + ' ' + command + ' -f ' + replacement_path + '/params.ini ')
    if BASH_PARALLEL_PROCESS:
        file_handle.write('&' + os.linesep + 'parallel_wait $max_parallel_processus' + os.linesep)
    else:
        file_handle.write(os.linesep)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles generates a directory structure capable of generating a complete 1 degree lon/lat-areas of scenery")
    parser.add_argument("-t", "--tile", dest="tile_name",
                        help="The name of the lon/lat-area (e.g. e009n47)", required=True)
    parser.add_argument("-f", "--properties", dest="properties",
                        help="The name of the property file to be copied", required=True)
    parser.add_argument("-o", "--out", dest="out",
                        help="The name of the property file to be generated", required=True)
    parser.add_argument("-u", "--url",
                        help='Address of the api',
                        default="http://overpass-api.de/api/xapi?",
                        choices=["http://jxapi.osm.rambler.ru/xapi/api/0.6/",
                                 "http://open.mapquestapi.com/xapi/api/0.6/",
                                 "http://jxapi.openstreetmap.org/xapi/api/0.6/",
                                 "http://www.overpass-api.de/api/xapi?", ],
                        type=str, required=False)
    parser.add_argument("-p",  "--parallel", dest="parallel",
                        help="Force generated script to include parallel processing handling",
                        action='store_true',
                        default=False,
                        required=False)
    parser.add_argument("-n", dest="new_download",
                        help="New download",
                        action='store_true',
                        default=False,
                        required=False)
    parser.add_argument("-x", dest="python_executable",
                        help="Path to specific Python executable",
                        default=False,
                        required=False)

    args = parser.parse_args()

    python_exe = "python"
    if args.python_executable:
        python_exe = args.python_executable

    logging.info('Generating directory structure for %s ', args.tile_name)
    matched = re.match("([ew])([0-9]{3})([ns])([0-9]{2})", args.tile_name)
    lon = int(matched.group(2))
    lat = int(matched.group(4))
    if matched.group(1) == 'w':
        lon *= -1
    if matched.group(3) == 's':
        lat *= -1
    if calc_tile.bucket_span(lat) > 1:
        num_rows = 1
    else:
        num_rows = int(1 / calc_tile.bucket_span(lat))
    num_cols = 8

    root_dir_name = calc_tile.root_directory_name((lon, lat))

    try:
        os.makedirs(root_dir_name)
    except OSError, e:
        if e.errno != 17:
            logging.exception("Unable to create path to output")
  
    download_file = _open_file(_get_file_name("download_", args.tile_name), root_dir_name)
    files = []
    utils = ['tools', 'osm2city', 'osm2pylon', 'platforms', 'roads', 'piers', ]
    for util in utils:
        files.append((util + '.py',
                      _open_file(_get_file_name(util + "_", args.tile_name), root_dir_name),
                      ))

    # Check if necessary to add parallel processing code
    BASH_PARALLEL_PROCESS = False
    is_linux_or_mac = setup.is_linux_or_mac()
    if args.parallel:
        if is_linux_or_mac:
            BASH_PARALLEL_PROCESS = True
        
    # Header for bash if necessary
    if is_linux_or_mac:
        header_bash = '''#!/bin/bash''' + os.linesep
        if BASH_PARALLEL_PROCESS:
            header_bash += '''#
max_parallel_process=1
if [ $# -gt 0 ] 
then
    if echo $1 | grep -q "^[1-9][0-9]*$"
    then
        max_parallel_process=$1 
    fi
fi
#
function parallel_wait(){
while [ $( LC_ALL=C jobs | grep -v -e Done | wc -l) -ge $max_parallel_process ]
do
    sleep 1
done
}
'''
        download_file.write(header_bash)
        for command in files:
            command[1].write(header_bash)

    for dy in range(0, num_cols):
        for dx in range(0, num_rows):
            index = calc_tile.tile_index((lon, lat), dx, dy)
            path = ("%s%s%s" % (calc_tile.directory_name((lon, lat)), os.sep, index))
            logging.info("Writing to : %s" % path)
            try:
                os.makedirs(path)
            except OSError, e:
                if e.errno != 17:
                    logging.exception("Unable to create path to output")
            #if(path.count('\\')):
            replacement_path = re.sub('\\\\', '/', path) if(path.count('\\')) else path
            
            #Manipulate the properties file and write to new destination
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
#            download_command = 'wget -O %s/buildings.osm ' + args.url + 'map?bbox=%f,%f,%f,%f   '
            if args.new_download:
                download_command = '%s download_tile.py -f %s/params.ini' % (python_exe, path)
                download_file.write(download_command + os.linesep)
            else:
                download_command = 'curl -f --retry 6 --proxy-ntlm -o %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep                        
                if BASH_PARALLEL_PROCESS:
                    download_command += '&' + os.linesep + 'parallel_wait $max_parallel_process' + os.linesep
                else:
                    download_command += os.linesep
    #            download_command = 'curl --proxy-ntlm -o %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep            
    #             download_command = 'wget -O %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f   ' + os.linesep
                
                # wget -O FT_WILLIAM/buildings.osm http://overpass-api.de/api/map?bbox=-5.2,56.8,-5.,56.9
                download_file.write(download_command % (replacement_path, calc_tile.get_west_lon(lon, lat, dx), calc_tile.get_south_lat(lat, dy), calc_tile.get_east_lon(lon, lat, dx), calc_tile.get_north_lat(lat, dy)))
            for command in files:
                _write_to_file(command[0], command[1], python_exe)
    for command in files:
        command[1].close()

    # chmod u+x on created scripts for linux
    if is_linux_or_mac:
        for util in utils + ['download', ]:
            f = calc_tile.root_directory_name((lon, lat)) + os.sep + _get_file_name(util + "_", args.tile_name)
            try:
                st = os.stat(f)
                os.chmod(f, st.st_mode | stat.S_IEXEC)
            except:
                print('[ WARNING ] could not add exec rights to ' + f)
            
    sys.exit(0)
