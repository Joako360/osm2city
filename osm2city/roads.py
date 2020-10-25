"""

Created on Sun Sep 29 10:42:12 2013

@author: tom

Data structures
---------------


nodes_dict: contains all op.Nodes, by OSM_ID
  nodes_dict[OSM_ID] -> Node
  KEEP, because we have a lot more nodes than junctions.
  
Roads.G: graph
  its nodes represent junctions. Indexed by OSM_ID of op.Nodes
  edges represent roads between junctions, and have obj=op.Way
  self.G[ref_1][ref_2]['obj'] -> op.Way

attached_ways_dict: for each (true) junction node, store a list of tuples (attached linear_obj, is_first)
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
        - store end nodes index in linear_obj
        - linear_obj does not write end node coords, central method does it
      write junction face

Splitting:
  find all junctions for the_way
  normally a linear_obj would have exactly two junctions (at the ends)
  sort junctions in linear_obj's node order:
    add junction node index to dict
    sort list
  split into njunctions-1 ways
Now each linear_obj's end node is either junction or dead-end.

Joining:

required graph functions:
- find neighbours
-
"""

from collections import OrderedDict
import enum
import logging
import math
import multiprocessing as mp
from operator import itemgetter
import os
import random
from typing import Dict, List, MutableMapping, Optional, Tuple
import unittest

import matplotlib.pyplot as plt
import numpy as np
import shapely.geometry as shg

from osm2city import linear, parameters
from osm2city.cluster import ClusterContainer
import osm2city.textures.road
import osm2city.utils.osmparser as op
from osm2city.utils import utilities, ac3d, graph, coordinates, stg_io2
from osm2city.types import osmstrings as s
from osm2city.utils.vec2d import Vec2d

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark our edits


def is_tunnel(tags: Dict[str, str]) -> bool:
    return s.K_TUNNEL in tags and tags[s.K_TUNNEL] not in [s.V_NO]


# specifies a linear_obj that was originally a bridge, but due to length was changed
REPLACED_BRIDGE_KEY = 'replaced_bridge'


def _is_bridge(tags: Dict[str, str]) -> bool:
    """Returns true if the tags for this linear_obj contains the OSM key for bridge."""
    if s.K_MAN_MADE in tags and tags[s.K_MAN_MADE] == s.V_BRIDGE:
        return True
    if s.K_BRIDGE in tags and tags not in [s.V_NO]:
        return True
    return False


def _replace_bridge_tags(tags: Dict[str, str]) -> None:
    if s.K_BRIDGE in tags:
        tags.pop(s.K_BRIDGE)
    if s.K_MAN_MADE in tags and tags[s.K_MAN_MADE] == s.V_BRIDGE:
        tags.pop(s.K_MAN_MADE)
    tags[REPLACED_BRIDGE_KEY] = s.V_YES


def _is_replaced_bridge(tags: Dict[str, str]) -> bool:
    """Returns true is this linear_obj was originally a bridge, but was changed to a non-bridge due to length.
    See method Roads._replace_short_bridges_with_ways.
    The reason to keep a replaced_tag is because else the linear_obj might be split if a node is in the water."""
    return REPLACED_BRIDGE_KEY in tags


def _is_lit(tags: Dict[str, str]) -> bool:
    if s.K_LIT in tags and tags[s.K_LIT] == s.V_YES:
        return True
    return False


def _is_highway(way: op.Way) -> bool:
    return s.K_HIGHWAY in way.tags


def is_railway(way: op.Way) -> bool:
    return s.K_RAILWAY in way.tags


def _compatible_ways(way1: op.Way, way2: op.Way) -> bool:
    """Returns True if both ways are either a railway, a bridge or a highway - and have common type attributes"""
    logging.debug("trying join %i %i", way1.osm_id, way2.osm_id)
    if is_railway(way1) != is_railway(way2):
        logging.debug("Nope, either both or none must be railway")
        return False
    elif _is_bridge(way1.tags) != _is_bridge(way2.tags):
        logging.debug("Nope, either both or none must be a bridge")
        return False
    elif _is_highway(way1) != _is_highway(way2):
        logging.debug("Nope, either both or none must be a highway")
        return False
    elif _is_highway(way1) and _is_highway(way2):
        # check type
        if highway_type_from_osm_tags(way1.tags) != highway_type_from_osm_tags(way2.tags):
            logging.debug("Nope, both must be of same highway type")
            return False
        # check lit
        if _is_lit(way1.tags) != _is_lit(way2.tags):
            logging.debug("Nope, both must be lit or not")
            return False
    elif is_railway(way1) and is_railway(way2):
        if railway_type_from_osm_tags(way1.tags) != railway_type_from_osm_tags(way2.tags):
            logging.debug("Nope, both must be of same railway type")
            return False
        # check electrified
        if is_electrified_railway(way1.tags) != is_electrified_railway(way2.tags):
            logging.debug("Nope, both must be electrified or not")
            return False
    return True


def _init_way_from_existing(way: op.Way, node_references: List[int]) -> op.Way:
    """Return copy of linear_obj. The copy will have same osm_id and tags, but only given refs"""
    new_way = op.Way(op.get_next_pseudo_osm_id(op.OSMFeatureType.road))
    new_way.pseudo_osm_id = way.osm_id
    new_way.tags = way.tags.copy()
    new_way.refs = node_references
    return new_way


def _has_duplicate_nodes(refs):
    for i, r in enumerate(refs):
        if r in refs[i+1:]:
            return True


def _calc_railway_gauge(tags: Dict[str, str]) -> float:
    """Based on railway tags determine the width in meters (3.18 meters for normal gauge)."""
    width = 1435  # millimeters
    if tags[s.K_RAILWAY] in [s.V_NARROW_GAUGE]:
        width = 1000
    if s.K_GAUGE in tags:
        if op.is_parsable_float(tags[s.K_GAUGE]):
            width = float(tags[s.K_GAUGE])
    return width / 1000 * 126 / 57  # in the texture roads.png the track uses 57 out of 126 pixels


def is_electrified_railway(tags: Dict[str, str]) -> bool:
    if s.K_ELECTRIFIED in tags and tags[s.K_ELECTRIFIED] in [s.V_CONTACT_LINE, s.V_YES]:
        return True
    return False


@enum.unique
class RailwayType(enum.IntEnum):
    normal = 5
    narrow = 3
    light = 1


def _get_railway_attributes(railway_type: RailwayType, tags: Dict[str, str]) -> Tuple[Tuple[float, float], float]:
    if railway_type is RailwayType.normal:
        tex = osm2city.textures.road.TRACK
    elif railway_type is RailwayType.narrow:
        tex = osm2city.textures.road.TRACK  # FIXME: should use proper narrow texture
    else:
        tex = osm2city.textures.road.TRAMWAY
    return tex, _calc_railway_gauge(tags)


