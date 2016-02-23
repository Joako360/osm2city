# -*- coding: utf-8 -*-
""" Copies texture related data in directory 'tex' into the scenery folders.
"""

import argparse
import logging
import os
import shutil
import sys

import parameters
import tools


def main():
    scenery_path = parameters.get_output_path()

    scenery_path += os.sep + "Objects"
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

        if len(level_two_dirs) == 0:
            logging.error("The scenery path does not seem to have necessary sub-directories in %s", scenery_path)
            sys.exit(1)
        else:
            orig_tex_dir = tools.get_osm2city_directory() + os.sep + "tex"
            tex_content_list = os.listdir(orig_tex_dir)
            if not os.path.exists(orig_tex_dir):
                logging.error("The original tex dir seems to be missing: %s", orig_tex_dir)
                sys.exit(1)
            for level_two_dir in level_two_dirs:
                tex_dir = level_two_dir + os.sep + "tex"
                if not os.path.exists(tex_dir):
                    os.mkdir(tex_dir)
                logging.info("Copying texture stuff to sub-directory %s", tex_dir)
                for content in tex_content_list:
                    shutil.copy(orig_tex_dir + os.sep + content, tex_dir)
    else:
        logging.error("The scenery path must include a directory 'Objects' like %s", scenery_path)
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Copies texture related data in directory 'tex' into the scenery folders.")
    parser.add_argument("-f", "--file", dest="filename",
                        help="Mandatory: read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-o", dest="o", action="store_true", help="do not overwrite existing elevation data")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    else:
        logging.error("The filename argument is mandatory")
        sys.exit(1)

    main()
