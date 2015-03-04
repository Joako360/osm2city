#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Deprecated, Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
"""
import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
import pdb
import osm
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os
import xml.sax

import subprocess
import logging
import osmparser

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


def param_interpolate():
    t = np.arange(0,1.1,.1)
    x = np.sin(2*np.pi*t)
    y = np.cos(np.pi*t)*2.
    tck,u = interpolate.splprep([x,y],s=0)
    unew = np.arange(0,1.01,0.05)
    out = interpolate.splev(unew,tck)
    xder, yder = interpolate.splev(unew,tck,der=1)
    xd = np.zeros_like(unew)
    yd = np.zeros_like(unew)
    s=0.1
    for i in range(len(xd)):
        xd[i] = out[0][i] - s*yder[i]
        yd[i] = out[1][i] + s*xder[i]

    plt.figure()
    #plt.plot(x,y,'x',out[0],out[1],np.sin(2*np.pi*unew),np.cos(2*np.pi*unew),x,y,'b')
    plt.plot(out[0],out[1], '-x', xd, yd, '-o')
    plt.legend(['Linear', 'a'])
    #plt.axis([-1.05,1.05,-1.05,1.05])
    plt.title('Spline of parametrically-defined curve')
    plt.show()

def plot_line(center, style='-x'):
    plt.plot(center.coords.xy[0], center.coords.xy[1], style)
    #plt.legend(['Linear'])
    #plt.title('Spline of parametrically-defined curve')


class Elev_probe(object):
    def __init__(self):
        fg_scenery="/home/tom/fgfs/home/Scenery-devel"
        fg_scenery="$FG_SCENERY"

        print "popen"
        self.fgelev = subprocess.Popen('/home/tom/daten/fgfs/cvs-build/git-2013-09-22-osg-3.2/bin/fgelev --fg-root $FG_ROOT --fg-scenery '+fg_scenery,  shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def __call__(self, coords):
        #print "write"
        n = len(coords)
        for i in range(n):
            self.fgelev.stdin.write("%i %g %g\n" % (i, coords[i][0], coords[i][1]))
        self.fgelev.stdin.flush()
        #print "read"
        elevs = np.zeros(n)
        for i in range(n):
            tmp, elev = self.fgelev.stdout.readline().split()
            elevs[i] = float(elev)

        return elevs

probe = Elev_probe() # FIXME: global variable

class Bridge(object):
#    def __init__(self, osm_id, tags, refs, scale=1):
    def __init__(self, coords, transform, scale=1.):
        self.transform = transform

        self.upper_offset = 0.5*scale
        self.body_height = 0.3*scale
        self.lower_offset = 0.3*scale
        # -- round piers
        #self.pillar_r0 = 0.2*scale
        #self.pillar_r1 = 0.2*scale
        #self.pillar_nnodes = 16

        self.pillar_r0 = 0.25*scale # -- lateral
        self.pillar_r1 = 0.1*scale  # -- longitudinal
        self.pillar_nnodes = 4


        self.scale = scale

        default = False
        if default:
            t = np.arange(0,1.1,.01)
            x = np.sin(2*np.pi*t)
            y = np.cos(np.pi*t)
            coords = zip(x,y)
        else:
            x = np.zeros(len(coords))
            y = np.zeros_like(x)
            #z = np.zeros(len(coords)+10)+10
            for i, c in enumerate(coords):
                x[i] = c[0]
                y[i] = c[1]

        self.center = shg.LineString(coords)
        print "# length %1.0f m" % self.center.length
        if len(coords) < 3 or self.center.length < 20:
            print "# too short"
            self.too_short = True
            return

        self.too_short = False


        # -- prepare elevation spline
        #    probe elev at n_probes locations
        n_probes = int(self.center.length/5.)
        self.probe_locations = np.linspace(0, 1., n_probes)
        probe_coords = np.zeros((n_probes, 2))
        for i, l in enumerate(self.probe_locations):
            local = self.center.interpolate(l, normalized=True)
            probe_coords[i] = self.transform.toGlobal(local.coords[0])

        #print "probing at", probe_coords
        self.elevs = probe(probe_coords)


        #print ">>> got", self.elevs
        self.elev_spline = scipy.interpolate.interp1d(self.probe_locations, self.elevs)

        self.prep_height()
        #center = center.simplify(0.03)

    def plot_height_profile(self, png_name):
        plt.figure()
        X = self.probe_locations * self.center.length
        plt.plot(X, self.elevs)
        dh = [self.deck_height(l) for l in self.probe_locations]
        plt.plot(X, dh)
        plt.axes().set_aspect('equal')
        plt.savefig(png_name)
        plt.clf()


    def pillar(self, x, y, h0, h1, ofs, angle):
        rx = self.pillar_r0
        ry = self.pillar_r1

        nodes_list = []
        vert = ""
        R = np.array([[np.cos(-angle), -np.sin(-angle)],
                      [np.sin(-angle),  np.cos(-angle)]])
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint = False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            vert += "%1.6f %1.6f %1.6f\n" % (-(y+node[0]), h1, -(x+node[1]) )
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint = False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            vert += "%1.6f %1.6f %1.6f\n" % (-(y+node[0]), h0, -(x+node[1]))

        for i in range(self.pillar_nnodes-1):
            face = [ofs+i, ofs+i+1, ofs+i+1+self.pillar_nnodes, ofs+i+self.pillar_nnodes][::-1]
            nodes_list.append(face)
        i = self.pillar_nnodes - 1
        face = [ofs+i, ofs, ofs+self.pillar_nnodes, ofs+i+self.pillar_nnodes][::-1]
        nodes_list.append(face)

        return ofs + 2*self.pillar_nnodes, vert, nodes_list

    def _prep_height(self):
        pass
        # - probe terrain at points on center
#        insert nodes at equidistant
#        simplify

#        pillar positions
#        height() = linear_height(b0, b1)

        # - probe terrain at 0..1, 100 nodes
        # - compute bridge deck height based on
        #   - terrain
        #   - crossed railroads, roads, streams, none
        #   -

#        if center.length < 10: raise ValueError("bridge length must be > 10 m")
#        ofs = 1.
#        s_ofs0 = center.interpolate(ofs)
#        s_ofs1 = center.interpolate(center.length - ofs)
#        s_street0 = center.interpolate(0.25, normalized=True)
#        s_street1 = center.interpolate(0.75, normalized=True)

#        bofs1 = b1 - ofs
#        min_height_border = 2.5
#        for node in [bofs0, bofs1]:
#            if height(node) - elev(node) < min_height_ofs:
#                height(node) = elev(node) + min_height_ofs

#        height(r0) = elev(r0)
#        height(r1) = elev(r1)

#        min_height_street = 4.5
#        for node in [street0, street1]:
#            if height(node) - elev(node) < min_height_street:
#                height(node) = elev(node) + min_height_street
#
#        compute total pier height -> cost


#                            -----o---
#                      -o----     |
#                  --+- |         |
#               ---  |  |         |
#        ___o_--_____|__|_________|__
#           s0       0  s_ofs0   s_street0
#         dh/dr=0  h>=min_h_ofs h>=min_h_street



    def prep_height(self):
        """Set deck shape depending on elevation."""
        h0 = self.elev(0.)
        hm = self.elev(0.5)
        h1 = self.elev(1.)
        print "# h0, hm, h1:", h0, hm, h1
        self.D = Deck_shape_linear(h0, h1)
        min_height = 6.
        if self.D(0.5) - hm < min_height:
            print "# poly", h0, hm+min_height, h1
            self.D = Deck_shape_poly(h0, hm+min_height, h1)

        #print "deck height @0, m, 1:", self.deck_height(0.), self.deck_height(0.5), self.deck_height(1.)


# probe elevation
# put constraint in middle
# prepare deck
# D = linear(h0, h1)
# hm = elev(middle)
#
#    def set_deck_height(self):
#        """accepts height function?
#           sets deck height at coords
#        """
#        pass

    def deck_height(self, l, normalized=True):
        """given linear distance [m], interpolate and return deck height"""
        if not normalized: l /= self.center.length
        #return -0.5*(math.cos(4*math.pi*x)-1.)*10
        #return -5.*((2.*x-1)**2-1.)
        #return 10.
        return self.D(l)

    def elev(self, l, normalized=True):
        """given linear distance [m], interpolate and return terrain elevation"""
        if not normalized: l /= self.center.length
        return self.elev_spline(l)

