# -*- coding: utf-8 -*-
"""
buildings.py aims at generating 3D city models for FG, using OSM data.
Currently, it generates 3D textured buildings.
However, it has a somewhat more advanced texture manager, and comes with a
number of facade/roof textures.

- cluster a number of buildings into a single .ac files
- LOD animation based on building height and area
- terrain elevation probing: places buildings at correct elevation
"""

import logging
import multiprocessing as mp
import os
import random
import textwrap
import time
from typing import Dict, List, Optional

import shapely.geometry as shg
import shapely.ops as sho

import building_lib
import cluster
import numpy as np
import owbb.plotting as p
import parameters
import prepare_textures
import textures.materials
import utils.osmparser as op
import utils.osmstrings as s
import utils.vec2d as v
from utils import coordinates, stg_io2, utilities

OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city

# Cf. https://taginfo.openstreetmap.org/keys/building%3Apart#values and
# https://wiki.openstreetmap.org/wiki/Key%3Abuilding%3Apart
ALLOWED_BUILDING_PART_VALUES = [s.V_YES, 'residential', 'apartments', 'house', 'commercial', 'retail']


def _in_skip_list(way: op.Way) -> bool:
    """Checking if the way's name or osm_id are SKIP_LIST"""
    if s.K_NAME in way.tags:
        name = way.tags[s.K_NAME]
        if name in parameters.SKIP_LIST:
            logging.debug('SKIPPING building with name tag=%s', name)
            return True
    if way.osm_id in parameters.SKIP_LIST:
        logging.debug('SKIPPING building with osm_id=%i', way.osm_id)
        return True
    return False


def _is_underground(tags: Dict[str, str]) -> bool:
    """Check in tags of building if something looks like underground - depending on parameters."""
    if parameters.BUILDING_UNDERGROUND_LOCATION:
        if s.K_LOCATION in tags and tags[s.K_LOCATION] in (s.V_UNDERGROUND, s.V_INDOOR):
            return True
    if parameters.BUILDING_UNDERGROUND_INDOOR:
        if s.K_INDOOR in tags and tags[s.K_INDOOR] != s.V_NO:
            return True
    if parameters.BUILDING_UNDERGROUND_TUNNEL:
        if s.K_TUNNEL in tags and tags[s.K_TUNNEL] != s.V_NO:
            return True
    if parameters.BUILDING_UNDERGROUND_LEVEL_NEGATIVE:
        if s.K_LEVEL in tags and op.parse_int(tags[s.K_LEVEL], 0) < 0:
            non_negative_levels = False
            if s.K_LEVELS in tags and op.parse_int(tags[s.K_LEVELS], 0) >= 0:
                non_negative_levels = True
            if s.K_BUILDING_LEVELS in tags and op.parse_int(tags[s.K_BUILDING_LEVELS], 0) >= 0:
                non_negative_levels = True
            if non_negative_levels is False:
                return True
    return False


def _process_rectify_buildings(nodes_dict: Dict[int, op.Node], rel_nodes_dict: Dict[int, op.Node],
                               ways_dict: Dict[int, op.Way], coords_transform: coordinates.Transformation) -> None:
    if not parameters.RECTIFY_ENABLED:
        return

    last_time = time.time()
    # create rectify objects
    ref_nodes = dict()
    for key, node in nodes_dict.items():
        x, y = coords_transform.to_local((node.lon, node.lat))
        rectify_node = building_lib.RectifyNode(node.osm_id, x, y)
        ref_nodes[node.osm_id] = rectify_node

    rectify_buildings = list()
    for key, way in ways_dict.items():
        if not (s.K_BUILDING in way.tags or s.K_BUILDING_PART in way.tags) or len(way.refs) == 0:
            continue
        if s.K_INDOOR in way.tags and way.tags[s.K_INDOOR] == s.V_YES:
            continue
        rectify_nodes_list = list()
        for ref in way.refs:
            if ref in ref_nodes:
                rectify_nodes_list.append(ref_nodes[ref])
        rectify_building = building_lib.RectifyBuilding(way.osm_id, rectify_nodes_list)
        rectify_buildings.append(rectify_building)

    # make a pseudo rectify building to make sure nodes in relations / Simple3D buildings do not get changed
    # the object is actually not used anywhere, but the related nodes get updated
    rectify_nodes_list = list()
    for key in rel_nodes_dict.keys():
        rectify_nodes_list.append(ref_nodes[key])

    building_lib.RectifyBuilding(-1, rectify_nodes_list)

    # classify the nodes
    change_candidates = list()
    for building in rectify_buildings:
        nodes_to_change = building.classify_and_relate_unchanged_nodes()
        if nodes_to_change:
            change_candidates.append(building)
    last_time = utilities.time_logging("Time used in seconds for classifying nodes", last_time)

    logging.info("Found %d buildings out of %d buildings with nodes to rectify",
                 len(change_candidates), len(rectify_buildings))

    for building in change_candidates:
        building.rectify_nodes()
    last_time = utilities.time_logging("Time used in seconds for rectifying nodes", last_time)

    if parameters.DEBUG_PLOT_RECTIFY:
        if change_candidates:
            logging.info('Start plotting rectify')
            p.draw_rectify(change_candidates, parameters.RECTIFY_MAX_DRAW_SAMPLE,
                           parameters.RECTIFY_SEED_SAMPLE)
            last_time = utilities.time_logging("Time used in seconds for plotting", last_time)
        else:
            logging.info("Nothing to plot.")

    # Finally update the nodes with the new lon/lat
    counter = 0
    for rectify_node in ref_nodes.values():
        if rectify_node.has_related_buildings:
            if rectify_node.is_updated:
                counter += 1
                original_node = nodes_dict[rectify_node.osm_id]
                lon, lat = coords_transform.to_global((rectify_node.x, rectify_node.y))
                original_node.lon = lon
                original_node.lat = lat
    logging.info("Number of changes for rectified nodes created: %d", counter)
    utilities.time_logging("Time used in seconds for updating lon/lat", last_time)


