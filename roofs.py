import copy
from enum import IntEnum, unique
import logging
from math import sin, cos, atan2, radians
from typing import List

import numpy as np

import parameters
import utils.ac3d as ac
import utils.coordinates as coord
import utils.osmstrings as s
from utils.utilities import Stats
from textures.texture import Texture, RoofManager


@unique
class RoofShape(IntEnum):
    """Matches the roof:shape in OSM, see http://wiki.openstreetmap.org/wiki/Simple_3D_buildings.

    Some of the OSM types might not be directly supported and are mapped to a different type,
    which actually is supported in osm2city.

    The enumeration should match what is provided in roofs.py and referenced in _write_roof_for_ac().
    """
    flat = 0
    skillion = 1
    gabled = 2
    hipped = 3
    pyramidal = 4
    dome = 5
    onion = 6


def map_osm_roof_shape(osm_roof_shape: str) -> RoofShape:
    """Maps OSM roof:shape tag to supported types in osm2city.

    See http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof_shape"""
    _shape = osm_roof_shape.strip()
    if len(_shape) == 0:
        return RoofShape.flat
    if _shape == 'flat':
        return RoofShape.flat
    if _shape in ['skillion', 'lean_to', 'pitched', 'shed']:
        return RoofShape.skillion
    if _shape in ['gabled', 'half-hipped', 'half_hipped', 'gambrel', 'round', 'saltbox']:
        return RoofShape.gabled
    if _shape in ['hipped', 'mansard']:
        return RoofShape.hipped
    if _shape == 'pyramidal':
        return RoofShape.pyramidal
    if _shape == 'dome':
        return RoofShape.dome
    if _shape == 'onion':
        return RoofShape.onion

    # fall back for all not directly handled OSM types
    logging.debug('Not handled roof shape found: %s. Therefore transformed to "flat".', _shape)
    return RoofShape.flat


def flat(ac_object: ac.Object, index_first_node_in_ac_obj: int, b, roof_mgr: RoofManager, roof_mat_idx: int,
         stats: Stats) -> None:
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
        # flat roof might have gotten required later in process, so we must find a new roof texture
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

    # FIXME Rick uv = face_uv(nodes, b.pts_all, b.roof_texture, angle=None)
    uv = face_uv_flat_roof(nodes, b.pts_all, b.roof_texture)
    nodes = np.array(nodes) + b.pts_all_count

    assert(len(nodes) == b.pts_all_count + 2 * len(b.polygon.interiors))

    nodes_uv_list = []
    for i, node in enumerate(nodes):
        nodes_uv_list.append((node + index_first_node_in_ac_obj, uv[i][0], uv[i][1]))
    ac_object.face(nodes_uv_list, mat_idx=roof_mat_idx)


def separate_hipped(ac_object: ac.Object, b, roof_mat_idx: int) -> None:
    return separate_gable(ac_object, b, roof_mat_idx, roof_mat_idx, inward_meters=3.)


def separate_gable(ac_object, b, roof_mat_idx: int, facade_mat_idx: int, inward_meters=0.) -> None:
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
        roof_orientation = str(b.tags[s.K_ROOF_ORIENTATION])
        if not (roof_orientation in [s.V_ALONG, s.V_ACROSS]):
            roof_orientation = s.V_ALONG
    except:
        roof_orientation = s.V_ALONG

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
            
    if roof_orientation == s.V_ACROSS:
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

    # roofs
    ac_object.face([(o + 0, t.x(0), t.y(0)),
                    (o + 1, t.x(repeat_x), t.y(0)),
                    (o + 5, t.x(repeat_x*(1-inward_meters/len_roof_bottom)), t.y(repeat_y)),
                    (o + 4, t.x(repeat_x*(inward_meters/len_roof_bottom)), t.y(repeat_y))],
                   mat_idx=roof_mat_idx)

    ac_object.face([(o + 2, t.x(0), t.y(0)),
                    (o + 3, t.x(repeat_x), t.y(0)),
                    (o + 4, t.x(repeat_x*(1-inward_meters/len_roof_bottom)), t.y(repeat_y)),
                    (o + 5, t.x(repeat_x*(inward_meters/len_roof_bottom)), t.y(repeat_y))],
                   mat_idx=roof_mat_idx)

    # sides if inward_meters = 0, else inward roofs for hipped
    len_roof_hypo = (inward_meters**2 + roof_height**2)**0.5
    repeat_y = len_roof_hypo/roof_texture_size_y
    if parameters.FLAG_2018_3 and inward_meters == 0.:
        repeat_y = 0

    repeat_x = b.edge_length_pts[ind_X[1]]/roof_texture_size_x
    if parameters.FLAG_2018_3 and inward_meters == 0.:
        repeat_x = 0
    ac_object.face([(o + 1, t.x(0), t.y(0)),
                    (o + 2, t.x(repeat_x), t.y(0)),
                    (o + 5, t.x(0.5*repeat_x), t.y(repeat_y))],
                   mat_idx=facade_mat_idx)

    repeat_x = b.edge_length_pts[ind_X[3]]/roof_texture_size_x
    if parameters.FLAG_2018_3 and inward_meters == 0.:
        repeat_x = 0
    ac_object.face([(o + 3, t.x(0), t.y(0)),
                    (o + 0, t.x(repeat_x), t.y(0)),
                    (o + 4, t.x(0.5*repeat_x), t.y(repeat_y))],
                   mat_idx=facade_mat_idx)


