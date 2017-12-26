# -*- coding: utf-8 -*-
"""
buildings.py aims at generating 3D city models for FG, using OSM data.
Currently, it generates 3D textured buildings.
However, it has a somewhat more advanced texture manager, and comes with a
number of facade/roof textures.

- cluster a number of buildings into a single .ac files
- LOD animation based on building height and area
- terrain elevation probing: places buildings at correct elevation

You should disable random buildings.
"""

# TODO:
# - FIXME: texture size meters works reversed??
# x one object per tile only. Now drawables 1072 -> 30fps
# x use geometry library
# x read original .stg+.xml, don't place OSM buildings when there's a static model near/within
# - compute static_object stg's on the fly
# x put roofs into separate LOD
# x lights
# x read relations tag == fix empty backyards
# x simplify buildings
# x put tall, large buildings in LOD rough, and small buildings in LOD detail
# - more complicated roof geometries
#   x split, new roofs.py?
# x cmd line switches
# -

# - city center??

# FIXME:
# - off-by-one error in building counter

# LOWI:
# - floating buildings
# - LOD?
# - rename textures
# x respect ac

# cmd line
# x skip nearby check
# x fake elev
# - log level

# development hints:
# variables
# b: a building instance
#
# coding style
# - indend 4 spaces, avoid tabulators
# - variable names: use underscores (my_long_variable), avoid CamelCase
# - capitalize class names: class Interpolator(object):
# - comments: code # -- comment

import logging
import multiprocessing as mp
import os
import random
import textwrap
from typing import Dict, List, Optional

import shapely.geometry as shg

import building_lib
import cluster
import numpy as np
import parameters
import prepare_textures
import textures.texture as tex
import utils.vec2d as v
from utils import osmparser, coordinates, stg_io2, utilities

OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city


