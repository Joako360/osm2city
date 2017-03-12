# -*- coding: utf-8 -*-
"""
Ugly, highly experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: Portree Kid
"""
import argparse
import logging
import numpy as np
import os
from typing import List

import shapely.geometry as shg

from cluster import ClusterContainer
import parameters
from utils import osmparser, coordinates, ac3d, stg_io2, utilities
from utils.vec2d import Vec2d


OUR_MAGIC = "osm2platforms"  # Used in e.g. stg files to mark edits by osm2platforms
SCENERY_TYPE = "Buildings"  # yes, not "Platforms"


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
        self.nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in self.osm_nodes])
        self.is_area = False
        if 'area' in tags and tags['area'] == 'yes' and len(self.nodes) > 2:
            self.is_area = True
        self.line_string = shg.LineString(self.nodes)
        self.anchor = Vec2d(self.nodes[0])


def _process_osm_platform(nodes_dict, ways_dict, my_coord_transformator) -> List[Platform]:
    my_platforms = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if not ('railway' in way.tags and way.tags['railway'] == 'platform'):
            continue

        if 'layer' in way.tags and int(way.tags['layer']) < 0:
            logging.debug("layer %s %d", way.tags['layer'], key)
            continue  # no underground platforms allowed

        first_node = nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        platform = Platform(my_coord_transformator, way.osm_id, way.tags, way.refs, nodes_dict)
        my_platforms.append(platform)

    return my_platforms


def _write(fg_elev: utilities.FGElev, stg_manager, replacement_prefix, clusters,
           coords_transform: coordinates.Transformation, stats: utilities.Stats):
    for cl in clusters:
        if cl.objects:
            center_tile = Vec2d(coords_transform.toGlobal(cl.center))
            ac_file_name = "%splatforms%02i%02i.ac" % (replacement_prefix, cl.grid_index.ix, cl.grid_index.iy)
            ac = ac3d.File(stats=stats)
            obj = ac.new_object('platforms', "Textures/Terrain/asphalt.png")
            for platform in cl.objects[:]:
                if platform.is_area:
                    _write_area(platform, fg_elev, obj, cl.center)
                else:
                    _write_line(platform, fg_elev, obj, cl.center)

            # using 0 elevation and 0 heading because ac-models already account for it
            path = stg_manager.add_object_static(ac_file_name, center_tile, 0, 0)
            file_name = path + os.sep + ac_file_name
            f = open(file_name, 'w')
            f.write(str(ac))
            f.close()


def _write_area(platform: Platform, fg_elev: utilities.FGElev, obj: ac3d.Object, offset) -> None:
    """Writes a platform mapped as an area"""
    if len(platform.nodes) < 3:
        logging.debug('ERROR: platform with osm_id=%d cannot created due to less then 3 nodes', platform.osm_id)
        return
    linear_ring = shg.LinearRing(platform.nodes)

    o = obj.next_node_index()
    if linear_ring.is_ccw:
        logging.debug('Anti-Clockwise')
    else:
        logging.debug("Clockwise")
        platform.nodes = platform.nodes[::-1]
    for p in platform.nodes:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) + 1
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    top_nodes = np.arange(len(platform.nodes))
    platform.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
    rd_len = len(platform.line_string.coords)
    platform.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        platform.dist[i] = platform.dist[i - 1] + platform.segment_len[i]
    face = []
    x = 0.
    # Top Face
    for i, n in enumerate(top_nodes):
        face.append((n + o, x, 0.5))
    obj.face(face, mat=0)
    # Build bottom ring
    for p in platform.nodes:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) - 1
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    # Build Sides
    for i, n in enumerate(top_nodes[1:]):
        sideface = list()
        sideface.append((n + o + rd_len - 1, x, 0.5))
        sideface.append((n + o + rd_len, x, 0.5))
        sideface.append((n + o, x, 0.5))
        sideface.append((n + o - 1, x, 0.5))
        obj.face(sideface, mat=0)


def _write_line(platform, fg_elev: utilities.FGElev, obj, offset) -> None:
    """Writes a platform as a area which only is mapped as a line"""
    o = obj.next_node_index()
    left = platform.line_string.parallel_offset(2, 'left', resolution=8, join_style=1, mitre_limit=10.0)
    right = platform.line_string.parallel_offset(2, 'right', resolution=8, join_style=1, mitre_limit=10.0)
    if not isinstance(left, shg.LineString) or not isinstance(right, shg.LineString):
        logging.debug("ERROR: platform with osm_id=%d cannot be created due to geometry constraints", platform.osm_id)
        return
    idx_left = obj.next_node_index()
    for p in left.coords:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) + 1
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    idx_right = obj.next_node_index()
    for p in right.coords:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) + 1
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    nodes_l = np.arange(len(left.coords))
    nodes_r = np.arange(len(right.coords))
    platform.segment_len = np.array([0] + [Vec2d(coord).distance_to(Vec2d(platform.line_string.coords[i])) for i, coord in enumerate(platform.line_string.coords[1:])])
    rd_len = len(platform.line_string.coords)
    platform.dist = np.zeros((rd_len))
    for i in range(1, rd_len):
        platform.dist[i] = platform.dist[i - 1] + platform.segment_len[i]
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
    for p in left.coords:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) + 1
        obj.node(-p[1] + offset.y, e, -p[0] + offset.x)
    # Build bottom right line
    idx_bottom_right = obj.next_node_index()
    for p in right.coords:
        e = fg_elev.probe_elev(Vec2d(p[0], p[1])) + 1
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


def process(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev) -> None:
    stats = utilities.Stats()
    # -- prepare transformation to local coordinates
    cmin, cmax = parameters.get_extent_global()

    # -- create (empty) clusters
    lmin = Vec2d(coords_transform.toLocal(cmin))
    lmax = Vec2d(coords_transform.toLocal(cmax))
    clusters = ClusterContainer(lmin, lmax)

    if not parameters.USE_DATABASE:
        osm_way_result = osmparser.fetch_osm_file_data(['railway', 'area', 'layer'], ["railway"])
    else:
        osm_way_result = osmparser.fetch_osm_db_data_ways_key_values(["railway=>platform"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    platforms = _process_osm_platform(osm_nodes_dict, osm_ways_dict, coords_transform)
    logging.info("ways: %i", len(platforms))
    if not platforms:
        logging.info("No platforms found -> aborting")
        return

    for platform in platforms:
        clusters.append(platform.anchor, platform, stats)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, SCENERY_TYPE, OUR_MAGIC, replacement_prefix)

    _write(fg_elev, stg_manager, replacement_prefix, clusters, coords_transform, stats)

    # -- write stg
    stg_manager.write()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="platforms.py reads OSM data and creates platform models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel", dest="loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    args = parser.parse_args()
    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    parameters.show()

    my_coords_transform = coordinates.Transformation(parameters.get_center_global())
    my_fg_elev = utilities.FGElev(my_coords_transform)

    process(my_coords_transform, my_fg_elev)

    my_fg_elev.close()

    logging.info("******* Finished *******")
