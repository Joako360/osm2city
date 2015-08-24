import shapely.geometry as shg
import numpy as np
import building_lib
import random
from math import sin, cos, atan2, tan, sqrt, pi
import copy
import logging
import parameters
import re

def _flat_relation(b):
    """relation flat roof, for one inner way only, included in base model"""

    out = ""

    # -- find inner node i that is closest to first outer node
    xo = shg.Point(b.X_outer[0])
    dists = np.array([shg.Point(xi).distance(xo) for xi in b.polygon.interiors[0].coords])
    # i = dists.argmin()
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


def flat(out, b, X, ac_name=""):
    if b.roof_texture is None:
        raise ValueError("Roof texture None")
    """Flat roof. Separate model if ac_name is not empty. Also works for relations."""
    #   3-----------------2  Outer is CCW: 0 1 2 3
    #   |                /|  Inner[0] is CW: 4 5 6 7
    #   |         11----8 |  Inner[1] is CW: 8 9 10 11
    #   | 5----6  |     | |  Inner rings are rolled such that their first nodes
    #   | |    |  10-<<-9 |  are closest to an outer node. (see b.roll_inner_nodes)
    #   | 4-<<-7          |
    #   |/                |  draw 0 - 4 5 6 7 4 - 0 1 2 - 8 9 10 11 8 - 2 3
    #   0---->>-----------1

    logging.verbose("FIXME: check if we duplicate nodes, and if separate model still makes sense.")

    if ac_name:
        out.new_object(ac_name, b.roof_texture.filename + '.png')
        for x in X:
            z = b.ground_elev - 1
#            out += "%1.2f %1.2f %1.2f\n" % (-x[1], b.ground_elev + b.height, -x[0])
            out.node(-x[1], b.ground_elev + b.height, -x[0])

    #out += "refs %i\n" % (b._nnodes_ground + 2 * len(b.polygon.interiors))

    if len(b.polygon.interiors):
        outer_closest = copy.copy(b.outer_nodes_closest)
        i = b.nnodes_outer
        inner_ring = 0
        nodes = []
        for o in range(b.nnodes_outer):
            nodes.append(o)
            if outer_closest and o == outer_closest[0]:
    #            print "inner ring!"
                len_ring = len(b.polygon.interiors[inner_ring].coords) - 1
                a = np.arange(len_ring) + i
                for x in a: nodes.append(x)
                nodes.append(a[0]) # -- close inner ring
                i += len_ring
                inner_ring += 1
                outer_closest.pop(0)
                nodes.append(o) # -- go back to outer ring
    else:
        nodes = range(b.nnodes_outer)

    #assert(len(X) >= len(nodes))
    if ac_name == "":
        uv = face_uv(nodes, X, b.roof_texture, angle=None)
        nodes = np.array(nodes) + b._nnodes_ground
#        uv = np.zeros((len(nodes), 2))
    else:
        uv = face_uv(nodes, X, b.roof_texture, angle=None)

#    print "len nodes", len(nodes)
    assert(len(nodes) == b._nnodes_ground + 2 * len(b.polygon.interiors))


    #if not ac_name: uv *= 0 # -- texture only separate roofs
    #print "uv, ", uv

    l = []
    for i, node in enumerate(nodes):
        l.append((node + b.first_node, uv[i][0], uv[i][1]))
#        print "roof", b.first_node, '--', l
    out.face(l)

def _flat(b):
    """plain flat roof, included in base model."""
    out = ""
    out += "SURF 0x0\n"
    out += "mat %i\n" % b.roof_mat
    out += "refs %i\n" % b.nnodes_outer
    #X = np.array(b.X_outer)
    #u = random.uniform(0, 1)
    #scale = b.lenX[0]
    #X = (X - X[0])/scale
    for i in range(b.nnodes_outer):
#        out += "%i %g %g\n" % (i+b.nnodes_outer, X[i,0], X[i,1])
        out += "%i %g %g\n" % (i+b.nnodes_outer, 0, 0)
    return out

def separate_hipped(out, b, X, max_height):
    return separate_gable(out, b, X, inward_meters = 3., max_height=max_height)