def _process_osm_relations(nodes_dict: Dict[int, op.Node], rel_ways_dict: Dict[int, op.Way],
                           relations_dict: Dict[int, op.Relation],
                           my_buildings: Dict[int, building_lib.Building],
                           coords_transform: coordinates.Transformation) -> None:
    """Adds buildings based on relation tags. There are two scenarios: multipolygon buildings and Simple3D tagging.
    Only multipolygon and simple 3D buildings are implemented currently. 
    The added buildings go into parameter my_buildings.
    Multipolygons:
        * see FIXMEs in building_lib whether inner rings etc. actually are supported.
        * Outer rings out of multiple parts are supported.
        * Islands are removed

    There is actually a third scenario from Simple3D buildings, where the "building" and "building:part" are not
    connected with a relation. This is handled separately in _process_building_parts()

    See also http://wiki.openstreetmap.org/wiki/Key:building:part
    See also http://wiki.openstreetmap.org/wiki/Buildings

    === Simple multipolygon buildings ===
    http://wiki.openstreetmap.org/wiki/Relation:multipolygon

    <relation id="4555444" version="1" timestamp="2015-02-03T19:59:54Z" uid="505667" user="Bullroarer"
    changeset="28596876">
    <member type="way" ref="326274370" role="outer"/>
    <member type="way" ref="326274316" role="inner"/>
    <tag k="type" v="multipolygon"/>
    <tag k="building" v="yes"/>
    </relation>

    === 3D buildings ===
    See also http://wiki.openstreetmap.org/wiki/Relation:building (has also examples and demo areas at end)
    http://taginfo.openstreetmap.org/relations/building#roles
    http://wiki.openstreetmap.org/wiki/Simple_3D_buildings

    Example of church: http://www.openstreetmap.org/relation/3792630
    <relation id="3792630" ...>
    <member type="way" ref="23813200" role="outline"/>
    <member type="way" ref="285981235" role="part"/>
    <member type="way" ref="285981232" role="part"/>
    <member type="way" ref="285981237" role="part"/>
    <member type="way" ref="285981234" role="part"/>
    <member type="way" ref="285981236" role="part"/>
    <member type="way" ref="285981233" role="part"/>
    <member type="way" ref="285981231" role="part"/>
    <member type="node" ref="1096083389" role="entrance"/>
    <tag k="note" v="The sole purpose of the building relation is to group the individual building:part members.
    The tags of the feature are on the building outline."/>
    <tag k="type" v="building"/>
    </relation>
    """
    number_of_created_buildings = 0
    for key, relation in relations_dict.items():
        try:
            if s.K_TYPE in relation.tags and relation.tags[s.K_TYPE] == s.V_MULTIPOLYGON:
                added_buildings = _process_multipolygon_buildings(nodes_dict, rel_ways_dict, relation,
                                                                  my_buildings, coords_transform)
                number_of_created_buildings += added_buildings
            elif s.K_TYPE in relation.tags and relation.tags[s.K_TYPE] == s.V_BUILDING:
                _process_simple_3d_building(relation, my_buildings)
        except Exception:
            logging.exception('Unable to process building relation osm_id %d', relation.osm_id)

    logging.info("Added {} buildings based on relations.".format(number_of_created_buildings))


