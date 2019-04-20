"""Route networks for use outside of osm2city in e.g. AI for FGFS based on OSM data."""

import argparse
import logging
import sys

import networkx as nx
import shapely.geometry as shg

import build_tiles
import parameters
import utils.osmparser as op
import utils.osmstrings as s
from utils.utilities import FGElev
from utils.vec2d import Vec2d


class NetworkNode:
    def __init__(self, osm_id: int, lon: float, lat: float, elev: float = 0) -> None:
        self.osm_id = osm_id
        self.lon = lon
        self.lat = lat
        self.elev = elev

    @classmethod
    def create_from_osm(cls, osm_node: op.Node) -> 'NetworkNode':
        return NetworkNode(osm_node.osm_id, osm_node.lon, osm_node.lat)


def _process_ferry_routes(fg_elev: FGElev) -> nx.Graph:
    """Reads all ferry routes from OSM and transforms them to a set of networks.

    See https://wiki.openstreetmap.org/wiki/Tag:route%3Dferry and https://wiki.openstreetmap.org/wiki/Relation:route
    """
    route_graph = nx.Graph()
    osm_read_results = op.fetch_osm_db_data_ways_key_values([s.KV_ROUTE_FERRY])
    osm_read_results = op.fetch_osm_db_data_relations_routes(osm_read_results)
    osm_nodes_dict = osm_read_results.nodes_dict
    osm_ways_dict = osm_read_results.ways_dict
    _ = osm_read_results.relations_dict
    osm_nodes_dict.update(osm_read_results.rel_nodes_dict)  # just add all relevant nodes to have one dict of nodes
    osm_rel_ways_dict = osm_read_results.rel_ways_dict
    osm_ways_dict.update(osm_rel_ways_dict)  # nothing special about relations - will just go into the networks

    routes_inside = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())
    for way in osm_ways_dict.values():
        routes_inside.extend(op.split_way_at_boundary(osm_nodes_dict, way, clipping_border,
                                                      op.OSMFeatureType.road))

    for way in routes_inside:
        position = 0
        network_nodes = list()
        for ref in way.refs:
            # analyse and add check elevation
            osm_node = osm_nodes_dict[ref]
            elev, solid = fg_elev.probe(Vec2d(osm_node.lon, osm_node.lat), True)
            network_node = NetworkNode.create_from_osm(osm_node)
            network_node.elev = elev if elev < 0 else elev  # nodes might be outside of the boundary
            if solid:
                if position not in [0, 1, len(way.refs) - 2, len(way.refs) - 1]:
                    network_nodes.append(network_node)
            else:
                network_nodes.append(network_node)
            position += 1

        if len(way.refs) > 1:  # add nodes and edges to graph
            prev_node = None
            for nn in network_nodes:
                route_graph.add_node(nn.osm_id, lon=nn.lon, lat=nn.lat, elev=nn.elev)
                if prev_node:
                    route_graph.add_edge(prev_node, nn.osm_id)
                prev_node = nn.osm_id

    return route_graph


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Routes generates a set of route networks based on OSM data \
    for a lon/lat defined area")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-b", "--boundary", dest="boundary",
                        help="set the boundary as WEST_SOUTH_EAST_NORTH like *9.1_47.0_11_48.8 (. as decimal)",
                        required=True)
    parser.add_argument("-l", "--loglevel", dest="logging_level",
                        help="set loggging level. Valid levels are DEBUG, INFO (default), WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument('-n', '--name', dest='name', help='The name of the area - used in naming output files',
                        required=True)

    args = parser.parse_args()
    my_log_level = 'INFO'
    if args.logging_level:
        my_log_level = args.logging_level.upper()

    build_tiles.configure_logging(my_log_level, False)
    parameters.read_from_file(args.filename)

    try:
        boundary_floats = build_tiles.parse_boundary(args.boundary)
    except build_tiles.BoundaryError as be:
        logging.error(be.message)
        sys.exit(1)

    boundary_west = boundary_floats[0]
    boundary_south = boundary_floats[1]
    boundary_east = boundary_floats[2]
    boundary_north = boundary_floats[3]
    logging.info("Overall boundary {}, {}, {}, {}".format(boundary_west, boundary_south, boundary_east, boundary_north))
    build_tiles.check_boundary(boundary_west, boundary_south, boundary_east, boundary_north)

    parameters.set_boundary(boundary_west, boundary_south, boundary_east, boundary_north)

    parameters.FG_ELEV_CACHE = False
    parameters.PROBE_FOR_WATER = True
    fg_elev = FGElev(None, 0)

    ferry_routes = _process_ferry_routes(fg_elev)
    logging.info('Generated graph with %i nodes and %i edges for ferry routes', ferry_routes.number_of_nodes(),
                 ferry_routes.number_of_edges())
    ferry_routes_file_name = args.name + '.pkl'
    nx.write_gpickle(ferry_routes, ferry_routes_file_name)
    logging.info('Written ferry routes to file %s', ferry_routes_file_name)

    fg_elev.close()