#        p = self.center.interpolate(l, normalized)
#        if not normalized: l /= self.center.length
#        l -= 0.1
        #return 0.4*l
#        return 2.*((2.*l-1)**2-1.)

    def angle(self, l):
        """given linear distance [m], interpolate and return angle"""
#        x = l / self.center.length
        dl = 0.5
        if l < dl:
            l0 = 0.
            l1 = dl
        elif l >= self.center.length - dl:
            l0 = self.center.length - dl
            l1 = self.center.length
        else:
            l0 = l - dl
            l1 = l + dl
        p0 = vec2d(self.center.interpolate(l0).coords[0])
        p1 = vec2d(self.center.interpolate(l1).coords[0])
        return (p1 - p0).atan2()

    def geom(self):

        # -- FIXME: compute angle
        center = self.center
        n = len(center.coords)
        angle = np.zeros(n)
        angle[0] = (vec2d(center.coords[1]) - vec2d(center.coords[0])).atan2()
        for i in range(1, n-1):
            angle[i] = 0.5 * ( (vec2d(center.coords[i-1]) - vec2d(center.coords[i])).atan2()
                              +(vec2d(center.coords[i])   - vec2d(center.coords[i+1])).atan2())
        angle[n-1] = (vec2d(center.coords[n-2]) - vec2d(center.coords[n-1])).atan2()

        ml = 10.
        offset_ul = center.parallel_offset(self.upper_offset, 'left', resolution=16, join_style=2, mitre_limit=ml)
        offset_ur = center.parallel_offset(self.upper_offset, 'right', resolution=16, join_style=2, mitre_limit=ml)
        offset_ll = center.parallel_offset(self.lower_offset, 'left', resolution=16, join_style=2, mitre_limit=ml)
        offset_lr = center.parallel_offset(self.lower_offset, 'right', resolution=16, join_style=2, mitre_limit=ml)
        assert(len(offset_ul.coords) == n)
        assert(len(offset_ur.coords) == n)
        assert(len(offset_ll.coords) == n)
        assert(len(offset_ur.coords) == n)

        # -- offset_ul: same order as center, whereas offset_ur is reversed

        #ofs = vec2d(center.coords[0])
        #for i in range(n):
        #    print vec2d(center.coords[i]) - ofs, vec2d(offset_ur.coords[i]) - ofs
        #sys.exit(0)

        self.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(center.coords[i])) for i, coord in enumerate(center.coords[1:])])
        #segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(offset_ul.coords[i])) for i, coord in enumerate(offset_ul.coords[1:])])
        # FIXME: use average offset_ur and offset_ul or fix parallel_offset computation.
