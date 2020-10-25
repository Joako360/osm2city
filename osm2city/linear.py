# -*- coding: utf-8 -*-
import copy
import logging
import math
from typing import List, Dict, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import scipy.interpolate
import shapely.geometry as shg

from osm2city import roads, parameters
from osm2city.textures import road
from osm2city.utils import ac3d
from osm2city.utils import coordinates as co
from osm2city.utils import osmparser as op
from osm2city.types import osmstrings as s
from osm2city.utils.utilities import FGElev
from osm2city.utils.vec2d import Vec2d


class LinearObject(object):
    """
    generic linear feature, base class for road, railroad, bridge etc.
    - source is a center line (OSM way)
    - parallel_offset (left, right)
    - texture

    - 2d:   roads, railroads. Draped onto terrain.
    - 2.5d: platforms. Height, but no bottom surface.
            roads with (one/two-sided) embankment.
            set angle of embankment
    - 3d:   bridges. Surfaces all around.

    possible cases:
    1. roads: left/right LS given. No v_add. Small gradient.
      -> probe z, paint on surface
    1a. roads, side. left Nodes given, right LS given. Probe right_z.
    2. embankment: center and left/right given, v_add.
      -> probe z, add v_add
    3. bridge:

    """

    def __init__(self, transform: co.Transformation, way: op.Way, nodes_dict:  Dict[int, op.Node],
                 lit_areas: List[shg.Polygon],
                 width: float, tex_coords: Tuple[float, float] = road.EMBANKMENT_1):
        self.width = width
        self.way = way
        self.nodes_dict = nodes_dict
        self.written_to_ac = False

        self.vectors = None  # numpy array defined in compute_angle_etc()
        self.normals = None  # numpy array defined in compute_angle_etc()
        self.angle = None  # numpy array defined in compute_angle_etc()
        self.segment_len = None  # numpy array defined in compute_angle_etc()
        self.dist = None  # numpy array defined in compute_angle_etc()

        osm_nodes = [nodes_dict[r] for r in way.refs]
        nodes = np.array([transform.to_local((n.lon, n.lat)) for n in osm_nodes])
        self.center = shg.LineString(nodes)
        self.lighting = list()  # same number of elements as self.center
        self._prepare_lighting(nodes, lit_areas)
        try:
            self._compute_angle_etc()
            self.left, self.right = self._compute_sides(self.width / 2.)  # LineStrings
        except Warning as reason:
            logging.warning("Warning in OSM_ID %i: %s", self.way.osm_id, reason)
        self.tex = tex_coords  # determines which part of texture we use

        # set in roads.py
        self.cluster_ref = None  # Cluster
        self.junction0 = None  # utils.graph.Junction
        self.junction1 = None  # utils.graph.Junction

    def _prepare_lighting(self, nodes, lit_areas: List[shg.Polygon]) -> None:
        """Checks each node of the way whether it is in a lit area and creates a bool in a list"""
        if s.K_LIT in self.way.tags and self.way.tags[s.K_LIT] == s.V_YES:
            for _ in nodes:
                self.lighting.append(True)
        for node in nodes:
            point = shg.Point(node)
            is_lit = False
            for area in lit_areas:
                if area.contains(point):
                    is_lit = True
                    break
            self.lighting.append(is_lit)

    def _compute_sides(self, offset: float) -> Tuple[shg.LineString, shg.LineString]:
        """Given an offset (ca. half of width) calculate left and right sides including taking care of angles."""
        offset += 1.
        n = len(self.center.coords)
        left = np.zeros((n, 2))
        right = np.zeros((n, 2))
        our_node = np.array(self.center.coords[0])
        left[0] = our_node + self.normals[0] * offset
        right[0] = our_node - self.normals[0] * offset
        for i in range(1, n - 1):
            mean_normal = (self.normals[i - 1] + self.normals[i])
            length = (mean_normal[0] ** 2 + mean_normal[1] ** 2) ** 0.5
            mean_normal /= length
            angle = (np.pi + self.angle[i - 1] - self.angle[i]) / 2.
            if abs(angle) < 0.0175:  # 1 deg
                raise ValueError('AGAIN angle > 179 in OSM_ID %i with refs %s' % (self.way.osm_id, str(self.way.refs)))
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

    def plot(self, center=True, left=False, right=False, angle=True, clf=True, show=True):
        """debug"""
        c = np.array(self.center.coords)
        left_edge = np.array(self.left.coords)
        right_edge = np.array(self.right.coords)
        if clf:
            plt.clf()
        if center:
            plt.plot(c[:, 0], c[:, 1], '-o', color='k')
        if left:
            plt.plot(left_edge[:, 0], left_edge[:, 1], '-o', color='g')
        if right:
            plt.plot(right_edge[:, 0], right_edge[:, 1], '-o', color='r')

        plt.axes().set_aspect('equal')
        import random
        if center:
            for i, n in enumerate(c):
                ss = "%i" % i
                if angle:
                    ss = ss + "_%1.0f " % (self.angle[i] * 57.3)
                plt.text(n[0], n[1] + random.uniform(-1, 1), ss, color='k')
        if left:
            for i, n in enumerate(left_edge):
                plt.text(n[0] - 3, n[1], "%i" % i, color='g')
        if right:
            for i, n in enumerate(right_edge):
                plt.text(n[0] + 3, n[1], "%i" % i, color='r')
        if show:
            plt.show()
            plt.savefig('roads_%i.eps' % self.way.osm_id)

    def _compute_angle_etc(self):
        """Compute normals, angle, segment_length, accumulated distance start"""
        n = len(self.center.coords)

        self.vectors = np.zeros((n - 1, 2))
        self.normals = np.zeros((n, 2))
        self.angle = np.zeros(n)
        self.segment_len = np.zeros(n)  # segment_len[-1] = 0, so loops over range(n) wont fail
        self.dist = np.zeros(n)
        cumulated_distance = 0.
        for i in range(n - 1):
            vector = np.array(self.center.coords[i + 1]) - np.array(self.center.coords[i])
            dx, dy = vector
            self.angle[i] = math.atan2(dy, dx)
            angle = np.pi - abs(self.angle[i - 1] - self.angle[i])
            if i > 0 and abs(angle) < 0.0175:  # 1 deg
                raise ValueError('CONSTR angle > 179 in OSM_ID %i at (%i, %i) with refs %s'
                                 % (self.way.osm_id, i, i - 1, str(self.way.refs)))

            self.segment_len[i] = (dy * dy + dx * dx) ** 0.5
            if self.segment_len[i] == 0:
                logging.error("osm id: %i contains a segment with zero len", self.way.osm_id)
                self.normals[i] = np.array((-dy, dx)) / 0.00000001
            else:
                self.normals[i] = np.array((-dy, dx)) / self.segment_len[i]
            cumulated_distance += self.segment_len[i]
            self.dist[i + 1] = cumulated_distance
            self.vectors[i] = vector

        self.normals[-1] = self.normals[-2]
        self.angle[-1] = self.angle[-2]

    def _write_nodes(self, obj: ac3d.Object, line_string: shg.LineString, z, cluster_elev: float,
                     offset: Optional[Vec2d] = None, join: bool = False, is_left: bool = False) -> List[int]:
        """given a LineString and z, write nodes to .ac.
           Return nodes_list
        """
        to_write = copy.copy(line_string.coords)
        nodes_list = []
        assert (self.cluster_ref is not None)
        if not join:
            nodes_list += list(obj.next_node_index() + np.arange(len(to_write)))
        else:
            if len(self.junction0) == 2:
                try:
                    # if other node already exists, do not write a new one
                    other_node = self.junction0.get_other_node(self, is_left,
                                                               self.cluster_ref)  # other nodes already written:
                    to_write = to_write[1:]
                    z = z[1:]
                    nodes_list.append(other_node)
                except KeyError:
                    self.junction0.set_other_node(self, is_left, obj.next_node_index(), self.cluster_ref)

            # -- make list with all but last node -- we might add last node later
            nodes_list += list(obj.next_node_index() + np.arange(len(to_write) - 1))
            last_node = obj.next_node_index() + len(to_write) - 1

            if len(self.junction1) == 2:
                try:
                    # if other node already exists, do not write a new one
                    other_node = self.junction1.get_other_node(self, is_left,
                                                               self.cluster_ref)  # other nodes already written:
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

    def _write_quads(self, obj: ac3d.Object, left_nodes_list, right_nodes_list, tex_y0, tex_y1,
                     check_lit: bool = False) -> None:
        """Write a series of quads bound by left and right.
        Left/right are lists of node indices which will be used to form a series of quads.
        Material index tells whether it is lit or not.
        """
        n_nodes = len(left_nodes_list)
        assert (len(left_nodes_list) == len(right_nodes_list))
        for i in range(n_nodes - 1):
            mat_idx = ac3d.MAT_IDX_UNLIT
            if check_lit:
                if self.lighting[i] or self.lighting[i + 1]:
                    mat_idx = ac3d.MAT_IDX_LIT
            xl = self.dist[i] / road.LENGTH
            xr = self.dist[i + 1] / road.LENGTH
            face = [(left_nodes_list[i], xl, tex_y0),
                    (left_nodes_list[i + 1], xr, tex_y0),
                    (right_nodes_list[i + 1], xr, tex_y1),
                    (right_nodes_list[i], xl, tex_y1)]
            obj.face(face[::-1], mat_idx=mat_idx)

    def _probe_ground(self, fg_elev: FGElev, line_string) -> np.ndarray:
        """Probe ground elevation along given line string, return array"""
        z_array = np.array([fg_elev.probe_elev(the_node) for the_node in line_string.coords])
        for i in range(0, len(self.way.refs)):
            node = self.nodes_dict[self.way.refs[i]]
            layer = node.layer_for_way(self.way)
            if layer > 0:
                z_array[i] += layer * parameters.DISTANCE_BETWEEN_LAYERS
            z_array[i] += parameters.MIN_ABOVE_GROUND_LEVEL
        return z_array

    def _get_v_add(self, fg_elev: FGElev):
        """Got v_add data for first and last node. Now lift intermediate nodes.
        So far, v_add is for center line only.
        """
        first_node = self.nodes_dict[self.way.refs[0]]
        last_node = self.nodes_dict[self.way.refs[-1]]

        center_z = self._probe_ground(fg_elev, self.center)

        epsilon = 0.001

        assert (len(self.left.coords) == len(self.right.coords))
        n_nodes = len(self.left.coords)

        v_add_0 = first_node.v_add
        v_add_1 = last_node.v_add
        dh_dx = roads.max_slope_for_road(self)
        msl_0 = center_z[0] + v_add_0
        msl_1 = center_z[-1] + v_add_1

        if v_add_0 <= epsilon and v_add_1 <= epsilon:
            v_add = np.zeros(n_nodes)
        elif v_add_0 <= epsilon:
            v_add = np.array([max(0, msl_1 - (self.dist[-1] - self.dist[i]) * dh_dx - center_z[i])
                              for i in range(n_nodes)])
        elif v_add_1 <= epsilon:
            v_add = np.array([max(0, msl_0 - self.dist[i] * dh_dx - center_z[i]) for i in range(n_nodes)])
        else:
            v_add = np.zeros(n_nodes)
            for i in range(n_nodes):
                v_add[i] = max(0, msl_0 - self.dist[i] * dh_dx - center_z[i])
                if v_add[i] < epsilon:
                    break

            for i in range(n_nodes)[::-1]:
                other_v_add = v_add[i]
                v_add[i] = max(0, msl_1 - (self.dist[-1] - self.dist[i]) * dh_dx - center_z[i])
                if other_v_add > v_add[i]:
                    v_add[i] = other_v_add
                    break

        return v_add, center_z

    def _level_out(self, fg_elev: FGElev, v_add):
        """given v_add, adjust left_z and right_z to stay below MAX_TRANSVERSE_GRADIENT"""
        left_z = self._probe_ground(fg_elev, self.left)
        right_z = self._probe_ground(fg_elev, self.right)

        diff_elev = left_z - right_z
        for i, the_diff in enumerate(diff_elev):
            # -- v_add larger than terrain gradient:
            #    terrain gradient doesnt matter, just create level road at v_add
            if v_add[i] > abs(the_diff / 2.):
                left_z[i] += (v_add[i] - the_diff / 2.)
                right_z[i] += (v_add[i] + the_diff / 2.)
            else:
                # v_add smaller than terrain gradient.
                # In case terrain gradient is significant, create levelled
                # road which is then higher than v_add anyway.
                # Otherwise, create sloped road and ignore v_add.
                if the_diff / self.width > parameters.MAX_TRANSVERSE_GRADIENT:  # left > right
                    right_z[i] += the_diff  # dirty
                    v_add[i] += the_diff / 2.
                elif -the_diff / self.width > parameters.MAX_TRANSVERSE_GRADIENT:  # right > left
                    left_z[i] += - the_diff  # dirty
                    v_add[i] -= the_diff / 2.  # the_diff is negative
                else:
                    # terrain gradient negligible and v_add small
                    pass
        return left_z, right_z, v_add

    def debug_print_node_info(self, the_node, v_add=None):
        if the_node in self.way.refs:
            i = self.way.refs.index(the_node)
            logging.debug(">> OSMID %i %i v_add %5.2g", self.way.osm_id, i, self.nodes_dict[the_node].v_add)
            if v_add is not None:
                logging.debug(v_add)
            else:
                pass
            return True
        return False

    def debug_label_nodes(self, line_string, z, ac, elev_offset, offset, v_add):
        for i, anchor in enumerate(line_string.coords):
            e = z[i] - elev_offset
            ac.add_label('<' + str(self.way.osm_id) + '> add %5.2f' % v_add[i], -(anchor[1] - offset.y),
                         e + 0.5, -(anchor[0] - offset.x), scale=1)

    def write_to(self, obj: ac3d.Object, fg_elev: FGElev, elev_offset, offset=None) -> bool:
        """
           assume we are a street: flat (or elevated) on terrain, left and right edges
           #need adjacency info
           #left: node index of left
           #right:
           offset accounts for tile center
        """
        v_add, center_z = self._get_v_add(fg_elev)
        left_z, right_z, v_add = self._level_out(fg_elev, v_add)

        left_nodes_list = self._write_nodes(obj, self.left, left_z, elev_offset,
                                            offset, join=True, is_left=True)
        right_nodes_list = self._write_nodes(obj, self.right, right_z, elev_offset,
                                             offset, join=True, is_left=False)

        self._write_quads(obj, left_nodes_list, right_nodes_list, self.tex[0], self.tex[1], True)
        if v_add is not None:
            # -- side walls of embankment
            if v_add.max() > parameters.MIN_EMBANKMENT_HEIGHT:
                left_ground_z = self._probe_ground(fg_elev, self.left)
                right_ground_z = self._probe_ground(fg_elev, self.right)

                left_ground_nodes = self._write_nodes(obj, self.left, left_ground_z, elev_offset, offset=offset)
                right_ground_nodes = self._write_nodes(obj, self.right, right_ground_z, elev_offset, offset=offset)
                self._write_quads(obj, left_ground_nodes, left_nodes_list, parameters.EMBANKMENT_TEXTURE[0],
                                  parameters.EMBANKMENT_TEXTURE[1])
                self._write_quads(obj, right_nodes_list, right_ground_nodes, parameters.EMBANKMENT_TEXTURE[0],
                                  parameters.EMBANKMENT_TEXTURE[1])

        return True


