# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 19:37:03 2013

@author: tom
"""

import logging
import os
import random

import numpy as np
import parameters
import pySkeleton.polygon as polygon
from utils import utilities
from utils.vec2d import Vec2d


def myskel(out, b, stats: utilities.Stats, offset_xy=Vec2d(0, 0), offset_z=0., header=False, max_height=1e99):
    vertices = b.X_outer
    no = len(b.X_outer)
    edges = [(i, i+1) for i in range(no-1)]
    edges.append((no-1, 0))
    speeds = [1.] * no

    if False and b.osm_id == 34112567:
        if False:
            vertices = np.array(vertices)

            minx = min(vertices[:, 0])
            maxx = max(vertices[:, 0])
            miny = min(vertices[:, 1])
            maxy = max(vertices[:, 1])
            print("minx", minx)
            print("miny", miny)
            dx = (maxx - minx)
            dy = (maxy - miny)
            vertices[:, 0] -= (minx)
            vertices[:, 1] -= (miny)

            vertices += 10.

        f = open("a.fp", "w")
        f.write("%i\n" % len(vertices))
        for v in vertices:
            f.write("%g %g\n" % (v[0], v[1]))
        f.write("%i\n" % len(edges))
        for e in edges:
            f.write("%i %i 1.0\n" % (e[0], e[1]))
        f.close()

        gp = "try"
        utilities.write_one_gp(b, gp)
        os.system("gnuplot %s.gp" % gp)
        utilities.write_one_gp(b, gp)
        poly = polygon.Polygon(vertices, edges, speeds)
        angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
        roof_mesh = poly.roof_3D(angle * 3.1415 / 180.)

        s = roof_mesh.ac3d_string(b, offset_xy, offset_z, header)

    try:
        poly = polygon.Polygon(vertices, edges, speeds)
        if 'roof:angle' in b.tags:
            angle = float(b.tags['roof:angle'])
        else:
            angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
        while angle > 0:    
            roof_mesh = poly.roof_3D(angle * 3.1415 / 180.)
            # roof.mesh.vertices
            roof_height = max([p[2] for p in roof_mesh.vertices])
            if roof_height < max_height:
                break
            # We'll just flatten the roof then instead of loosing it
            angle -= 5
        if roof_height > max_height:
            logging.warning("roof too high %g > %g" % (roof_height, max_height))
            return False

        result = roof_mesh.to_out(out, b, offset_xy, offset_z, header)
    except Exception as reason:
        logging.error("Error while creating 3d roof (OSM_ID %s, %s)" % (b.osm_id, reason))
        stats.roof_errors += 1
        gp = parameters.PREFIX + os.sep + 'roof-error-%04i' % stats.roof_errors
        utilities.write_one_gp(b, gp)
        return False

    if False and header:
        f = open("r.ac", "w")
        f.write(s)
        f.close()

    return result
