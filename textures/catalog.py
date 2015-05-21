#!/usr/bin/env python2
# -*- coding: utf-8 -*-

from textures.texture import Texture
import os
import logging

def append_facades_test(tex_prefix, facades):
    """---------------- ADD YOUR FACADE TEXTURES HERE -------------------"""

    # -- testing
    facades.append(Texture(tex_prefix + 'tex.src/10storymodernconcrete.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/11storymodernsq.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    facades.append(Texture(tex_prefix + 'tex.src/12storyconcrglassblkwhtmodern.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443,  1204, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/12storygovtmodern.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/14storyconcrwhite.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 577, 712, 846, 1204, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


def append_facades_us(tex_prefix, facades):

    
# here    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/3storystorefronttown.jpg',
        h_size_meters=9, h_cuts=[], h_can_repeat=False,
        v_size_meters=9, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/salmon_3_story_0_scale.jpg',
        h_size_meters=8, h_cuts=[], h_can_repeat=False,
        v_size_meters=8, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/2stFancyconcrete1.jpg',
        h_size_meters=14, h_cuts=[], h_can_repeat=False,
        v_size_meters=7, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-dcwhiteconcr2st.jpg',
        h_size_meters=16, h_cuts=[], h_can_repeat=False,
        v_size_meters=8, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-dctbrickcomm2st.jpg',
        h_size_meters=21, h_cuts=[], h_can_repeat=False,
        v_size_meters=5.25, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/USUAE-4stCommercial.jpg',
        h_size_meters=20, h_cuts=[], h_can_repeat=False,
        v_size_meters=10, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-OfficeComm-2st.jpg',
        h_size_meters=15, h_cuts=[], h_can_repeat=False,
        v_size_meters=3.75, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-1stCommWarehousewhite1.jpg',
        h_size_meters=15, h_cuts=[], h_can_repeat=False,
        v_size_meters=3.75, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-1stCommBrick2.jpg',
        h_size_meters=15, h_cuts=[], h_can_repeat=False,
        v_size_meters=3.75, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/commercial/US-1stCommStFront3.jpg',
        h_size_meters=10, h_cuts=[], h_can_repeat=False,
        v_size_meters=5, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/residential/tiles/USUAE-8stTile_rep.jpg',
        h_size_meters=15, h_cuts=[], h_can_repeat=False,
        v_size_meters=30, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True, height_min=10,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/residential/6storybrickbrown1.jpg',
        h_size_meters=21, h_cuts=[], h_can_repeat=False,
        v_size_meters=21, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/residential/5storyCondo_concrglasswhite.jpg',
        h_size_meters=14, h_cuts=[], h_can_repeat=False,
        v_size_meters=28, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/residential/US-CityCondo_brick_4st.jpg',
        h_size_meters=16, h_cuts=[], h_can_repeat=False,
        v_size_meters=16, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    
    facades.append(Texture(tex_prefix + 'tex.src/us/residential/US-CityCondo2st.jpg',
        h_size_meters=11, h_cuts=[], h_can_repeat=False,
        v_size_meters=11, v_cuts=[], v_can_repeat=False,
        v_align_bottom=True,
        requires=['roof:color:gray'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

def append_dynamic(tex_prefix, facades): 
    """--- Dynamically runs py files in tex.src ---
    In texture .py files, we load a texture like so:
      Texture(tex_prefix + 'filename.jpg' ...
    tex_prefix is the path to the texture file, and should end in os.sep
    """   
    for subdir, dirs, files in os.walk(tex_prefix, topdown=True):
        for file in files:
                if not file.endswith("py"):
                    continue 
                logging.debug("Executing %s "% (subdir + os.sep + file))
                tex_prefix = subdir + os.sep
                try:
                    execfile(subdir + os.sep + file)
                except:
                    logging.exception("Error while running %s"%file)
            

def append_roofs(tex_prefix, roofs):
    """------------ ADD YOUR ROOF TEXTURES HERE -------------------"""

#    roofs.append(Texture(tex_prefix + 'tex.src/roof_tiled_black',
#                         1., [], True, 1., [], False, provides=['color:black']))
#    roofs.append(Texture(tex_prefix + 'tex.src/roof_tiled_red',
#                         1., [], True, 1., [], False, provides=['color:red']))

    roofs.append(Texture(tex_prefix + 'roof_red1.png',
        31.8, [], True, 16.1, [], False, provides=['color:red', 'compat:roof-pitched']))

    roofs.append(Texture(tex_prefix + 'roof_black1.png',
        31.8, [], True, 16.1, [], False, provides=['color:black', 'compat:roof-pitched']))

    roofs.append(Texture(tex_prefix + 'roof_black4.jpg',
        6., [], True, 3.5, [], False, provides=['color:black', 'compat:roof-pitched']))

    roofs.append(Texture(tex_prefix + 'roof_gen_black1.png',
        100., [], True, 100., [], False, provides=['color:black', 'compat:roof-flat']))

    roofs.append(Texture(tex_prefix + 'roof_gen_gray1.png',
        100., [], True, 100., [], False, provides=['color:gray', 'compat:roof-flat']))
    roofs.append(Texture(tex_prefix + 'roof_gen_gray2.png',
        100., [], True, 100., [], False, provides=['color:gray', 'compat:roof-flat']))

    roofs.append(Texture(tex_prefix + 'roof_gen_gray3.png',
        100., [], True, 100., [], False, provides=['color:gray', 'compat:roof-flat']))

    roofs.append(Texture(tex_prefix + 'roof_gen_brown1.png',
        100., [], True, 100., [], False, provides=['color:brown', 'compat:roof-flat']))

#    roofs.append(Texture(tex_prefix + 'roof_black2',
#                             1.39, [], True, 0.89, [], True, provides=['color:black']))
#    roofs.append(Texture(tex_prefix + 'roof_black3',
#                             0.6, [], True, 0.41, [], True, provides=['color:black']))

#    roofs.append(Texture(tex_prefix + 'roof_black3_small_256x128',
#                             0.25, [], True, 0.12, [], True, provides=['color:black']))