def _process_multipolygon_buildings(nodes_dict: Dict[int, op.Node], rel_ways_dict: Dict[int, op.Way],
                                    relation: op.Relation, my_buildings: Dict[int, building_lib.Building],
                                    coords_transform: coordinates.Transformation) -> int:
    """Processes the members in a multipolygon relationship. Returns the number of buildings actually created.
    If there are several members of type 'outer', then multiple buildings are created.
    """
    outer_ways = []
    outer_ways_multiple = []  # outer ways, where multiple ways form one or more closed ring
    inner_ways = []
    inner_ways_multiple = []  # inner ways, where multiple ways form one or more closed ring

    # find relationships
    for member in relation.members:
        relation_found = False
        if member.type_ == s.V_WAY:
            if member.ref in rel_ways_dict:
                way = rel_ways_dict[member.ref]
                # check whether we really want to have this member
                if _in_skip_list(way) or _is_underground(way.tags):
                    continue
                # because the member way already has been processed as normal way, we need to remove
                # otherwise we might get flickering due to two buildings on top of each other
                my_buildings.pop(way.osm_id, None)
                relation_found = True
                if member.role == s.V_OUTER:
                    if way.refs[0] == way.refs[-1]:
                        outer_ways.append(way)
                        logging.debug("add way outer " + str(way.osm_id))
                    else:
                        outer_ways_multiple.append(way)
                        logging.debug("add way outer multiple " + str(way.osm_id))
                elif member.role == s.V_INNER:
                    if way.refs[0] == way.refs[-1]:
                        inner_ways.append(way)
                        logging.debug("add way inner " + str(way.osm_id))
                    else:
                        inner_ways_multiple.append(way)
                        logging.debug("add way inner multiple" + str(way.osm_id))
            if not relation_found:
                logging.debug("Way osm_id={} not found for relation osm_id={}.".format(member.ref, relation.osm_id))

    # Process multiple and add to outer_ways/inner_ways as whole rings
    inner_ways.extend(op.closed_ways_from_multiple_ways(inner_ways_multiple))
    outer_ways.extend(op.closed_ways_from_multiple_ways(outer_ways_multiple))

    # Create polygons to allow some geometry analysis
    polygons = dict()
    for way in outer_ways:
        polygons[way.osm_id] = way.polygon_from_osm_way(nodes_dict, coords_transform)
    for way in inner_ways:
        polygons[way.osm_id] = way.polygon_from_osm_way(nodes_dict, coords_transform)

    # exclude inner islands
    for way in reversed(outer_ways):
        compared_to = outer_ways[:]
        for compared_way in compared_to:
            if way.osm_id != compared_way.osm_id:
                if polygons[way.osm_id].within(polygons[compared_way.osm_id]):
                    outer_ways.remove(way)
                    break

    # create the actual buildings
    added_buildings = 0
    for outer_way in outer_ways:
        # use the tags from the relation and the member
        all_tags = dict(list(outer_way.tags.items()) + list(relation.tags.items()))

        inner_rings = list()
        for inner_way in inner_ways:
            if polygons[inner_way.osm_id].within(polygons[outer_way.osm_id]):
                inner_rings.append(inner_way)
        a_building = _make_building_from_way(nodes_dict, all_tags, outer_way, coords_transform, inner_rings)
        my_buildings[a_building.osm_id] = a_building
        added_buildings += 1
    return added_buildings


