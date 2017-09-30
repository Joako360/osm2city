import copy
import logging
from math import sin, cos, atan2
from typing import List

import numpy as np

import utils.ac3d as ac
from utils.utilities import Stats
from textures.texture import Texture, RoofManager


def flat(ac_object: ac.Object, index_first_node_in_ac_obj: int, b, roof_mgr: RoofManager, stats: Stats) -> None:
    """Flat roof. Also works for relations."""
    #   3-----------------2  Outer is CCW: 0 1 2 3
    #   |                /|  Inner[0] is CW: 4 5 6 7
    #   |         11----8 |  Inner[1] is CW: 8 9 10 11
    #   | 5----6  |     | |  Inner rings are rolled such that their first nodes
    #   | |    |  10-<<-9 |  are closest to an outer node. (see b.roll_inner_nodes)
    #   | 4-<<-7          |
    #   |/                |  draw 0 - 4 5 6 7 4 - 0 1 2 - 8 9 10 11 8 - 2 3
    #   0---->>-----------1
    if b.roof_texture is None:
        raise ValueError("Roof texture None")

    if "compat:roof-flat" not in b.roof_requires:
        logging.debug("Replacing texture for flat roof despite " + str(b.roof_requires))
        if "compat:roof-pitched" in b.roof_requires:
            b.roof_requires.remove("compat:roof-pitched")
        b.roof_requires.append("compat:roof-flat")
        b.roof_texture = roof_mgr.find_matching_roof(b.roof_requires, b.longest_edge_length, stats)

    if b.polygon.interiors:
        outer_closest = copy.copy(b.outer_nodes_closest)
        i = b.pts_outer_count
        inner_ring = 0
        nodes = []
        for o in range(b.pts_outer_count):
            nodes.append(o)
            if outer_closest and o == outer_closest[0]:
                len_ring = len(b.polygon.interiors[inner_ring].coords) - 1
                a = np.arange(len_ring) + i
                for x in a:
                    nodes.append(x)
                nodes.append(a[0])  # -- close inner ring
                i += len_ring
                inner_ring += 1
                outer_closest.pop(0)
                nodes.append(o)  # -- go back to outer ring
    else:
        nodes = list(range(b.pts_outer_count))

    uv = face_uv(nodes, b.pts_all, b.roof_texture, angle=None)
    nodes = np.array(nodes) + b.pts_all_count

    assert(len(nodes) == b.pts_all_count + 2 * len(b.polygon.interiors))

    nodes_uv_list = []
    for i, node in enumerate(nodes):
        nodes_uv_list.append((node + index_first_node_in_ac_obj, uv[i][0], uv[i][1]))
    ac_object.face(nodes_uv_list)


def separate_hipped(ac_object: ac.Object, b) -> None:
    return separate_gable(ac_object, b, inward_meters=3.)


