#!/usr/bin/env python
"""
osm2city uses a LM with channels indicating special lights:
- R for yellowish lights -- mostly for windows (lighmap n="0")
- G for orange lights -- ambient street lights shining onto facade (n="1").
- B for white lights (n="2") -- e.g., logos, but also windows
- alpha unused

This script
- reads window LM from given file into red channel
- tries to find windows in R channel, lights them up randomly.
- adds 'ambient' light to facade textures. The ambient light depends on the type of texture, deduced from the file name.
  If the file name contains 'roof':
  - add small constant + vertical gradient to green channel
  Otherwise:
  - add vertical gradient and horizontal gaussian to green channel
- saves to LM/filename.png

TODO:
- automatically add windows to R, from .py, if arg endswith .py
- try new RGB LM scheme


"""

from PIL import Image, ImageDraw

import numpy as np
import scipy.stats
from copy import copy
from pdb import pm
import sys
import random
import re
import os
import logging


def img2RGBA(img):
    """convert PIL image to individual np arrays for R,G,B,A"""
    n = np.array(img)/255.
    height_px, width_px = n.shape[:2]
    if len(n.shape) == 2:
        n_channels = 1
    else:
        n_channels = n.shape[2]
    
    zero = np.zeros((height_px, width_px))
    
    if n_channels == 1:
        R = copy(n)
        G = copy(zero)
        B = copy(zero)
        A = copy(zero) + 1.
    elif n_channels >= 3:
        R = copy(n[:,:,0])
        G = copy(n[:,:,1])
        B = copy(n[:,:,2])
        if n_channels == 4:
            A = copy(n[:,:,3])
        else:
            A = copy(zero) + 1.
    else:
        raise NotImplementedError("can't handle number of channels")
    return R, G, B, A

def RGBA2img(R, G, B, A):
    height_px, width_px = R.shape
    n = np.zeros((height_px, width_px, 4))
    n[:,:,0] = R #* random.uniform(0.5, 1.0)
    n[:,:,1] = G
    n[:,:,2] = B
    n[:,:,3] = A
    out = (n*255).astype('uint8')
    return Image.fromarray(out, 'RGBA')

def RGBAlike(img):
    """return empty RGBA np arrays shaped like img"""
    R, G, B, A = img2RGBA(img)
    R *= 0
    G *= 0
    B *= 0
    A *= 0
    return R, G, B, A


def lit_windows(R, img):
    """Accept R channel. Identify floors and windows. Light them up randomly.
       Return R, img
    """
    # -- Find floors.
    #    We're at a floor's border if the x-averaged red value goes from below
    #    threshold_lo to above threshold_hi.
    
    import matplotlib.pylab as plt
    x_sum = R.sum(axis=1) / width_px
    threshold_lo = 0.2
    threshold_hi = 0.4
    on_lo = x_sum[0] < threshold_lo
    floor_borders = []
    all_centers = [] # 2-D list of window centers
    i = 1
    while i < len(x_sum):
        if on_lo:
            if x_sum[i] > threshold_hi:
                on_lo = False
                floor_border_up = i
        else:
            if x_sum[i] < threshold_lo:
                on_lo = True
                floor_border_down = i
                floor_borders.append((floor_border_up, floor_border_down))
        i += 1
    
    # -- Now, at each floor, find windows in a similar fashion.
    for floor_border_up, floor_border_down in floor_borders:
        y_sum = R[floor_border_up:floor_border_down].sum(axis=0) / (floor_border_down-floor_border_up)
        on_lo = y_sum[0] < threshold_lo
        window_borders = []
        center_y = (floor_border_up + floor_border_down)/2
        i = 1
        while i < len(y_sum):
            if on_lo:
                if y_sum[i] > threshold_hi:
                    on_lo = False
                    border_up = i
            else:
                if y_sum[i] < threshold_lo:
                    on_lo = True
                    border_down = i
                    window_borders.append((border_up, border_down))
    
            i += 1

        # -- list of window centers for our floor    
        this_floor_centers = []
        for border_up, border_down in window_borders:
            center_x = (border_up + border_down)/2
            this_floor_centers.append((center_x, center_y))
            #X = [border_up, border_down, border_down, border_up, border_up]
            #Y = [floor_border_up, floor_border_up, floor_border_down, floor_border_down, floor_border_up]
            #plt.plot(X, Y, 'r-')
        all_centers.append(this_floor_centers)
        if 0:    
            y = [threshold_hi for tmp in window_borders]
            plt.plot(y_sum)
            plt.plot(window_borders, y, 'o') 
            plt.show()
            plt.clf()
        
    # -- light rows of windows per floor with a pair of (R, B) picked randomly from this list:
    lit_values = np.array([[30, 0], [100, 0], [150, 0], [0, 50], [0, 70]]) * 1.5
    for this_floor_centers in all_centers:
        lit_len = 0
        for x, y in this_floor_centers:
            if lit_len == 0:
                lit_len = int(random.gauss(len(this_floor_centers)/2., len(this_floor_centers)/5))
                lit_value = lit_values[random.randint(0,len(lit_values)-1)]
    
            lit_len -= 1
            # -- test if seed pixel is actually red to avoid accidentally 
            #    filling background
            if R[y,x] > 0.5:
        #            plt.plot(x, y, 'gs')
                ImageDraw.floodfill(img, (x,y), (int(lit_value[0]), 0, int(lit_value[1]), 255))

    R, G, B, A = img2RGBA(img)
    return R, G, B, A


