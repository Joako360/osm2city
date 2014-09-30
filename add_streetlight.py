#!/usr/bin/env python
"""
osm2city uses
- red channel for window lights
- green channel for ambient street lights shining onto facade.
- blue and alpha unused

This script
1. reads window LM from given file into red channel
2. adds 'ambient' light to facade textures. The ambient light depends on the type of texture, deduced from the file name.
  If the file name contains 'roof':
  - add small constant + vertical gradient to green channel
  Otherwise:
  - add vertical gradient and horizontal gaussian to green channel
3. saves to LM/filename.png
"""

import numpy as np
import scipy.stats
from PIL import Image
from copy import copy
from pdb import pm
import sys
import random

if 0:
    x = np.linspace(0, 1, 11)
    v = scipy.stats.norm(loc = 0.5, scale = 0.2).pdf(x)
    v /= v.max()
    import matplotlib.pyplot as plt
    plt.plot(x, v)
    plt.show()
    bla

try:
    file_name = sys.argv[1]
except:
    print "usage: %s image" % sys.argv[0]
    sys.exit(-1)

print file_name
#file_name = "DSCF9503_noroofsec_LM.png"
img = Image.open(file_name)

roof = 'roof' in file_name

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

aspect = float(height_px) / width_px
height_m = 10. # TODO: read from meta data
width_m = 10. / aspect
y = np.linspace(1, 0, height_px)
x = np.linspace(0, 1, width_px)

X, Y = np.meshgrid(x, y)

X_m = X * width_m
Y_m = Y * height_m



# window light in R
R = R * A

if roof:
    G = copy(zero)
    G += 0.3 - 0.1*Y
else:
    # street light in G
    # vertical gradient, plus horizonal gaussian for
    v = scipy.stats.norm(loc = 0.5, scale = 0.7).pdf(x)
    gauss_x = v / v.max()

    G = copy(zero)
    G += 0.3 + 0.7 * np.exp(-Y_m/5.)
    G *= gauss_x


# B and A unused. Set A = 1 to ease vis
B *= 0.
A = zero + 1.

n = np.zeros((height_px, width_px, 4))
n[:,:,0] = R * random.uniform(0.5, 1.0)
n[:,:,1] = G
n[:,:,2] = B
n[:,:,3] = A

channel_name = 'RGBA'
for i, channel in enumerate([R, G, B, A]):
    print "%s: %1.2f %1.2f" % (channel_name[i], channel.min(), channel.max())


out = (n*255).astype('uint8')
im_out = Image.fromarray(out, 'RGBA')

im_out.save('LM/%s' % file_name)