def separate_gable(ac_object, b, inward_meters=0.) -> None:
    """gable roof, 4 nodes, separate model. Inward_"""
    # -- pitched roof for 4 ground nodes
    t = b.roof_texture
    
    if b.roof_height:
        roof_height = b.roof_height
    else:
        logging.error("no roof_height in separate_gable for building %i" % b.osm_id)
        return
    
    # get orientation if exits :
    try:
        roof_orientation = str(b.tags['roof:orientation'])
        if not (roof_orientation in ['along', 'across']):
            roof_orientation = 'along'
    except:
        roof_orientation = 'along'

    # search smallest and longest sides
    i_small = 3
    i_long = 3
    l_side2 = (b.pts_all[0][0] - b.pts_all[3][0])**2 + (b.pts_all[0][1] - b.pts_all[3][1])**2
    l_small = l_side2
    l_long = l_side2
    
    for i in range(0, 3):
        l_side2 = (b.pts_all[i+1][0] - b.pts_all[i][0])**2 + (b.pts_all[i+1][1] - b.pts_all[i][1])**2
        if l_side2 > l_long:
            i_long = i
            l_long = l_side2
        elif l_side2 < l_small:
            i_small = i
            l_small = l_side2
            
    if roof_orientation == 'across':
        i_side = i_small
    else:
        i_side = i_long

    ind_X = []
    for i in range(0, 4):
        ind_X.append((i_side + i) % 4)
    
    # -- 4 corners
    o = ac_object.next_node_index()
    for i in range(0, 4):
        ac_object.node(-b.pts_all[ind_X[i]][1], b.beginning_of_roof_above_sea_level, -b.pts_all[ind_X[i]][0])
    # We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height, inward_meters)

    # -- tangential vector of long edge
    tang = (b.pts_all[ind_X[1]]-b.pts_all[ind_X[0]])/b.edge_length_pts[ind_X[1]] * inward_meters
    
    len_roof_bottom = 1.*b.edge_length_pts[ind_X[0]]

    ac_object.node(-(0.5 * (b.pts_all[ind_X[3]][1] + b.pts_all[ind_X[0]][1]) + tang[1]), b.top_of_roof_above_sea_level,
                   -(0.5*(b.pts_all[ind_X[3]][0] + b.pts_all[ind_X[0]][0]) + tang[0]))
    ac_object.node(-(0.5 * (b.pts_all[ind_X[1]][1] + b.pts_all[ind_X[2]][1]) - tang[1]), b.top_of_roof_above_sea_level,
                   -(0.5*(b.pts_all[ind_X[1]][0] + b.pts_all[ind_X[2]][0]) - tang[0]))

    roof_texture_size_x = t.h_size_meters  # size of roof texture in meters
    roof_texture_size_y = t.v_size_meters
    repeat_x = len_roof_bottom / roof_texture_size_x
    len_roof_hypo = ((0.5*b.edge_length_pts[ind_X[1]])**2 + roof_height**2)**0.5
    repeat_y = len_roof_hypo / roof_texture_size_y

    ac_object.face([(o + 0, t.x(0), t.y(0)),
                    (o + 1, t.x(repeat_x), t.y(0)),
                    (o + 5, t.x(repeat_x*(1-inward_meters/len_roof_bottom)), t.y(repeat_y)),
                    (o + 4, t.x(repeat_x*(inward_meters/len_roof_bottom)), t.y(repeat_y))])

    ac_object.face([(o + 2, t.x(0), t.y(0)),
                    (o + 3, t.x(repeat_x), t.y(0)),
                    (o + 4, t.x(repeat_x*(1-inward_meters/len_roof_bottom)), t.y(repeat_y)),
                    (o + 5, t.x(repeat_x*(inward_meters/len_roof_bottom)), t.y(repeat_y))])

    repeat_x = b.edge_length_pts[ind_X[1]]/roof_texture_size_x
    len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
    repeat_y = len_roof_hypo/roof_texture_size_y
    ac_object.face([(o + 1, t.x(0), t.y(0)),
                    (o + 2, t.x(repeat_x), t.y(0)),
                    (o + 5, t.x(0.5*repeat_x), t.y(repeat_y))])

    repeat_x = b.edge_length_pts[ind_X[3]]/roof_texture_size_x
    ac_object.face([(o + 3, t.x(0), t.y(0)),
                    (o + 0, t.x(repeat_x), t.y(0)),
                    (o + 4, t.x(0.5*repeat_x), t.y(repeat_y))])