#        segment_len = np.array([vec2d(coord).distance_to(vec2d(center.coords[i])) for i, coord in enumerate(center.coords[1:])])

        if False:
            # -- plot
            plt.figure()
            plot_line(center, 'k-o')
            plot_line(offset_ul, 'b-x')
            plot_line(offset_ur, 'b-x')
            plt.axis([-1.5,1.5,-1.5,1.5])
            plt.axes().set_aspect('equal')
            #plt.show()

        out = ""
        # vertices
        out += "OBJECT poly\n"
        out += 'name "b6"\n'
        out += 'texture "tex/bridge.png"\n'
        n_ul = len(offset_ul.coords)
        n_ll = len(offset_ll.coords)
        n_ur = len(offset_ul.coords)
        n_lr = len(offset_ll.coords)

        print "# lens", n, n_ul, n_ll, n_ur, n_lr

        def succ_range(i, delta):
            return i + delta, range(i, i + delta)

        i, nodes_ul = succ_range(0, n_ul)
        i, nodes_ll = succ_range(i, n_ll)
        i, nodes_ur = succ_range(i, n_ur)
        i, nodes_lr = succ_range(i, n_lr)

        # -- how many pillars?
        i0 = n_ul + n_ll + n_ur + n_lr
        p_nodes = []
        pillar_out = ""
        if True:
            """equi-distant pillars"""
            pillar_distance = 40.
            npfeiler = int(center.length / pillar_distance)
            pillar_distance = center.length / npfeiler

            # -- pillar verts
            l = 0.
            for i in range(npfeiler):
                pillar_pos = center.interpolate(l)
                # FIXME: angle
                i0, verts, nodes = self.pillar(pillar_pos.coords[0][0],
                                               pillar_pos.coords[0][1],
                                               self.deck_height(l, normalized=False) - self.body_height,
                                               self.elev(l, normalized=False), i0, self.angle(l))
                pillar_out += verts
                p_nodes.append(nodes)
                l += pillar_distance
        else:
            ipfeiler = range(len(x))[::1]
            npfeiler = len(ipfeiler)

            # -- pillar verts
            for j, i in enumerate(ipfeiler):
                i0, verts, nodes = self.pillar(x[i], y[i],
                                               self.deck_height(l, normalized=False) - self.body_height,
                                               self.elev(l, normalized=False), i0, angle[i])
                pillar_out += verts
                p_nodes.append(nodes)

        out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr + 2*self.pillar_nnodes*npfeiler)

