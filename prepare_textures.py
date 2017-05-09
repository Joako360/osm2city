# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
# The provides/requires mechanism could be improved. 
# Currently, RoofManager prepends the "provides" tags with the texture class.
# Find_matching will match only if "requires" is a subset of "provides".
# That is, there is no OR. All "requires" must be matched 
#
# ideally:
# Texture(rules='building.height > 15 
#                AND (roof.color = black OR roof.color = grey)
#                AND roof.shape = flat ')


import argparse
import datetime
import logging
import math
import os
import pickle
import sys
from typing import List

import img2np
import numpy as np
import parameters
import utils.utilities as util
from PIL import Image
from textures import atlas
from textures.texture import Texture, RoofManager, FacadeManager

atlas_file_name = None

ROOFS_DEFAULT_FILE_NAME = "roofs_default.py"


def _next_pow2(value):
    return 2**(int(math.log(value) / math.log(2)) + 1)


def _make_texture_atlas(texture_list: List[Texture], atlas_filename: str, ext: str, size_x: int=256, pad_y: int=0,
                        lightmap: bool=False, ambient_occlusion: bool=False):
    """
    Create texture atlas from all textures. Update all our item coordinates.
    """
    logging.info("Making texture atlas")
    
    if len(texture_list) < 1:
        logging.error('Got an empty texture list. Check installation of tex.src/ folder!')
        sys.exit(-1)

    atlas_sx = size_x
    keep_aspect = True  # FIXME: False won't work -- im.thumbnail seems to keep aspect no matter what

    next_y = 0

    # -- load and rotate images, store image data in RoofManager object
    #    append to either can_repeat or non_repeat list
    can_repeat_list = []
    non_repeat_list = []
    for l in texture_list:
        filename = l.filename
        l.im = Image.open(filename)
        logging.debug("name %s size " % filename + str(l.im.size))
        if lightmap:
            filename, file_extension = os.path.splitext(l.filename)
            filename += '_LM' + file_extension
            try:
                l.im_LM = Image.open(filename)
            except IOError:
                l.im_LM = None

        assert (l.v_can_repeat + l.h_can_repeat < 2)
        if l.v_can_repeat:
            l.rotated = True
            l.im = l.im.transpose(Image.ROTATE_270)
            if lightmap:
                l.im_LM = l.im_LM.transpose(Image.ROTATE_270)
        
        if l.v_can_repeat or l.h_can_repeat: 
            can_repeat_list.append(l)
        else:
            non_repeat_list.append(l)

    # FIXME: maybe auto-calc x-size here

    the_atlas = atlas.Atlas(0, 0, atlas_sx, 1e10, 'Facades')

    # Work on not repeatable textures
    # Sort textures by perimeter size in non-increasing order
    non_repeat_list = sorted(non_repeat_list, key=lambda i: i.sy, reverse=True)
    for the_texture in non_repeat_list:
        the_texture.width_px, the_texture.height_px = the_texture.im.size

        if not the_atlas.pack(the_texture):
            logging.info("Failed to pack" + str(the_texture))
    atlas_sy = the_atlas.cur_height()

    # Work on repeatable textures.
    # Scale each to full atlas width
    # Compute total height of repeatable section
    for l in can_repeat_list:
        scale_x = 1. * atlas_sx / l.im.size[0]
        if keep_aspect:
            scale_y = scale_x
        else:
            scale_y = 1.
        org_size = l.im.size
        
        nx = int(org_size[0] * scale_x)
        ny = int(org_size[1] * scale_y)
        l.im = l.im.resize((nx, ny), Image.ANTIALIAS)
        if lightmap and l.im_LM:
            l.im_LM = l.im_LM.resize((nx, ny), Image.ANTIALIAS)
        logging.debug("scale:" + str(org_size) + str(l.im.size))
        atlas_sy += l.im.size[1] + pad_y
        l.width_px, l.height_px = l.im.size

    # Bake fake ambient occlusion. Multiply all channels of a facade texture by
    # 1. - parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE * np.exp(-z / parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT)
    #    where z is height above ground. 
    if ambient_occlusion:
        for l in texture_list:
            if l.cls == 'facade':
                R, G, B, A = img2np.img2RGBA(l.im)
                height_px = R.shape[0]
                # reversed height
                Z = np.linspace(l.v_size_meters, 0, height_px).reshape(height_px, 1)
                fac = 1. - parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE * np.exp(-Z / parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT)
                l.im = img2np.RGBA2img(R * fac, G * fac, B * fac)

    # -- paste, compute atlas coords
    #    lower left corner of texture is x0, y0
    for l in can_repeat_list:
        l.x0 = 0
        l.x1 = float(l.width_px) / atlas_sx
        l.y1 = 1 - float(next_y) / atlas_sy
        l.y0 = 1 - float(next_y + l.height_px) / atlas_sy
        l.sy = float(l.height_px) / atlas_sy
        l.sx = 1.

        next_y += l.height_px + pad_y
        if not the_atlas.pack(l):
            logging.info("Failed to pack" + str(l))

    atlas_sy = _next_pow2(atlas_sy)
    the_atlas.set_height(atlas_sy)
    logging.info("Final atlas height %i" % atlas_sy)

    the_atlas.write(atlas_filename + ext, 'im')

    # -- create LM atlas, using the coordinates of the main atlas
    if lightmap:
        light_map_atlas = atlas.Atlas(0, 0, atlas_sx, the_atlas.height_px, 'FacadesLM')
        for l in texture_list:
            light_map_atlas.pack_at(l, l.ax, l.ay)
        light_map_atlas.write(atlas_filename + '_LM' + ext, 'im_LM')

    for l in texture_list:
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (l.filename, l.x0, l.y0, l.x1, l.y1))
        del l.im
        if lightmap:
            del l.im_LM


