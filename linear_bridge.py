#!/usr/bin/env python
"""
Specialized LinearObject for bridges. Overrides write_to() method.

TODO: linear deck: limit slope
      stitch road to bridge
      limit transverse slope of road
      if h_add too high, continue/insert bridge
"""

import linear
import numpy as np
import scipy.interpolate
from pdb import pm
from vec2d import vec2d
import matplotlib.pyplot as plt
#from turtle import Vec2D

class Deck_shape_linear(object):
    def __init__(self, h0, h1):
        self.h0 = h0
        self.h1 = h1

    def _compute(self, x):
        return (1-x) * self.h0 + x * self.h1

    def __call__(self, s):
        #assert(s <= 1. and s >= 0.)
        try:
            return [self._compute(x) for x in s]
        except TypeError:
            return self._compute(s) 
#        return (1-s) * self.h0 + s * self.h1

class Deck_shape_poly(object):
    def __init__(self, h0, hm, h1):
        self.h0 = h0
        self.hm = hm
        self.h1 = h1
        self.a0 = h0
        self.a2 = 2*(h1 - 2*hm + h0)
        self.a1 = h1 - h0 - self.a2

    def __call__(self, s):
        #print "call", s
        #assert(s <= 1. and s >= 0.)
        return self.a0 + self.a1*s + self.a2*s*s

class LinearBridge(linear.LinearObject):
    def __init__(self, transform, elev, osm_id, tags, refs, nodes_dict, width=9, tex_y0=0.5, tex_y1=0.75, AGL=0.5):
        super(LinearBridge, self).__init__(transform, osm_id, tags, refs, nodes_dict, width, tex_y0, tex_y1, AGL)
        # -- prepare elevation spline
        #    probe elev at n_probes locations
        n_probes = max(int(self.center.length / 5.), 3)
        probe_locations_nondim = np.linspace(0, 1., n_probes)
        elevs = np.zeros(n_probes)
        for i, l in enumerate(probe_locations_nondim):
            local_point = self.center.interpolate(l, normalized=True)
            elevs[i] = elev(local_point.coords[0]) # fixme: have elev do the transform?
