#!/usr/bin/env python
# -*- coding: utf-8 -*-
import numpy as np
from vec2d import vec2d
import ac3d
import shapely.geometry as shg
import matplotlib.pyplot as plt
import math
import copy

# debug
import test
#import warnings
#warnings.filterwarnings('error')

class LinearObject(object):
    """
    generic linear feature, base class for road, railroad, bridge etc.
    - source is a center line (OSM way)
    - parallel_offset (left, right)
    - texture

    - height? Could derive specific classes that take care of this.
    - 2d:   roads, railroads. Draped onto terrain.
    - 2.5d: platforms. Height, but no bottom surface.
            roads with (one/two-sided) embankment.
            set angle of embankment
    - 3d:   bridges. Surfaces all around.

    TODO:
      - better draping. Find discontinuity in elev, insert node
      - 2.5d, 3d, embankment
    """
    def __init__(self, transform, osm_id, tags, refs, nodes_dict, width=9, tex_y0=0.5, tex_y1=0.75, AGL=0.5):
        #self.transform = transform
        self.joints = np.arange(4)  # node indices of joints. 8 if 2.5d.
        self.start_joint = False
        self.end_joint = False
        self.width = width
        self.AGL = AGL  # drape distance above terrain
        self.osm_id = osm_id
        self.refs = refs
        self.tags = tags
        self.nodes_dict = nodes_dict
        osm_nodes = [nodes_dict[r] for r in refs]
        nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        self.center = shg.LineString(nodes)
        try:
            self.compute_angle_etc()
            self.edge = self.compute_offset(self.width / 2.)
        except Warning, reason:
            print "Warning in OSM_ID %i: %s" % (self.osm_id, reason)

        self.tex_y0 = tex_y0  # determines which part of texture we use
        self.tex_y1 = tex_y1

#        if self.osm_id == 235008364:
#            test.show_nodes(osm_id, nodes, refs, nodes_dict, self.edge[0], self.edge[1])
#            self.plot(left=False, right=False, angle=True)

    def has_large_angle(self):
        """check for angle > 179 in way, most likely OSM errors"""
        for i, a in enumerate(self.angle[:-1]):
            diff = abs(math.degrees(a - self.angle[i+1]))
            if diff > 180.: diff = 360 - diff
            if diff > 179.: 
                #self.plot()
                #raise ValueError('angle > 179 in OSM_ID %i' % self.osm_id)
                return True
        return False


    def compute_offset(self, offset):

        if 0:
            # -- shapely's parallel_offset sometimes introduces extra nodes??
            left  = self.center.parallel_offset(offset, 'left', resolution=0, join_style=2, mitre_limit=100.0)
            right = self.center.parallel_offset(offset, 'right', resolution=0, join_style=2, mitre_limit=100.0)
        else:
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
                o = abs(offset / math.sin(angle))
                our_node = np.array(self.center.coords[i])
                left[i] = our_node + mean_normal * o
                right[i] = our_node - mean_normal * o

            our_node = np.array(self.center.coords[-1])
            left[-1] = our_node + self.normals[-1] * offset
            right[-1] = our_node - self.normals[-1] * offset
#            right = copy.copy(right[::-1])

            left = shg.LineString(left)
            right = shg.LineString(right)

            return left, right

    def plot(self, center=True, left=False, right=False, angle=True, clf=True, show=True):
        """debug"""
        c = np.array(self.center.coords)
        l = np.array(self.edge[0].coords)
        r = np.array(self.edge[1].coords)
#        l1 = np.array(self.left1.coords)
#        r1 = np.array(self.right1.coords)
        if clf: plt.clf()
        #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
        if center: plt.plot(c[:,0], c[:,1], '-o', color='k')
        if left:   plt.plot(l[:,0], l[:,1], '-o', color='g')
        if right:  plt.plot(r[:,0], r[:,1], '-o', color='r')