def _process_simple_3d_building(relation: op.Relation, my_buildings: Dict[int, building_lib.Building]):
    """Processes the members in a Simple3D relationship in order to make sure that a building outline exists."""
    buildings_found = list()  # osm_id
    building_outlines_found = list()  # osm_id
    # make relations - we are only interested
    for member in relation.members:
        if member.type_ == s.V_WAY:
            if member.ref in my_buildings:
                related_building = my_buildings[member.ref]
                if s.K_BUILDING in related_building.tags:
                    if member.role == s.V_OUTLINE:
                        building_outlines_found.append(related_building.osm_id)
                    else:
                        buildings_found.append(related_building.osm_id)

    if len(building_outlines_found) == 1:
        # nothing to be done - everything as it should and _process_building_parts() takes care of relating etc.
        parent = building_lib.BuildingParent(building_outlines_found[0], True)
        outline_part = my_buildings[building_outlines_found[0]]
        parent.add_child(outline_part)
        for member in buildings_found:
            b_part = my_buildings[member]
            parent.add_child(b_part)
    elif len(building_outlines_found) > 1:
        # meaning the tagging in OSM is wrong - there should only be one outline
        # _process_building_parts() takes care of relating etc. and will probably find different parents.
        logging.warning('OSM data error: there is more than one "outline" member in relation %i',
                        relation.osm_id)
    else:
        # meaning that the tagging in OSM is wrong - there should be one outline
        if buildings_found:
            # Most probably the role was tagged wrongly.
            # nothing to be done - at least one building it will be found as parent in _process_building_parts()
            logging.warning('OSM data error: there is no "outline" member, but at least one "building" in relation %i',
                            relation.osm_id)
        else:
            # now we do not have a building to find as parent in _process_building_parts(). In order to have
            # the building_parts relate nevertheless, we create a virtual parent and relate all parts to
            # this after checking that the building_parts are relevant.
            # There will be no additional checking in _process_building_parts() because now there is a parent already
            logging.warning('OSM data error: there is no "outline" member in relation %i', relation.osm_id)
            parent = building_lib.BuildingParent(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_relation), False)
            # no tags are available to be added on parent level
            for member in relation.members:
                if member.ref in my_buildings:
                    building_part = my_buildings[member.ref]
                    if s.K_BUILDING_PART in building_part.tags and \
                            building_part.tags[s.K_BUILDING_PART] not in ALLOWED_BUILDING_PART_VALUES:
                        parent.add_child(building_part)