def railway_type_from_osm_tags(tags: Dict[str, str]) -> Optional[RailwayType]:
    """Based on OSM tags deducts the RailwayType.
    Returns None if not a highway are unknown value.
    """
    if s.K_RAILWAY in tags:
        value = tags[s.K_RAILWAY]
    else:
        return None

    if value in [s.V_RAIL, s.V_DISUSED, s.V_PRESERVED, s.V_SUBWAY]:
        # disused != abandoned cf. https://wiki.openstreetmap.org/wiki/Key:abandoned:
        return RailwayType.normal
    elif value in [s.V_NARROW_GAUGE]:
        return RailwayType.narrow
    elif value in [s.V_LIGHT_RAIL]:
        return RailwayType.light
    elif parameters.USE_TRAM_LINES and value == s.V_TRAM:
        return RailwayType.light
    else:
        return None


@enum.unique
class HighwayType(enum.IntEnum):
    roundabout = 13
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


def get_highway_attributes(highway_type: HighwayType) -> Tuple[Tuple[float, float], float]:
    """This must be aligned with HighwayType as well as textures.road and Roads.create_linear_objects."""
    if highway_type is HighwayType.roundabout:
        tex = osm2city.textures.road.ROAD_1
        width = 6.
    elif highway_type is HighwayType.motorway:
        tex = osm2city.textures.road.ROAD_3
        width = 6.
    elif highway_type in [HighwayType.primary, HighwayType.trunk]:
        tex = osm2city.textures.road.ROAD_2
        width = 6.
    elif highway_type in [HighwayType.secondary]:
        tex = osm2city.textures.road.ROAD_2
        width = 6.
    elif highway_type in [HighwayType.tertiary, HighwayType.unclassified, HighwayType.road]:
        tex = osm2city.textures.road.ROAD_1
        width = 6.
    elif highway_type in [HighwayType.residential, HighwayType.service]:
        tex = osm2city.textures.road.ROAD_1
        width = 4.
    else:
        tex = osm2city.textures.road.ROAD_1
        width = 4.
    return tex, width


def highway_type_from_osm_tags(tags: Dict[str, str]) -> Optional[HighwayType]:
    """Based on OSM tags deducts the HighwayType.
    Returns None if not a highway are unknown value.
    """
    if s.K_HIGHWAY in tags:
        value = tags[s.K_HIGHWAY]
    else:
        return None

    if s.K_JUNCTION in tags and tags[s.K_JUNCTION] in [s.V_ROUNDABOUT, s.V_CIRCULAR]:
        return HighwayType.roundabout

    if value in [s.V_MOTORWAY]:
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
    if s.K_HIGHWAY in obj.way.tags:
        if obj.way.tags[s.K_HIGHWAY] in [s.V_MOTORWAY]:
            return parameters.MAX_SLOPE_MOTORWAY
        else:
            return parameters.MAX_SLOPE_ROAD
    # must be aligned with accepted railways in Roads._create_linear_objects
    elif s.K_RAILWAY in obj.way.tags:
        return parameters.MAX_SLOPE_RAILWAY


def _find_junctions(attached_ways_dict: Dict[int, List[Tuple[op.Way, bool]]],
                    ways_list: List[op.Way]) -> None:
    """Finds nodes, which are shared by at least 2 ways at the start or end of the linear_obj.

    The node may only be referenced one, otherwise unclear how to join (e.g. circular)
    """
    logging.info('Finding junctions...')
    for the_way in ways_list:
        start_ref = the_way.refs[0]
        if the_way.refs.count(start_ref) == 1:  # check only once in list
            _attached_ways_dict_append(attached_ways_dict, start_ref, the_way, True)
        end_ref = the_way.refs[-1]
        if the_way.refs.count(end_ref) == 1:
            _attached_ways_dict_append(attached_ways_dict, end_ref, the_way, False)


def _attached_ways_dict_remove(attached_ways_dict: Dict[int, List[Tuple[op.Way, bool]]], the_ref: int,
                               the_way: op.Way, is_start: bool) -> None:
    """Remove given linear_obj from given node in attached_ways_dict"""
    if the_ref not in attached_ways_dict:
        logging.warning("not removing linear_obj %i from the ref %i because the ref is not in attached_ways_dict",
                        the_way.osm_id, the_ref)
        return
    for way_pos_tuple in attached_ways_dict[the_ref]:
        if way_pos_tuple[0] == the_way and way_pos_tuple[1] is is_start:
            logging.debug("removing linear_obj %s from node %i", the_way, the_ref)
            attached_ways_dict[the_ref].remove(way_pos_tuple)
            break


def _attached_ways_dict_append(attached_ways_dict: Dict[int, List[Tuple[op.Way, bool]]], the_ref: int,
                               the_way: op.Way, is_start: bool) -> None:
    """Append given linear_obj to attached_ways_dict."""
    if the_ref not in attached_ways_dict:
        attached_ways_dict[the_ref] = list()
    attached_ways_dict[the_ref].append((the_way, is_start))


def cut_line_at_points(line: shg.LineString, points: List[shg.Point]) -> List[shg.LineString]:
    """Creates a set of new lines based on an existing line and cutting points.
    E.g. used to cut a line at intersection points with other lines / polygons.
    See https://stackoverflow.com/questions/34754777/shapely-split-linestrings-at-intersections-with-other-linestrings.
    """
    lines = list()

    # First coords of line
    coords = list(line.coords)

    # Keep list coords where to cut (cuts = 1)
    cuts = [0] * len(coords)
    cuts[0] = 1
    cuts[-1] = 1

    # Add the coords from the points
    coords += [list(p.coords)[0] for p in points]
    cuts += [1] * len(points)

    # Calculate the distance along the line for each point
    dists = [line.project(shg.Point(p)) for p in coords]

    # sort the coords/cuts based on the distances
    # see http://stackoverflow.com/questions/6618515/sorting-list-based-on-values-from-another-list
    coords = [p for (d, p) in sorted(zip(dists, coords))]
    cuts = [p for (d, p) in sorted(zip(dists, cuts))]

    for i in range(len(coords)-1):
        if cuts[i] == 1:
            # find next element in cuts == 1 starting from index i + 1
            j = cuts.index(1, i + 1)
            lines.append(shg.LineString(coords[i:j+1]))

    return lines


def check_points_on_line_distance(max_point_dist: int, ways_list: List[op.Way], nodes_dict: Dict[int, op.Node],
                                  transform: coordinates.Transformation) -> None:
    """Based on parameter makes sure that points on a line are not too long apart for elevation probing reasons.

    If distance is longer than the related parameter, then new points are added along the line.
    """
    for the_way in ways_list:
        my_new_refs = [the_way.refs[0]]
        for index in range(1, len(the_way.refs)):
            node0 = nodes_dict[the_way.refs[index - 1]]
            node1 = nodes_dict[the_way.refs[index]]
            my_line = shg.LineString([transform.to_local((node0.lon, node0.lat)),
                                      transform.to_local((node1.lon, node1.lat))])
            if my_line.length <= max_point_dist:
                my_new_refs.append(the_way.refs[index])
                continue
            else:
                additional_needed_nodes = int(my_line.length / max_point_dist)
                for x in range(additional_needed_nodes):
                    new_point = my_line.interpolate((x + 1) * max_point_dist)
                    osm_id = op.get_next_pseudo_osm_id(op.OSMFeatureType.road)
                    lon_lat = transform.to_global((new_point.x, new_point.y))
                    new_node = op.Node(osm_id, lon_lat[1], lon_lat[0])
                    nodes_dict[osm_id] = new_node
                    my_new_refs.append(osm_id)
                my_new_refs.append(the_way.refs[index])

        the_way.refs = my_new_refs


