# -*- coding: utf-8 -*-

"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
import coordinates
import tools
import parameters
import os
import ac3d
import stg_io2
from objectlist import ObjectList
from random import randint


import logging
import osmparser
from shapely.geometry.base import CAP_STYLE, JOIN_STYLE
import math
from shapely.geometry.linestring import LineString
from cluster import Clusters

OUR_MAGIC = "osm2piers"  # Used in e.g. stg files to mark edits by osm2Piers


class Pier(object):
    def __init__(self, transform, osm_id, tags, refs, nodes_dict):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.typ = 0
        self.nodes = []
        self.is_area = 'area' in tags
        self.elevation = 0

        self.osm_nodes = list()
        for r in refs:  # safe way instead of [nodes_dict[r] for r in refs] if ref would be missing
            if r in nodes_dict:
                self.osm_nodes.append(nodes_dict[r])
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in self.osm_nodes])
        self.anchor = vec2d(self.nodes[0])

    def calc_elevation(self, elev_interpolator):
        """Calculates the elevation (level above sea) as a minimum of all nodes.

        Minimum is taken because there could be residuals from shore in FlightGear scenery.
        """
        min_elevation = 99999
        for node in self.nodes:
            node_elev = elev_interpolator(node)
            node_elev = max(node_elev, -9999)  # Account for elevation probing errors
            min_elevation = min(min_elevation, node_elev)
        self.elevation = min_elevation


class Piers(ObjectList):
    valid_node_keys = []
    req_keys = ['man_made']
    valid_keys = ['area']

    def __init__(self, transform, clusters, boundary_clipping_complete_way):
        ObjectList.__init__(self, transform, clusters, boundary_clipping_complete_way)

    def create_from_way(self, way, nodes_dict):
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)

        col = None
        if 'man_made' in way.tags:
            if way.tags['man_made'] == 'pier':
                col = 6
        if col is None:
            return

        if self.boundary_clipping_complete_way is not None:
            first_node = nodes_dict[way.refs[0]]
            if not self.boundary_clipping_complete_way.contains(shg.Point(first_node.lon, first_node.lat)):
                return

        pier = Pier(self.transform, way.osm_id, way.tags, way.refs, nodes_dict)
        self.objects.append(pier)
        self.clusters.append(pier.anchor, pier)

    def write_piers(self, stg_manager, replacement_prefix):
        for cl in self.clusters:
            if len(cl.objects) > 0:
                center_tile = vec2d(tools.transform.toGlobal(cl.center))       
                ac_fname = "%spiers%02i%02i.ac" % (replacement_prefix, cl.I.x, cl.I.y)
                ac = ac3d.File(stats=tools.stats)
                obj = ac.new_object('piers', "Textures/Terrain/asphalt.png")
                for pier in cl.objects[:]:
                    length = len(pier.nodes)
                    if length > 3 \
                            and pier.nodes[0][0] == pier.nodes[(length - 1)][0] \
                            and pier.nodes[0][1] == pier.nodes[(length - 1)][1]:
                        _write_pier_area(pier, obj, cl.center)
                    else:
                        _write_pier_line(pier, obj, cl.center)
                path = stg_manager.add_object_static(ac_fname, center_tile, 0, 0)
                fname = path + os.sep + ac_fname
                f = open(fname, 'w')
                f.write(str(ac))
                f.close()                

    def write_boats(self, stg_manager):
        for pier in self.objects[:]:
            length = len(pier.nodes)
            if length > 3 \
                    and pier.nodes[0][0] == pier.nodes[(length - 1)][0] \
                    and pier.nodes[0][1] == pier.nodes[(length - 1)][1]:
                _write_boat_area(pier, stg_manager)
            else:
                _write_boat_line(pier, stg_manager)


