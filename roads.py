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
from collections import OrderedDict
import enum
import logging
import math
import multiprocessing as mp
import os
import random
import textwrap
from typing import Dict, List, MutableMapping, Optional, Tuple
import unittest

import graph
import matplotlib.pyplot as plt
import numpy as np
import shapely.geometry as shg

import linear
import linear_bridge
import parameters
import textures.road
from cluster import ClusterContainer
from utils import osmparser, coordinates, ac3d, stg_io2, utilities, aptdat_io, landuse
from utils.vec2d import Vec2d

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark our edits


BRIDGE_KEY = 'bridge'  # the original OSM tag key
MAN_MADE_KEY = 'man_made'
REPLACED_BRIDGE_KEY = 'replaced_bridge'  # specifies a way that was originally a bridge, but due to length was changed
LIT = 'lit'
MIN_SEGMENT_LENGTH = 1.0


def _is_bridge(way: osmparser.Way) -> bool:
    """Returns true if the tags for this way contains the OSM key for bridge."""
    if MAN_MADE_KEY in way.tags and way.tags[MAN_MADE_KEY] == BRIDGE_KEY:
        return True
    return BRIDGE_KEY in way.tags


def _replace_bridge_tags(tags: Dict[str, str]) -> None:
    if BRIDGE_KEY in tags:
        tags.pop(BRIDGE_KEY)
    if MAN_MADE_KEY in tags and tags[MAN_MADE_KEY] == BRIDGE_KEY:
        tags.pop(MAN_MADE_KEY)
    tags[REPLACED_BRIDGE_KEY] = 'yes'


def _is_replaced_bridge(way: osmparser.Way) -> bool:
    """Returns true is this way was originally a bridge, but was changed to a non-bridge due to lenght.
    See method Roads._replace_short_bridges_with_ways.
    The reason to keep a replaced_tag is because else the way might be split if a node is in the water."""
    return REPLACED_BRIDGE_KEY in way.tags


def _is_processed_railway(way):
    """Check whether this is not only a railway, but one that gets processed.

    E.g. funiculars are currently not processed.
    Must be aligned with accepted railways in Roads._create_linear_objects.
    """
    if not osmparser.is_railway(way):
        return False
    if way.tags['railway'] in ['rail', 'disused', 'preserved', 'subway', 'narrow_gauge', 'tram', 'light_rail']:
        return True
    return False


def is_lit(tags: Dict[str, str]) -> bool:
    if LIT in tags and tags[LIT] == 'yes':
        return True
    return False


def _calc_railway_gauge(way) -> float:
    """Based on railway tags determine the width in meters (3.18 meters for normal gauge)."""
    width = 1435  # millimeters
    if way.tags['railway'] in ['narrow_gauge']:
        width = 1000
    if "gauge" in way.tags:
        if osmparser.is_parsable_float(way.tags['gauge']):
            width = float(way.tags['gauge'])
    return width / 1000 * 126 / 57  # in the texture roads.png the track uses 57 out of 126 pixels


def _is_highway(way):
    return "highway" in way.tags


def _compatible_ways(way1: osmparser.Way, way2: osmparser.Way) -> bool:
    """Returns True if both ways are either a railway, a bridge or a highway - and have common type attributes"""
    logging.debug("trying join %i %i", way1.osm_id, way2.osm_id)
    if osmparser.is_railway(way1) != osmparser.is_railway(way2):
        logging.debug("Nope, either both or none must be railway")
        return False
    elif _is_bridge(way1) != _is_bridge(way2):
        logging.debug("Nope, either both or none must be a bridge")
        return False
    elif _is_highway(way1) != _is_highway(way2):
        logging.debug("Nope, either both or none must be a highway")
        return False
    elif _is_highway(way1) and _is_highway(way2):
        # check type
        highway_type1 = highway_type_from_osm_tags(way1.tags["highway"])
        highway_type2 = highway_type_from_osm_tags(way2.tags["highway"])
        if highway_type1 != highway_type2:
            logging.debug("Nope, both must be of same highway type")
            return False
        # check lit
        highway_lit1 = is_lit(way1.tags)
        highway_lit2 = is_lit(way2.tags)
        if highway_lit1 != highway_lit2:
            return False
    elif osmparser.is_railway(way1) and osmparser.is_railway(way2):
        if way1.tags['railway'] != way2.tags['railway']:
            logging.debug("Nope, both must be of same railway type")
            return False
    return True


def _init_way_from_existing(way: osmparser.Way, node_references: List[int]) -> osmparser.Way:
    """Return copy of way. The copy will have same osm_id and tags, but only given refs"""
    new_way = osmparser.Way(osmparser.get_next_pseudo_osm_id())
    new_way.pseudo_osm_id = way.osm_id
    new_way.tags = way.tags.copy()
    new_way.refs = node_references
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


