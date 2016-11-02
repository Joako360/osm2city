"""
Created on 25.04.2014

@author: keith.paterson
"""
import argparse
import logging
import os
import re
import stat
import sys
from _io import open

import parameters
import utils.utilities as uu
from utils import calc_tile

OSM_FILE_NAME = "data.osm"


def _get_file_name(name, tile_name):
    """
    Returns a command file (Extension cmd for windows)
    """
    my_os_type = uu.get_os_type()
    if my_os_type is uu.OSType.windows:
        extension = ".cmd"
    elif my_os_type is uu.OSType.linux or my_os_type is uu.OSType.mac:
        extension = ".sh" 
    else:
        extension = ""
    return name + tile_name + extension


def _open_file(name, directory):
    return open(directory + name, "w")


def _write_to_file(the_command, file_handle, python_exec, params_out):
    file_handle.write(python_exec + ' ' + uu.get_osm2city_directory() + os.sep + the_command)
    file_handle.write(' -f ' + params_out)
    if BASH_PARALLEL_PROCESS:
        file_handle.write(' &' + os.linesep + 'parallel_wait $max_parallel_process' + os.linesep)
    else:
        file_handle.write(os.linesep)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles generates a directory structure capable of \
    generating a complete 1 degree lon/lat-areas of scenery")
    parser.add_argument("-t", "--tile", dest="tile_name",
                        help="The name of the lon/lat-area (e.g. e009n47)", required=True)
    parser.add_argument("-f", "--properties", dest="properties",
                        help="The name of the property file to be copied", required=True)
    parser.add_argument("-o", "--out", dest="out",
                        help="The name of the property file to be generated", required=False)
    parser.add_argument("-u", "--url",
                        help='Address of the api to download OSM data on the fly',
                        dest="api_url",
                        default="http://www.overpass-api.de/api/xapi_meta?",
                        choices=["http://www.overpass-api.de/api/xapi_meta?",
                                 "http://overpass.osm.rambler.ru/cgi/xapi_meta?",
                                 "http://api.openstreetmap.fr/xapi?", ],
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
                        required=False)
    parser.add_argument("-d", dest="osmosis_executable",
                        help="Use the OSM data as specified in params.ini and split it with Osmosis \
                        using the specified path to Osmosis",
                        required=False)

    args = parser.parse_args()

    python_exe = "python"
    if args.python_executable:
        python_exe = args.python_executable

    params_out_file_name = "params.ini"
    if args.out:
        params_out_file_name = args.out

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
    except OSError as e:
        if e.errno != 17:
            logging.exception("Unable to create path to output")

    osmosis_command = None
    if args.osmosis_executable:
        osmosis_path = args.osmosis_executable
        osm_xml_based = True  # if False then the input is using pbf formatting
        parameters.read_from_file(args.properties)

        osmosis_command = args.osmosis_executable
        if parameters.OSM_FILE.endswith(".pbf"):
            osmosis_command += ' --read-pbf file="'
        else:
            osmosis_command += ' --read-xml file="'
        sep_pos = args.properties.rfind(os.sep)
        if sep_pos >= 0:
            orig_path = args.properties[:sep_pos + 1]
            osmosis_command += orig_path
        osmosis_command += parameters.OSM_FILE + '"  --bounding-box completeWays=yes '
        osmosis_command += 'top=%f left=%f bottom=%f right=%f --wx file="%s"' + os.linesep

    download_file = _open_file(_get_file_name("download_", args.tile_name), root_dir_name)
    files = []
    utils = ['tools', 'buildings', 'pylons', 'platforms', 'roads', 'piers', ]
    for util in utils:
        files.append((util + '.py',
                      _open_file(_get_file_name(util + "_", args.tile_name), root_dir_name),
                      ))

    # Check if necessary to add parallel processing code
    BASH_PARALLEL_PROCESS = False
    is_linux_or_mac = uu.is_linux_or_mac()
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
            except OSError as e:
                if e.errno != 17:
                    logging.exception("Unable to create path to output")
            replacement_path = re.sub('\\\\', '/', path) if(path.count('\\')) else path
            
            # Manipulate the properties file and write to new destination
            with open(args.properties, "r") as sources:
                lines = sources.readlines()
            with open(path + os.sep + params_out_file_name, "w") as sources:
                replacement = '\\1 "' + replacement_path + '"'
                for line in lines:
                    line = re.sub('^\s*(PREFIX\s*=)(.*)', replacement, line)
                    line = re.sub('^\s*(BOUNDARY_EAST\s*=)(.*)', '\\1 %f' % (calc_tile.get_east_lon(lon, lat, dx)),
                                  line)
                    line = re.sub('^\s*(BOUNDARY_WEST\s*=)(.*)', '\\1 %f' % (calc_tile.get_west_lon(lon, lat, dx)),
                                  line)
                    line = re.sub('^\s*(BOUNDARY_NORTH\s*=)(.*)', '\\1 %f' % (calc_tile.get_north_lat(lat, dy)), line)
                    line = re.sub('^\s*(BOUNDARY_SOUTH\s*=)(.*)', '\\1 %f' % (calc_tile.get_south_lat(lat, dy)), line)
                    line = re.sub('^\s*(OSM_FILE\s*=)(.*)', '\\1 "%s"' % OSM_FILE_NAME, line)
                    sources.write(line)
            if args.new_download:
                download_command = '%s %s%sdownload_tile.py -f %s/params.ini -d "%s"' % (python_exe,
                                                                                         uu.get_osm2city_directory(),
                                                                                         os.sep,
                                                                                         path, OSM_FILE_NAME)
                download_file.write(download_command + os.linesep)
            elif args.osmosis_executable:
                download_file.write(osmosis_command % (calc_tile.get_north_lat(lat, dy),
                                                       calc_tile.get_west_lon(lon, lat, dx),
                                                       calc_tile.get_south_lat(lat, dy),
                                                       calc_tile.get_east_lon(lon, lat, dx),
                                                       replacement_path + os.sep + OSM_FILE_NAME))
            else:
                download_command = 'curl -f --retry 6 --proxy-ntlm -o %s/%s -g %s*[bbox=%f,%f,%f,%f]   '
                if BASH_PARALLEL_PROCESS:
                    download_command += '&' + os.linesep + 'parallel_wait $max_parallel_process' + os.linesep
                else:
                    download_command += os.linesep

                download_file.write(download_command % (replacement_path, OSM_FILE_NAME, args.api_url,
                                                        calc_tile.get_west_lon(lon, lat, dx),
                                                        calc_tile.get_south_lat(lat, dy),
                                                        calc_tile.get_east_lon(lon, lat, dx),
                                                        calc_tile.get_north_lat(lat, dy)))
            for command in files:
                _write_to_file(command[0], command[1], python_exe, replacement_path + os.sep + params_out_file_name)
    for command in files:
        command[1].close()

    # chmod u+x on created scripts for linux
    if is_linux_or_mac:
        for util in utils + ['download', ]:
            f = calc_tile.root_directory_name((lon, lat)) + os.sep + _get_file_name(util + "_", args.tile_name)
            try:
                st = os.stat(f)
                os.chmod(f, st.st_mode | stat.S_IEXEC)
            except OSError:
                logging.warning('[ WARNING ] could not add exec rights to ' + f)
            
    sys.exit(0)