class WaySegment:
    """A segment of a linear_obj as a temporary storage to process nodes attributes for layers"""
    __slots__ = ('way', 'start_layer', 'end_layer', 'nodes')

    def __init__(self, way: op.Way) -> None:
        self.way = way
        self.nodes = list()

    def add_node(self, node: op.Node) -> None:
        self.nodes.append(node)

    @property
    def number_of_nodes(self) -> int:
        return len(self.nodes)

    @staticmethod
    def split_way_into_way_segments(way: op.Way, nodes_dict: Dict[int, op.Node]) -> List['WaySegment']:
        """Split is only done when a node has a layer for the specific linear_obj.

        A segment can start and/or stop at a node, which does not have a layer attribute."""
        segments = list()
        the_segment = WaySegment(way)
        the_segment.add_node(nodes_dict[way.refs[0]])
        for i in range(1, len(way.refs)):
            next_node = nodes_dict[way.refs[i]]
            the_segment.add_node(next_node)
            if the_segment.number_of_nodes == 2:
                segments.append(the_segment)
            if the_segment.number_of_nodes > 1 and next_node.layer_for_way(way) >= 0:
                the_segment = WaySegment(way)
                the_segment.add_node(next_node)
        return segments

    def calc_missing_layers_for_nodes(self) -> None:
        """Make sure each node of the segment gets a layer for the linear_obj assigned.

        Unless none of the nodes has a node with a layer at start or end (i.e. a Way in osm2city disconnected from
        other ways.
        If there is no end or start layer, then all nodes take over from the one node with a layer.
        If there is both an end and a start layer, then it is distributed half/half.
        We do NOT gradually go from e.g. layer 5 to e.g. 2, because if two ways follow each other in a shallow
        angle (e.g. junction to motorway), we want to avoid z-fighting as much as possible."""
        start_layer = self.nodes[0].layer_for_way(self.way)
        end_layer = self.nodes[-1].layer_for_way(self.way)
        if start_layer < 0 and end_layer < 0:
            start_layer = 0
            end_layer = 0
        elif start_layer < 0:
            start_layer = end_layer
        elif end_layer < 0:
            end_layer = start_layer

        switch_point = int(len(self.nodes) / 2 + 0.5) - 1
        layer = start_layer
        for i in range(0, len(self.nodes)):
            if i > switch_point:
                layer = end_layer
            self.nodes[i].layers[self.way] = layer


