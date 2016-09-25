import random
import re
from typing import Dict

import numpy as np
import tools
from PIL import Image
import logging
import os


class Texture(object):

    tex_prefix = ''  # static variable to reduce the dynamic path info the texture registrations. Needs to be set first.
    """
    spelling used internally in osm2city and in many cases automatically converted:
        - colour (instead of color)
        - grey (instead of gray)

    possible texture types:
        - facade
        - roof

    facade:
      provides
        - shape:skyscraper
        - shape:residential
        - shape:commercial/business
        - shape:industrial
        - age:modern/old
        - color: white
        - region: europe-middle
        - region: europe-north
        - minlevels: 2
        - maxlevels: 4
      requires
        - roof:shape:flat
        - roof:colour:red|black

    roof: http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof
      provides
        - colour:black (red, ..)
        - shape:flat  (pitched, ..)

    """
    def __init__(self, filename:str,
                 h_size_meters=None, h_cuts=list(), h_can_repeat=False,
                 v_size_meters=None, v_cuts=list(), v_can_repeat=False,
                 height_min=0, height_max=9999,
                 v_align_bottom=False,
                 provides=list(), requires=list(), levels=None) -> None:
        self.filename = Texture.tex_prefix + os.sep + filename
        self.x0 = self.x1 = self.y0 = self.y1 = 0
        self.sy = self.sx = 0
        self.rotated = False
        self.provides = provides
        self.requires = requires
        self.height_min = height_min
        self.height_max = height_max
        self.width_min = 0
        self.width_max = 9999
        self.v_align_bottom = v_align_bottom
        h_cuts.sort()
        v_cuts.sort()
        self.ax = 0  # coordinate in atlas (int)
        self.ay = 0
        self.validation_message = None
        self.registered_in = None  # filename of the .py file, where this texture has been referenced

        try:
            self.im = Image.open(self.filename)
        except IOError:
            self.validation_message = "Skipping non-existing texture %s" % self.filename
            return
        self.width_px, self.height_px = self.im.size
        image_aspect = self.height_px / float(self.width_px)

        if v_size_meters:
            if levels:
                logging.warning("Ignoring levels=%g because v_size_meters=%g is given for texture %s."
                                % (levels, v_size_meters, filename))
            self.v_size_meters = v_size_meters
        else:
            if not levels:
                logging.warning("Ignoring texture %s because neither v_size_meters nor levels is given"
                                % filename)
                # Set filename to "" to make TextureManger reject us. Bad style, but raising
                # an exception instead would prohibit the nice, simple structure of catalog.py
                self.filename = "" 
                return
            else:
                self.v_size_meters = levels * 3.3  # FIXME: this should be configurable
            
        if h_size_meters: 
            self.h_size_meters = h_size_meters
        else:
            self.h_size_meters = self.v_size_meters / image_aspect
            logging.debug("No hsize, using image aspect %i x %i = %g. h_size = %g v_size = %g" %
                          (self.width_px, self.height_px, image_aspect, self.h_size_meters, self.v_size_meters))
            
        # aspect = v / h
        if len(v_cuts) == 0:
            v_cuts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
            
        if v_cuts is not None:
            v_cuts.insert(0, 0)
            self.v_cuts = np.array(v_cuts, dtype=np.float)
            if len(self.v_cuts) > 1:
                # FIXME: test for not type list
                self.v_cuts /= self.v_cuts[-1]
                # -- Gimp origin is upper left, convert to OpenGL lower left
                self.v_cuts = (1. - self.v_cuts)[::-1]
        else:
            self.v_cuts = 1.
        self.v_cuts_meters = self.v_cuts * self.v_size_meters

        self.v_can_repeat = v_can_repeat

        if not self.v_can_repeat:
            self.height_min = self.v_cuts_meters[0]
            self.height_max = self.v_size_meters

        if len(h_cuts) == 0:
            h_cuts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        self.h_cuts = np.array(h_cuts, dtype=np.float)

        if h_cuts is None:
            self.h_cuts = np.array([1.])
        elif len(self.h_cuts) > 1:
            self.h_cuts /= self.h_cuts[-1]
        self.h_cuts_meters = self.h_cuts * self.h_size_meters
        self.h_can_repeat = h_can_repeat

        if not self.h_can_repeat:
            self.width_min = self.h_cuts_meters[0]
            self.width_max = self.h_size_meters

        if self.h_can_repeat + self.v_can_repeat > 1:
            self.validation_message = '%s: Textures can repeat in one direction only. \
Please set either h_can_repeat or v_can_repeat to False.' % self.filename

    def x(self, x):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
            return self.y0 + x * self.sy
        else:
            return self.x0 + x * self.sx

    def y(self, y):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
            return self.x0 + y * self.sx
        else:
            return self.y0 + y * self.sy

    def __str__(self):
        return "<%s> x0,1 %4.2f %4.2f  y0,1 %4.2f %4.2f  sh,v %4.2fm %4.2fm" % \
                (self.filename, self.x0, self.x1, self.y0, self.y1,
                 self.h_size_meters, self.v_size_meters)
        # self.type = type
        # commercial-
        # - warehouse
        # - skyscraper
        # industrial
        # residential
        # - old
        # - modern
        # european, north_american, south_american, mediterreanian, african, asian

    def closest_h_match(self, frac):
        return self.h_cuts[np.abs(self.h_cuts - frac).argmin()]


