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
    
    # -- 4 corners
    o = out.next_node_index()
    for x in X:
        out.node(-x[1], b.ground_elev + b.height, -x[0])
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

    out.node(-(0.5*(X[3][1]+X[0][1]) + tang[1]), b.ground_elev + b.height + roof_height, -(0.5*(X[3][0]+X[0][0]) + tang[0]))
    out.node(-(0.5*(X[1][1]+X[2][1]) - tang[1]), b.ground_elev + b.height + roof_height, -(0.5*(X[1][0]+X[2][0]) - tang[0]))

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
    
    # -- ? corners
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

    len_roof_top = b.lenX[0] - 2.*inward_meters
    len_roof_bottom = 1.*b.lenX[0]

    # get middle node of the "tower"
    out_1 = -sum([ xi[1] for xi in X ])/len(X)
    out_2 = -sum([ xi[0] for xi in X ])/len(X)
    out.node( out_1, b.ground_elev + b.height + roof_height, out_2)

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
            angle = angle - 1
        if roof_height > max_height:
            logging.warn("roof too high %g > %g" % (roof_height, max_height))
            return False


    # -- 4 corners
    o = out.next_node_index()
    o0 = o
    for x in X:
        out.node(-x[1], b.ground_elev + b.height, -x[0])

    print('SKILLION ', b.osm_id, ' ', b.tags)

    if 'roof:slope:direction' in b.tags :
        # Input angle
        # angle are given clock wise with reference 0 as north
        # 
        # angle 0 north
        # angle 90 east
        # angle 180 south
        # angle 270 west
        # angle 360 north
        #
        # here we works with trigo angles 
        angle00 = ( pi/2. - (((float(b.tags['roof:slope:direction']) )%360.)*pi/180.)  )
        angle90 = angle00 + pi/2.
        ibottom = 0
        # assume that first point is on the bottom side of the roof
        # and is a reference point (0,0)
        # compute line slope*x
        
        slope=sin(angle90)
        
        dir1 = (cos(angle90),slope)
        ndir1 = 1 #sqrt(1 + slope**2)
        dir1n =  (cos(angle90),slope)#(1/ndir1, slope/ndir1)
        
        print("dir1n", dir1n)
        # keep in mind direction
        #if angle90 < 270 and angle90 >= 90 :
        #    #dir1, dir1n = -dir1, -dir1n
        #    dir1=(-dir1[0],-dir1[1])
        #    dir1n=(-dir1n[0],-dir1n[1])

        # compute distance from points to line slope*x
        X2=list()
        XN=list()
        nXN=list()
        vprods=list()
        
        p0=(X[0][0], X[0][1])
        for i in range(0,len(X)):
            # compute coord in new referentiel
            vecA =  (X[i][0]-p0[0], X[i][1]-p0[1] )
            X2.append( vecA )             
            # 
            norm = vecA[0]*dir1n[0] + vecA[1]*dir1n[1]
            vecN = ( vecA[0] - norm*dir1n[0], vecA[1] - norm*dir1n[1] )
            nvecN = sqrt( vecN[0]**2 + vecN[1]**2 )
            # store vec and norms
            XN.append(vecN)
            nXN.append(nvecN)
            # compute ^ product
            vprod = dir1n[0]*vecN[1]-dir1n[1]*vecN[0]
            vprods.append(vprod)
    
        # if first point was not on bottom side, one must find the right point
        # and correct distances
        if min(vprods) < 0 :
            ibottom=vprods.index(min(vprods))
            offset=nXN[ibottom]
            norms_o=[ nXN[i] + offset if vprods[i] >=0 else -nXN[i] + offset for i in range(0,len(X)) ] #oriented norm
        else :
            norms_o=nXN

        # compute height for each point with thales
        L = float(max(norms_o)) 
        print('--- ID',b.osm_id)
        print("norms_o", norms_o)
        print("roof_height",roof_height)
        print("roof_height tag", str(b.tags['roof:height']))
        print("b.height", str(b.height))

        try :
            roof_height_X=[ roof_height*l/L for l in norms_o  ]
            # try to simplify
            if len(roof_height_X) in [3,4] :
                for i in range(0,len(roof_height_X)) :
                    if roof_height_X[i]             < 0.5 : roof_height_X[i] = 0
                    if roof_height-roof_height_X[i] < 0.5 : roof_height_X[i] = roof_height
        except :
            logging.warn("skillion roof with estimated width of 0")
    else :
        return

    # loop on sides of the building
    #for i in range(0,len(X)) :
    #    repeatx = b.lenX[1]/roof_texture_size_x
    #    len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
    #    repeaty = len_roof_hypo/roof_texture_size_x
    #    out.face([ (o + i            , t.x(0)          , t.y(0)),
    #               (o + (i+1)%len(X) , t.x(repeatx)    , t.y(0)),
    #               (o + len(X)       , t.x(0.5*repeatx), t.y(repeaty)) ])

    print('there')
    #We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height,inward_meters)

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
                out.node(-x[1], b.ground_elev + b.height + roof_height_X[i], -x[0])
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
            print("else len(b.polygon.interiors)")
            nodes = range(b.nnodes_outer)

        #assert(len(X) >= len(nodes))
        if False : #ac_name == "":
            uv = face_uv(nodes, X, b.roof_texture, angle=angle00)
            nodes = np.array(nodes) + b._nnodes_ground

        else:
            uv = face_uv(nodes, X, b.roof_texture, angle=None)

        assert(len(nodes) == b._nnodes_ground + 2 * len(b.polygon.interiors))


        #if not ac_name: uv *= 0 # -- texture only separate roofs
        #print "uv, ", uv

        l = []
        o=out.next_node_index()

        #for i in range(0,len(nodes)):
        #    out.node(-X[i][1], b.ground_elev + b.height + roof_height_X[i], -X[i][0])
        #for i, node in enumerate(nodes):
        #    #out.node(-X[node][1], b.ground_elev + b.height + roof_height_X[node], -X[node][0])

        # create nodes for/ and roof
        for i, node in enumerate(nodes):
            #New nodes
            out.node(-X[node][1], b.ground_elev + b.height + roof_height_X[node], -X[node][0])
            l.append((o + node, uv[i][0], uv[i][1]))
            #l.append((o + node + b.first_node, uv[i][0], uv[i][1]))
        out.face(l)

        # create faces for sides
        nn=len(nodes)
        facade_texture_size_x = tf.h_size_meters # size of roof texture in meters
        facade_texture_size_y = tf.v_size_meters
        for i in range(0,nn):
            if (roof_height_X[i] - roof_height_X[0]) > 0.01 or (roof_height_X[(i+1)%nn] - roof_height_X[0]) > 0.01 : 
                ipp = (i+1)%nn
                repeatx       = b.lenX[i]/facade_texture_size_x
                len_roof_hypo = ( roof_height**2)**0.5
                #repeaty_i       = len_roof_hypo/roof_texture_size_y
                repeaty_i       =  roof_height_X[i  ]/facade_texture_size_y
                repeaty_ipp     =  roof_height_X[ipp]/facade_texture_size_y
                delta           =  repeaty_ipp - repeaty_i
                delta = ( 0, -delta )  if repeaty_i > repeaty_ipp else ( delta, 0)
                
                out.face([(o0 + nodes[i]  , tf.x(0),       tf.y(max(1-repeaty_i   - delta[0],0))), 
                          (o0 + nodes[ipp], tf.x(repeatx), tf.y(max(1-repeaty_ipp - delta[1],0))), 
                          (o  + nodes[ipp], tf.x(repeatx), tf.y(1-delta[1])), 
                          (o  + nodes[i]  , tf.x(0),       tf.y(1-delta[0]))]    )

        #exit(1)

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