class Roads(object):
    def __init__(self, raw_osm_ways: List[op.Way], nodes_dict: Dict[int, op.Node],
                 coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev) -> None:
        self.transform = coords_transform
        self.fg_elev = fg_elev
        self.ways_list = raw_osm_ways  # raw ways from OSM
        self.bridges_list = list()
        self.railway_list = list()
        self.roads_list = list()
        self.nodes_dict = nodes_dict
        self.G = None  # network graph of ways
        self.roads_clusters = None
        self.roads_rough_clusters = None
        self.railways_clusters = None

    def __str__(self):
        return "%i ways, %i roads, %i railways, %i bridges" % (len(self.ways_list), len(self.roads_list),
                                                               len(self.railway_list), len(self.bridges_list))

    def _check_ways_sanity(self, prev_method_name: str) -> None:
        """Makes sure all ways have at least 2 nodes.
        If one is found with less nodes, it is discarded. Should not happen, but does."""
        num_removed = 0
        for way in reversed(self.ways_list):
            if len(way.refs) < 2:
                logging.warning('Removing linear_obj with osm_id=%i due to only %i nodes after "%s"',
                                way.osm_id, len(way.refs), prev_method_name)
                self.ways_list.remove(way)
                num_removed += 1
        if num_removed > 0:
            logging.info('Removed %i ways due to only 1 node after "%s"', num_removed, prev_method_name)
        else:
            logging.info('No ways with only one node after "%s"', prev_method_name)

    def process(self, blocked_areas: List[shg.Polygon],
                lit_areas: List[shg.Polygon], water_areas: List[shg.Polygon],
                stats: utilities.Stats) -> None:
        """Processes the OSM data until data can be clusterised."""
        self._remove_tunnels()
        self._replace_short_bridges_with_ways()
        self._check_against_blocked_areas(water_areas, True)
        self._check_ways_sanity('_check_against_blocked_areas_water')
        self._check_against_blocked_areas(blocked_areas)
        self._check_ways_sanity('_check_against_blocked_areas')

        self._remove_short_way_segments()
        self._check_ways_sanity('_remove_short_way_segments')
        self._cleanup_topology()
        check_points_on_line_distance(parameters.POINTS_ON_LINE_DISTANCE_MAX, self.ways_list, self.nodes_dict,
                                      self.transform)

        self._remove_unused_nodes()
        self._probe_elev_at_nodes()

        # -- no change in topology beyond create_linear_objects() !
        logging.debug("before linear " + str(self))
        self._calculate_way_layers_at_node()
        self._calculate_way_layers_all_nodes()
        self._create_linear_objects(lit_areas)
        self._propagate_v_add()
        logging.debug("after linear " + str(self))

        if parameters.CREATE_BRIDGES_ONLY:
            self._keep_only_bridges_and_embankments()

        self._clusterize(stats)

    def _check_against_blocked_areas(self, blocked_areas: List[shg.Polygon], is_water: bool = False) -> None:
        """Makes sure that there are no ways, which go across a blocked area (e.g. airport runway).
        Ways are clipped over into two ways if intersecting. If they are contained, then they are removed."""
        if not blocked_areas:
            return

        # Need to be absolutely sure that overlapping blocked areas have been merged.
        # Otherwise for some reason the algorithm re-creates ways when tested against overlapping areas.
        merged_areas = utilities.merge_buffers(blocked_areas)
        if parameters.DEBUG_PLOT_BLOCKED_AREAS_ROADS and is_water is False:
            line_strings = list()
            for way in self.ways_list:
                if way.osm_id in parameters.DEBUG_PLOT_BLOCKED_AREAS_ROADS:
                    line_strings.append(self._line_string_from_way(way))
            utilities.plot_blocked_areas_roads(merged_areas, line_strings, self.transform)

        new_ways = list()
        for way in reversed(self.ways_list):
            if is_water and (_is_bridge(way.tags) or _is_replaced_bridge(way.tags)):
                new_ways.append(way)
                continue
            my_list = [way]
            continue_loop = True
            while continue_loop and my_list:
                continue_loop = False  # only set to true if something changed
                continue_intersect = True
                for a_way in reversed(my_list):
                    my_line = self._line_string_from_way(a_way)
                    for blocked_area in merged_areas:
                        if my_line.within(blocked_area):
                            my_list.remove(a_way)
                            logging.debug('removed %d because within', a_way.osm_id)
                            continue_intersect = False
                            continue_loop = True
                            break
                    if continue_intersect:
                        for blocked_area in merged_areas:
                            if my_line.intersects(blocked_area):
                                my_line_difference = my_line.difference(blocked_area)
                                length_diff = my_line.length - my_line_difference.length
                                if isinstance(my_line_difference, shg.LineString) and \
                                        length_diff > parameters.TOLERANCE_MATCH_NODE:
                                    if my_line_difference.length < parameters.OVERLAP_CHECK_ROAD_MIN_REMAINING:
                                        my_list.remove(a_way)
                                        logging.debug('removed %d because too short', a_way.osm_id)
                                    else:
                                        self._change_way_for_object(my_line_difference, a_way)
                                        logging.debug('reduced %d', a_way.osm_id)
                                    continue_loop = True
                                    break
                                elif isinstance(my_line_difference, shg.MultiLineString):
                                    split_ways = self._split_way_for_object(my_line_difference, a_way)
                                    if len(split_ways) > 0:
                                        for split_way in split_ways:
                                            my_list.append(split_way)
                                        logging.debug('split %d into %d ways', a_way.osm_id, len(split_ways) + 1)
                                    else:
                                        my_list.remove(a_way)
                                        continue_loop = True
                                        break
            if my_list:
                new_ways.extend(my_list)

        self.ways_list = new_ways

    def cut_way_at_intersection_points(self, intersection_points: List[shg.Point], way: op.Way,
                                       my_line: shg.LineString) -> MutableMapping[op.Way, float]:
        """Cuts an existing linear_obj into several parts based in intersection points given as a parameter.
        Returns an OrderedDict of Ways, where the first element is always the (changed) original linear_obj, such
        that the distance from start to intersection is clear.
        Cutting also checks that the potential new cut ways have a minimum distance based on 
        parameters.BUILT_UP_AREA_LIT_BUFFER, such that the splitting is not too tiny. This can lead to that
        an original linear_obj just keeps its original length despite one or several intersection points.
        Distance in the returned dictionary refers to the last point's distance along the original linear_obj, which
        is e.g. the length of the original linear_obj for the last cut linear_obj."""
        intersect_dict = dict()  # osm_id for node, distance from start
        cut_ways_dict = OrderedDict()  # key: linear_obj, value: distance of end from start of original linear_obj
        # create new global nodes
        for point in intersection_points:
            distance = my_line.project(point)
            lon, lat = self.transform.to_global((point.x, point.y))

            # make sure that the new node is relevant and not just a rounding residual
            add_intersection = True
            refs_to_remove = set()
            for ref in way.refs:
                ref_node = self.nodes_dict[ref]
                segment_length = coordinates.calc_distance_global(lon, lat, ref_node.lon, ref_node.lat)
                if segment_length < parameters.MIN_ROAD_SEGMENT_LENGTH:
                    if ref == way.refs[0] or ref == way.refs[-1]:  # ignore because it is almost at either start or end
                        add_intersection = False
                        break
                    else:  # tweak so it can be used as intersection, but based on existing point
                        add_intersection = False
                        refs_to_remove.add(ref)
                        intersect_dict[ref] = distance
                        my_line = self._line_string_from_way(way)
                        break

            for ref in refs_to_remove:
                way.refs.remove(ref)

            if add_intersection:
                new_node = op.Node(op.get_next_pseudo_osm_id(op.OSMFeatureType.road), lat, lon)
                self.nodes_dict[new_node.osm_id] = new_node
                intersect_dict[new_node.osm_id] = distance

        # create lines based on old and new points
        original_refs = way.refs[:]
        coords = list(my_line.coords)
        prev_orig_point_dist = 0
        is_first = True
        current_way_refs = list()
        new_way = None
        ordered_intersect_dict = OrderedDict(sorted(intersect_dict.items(), key=lambda t: t[1]))
        for next_index in range(len(coords) - 1):
            current_way_refs.append(original_refs[next_index])
            next_orig_point_dist = my_line.project(shg.Point(coords[next_index + 1]))
            intersects_to_remove = list()  # osm_id
            for key, distance in ordered_intersect_dict.items():
                if prev_orig_point_dist < distance < next_orig_point_dist:
                    intersects_to_remove.append(key)
                    # check minimal distance of linear_obj pieces
                    if (distance - prev_orig_point_dist) < parameters.OWBB_BUILT_UP_BUFFER:
                        continue
                    # make cut
                    current_way_refs.append(key)
                    if is_first:
                        is_first = False
                        way.refs = current_way_refs.copy()
                        new_way = way  # needed to have reference for closing last node below
                    else:
                        new_way = op.Way(op.get_next_pseudo_osm_id(op.OSMFeatureType.road))
                        new_way.pseudo_osm_id = way.osm_id
                        new_way.tags = way.tags.copy()
                        new_way.refs = current_way_refs.copy()
                    middle_distance = distance - (distance - prev_orig_point_dist) / 2
                    cut_ways_dict[new_way] = middle_distance

                    # restart current_way_refs with found cut point as new starting
                    current_way_refs = [key]
                    prev_orig_point_dist = distance

            # remove not needed intersection points
            for key in intersects_to_remove:
                del ordered_intersect_dict[key]

        # close the last node
        if is_first:  # maybe the intersection points were all below minimal distance -> nothing to do
            cut_ways_dict[way] = my_line.length / 2
        else:
            # check minimal distance of linear_obj pieces
            if (my_line.length - prev_orig_point_dist) < parameters.OWBB_BUILT_UP_BUFFER:
                # instead of new cut linear_obj extend the last cut linear_obj, but do not change its middle_distance
                # last cut_way is still "new_way", because we are not is_first
                new_way.refs.append(original_refs[-1])
            else:
                new_way = op.Way(op.get_next_pseudo_osm_id(op.OSMFeatureType.road))
                new_way.pseudo_osm_id = way.osm_id
                new_way.tags = way.tags.copy()
                new_way.refs = current_way_refs.copy()
                new_way.refs.append(original_refs[-1])
                cut_ways_dict[new_way] = my_line.length - (my_line.length - prev_orig_point_dist) / 2

        logging.debug('{} new cut ways (not including orig linear_obj) from {} intersections'.format(
            len(cut_ways_dict) - 1, len(intersection_points)))
        return cut_ways_dict

    def _change_way_for_object(self, my_line: shg.LineString, original_way: op.Way) -> None:
        """Processes an original linear_obj and replaces its coordinates with the coordinates of a LineString."""
        prev_refs = original_way.refs[:]
        the_coordinates = list(my_line.coords)
        original_way.refs = utilities.match_local_coords_with_global_nodes(the_coordinates, prev_refs, self.nodes_dict,
                                                                           self.transform, original_way.osm_id, True)

    def _split_way_for_object(self, my_multiline: shg.MultiLineString, original_way: op.Way) -> List[op.Way]:
        """Processes an original linear_obj split by an object (blocked area, stg_entry) and creates additional
        linear_obj.
        If one of the line strings is shorter than parameter, then it is discarded to reduce the number of residuals.
        The list of returned ways can be empty, in which case the original linear_obj should be removed after the call.
        """
        is_first = True
        additional_ways = list()
        prev_refs = original_way.refs[:]
        for line in my_multiline.geoms:
            if line.length > parameters.OVERLAP_CHECK_ROAD_MIN_REMAINING:
                the_coordinates = list(line.coords)
                new_refs = utilities.match_local_coords_with_global_nodes(the_coordinates, prev_refs, self.nodes_dict,
                                                                          self.transform, original_way.osm_id, True)
                if is_first:
                    is_first = False
                    original_way.refs = new_refs
                else:
                    new_way = _init_way_from_existing(original_way, list())
                    new_way.refs = new_refs
                    additional_ways.append(new_way)
        return additional_ways

    def _remove_unused_nodes(self):
        """Remove all nodes which are not used in ways in order not to do elevation probing in vane."""
        used_nodes_dict = dict()
        for way in self.ways_list:
            for ref in way.refs:
                used_nodes_dict[ref] = self.nodes_dict[ref]
        self.nodes_dict = used_nodes_dict

    def _probe_elev_at_nodes(self):
        """Add elevation info to all nodes.

        msl = meters above sea level (i.e. the elevation of the ground)
        v_add = elevation after some adjustment has been added to take care of elevation probing bumpiness.

        At the end save the cache.
        """
        for the_node in list(self.nodes_dict.values()):
            if math.isnan(the_node.lon) or math.isnan(the_node.lat):
                logging.error("NaN encountered while probing elevation")
                continue
            the_node.msl = self.fg_elev.probe_elev((the_node.lon, the_node.lat), is_global=True)
            the_node.v_add = 0.

    def _propagate_v_add_over_edge(self, ref0, ref1, args):
        """propagate v_add over edges of graph"""
        obj = self.G[ref0][ref1]['obj']
        dh_dx = max_slope_for_road(obj)
        n0 = self.nodes_dict[ref0]
        n1 = self.nodes_dict[ref1]
        if n1.v_add > 0:
            return False
            # FIXME: should we really just stop here? Probably yes.
        n1.v_add = max(0, n0.msl + n0.v_add - obj.center.length * dh_dx - n1.msl)
        if n1.v_add <= 0.:
            return False
        return True
    
    def _propagate_v_add(self):
        """start at bridges, propagate v_add through nodes"""
        for the_bridge in self.bridges_list:
            # build tree starting at node0
            node0 = the_bridge.way.refs[0]
            node1 = the_bridge.way.refs[-1]

            node0s = {node1}
            visited = {node0, node1}
            graph.for_edges_in_bfs_call(self._propagate_v_add_over_edge, None, self.G, node0s, visited)
            node0s = {node0}
            visited = {node0, node1}
            graph.for_edges_in_bfs_call(self._propagate_v_add_over_edge, None, self.G, node0s, visited)

    def _line_string_from_way(self, way: op.Way) -> shg.LineString:
        osm_nodes = [self.nodes_dict[r] for r in way.refs]
        nodes = np.array([self.transform.to_local((n.lon, n.lat)) for n in osm_nodes])
        return shg.LineString(nodes)

    def _remove_short_way_segments(self) -> None:
        """Make sure there are no almost zero length segments.

        In the tile 3088961 around Luzern in Switzerland for around 10000 ways there were 106 nodes removed.
        """
        num_refs_removed = 0
        for way in self.ways_list:
            if len(way.refs) == 2:
                continue
            refs_to_remove = list()
            ref_len = len(way.refs)
            for i in range(1, ref_len):
                first_node = self.nodes_dict[way.refs[i - 1]]
                second_node = self.nodes_dict[way.refs[i]]
                distance = coordinates.calc_distance_global(first_node.lon, first_node.lat,
                                                            second_node.lon, second_node.lat)
                if distance < parameters.MIN_ROAD_SEGMENT_LENGTH:
                    if i == ref_len - 1:
                        refs_to_remove.append(way.refs[i - 1])  # shall not remove the last node
                    else:
                        refs_to_remove.append(way.refs[i])

            for ref in refs_to_remove:
                if len(way.refs) == 2:
                    break
                if ref in way.refs:  # A hack for something that actually happens (closed linear_obj?), but should not
                    if way.refs.count(ref) > 1:
                        continue  # in seldom cases the same node might also be used several times (e.g. for an 8-form)
                    way.refs.remove(ref)
                    num_refs_removed += 1
                    logging.debug('Removing ref %d from linear_obj %d due to too short segment', ref, way.osm_id)
                else:
                    logging.warning('Removing ref %d from linear_obj %d not possible because ref not there',
                                    ref, way.osm_id)
        logging.debug('Removed %i refs in %i ways due to too short segments', num_refs_removed, len(self.ways_list))

    def _cleanup_topology(self) -> None:
        """Cleans up the topology for junctions etc."""
        logging.debug("Number of ways before cleaning topology: %i" % len(self.ways_list))

        # a dictionary with a Node id as key. Each node has one or several ways using it in a list.
        # The entry per linear_obj is a tuple of the linear_obj object as well as whether the node is at the start
        attached_ways_dict = dict()  # Dict[int, List[Tuple[op.Way, bool]]]

        # do it again, because the references and positions have changed
        _find_junctions(attached_ways_dict, self.ways_list)

        self._rejoin_ways(attached_ways_dict)

        logging.debug("Number of ways after cleaning topology: %i" % len(self.ways_list))

    def _remove_tunnels(self):
        """Remove tunnels."""
        for the_way in reversed(self.ways_list):
            if is_tunnel(the_way.tags):
                self.ways_list.remove(the_way)

    def _replace_short_bridges_with_ways(self):
        """Remove bridge tag from short bridges, making them a simple linear_obj."""
        for the_way in self.ways_list:
            if _is_bridge(the_way.tags):
                bridge = self._line_string_from_way(the_way)
                if bridge.length < parameters.BRIDGE_MIN_LENGTH:
                    _replace_bridge_tags(the_way.tags)

    def _keep_only_bridges_and_embankments(self):
        """Remove everything that is not elevated - for debugging purposes"""
        for the_way in reversed(self.roads_list):
            v_add = np.array([abs(self.nodes_dict[the_ref].v_add) for the_ref in the_way.refs])
            if v_add.sum() == 0:
                self.roads_list.remove(the_way)
                logging.debug("kick %i", the_way.osm_id)

    def _calculate_way_layers_at_node(self) -> None:
        """At each node shared between ways determine, which layer a linear_obj should belong to.

        Otherwise the different textures at a given point might be fighting in the z-layer in rendering.

        A linear_obj where the node is not at the start/end gets priority over a linear_obj, where it is at start/end.
        Then a railway gets priority over a road
        Then within a railway or road the priority is based on the value of the type
        Last a higher osm_id wins anything else equal.
        """
        # first just make sure that we have a reference for all ways
        for the_way in self.ways_list:
            for ref in the_way.refs:
                node = self.nodes_dict[ref]
                if the_way not in node.layers:  # the same node can be several times in a linear_obj
                    node.layers[the_way] = 0

        # now we need to do the sorting. If a node has none or 1 reference, then it is easy.
        # otherwise create a tuple to do the sorting (cf. https://docs.python.org/3/howto/sorting.html#key-functions)
        for key, node in self.nodes_dict.items():
            if len(node.layers) > 1:
                # build up a tuple with the relevant attributes for sorting (higher values = more priority)
                way_tuples = list()
                for the_way in node.layers.keys():
                    if key == the_way.refs[0] or key == the_way.refs[-1]:
                        between = 0
                    else:
                        between = 1
                    if _is_highway(the_way):
                        type_factor = highway_type_from_osm_tags(the_way.tags)
                    else:
                        type_factor = railway_type_from_osm_tags(the_way.tags) * 100  # 100 -> railway on top of roads
                    way_tuples.append((the_way, between, type_factor, the_way.osm_id))

                # now do the sorting in steps
                way_tuples.sort(key=itemgetter(1, 2, 3))

                # based on this we can now
                node.layers = dict()
                for i, my_tuple in enumerate(way_tuples):
                    node.layers[my_tuple[0]] = i

    def _calculate_way_layers_all_nodes(self) -> None:
        """Given the layers at intersecting nodes calculate the layers for the other nodes in all ways."""
        for the_way in self.ways_list:
            the_segments = WaySegment.split_way_into_way_segments(the_way, self.nodes_dict)
            for segment in the_segments:
                segment.calc_missing_layers_for_nodes()

    def _create_linear_objects(self, lit_areas: List[shg.Polygon]) -> None:
        """Creates the linear objects, which will be created as scenery objects.

        Not processing parking for now (the_way.tags['amenity'] in ['parking'])
        While certainly good to have, parking in OSM is not a linear feature in general.
        We'd need to add areas.
        """
        self.G = graph.Graph()

        for the_way in self.ways_list:
            if _is_highway(the_way):
                highway_type = highway_type_from_osm_tags(the_way.tags)
                # in method Roads.store_way smaller highways already got removed

                tex, width = get_highway_attributes(highway_type)

            elif is_railway(the_way):
                railway_type = railway_type_from_osm_tags(the_way.tags)
                tex, width = _get_railway_attributes(railway_type, the_way.tags)
            else:
                continue

            try:
                if _is_bridge(the_way.tags):
                    obj = linear.LinearBridge(self.transform, self.fg_elev, the_way, self.nodes_dict, lit_areas,
                                              width, tex_coords=tex)
                    self.bridges_list.append(obj)
                else:
                    obj = linear.LinearObject(self.transform, the_way, self.nodes_dict, lit_areas,
                                              width, tex_coords=tex)
                    if is_railway(the_way):
                        self.railway_list.append(obj)
                    else:
                        self.roads_list.append(obj)

                self.G.add_linear_object_edge(obj)
            except ValueError as reason:
                logging.warning("skipping OSM_ID %i: %s" % (the_way.osm_id, reason))
                continue

    def debug_plot_way(self, way, ls, lw, color=None, ends_marker='', show_label=False) -> None:
        if not parameters.DEBUG_PLOT_ROADS:
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

    def debug_label_node(self, ref, text=""):
        node = self.nodes_dict[ref]
        plt.plot(node.lon, node.lat, 'rs', mfc='None', ms=10)
        plt.text(node.lon+0.0001, node.lat, str(node.osm_id) + " h" + str(text))

    def debug_plot(self, save=False, show=False, label_nodes=None, clusters=None):
        if label_nodes is None:
            label_nodes = list()
        plt.clf()
        for ref in label_nodes:
            self.debug_label_node(ref)
        col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
        lw_w = np.array([1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]) * 0.1

        if clusters:
            cluster_color = col[0]
            for i, cl in enumerate(clusters):
                if cl.objects:
                    cluster_color = col[random.randint(0, len(col)-1)]
                    c = np.array([[cl.min.x, cl.min.y], 
                                  [cl.max.x, cl.min.y], 
                                  [cl.max.x, cl.max.y], 
                                  [cl.min.x, cl.max.y],
                                  [cl.min.x, cl.min.y]])
                    c = np.array([self.transform.to_global(p) for p in c])
                    plt.plot(c[:, 0], c[:, 1], '-', color=cluster_color)
                for r in cl.objects:
                    a = np.array(r.center.coords)
                    a = np.array([self.transform.to_global(p) for p in a])
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

    def _join_ways(self, way1: op.Way, way2: op.Way,
                   attached_ways_dict: Dict[int, List[Tuple[op.Way, bool]]]) -> None:
        """Join ways of compatible type, where way1's last node is way2's first node."""
        logging.debug("Joining %i and %i", way1.osm_id, way2.osm_id)
        if way1.osm_id == way2.osm_id:
            logging.debug("WARNING: Not joining linear_obj %i with itself", way1.osm_id)
            return
        _attached_ways_dict_remove(attached_ways_dict, way1.refs[-1], way1, False)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[0], way2, True)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[-1], way2, False)

        way1.refs.extend(way2.refs[1:])

        _attached_ways_dict_append(attached_ways_dict, way1.refs[-1], way1, False)

        try:
            self.ways_list.remove(way2)
            logging.debug("2ok")
        except ValueError:
            try:
                self.ways_list.remove(self._find_way_by_osm_id(way2.osm_id))
            except ValueError:
                logging.warning('Way with osm_id={} cannot be removed because cannot be found'.format(way2.osm_id))
            logging.debug("2not")

    def _rejoin_ways(self, attached_ways_dict: Dict[int, List[Tuple[op.Way, bool]]]) -> None:
        number_merged_ways = 0
        for ref in list(attached_ways_dict.keys()):  # dict is changed during looping, so using list of keys
            way_pos_list = attached_ways_dict[ref]
            if len(way_pos_list) < 2:
                continue

            start_dict = dict()  # dict of ways where node is start point with key=linear_obj, value=degree from north
            end_dict = dict()  # ditto for node is end point
            for way, is_start in way_pos_list:
                if is_start:
                    first_node = self.nodes_dict[way.refs[0]]
                    second_node = self.nodes_dict[way.refs[1]]
                    angle = coordinates.calc_angle_of_line_global(first_node.lon, first_node.lat,
                                                                  second_node.lon, second_node.lat,
                                                                  self.transform)
                    start_dict[way] = angle
                else:
                    first_node = self.nodes_dict[way.refs[-2]]
                    second_node = self.nodes_dict[way.refs[-1]]
                    angle = coordinates.calc_angle_of_line_global(first_node.lon, first_node.lat,
                                                                  second_node.lon, second_node.lat,
                                                                  self.transform)
                    end_dict[way] = angle

            # for each in end_dict search in start_dict the one with the closest angle and is a compatible linear_obj
            for end_way, end_angle in end_dict.items():
                if end_way.is_closed():
                    continue  # never combine ways which are closed (e.g. roundabouts)
                candidate_way = None
                candidate_angle = 999
                for start_way, start_angle in start_dict.items():
                    if start_way.is_closed():
                        continue
                    if _compatible_ways(end_way, start_way):
                        if abs(start_angle - end_angle) >= 90:
                            continue  # larger angles lead to strange visuals
                        if candidate_way is None:
                            candidate_way = start_way
                            candidate_angle = start_angle
                        elif abs(candidate_angle - end_angle) > abs(start_angle - end_angle):
                            candidate_way = start_way
                            candidate_angle = start_angle

                if candidate_way is not None:
                    self._join_ways(end_way, candidate_way, attached_ways_dict)
                    del start_dict[candidate_way]
                    number_merged_ways += 1
                    logging.debug('Merging at %i ways %i and %i', ref, end_way.osm_id, candidate_way.osm_id)

        logging.info('Merged %i ways', number_merged_ways)

    def _find_way_by_osm_id(self, osm_id):
        for the_way in self.ways_list:
            if the_way.osm_id == osm_id:
                return the_way
        raise ValueError("linear_obj %i not found" % osm_id)

    def _clusterize(self, stats: utilities.Stats):
        """Create cluster.
           Put objects in clusters based on their centroid.
        """
        lmin, lmax = [Vec2d(self.transform.to_local(c)) for c in parameters.get_extent_global()]
        self.roads_clusters = ClusterContainer(lmin, lmax)
        self.roads_rough_clusters = ClusterContainer(lmin, lmax)
        self.railways_clusters = ClusterContainer(lmin, lmax)

        for the_object in self.bridges_list + self.roads_list + self.railway_list:
            if is_railway(the_object.way):
                cluster_ref = self.railways_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                            the_object, stats)
            else:
                if _is_highway(the_object.way):
                    if highway_type_from_osm_tags(the_object.way.tags).value < parameters.HIGHWAY_TYPE_MIN_ROUGH_LOD:
                        cluster_ref = self.roads_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                                 the_object, stats)
                    else:
                        cluster_ref = self.roads_rough_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                                       the_object, stats)
                else:
                    cluster_ref = self.roads_clusters.append(Vec2d(the_object.center.centroid.coords[0]), the_object,
                                                             stats)
            the_object.cluster_ref = cluster_ref


