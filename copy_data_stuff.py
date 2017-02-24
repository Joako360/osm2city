# -*- coding: utf-8 -*-
""" Copies texture related data in directory 'tex' into the scenery folders.
"""

import argparse
from distutils.dir_util import copy_tree
import logging
import os
import shutil
import sys

import parameters
import utils.utilities as util


def process(copy_fg_data: bool, scenery_type: str) -> None:
    scenery_path = parameters.get_output_path()

    scenery_path += os.sep + scenery_type
    if os.path.exists(scenery_path):
        level_one_dirs = os.listdir(scenery_path)
        level_two_dirs = list()
        for level_one_dir in level_one_dirs:
            sub_dir_path = scenery_path + os.sep + level_one_dir
            if os.path.isdir(sub_dir_path):
                level_two_dir_list = os.listdir(sub_dir_path)
                for level_two_dir in level_two_dir_list:
                    if os.path.isdir(sub_dir_path + os.sep + level_two_dir):
                        level_two_dirs.append(sub_dir_path + os.sep + level_two_dir)

        if not level_two_dirs:
            logging.info("ERROR: The scenery path does not seem to have necessary sub-directories in %s", scenery_path)
        else:
            data_dir = util.assert_trailing_slash(parameters.PATH_TO_OSM2CITY_DATA)
            # textures
            source_dir = data_dir + "tex"
            content_list = os.listdir(source_dir)
            if not os.path.exists(source_dir):
                logging.error("The original tex dir seems to be missing: %s", source_dir)
                sys.exit(1)
            for level_two_dir in level_two_dirs:
                tex_dir = level_two_dir + os.sep + "tex"
                if not os.path.exists(tex_dir):
                    os.mkdir(tex_dir)
                logging.info("Copying texture stuff to sub-directory %s", tex_dir)
                for content in content_list:
                    shutil.copy(source_dir + os.sep + content, tex_dir)
            # light-map effects
            source_dir = data_dir + "lightmap"
            if not os.path.exists(source_dir):
                logging.error("The original lightmap dir seems to be missing: %s", source_dir)
                sys.exit(1)
            for level_two_dir in level_two_dirs:
                logging.info("Copying lightmap stuff directory %s", level_two_dir)
                content_list = os.listdir(source_dir)
                for content in content_list:
                    shutil.copy(source_dir + os.sep + content, level_two_dir)

            if copy_fg_data:
                fg_root_dir = util.get_fg_root()
                logging.info("Copying fgdata directory into $FG_ROOT (%s)", fg_root_dir)
                source_dir = data_dir + "fgdata"
                copy_tree(source_dir, fg_root_dir)

    else:
        logging.info("ERROR: The scenery path must include a directory '%s' - maybe no objects written",
                     scenery_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Copies texture and effects related data in directory 'tex' \
    into the scenery folders.")
    parser.add_argument("-f", "--file", dest="filename",
                        help="Mandatory: read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-t", "--type", dest="scenery_type",
                        help="Mandatory: Scenery type - typically 'Buildings', 'Roads', 'Pylons'",
                        metavar="STRING", required=True)
    parser.add_argument("-a", action="store_true",
                        help="also copy effects etc. in fgdata to $FG_ROOT", required=False)
    args = parser.parse_args()

    parameters.read_from_file(args.filename)

    process(args.a, args.scenery_type)
