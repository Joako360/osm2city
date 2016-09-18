"""
Created on 10.05.2014

@author: keith.paterson
"""

import argparse
import logging
import os
import sys

import utils.utilities as util


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="prepare_elev will set some properties and copy the elev.nas")
    parser.add_argument("-fg", "--fg_root", dest="fg_root",
                        help="$FG_ROOT see http://wiki.flightgear.org/$FG_ROOT. \
                        Typically '.../data' or '.../fgdata'."
                        , required=True)
    args = parser.parse_args()

    if args.fg_root is not None:
        nasalDir = os.path.abspath(args.fg_root) + os.sep + "Nasal"
        if not os.path.exists(nasalDir):
            logging.error("Directory not found %s", nasalDir)
            sys.exit(1)

        fg_home_path = util.get_fg_home()
        if fg_home_path is None:
            logging.error("Operating system unknown and therefore FGHome unknown.")
            os._exit(1)
        with open(util.get_original_elev_nas_path(), "r") as sources:
            lines = sources.readlines()
        with open(nasalDir + os.sep + "elev.nas", "w") as sources:
            for line in lines:
                if "var in " in line:
                    line = '  var in = "' + util.get_elev_in_path(fg_home_path) + '";\n'
                if "var out" in line:
                    line = '  var out = "' + util.get_elev_out_dir(fg_home_path) + '";\n'
                sources.write(line)
        logging.info('Successfully installed elev.nas')
