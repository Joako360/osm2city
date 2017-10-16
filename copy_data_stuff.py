"""
Copies texture related data in directory 'tex' into the scenery folders.
"""

from distutils.dir_util import copy_tree
import logging
import os
import shutil
import sys
import textwrap

import parameters
import utils.utilities as util
import utils.stg_io2 as stg


def _write_roads_eff(path_to_dir: str) -> None:
    eff = open(os.path.join(path_to_dir, 'roads.eff'), 'w')
    eff.write(textwrap.dedent("""<?xml version="1.0" encoding="utf-8"?>
<PropertyList>
        <name>roadsLM</name>
        <inherits-from>Effects/road</inherits-from>
        <parameters>
                <!-- Light Map -->
                <lightmap-enabled type="int">1</lightmap-enabled>
                <lightmap-multi type="int">0</lightmap-multi>
                <lightmap-color type="vec3d" n="0"> 0.941 0.682 0.086 </lightmap-color>
                <texture n="3">
                    <image>tex/roads_LM.png</image>
                    <wrap-s>repeat</wrap-s>
                    <wrap-t>repeat</wrap-t>
                </texture>
        </parameters>
</PropertyList>
    """))


def _write_citylm_eff(path_to_dir: str) -> None:
    eff = open(os.path.join(path_to_dir, 'cityLM.eff'), 'w')
    eff.write(textwrap.dedent("""<?xml version="1.0" encoding="utf-8"?>
<PropertyList>
        <name>cityLM</name>
        <inherits-from>/Effects/model-combined-deferred</inherits-from>
        <parameters>
                <!-- Light Map -->
                <lightmap-enabled type="int">1</lightmap-enabled>
                <lightmap-multi type="int">1</lightmap-multi>
                <texture n="3">
                  <image>tex/atlas_facades_LM.png</image>
                  <wrap-s>repeat</wrap-s>
                  <wrap-t>repeat</wrap-t>
                </texture>
                <lightmap-factor type="float" n="0"><use>/environment/lightmap-factor</use></lightmap-factor>
                <lightmap-color type="vec3d" n="0"> 1. 0.88 0.6 </lightmap-color>
                <lightmap-factor type="float" n="1"><use>/environment/lightmap-factor</use></lightmap-factor>
                <lightmap-color type="vec3d" n="1"> 0.564 0.409 0.172 </lightmap-color>
                <lightmap-factor type="float" n="2">0</lightmap-factor>
                <lightmap-factor type="float" n="3">0</lightmap-factor>
        </parameters>
</PropertyList>
    """))


def process(scenery_type: stg.SceneryType) -> None:
    if parameters.FLAG_2017_2:
        logging.info('Nothing to do for 2017.2 and onwards')
        return

    scenery_path = os.path.join(parameters.get_output_path(), stg.scenery_directory_name(scenery_type))

    if os.path.exists(scenery_path):
        level_one_dirs = os.listdir(scenery_path)
        level_two_dirs = list()
        for level_one_dir in level_one_dirs:
            sub_dir_path = os.path.join(scenery_path, level_one_dir)
            if os.path.isdir(sub_dir_path):
                level_two_dir_list = os.listdir(sub_dir_path)
                for level_two_dir in level_two_dir_list:
                    if os.path.isdir(os.path.join(sub_dir_path, level_two_dir)):
                        level_two_dirs.append(os.path.join(sub_dir_path, level_two_dir))

        if not level_two_dirs:
            logging.info("ERROR: The scenery path does not seem to have necessary sub-directories in %s", scenery_path)
        else:
            # textures
            source_dir = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, "tex")
            content_list = os.listdir(source_dir)
            if not os.path.exists(source_dir):
                logging.error("The original tex dir seems to be missing: %s", source_dir)
                sys.exit(1)
            for level_two_dir in level_two_dirs:
                if scenery_type in [stg.SceneryType.roads, stg.SceneryType.buildings]:
                    tex_dir = os.path.join(level_two_dir, "tex")
                    if not os.path.exists(tex_dir):
                        os.mkdir(tex_dir)
                    logging.info("Copying texture stuff to sub-directory %s", tex_dir)
                    for content in content_list:
                        if scenery_type is stg.SceneryType.roads and content.startswith('road') \
                                and content.endswith('.png'):
                            shutil.copy(os.path.join(source_dir, content), tex_dir)
                        if scenery_type is stg.SceneryType.buildings and content.startswith('atlas') \
                                and content.endswith('.png'):
                            shutil.copy(os.path.join(source_dir, content), tex_dir)

            # light-map effects
            if scenery_type in [stg.SceneryType.roads, stg.SceneryType.buildings]:
                source_dir = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, "lightmap")
                if not os.path.exists(source_dir):
                    logging.error("The original lightmap dir seems to be missing: %s", source_dir)
                    sys.exit(1)
                for level_two_dir in level_two_dirs:
                    logging.info("Copying lightmap stuff directory %s", level_two_dir)
                    content_list = os.listdir(source_dir)
                    for content in content_list:
                        shutil.copy(os.path.join(source_dir, content), level_two_dir)

                if parameters.TRAFFIC_SHADER_ENABLE:
                    fg_root_dir = util.get_fg_root()
                    logging.info("Copying fgdata directory into $FG_ROOT (%s)", fg_root_dir)
                    source_dir = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, "fgdata")
                    copy_tree(source_dir, fg_root_dir)

    else:
        logging.info("ERROR: The scenery path must include a directory '%s' - maybe no objects written",
                     scenery_path)