#        print "probing at", probe_coords
#        self.elevs = probe(probe_coords)
#        print n_probes
#        print ">>>    ", probe_locations_nondim
#        print ">>> got", elevs
        self.elev_spline = scipy.interpolate.interp1d(probe_locations_nondim, elevs)
        self.prep_height(nodes_dict, elev)

    def elev(self, l, normalized=True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized:
            l /= self.center.length
        return self.elev_spline(l)

    def prep_height(self, nodes_dict, elev):
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

        #MSL = np.zeros_like(self.normals)
        #MSL = self.elev([0, 0.5, 1]) # FIXME: use elev interpolator instead
        MSL_mid = self.elev([0.5]) # FIXME: use elev interpolator instead?
        
        MSL = np.array([elev(the_node) for the_node in self.center.coords])

        deck_MSL = MSL.copy()
        deck_MSL[0] += node0.h_add
        deck_MSL[-1] += node1.h_add
        
        if deck_MSL[-1] > deck_MSL[0]:
            hi_end = -1
            lo_end = 0
        else:
            hi_end = 0
            lo_end = -1
        #mid = 1
        #self.avg_slope = (MSL[hi_end] - MSL[lo_end])/self.center.length
#        print "# MSL_0, MSL_m, MSL_1:", MSL_0, MSL_m, MSL_1
        self.D = Deck_shape_linear(deck_MSL[0], deck_MSL[-1])
        try:
            required_height = 5. * int(self.tags['layer'])
        except KeyError:
            required_height = 5.
            
        if (self.D(0.5) - MSL_mid) > required_height:
            return
        
        dh_dx = linear.max_slope_for_road(self)
        
        # -- need to elevate one or both ends
        deck_MSL_mid = MSL_mid + required_height
        if deck_MSL[hi_end] > deck_MSL_mid:
            # -- elevate lower end
#            print "elevating lower end"
            deck_MSL[lo_end] = max(deck_MSL[hi_end] - 2 * (deck_MSL[hi_end] - deck_MSL_mid), 
                                   deck_MSL[hi_end] - dh_dx * self.center.length)
        else:
#            print "elevating both"
            # -- elevate both ends to same MSL
            deck_MSL[hi_end] = deck_MSL[lo_end] = deck_MSL_mid

        h_add = np.maximum(deck_MSL - MSL, np.zeros_like(deck_MSL))
        
        left_z, right_z, h_add = self.level_out(elev, h_add)
        deck_MSL = MSL + h_add
            
#        h_add = 0. # debug: no h_add at all
        self.D = Deck_shape_linear(deck_MSL[0], deck_MSL[-1])
        
#        print "midh", self.D(0.5) - MSL[1], required_height

        node0.h_add = h_add[0]
        node1.h_add = h_add[-1]
#        if self.D(0.5) - MSL_m < required_height:
#            self.D = Deck_shape_poly(MSL_0, MSL_m+required_height, MSL_1)

        if self.osm_id == 126452863:
            print "hj", node0.h_add, node1.h_add

#        node0.h_add = h_add
#        node1.h_add = h_add


        if 0:
            plt.clf()
            X = np.linspace(0,1,11)
            plt.plot(X, self.D(X), 'r-o')
#            plt.plot(X, self.D(X) + h_add, 'r-o')
            plt.plot(X, self.elev(X), 'g-o')
            plt.show()

#        bla

    def deck_height(self, l, normalized=True):
        """given linear distance [m], interpolate and return deck height"""
        if not normalized:
            l /= self.center.length
        #return -0.5*(math.cos(4*math.pi*x)-1.)*10
        #return -5.*((2.*x-1)**2-1.)
        #return 10.
        return self.D(l)


    def pillar(self, obj, x, y, h0, h1, ofs, angle):
        self.pillar_r0 = 2.
        self.pillar_r1 = 1.
        self.pillar_nnodes = 8

        rx = self.pillar_r0
        ry = self.pillar_r1

        nodes_list = []
        ofs = obj.next_node_index()
        vert = ""
        R = np.array([[np.cos(-angle), -np.sin(-angle)],
                      [np.sin(-angle),  np.cos(-angle)]])
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint = False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            obj.node(-(y+node[0]), h1, -(x+node[1]))
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint = False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            obj.node(-(y+node[0]), h0, -(x+node[1]))

        for i in range(self.pillar_nnodes-1):
            face = [(ofs+i,                      0, 4/8.-0.05),
                    (ofs+i+1,                    1, 4/8.-0.05), 
                    (ofs+i+1+self.pillar_nnodes, 1, 4/8.), 
                    (ofs+i+self.pillar_nnodes,   0, 4/8.)]
            obj.face(face)
            
        i = self.pillar_nnodes - 1
        face = [(ofs+i,                    0, 4/8.-0.05),
                (ofs,                      1, 4/8.-0.05), 
                (ofs+self.pillar_nnodes,   1, 4/8.), 
                (ofs+i+self.pillar_nnodes, 0, 4/8.)]
        obj.face(face)

        nodes_list.append(face)

        return ofs + 2*self.pillar_nnodes, vert, nodes_list

    def write_to(self, obj, elev, elev_offset, ac=None, offset=None):
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
            
        left_top_nodes =  self.write_nodes(obj, self.edge[0], z, elev_offset,
                                           offset, join=True, is_left=True)
        right_top_nodes = self.write_nodes(obj, self.edge[1], z, elev_offset,
                                           offset, join=True, is_left=False)
                                           
        bridge_body_height = 1.5
        left_bottom_edge, right_bottom_edge = self.compute_offset(self.width/2 * 0.5)
        left_bottom_nodes =  self.write_nodes(obj, left_bottom_edge, z-bridge_body_height,
                                              elev_offset, offset)
        right_bottom_nodes = self.write_nodes(obj, right_bottom_edge, z-bridge_body_height, 
                                              elev_offset, offset)
        # -- top
        self.write_quads(obj, left_top_nodes, right_top_nodes, self.tex_y0, self.tex_y1, debug_ac=None)
        
        # -- right
        self.write_quads(obj, right_top_nodes, right_bottom_nodes,  4/8., 3/8., debug_ac=None)
        
        # -- left
        self.write_quads(obj, left_bottom_nodes, left_top_nodes, 3/8., 4/8., debug_ac=None)

        # -- bottom
        self.write_quads(obj, right_bottom_nodes, left_bottom_nodes,  4/8.-0.05, 4/8., debug_ac=None)

        # -- end wall 1
        the_node = self.edge[0].coords[0]
        e = elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.edge[1].coords[0]
        e = elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [ (left_top_nodes[0],    0, 4/8.), # FIXME: texture coords
                 (right_top_nodes[0],   0, 5/8.),
                 (right_bottom_node,    1, 5/8.),
                 (left_bottom_node,     1, 4/8.) ]
        obj.face(face)

        # -- end wall 2
        the_node = self.edge[0].coords[-1]
        e = elev(the_node) - elev_offset
        left_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        the_node = self.edge[1].coords[-1]
        e = elev(the_node) - elev_offset
        right_bottom_node = obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))

        face = [ (left_top_nodes[-1],    0, 4/8.),
                 (right_top_nodes[-1],   0, 5/8.),
                 (right_bottom_node,    1, 5/8.),
                 (left_bottom_node,     1, 4/8.) ]
        obj.face(face[::-1])
        
        # pillars
        #if len(self.refs) > 2:
        z -= elev_offset
        for i in range(1, n_nodes-1):
            z0 = elev(self.center.coords[i]) - elev_offset - 1.
            point = self.center.coords[i]
            self.pillar(obj, point[0]-offset.x, point[1]-offset.y, z0, z[i], 0, self.angle[i])

