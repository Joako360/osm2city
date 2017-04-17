# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 19:37:03 2013

@author: tom
"""

import logging
import random

import parameters
import pySkeleton.polygon as polygon
from utils import utilities
from utils.vec2d import Vec2d


def myskel(out, b, stats: utilities.Stats, offset_xy=Vec2d(0, 0), offset_z=0., header=False, max_height=1e99) -> bool:
    vertices = b.X_outer
    no = len(b.X_outer)
    edges = [(i, i+1) for i in range(no-1)]
    edges.append((no-1, 0))
    speeds = [1.] * no

    try:
        poly = polygon.Polygon(vertices, edges, speeds)
        if 'roof:angle' in b.tags:
            angle = float(b.tags['roof:angle'])
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
            logging.debug("WARNING: roof too high %g > %g" % (roof_height, max_height))
            return False

        result = roof_mesh.to_out(out, b, offset_xy, offset_z, header)
    except Exception as reason:
        logging.debug("ERROR: while creating 3d roof (OSM_ID %s, %s)" % (b.osm_id, reason))
        stats.roof_errors += 1
        gp = parameters.get_repl_prefix() + '_roof-error-%04i' % stats.roof_errors
        if parameters.log_level_debug_or_lower():
            utilities.write_one_gp(b, gp)
        return False

    return result
