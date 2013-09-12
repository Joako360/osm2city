import shapely.geometry as shg
import numpy as np
import building_lib

def flat_relation(b):
    """relation flat roof, for one inner way only, included in base model"""
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
    out += "mat %i\n" % b.roof_mat
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
    return out

def flat(b):
    """plain flat roof, included in base model"""
    out = ""    
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.roof_mat
    out += "refs %i\n" % b.nnodes_outer
    for i in range(b.nnodes_outer):
        out += "%i %g %g\n" % (i+b.nnodes_outer, 0, 0)
    return out

def separate_gable(b, X):
    """gable roof, 4 nodes, separate model"""
    out = ""
    out += "OBJECT poly\n"
    out += 'name "%s"\n' % b.roof_ac_name

    out += 'texture "%s"\n' % (b.roof_texture.filename + '.png')

    # -- pitched roof for 4 ground nodes
    numvert = b.nnodes_outer + 2
    out += "numvert %i\n" % numvert
    b.vertices += numvert

    # -- 4 corners
    for x in X:
        z = b.ground_elev - 1
        out += "%1.2f %1.2f %1.2f\n" % (-x[1], b.ground_elev + b.height, -x[0])
    # --
    #mid_short_x = 0.5*(X[3][1]+X[0][1])
    #mid_short_z = 0.5*(X[3][0]+X[0][0])
    # -- tangential vector of long edge
    inward = 4. # will shift roof top 4m inward
    roof_height = 3. # 3m
    tang = (X[1]-X[0])/b.lenX[0] * inward

    len_roof_top = b.lenX[0] - 2.*inward
    len_roof_bottom = 1.*b.lenX[0]

    out += "%1.2f %1.2f %1.2f\n" % (-(0.5*(X[3][1]+X[0][1]) + tang[1]), b.ground_elev + b.height + roof_height, -(0.5*(X[3][0]+X[0][0]) + tang[0]))
    out += "%1.2f %1.2f %1.2f\n" % (-(0.5*(X[1][1]+X[2][1]) - tang[1]), b.ground_elev + b.height + roof_height, -(0.5*(X[1][0]+X[2][0]) - tang[0]))

    roof_texture_size_x = b.roof_texture.h_size_meters # size of roof texture in meters
    roof_texture_size_y = b.roof_texture.v_size_meters
    repeatx = len_roof_bottom / roof_texture_size_x
    len_roof_hypo = ((0.5*b.lenX[1])**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo / roof_texture_size_y

    numsurf = 4    
    out += "numsurf %i\n" % numsurf
    b.surfaces += numsurf

    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % b.nnodes_outer
    out += "%i %g %g\n" % (0, 0, 0)
    out += "%i %g %g\n" % (1, repeatx, 0)
    out += "%i %g %g\n" % (5, repeatx*(1-inward/len_roof_bottom), repeaty)
    out += "%i %g %g\n" % (4, repeatx*(inward/len_roof_bottom), repeaty)

    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % b.nnodes_outer
    out += "%i %g %g\n" % (2, 0, 0)
    out += "%i %g %g\n" % (3, repeatx, 0)
    out += "%i %g %g\n" % (4, repeatx*(1-inward/len_roof_bottom), repeaty)
    out += "%i %g %g\n" % (5, repeatx*(inward/len_roof_bottom), repeaty)

    repeatx = b.lenX[1]/roof_texture_size_x
    len_roof_hypo = (inward**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo/roof_texture_size_y
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % 3
    out += "%i %g %g\n" % (1, 0, 0)
    out += "%i %g %g\n" % (2, repeatx, 0)
    out += "%i %g %g\n" % (5, 0.5*repeatx, repeaty)

    repeatx = b.lenX[3]/roof_texture_size_x
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % 3
    out += "%i %g %g\n" % (3, 0, 0)
    out += "%i %g %g\n" % (0, repeatx, 0)
    out += "%i %g %g\n" % (4, 0.5*repeatx, repeaty)
    return out
    
def separate_flat(b, ac_name, X):
    """flat roof, any number of nodes, separate model"""
    out = ""
    out += "OBJECT poly\n"
    out += 'name "%s"\n' % ac_name

    out += 'texture "%s"\n' % (b.roof_texture.filename + '.png')
    out += "numvert %i\n" % b.nnodes_outer

    for x in X:
        z = b.ground_elev - 1
        out += "%1.2f %1.2f %1.2f\n" % (-x[1], b.ground_elev + b.height, -x[0])
    out += "numsurf 1\n"
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.mat
    out += "refs %i\n" % b.nnodes_outer
    for i in range(b.nnodes_outer):
        out += "%i %g %g\n" % (i, 0, 0)
    return out
