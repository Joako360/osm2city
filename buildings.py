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
import os
import random
import sys
import textwrap
from typing import Dict, List, Optional

import shapely.geometry as shgm

import building_lib
import cluster
import numpy as np
import parameters
import prepare_textures
import textures.texture as tex
import tools
import utils.stg_io2
import utils.vec2d as v
from utils import aptdat_io, osmparser, calc_tile, coordinates, stg_io2, utilities

OUR_MAGIC = "osm2city"  # Used in e.g. stg files to mark edits by osm2city
SCENERY_TYPE = "Buildings"


def _process_osm_relation(rel_nodes_dict: Dict[int, osmparser.Node], rel_ways_dict: Dict[int, osmparser.Way],
                          relations_dict: Dict[int, osmparser.Relation],
                          my_buildings: List[building_lib.Building]) -> None:
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
                            a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, [inner_ways[0]])
                        else:
                            a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, inner_ways)
                    except:
                        a_building = _make_building_from_way(rel_nodes_dict, all_tags, way, way.refs)
                    if a_building is not None:
                        my_buildings.append(a_building)

            if len(outer_ways) > 0:
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
                    a_building = _make_building_from_way(rel_nodes_dict, all_tags, pseudo_way, [inner_ways[0]])
                else:
                    a_building = _make_building_from_way(rel_nodes_dict, all_tags, pseudo_way, inner_ways)
                if a_building is not None:
                    my_buildings.append(a_building)

            if not outer_multipolygons and not outer_ways:
                logging.info("Skipping relation %i: no outer way." % relation.osm_id)
    additional_buildings = len(my_buildings) - number_of_buildings_before
    logging.info("Added {} buildings based on relations.".format(additional_buildings))


def _process_osm_building(nodes_dict: Dict[int, osmparser.Node], ways_dict: Dict[int, osmparser.Way],
                          clipping_border: shgm.Polygon) -> List[building_lib.Building]:
    my_buildings = list()

    for key, way in ways_dict.items():
        if not ('building' in way.tags or 'building:part' in way.tags):
            continue

        if clipping_border is not None:
            first_node = nodes_dict[way.refs[0]]
            if not clipping_border.contains(shgm.Point(first_node.lon, first_node.lat)):
                continue

        my_building = _make_building_from_way(nodes_dict, way.tags, way, list())
        if my_building is not None:
            my_buildings.append(my_building)

        tools.stats.objects += 1

    return my_buildings