def _process_osm_ways(nodes_dict: Dict[int, op.Node], ways_dict: Dict[int, op.Way]) -> List[op.Way]:
    """Processes the values returned from OSM and does a bit of filtering.
    Transformation to roads, railways and bridges is only done later in Roads.process()."""
    my_ways = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if way.osm_id in parameters.SKIP_LIST:
            logging.debug("SKIPPING OSM_ID %i", way.osm_id)
            continue

        if _is_highway(way):
            highway_type = highway_type_from_osm_tags(way.tags)
            if highway_type is None:
                continue
            elif highway_type.value < parameters.HIGHWAY_TYPE_MIN:
                continue
        elif is_railway(way):
            railway_type = railway_type_from_osm_tags(way.tags)
            if railway_type is None:
                continue

        split_ways = op.split_way_at_boundary(nodes_dict, way, clipping_border, op.OSMFeatureType.road)
        if split_ways:
            my_ways.extend(split_ways)

    return my_ways


def _process_clusters(clusters, fg_elev: utilities.FGElev,
                      stg_manager, stg_paths, do_railway,
                      coords_transform: coordinates.Transformation, stats: utilities.Stats, is_rough_lod: bool) -> None:
    for cl in clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS:
            continue  # skip almost empty clusters

        if do_railway:
            file_start = "railways"
        else:
            file_start = "roads"
        if is_rough_lod:
            file_start += "_rough"
        file_name = parameters.PREFIX + file_start + "%02i%02i" % (cl.grid_index.ix, cl.grid_index.iy)
        center_global = Vec2d(coords_transform.to_global(cl.center))
        offset_local = cl.center
        cluster_elev = fg_elev.probe_elev((center_global.lon, center_global.lat), True)

        # -- Now write cluster to disk.
        #    First create ac object. Write cluster's objects. Register stg object.
        #    Write ac to file.
        ac = ac3d.File(stats=stats, show_labels=True)
        ac3d_obj = ac.new_object(file_name, 'Textures/osm2city/roads.png',
                                 default_swap_uv=True, default_mat_idx=ac3d.MAT_IDX_UNLIT)
        for rd in cl.objects:
            rd.write_to(ac3d_obj, fg_elev, cluster_elev, offset=offset_local)

        if do_railway:
            stg_verb_type = stg_io2.STGVerbType.object_railway_detailed
        else:
            stg_verb_type = stg_io2.STGVerbType.object_road_detailed
        if is_rough_lod:
            if do_railway:
                stg_verb_type = stg_io2.STGVerbType.object_railway_rough
            else:
                stg_verb_type = stg_io2.STGVerbType.object_road_rough
        path_to_stg = stg_manager.add_object_static(file_name + '.ac', center_global, cluster_elev, 0,
                                                    stg_verb_type)
        stg_paths.add(path_to_stg)
        ac.write(os.path.join(path_to_stg, file_name + '.ac'))

        for the_way in cl.objects:
            the_way.junction0.reset()
            the_way.junction1.reset()


