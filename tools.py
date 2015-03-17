#!/usr/bin/env python2
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
import os
import logging
import batch_processing.fg_telnet as telnet
import shutil
import cPickle
import parameters
import math
import string

stats = None

from vec2d import vec2d
import coordinates
import calc_tile
import time
import re
import csv
import subprocess
# import Queue

import matplotlib.pyplot as plt
transform = None

class Interpolator(object):
    """load elevation data from file, interpolate"""
    def __init__(self, filename, fake=False, clamp=False):
        """If clamp = False, out-of-bounds elev probing returns -9999.
           Otherwise, return elev at closest boundary.
        """
        # FIXME: use values from header in filename
        # FIXME: could save lots of mem by not storing regular grid XY
        if fake:
            self.fake = True
            self.h = 0.
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

        self.min = vec2d(min(self.x), min(self.y))
        self.max = vec2d(max(self.x), max(self.y))
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
        fx = (x - self.x[j,i])/self.dx
        fy = (y - self.y[j,i])/self.dy
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
        self.fake = fake
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
        #fg_root = "$FG_ROOT"
#        fgelev_cmd = path_to_fgelev + ' --expire 1000000 --fg-root ' + fg_root + ' --fg-scenery '+ parameters.PATH_TO_SCENERY
        fgelev_cmd = path_to_fgelev + ' --expire 1000000 --fg-scenery '+ parameters.PATH_TO_SCENERY
        logging.info("cmd line: " + fgelev_cmd)
        self.fgelev_pipe = subprocess.Popen(fgelev_cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        # -- This should catch spawn errors, but it doesn't. We
        #    check for sane return values on fgelev calls later.
#        if self.fgelev_pipe.poll() != 0:
#            raise RuntimeError("Spawning fgelev failed.")

    def save_cache(self):
        "save cache to disk"
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
                    empty_lines+=1
                    line = self.fgelev_pipe.stdout.readline().strip()
                elev = float(line.split()[1]) + self.h_offset
            except IndexError, reason:
                self.save_cache()
                if empty_lines > 1:
                    logging.fatal("Skipped %i lines" % (empty_lines))
                logging.fatal("%i %g %g" % (self.record, position.lon, position.lat))
                logging.fatal("fgelev returned <%s>, resulting in %s. Did fgelev start OK (Record : %i)?", line, reason, self.record)
                raise RuntimeError("fgelev errors are fatal.")

            return elev

        if self.fake:
            return 0.

        global transform
        if not is_global:
            position = vec2d(transform.toGlobal(position))
        else:
            position = vec2d(position[0], position[1])

        self.record = self.record + 1
        if self._cache == None:
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
    p = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
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
            p = vec2d(x, y)
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

def raster_glob():
    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center = (cmin + cmax) * 0.5
    transform = coordinates.Transformation((center.x, center.y), hdg=0)
    lmin = vec2d(transform.toLocal(cmin.__iter__()))
    lmax = vec2d(transform.toLocal(cmax.__iter__()))
    delta = (lmax - lmin) * 0.5
    print "Distance from center to boundary in meters (x, y):", delta
    err_msg = "Unknown Elevation Query mode : %s Use Manual, Telnet or Fgelev for parameter ELEV_MODE " % (parameters.ELEV_MODE)
    if parameters.ELEV_MODE == '':
        logging.error(err_msg)
        sys.exit(err_msg)
    elif parameters.ELEV_MODE == 'Manual':
        print "Creating elev.in ..."
        fname = parameters.PREFIX + os.sep + "elev.in"
        raster(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y, parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)

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
    elif parameters.ELEV_MODE == 'Telnet':
        fname = parameters.PREFIX + os.sep + 'elev.in'
        if not os.path.exists(parameters.PREFIX + os.sep + 'elev.out'):
            print "Creating ", fname
            raster_telnet(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y, parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)
        else:
            print "Skipping ", parameters.PREFIX + os.sep + 'elev.out', " exists"
    elif parameters.ELEV_MODE == 'Fgelev':
        if not os.path.exists(parameters.PREFIX + os.sep + 'elev.out'):
            fname = parameters.PREFIX + os.sep + 'elev.out'
            print "Creating ", fname
            raster_fgelev(transform, fname, -delta.x, -delta.y, 2 * delta.x, 2 * delta.y, parameters.ELEV_RASTER_X, parameters.ELEV_RASTER_Y)
        else:
            print "Skipping ", parameters.PREFIX + os.sep + 'elev.out', " exists"
    else:
        logging.error(err_msg)
        sys.exit(err_msg)

def wait_for_fg(fg):
# Waits for Flightgear to signal, that the elevation processing has finished
    for count in range(0, 1000):
        semaphore = fg.get_prop("/osm2city/tiles")
        semaphore = semaphore.split('=')[1]
        m = re.search("([0-9.]+)", semaphore)
# We don't care if we get 0.0000 (String) or 0 (Int)
        record = fg.get_prop("/osm2city/record")
        record = record.split('=')[1]
        m2 = re.search("([0-9.]+)", record)
        if not m is None and float(m.groups()[0]) > 0:
            try:
                return True
            except:
                # perform an action#
                pass
        time.sleep(1)
        if not m2 is None:
            logging.debug("Waiting for Semaphore " + m2.groups()[0])
    return False


def raster_telnet(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    # --- need $FGDATA/Nasal/elev.nas and elev.in
    #     hide scenery/Objects/e.... folder
    #     in Nasal console: elev.get()
    #     data gets written to /tmp/elev.xml

    # check $FGDATA/Nasal/IOrules
    fg = telnet.FG_Telnet("localhost", 5501)
    center_lat = abs(parameters.BOUNDARY_NORTH - parameters.BOUNDARY_SOUTH) / 2 + parameters.BOUNDARY_SOUTH
    center_lon = abs(parameters.BOUNDARY_WEST - parameters.BOUNDARY_EAST) / 2 + parameters.BOUNDARY_WEST
    fg.set_prop("/position/latitude-deg", center_lat);
    fg.set_prop("/position/longitude-deg", center_lon);
    fg.set_prop("/position/altitude-ft", 3000);
    f = open("C:/Users/keith.paterson/AppData/Roaming/flightgear.org/elev.in", "w");
#       f = open(fname, 'w')
#    f.write("# Tile %s\n" % (parameters.PREFIX))
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in np.arange(y0, y0 + size_y, step_y):
        for x in np.arange(x0, x0 + size_x, step_x):
            lon, lat = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()
    fg.set_prop("/position/latitude-deg", center_lat);
    fg.set_prop("/position/longitude-deg", center_lon);
    fg.set_prop("/position/altitude-ft", 3000);

    logging.info("Running FG Command")
    fg.set_prop("/osm2city/tiles", 0)
    if(fg.run_command("get-elevation")):
        if not wait_for_fg(fg):
            logging.error("Process in FG timed out")
        else:
            logging.info("Success")
            shutil.copy2("C:/Users/keith.paterson/AppData/Roaming/flightgear.org/Export/elev.out", parameters.PREFIX + os.sep + 'elev.out')
    fg.close()




def raster_fgelev(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    """fgelev seems to freeze every now and then, so this can be really slow.
       Same happens when run from bash: fgelev < fgelev.in
    """
    import subprocess
    import Queue
    #fg_root = "$FG_ROOT"

    center_global = vec2d(transform.toGlobal((x0,y0)))
    btg_file = parameters.PATH_TO_SCENERY + os.sep + "Terrain"
    btg_file = btg_file + os.sep + calc_tile.directory_name(center_global) + os.sep + calc_tile.construct_btg_file_name(center_global)
    if not os.path.exists(btg_file):
        logging.error("Terrain File " + btg_file + " does not exist. Set scenery path correctly or fly there with TerraSync enabled")
        sys.exit(2)

    fg_elev = parameters.FG_ELEV

#    fgelev = subprocess.Popen( fg_elev + ' --expire 1000000 --fg-root ' + fg_root + ' --fg-scenery '+ parameters.PATH_TO_SCENERY,  shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    fgelev = subprocess.Popen( fg_elev + ' --expire 1000000 --fg-scenery '+ parameters.PATH_TO_SCENERY,  shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # fgelev = subprocess.Popen(["/home/tom/daten/fgfs/cvs-build/git-2013-09-22-osg-3.2/bin/fgelev", "--fg-root", "$FG_ROOT",  "--fg-scenery", "$FG_SCENERY"],  stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # time.sleep(5)
    buf_in = Queue.Queue(maxsize=0)
    f = open(fname, 'w')
    # f = sys.stdout
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    i = 0
    y_array = np.arange(y0, y0 + size_y, step_y)
    x_array = np.arange(x0, x0 + size_x, step_x)
    n_total = len(x_array) * len(y_array)
    print "building buffer %i (%i x %i)" % (n_total, len(x_array), len(y_array))

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

    print "reading"
    i = 0
    for y in y_array:
        for x in x_array:
            print "done %i %3.1f %%\r" % (i, i*100/n_total),
            i += 1
            if not buf_in.empty():
                line = buf_in.get()
                print line
                fgelev.stdin.write(line)
            tmp, elev = fgelev.stdout.readline().split()
            lon, lat = transform.toGlobal((x, y))
            # f.write("%i " % i)
            f.write("%1.8f %1.8f %g %g %g\n" % (lon, lat, x, y, float(elev)))
            # if i > 10000: return
        f.write("\n")
        print "done %i %3.1f %%\r" % (i, i*100/n_total),

    f.close()
    end = time.time()
    print "done %d records/s" % ((i / (end - start)))


def raster(transform, fname, x0, y0, size_x=1000, size_y=1000, step_x=5, step_y=5):
    # --- need $FGDATA/Nasal/elev.nas and elev.in
    #     hide scenery/Objects/e.... folder
    #     in Nasal console: elev.get()
    #     data gets written to /tmp/elev.xml

    # check $FGDATA/Nasal/IOrules
    f = open(fname, 'w')
    f.write("# %g %g %g %g %g %g\n" % (x0, y0, size_x, size_y, step_x, step_y))
    for y in np.arange(y0, y0 + size_y, step_y):
        for x in np.arange(x0, x0 + size_x, step_x):
            lon, lat = transform.toGlobal((x, y))
            f.write("%1.8f %1.8f %g %g\n" % (lon, lat, x, y))
        f.write("\n")
    f.close()

def write_map(filename, transform, elev, gmin, gmax):
    lmin = vec2d(transform.toLocal((gmin.x, gmin.y)))
    lmax = vec2d(transform.toLocal((gmax.x, gmax.y)))
    map_z0 = 0.
    elev_offset = elev(vec2d(0,0))
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
            out.write("%g %g %g\n" % (y[j], (elev(vec2d(x[i],y[j])) - elev_offset), x[i]))

    out.write("numsurf %i\n" % ((nx - 1) * (ny - 1)))
    for j in range(ny - 1):
        for i in range(nx - 1):
            out.write(textwrap.dedent("""\
            SURF 0x0
            mat 0
            refs 4
            """))
            out.write("%i %g %g\n" % (i + j * (nx), u[i], v[j]))
            out.write("%i %g %g\n" % (i + 1 + j * (nx), u[i + 1], v[j]))
            out.write("%i %g %g\n" % (i + 1 + (j + 1) * (nx), u[i + 1], v[j + 1]))
            out.write("%i %g %g\n" % (i + (j + 1) * (nx), u[i], v[j + 1]))
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
        self.textures_total = 0
        self.textures_used = set()

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
        self.textures_used.add(str(texture))

    def print_summary(self):
        if parameters.quiet: return
        out = sys.stdout
        total_written = self.LOD.sum()
        lodzero = 0
        lodone = 0
        lodtwo = 0
        if total_written > 0:
            lodzero = 100.*self.LOD[0] / total_written
            lodone = 100.*self.LOD[1] / total_written
            lodtwo = 100.*self.LOD[0] / total_written
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
            roof_line += """\r\n          %s\t%i""" % (roof_type, self.roof_types[roof_type])
        out.write(textwrap.dedent(roof_line))

        try:
            textures_used_percent = len(self.textures_used) * 100. / self.textures_total
        except:
            textures_used_percent = 99.9

        out.write(textwrap.dedent("""
              complex       %i
              roof_errors   %i
            ground nodes    %i
              simplified    %i
            vertices        %i
            surfaces        %i
            used tex        %i out of %i (%2.0f %%)
                LOD bare        %i (%2.0f %%)
                LOD rough       %i (%2.0f %%)
                LOD detail      %i (%2.0f %%)
            """ % (self.have_complex_roof, self.roof_errors,
                   self.nodes_ground, self.nodes_simplified,
                   self.vertices, self.surfaces,
                   len(self.textures_used), self.textures_total, textures_used_percent, 
                   self.LOD[0], lodzero,
                   self.LOD[1], lodone,
                   self.LOD[2], lodtwo)))
        out.write("\narea >=\n")
        max_area_above = max(1, self.area_above.max())
        for i in xrange(len(self.area_levels)):
            out.write(" %5g m^2  %5i |%s\n" % (self.area_levels[i], self.area_above[i], \
                      "#" * int(56. * self.area_above[i] / max_area_above)))

        out.write("\nnumber of corners >=\n")
        max_corners = max(1, self.corners.max())
        for i in xrange(3, len(self.corners)):
            out.write("     %2i %6i |%s\n" % (i, self.corners[i], \
                      "#" * int(56. * self.corners[i] / max_corners)))
        out.write(" complex %5i |%s\n" % (self.corners[0], \
                  "#" * int(56. * self.corners[0] / max_corners)))
                  

def init(new_transform):
    global transform
    transform = new_transform

    global stats
    stats = Stats()
    logging.debug("tools: init %s"%stats)

def install_files(file_list, dst):
    """link files in file_list to dst"""
    for the_file in file_list:
        the_dst = dst + os.sep + the_file
        logging.info("cp %s %s" % (the_file, the_dst))
        try:
            shutil.copy2(the_file, the_dst)
        except OSError, reason:
            if reason.errno not in [17]:
                logging.warn("Error while installing %s: %s" % (the_file, reason))
        except AttributeError, reason:
            logging.warn("Error while installing %s: %s" % (the_file, reason))

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
    # Parse arguments and eventually override Parameters
    import argparse
    parser = argparse.ArgumentParser(description="tools prepares an elevation grid for Nasal script and then osm2city")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    args = parser.parse_args()
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.show()

    if 0:
        for N in [1000, 100]:
            test_fgelev(True, N)
            # test_fgelev(False, N)
        sys.exit(0)

    raster_glob()

