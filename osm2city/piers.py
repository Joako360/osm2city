# -*- coding: utf-8 -*-

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import logging
import math
from random import randint
from typing import List

import numpy as np
import shapely.geometry as shg
from shapely.geometry.base import CAP_STYLE, JOIN_STYLE
from shapely.geometry.linestring import LineString

from osm2city import parameters
from osm2city.utils import coordinates as co
from osm2city.utils import utilities, ac3d, osmparser, stg_io2
from osm2city.types import osmstrings as s


class Pier(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.elevation = 0

        self.osm_nodes = list()
        for r in refs:  # safe way instead of [nodes_dict[r] for r in refs] if ref would be missing
            if r in nodes_dict:
                self.osm_nodes.append(nodes_dict[r])
        self.nodes = np.array([transform.to_local((n.lon, n.lat)) for n in self.osm_nodes])
        self.anchor = co.Vec2d(self.nodes[0])

    def calc_elevation(self, fg_elev: utilities.FGElev) -> None:
        """Calculates the elevation (level above sea) as a minimum of all nodes.

        Minimum is taken because there could be residuals from shore in FlightGear scenery.
        """
        min_elevation = 99999
        for node in self.nodes:
            node_elev = fg_elev.probe_elev(node)
            node_elev = max(node_elev, -9999)  # Account for elevation probing errors
            min_elevation = min(min_elevation, node_elev)
        self.elevation = min_elevation

    @property
    def handle_as_area(self) -> bool:
        length = len(self.nodes)
        return length > 3 \
            and self.nodes[0][0] == self.nodes[(length - 1)][0] \
            and self.nodes[0][1] == self.nodes[(length - 1)][1]

    def write(self, obj: ac3d.Object, offset):
        if self.handle_as_area:
            self._write_pier_area(obj, offset)
        else:
            self._write_pier_line(obj, offset)

    def _write_pier_area(self, obj: ac3d.Object, offset) -> None:
        """Writes a Pier mapped as an area"""
        if len(self.nodes) < 3:
            logging.debug('ERROR: platform with osm_id=%d cannot created due to less then 3 nodes', self.osm_id)
            return
        linear_ring = shg.LinearRing(self.nodes)
        # TODO shg.LinearRing().is_ccw
        o = obj.next_node_index()
        if linear_ring.is_ccw:
            logging.info('CounterClockWise')
        else:
            # normalize to CCW
            logging.info("Clockwise")
            self.nodes = self.nodes[::-1]
        # top ring
        e = self.elevation + 1
        for p in self.nodes:
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        top_nodes = np.arange(len(self.nodes))
        self.segment_len = np.array([0] + [co.Vec2d(coord).distance_to(co.Vec2d(linear_ring.coords[i]))
                                           for i, coord in enumerate(linear_ring.coords[1:])])
        rd_len = len(linear_ring.coords)
        self.dist = np.zeros((rd_len))
        for i in range(1, rd_len):
            self.dist[i] = self.dist[i - 1] + self.segment_len[i]
        face = []
        x = 0.
        # reversed(list(enumerate(a)))
        # Top Face
        for i, n in enumerate(top_nodes):
            face.append((n + o, x, 0.5))
        obj.face(face)
        # Build bottom ring
        e = self.elevation - 5
        for p in self.nodes:
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        # Build Sides
        for i, n in enumerate(top_nodes[1:]):
            sideface = list()
            sideface.append((n + o + rd_len - 1, x, 0.5))
            sideface.append((n + o + rd_len, x, 0.5))
            sideface.append((n + o, x, 0.5))
            sideface.append((n + o - 1, x, 0.5))
            obj.face(sideface)

    def _write_pier_line(self, obj, offset):
        """Writes a Pier as a area which only is mapped as a line."""
        line_string = shg.LineString(self.nodes)
        o = obj.next_node_index()
        left = line_string.parallel_offset(1, 'left', resolution=8, join_style=1, mitre_limit=10.0)
        right = line_string.parallel_offset(1, 'right', resolution=8, join_style=1, mitre_limit=10.0)
        if not isinstance(left, shg.LineString) or not isinstance(right, shg.LineString):
            logging.debug("ERROR: pier with osm_id=%d cannot be created due to geometry constraints", self.osm_id)
            return
        idx_left = obj.next_node_index()

        e = self.elevation + 1
        for p in left.coords:
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        idx_right = obj.next_node_index()
        for p in right.coords:
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        nodes_l = np.arange(len(left.coords))
        nodes_r = np.arange(len(right.coords))
        self.segment_len = np.array([0] + [co.Vec2d(coord).distance_to(co.Vec2d(line_string.coords[i]))
                                           for i, coord in enumerate(line_string.coords[1:])])
        rd_len = len(line_string.coords)
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

        e = self.elevation - 1
        for p in left.coords:
            obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
        # Build bottom right line
        idx_bottom_right = obj.next_node_index()
        for p in right.coords:
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


def process_osm_piers(my_coord_transformator: co.Transformation) -> List[Pier]:
    osm_way_result = osmparser.fetch_osm_db_data_ways_key_values(["man_made=>pier"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict
    my_piers = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in osm_ways_dict.items():
        if not (s.K_MAN_MADE in way.tags and way.tags[s.K_MAN_MADE] == s.V_PIER):
            continue

        first_node = osm_nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        pier = Pier(my_coord_transformator, way.osm_id, way.tags, way.refs, osm_nodes_dict)
        my_piers.append(pier)

    return my_piers


def write_boats(stg_manager, piers: List[Pier], coords_transform: co.Transformation):
    for pier in piers:
        if pier.handle_as_area:
            _write_boat_area(pier, stg_manager, coords_transform)
        else:
            _write_boat_line(pier, stg_manager, coords_transform)


def _write_boat_area(pier, stg_manager, coords_transform: co.Transformation):
    if len(pier.nodes) < 3:
        return
    # Guess a possible position for realistic boat placement
    linear_ring = shg.LinearRing(pier.nodes)
    centroid = linear_ring.centroid
    # Simplify
    ring = linear_ring.convex_hull.buffer(40, cap_style=CAP_STYLE.square, join_style=JOIN_STYLE.bevel).simplify(20)
    for p in ring.exterior.coords:
        line_coords = [[centroid.x, centroid.y], p]
        target_vector = shg.LineString(line_coords)
        coords = linear_ring.coords
        for i in range(len(coords) - 1):
            segment = LineString(coords[i:i + 2])
            if segment.length > 20 and segment.intersects(target_vector):
                direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0],
                                                    segment.coords[0][1] - segment.coords[1][1]))
                parallel = segment.parallel_offset(10, 'right')
                boat_position = parallel.interpolate(segment.length / 2)
                try:
                    pos_global = coords_transform.to_global((boat_position.x, boat_position.y))
                    _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
                except AttributeError as reason:
                    logging.error(reason)


