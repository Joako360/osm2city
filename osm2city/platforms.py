# -*- coding: utf-8 -*-
"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import logging
import numpy as np
from typing import List

import shapely.geometry as shg

from osm2city import parameters
from osm2city.utils import utilities, ac3d, coordinates, osmparser
from osm2city.types import osmstrings as s
from osm2city.utils.vec2d import Vec2d


class Platform(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []

        self.osm_nodes = list()
        for r in refs:  # safe way instead of [nodes_dict[r] for r in refs] if ref would be missing
            if r in nodes_dict:
                self.osm_nodes.append(nodes_dict[r])
        self.nodes = np.array([transform.to_local((n.lon, n.lat)) for n in self.osm_nodes])
        self.is_area = False
        if s.K_AREA in tags and tags[s.K_AREA] == s.V_YES and len(self.nodes) > 2:
            self.is_area = True
        self.line_string = shg.LineString(self.nodes)
        self.anchor = Vec2d(self.nodes[0])

    def write(self, fg_elev: utilities.FGElev, obj: ac3d.Object, offset) -> None:
        if self.is_area:
            self._write_area(fg_elev, obj, offset)
        else:
            self._write_line(fg_elev, obj, offset)

    def _write_area(self, fg_elev: utilities.FGElev, obj: ac3d.Object, offset) -> None:
        """Writes a platform mapped as an area"""
        if len(self.nodes) < 3:
            logging.debug('ERROR: platform with osm_id=%d cannot created due to less then 3 nodes', self.osm_id)
            return
        linear_ring = shg.LinearRing(self.nodes)

        o = obj.next_node_index()
        if linear_ring.is_ccw:
            logging.debug('Anti-Clockwise')
        else:
            logging.debug("Clockwise")
            self.nodes = self.nodes[::-1]
        for p in self.nodes:
            e = fg_elev.probe_elev((p[0], p[1])) + 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        top_nodes = np.arange(len(self.nodes))
        self.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(self.line_string.coords[i])) for i, coord in enumerate(self.line_string.coords[1:])])
        rd_len = len(self.line_string.coords)
        self.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            self.dist[i] = self.dist[i - 1] + self.segment_len[i]
        face = []
        x = 0.
        # Top Face
        for i, n in enumerate(top_nodes):
            face.append((n + o, x, 0.5))
        obj.face(face)
        # Build bottom ring
        for p in self.nodes:
            e = fg_elev.probe_elev((p[0], p[1])) - 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        # Build Sides
        for i, n in enumerate(top_nodes[1:]):
            sideface = list()
            sideface.append((n + o + rd_len - 1, x, 0.5))
            sideface.append((n + o + rd_len, x, 0.5))
            sideface.append((n + o, x, 0.5))
            sideface.append((n + o - 1, x, 0.5))
            obj.face(sideface)

    def _write_line(self, fg_elev: utilities.FGElev, obj, offset) -> None:
        """Writes a platform as a area which only is mapped as a line"""
        o = obj.next_node_index()
        left = self.line_string.parallel_offset(2, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = self.line_string.parallel_offset(2, 'right', resolution=8, join_style=1, mitre_limit=10.0)
        if not isinstance(left, shg.LineString) or not isinstance(right, shg.LineString):
            logging.debug("ERROR: platform with osm_id=%d cannot be created due to geometry constraints", self.osm_id)
            return
        idx_left = obj.next_node_index()
        for p in left.coords:
            e = fg_elev.probe_elev((p[0], p[1])) + 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        idx_right = obj.next_node_index()
        for p in right.coords:
            e = fg_elev.probe_elev((p[0], p[1])) + 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        nodes_l = np.arange(len(left.coords))
        nodes_r = np.arange(len(right.coords))
        self.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(self.line_string.coords[i])) for i, coord in enumerate(self.line_string.coords[1:])])
        rd_len = len(self.line_string.coords)
        self.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            self.dist[i] = self.dist[i - 1] + self.segment_len[i]
        # Top Surface
        face = []
        x = 0.
        for i, n in enumerate(nodes_l):
            face.append((n + o, x, 0.5))
        o += len(left.coords)
        for i, n in enumerate(nodes_r):
            face.append((n + o, x, 0.75))
        obj.face(face[::-1])
        # Build bottom left line
        idx_bottom_left = obj.next_node_index()
        for p in left.coords:
            e = fg_elev.probe_elev((p[0], p[1])) + 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        # Build bottom right line
        idx_bottom_right = obj.next_node_index()
        for p in right.coords:
            e = fg_elev.probe_elev((p[0], p[1])) + 1
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        idx_end = obj.next_node_index() - 1
        # Build Sides
        for i, n in enumerate(nodes_l[1:]):
            # Start with Second point looking back
            sideface = list()
            sideface.append((n + idx_bottom_left, x, 0.5))
            sideface.append((n + idx_bottom_left - 1, x, 0.5))
            sideface.append((n + idx_left - 1, x, 0.5))
            sideface.append((n + idx_left, x, 0.5))
            obj.face(sideface)
        for i, n in enumerate(nodes_r[1:]):
            # Start with Second point looking back
            sideface = list()
            sideface.append((n + idx_bottom_right, x, 0.5))
            sideface.append((n + idx_bottom_right - 1, x, 0.5))
            sideface.append((n + idx_right - 1, x, 0.5))
            sideface.append((n + idx_right, x, 0.5))
            obj.face(sideface)
        # Build Front&Back
        sideface = list()
        sideface.append((idx_left, x, 0.5))
        sideface.append((idx_bottom_left, x, 0.5))
        sideface.append((idx_end, x, 0.5))
        sideface.append((idx_bottom_left - 1, x, 0.5))
        obj.face(sideface)
        sideface = list()
        sideface.append((idx_bottom_right, x, 0.5))
        sideface.append((idx_bottom_right - 1, x, 0.5))
        sideface.append((idx_right - 1, x, 0.5))
        sideface.append((idx_right, x, 0.5))
        obj.face(sideface)


def process_osm_platform(my_coord_transformator: coordinates.Transformation) -> List[Platform]:
    osm_way_result = osmparser.fetch_osm_db_data_ways_key_values(["railway=>platform"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    my_platforms = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in osm_ways_dict.items():
        if not (s.K_RAILWAY in way.tags and way.tags[s.K_RAILWAY] == s.V_PLATFORM):
            continue

        if s.K_LAYER in way.tags and int(way.tags[s.K_LAYER]) < 0:
            logging.debug("layer %s %d", way.tags[s.K_LAYER], key)
            continue  # no underground platforms allowed

        first_node = osm_nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        platform = Platform(my_coord_transformator, way.osm_id, way.tags, way.refs, osm_nodes_dict)
        my_platforms.append(platform)

    return my_platforms