def process_roads(transform: coordinates.Transformation, fg_elev: utilities.FGElev,
                  blocked_apt_areas: List[shg.Polygon], lit_areas: List[shg.Polygon], water_areas: List[shg.Polygon],
                  stg_entries: List[stg_io2.STGEntry], file_lock: mp.Lock = None) -> None:
    random.seed(42)
    stats = utilities.Stats()

    osm_way_result = op.fetch_osm_db_data_ways_keys([s.K_HIGHWAY, s.K_RAILWAY])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    # OSM APRONS
    if parameters.OVERLAP_CHECK_APT_USE_OSM_APRON_ROADS:
        osm_result = op.fetch_osm_db_data_ways_key_values([op.create_key_value_pair(s.K_AEROWAY, s.V_APRON)])
        for way in list(osm_result.ways_dict.values()):
            my_geometry = way.polygon_from_osm_way(osm_result.nodes_dict, transform)
            blocked_apt_areas.append(my_geometry)

    # add STGEntries to the blocked area mix
    extended_blocked_areas = stg_io2.merge_stg_entries_with_blocked_areas(stg_entries, blocked_apt_areas)

    logging.info("Number of ways before basic processing: %i", len(osm_ways_dict))
    filtered_osm_ways_list = _process_osm_ways(osm_nodes_dict, osm_ways_dict)
    logging.info("Number of ways after basic processing: %i", len(filtered_osm_ways_list))
    if not filtered_osm_ways_list:
        logging.info("No roads and railways found -> aborting")
        return

    roads = Roads(filtered_osm_ways_list, osm_nodes_dict, transform, fg_elev)

    path_to_output = parameters.get_output_path()

    roads.process(extended_blocked_areas, lit_areas, water_areas, stats)  # does the heavy lifting incl. clustering

    stg_manager = stg_io2.STGManager(path_to_output, stg_io2.SceneryType.roads, OUR_MAGIC, parameters.PREFIX)

    # -- write stg
    stg_paths = set()

    _process_clusters(roads.railways_clusters, fg_elev, stg_manager, stg_paths, True,
                      transform, stats, True)
    _process_clusters(roads.roads_clusters, fg_elev, stg_manager, stg_paths, False,
                      transform, stats, False)
    _process_clusters(roads.roads_rough_clusters, fg_elev, stg_manager, stg_paths, False,
                      transform, stats, True)

    if parameters.DEBUG_PLOT_ROADS:
        roads.debug_plot(show=True, clusters=roads.roads_clusters)

    stg_manager.write(file_lock)

    utilities.troubleshoot(stats)


