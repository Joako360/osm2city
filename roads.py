"""

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
x clusterize (however, you don't see residential roads in cities from low alt anyway. LOD?)
  - a road meandering along a cluster boarder should not be clipped all the time.
  - only clip if on next-to-next tile?
  - clip at next tile center?
- LOD
  - major roads - LOD rough
  - minor roads - LOD detail
  - roads LOD? road_rough, road_detail?
- handle junctions
- handle layers/bridges

junctions:
- currently, we get false positives: one road ends, another one begins.
- loop junctions:
    for the_node in nodes:
    if the_node is not endpoint: put way into splitting list
    #if only 2 nodes, and both end nodes, and road types compatible:
    #put way into joining list

Data structures
---------------


nodes_dict: contains all osmparser.Nodes, by OSM_ID
  nodes_dict[OSM_ID] -> Node
  KEEP, because we have a lot more nodes than junctions.
  
Roads.G: graph
  its nodes represent junctions. Indexed by OSM_ID of osmparser.Nodes
  edges represent roads between junctions, and have obj=osmparser.Way
  self.G[ref_1][ref_2]['obj'] -> osmparser.Way

attached_ways_dict: for each (true) junction node, store a list of tuples (attached way, is_first)
  basically, this duplicates Roads.G!
  need self.G[ref]['stubs'][4]
  self.G[ref][] -> Junction.stubs_list[2]
    


Render junction:
  if 2 ways:
    simply join here. Or ignore for now.
  else:
                              
              
      for the_way in ways:
        left_neighbor = compute from angles and width
        store end nodes coords separately
        add to object, get node index
        - store end nodes index in way
        - way does not write end node coords, central method does it
      write junction face

Splitting:
  find all junctions for the_way
  normally a way would have exactly two junctions (at the ends)
  sort junctions in way's node order:
    add junction node index to dict
    sort list
  split into njunctions-1 ways
Now each way's end node is either junction or dead-end.

Joining:

required graph functions:
- find neighbours
-
"""

import argparse
import enum
import logging
import math
import random
import textwrap
from typing import Dict, List

import graph
import linear
import linear_bridge
import matplotlib.pyplot as plt
import numpy as np
import parameters
import scipy.interpolate
import shapely.geometry as shg
import textures.road
import tools
from cluster import ClusterContainer
from utils import osmparser, coordinates, ac3d, stg_io2, utilities, aptdat_io
from utils.vec2d import Vec2d

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark our edits


PSEUDO_OSM_ID = -1  # For those nodes and ways, which get added as part of processing. Not written back to OSM.


def _get_next_pseudo_osm_id():
    global PSEUDO_OSM_ID
    PSEUDO_OSM_ID -= 1
    return PSEUDO_OSM_ID


BRIDGE_KEY = 'bridge'  # the original OSM tag key
REPLACED_BRIDGE_KEY = 'replaced_bridge'  # specifies a way that was originally a bridge, but due to length was changed


def _is_bridge(way: osmparser.Way) -> bool:
    """Returns true if the tags for this way constains the OSM key for bridge."""
    return BRIDGE_KEY in way.tags


def _is_replaced_bridge(way: osmparser.Way) -> bool:
    """Returns true is this way was originally a bridge, but was changed to a non-bridge due to lenght.
    See method Roads._replace_short_bridges_with_ways.
    The reason to keep a replaced_tag is because else the way might be split if a node is in the water."""
    return REPLACED_BRIDGE_KEY in way.tags


def _is_railway(way):
    return "railway" in way.tags


def _is_processed_railway(way):
    """Check whether this is not only a railway, but one that gets processed.

    E.g. funiculars are currently not processed.
    Must be aligned with accepted railways in Roads._create_linear_objects.
    """
    if not _is_railway(way):
        return False
    if way.tags['railway'] in ['rail', 'disused', 'preserved', 'subway', 'narrow_gauge', 'tram', 'light_rail']:
        return True
    return False


def _calc_railway_gauge(way):
    width = 1435
    if way.tags['railway'] in ['narrow_gauge']:
        width = 1000
    if "gauge" in way.tags:
        if osmparser.is_parsable_float(way.tags['gauge']):
            width = float(way.tags['gauge'])
    return width / 1000 * 126 / 57  # in the texture the track uses 57 out of 126 pixels


def _is_highway(way):
    return "highway" in way.tags


def _compatible_ways(way1, way2):
    """Returns True if both ways are either a railway, a bridge or a highway."""
    logging.debug("trying join %i %i", way1.osm_id, way2.osm_id)
    if _is_railway(way1) != _is_railway(way2):
        logging.debug("Nope, either both or none must be railway")
        return False
    elif _is_bridge(way1) != _is_bridge(way2):
        logging.debug("Nope, either both or none must be a bridge")
        return False
    elif _is_highway(way1) != _is_highway(way2):
        logging.debug("Nope, either both or none must be a highway")
        return False
    elif _is_highway(way1) and _is_highway(way2):
        highway_type1 = highway_type_from_osm_tags(way1.tags["highway"])
        highway_type2 = highway_type_from_osm_tags(way2.tags["highway"])
        if highway_type1 != highway_type2:
            logging.debug("Nope, both must be of same highway type")
            return False
    elif _is_railway(way1) and _is_railway(way2):
        if way1.tags['railway'] != way2.tags['railway']:
            logging.debug("Nope, both must be of same railway type")
            return False
    return True


def _init_way_from_existing(way: osmparser.Way, node_references: List[int]) -> osmparser.Way:
    """Return copy of way. The copy will have same osm_id and tags, but only given refs"""
    new_way = osmparser.Way(way.osm_id)
    new_way.pseudo_osm_id = _get_next_pseudo_osm_id()
    new_way.tags = way.tags
    new_way.refs.extend(node_references)
    return new_way


def _has_duplicate_nodes(refs):
    for i, r in enumerate(refs):
        if r in refs[i+1:]:
            return True