def _process_osm_relation(nodes_dict: Dict[int, osmparser.Node], rel_ways_dict: Dict[int, osmparser.Way],
                          relations_dict: Dict[int, osmparser.Relation],
                          my_buildings: Dict[int, building_lib.Building],
                          coords_transform: coordinates.Transformation,
                          stats: utilities.Stats) -> None:
    """Adds buildings based on relation tags. There are two scenarios: multipolygon buildings and Simple3D tagging.
    Only multipolygon and simple 3D buildings are implemented currently. 
    The added buildings go into parameter my_buildings.
    Multipolygons:
        * see FIXMEs for in building_lib whether inner rings etc. actually are supported.
        * Outer rings out of multiple parts are supported.
        * Islands are removed
    
    3D: 
        * only not-intersecting parts are kept.
        * min_height and min_level are not supported: parts stay on ground.
    
    There is actually a third scenario from Simple3D buildings, where the "building" and "building:part" are not
    connected with a relation. This is handled separately in _process_lonely_building_parts()
    

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
    http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Demo_areas

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
            if 'type' in relation.tags and relation.tags['type'] == 'multipolygon':
                added_buildings = _process_multipolygon_building(nodes_dict, rel_ways_dict, relation,
                                                                 my_buildings, coords_transform, stats)
                number_of_created_buildings += added_buildings
            elif 'type' in relation.tags and relation.tags['type'] == 'building':
                added_buildings = _process_simple_3d_building(nodes_dict, rel_ways_dict, relation,
                                                              my_buildings, coords_transform, stats)
                number_of_created_buildings += added_buildings
        except Exception:
            logging.exception('Unable to process building relation osm_id %d', relation.osm_id)

    logging.info("Added {} buildings based on relations.".format(number_of_created_buildings))


def _process_multipolygon_building(nodes_dict: Dict[int, osmparser.Node], rel_ways_dict: Dict[int, osmparser.Way],
                                   relation: osmparser.Relation, my_buildings: Dict[int, building_lib.Building],
                                   coords_transform: coordinates.Transformation,
                                   stats: utilities.Stats) -> int:
    """Processes the members in a multipolygon relationship. Returns the number of buildings actually created.
    If there are several members of type 'outer', then multiple buildings are created.
    """
    outer_ways = []
    outer_ways_multiple = []  # outer ways, where multiple ways form one or more closed ring
    inner_ways = []
    inner_ways_multiple = []  # inner ways, where multiple ways form one or more closed ring

    # find relationships
    for m in relation.members:
        relation_found = False
        if m.type_ == 'way':
            if m.ref in rel_ways_dict:
                way = rel_ways_dict[m.ref]
                # because the member way already has been processed as normal way, we need to remove
                # otherwise we might get flickering due to two buildings on top of each other
                my_buildings.pop(way.osm_id, None)
                relation_found = True
                if m.role == 'outer':
                    if way.refs[0] == way.refs[-1]:
                        outer_ways.append(way)
                        logging.debug("add way outer " + str(way.osm_id))
                    else:
                        outer_ways_multiple.append(way)
                        logging.debug("add way outer multiple" + str(way.osm_id))
                elif m.role == 'inner':
                    if way.refs[0] == way.refs[-1]:
                        inner_ways.append(way)
                        logging.debug("add way inner " + str(way.osm_id))
                    else:
                        inner_ways_multiple.append(way)
                        logging.debug("add way inner multiple" + str(way.osm_id))
            if not relation_found:
                logging.debug("Way osm_id={} not found for relation osm_id={}.".format(m.ref, relation.osm_id))

    # Process multiple and add to outer_ways/inner_ways as whole rings
    inner_ways.extend(osmparser.closed_ways_from_multiple_ways(inner_ways_multiple))
    outer_ways.extend(osmparser.closed_ways_from_multiple_ways(outer_ways_multiple))

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
        a_building = _make_building_from_way(nodes_dict, all_tags, outer_way, coords_transform,
                                             stats, inner_rings)
        my_buildings[a_building.osm_id] = a_building
        added_buildings += 1
    return added_buildings


def _process_simple_3d_building(nodes_dict: Dict[int, osmparser.Node], rel_ways_dict: Dict[int, osmparser.Way],
                                relation: osmparser.Relation, my_buildings: Dict[int, building_lib.Building],
                                coords_transform: coordinates.Transformation,
                                stats: utilities.Stats) -> int:
    """Processes the members in a Simple3D relationship."""
    my_buildings.pop(relation.osm_id, None)  # we do not need the outline - it will be replaced by parts
    # find relationships
    outline_member = None
    parts = dict()
    for m in relation.members:
        relation_found = False
        if m.type_ == 'way':
            if m.ref in rel_ways_dict:
                way = rel_ways_dict[m.ref]
                # because the member way already has been processed as normal way, we need to remove
                # otherwise we might get flickering due to two buildings on top of each other
                my_buildings.pop(way.osm_id, None)
                if m.role == 'outline':
                    outline_member = way
                elif m.role == 'part':
                    if way.refs[0] == way.refs[-1]:
                        parts[way.osm_id] = way
                    else:
                        logging.debug("removed part with osm_id=%d as it is not closed way." % way.osm_id)
            if not relation_found:
                logging.debug("Way osm_id=%d not found for relation osm_id=%d}." % (m.ref, relation.osm_id))

    if len(parts) == 0:
        return 0
    if len(parts) == 1:
        my_part = parts.popitem()[1]
        if outline_member is not None:  # combine the tags and then this is it
            all_tags = osmparser.combine_tags(my_part.tags, outline_member.tags)
        else:
            all_tags = my_part.tags
        a_building = _make_building_from_way(nodes_dict, all_tags, my_part, coords_transform, stats)
        my_buildings[a_building.osm_id] = a_building
        return 1

    # otherwise make sure that parts only touch, not intersect
    # Create polygons to allow some geometry analysis
    polygons = dict()
    validated_parts = list()
    for key, way in parts.items():
        polygons[way.osm_id] = way.polygon_from_osm_way(nodes_dict, coords_transform)
    for o_key, o_value in polygons.items():
        is_intersecting = False
        for i_key, i_value in polygons.items():
            if o_key == i_key:
                continue
            if (o_value.intersects(i_value) is True) and (o_value.touches(i_value) is False):
                is_intersecting = True
                break
        if not is_intersecting:
            validated_parts.append(parts[o_key])

    # check again (same logic as above)
    if len(validated_parts) == 0:
        return 0
    if len(validated_parts) == 1:
        my_part = validated_parts[0]
        if outline_member is not None:  # combine the tags and then this is it
            all_tags = osmparser.combine_tags(my_part.tags, outline_member.tags)
        else:
            all_tags = my_part.tags
        a_building = _make_building_from_way(nodes_dict, all_tags, my_part, coords_transform, stats)
        my_buildings[a_building.osm_id] = a_building
        return 1

    parent = None
    if outline_member is not None:
        parent = building_lib.BuildingParent(outline_member.osm_id)
    added_buildings = 0
    for my_part in validated_parts:
        if outline_member is not None:
            all_tags = osmparser.combine_tags(my_part.tags, outline_member.tags)
        else:
            all_tags = my_part.tags
        a_building = _make_building_from_way(nodes_dict, all_tags, my_part, coords_transform, stats)
        my_buildings[a_building.osm_id] = a_building
        added_buildings += 1
        if outline_member is not None:
            parent.children.append(a_building)
            a_building.parent = parent
    return added_buildings


def _process_lonely_building_parts(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way],
                                   my_buildings: Dict[int, building_lib.Building],
                                   coords_transform: coordinates.Transformation, stats: utilities.Stats) -> None:
    """Process building parts, for which there is no relationship tagging and therefore there might be overlaps.
    I.e. methods related to _process_osm_relation do not help. Therefore some brute force searching is needed.
    If a building: part is within a building, then keep only the difference of the building and mark it as
    pseudo_parent. In building_lib.analyse() at the end all pseudo_parents get the textures from the building:part."""
    found_pseudo_parents = 0
    valid_parts = list()
    buildings_to_remove = set()  # those pseudo_parents, which are not large enough. List of osm_id
    buildings_to_add = list()  # new pseudo parents from split buildings. List of Building
    for part_key, b_part in my_buildings.items():
        if 'building:part' in b_part.tags and 'building' not in b_part.tags:
            if 'type' in b_part.tags and b_part.tags['type'] == 'multipolygon':
                continue
            if b_part.parent is None:  # i.e. there is no relation tagging in OSM
                valid_parts.append(part_key)
                if part_key in ways_dict:
                    my_way = ways_dict[part_key]
                else:
                    my_way = osmparser.Way(part_key)
                    my_way.refs = b_part.refs
                part_poly = my_way.polygon_from_osm_way(nodes_dict, coords_transform)
                if part_poly is None:
                    continue
                # need to find all buildings, which have at least one node in common
                # do it by common nodes instead of geometry due to performance
                pseudo_candidates = set()
                b_refs_set = set(b_part.refs)
                for c_key, candidate in my_buildings.items():
                    if part_key != c_key and c_key not in pseudo_candidates and 'building:part' not in candidate.tags:
                        if b_refs_set.intersection(set(candidate.refs)):
                            pseudo_candidates.add(c_key)

                # now check by geometry whether they only touch or whether the part is in the building
                for candidate in pseudo_candidates:
                    c_way = osmparser.Way(candidate)
                    c_way.refs = my_buildings[candidate].refs
                    candidate_poly = c_way.polygon_from_osm_way(nodes_dict, coords_transform)
                    if candidate_poly is not None and not part_poly.touches(candidate_poly):
                        # now reduce the pseudo parent building by the building:part.
                        # this might split the pseudo parent into several pieces.
                        pseudo_parent = my_buildings[candidate]
                        pp_refs = pseudo_parent.refs.copy()
                        a_geometry = candidate_poly.difference(part_poly)
                        try:
                            if isinstance(a_geometry, shg.Polygon) and a_geometry.is_valid:
                                coords_list = list(a_geometry.exterior.coords)
                                new_refs = utilities.match_local_coords_with_global_nodes(
                                    coords_list, pp_refs + b_part.refs, nodes_dict,
                                    coords_transform, pseudo_parent.osm_id)
                                pseudo_parent.update_geometry(a_geometry.exterior, refs=new_refs)
                                b_part.pseudo_parents.append(pseudo_parent)
                                found_pseudo_parents += 1
                            elif isinstance(a_geometry, shg.MultiPolygon):
                                my_polygons = a_geometry.geoms
                                is_first = True
                                if my_polygons is not None:
                                    for my_poly in my_polygons:
                                        if isinstance(my_poly, shg.Polygon) and my_poly.is_valid:
                                            if my_poly.area > parameters.BUILDING_MIN_AREA:
                                                coords_list = list(my_poly.exterior.coords)
                                                new_refs = utilities.match_local_coords_with_global_nodes(
                                                    coords_list, pp_refs + b_part.refs, nodes_dict,
                                                    coords_transform, pseudo_parent.osm_id)
                                                found_pseudo_parents += 1
                                                if is_first:
                                                    pseudo_parent.update_geometry(my_poly.exterior, refs=new_refs)
                                                    b_part.pseudo_parents.append(pseudo_parent)
                                                    is_first = False
                                                else:
                                                    other_way = osmparser.Way(osmparser.get_next_pseudo_osm_id())
                                                    other_way.refs = new_refs
                                                    other_pp = _make_building_from_way(nodes_dict,
                                                                                       pseudo_parent.tags.copy(),
                                                                                       other_way,
                                                                                       coords_transform, stats)
                                                    b_part.pseudo_parents.append(other_pp)
                                                    buildings_to_add.append(other_pp)

                                if is_first:  # none of the splits from pseudo_parent were large enough
                                    buildings_to_remove.add(pseudo_parent.osm_id)

                        except (ValueError, KeyError) as e:  # FIXME: for key errors should probably add relation nodes
                            logging.debug(e)
                            buildings_to_remove.add(pseudo_parent.osm_id)  # bold move - just get rid of flickering!
                        break  # no matter whether an exception or not, as there cannot be other buildings

    logging.debug('Removing %d pseudo_parents: %s' % (len(buildings_to_remove), str(buildings_to_remove)))
    for key in buildings_to_remove:
        del my_buildings[key]

    for new_building in buildings_to_add:
        my_buildings[new_building.osm_id] = new_building

    logging.info('Processed valid build:part objects: %d', len(valid_parts))
    logging.info('Parts: %s', str(valid_parts))
    logging.info('Number of found building:part objects within buildings outside of relation: %d', found_pseudo_parents)


def _process_osm_building(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way],
                          coords_transform: coordinates.Transformation,
                          stats: utilities.Stats) -> Dict[int, building_lib.Building]:
    my_buildings = dict()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if not ('building' in way.tags or 'building:part' in way.tags) or len(way.refs) == 0:
            continue

        if 'indoor' in way.tags and way.tags['indoor'] == 'yes':
            continue

        first_node = nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        my_building = _make_building_from_way(nodes_dict, way.tags, way, coords_transform, stats)
        if my_building is not None and my_building.polygon.is_valid:
            my_buildings[my_building.osm_id] = my_building
            stats.objects += 1
        else:
            logging.info('Excluded building with osm_id=%d because of geometry problems', way.osm_id)

    return my_buildings


def _make_building_from_way(nodes_dict: Dict[int, osmparser.Node], all_tags: Dict[str, str], way: osmparser.Way,
                            coords_transform: coordinates.Transformation, stats: utilities.Stats,
                            inner_ways=list()) -> Optional[building_lib.Building]:
    if way.refs[0] == way.refs[-1]:
        way.refs = way.refs[0:-1]  # -- kick last ref if it coincides with first

    name = ""

    # -- funny things might happen while parsing OSM
    try:
        if 'name' in all_tags:
            name = all_tags['name']
            if name in parameters.SKIP_LIST:
                logging.debug("SKIPPING " + name)
                return None

        # -- make outer and inner rings from refs
        outer_ring = _refs_to_ring(coords_transform, way.refs, nodes_dict)
        inner_rings_list = []

        # FIXME : inner rings does not seem to work. Therefore leave out following code
        # for _way in inner_ways:
        #    inner_rings_list.append(_refs_to_ring(coords_transform, _way.refs, nodes_dict, inner=True))
    except KeyError as reason:
        logging.debug("ERROR: Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (
            reason, way.osm_id, all_tags, way.refs))
        stats.parse_errors += 1
        return None
    except Exception as reason:
        logging.debug("ERROR: Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, way.osm_id, all_tags,
                                                                                     way.refs))
        stats.parse_errors += 1
        return None

    return building_lib.Building(way.osm_id, all_tags, outer_ring, name, inner_rings_list=inner_rings_list,
                                 refs=way.refs)


def _refs_to_ring(coords_transform: coordinates.Transformation, refs,
                  nodes_dict: Dict[int, osmparser.Node]) -> shg.LinearRing:
    """Accept a list of OSM refs, return a linear ring."""
    coords = []
    for ref in refs:
        c = nodes_dict[ref]
        coords.append(coords_transform.toLocal((c.lon, c.lat)))

    ring = shg.polygon.LinearRing(coords)
    return ring


def _write_xml(path: str, file_name: str) -> None:
    """Light map animation"""
    xml = open(os.path.join(path, file_name + ".xml"), "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % file_name)

    if parameters.LIGHTMAP_ENABLE:
        xml.write(textwrap.dedent("""
        <effect>
          <inherits-from>cityLM</inherits-from>
          """))
        xml.write("  <object-name>LOD_detail</object-name>\n")
        xml.write("  <object-name>LOD_rough</object-name>\n")
        xml.write("</effect>\n")

    xml.write(textwrap.dedent("""
    </PropertyList>
    """))
    xml.close()


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


def process_buildings(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev,
                      blocked_areas: List[shg.Polygon], stg_entries: List[stg_io2.STGEntry],
                      file_lock: mp.Lock=None) -> None:
    random.seed(42)
    stats = utilities.Stats()

    osm_read_results = osmparser.fetch_osm_db_data_ways_keys(["building", "building:part"])
    osm_read_results = osmparser.fetch_osm_db_data_relations_keys(["building", "building:part"], osm_read_results)
    osm_nodes_dict = osm_read_results.nodes_dict
    osm_ways_dict = osm_read_results.ways_dict
    osm_relations_dict = osm_read_results.relations_dict
    osm_nodes_dict.update(osm_read_results.rel_nodes_dict)  # just add all relevant nodes to have one dict of nodes
    osm_rel_ways_dict = osm_read_results.rel_ways_dict

    the_buildings = _process_osm_building(osm_nodes_dict, osm_ways_dict, coords_transform, stats)
    _process_osm_relation(osm_nodes_dict, osm_rel_ways_dict, osm_relations_dict, the_buildings, coords_transform,
                          stats)
    _process_lonely_building_parts(osm_nodes_dict, osm_ways_dict, the_buildings, coords_transform, stats)

    # for convenience change to list from dict
    the_buildings = list(the_buildings.values())

    cmin, cmax = parameters.get_extent_global()
    logging.info("min/max " + str(cmin) + " " + str(cmax))

    if not the_buildings:
        logging.info("No buildings found in OSM data. Stopping further processing.")
        return

    logging.info("Created %i buildings." % len(the_buildings))

    # clean up "color" in tags
    for b in the_buildings:
        tex.screen_osm_tags_for_colour_spelling(b.osm_id, b.tags)

    # -- create (empty) clusters
    lmin = v.Vec2d(coords_transform.toLocal(cmin))
    lmax = v.Vec2d(coords_transform.toLocal(cmax))

    handled_clusters = list()  # cluster.ClusterContainer objects
    clusters_building_mesh_detailed = cluster.ClusterContainer(lmin, lmax,
                                                               stg_io2.STGVerbType.object_building_mesh_detailed)
    handled_clusters.append(clusters_building_mesh_detailed)
    clusters_building_mesh_rough = cluster.ClusterContainer(lmin, lmax,
                                                            stg_io2.STGVerbType.object_building_mesh_rough)
    handled_clusters.append(clusters_building_mesh_rough)

    # check for buildings on airport runways etc.
    if blocked_areas:
        the_buildings = building_lib.overlap_check_blocked_areas(the_buildings, blocked_areas)

    if parameters.OVERLAP_CHECK_CONVEX_HULL:  # needs to be before building_lib.analyse to catch more at first hit
        the_buildings = building_lib.overlap_check_convex_hull(the_buildings, stg_entries, stats)

    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - TODO: analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc

    if not the_buildings:
        logging.info("No buildings after overlap check etc. Stopping further processing.")
        return

    prepare_textures.init(stats)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, stg_io2.SceneryType.buildings, OUR_MAGIC, replacement_prefix)

    the_buildings = building_lib.analyse(the_buildings, fg_elev, stg_manager, coords_transform,
                                         prepare_textures.facades, prepare_textures.roofs, stats)
    building_lib.decide_lod(the_buildings, stats)

    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    for b in the_buildings:
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
            cluster_offset = v.Vec2d((max_x - min_x)/2 + min_x, (max_y - min_y)/2 + min_y)
            center_global = v.Vec2d(coords_transform.toGlobal(cluster_offset))
            logging.debug("Cluster center -> elevation: %d, position: %s", cluster_elev, cluster_offset)

            file_name = replacement_prefix + "city" + str(handled_index) + "%02i%02i" % (cl.grid_index.ix,
                                                                                         cl.grid_index.iy)
            logging.info("writing cluster %s with %d buildings" % (file_name, len(cl.objects)))

            file_name_in_stg = file_name + '.xml'
            if parameters.FLAG_2017_2:
                file_name_in_stg = file_name + '.ac'

            path_to_stg = stg_manager.add_object_static(file_name_in_stg, center_global, cluster_elev, 0,
                                                        my_clusters.stg_verb_type)

            stg_manager.add_object_static('lightmap-switch.xml', center_global, cluster_elev, 0, once=True)

            # -- write .ac and .xml
            building_lib.write(os.path.join(path_to_stg, file_name + ".ac"), cl.objects,
                               cluster_elev, cluster_offset, prepare_textures.roofs, stats)
            if not parameters.FLAG_2017_2:
                _write_xml(path_to_stg, file_name)
            if parameters.OBSTRUCTION_LIGHT_MIN_LEVELS > 0:
                obstr_file_name = file_name + '_obstrlights.xml'
                has_models = _write_obstruction_lights(path_to_stg, obstr_file_name, cl.objects, cluster_offset)
                if has_models:
                    stg_manager.add_object_static(obstr_file_name, center_global, cluster_elev, 0,
                                                  stg_io2.STGVerbType.object_static)
            total_buildings_written += len(cl.objects)

        handled_index += 1
    logging.debug("Total number of buildings written to a cluster *.ac files: %d", total_buildings_written)

    stg_manager.write(file_lock)
    stats.print_summary()
    utilities.troubleshoot(stats)
