#!/usr/bin/env python
# -*- coding: utf-8 -*-
import numpy as np
from vec2d import vec2d
import ac3d
import shapely.geometry as shg
import matplotlib.pyplot as plt
import math
import copy

class LineObject(object):
    """
    generic linear feature, base class for road, railroad, bridge etc.
    - source is an OSM way (center)
    - parallel_offset (left, right)
    - texture

    - height? Could derive specific classes that take care of this.
    - 2d:   roads, railroads. Draped onto terrain.
    - 2.5d: platforms. Height, but no bottom surface.
            roads with (one/two-sided) embankment.
            set angle of embankment
    - 3d:   bridges. Surfaces all around.
    """
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.joints = np.arange(4) # node indices of joints. 8 if 2.5d.
        self.start_joint = False
        self.end_joint = False
        self.width = 3
        self.osm_id = osm_id
        osm_nodes = [nodes_dict[r] for r in refs]
        nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        #self.nodes = np.array([(n.lon, n.lat) for n in osm_nodes])
        self.center = shg.LineString(nodes)
        self.compute_angle_etc()
        self.compute_offset(self.width/2.)

    def compute_offset(self, offset):
        def sgn(x):
            return x >= 0

        if 0:
            self.left  = self.center.parallel_offset(offset, 'left', resolution=0, join_style=2, mitre_limit=100.0)
            self.right = self.center.parallel_offset(offset, 'right', resolution=0, join_style=2, mitre_limit=100.0)
        if 1:
            offset += 1.
            n = len(self.center.coords)
            left = np.zeros((n,2))
            right = np.zeros((n,2))
            our_node = np.array(self.center.coords[0])
            left[0] = our_node + self.normals[0] * offset
            right[0] = our_node - self.normals[0] * offset
            for i in range(1,n-1):
                mean_normal = (self.normals[i-1] + self.normals[i])
                l = (mean_normal[0]**2 + mean_normal[1]**2)**0.5
                mean_normal /= l
                angle = (np.pi + self.angle[i-1] - self.angle[i])/2.
                if sgn(self.angle[i-1]) != sgn(self.angle[i]):
                    print "a", angle*57.3
                o = abs(offset / math.sin(angle))
                print "o", o
                our_node = np.array(self.center.coords[i])
                left[i] = our_node + mean_normal * o
                right[i] = our_node - mean_normal * o

            our_node = np.array(self.center.coords[-1])
            left[-1] = our_node + self.normals[-1] * offset
            right[-1] = our_node - self.normals[-1] * offset
            self.left = shg.LineString(left)
            right = copy.copy(right[::-1])
            self.right = shg.LineString(right)
            if 0 and self.osm_id == 112390391:
                r = copy.copy(right[::-1])
                self.right1 = shg.LineString(r)
                for n in self.right1.coords:
                    print n,
                print "--"
                self.right2 = shg.LineString(right)
                for n in self.right2.coords:
                    print n,
                bla



    def plot(self):
        return
        c = np.array(self.center.coords)
        l = np.array(self.left.coords)
        r = np.array(self.right.coords)
#        l1 = np.array(self.left1.coords)
#        r1 = np.array(self.right1.coords)
        plt.clf()
        #np.array([transform.toLocal((n.lon, n.lat)) for n in r.nodes])
        plt.plot(c[:,0], c[:,1], '-o', color='b')
        plt.plot(l[:,0], l[:,1], '-o', color='g')
        plt.plot(r[:,0], r[:,1], '-o', color='r')

#        plt.plot(l1[:,0], l1[:,1], '--.', color='g')
#        plt.plot(r1[:,0], r1[:,1], '--.', color='r')

        #plt.axes().set_aspect('equal')
        for i, n in enumerate(c):
            plt.text(n[0]+10, n[1], "%i_%1.0f " % (i, self.angle[i]*57.3))
        for i, n in enumerate(l):
            plt.text(n[0]-3, n[1], "%i" % (i), color='g')
        for i, n in enumerate(r):
            plt.text(n[0]+3, n[1], "%i" % (i), color='r')

 #       for i, n in enumerate(l1):
 #           plt.text(n[0]-6, n[1], "(%i)" % (i), color='g')
 #       for i, n in enumerate(r1):
 #           plt.text(n[0]+6, n[1], "(%i)" % (i), color='r')


        #plt.show()
        plt.savefig('roads_%i.eps' % self.osm_id)


    def compute_angle_etc(self):
        """Compute angle, segment_length"""
        n = len(self.center.coords)
#        self.angle[0] = (vec2d(self.center.coords[1]) - vec2d(self.center.coords[0])).atan2()
#        for i in range(1, n-1):
#            self.angle[i] = 0.5 * ( (vec2d(self.center.coords[i-1]) - vec2d(self.center.coords[i])).atan2()
#                              +(vec2d(self.center.coords[i])   - vec2d(self.center.coords[i+1])).atan2())

#            self.angle[i] = (vec2d(self.center.coords[i]) - vec2d(self.center.coords[i-1])).atan2()

        # -- normal vectors
        self.vectors = np.zeros((n-1, 2))
        self.normals = np.zeros((n, 2))
        self.angle = np.zeros(n)
        self.segment_len = np.zeros(n-1)
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


    def write_to(self, obj, elev):
        """need adjacency info"""
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
            len_left = len(self.left.coords)
            len_right = len(self.right.coords)

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
            #if len_left != 3: continue
            #print np.array(self.right.coords)
            for p in self.left.coords:
                e = elev(vec2d(p[0], p[1])) + 1
                obj.node(-p[1], e, -p[0])
            for p in self.right.coords:
                e = elev(vec2d(p[0], p[1])) + 1
                obj.node(-p[1], e, -p[0])
            #refs = np.arange(len_left + len_right) + o
            nodes_l = np.arange(len(self.left.coords))
            nodes_r = np.arange(len(self.right.coords))
            rd_len = len(self.center.coords)

            face = []
            scale = 20.
            x = 0.
#            y0 = 0;
#            y1 = 0.25
            y0 = 0.5
            y1 = 0.75
            for i, n in enumerate(nodes_l):
                #face.append((r+o, 0, 0))
                if do_tex: x = self.dist[i]/scale
                face.append((n+o, x, y0))
            o += len(self.left.coords)

            for i, n in enumerate(nodes_r):
                if do_tex: x = self.dist[-i-1]/scale
                #x = 0
                #face.append((r+o, 0, 0))
                face.append((n+o, x, y1))
            #face = [(r, 0, 0) for r in refs[0:len_left]]
            obj.face(face[::-1])
        except NotImplementedError:
            print "error in osm_id", self.osm_id

        return True

def main():
    ac = ac3d.Writer(tools.stats)
    obj = ac.new_object('roads', 'bridge.png')
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