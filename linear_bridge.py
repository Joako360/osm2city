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
        self.prep_height(nodes_dict)

    def elev(self, l, normalized=True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized:
            l /= self.center.length
        return self.elev_spline(l)

    def prep_height(self, nodes_dict):
        """Set deck shape depending on elevation."""
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
        h0, hm, h1 = self.elev([0,0.5,1])
        self.avg_slope = (h1 - h0)/self.center.length
#        print "# h0, hm, h1:", h0, hm, h1
        self.D = Deck_shape_linear(h0, h1)
        try:
            min_height = 8. * int(self.tags['layer'])
        except KeyError:
            min_height = 8.
        h_add = max(0, min_height - (self.D(0.5) - hm))
        
#        h_add = 0. # debug: no h_add at all
        if h_add > 0.:
            self.D = Deck_shape_linear(h0 + h_add, h1 + h_add)

        node0 = nodes_dict[self.refs[0]]
        node1 = nodes_dict[self.refs[-1]]
        
        if node0.h_add != 0:
            node0.h_add = 0.5*(node0.h_add + h_add)
        else:
            node0.h_add = h_add
            
        if node1.h_add != 0:
            node1.h_add = 0.5*(node1.h_add + h_add)
        else:
            node1.h_add = h_add
#        if self.D(0.5) - hm < min_height:
#            self.D = Deck_shape_poly(h0, hm+min_height, h1)

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

        left_top_nodes =  self.write_nodes(obj, self.edge[0], z, elev_offset, offset=offset)
        right_top_nodes = self.write_nodes(obj, self.edge[1], z, elev_offset, offset=offset)

        left_bottom_edge, right_bottom_edge = self.compute_offset(3)
        left_bottom_nodes =  self.write_nodes(obj, left_bottom_edge, z-3, elev_offset, offset=offset)
        right_bottom_nodes = self.write_nodes(obj, right_bottom_edge, z-3, elev_offset, offset=offset)

        # -- top
        self.write_quads(obj, left_top_nodes, right_top_nodes, self.tex_y0, self.tex_y1, debug_ac=None)
        
        # -- right
        self.write_quads(obj, right_top_nodes, right_bottom_nodes, self.tex_y0, self.tex_y1, debug_ac=None)
        
        # -- left
        self.write_quads(obj, left_bottom_nodes, left_top_nodes, self.tex_y0, self.tex_y1, debug_ac=None)

        # -- bottom
        self.write_quads(obj, right_bottom_nodes, left_bottom_nodes, self.tex_y0, self.tex_y1, debug_ac=None)