def _check_missed_input_textures(tex_prefix: str, registered_textures: List[Texture]) -> None:
    """Find all .jpg and .png files in tex.src and compare with registered textures.

    If not found in registered textures, then log a warning"""
    for subdir, dirs, files in os.walk(tex_prefix, topdown=True):
        for filename in files:
            if filename[-4:] in [".jpg", ".png"]:
                if filename[-7:-4] in ["_LM", "_MA"]:
                    continue
                my_path = os.path.join(subdir, filename)
                found = False
                for registered in registered_textures:
                    if registered.filename == my_path:
                        found = True
                        break
                if not found:
                    logging.warning("Texture %s has not been registered", my_path)


def _append_dynamic(facade_manager: FacadeManager, tex_prefix: str) -> None:
    """Dynamically runs .py files in tex.src and sub-directories to add facades.

    For roofs see add_roofs(roofs)"""
    for subdir, dirs, files in os.walk(tex_prefix, topdown=True):
        for filename in files:
            if filename[-2:] != "py":
                continue
            elif filename == ROOFS_DEFAULT_FILE_NAME:
                continue

            my_path = os.path.join(subdir, filename)
            logging.info("Executing %s ", my_path)
            try:
                facade_manager.current_registered_in = my_path
                exec(compile(open(my_path).read(), my_path, 'exec'))
            except:
                logging.exception("Error while running %s" % filename)


def _append_roofs(roof_manager: RoofManager, tex_prefix: str) -> None:
    """Dynamically runs the content of a hard-coded file to fill the roofs texture list.

    Argument roof_manager is used dynamically in execfile
    ."""
    try:
        file_name = os.path.join(tex_prefix, ROOFS_DEFAULT_FILE_NAME)
        roof_manager.current_registered_in = file_name
        exec(compile(open(file_name).read(), file_name, 'exec'))
    except Exception as e:
        logging.exception("Unrecoverable error while loading roofs", e)
        sys.exit(1)


def _dump_all_provides_across_textures(texture_list: List[Texture]) -> None:
    provided_features_level_one = set()
    provided_features_level_two = set()
    provided_features_level_three = set()
    provided_features_level_four = set()

    for texture in texture_list:
        for feature in texture.provides:
            parts = feature.split(":")
            if parts:
                provided_features_level_one.add(parts[0])
            if len(parts) > 1:
                provided_features_level_two.add(parts[1])
            if len(parts) > 2:
                provided_features_level_three.add(parts[2])
            if len(parts) > 3:
                provided_features_level_four.add(parts[3])

    logging.debug("1st level provides: %s", provided_features_level_one)
    logging.debug("2nd level provides: %s", provided_features_level_two)
    logging.debug("3rd level provides: %s", provided_features_level_three)
    logging.debug("4th level provides: %s", provided_features_level_four)


def init(stats: util.Stats, create_atlas: bool=True) -> None:
    logging.debug("textures: init")
    global facades
    global roofs
    global atlas_file_name

    atlas_file_name = os.path.join("tex", "atlas_facades")
    my_tex_prefix_src = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, 'tex.src')
    Texture.tex_prefix = my_tex_prefix_src  # need to set static variable so managers get full path

    pkl_file_name = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, "tex", "atlas_facades.pkl")
    
    if create_atlas:
        facades = FacadeManager('facade', stats)
        roofs = RoofManager('roof', stats)

        # read registrations
        _append_roofs(roofs, my_tex_prefix_src)
        _append_dynamic(facades, my_tex_prefix_src)

        texture_list = facades.get_list() + roofs.get_list()

        # warn for missed out textures
        _check_missed_input_textures(my_tex_prefix_src, texture_list)

        # -- make texture atlas
        if parameters.ATLAS_SUFFIX_DATE:
            now = datetime.datetime.now()
            atlas_file_name += "_%04i%02i%02i" % (now.year, now.month, now.day)

        _make_texture_atlas(texture_list, os.path.join(parameters.PATH_TO_OSM2CITY_DATA, atlas_file_name), '.png',
                            lightmap=True, ambient_occlusion=parameters.BUILDING_FAKE_AMBIENT_OCCLUSION)
        
        params = dict()
        params['atlas_file_name'] = atlas_file_name

        logging.info("Saving %s", pkl_file_name)
        pickle_file = open(pkl_file_name, 'wb')
        pickle.dump(facades, pickle_file, -1)
        pickle.dump(roofs, pickle_file, -1)
        pickle.dump(params, pickle_file, -1)
        pickle_file.close()

        logging.info(str(facades))
        logging.info(str(roofs))
    else:
        logging.info("Loading %s", pkl_file_name)
        pickle_file = open(pkl_file_name, 'rb')
        facades = pickle.load(pickle_file)
        roofs = pickle.load(pickle_file)
        params = pickle.load(pickle_file)
        atlas_file_name = params['atlas_file_name']
        pickle_file.close()

    stats.textures_total = dict((filename, 0) for filename in map((lambda x: x.filename), facades.get_list()))
    stats.textures_total.update(dict((filename, 0) for filename in map((lambda x: x.filename), roofs.get_list())))
    logging.info('Skipped textures: %d', stats.skipped_texture)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="texture manager either reads existing texture atlas or creates new")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

    my_stats = util.Stats()
    init(my_stats)