def _write_boat_line(pier, stg_manager, coords_transform: co.Transformation):
    line_string = LineString(pier.nodes)
    right_line = line_string.parallel_offset(4, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    if isinstance(right_line, LineString):  # FIXME: what to do else?
        coords = right_line.coords
        for i in range(len(coords) - 1):
            segment = LineString(coords[i:i + 2])
            boat_position = segment.interpolate(segment.length / 2)
            try:
                pos_global = coords_transform.to_global((boat_position.x, boat_position.y))
                direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0],
                                                    segment.coords[0][1] - segment.coords[1][1]))
                if segment.length > 5:
                    _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
            except AttributeError as reason:
                logging.error(reason)


def _write_model(length, stg_manager: stg_io2.STGManager, pos_global, direction, my_elev) -> None:
    if length < 20:
        models = [('Models/Maritime/Civilian/wooden_boat.ac', 120),
                  ('Models/Maritime/Civilian/wooden_blue_boat.ac', 120),
                  ('Models/Maritime/Civilian/wooden_green_boat.ac', 120)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 70:
        models = [('Models/Maritime/Civilian/small-red-yacht.ac', 180),
                  ('Models/Maritime/Civilian/small-black-yacht.ac', 180),
                  ('Models/Maritime/Civilian/small-clear-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide_black_yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide_red_yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide_clear_yacht.ac', 180),
                  ('Models/Maritime/Civilian/blue-sailing-boat-20m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-11m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-20m.ac', 180)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 250:
        models = [('Models/Maritime/Civilian/MediumFerry.xml', 10)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 400:
        models = [('Models/Maritime/Civilian/LargeTrawler.xml', 10),
                  ('Models/Maritime/Civilian/LargeFerry.xml', 100),
                  ('Models/Maritime/Civilian/barge.xml', 80)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    else:
        models = [('Models/Maritime/Civilian/SimpleFreighter.ac', 20),
                  ('Models/Maritime/Civilian/FerryBoat1.ac', 70)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    stg_manager.add_object_shared(model[0], co.Vec2d(pos_global), my_elev, direction + model[1])
