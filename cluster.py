# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:39:23 2013

@author: tom
"""
class Cluster(object):
    def __init__(self):
        #self.out = open
        pass

class Clusters(object):
    def __init__(self, minx, maxx, cx, miny, maxy, cy):
        self.maxx = maxx
        self.minx = minx
        self.maxy = maxy
        self.miny = miny
        self.dx = maxx - minx
        self.dy = maxy - miny
        self.nx = int(self.dx / cx) + 1
        self.ny = int(self.dy / cy) + 1
        self.cx = cx
        self.cy = cy
        self.list = []
        for i in range(self.nx * self.ny):
            self.list.append([])

        print "cluster: %g %g %i %i" % (self.dx, self.dy, self.nx, self.ny)

    def cluster_id(self, x, y):
        """return cluster id for given (x, y)"""
        if x < self.minx: x = self.minx
        if x > self.maxx: x = self.maxx
        if y < self.miny: y = self.miny
        if y > self.maxy: y = self.maxy

        i = int((x - self.minx) / self.cx)
        j = int((y - self.miny) / self.cy)
        return j * self.nx + i

    def cluster(self, x, y):
        return self.list[self.cluster_id(self, x, y)]

    def append(self, x, y, building):
        id = self.cluster_id(x, y)
        print "cluster id", id
        self.list[id].append(building)

    def stats(self):
        f = open("cluster_stats.dat", "w")
        for j in range(self.ny):
            for i in range(self.nx):
                id = j * self.nx + i
                f.write("%i %i %i\n" % (i,j,len(self.list[id])))
            f.write("\n")
        f.close()
#c = Clusters(0,5,2,  0,7,3)
#print c.cluster_id(-1111.999,3)