#        plt.plot(l1[:,0], l1[:,1], '--.', color='g')
#        plt.plot(r1[:,0], r1[:,1], '--.', color='r')

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
                plt.text(n[0]-3, n[1], "%i" % (i), color='g')
        if right:
            for i, n in enumerate(r):
                plt.text(n[0]+3, n[1], "%i" % (i), color='r')

 #       for i, n in enumerate(l1):
 #           plt.text(n[0]-6, n[1], "(%i)" % (i), color='g')
 #       for i, n in enumerate(r1):
 #           plt.text(n[0]+6, n[1], "(%i)" % (i), color='r')

        if show:
            plt.show()
            plt.savefig('roads_%i.eps' % self.osm_id)


    def compute_angle_etc(self):
        """Compute normals, angle, segment_length, cumulated distance start"""
        n = len(self.center.coords)

        self.vectors = np.zeros((n-1, 2))
        self.normals = np.zeros((n, 2))
        self.angle = np.zeros(n)
        self.segment_len = np.zeros(n)  # segment_len[-1] = 0, so loops over range(n) wont fail
        self.dist = np.zeros(n)
        cumulated_distance = 0.
        for i in range(n-1):
            vector = np.array(self.center.coords[i+1]) - np.array(self.center.coords[i])
            dx, dy = vector
            self.angle[i] = math.atan2(dy, dx)
            self.segment_len[i] = (dy*dy + dx*dx)**0.5
            cumulated_distance += self.segment_len[i]
            self.dist[i+1] = cumulated_distance
            self.normals[i] = np.array((-dy, dx))/self.segment_len[i]
            self.vectors[i] = vector
        
            #assert abs(self.normals[i].magnitude() - 1.) < 0.00001
        self.normals[-1] = self.normals[-2]
        self.angle[-1] = self.angle[-2]

    def _write_to(self, obj, elev, left, right, tex_y0, tex_y1, n_nodes=None, left_z=None,
                  right_z=None, ac=None, offset=None):
        """given left and right LineStrings, write quads
           Use height z if given, probe elev otherwise
           
           if left or right is integer, assume nodes are already written and use 
           integer as node index.
        """
        if not offset:
            offset = vec2d(0,0)
            
        try:
            n_nodes = len(left.coords)
        except AttributeError:
            try:
                n_nodes = len(right.coords)
            except AttributeError:
                if n_nodes is None:
                    raise ValueError("Neither left nor right are iterable: need n_nodes.")

        # -- get elev
        if left_z is not None:
            assert(len(left_z) == n_nodes)

        if right_z is not None:
            assert(len(right_z) == n_nodes)

        # -- write left nodes
        ni = 0
        try:
            node0_l = obj.next_node_index()
            for i, the_node in enumerate(left.coords):
                if left_z is not None:
                    e = left_z[i]
                else:
                    e = elev(vec2d(the_node[0], the_node[1])) + self.AGL
                    #print "s", e, vec2d(the_node[0], the_node[1])
                obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))
#                if abs(the_node[1]) > 50000. or abs(the_node[0]) > 50000.:
#                    print "large node %6.0f %6.0f %i" % (the_node[0], the_node[1], self.osm_id)
                #ac.add_label(''+str(self.osm_id), -the_node[1], e+5, -the_node[0], scale=5)
                ni += 1
        except AttributeError:
            node0_l = left
#        nodes_l = range(node0_l, node0_l + n_nodes)

        # -- write right nodes
        try:
            node0_r = obj.next_node_index()
            for i, the_node in enumerate(right.coords):
                if right_z is not None:
                    e = right_z[i]
                else:
                    e = elev(vec2d(the_node[0], the_node[1])) + self.AGL
                obj.node(-(the_node[1] - offset.y), e, -(the_node[0] - offset.x))
#                ac.add_label(''+str(self.osm_id), -the_node[1], e+5, -the_node[0], scale=5)
                ni += 1
        except AttributeError:
            node0_r = right
