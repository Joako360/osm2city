# -*- coding: utf-8 -*-
"""
tools.py
misc stuff

Created on Sat Mar 23 18:42:23 2013

@author: tom
"""
import numpy as np

class Interpolator(object):
    """load elevation data from file, interpolate"""
    def __init__(self, filename, fake=False):
        # FIXME: use values from header in filename
        if fake:
            self.fake = True
            self.h = 0.
            return
        else:
            self.fake = False
        elev = np.loadtxt(filename)[:,2:]
        self.x = elev[:,0]
        self.y = elev[:,1]
        self.h = elev[:,2]
        self.min_x = min(self.x)
        self.max_x = max(self.x)
        self.min_y = min(self.y)
        self.max_y = max(self.y)
        self.h = self.h.reshape(2000,2000)
        self.x = self.x.reshape(2000,2000)
        self.y = self.y.reshape(2000,2000)
        #print self.h[0,0], self.h[0,1], self.h[0,2]
        #self.dx = self.h[0,0] - self.x[0,1]
        self.dx = 20.
        self.dy = 20.

    def __call__(self, p):
        """compute elevation at (x,y) by linear interpolation"""
        if self.fake: return 0.
        if p.x <= self.min_x or p.x >= self.max_x or \
           p.y <= self.min_y or p.y >= self.max_y: return 1999
        i = int((p.x - self.min_x)/self.dx)
        j = int((p.y - self.min_y)/self.dy)
        fx = (p.x - self.x[j,i])/self.dx
        fy = (p.y - self.y[j,i])/self.dy
        #print fx, fy, i, j
        h =  (1-fx) * (1-fy) * self.h[j,i] \
           +    fx  * (1-fy) * self.h[j,i+1] \
           + (1-fx) *    fy  * self.h[j+1,i] \
           +    fx  *    fy  * self.h[j+1,i+1]
        return h

    def shift(self, h):
        self.h += h

def raster(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    # check $FGDATA/Nasal/IOrules
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in range(y0, y0+size_y, step_y):
        for x in range(x0, x0+size_x, step_x):
            lat, lon = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()