def get_highway_attributes(highway_type: HighwayType) -> Tuple[int, Tuple[float, float], float]:
    """This must be aligned with HighwayType as well as textures.road and Roads.create_linear_objects."""
    if highway_type in [HighwayType.motorway]:
        priority = 6  # highest of all, but should be 1 less than for railway
        tex = textures.road.ROAD_3
        width = 6.
    elif highway_type in [HighwayType.primary, HighwayType.trunk]:
        priority = 5
        tex = textures.road.ROAD_2
        width = 6.
    elif highway_type in [HighwayType.secondary]:
        priority = 4
        tex = textures.road.ROAD_2
        width = 6.
    elif highway_type in [HighwayType.tertiary, HighwayType.unclassified, HighwayType.road]:
        priority = 3
        tex = textures.road.ROAD_1
        width = 6.
    elif highway_type in [HighwayType.residential, HighwayType.service]:
        priority = 2
        tex = textures.road.ROAD_1
        width = 4.
    else:
        priority = 1
        tex = textures.road.ROAD_1
        width = 4.
    return priority, tex, width


def highway_type_from_osm_tags(value: str) -> Optional[HighwayType]:
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


def _find_junctions(ways_list: List[osmparser.Way]) -> Dict[int, List[Tuple[osmparser.Way, int]]]:
    """Finds nodes, which are shared by at least 2 ways.
    N = number of nodes
    find junctions by brute force:
    - for each node, store attached ways in a dict                O(N)
    - if a node has 2 ways, store that node as a candidate
    - remove entries/nodes that have less than 2 ways attached    O(N)
    - one way ends, other way starts: also a junction
    """

    logging.info('Finding junctions...')
    attached_ways_dict = {}  # a dict: for each ref (aka node) hold a list of attached ways
    for j, the_way in enumerate(ways_list):
        utilities.progress(j, len(ways_list))
        for i, ref in enumerate(the_way.refs):
            if i == 0:  # start
                position = -1
            elif i == len(the_way.refs) - 1:  # last
                position = 1
            else:
                position = 0
            _attached_ways_dict_append(attached_ways_dict, ref, the_way, position)

    # kick nodes that belong to one way only
    for ref, the_ways in list(attached_ways_dict.items()):
        if len(the_ways) < 2:
            attached_ways_dict.pop(ref)
    return attached_ways_dict


def _attached_ways_dict_remove(attached_ways_dict: Dict[int, List[Tuple[osmparser.Way, int]]], the_ref: int,
                               the_way: osmparser.Way) -> None:
    """Remove given way from given node in attached_ways_dict"""
    if the_ref not in attached_ways_dict:
        logging.warning("not removing way from the ref %i because the ref is not in attached_ways_dict", the_ref)
        return
    for way_pos_tuple in attached_ways_dict[the_ref]:
        if way_pos_tuple[0] == the_way:
            logging.debug("removing way %s from node %i", the_way, the_ref)
            attached_ways_dict[the_ref].remove(way_pos_tuple)


def _attached_ways_dict_append(attached_ways_dict: Dict[int, List[Tuple[osmparser.Way, int]]], the_ref: int,
                               the_way: osmparser.Way, position: int) -> None:
    """Append given way to attached_ways_dict."""
    if the_ref not in attached_ways_dict:
        attached_ways_dict[the_ref] = list()
    attached_ways_dict[the_ref].append((the_way, position))


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


