#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:39:23 2013

@author: tom
"""
from vec2d import vec2d
import tools
import numpy as np


class Cluster(object):
    def __init__(self, I, center):
        #self.out = open
        self.objects = []
        self.I = I
        self.center = center # -- center in local coord
        self.stats = tools.Stats()

    def __str__(self):
        print "cl", self.I

def clamp(i, vmin, vmax):
    return max(vmin, min(i, vmax))


class Clusters(object):
    def __init__(self, min, max, size):
        self.max = max
        self.min = min
        self.delta = max - min
        self.size = size
        self.n = (self.delta / size).int() + 1

        #self.list = []
        self._clusters = [[self.init_cluster(vec2d(i,j)) for j in range(self.n.y)] for i in range(self.n.x)]
#        for i in range(self.nx * self.ny):
#            self.list.append([])


        print "cluster: ", self.n
        print "  delta: ", self.delta
        print "  min: ", self.min
        print "  max: ", self.max

        #print self._clusters

    def init_cluster(self, I):
        center = self.min + (I + 0.5) * self.size # in meters
        new_cluster = Cluster(I, center)
        return new_cluster

    def coords_to_index(self, X):
        """return cluster id for given (x, y)"""
        if X.x < self.min.x: X.x = self.min.x
        if X.x > self.max.x: X.x = self.max.x
        if X.y < self.min.y: X.y = self.min.y
        if X.y > self.max.y: X.y = self.max.y
        #print "min", self.min
        #print "max", self.max

        I = ((X - self.min) / self.size).int()
        return I

    def __call__(self, X):
        I = self.coords_to_index(X)
        #print "  I=(%s)" % I

        return self._clusters[I.x][I.y]

    def append(self, anchor, obj):
        #print "appending at pos", X
        #print "  to ", self(X)
        self(anchor).objects.append(obj)
        self(anchor).stats.count(obj)

    def transfer_buildings(self):
        """1|0
           -+-
           3|2
               import random
    N = 20
    X, Y = np.meshgrid(np.linspace(-1,1,N), np.linspace(-1,1,N))
    for i in range(len(X.ravel())):
        x = X.ravel()[i]
        y = Y.ravel()[i]
        p = vec2d(x,y)
        r = vec2d(np.random.uniform(0,1,2))
        out = p.sign() * (r < abs(p)).int()
        f = out.x + out.y*3
        x += out.x
        y += out.y
        print x, y, out.x, out.y, f
        #int(f)
self._clusters[I.x][I.y]
        """
        print "clusters", self.n
        newclusters = [[self.init_cluster(vec2d(i,j)) for j in range(self.n.y)] for i in range(self.n.x)]

        f = open("reclustered.dat", "w")
        for j in range(self.n.y):
            for i in range(self.n.x):
                cluster = self._clusters[i][j]
                print i, j, cluster.center
                for b in cluster.objects:
                    if b.LOD == 1:
                        norm_coord = (b.anchor - cluster.center) / self.size
                        rnd = vec2d(np.random.uniform(0,1,2))
                        out = norm_coord.sign() * (rnd < abs(norm_coord)).int()
                        ni = int(i + out.x)
                        nj = int(j + out.y)
                        ni = clamp(ni, 0, self.n.x-1)
                        nj = clamp(nj, 0, self.n.y-1)
                    else:
                        ni = i
                        nj = j

                    newclusters[ni][nj].objects.append(b)
                    f.write("%4.0f %4.0f %i %i %i %i %i %i\n" %
                        (b.anchor.x, b.anchor.y,
                         i, j, i + j * self.n.x,
                         ni, nj, ni + nj * self.n.x))
        f.close()
        self._clusters = newclusters
        return

#        import random
#        new_objects = []
#        #print "shuffle", self.center
#        #for c in self:
#        for b in self.objects:
#            nl = (b.anchor - self.center) / self.size * 2.
#            quadrant = (nl.x < 0) + 2*(nl.y < 0)
#            #print "  normalized", nl, abs(nl) #, "m " #, b.anchor - self.center
#            nl = abs(nl)
#            a = random.uniform(0,1)
#            #print "    a=%3.1f %3.1f" % (a, nl.x * nl.y)
#            if a > nl.x * nl.y:
#                self.vacant[quadrant].append(b)
#            else:
#                new_objects.append(b)
#        self.objects = new_objects
#        print "  vacant", len(self.vacant[0]), len(self.vacant[1]), len(self.vacant[2]), len(self.vacant[3]), "new", len(self.objects)
#

    def write_stats(self):
        f = open("cluster_stats.dat", "w")
        for j in range(self.n.y):
            for i in range(self.n.x):
                #id = j * self.n.x + i
                cl = self._clusters[i][j]
                f.write("%i %i %i\n" % (i,j,len(cl.objects)))
            f.write("\n")
        f.close()

    def get_center(self, id):
        pass
#c = Clusters(0,5,2,  0,7,3)
#print c.cluster_id(-1111.999,3)

#def test(x,y):
#    return [x, y]
#
#a = test(1,2)
#print a
if __name__ == "__main__":
    import random
    N = 20
    X, Y = np.meshgrid(np.linspace(-1,1,N), np.linspace(-1,1,N))
    for i in range(len(X.ravel())):
        x = X.ravel()[i]
        y = Y.ravel()[i]
        p = vec2d(x,y)
        r = vec2d(np.random.uniform(0,1,2))
        out = p.sign() * (r < abs(p)).int()
        f = out.x + out.y*3
        x += out.x
        y += out.y
        print x, y, out.x, out.y, f
        #int(f)


