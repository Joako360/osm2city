#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 13 22:22:05 2013

@author: tom
"""
import numpy as np
import random
from pdb import pm
import logging
from PIL import Image
import math
import cPickle
import string
import os
import sys
import atlas
from texture import Texture
import catalog

#import textures_src

def next_pow2(value):
    return 2**(int(math.log(value) / math.log(2)) + 1)

def make_texture_atlas(texture_list, atlas_filename, ext, size_x = 256, pad_y = 0, lightmap=False):
    """
    create texture atlas from all textures. Update all our item coordinates.
    """
    logging.debug("Making texture atlas")
    
    if len(texture_list) < 1:
        logging.error('Got an empty texture list. Check installation of tex.src/ folder!')
        sys.exit(-1)

    atlas_sx = size_x
    keep_aspect = True # FIXME: False won't work -- im.thumbnail seems to keep aspect no matter what

#    atlas_sy = 0
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
        non_repeat_list = sorted(non_repeat_list, key=lambda i:i.sy, reverse=True)
        deb = 0
        for the_texture in non_repeat_list:
            the_texture.width_px, the_texture.height_px = the_texture.im.size
            #if the_texture.filename == "tex.src/samples/US-dcwhiteconc10st2.jpg":
                #the_atlas.write("atlas.png", "RGBA")
                #raw_input("Press Enter to continue...")
                #deb = 1
    
            if the_atlas.pack(the_texture):
                if deb:
                    the_atlas.write("atlas.png", "RGBA")
                    raw_input("Press Enter to continue...")
                pass
            else:
                print "no"

    atlas_sy = the_atlas.cur_height()

    #can_repeat_list = []

    # -- work on repeatable textures.
    #    Scale each to full atlas width
    #    Compute total height of repeatable section
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
        if lightmap:
            l.im_LM = l.im_LM.resize((nx, ny), Image.ANTIALIAS)
        logging.debug("scale:" + str(org_size) + str(l.im.size))
        atlas_sy += l.im.size[1] + pad_y
        l.width_px, l.height_px = l.im.size

    # assert(max(sx) <= altas_sx)

    # -- paste, compute atlas coords
    #    lower left corner of texture is x0, y0
    for l in can_repeat_list:
        #atlas.paste(l.im, (0, next_y))
        l.x0 = 0
        l.x1 = float(l.width_px) / atlas_sx
        l.y1 = 1 - float(next_y) / atlas_sy
        l.y0 = 1 - float(next_y + l.height_px) / atlas_sy
        l.sy = float(l.height_px) / atlas_sy
        l.sx = 1.

        next_y += l.height_px + pad_y
#        print "pack?", l.width_px, l.height_px
#        success = the_atlas.pack(l)
        if the_atlas.pack(l):
#        if success:
#            l._x = x
#            l._y = y
            pass
        else:
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
        
    atlas_sy = next_pow2(atlas_sy)
    the_atlas.set_height(atlas_sy)
    logging.info("Final atlas height %i" % atlas_sy)

    the_atlas.write(atlas_filename + ext, "RGBA", 'im')

    # -- create LM atlas, using the coords of the main atlas
    if lightmap:
        LM_atlas = atlas.Atlas(0, 0, atlas_sx, the_atlas.height_px, 'FacadesLM')
        for l in texture_list:
            LM_atlas.pack_at(l, l._x, l._y)
        LM_atlas.write(atlas_filename + '_LM' + ext, "RGBA", 'im_LM')

    for l in texture_list:
        logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (l.filename, l.x0, l.y0, l.x1, l.y1))
        del l.im
        if lightmap:
            del l.im_LM

class TextureManager(object):
    def __init__(self,cls):
        self.__l = []
        self.__cls = cls # -- class (roof, facade, ...)

    def append(self, t):
        # -- prepend each item in t.provides with class name,
        #    except for class-independent keywords: age,region,compat
        if not os.path.exists(t.filename):
            return

        new_provides = []
        for item in t.provides:
            if item.split(':')[0] in ('age', 'region', 'compat'):
                new_provides.append(item)
            else:
                new_provides.append(self.__cls + ':' + item)
        #t.provides = [self.__cls + ':' + i for i in t.provides]
        t.provides = new_provides
        self.__l.append(t)

    def keep_only(self, i):
        """debug: loose all but this texture"""
        self.__l = [self.__l[i]]

    def find_matching(self, requires = []):
        candidates = self.find_candidates(requires)
        logging.debug("looking for texture" + str(requires))
        for c in candidates:
            logging.debug("  candidate " + c.filename + " provides " + str(c.provides))
        if len(candidates) == 0:
            logging.warn("WARNING: no matching texture for <%s>" % str(requires))
            return None
        #print "cands are\n", string.join(["  " + str(c) for c in candidates], '\n')
        #return candidates[3]
        return candidates[random.randint(0, len(candidates)-1)]

    def find_candidates(self, requires = []):
        #return [self.__l[0]]
        candidates = []
        for cand in self.__l:
            if set(requires).issubset(cand.provides):
                candidates.append(cand)
        return candidates

    def __str__(self):
        return string.join([str(t) + '\n' for t in self.__l])

    def __getitem__(self, i):
        return self.__l[i]

    def get_list(self):
        return self.__l


class FacadeManager(TextureManager):
    def find_matching(self, requires, tags, height, width):
        candidates = self.find_candidates(requires, height, width)
        if len(candidates) == 0:
            logging.warn("no matching texture for %1.f m x %1.1f m <%s>" % (height, width, str(requires)))
            return None
        ranked_list = self.rank_candidates(candidates, tags)
        return ranked_list[random.randint(0, len(ranked_list) - 1)]

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
        if(max_val > 0):
            logging.info("Max Rank %d" % max_val)
        return [t[1] for t in ranked_list if t[0] >= max_val]

    def find_candidates(self, requires, height, width):
        candidates = TextureManager.find_candidates(self, requires)
#        print "\ncands", [str(t.filename) for t in candidates]
        # -- check height
#        print " Candidates:"
        new_candidates = []
        for t in candidates:
#            print "  <<<", t.filename
#            print "     building_height", building_height
#            print "     min/max", t.height_min, t.height_max
            if height < t.height_min or height > t.height_max:
                continue
            if width < t.width_min or width > t.width_max:
                continue

            new_candidates.append(t)

#                candidates.remove(t)
#        print "remaining cands", [str(t.filename) for t in new_candidates]
        return new_candidates

def find_matching_texture(cls, textures):
    candidates = []
    for t in textures:
        if t.cls == cls: candidates.append(t)
    if len(candidates) == 0: return None
    return candidates[random.randint(0, len(candidates)-1)]


# pitched roof: requires = facade:age:old

def init(tex_prefix=''):
    print "textures: init"
    global facades
    global roofs
    facades = FacadeManager('facade')
    roofs = TextureManager('roof')

    catalog.append_facades_de(tex_prefix, facades)
    #append_facades_test()
    catalog.append_roofs(tex_prefix, roofs)
    catalog.append_facades_us(tex_prefix, facades)
    #facades.keep_only(1)

    if False:
        print roofs[0].provides
        print "black roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:black'])]
        print "red   roofs: ", [str(i) for i in roofs.find_candidates(['roof:color:red'])]
        print "old facades: "
        for i in facades.find_candidates(['facade:shape:residential','age:old'], 10):
            print i, i.v_cuts * i.v_size_meters
    #print facades[0].provides

    if False:
        facades = FacadeManager('facade')
        roofs = TextureManager('roof')
        facades.append(Texture(tex_prefix + 'test.png',
                               10, [142,278,437,590,756,890,1024], True,
                               10, [130,216,297,387,512], True, True,
                               provides=['shape:urban','shape:residential','age:modern','age:old','compat:roof-flat','compat:roof-pitched']))
        roofs.append(Texture(tex_prefix + 'test.png',
                             10., [], True, 10., [], True, provides=['color:black', 'color:red']))

    # -- make texture atlas (or unpickle)
    filename = tex_prefix + 'tex/atlas_facades'
    pkl_fname = filename + '.pkl'
    if 1:
#        facades.make_texture_atlas(filename + '.png')
        texture_list = facades.get_list() + roofs.get_list()
        make_texture_atlas(texture_list, filename, '.png', lightmap=True)

        logging.info("Saving %s", pkl_fname)
        #fpickle = open(pkl_fname, 'wb')
        #cPickle.dump(facades, fpickle, -1)
        #fpickle.close()
    else:
        logging.info("Loading %s", pkl_fname)
        fpickle = open(pkl_fname, 'rb')
        facades = cPickle.load(fpickle)
        fpickle.close()

    logging.info(facades)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    init(tex_prefix = "../")

    if 0:
        cands = facades.find_candidates([], 14)
        #print "cands are", cands
        for t in cands:
            #print "%5.2g  %s" % (t.height_min, t.filename)
            logging.debug('%s (%4.2f, %4.2f) (%4.2f, %4.2f)' % (t.filename, t.x0, t.y0, t.x1, t.y1))