@enum.unique
class HighwayType(enum.IntEnum):
    motorway = 12
    trunk = 11
    primary = 10
    secondary = 9
    tertiary = 8
    unclassified = 7
    road = 6
    residential = 5
    living_street = 4
    service = 3
    pedestrian = 2
    slow = 1  # cycle ways, tracks, footpaths etc


def get_highway_attributes(highway_type):
    """This must be aligned with HighwayType as well as textures.road and Roads.create_linear_objects."""
    if highway_type in [HighwayType.motorway]:
        priority = 6  # highest of all, but should be 1 less than for railway
        tex = textures.road.ROAD_3
        width = 6
    elif highway_type in [HighwayType.primary, HighwayType.trunk]:
        priority = 5
        tex = textures.road.ROAD_2
        width = 6
    elif highway_type in [HighwayType.secondary]:
        priority = 4
        tex = textures.road.ROAD_2
        width = 6
    elif highway_type in [HighwayType.tertiary, HighwayType.unclassified, HighwayType.road]:
        priority = 3
        tex = textures.road.ROAD_1
        width = 6
    elif highway_type in [HighwayType.residential, HighwayType.service]:
        priority = 2
        tex = textures.road.ROAD_1
        width = 4
    else:
        priority = 1
        tex = textures.road.ROAD_1
        width = 4
    return priority, tex, width


def highway_type_from_osm_tags(value):
    """Based on OSM tags deducts the HighWayType.
    Returns None if not a highway are unknown value.

    FIXME: Shouldn't we also take care of "junction" and "roundabout"?
    """
    if value in ["motorway"]:
        return HighwayType.motorway
    elif value in ["trunk"]:
        return HighwayType.trunk
    elif value in ["primary"]:
        return HighwayType.primary
    elif value in ["secondary"]:
        return HighwayType.secondary
    elif value in ["tertiary", "tertiary_link", "secondary_link", "primary_link", "motorway_link", "trunk_link"]:
        return HighwayType.tertiary
    elif value == "unclassified":
        return HighwayType.unclassified
    elif value == "road":
        return HighwayType.road
    elif value == "residential":
        return HighwayType.residential
    elif value == "living_street":
        return HighwayType.living_street
    elif value == "service":
        return HighwayType.service
    elif value == "pedestrian":
        return HighwayType.pedestrian
    elif value in ["track", "footway", "cycleway", "bridleway", "steps", "path"]:
        return HighwayType.slow
    else:
        return None


def max_slope_for_road(obj):
    if 'highway' in obj.tags:
        if obj.tags['highway'] in ['motorway']:
            return parameters.MAX_SLOPE_MOTORWAY
        else:
            return parameters.MAX_SLOPE_ROAD
    # must be aligned with accepted railways in Roads._create_linear_objects
    elif 'railway' in obj.tags:
        return parameters.MAX_SLOPE_RAILWAY


def _find_junctions(ways_list, degree=2):
    """
    N = number of nodes
    find junctions by brute force:
    - for each node, store attached ways in a dict                O(N)
    - if a node has 2 ways, store that node as a candidate
    - remove entries/nodes that have less than 2 ways attached    O(N)
    - one way ends, other way starts: also a junction
    FIXME: use quadtree/kdtree
    """

    logging.info('Finding junctions...')
    attached_ways_dict = {}  # a dict: for each ref (aka node) hold a list of attached ways
    for j, the_way in enumerate(ways_list):
        utilities.progress(j, len(ways_list))
        for i, ref in enumerate(the_way.refs):
            try:
                attached_ways_dict[ref].append((the_way, i == 0))  # store tuple (the_way, is_first)
                # -- check if ways are actually distinct before declaring
                #    an junction?
                # not an junction if
                # - only 2 ways && one ends && other starts
                # easier?: only 2 ways, at least one node is middle node
#                        self.junctions_set.add(ref)
            except KeyError:
                attached_ways_dict[ref] = [(the_way, i == 0)]  # initialize node

    # kick nodes that belong to one way only
    for ref, the_ways in list(attached_ways_dict.items()):
        if len(the_ways) < degree:
            # FIXME: join_ways, then return 2 here
            attached_ways_dict.pop(ref)
    return attached_ways_dict


def _attached_ways_dict_remove(attached_ways_dict, the_ref, the_way, ignore_missing_ref=False):
    """Remove given way from given node in attached_ways_dict"""
    if ignore_missing_ref and the_ref not in attached_ways_dict:
        logging.debug("not removing way from the ref %i because the ref is not in attached_ways_dict", the_ref)
        return
    for way, boolean in attached_ways_dict[the_ref]:
        if way == the_way:
            logging.debug("removing way %s from node %i", the_way, the_ref)
            attached_ways_dict[the_ref].remove((the_way, boolean))


def _attached_ways_dict_append(attached_ways_dict, the_ref, the_way, is_first, ignore_missing_ref=False):
    """Append given way to attached_ways_dict. If ignore_non_existing is True, silently
       do nothing in case the_ref does not exist. Otherwise we may get a KeyError."""
    if ignore_missing_ref and the_ref not in attached_ways_dict:
        return
    attached_ways_dict[the_ref].append((the_way, is_first))