#        out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr)
        # -- body verts

        _z = np.zeros(n)
        l = 0.
        for i in range(n):
            l += self.segment_len[i]
            _z[i] = self.deck_height(l, normalized=False)
            #print "seg", l/self.center.length, _z[i]

#            -y, z, -x
        if True:
            for i, v in enumerate(offset_ul.coords):
                out += "%g %g %g\n" % (-v[1], _z[i], -v[0])
            for i, v in enumerate(offset_ll.coords):
                out += "%g %g %g\n" % (-v[1], _z[i] - self.body_height, -v[0])
            for i, v in enumerate(offset_ur.coords[::-1]):
                out += "%g %g %g\n" % (-v[1], _z[i], -v[0])
            for i, v in enumerate(offset_lr.coords[::-1]):
                out += "%g %g %g\n" % (-v[1], _z[i] - self.body_height, -v[0])
        # -- pillars
        #for u in linspace(0, 1., 4):

        out += pillar_out

        #out  += "# pil\n"

        ns = 4*(len(nodes_ul)-1)
        ns += self.pillar_nnodes*len(p_nodes)
        out += "numsurf %i\n" % (ns)

        # -- body nodes
        def surf_between_lines(l1, l2, u, v0, v1):
            out = ""
            u0 = u[0]
            for i in range(len(l1)-1):
                u1 = u0 + u[i+1]
                out += "SURF 0x0\n"
                out += "mat 0\n"
                out += "refs 4\n"
                out += "%i %g %g\n" % (l1[i],   u0, v0)
                out += "%i %g %g\n" % (l1[i+1], u1, v0)
                out += "%i %g %g\n" % (l2[i+1], u1, v1)
                out += "%i %g %g\n" % (l2[i],   u0, v1)
                u0 = u1
            return out

        u = self.segment_len / 25.
#        out += surf_between_lines(nodes_ul[::-1], nodes_ll[::-1], u, 1, 0.75)
#        out += surf_between_lines(nodes_ur, nodes_lr, u, 1, 0.75)
#        out += surf_between_lines(nodes_ul, nodes_ur, u, 0.75, 0.5)
#        out += surf_between_lines(nodes_ll[::-1], nodes_lr[::-1], u, 0.5, 0.25)

        out += surf_between_lines(nodes_ll[::-1], nodes_ul[::-1], u, 1, 0.75)
        out += surf_between_lines(nodes_lr, nodes_ur, u, 1, 0.75)
        out += surf_between_lines(nodes_ur, nodes_ul, u, 0.75, 0.5)
        out += surf_between_lines(nodes_lr[::-1], nodes_ll[::-1], u, 0.5, 0.25)


        for pillar in p_nodes:
            for face in pillar:
                out += "SURF 0x0\n"
                out += "mat 0\n"
                out += "refs %i\n" % (len(face))
        #        for n in face:
        #            out += "%i 0 0\n" % n

                out += "%i 0 0.5\n" % face[0]
                out += "%i 1 0.5\n" % face[1]
                out += "%i 1 0\n" % face[2]
                out += "%i 0 0\n" % face[3]


        out += "kids 0\n"
        #print out
        return out


def ac_header(kids=500):
    out  = "AC3Db\n"
    out += 'MATERIAL "" rgb 1 1 1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n'
    out += "OBJECT world\n"
    out += "kids %i\n" % kids
    return out