def create_windows(py_name):
    """read .py, auto-create raw LM with windows in red on"""
    facades = []
    try:
        execfile(py_name)
    except:
        logging.exception("Error while running %s" % py_name)

    T = facades[0]
    img = Image.open(T.filename)
    img = Image.new("RGBA", (img.size), (0,0,0,255))
    
    # -- horizontal borders of windows. Assume some window/gap width
    h_margin_meters = 0.5
    window_width_meters = 1.1
    window_gap_meters = 0.7
    window_offset_meters = window_width_meters + window_gap_meters
    window_u = [[u0, u0 + window_width_meters / T.h_size_meters] for u0 in np.arange(h_margin_meters, T.h_size_meters - h_margin_meters, window_offset_meters) / T.h_size_meters]
#    for i, the_split_width_meters in enumerate(np.diff(T.h_cuts_meters)):
#        if the_split_width_meters > 2.5 and the_split_width_meters < 5.:
        
    # -- vertical borders. Use T.v_cuts, assume ...
    lo = 0.4 # ...  a percentage of level height
    hi = 0.9
    window_v = []
    for j, the_level_height_meters in enumerate(np.diff(T.v_cuts_meters)):
        if the_level_height_meters > 2.5 and the_level_height_meters < 5.:
            v0 = T.v_cuts[j]
            v1 = T.v_cuts[j+1]
            dv = v1 - v0
            # origin is upper left, so vertical is upside-down, hence 1-
            window_v.append([v0 + (1-hi) * dv, v0 + (1-lo) * dv])
    width_px, height_px = img.size
    window_u = np.array(window_u) * width_px
    window_v = np.array(window_v) * height_px

    # -- make windows red
    rgba = (255, 0, 0, 255)
    for u in window_u:
        for v in window_v:
                                    
            dr = ImageDraw.Draw(img)
            dr.rectangle((u[0], v[0], u[1], v[1]), fill=rgba, outline = rgba)
    
    #img.save('test.png')
    return img
# ------------------------------------------------------------------------

if 0:
    x = np.linspace(0, 1, 11)
    v = scipy.stats.norm(loc = 0.5, scale = 0.2).pdf(x)
    v /= v.max()
    import matplotlib.pyplot as plt
    plt.plot(x, v)
    plt.show()

#print file_name
#file_name = "DSCF9503_noroofsec_LM.png"
#file_name = "facade_modern_commercial_46x169m_LM.jpg"
#file_name = "a.png"

try:
    file_name = sys.argv[1]
except:
    print "usage: %s image" % sys.argv[0]
    sys.exit(-1)

roof = 'roof' in file_name

name, ext = os.path.splitext(file_name)
if name.endswith('_LM'):
    # -- if we're given a LM, use it, assuming it contains windows marked in red
    img = Image.open(file_name)
else:
    # ... otherwise auto-get windows. Need .py
    py_name = sys.argv[2]
    img = create_windows(py_name)

R, G, B, A = img2RGBA(img)
#pixel = img.load()
#a = PIL.ImageDraw.floodfill(img, (10,60), (244,0,0,250))
#img.save('aout.png')


height_px, width_px = R.shape
aspect = float(height_px) / width_px

try:
    regex = re.compile("_[0-9]+x[0-9]+m")
    width_m, height_m = [float(v) for v in regex.findall(file_name)[0][1:-1].split('x')]
except:
    height_m = 10.
    width_m = 10. / aspect

y = np.linspace(1, 0, height_px)
x = np.linspace(0, 1, width_px)

X, Y = np.meshgrid(x, y)

X_m = X * width_m
Y_m = Y * height_m

# yellow window light in R
R = R * A


R, G, B, A = lit_windows(R, img)

if roof:
    G = np.zeros_like(R)
    G += 0.3 - 0.1*Y
else:
    # street light in G
    # vertical gradient, plus horizonal gaussian for
    v = scipy.stats.norm(loc = 0.5, scale = 0.7).pdf(x)
    gauss_x = v / v.max()

    G = np.zeros_like(R)
    G += 0.3 + 0.7 * np.exp(-Y_m/5.)
    G *= gauss_x
        
#plt.show()


if 0:    
    plt.plot(x_sum)
    y = [threshold_hi for tmp in floor_borders]
    print y
    plt.plot(floor_borders, y, 'o') 
    plt.show()

# -- Assemble image from RGBA and save LM
# A unused. Set A = 1 to ease vis
A = np.zeros_like(R) + 1.

channel_name = 'RGBA'
for i, channel in enumerate([R, G, B, A]):
    print "%s: %1.2f %1.2f" % (channel_name[i], channel.min(), channel.max())

im_out = RGBA2img(R, G, B, A)
#file_name="a123.png"
im_out.save('LM/%s' % file_name)