# ================ UNITTESTS =======================

class TestUtilities(unittest.TestCase):
    def test_cut_way_at_intersection_points(self):
        raw_osm_ways = list()
        nodes_dict = dict()
        coords_transform = coordinates.Transformation(parameters.get_center_global())
        the_fg_elev = utilities.FGElev(coords_transform, 111111)
        way = op.Way(1)
        way.tags["hello"] = "world"
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        lon, lat = coords_transform.to_global((0, 0))
        nodes_dict[1] = op.Node(1, lat, lon)
        lon, lat = coords_transform.to_global((0, 300))
        nodes_dict[2] = op.Node(2, lat, lon)
        lon, lat = coords_transform.to_global((0, 500))
        nodes_dict[3] = op.Node(3, lat, lon)
        lon, lat = coords_transform.to_global((0, 600))
        nodes_dict[4] = op.Node(4, lat, lon)
        lon, lat = coords_transform.to_global((0, 900))
        nodes_dict[5] = op.Node(5, lat, lon)
        lon, lat = coords_transform.to_global((0, 1000))
        nodes_dict[6] = op.Node(6, lat, lon)

        test_roads = Roads(raw_osm_ways, nodes_dict, coords_transform, the_fg_elev)

        msg = 'line with no intersection points -> 1 way orig'
        intersection_points = []

        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 valid intersection point -> 1 way orig shorter, 1 new way'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 100)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(2, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(2, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with one intersection point too short at start -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, parameters.OWBB_BUILT_UP_BUFFER - 1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point too short at end -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 1000 - (parameters.OWBB_BUILT_UP_BUFFER - 1))]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(7, len(way.refs), 'references of orig way: ' + msg)  # 1 more because intersec. point remains

        msg = 'line with 2 intersection points just after each other -> 1 way orig shorter, 2 new ways'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, parameters.OWBB_BUILT_UP_BUFFER + 2),
                               shg.Point(0, 2 * parameters.OWBB_BUILT_UP_BUFFER + 10)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(3, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(2, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 6 nodes and two intersection points given in reverse order for distance -> 1 & 2 new ways'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 700),
                               shg.Point(0, 400)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(3, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(3, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point almost at start -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, parameters.MIN_ROAD_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point almost at end -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, parameters.MIN_ROAD_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point almost at inner-reference -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 500 + parameters.MIN_ROAD_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(2, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(4, len(way.refs), 'references of orig way: ' + msg)

    def test_assign_missing_node_layers(self) -> None:
        nodes_dict = dict()
        coords_transform = coordinates.Transformation(parameters.get_center_global())
        way = op.Way(1)
        way.tags["hello"] = "world"
        lon, lat = coords_transform.to_global((0, 0))
        node_1 = op.Node(1, lat, lon)
        nodes_dict[1] = node_1
        lon, lat = coords_transform.to_global((0, 300))
        node_2 = op.Node(2, lat, lon)
        nodes_dict[2] = node_2
        lon, lat = coords_transform.to_global((0, 500))
        node_3 = op.Node(3, lat, lon)
        nodes_dict[3] = node_3
        lon, lat = coords_transform.to_global((0, 600))
        node_4 = op.Node(4, lat, lon)
        nodes_dict[4] = node_4
        node_4.layers[way] = 4  # just use the index as layer to make it easy
        lon, lat = coords_transform.to_global((0, 900))
        node_5 = op.Node(5, lat, lon)
        nodes_dict[5] = node_5
        node_5.layers[way] = 5
        lon, lat = coords_transform.to_global((0, 1000))
        node_6 = op.Node(6, lat, lon)
        nodes_dict[6] = node_6
        node_6.layers[way] = 6

        # test the splitting into segments
        way.refs = [4, 5]
        segments = WaySegment.split_way_into_way_segments(way, nodes_dict)
        self.assertEqual(1, len(segments), '2 nodes both having layers')

        way.refs = [1, 2]
        segments = WaySegment.split_way_into_way_segments(way, nodes_dict)
        self.assertEqual(1, len(segments), '2 nodes none having layers')

        way.refs = [1, 4, 5]
        segments = WaySegment.split_way_into_way_segments(way, nodes_dict)
        self.assertEqual(2, len(segments), '3 nodes last 2 having layers')

        way.refs = [4, 5, 1]
        segments = WaySegment.split_way_into_way_segments(way, nodes_dict)
        self.assertEqual(2, len(segments), '3 nodes last having no layers')

        way.refs = [4, 1, 5]
        segments = WaySegment.split_way_into_way_segments(way, nodes_dict)
        self.assertEqual(1, len(segments), '3 nodes middle having no layers')

        # test layers
        way.refs = [1, 2]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(0, my_segment.nodes[0].layers[way], 'First node in 2 nodes none having layers')
        self.assertEqual(0, my_segment.nodes[1].layers[way], 'Second node in 2 nodes none having layers')

        way.refs = [4, 5]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(4, my_segment.nodes[0].layers[way], 'First node in 2 nodes with having layers')
        self.assertEqual(5, my_segment.nodes[1].layers[way], 'Second node in 2 nodes with having layers')

        way.refs = [1, 2, 4]
        del node_1.layers[way]
        del node_2.layers[way]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(4, my_segment.nodes[0].layers[way], 'First node in 3 nodes last having layers')
        self.assertEqual(4, my_segment.nodes[1].layers[way], 'Second node in 3 nodes last having layers')
        self.assertEqual(4, my_segment.nodes[2].layers[way], 'Third node in 3 nodes last having layers')

        way.refs = [5, 1, 2]
        del node_1.layers[way]
        del node_2.layers[way]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(5, my_segment.nodes[0].layers[way], 'First node in 3 nodes first having layers')
        self.assertEqual(5, my_segment.nodes[1].layers[way], 'Second node in 3 nodes first having layers')
        self.assertEqual(5, my_segment.nodes[2].layers[way], 'Third node in 3 nodes first having layers')

        way.refs = [6, 1, 4]
        del node_1.layers[way]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(6, my_segment.nodes[0].layers[way], 'First node in 3 nodes middle having no layers')
        self.assertEqual(6, my_segment.nodes[1].layers[way], 'Second node in 3 nodes middle having no layers')
        self.assertEqual(4, my_segment.nodes[2].layers[way], 'Third node in 3 nodes middle having no layers')

        way.refs = [6, 1, 2, 3, 4]
        del node_1.layers[way]
        del node_2.layers[way]
        my_segment = WaySegment.split_way_into_way_segments(way, nodes_dict)[0]
        my_segment.calc_missing_layers_for_nodes()
        self.assertEqual(6, my_segment.nodes[0].layers[way], 'First node in 5 nodes middle having no layers')
        self.assertEqual(6, my_segment.nodes[1].layers[way], 'Second node in 5 nodes middle having no layers')
        self.assertEqual(6, my_segment.nodes[2].layers[way], 'Third node in 5 nodes middle having no layers')
        self.assertEqual(4, my_segment.nodes[3].layers[way], 'Forth node in 5 nodes middle having no layers')
        self.assertEqual(4, my_segment.nodes[4].layers[way], 'Fifth node in 5 nodes middle having no layers')