def simplify_line(coords, z = None):

    coords = np.array(coords) - coords[0]
    x = coords[:,0]
    y = coords[:,1]
    print "l=", len(x)
    do_interp = False
    if do_interp: # interpolate?
        if len(x) < 4: return
        tck,u = interpolate.splprep([x,y],s=0)
        unew = np.arange(0,1.0,0.0002)
        #out = interpolate.splev(unew,tck) # parametric
        nx, ny = interpolate.splev(unew,tck) # parametric
        xder, yder = interpolate.splev(unew,tck,der=1)

        a = interpolate.spalde(unew, tck) # derivatives
        dx = np.array([ar[1] for ar in a[0]])
        dy = np.array([ar[1] for ar in a[1]])
        an = np.array([math.atan2(_dy, _dx) for _dx, _dy in zip(dx, dy)])

        print "nx", len(nx)

    def get_angle(x, y):
        an = np.zeros_like(x)
        for i in range(1, len(x)-1):
            an[i] = math.atan2(y[i+1] - y[i], x[i+1] - x[i])
        return an

    an = get_angle(x, y)

    #print dx
    #print dy
    #print "an", an * 57.3
    #print "tck", tck


    u = 0.1*np.cos(an)
    v = 0.1*np.sin(an)

    def simple(nx, ny, an, eps_l, eps_a):
        sx = []
        sy = []
        sx.append(nx[0])
        sy.append(ny[0])
        last_angle = an[0]
        l = 0
        for i, a in enumerate(an[1:], 1):
            l += ((nx[i] - nx[i-1])**2 + (ny[i] - ny[i-1])**2)**0.5
            if abs(a - last_angle)*l > eps_l and abs(a - last_angle) > eps_a:
                sx.append(nx[i])
                sy.append(ny[i])
                last_angle = a
                l = 0
        print "simplified", len(sx)
        return sx, sy


    if 0:
        plt.figure()
        plt.plot(x, y, 'c-|', ms=20, label='osm', linewidth=5)
        #plt.plot(x, dx, 'k-')
        #plt.plot(x, dy, 'r-')
        if do_interp: plt.plot(nx, ny, 'k-', label='spline')

        sx, sy = simple(x, y, an, 0.0, 4/57.3)
        plt.plot(sx, sy, 'r-o', label="simple")

        for i, a in enumerate(an[1:], 1):
#            plt.text(x[i], y[i], u"%1.0f°\n%i" % ((an[i]-an[i-1])*57.3, i))
            plt.text(x[i], y[i], u"%1.0f°\n" % ((an[i]-an[i-1])*57.3))

        plt.legend()
        #sx, sy = simple(nx, ny, an, 0.2, 0*5/57.3)
        #plt.plot(sx, sy, 'b-o')

#        plt.quiver(nx, ny, u, v)




    #    plt.legend(['Linear', 'a'])
        plt.axes().set_aspect('equal')
  #  plt.axis([-2.05,2.05,-2.05,2.05])
#    plt.title('Spline of parametrically-defined curve')

        plt.show()



def make_road_from_way(osm_id, tags, coords):
    if osm_id != 35586594: return
    width = 5
    bridge = Bridge(width)
    simplify_line(coords)
    z = np.ones(len(coords))*10.
    out = bridge.geom(False, coords)
    ac = open("bridge.ac", "a")
    ac.write(out)
    ac.close()

    print ">>>", osm_id

def print_stg_info(center_global, ac_name):
    #print "center glob", center_global
    path = calc_tile.directory_name(center_global)
    stg = "%07i.stg" % calc_tile.tile_index(center_global)
    print path + os.sep + stg + ':',
    print "OBJECT_STATIC %s %g %g %1.2f %g\n" % (ac_name, center_global.lon, center_global.lat, 0, 0)


def make_bridge_from_way(osm_id, tags, coords):

    _name = ""
    _height = 0.
    _levels = 0
    _layer = 99

    #if osm_id != 24960801: return True

    ok = (u'Flügelwegbrücke', u'Albertbrücke', u'Waldschlößchenbrücke', u'Loschwitzer Brücke', u'Carolabrücke', u'Marienbrücke', u'Europabrücke')


    if 'highway' in tags and tags['highway'] in ('motorway', '_primary', '_secondary', '_residential'):

        if 'name' in tags:
            if False or tags['name'] in ok:
                pass
            else:
                #print tags['name']
                return
    else:
        if False:
            print "make way", osm_id
            print " T ", tags
            print " R ", coords
        return