def _process_building_parts(nodes_dict: Dict[int, op.Node],
                            my_buildings: Dict[int, building_lib.Building],
                            coords_transform: coordinates.Transformation) -> None:
    """Process building parts, for which there is no relationship tagging and therefore there might be overlaps.
    I.e. methods related to _process_osm_relation do not help. Therefore some brute force searching is needed.
    """
    stats_parts_tested = 0
    stats_parts_removed = 0
    stats_parts_remodelled = 0
    stats_original_removed = 0
    # first relate all parts to parent buildings
    building_parents = dict()  # osm_id, BuildingParent object
    building_parts_to_remove = list()  # osm_ids
    for part_key, b_part in my_buildings.items():
        if s.K_BUILDING_PART in b_part.tags and s.K_BUILDING not in b_part.tags:
            stats_parts_tested += 1
            if s.K_TYPE in b_part.tags and b_part.tags[s.K_TYPE] == s.V_MULTIPOLYGON:
                continue
            if b_part.parent is None:  # i.e. there is no relation tagging in OSM
                # exclude parts, which we do not want
                if b_part.tags[s.K_BUILDING_PART] not in ALLOWED_BUILDING_PART_VALUES:
                    building_parts_to_remove.append(b_part.osm_id)
                    continue
                if b_part.polygon is None or b_part.polygon.area < parameters.BUILDING_PART_MIN_AREA:
                    building_parts_to_remove.append(b_part.osm_id)
                    continue
                # need to find all buildings, which have at least one node in common
                # do it by common nodes instead of geometry due to performance
                parent_missing = True
                for c_key, candidate in my_buildings.items():
                    if part_key != c_key and s.K_BUILDING_PART not in candidate.tags and candidate.polygon is not None:
                        # Not sure why it is not enough to just test for "within", but e.g. 511476571 is not
                        # within 30621689 (building in Prague). Therefore test for references to nodes
                        # and be satisfied if all references are found in candidate
                        all_refs_found = True
                        for ref in b_part.refs:
                            if ref not in candidate.refs:
                                all_refs_found = False
                                break
                        if all_refs_found:
                            parent_missing = False
                        elif b_part.polygon.is_valid and candidate.polygon.is_valid and\
                                b_part.polygon.within(candidate.polygon):
                            parent_missing = False
                        if not parent_missing:
                            if c_key in building_parents:
                                building_parent = building_parents[c_key]
                            else:
                                building_parent = building_lib.BuildingParent(c_key, True)
                                building_parents[building_parent.osm_id] = building_parent
                            building_parent.add_child(b_part)
                            break
                # if no parent was found, then re-model as a building
                if parent_missing:
                    stats_parts_remodelled += 1
                    b_part.make_building_from_part()
            else:
                if b_part.parent.outline:
                    if b_part.parent.osm_id not in building_parents:
                        building_parents[b_part.parent.osm_id] = b_part.parent
    # get rid of those building_parts, which we do not need anymore
    for osm_id in building_parts_to_remove:
        del my_buildings[osm_id]
        stats_parts_removed += 1
    logging.info('Removed %i building:parts, which are not needed due to area etc.', stats_parts_removed)
    logging.info('Remodelled %i building:parts to buildings due to missing parent', stats_parts_remodelled)
    logging.info('Tested %i building:parts', stats_parts_tested)

    # now reduce the area of the building_parents' original building and if some area left then add as new part
    for key, building_parent in building_parents.items():
        original_building = my_buildings[key]  # the original building acting as parent
        original_building_still_used = False
        building_parent.add_tags(original_building.tags.copy())

        # combine all node references for later search space
        node_refs = original_building.refs.copy()
        for child in building_parent.children:
            node_refs.extend(child.refs.copy())
        # add up all areas of the children - we are only interested in what is left
        children_polygons = list()
        for child in building_parent.children:
            common_refs = [x for x in child.refs if x in original_building.refs]
            if len(common_refs) < 2:
                continue  # excluding, because could have min_height on top of building (e.g. a dome)
            children_polygons.append(child.polygon)
        total_area_building_parts = sho.cascaded_union(children_polygons)
        geometry_difference = original_building.polygon.difference(total_area_building_parts)
        try:
            if isinstance(geometry_difference, shg.Polygon) and geometry_difference.is_valid:
                if geometry_difference.area >= parameters.BUILDING_PART_MIN_AREA:
                    coords_list = list(geometry_difference.exterior.coords)
                    new_refs = utilities.match_local_coords_with_global_nodes(
                        coords_list, node_refs, nodes_dict,
                        coords_transform, key)
                    # make the original building a building_part and update with the remaining geometry
                    original_building.update_geometry(geometry_difference.exterior, refs=new_refs)
                    original_building.tags = dict()
                    original_building.tags[s.K_BUILDING_PART] = s.V_YES
                    building_parent.add_child(original_building)
                    original_building_still_used = True
            elif isinstance(geometry_difference, shg.MultiPolygon):
                my_polygons = geometry_difference.geoms
                if geometry_difference.area >= parameters.BUILDING_PART_MIN_AREA and my_polygons is not None:
                    is_first = True
                    for my_poly in my_polygons:
                        if isinstance(my_poly, shg.Polygon) and my_poly.is_valid and \
                                my_poly.area >= parameters.BUILDING_PART_MIN_AREA:
                            coords_list = list(my_poly.exterior.coords)
                            new_refs = utilities.match_local_coords_with_global_nodes(
                                coords_list, node_refs, nodes_dict,
                                coords_transform, key)
                            if is_first:
                                is_first = False
                                # make the original building a building_part and update with the remaining geometry
                                original_building.update_geometry(my_poly.exterior, refs=new_refs)
                                original_building.tags = dict()
                                original_building.tags[s.K_BUILDING_PART] = s.V_YES
                                building_parent.add_child(original_building)
                                original_building_still_used = True
                            else:
                                new_way = op.Way(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_relation))
                                new_way.refs = new_refs
                                new_tags = {s.K_BUILDING_PART: s.V_YES}
                                new_building_part = _make_building_from_way(nodes_dict, new_tags, new_way,
                                                                            coords_transform)
                                my_buildings[new_building_part.osm_id] = new_building_part
                                building_parent.add_child(new_building_part)

            else:  # GeometryCollection empty -> nothing left, i.e. the parts cover the whole original building
                pass
        except Exception as e:
            logging.warning('There is an unresolved problem for building parent with key %i', key)
            logging.warning(e)
            # nothing else to be done, original_building_still_used either properly set to True or not

        if not original_building_still_used:
            # if the original_building is not reused, then remove it
            del my_buildings[key]
            stats_original_removed += 1

    logging.info('Handled %i building_parents and removed %i original buildings',
                 len(building_parents), stats_original_removed)


def _process_osm_building(nodes_dict: Dict[int, op.Node], ways_dict: Dict[int, op.Way],
                          coords_transform: coordinates.Transformation) -> Dict[int, building_lib.Building]:
    my_buildings = dict()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if not (s.K_BUILDING in way.tags or s.K_BUILDING_PART in way.tags) or len(way.refs) == 0:
            continue

        if s.K_INDOOR in way.tags and way.tags[s.K_INDOOR] == s.V_YES:
            continue

        first_node = nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        # checking whether a building should be left out
        if _in_skip_list(way) or _is_underground(way.tags):
            continue

        my_building = _make_building_from_way(nodes_dict, way.tags, way, coords_transform)
        if my_building is not None and my_building.polygon.is_valid:
            my_buildings[my_building.osm_id] = my_building
        else:
            logging.info('Excluded building with osm_id=%d because of geometry problems', way.osm_id)

    return my_buildings