def separate_gable(out, b, X, inward_meters = 0., max_height = 1e99):
    """gable roof, 4 nodes, separate model. Inward_"""
    #out.new_object(b.roof_ac_name, b.roof_texture.filename + '.png')

    # -- pitched roof for 4 ground nodes
    t = b.roof_texture
    
    if 'roof:angle' in b.tags:
        angle = float(b.tags['roof:angle'])
    else:
        angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
    while angle > 0:
        roof_height = tan(np.deg2rad(angle)) * (b.lenX[1]/2)
        if roof_height < max_height:
            break
        angle = angle - 5
    if roof_height > max_height:
        logging.warn("roof too high %g > %g" % (roof_height, max_height))
        return False

    # -- 4 corners
    o = out.next_node_index()
    for x in X:
        out.node(-x[1], b.ground_elev + b.height - roof_height, -x[0])
    #We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height,inward_meters)

    # -- tangential vector of long edge
    tang = (X[1]-X[0])/b.lenX[1] * inward_meters

    len_roof_top = b.lenX[0] - 2.*inward_meters
    len_roof_bottom = 1.*b.lenX[0]

    out.node(-(0.5*(X[3][1]+X[0][1]) + tang[1]), b.ground_elev + b.height, -(0.5*(X[3][0]+X[0][0]) + tang[0]))
    out.node(-(0.5*(X[1][1]+X[2][1]) - tang[1]), b.ground_elev + b.height, -(0.5*(X[1][0]+X[2][0]) - tang[0]))

    roof_texture_size_x = t.h_size_meters # size of roof texture in meters
    roof_texture_size_y = t.v_size_meters
    repeatx = len_roof_bottom / roof_texture_size_x
    len_roof_hypo = ((0.5*b.lenX[1])**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo / roof_texture_size_y


    out.face([ (o + 0, t.x(0), t.y(0)),
               (o + 1, t.x(repeatx), t.y(0)),
               (o + 5, t.x(repeatx*(1-inward_meters/len_roof_bottom)), t.y(repeaty)),
               (o + 4, t.x(repeatx*(inward_meters/len_roof_bottom)), t.y(repeaty)) ])

    out.face([ (o + 2, t.x(0), t.y(0)),
               (o + 3, t.x(repeatx), t.y(0)),
               (o + 4, t.x(repeatx*(1-inward_meters/len_roof_bottom)), t.y(repeaty)),
               (o + 5, t.x(repeatx*(inward_meters/len_roof_bottom)), t.y(repeaty)) ])

    repeatx = b.lenX[1]/roof_texture_size_x
    len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo/roof_texture_size_y
    out.face([ (o + 1, t.x(0), t.y(0)),
               (o + 2, t.x(repeatx), t.y(0)),
               (o + 5, t.x(0.5*repeatx), t.y(repeaty)) ])

    repeatx = b.lenX[3]/roof_texture_size_x
    out.face([ (o + 3, t.x(0), t.y(0)),
               (o + 0, t.x(repeatx), t.y(0)),
               (o + 4, t.x(0.5*repeatx), t.y(repeaty)) ])

def separate_pyramidal(out, b, X, inward_meters = 0.0, max_height = 1.e99):
    """pyramidal roof, ? nodes, separate model. Inward_"""
    #out.new_object(b.roof_ac_name, b.roof_texture.filename + '.png')

    # -- pitched roof for ? ground nodes
    t = b.roof_texture
        
    if 'roof:height' in b.tags:
        # force clean of tag if the unit is given 
        roof_height = float(re.sub(' .*', ' ',b.tags['roof:height'].strip()))
    else :
        if 'roof:angle' in b.tags:
            angle = float(b.tags['roof:angle'])
        else:
            angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
            
        while angle > 0:
            roof_height = tan(np.deg2rad(angle)) * (b.lenX[1]/2)
            if roof_height < max_height:
                break
            angle = angle - 5
        if roof_height > max_height:
            logging.warn("roof too high %g > %g" % (roof_height, max_height))
            return False
            
    # -- ? corners
    o = out.next_node_index()
    for x in X:
        out.node(-x[1], b.ground_elev + b.height - roof_height, -x[0])

    #We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height,inward_meters)

    len_roof_top = b.lenX[0] - 2.*inward_meters
    len_roof_bottom = 1.*b.lenX[0]

    # get middle node of the "tower"
    out_1 = -sum([ xi[1] for xi in X ])/len(X)
    out_2 = -sum([ xi[0] for xi in X ])/len(X)
    out.node( out_1, b.ground_elev + b.height, out_2)

    # texture it
    roof_texture_size_x = t.h_size_meters # size of roof texture in meters
    roof_texture_size_y = t.v_size_meters

    # loop on sides of the building
    for i in range(0,len(X)) :
        repeatx = b.lenX[1]/roof_texture_size_x
        len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
        repeaty = len_roof_hypo/roof_texture_size_x
        out.face([ (o + i            , t.x(0)          , t.y(0)),
                   (o + (i+1)%len(X) , t.x(repeatx)    , t.y(0)),
                   (o + len(X)       , t.x(0.5*repeatx), t.y(repeaty)) ])



def separate_skillion2(out, b, X, inward_meters = 0., max_height = 1e99, ac_name=""):
    """skillion roof, n nodes, separate model. Inward_"""
    # - handle square skillion roof
    #   it's assumed that the first 2 nodes are at building:height-roof:height
    #                     the last  2 nodes are at building:height
    # 
    t  = b.roof_texture
    tf = b.facade_texture
    
    # -- 4 corners
    o = out.next_node_index()
    o0 = o
    for x in X:
        out.node(-x[1], b.ground_elev + b.height - b.roof_height , -x[0])

    print('SKILLION ', b.osm_id, ' ', b.tags)



    #We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(b.roof_height,inward_meters)

    # -- tangential vector of long edge
    tang = (X[1]-X[0])/b.lenX[1] * inward_meters

    len_roof_top = b.lenX[0] - 2.*inward_meters
    len_roof_bottom = 1.*b.lenX[0]

    #imax=roof_height_X.index(max(roof_height_X))
    #imax2=roof_height_X.index(max([roof_height_X((imax-1)%4),roof_height_X((imax+1)%4)]))
    
    if True :
        #
        # FLAT PART
        #
        if True : #ac_name:
            #out.new_object(ac_name, b.roof_texture.filename + '.png')
            i=0
            for x in X:
                z = b.ground_elev - 1
    #            out += "%1.2f %1.2f %1.2f\n" % (-x[1], b.ground_elev + b.height, -x[0])
                out.node(-x[1], b.ground_elev + b.height - b.roof_height + b.roof_height_X[i], -x[0])
                i+=1

        #out += "refs %i\n" % (b._nnodes_ground + 2 * len(b.polygon.interiors))

        if len(b.polygon.interiors):
            print(" len(b.polygon.interiors)")
            outer_closest = copy.copy(b.outer_nodes_closest)
            print("outer_closest = copy.copy(b.outer_nodes_closest)", outer_closest)
            i = b.nnodes_outer
            inner_ring = 0
            nodes = []
            for o in range(b.nnodes_outer):
                nodes.append(o)
                if outer_closest and o == outer_closest[0]:
                    len_ring = len(b.polygon.interiors[inner_ring].coords) - 1
                    a = np.arange(len_ring) + i
                    for x in a: nodes.append(x)
                    nodes.append(a[0]) # -- close inner ring
                    i += len_ring
                    inner_ring += 1
                    outer_closest.pop(0)
                    nodes.append(o) # -- go back to outer ring
        else:
            nodes = range(b.nnodes_outer)

        #assert(len(X) >= len(nodes))
        if False : #ac_name == "":
            uv = face_uv(nodes, X, b.roof_texture, angle=angle00)
            nodes = np.array(nodes) + b._nnodes_ground

        else:
            uv = face_uv(nodes, X, b.roof_texture, angle=None)

        assert(len(nodes) == b._nnodes_ground + 2 * len(b.polygon.interiors))

        l = []
        o=out.next_node_index()

        # create nodes for/ and roof
        for i, node in enumerate(nodes):
            #New nodes
            out.node(-X[node][1], b.ground_elev + b.height - b.roof_height + b.roof_height_X[node], -X[node][0])
            l.append((o + node, uv[i][0], uv[i][1]))
            #l.append((o + node + b.first_node, uv[i][0], uv[i][1]))
        out.face(l)

    return

def separate_skillion(out, b, X, inward_meters = 0., max_height = 1e99):
    """skillion roof, 4 nodes, separate model. Inward_"""
    # - handle square skillion roof
    #   it's assumed that the first 2 nodes are at building:height-roof:height
    #                     the last  2 nodes are at building:height
    # 
    t = b.roof_texture
    
    # -- 4 corners
    o = out.next_node_index()

    for x in X:
        out.node(-x[1], b.ground_elev + b.height, -x[0])

    if 'roof:height' in b.tags:
        # force clean of tag if the unit is given 
        roof_height = float(re.sub(' .*', ' ',b.tags['roof:height'].strip()))
    else :
        if 'roof:angle' in b.tags:
            angle = float(b.tags['roof:angle'])
        else:
            angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
            
        while angle > 0:
            roof_height = tan(np.deg2rad(angle)) * (b.lenX[1]/2)
            if roof_height < max_height:
                break
            angle = angle - 5
        if roof_height > max_height:
            logging.warn("roof too high %g > %g" % (roof_height, max_height))
            return False

    #We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height,inward_meters)

    # -- tangential vector of long edge
    tang = (X[1]-X[0])/b.lenX[1] * inward_meters

    len_roof_top = b.lenX[0] - 2.*inward_meters
    len_roof_bottom = 1.*b.lenX[0]

    out.node(-X[3][1], b.ground_elev + b.height + roof_height, -X[3][0])
    out.node(-X[2][1], b.ground_elev + b.height + roof_height, -X[2][0])

    roof_texture_size_x = t.h_size_meters # size of roof texture in meters
    roof_texture_size_y = t.v_size_meters
    repeatx = len_roof_bottom / roof_texture_size_x
    len_roof_hypo = ((0.5*b.lenX[1])**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo / roof_texture_size_y


    out.face([ (o + 0, t.x(0), t.y(0)),
               (o + 1, t.x(repeatx), t.y(0)),
               (o + 5, t.x(repeatx*(1-inward_meters/len_roof_bottom)), t.y(repeaty)),
               (o + 4, t.x(repeatx*(inward_meters/len_roof_bottom)), t.y(repeaty)) ])

    out.face([ (o + 2, t.x(0), t.y(0)),
               (o + 3, t.x(repeatx), t.y(0)),
               (o + 4, t.x(repeatx*(1-inward_meters/len_roof_bottom)), t.y(repeaty)),
               (o + 5, t.x(repeatx*(inward_meters/len_roof_bottom)), t.y(repeaty)) ])

    repeatx = b.lenX[1]/roof_texture_size_x
    len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
    repeaty = len_roof_hypo/roof_texture_size_y
    out.face([ (o + 1, t.x(0), t.y(0)),
               (o + 2, t.x(repeatx), t.y(0)),
               (o + 5, t.x(0.5*repeatx), t.y(repeaty)) ])

    repeatx = b.lenX[3]/roof_texture_size_x
    out.face([ (o + 3, t.x(0), t.y(0)),
               (o + 0, t.x(repeatx), t.y(0)),
               (o + 4, t.x(0.5*repeatx), t.y(repeaty)) ])


def _separate_flat(b, X, ac_name = ""):

    """flat roof, any number of nodes, separate model"""
    uv = face_uv(range(b.nnodes_outer), X, b.roof_texture)

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
        out += "%i %1.2f %1.2f\n" % (i, uv[i][0], uv[i][1])

    return out

def face_uv(nodes, X, texture, angle=None):
    """return list of uv coords for given face"""
    X = X[nodes]
    X = (X - X[0])
    if angle == None:
        x, y = X[1]
        angle = -atan2(y, x)
    R = np.array([[cos(angle), -sin(angle)],
                  [sin(angle),  cos(angle)]])
    uv = np.dot(X, R.transpose())
#    print "SCALE", h_scale, v_scale
#    print "X=", X
#    print "UV", uv

    uv[:,0] = texture.x(uv[:,0] / texture.h_size_meters)
    uv[:,1] = texture.y(uv[:,1] / texture.v_size_meters)
#    print "UVsca", uv
    return uv