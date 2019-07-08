"""
Specialized LinearObject for bridges. Overrides write_to() method.

TODO: linear deck: limit slope
      stitch road to bridge
      limit transverse slope of road
      if h_add too high, continue/insert bridge
"""
import numpy as np
import scipy.interpolate

import linear
import parameters
import textures.road
from utils.utilities import FGElev
import utils.ac3d


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
    def __init__(self, transform, fg_elev: FGElev, osm_id, tags, refs, nodes_dict, width: float,
                 above_ground_level: float, tex=textures.road.EMBANKMENT_2):
        super().__init__(transform, osm_id, tags, refs, nodes_dict, width, above_ground_level, tex)
        # -- prepare elevation spline
        #    probe elev at n_probes locations
        n_probes = max(int(self.center.length / 5.), 3)
        probe_locations_nondim = np.linspace(0, 1., n_probes)
        elevs = np.zeros(n_probes)
        for i, l in enumerate(probe_locations_nondim):
            local_point = self.center.interpolate(l, normalized=True)
            elevs[i] = fg_elev.probe_elev(local_point.coords[0])  # fixme: have elev do the transform?
        self.elev_spline = scipy.interpolate.interp1d(probe_locations_nondim, elevs)
        self.prep_height(nodes_dict, fg_elev)

        # properties
        self.pillar_r0 = 0.
        self.pillar_r1 = 0.
        self.pillar_nnodes = 0
        # self.deck_shape_poly = None

    def elev(self, l, normalized: bool = True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized:
            l /= self.center.length
        return self.elev_spline(l)

    def prep_height(self, nodes_dict, fg_elev: FGElev):
        """Preliminary deck shape depending on elevation. Write required h_add to end nodes"""
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
        # - store MSL
        # - store elev
        # loop:
        #   lowering MSL towards elev, respect max slope
        #   if terrain is sloping, keep MSL, such that terrain approaches MSL
        # eventually write MSL
        #
        node0 = nodes_dict[self.refs[0]]
        node1 = nodes_dict[self.refs[-1]]

        MSL_mid = self.elev([0.5])  # FIXME: use elev interpolator instead?
        
        MSL = np.array([fg_elev.probe_elev(the_node) for the_node in self.center.coords])

        deck_MSL = MSL.copy()
        deck_MSL[0] += node0.h_add
        deck_MSL[-1] += node1.h_add
        
        if deck_MSL[-1] > deck_MSL[0]:
            hi_end = -1
            lo_end = 0
        else:
            hi_end = 0
            lo_end = -1
        self.deck_shape_poly = DeckShapeLinear(deck_MSL[0], deck_MSL[-1])
        try:
            required_height = parameters.BRIDGE_LAYER_HEIGHT * int(self.tags['layer'])
        except KeyError:
            required_height = parameters.BRIDGE_LAYER_HEIGHT
            
        if (self.deck_shape_poly(0.5) - MSL_mid) > required_height:
            return

        import roads  # late import due to circular dependency
        dh_dx = roads.max_slope_for_road(self)
        
        # -- need to elevate one or both ends
        deck_MSL_mid = MSL_mid + required_height
        if deck_MSL[hi_end] > deck_MSL_mid:
            # -- elevate lower end
            deck_MSL[lo_end] = max(deck_MSL[hi_end] - 2 * (deck_MSL[hi_end] - deck_MSL_mid),
                                   deck_MSL[hi_end] - dh_dx * self.center.length)
        else:
            # -- elevate both ends to same MSL
            deck_MSL[hi_end] = deck_MSL[lo_end] = deck_MSL_mid

        h_add = np.maximum(deck_MSL - MSL, np.zeros_like(deck_MSL))
        
        left_z, right_z, h_add = self.level_out(fg_elev, h_add)
        deck_MSL = MSL + h_add
            
        self.deck_shape_poly = DeckShapeLinear(deck_MSL[0], deck_MSL[-1])

        node0.h_add = h_add[0]
        node1.h_add = h_add[-1]

    def deck_height(self, l: float, normalized: bool=True):
        """given linear distance [m], interpolate and return deck height"""
        if not normalized and self.center.length != 0:
            l /= self.center.length
        return self.deck_shape_poly(l)

    def pillar(self, obj: utils.ac3d.Object, x, y, h0, h1, angle):
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
        n_nodes = len(self.edge[0].coords)
        # -- deck height
        z = np.zeros(n_nodes)
        l = 0.
        for i in range(n_nodes):
            z[i] = self.deck_height(l, normalized=False) + self.AGL
            l += self.segment_len[i]
            
        left_top_nodes = self.write_nodes(obj, self.edge[0], z, elev_offset,
                                          offset, join=True, is_left=True)
        right_top_nodes = self.write_nodes(obj, self.edge[1], z, elev_offset,
                                           offset, join=True, is_left=False)
                                           
        left_bottom_edge, right_bottom_edge = self.compute_offset(self.width/2 * 0.85)
        left_bottom_nodes = self.write_nodes(obj, left_bottom_edge, z-parameters.BRIDGE_BODY_HEIGHT,
                                             elev_offset, offset)
        right_bottom_nodes = self.write_nodes(obj, right_bottom_edge, z-parameters.BRIDGE_BODY_HEIGHT, 
                                              elev_offset, offset)
        # -- top
        mat_idx = utils.ac3d.MAT_IDX_UNLIT
        if 'lit' in self.tags and self.tags['lit'] == 'yes':
            mat_idx = utils.ac3d.MAT_IDX_LIT
        self.write_quads(obj, left_top_nodes, right_top_nodes, self.tex[0], self.tex[1], mat_idx)
        
        # -- right
        self.write_quads(obj, right_top_nodes, right_bottom_nodes, textures.road.BRIDGE_1[1], textures.road.BRIDGE_1[0],
                         utils.ac3d.MAT_IDX_UNLIT)
        
        # -- left
        self.write_quads(obj, left_bottom_nodes, left_top_nodes, textures.road.BRIDGE_1[0], textures.road.BRIDGE_1[1],
                         utils.ac3d.MAT_IDX_UNLIT)

        # -- bottom
        self.write_quads(obj, right_bottom_nodes, left_bottom_nodes, textures.road.BOTTOM[0], textures.road.BOTTOM[1],
                         utils.ac3d.MAT_IDX_UNLIT)

        # -- end wall 1
        the_node = self.edge[0].coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.edge[1].coords[0]
        e = fg_elev.probe_elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [(left_top_nodes[0],    0, parameters.EMBANKMENT_TEXTURE[0]),  # FIXME: texture coords
                (right_top_nodes[0],   0, parameters.EMBANKMENT_TEXTURE[1]),
                (right_bottom_node,    1, parameters.EMBANKMENT_TEXTURE[1]),
                (left_bottom_node,     1, parameters.EMBANKMENT_TEXTURE[0])]
        obj.face(face)

        # -- end wall 2
        the_node = self.edge[0].coords[-1]
        e = fg_elev.probe_elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.edge[1].coords[-1]
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
            self.pillar(obj, point[0]-offset.x, point[1]-offset.y, z0, z[i], self.angle[i])
