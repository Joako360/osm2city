#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
tools.py
misc stuff

Created on Sat Mar 23 18:42:23 2013½

@author: tom
"""
import argparse
import cPickle
import csv
import logging
import math
import os
import os.path as osp
import Queue
import re
import shutil
import subprocess
import sys
import textwrap
import time

import matplotlib.pyplot as plt
import numpy as np

import batch_processing.fg_telnet as telnet
import calc_tile
import coordinates
import parameters
import setup
import vec2d as ve

from _collections import defaultdict


stats = None
transform = None


def get_osm2city_directory():
    """Determines the absolute path of the osm2city root directory.

    Used e.g. when copying roads.eff, elev.nas and other resources.
    """
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]
    return my_dir


class Interpolator(object):
    """load elevation data from file, interpolate"""
    def __init__(self, filename, fake=False, clamp=False):
        """If clamp = False, out-of-bounds elev probing returns -9999.
           Otherwise, return elev at closest boundary.
           If fake_elev != False, don't probe elev. Instead, always return given value.
        """
        # FIXME: use values from header in filename
        # FIXME: could save lots of mem by not storing regular grid XY
        if fake:
            self.h = fake
            self.fake = True
            return
        else:
            self.fake = False
        self.clamp = clamp
        logging.debug("reading elev from %s" % filename)
        f = open(filename, "r")
        x0, y0, size_x, size_y, self.step_x, self.step_y = [float(i) for i in f.readline().split()[1:]]
        f.close()

        nx = len(np.arange(x0, x0 + size_x, self.step_x))
        ny = len(np.arange(y0, y0 + size_y, self.step_y))

        # elev = np.loadtxt(filename)

        elev = np.zeros((nx * ny, 5))
        with open(filename, 'r') as f:
            reader = csv.reader(f, delimiter=' ')
            tmp = reader.next()
            i = 0
            for row in reader:
                tmp = np.array(row)
                if len(tmp) == 5:
                    elev[i,:] = tmp
                    i += 1

        self.x = elev[:, 0]  # -- that's actually lon
        self.y = elev[:, 1]  #                and lat
        self.h = elev[:, 4]
        if nx * ny != len(self.x):
            raise ValueError("expected %i, but read %i lines." % (nx * ny, len(self.x)))

        self.min = ve.vec2d(min(self.x), min(self.y))
        self.max = ve.vec2d(max(self.x), max(self.y))
        self.h = self.h.reshape(ny, nx)
        self.x = self.x.reshape(ny, nx)
        self.y = self.y.reshape(ny, nx)
        # print self.h[0,0], self.h[0,1], self.h[0,2]
        self.dx = self.x[0, 1] - self.x[0, 0]
        self.dy = self.y[1, 0] - self.y[0, 0]
        print "dx, dy", self.dx, self.dy
        print "min %s  max %s" % (self.min, self.max)

    def _move_to_boundary(self, x, y):
        if x <= self.min.x:
            x = self.min.x
        elif x >= self.min.x:
            x = self.min.x
        if y <= self.min.x:
            y = self.min.x
        elif y >= self.min.x:
            y = self.min.x
        return x, y

    def __call__(self, position, is_global=False):
        """compute elevation at (x,y) by linear interpolation
           Work with global coordinates: x, y is in fact lon, lat.
        """
        if self.fake:
            return 0.
            #return x + y
        global transform

        if not is_global:
            x, y = transform.toGlobal(position)
        else:
            x, y = position

        if self.clamp:
            x, y = self._move_to_boundary(x, y)
        else:
            if x <= self.min.x or x >= self.max.x:
                plt.plot(x, y, 'r.')
                return -9999
            elif y <= self.min.y or y >= self.max.y:
                plt.plot(x, y, 'r.')
                return -9999

        #plt.plot(x, y, 'k.')
        i = int((x - self.min.x)/self.dx)
        j = int((y - self.min.y)/self.dy)
        fx = (x - self.x[j, i])/self.dx
        fy = (y - self.y[j, i])/self.dy
        # rounding errors at boundary.
        if j + 1 >= self.h.shape[0]:
            j -= 1
        if i + 1 >= self.h.shape[1]:
            i -= 1
        # print fx, fy, i, j
        h = (1 - fx) * (1 - fy) * self.h[j, i] \
           + fx * (1 - fy) * self.h[j, i + 1] \
           + (1 - fx) * fy * self.h[j + 1, i] \
           + fx * fy * self.h[j + 1, i + 1]
        return h

    def shift(self, h):
        self.h += h

    def write(self, filename, downsample=2):
        """Interpolate, write to file. Useful to create a coarser grid that loads faster"""
        x = self.x[::downsample, ::downsample]
        y = self.y[::downsample, ::downsample]
        h = self.h[::downsample, ::downsample]
        ny, nx = x.shape
        zero = np.zeros_like(x).ravel()
        size_x = self.step_x * downsample * nx
        size_y = self.step_y * downsample * ny
        header = "%g %g %g %g %g %g" \
            % (0, 0, size_x, size_y, self.step_x * downsample, self.step_y * downsample)
        X = np.vstack((x.ravel(), y.ravel(), zero, zero, h.ravel())).transpose()
        np.savetxt(filename, X, header=header, fmt=["%1.8f", "%1.8f", "%g", "%g", "%1.2f"])

    def save_cache(self):
        """To keep the interface consistent"""
        pass


class Probe_fgelev(object):
    """A drop-in replacement for Interpolator. Probes elevation via fgelev.
       Make sure to use the patched version of fgelev (see osm2city/fgelev/) or
       performance is likely to be terrible.

       By default, queries are cached. Call save_cache() to
       save the cache to disk before freeing the object.
    """
    def __init__(self, fake=False, cache=True, auto_save_every=50000):
        """Open pipe to fgelev.
           Unless disabled by cache=False, initialize the cache and try to read
           it from disk. Automatically save the cache to disk every auto_save_every misses.
           If fake=True, never do any probing and return 0 on all queries.
        """
        if fake:
            self.h = fake
            self.fake = True
            return
        else:
            self.fake = False

        self.auto_save_every = auto_save_every
        self.h_offset = 0
        self.fgelev_pipe = None
        self.record = 0

        if cache:
            self.pkl_fname = parameters.PREFIX + os.sep + 'elev.pkl'
            try:
                logging.info("Loading %s", self.pkl_fname)
                fpickle = open(self.pkl_fname, 'rb')
                self._cache = cPickle.load(fpickle)
                fpickle.close()
                logging.info("OK")
            except IOError, reason:
                logging.warn("Loading elev cache failed (%s)", reason)
                self._cache = {}
            except EOFError, reason:
                logging.warn("Loading elev cache failed (%s)", reason)
                self._cache = {}
        else:
            self._cache = None

    def open_fgelev(self):
        logging.info("Spawning fgelev")
        path_to_fgelev = parameters.FG_ELEV

        fgelev_cmd = path_to_fgelev + ' --expire 1000000 --fg-scenery ' + parameters.PATH_TO_SCENERY
        logging.info("cmd line: " + fgelev_cmd)
        self.fgelev_pipe = subprocess.Popen(fgelev_cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        # -- This should catch spawn errors, but it doesn't. We
        #    check for sane return values on fgelev calls later.
#        if self.fgelev_pipe.poll() != 0:
#            raise RuntimeError("Spawning fgelev failed.")

    def save_cache(self):
        """save cache to disk"""
        if self.fake:
            return
        fpickle = open(self.pkl_fname, 'wb')
        cPickle.dump(self._cache, fpickle, -1)
        fpickle.close()

    def shift(self, h):
        self.h_offset += h

    def __call__(self, position, is_global=False, check_btg=False):
        """return elevation at (x,y). We try our cache first. Failing that,
           call fgelev.
        """
        def really_probe(position):
            if check_btg:
                btg_file = parameters.PATH_TO_SCENERY + os.sep + "Terrain" \
                           + os.sep + calc_tile.directory_name(position) + os.sep \
                           + calc_tile.construct_btg_file_name(position)
                print calc_tile.construct_btg_file_name(position)
                if not os.path.exists(btg_file):
                    logging.error("Terrain File " + btg_file + " does not exist. Set scenery path correctly or fly there with TerraSync enabled")
                    sys.exit(2)

            if not self.fgelev_pipe:
                self.open_fgelev()
            if math.isnan(position.lon) or math.isnan(position.lat):
                logging.error("Nan encountered while probing elevation")
                return -100

            try:
                self.fgelev_pipe.stdin.write("%i %1.10f %1.10f\r\n" % (self.record, position.lon, position.lat))
            except IOError, reason:
                logging.error(reason)

            empty_lines = 0
            try:
                line = ""
                while line == "" and (empty_lines) < 20:
                    empty_lines += 1
                    line = self.fgelev_pipe.stdout.readline().strip()
                elev = float(line.split()[1]) + self.h_offset
            except IndexError, reason:
                self.save_cache()
                if empty_lines > 1:
                    logging.fatal("Skipped %i lines" % empty_lines)
                logging.fatal("%i %g %g" % (self.record, position.lon, position.lat))
                logging.fatal("fgelev returned <%s>, resulting in %s. Did fgelev start OK (Record : %i)?"
                              , line, reason, self.record)
                raise RuntimeError("fgelev errors are fatal.")

            return elev

        if self.fake:
            return self.h

        global transform
        if not is_global:
            position = ve.vec2d(transform.toGlobal(position))
        else:
            position = ve.vec2d(position[0], position[1])

        self.record += 1
        if self._cache is None:
            return really_probe(position)

        key = (position.lon, position.lat)
        try:
            elev = self._cache[key]
            # logging.debug("hit %s %g" % (str(key), elev))
            return elev
        except KeyError:
            #logging.debug("miss (%i) %s" % (len(self._cache), str(key)))
            elev = really_probe(position)
            #logging.debug("   %g" % elev)
            self._cache[key] = elev

            if self.auto_save_every and len(self._cache) % self.auto_save_every == 0:
                self.save_cache()
            return elev


def test_fgelev(cache, N):
    """simple testing for Probe_fgelev class"""
    elev = Probe_fgelev(cache=cache)
    delta = 0.3
    check_btg = True
    p = ve.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    elev(p, True, check_btg)  # -- ensure fgelev is up and running
    #p = vec2d(parameters.BOUNDARY_WEST+delta, parameters.BOUNDARY_SOUTH+delta)
    # elev(p, True, check_btg) # -- ensure fgelev is up and running
    nx = ny = N
    ny = 1
    # X = np.linspace(parameters.BOUNDARY_WEST, parameters.BOUNDARY_WEST+delta, nx)
    # Y = np.linspace(parameters.BOUNDARY_SOUTH, parameters.BOUNDARY_SOUTH+delta, ny)
    X = np.linspace(parameters.BOUNDARY_WEST, parameters.BOUNDARY_EAST, nx)
    Y = np.linspace(parameters.BOUNDARY_SOUTH, parameters.BOUNDARY_NORTH, ny)


    # cache? N  speed
    # True   10 30092 records/s
    # False  10 17914 records/s
    # True   20 27758 records/s
    # False  20 18010 records/s
    # True   50 29937 records/s
    # False  50 18481 records/s
    # True  100 30121 records/s
    # False 100 18230 records/s
    # True  200 29868 records/s
    # False 200 18271 records/s

    start = time.time()
    s = []
    i = 0
    for y in Y:
        for x in X:
            p = ve.vec2d(x, y)
            print i / 2,
            e = elev(p, True, check_btg)
            i += 1
            e = elev(p, True)
            i += 1
#            e = elev(p, True)
#            i += 1
            # s.append("%s %g" % (str(p), e))
    end = time.time()
    # for item in s:
    #    print item
    print cache, N, "%d records/s" % (i / (end - start))
    elev.save_cache()


def raster_glob(prevent_overwrite=False):
    cmin = ve.vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = ve.vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax) * 0.5
    transform = coordinates.Transformation((center.x, center.y), hdg=0)
    lmin = ve.vec2d(transform.toLocal(cmin.__iter__()))
    lmax = ve.vec2d(transform.toLocal(cmax.__iter__()))
    delta = (lmax - lmin) * 0.5
    logging.info("Distance from center to boundary in meters: x=%d, y=%d", delta.x, delta.y)

    err_msg = "Unknown elevation probing mode : '%s'. Use Manual, Telnet or Fgelev for parameter ELEV_MODE " \
              % parameters.ELEV_MODE
    if parameters.ELEV_MODE == 'Manual':
        logging.info("Creating elev.in ...")
        fname = parameters.PREFIX + os.sep + "elev.in"
        _raster(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y
                , parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)

        path = calc_tile.directory_name(center)
        msg = textwrap.dedent("""
        Done. You should now
        - Copy elev.in to FGData/Nasal/
        - Hide the scenery folder Objects/%s to prevent probing on top of existing objects
        - Start FG, open Nasal console, enter 'elev.get_elevation()', press execute. This will create /Export/elev.out
        - Once that's done, copy /Export/elev.out to your $PREFIX folder
        - Unhide the scenery folder
        """ % path)
        logging.info(msg)
    elif (parameters.ELEV_MODE == 'Telnet') or (parameters.ELEV_MODE == 'Fgelev'):
        fname = parameters.PREFIX + os.sep + 'elev.out'
        if prevent_overwrite and os.path.exists(fname):
            logging.info("Skipping %s as it already exists", fname)
            sys.exit(1)

        logging.info("Creating %s", fname)
        if parameters.ELEV_MODE == 'Telnet':
            _raster_telnet(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y
                           , parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)
        else:
            _raster_fgelev(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y
                           , parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)
    else:
        logging.error(err_msg)
        sys.exit(1)


def wait_for_fg(fg):
    """Waits for FlightGear to signal, that the elevation processing has finished."""
    for count in range(0, 1000):
        semaphore = fg.get_prop("/osm2city/tiles")
        semaphore = semaphore.split('=')[1]
        m = re.search("([0-9.]+)", semaphore)
        # We don't care if we get 0.0000 (String) or 0 (Int)
        record = fg.get_prop("/osm2city/record")
        record = record.split('=')[1]
        m2 = re.search("([0-9.]+)", record)
        if m is not None and float(m.groups()[0]) > 0:
            try:
                return True
            except:
                # perform an action#
                pass
        time.sleep(1)
        if m2 is not None:
            logging.debug("Waiting for Semaphore " + m2.groups()[0])
    return False


def _raster_telnet(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    """Writes elev.in and elev.out using Telnet to a running FlightGear instance."""
    fg_home_path = setup.getFGHome()
    if fg_home_path is None:
        logging.error("Operating system unknown and therefore FGHome unknown.")
        sys.exit(1)
    f = open(setup.get_elev_in_path(fg_home_path), "w")
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in np.arange(y0, y0 + size_y, step_y):
        for x in np.arange(x0, x0 + size_x, step_x):
            lon, lat = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()

    fg = telnet.FG_Telnet("localhost", parameters.TELNET_PORT)
    center_lat = abs(parameters.BOUNDARY_NORTH - parameters.BOUNDARY_SOUTH) / 2 + parameters.BOUNDARY_SOUTH
    center_lon = abs(parameters.BOUNDARY_WEST - parameters.BOUNDARY_EAST) / 2 + parameters.BOUNDARY_WEST
    fg.set_prop("/position/latitude-deg", center_lat)
    fg.set_prop("/position/longitude-deg", center_lon)
    fg.set_prop("/position/altitude-ft", 10000)

    logging.info("Running FG Command")
    fg.set_prop("/osm2city/tiles", 0)
    if fg.run_command("get-elevation"):
        if not wait_for_fg(fg):
            logging.error("Process in FG timed out")
        else:
            logging.info("Success")
            shutil.copy2(setup.get_elev_out_path(fg_home_path), fname)
    fg.close()


def _raster_fgelev(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    """fgelev seems to freeze every now and then, so this can be really slow.
       Same happens when run from bash: fgelev < fgelev.in
    """
    center_global = ve.vec2d(transform.toGlobal((x0, y0)))
    btg_file = parameters.PATH_TO_SCENERY + os.sep + "Terrain"
    btg_file = btg_file + os.sep + calc_tile.directory_name(center_global) + os.sep + calc_tile.construct_btg_file_name(center_global)
    if not os.path.exists(btg_file):
        logging.error("Terrain File " + btg_file + " does not exist. Set scenery path correctly or fly there with TerraSync enabled")
        sys.exit(2)

    fg_elev_path = parameters.FG_ELEV

    fgelev = subprocess.Popen(fg_elev_path + ' --expire 1000000 --fg-scenery ' + parameters.PATH_TO_SCENERY
                              , shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    buf_in = Queue.Queue(maxsize=0)
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    i = 0
    y_array = np.arange(y0, y0 + size_y, step_y)
    x_array = np.arange(x0, x0 + size_x, step_x)
    n_total = len(x_array) * len(y_array)
    logging.info("building buffer %i (%i x %i)", n_total, len(x_array), len(y_array))

    for y in y_array:
        for x in x_array:
            i += 1
            lon, lat = transform.toGlobal((x, y))
            buf_in.put("%i %g %g\n" % (i, lon, lat))

# Doesn't work on Windows. Process will block if output buffer isn't read
    if 0:
        print "sending buffer"
        for i in range(1000):
            fgelev.stdin.write(buf_in.get())
    start = time.time()

    logging.info("reading")
    i = 0
    for y in y_array:
        for x in x_array:
            logging.info("done %i %3.1f %%\r", i, i*100/n_total)
            i += 1
            if not buf_in.empty():
                line = buf_in.get()
                logging.debug(line)
                fgelev.stdin.write(line)
            tmp, elev = fgelev.stdout.readline().split()
            lon, lat = transform.toGlobal((x, y))
            # f.write("%i " % i)
            f.write("%1.8f %1.8f %g %g %g\n" % (lon, lat, x, y, float(elev)))
            # if i > 10000: return
        f.write("\n")
        logging.info("done %i %3.1f %%\r", i, i*100/n_total)

    f.close()
    end = time.time()
    logging.info("done %d records per second", i / (end - start))


def _raster(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    """Writes an elev.in file that ca be used with ELEV_MODE = 'Manual'."""
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in np.arange(y0, y0 + size_y, step_y):
        for x in np.arange(x0, x0 + size_x, step_x):
            lon, lat = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()


def write_map(filename, transform, elev, gmin, gmax):
    lmin = ve.vec2d(transform.toLocal((gmin.x, gmin.y)))
    lmax = ve.vec2d(transform.toLocal((gmax.x, gmax.y)))
    map_z0 = 0.
    elev_offset = elev(ve.vec2d(0, 0))
    print "offset", elev_offset

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
            out.write("%g %g %g\n" % (y[j], (elev(ve.vec2d(x[i], y[j])) - elev_offset), x[i]))

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
#            0 0 0
#            1 1 0
#            2 1 1
#            3 0 1
    out.write("kids 0\n")
    out.close()
    # print "OBJECT_STATIC surface.ac"


def write_gp(buildings):
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
#    term = "postscript enh eps"
#    ext = ".eps"
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


class Stats(object):
    def __init__(self):
        self.objects = 0
        self.parse_errors = 0
        self.skipped_small = 0
        self.skipped_nearby = 0
        self.skipped_texture = 0
        self.skipped_no_elev = 0
        self.buildings_in_LOD = np.zeros(3)
        self.area_levels = np.array([1, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000])
        self.corners = np.zeros(10)
        self.area_above = np.zeros_like(self.area_levels)
        self.vertices = 0
        self.surfaces = 0
        self.roof_types = {}
        self.have_complex_roof = 0
        self.roof_errors = 0
        self.out = None
        self.LOD = np.zeros(3)
        self.nodes_simplified = 0
        self.nodes_ground = 0
        self.textures_total = defaultdict(int)

    def count(self, b):
        """update stats (vertices, surfaces, area, corners) with given building's data
        """
        if b.roof_type in self.roof_types:
            self.roof_types[b.roof_type] += 1
        else:
            self.roof_types[b.roof_type] = 1

        # -- stats on number of ground nodes.
        #    Complex buildings counted in corners[0]
        if b.X_inner:
            self.corners[0] += 1
        else:
            self.corners[min(b.nnodes_outer, len(self.corners)-1)] += 1
        
        # --stats on area
        for i in range(len(self.area_levels))[::-1]:
            if b.area >= self.area_levels[i]:
                self.area_above[i] += 1
                return i
        self.area_above[0] += 1
       
        return 0

    def count_LOD(self, lod):
        self.LOD[lod] += 1
        
    def count_texture(self, texture):
        self.textures_total[str(texture.filename)] += 1 

    def print_summary(self):
        if parameters.quiet:
            return
        out = sys.stdout
        total_written = self.LOD.sum()
        lodzero = 0
        lodone = 0
        lodtwo = 0
        if total_written > 0:
            lodzero = 100.*self.LOD[0] / total_written
            lodone = 100.*self.LOD[1] / total_written
            lodtwo = 100.*self.LOD[2] / total_written
        out.write(textwrap.dedent("""
            total buildings %i
            parse errors    %i
            written         %i
              four-sided    %i
            skipped
              small         %i
              nearby        %i
              no elevation  %i
              no texture    %i
            """ % (self.objects, self.parse_errors, total_written, self.corners[4],
                   self.skipped_small, self.skipped_nearby, self.skipped_no_elev, self.skipped_texture)))
        roof_line = "        roof-types"
        for roof_type in self.roof_types:
            roof_line += """\n          %s\t%i""" % (roof_type, self.roof_types[roof_type])
        out.write(textwrap.dedent(roof_line))

        textures_used = {k: v for k, v in self.textures_total.iteritems() if v > 0}
        textures_notused = {k: v for k, v in self.textures_total.iteritems() if v == 0}
        try:
            textures_used_percent = len(textures_used) * 100. / len(self.textures_total)
        except:
            textures_used_percent = 99.9

        out.write(textwrap.dedent("""
            used tex        %i out of %i (%2.0f %%)""" % (len(textures_used), len(self.textures_total), textures_used_percent)))
        out.write(textwrap.dedent("""
            Used Textures : """))    
        for item in sorted(textures_used.items(), key=lambda item: item[1], reverse=True):            
            out.write(textwrap.dedent("""
                 %i %s""" % (item[1], item[0])))
        out.write(textwrap.dedent("""
            Unused Textures : """))    
        for item in sorted(textures_notused.items(), key=lambda item: item[1], reverse=True):            
            out.write(textwrap.dedent("""
                 %i %s""" % (item[1], item[0])))
        out.write(textwrap.dedent("""
              complex       %i
              roof_errors   %i
            ground nodes    %i
              simplified    %i
            vertices        %i
            surfaces        %i
            LOD
                LOD bare        %i (%2.0f %%)
                LOD rough       %i (%2.0f %%)
                LOD detail      %i (%2.0f %%)
            """ % (self.have_complex_roof, self.roof_errors,
                   self.nodes_ground, self.nodes_simplified,
                   self.vertices, self.surfaces, 
                   self.LOD[0], lodzero,
                   self.LOD[1], lodone,
                   self.LOD[2], lodtwo)))
        out.write("\narea >=\n")
        max_area_above = max(1, self.area_above.max())
        for i in xrange(len(self.area_levels)):
            out.write(" %5g m^2  %5i |%s\n" % (self.area_levels[i], self.area_above[i],
                      "#" * int(56. * self.area_above[i] / max_area_above)))

        if logging.getLogger().level <= logging.VERBOSE:  # @UndefinedVariable
            for name in sorted(self.textures_used):
                out.write("%s\n" % name)

        out.write("\nnumber of corners >=\n")
        max_corners = max(1, self.corners.max())
        for i in xrange(3, len(self.corners)):
            out.write("     %2i %6i |%s\n" % (i, self.corners[i],
                      "#" * int(56. * self.corners[i] / max_corners)))
        out.write(" complex %5i |%s\n" % (self.corners[0],
                  "#" * int(56. * self.corners[0] / max_corners)))


def init(new_transform):
    global transform
    transform = new_transform

    global stats
    stats = Stats()
    logging.debug("tools: init %s" % stats)


def install_files(file_list, dst):
    """link files in file_list to dst"""
    for the_file in file_list:
        the_dst = dst  # + os.sep + the_file
        logging.info("cp %s %s" % (the_file, the_dst))
        if os.path.exists(the_dst + the_file):
            return
        try:
            shutil.copy2(the_file, the_dst)
        except OSError, reason:
            if reason.errno not in [17]:
                logging.warn("Error while installing %s: %s" % (the_file, reason))
        except (AttributeError, shutil.Error) as e:
            logging.warn("Error while installing %s: %s" % (the_file, repr(e)))


def get_interpolator(**kwargs):
    if parameters.ELEV_MODE == 'FgelevCaching':
        return Probe_fgelev(**kwargs)
    else:
        filename = parameters.PREFIX + os.sep + 'elev.out'
        return Interpolator(filename, **kwargs)


def progress(i, max_i):
    """progress indicator"""
    if sys.stdout.isatty() and not parameters.quiet:
        try:
            if i % (max_i / 100) > 0:
                return
        except ZeroDivisionError:
            pass
        print "%i %i %5.1f%%     \r" % (i+1, max_i, (float(i+1)/max_i) * 100),
        if i > max_i - 2:
            print


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="tools prepares an elevation grid for Nasal script and then osm2city")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-o", dest="o", action="store_true", help="do not overwrite existing elevation data")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.show()

    if args.o:
        raster_glob(True)
    else:
        raster_glob(False)
