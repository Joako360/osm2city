import shapely.geometry as shg
import numpy as np

def flat_relation(b):
    #print "one roof"
    #
    #   3-----------2  Outer is CCW : 0 1 2 3
    #   |           |  Inner is CW  : 4 5 6 7
    #   |           |
    #   | 7----4    |  draw 0 1 2 3 - 0 - 6 7 4 5 - 6
    #   | |    |    |
    #   | 6-<<-5    |  6 is the inner node which is closest to first outer node
    #   |/          |
    #   0---->>-----1

    out = ""

    # -- find inner node i that is closest to first outer node
    xo = shg.Point(b.X_outer[0])
    dists = np.array([shg.Point(xi).distance(xo) for xi in b.polygon.interiors[0].coords])
    #i = dists.argmin()
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % (b._nnodes_ground + 2)

    for i in range(b._nnodes_ground, b._nnodes_ground + b.nnodes_outer):
        out += "%i %g %g\n" % (i, 0, 0)
    out += "%i %g %g\n" % (b._nnodes_ground, 0, 0)
    ninner = len(b.X_inner)
    Xi = np.arange(ninner) + b.nnodes_outer + b._nnodes_ground
    Xi = np.roll(Xi, dists.argmin())
    for i in Xi:
        out += "%i %g %g\n" % (i, 0, 0)
    out += "%i %g %g\n" % (Xi[0], 0, 0)
    out += "kids 0\n"
    return out

def flat(b):
    """plain flat roof"""
    out = ""    
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.roof_mat
    out += "refs %i\n" % b.nnodes_outer
    for i in range(b.nnodes_outer):
        out += "%i %g %g\n" % (i+b.nnodes_outer, 0, 0)
    out += "kids 0\n"
    
    return out
    