class Roads(object):
    VALID_NODE_KEYS = []
    REQ_KEYS = ['highway', 'railway']

    def __init__(self, raw_osm_ways: List[osmparser.Way], nodes_dict: Dict[int, osmparser.Node],
                 coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev) -> None:
        self.transform = coords_transform
        self.fg_elev = fg_elev
        self.ways_list = raw_osm_ways  # raw ways from OSM
        self.bridges_list = list()
        self.railway_list = list()
        self.roads_list = list()
        self.nodes_dict = nodes_dict
        self.graph = None  # network graph of ways
        self.roads_clusters = None
        self.railways_clusters = None

    def __str__(self):
        return "%i ways, %i roads, %i railways, %i bridges" % (len(self.ways_list), len(self.roads_list),
                                                               len(self.railway_list), len(self.bridges_list))

    def process(self, blocked_areas: List[shg.Polygon]) -> None:
        """Processes the OSM data until data can be clusterized.

        Needs to be called after OSM data have been processed using the store_way callback method from
        OSMContentHandler.
        """
        self._remove_tunnels()
        self._replace_short_bridges_with_ways()
        self._check_ways_in_water()
        self._check_blocked_areas(blocked_areas)
        self._cleanup_topology()
        self._check_points_on_line_distance()

        self._remove_unused_nodes()
        self._probe_elev_at_nodes()

        # -- no change in topology beyond create_linear_objects() !
        logging.debug("before linear " + str(self))
        self._create_linear_objects()
        self._propagate_h_add()
        logging.debug("after linear" + str(self))

        if parameters.CREATE_BRIDGES_ONLY:
            self._keep_only_bridges_and_embankments()

        self._clusterize()

    def _check_ways_in_water(self) -> None:
        """Checks whether a way or parts of a way is in water and removes those parts.
        Water in relation to the FlightGear scenery, not OSM data (can be different).
        Bridges and replaced bridges needs to be kept.
        It does performance wise not matter, that _probe_elev_at_nodes also checks the scenery as stuff is cached."""
        extra_ways = list()  # new ways to be added based on split ways
        removed_ways = list()  # existing ways to be removed because not more than one node outside of water
        for way in self.ways_list:
            if _is_bridge(way) or _is_replaced_bridge(way):
                continue
            current_part_refs = list()
            list_of_parts = [current_part_refs]  # a list of "current_parts". A way is split in parts if there is water
            node_refs_in_water = list()
            for ref in way.refs:
                the_node = self.nodes_dict[ref]
                if self.fg_elev.probe_solid(Vec2d(the_node.lon, the_node.lat), is_global=True):
                    current_part_refs.append(ref)
                else:
                    current_part_refs = list()
                    list_of_parts.append(current_part_refs)
                    node_refs_in_water.append(ref)

            if len(node_refs_in_water) == 0:  # all on land - just continue
                continue
            elif len(node_refs_in_water) == 1 and len(way.refs) > 2:  # only 1 point
                if way.refs[0] is not node_refs_in_water[0] and way.refs[-1] is not node_refs_in_water[0]:
                    if logging.getLogger().isEnabledFor(logging.DEBUG):
                        my_string = """Accepting way with only 1 point in water at odm_id = {};
                         first node = {}, last node = {}, removed node {}"""
                        logging.debug(my_string.format(way.osm_id, way.refs[0], way.refs[-1], node_refs_in_water[0]))
                    continue  # only 1 point somewhere in the middle is accepted

            whole_way_found = False
            for part_refs in list_of_parts:
                if len(part_refs) < 2:
                    continue
                else:
                    if not whole_way_found:  # let us re-use the existing way
                        whole_way_found = True
                        way.refs = part_refs
                        logging.debug("Shortening existing way partly in water - osm_id = {}".format(way.osm_id))
                    else:
                        new_way = _init_way_from_existing(way, part_refs)
                        extra_ways.append(new_way)
                        logging.debug("Adding new way from partly in water - osm_id = {}".format(way.osm_id))
            if not whole_way_found:
                removed_ways.append(way)
                logging.debug("Removing way because in water - osm_id = {}".format(way.osm_id))

        # update ways list
        for way in removed_ways:
            try:
                self.ways_list.remove(way)
            except ValueError as e:
                logging.warning("Unable to remove way with osm_id = {}".format(way.osm_id))
        self.ways_list.extend(extra_ways)

    def _check_blocked_areas(self, blocked_areas: List[shg.Polygon]) -> None:
        """Makes sure that there are no ways, which go across a blocked area (e.g. airport runway).
        Ways are clipped over into two ways if intersecting."""
        if len(blocked_areas) == 0:
            return
        new_ways = list()
        for way in self.ways_list:
            my_line = self._line_string_from_way(way)
            for blocked_area in blocked_areas:
                if my_line.intersects(blocked_area):
                    my_multiline = my_line.difference(blocked_area)
                    if len(my_multiline.geoms) != 2:
                        logging.warning("Intersection of way (osm_id=%d) with blocked area cannot be processed.",
                                        way.osm_id)
                        continue
                    # last node in first line is "new" node not found in original line
                    index = len(list(my_multiline.geoms[0].coords)) - 2
                    original_refs = way.refs
                    way.refs = original_refs[:index + 1]
                    new_way = _init_way_from_existing(way, original_refs[index + 1:])
                    new_ways.append(new_way)
                    # now add new nodes from intersection
                    lon_lat = self.transform.toGlobal(list(my_multiline.geoms[0].coords)[-1])
                    new_node = osmparser.Node(_get_next_pseudo_osm_id(), lon_lat[1], lon_lat[0])
                    self.nodes_dict[new_node.osm_id] = new_node
                    way.refs.append(new_node.osm_id)
                    lon_lat = self.transform.toGlobal(list(my_multiline.geoms[1].coords)[0])
                    new_node = osmparser.Node(_get_next_pseudo_osm_id(), lon_lat[1], lon_lat[0])
                    self.nodes_dict[new_node.osm_id] = new_node
                    new_way.refs.insert(0, new_node.osm_id)
                    logging.info("Split way (osm_id=%d) into 2 ways due to blocked area.", way.osm_id)

        self.ways_list.extend(new_ways)

    def _remove_unused_nodes(self):
        """Remove all nodes which are not used in ways in order not to do elevation probing in vane."""
        used_nodes_dict = dict()
        for way in self.ways_list:
            for ref in way.refs:
                used_nodes_dict[ref] = self.nodes_dict[ref]
        self.nodes_dict = used_nodes_dict

    def _probe_elev_at_nodes(self):
        """Add elevation info to all nodes.

        MSL = meters above sea level (i.e. the elevation of the ground)
        h_add = elevation after some adjustment has been added to take care of elevation probing bumpiness.

        At the end save the cache.
        """
        for the_node in list(self.nodes_dict.values()):
            if math.isnan(the_node.lon) or math.isnan(the_node.lat):
                logging.error("NaN encountered while probing elevation")
                continue
            the_node.MSL = self.fg_elev.probe_elev(Vec2d(the_node.lon, the_node.lat), is_global=True)
            the_node.h_add = 0.
        self.fg_elev.save_cache()
    
    def _propagate_h_add_over_edge(self, ref0, ref1, args):
        """propagate h_add over edges of graph"""
        obj = self.G[ref0][ref1]['obj']
        dh_dx = max_slope_for_road(obj)
        n0 = self.nodes_dict[ref0]
        n1 = self.nodes_dict[ref1]
        if n1.h_add > 0:
            return False
            # FIXME: should we really just stop here? Probably yes.
        n1.h_add = max(0, n0.MSL + n0.h_add - obj.center.length * dh_dx - n1.MSL)
        if n1.h_add <= 0.:
            return False
        return True
    
    def _propagate_h_add(self):
        """start at bridges, propagate h_add through nodes"""
        for the_bridge in self.bridges_list:
            # build tree starting at node0
            node0 = the_bridge.refs[0]
            node1 = the_bridge.refs[-1]

            node0s = {node1}
            visited = {node0, node1}
            graph.for_edges_in_bfs_call(self._propagate_h_add_over_edge, None, self.G, node0s, visited)
            node0s = {node0}
            visited = {node0, node1}
            graph.for_edges_in_bfs_call(self._propagate_h_add_over_edge, None, self.G, node0s, visited)

    def _line_string_from_way(self, way: osmparser.Way) -> shg.LineString:
        osm_nodes = [self.nodes_dict[r] for r in way.refs]
        nodes = np.array([self.transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        return shg.LineString(nodes)

    def _cleanup_topology(self):
        """Cleans op the topology for junctions etc."""
        logging.debug("len before %i" % len(self.ways_list))
        attached_ways_dict = _find_junctions(self.ways_list)
        self._split_ways_at_inner_junctions(attached_ways_dict)
        self._join_degree2_junctions(attached_ways_dict)

        logging.debug("len after %i" % len(self.ways_list))

    def _remove_tunnels(self):
        """Remove tunnels."""
        for the_way in self.ways_list:
            if "tunnel" in the_way.tags:
                self.ways_list.remove(the_way)

    def _replace_short_bridges_with_ways(self):
        """Remove bridge tag from short bridges, making them a simple way."""
        for the_way in self.ways_list:
            if _is_bridge(the_way):
                center = self._line_string_from_way(the_way)
                if center.length < parameters.BRIDGE_MIN_LENGTH:
                    the_way.tags.pop(BRIDGE_KEY)
                    the_way.tags[REPLACED_BRIDGE_KEY] = 'yes'
    
    def _keep_only_bridges_and_embankments(self):
        """Remove everything that is not elevated - for debugging purposes"""
        for the_way in self.roads_list:
            h_add = np.array([abs(self.nodes_dict[the_ref].h_add) for the_ref in the_way.refs])
            if h_add.sum() == 0:
                self.roads_list.remove(the_way)
                logging.debug("kick %i", the_way.osm_id)

    def _check_points_on_line_distance(self):
        """Based on parameter makes sure that points on a line are not too long apart for elevation probing reasons.

        If distance is longer than the related parameter, then new points are added along the line.
        """
        for the_way in self.ways_list:
            my_new_refs = [the_way.refs[0]]
            for index in range(1, len(the_way.refs)):
                node0 = self.nodes_dict[the_way.refs[index - 1]]
                node1 = self.nodes_dict[the_way.refs[index]]
                my_line = shg.LineString([self.transform.toLocal((node0.lon, node0.lat)),
                                         self.transform.toLocal((node1.lon, node1.lat))])
                if my_line.length <= parameters.POINTS_ON_LINE_DISTANCE_MAX:
                    my_new_refs.append(the_way.refs[index])
                    continue
                else:
                    additional_needed_nodes = int(my_line.length / parameters.POINTS_ON_LINE_DISTANCE_MAX)
                    for x in range(additional_needed_nodes):
                        new_point = my_line.interpolate((x + 1) * parameters.POINTS_ON_LINE_DISTANCE_MAX)
                        osm_id = _get_next_pseudo_osm_id()
                        lon_lat = self.transform.toGlobal((new_point.x, new_point.y))
                        new_node = osmparser.Node(osm_id, lon_lat[1], lon_lat[0])
                        self.nodes_dict[osm_id] = new_node
                        my_new_refs.append(osm_id)
                    my_new_refs.append(the_way.refs[index])

            the_way.refs = my_new_refs

    def _create_linear_objects(self):
        """Creates the linear objects, which will be created as scenery objects.

        Not processing parking for now (the_way.tags['amenity'] in ['parking'])
        While certainly good to have, parking in OSM is not a linear feature in general.
        We'd need to add areas.
        """
        self.G = graph.Graph()

        priority = 0  # Used both to indicate whether it should be drawn and the priority when crossing

        for the_way in self.ways_list:
            if _is_highway(the_way):
                if "access" in the_way.tags:
                    if not (the_way.tags["access"] == 'no'):
                        continue  # do not process small access links
                highway_type = highway_type_from_osm_tags(the_way.tags["highway"])
                # in method Roads.store_way smaller highways already got removed
                priority, tex, width = get_highway_attributes(highway_type)

            elif _is_railway(the_way):
                if the_way.tags['railway'] in ['rail', 'disused', 'preserved', 'subway']:
                    priority = 20
                    tex = textures.road.TRACK
                elif the_way.tags['railway'] in ['narrow_gauge']:
                    priority = 19
                    tex = textures.road.TRACK  # FIXME: should use proper texture
                elif the_way.tags['railway'] in ['tram', 'light_rail']:
                    priority = 18
                    tex = textures.road.TRAMWAY
                else:
                    priority = 0  # E.g. monorail, miniature
                if priority > 0:
                    width = _calc_railway_gauge(the_way)

            if priority == 0:
                continue

            # The above the ground level determines how much the way will be hovering above the ground.
            # The reason to include the type is that when (highways) are crossing, then the higher level way
            # should have priority in visibility.
            # In earlier code the following was added to give some variance: random.uniform(0.01, 0.1)
            above_ground_level = parameters.MIN_ABOVE_GROUND_LEVEL + 0.005*priority

            try:
                if _is_bridge(the_way):
                    obj = linear_bridge.LinearBridge(self.transform, self.fg_elev, the_way.osm_id,
                                                     the_way.tags, the_way.refs, self.nodes_dict,
                                                     width=width, tex=tex, AGL=above_ground_level)
                    obj.typ = priority  # FIXME: can this be deleted. does not seem to be used at all
                    self.bridges_list.append(obj)
                else:
                    obj = linear.LinearObject(self.transform, the_way.osm_id,
                                              the_way.tags, the_way.refs,
                                              self.nodes_dict, width=width, tex=tex, AGL=above_ground_level)
                    obj.typ = priority
                    if _is_railway(the_way):
                        self.railway_list.append(obj)
                    else:
                        self.roads_list.append(obj)
            except ValueError as reason:
                logging.warning("skipping OSM_ID %i: %s" % (the_way.osm_id, reason))
                continue

            self.G.add_edge(obj)

    def _split_ways_at_inner_junctions(self, attached_ways_dict):
        """Split ways such that none of the interior nodes are junctions.
           I.e., each way object connects to at most two junctions.
        """
        logging.info('Splitting ways at inner junctions...')
        # FIXME: auch splitten, wenn Weg1 von Weg2 erst abzweigt und später wieder hinzukommt 
        #        i.e. way1 and way2 share TWO nodes, both end nodes of one of them 
        new_list = []
        for i, the_way in enumerate(self.ways_list):
            utilities.progress(i, len(self.ways_list))
            self.debug_plot_way(the_way, '-', lw=2, color='0.90', show_label=0)

            new_way = _init_way_from_existing(the_way, [the_way.refs[0]])
            for the_ref in the_way.refs[1:]:
                new_way.refs.append(the_ref)
                if the_ref in attached_ways_dict:
                    new_list.append(new_way)
                    self.debug_plot_way(new_way, '-', lw=1)
                    new_way = _init_way_from_existing(the_way, [the_ref])
            if the_ref not in attached_ways_dict:  # FIXME: store previous test?
                new_list.append(new_way)
                self.debug_plot_way(new_way, '--', lw=1)

        self.ways_list = new_list

    def _compute_junction_nodes(self):
        """ac3d nodes that belong to an junction need special treatment to make sure
           the ways attached to an junction join exactly, i.e., without gaps or overlap. 
        """
        def pr_angle(a):
            print("%5.1f " % (a * 57.3), end='x')

        def angle_from(lin_obj, is_first):
            """if IS_FIRST, the way is pointing away from us, and we can use the angle straight away.
               Otherwise, add 180 deg.
            """
            if is_first:
                angle = lin_obj.angle[0]
            else:
                angle = lin_obj.angle[-1] + np.pi
                if angle > np.pi:
                    angle -= np.pi * 2
            return angle

        for the_ref, ways_list in list(self.attached_ways_dict.items()):
            # each junction knows about the attached ways
            # -- Sort (the_junction.ways) by angle, taking into account is_first. 
            #    This is tricky. x[0] is our linear_object (which has a property "angle").
            #    x[1] is our IS_FIRST flag.
            #    According to IS_FIRST use either first or last angle in list,
            #    (-1 + is_first) evaluates to 0 or -1.
            #    Sorting results in LHS neighbours.
            ways_list.sort(key=lambda x: angle_from(x[0], x[1])) 

            # testing            
            if 1:
                pref_an = -999
    #            print the_ref, " : ",
                for way, is_first in ways_list:
                    an = angle_from(way, is_first)
    
    #                print " (%i)" % way.osm_id, is_first,
    #                pr_angle(an)
                    assert(an > pref_an)
                    pref_an = an
                    
    #            if len(ways_list) > 3: bla
                #if the_ref == 290863179: bla

            our_node = np.array(ways_list[0][0].center.coords[-1 + ways_list[0][1]])
            for i, (way_a, is_first_a) in enumerate(ways_list):
                (way_b, is_first_b) = ways_list[(i+1) % len(ways_list)] # wrap around
                # now we have two neighboring ways
                print(way_a, is_first_a, "joins with", way_b, is_first_b)
                # compute their joining node
                index_a = -1 + is_first_a                
                index_b = -1 + is_first_b                
                if 1:
                    va = way_a.vectors[index_a]
                    na = way_a.normals[index_a] * way_a.width / 2.
                    vb = way_b.vectors[index_b]
                    nb = way_b.normals[index_b] * way_b.width / 2.
                    if not is_first_a:
                        va *= -1
                        na *= -1
                    if is_first_b:
                        vb *= -1
                        nb *= -1
                    
                    Ainv = 1./(va[1]*vb[0]-va[0]*vb[1]) * np.array([[-vb[1], vb[0]], [-va[1], va[0]]])
                    RHS = (nb - na)
                    s = np.dot(Ainv, RHS)
    # FIXME: check which is faster
                    A = np.vstack((va, -vb)).transpose()
                    s = scipy.linalg.solve(A, RHS)
                    q = our_node + na * s[0]

                way_a_lr = way_a.edge[1-is_first_a]
                way_b_lr = way_b.edge[is_first_b]

                q1 = way_a_lr.junction(way_b_lr)
                print(q, q1)
                way_a.plot(center=False, left=True, right=True, show=False)
                way_b.plot(center=False, left=True, right=True, clf=False, show=False)
                plt.plot(q[0], q[1], 'b+')
                plt.plot(q1.coords[0][0], q1.coords[0][1], 'bo')
                plt.show()

    def debug_plot_ref(self, ref, style): 
        if not parameters.DEBUG_PLOT:
            return
        plt.plot(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, style)

    def debug_plot_way(self, way, ls, lw, color=False, ends_marker=False, show_label=False, show_ends=False):
        if not parameters.DEBUG_PLOT:
            return
        col = ['b', 'r', 'y', 'g', '0.25', 'k', 'c']
        if not color:
            color = col[random.randint(0, len(col)-1)]

        osm_nodes = np.array([(self.nodes_dict[r].lon, self.nodes_dict[r].lat) for r in way.refs])
        a = osm_nodes
        plt.plot(a[:, 0], a[:, 1], ls, linewidth=lw, color=color)
        if ends_marker:
            plt.plot(a[0, 0], a[0, 1], ends_marker, linewidth=lw, color=color)
            plt.plot(a[-1, 0], a[-1, 1], ends_marker, linewidth=lw, color=color)
        if show_label:
            plt.text(0.5*(a[0, 0]+a[-1, 0]), 0.5*(a[0, 1]+a[-1, 1]), way.osm_id, color="b")
    
    def debug_plot_junctions(self, style):
        if not parameters.DEBUG_PLOT:
            return
        for ref in self.attached_ways_dict:
            node = self.nodes_dict[ref]
            plt.plot(node.lon, node.lat, style, mfc='None')

    def debug_label_node(self, ref, text=""):
        if not parameters.DEBUG_PLOT:
            return

        node = self.nodes_dict[ref]
        plt.plot(node.lon, node.lat, 'rs', mfc='None', ms=10)
        plt.text(node.lon+0.0001, node.lat, str(node.osm_id) + " h" + str(text))

    def debug_plot(self, save=False, plot_junctions=False, show=False, label_nodes=[], label_all_ways=False, clusters=None):
        if not parameters.DEBUG_PLOT: return
        plt.clf()
        if plot_junctions:
            self.debug_plot_junctions('o')            
        for ref in label_nodes:
            self.debug_label_node(ref)
        col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k', 'c']
        col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
        lw    = [1, 1, 1, 1.2, 1.5, 2, 1]
        lw_w  = np.array([1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]) * 0.1

        if clusters:
            for i, cl in enumerate(clusters):
                if len(cl.objects): 
                    cluster_color = col[random.randint(0, len(col)-1)]
                    c = np.array([[cl.min.x, cl.min.y], 
                                  [cl.max.x, cl.min.y], 
                                  [cl.max.x, cl.max.y], 
                                  [cl.min.x, cl.max.y],
                                  [cl.min.x, cl.min.y]])
                    c = np.array([self.transform.toGlobal(p) for p in c])
                    plt.plot(c[:, 0], c[:, 1], '-', color=cluster_color)
                for r in cl.objects:
                    random_color = col[random.randint(0, len(col)-1)]
                    osmid_color = col[(r.osm_id + len(r.refs)) % len(col)]                
                    a = np.array(r.center.coords)
                    a = np.array([self.transform.toGlobal(p) for p in a])
                    #color = col[r.typ]
                    try:
                        lw = lw_w[r.typ]
                    except:
                        lw = lw_w[0]
                        
                    plt.plot(a[:, 0], a[:, 1], color=cluster_color, linewidth=lw+2)

        for the_way in self.ways_list:
            self.debug_plot_way(the_way, '-', lw=0.5, show_label=True, ends_marker='x')
            
            if 1:
                ref = the_way.refs[0]
                self.debug_label_node(ref)
                ref = the_way.refs[-1]
                self.debug_label_node(ref)

        if save:
            plt.savefig(save)
        if show:
            plt.show()

    def _debug_show_h_add(self, context):
        for the_node in self.nodes_dict.values():
            logging.debug("Context: %s # id=%12i h_add %5.2f", context, the_node.osm_id, the_node.h_add)

    def _join_ways(self, way1, way2, attached_ways_dict):
        """Join ways that
           - don't make an junction and
           - are of compatible type
           must share exactly one node
        """
        logging.debug("Joining %i and %i", way1.osm_id, way2.osm_id)
        if way1.osm_id == way2.osm_id:
            logging.warning("Not joining way %i with itself", way1.osm_id)
            return
        if way1.refs[0] == way2.refs[0]:
            new_refs = way1.refs[::-1] + way2.refs[1:]
        elif way1.refs[0] == way2.refs[-1]:
            new_refs = way2.refs + way1.refs[1:]
        elif way1.refs[-1] == way2.refs[0]:
            new_refs = way1.refs + way2.refs[1:]
        elif way1.refs[-1] == way2.refs[-1]:
            new_refs = way1.refs[:-1] + way2.refs[::-1]
        else:
            logging.warning("Not joining ways that share no endpoint %i %i", way1.osm_id, way2.osm_id)
            return
            
        new_way = _init_way_from_existing(way1, new_refs)
        logging.debug("old and new" + str(way1) + str(new_way))

        _attached_ways_dict_remove(attached_ways_dict, way1.refs[0], way1, ignore_missing_ref=True)
        _attached_ways_dict_remove(attached_ways_dict, way1.refs[-1], way1, ignore_missing_ref=True)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[0], way2, ignore_missing_ref=True)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[-1], way2, ignore_missing_ref=True)

        _attached_ways_dict_append(attached_ways_dict, new_way.refs[0], new_way,
                                   is_first=True, ignore_missing_ref=True)
        _attached_ways_dict_append(attached_ways_dict, new_way.refs[-1], new_way,
                                   is_first=False, ignore_missing_ref=True)

        try:
            self.ways_list.remove(way1)
            logging.debug("1ok ")
        except ValueError:
            self.ways_list.remove(self._debug_find_way_by_osm_id(way1.osm_id))
            logging.debug("1not ")
        try:
            self.ways_list.remove(way2)
            logging.debug("2ok")
        except ValueError:
            self.ways_list.remove(self._debug_find_way_by_osm_id(way2.osm_id))
            logging.debug("2not")
        self.ways_list.append(new_way)

    def _join_degree2_junctions(self, attached_ways_dict):
        for ref, ways_tuple_list in attached_ways_dict.items():
            if len(ways_tuple_list) == 2:
                if _compatible_ways(ways_tuple_list[0][0], ways_tuple_list[1][0]):
                    self._join_ways(ways_tuple_list[0][0], ways_tuple_list[1][0], attached_ways_dict)
                    
    def _debug_find_way_by_osm_id(self, osm_id):
        for the_way in self.ways_list:
            if the_way.osm_id == osm_id:
                return the_way
        raise ValueError("way %i not found" % osm_id)

    def debug_drop_unused_nodes(self):
        new_nodes_dict = {}
        for the_list in [self.ways_list, self.bridges_list, self.roads_list, self.railway_list]:
            for the_obj in the_list:
                for the_ref in the_obj.refs:
                    new_nodes_dict[the_ref] = self.nodes_dict[the_ref]
        self.nodes_dict = new_nodes_dict
                
    def debug_label_nodes(self, stg_manager, file_name="labels"):
        """write OSM_ID for nodes"""
        ac = ac3d.File(stats=tools.stats, show_labels=True)

        for way in self.bridges_list + self.roads_list + self.railway_list:
            # -- label center with way ID
            the_node = self.nodes_dict[way.refs[len(way.refs)/2]]
            anchor = Vec2d(self.transform.toLocal(Vec2d(the_node.lon, the_node.lat)))
            if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                logging.error("Nan encountered while probing anchor elevation")
                continue

            e = self.fg_elev.probe_elev(anchor) + the_node.h_add + 1.
            ac.add_label('way %i' % way.osm_id, -anchor.y, e, -anchor.x, scale=1.)

            # -- label first node
            the_node = self.nodes_dict[way.refs[0]]
            anchor = Vec2d(self.transform.toLocal(Vec2d(the_node.lon, the_node.lat)))
            if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                logging.error("Nan encountered while probing anchor elevation")
                continue

            e = self.fg_elev.probe_elev(anchor) + the_node.h_add + 3.
            ac.add_label(' %i h=%1.1f' % (the_node.osm_id, the_node.h_add), -anchor.y, e, -anchor.x, scale=1.)

            # -- label last node
            the_node = self.nodes_dict[way.refs[-1]]
            anchor = Vec2d(self.transform.toLocal(Vec2d(the_node.lon, the_node.lat)))
            if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                logging.error("Nan encountered while probing anchor elevation")
                continue

            e = self.fg_elev.probe_elev(anchor) + the_node.h_add + 3.
            ac.add_label(' %i h=%1.1f' % (the_node.osm_id, the_node.h_add), -anchor.y, e, -anchor.x, scale=1.)

        path_to_stg = stg_manager.add_object_static(file_name + '.ac', Vec2d(self.transform.toGlobal((0, 0))), 0, 0)
        ac.write(path_to_stg + file_name + '.ac')

    def debug_print_refs_of_way(self, way_osm_id):
        """print refs of given way"""
        for the_way in self.ways_list:
            if the_way.osm_id == way_osm_id:
                print("found", the_way)
                for the_ref in the_way.refs:
                    print("+", the_ref)

    def _clusterize(self):
        """Create cluster.
           Put objects in clusters based on their centroid.
        """
        lmin, lmax = [Vec2d(self.transform.toLocal(c)) for c in parameters.get_extent_global()]
        self.roads_clusters = ClusterContainer(lmin, lmax)
        self.railways_clusters = ClusterContainer(lmin, lmax)

        for the_object in self.bridges_list + self.roads_list + self.railway_list:
            if _is_railway(the_object):
                cluster_ref = self.railways_clusters.append(Vec2d(the_object.center.centroid.coords[0]), the_object)
            else:
                cluster_ref = self.roads_clusters.append(Vec2d(the_object.center.centroid.coords[0]), the_object)
            the_object.cluster_ref = cluster_ref