def separate_pyramidal(ac_object: ac.Object, b, roof_mat_idx: int, shape: RoofShape) -> None:
    """Pyramidal, dome or onion roof."""
    roof_texture = b.roof_texture
        
    # -- get roof height 
    if b.roof_height:
        roof_height = b.roof_height 
    else:
        return

    bottom = b.beginning_of_roof_above_sea_level
            
    # add nodes for each of the corners
    object_node_index = ac_object.next_node_index()
    prev_ring = list()
    for pt in b.pts_all:
        ac_object.node(-pt[1], bottom, -pt[0])
        prev_ring.append([pt[0], pt[1]])

    # calculate node for the middle node of the roof
    x_centre = sum([xi[0] for xi in b.pts_all])/len(b.pts_all)
    y_centre = sum([xi[1] for xi in b.pts_all])/len(b.pts_all)

    ring = b.pts_all
    top = bottom + roof_height

    if shape in [RoofShape.dome, RoofShape.onion]:
        # For dome and onion we need to add new rings and faces before the top
        height_share = list()  # the share of the roof height by each ring
        radius_share = list()  # the share of the radius by each ring
        if shape is RoofShape.dome:  # we use five additional rings
            height_share = [sin(radians(90 / 6)),
                            sin(radians(90 * 2 / 6)),
                            sin(radians(90 * 3 / 6)),
                            sin(radians(90 * 4 / 6)),
                            sin(radians(90 * 5 / 6))
            ]

            radius_share = [cos(radians(90 / 6)),
                            cos(radians(90 * 2 / 6)),
                            cos(radians(90 * 3 / 6)),
                            cos(radians(90 * 4 / 6)),
                            cos(radians(90 * 5 / 6))
            ]
        else:  # we use five additional rings based on guessed values - onion diameter gets broader than drum
            height_share = [.1, .2, .3, .4, .5, .7]

            radius_share = [1.2, 1.25, 1.2, 1., .6, .2]

        # texture it
        roof_texture_size = roof_texture.h_size_meters  # size of roof texture in meters

        n_pts = len(ring)
        for r in range(0, len(height_share)):
            ring = list()
            top = bottom + roof_height * height_share[r]
            # calculate the new points of the ring
            for pt in b.pts_all:
                x, y = coord.calc_point_on_line_local(pt[0], pt[1], x_centre, y_centre, 1 - radius_share[r])
                ac_object.node(-y, top, -x)
                ring.append([x, y])

            # create the faces
            prev_offset = r * n_pts
            this_offset = (r+1) * n_pts
            for i in range(0, n_pts):
                j = (i + 1) % n_pts  # little trick to reset to 0
                dist_edge = coord.calc_distance_local(ring[i][0], ring[i][1], ring[j][0], ring[j][1])
                dist_edge_prev = coord.calc_distance_local(prev_ring[i][0], prev_ring[i][1],
                                                           prev_ring[j][0], prev_ring[j][1])
                ring_height_diff = height_share[r] * roof_height
                ring_radius_diff = coord.calc_distance_local(ring[i][0], ring[i][1], prev_ring[i][0], prev_ring[i][1])
                len_roof_hypo = (ring_height_diff ** 2 + ring_radius_diff ** 2) ** 0.5
                repeat_x = dist_edge / roof_texture_size
                repeat_y = len_roof_hypo / roof_texture_size
                ac_object.face([(object_node_index + i + prev_offset, roof_texture.x(0), roof_texture.y(0)),
                                (object_node_index + j + prev_offset, roof_texture.x(repeat_x), roof_texture.y(0)),
                                (object_node_index + j + this_offset, roof_texture.x(repeat_x), roof_texture.y(repeat_y)),
                                (object_node_index + i + this_offset, roof_texture.x(0), roof_texture.y(repeat_y))],
                               mat_idx=roof_mat_idx)

            prev_ring = copy.deepcopy(ring)

        # prepare for pyramidal top
        top = bottom + roof_height
        bottom = bottom + roof_height * height_share[-1]
        object_node_index += len(height_share) * n_pts

    # add the pyramidal top
    _pyramidal_top(ac_object, x_centre, y_centre, top,
                   roof_texture, roof_mat_idx, top - bottom,
                   ring, object_node_index)


