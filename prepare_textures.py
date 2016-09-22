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
#                AND (roof.color = black OR roof.color = gray) 
#                AND roof.shape = flat ')


import argparse
import datetime
import logging
import math
import os
import pickle
import sys

import img2np
import numpy as np
import parameters
import tools
import utils.utilities as util
from PIL import Image
from textures import atlas
from textures.texture import Texture, RoofManager, FacadeManager

atlas_file_name = None

ROOFS_DEFAULT_FILE_NAME = "roofs_default.py"


def _next_pow2(value):
    return 2**(int(math.log(value) / math.log(2)) + 1)


def _make_texture_atlas(texture_list, atlas_filename, ext, size_x=256, pad_y=0,
                        lightmap=False, ambient_occlusion=False):
    """
    Create texture atlas from all textures. Update all our item coordinates.
    """
    logging.debug("Making texture atlas")
    
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
            filename, fileext = os.path.splitext(l.filename)
            filename += '_LM' + fileext
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

    # -- pack non_repeatables
    # Sort textures by perimeter size in non-increasing order
    the_atlas = atlas.Atlas(0, 0, atlas_sx, 1e10, 'Facades')
    if 1:
        non_repeat_list = sorted(non_repeat_list, key=lambda i: i.sy, reverse=True)
        deb = 0
        for the_texture in non_repeat_list:
            the_texture.width_px, the_texture.height_px = the_texture.im.size

            if the_atlas.pack(the_texture):
                if deb:
                    the_atlas.write("atlas.png", "RGBA")
                    input("Press Enter to continue...")
                pass
            else:
                print("no")

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
        try:        
            #l.x0 = x_px / atlas_sx
            #l.y0 = y_px / atlas_sy
            #the_atlas.write('atlas.png', 'RGBA')
            #raw_input("Press Enter to continue...")
            pass
        except:
            logging.info("Failed to pack", l)

#    the_atlas.write("atlas.png", "RGBA")
#    return
        
    atlas_sy = _next_pow2(atlas_sy)
    the_atlas.set_height(atlas_sy)
    logging.info("Final atlas height %i" % atlas_sy)

    the_atlas.write(atlas_filename + ext, "RGBA", 'im')

    # -- create LM atlas, using the coordinates of the main atlas
    if lightmap:
        LM_atlas = atlas.Atlas(0, 0, atlas_sx, the_atlas.height_px, 'FacadesLM')
        for l in texture_list:
            LM_atlas.pack_at(l, l.ax, l.ay)
        LM_atlas.write(atlas_filename + '_LM' + ext, "RGBA", 'im_LM')

    for l in texture_list:
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (l.filename, l.x0, l.y0, l.x1, l.y1))
        del l.im
        if lightmap:
            del l.im_LM


def _check_missed_input_textures(tex_prefix, registered_textures):
    """Find all .jpg and .png files in tex.src and compare with registered textures.

    If not found in registered textures, then log a warning"""
    for subdir, dirs, files in os.walk(tex_prefix, topdown=True):
        for filename in files:
            if filename[-4:] in [".jpg", ".png"]:
                if filename[-7:-4] in ["_LM", "_MA"]:
                    continue
                my_path = subdir + os.sep + filename
                found = False
                for registered in registered_textures:
                    if registered.filename == my_path:
                        found = True
                        break
                if not found:
                    logging.warning("Texture %s has not been registered", my_path)


def _append_dynamic(facades, tex_prefix):
    """Dynamically runs .py files in tex.src and sub-directories to add facades.

    For roofs see add_roofs(roofs)"""
    for subdir, dirs, files in os.walk(tex_prefix, topdown=True):
        for filename in files:
            if filename[-2:] != "py":
                continue
            elif filename == ROOFS_DEFAULT_FILE_NAME:
                continue

            my_path = subdir + os.sep + filename
            logging.info("Executing %s ", my_path)
            try:
                facades.current_registered_in = my_path
                exec(compile(open(my_path).read(), my_path, 'exec'))
            except:
                logging.exception("Error while running %s" % filename)


def _append_roofs(roofs, tex_prefix):  # parameter roofs is used dynamically in execfile
    """Dynamically runs the content of a hard-coded file to fill the roofs texture list."""
    try:
        file_name = tex_prefix + os.sep + ROOFS_DEFAULT_FILE_NAME
        roofs.current_registered_in = file_name
        exec(compile(open(file_name).read(), file_name, 'exec'))
    except Exception as e:
        logging.exception("Unrecoverable error while loading roofs")
        sys.exit(1)


def init(tex_prefix='', create_atlas=False):  # in most situations tex_prefix should be osm2city root directory
    logging.debug("textures: init")
    global facades
    global roofs
    global atlas_file_name

    if tools.stats is None:  # if e.g. manager.init is called from osm2city, then tools.init does not need to be called
        tools.init(None)

    my_tex_prefix = util.assert_trailing_slash(tex_prefix)
    atlas_file_name = "tex" + os.sep + "atlas_facades"
    my_tex_prefix_src = my_tex_prefix + 'tex.src'
    Texture.tex_prefix = my_tex_prefix_src  # need to set static variable so managers get full path

    pkl_fname = my_tex_prefix + "tex" + os.sep + "atlas_facades.pkl"
    
    if create_atlas:
        facades = FacadeManager('facade')
        roofs = RoofManager('roof')

        # read registration
        _append_roofs(roofs, my_tex_prefix_src)
        _append_dynamic(facades, my_tex_prefix_src)

        texture_list = facades.get_list() + roofs.get_list()

        # warn for missed out textures
        _check_missed_input_textures(my_tex_prefix_src, texture_list)

        # -- make texture atlas
        if parameters.ATLAS_SUFFIX_DATE:
            now = datetime.datetime.now()
            atlas_file_name += "_%04i%02i%02i" % (now.year, now.month, now.day)

        _make_texture_atlas(texture_list, my_tex_prefix + atlas_file_name, '.png',
                            lightmap=True, ambient_occlusion=parameters.BUILDING_FAKE_AMBIENT_OCCLUSION)
        
        params = dict()
        params['atlas_file_name'] = atlas_file_name

        logging.info("Saving %s", pkl_fname)
        fpickle = open(pkl_fname, 'wb')
        pickle.dump(facades, fpickle, -1)
        pickle.dump(roofs, fpickle, -1)
        pickle.dump(params, fpickle, -1)
        fpickle.close()
    else:
        logging.info("Loading %s", pkl_fname)
        fpickle = open(pkl_fname, 'rb')
        facades = pickle.load(fpickle)
        roofs = pickle.load(fpickle)
        params = pickle.load(fpickle)
        atlas_file_name = params['atlas_file_name']
        fpickle.close()

    logging.debug(facades)
    tools.stats.textures_total = dict((filename, 0) for filename in map((lambda x: x.filename), facades.get_list()))
    tools.stats.textures_total.update(dict((filename, 0) for filename in map((lambda x: x.filename), roofs.get_list())))


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

    init(util.get_osm2city_directory(), True)