#    for i, c in enumerate(coords):
#        print "bri %1.4f %1.4f" % (c[0], c[1])

    try:
        lanes = float(tags['lanes'])
    except:
        lanes = 1
    #if lanes == 1: return
    width = lanes * 3. + 2.
    print "# width %g, lanes %g" % (width, lanes)

    # -- to local coordinates
    center_this = vec2d(coords[0])
    transform = coordinates.Transformation(center_this, hdg = 0)
    coords_local = [transform.toLocal(c) for c in coords]

#    coords = np.array(coords)
#    coords -= coords[0]
    bridge = Bridge(coords_local, transform, width)
    if bridge.too_short: return

#   coords = simplify_line(coords)
    try:
        out = bridge.geom()
    except:
        print "# geom failed"
        return True
    ac_name = "bridge_%i.ac" % osm_id
    ac = open(ac_name, "w")
    ac.write(ac_header(1))
    ac.write(out)
    ac.close()

    bridge.plot_height_profile('bridge_%i.png' % osm_id)

    print_stg_info(center_this, ac_name)

    # append .stg to list
    # store stg_line in dict

    #def uninstall_ours(stg_fname, our_magic):

    #sys.exit(0)
    # -- funny things might happen while parsing OSM
#    try:
#        if 'name' in tags:
#            _name = tags['name']
#            #print "%s" % _name
#            if _name in parameters.SKIP_LIST:
#                print "SKIPPING", _name
#                return False
#        if 'height' in tags:
#            _height = float(tags['height'].replace('m',''))
#        elif 'building:height' in tags:
#            _height = float(tags['building:height'].replace('m',''))
#        if 'building:levels' in tags:
#            _levels = float(tags['building:levels'])
#        if 'layer' in tags:
#            _layer = int(tags['layer'])
#
#        # -- simple (silly?) heuristics to 'respect' layers
#        if _layer == 0: return False
#        if _layer < 99 and _height == 0 and _levels == 0:
#            _levels = _layer + 2
#
#    #        if len(refs) != 4: return False# -- testing, 4 corner buildings only
#
#        # -- all checks OK: accept building
#
#        # -- make outer and inner rings from refs
#        outer_ring = self.refs_to_ring(refs)
#        inner_rings_list = []
#        for way in inner_ways:
#            inner_rings_list.append(self.refs_to_ring(way.refs, inner=True))
#    except Exception, reason:
#        print "\nFailed to parse building (%s)" % reason, osm_id, tags, refs
#        tools.stats.parse_errors += 1
#        return False
#
#    self.buildings.append(Building(osm_id, tags, outer_ring, _name, _height, _levels, inner_rings_list = inner_rings_list))
#
#    tools.stats.objects += 1
#    if tools.stats.objects % 70 == 0: print tools.stats.objects
#    else: sys.stdout.write(".")
    return True



# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y


class Way_extract(object):
    def __init__(self):
        self.roads = []
        self.coord_dict = {}
        self.way_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.

    def process_osm_elements(self, nodes, ways, relations):
        """Takes osmparser Node, Way and Relation objects and transforms them to Building objects"""
        self._process_coords(nodes)
        self._process_ways(ways)
        #yself._process_relations(relations)
        return
        for way in self.way_list:
            if 'building' in way.tags:
                if tools.stats.objects >= parameters.MAX_OBJECTS:
                    return
                self._make_building_from_way(way.osm_id, way.tags, way.refs)
            elif 'building:part' in way.tags:
                if tools.stats.objects >= parameters.MAX_OBJECTS:
                    return
                self._make_building_from_way(way.osm_id, way.tags, way.refs)
#            elif 'bridge' in way.tags:
#                self.make_bridge_from_way(way.osm_id, way.tags, way.refs)

    def _process_ways(self, ways):
        for way in ways.values():
            #if tools.stats.objects >= parameters.MAX_OBJECTS: return
            self.way_list.append(way)

    def _process_coords(self, coords):
       self.coord_dict = coords
       # -- get bounding box
       for node in self.coord_dict.values():
            logging.debug('%s %.4f %.4f', node.osm_id, node.lon, node.lat)
            if node.lon > self.maxlon:
                self.maxlon = node.lon
            if node.lon < self.minlon:
                self.minlon = node.lon
            if node.lat > self.maxlat:
                self.maxlat = node.lat
            if node.lat < self.minlat:
                self.minlat = node.lat

    def _refs_to_line_string(self, refs, inner = False):
        """accept a list of OSM refs, return a line string. Also
           fixes face orientation, depending on inner/outer.
        """
        coords = []
        for ref in refs:
                c = self.coord_dict[ref]
                coords.append(tools.transform.toLocal((c.lon, c.lat)))

        line_string = shg.LineString(coords)
