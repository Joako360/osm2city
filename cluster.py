# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:39:23 2013

"Tile" might be a better name for what we now denote "cluster" in osm2city.
It was chosen however to avoid confusion with FG's scenery tiles.

A cluster is a collection of scenery objects (buildings, roads, etc), roughly
bounded by a rectangle. To speed up rendering, these objects will be merged 
into as few AC3D objects (drawables) as possible.

Cluster borders overlap to make LOD less obvious.

@author: tom
"""
import logging
import os

import numpy as np

import parameters
import tools
import utils.utilities
from utils.vec2d import Vec2d
from utils.stg_io2 import STGVerbType


class Cluster(object):
    def __init__(self, I: Vec2d, center: Vec2d, size: int) -> None:
        self.objects = []
        self.I = I
        self.center = center  # -- center in local coord
        self.min = center - size/2.
        self.max = center + size/2.
        self.stats = utils.utilities.Stats()

    def __str__(self):
        print("cl", self.I)


def clamp(i, vmin, vmax):
    return max(vmin, min(i, vmax))


class Clusters(object):
    def __init__(self, min_point: Vec2d, max_point: Vec2d,
                 stg_verb_type: STGVerbType=STGVerbType.object_static) -> None:
        self.max = max_point
        self.min = min_point
        self.delta = max_point - min_point
        self.size = parameters.TILE_SIZE
        self.n = (self.delta // self.size).int() + 1
        self.__len = self.n.x * self.n.y
        self.prefix = parameters.PREFIX
        self.stg_verb_type = stg_verb_type

        logging.info("Generating clusters %s %s", min_point, max_point)
        self._clusters = [[self.init_cluster(Vec2d(i, j))
        for j in range(self.n.y)] for i in range(self.n.x)]

        print("cluster: ", self.n)
        print("  delta: ", self.delta)
        print("  min: ", self.min)
        print("  max: ", self.max)

    def __len__(self):
        return self.__len
        
    def init_cluster(self, I):
        center = self.min + (I + 0.5) * self.size # in meters
        new_cluster = Cluster(I, center, self.size)
        return new_cluster

    def coords_to_index(self, X):
        """return cluster id for given point X"""
        if X.x < self.min.x:
            X.x = self.min.x
        elif X.x > self.max.x:
            X.x = self.max.x
        if X.y < self.min.y:
            X.y = self.min.y
        elif X.y > self.max.y:
            X.y = self.max.y

        I = ((X - self.min) // self.size).int()
        return I

    def __call__(self, X):
        """return cluster instance for given point X"""
        I = self.coords_to_index(X)

        return self._clusters[I.x][I.y]

    def __iter__(self):
        for each_list in self._clusters: 
            for item in each_list: yield item

    def append(self, anchor: Vec2d, obj) -> Cluster:
        """find cluster of """
        the_cluster = self(anchor)
        the_cluster.objects.append(obj)
        try:
            # Local stats
            self(anchor).stats.count(obj)
            # Global stats
            tools.stats.count(obj)
        except AttributeError:
            pass
        return the_cluster
        
    def transfer_buildings(self) -> None:
        """1|0
           -+-
           3|2
               import random
    N = 20
    X, Y = np.meshgrid(np.linspace(-1,1,N), np.linspace(-1,1,N))
    for i in range(len(X.ravel())):
        x = X.ravel()[i]
        y = Y.ravel()[i]
        p = Vec2d(x,y)
        r = Vec2d(np.random.uniform(0,1,2))
        out = p.sign() * (r < abs(p)).int()
        f = out.x + out.y*3
        x += out.x
        y += out.y
        print x, y, out.x, out.y, f
        #int(f)
self._clusters[I.x][I.y]
        """
        print("clusters", self.n)
        newclusters = [[self.init_cluster(Vec2d(i, j)) for j in range(self.n.y)] for i in range(self.n.x)]

        f = open(self.prefix + os.sep + "reclustered.dat", "w")
        for j in range(self.n.y):
            for i in range(self.n.x):
                cluster = self._clusters[i][j]
                for b in cluster.objects:
                    norm_coord = (b.anchor - cluster.center) // self.size
                    rnd = Vec2d(np.random.uniform(0, 1, 2))
                    out = norm_coord.sign() * (rnd < abs(norm_coord)).int()
                    ni = int(i + out.x)
                    nj = int(j + out.y)
                    ni = clamp(ni, 0, self.n.x-1)
                    nj = clamp(nj, 0, self.n.y-1)

                    newclusters[ni][nj].objects.append(b)
                    f.write("%4.0f %4.0f %i %i %i %i %i %i\n" %
                            (b.anchor.x, b.anchor.y,
                             i, j, i + j * self.n.x,
                             ni, nj, ni + nj * self.n.x))
        f.close()
        self._clusters = newclusters

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

    def write_stats(self, clusters_name: str):
        f = open(self.prefix + os.sep + clusters_name + ".dat", "w")
        for j in range(self.n.y):
            for i in range(self.n.x):
                cl = self._clusters[i][j]
                f.write("%i %i %i\n" % (i, j, len(cl.objects)))
            f.write("\n")
        f.close()

    def get_center(self, id):
        pass
    

if __name__ == "__main__":
    N = 20
    X, Y = np.meshgrid(np.linspace(-1, 1, N), np.linspace(-1, 1, N))
    for i in range(len(X.ravel())):
        x = X.ravel()[i]
        y = Y.ravel()[i]
        p = Vec2d(x, y)
        r = Vec2d(np.random.uniform(0, 1, 2))
        out = p.sign() * (r < abs(p)).int()
        f = out.x + out.y*3
        x += out.x
        y += out.y
        print(x, y, out.x, out.y, f)

