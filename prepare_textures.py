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
#                AND (roof.colour = black OR roof.colour = gray)
#                AND roof.shape = flat ')


import argparse
import enum
import logging
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
from textures.texture import Texture, FacadeManager, RoofManager, SpecialManager

atlas_file_name = None

ROOFS_DEFAULT_FILE_NAME = "roofs_default.py"

# expose the three managers on module level
roofs = None  # RoofManager
facades = None  # FacadeManager
specials = None  # SpecialManager

# Hard-coded constants for the texture atlas. If they are changed, then maybe all sceneries in Terrasync need
# to be recreated -> therefore not configurable. Numbers are in pixels (need to be factor 2).
ATLAS_ROOFS_START = 0
ATLAS_FACADES_START = 18 * 256
ATLAS_HEIGHT = 64 * 256  # 16384
ATLAS_WIDTH = 256


def _make_texture_atlas(roofs_list: List[Texture], facades_list: List[Texture], specials_list: List[Texture],
                        atlas_filename: str, ext: str, pad_y: int=0) -> None:
    """
    Create texture atlas from all textures. Update all our item coordinates.
    """
    logging.info("Making texture atlas")

    if (len(facades_list) + len(roofs_list) + len(specials_list)) < 1:
        logging.error('Got an empty texture list. Check installation of tex.src/ folder!')
        sys.exit(-1)

    the_atlas = atlas.Atlas(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT, 'Facades')

    _make_per_texture_type(roofs_list, the_atlas, pad_y)
    # reduce the available region based on roof slot
    the_atlas.regions = [atlas.Region(0, ATLAS_FACADES_START, ATLAS_WIDTH, ATLAS_HEIGHT - ATLAS_FACADES_START)]
    _make_per_texture_type(facades_list, the_atlas, pad_y)

    the_atlas.compute_nondim_tex_coords()
    the_atlas.write(atlas_filename + ext, 'im')

    # -- create LM atlas, using the coordinates of the main atlas
    light_map_atlas = atlas.Atlas(0, 0, ATLAS_WIDTH, ATLAS_HEIGHT, 'FacadesLM')
    for tex in roofs_list:
        light_map_atlas.pack_at_coords(tex, tex.ax, tex.ay)
    for tex in facades_list:
        light_map_atlas.pack_at_coords(tex, tex.ax, tex.ay)
    light_map_atlas.write(atlas_filename + '_LM' + ext, 'im_LM')

    for tex in (roofs_list + facades_list + specials_list):
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (tex.filename, tex.x0, tex.y0, tex.x1, tex.y1))
        del tex.im
        del tex.im_LM


def _make_per_texture_type(texture_list: List[Texture], the_atlas: atlas.Atlas, pad_y: int, ) -> None:
    keep_aspect = True  # FIXME: False won't work -- im.thumbnail seems to keep aspect no matter what

    next_y = 0

    # -- load and rotate images, store image data in RoofManager object
    #    append to either can_repeat or non_repeat list
    can_repeat_list = []
    non_repeat_list = []
    for tex in texture_list:
        filename = tex.filename
        tex.im = Image.open(filename)
        logging.debug("name %s size " % filename + str(tex.im.size))

        # light-map
        filename, file_extension = os.path.splitext(tex.filename)
        filename += '_LM' + file_extension
        try:
            tex.im_LM = Image.open(filename)
        except IOError:
            # assuming there is no light-map. Put a dark uniform light-map
            the_image = Image.new('RGB', tex.im.size, 'rgb({0},{0},{0})'.format(parameters.TEXTURES_EMPTY_LM_RGB_VALUE))
            tex.im_LM = the_image

        assert (tex.v_can_repeat + tex.h_can_repeat < 2)
        if tex.v_can_repeat:
            tex.rotated = True
            tex.im = tex.im.transpose(Image.ROTATE_270)

            tex.im_LM = tex.im_LM.transpose(Image.ROTATE_270)

        if tex.v_can_repeat or tex.h_can_repeat:
            can_repeat_list.append(tex)
        else:
            non_repeat_list.append(tex)

    # Work on not repeatable textures
    for tex in non_repeat_list:
        tex.width_px, tex.height_px = tex.im.size

        if not the_atlas.pack(tex):
            raise ValueError("No more space left and therefore failed to pack: %s" % str(tex))
    atlas_sy = the_atlas.cur_height()

    # Work on repeatable textures.
    # Scale each to full atlas width
    # Compute total height of repeatable section
    for tex in can_repeat_list:
        scale_x = 1. * ATLAS_WIDTH / tex.im.size[0]
        if keep_aspect:
            scale_y = scale_x
        else:
            scale_y = 1.
        org_size = tex.im.size

        nx = int(org_size[0] * scale_x)
        ny = int(org_size[1] * scale_y)
        tex.im = tex.im.resize((nx, ny), Image.ANTIALIAS)
        if tex.im_LM:
            tex.im_LM = tex.im_LM.resize((nx, ny), Image.ANTIALIAS)
        logging.debug("scale:" + str(org_size) + str(tex.im.size))
        atlas_sy += tex.im.size[1] + pad_y
        tex.width_px, tex.height_px = tex.im.size

    # Bake fake ambient occlusion. Multiply all channels of a facade texture by
    # 1. - param.BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE * np.exp(-z / param.BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT)
    #    where z is height above ground.
    # Has to be done after scaling of texture has happened
    if parameters.BUILDING_FAKE_AMBIENT_OCCLUSION:
        for tex in texture_list:
            if tex.cls == 'facade':
                R, G, B, A = img2np.img2RGBA(tex.im)
                height_px = R.shape[0]
                # reversed height
                Z = np.linspace(tex.v_size_meters, 0, height_px).reshape(height_px, 1)
                fac = 1. - parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_VALUE * np.exp(
                    -Z / parameters.BUILDING_FAKE_AMBIENT_OCCLUSION_HEIGHT)
                tex.im = img2np.RGBA2img(R * fac, G * fac, B * fac)

    # -- paste, compute atlas coords
    #    lower left corner of texture is x0, y0
    for tex in can_repeat_list:
        tex.x0 = 0
        tex.x1 = float(tex.width_px) / ATLAS_WIDTH
        tex.y1 = 1 - float(next_y) / atlas_sy
        tex.y0 = 1 - float(next_y + tex.height_px) / atlas_sy
        tex.sy = float(tex.height_px) / atlas_sy
        tex.sx = 1.

        next_y += tex.height_px + pad_y
        if not the_atlas.pack(tex):
            #logging.debug("No more space left and therefore failed to pack: %s", str(tex))
            raise ValueError("No more space left and therefore failed to pack: %s" % str(tex))


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