def _make_building_from_way(nodes_dict: Dict[int, osmparser.Node], all_tags: Dict[str, str], way: osmparser.Way,
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
                logging.info("SKIPPING " + name)
                return False
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
        outer_ring = _refs_to_ring(way.refs, nodes_dict)
        inner_rings_list = []
        for _way in inner_ways:
            inner_rings_list.append(_refs_to_ring(_way.refs, nodes_dict, inner=True))
    except KeyError as reason:
        logging.error("Failed to parse building referenced node missing clipped?(%s) WayID %d %s Refs %s" % (
            reason, way.osm_id, all_tags, way.refs))
        tools.stats.parse_errors += 1
        return None
    except Exception as reason:
        logging.error("Failed to parse building (%s)  WayID %d %s Refs %s" % (reason, way.osm_id, all_tags,
                                                                              way.refs))
        tools.stats.parse_errors += 1
        return None

    return building_lib.Building(way.osm_id, all_tags, outer_ring, name, height, levels,
                                 inner_rings_list=inner_rings_list, building_type=_building_type,
                                 roof_type=_roof_type, roof_height=_roof_height, refs=way.refs)


def _refs_to_ring(refs, nodes_dict: Dict[int, osmparser.Node], inner=False):
    """Accept a list of OSM refs, return a linear ring. Also
       fixes face orientation, depending on inner/outer.
    """
    coords = []
    for ref in refs:
        c = nodes_dict[ref]
        coords.append(tools.transform.toLocal((c.lon, c.lat)))

    ring = shgm.polygon.LinearRing(coords)
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

        if b.LOD is not None:
            if b.LOD is utils.stg_io2.LOD.rough:
                has_lod_rough = True
            elif b.LOD is utils.stg_io2.LOD.detail:
                has_lod_detail = True
            else:
                logging.warning("Building %s with unknown LOD level %i", b.osm_id, b.LOD)

    if parameters.USE_NEW_STG_VERBS is False:
        # -- LOD animation
        #    instead use rough, detail, roof
        if has_lod_rough:
            xml.write(textwrap.dedent("""
            <animation>
              <type>range</type>
              <min-m>0</min-m>
              <max-property>/sim/rendering/static-lod/rough</max-property>
              <object-name>LOD_rough</object-name>
            </animation>
            """))
        if has_lod_detail:
            xml.write(textwrap.dedent("""
            <animation>
              <type>range</type>
              <min-m>0</min-m>
              <max-property>/sim/rendering/static-lod/detailed</max-property>
              <object-name>LOD_detail</object-name>
            </animation>
            """))
    xml.write(textwrap.dedent("""

    </PropertyList>
    """))
    xml.close()


def process(uninstall: bool=False, create_atlas: bool=False) -> None:
    random.seed(42)

    files_to_remove = list()
    if uninstall:
        logging.info("Uninstalling.")
        parameters.NO_ELEV = True
        parameters.OVERLAP_CHECK = False

    # -- prepare transformation to local coordinates
    center = parameters.get_center_global()
    coords_transform = coordinates.Transformation(center, hdg=0)
    tools.init(coords_transform)

    prepare_textures.init(create_atlas)

    if parameters.BOUNDARY_CLIPPING:
        clipping_border = shgm.Polygon(parameters.get_clipping_extent())
    else:
        clipping_border = None

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

    the_buildings = _process_osm_building(osm_nodes_dict, osm_ways_dict, clipping_border)
    _process_osm_relation(osm_rel_nodes_dict, osm_rel_ways_dict, osm_relations_dict, the_buildings)

    cmin, cmax = parameters.get_extent_global()
    logging.info("min/max " + str(cmin) + " " + str(cmax))

    logging.info("Created %i buildings." % len(the_buildings))

    # clean up "color" in tags
    for b in the_buildings:
        tex.screen_osm_tags_for_colour_spelling(b.osm_id, b.tags)

    # -- create (empty) clusters
    lmin = v.Vec2d(tools.transform.toLocal(cmin))
    lmax = v.Vec2d(tools.transform.toLocal(cmax))

    handled_clusters = list()  # cluster.ClusterContainer objects
    # cluster_non_lod is used when not using new STG verbs and for mesh_detailed when using new STG verbs
    clusters_default = cluster.ClusterContainer(lmin, lmax)
    handled_clusters.append(clusters_default)
    clusters_building_mesh_rough = None

    if parameters.USE_NEW_STG_VERBS:
        clusters_default.stg_verb_type = stg_io2.STGVerbType.object_building_mesh_detailed
        clusters_building_mesh_rough = cluster.ClusterContainer(lmin, lmax,
                                                                stg_io2.STGVerbType.object_building_mesh_rough)
        handled_clusters.append(clusters_building_mesh_rough)

    # check for buildings on airport runways etc.
    # get blocked areas from apt.dat airport data
    blocked_areas = aptdat_io.get_apt_dat_blocked_areas(coords_transform,
                                                        parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                                                        parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)

    if len(blocked_areas) > 0:
        the_buildings = building_lib.overlap_check_blocked_areas(the_buildings, blocked_areas)

    if parameters.OVERLAP_CHECK:
        # -- read static/shared objects in our area from .stg(s)
        #    FG tiles are assumed to be much larger than our clusters.
        #    Loop all clusters, find relevant tile by checking tile_index at center of each cluster.
        #    Then read objects from .stg.
        stgs = []
        static_objects = []
        for cl in clusters_default:
            center_global = tools.transform.toGlobal(cl.center)
            path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, "Objects", center_global)
            stg_file_name = calc_tile.construct_stg_file_name(center_global)

            if stg_file_name not in stgs:
                stgs.append(stg_file_name)
                static_objects.extend(building_lib.read_buildings_from_stg_entries(path, stg_file_name, OUR_MAGIC))

        logging.info("read %i objects from %i tiles", len(static_objects), len(stgs))
    else:
        static_objects = None

    if parameters.OVERLAP_CHECK_CONVEX_HULL:  # needs to be before building_lib.analyse to catch more at first hit
        the_buildings = building_lib.overlap_check_convex_hull(the_buildings, tools.transform)

    # - analyze buildings
    #   - calculate area
    #   - location clash with stg static models? drop building
    #   - TODO: analyze surrounding: similar shaped buildings nearby? will get same texture
    #   - set building type, roof type etc
    fg_elev = utilities.FGElev(coords_transform, fake=parameters.NO_ELEV)

    the_buildings = building_lib.analyse(the_buildings, static_objects, fg_elev,
                                         prepare_textures.facades, prepare_textures.roofs)
    building_lib.decide_lod(the_buildings)

    # -- initialize STGManager
    path_to_output = parameters.get_output_path()
    replacement_prefix = parameters.get_repl_prefix()
    stg_manager = stg_io2.STGManager(path_to_output, SCENERY_TYPE, OUR_MAGIC, replacement_prefix,
                                     overwrite=True)

    # -- put buildings into clusters, decide LOD, shuffle to hide LOD borders
    for b in the_buildings:
        if parameters.USE_NEW_STG_VERBS:
            if b.LOD is utils.stg_io2.LOD.detail:
                clusters_default.append(b.anchor, b)
            elif b.LOD is utils.stg_io2.LOD.rough:
                clusters_building_mesh_rough.append(b.anchor, b)
        else:
            clusters_default.append(b.anchor, b)

    # -- write clusters
    handled_index = 0
    total_buildings_written = 0
    for my_clusters in handled_clusters:
        my_clusters.write_statistics("cluster_%d" % handled_index)

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
            center_global = v.Vec2d(tools.transform.toGlobal(cluster_offset))
            logging.debug("Cluster center -> elevation: %d, position: %s", cluster_elev, cluster_offset)

            file_name = replacement_prefix + "city" + str(handled_index) + "%02i%02i" % (cl.grid_index.ix,
                                                                                         cl.grid_index.iy)
            logging.info("writing cluster %s with %d buildings" % (file_name, len(cl.objects)))

            path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, cluster_elev, 0,
                                                        my_clusters.stg_verb_type)

            stg_manager.add_object_static('lightmap-switch.xml', center_global, cluster_elev, 0, once=True)

            if uninstall:
                files_to_remove.append(path_to_stg + file_name + ".ac")
                files_to_remove.append(path_to_stg + file_name + ".xml")
            else:
                # -- write .ac and .xml
                building_lib.write(path_to_stg + file_name + ".ac", cl.objects, fg_elev,
                                   cluster_elev, cluster_offset, prepare_textures.roofs)
                _write_xml(path_to_stg, file_name, cl.objects, cluster_offset)
            total_buildings_written += len(cl.objects)

        handled_index += 1
    logging.debug("Total number of buildings written to a cluster *.ac files: %d", total_buildings_written)

    if uninstall:
        for f in files_to_remove:
            try:
                os.remove(f)
            except:
                pass
        stg_manager.drop_ours()
        stg_manager.write()
        logging.info("uninstall done.")
        sys.exit(0)

    fg_elev.save_cache()
    stg_manager.write()
    tools.stats.print_summary()
    utilities.troubleshoot(tools.stats)
    logging.info("done.")


if __name__ == "__main__":
    # -- Parse arguments. Command line overrides config file.
    parser = argparse.ArgumentParser(
        description="buildings.py reads OSM data and creates buildings for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-e", dest="skip_elev", action="store_true",
                        help="skip elevation interpolation", required=False)
    parser.add_argument("-c", dest="skip_overlap_check", action="store_true",
                        help="do not check for overlapping with static objects", required=False)
    parser.add_argument("-a", "--create-atlas", dest="create_atlas", action="store_true",
                        help="create texture atlas", required=False)
    parser.add_argument("-u", dest="uninstall", action="store_true",
                        help="uninstall ours from .stg", required=False)
    parser.add_argument("-l", "--loglevel",
                        help="set loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL",
                        required=False)
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

    process(args.uninstall, args.create_atlas)