#        # -- outer -> CCW, inner -> not CCW
#        if line_string.is_ccw == inner:
#            line_string.coords = list(line_string.coords)[::-1]
        return line_string

    def make_road_from_way(self, way):
        # transform to local
        self._refs_to_line_string(way.refs)
        # create line string

#    def print_dict(self, dic, tag):
#        for d in dic:
#            print "%10i" % d, dic[d], tag

def alt_main():
    logging.basicConfig(level=logging.INFO)
    #logging.basicConfig(level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser(description="bridge.py reads OSM data and creates bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
#    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

#    if args.e:
#        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    parameters.show()

    osm_fname = parameters.PREFIX + os.sep + parameters.OSM_FILE

    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center_global = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center_global, hdg = 0))

    valid_node_keys = []
#    valid_way_keys = ["building", "building:part", "building:height", "height", "building:levels", "layer"]
    valid_way_keys = ["highway"]
    req_way_keys = ["highway"]
#    valid_relation_keys = ["building"]
#    req_relation_keys = ["building"]
    valid_relation_keys = []
    req_relation_keys = []
    handler = osmparser.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys)
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")
    xml.sax.parse(source, handler)
    logging.info("done.")
    logging.info("Transforming OSM objects to roads")

    way = Way_extract()
    way.process_osm_elements(handler.nodes_dict, handler.ways_dict, handler.relations_dict)
    logging.info("done.")

    logging.info("ways: %i", len(way.way_list))
    if 0:
        import matplotlib.pylab as plt
        for w in way.way_list:
            a = np.array([(way.coord_dict[ref].lon, way.coord_dict[ref].lat) for ref in w.refs])
            plt.plot(a[:,0], a[:,1])
        plt.show()

    elev = tools.Interpolator(parameters.PREFIX + os.sep + "elev.out", fake=parameters.NO_ELEV) # -- fake skips actually reading the file, speeding up things



def main():

    if False:
        coords = np.array(coords)
        x = coords[:,0]
        y = coords[:,1]
        print "l=", len(x)
        #if len(x) < 4: return
        tck,u = interpolate.splprep([x,y],s=0)
        unew = np.arange(0,1.01,0.05)
        out = interpolate.splev(unew,tck) # parametric

        xder, yder = interpolate.splev(unew,tck,der=1)

        plt.figure()
        plt.plot(x, y, '-x')
        plt.plot(out[0], out[1], '-o')

    #    plt.legend(['Linear', 'a'])
        #plt.axis([-1.05,1.05,-1.05,1.05])
    #    plt.title('Spline of parametrically-defined curve')

        plt.show()
        a = interpolate.spalde(unew, tck)
        print "sh", a.shape
        print a

        #bridge_geom(True, None, None)
        sys.exit(0)
    import argparse
    parser = argparse.ArgumentParser(description="bridge.py reads OSM data and creates bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
#    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

#    if args.e:
#        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    parameters.show()


    cmin = vec2d(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH)
    cmax = vec2d(parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    center_global = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center_global, hdg = 0))

    #ac_header()
#    way = osm.OsmExtract(tools.transform.toLocal)
    way = osm.OsmExtract(no_transform)

    #way.register_way_callback('highway', make_road_from_way)
    #way.parse("serpentine.osm")

    way.register_way_callback('bridge', make_bridge_from_way)
#    way.parse("EDDC/carolarbruecke.osm")
    #way.parse("EDDC/bridges.osm")
    #way.parse("LOWI/europabruecke.osm")
    way.parse(parameters.PREFIX + os.sep + parameters.OSM_FILE)

    #stg_dict = {}

    print "done parsing"
    #print_stg_info(center_global, 'bridge.ac')



# probe elevation
# if not linear: split coords
# done
if __name__ == "__main__":
    alt_main()
