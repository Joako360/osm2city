#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tools.py
misc stuff

Created on Sat Mar 23 18:42:23 2013

@author: tom
"""
import numpy as np
import sys
import textwrap

stats = None

import vec2d
import coordinates
import calc_tile
import parameters

class Interpolator(object):
    """load elevation data from file, interpolate"""
    def __init__(self, filename, fake=False):
        # FIXME: use values from header in filename
        if fake:
            self.fake = True
            self.h = 0.
            print "FAKE!"
            return
        else:
            self.fake = False
        f = open(filename, "r")
        x0, y0, size_x, size_y, step_x, step_y = [float(i) for i in f.readline().split()[1:]]
        ny = len(np.arange(y0, y0+size_y, step_y))
        nx = len(np.arange(x0, x0+size_x, step_x))

        #elev = np.loadtxt(filename)[:,2:]
        elev = np.loadtxt(filename)
        f.close()
        self.x = elev[:,0]
        self.y = elev[:,1]
        self.h = elev[:,4]
        if nx * ny != len(self.x):
            raise ValueError("expected %i, but read %i lines." % (nx*ny, len(self.x)))

        self.min_x = min(self.x)
        self.max_x = max(self.x)
        self.min_y = min(self.y)
        self.max_y = max(self.y)
        self.h = self.h.reshape(ny, nx)
        self.x = self.x.reshape(ny, nx)
        self.y = self.y.reshape(ny, nx)
        #print self.h[0,0], self.h[0,1], self.h[0,2]
        self.dx = self.x[0,1] - self.x[0,0]
        self.dy = self.y[1,0] - self.y[0,0]
        print "dx, dy", self.dx, self.dy

    def __call__(self, p):
        """compute elevation at (x,y) by linear interpolation"""
        if self.fake: return 0.
        global transform
        p = vec2d.vec2d(transform.toGlobal(p))
        if p.x <= self.min_x or p.x >= self.max_x or \
           p.y <= self.min_y or p.y >= self.max_y: return -9999
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


def raster_glob():
    cmin = vec2d.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax) * 0.5
    transform = coordinates.Transformation((center.x, center.y), hdg = 0)
    lmin = vec2d.vec2d(transform.toLocal(cmin.__iter__()))
    lmax = vec2d.vec2d(transform.toLocal(cmax.__iter__()))
    delta = (lmax - lmin)*0.5
    print "Distance from center to boundary in meters (x, y):", delta
    print "Creating elev.in ..."
    raster(transform, "elev.in", -delta.x, -delta.y, 2*delta.x, 2*delta.y, parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)
    
    path = calc_tile.directory_name(center)
    msg = textwrap.dedent("""
    Done. You should now
    - copy elev.in to $FGDATA/Nasal/
    - hide the scenery folder Objects/%s to prevent probing on top of existing objects
    - start FG, open Nasal console, enter 'elev.get()', press execute. This will create /tmp/elev.xml
    - once that's done, copy /tmp/elev.xml to your $PREFIX folder
    - unhide the scenery folder
    """ % path)
    print msg



def raster(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    # --- need $FGDATA/Nasal/elev.nas and elev.in
    #     hide scenery/Objects/e.... folder
    #     in Nasal console: elev.get()
    #     data gets written to /tmp/elev.xml

    # check $FGDATA/Nasal/IOrules
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in np.arange(y0, y0+size_y, step_y):
        for x in np.arange(x0, x0+size_x, step_x):
            lon, lat = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()

def write_map(filename, transform, elev, gmin, gmax):
    lmin = vec2d.vec2d(transform.toLocal((gmin.x, gmin.y)))
    lmax = vec2d.vec2d(transform.toLocal((gmax.x, gmax.y)))
    map_z0 = 0.
    elev_offset = elev(vec2d.vec2d(0,0))
    print "offset", elev_offset

    nx, ny = ((lmax - lmin)/100.).int().list() # 100m raster

    x = np.linspace(lmin.x, lmax.x, nx)
    y = np.linspace(lmin.y, lmax.y, ny)

    u = np.linspace(0., 1., nx)
    v = np.linspace(0., 1., ny)


    out = open("surface.ac", "w")
    out.write(textwrap.dedent("""\
    AC3Db
    MATERIAL "" rgb 1   1    1 amb 1 1 1  emis 0 0 0  spec 0.5 0.5 0.5  shi 64  trans 0
    OBJECT world
    kids 1
    OBJECT poly
    name "surface"
    texture "%s"
    numvert %i
    """ % (filename, nx*ny)))

    for j in range(ny):
        for i in range(nx):
            out.write("%g %g %g\n" % (y[j], (elev(vec2d.vec2d(x[i],y[j])) - elev_offset), x[i]))

    out.write("numsurf %i\n" % ((nx-1)*(ny-1)))
    for j in range(ny-1):
        for i in range(nx-1):
            out.write(textwrap.dedent("""\
            SURF 0x0
            mat 0
            refs 4
            """))
            out.write("%i %g %g\n" % (i  +j*(nx),     u[i],   v[j]))
            out.write("%i %g %g\n" % (i+1+j*(nx),     u[i+1], v[j]))
            out.write("%i %g %g\n" % (i+1+(j+1)*(nx), u[i+1], v[j+1]))
            out.write("%i %g %g\n" % (i  +(j+1)*(nx), u[i],   v[j+1]))
#            0 0 0
#            1 1 0
#            2 1 1
#            3 0 1
    out.write("kids 0\n")
    out.close()
    #print "OBJECT_STATIC surface.ac"

def write_gp(buildings):
    gp = open("buildings.dat", "w")
    for b in buildings:
        gp.write("# %s\n" % b.osm_id)
        for x in b.X:
            gp.write("%g %g\n" % (x[0], x[1]))
        gp.write("\n")

    gp.close()


class Stats(object):
    def __init__(self):
        self.objects = 0
        self.parse_errors = 0
        self.skipped_small = 0
        self.skipped_nearby = 0
        self.skipped_texture = 0
        self.skipped_no_elev = 0
        self.buildings_in_LOD = np.zeros(3)
        self.area_levels = np.array([1,10,20,50,100,200,500,1000,2000,5000,10000,20000,50000])
        self.area_above = np.zeros_like(self.area_levels)
        self.vertices = 0
        self.surfaces = 0
        self.have_pitched_roof = 0
        self.out = None
        self.LOD = np.zeros(3)
        self.nodes_ground = 0
        self.nodes_simplified = 0

    def count(self, b):
        """update stats (vertices, surfaces, area) with given building's data
        """
        self.vertices += b.vertices
        self.surfaces += b.surfaces
        self.have_pitched_roof += not b.roof_flat
        # self.objects += 1 # skipped because we count buildings while OSM parsing
        for i in range(len(self.area_levels))[::-1]:
            if b.area >= self.area_levels[i]:
                self.area_above[i] += 1
                return i
        self.area_above[0] += 1
        return 0

    def count_LOD(self, lod):
        self.LOD[lod] += 1

    def print_summary(self):
        out = sys.stdout
        total_written = self.LOD.sum()
        out.write(textwrap.dedent("""
        total buildings %i
        parse errors    %i
        written         %i
        skipped
          small         %i
          nearby        %i
          no elevation  %i
          no texture    %i
        pitched roof    %i
        ground nodes    %i
          simplified    %i
        vertices        %i
        surfaces        %i
        LOD bare        %i (%2.0f %%)
        LOD rough       %i (%2.0f %%)
        LOD detail      %i (%2.0f %%)
        """ % (self.objects, self.parse_errors, total_written,
               self.skipped_small, self.skipped_nearby, self.skipped_no_elev, self.skipped_texture,
               self.have_pitched_roof,
               self.nodes_ground, self.nodes_simplified,
               self.vertices, self.surfaces,
               self.LOD[0], 100.*self.LOD[0]/total_written,
               self.LOD[1], 100.*self.LOD[1]/total_written,
               self.LOD[2], 100.*self.LOD[2]/total_written)))
        out.write("above\n")
        for i in range(len(self.area_levels)):
            out.write(" %5g m^2  %5i\n" % (self.area_levels[i], self.area_above[i]))
        #print self

def init(new_transform):
    global transform
    transform = new_transform

    global stats
    stats = Stats()
    print "tools: init", stats

if __name__ == "__main__":
    #Parse arguments and eventually override Parameters
    import argparse
    parser = argparse.ArgumentParser(description="tools prepares an elevation grid for Nasal script and then osm2city")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.show()
    raster_glob()