def _make_building_from_way(nodes_dict: Dict[int, op.Node], all_tags: Dict[str, str], way: op.Way,
                            coords_transform: coordinates.Transformation,
                            inner_ways=None) -> Optional[building_lib.Building]:
    if way.refs[0] == way.refs[-1]:
        way.refs = way.refs[0:-1]  # -- kick last ref if it coincides with first

    name = ""

    # -- funny things might happen while parsing OSM
    try:
        # -- make outer and inner rings from refs
        outer_ring = _refs_to_ring(coords_transform, way.refs, nodes_dict)
        inner_rings_list = list()
        if inner_ways:
            for _way in inner_ways:
                inner_rings_list.append(_refs_to_ring(coords_transform, _way.refs, nodes_dict))
    except KeyError as reason:
        logging.debug("ERROR: Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (
            reason, way.osm_id, all_tags, way.refs))
        return None
    except Exception as reason:
        logging.debug("ERROR: Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, way.osm_id, all_tags,
                                                                                     way.refs))
        return None

    return building_lib.Building(way.osm_id, all_tags, outer_ring, name, None, inner_rings_list=inner_rings_list,
                                 refs=way.refs)


def _refs_to_ring(coords_transform: coordinates.Transformation, refs,
                  nodes_dict: Dict[int, op.Node]) -> shg.LinearRing:
    """Accept a list of OSM refs, return a linear ring."""
    coords = []
    for ref in refs:
        c = nodes_dict[ref]
        coords.append(coords_transform.to_local((c.lon, c.lat)))

    ring = shg.polygon.LinearRing(coords)
    return ring


def _clean_building_zones_dangling_children(my_buildings: List[building_lib.Building]) -> None:
    """Make sure that building zones / city blocks do not have linked buildings, which are not used anymore."""
    building_zones = set()
    for building in my_buildings:
        if building.zone:
            building_zones.add(building.zone)

    for zone in building_zones:
        # remove no longer valid children
        for building in reversed(zone.osm_buildings):
            if building not in my_buildings:
                zone.osm_buildings.remove(building)


def _write_obstruction_lights(path: str, file_name: str,
                              the_buildings: List[building_lib.Building], cluster_offset: v.Vec2d) -> bool:
    """Add obstruction lights on top of high buildings. Return true if at least one obstruction light is added."""
    models_list = list()  # list of strings
    for b in the_buildings:
        if b.levels >= parameters.OBSTRUCTION_LIGHT_MIN_LEVELS:
            nodes_outer = np.array(b.pts_outer)
            for i in np.arange(0, b.pts_outer_count, b.pts_outer_count / 4.):
                xo = nodes_outer[int(i + 0.5), 0] - cluster_offset.x
                yo = nodes_outer[int(i + 0.5), 1] - cluster_offset.y
                zo = b.top_of_roof_above_sea_level + 1.5

                models_list.append(textwrap.dedent("""
                <model>
                  <path>Models/Effects/pos_lamp_red_light_2st.xml</path>
                  <offsets>
                    <x-m>%g</x-m>
                    <y-m>%g</y-m>
                    <z-m>%g</z-m>
                    <pitch-deg> 0.00</pitch-deg>
                    <heading-deg>0.0 </heading-deg>
                  </offsets>
                </model>""") % (-yo, xo, zo))
    if len(models_list) > 0:
        xml = open(os.path.join(path, file_name), "w")
        xml.write('<?xml version="1.0"?>\n<PropertyList>\n')
        xml.write('\n'.join(models_list))
        xml.write(textwrap.dedent("""
        </PropertyList>
        """))
        xml.close()
        return True
    else:
        return False


def construct_buildings_from_osm(coords_transform: coordinates.Transformation) -> List[building_lib.Building]:
    osm_read_results = op.fetch_osm_db_data_ways_keys([s.K_BUILDING, s.K_BUILDING_PART])
    osm_read_results = op.fetch_osm_db_data_relations_buildings(osm_read_results)
    osm_nodes_dict = osm_read_results.nodes_dict
    osm_ways_dict = osm_read_results.ways_dict
    osm_relations_dict = osm_read_results.relations_dict
    osm_nodes_dict.update(osm_read_results.rel_nodes_dict)  # just add all relevant nodes to have one dict of nodes
    osm_rel_ways_dict = osm_read_results.rel_ways_dict

    # first make sure that buildings are as rectified as possible -> temporary buildings
    _process_rectify_buildings(osm_nodes_dict, osm_read_results.rel_nodes_dict, osm_ways_dict, coords_transform)

    # then create the actual building objects
    last_time = time.time()
    the_buildings = _process_osm_building(osm_nodes_dict, osm_ways_dict, coords_transform)
    last_time = utilities.time_logging('Time used in seconds for processing OSM buildings', last_time)
    _process_osm_relations(osm_nodes_dict, osm_rel_ways_dict, osm_relations_dict, the_buildings, coords_transform)
    last_time = utilities.time_logging('Time used in seconds for processing OSM relations', last_time)
    _process_building_parts(osm_nodes_dict, the_buildings, coords_transform)
    _ = utilities.time_logging('Time used in seconds for processing building parts', last_time)

    # for convenience change to list from dict
    return list(the_buildings.values())