class Roads(object):
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
        self.roads_rough_clusters = None
        self.railways_clusters = None

    def __str__(self):
        return "%i ways, %i roads, %i railways, %i bridges" % (len(self.ways_list), len(self.roads_list),
                                                               len(self.railway_list), len(self.bridges_list))

    def process(self, blocked_areas: List[shg.Polygon], stg_entries: List[stg_io2.STGEntry],
                landuses_lit: List[landuse.Landuse], stats: utilities.Stats) -> None:
        """Processes the OSM data until data can be clusterized.
        """
        self._remove_tunnels()
        self._replace_short_bridges_with_ways()
        self._check_ways_in_water()
        self._check_against_blocked_areas(blocked_areas)
        self._check_against_stg_entries(stg_entries)
        self._check_lighting(landuses_lit)
        self._cleanup_topology()
        self._check_points_on_line_distance()

        self._remove_unused_nodes()
        self._probe_elev_at_nodes()

        # -- no change in topology beyond create_linear_objects() !
        logging.debug("before linear " + str(self))
        self._create_linear_objects()
        self._propagate_h_add()
        logging.debug("after linear " + str(self))

        if parameters.CREATE_BRIDGES_ONLY:
            self._keep_only_bridges_and_embankments()

        self._clusterize(stats)

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

            if not node_refs_in_water:  # all on land - just continue
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

    def _check_against_blocked_areas(self, blocked_areas: List[shg.Polygon]) -> None:
        """Makes sure that there are no ways, which go across a blocked area (e.g. airport runway).
        Ways are clipped over into two ways if intersecting."""
        if not blocked_areas:
            return
        new_ways = list()
        for way in self.ways_list:
            my_line = self._line_string_from_way(way)
            for blocked_area in blocked_areas:
                if my_line.intersects(blocked_area):
                    my_line_difference = my_line.difference(blocked_area)
                    if isinstance(my_line_difference, shg.LineString):
                        self._change_way_for_object(my_line_difference, way)
                        continue
                    if isinstance(my_line_difference, shg.MultiLineString) and len(my_line_difference.geoms) == 2:
                        new_ways.append(self._split_way_for_object(my_line_difference, way))

        self.ways_list.extend(new_ways)

    def _check_against_stg_entries(self, stg_entries: List[stg_io2.STGEntry]) -> None:
        """Makes sure that there are no ways tagged as bridges, which go across a STGEntry.
        Ways are clipped over into two ways if intersecting."""
        if not stg_entries:
            return
        new_ways = list()
        for way in reversed(self.ways_list):
            if not _is_bridge(way):
                continue
            my_line = self._line_string_from_way(way)
            for stg_entry in stg_entries:
                if stg_entry.verb_type is not stg_io2.STGVerbType.object_static:
                    continue
                if my_line.intersects(stg_entry.convex_hull):
                    my_line_difference = my_line.difference(stg_entry.convex_hull)
                    if isinstance(my_line_difference, shg.GeometryCollection) and my_line_difference.is_empty:
                        try:
                            self.ways_list.remove(way)
                            logging.debug("Remove way (osm_id=%d) due to static object.", way.osm_id)
                        except ValueError:
                            pass
                        continue
                    if isinstance(my_line_difference, shg.LineString):
                        if my_line_difference.length < parameters.OVERLAP_CHECK_BRIDGE_MIN_REMAINING:
                            try:
                                self.ways_list.remove(way)
                            except ValueError:
                                pass
                            logging.debug("Remove way (osm_id=%d) due to static object.", way.osm_id)
                            continue
                        self._change_way_for_object(my_line_difference, way)
                        logging.debug("Reduced way length (osm_id=%d) due to static object.", way.osm_id)
                        continue
                    if isinstance(my_line_difference, shg.MultiLineString) and len(my_line_difference.geoms) == 2:
                        new_ways.append(self._split_way_for_object(my_line_difference, way))

        self.ways_list.extend(new_ways)

    def _check_lighting(self, landuses_lit: List[landuse.Landuse]) -> None:
        """Checks ways for lighting and maybe splits at borders for built-up areas."""
        way_lul_map = dict()  # key: way, value: list(landuse_lit) from split -> prevent re-check of mini-residuals
        new_ways_1 = self._check_lighting_inner(self.ways_list, landuses_lit, way_lul_map)
        self.ways_list.extend(new_ways_1)
        new_ways_2 = self._check_lighting_inner(new_ways_1, landuses_lit, way_lul_map)
        self.ways_list.extend(new_ways_2)
        # Looping again might get even better splits, but is quite costly for the gained extra effect.
        # now replace 'gen' with 'yes'
        for way in self.ways_list:
            if LIT in way.tags and way.tags[LIT] == 'gen':
                way.tags[LIT] = 'yes'

    def _check_lighting_inner(self, ways_list: List[osmparser.Way], landuses_lit: List[landuse.Landuse],
                              way_lul_map: Dict[osmparser.Way, landuse.Landuse]) -> List[osmparser.Way]:
        """Inner method for _check_lighting doing the actual checking. New split ways are the outcome of the method.
        However all ways by reference get updated tags. This method exists such that new ways can be checked again
        against other built-up areas.
        Using 'gen' instead of 'yes' for lit, because else it would be excluded from further processing by first
        check in loop."""
        new_ways = list()
        non_highway = 0
        orig_lit = 0  # where the tag was set in OSM
        has_intersection = 0
        for i, way in enumerate(ways_list):
            if not _is_highway(way):
                non_highway += 1
                continue
            if is_lit(way.tags):
                orig_lit += 1
                continue  # nothing further to do with this way

            if way in way_lul_map:
                already_checked_luls = way_lul_map[way]
            else:
                already_checked_luls = list()
                way_lul_map[way] = already_checked_luls

            way_changed = True
            my_line = None
            my_line_bounds = None
            for landuse_lit in landuses_lit:
                if way_changed:
                    my_line = self._line_string_from_way(way)  # needs to be re-calculated because could change below
                    my_line_bounds = my_line.bounds
                    way_changed = False
                if landuse_lit in already_checked_luls:
                    continue
                # do a fast cheap check on intersection working with static .bounds (ca. 200 times faster than calling
                # every time)
                if coordinates.disjoint_bounds(my_line_bounds, landuse_lit.bounds):
                    continue

                # do more narrow intersection checks
                if my_line.within(landuse_lit.polygon):
                    way.tags[LIT] = 'gen'
                    break  # it cannot be in more than one built_up area at a time

                intersection_points = list()
                some_geometry = my_line.intersection(landuse_lit.polygon.exterior)
                if isinstance(some_geometry, shg.LineString):
                    continue  # it only touches
                elif isinstance(some_geometry, shg.Point):
                    intersection_points.append(some_geometry)
                elif isinstance(some_geometry, shg.MultiPoint):
                    for a_point in some_geometry:
                        intersection_points.append(a_point)
                elif isinstance(some_geometry, shg.GeometryCollection):
                    if some_geometry.is_empty:
                        continue  # disjoint
                    for a_geom in some_geometry:
                        if isinstance(a_geom, shg.Point):
                            intersection_points.append(a_geom)
                        elif isinstance(a_geom, shg.MultiPoint):
                            for a_point in a_geom:
                                intersection_points.append(a_point)
                        # else nothing to do (we are not interested in a touching LineString
                if intersection_points:
                    way_changed = True
                    has_intersection += 1
                    cut_ways_dict = self.cut_way_at_intersection_points(intersection_points, way, my_line)

                    # now check whether it is lit or not. Due to rounding errors we do this conservatively
                    is_new_way = False  # the first item in the dict is the original way by convention
                    for cut_way, distance in cut_ways_dict.items():
                        my_point = my_line.interpolate(distance)
                        if my_point.within(landuse_lit.polygon):
                            cut_way.tags[LIT] = 'gen'
                        else:
                            cut_way.tags[LIT] = 'no'
                        already_checked_luls.append(landuse_lit)
                        if is_new_way:
                            new_ways.append(cut_way)
                        else:
                            is_new_way = True  # set at end of (first) loop

            if LIT not in way.tags:
                way.tags[LIT] = 'no'

        number_lit = 0
        number_unlit = 0
        for way in ways_list:
            if not _is_highway(way):
                continue
            if way.tags[LIT] in ['yes', 'gen']:
                number_lit += 1
            elif way.tags[LIT] == 'no':
                number_unlit += 1
        for way in new_ways:
            if way.tags[LIT] in ['yes', 'gen']:
                number_lit += 1
            elif way.tags[LIT] == 'no':
                number_unlit += 1

        logging.info('Originally lit {} - generated lit {} - no lit {}'.format(orig_lit, number_lit - orig_lit,
                                                                               number_unlit))
        logging.info('Added {} new streets to existing {} highways'.format(len(new_ways), len(ways_list) - non_highway))
        logging.info('There were {} existing highways with at least 1 intersection'.format(has_intersection))

        return new_ways

    def cut_way_at_intersection_points(self, intersection_points: List[shg.Point], way: osmparser.Way,
                                       my_line: shg.LineString) -> MutableMapping[osmparser.Way, float]:
        """Cuts an existing way into several parts based in intersection points given as a parameter.
        Returns an OrderedDict of Ways, where the first element is always the (changed) original way, such
        that the distance from start to intersection is clear.
        Cutting also checks that the potential new cut ways have a minimum distance based on 
        parameters.BUILT_UP_AREA_LIT_BUFFER, such that the splitting is not too tiny. This can lead to that
        an original way just keeps its original length despite one or several intersection points.
        Distance in the returned dictionary refers to the last point's distance along the original way, which
        is e.g. the length of the original way for the last cut way."""
        intersect_dict = dict()  # osm_id for node, distance from start
        cut_ways_dict = OrderedDict()  # key: way, value: distance of end from start of original way
        # create new global nodes
        for point in intersection_points:
            distance = my_line.project(point)
            lon, lat = self.transform.toGlobal((point.x, point.y))

            # make sure that the new node is relevant and not just a rounding residual
            add_intersection = True
            for ref in way.refs:
                ref_node = self.nodes_dict[ref]
                segment_length = coordinates.calc_distance_global(lon, lat, ref_node.lon, ref_node.lat)
                if segment_length < MIN_SEGMENT_LENGTH:
                    if ref == way.refs[0] or ref == way.refs[-1]:  # ignore because it is almost at either start or end
                        add_intersection = False
                        break
                    else:  # tweak so it can be used as intersection, but based on existing point
                        add_intersection = False
                        way.refs.remove(ref)
                        intersect_dict[ref] = distance
                        my_line = self._line_string_from_way(way)
                        break

            if add_intersection:
                new_node = osmparser.Node(osmparser.get_next_pseudo_osm_id(), lat, lon)
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
                    # check minimal distance of way pieces
                    if (distance - prev_orig_point_dist) < parameters.BUILT_UP_AREA_LIT_BUFFER:
                        continue
                    # make cut
                    current_way_refs.append(key)
                    if is_first:
                        is_first = False
                        way.refs = current_way_refs.copy()
                        new_way = way  # needed to have reference for closing last node below
                    else:
                        new_way = osmparser.Way(osmparser.get_next_pseudo_osm_id())
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
            # check minimal distance of way pieces
            if (my_line.length - prev_orig_point_dist) < parameters.BUILT_UP_AREA_LIT_BUFFER:
                # instead of new cut way extend the last cut way, but do not change its middle_distance
                # last cut_way is still "new_way", because we are not is_first
                new_way.refs.append(original_refs[-1])
            else:
                new_way = osmparser.Way(osmparser.get_next_pseudo_osm_id())
                new_way.pseudo_osm_id = way.osm_id
                new_way.tags = way.tags.copy()
                new_way.refs = current_way_refs.copy()
                new_way.refs.append(original_refs[-1])
                cut_ways_dict[new_way] = my_line.length - (my_line.length - prev_orig_point_dist) / 2

        logging.debug('{} new cut ways (not including orig way) from {} intersections'.format(len(cut_ways_dict) - 1,
                                                                                              len(intersection_points)))
        return cut_ways_dict

    def _change_way_for_object(self, my_line: shg.LineString, original_way: osmparser.Way) -> None:
        """Processes an original way and replaces its coordinates with the coordinates of a LineString."""
        original_way.refs = list()
        the_coordinates = list(my_line.coords)
        for coords in the_coordinates:
            lon_lat = self.transform.toGlobal(coords)
            new_node = osmparser.Node(osmparser.get_next_pseudo_osm_id(), lon_lat[1], lon_lat[0])
            self.nodes_dict[new_node.osm_id] = new_node
            original_way.refs.append(new_node.osm_id)

    def _split_way_for_object(self, my_multiline: shg.MultiLineString, original_way: osmparser.Way) -> osmparser.Way:
        """Processes an original way split by an object (blocked area, stg_entry) and creates additional way"""
        # last node in first line is "new" node not found in original line
        index = len(list(my_multiline.geoms[0].coords)) - 2
        original_refs = original_way.refs
        original_way.refs = original_refs[:index + 1]
        new_way = _init_way_from_existing(original_way, original_refs[index + 1:])
        # now add new nodes from intersection
        lon_lat = self.transform.toGlobal(list(my_multiline.geoms[0].coords)[-1])
        new_node = osmparser.Node(osmparser.get_next_pseudo_osm_id(), lon_lat[1], lon_lat[0])
        self.nodes_dict[new_node.osm_id] = new_node
        original_way.refs.append(new_node.osm_id)
        lon_lat = self.transform.toGlobal(list(my_multiline.geoms[1].coords)[0])
        new_node = osmparser.Node(osmparser.get_next_pseudo_osm_id(), lon_lat[1], lon_lat[0])
        self.nodes_dict[new_node.osm_id] = new_node
        new_way.refs.insert(0, new_node.osm_id)
        logging.debug("Split way (osm_id=%d) into 2 ways due to blocked area.", original_way.osm_id)
        return new_way

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
        """Cleans up the topology for junctions etc."""
        logging.debug("Number of ways before cleaning topology: %i" % len(self.ways_list))

        # make sure there are no almost zero length segments
        # FIXME: this should not be necessary and is most probably residual from _check_lighting
        for way in self.ways_list:
            refs_to_remove = list()
            for i in range(1, len(way.refs)):
                first_node = self.nodes_dict[way.refs[i - 1]]
                second_node = self.nodes_dict[way.refs[i]]
                distance = coordinates.calc_distance_global(first_node.lon, first_node.lat,
                                                            second_node.lon, second_node.lat)
                if distance < MIN_SEGMENT_LENGTH:
                    if len(way.refs) == 2:
                        break  # nothing to do - need to keep it
                    elif i == 1:
                        refs_to_remove.append(way.refs[i])
                    else:
                        refs_to_remove.append(way.refs[i - 1])

            for ref in refs_to_remove:
                way.refs.remove(ref)
                logging.debug('Removing ref {} from way {} due to too short segment')

        # create a dict referencing for every node those ways, which are using this node in their references
        # key = node ref, value = List((way, pos)), where pos=-1 for start, pos=0 for inner, pos=1 for end
        attached_ways_dict = _find_junctions(self.ways_list)

        # split ways where a node not being at start or end is referenced by another way
        self._split_ways_at_inner_junctions(attached_ways_dict)

        # do it again, because the references and positions have changed
        attached_ways_dict = _find_junctions(self.ways_list)

        self._rejoin_ways(attached_ways_dict)

        logging.debug("Number of ways after cleaning topology: %i" % len(self.ways_list))

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
                    _replace_bridge_tags(the_way.tags)

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
                        osm_id = osmparser.get_next_pseudo_osm_id()
                        lon_lat = self.transform.toGlobal((new_point.x, new_point.y))
                        new_node = osmparser.Node(osm_id, lon_lat[1], lon_lat[0])
                        self.nodes_dict[osm_id] = new_node
                        my_new_refs.append(osm_id)
                    my_new_refs.append(the_way.refs[index])

            the_way.refs = my_new_refs

    def _create_linear_objects(self) -> None:
        """Creates the linear objects, which will be created as scenery objects.

        Not processing parking for now (the_way.tags['amenity'] in ['parking'])
        While certainly good to have, parking in OSM is not a linear feature in general.
        We'd need to add areas.
        """
        self.G = graph.Graph()

        priority = 0  # Used both to indicate whether it should be drawn and the priority when crossing

        for the_way in self.ways_list:
            if _is_highway(the_way):
                highway_type = highway_type_from_osm_tags(the_way.tags['highway'])
                # in method Roads.store_way smaller highways already got removed

                priority, tex, width = get_highway_attributes(highway_type)

            elif osmparser.is_railway(the_way):
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
                                                     width=width, tex=tex,
                                                     AGL=above_ground_level)
                    self.bridges_list.append(obj)
                else:
                    obj = linear.LinearObject(self.transform, the_way.osm_id,
                                              the_way.tags, the_way.refs,
                                              self.nodes_dict, width=width, tex=tex,
                                              AGL=above_ground_level)
                    if osmparser.is_railway(the_way):
                        self.railway_list.append(obj)
                    else:
                        self.roads_list.append(obj)
            except ValueError as reason:
                logging.warning("skipping OSM_ID %i: %s" % (the_way.osm_id, reason))
                continue

            self.G.add_edge(obj)

    def _split_ways_at_inner_junctions(self, attached_ways_dict: Dict[int, List[Tuple[osmparser.Way, int]]]) -> None:
        """Split ways such that none of the interior nodes are junctions to other ways.
        I.e., each way object connects to at most two junctions at start and end.
        """
        logging.info('Splitting ways at inner junctions...')
        new_list = []
        the_ref = 0
        for i, the_way in enumerate(self.ways_list):
            utilities.progress(i, len(self.ways_list))
            self.debug_plot_way(the_way, '-', lw=2, color='0.90', show_label=False)

            new_way = _init_way_from_existing(the_way, [the_way.refs[0]])
            for the_ref in the_way.refs[1:]:
                new_way.refs.append(the_ref)
                if the_ref in attached_ways_dict:
                    new_list.append(new_way)
                    self.debug_plot_way(new_way, '-', lw=1)
                    new_way = _init_way_from_existing(the_way, [the_ref])
            if the_ref not in attached_ways_dict:
                new_list.append(new_way)
                self.debug_plot_way(new_way, '--', lw=1)

        self.ways_list = new_list

    def debug_plot_way(self, way, ls, lw, color=None, ends_marker='', show_label=False) -> None:
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

    def debug_label_node(self, ref, text=""):
        node = self.nodes_dict[ref]
        plt.plot(node.lon, node.lat, 'rs', mfc='None', ms=10)
        plt.text(node.lon+0.0001, node.lat, str(node.osm_id) + " h" + str(text))

    def debug_plot(self, save=False, show=False, label_nodes=list(), clusters=None):
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
                    c = np.array([self.transform.toGlobal(p) for p in c])
                    plt.plot(c[:, 0], c[:, 1], '-', color=cluster_color)
                for r in cl.objects:
                    a = np.array(r.center.coords)
                    a = np.array([self.transform.toGlobal(p) for p in a])
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

    def _join_ways(self, way1: osmparser.Way, way2: osmparser.Way,
                   attached_ways_dict: Dict[int, List[Tuple[osmparser.Way, int]]]) -> None:
        """Join ways of compatible type, where way1's last node is way2's first node."""
        logging.debug("Joining %i and %i", way1.osm_id, way2.osm_id)
        if way1.osm_id == way2.osm_id:
            logging.debug("WARNING: Not joining way %i with itself", way1.osm_id)
            return
        way1.refs.extend(way2.refs[1:])

        _attached_ways_dict_remove(attached_ways_dict, way1.refs[-1], way1)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[0], way2)
        _attached_ways_dict_remove(attached_ways_dict, way2.refs[-1], way2)
        _attached_ways_dict_append(attached_ways_dict, way1.refs[-1], way1, 1)

        try:
            self.ways_list.remove(way2)
            logging.debug("2ok")
        except ValueError:
            try:
                self.ways_list.remove(self._find_way_by_osm_id(way2.osm_id))
            except ValueError:
                logging.warning('Way with osm_id={} cannot be removed because cannot be found'.format(way2.osm_id))
            logging.debug("2not")

    def _rejoin_ways(self, attached_ways_dict: Dict[int, List[Tuple[osmparser.Way, int]]]) -> None:
        for ref in list(attached_ways_dict.keys()):  # dict is changed during looping, so using list of keys
            way_pos_list = attached_ways_dict[ref]
            start_dict = dict()  # dict of ways where node is start point with key = way, value = degree from north
            end_dict = dict()  # ditto for node is end point
            for way, position in way_pos_list:
                try:
                    if position == -1:  # start
                        first_node = self.nodes_dict[way.refs[0]]
                        second_node = self.nodes_dict[way.refs[1]]
                        angle = coordinates.calc_angle_of_line_global(first_node.lon, first_node.lat,
                                                                       second_node.lon, second_node.lat)
                        start_dict[way] = angle
                    elif position == 1:  # end
                        first_node = self.nodes_dict[way.refs[-2]]
                        second_node = self.nodes_dict[way.refs[-1]]
                        angle = coordinates.calc_angle_of_line_global(first_node.lon, first_node.lat,
                                                                       second_node.lon, second_node.lat)
                        end_dict[way] = angle
                    else:  # should never happen
                        logging.warning("Way with osm-id={} has not valid position {} for node {}.".format(way.osm_id,
                                                                                                           position,
                                                                                                           ref))
                except ValueError as e:
                    logging.exception('Rejoin not possible for way {} and position {}.'.format(way.osm_id, position))
                    # nothing more to do - most probably rounding error or zero segment length
            # for each in end_dict search in start_dict the one with the closest angle and which is a compatible way
            for end_way, end_angle in end_dict.items():
                candidate_way = None
                candidate_angle = 999
                start_way = None
                for start_way, start_angle in start_dict.items():
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

    def _find_way_by_osm_id(self, osm_id):
        for the_way in self.ways_list:
            if the_way.osm_id == osm_id:
                return the_way
        raise ValueError("way %i not found" % osm_id)

    def _clusterize(self, stats: utilities.Stats):
        """Create cluster.
           Put objects in clusters based on their centroid.
        """
        lmin, lmax = [Vec2d(self.transform.toLocal(c)) for c in parameters.get_extent_global()]
        self.roads_clusters = ClusterContainer(lmin, lmax)
        self.roads_rough_clusters = ClusterContainer(lmin, lmax)
        self.railways_clusters = ClusterContainer(lmin, lmax)

        for the_object in self.bridges_list + self.roads_list + self.railway_list:
            if osmparser.is_railway(the_object):
                cluster_ref = self.railways_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                            the_object, stats)
            else:
                if _is_highway(the_object):
                    if highway_type_from_osm_tags(the_object.tags["highway"]).value < parameters.HIGHWAY_TYPE_MIN_ROUGH_LOD:
                        cluster_ref = self.roads_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                                 the_object, stats)
                    else:
                        cluster_ref = self.roads_rough_clusters.append(Vec2d(the_object.center.centroid.coords[0]),
                                                                       the_object, stats)
                else:
                    cluster_ref = self.roads_clusters.append(Vec2d(the_object.center.centroid.coords[0]), the_object,
                                                             stats)
            the_object.cluster_ref = cluster_ref


