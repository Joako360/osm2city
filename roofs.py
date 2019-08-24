import copy
from enum import IntEnum, unique
import logging
from math import sin, cos, atan2, radians, tan, sqrt, fabs
from typing import List
import unittest

import numpy as np

import utils.ac3d as ac
import utils.coordinates as coord
import utils.osmstrings as s
from utils.utilities import Stats
from textures.texture import Texture, RoofManager

GAMBREL_ANGLE_LOWER_PART = 70
GAMBREL_HEIGHT_RATIO_LOWER_PART = 0.75


def roof_looks_square(circumference: float, area: float) -> bool:
    """Determines if a roof's floor plan looks square.
    The formula basically states that if it was a rectangle, then the ratio between the long side length
    and the short side length should be at least 2.
    """
    if circumference < 3 * sqrt(2 * area):
        return True
    return False


@unique
class RoofShape(IntEnum):
    """Matches the roof:shape in OSM, see http://wiki.openstreetmap.org/wiki/Simple_3D_buildings.

    Some of the OSM types might not be directly supported and are mapped to a different type,
    which actually is supported in osm2city.

    The enumeration should match what is provided in roofs.py and referenced in _write_roof_for_ac().

    The values need to correspond to the S value in FG BUILDING_LIST
    """
    flat = 0
    skillion = 1
    gabled = 2
    half_hipped = 3
    hipped = 4
    pyramidal = 5
    gambrel = 6
    mansard = 7
    dome = 8
    onion = 9
    round = 10
    saltbox = 11
    skeleton = 99  # does not exist in OSM


def map_osm_roof_shape(osm_roof_shape: str) -> RoofShape:
    """Maps OSM roof:shape tag to supported types in osm2city.

    See http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof_shape"""
    _shape = osm_roof_shape.strip()
    if len(_shape) == 0:
        return RoofShape.flat
    if _shape == s.V_FLAT:
        return RoofShape.flat
    if _shape in ['skillion', 'lean_to', 'pitched', 'shed']:
        return RoofShape.skillion
    if _shape in ['gabled', 'half-hipped', 'saltbox']:
        return RoofShape.gabled
    if _shape in ['gambrel', 'round']:
        return RoofShape.gambrel
    if _shape in ['hipped', 'mansard']:
        return RoofShape.hipped
    if _shape == 'pyramidal':
        return RoofShape.pyramidal
    if _shape == 'dome':
        return RoofShape.dome
    if _shape == 'onion':
        return RoofShape.onion

    # fall back for all not directly handled OSM types. The rational for using "hipped" as default is that most
    # probably if someone actually has tried to specify a shape, then 'flat' is unliekly to be misspelled and
    # most probably a form with a ridge was meant.
    logging.debug('Not handled roof shape found: %s. Therefore transformed to "hipped".', _shape)
    return RoofShape.skeleton


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

    uv = _face_uv_flat_roof(nodes, b.pts_all, b.roof_texture)
    nodes = np.array(nodes) + b.pts_all_count

    assert(len(nodes) == b.pts_all_count + 2 * len(b.polygon.interiors))

    nodes_uv_list = []
    for i, node in enumerate(nodes):
        nodes_uv_list.append((node + index_first_node_in_ac_obj, uv[i][0], uv[i][1]))
    ac_object.face(nodes_uv_list, mat_idx=roof_mat_idx)


def separate_hipped(ac_object: ac.Object, b, roof_mat_idx: int) -> None:
    return separate_gable(ac_object, b, roof_mat_idx, roof_mat_idx, inward_meters=2.)