def write_buildings_in_lists(coords_transform: coordinates.Transformation,
                             list_buildings: List[building_lib.Building],
                             stg_manager: stg_io2.STGManager,
                             stats: utilities.Stats) -> None:
    min_elevation = 9999
    max_elevation = -9999
    for b in list_buildings:
        min_elevation = min(min_elevation, b.ground_elev)
        max_elevation = max(max_elevation, b.ground_elev)
    list_elev = (max_elevation - min_elevation) / 2 + min_elevation

    material_name_shader = 'OSMBuildings'
    file_shader = stg_manager.prefix + "_buildings_shader.txt"

    path_to_stg = stg_manager.add_building_list(file_shader, material_name_shader, coords_transform.anchor, list_elev)

    try:
        with open(os.path.join(path_to_stg, file_shader), 'w') as shader:
            for b in list_buildings:
                if not b.is_owbb_model:
                    b.update_anchor(True)
                elev = b.ground_elev - list_elev - coordinates.calc_horizon_elev(b.anchor.x, b.anchor.y)
                line = '{:.1f} {:.1f} {:.1f} {:.0f} {}\n'.format(-b.anchor.y, b.anchor.x, elev, b.street_angle,
                                                                 b.building_list_type.value)
                shader.write(line)
    except IOError as e:
        logging.warning('Could not write buildings in list to file %s', e)
    logging.debug("Total number of buildings written to a building_list: %d", len(list_buildings))
    stats.random_buildings = len(list_buildings)


def write_buildings_in_meshes(coords_transform: coordinates.Transformation,
                              mesh_buildings: List[building_lib.Building],
                              stg_manager: stg_io2.STGManager,
                              stats: utilities.Stats) -> None:
    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    cmin, cmax = parameters.get_extent_global()
    logging.info("min/max " + str(cmin) + " " + str(cmax))
    lmin = v.Vec2d(coords_transform.to_local(cmin))
    lmax = v.Vec2d(coords_transform.to_local(cmax))

    handled_clusters = list()  # cluster.ClusterContainer objects
    clusters_building_mesh_detailed = cluster.ClusterContainer(lmin, lmax,
                                                               stg_io2.STGVerbType.object_building_mesh_detailed)
    handled_clusters.append(clusters_building_mesh_detailed)
    clusters_building_mesh_rough = cluster.ClusterContainer(lmin, lmax,
                                                            stg_io2.STGVerbType.object_building_mesh_rough)
    handled_clusters.append(clusters_building_mesh_rough)
    for b in mesh_buildings:
        if b.LOD is stg_io2.LOD.detail:
            clusters_building_mesh_detailed.append(b.anchor, b, stats)
        elif b.LOD is stg_io2.LOD.rough:
            clusters_building_mesh_rough.append(b.anchor, b, stats)

    # -- write clusters
    handled_index = 0
    total_buildings_written = 0
    for my_clusters in handled_clusters:
        my_clusters.write_statistics_for_buildings("cluster_%d" % handled_index)

        for ic, cl in enumerate(my_clusters):
            number_of_buildings = len(cl.objects)
            if number_of_buildings < parameters.CLUSTER_MIN_OBJECTS:
                continue  # skip almost empty clusters

            # calculate relative positions within cluster
            min_elevation = 9999
            max_elevation = -9999
            min_x = 1000000000
            min_y = 1000000000
            max_x = -1000000000
            max_y = -1000000000
            for b in cl.objects:
                min_elevation = min(min_elevation, b.ground_elev)
                max_elevation = max(max_elevation, b.ground_elev)
                min_x = min(min_x, b.anchor.x)
                min_y = min(min_y, b.anchor.y)
                max_x = max(max_x, b.anchor.x)
                max_y = max(max_y, b.anchor.y)
            cluster_elev = (max_elevation - min_elevation) / 2 + min_elevation
            cluster_offset = v.Vec2d((max_x - min_x) / 2 + min_x, (max_y - min_y) / 2 + min_y)
            center_global = v.Vec2d(coords_transform.to_global((cluster_offset.x, cluster_offset.y)))
            logging.debug("Cluster center -> elevation: %d, position: %s", cluster_elev, cluster_offset)

            file_name = stg_manager.prefix + "city" + str(handled_index) + "%02i%02i" % (cl.grid_index.ix,
                                                                                         cl.grid_index.iy)
            logging.info("writing cluster %s with %d buildings" % (file_name, len(cl.objects)))

            path_to_stg = stg_manager.add_object_static(file_name + '.ac', center_global, cluster_elev, 0,
                                                        my_clusters.stg_verb_type)

            # -- write .ac and .xml
            building_lib.write(os.path.join(path_to_stg, file_name + ".ac"), cl.objects,
                               cluster_elev, cluster_offset, prepare_textures.roofs, stats)
            if parameters.OBSTRUCTION_LIGHT_MIN_LEVELS > 0:
                obstr_file_name = file_name + '_obstrlights.xml'
                has_models = _write_obstruction_lights(path_to_stg, obstr_file_name, cl.objects, cluster_offset)
                if has_models:
                    stg_manager.add_object_static(obstr_file_name, center_global, cluster_elev, 0,
                                                  stg_io2.STGVerbType.object_static)
            total_buildings_written += len(cl.objects)

        handled_index += 1
    logging.debug("Total number of buildings written to a cluster *.ac files: %d", total_buildings_written)