def process_osm_ways(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way]) -> List[osmparser.Way]:
    """Processes the values returned from OSM and does a bit of filtering.
    Transformation to roads, railways and bridges is only done later in Roads.process()."""
    my_ways = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if way.osm_id in parameters.SKIP_LIST:
            logging.debug("SKIPPING OSM_ID %i", way.osm_id)
            continue

        if _is_highway(way):
            highway_type = highway_type_from_osm_tags(way.tags["highway"])
            if highway_type is None:
                continue
            elif highway_type.value < parameters.HIGHWAY_TYPE_MIN:
                continue
        elif osmparser.is_railway(way):
            if not _is_processed_railway(way):
                continue

        split_ways = osmparser.split_way_at_boundary(nodes_dict, way, clipping_border)
        if split_ways:
            my_ways.extend(split_ways)

    return my_ways


def _process_clusters(clusters, replacement_prefix, fg_elev: utilities.FGElev, stg_manager, stg_paths, is_railway,
                      coords_transform: coordinates.Transformation, stats: utilities.Stats, is_rough_LOD: bool) -> None:
    for cl in clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS:
            continue  # skip almost empty clusters

        if is_railway:
            file_start = "railways"
        else:
            file_start = "roads"
        if is_rough_LOD:
            file_start += "_rough"
        file_name = replacement_prefix + file_start + "%02i%02i" % (cl.grid_index.ix, cl.grid_index.iy)
        center_global = Vec2d(coords_transform.toGlobal(cl.center))
        offset_local = cl.center
        cluster_elev = fg_elev.probe_elev(center_global, True)

        # -- Now write cluster to disk.
        #    First create ac object. Write cluster's objects. Register stg object.
        #    Write ac to file.
        ac = ac3d.File(stats=stats, show_labels=True)
        texture_string = 'tex/roads.png'
        if parameters.FLAG_2017_2:
            texture_string = 'Textures/osm2city/roads.png'
        ac3d_obj = ac.new_object(file_name, texture_string, default_swap_uv=True, default_mat_idx=ac3d.MAT_IDX_UNLIT)
        for rd in cl.objects:
            rd.write_to(ac3d_obj, fg_elev, cluster_elev, offset=offset_local)

        suffix = ".xml"
        if is_railway or parameters.FLAG_2017_2:
            suffix = ".ac"
        stg_verb_type = stg_io2.STGVerbType.object_building_mesh_detailed
        if parameters.FLAG_2017_2:
            if is_railway:
                stg_verb_type = stg_io2.STGVerbType.object_railway_detailed
            else:
                stg_verb_type = stg_io2.STGVerbType.object_road_detailed
        if is_rough_LOD:
            stg_verb_type = stg_io2.STGVerbType.object_building_mesh_rough
            if parameters.FLAG_2017_2:
                if is_railway:
                    stg_verb_type = stg_io2.STGVerbType.object_railway_rough
                else:
                    stg_verb_type = stg_io2.STGVerbType.object_road_rough
        path_to_stg = stg_manager.add_object_static(file_name + suffix, center_global, cluster_elev, 0,
                                                    stg_verb_type)
        stg_paths.add(path_to_stg)
        ac.write(os.path.join(path_to_stg, file_name + '.ac'))

        if not is_railway:
            if not parameters.FLAG_2017_2:
                _write_xml(path_to_stg, file_name, file_name)

        for the_way in cl.objects:
            the_way.junction0.reset()
            the_way.junction1.reset()


