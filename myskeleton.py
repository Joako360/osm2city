# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 19:37:03 2013

@author: tom
"""

import pySkeleton.polygon as polygon
from vec2d import vec2d
import random
import textwrap
import numpy as np
import tools
import os
import logging
import parameters



def myskel(out, b, name = "roof", offset_xy = vec2d(0, 0), offset_z = 0., header = False, max_height = 1e99):
#vertices = [(202.0, 52.0), (400.0, 52.0), (400.0, 153.0), (202.0, 152.0)]
#edges =  [(0, 1), (1, 2), (2, 3), (3, 0)]
#speeds = [1.0, 1.0, 1.0, 1.0]

#    vertices = [(550.0, 102.0), (550.0, 301.0), (200.0, 303.0), (201.0, 102.0), (501.0, 154.0), (351.0, 152.0), (350.0, 251.0), (498.0, 249.0)]
#    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)]
#    speeds = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

    vertices = b.X_outer
    no = len(b.X_outer)
    edges = [(i, i+1) for i in range(no-1)]
    edges.append((no-1, 0))
    speeds = [1.] * no

    #print "OSMID", b.osm_id
    if False and b.osm_id == 34112567:
        if False:
            vertices = np.array(vertices)
    #        print "vertices = ", vertices

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

            #sc = dx/600.
            #vertices /= sc
            vertices += 10.

    #        print "vertices = ", vertices
    #        print "edges = ", edges
    #        print "speeds = ", speeds
        f = open("a.fp", "w")
        f.write("%i\n" % len(vertices))
        for v in vertices:
            f.write("%g %g\n" % (v[0], v[1]))
        f.write("%i\n" % len(edges))
        for e in edges:
            f.write("%i %i 1.0\n" % (e[0], e[1]))
        f.close()

        gp = "try"
        tools.write_one_gp(b, gp)
        os.system("gnuplot %s.gp" % gp)
        tools.write_one_gp(b, gp)
        poly = polygon.Polygon(vertices, edges, speeds)
        angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
#        print angle
        #skeleton = poly.straight_skeleton()
#        print "skel", skeleton
        roof_mesh = poly.roof_3D(angle * 3.1415 / 180.)

        s = roof_mesh.ac3d_string(b, offset_xy, offset_z, header)

    # -- for some reason, roof_3d fails at times.
    try:
#    if True:
        poly = polygon.Polygon(vertices, edges, speeds)
        if 'roof:angle' in b.tags:
            angle = float(b.tags['roof:angle'])
        else:
            angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
        while angle > 0:    
            roof_mesh = poly.roof_3D(angle * 3.1415 / 180.)
            #roof.mesh.vertices
            roof_height = max([p[2] for p in roof_mesh.vertices])
            if roof_height < max_height:
                break
            #We'll just flatten the roof then instead of loosing it 
            angle = angle - 5
        if roof_height > max_height:
            logging.warning("roof too high %g > %g" % (roof_height, max_height))
            return False

        result = roof_mesh.to_out(out, b, offset_xy, offset_z, header)
    except Exception as reason:
#    if False:
        logging.error("Error while creating 3d roof (OSM_ID %s, %s)" % (b.osm_id, reason))
        tools.stats.roof_errors += 1
        gp = parameters.PREFIX + os.sep + 'roof-error-%04i' % tools.stats.roof_errors
        tools.write_one_gp(b, gp)
        #os.system("gnuplot %s.gp" % gp)
        return False

    if False and header:
        f = open("r.ac", "w")
        f.write(s)
        f.close()

    return result


if __name__ == "__main__":
    myskel(header = True)