def process_buildings(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev,
                      blocked_areas: List[shg.Polygon], stg_entries: List[stg_io2.STGEntry],
                      the_buildings: List[building_lib.Building],
                      file_lock: mp.Lock = None) -> None:
    last_time = time.time()
    random.seed(42)

    if not the_buildings:
        logging.info("No buildings found in OSM data. Stopping further processing.")
        return

    logging.info("Created %i buildings." % len(the_buildings))

    # clean up "color" in tags
    for b in the_buildings:
        textures.materials.screen_osm_keys_for_colour_material_variants(b.tags)

    # check for buildings on airport runways etc.
    if blocked_areas:
        the_buildings = building_lib.overlap_check_blocked_areas(the_buildings, blocked_areas)

    if parameters.OVERLAP_CHECK_CONVEX_HULL:  # needs to be before building_lib.analyse to catch more at first hit
        the_buildings = building_lib.overlap_check_convex_hull(the_buildings, stg_entries)

    # final check on building parent hierarchy and zones linked to buildings > remove dangling stuff
    building_lib.BuildingParent.clean_building_parents_dangling_children(the_buildings)
    _clean_building_zones_dangling_children(the_buildings)

    building_lib.update_building_tags_in_aerodromes(the_buildings)

    if not the_buildings:
        logging.info("No buildings after overlap check etc. Stopping further processing.")
        return

    stats = utilities.Stats()

    prepare_textures.init(stats)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    stg_manager = stg_io2.STGManager(path_to_output, stg_io2.SceneryType.buildings, OUR_MAGIC, parameters.PREFIX)

    last_time = utilities.time_logging("Time used in seconds until before analyse", last_time)

    # the heavy lifting: analysis
    the_buildings = building_lib.analyse(the_buildings, fg_elev, stg_manager, coords_transform,
                                         prepare_textures.facades, prepare_textures.roofs, stats)
    last_time = utilities.time_logging("Time used in seconds for analyse", last_time)

    # split between buildings in meshes and in buildings lists
    building_lib.decide_lod(the_buildings, stats)
    buildings_in_meshes = list()
    buildings_in_lists = list()
    if parameters.FLAG_STG_BUILDING_LIST:
        for building in the_buildings:
            if building.is_building_list_candidate():
                buildings_in_lists.append(building)
            else:
                buildings_in_meshes.append(building)
        if parameters.FLAG_BUILDINGS_LIST_SKIP is False:
            write_buildings_in_lists(coords_transform, buildings_in_lists, stg_manager, stats)
            last_time = utilities.time_logging("Time used in seconds to write buildings in lists", last_time)
    else:
        buildings_in_meshes = the_buildings[:]
    if parameters.FLAG_BUILDINGS_MESH_SKIP is False:
        write_buildings_in_meshes(coords_transform, buildings_in_meshes, stg_manager, stats)
        last_time = utilities.time_logging("Time used in seconds to write buildings in meshes", last_time)

    stg_manager.write(file_lock)
    _ = utilities.time_logging("Time used in seconds to write stg file", last_time)
    stats.print_summary()
    utilities.troubleshoot(stats)
