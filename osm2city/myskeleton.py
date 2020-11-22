# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 19:37:03 2013

@author: tom
"""

import logging
from math import fabs
import random
import textwrap

import numpy as np

from osm2city import parameters
from osm2city.pySkeleton import polygon
import osm2city.utils.log_helper as ulog
from osm2city.static_types import osmstrings as s
from osm2city.utils import utilities
from osm2city.utils.coordinates import Vec2d


def myskel(out, b, stats: utilities.Stats, offset_xy=Vec2d(0, 0), offset_z=0., header=False, max_height=1e99) -> bool:
    vertices = b.pts_outer
    no = len(b.pts_outer)
    edges = [(i, i+1) for i in range(no-1)]
    edges.append((no-1, 0))
    speeds = [1.] * no

    try:
        poly = polygon.Polygon(vertices, edges, speeds)
        if s.K_ROOF_ANGLE in b.tags:
            angle = float(b.tags[s.K_ROOF_ANGLE])
        else:
            angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
        roof_height = 0.
        while angle > 0:    
            roof_mesh = poly.roof_3D(angle * 3.1415 / 180.)
            # roof.mesh.vertices
            roof_height = max([p[2] for p in roof_mesh.vertices])
            if roof_height < max_height:
                break
            # We'll just flatten the roof then instead of loosing it
            angle -= 5
        if roof_height > max_height:
            logging.debug("Skeleton roof too high %g > %g - and therefore not accepted", roof_height, max_height)
            return False

        # The following is a hack as in certain (not further investigated situation) the dimensions can get out
        # of control generating e+07 numbers, which cannot be right.
        # FG crashes if an ac-file has such values.
        for p in roof_mesh.vertices:
            if fabs(p[0] - b.polygon.centroid.x) > parameters.BUILDING_SKEL_MAX_DIST_FROM_CENTROID or (
                    fabs(p[1] - b.polygon.centroid.y) > parameters.BUILDING_SKEL_MAX_DIST_FROM_CENTROID):
                logging.debug("Skeleton roof might be broken - and therefore not accepted")
                return False

        result = roof_mesh.to_out(out, b, offset_xy, offset_z, header)
    except Exception as reason:
        logging.debug("ERROR: while creating 3d roof (OSM_ID %s, %s)" % (b.osm_id, reason))
        stats.roof_errors += 1
        gp = parameters.PREFIX + '_roof-error-%04i' % stats.roof_errors
        if ulog.log_level_debug_or_lower():
            _write_one_gp(b.pts_outer, b.osm_id, gp)
        return False

    return result


def _write_one_gp(pts_outer, osm_id: int, filename: str) -> None:
    npv = np.array(pts_outer)
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
    set title "%d"
    unset key
    """ % (term, filename, ext, minx, maxx, miny, maxy, osm_id)))
    i = 0
    for v in pts_outer:
        i += 1
        gp.write('set label "%i" at %g, %g\n' % (i, v[0], v[1]))

    gp.write("plot '-' w lp\n")
    for v in pts_outer:
        gp.write('%g %g\n' % (v[0], v[1]))
    gp.close()