def _pyramidal_top(ac_object: ac.Object, x_centre: float, y_centre: float, top: float,
                   roof_texture, roof_mat_idx: int, pyramid_height: float,
                   ring: List[List[float]], object_node_index: int) -> None:
    """Adds the pyramidal top by adding the centre node and the necessary faces.

    ring is a list of x,y coordinates for the current top points of the roof.
    """
    # add node for the middle of the roof
    ac_object.node(-1 * y_centre, top, -1 * x_centre)

    roof_texture_size = roof_texture.h_size_meters

    # loop on sides of the building
    n_pts = len(ring)  # number of points
    for i in range(0, n_pts):
        dist_inwards = coord.calc_distance_local(ring[i][0], ring[i][1], x_centre, y_centre)
        j = (i+1) % n_pts
        dist_edge = coord.calc_distance_local(ring[i][0], ring[i][1], ring[j][0], ring[j][1])
        len_roof_hypo = (dist_inwards ** 2 + pyramid_height ** 2) ** 0.5
        repeat_x = dist_edge/roof_texture_size
        repeat_y = len_roof_hypo/roof_texture_size
        ac_object.face([(object_node_index + i, roof_texture.x(0), roof_texture.y(0)),
                        (object_node_index + j, roof_texture.x(repeat_x), roof_texture.y(0)),
                        (object_node_index + n_pts, roof_texture.x(0.5*repeat_x), roof_texture.y(repeat_y))],
                       mat_idx=roof_mat_idx)


def separate_skillion(ac_object: ac.Object, b, roof_mat_idx: int):
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
    ac_object.face(nodes_uv_list, mat_idx=roof_mat_idx)
    return


def face_uv(nodes: List[int], pts_all, texture: Texture, angle=None):
    """return list of uv coordinates for given face"""
    pts_all = pts_all[nodes]
    pts_all = (pts_all - pts_all[0])
    if angle is None:
        x, y = pts_all[1]
        angle = -atan2(y, x)
    rotation = np.array([[cos(angle), -sin(angle)],
                        [sin(angle),  cos(angle)]])
    uv = np.dot(pts_all, rotation.transpose())

    uv[:, 0] = texture.x(uv[:, 0] / texture.h_size_meters)
    uv[:, 1] = texture.y(uv[:, 1] / texture.v_size_meters)
    return uv


def face_uv_flat_roof(nodes: List[int], pts_all, texture: Texture):
    """Special handling for flat roofs."""
    pts_all = pts_all[nodes]

    # rotate the roof to align with edge between first and second node
    x0, y0 = pts_all[0]
    x1, y1 = pts_all[1]
    angle = -atan2(y1 - y0, x1 - x0)
    rotation = np.array([[cos(angle), -sin(angle)],
                        [sin(angle),  cos(angle)]])
    uv = np.dot(pts_all, rotation.transpose())

    # make sure all is translated to positive values
    min_x = 99999.
    min_y = 99999.
    max_x = -99999.
    max_y = -99999.
    for pt in uv:
        min_x = min(min_x, pt[0])
        min_y = min(min_y, pt[1])
        max_x = max(max_x, pt[0])
        max_y = max(max_y, pt[1])
    min_pt = np.array([min_x, min_y])
    uv = (uv - min_pt)
    max_x -= min_x
    max_y -= min_y

    # check whether texture might be smaller in one or the other dimension
    h_ratio = max_x / texture.h_size_meters
    v_ratio = max_y / texture.v_size_meters
    max_ratio = max(h_ratio, v_ratio)
    scale_factor = 1.
    if max_ratio > 1.:
        scale_factor = max_ratio  # meaning we artifically make the texture larger
    uv[:, 0] = texture.x(uv[:, 0] / (texture.h_size_meters * scale_factor))
    uv[:, 1] = texture.y(uv[:, 1] / (texture.v_size_meters * scale_factor))
    return uv
