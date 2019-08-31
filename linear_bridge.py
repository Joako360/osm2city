"""
Specialized LinearObject for bridges. Overrides write_to() method.

TODO: linear deck: limit slope
      stitch road to bridge
      limit transverse slope of road
      if v_add too high, continue/insert bridge
"""
import numpy as np
import scipy.interpolate
from typing import Dict, Tuple

import linear
import parameters
import textures.road
from utils.utilities import FGElev
import utils.ac3d
import utils.osmparser as op
import utils.osmstrings as s


class DeckShapeLinear(object):
    def __init__(self, h0, h1):
        self.h0 = h0
        self.h1 = h1

    def _compute(self, x):
        return (1-x) * self.h0 + x * self.h1

    def __call__(self, s):
        try:
            return [self._compute(x) for x in s]
        except TypeError:
            return self._compute(s)


class DeckShapePoly(object):
    def __init__(self, h0, hm, h1):
        self.h0 = h0
        self.hm = hm
        self.h1 = h1
        self.a0 = h0
        self.a2 = 2*(h1 - 2*hm + h0)
        self.a1 = h1 - h0 - self.a2

    def __call__(self, s):
        return self.a0 + self.a1*s + self.a2*s*s


class LinearBridge(linear.LinearObject):
    def __init__(self, transform, fg_elev: FGElev, way: op.Way, nodes_dict: Dict[int, op.Node], width: float,
                 tex_coords: Tuple[float, float] = textures.road.EMBANKMENT_2):
        super().__init__(transform, way, nodes_dict, width, tex_coords)
        # -- prepare elevation spline
        #    probe elev at n_probes locations
        n_probes = max(int(self.center.length / 5.), 3)
        probe_locations_nondim = np.linspace(0, 1., n_probes)
        elevs = np.zeros(n_probes)
        for i, l in enumerate(probe_locations_nondim):
            local_point = self.center.interpolate(l, normalized=True)
            elevs[i] = fg_elev.probe_elev(local_point.coords[0])  # fixme: have elev do the transform?
        self.elev_spline = scipy.interpolate.interp1d(probe_locations_nondim, elevs)
        self._prep_height(nodes_dict, fg_elev)

        # properties
        self.pillar_r0 = 0.
        self.pillar_r1 = 0.
        self.pillar_nnodes = 0
        # self.deck_shape_poly = None

    def _elev(self, l, normalized: bool = True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized:
            l /= self.center.length
        return self.elev_spline(l)

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

        msl_mid = self._elev([0.5])  # FIXME: use elev interpolator instead?

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
        self.deck_shape_poly = DeckShapeLinear(deck_msl[0], deck_msl[-1])
        try:
            required_height = parameters.BRIDGE_LAYER_HEIGHT * int(self.way.tags[s.K_LAYER])
        except KeyError:
            required_height = parameters.BRIDGE_LAYER_HEIGHT

        if (self.deck_shape_poly(0.5) - msl_mid) > required_height:
            return

        import roads  # late import due to circular dependency
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

        self.deck_shape_poly = DeckShapeLinear(deck_msl[0], deck_msl[-1])

        node0.v_add = v_add[0]
        node1.v_add = v_add[-1]

    def _deck_height(self, l: float, normalized: bool = True):
        """given linear distance [m], interpolate and return deck height"""
        if not normalized and self.center.length != 0:
            l /= self.center.length
        return self.deck_shape_poly(l)

    def _pillar(self, obj: utils.ac3d.Object, x, y, h0, h1, angle):
        self.pillar_r0 = 1.
        self.pillar_r1 = 0.5
        self.pillar_nnodes = 8

        rx = self.pillar_r0
        ry = self.pillar_r1

        nodes_list = []
        ofs = obj.next_node_index()
        vert = ""
        R = np.array([[np.cos(-angle), -np.sin(-angle)],
                      [np.sin(-angle),  np.cos(-angle)]])
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint=False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            obj.node(-(y+node[0]), h1, -(x+node[1]))
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint=False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            obj.node(-(y+node[0]), h0, -(x+node[1]))

        for i in range(self.pillar_nnodes-1):
            face = [(ofs+i,                      0, textures.road.BOTTOM[0]),
                    (ofs+i+1,                    1, textures.road.BOTTOM[0]),
                    (ofs+i+1+self.pillar_nnodes, 1, textures.road.BOTTOM[1]),
                    (ofs+i+self.pillar_nnodes,   0, textures.road.BOTTOM[1])]
            obj.face(face)

        i = self.pillar_nnodes - 1
        face = [(ofs+i,                    0, textures.road.BOTTOM[0]),
                (ofs,                      1, textures.road.BOTTOM[0]),
                (ofs+self.pillar_nnodes,   1, textures.road.BOTTOM[1]),
                (ofs+i+self.pillar_nnodes, 0, textures.road.BOTTOM[1])]
        obj.face(face)

        nodes_list.append(face)

        return ofs + 2*self.pillar_nnodes, vert, nodes_list

    def write_to(self, obj: utils.ac3d.Object, fg_elev: FGElev, elev_offset, offset=None) -> None:
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
        mat_idx = utils.ac3d.MAT_IDX_UNLIT
        if s.K_LIT in self.way.tags and self.way.tags[s.K_LIT] == s.V_YES:
            mat_idx = utils.ac3d.MAT_IDX_LIT
        self._write_quads(obj, left_top_nodes, right_top_nodes, self.tex[0], self.tex[1], mat_idx)

        # -- right
        self._write_quads(obj, right_top_nodes, right_bottom_nodes, textures.road.BRIDGE_1[1], textures.road.BRIDGE_1[0],
                          utils.ac3d.MAT_IDX_UNLIT)

        # -- left
        self._write_quads(obj, left_bottom_nodes, left_top_nodes, textures.road.BRIDGE_1[0], textures.road.BRIDGE_1[1],
                          utils.ac3d.MAT_IDX_UNLIT)

        # -- bottom
        self._write_quads(obj, right_bottom_nodes, left_bottom_nodes, textures.road.BOTTOM[0], textures.road.BOTTOM[1],
                          utils.ac3d.MAT_IDX_UNLIT)

        # -- end wall 1
        the_node = self.left.coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.right.coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [(left_top_nodes[0],    0, parameters.EMBANKMENT_TEXTURE[0]),  # FIXME: texture coords
                (right_top_nodes[0],   0, parameters.EMBANKMENT_TEXTURE[1]),
                (right_bottom_node,    1, parameters.EMBANKMENT_TEXTURE[1]),
                (left_bottom_node,     1, parameters.EMBANKMENT_TEXTURE[0])]
        obj.face(face)

        # -- end wall 2
        the_node = self.left.coords[-1]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.right.coords[-1]
        e = fg_elev.probe_elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [(left_top_nodes[-1],    0, parameters.EMBANKMENT_TEXTURE[0]),
                (right_top_nodes[-1],   0, parameters.EMBANKMENT_TEXTURE[1]),
                (right_bottom_node,    1, parameters.EMBANKMENT_TEXTURE[1]),
                (left_bottom_node,     1, parameters.EMBANKMENT_TEXTURE[0])]
        obj.face(face[::-1])

        # pillars
        z -= elev_offset
        for i in range(1, n_nodes-1):
            z0 = fg_elev.probe_elev(self.center.coords[i]) - elev_offset - 1.
            point = self.center.coords[i]
            self._pillar(obj, point[0] - offset.x, point[1] - offset.y, z0, z[i], self.angle[i])