def _write_xml(path_to_stg, file_name, object_name):
    xml = open(os.path.join(path_to_stg, file_name + '.xml'), "w")
    if parameters.TRAFFIC_SHADER_ENABLE and not parameters.FLAG_2017_2:
        shader_str = "Effects/road-high"
    else:
        shader_str = "roads"
    xml.write(textwrap.dedent("""        <?xml version="1.0"?>
        <PropertyList>
        <path>%s.ac</path>
        <effect>
                <inherits-from>%s</inherits-from>
                <object-name>%s</object-name>
        </effect>
        </PropertyList>
    """ % (file_name, shader_str, object_name)))


def process(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev,
            blocked_areas: List[shg.Polygon], stg_entries: List[stg_io2.STGEntry],
            file_lock: mp.Lock=None) -> None:
    random.seed(42)
    stats = utilities.Stats()

    if not parameters.USE_DATABASE:
        osm_way_result = osmparser.fetch_osm_file_data(['highway', 'railway', "tunnel", "bridge", "gauge", "access",
                                                        "lit"],
                                                       ['highway', 'railway'])
    else:
        osm_way_result = osmparser.fetch_osm_db_data_ways_keys(["highway", "railway"])
    osm_nodes_dict = osm_way_result.nodes_dict
    osm_ways_dict = osm_way_result.ways_dict

    logging.info("Number of ways before basic processing: %i", len(osm_ways_dict))
    filtered_osm_ways_list = process_osm_ways(osm_nodes_dict, osm_ways_dict)
    logging.info("Number of ways after basic processing: %i", len(filtered_osm_ways_list))
    if not filtered_osm_ways_list:
        logging.info("No roads and railways found -> aborting")
        return

    roads = Roads(filtered_osm_ways_list, osm_nodes_dict, coords_transform, fg_elev)

    # land-use data for lighting
    if not parameters.USE_DATABASE:
        landuse_result = osmparser.fetch_osm_file_data(['landuse'], ['landuse'])
    else:
        landuse_result = osmparser.fetch_osm_db_data_ways_keys(['landuse'])
    landuse_nodes_dict = landuse_result.nodes_dict
    landuse_ways_dict = landuse_result.ways_dict
    landuses_lit = landuse.process_osm_landuse_for_lighting(landuse_nodes_dict, landuse_ways_dict, coords_transform)

    path_to_output = parameters.get_output_path()
    logging.debug("before linear " + str(roads))

    roads.process(blocked_areas, stg_entries, landuses_lit, stats)  # does the heavy lifting incl. clustering

    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, stg_io2.SceneryType.roads, OUR_MAGIC, replacement_prefix)

    # -- write stg
    stg_paths = set()

    _process_clusters(roads.railways_clusters, replacement_prefix, fg_elev, stg_manager, stg_paths, True,
                      coords_transform, stats, True)
    _process_clusters(roads.roads_clusters, replacement_prefix, fg_elev, stg_manager, stg_paths, False,
                      coords_transform, stats, False)
    _process_clusters(roads.roads_rough_clusters, replacement_prefix, fg_elev, stg_manager, stg_paths, False,
                      coords_transform, stats, True)

    if parameters.DEBUG_PLOT:
        roads.debug_plot(show=True, clusters=roads.roads_clusters)

    stg_manager.write(file_lock)

    utilities.troubleshoot(stats)
    logging.debug("final " + str(roads))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="roads.py reads OSM data and creates road, railway and bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL", required=False)
    parser.add_argument("-e", dest="skip_elev", action="store_true",
                        help="skip elevation interpolation", required=False)
    parser.add_argument("-b", "--bridges-only", dest="bridges_only", action="store_true",
                        help="create only bridges and embankments", required=False)
    args = parser.parse_args()
    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    if args.skip_elev:
        parameters.NO_ELEV = True
    if args.bridges_only:
        parameters.CREATE_BRIDGES_ONLY = True
    parameters.show()

    my_coords_transform = coordinates.Transformation(parameters.get_center_global())
    my_fg_elev = utilities.FGElev(my_coords_transform)
    my_blocked_areas = aptdat_io.get_apt_dat_blocked_areas(my_coords_transform,
                                                           parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                           parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)
    my_stg_entries = stg_io2.read_stg_entries_in_boundary(True, my_coords_transform)

    process(my_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)

    my_fg_elev.close()

    logging.info("******* Finished *******")


