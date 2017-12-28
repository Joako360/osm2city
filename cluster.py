# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:39:23 2013

"Tile" might be a better name for what we now denote "cluster" in osm2city.
It was chosen however to avoid confusion with FG's scenery tiles.

A cluster is a collection of scenery objects (buildings, roads, etc), roughly
bounded by a rectangle. To speed up rendering, these objects will be merged 
into as few AC3D objects (drawables) as possible.

@author: tom
"""
import logging
import os

import parameters
import utils.utilities
from utils.vec2d import Vec2d
from utils.stg_io2 import STGVerbType


class GridIndex(object):
    """A index position in a 2d grid"""
    def __init__(self, index_x: int, index_y: int) -> None:
        self.ix = index_x
        self.iy = index_y

    def __str__(self) -> str:
        return "index_x: " + str(self.ix) + ", index_y: " + str(self.iy)


class Cluster(object):
    """A container for objects to be included in a single mesh and then written as an ac-file"""
    def __init__(self, grid_index: GridIndex, center: Vec2d, size: int) -> None:
        self.objects = []
        self.grid_index = grid_index  # holds the position in the n*m grid (zero-based)
        self.center = center  # -- center in local coordinates
        self.min = center - size/2.
        self.max = center + size/2.
        self.stats = utils.utilities.Stats()

    def __str__(self) -> str:
        return "cl" + str(self.grid_index)


class ClusterContainer(object):
    """A container for clusters. Initially each cluster is part of a grid of size parameters.TILE_SIZE"""
    def __init__(self, min_point: Vec2d, max_point: Vec2d,
                 stg_verb_type: STGVerbType=STGVerbType.object_static) -> None:
        self.max = max_point
        self.min = min_point
        delta = max_point - min_point  # Vec2d
        self.size = parameters.TILE_SIZE
        max_grid_x = int(delta.x // self.size + 1)
        max_grid_y = int(delta.y // self.size + 1)
        self.max_grid = GridIndex(max_grid_x, max_grid_y)
        self.__len = self.max_grid.ix * self.max_grid.iy
        self.stg_verb_type = stg_verb_type

        logging.info("Generating clusters %s %s for %s", min_point, max_point, stg_verb_type.name)
        self._clusters = [[self._init_cluster(GridIndex(i, j)) for j in range(self.max_grid.iy)] for i in
                          range(self.max_grid.ix)]

        logging.debug("cluster: %s", self.max_grid)
        logging.debug("  delta: %s", delta)
        logging.debug("  min: %s", self.min)
        logging.debug("  max: %s", self.max)

    def __len__(self):
        return self.__len
        
    def _init_cluster(self, grid_index: GridIndex) -> Cluster:
        center = Vec2d(self.min.x + (grid_index.ix + 0.5) * self.size,
                       self.min.y + (grid_index.iy + 0.5) * self.size)  # in meters
        new_cluster = Cluster(grid_index, center, self.size)
        return new_cluster

    def _coords_to_grid_index(self, object_anchor: Vec2d) -> GridIndex:
        """Return the cluster grid_index for a given point in local coordinates"""
        if object_anchor.x < self.min.x:
            object_anchor.x = self.min.x
        elif object_anchor.x > self.max.x:
            object_anchor.x = self.max.x
        if object_anchor.y < self.min.y:
            object_anchor.y = self.min.y
        elif object_anchor.y > self.max.y:
            object_anchor.y = self.max.y

        grid_index = GridIndex(int((object_anchor.x - self.min.x) // self.size),
                               int((object_anchor.y - self.min.y) // self.size))
        return grid_index

    def __call__(self, object_anchor: Vec2d) -> Cluster:
        """Return the cluster instance for a given object's anchor point"""
        grid_index = self._coords_to_grid_index(object_anchor)
        return self._clusters[grid_index.ix][grid_index.iy]

    def __iter__(self):
        for each_list in self._clusters: 
            for item in each_list:
                yield item

    def append(self, anchor: Vec2d, obj, stats: utils.utilities.Stats=None) -> Cluster:
        """Finds the cluster within the cluster grid where a given object's anchor point is situated and then
        adds the object to that cluster."""
        the_cluster = self(anchor)
        the_cluster.objects.append(obj)
        if stats is not None:
            try:
                # Local stats
                self(anchor).stats.count(obj)
                # Global stats
                stats.count(obj)
            except AttributeError:
                pass
        return the_cluster

    def write_statistics_for_buildings(self, clusters_name: str) -> None:
        if utils.utilities.log_level_debug_or_lower() and parameters.WRITE_CLUSTER_STATS:
            my_file = open(os.path.join(parameters.PREFIX, clusters_name + ".dat"), "w")
            for j in range(self.max_grid.iy):
                for i in range(self.max_grid.ix):
                    cl = self._clusters[i][j]
                    my_file.write("%i %i %i\n" % (i, j, len(cl.objects)))
                my_file.write("\n")
            my_file.close()
