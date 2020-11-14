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
from typing import Dict, List, Optional, Tuple

import shapely.geometry as shg
import shapely.ops as sho
from shapely.prepared import prep

import numpy as np
from osm2city import building_lib, prepare_textures, cluster, parameters
import osm2city.textures.materials
import osm2city.utils.coordinates as co
import osm2city.utils.osmparser as op
from osm2city.utils import utilities, stg_io2
from osm2city.owbb import plotting as p
from osm2city.types import osmstrings as s
from osm2city.types import enumerations as enu

OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city

# Cf. https://taginfo.openstreetmap.org/keys/building%3Apart#values and
# https://wiki.openstreetmap.org/wiki/Key%3Abuilding%3Apart
ALLOWED_BUILDING_PART_VALUES = [s.V_YES, s.V_RESIDENTIAL, s.V_APARTMENTS, s.V_HOUSE, s.V_COMMERCIAL, s.V_RETAIL]


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
                               ways_dict: Dict[int, op.Way], coords_transform: co.Transformation) -> None:
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
                           coords_transform: co.Transformation) -> None:
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
                                    coords_transform: co.Transformation) -> int:
    """Processes the members in a multipolygon relationship. Returns the number of buildings actually created.
    If there are several members of type 'outer', then multiple buildings are created.
    Also, tif there are several 'outer', then these buildings are combined in a parent.
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
    building_parent = None
    if len(outer_ways) > 1:
        building_parent = building_lib.BuildingParent(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_relation),
                                                      True)
    for outer_way in outer_ways:
        # use the tags from the relation and the member
        all_tags = dict(list(outer_way.tags.items()) + list(relation.tags.items()))

        inner_rings = list()
        for inner_way in inner_ways:
            if polygons[inner_way.osm_id].within(polygons[outer_way.osm_id]):
                inner_rings.append(inner_way)
        a_building = _make_building_from_way(nodes_dict, all_tags, outer_way, coords_transform, inner_rings)
        my_buildings[a_building.osm_id] = a_building
        if building_parent:
            building_parent.add_child(a_building)
        added_buildings += 1
    return added_buildings


def _process_simple_3d_building(relation: op.Relation, my_buildings: Dict[int, building_lib.Building]):
    """Processes the members in a Simple3D relationship in order to make sure that a building outline exists.

    According to https://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Building_outlines the outline is not
    used for rendering and therefore it is omitted from the parent/child relationship and removed.
    """
    building_outlines_found = list()  # osm_id
    # make relations - we are only interested
    parent = building_lib.BuildingParent(op.get_next_pseudo_osm_id(op.OSMFeatureType.building_relation), False)
    for member in relation.members:
        if member.type_ == s.V_WAY:
            if member.ref in my_buildings:
                related_building = my_buildings[member.ref]
                if s.K_BUILDING in related_building.tags or s.K_BUILDING_PART in related_building.tags:
                    if member.role == s.V_OUTLINE:
                        building_outlines_found.append(related_building.osm_id)
                    else:
                        if s.K_BUILDING_PART in related_building.tags and \
                                related_building.tags[s.K_BUILDING_PART] in ALLOWED_BUILDING_PART_VALUES:
                            parent.add_child(related_building)

    for osm_id in building_outlines_found:
        if osm_id in my_buildings:
            del my_buildings[osm_id]


def _process_building_parts(nodes_dict: Dict[int, op.Node],
                            my_buildings: Dict[int, building_lib.Building],
                            coords_transform: co.Transformation) -> None:
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
    building_prepared_geoms = dict()  # osm_id, PreparedGeometry
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
                b_part_valid_poly = b_part.polygon.is_valid
                parent_missing = True
                for c_key, candidate in my_buildings.items():
                    if part_key != c_key and s.K_BUILDING_PART not in candidate.tags and candidate.polygon is not None:
                        if c_key not in building_prepared_geoms:
                            prep_geom = None
                            if candidate.polygon.is_valid:
                                prep_geom = prep(candidate.polygon)
                            building_prepared_geoms[c_key] = prep_geom
                        else:
                            prep_geom = building_prepared_geoms[c_key]
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
                        elif b_part_valid_poly and prep_geom and\
                                prep_geom.contains_properly(b_part.polygon):
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


def _remove_pseudo_outlines(my_buildings: Dict[int, building_lib.Building]) -> None:
    """Removes buildings with overlap to Simple3D buildings due to special modelling in OSM -> reduce flickering.

    E.g. https://www.openstreetmap.org/query?lat=21.31293&lon=-157.85991 -> Honolulu Park Place:
    https://www.openstreetmap.org/way/500644307 building overlaps with https://www.openstreetmap.org/relation/7301766
    relation, which has 3 ways. The relation with 3 ways models the building better than the building (outline).
    Same for https://www.openstreetmap.org/query?lat=21.31202&lon=-157.85955 -> Kukui Plaza
    https://www.openstreetmap.org/way/293593313 building overlaps with https://www.openstreetmap.org/relation/4064546
    relation.
    Also https://www.openstreetmap.org/query?lat=21.30903&lon=-157.86345 -> Harbour Court
    https://www.openstreetmap.org/way/500162714 building and https://www.openstreetmap.org/relation/7302050 relation.


    https://www.openstreetmap.org/relation/7331962 relation (Hawaii Pacific University)

    Note that sometimes the combination of the floor plan of all relations could be larger than the building.
    """
    building_parents = set()
    for building in my_buildings.values():
        if building.parent:
            building_parents.add(building.parent)

    building_keys_to_remove = set()  # save them to remove for later -> no problem in looping

    for parent in building_parents:
        my_polies = list()
        for child in parent.children:
            my_polies.append(child.geometry)
        my_outline = utilities.merge_buffers(my_polies)[0]  # In most situations there will only be one.

        for key, building in my_buildings.items():
            if building.parent is not None:
                continue  # this is not the case we are looking for
            if building.geometry.disjoint(my_outline):
                continue
            # we have a candidate. Now make sure that there is a high probability by requesting at least 70% overlap
            difference = my_outline.difference(building.geometry)
            if difference.area < 0.3 * my_outline.area:
                building_keys_to_remove.add(key)
                break  # there should not be any other with the same overlap

    for key in building_keys_to_remove:
        del my_buildings[key]
    logging.info('Removed %i pseudo outlines', len(building_keys_to_remove))


def process_building_loose_parts(nodes_dict: Dict[int, op.Node], my_buildings: List[building_lib.Building]) -> None:
    """Checks whether some buildings actually should have the same parent based on shared references.

    This is due to the fact that relations in OSM are not always done clearly - and building:parts are often
    only related by geometry and not distinct modelling in OSM.

    Therefore the following assumption is made:
    * If a building shares 4 or more nodes with another building, then it is related and they get the same parent
    * If a buildings shares 3 consecutive nodes and for each segment the length is more than 2 metres, then
      they are related and get the same parent. In order not to depend on correct sequence etc. it is just assumed
      that the distance between each of the 3 points must be more than 2 metres. It is very improbable that that
      would not be the case for the distance between the 2 pints not directly connected. We take the risk.
    """
    new_relations = 0
    for first_building in my_buildings:
        potential_attached = first_building.zone.osm_buildings
        ref_set_first = set(first_building.refs)
        for second_building in potential_attached:
            if first_building.osm_id == second_building.osm_id:  # do not compare with self
                continue
            if first_building.parent is not None and first_building.parent.contains_child(second_building):
                continue  # existing relationship, nothing to add
            ref_set_second = set(second_building.refs)
            if ref_set_first.isdisjoint(ref_set_second):
                continue  # not related (actually could be related if within, but then _process_building_parts())
            common_refs = list()
            for pos_i in range(len(first_building.refs)):
                for pos_j in range(len(second_building.refs)):
                    if first_building.refs[pos_i] == second_building.refs[pos_j]:
                        common_refs.append(first_building.refs[pos_i])
            # now check our requirements
            if len(common_refs) < 3:
                continue
            new_relationship = False
            if len(common_refs) > 3:
                new_relationship = True
            else:
                node_0 = nodes_dict[common_refs[0]]
                node_1 = nodes_dict[common_refs[1]]
                node_2 = nodes_dict[common_refs[2]]
                len_side_1 = co.calc_distance_global(node_0.lon, node_0.lat, node_1.lon, node_1.lat)
                len_side_2 = co.calc_distance_global(node_1.lon, node_1.lat, node_2.lon, node_2.lat)
                len_side_3 = co.calc_distance_global(node_2.lon, node_2.lat, node_0.lon, node_0.lat)
                if len_side_1 > 2 and len_side_2 > 2 and len_side_3 > 2:
                    new_relationship = True
            if new_relationship:
                new_relations += 1
                if first_building.parent and second_building.parent:
                    # need to decide on one parent (we pick first) and transfer all children from other parent
                    second_building.parent.transfer_children(first_building.parent)
                elif first_building.parent:
                    first_building.parent.add_child(second_building)
                elif second_building.parent:
                    second_building.parent.add_child(first_building)
                else:
                    my_parent = building_lib.BuildingParent(op.get_next_pseudo_osm_id(
                                op.OSMFeatureType.building_relation), False)
                    my_parent.add_child(first_building)
                    my_parent.add_child(second_building)
    logging.info('Created %i new building relations based on shared references', new_relations)


def _process_osm_buildings(nodes_dict: Dict[int, op.Node], ways_dict: Dict[int, op.Way],
                           coords_transform: co.Transformation) -> Dict[int, building_lib.Building]:
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
                            coords_transform: co.Transformation,
                            inner_ways: List[op.Way] = None) -> Optional[building_lib.Building]:
    if way.refs[0] == way.refs[-1]:
        way.refs = way.refs[0:-1]  # -- kick last ref if it coincides with first

    try:
        outer_ring = op.refs_to_ring(coords_transform, way.refs, nodes_dict)
        inner_rings_list = list()
        inner_refs_list = list()
        if inner_ways:
            for _way in inner_ways:
                if _way.refs[0] == _way.refs[-1]:
                    _way.refs = _way.refs[0:-1]  # -- kick last ref if it coincides with first
                inner_rings_list.append(op.refs_to_ring(coords_transform, _way.refs, nodes_dict))
                inner_refs_list.append(_way.refs)
    except KeyError as reason:
        logging.debug("ERROR: Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (
            reason, way.osm_id, all_tags, way.refs))
        return None
    except Exception as reason:
        logging.debug("ERROR: Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, way.osm_id, all_tags,
                                                                                     way.refs))
        return None

    return building_lib.Building(way.osm_id, all_tags, outer_ring, None, inner_rings_list=inner_rings_list,
                                 refs=way.refs, refs_inner=inner_refs_list)


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
                              the_buildings: List[building_lib.Building], cluster_offset: co.Vec2d) -> bool:
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
                    <pitch-deg>0.00</pitch-deg>
                    <heading-deg>0.0</heading-deg>
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


def construct_buildings_from_osm(coords_transform: co.Transformation) -> Tuple[List[building_lib.Building],
                                                                               Dict[int, op.Node]]:
    osm_read_results = op.fetch_osm_db_data_ways_keys([s.K_BUILDING, s.K_BUILDING_PART])
    osm_read_results = op.fetch_osm_db_data_relations_buildings(osm_read_results)
    osm_nodes_dict = osm_read_results.nodes_dict
    osm_ways_dict = osm_read_results.ways_dict
    osm_relations_dict = osm_read_results.relations_dict
    osm_nodes_dict.update(osm_read_results.rel_nodes_dict)  # just add all relevant nodes to have one dict of nodes
    osm_rel_ways_dict = osm_read_results.rel_ways_dict

    # remove those buildings, which will not be rendered and not used in land-use processing
    remove_unused = set()
    for key, way in osm_ways_dict.items():
        if s.is_small_building_detail(way.tags, True) or s.is_small_building_detail(way.tags, False):
            remove_unused.add(key)
        elif s.is_storage_tank(way.tags, True) or s.is_storage_tank(way.tags, False):
            remove_unused.add(key)
        elif s.is_chimney(way.tags):
            remove_unused.add(key)
    for key in remove_unused:
        del osm_ways_dict[key]
    logging.info('Removed %i small buildings not used in land-use', len(remove_unused))

    # make sure that buildings are as rectified as possible -> temporary buildings
    _process_rectify_buildings(osm_nodes_dict, osm_read_results.rel_nodes_dict, osm_ways_dict, coords_transform)

    # then create the actual building objects
    last_time = time.time()
    the_buildings = _process_osm_buildings(osm_nodes_dict, osm_ways_dict, coords_transform)
    last_time = utilities.time_logging('Time used in seconds for processing OSM buildings', last_time)
    _process_osm_relations(osm_nodes_dict, osm_rel_ways_dict, osm_relations_dict, the_buildings, coords_transform)
    last_time = utilities.time_logging('Time used in seconds for processing OSM relations', last_time)
    _process_building_parts(osm_nodes_dict, the_buildings, coords_transform)
    last_time = utilities.time_logging('Time used in seconds for processing building parts', last_time)
    _remove_pseudo_outlines(the_buildings)
    _ = utilities.time_logging('Time used in seconds for removing pseudo outlines', last_time)

    # for convenience change to list from dict
    return list(the_buildings.values()), osm_nodes_dict


def _debug_building_list_lsme(coords_transform: co.Transformation, file_writer, list_elev: float) -> None:
    """Writes a set of list buildings for debugging purposes.

    Should be called at end of with file handler in  write_buildings_in_list.

    The buildings are added from North along the Southern side of the runway at LSME ca. 30m from the runway.
    """
    anchor = coords_transform.to_local((8.3125, 47.0975))
    elev = 427 - list_elev - co.calc_horizon_elev(anchor[0], anchor[1])
    street_angle = 120
    list_type = building_lib.BuildingListType.small
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    width = building_lib.BUILDING_LIST_SMALL_MIN_SIDE * 3
    depth = building_lib.BUILDING_LIST_SMALL_MIN_SIDE
    levels = 2
    body_height = enu.BUILDING_LEVEL_HEIGHT_RURAL * levels
    roof_height = enu.BUILDING_LEVEL_HEIGHT_RURAL
    roof_shape = 1
    wall_tex_idx = 0
    roof_tex_idx = 0
    roof_orientation = 1
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3121, 47.0972))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 2
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3118, 47.0969))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 3
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3114, 47.0966))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 4
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3110, 47.0962))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 5
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3104, 47.0957))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 6
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3099, 47.0953))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 7
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3094, 47.0947))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 8
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3090, 47.0943))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 9
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3087, 47.0940))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 10
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3080, 47.0935))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 11
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3073, 47.0928))
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_shape = 0
    roof_height = 0
    levels = building_lib.BUILDING_LIST_SMALL_MAX_LEVELS
    body_height = enu.BUILDING_LEVEL_HEIGHT_URBAN * levels
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3067, 47.0923))
    list_type = building_lib.BuildingListType.medium
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    width = building_lib.BUILDING_LIST_MEDIUM_MIN_SIDE + 1
    depth = 3 * width
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3061, 47.0918))
    list_type = building_lib.BuildingListType.medium
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    roof_height = enu.BUILDING_LEVEL_HEIGHT_URBAN
    roof_shape = 2
    roof_orientation = 0
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3051, 47.0909))
    list_type = building_lib.BuildingListType.medium
    width = depth
    levels = building_lib.BUILDING_LIST_MEDIUM_MAX_LEVELS
    body_height = levels * enu.BUILDING_LEVEL_HEIGHT_URBAN
    roof_height = 0
    roof_shape = 0
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')

    anchor = coords_transform.to_local((8.3039, 47.0894))
    list_type = building_lib.BuildingListType.large
    width = building_lib.BUILDING_LIST_LARGE_MIN_SIDE
    depth = 4 * width
    levels = building_lib.BUILDING_LIST_LARGE_MAX_LEVELS
    body_height = levels * enu.BUILDING_LEVEL_HEIGHT_URBAN
    line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-anchor[1], anchor[0], elev, street_angle, list_type.value)
    line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(width, depth, body_height,
                                                                 roof_height, roof_shape,
                                                                 roof_orientation, levels,
                                                                 wall_tex_idx, roof_tex_idx)
    file_writer.write(line)
    file_writer.write('\n')


def write_buildings_in_lists(coords_transform: co.Transformation,
                             list_buildings: Dict[building_lib.Building, building_lib.BuildingListType],
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
    wall_tex_idx = 0
    roof_tex_idx = 0
    loc_x = 0
    loc_y = 0

    path_to_stg = stg_manager.add_building_list(file_shader, material_name_shader, coords_transform.anchor, list_elev)

    try:
        with open(os.path.join(path_to_stg, file_shader), 'w') as shader:
            for b, list_type in list_buildings.items():
                elev = b.ground_elev - list_elev - co.calc_horizon_elev(b.anchor.x, b.anchor.y)
                line = '{:.1f} {:.1f} {:.1f} {:.0f} {}'.format(-b.anchor.y, b.anchor.x, elev, b.street_angle,
                                                               list_type.value)
                b.compute_roof_height(True)
                if parameters.BUILDING_TEXTURE_GROUP_RADIUS_M > 0:
                    # Use same texture indexes for small buildings close together.  We take advantage of the building
                    # list being approximately sorted spatially.  This provides some variability.
                    delta_x = b.anchor.x - loc_x
                    delta_y = b.anchor.y - loc_y
                    dist2 = delta_x * delta_x + delta_y * delta_y

                    if list_type.value == building_lib.BuildingListType.small:
                        if dist2 > (parameters.BUILDING_TEXTURE_GROUP_RADIUS_M *
                                    parameters.BUILDING_TEXTURE_GROUP_RADIUS_M):
                            # Generate new texture index if a sufficient distance the center of the last location.
                            wall_tex_idx = int(abs(b.anchor.x / 7.0))
                            roof_tex_idx = int(abs(b.anchor.y / 5.0))
                            loc_x = b.anchor.x
                            loc_y = b.anchor.y
                    else:
                        # Medium and large buildings have semi-random texture
                        wall_tex_idx = int(abs(b.anchor.x / 7.0))
                        roof_tex_idx = int(abs(b.anchor.y / 5.0))
                else:
                    tex_variability = 6
                    if list_type is building_lib.BuildingListType.large:
                        tex_variability = 4
                    wall_tex_idx = random.randint(0, tex_variability - 1)  # FIXME: should calc on street level or owbb
                    roof_tex_idx = wall_tex_idx

                roof_orientation = b.calc_roof_list_orientation()
                line += ' {:.1f} {:.1f} {:.1f} {:.1f} {} {} {} {} {}'.format(b.width, b.depth, b.body_height,
                                                                             b.roof_height, b.roof_shape.value,
                                                                             roof_orientation, round(b.levels),
                                                                             wall_tex_idx, roof_tex_idx)
                shader.write(line)
                shader.write('\n')
            # _debug_building_list_lsme(coords_transform, shader, list_elev)
    except IOError as e:
        logging.warning('Could not write buildings in list to file %s', e)
    logging.info("Total number of shader buildings written to a building_list: %d", len(list_buildings))
    stats.random_buildings = len(list_buildings)


def write_buildings_in_meshes(coords_transform: co.Transformation,
                              mesh_buildings: List[building_lib.Building],
                              stg_manager: stg_io2.STGManager,
                              stats: utilities.Stats) -> None:
    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    cmin, cmax = parameters.get_extent_global()
    logging.info("min/max " + str(cmin) + " " + str(cmax))
    lmin = co.Vec2d(coords_transform.to_local(cmin))
    lmax = co.Vec2d(coords_transform.to_local(cmax))

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
            cluster_offset = co.Vec2d((max_x - min_x) / 2 + min_x, (max_y - min_y) / 2 + min_y)
            center_global = co.Vec2d(coords_transform.to_global((cluster_offset.x, cluster_offset.y)))
            logging.debug("Cluster center -> elevation: %d, position: %s", cluster_elev, cluster_offset)

            file_name = stg_manager.prefix + "b" + str(handled_index) + "%i%i" % (cl.grid_index.ix,
                                                                                  cl.grid_index.iy)
            logging.info("writing cluster %s with %d buildings" % (file_name, len(cl.objects)))

            path_to_stg = stg_manager.add_object_static(file_name + '.ac', center_global, cluster_elev, 0,
                                                        my_clusters.stg_verb_type)

            # -- write .ac and .xml
            building_lib.write(os.path.join(path_to_stg, file_name + ".ac"), cl.objects,
                               cluster_elev, cluster_offset, prepare_textures.roofs, stats)
            if parameters.OBSTRUCTION_LIGHT_MIN_LEVELS > 0:
                obstr_file_name = file_name + '_o.xml'
                has_models = _write_obstruction_lights(path_to_stg, obstr_file_name, cl.objects, cluster_offset)
                if has_models:
                    stg_manager.add_object_static(obstr_file_name, center_global, cluster_elev, 0,
                                                  stg_io2.STGVerbType.object_static)
            total_buildings_written += len(cl.objects)

        handled_index += 1
    logging.info("Total number of buildings written to a cluster *.ac files: %d", total_buildings_written)


def process_buildings(coords_transform: co.Transformation, fg_elev: utilities.FGElev,
                      blocked_apt_areas: List[shg.Polygon], stg_entries: List[stg_io2.STGEntry],
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
        osm2city.textures.materials.screen_osm_keys_for_colour_material_variants(b.tags)

    # check for buildings on airport runways etc.
    before = list()
    if parameters.DEBUG_PLOT_BLOCKED_AREAS_DIFFERENTIATED:
        for b in the_buildings:
            before.append(b.geometry)

    if parameters.OVERLAP_CHECK_CONVEX_HULL:
        blocked_apt_areas = stg_io2.merge_stg_entries_with_blocked_areas(stg_entries, blocked_apt_areas)
    if blocked_apt_areas:
        the_buildings = building_lib.overlap_check_blocked_areas(the_buildings, blocked_apt_areas)

    if parameters.DEBUG_PLOT_BLOCKED_AREAS_DIFFERENTIATED:
        static_objects = stg_io2.convex_hulls_from_stg_entries(stg_entries, [stg_io2.STGVerbType.object_static])
        shared_objects = stg_io2.convex_hulls_from_stg_entries(stg_entries, [stg_io2.STGVerbType.object_shared])
        after = list()
        for b in the_buildings:
            after.append(b.geometry)
        utilities.plot_blocked_areas_and_stg_entries(blocked_apt_areas, static_objects, shared_objects, before, after,
                                                     coords_transform)

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
    buildings_in_lists = dict()  # key = building, value = building list type
    if parameters.FLAG_STG_BUILDING_LIST:
        for building in the_buildings:
            if not building.is_owbb_model:  # owbb models already have it set when init of Building object
                building.update_anchor(True)  # prepare anchor, street_angle, width, depth
            building_list_type = building.calc_building_list_type()
            if building_list_type is not None:
                buildings_in_lists[building] = building_list_type
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
