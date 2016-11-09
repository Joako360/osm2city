# -*- coding: utf-8 -*-
"""
tools.py
misc stuff

Created on Sat Mar 23 18:42:23 2013½

@author: tom
"""
import logging
import textwrap

import numpy as np
from utils.utilities import Stats, FGElev
import utils.vec2d as ve

stats = None
transform = None


def write_map(filename, transform, fg_elev: FGElev, gmin, gmax):  # FIXME: not used
    lmin = ve.Vec2d(transform.toLocal((gmin.x, gmin.y)))
    lmax = ve.Vec2d(transform.toLocal((gmax.x, gmax.y)))
    elev_offset = fg_elev.probe_elev(ve.Vec2d(0, 0))
    print("offset", elev_offset)

    nx, ny = ((lmax - lmin) / 100.).int().list()  # 100m raster

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
    """ % (filename, nx * ny)))

    for j in range(ny):
        for i in range(nx):
            out.write("%g %g %g\n" % (y[j], (fg_elev.probe_elev(ve.Vec2d(x[i], y[j])) - elev_offset), x[i]))

    out.write("numsurf %i\n" % ((nx - 1) * (ny - 1)))
    for j in range(ny - 1):
        for i in range(nx - 1):
            out.write(textwrap.dedent("""\
            SURF 0x0
            mat 0
            refs 4
            """))
            out.write("%i %g %g\n" % (i + j * nx, u[i], v[j]))
            out.write("%i %g %g\n" % (i + 1 + j * nx, u[i + 1], v[j]))
            out.write("%i %g %g\n" % (i + 1 + (j + 1) * nx, u[i + 1], v[j + 1]))
            out.write("%i %g %g\n" % (i + (j + 1) * nx, u[i], v[j + 1]))
    out.write("kids 0\n")
    out.close()


def write_gp(buildings):  # FIXME: not used
    gp = open("buildings.dat", "w")
    for b in buildings:
        gp.write("# %s\n" % b.osm_id)
        for x in b.X:
            gp.write("%g %g\n" % (x[0], x[1]))
        gp.write("\n")

    gp.close()


def write_one_gp(b, filename):
    npv = np.array(b.X_outer)
    minx = min(npv[:, 0])
    maxx = max(npv[:, 0])
    miny = min(npv[:, 1])
    maxy = max(npv[:, 1])
    dx = 0.1 * (maxx - minx)
    minx -= dx
    maxx += dx
    dy = 0.1 * (maxy - miny)
    miny -= dy
    maxy += dy

    gp = open(filename + '.gp', 'w')
    term = "png"
    ext = "png"
    gp.write(textwrap.dedent("""
    set term %s
    set out '%s.%s'
    set xrange [%g:%g]
    set yrange [%g:%g]
    set title "%s"
    unset key
    """ % (term, filename, ext, minx, maxx, miny, maxy, b.osm_id)))
    i = 0
    for v in b.X_outer:
        i += 1
        gp.write('set label "%i" at %g, %g\n' % (i, v[0], v[1]))

    gp.write("plot '-' w lp\n")
    for v in b.X_outer:
        gp.write('%g %g\n' % (v[0], v[1]))
    gp.close()


def init(new_transform):
    global transform
    transform = new_transform

    global stats
    stats = Stats()
    logging.debug("tools: init %s" % stats)