#        nodes_r = range(node0_r, node0_r + n_nodes)


        # make left node index list
        # write right nodes
        # make right node index list

        # write textured quads SURF
                # -- write face as series of quads. Works OK, but produces more
                #    SURFs in .ac.
        scale = 30.
        l = node0_l
        r = node0_r
        for i in range(n_nodes-1):
            xl = self.dist[i]/scale
            xr = self.dist[i+1]/scale
            face = [ (l,   xl, tex_y0),
                     (l+1, xr, tex_y0),
                     (r+1, xr, tex_y1),
                     (r,   xl, tex_y1) ]
            l += 1
            r += 1
            obj.face(face[::-1])
        return node0_l, node0_r

    def write_to(self, obj, elev, ac=None, left=None, right=None, z=None, offset=None):
        """need adjacency info
           left: node index of left
           right:
        """
        self._write_to(obj, elev, self.edge[0], self.edge[1],
                                  self.tex_y0, self.tex_y1, ac=ac, offset=offset)
        return True
        # options:
        # - each way has two ends.
        #   store left neighbour? communicate with that one?

        # - on init: compute generic ends, set flag = generic
        # - walk through all intersections
        #     make intersection compute endpoints of all ways, replace generic ones
        # - how to re-use nodes?
        #   - ac3d writer could take care of that -- merge double nodes within tolerance
        #   - store node number in way! Each way will have 4 corners as nodes,
        #     compute intermediate ones on write
        #     is OK with texturing, since can query node position
        # who gets to write the joint nodes?
        # -> the method that takes care of intersections
        # if generic on write: write joint nodes, too
        #self.plot()
        o = obj.next_node_index()
        #face = np.zeros((len(left.coords) + len(right.coords)))
        try:
            do_tex = True
            len_left = len(self.edge[0].coords)
            len_right = len(self.edge[1].coords)

            if len_left != len_right:
                print "different lengths not yet implemented ", self.osm_id
                do_tex = False
                #continue
            elif len_left != len(self.center.coords):
                print "WTF? ", self.osm_id, len(self.center.coords)
                do_tex = False
#            else:
#                return False
            self.plot()
                #continue

            # -- write OSM_ID label
            if 0:
                anchor = self.edge[0].coords[len_left/2]
                e = elev(vec2d(anchor[0], anchor[1])) + self.AGL
                ac.add_label('   ' + str(self.osm_id), -anchor[1], e+4.8, -anchor[0], scale=2)

            # -- write nodes
            if 1:
                ni = 0
                ofs_l = obj.next_node_index()
                for p in self.edge[0].coords:
                    e = elev(vec2d(p[0], p[1])) + self.AGL
                    obj.node(-p[1], e, -p[0])
#                    ac.add_label('l'+str(ni), -p[1], e+5, -p[0], scale=5)
                    ni += 1

                ofs_r = obj.next_node_index()
                for p in self.edge[1].coords[::-1]:
                    e = elev(vec2d(p[0], p[1])) + self.AGL
                    obj.node(-p[1], e, -p[0])
#                    ac.add_label('r'+str(ni), -p[1], e+5, -p[0], scale=5)
                    ni += 1
                #refs = np.arange(len_left + len_right) + o
                nodes_l = np.arange(len(self.edge[0].coords))
                nodes_r = np.arange(len(self.edge[1].coords))

            if 0:
                # -- write face as one polygon. Seems to produce artifacts
                #    in sloped terrain. Maybe do flatness check in the future.
                face = []
                scale = 10.
                x = 0.
                for i, n in enumerate(nodes_l):
                    if do_tex: x = self.dist[i]/scale
                    face.append((n+o, x, self.tex_y0))
                o += len(self.edge[0].coords)

                for i, n in enumerate(nodes_r):
                    if do_tex: x = self.dist[-i-1]/scale
                    face.append((n+o, x, self.y1))
                obj.face(face[::-1])
            else:
                # -- write face as series of quads. Works OK, but produces more
                #    SURFs in .ac.
                scale = 30.
                l = ofs_l
                r = ofs_r
                for i in range(len(self.edge[0].coords)-1):
                    xl = self.dist[i]/scale
                    xr = self.dist[i+1]/scale
                    face = [ (l,   xl, self.tex_y0),
                             (l+1, xr, self.tex_y0),
                             (r+1, xr, self.tex_y1),
                             (r,   xl, self.tex_y1) ]
                    l += 1
                    r += 1
                    obj.face(face[::-1])

        except NotImplementedError:
            print "error in osm_id", self.osm_id

        return True

def main():
    ac = ac3d.Writer(tools.stats)
    obj = ac.new_object('roads', 'tex/bridge.png')
    line.write_to(obj)
    f = open('line.ac', 'w')

    if 0:
        ac.center()
        plt.clf()
        ac.plot()
        plt.show()

    f.write(str(ac))
    f.close()

if __name__ == "__main__":
    main()