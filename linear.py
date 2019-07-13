# -*- coding: utf-8 -*-
import copy
import logging
import math
from typing import List, Dict, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import shapely.geometry as shg

import parameters
import textures.road
from utils.utilities import FGElev
from utils.vec2d import Vec2d
import utils.ac3d
import utils.osmparser as op
import utils.osmstrings as os


def _probe_ground(fg_elev: FGElev, line_string):
    """Probe ground elevation along given line string, return array"""
    return np.array([fg_elev.probe_elev(the_node) for the_node in line_string.coords])


class LinearObject(object):
    """
    generic linear feature, base class for road, railroad, bridge etc.
    - source is a center line (OSM way as LineString)
    - parallel_offset LineStrings (left, right)
    - texture

    - height? Could derive specific classes that take care of this.
    - 2d:   roads, railroads. Draped onto terrain.
    - 2.5d: platforms. Height, but no bottom surface.
            roads with (one/two-sided) embankment.
            set angle of embankment
    - 3d:   bridges. Surfaces all around.
    
    possible cases:
    1. roads: left/right LS given. No h_add. Small gradient.
      -> probe z, paint on surface
    1a. roads, side. left Nodes given, right LS given. Probe right_z.
    2. embankment: center and left/right given, h_add.
      -> probe z, add h
    3. bridge: 
     
    API: just write the damn thing!
    - work out left_z, right_z
    - write once all z is figured out
    - 
    
    
    z: - small gradient: paint on surface
       - large gradient: elevate left or right
       - left/right elev given?
       - h_add given
    write_nodes_to_ac
    compute_or_set_z

    TODO:
      - better draping. Find discontinuity in elev, insert node
      - 2.5d, 3d, embankment
      - merge junction nodes:
        - merge_junction_nodes():
          for the_junction in those with 2 ways attached:
          move left and right coords
        - write_to()
          - check if our junction already has a written way attached
          - if not, write our node and store node indices in junction
          - if yes, use stored node indices
    """
    def __init__(self, transform, osm_id: int, tags: Dict[str, str], refs: List[int], nodes_dict: Dict[int, op.Node],
                 width: float, above_ground_level: float, tex_coords: float = textures.road.EMBANKMENT_1) -> None:
        self.width = width
        self.AGL = above_ground_level  # drape distance above terrain
        self.osm_id = osm_id
        self.refs = refs
        self.tags = tags
        self.nodes_dict = nodes_dict
        osm_nodes = [nodes_dict[r] for r in refs]
        nodes = np.array([transform.to_local((n.lon, n.lat)) for n in osm_nodes])
        self.center = shg.LineString(nodes)  # center line string
        self.left = None  # LineString
        self.right = None  # LineString
        try:
            self._compute_angle_etc()
            self.left, self.right = self._compute_offset(self.width / 2.)
        except Warning as reason:
            logging.warning("Warning in OSM_ID %i: %s", self.osm_id, reason)
        self.tex_coords = tex_coords  # determines which part of texture we use

        # set later from roads.py
        self.junction0 = None
        self.junction1 = None
        self.cluster_ref = None

    def _compute_offset(self, offset: float) -> Tuple[shg.LineString, shg.LineString]:
        offset += 1.
        n = len(self.center.coords)
        left = np.zeros((n, 2))
        right = np.zeros((n, 2))
        our_node = np.array(self.center.coords[0])
        left[0] = our_node + self.normals[0] * offset
        right[0] = our_node - self.normals[0] * offset
        for i in range(1, n-1):
            mean_normal = (self.normals[i-1] + self.normals[i])
            l = (mean_normal[0]**2 + mean_normal[1]**2)**0.5
            mean_normal /= l
            angle = (np.pi + self.angle[i-1] - self.angle[i])/2.
            if abs(angle) < 0.0175:  # 1 deg
                raise ValueError('AGAIN angle > 179 in OSM_ID %i with refs %s' % (self.osm_id, str(self.refs)))
            o = abs(offset / math.sin(angle))
            our_node = np.array(self.center.coords[i])
            left[i] = our_node + mean_normal * o
            right[i] = our_node - mean_normal * o

        our_node = np.array(self.center.coords[-1])
        left[-1] = our_node + self.normals[-1] * offset
        right[-1] = our_node - self.normals[-1] * offset

        left = shg.LineString(left)
        right = shg.LineString(right)

        return left, right

    def plot(self, center=True, left=False, right=False, angle=True, clf=True, show=True) -> None:
        """debug"""
        c = np.array(self.center.coords)
        l = np.array(self.left.coords)
        r = np.array(self.right.coords)
        if clf:
            plt.clf()
        if center:
            plt.plot(c[:, 0], c[:, 1], '-o', color='k')
        if left:
            plt.plot(l[:, 0], l[:, 1], '-o', color='g')
        if right:
            plt.plot(r[:, 0], r[:, 1], '-o', color='r')

        plt.axes().set_aspect('equal')
        import random
        if center:
            for i, n in enumerate(c):
                s = "%i" % i
                if angle:
                    s = s + "_%1.0f " % (self.angle[i]*57.3)
                plt.text(n[0], n[1]+random.uniform(-1, 1), s, color='k')
        if left: 
            for i, n in enumerate(l):
                plt.text(n[0]-3, n[1], "%i" % i, color='g')
        if right:
            for i, n in enumerate(r):
                plt.text(n[0]+3, n[1], "%i" % i, color='r')
        if show:
            plt.show()
            plt.savefig('roads_%i.eps' % self.osm_id)

    def _compute_angle_etc(self) -> None:
        """Compute normals, angle, segment_length, accumulated distance start"""
        n = len(self.center.coords)

        self.vectors = np.zeros((n-1, 2))
        self.normals = np.zeros((n, 2))
        self.angle = np.zeros(n)
        self.segment_len = np.zeros(n)  # segment_len[-1] = 0, so loops over range(n) wont fail
        self.dist = np.zeros(n)
        accumulated_distance = 0.
        for i in range(n-1):
            vector = np.array(self.center.coords[i+1]) - np.array(self.center.coords[i])
            dx, dy = vector
            self.angle[i] = math.atan2(dy, dx)
            angle = np.pi - abs(self.angle[i-1] - self.angle[i])
            if i > 0 and abs(angle) < 0.0175:  # 1 deg
                raise ValueError('CONSTR angle > 179 in OSM_ID %i at (%i, %i) with refs %s' 
                                 % (self.osm_id, i, i-1, str(self.refs)))

            self.segment_len[i] = (dy*dy + dx*dx)**0.5
            if self.segment_len[i] == 0:
                logging.error("osm id: %i contains a segment with zero len", self.osm_id)
                self.normals[i] = np.array((-dy, dx)) / 0.00000001
            else:
                self.normals[i] = np.array((-dy, dx)) / self.segment_len[i]
            accumulated_distance += self.segment_len[i]
            self.dist[i+1] = accumulated_distance
            self.vectors[i] = vector
        
        self.normals[-1] = self.normals[-2]
        self.angle[-1] = self.angle[-2]

    def _write_nodes(self, obj: utils.ac3d.Object, line_string: shg.LineString, z, cluster_elev: float,
                     offset: Optional[Vec2d] = None, join: bool = False, is_left: bool = False) -> List[int]:
        """given a LineString and z, write nodes to .ac.
           Return nodes_list         
        """
        to_write = copy.copy(line_string.coords)
        nodes_list = []
        assert(self.cluster_ref is not None)
        if not join:
            nodes_list += list(obj.next_node_index() + np.arange(len(to_write)))
        else:
            if len(self.junction0) == 2:
                try:
                    # if other node already exists, do not write a new one
                    other_node = self.junction0.get_other_node(self, is_left, self.cluster_ref) #other nodes already written:
                    to_write = to_write[1:]
                    z = z[1:]
                    nodes_list.append(other_node)
                except KeyError:
                    self.junction0.set_other_node(self, is_left, obj.next_node_index(), self.cluster_ref)
    
            # -- make list with all but last node -- we might add last node later
            nodes_list += list(obj.next_node_index() + np.arange(len(to_write)-1))
            last_node = obj.next_node_index() + len(to_write)-1

            if len(self.junction1) == 2:
                try:
                    # if other node already exists, do not write a new one
                    other_node = self.junction1.get_other_node(self, is_left, self.cluster_ref) #other nodes already written:
                    to_write = to_write[:-1]
                    z = z[:-1]
                    nodes_list.append(other_node)
                except KeyError:
                    self.junction1.set_other_node(self, is_left, last_node, self.cluster_ref)
                    nodes_list.append(last_node)
            else:
                nodes_list.append(last_node)
                
        for i, the_node in enumerate(to_write):
            e = z[i] - cluster_elev
            obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))
            
        return nodes_list

    def _write_quads(self, obj: utils.ac3d.Object, left_nodes_list, right_nodes_list, tex_y0, tex_y1,
                     mat_idx: int) -> None:
        """Write a series of quads bound by left and right. 
        Left/right are lists of node indices which will be used to form a series of quads.
        Material index tells whether it is lit or not.
        """
        n_nodes = len(left_nodes_list)
        assert(len(left_nodes_list) == len(right_nodes_list))
        for i in range(n_nodes-1):
            xl = self.dist[i] / textures.road.LENGTH
            xr = self.dist[i+1] / textures.road.LENGTH
            face = [(left_nodes_list[i],    xl, tex_y0),
                    (left_nodes_list[i+1],  xr, tex_y0),
                    (right_nodes_list[i+1], xr, tex_y1),
                    (right_nodes_list[i],   xl, tex_y1)]
            obj.face(face[::-1], mat_idx=mat_idx)

    def _get_h_add(self, fg_elev: FGElev):
        """
        """
        first_node = self.nodes_dict[self.refs[0]]
        last_node = self.nodes_dict[self.refs[-1]]
                
        # -- elevated road. Got h_add data for first and last node. Now lift intermediate
        #    nodes. So far, h_add is for center line only.
        # FIXME: when do we need this? if left_z_given is None and right_z_given is None?

        center_z = np.array([fg_elev.probe_elev(the_node) for the_node in self.center.coords]) + self.AGL

        epsilon = 0.001

        assert(len(self.left.coords) == len(self.right.coords))
        n_nodes = len(self.left.coords)

        h_add_0 = first_node.h_add
        h_add_1 = last_node.h_add
        import roads  # late import due to circular dependency
        dh_dx = roads.max_slope_for_road(self)
        MSL_0 = center_z[0] + h_add_0
        MSL_1 = center_z[-1] + h_add_1

        if h_add_0 <= epsilon and h_add_1 <= epsilon:
            h_add = np.zeros(n_nodes)
        elif h_add_0 <= epsilon:
            h_add = np.array([max(0, MSL_1 - (self.dist[-1] - self.dist[i]) * dh_dx - center_z[i])
                              for i in range(n_nodes)])
        elif h_add_1 <= epsilon:
            h_add = np.array([max(0, MSL_0 - self.dist[i] * dh_dx - center_z[i]) for i in range(n_nodes)])
        else:
            h_add = np.zeros(n_nodes)
            for i in range(n_nodes):
                h_add[i] = max(0, MSL_0 - self.dist[i] * dh_dx - center_z[i])
                if h_add[i] < epsilon:  # FIXME: different for other h_add?
                    break
            
