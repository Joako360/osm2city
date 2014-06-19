#!/usr/bin/env python
"""
Specialized LinearObject for bridges. Overrides write_to() method.
"""

import linear
import numpy as np
import scipy.interpolate
from pdb import pm

class Deck_shape_linear(object):
    def __init__(self, h0, h1):
        self.h0 = h0
        self.h1 = h1

    def __call__(self, s):
        #assert(s <= 1. and s >= 0.)
        return (1-s) * self.h0 + s * self.h1

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
        probe_locations = np.linspace(0, 1., n_probes)
        elevs = np.zeros(n_probes)
        probe_coords = np.zeros((n_probes, 2))
        for i, l in enumerate(probe_locations):
            local = self.center.interpolate(l, normalized=True)
            probe_coords[i] = transform.toGlobal(local.coords[0])
            elevs[i] = elev(probe_coords[i])
#        print "probing at", probe_coords
#        self.elevs = probe(probe_coords)
#        print n_probes
#        print ">>>    ", probe_locations
#        print ">>> got", elevs

        self.elev_spline = scipy.interpolate.interp1d(probe_locations, elevs)
        self.prep_height()

    def elev(self, l, normalized=True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized: l /= self.center.length
        return self.elev_spline(l)

    def prep_height(self):
        """Set deck shape depending on elevation."""
        h0 = self.elev(0.)
        hm = self.elev(0.5)
        h1 = self.elev(1.)
#        print "# h0, hm, h1:", h0, hm, h1
        self.D = Deck_shape_linear(h0, h1)
        min_height = 6.
        if self.D(0.5) - hm < min_height:
#            print "# poly", h0, hm+min_height, h1
            self.D = Deck_shape_poly(h0, hm+min_height, h1)

    def deck_height(self, l, normalized=True):
        """given linear distance [m], interpolate and return deck height"""
        if not normalized:
            l /= self.center.length
        #return -0.5*(math.cos(4*math.pi*x)-1.)*10
        #return -5.*((2.*x-1)**2-1.)
        #return 10.
        return self.D(l)

    def write_to(self, obj, elev, ac=None):
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
        z = np.zeros(n_nodes)

        # deck height
#        _z = np.zeros(n_nodes)
#        l = 0.
#        for i in range(n_nodes):
#            l += self.segment_len[i]
#            _z[i] = self.deck_height(l, normalized=False)


        # top
        node0_l, node0_r = self._write_to(obj, elev, self.left, self.right,
                                          self.tex_y0, self.tex_y1, left_z=z, right_z=z, ac=ac)
        left2, right2 = self.compute_offset(3)
        #left2, right2 = self.left, self.right

        # right
        tmp, node0_r2 = self._write_to(obj, elev, node0_r, right2,
                                       1, 0.75, left_z=z-5, right_z=z-5, ac=ac)
        # left
        node0_l2, tmp = self._write_to(obj, elev, left2, node0_l,
                                       0.75, 1, left_z=z-5, right_z=z-5, ac=ac)
        # bottom
        self._write_to(obj, elev, node0_r2, node0_l2, 0.9, 1, ac=ac, n_nodes=n_nodes)