def separate_gable(ac_object, b, roof_mat_idx: int, facade_mat_idx: int, inward_meters=0.) -> None:
    """Gabled roof (or hipped if inward_meters > 0) with 4 nodes."""
    t = b.roof_texture
    
    if b.roof_height:
        roof_height = b.roof_height
    else:
        my_type = 'separate_gable'
        if inward_meters > 0:
            my_type = 'separate_hipped'
        logging.warning("no roof_height in %s for building %i", my_type, b.osm_id)
        roof_height = 2.0
    
    # get orientation if exits:
    osm_roof_orientation_exists = False
    if s.K_ROOF_ORIENTATION in b.tags:
        osm_roof_orientation_exists = True
        osm_roof_orientation = str(b.tags[s.K_ROOF_ORIENTATION])
        if not (osm_roof_orientation in [s.V_ALONG, s.V_ACROSS]):
            osm_roof_orientation_exists = False
            osm_roof_orientation = s.V_ALONG
    else:
        osm_roof_orientation = s.V_ALONG

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

    i_side = i_long  # i.e. "along"
    if osm_roof_orientation_exists:
        if osm_roof_orientation == s.V_ACROSS:
            i_side = i_small
    elif b.roof_neighbour_orientation >= 0.:  # only override if we have neighbours
        # calculate the angle of the "along"
        along_angle = coord.calc_angle_of_line_local(b.pts_all[i_long % 4][0],
                                                     b.pts_all[i_long % 4][1],
                                                     b.pts_all[(i_long + 1) % 4][0],
                                                     b.pts_all[(i_long + 1)% 4][1])
        if along_angle >= 180.:
            along_angle -= 180.
        difference = fabs(b.roof_neighbour_orientation - along_angle)
        # if the difference is closer to 90 than parallel, then change the orientation
        if 45 < difference < 135:
            i_side = i_small

    seq_n = []  # the sequence of nodes such that 0-1 and 2-3 are along with ridge in parallel in the middle
    for i in range(0, 4):
        seq_n.append((i_side + i) % 4)

    object_node_index = ac_object.next_node_index()  # must be before nodes are added!
    # -- 4 corners
    for i in range(0, 4):
        ac_object.node(-b.pts_all[seq_n[i]][1], b.beginning_of_roof_above_sea_level, -b.pts_all[seq_n[i]][0])
    # We don't want the hipped part to be larger than the height, which is 45 deg
    inward_meters = min(roof_height, inward_meters)

    if inward_meters > 0. and b.roof_shape is RoofShape.hipped:
        # -- tangential vector of long edge (always [0, 0] if not hipped (because inward meters = 0)
        tang = (b.pts_all[seq_n[1]]-b.pts_all[seq_n[0]])/b.edge_length_pts[seq_n[1]] * inward_meters
    else:
        tang = [0., 0.]

    # nodes for the ridge with indexes 4 and 5
    point_4 = coord.calc_point_on_line_local(b.pts_all[seq_n[0]][0], b.pts_all[seq_n[0]][1],
                                             b.pts_all[seq_n[3]][0], b.pts_all[seq_n[3]][1],
                                             0.5)
    point_5 = coord.calc_point_on_line_local(b.pts_all[seq_n[1]][0], b.pts_all[seq_n[1]][1],
                                             b.pts_all[seq_n[2]][0], b.pts_all[seq_n[2]][1],
                                             0.5)
    ac_object.node(-point_4[1], b.top_of_roof_above_sea_level, -point_4[0])
    ac_object.node(-point_5[1], b.top_of_roof_above_sea_level, -point_5[0])

    # after the nodes now the faces
    # The front and back have not necessarily the same length, as the
    # 4 sides might not make a perfect rectangle)
    len_roof_bottom_front = b.edge_length_pts[seq_n[0]]
    len_roof_bottom_back = b.edge_length_pts[seq_n[2]]
    len_roof_ridge = (len_roof_bottom_front + len_roof_bottom_back) / 2.

    roof_texture_size_x = t.h_size_meters  # size of roof texture in meters
    roof_texture_size_y = t.v_size_meters
    repeat_x_front = ((len_roof_bottom_front + len_roof_ridge) / 2) / roof_texture_size_x
    repeat_x_back = ((len_roof_bottom_back + len_roof_ridge) / 2) / roof_texture_size_x

    if b.roof_shape in [RoofShape.gabled, RoofShape.hipped]:
        # roofs
        len_roof_hypo = ((0.5*b.edge_length_pts[seq_n[1]])**2 + roof_height**2)**0.5
        repeat_y = len_roof_hypo / roof_texture_size_y

        ac_object.face([(object_node_index + 0, t.x(0), t.y(0)),
                        (object_node_index + 1, t.x(repeat_x_front), t.y(0)),
                        (object_node_index + 5, t.x(repeat_x_front*(1-inward_meters/len_roof_bottom_front)), t.y(repeat_y)),
                        (object_node_index + 4, t.x(repeat_x_front*(inward_meters/len_roof_bottom_front)), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)

        ac_object.face([(object_node_index + 2, t.x(0), t.y(0)),
                        (object_node_index + 3, t.x(repeat_x_back), t.y(0)),
                        (object_node_index + 4, t.x(repeat_x_back*(1-inward_meters/len_roof_bottom_back)), t.y(repeat_y)),
                        (object_node_index + 5, t.x(repeat_x_back*(inward_meters/len_roof_bottom_back)), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)

        # sides
        # if roof is hipped, then facade_mat_idx is actually roof_mat_idx
        base_len = (inward_meters**2 + b.edge_length_pts[seq_n[1]]**2)**0.5
        len_roof_hypo = (base_len**2 + roof_height**2)**0.5
        repeat_y = len_roof_hypo/roof_texture_size_y
        repeat_x = b.edge_length_pts[seq_n[1]]/roof_texture_size_x
        ac_object.face([(object_node_index + 1, t.x(0), t.y(0)),
                        (object_node_index + 2, t.x(repeat_x), t.y(0)),
                        (object_node_index + 5, t.x(0.5*repeat_x), t.y(repeat_y))],
                       mat_idx=facade_mat_idx)

        base_len = (inward_meters**2 + b.edge_length_pts[seq_n[3]]**2)**0.5
        len_roof_hypo = (base_len**2 + roof_height**2)**0.5
        repeat_y = len_roof_hypo/roof_texture_size_y
        repeat_x = b.edge_length_pts[seq_n[3]]/roof_texture_size_x
        ac_object.face([(object_node_index + 3, t.x(0), t.y(0)),
                        (object_node_index + 0, t.x(repeat_x), t.y(0)),
                        (object_node_index + 4, t.x(0.5*repeat_x), t.y(repeat_y))],
                       mat_idx=facade_mat_idx)
    else:  # b.roof_shape is RoofShape.gambrel. point_4 and point_5 on ridge still valid
        away_from_edge = GAMBREL_HEIGHT_RATIO_LOWER_PART * roof_height / tan(radians(GAMBREL_ANGLE_LOWER_PART))
        distance_across_left = coord.calc_distance_local(b.pts_all[seq_n[0]][1], b.pts_all[seq_n[0]][0],
                                                         b.pts_all[seq_n[3]][1], b.pts_all[seq_n[3]][0])
        distance_across_right = coord.calc_distance_local(b.pts_all[seq_n[1]][1], b.pts_all[seq_n[1]][0],
                                                          b.pts_all[seq_n[2]][1], b.pts_all[seq_n[2]][0])
        # indexes 6 and 7 on this side of the ridge and 8/9 on other side
        factor_left = away_from_edge / distance_across_left
        factor_right = away_from_edge / distance_across_right
        point_6 = coord.calc_point_on_line_local(b.pts_all[seq_n[0]][0], b.pts_all[seq_n[0]][1],
                                                 b.pts_all[seq_n[3]][0], b.pts_all[seq_n[3]][1],
                                                 factor_left)
        point_7 = coord.calc_point_on_line_local(b.pts_all[seq_n[1]][0], b.pts_all[seq_n[1]][1],
                                                 b.pts_all[seq_n[2]][0], b.pts_all[seq_n[2]][1],
                                                 factor_right)
        point_8 = coord.calc_point_on_line_local(b.pts_all[seq_n[1]][0], b.pts_all[seq_n[1]][1],
                                                 b.pts_all[seq_n[2]][0], b.pts_all[seq_n[2]][1],
                                                 1 - factor_right)
        point_9 = coord.calc_point_on_line_local(b.pts_all[seq_n[0]][0], b.pts_all[seq_n[0]][1],
                                                 b.pts_all[seq_n[3]][0], b.pts_all[seq_n[3]][1],
                                                 1 - factor_left)
        ratio_upper = 1 - GAMBREL_HEIGHT_RATIO_LOWER_PART
        ac_object.node(-point_6[1], b.top_of_roof_above_sea_level - ratio_upper * roof_height, -point_6[0])
        ac_object.node(-point_7[1], b.top_of_roof_above_sea_level - ratio_upper * roof_height, -point_7[0])
        ac_object.node(-point_8[1], b.top_of_roof_above_sea_level - ratio_upper * roof_height, -point_8[0])
        ac_object.node(-point_9[1], b.top_of_roof_above_sea_level - ratio_upper * roof_height, -point_9[0])

        # roofs
        lower_hypo = GAMBREL_HEIGHT_RATIO_LOWER_PART * roof_height / sin(radians(GAMBREL_ANGLE_LOWER_PART))
        top_hypo_left = ((distance_across_left / 2 - away_from_edge)**2 +
                         ((1 - GAMBREL_HEIGHT_RATIO_LOWER_PART) * roof_height)**2)**0.5
        top_hypo_right = ((distance_across_right / 2 - away_from_edge)**2 +
                          ((1 - GAMBREL_HEIGHT_RATIO_LOWER_PART) * roof_height)**2)**0.5

        # lower faces front and back
        repeat_y = lower_hypo/roof_texture_size_y
        ac_object.face([(object_node_index + 0, t.x(0), t.y(0)),
                        (object_node_index + 1, t.x(repeat_x_front), t.y(0)),
                        (object_node_index + 7, t.x(repeat_x_front), t.y(repeat_y)),
                        (object_node_index + 6, t.x(0), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)
        ac_object.face([(object_node_index + 2, t.x(0), t.y(0)),
                        (object_node_index + 3, t.x(repeat_x_back), t.y(0)),
                        (object_node_index + 9, t.x(repeat_x_back), t.y(repeat_y)),
                        (object_node_index + 8, t.x(0), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)
        # upper faces front and back
        repeat_y = top_hypo_left/roof_texture_size_y
        ac_object.face([(object_node_index + 6, t.x(0), t.y(0)),
                        (object_node_index + 7, t.x(repeat_x_front), t.y(0)),
                        (object_node_index + 5, t.x(repeat_x_front), t.y(repeat_y)),
                        (object_node_index + 4, t.x(0), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)
        repeat_y = top_hypo_right/roof_texture_size_y
        ac_object.face([(object_node_index + 8, t.x(0), t.y(0)),
                        (object_node_index + 9, t.x(repeat_x_back), t.y(0)),
                        (object_node_index + 4, t.x(repeat_x_back), t.y(repeat_y)),
                        (object_node_index + 5, t.x(0), t.y(repeat_y))],
                       mat_idx=roof_mat_idx)

        # side left
        repeat_y = roof_height / roof_texture_size_y
        repeat_x_base = b.edge_length_pts[seq_n[3]] / roof_texture_size_x
        middle_factor = away_from_edge / b.edge_length_pts[seq_n[3]]
        ac_object.face([(object_node_index + 3, t.x(0), t.y(0)),
                        (object_node_index + 0, t.x(repeat_x_base), t.y(0)),
                        (object_node_index + 6, t.x((1 - middle_factor) * repeat_x_base),
                         t.y(GAMBREL_HEIGHT_RATIO_LOWER_PART * repeat_y)),
                        (object_node_index + 4, t.x(0.5 * repeat_x_base), t.y(repeat_y)),
                        (object_node_index + 9, t.x(middle_factor * repeat_x_base),
                         t.y(GAMBREL_HEIGHT_RATIO_LOWER_PART * repeat_y))],
                       mat_idx=roof_mat_idx)
        # side right
        repeat_x_base = b.edge_length_pts[seq_n[1]] / roof_texture_size_x
        middle_factor = away_from_edge / b.edge_length_pts[seq_n[1]]
        ac_object.face([(object_node_index + 1, t.x(0), t.y(0)),
                        (object_node_index + 2, t.x(repeat_x_base), t.y(0)),
                        (object_node_index + 8, t.x((1 - middle_factor) * repeat_x_base),
                         t.y(GAMBREL_HEIGHT_RATIO_LOWER_PART * repeat_y)),
                        (object_node_index + 5, t.x(0.5 * repeat_x_base), t.y(repeat_y)),
                        (object_node_index + 7, t.x(middle_factor * repeat_x_base),
                         t.y(GAMBREL_HEIGHT_RATIO_LOWER_PART * repeat_y))],
                       mat_idx=roof_mat_idx)


def separate_pyramidal(ac_object: ac.Object, b, roof_mat_idx: int) -> None:
    """Pyramidal, dome or onion roof."""
    shape = b.roof_shape
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


def _face_uv_flat_roof(nodes: List[int], pts_all, texture: Texture):
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


# ================ UNITTESTS =======================


class TestRoofs(unittest.TestCase):
    def test_roof_looks_square(self):
        long_side = 1
        short_side = 1
        self.assertTrue(roof_looks_square(2*long_side + 2*short_side, long_side*short_side), "square")
        long_side = 1.5
        short_side = 1
        self.assertTrue(roof_looks_square(2*long_side + 2*short_side, long_side*short_side), "almost square")
        long_side = 2
        short_side = 1
        self.assertFalse(roof_looks_square(2*long_side + 2*short_side, long_side*short_side), "1:2 ratio")
        long_side = 2.1
        short_side = 1
        self.assertFalse(roof_looks_square(2*long_side + 2*short_side, long_side*short_side), "ratio larger than 1:2")
