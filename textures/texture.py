import numpy as np
from PIL import Image
import logging

class Texture(object):
    """
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
        - roof:color:red|black

    roof:
      provides
        - color:black (red, ..)
        - shape:flat  (pitched, ..)

    """
    def __init__(self, filename,
                 h_size_meters=None, h_cuts=[], h_can_repeat=False, \
                 v_size_meters=None, v_cuts=[], v_can_repeat=False, \
                 height_min = 0, height_max = 9999, \
                 v_align_bottom = False, \
                 provides = [], requires = [], levels=None):
        self.filename = filename
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
        # roof type, color
#        self.v_min = v_min
#        self.v_max = v_max

        try:
            self.im = Image.open(self.filename)
        except:
             logging.warning("Skipping non-existing texture %s" % self.filename)
             return
        self.width_px, self.height_px = self.im.size
        image_aspect = self.height_px / self.width_px

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
                # an exception instead would prohobit the nice, simple structure of catalog.py
                self.filename = "" 
                return
            else:
                self.v_size_meters = levels * 3.3                 
            
        if h_size_meters: 
            self.h_size_meters = h_size_meters
        else:
            self.h_size_meters = self.v_size_meters / image_aspect
            print "No hsize, using image aspect %i x %i = %g. h_size = %g v_size = %g" % \
              (self.width_px, self.height_px, image_aspect, self.h_size_meters, self.v_size_meters)
            
        # aspect = v / h
        if v_cuts == []:
            v_cuts = [1,2,3,4,5,6,7,8,9,10]
            
        if v_cuts != None:
            v_cuts.insert(0,0)
            self.v_cuts = np.array(v_cuts, dtype=np.float)
            if len(self.v_cuts) > 1:
                # FIXME            test for not type list
                self.v_cuts /= self.v_cuts[-1]
#                print self.v_cuts
                # -- Gimp origin is upper left, convert to OpenGL lower left
                self.v_cuts = (1. - self.v_cuts)[::-1]
#                print self.v_cuts
        else:
            self.v_cuts = 1.
        self.v_cuts_meters = self.v_cuts * self.v_size_meters

        self.v_can_repeat = v_can_repeat

        if not self.v_can_repeat:
            self.height_min = self.v_cuts_meters[0]
            self.height_max = self.v_size_meters

        if h_cuts == []:
            h_cuts = [1,2,3,4,5,6,7,8,9,10]

        self.h_cuts = np.array(h_cuts, dtype=np.float)
        #print "h1", self.h_cuts
        #print "h2", h_cuts

        if h_cuts == None:
            self.h_cuts = np.array([1.])
        elif len(self.h_cuts) > 1:
            self.h_cuts /= self.h_cuts[-1]
        self.h_cuts_meters = self.h_cuts * self.h_size_meters
        self.h_can_repeat = h_can_repeat

        if not self.h_can_repeat:
            self.width_min = self.h_cuts_meters[0]
            self.width_max = self.h_size_meters

        if self.h_can_repeat + self.v_can_repeat > 1:
            raise ValueError('%s: Textures can repeat in one direction only. '\
              'Please set either h_can_repeat or v_can_repeat to False.' % self.filename)

    def x(self, x):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
            return self.y0 + x * self.sy
        else:
            return self.x0 + x * self.sx

    def y(self, y):
        """given non-dimensional texture coord, return position in atlas"""
        if self.rotated:
#            print "Yr self.x0 + y * self.sx  %g + (%s) * %g:", (self.x0, str(y), self.sx)
            return self.x0 + y * self.sx
        else:
#            print "YY self.y0 + y * self.sy : %g + (%s) * %g" % (self.y0, str(y), self.sy)
            return self.y0 + y * self.sy

    def __str__(self):
        return "<%s> x0,1 %4.2f %4.2f  y0,1 %4.2f %4.2f  sh,v %4.2fm %4.2fm" % \
                (self.filename, self.x0, self.x1, self.y0, self.y1, \
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
        #self.h_cuts[np.abs(self.h_cuts - frac).argmin()]
        #bla