def process_osm_ways(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way],
                     clipping_border: shg.Polygon) -> List[osmparser.Way]:
    """Processes the values returned from OSM and does a bit of filtering.
    Transformation to roads, railways and bridges is only done later in Roads.process()."""
    my_ways = list()
    for key, way in ways_dict.items():
        if way.osm_id in parameters.SKIP_LIST:
            logging.info("SKIPPING OSM_ID %i", way.osm_id)
            continue

        if _is_highway(way):
            highway_type = highway_type_from_osm_tags(way.tags["highway"])
            if highway_type is None:
                continue
            elif highway_type.value < parameters.HIGHWAY_TYPE_MIN:
                continue
        elif _is_railway(way):
            if not _is_processed_railway(way):
                continue

        if clipping_border is not None:
            first_node = nodes_dict[way.refs[0]]
            if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
                continue
        my_ways.append(way)

    return my_ways


def _process_clusters(clusters, replacement_prefix, fg_elev: utilities.FGElev, stg_manager, stg_paths, is_railway):
    for cl in clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS:
            continue  # skip almost empty clusters

        if is_railway:
            file_start = "railways"
        else:
            file_start = "roads"
        file_name = replacement_prefix + file_start + "%02i%02i" % (cl.grid_index.ix, cl.grid_index.iy)
        center_global = Vec2d(tools.transform.toGlobal(cl.center))
        offset_local = cl.center
        cluster_elev = fg_elev.probe_elev(center_global, True)

        # -- Now write cluster to disk.
        #    First create ac object. Write cluster's objects. Register stg object.
        #    Write ac to file.
        ac = ac3d.File(stats=tools.stats, show_labels=True)
        ac3d_obj = ac.new_object(file_name, 'tex/roads.png', default_swap_uv=True)
        for rd in cl.objects:
            rd.write_to(ac3d_obj, fg_elev, cluster_elev, ac, offset=offset_local)  # FIXME: remove .ac, needed only for adding debug labels

        suffix = ".xml"
        if is_railway:
            suffix = ".ac"
        path_to_stg = stg_manager.add_object_static(file_name + suffix, center_global, cluster_elev, 0)
        stg_paths.add(path_to_stg)
        ac.write(path_to_stg + file_name + '.ac')

        if not is_railway:
            _write_xml(path_to_stg, file_name, file_name)

        for the_way in cl.objects:
            the_way.junction0.reset()
            the_way.junction1.reset()