def _write_boat_area(pier, stg_manager):
    if len(pier.nodes) < 3:
        return
    # Guess a possible position for realistic boat placement
    linear_ring = shg.LinearRing(pier.nodes)
    centroid = linear_ring.centroid
    # Simplyfy
    ring = linear_ring.convex_hull.buffer(40, cap_style=CAP_STYLE.square, join_style=JOIN_STYLE.bevel).simplify(20)
    for p in ring.exterior.coords:
        coord = vec2d(p[0], p[1])
        line_coords = [[centroid.x, centroid.y], p]
        target_vector = shg.LineString(line_coords)
        boat_position = linear_ring.intersection(target_vector)
        coords = linear_ring.coords
        direction = None
        for i in range(len(coords) - 1):
            segment = LineString(coords[i:i + 2])
            if segment.length > 20 and segment.intersects(target_vector):
                direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0]
                                                    , segment.coords[0][1] - segment.coords[1][1]))
                parallel = segment.parallel_offset(10, 'right')
                boat_position = parallel.interpolate(segment.length / 2)
                try:
                    pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
                    _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
                except AttributeError as reason:
                    logging.error(reason)


def _write_boat_line(pier, stg_manager):
    line_string = LineString(pier.nodes)
    right_line = line_string.parallel_offset(4, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    coords = right_line.coords
    for i in range(len(coords) - 1):
        segment = LineString(coords[i:i + 2])
        boat_position = segment.interpolate(segment.length / 2)
        try:
            pos_global = tools.transform.toGlobal((boat_position.x, boat_position.y))
            direction = math.degrees(math.atan2(segment.coords[0][0] - segment.coords[1][0]
                                                , segment.coords[0][1] - segment.coords[1][1]))
            if segment.length > 5:
                _write_model(segment.length, stg_manager, pos_global, direction, pier.elevation)
        except AttributeError as reason:
            logging.error(reason)


def _write_model(length, stg_manager, pos_global, direction, my_elev):
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
                  ('Models/Maritime/Civilian/wide-black-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide-red-yacht.ac', 180),
                  ('Models/Maritime/Civilian/wide-clear-yacht.ac', 180),
                  ('Models/Maritime/Civilian/blue-sailing-boat-20m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-11m.ac', 180),
                  ('Models/Maritime/Civilian/red-sailing-boat-20m.ac', 180)]
        choice = randint(0, len(models) - 1)
        model = models[choice]
    elif length < 250:
        #('Models/Maritime/Civilian/Trawler.xml', 300),
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
    stg_manager.add_object_shared(model[0], vec2d(pos_global), my_elev, direction + model[1])


def _write_pier_area(pier, obj, offset):
    """Writes a Pier mapped as an area"""
    linear_ring = shg.LinearRing(pier.nodes)
#         print ring_lat_lon
    # TODO shg.LinearRing().is_ccw
    o = obj.next_node_index()
    if linear_ring.is_ccw:
        logging.info('CounterClockWise')
    else:
        # normalize to CCW
        logging.info("Clockwise")
        pier.nodes = pier.nodes[::-1]
    # top ring
    e = pier.elevation + 1
    for p in pier.nodes:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    top_nodes = np.arange(len(pier.nodes))
    pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(linear_ring.coords[i])) for i, coord in enumerate(linear_ring.coords[1:])])
    rd_len = len(linear_ring.coords)
    pier.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
    face = []
    x = 0.
    # reversed(list(enumerate(a)))
# Top Face
    for i, n in enumerate(top_nodes):
        face.append((n + o, x, 0.5))
    obj.face(face, mat=0)
# Build bottom ring
    e = pier.elevation - 5
    for p in pier.nodes:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
# Build Sides
    for i, n in enumerate(top_nodes[1:]):
        sideface = list()
        sideface.append((n + o + rd_len - 1, x, 0.5))
        sideface.append((n + o + rd_len, x, 0.5))
        sideface.append((n + o, x, 0.5))
        sideface.append((n + o - 1, x, 0.5))
        obj.face(sideface, mat=0)


