'''
'Tool to download inclusive backing off when receiving 429
'''
import argparse
import logging
import os
import re
from subprocess import STDOUT, PIPE
import subprocess
from time import sleep

import parameters


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Downloads a tile from osm. It handles too many requests and backs off")
    parser.add_argument("-f", "--properties", dest="properties",
                        help="The name of the property file to be copied", required=True)
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL")
    args = parser.parse_args()

    if args.properties is not None:
        parameters.read_from_file(args.properties)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    
    for x in range(0, 10):
        download_command = 'curl -w %s -f --proxy-ntlm -o %s/buildings.osm http://overpass-api.de/api/map?bbox=%f,%f,%f,%f'
        path = '%s/buildings.osm' % parameters.PREFIX            
        url = 'http://overpass-api.de/api/map?bbox=%f,%f,%f,%f' % (parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH, parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    #     if parameters.BASH_PARALLEL_PROCESS :
    #         download_command += '&' + os.linesep + 'parallel_wait $max_parallel_process' + os.linesep
    #     else :
    #         download_command += os.linesep
    #     print download_command % (parameters.PREFIX, parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH, parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
        logging.info("Downloading %s"%parameters.PREFIX)
        tries = 0
        download_command = download_command % ("CODE:%{http_code}:", parameters.PREFIX, parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH, parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)    
        while tries < 10:    
            proc = subprocess.Popen(download_command, stderr=PIPE, stdout=PIPE,bufsize=1, universal_newlines=True)
        #     exitcode = proc.wait()
            outlines = ""
            with proc.stderr:
                for line in iter(proc.stderr.readline, b''):
                    print line.strip()
                    outlines += line
# Already read stderr setting to None lets us get stdout
            proc.stderr = None
            output = proc.communicate()[0]
            exitcode = proc.wait() # wait for the subprocess to exit            http_code = re.search("CODE:([0-9]*):", outs).group(1)
            http_code = re.search("CODE:([0-9]*):", output).group(1)

            logging.info("Received %s" % (http_code))
            if http_code != "429":
                if http_code == "200":
                    logging.info("Downloaded sucessfully %s" % (http_code))
                    exit(0)
                else:
                    logging.error("Non repeatable http_code %s" % (http_code))
                    exit(http_code) 
            tries += 1
            wait = 60 * tries
            logging.info("Received too many requests retrying in %d s %d" % (wait, tries))
            sleep(wait)
        logging.info("Too many requests failing with %s" % (http_code))
        exit(http_code)
        #     exitcode = os.spawnv(os.P_WAIT,'curl', ['-f', '--proxy-ntlm', '-o', path, url])
    #     print exitcode