def _write_xml(path_to_stg, file_name, object_name):
    xml = open(path_to_stg + file_name + '.xml', "w")
    if parameters.TRAFFIC_SHADER_ENABLE:
        shader_str = "<inherits-from>Effects/road-high</inherits-from>"
    else:
        shader_str = "<inherits-from>roads</inherits-from>"
    xml.write(textwrap.dedent("""        <?xml version="1.0"?>
        <PropertyList>
        <path>%s.ac</path>
        <effect>
        <!--
            EITHER enable the traffic shader
                <inherits-from>Effects/road-high</inherits-from>
            OR the lightmap shader
                <inherits-from>roads</inherits-from>
        -->
                %s
                <object-name>%s</object-name>
        </effect>
        </PropertyList>
    """ % (file_name, shader_str, object_name)))


def debug_create_eps(roads, clusters, elev, plot_cluster_borders=0):
    """debug: plot roads map to .eps"""
    if not parameters.DEBUG_PLOT:
        return
    plt.clf()
    transform = tools.transform
    if 0:
        c = np.array([[elev.min.x, elev.min.y], 
                      [elev.max.x, elev.min.y], 
                      [elev.max.x, elev.max.y], 
                      [elev.min.x, elev.max.y],
                      [elev.min.x, elev.min.y]])
        #c = np.array([transform.toGlobal(p) for p in c])
        plt.plot(c[:, 0], c[:, 1], 'r-', label="elev")

    col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k', 'c']
    col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
    lw = [1, 1, 1, 1.2, 1.5, 2, 1]
    lw_w = np.array([1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]) * 0.1

    if 1:
        for i, cl in enumerate(clusters):
            if plot_cluster_borders and len(cl.objects): 
                cluster_color = col[random.randint(0, len(col)-1)]
                c = np.array([[cl.min.x, cl.min.y], 
                              [cl.max.x, cl.min.y], 
                              [cl.max.x, cl.max.y], 
                              [cl.min.x, cl.max.y],
                              [cl.min.x, cl.min.y]])
                c = np.array([transform.toGlobal(p) for p in c])
                plt.plot(c[:, 0], c[:, 1], '-', color=cluster_color)
            for r in cl.objects:
                random_color = col[random.randint(0, len(col)-1)]
                osmid_color = col[(r.osm_id + len(r.refs)) % len(col)]                
                a = np.array(r.center.coords)
                a = np.array([transform.toGlobal(p) for p in a])
                #color = col[r.typ]
                try:
                    lw = lw_w[r.typ]
                except:
                    lw = lw_w[0]
                    
                plt.plot(a[:, 0], a[:, 1], color=cluster_color, linewidth=lw)

    plt.axes().set_aspect('equal')
    plt.legend()
    plt.savefig('roads.eps')
    plt.clf()