class RoofManager(object):
    def __init__(self, cls):
        self.__l = []
        self.__cls = cls  # -- class (roof, facade, ...)
        self.current_registered_in = ""
        self.available_materials = set()

    def append(self, texture: Texture) -> None:
        """Appends a texture to the catalog if the referenced file exists, in which case True is returned.
        Otherwise False is returned and the texture is not added.

        Prepend each item in t.provides with class name, except for class-independent keywords: age,region,compat
        """
        # check whether already during initialization an error occurred
        if texture.validation_message:
            logging.warning("Error during initialization. Defined in registration file %s: %s",
                            self.current_registered_in, texture.validation_message)
            return False

        texture.registered_in = self.current_registered_in

        # check whether the same texture already has been referenced in an existing entry
        for existing in self.__l:
            if existing.filename == texture.filename:
                logging.warning("Double registration. Defined in registration file %s: %s is already referenced in %s",
                                self.current_registered_in, texture.filename, existing.registered_in)
                return False

        new_provides = list()
        logging.debug("Based on registration file %s: added %s ", self.current_registered_in, texture.filename)
        for item in texture.provides:
            if item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(screen_texture_tags_for_colour_spelling(item))
            else:
                if item.split(":")[0] == "material":
                    self.available_materials.add(item.split(":")[1])
                new_provides.append(screen_texture_tags_for_colour_spelling(self.__cls + ':' + item))
        texture.provides = new_provides
        new_requires = list()
        for item in texture.requires:
            new_requires.append(screen_texture_tags_for_colour_spelling(item))
        texture.requires = new_requires
        texture.cls = self.__cls

        tools.stats.textures_total[texture.filename] = None
        self.__l.append(texture)
        return True

    def find_matching_roof(self, requires=[]):
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
                if re.match('^.*material:.*', ex):
                    ex_material_key = re.match('(^.*:material:)[^:]*', ex).group(1)
                    ex_material = re.match('^.*material:([^:]*)', ex).group(1)
                elif re.match('^.*:colour:.*', ex):
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
                        elif re.match('^.*:colour:.*', req):
                            req_colour = re.match('^.*:colour:(.*)', req).group(0)

                    prov_materials = []
                    prov_colours = []
                    for prov in candidate.provides:
                        if re.match('^.*:material:.*', prov):
                            prov_material = re.match('^.*:material:(.*)', prov).group(0)
                            prov_materials.append(prov_material)
                        elif re.match('^.*:colour:.*', prov):
                            prov_colour = re.match('^.*:colour:(.*)', prov).group(0)
                            prov_colours.append(prov_colour)

                    # req_material and colour
                    can_material = False
                    if req_material is not None:
                        for prov_material in prov_materials:
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
                logging.verbose("  unmet requires %s req %s prov %s",
                                str(candidate.filename), str(requires), str(candidate.provides))  # @UndefinedVariable
        return candidates

    def __str__(self):
        return "".join([str(t) + '\n' for t in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

    def get_list(self):
        return self.__l


class FacadeManager(RoofManager):
    def find_matching_facade(self, requires, tags, height, width):
        exclusions = []
        if 'roof:colour' in tags:
            exclusions.append("%s:%s" % ('roof:colour', tags['roof:colour']))
        candidates = self.find_facade_candidates(requires, exclusions, height, width)
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
                new_key = "facade:building:material:%s" % val
                if new_key in t.provides:
                    match += 1
            ranked_list.append([match, t])
        ranked_list.sort(key=lambda tup: tup[0], reverse=True)
        max_val = ranked_list[0][0]
        if max_val > 0:
            logging.info("Max Rank %d" % max_val)
        return [t[1] for t in ranked_list if t[0] >= max_val]

    def find_facade_candidates(self, requires, excludes, height, width):
        candidates = RoofManager.find_candidates(self, requires, excludes)
        # -- check height
        new_candidates = []
        for t in candidates:
            if height < t.height_min or height > t.height_max:
                logging.verbose("height %.2f (%.2f-%.2f) outside bounds : %s",
                                height, t.height_min, t.height_max, str(t.filename))  # @UndefinedVariable
                continue
            if width < t.width_min or width > t.width_max:
                logging.verbose("width %.2f (%.2f-%.2f) outside bounds : %s",
                                width, t.width_min, t.width_max, str(t.filename))  # @UndefinedVariable
                continue

            new_candidates.append(t)
        return new_candidates


def _map_hex_colour(value):
    colour_map = {
                  "#000000": "black",
                  "#FFFFFF": "white",
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


def screen_texture_tags_for_colour_spelling(original: str) -> str:
    """Replaces all occurrences of color with colour"""
    if "color" in original or "gray" in original:
        new_string = original.replace("color", "colour")
        new_string = new_string.replace("gray", "grey")
        return new_string
    else:
        return original


def screen_osm_tags_for_colour_spelling(osm_id: int, tags: Dict[str, str]) -> None:
    if 'building:color' in tags and 'building:colour' not in tags:
        logging.debug('osm_id %i uses color instead of colour' % osm_id)
        tags['building:colour'] = tags['building:color']
        del (tags['building:color'])
    elif 'building:color' in tags and 'building:colour' in tags:
        del (tags['building:color'])
    if 'roof:color' in tags and 'roof:colour' not in tags:
        logging.debug('osm_id %i uses color instead of colour' % osm_id)
        tags['roof:colour'] = tags['roof:color']
        del (tags['roof:color'])
    elif 'roof:color' in tags and 'roof:colour' in tags:
        del (tags['roof:color'])