#            for i in range(n_nodes):
#                h_add[i] = max(0, h_add_0 - self.dist[i] * dh_dx - (center_z[i] - center_z[0]))
#                if h_add[i] < 0.001:
#                    break
            for i in range(n_nodes)[::-1]:
                other_h_add = h_add[i]
                h_add[i] = max(0, MSL_1 - (self.dist[-1] - self.dist[i]) * dh_dx - center_z[i])
#                h_add[i] = max(0, h_add_1 - (self.dist[-1] - self.dist[i]) * dh_dx - (center_z[i] - center_z[-1]))
                if other_h_add > h_add[i]:
                    h_add[i] = other_h_add # FIXME: this is different than for first h_add?
                    break

        return h_add, center_z

    def _level_out(self, fg_elev: FGElev, h_add):
        """given h_add, adjust left_z and right_z to stay below MAX_TRANSVERSE_GRADIENT"""
        left_z = _probe_ground(fg_elev, self.left) + self.AGL
        right_z = _probe_ground(fg_elev, self.right) + self.AGL

        diff_elev = left_z - right_z
        for i, the_diff in enumerate(diff_elev):
            # -- h_add larger than terrain gradient:
            #    terrain gradient doesnt matter, just create level road at h_add
            if h_add[i] > abs(the_diff/2.):
                left_z[i] += (h_add[i] - the_diff/2.)
                right_z[i] += (h_add[i] + the_diff/2.)
            else:
                # h_add smaller than terrain gradient. 
                # In case terrain gradient is significant, create level
                # road which is then higher than h_add anyway.
                # Otherwise, create sloped road and ignore h_add.
                # FIXME: is this a bug?
                if the_diff / self.width > parameters.MAX_TRANSVERSE_GRADIENT:  # left > right
                    right_z[i] += the_diff  # dirty
                    h_add[i] += the_diff/2.
                elif -the_diff / self.width > parameters.MAX_TRANSVERSE_GRADIENT:  # right > left
                    left_z[i] += - the_diff  # dirty
                    h_add[i] -= the_diff/2.  # the_diff is negative
                else:
                    # terrain gradient negligible and h_add small
                    pass
        return left_z, right_z, h_add

    # FIXME: this is really a road type of linearObject, so make it linearRoad
    # FIXME: what is offset?

    def debug_print_node_info(self, the_node, h_add=None):
        if the_node in self.refs:
            i = self.refs.index(the_node)
            logging.debug(">> OSMID %i %i h_add %5.2g", self.osm_id, i, self.nodes_dict[the_node].h_add)
            if h_add is not None:
                logging.debug(h_add)
            else:
                pass
            return True
        return False

    def debug_label_nodes(self, line_string, z, ac, elev_offset, offset, h_add):
        for i, anchor in enumerate(line_string.coords):
            e = z[i] - elev_offset
            ac.add_label('<' + str(self.osm_id) + '> add %5.2f' % h_add[i], -(anchor[1] - offset.y),
                         e+0.5, -(anchor[0] - offset.x), scale=1)
        
    def write_to(self, obj: utils.ac3d.Object, fg_elev: FGElev, elev_offset, offset=None) -> bool:
        """
           assume we are a street: flat (or elevated) on terrain, left and right edges
           #need adjacency info
           #left: node index of left
           #right:
           offset accounts for tile center
        """
        h_add, center_z = self._get_h_add(fg_elev)
        left_z, right_z, h_add = self._level_out(fg_elev, h_add)

        left_nodes_list = self._write_nodes(obj, self.left, left_z, elev_offset,
                                            offset, join=True, is_left=True)
        right_nodes_list = self._write_nodes(obj, self.right, right_z, elev_offset,
                                             offset, join=True, is_left=False)

        mat_idx = utils.ac3d.MAT_IDX_UNLIT
        if os.K_LIT in self.tags and self.tags[os.K_LIT] == os.V_YES:
            mat_idx = utils.ac3d.MAT_IDX_LIT

        self._write_quads(obj, left_nodes_list, right_nodes_list, self.tex_coords[0], self.tex_coords[1], mat_idx)
        if h_add is not None:
            # -- side walls of embankment
            if h_add.max() > 0.1:
                left_ground_z = _probe_ground(fg_elev, self.left)
                right_ground_z = _probe_ground(fg_elev, self.right)

                left_ground_nodes = self._write_nodes(obj, self.left, left_ground_z, elev_offset, offset=offset)
                right_ground_nodes = self._write_nodes(obj, self.right, right_ground_z, elev_offset, offset=offset)
                self._write_quads(obj, left_ground_nodes, left_nodes_list, parameters.EMBANKMENT_TEXTURE[0],
                                  parameters.EMBANKMENT_TEXTURE[1], utils.ac3d.MAT_IDX_UNLIT)
                self._write_quads(obj, right_nodes_list, right_ground_nodes, parameters.EMBANKMENT_TEXTURE[0],
                                  parameters.EMBANKMENT_TEXTURE[1], utils.ac3d.MAT_IDX_UNLIT)

        return True
