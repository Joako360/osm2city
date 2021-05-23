# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 19:37:03 2013

@author: tom
"""

import logging
from math import fabs
import random

from osm2city import parameters
from osm2city.pySkeleton import polygon
from osm2city.static_types import osmstrings as s
from osm2city.utils.coordinates import Vec2d


def myskel(out, b, offset_xy=Vec2d(0, 0), offset_z=0., max_height=1e99) -> bool:
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

        result = roof_mesh.to_out(out, b, offset_xy, offset_z)
    except Exception as reason:
        logging.debug("ERROR: while creating 3d roof (OSM_ID %s, %s)" % (b.osm_id, reason))
        return False

    return result
