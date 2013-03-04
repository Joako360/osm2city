# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:39:23 2013

@author: tom
"""
from vec2d import vec2d

class Cluster(object):
    def __init__(self, I, center):
        #self.out = open
        self.objects = []
        self.I = I
        self.center = center # -- center in local coord

    def __str__(self):
        print "cl", self.I

class Clusters(object):
    def __init__(self, min, max, step):
        self.max = max
        self.min = min
        self.delta = max - min
        self.step = step
        self.n = (self.delta / step).int() + 1

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
        center = self.min + (I + 0.5) * self.step # in meters
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

        I = ((X - self.min) / self.step).int()
        return I

    def __call__(self, X):
        I = self.coords_to_index(X)
        #print "  I=(%s)" % I

        return self._clusters[I.x][I.y]

    def append(self, X, obj):
        #print "appending at pos", X
        #print "  to ", self(X)
        self(X).objects.append(obj)

    def stats(self):
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