def _write_pier_line(pier, obj, offset):
    """Writes a Pier as a area which only is mapped as a line."""
    line_string = shg.LineString(pier.nodes)
    o = obj.next_node_index()
    left = line_string.parallel_offset(1, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    right = line_string.parallel_offset(1, 'right', resolution=8, join_style=1, mitre_limit=10.0)
    idx_left = obj.next_node_index()

    e = pier.elevation + 1
    for p in left.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    idx_right = obj.next_node_index()
    for p in right.coords:
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    nodes_l = np.arange(len(left.coords))
    nodes_r = np.arange(len(right.coords))
    pier.segment_len = np.array([0] + [vec2d(coord).distance_to(vec2d(line_string.coords[i])) for i, coord in enumerate(line_string.coords[1:])])
    rd_len = len(line_string.coords)
    pier.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        pier.dist[i] = pier.dist[i - 1] + pier.segment_len[i]
# Top Surface
    face = []
    x = 0.
    for i, n in enumerate(nodes_l):
        face.append((n + o, x, 0.5))
    o += len(left.coords)
    for i, n in enumerate(nodes_r):
        face.append((n + o, x, 0.75))
    obj.face(face[::-1], mat=0)
# Build bottom left line
    idx_bottom_left = obj.next_node_index()

    e = pier.elevation - 1
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
        obj.face(sideface, mat=0)
    for i, n in enumerate(nodes_r[1:]):
        # Start with Second point looking back
        sideface = list()
        sideface.append((n + idx_bottom_right, x, 0.5))
        sideface.append((n + idx_bottom_right - 1, x, 0.5))
        sideface.append((n + idx_right - 1, x, 0.5))
        sideface.append((n + idx_right, x, 0.5))
        obj.face(sideface, mat=0)
# Build Front&Back
    sideface = list()
    sideface.append((idx_left, x, 0.5))
    sideface.append((idx_bottom_left, x, 0.5))
    sideface.append((idx_end, x, 0.5))
    sideface.append((idx_bottom_left - 1, x, 0.5))
    obj.face(sideface, mat=0)
    sideface = list()
    sideface.append((idx_bottom_right, x, 0.5))
    sideface.append((idx_bottom_right - 1, x, 0.5))
    sideface.append((idx_right - 1, x, 0.5))
    sideface.append((idx_right, x, 0.5))
    obj.face(sideface, mat=0)


def main():
    logging.basicConfig(level=logging.INFO)
    # logging.basicConfig(level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser(description="piers.py reads OSM data and creates Pier models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
#    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
#    parser.add_argument("-c", dest="c", action="store_true", help="do not check for overlapping with static objects")
    parser.add_argument("-l", "--loglevel"
                        , help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL"
                        , required=False)
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file

#    if args.e:
#        parameters.NO_ELEV = True
#    if args.c:
#        parameters.OVERLAP_CHECK = False

    parameters.show()

    osm_fname = parameters.get_OSM_file_name()
    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()
    center_global = parameters.get_center_global()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    
    # -- create (empty) clusters
    lmin = vec2d(tools.transform.toLocal(cmin))
    lmax = vec2d(tools.transform.toLocal(cmax))
    clusters = Clusters(lmin, lmax, parameters.TILE_SIZE, parameters.PREFIX)
   
    border = None
    boundary_clipping_complete_way = None
    if parameters.BOUNDARY_CLIPPING_COMPLETE_WAYS:
        boundary_clipping_complete_way = shg.Polygon(parameters.get_clipping_extent(False))
    elif parameters.BOUNDARY_CLIPPING:
        border = shg.Polygon(parameters.get_clipping_extent())
    piers = Piers(transform, clusters, boundary_clipping_complete_way)
    handler = osmparser.OSMContentHandler(valid_node_keys=[], border=border)
    source = open(osm_fname, encoding="utf8")
    logging.info("Reading the OSM file might take some time ...")

    handler.register_way_callback(piers.create_from_way, req_keys=piers.req_keys)
    handler.parse(source)
    logging.info("ways: %i", len(piers))
    if len(piers) == 0:
        logging.info("No piers found ignoring")
        return

    elev = tools.get_interpolator()
    for pier in piers.objects:
        pier.calc_elevation(elev)

    # -- initialize STG_Manager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)

    piers.write_piers(stg_manager, replacement_prefix)
    logging.info("done.")

    piers.write_boats(stg_manager)
    # -- write stg
    stg_manager.write()
    elev.save_cache()

    logging.info("Done")


if __name__ == "__main__":
    main()
