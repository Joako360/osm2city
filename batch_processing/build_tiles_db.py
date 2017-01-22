import argparse
import logging
import parameters
import sys

from utils.utilities import BoundaryError, parse_boundary


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="build-tiles DB generates a whole scenery of osm2city objects \
    based on a lon/lat defined area")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel", dest="loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument("-b", "--boundary", dest="boundary",
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (. as decimal)",
                        required=True)

    args = parser.parse_args()

    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    parameters.USE_DATABASE = True  # just to be sure

    try:
        boundary_floats = parse_boundary(args.boundary)
    except BoundaryError as be:
        logging.error(be.message)
        sys.exit(1)