def process():
    random.seed(42)
    parser = argparse.ArgumentParser(description="roads.py reads OSM data and creates road, railway and bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-e", dest="e", action="store_true",
                        help="skip elevation interpolation", required=False)
    parser.add_argument("-b", "--bridges-only", action="store_true",
                        help="create only bridges and embankments", required=False)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL", required=False)

    args = parser.parse_args()
    # -- command line args override parameters
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)

    if args.e:
        parameters.NO_ELEV = True
    if args.bridges_only:
        parameters.CREATE_BRIDGES_ONLY = True
    parameters.show()

    center_global = parameters.get_center_global()
    coords_transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(coords_transform)

    if not parameters.USE_DATABASE:
        osm_way_result = osmparser.fetch_osm_file_data(['highway', 'railway', "tunnel", "bridge", "gauge", "access"],
                                                       ['highway', 'railway'])
    else:
        osm_way_result = osmparser.fetch_osm_db_data_ways_keys(["highway", "railway"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    clipping_border = None
    if parameters.BOUNDARY_CLIPPING_COMPLETE_WAYS:
        clipping_border = shg.Polygon(parameters.get_clipping_extent(False))

    # get blocked areas from apt.dat airport data
    blocked_areas = aptdat_io.get_apt_dat_blocked_areas(coords_transform,
                                                        parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                        parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)

    filtered_osm_ways_list = process_osm_ways(osm_nodes_dict, osm_ways_dict, clipping_border)
    logging.info("ways: %i", len(filtered_osm_ways_list))
    if len(filtered_osm_ways_list) == 0:
        logging.info("No roads and railways found -> aborting")
        return

    fg_elev = utilities.FGElev(coords_transform, fake=parameters.NO_ELEV)
    roads = Roads(filtered_osm_ways_list, osm_nodes_dict, coords_transform, fg_elev)

    path_to_output = parameters.get_output_path()
    logging.debug("before linear " + str(roads))

    roads.process(blocked_areas)  # does the heavy lifting based on OSM data including clustering

    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)

    # -- write stg
    stg_paths = set()

    _process_clusters(roads.railways_clusters, replacement_prefix, fg_elev, stg_manager, stg_paths, True)
    _process_clusters(roads.roads_clusters, replacement_prefix, fg_elev, stg_manager, stg_paths, False)

    roads.debug_plot(show=True, plot_junctions=False, clusters=roads.roads_clusters)
    
    debug_create_eps(roads, roads.roads_clusters, fg_elev, plot_cluster_borders=1)
    stg_manager.write()

    utilities.troubleshoot(tools.stats)
    logging.info('Done.')
    logging.debug("final " + str(roads))

if __name__ == "__main__":
    process()
