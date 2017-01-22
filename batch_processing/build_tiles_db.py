import argparse
import logging
import parameters
import sys
from typing import List, Optional
import unittest


def parse_boundary(boundary_string: str) -> Optional[List[float]]:
    boundary_parts = boundary_string.split("_")
    if len(boundary_parts) != 4:
        logging.error("Boundary must have four elements separated by '_': {} has only {} element(s) \
        -> aborting!".format(args.boundary, len(boundary_parts)))
        return None

    boundary_float_list = list()
    for i in range(len(boundary_parts)):
        try:
            boundary_float_list[i] = float(boundary_parts[i])
        except ValueError:
            logging.error("Boundary part {} cannot be parsed as float (decimal)".format(boundary_parts[i]))
            return None
    return boundary_float_list


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
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (. as decimal)")

    args = parser.parse_args()

    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    parameters.USE_DATABASE = True  # just to be sure

    boundary_floats = parse_boundary(args.boundary)
    if boundary_floats is None:
        sys.exit(1)


# ================ UNITTESTS =======================

class TestBuildTilesDB(unittest.TestCase):
    def test_parse_boundary(self):
        pass
