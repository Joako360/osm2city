# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
# The provides/requires mechanism could be improved. 
# Currently, TextureManager prepends the "provides" tags with the texture class.
# Find_matching will match only if "requires" is a subset of "provides".
# That is, there is no OR. All "requires" must be matched 
#
# ideally:
# Texture(rules='building.height > 15 
#                AND (roof.color = black OR roof.color = gray) 
#                AND roof.shape = flat ')


import argparse
import pickle
import datetime
import logging
import math
import os
import random
import re
import sys

import numpy as np
from PIL import Image

from textures import atlas
import img2np
import parameters
import tools
from textures.texture import Texture

atlas_file_name = None

ROOFS_DEFAULT_FILE_NAME = "roofs_default.py"


def _next_pow2(value):
    return 2**(int(math.log(value) / math.log(2)) + 1)


def _make_texture_atlas(texture_list, atlas_filename, ext, tex_prefix, size_x=256, pad_y=0,
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

    # -- load and rotate images, store image data in TextureManager object
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


class TextureManager(object):
    def __init__(self, cls):
        self.__l = []
        self.__cls = cls  # -- class (roof, facade, ...)
        self.current_registered_in = ""

    def append(self, t):
        """Appends a texture to the catalog if the referenced file exists, in which case True is returned.
        Otherwise False is returned and the texture is not added.

        Prepend each item in t.provides with class name, except for class-independent keywords: age,region,compat
        """
        # check whether already during initialization an error occured
        if t.validation_message:
            logging.warning("Defined in registration file %s: %s", self.current_registered_in, t.validation_message)
            return False

        t.registered_in = self.current_registered_in

        # check whether the same texture already has been referenced in an existing entry
        for existing in self.__l:
            if existing.filename == t.filename:
                logging.warning("Defined in registration file %s: %s has already been referenced in %s",
                                self.current_registered_in, t.filename, existing.registered_in)
                return False

        new_provides = []
        logging.debug("Based on registration file %s: added %s ", self.current_registered_in, t.filename)
        for item in t.provides:
            if item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(item)
            else:
                new_provides.append(self.__cls + ':' + item)
        t.provides = new_provides
        t.cls = self.__cls
        
        tools.stats.textures_total[t.filename] = None
        self.__l.append(t)
        return True

    def find_matching(self, requires=[]):
        candidates = self.find_candidates(requires)
        logging.verbose("looking for texture" + str(requires))  # @UndefinedVariable
        for c in candidates:
            logging.verbose("  candidate " + c.filename + " provides " + str(c.provides))  # @UndefinedVariable
        if len(candidates) == 0:
            return None
        the_texture = candidates[random.randint(0, len(candidates)-1)]
        tools.stats.count_texture(the_texture)        
        return the_texture 

    def find_candidates(self, requires=[], excludes=[]):
        candidates = []
        # replace known hex colour codes
        requires = list(_map_hex_colour(value) for value in requires)
        can_use = True
        for candidate in self.__l:
            for ex in excludes:
                # check if we maybe have a tag that doesn't match a requires
                ex_material_key = 'XXX'
                ex_colour_key = 'XXX'
                ex_material = ''
                ex_colour = ''
                if re.match('^.*material:.*', ex) :
                    ex_material_key = re.match('(^.*:material:)[^:]*', ex).group(1)
                    ex_material = re.match('^.*material:([^:]*)', ex).group(1)
                elif re.match('^.*:colour:.*', ex) :
                    ex_colour_key = re.match('(^.*:colour:)[^:]*', ex).group(1)
                    ex_colour = re.match('^.*:colour:([^:]*)', ex).group(1)
                for req in candidate.requires:
                    if req.startswith(ex_colour_key) and ex_colour is not re.match('^.*:colour:(.*)', req).group(1):
                        can_use = False                        
                    if req.startswith(ex_material_key) and ex_material is not re.match('^.*:material:(.*)',
                                                                                       req).group(1):
                        can_use = False                        

            if set(requires).issubset(candidate.provides):
                # Check for "specific" texture in order they do not pollute everything
                if ('facade:specific' in candidate.provides) or ('roof:specific' in candidate.provides):
                    can_use = False
                    req_material = None
                    req_colour = None
                    for req in requires:
                        if re.match('^.*material:.*', req):
                            req_material = re.match('^.*material:(.*)', req).group(0)
                        elif re.match('^.*:colour:.*', req) :
                            req_colour = re.match('^.*:colour:(.*)', req).group(0)
                            
                    prov_materials = []
                    prov_colours = []
                    prov_material = None
                    prov_colour   = None
                    for prov in candidate.provides :
                        if re.match('^.*:material:.*', prov):
                            prov_material = re.match('^.*:material:(.*)', prov).group(0)
                            prov_materials.append(prov_material)
                        elif re.match('^.*:colour:.*', prov):
                            prov_colour = re.match('^.*:colour:(.*)', prov).group(0)                    
                            prov_colours.append(prov_colour)

                    # req_material and colour
                    can_material = False
                    if req_material is not None:
                        for prov_material in prov_materials :
                            logging.verbose("Provides ", prov_material, " Requires ", requires)  # @UndefinedVariable
                            if prov_material in requires:
                                can_material = True
                                break
                    else:
                        can_material = True

                    can_colour = False
                    if req_colour is not None:
                        for prov_colour in prov_colours:
                            if prov_colour in requires:
                                can_colour = True
                                break
                    else:
                        can_colour = True
                                
                    if can_material and can_colour:
                        can_use = True

                if can_use:
                    candidates.append(candidate)
            else:
                logging.verbose("  unmet requires %s req %s prov %s"
                                , str(candidate.filename), str(requires), str(candidate.provides))  # @UndefinedVariable
        return candidates

    def __str__(self):
        return "".join([str(t) + '\n' for t in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

    def get_list(self):
        return self.__l


class FacadeManager(TextureManager):
    def find_matching(self, requires, tags, height, width):
        exclusions = []
        if 'roof:colour' in tags:
            exclusions.append("%s:%s" % ('roof:colour', tags['roof:colour']))
        candidates = self.find_candidates(requires, exclusions, height, width)
        if len(candidates) == 0:
            logging.warning("no matching facade texture for %1.f m x %1.1f m <%s>", height, width, str(requires))
            return None
        ranked_list = self.rank_candidates(candidates, tags)
        the_texture = ranked_list[random.randint(0, len(ranked_list) - 1)]
        tools.stats.count_texture(the_texture)        
        return the_texture 

    def rank_candidates(self, candidates, tags):
        ranked_list = []
        for t in candidates:
            match = 0
            if 'building:material' in tags:
                val = tags['building:material']
                new_key = ("facade:building:material:%s") % (val)
                if new_key in t.provides:
                    match += 1
            ranked_list.append([match, t])
#         b = ranked_list[:,0]
        ranked_list.sort(key=lambda tup: tup[0], reverse=True)
        max_val = ranked_list[0][0]
        if max_val > 0:
            logging.info("Max Rank %d" % max_val)
        return [t[1] for t in ranked_list if t[0] >= max_val]

    def find_candidates(self, requires, excludes, height, width):
        candidates = TextureManager.find_candidates(self, requires, excludes)
        # -- check height
        new_candidates = []
        for t in candidates:
            if height < t.height_min or height > t.height_max:
                logging.verbose("height %.2f (%.2f-%.2f) outside bounds : %s"
                                , height, t.height_min, t.height_max, str(t.filename))  # @UndefinedVariable
                continue
            if width < t.width_min or width > t.width_max:
                logging.verbose("width %.2f (%.2f-%.2f) outside bounds : %s"
                                , width, t.width_min, t.width_max, str(t.filename))  # @UndefinedVariable
                continue

            new_candidates.append(t)
        return new_candidates


def _map_hex_colour(value):
    colour_map = {
                  "#000000": "black",
                  "#FFFFFF": "white",
                  "#fff": "white",
                  "#808080": "grey",
                  "#C0C0C0": "silver",
                  "#800000": "maroon",
                  "#FF0000": "red",
                  "#808000": "olive",
                  "#FFFF00": "yellow",
                  "#008000": "green",
                  "#00FF00": "lime",
                  "#008080": "teal",
                  "#00FFFF": "aqua",
                  "#000080": "navy",
                  "#0000FF": "blue",
                  "#800080": "purple",
                  "#FF00FF": "fuchsia"
    }
    hash_pos = value.find("#")
    if (value.startswith("roof:colour") or value.startswith("facade:building:colour")) and hash_pos > 0:
        try:
            tag_string = value[:hash_pos]
            colour_hex_string = value[hash_pos:].upper()

            return tag_string + colour_map[colour_hex_string]
        except KeyError:
            return value
    return value


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

    my_tex_prefix = tools.assert_trailing_slash(tex_prefix)
    atlas_file_name = my_tex_prefix + "tex" + os.sep + "atlas_facades"
    my_tex_prefix += 'tex.src'
    Texture.tex_prefix = my_tex_prefix  # need to set static variable so managers get full path

    pkl_fname = atlas_file_name + '.pkl'
    
    if create_atlas:
        facades = FacadeManager('facade')
        roofs = TextureManager('roof')

        # read registration
        _append_roofs(roofs, my_tex_prefix)
        _append_dynamic(facades, my_tex_prefix)

        texture_list = facades.get_list() + roofs.get_list()

        # warn for missed out textures
        _check_missed_input_textures(my_tex_prefix, texture_list)

        # -- make texture atlas
        if parameters.ATLAS_SUFFIX_DATE:
            now = datetime.datetime.now()
            atlas_file_name += "_%04i%02i%02i" % (now.year, now.month, now.day)

        _make_texture_atlas(texture_list, atlas_file_name, '.png', my_tex_prefix,
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
    parser.add_argument("-a", dest="a", action="store_true",
                        help="create texture atlas", required=False)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

    init(tools.get_osm2city_directory(), args.a)
