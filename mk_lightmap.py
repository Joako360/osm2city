#!/usr/bin/env python2
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
import argparse

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
#    return Image.fromarray(n, 'RGBA')
    if 1:
        n[:,:,0] = R #* random.uniform(0.5, 1.0)
        n[:,:,1] = G
        n[:,:,2] = B
        n[:,:,3] = A
    out = (n*255).astype('uint8').copy()
    #out = (n*255).uint8()  #astype('uint8').copy()
    #import copy
    #out = np.uint8(n*255)
    return Image.fromarray(out, 'RGBA')

def empty_RGBA_like(img):
    """return empty RGBA np arrays shaped like img"""
    R, G, B, A = img2RGBA(img)
    R *= 0
    G *= 0
    B *= 0
    A *= 0
    return R, G, B, A

def mk_lit_values_from_float(num, mean_min, mean_max, R_var, G_var, G_minus, B_var, B_minus):
    """auto-gen a list of num window colors. Each color uses given range for
       a mean value; RGB values are offset from mean by given _var"""
    lit_values = []
    for i in range(num):
        mean = random.uniform(mean_min, mean_max)
        R = mean + random.uniform(-R_var, R_var)
        G = mean + random.uniform(-G_var, G_var) - G_minus
        B = mean + random.uniform(-B_var, B_var) - B_minus
        lit_values.append([min(int(value * 255.), 255) for value in [R, G, B]])
    return lit_values


def lit_windows(R, img):
    """Accept R channel. Identify floors and windows. Light them up randomly.
       Return R, img
    """
    # -- Find floors.
    #    We're at a floor's border if the x-averaged red value goes from below
    #    threshold_lo to above threshold_hi.

    import matplotlib.pylab as plt
    width_px, height_px = img.size
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

    # -- light rows of windows per floor with a tuple RGB picked randomly from this list:
#    lit_values = mk_lit_values_from_float(200, mean_min=0.7, mean_max=1.0,
#                                          R_var=0.05, G_var=0.02, G_minus=0.05, B_var=0.1, B_minus=0.15)
    lit_values = np.array([(226, 229, 198), (255, 254, 231), (243, 224, 191),
                           (255, 238, 206), (229, 226, 191), (243, 255, 255),
                           (255, 252, 245)])

    for this_floor_centers in all_centers:
        lit_len = 0
        for x, y in this_floor_centers:
            if lit_len == 0:
                lit_len = int(random.gauss(len(this_floor_centers)/2., len(this_floor_centers)/5))
                lit_len = min(lit_len, 7) # limit row length
                #lit_len = 1
                lit_value = lit_values[random.randint(0,len(lit_values)-1)].copy()
                lit_value *= random.uniform(0.8, 1.) # randomly dim
                alpha = 255
                if random.uniform(0, 1.) < 0.1:
                    lit_value *= 0. # switch off some
                    alpha = 0

            lit_len -= 1
            # -- test if seed pixel is actually red to avoid accidentally
            #    filling background
            if R[y,x] > 0.5:
                print "."
        #            plt.plot(x, y, 'gs')
                ImageDraw.floodfill(img, (x,y), (int(lit_value[0]), int(lit_value[1]), int(lit_value[2]), alpha))

    R, G, B, A = img2RGBA(img)
    return R, G, B, A


def create_red_windows(T):
    """read .py, auto-create raw LM with windows in red on"""
    img = Image.new("RGBA", (T.im.size), (0,0,0,255))

    # -- horizontal borders of windows. Assume some window/gap width
    h_margin_m = 0.5
    window_width_m = 1.1
    window_gap_m = 0.7
    window_offset_m = window_width_m + window_gap_m
    window_u = [[u0, u0 + window_width_m / T.h_size_meters] for u0 in np.arange(h_margin_m, T.h_size_meters - h_margin_m, window_offset_m) / T.h_size_meters]
#    for i, the_split_width_m in enumerate(np.diff(T.h_cuts_m)):
#        if the_split_width_m > 2.5 and the_split_width_m < 5.:

    # -- vertical borders. Use T.v_cuts, assume ...
    lo = 0.4 # ...  a percentage of level height
    hi = 0.9
    window_v = []

    # -- T.v_cuts' origin is lower left (OpenGL convention)
    for j, the_level_height_m in enumerate(np.diff(T.v_cuts_meters)):
        if the_level_height_m > 2.5 and the_level_height_m < 5.:
            v0 = T.v_cuts[j]
            v1 = T.v_cuts[j+1]
            dv = v1 - v0
            window_v.append([v0 + lo * dv, v0 + hi * dv])

    width_px, height_px = img.size
    window_u = np.array(window_u) * width_px
    # -- image origin is upper left, hence 1 - v
    window_v = (1. - np.array(window_v)) * height_px

    # -- make windows red
    rgba = (255, 0, 0, 255)
    for u in window_u:
        for v in window_v:

            dr = ImageDraw.Draw(img)
            dr.rectangle((u[0], v[0], u[1], v[1]), fill=rgba, outline = rgba)

    #img.save('test.png')
    return img

def load_py(image_file_name):
    """try and load .py for given image file name"""
    facades = []
    name, ext = os.path.splitext(image_file_name)
    py_name = name + '.py'
    try:
        execfile(py_name)
    except:
        logging.warn("Error while loading %s" % py_name)
        print "no wo"
        return None

    T = facades[0]
    return T

# ------------------------------------------------------------------------