class DeckShapeLinear(object):
    def __init__(self, h0: float, h1: float) -> None:
        self.h0 = h0  # height of start node (msl)
        self.h1 = h1  # height of end node (msl)

    def _compute(self, x: float) -> float:
        return (1-x) * self.h0 + x * self.h1

    def __call__(self, ratio):
        try:
            return [self._compute(x) for x in ratio]
        except TypeError:
            return self._compute(ratio)


class LinearBridge(LinearObject):
    def __init__(self, transform: co.Transformation, fg_elev: FGElev, way: op.Way, nodes_dict: Dict[int, op.Node],
                 lit_areas: List[shg.Polygon],
                 width: float, tex_coords: Tuple[float, float] = road.EMBANKMENT_2):
        super().__init__(transform, way, nodes_dict, lit_areas, width, tex_coords)
        # -- prepare elevation spline
        #    probe elev at n_probes locations
        n_probes = max(int(self.center.length / 5.), 3)
        probe_locations_nondim = np.linspace(0, 1., n_probes)
        elevs = np.zeros(n_probes)
        for i, l in enumerate(probe_locations_nondim):
            local_point = self.center.interpolate(l, normalized=True)
            elevs[i] = fg_elev.probe_elev(local_point.coords[0])
        self.elev_spline = scipy.interpolate.interp1d(probe_locations_nondim, elevs)
        self._prep_height(nodes_dict, fg_elev)

        # properties
        self.pillar_r0 = 0.
        self.pillar_r1 = 0.
        self.pillar_nnodes = 0

    def _elev(self, linear_dist, normalized: bool = True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized:
            linear_dist /= self.center.length
        return self.elev_spline(linear_dist)

    def _prep_height(self, nodes_dict, fg_elev: FGElev):
        """Preliminary deck shape depending on elevation. Write required v_add to end nodes"""
        # deck slope more or less continuous!
        # d2z/dx2 limit
        # - put some constraints: min clearance
        # - adjust z to meet constraints
        # - minimize cost function?
        #   -
        # assume linear
        # test if clearance at mid-span is sufficient
        # if not
        #   if embankment:
        #     raise end-node
        #   else:
        #     try deck-shape poly
        #     deck slope OK?
        #     if not: raise end-node
        #
        # at node:
        # - store msl
        # - store elev
        # loop:
        #   lowering msl towards elev, respect max slope
        #   if terrain is sloping, keep msl, such that terrain approaches msl
        # eventually write msl
        #
        node0 = nodes_dict[self.way.refs[0]]
        node1 = nodes_dict[self.way.refs[-1]]

        msl_mid = self._elev([0.5])

        msl = np.array([fg_elev.probe_elev(the_node) for the_node in self.center.coords])

        deck_msl = msl.copy()
        deck_msl[0] += node0.v_add
        deck_msl[-1] += node1.v_add

        if deck_msl[-1] > deck_msl[0]:
            hi_end = -1
            lo_end = 0
        else:
            hi_end = 0
            lo_end = -1
        self.deck_shape_linear = DeckShapeLinear(deck_msl[0], deck_msl[-1])
        try:
            required_height = parameters.BRIDGE_LAYER_HEIGHT * int(self.way.tags[s.K_LAYER])
        except KeyError:
            required_height = parameters.BRIDGE_LAYER_HEIGHT  # e.g. if bridge over water

        if (self.deck_shape_linear(0.5) - msl_mid) > required_height:
            return

        dh_dx = roads.max_slope_for_road(self)

        # -- need to elevate one or both ends
        deck_msl_mid = msl_mid + required_height
        if deck_msl[hi_end] > deck_msl_mid:
            # -- elevate lower end
            deck_msl[lo_end] = max(deck_msl[hi_end] - 2 * (deck_msl[hi_end] - deck_msl_mid),
                                   deck_msl[hi_end] - dh_dx * self.center.length)
        else:
            # -- elevate both ends to same msl
            deck_msl[hi_end] = deck_msl[lo_end] = deck_msl_mid

        v_add = np.maximum(deck_msl - msl, np.zeros_like(deck_msl))

        left_z, right_z, v_add = self._level_out(fg_elev, v_add)
        deck_msl = msl + v_add

        self.deck_shape_linear = DeckShapeLinear(deck_msl[0], deck_msl[-1])

        node0.v_add = v_add[0]
        node1.v_add = v_add[-1]

    def _deck_height(self, linear_dist: float, normalized: bool = True):
        """Given linear distance [m], interpolate and return deck height"""
        if not normalized and self.center.length != 0:
            linear_dist /= self.center.length
        return self.deck_shape_linear(linear_dist)

    def _pillar(self, obj: ac3d.Object, x, y, h0, h1, angle):
        self.pillar_r0 = 1.
        self.pillar_r1 = 0.5
        self.pillar_nnodes = 8

        rx = self.pillar_r0
        ry = self.pillar_r1

        nodes_list = []
        ofs = obj.next_node_index()
        vert = ""
        r = np.array([[np.cos(-angle), -np.sin(-angle)],
                      [np.sin(-angle),  np.cos(-angle)]])
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint=False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(r, node)
            obj.node(-(y+node[0]), h1, -(x+node[1]))
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint=False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(r, node)
            obj.node(-(y+node[0]), h0, -(x+node[1]))

        for i in range(self.pillar_nnodes-1):
            face = [(ofs + i, 0, road.BOTTOM[0]),
                    (ofs + i + 1, 1, road.BOTTOM[0]),
                    (ofs + i + 1 + self.pillar_nnodes, 1, road.BOTTOM[1]),
                    (ofs + i + self.pillar_nnodes, 0, road.BOTTOM[1])]
            obj.face(face)

        i = self.pillar_nnodes - 1
        face = [(ofs + i, 0, road.BOTTOM[0]),
                (ofs, 1, road.BOTTOM[0]),
                (ofs + self.pillar_nnodes, 1, road.BOTTOM[1]),
                (ofs + i + self.pillar_nnodes, 0, road.BOTTOM[1])]
        obj.face(face)

        nodes_list.append(face)

        return ofs + 2*self.pillar_nnodes, vert, nodes_list

    def write_to(self, obj: ac3d.Object, fg_elev: FGElev, elev_offset, offset=None) -> None:
        """
        write
        - deck
        - sides
        - bottom
        - pillars

        needs
        - pillar positions
        - deck elev
        -
        """
        n_nodes = len(self.left.coords)
        # -- deck height
        z = np.zeros(n_nodes)
        length = 0.
        for i in range(n_nodes):
            z[i] = self._deck_height(length, normalized=False)
            node = self.nodes_dict[self.way.refs[i]]
            layer = node.layer_for_way(self.way)
            if layer > 0:
                z[i] += layer * parameters.DISTANCE_BETWEEN_LAYERS
            z[i] += parameters.MIN_ABOVE_GROUND_LEVEL
            length += self.segment_len[i]

        left_top_nodes = self._write_nodes(obj, self.left, z, elev_offset,
                                           offset, join=True, is_left=True)
        right_top_nodes = self._write_nodes(obj, self.right, z, elev_offset,
                                            offset, join=True, is_left=False)

        left_bottom_edge, right_bottom_edge = self._compute_sides(self.width / 2 * 0.85)
        left_bottom_nodes = self._write_nodes(obj, left_bottom_edge, z - parameters.BRIDGE_BODY_HEIGHT,
                                              elev_offset, offset)
        right_bottom_nodes = self._write_nodes(obj, right_bottom_edge, z - parameters.BRIDGE_BODY_HEIGHT,
                                               elev_offset, offset)
        # -- top
        self._write_quads(obj, left_top_nodes, right_top_nodes, self.tex[0], self.tex[1], True)

        # -- right
        self._write_quads(obj, right_top_nodes, right_bottom_nodes, road.BRIDGE_1[1],
                          road.BRIDGE_1[0])

        # -- left
        self._write_quads(obj, left_bottom_nodes, left_top_nodes, road.BRIDGE_1[0], road.BRIDGE_1[1])

        # -- bottom
        self._write_quads(obj, right_bottom_nodes, left_bottom_nodes, road.BOTTOM[0], road.BOTTOM[1])

        # -- end wall 1
        the_node = self.left.coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.right.coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [(left_top_nodes[0], 0, parameters.EMBANKMENT_TEXTURE[0]),
                (right_top_nodes[0], 0, parameters.EMBANKMENT_TEXTURE[1]),
                (right_bottom_node, 1, parameters.EMBANKMENT_TEXTURE[1]),
                (left_bottom_node, 1, parameters.EMBANKMENT_TEXTURE[0])]
        obj.face(face)

        # -- end wall 2
        the_node = self.left.coords[-1]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.right.coords[-1]
        e = fg_elev.probe_elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [(left_top_nodes[-1], 0, parameters.EMBANKMENT_TEXTURE[0]),
                (right_top_nodes[-1], 0, parameters.EMBANKMENT_TEXTURE[1]),
                (right_bottom_node, 1, parameters.EMBANKMENT_TEXTURE[1]),
                (left_bottom_node, 1, parameters.EMBANKMENT_TEXTURE[0])]
        obj.face(face[::-1])

        # pillars
        z -= elev_offset
        for i in range(1, n_nodes-1):
            z0 = fg_elev.probe_elev(self.center.coords[i]) - elev_offset - 1.
            point = self.center.coords[i]
            self._pillar(obj, point[0] - offset.x, point[1] - offset.y, z0, z[i], self.angle[i])