# ================ UNITTESTS =======================

class TestUtilities(unittest.TestCase):
    def test_cut_way_at_intersection_points(self):
        raw_osm_ways = list()
        nodes_dict = dict()
        coords_transform = coordinates.Transformation(parameters.get_center_global())
        the_fg_elev = utilities.FGElev(coords_transform)
        way = osmparser.Way(1)
        way.tags["hello"] = "world"
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        lon, lat = coords_transform.toGlobal((0,0))
        nodes_dict[1] = osmparser.Node(1, lat, lon)
        lon, lat = coords_transform.toGlobal((0,300))
        nodes_dict[2] = osmparser.Node(2, lat, lon)
        lon, lat = coords_transform.toGlobal((0,500))
        nodes_dict[3] = osmparser.Node(3, lat, lon)
        lon, lat = coords_transform.toGlobal((0,600))
        nodes_dict[4] = osmparser.Node(4, lat, lon)
        lon, lat = coords_transform.toGlobal((0,900))
        nodes_dict[5] = osmparser.Node(5, lat, lon)
        lon, lat = coords_transform.toGlobal((0,1000))
        nodes_dict[6] = osmparser.Node(6, lat, lon)

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
        intersection_points = [shg.Point(0, parameters.BUILT_UP_AREA_LIT_BUFFER - 1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point too short at end -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 1000 - (parameters.BUILT_UP_AREA_LIT_BUFFER - 1))]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(7, len(way.refs), 'references of orig way: ' + msg)  # 1 more because intersec. point remains

        msg = 'line with 2 intersection points just after each other -> 1 way orig shorter, 2 new ways'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, parameters.BUILT_UP_AREA_LIT_BUFFER + 2),
                               shg.Point(0, 2 * parameters.BUILT_UP_AREA_LIT_BUFFER + 10)]
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
        intersection_points = [shg.Point(0, MIN_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point almost at end -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, MIN_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(1, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(6, len(way.refs), 'references of orig way: ' + msg)

        msg = 'line with 1 intersection point almost at inner-reference -> 1 way orig'
        way.refs = [1, 2, 3, 4, 5, 6]
        my_line = shg.LineString([(0, 0), (0, 300), (0, 500), (0, 600), (0, 900), (0, 1000)])
        intersection_points = [shg.Point(0, 500 + MIN_SEGMENT_LENGTH * 0.1)]
        cut_ways_dict = test_roads.cut_way_at_intersection_points(intersection_points, way, my_line)
        self.assertEqual(2, len(cut_ways_dict), 'number of ways: ' + msg)
        self.assertEqual(3, len(way.refs), 'references of orig way: ' + msg)
