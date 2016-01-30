"""
Created on 10.05.2014

@author: keith.paterson
"""

import argparse
import logging
import os
import os.path as osp
import sys


def getFGHome():
    """Constructs the path to FGHome.

    See also http://wiki.flightgear.org/$FG_HOME
    If the operating system cannot be determined the function returns None.
    Otherwise a platform specific path.
    """
    home_dir = osp.expanduser("~")
    if sys.platform.startswith("win"):
        home = os.getenv("APPDATA", "APPDATA_NOT_FOUND") + os.sep + "flightgear.org" + os.sep
        return home.replace("\\", "/")
    elif sys.platform.startswith("linux"):
        return home_dir + "/.fgfs/"
    elif sys.platform.startswith("darwin"):
        return home_dir + "/Library/Application Support/FlightGear/"
    else:
        return None


def get_elev_in_path(home_path):
    return home_path + "elev.in"


def get_elev_out_dir(home_path):
    return home_path + "Export/"


def get_elev_out_path(home_path):
    return get_elev_out_dir(home_path) + "elev.out"


def _get_original_elev_nas_path():
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]
    return my_dir + os.sep + "elev.nas"


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Setup will set some properties and copy the elev.nas")
    parser.add_argument("-fg", "--fg_root", dest="fg_root",
                        help="$FG_ROOT see http://wiki.flightgear.org/$FG_ROOT. \
                        Typically '.../data' or '.../fgdata'.")
    args = parser.parse_args()

    if args.fg_root is not None:
        nasalDir = os.path.abspath(args.fg_root) + os.sep + "Nasal"
        if not os.path.exists(nasalDir):
            logging.error("Directory not found %s", nasalDir)
            os._exit(1)  # FIXME: why is os._exit(1) used instead of sys.exit(1)? Better handling in batch processing?

        fg_home_path = getFGHome()
        if fg_home_path is None:
            logging.error("Operating system unknown and therefore FGHome unknown.")
            os._exit(1)
        with open(_get_original_elev_nas_path(), "r") as sources:
            lines = sources.readlines()
        with open(nasalDir + os.sep + "elev.nas", "w") as sources:
            for line in lines:
                if "var in" in line:
                    line = '  var in = "' + get_elev_in_path(fg_home_path) + '";\n'
                if "var out" in line:
                    line = '  var out = "' + get_elev_out_dir(fg_home_path) + '";\n'
                sources.write(line)
        logging.info('Successfully installed elev.nas')
