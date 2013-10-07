#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Created on Sun Sep 29 10:42:12 2013

@author: tom
"""
import scipy.interpolate as interpolate
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

def probe_elev():
    pass
    import subprocess
    
    pid = subprocess.Popen(["/bin/mycmd", "myarg"],  stdin=subprocess.PIPE, stdout=subprocess.PIPE).pid
    pid.communicate( "input data\n" )
    pid.wait()
    pid.stdout.read()
    
class Bridge(object):
#    def __init__(self, osm_id, tags, refs, scale=1):
    def __init__(self, scale=1):
        pass
    
        self.upper_offset = 0.5*scale
        self.body_height = 0.3*scale
        self.lower_offset = 0.3*scale
        self.pillar_r0 = 0.2*scale
        self.pillar_r1 = 0.2*scale
        self.pillar_nnodes = 16
        
        self.scale = scale


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
            vert += "%1.6f %1.6f %1.6f\n" % (x+node[1], y+node[0], h1)
        for a in np.linspace(0, 2*np.pi, self.pillar_nnodes, endpoint = False):
            a += np.pi/self.pillar_nnodes
            node = np.array([rx*np.cos(a), ry*np.sin(a)])
            node = np.dot(R, node)
            vert += "%1.6f %1.6f %1.6f\n" % (x+node[1], y+node[0], h0)
    
        for i in range(self.pillar_nnodes-1):
            face = [ofs+i, ofs+i+1, ofs+i+1+self.pillar_nnodes, ofs+i+self.pillar_nnodes][::-1]
            nodes_list.append(face)
        i = self.pillar_nnodes - 1
        face = [ofs+i, ofs, ofs+self.pillar_nnodes, ofs+i+self.pillar_nnodes][::-1]
        nodes_list.append(face)
    
        return ofs + 2*self.pillar_nnodes, vert, nodes_list

    def prep_height(self):
        pass
        # - probe terrain at points on center
#        insert nodes at equidistant
#        simplify
        
#        pillar positions
#        height() = linear_height(b0, b1)

        if center.length < 10: raise ValueError("bridge length must be > 10 m")

        ofs = 1. 
        s_ofs0 = center.interpolate(ofs)
        s_ofs1 = center.interpolate(center.length - ofs)
        s_street0 = center.interpolate(0.25, normalized=True)
        s_street1 = center.interpolate(0.75, normalized=True)
        
        
        
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
#        compute total pillar height -> cost
        
        
#                            -----o---
#                      -o----     |
#                  --+- |         |
#               ---  |  |         |
#        ___o_--_____|__|_________|__
#           s0       0  s_ofs0   s_street0
#         dh/dr=0  h>=min_h_ofs h>=min_h_street



    def geom(self, default, coords, z):
    
        if default:
            t = np.arange(0,1.1,.01)
            x = np.sin(2*np.pi*t)
            y = np.cos(np.pi*t)
            z = np.sin(2*np.pi*t)*0+1
            coords = zip(x,y)
        else:
            x = np.zeros(len(coords))
            y = np.zeros_like(x)
            z = np.zeros(len(coords)+10)+10
            for i, c in enumerate(coords):
                x[i] = c[0]
                y[i] = c[1]
    
        center = shg.LineString(coords)
        #center = center.simplify(0.03)
            
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

#        segment_len = np.array([vec2d(coord).distance_to(vec2d(center.coords[i])) for i, coord in enumerate(center.coords[1:])])
        segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(offset_ur.coords[i])) for i, coord in enumerate(offset_ur.coords[1:])])
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
        out += 'texture "bridge.png"\n'
        n_ul = len(offset_ul.coords)
        n_ll = len(offset_ll.coords)
        n_ur = len(offset_ul.coords)
        n_lr = len(offset_ll.coords)
        
        print "lens", n, n_ul, n_ll, n_ur, n_lr
        
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
            height = z[0]
            for i in range(npfeiler):
                pillar_pos = center.interpolate(l)
                # FIXME: angle
                i0, verts, nodes = self.pillar(pillar_pos.coords[0][0], pillar_pos.coords[0][1], height - self.body_height, 0, i0, 0.)
                pillar_out += verts
                p_nodes.append(nodes)
                l += pillar_distance
        else:
            ipfeiler = range(len(x))[::1]
            npfeiler = len(ipfeiler)

            # -- pillar verts
            for j, i in enumerate(ipfeiler):
                i0, verts, nodes = self.pillar(x[i], y[i], z[j] - self.body_height, 0, i0, angle[i])
                pillar_out += verts
                p_nodes.append(nodes)


            
        out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr + 2*self.pillar_nnodes*npfeiler)
        
#        out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr)
        
        # -- body verts
        if True:
            for i, v in enumerate(offset_ul.coords):
                out += "%g %g %g\n" % (v[0], v[1], z[i])
            for i, v in enumerate(offset_ll.coords):
                out += "%g %g %g\n" % (v[0], v[1], z[i] - self.body_height)
            for i, v in enumerate(offset_ur.coords[::-1]):
                out += "%g %g %g\n" % (v[0], v[1], z[i])
            for i, v in enumerate(offset_lr.coords[::-1]):
                out += "%g %g %g\n" % (v[0], v[1], z[i] - self.body_height)
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

        u = segment_len / 25.
        out += surf_between_lines(nodes_ul, nodes_ll, u, 1, 0.75)
        out += surf_between_lines(nodes_ur[::-1], nodes_lr[::-1], u, 1, 0.75)
        out += surf_between_lines(nodes_ul[::-1], nodes_ur[::-1], u, 0.75, 0.5)
        out += surf_between_lines(nodes_ll, nodes_lr, u, 0.5, 0.25)
        
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
 

def ac_header():
    ac = open("bridge.ac", "w")
    out  = "AC3Db\n"
    out += 'MATERIAL "" rgb 1 1 1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n'
    out += "OBJECT world\n"
    out += "kids 500\n"
    ac.write(out)
    ac.close()
    
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
    out = bridge.geom(False, coords, z)
    ac = open("bridge.ac", "a")
    ac.write(out)
    ac.close()

    print ">>>", osm_id


def make_bridge_from_way(osm_id, tags, coords):

    _name = ""
    _height = 0.
    _levels = 0
    _layer = 99

    ok = (u'Flügelwegbrücke', u'Albertbrücke', u'Waldschlößchenbrücke', u'Loschwitzer Brücke', u'Carolabrücke', u'Marienbrücke')


    if 'highway' in tags and tags['highway'] in ('motorway', 'primary', 'secondary', 'residential'):

        if 'name' in tags:
            if tags['name'] in ok:
                pass
            else:
                print tags['name']
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
    width = lanes * 3. + 2.
    print "width %g, lanes %g" % (width, lanes)
    
#    coords = np.array(coords)    
#    coords -= coords[0]
    z = np.ones(len(coords))*10.
    bridge = Bridge(width)
    simplify_line(coords)
    out = bridge.geom(False, coords, z)
    ac = open("bridge.ac", "a")
    ac.write(out)
    ac.close()

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


if __name__ == "__main__":

    if 0:
        coords = [[0,0], [1,0], [2,0.5]]
        a = shg.LineString(coords)
        print a
        sys.exit(0)

    if 0:
        an = np.array([0.,0,45,45,45,20,0,0])
        coords = np.zeros((len(an),2))
        for i, a in enumerate(an[1:], 1):
            r = 20
            coords[i,0] = coords[i-1, 0] + r * math.cos(a/57.3)
            coords[i,1] = coords[i-1, 1] + r * math.sin(a/57.3)
#        l = shg.LineString(coords)
#        l.interpolate(10)
#        bla
        simplify_line(coords)
        sys.exit(0)


    if False:
        p = np.linspace(-1.5, 1.5, 20)
        coords = np.zeros((20,2))
        coords[:,0] = 2*p**3-p
        coords[:,1] = -2*p**2+1
        #coords[:,1] = p
    
        simplify_line(coords)
        sys.exit(0)

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
    parser = argparse.ArgumentParser(description="osm2city reads OSM data and creates buildings for use with FlightGear")
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
    center = (cmin + cmax)*0.5
    tools.init(coordinates.Transformation(center, hdg = 0))

    ac_header()
    way = osm.OsmExtract(tools.transform.toLocal)

    #way.register_way_callback('highway', make_road_from_way)
    #way.parse("serpentine.osm")

    way.register_way_callback('bridge', make_bridge_from_way)
    way.parse("EDDC/carolarbruecke.osm")
#    way.parse("EDDC/bridges.osm")
    
    print "done parsing"