def _append_facades(facade_manager: FacadeManager, tex_prefix: str) -> None:
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


@enum.unique
class InitMode(enum.IntEnum):
    read = 0
    create = 1  # create new texture atlas by reading from sources
    update = 2  # update existing texture atlas by reading from sources


def init(stats: util.Stats, mode: InitMode=InitMode.read) -> None:
    """Initializes the texture atlas based on the init mode of the process."""
    logging.debug("prepare_textures: init")
    global roofs
    global facades
    global specials
    global atlas_file_name

    atlas_file_name = os.path.join("tex", "atlas_facades")
    my_tex_prefix_src = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, 'tex.src')
    Texture.tex_prefix = my_tex_prefix_src  # need to set static variable so managers get full path

    pkl_file_name = os.path.join(parameters.PATH_TO_OSM2CITY_DATA, "tex", "atlas_facades.pkl")
    
    if mode is InitMode.create:
        roofs = RoofManager('roof', stats)
        facades = FacadeManager('facade', stats)
        specials = SpecialManager('special', stats)

        # read registrations
        _append_roofs(roofs, my_tex_prefix_src)
        _append_facades(facades, my_tex_prefix_src)
        # FIXME: nothing to do yet for SpecialManager

        # warn for missed out textures
        _check_missed_input_textures(my_tex_prefix_src, roofs.get_list() + facades.get_list())

        # -- make texture atlas
        if parameters.ATLAS_SUFFIX:
            atlas_file_name += '_' + parameters.ATLAS_SUFFIX

        _make_texture_atlas(roofs.get_list(), facades.get_list(), specials.get_list(),
                            os.path.join(parameters.PATH_TO_OSM2CITY_DATA, atlas_file_name), '.png')
        
        params = dict()
        params['atlas_file_name'] = atlas_file_name

        logging.info("Saving %s", pkl_file_name)
        pickle_file = open(pkl_file_name, 'wb')
        pickle.dump(roofs, pickle_file, -1)
        pickle.dump(facades, pickle_file, -1)
        pickle.dump(specials, pickle_file, -1)
        pickle.dump(params, pickle_file, -1)
        pickle_file.close()

        logging.info(str(roofs))
        logging.info(str(facades))
        logging.info(str(specials))
    else:
        logging.info("Loading %s", pkl_file_name)
        pickle_file = open(pkl_file_name, 'rb')
        roofs = pickle.load(pickle_file)
        facades = pickle.load(pickle_file)
        specials = pickle.load(pickle_file)
        params = pickle.load(pickle_file)
        atlas_file_name = params['atlas_file_name']
        pickle_file.close()

    stats.textures_total = dict((filename, 0) for filename in map((lambda x: x.filename), roofs.get_list()))
    stats.textures_total.update(dict((filename, 0) for filename in map((lambda x: x.filename), facades.get_list())))
    stats.textures_total.update(dict((filename, 0) for filename in map((lambda x: x.filename), specials.get_list())))
    logging.info('Skipped textures: %d', stats.skipped_texture)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="texture manager either reads existing texture atlas or creates new")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel", dest='loglevel',
                        help="set logging level. Valid levels are DEBUG, INFO (default), WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument("-u", "--update", dest="update", action="store_true",
                        help="update texture atlas instead of creating new", required=False)
    args = parser.parse_args()

    log_level = 'INFO'
    if args.loglevel:
        log_level = args.loglevel
    logging.getLogger().setLevel(log_level)

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.show()

    init_mode = InitMode.create
    if args.update:
        init_mode = InitMode.update

    my_stats = util.Stats()
    init(my_stats, init_mode)
