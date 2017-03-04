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

import argparse
import logging
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
import utils.stg_io2
import utils.vec2d as v
from utils import aptdat_io, osmparser, coordinates, stg_io2, utilities

OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city
SCENERY_TYPE = "Buildings"


def _process_osm_relation(rel_nodes_dict: Dict[int, osmparser.Node], rel_ways_dict: Dict[int, osmparser.Way],
                          relations_dict: Dict[int, osmparser.Relation],
                          my_buildings: List[building_lib.Building],
                          coords_transform: coordinates.Transformation,
                          stats: utilities.Stats) -> None:
    """Adds buildings based on relation tags. There are two scenarios: multipolygon buildings and 3D tagging.
    Only multipolygon are implemented currently. The added buildings go into parameter my_buildings

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
    number_of_buildings_before = len(my_buildings)
    for key, relation in relations_dict.items():
        if 'building' in relation.tags or 'building:part' in relation.tags:
            outer_ways = []
            inner_ways = []
            outer_multipolygons = []
            for m in relation.members:
                relation_found = False
                if m.type_ == 'way':
                    if m.role == 'outer':
                        for key, way in rel_ways_dict.items():
                            if way.osm_id == m.ref:
                                relation_found = True
                                if way.refs[0] == way.refs[-1]:
                                    outer_multipolygons.append(way)
                                    logging.debug("add way outer multipolygon " + str(way.osm_id))
                                else:
                                    outer_ways.append(way)
                                    logging.debug("add way outer " + str(way.osm_id))
                    elif m.role == 'inner':
                        for key, way in rel_ways_dict.items():
                            if way.osm_id == m.ref:
                                relation_found = True
                                inner_ways.append(way)
                    if not relation_found:
                        logging.debug("Way osm_id={} not found for relation osm_id={}.".format(m.ref, relation.osm_id))

            if outer_multipolygons:
                all_tags = relation.tags
                for way in outer_multipolygons:
                    logging.debug("Multipolygon " + str(way.osm_id))
                    all_tags = dict(list(way.tags.items()) + list(all_tags.items()))
                    try:
                        if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                            a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, coords_transform,
                                                                 stats, [inner_ways[0]])
                        else:
                            a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, coords_transform,
                                                                 stats, inner_ways)
                    except:
                        a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, coords_transform,
                                                             stats, way.refs)
                    if a_building is not None:
                        my_buildings.append(a_building)

            if outer_ways:
                # build all_outer_refs
                list_outer_refs = [way.refs for way in outer_ways[1:]]
                # get some order :
                all_outer_refs = []
                all_outer_refs.extend(outer_ways[0].refs)

                for foo in range(1, len(outer_ways)):  # FIXME: why loop when same thing happens without foo variable?
                    for way_refs in list_outer_refs:
                        if way_refs[0] == all_outer_refs[-1]:
                            # first node of way is last of previous
                            all_outer_refs.extend(way_refs[0:])
                            continue
                        elif way_refs[-1] == all_outer_refs[-1]:
                            # last node of way is last of previous
                            all_outer_refs.extend(way_refs[::-1])
                            continue
                        list_outer_refs.remove(way_refs)

                all_tags = relation.tags
                for way in outer_ways:
                    all_tags = dict(list(way.tags.items()) + list(all_tags.items()))
                pseudo_way = osmparser.Way(relation.osm_id)
                pseudo_way.refs = all_outer_refs
                if not parameters.EXPERIMENTAL_INNER and len(inner_ways) > 1:
                    logging.info("FIXME: ignoring all but first inner way (%i total) of ID %i" % (len(inner_ways),
                                                                                                  relation.osm_id))
                    a_building = _make_building_from_way(rel_nodes_dict, all_tags, pseudo_way, coords_transform,
                                                         stats, [inner_ways[0]])
                else:
                    a_building = _make_building_from_way(rel_nodes_dict, all_tags, pseudo_way, coords_transform,
                                                         stats, inner_ways)
                if a_building is not None:
                    my_buildings.append(a_building)

            if not outer_multipolygons and not outer_ways:
                logging.debug("Skipping relation %i: no outer way." % relation.osm_id)
    additional_buildings = len(my_buildings) - number_of_buildings_before
    logging.info("Added {} buildings based on relations.".format(additional_buildings))


def _process_osm_building(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way],
                          coords_transform: coordinates.Transformation,
                          stats: utilities.Stats) -> List[building_lib.Building]:
    my_buildings = list()
    clipping_border = shg.Polygon(parameters.get_clipping_border())

    for key, way in ways_dict.items():
        if not ('building' in way.tags or 'building:part' in way.tags):
            continue

        first_node = nodes_dict[way.refs[0]]
        if not clipping_border.contains(shg.Point(first_node.lon, first_node.lat)):
            continue

        my_building = _make_building_from_way(nodes_dict, way.tags, way, coords_transform, stats)
        if my_building is not None:
            my_buildings.append(my_building)

        stats.objects += 1

    return my_buildings


def _make_building_from_way(nodes_dict: Dict[int, osmparser.Node], all_tags: Dict[str, str], way: osmparser.Way,
                            coords_transform: coordinates.Transformation, stats: utilities.Stats,
                            inner_ways=list()) -> Optional[building_lib.Building]:
    if way.refs[0] == way.refs[-1]:
        way.refs = way.refs[0:-1]  # -- kick last ref if it coincides with first

    name = ""
    height = 0.
    levels = 0
    layer = 99

    # -- funny things might happen while parsing OSM
    try:
        if 'name' in all_tags:
            name = all_tags['name']
            if name in parameters.SKIP_LIST:
                logging.debug("SKIPPING " + name)
                return None
        if 'height' in all_tags:
            height = osmparser.parse_length(all_tags['height'])
        elif 'building:height' in all_tags:
            height = osmparser.parse_length(all_tags['building:height'])
        if 'building:levels' in all_tags:
            levels = float(all_tags['building:levels'])
        if 'levels' in all_tags:
            levels = float(all_tags['levels'])
        if 'layer' in all_tags:
            layer = int(all_tags['layer'])
        if 'roof:shape' in all_tags:
            _roof_type = all_tags['roof:shape']
        else:
            _roof_type = parameters.BUILDING_UNKNOWN_ROOF_TYPE

        _roof_height = 0
        if 'roof:height' in all_tags:
            try:
                _roof_height = float(all_tags['roof:height'])
            except:
                _roof_height = 0

        _building_type = building_lib.map_building_type(all_tags)

        # -- simple (silly?) heuristics to 'respect' layers
        if layer == 0:
            return None
        if layer < 99 and height == 0 and levels == 0:
            levels = layer + 2

        # -- make outer and inner rings from refs
        outer_ring = _refs_to_ring(coords_transform, way.refs, nodes_dict)
        inner_rings_list = []
        for _way in inner_ways:
            inner_rings_list.append(_refs_to_ring(coords_transform, _way.refs, nodes_dict, inner=True))
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

    return building_lib.Building(way.osm_id, all_tags, outer_ring, name, height, levels,
                                 inner_rings_list=inner_rings_list, building_type=_building_type,
                                 roof_type=_roof_type, roof_height=_roof_height, refs=way.refs)


def _refs_to_ring(coords_transform: coordinates.Transformation, refs, nodes_dict: Dict[int, osmparser.Node],
                  inner=False):
    """Accept a list of OSM refs, return a linear ring. Also
       fixes face orientation, depending on inner/outer.
    """
    coords = []
    for ref in refs:
        c = nodes_dict[ref]
        coords.append(coords_transform.toLocal((c.lon, c.lat)))

    ring = shg.polygon.LinearRing(coords)
    # -- outer -> CCW, inner -> not CCW
    if ring.is_ccw == inner:
        ring.coords = list(ring.coords)[::-1]
    return ring


def _write_xml(path: str, file_name: str, the_buildings: List[building_lib.Building], cluster_offset: v.Vec2d) -> None:
    #  -- LOD animation
    xml = open(path + file_name + ".xml", "w")
    xml.write("""<?xml version="1.0"?>\n<PropertyList>\n""")
    xml.write("<path>%s.ac</path>" % file_name)

    has_lod_rough = False
    has_lod_detail = False

    if parameters.LIGHTMAP_ENABLE:
        xml.write(textwrap.dedent("""
        <effect>
          <inherits-from>cityLM</inherits-from>
          """))
        xml.write("  <object-name>LOD_detail</object-name>\n")
        xml.write("  <object-name>LOD_rough</object-name>\n")
        xml.write("</effect>\n")

    # -- put obstruction lights on hi-rise buildings
    for b in the_buildings:
        if b.levels >= parameters.OBSTRUCTION_LIGHT_MIN_LEVELS:
            Xo = np.array(b.X_outer)
            for i in np.arange(0, b.nnodes_outer, b.nnodes_outer/4.):
                xo = Xo[int(i+0.5), 0] - cluster_offset.x
                yo = Xo[int(i+0.5), 1] - cluster_offset.y
                zo = b.ceiling + 1.5
                # <path>cursor.ac</path>
                xml.write(textwrap.dedent("""
                <model>
                  <path>Models/Effects/pos_lamp_red_light_2st.xml</path>
                  <offsets>
                    <x-m>%g</x-m>
                    <y-m>%g</y-m>
                    <z-m>%g</z-m>
                    <pitch-deg> 0.00</pitch-deg>
                    <heading-deg>0.0 </heading-deg>
                  </offsets>
                </model>""" % (-yo, xo, zo)))  # -- I just don't get those coordinate systems.

    xml.write(textwrap.dedent("""

    </PropertyList>
    """))
    xml.close()


def process(coords_transform: coordinates.Transformation, fg_elev: utilities.FGElev,
            blocked_areas: List[shg.Polygon], stg_entries: List[utils.stg_io2.STGEntry]) -> None:
    random.seed(42)
    stats = utilities.Stats()

    if not parameters.USE_DATABASE:
        osm_read_results = osmparser.fetch_osm_file_data(list(), ["building", "building:part"],
                                                         ["building", "building:part"])
    else:
        osm_read_results = osmparser.fetch_osm_db_data_ways_keys(["building", "building:part"])
        osm_read_results = osmparser.fetch_osm_db_data_relations_keys(["building", "building:part"], osm_read_results)
    osm_nodes_dict = osm_read_results.nodes_dict
    osm_ways_dict = osm_read_results.ways_dict
    osm_relations_dict = osm_read_results.relations_dict
    osm_rel_nodes_dict = osm_read_results.rel_nodes_dict
    osm_rel_ways_dict = osm_read_results.rel_ways_dict

    the_buildings = _process_osm_building(osm_nodes_dict, osm_ways_dict, coords_transform, stats)
    _process_osm_relation(osm_rel_nodes_dict, osm_rel_ways_dict, osm_relations_dict, the_buildings, coords_transform,
                          stats)

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

    prepare_textures.init(stats, False)

    the_buildings = building_lib.analyse(the_buildings, fg_elev,
                                         prepare_textures.facades, prepare_textures.roofs, stats)
    building_lib.decide_lod(the_buildings, stats)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, SCENERY_TYPE, OUR_MAGIC, replacement_prefix)

    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    for b in the_buildings:
        if b.LOD is utils.stg_io2.LOD.detail:
            clusters_building_mesh_detailed.append(b.anchor, b, stats)
        elif b.LOD is utils.stg_io2.LOD.rough:
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

            path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, cluster_elev, 0,
                                                        my_clusters.stg_verb_type)

            stg_manager.add_object_static('lightmap-switch.xml', center_global, cluster_elev, 0, once=True)

            # -- write .ac and .xml
            building_lib.write(path_to_stg + file_name + ".ac", cl.objects, fg_elev,
                               cluster_elev, cluster_offset, prepare_textures.roofs, stats)
            _write_xml(path_to_stg, file_name, cl.objects, cluster_offset)
            total_buildings_written += len(cl.objects)

        handled_index += 1
    logging.debug("Total number of buildings written to a cluster *.ac files: %d", total_buildings_written)

    stg_manager.write()
    stats.print_summary()
    utilities.troubleshoot(stats)


if __name__ == "__main__":
    # -- Parse arguments. Command line overrides config file.
    parser = argparse.ArgumentParser(
        description="buildings.py reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
    parser.add_argument("-e", dest="skip_elev", action="store_true",
                        help="skip elevation interpolation", required=False)
    parser.add_argument("-c", dest="skip_overlap_check", action="store_true",
                        help="do not check for overlapping with static objects", required=False)
    args = parser.parse_args()
    parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)  # -- must go after reading params file
    if args.skip_elev:
        parameters.NO_ELEV = True
    parameters.show()

    if args.skip_elev:
        parameters.NO_ELEV = True
    if args.skip_overlap_check:
        parameters.OVERLAP_CHECK = False

    my_coords_transform = coordinates.Transformation(parameters.get_center_global())
    my_fg_elev = utilities.FGElev(my_coords_transform)
    my_blocked_areas = aptdat_io.get_apt_dat_blocked_areas(my_coords_transform,
                                                           parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                           parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)

    my_stg_entries = utils.stg_io2.read_stg_entries_in_boundary(True, my_coords_transform)

    process(my_coords_transform, my_fg_elev, my_blocked_areas, my_stg_entries)

    my_fg_elev.close()

    logging.info("******* Finished *******")