def separate_pyramidal(ac_object: ac.Object, b, inward_meters=0.0) -> None:
    """pyramidal roof, ? nodes, separate model. Inward_"""
    # -- pitched roof for ? ground nodes
    t = b.roof_texture
        
    # -- get roof height 
    if b.roof_height:
        roof_height = b.roof_height 
    else:
        return
            
    # -- ? corners
    o = ac_object.next_node_index()
    for pt in b.pts_all:
        ac_object.node(-pt[1], b.beginning_of_roof_above_sea_level, -pt[0])

    # We don't want the hipped part to be greater than the height, which is 45 deg
    inward_meters = min(roof_height, inward_meters)

    # get middle node of the "tower"
    out_1 = -sum([xi[1] for xi in b.pts_all])/len(b.pts_all)
    out_2 = -sum([xi[0] for xi in b.pts_all])/len(b.pts_all)
    ac_object.node(out_1, b.top_of_roof_above_sea_level, out_2)

    # texture it
    roof_texture_size_pt = t.h_size_meters  # size of roof texture in meters

    # loop on sides of the building
    for i in range(0, len(b.pts_all)):
        repeat_x = b.edge_length_pts[1]/roof_texture_size_pt
        len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
        repeat_y = len_roof_hypo/roof_texture_size_pt
        ac_object.face([(o + i, t.x(0), t.y(0)),
                        (o + (i+1) % len(b.pts_all), t.x(repeat_x), t.y(0)),
                        (o + len(b.pts_all), t.x(0.5*repeat_x), t.y(repeat_y))])


def separate_skillion(ac_object: ac.Object, b):
    """skillion roof, n nodes, separate model. Inward_"""
    # - handle square skillion roof
    #   it's assumed that the first 2 nodes are at building:height-roof:height
    #                     the last  2 nodes are at building:height
    # -- 4 corners
    object_node_index = ac_object.next_node_index()
    for x in b.pts_all:
        ac_object.node(-x[1], b.beginning_of_roof_above_sea_level, -x[0])

    # We don't want the hipped part to be greater than the height, which is 45 deg

    # FLAT PART
    i = 0
    for pt in b.pts_all:
        ac_object.node(-pt[1], b.beginning_of_roof_above_sea_level + b.roof_height_pts[i], -pt[0])
        i += 1

    if b.polygon.interiors:
        print(" len(b.polygon.interiors)")
        outer_closest = copy.copy(b.outer_nodes_closest)
        print(("outer_closest = copy.copy(b.outer_nodes_closest)", outer_closest))
        i = b.pts_outer_count
        inner_ring = 0
        nodes = []
        for object_node_index in range(b.pts_outer_count):
            nodes.append(object_node_index)
            if outer_closest and object_node_index == outer_closest[0]:
                len_ring = len(b.polygon.interiors[inner_ring].coords) - 1
                a = np.arange(len_ring) + i
                for x in a:
                    nodes.append(x)
                nodes.append(a[0])  # -- close inner ring
                i += len_ring
                inner_ring += 1
                outer_closest.pop(0)
                nodes.append(object_node_index)  # -- go back to outer ring
    else:
        nodes = list(range(b.pts_outer_count))

    uv = face_uv(nodes, b.pts_all, b.roof_texture, angle=None)

    assert(len(nodes) == b.pts_all_count + 2 * len(b.polygon.interiors))

    nodes_uv_list = []
    object_node_index = ac_object.next_node_index()

    # create nodes for/ and roof
    for i, node in enumerate(nodes):
        # new nodes
        ac_object.node(-b.pts_all[node][1], b.beginning_of_roof_above_sea_level + b.roof_height_pts[node],
                       -b.pts_all[node][0])
        nodes_uv_list.append((object_node_index + node, uv[i][0], uv[i][1]))
    ac_object.face(nodes_uv_list)
    return


def face_uv(nodes: List[int], pts_all, texture: Texture, angle=None):
    """return list of uv coordinates for given face"""
    pts_all = pts_all[nodes]
    pts_all = (pts_all - pts_all[0])
    if angle is None:
        x, y = pts_all[1]
        angle = -atan2(y, x)
    R = np.array([[cos(angle), -sin(angle)],
                  [sin(angle),  cos(angle)]])
    uv = np.dot(pts_all, R.transpose())

    uv[:, 0] = texture.x(uv[:, 0] / texture.h_size_meters)
    uv[:, 1] = texture.y(uv[:, 1] / texture.v_size_meters)
    return uv