def main():
    random.seed(42)
    # -- Parse arguments. Command line overrides config file.
    parser = argparse.ArgumentParser(description="mk_lightmap.py creates lightmaps for use with osm2city")
    parser.add_argument("-a", "--auto-windows", action="store_true", help="auto-create lit windows")
    parser.add_argument("-s", "--add-streetlight", action="store_true", help="add streetlight to facade")
    parser.add_argument("-w", "--lit-windows", action="store_true", help="add streetlight to facade")
    parser.add_argument("-f", "--force", action="store_true", help="overwrite _LM")
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL")
    parser.add_argument("FILE", nargs="+")
    args = parser.parse_args()

    for arg_name in args.FILE:

        name, ext = os.path.splitext(arg_name)
        if name.endswith('_LM'):
            logging.warn('Ignoring lightmap %s.' % arg_name)
            continue

        T = load_py(arg_name)
        roof = 'roof' in arg_name


        # -- if we have a .py, use image from Texture object
        #    otherwise assume we have a manual LM == _MA
        if ext == '.py':
            img = None
            img_name = T.filename
            name, ext = os.path.splitext(img_name)
            R, G, B, A = empty_RGBA_like(T.im)
            img = RGBA2img(R, G, B, A)
        else:
            img_name = arg_name
            img = Image.open(img_name)
            R, G, B, A = img2RGBA(img)

        if args.auto_windows:
            if not T:
                logging.warn("Can't auto-create windows for %s because .py is missing" % img_name)
            else:
                img = create_red_windows(T)
                R_win, G, B, A = img2RGBA(img)
        else:
            R_win = R.copy()


        height_px, width_px = R.shape
        aspect = float(height_px) / width_px
        # -- get size in meters, either from .py, from file name or assume something
        if T:
            width_m = T.h_size_meters
            height_m = T.v_size_meters
        else:
            try:
                regex = re.compile("_[0-9]+x[0-9]+m")
                width_m, height_m = [float(v) for v in regex.findall(img_name)[0][1:-1].split('x')]
            except:
                height_m = 10.
                width_m = 10. / aspect

        #R_org = R.copy() # -- save R to identify windows later

        if args.add_streetlight and 1:
            y = np.linspace(1, 0, height_px)
            x = np.linspace(0, 1, width_px)
            X, Y = np.meshgrid(x, y)
            X_m = X * width_m
            Y_m = Y * height_m

            # yellow window light in R
            R = R * A

            if roof:
                A = np.zeros_like(R)
                A += 0.3 - 0.1*Y
            else:
                # street light in G
                # vertical gradient, plus horizonal gaussian for
                v = scipy.stats.norm(loc = 0.5, scale = 0.7).pdf(x)
                gauss_x = v / v.max()

                A = np.zeros_like(R)
                A += 0.3 + 0.7 * np.exp(-Y_m/5.)
                A *= gauss_x
                R = A * 0.564
                G = A * 0.409
                B = A * 0.172
                A = 1.

            img = RGBA2img(R, G, B, A)
#            img.save("wbs_lit.png")

            #plt.show()
        #bl
        if args.lit_windows and 1:
            img.putpixel((5,4), (255,210,20,255))
            imR = RGBA2img(R_win, 0., 0., 0.)
            # -- If I don't do this, Image is readonly. WTF?!?
            imR.putpixel((5,4), (255,210,20,255))
            R, G, B, A = lit_windows(R_win, imR)
#            imR.save("wbs_imR.png")
            img.paste(imR, None, imR)
#            img.save("img.png")

#            imm = RGBA2img(R_win, 0., 0., 1.)
#            imm.save('imtt.png')

        if 0:
            plt.plot(x_sum)
            y = [threshold_hi for tmp in floor_borders]
            print y
            plt.plot(floor_borders, y, 'o')
            plt.show()



        # -- Assemble image from RGBA and save LM
        # A unused. Set A = 1 to ease vis
#        A = np.zeros_like(R) + 1.

        if 0:
            channel_name = 'RGBA'
            for i, channel in enumerate([R, G, B, A]):
                print "%s: %1.2f %1.2f" % (channel_name[i], channel.min(), channel.max())

#        im_out = RGBA2img(R, G, B, A)
        #file_name="a123.png"
        file_name_LM = name + '_LM' + ext
        if os.path.exists(file_name_LM) and not args.force:
            logging.warn("Not overwriting %s" % file_name_LM)
        else:
            img.save(file_name_LM)
        del R, G, B, A, img

    if 0:
        x = np.linspace(0, 1, 11)
        v = scipy.stats.norm(loc = 0.5, scale = 0.2).pdf(x)
        v /= v.max()
        import matplotlib.pyplot as plt
        plt.plot(x, v)
        plt.show()



if __name__ == "__main__":
    main()
    bla
#    img = Image.open("wbs70_36x36m.png")

    height_px, width_px = (10,20)
    n = np.zeros((height_px, width_px, 4))
    R = np.zeros((height_px, width_px)) + 0.
    G = np.zeros((height_px, width_px)) + 1
    B = np.zeros((height_px, width_px)) + 1
    A = np.zeros((height_px, width_px)) + 1.
#    return Image.fromarray(n, 'RGBA')
    if 1:
        n[:,:,0] = R #* random.uniform(0.5, 1.0)
        n[:,:,1] = G
        n[:,:,2] = B
        n[:,:,3] = A
    out = (n*255).astype('uint8')
#    out = (n*255).uint8()  astype('uint8').copy()
    import copy
#    out = copy.copy(np.uint8(n*255))
    img = Image.fromarray(out, 'RGBA')

    img.putpixel((5,4), (255,210,20,255))
    img.save('out.png')

