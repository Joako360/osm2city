import logging
import math
import multiprocessing as mp
import os
import random
from typing import Dict, List, Set

import shapely.geometry as shg
from shapely.prepared import prep

from osm2city import parameters
from osm2city import building_lib as bl
from osm2city.owbb.models import Bounds, CityBlock
from osm2city.static_types import osmstrings as s
from osm2city.utils import coordinates as co
from osm2city.static_types import enumerations as e
from osm2city.utils import utilities, stg_io2
from osm2city.utils import osmparser as op

TREES_MAGIC = 'trees'


class Tree:
    """A single tree from OSM or interpreted OSM data.

    Cf. https://wiki.openstreetmap.org/wiki/Tag:natural=tree?uselang=en
    Cf. https://wiki.openstreetmap.org/wiki/Key%3Adenotation
    """
    def __init__(self, osm_id: int, x: float, y: float, elev: float) -> None:
        self.osm_id = osm_id
        self.x = x
        self.y = y
        self.elev = elev
        self.tree_type = e.TreeType.default

    def parse_tags(self, tags: Dict[str, str]) -> None:
        if s.K_DENOTATION in tags:  # significant trees should be at least normal
            self.tree_type = e.TreeType.default

    @classmethod
    def tree_from_node(cls, node: op.Node, coords_transform: co.Transformation, fg_elev: utilities.FGElev) -> 'Tree':
        elev = fg_elev.probe_elev((node.lon, node.lat), True)
        x, y = coords_transform.to_local((node.lon, node.lat))
        tree = Tree(node.osm_id, x, y, elev)
        tree.parse_tags(node.tags)
        return tree


def _process_osm_trees_nodes(osm_nodes_dict: Dict[int, op.Node], coords_transform: co.Transformation,
                             fg_elev: utilities.FGElev) -> List[Tree]:
    """Uses trees directly mapped in OSM."""
    trees = list()

    for key, node in osm_nodes_dict.items():
        trees.append(Tree.tree_from_node(node, coords_transform, fg_elev))
    return trees


def _process_osm_trees_parks(parks: List[shg.Polygon], trees: List[Tree], city_blocks: Set[CityBlock],
                             fg_elev: utilities.FGElev) -> None:
    """Additional trees based on specific land-use (not woods) in urban areas.

    NB: extends the existing list of trees from the input parameter.
    """
    additional_trees = list()  # not directly adding to trees due to spatial comparison
    mapped_factor = math.pow(parameters.C2P_TREES_DIST_BETWEEN_TREES_PARK_MAPPED, 2)
    logging.info('Number of area polygons for process for trees: %i', len(parks))
    tree_points_to_check = list()
    for tree in trees:
        tree_points_to_check.append(shg.Point(tree.x, tree.y))
    for my_geometry in parks:
        trees_contained = 0
        prep_geom = prep(my_geometry)
        # check whether any of the existing manually mapped trees is within the area.
        # if yes, then most probably all trees where manually mapped
        for tree_point in tree_points_to_check:
            if prep_geom.contains(tree_point):
                trees_contained += 1
                # not removing from to be checked as probably takes more time to remove than check again
        if trees_contained == 0 or (my_geometry.area / trees_contained) > mapped_factor:
            # we are good to try to add more trees
            points = _random_trees_in_area(my_geometry, prep_geom,
                                           city_blocks,
                                           parameters.C2P_TREES_DIST_BETWEEN_TREES_PARK,
                                           parameters.C2P_TREES_SKIP_RATE_TREES_PARK)
            for point in points:
                elev = fg_elev.probe_elev((point.x, point.y), False)
                additional_trees.append(Tree(op.get_next_pseudo_osm_id(op.OSMFeatureType.generic_node),
                                             point.x, point.y, elev))
    logging.info('Number of trees added in areas: %i', len(additional_trees))
    trees.extend(additional_trees)


def _process_osm_trees_gardens(city_blocks: Set[CityBlock], parks: List[shg.Polygon],
                               fg_elev: utilities.FGElev) -> Dict[e.TreeType, List[Tree]]:
    suburban_trees = list()
    town_trees = list()
    urban_trees = list()
    for city_block in city_blocks:
        tree_type = e.map_tree_type_from_settlement_type_garden(city_block.settlement_type)
        if city_block.type_ is e.BuildingZoneType.special_processing:
            continue
        prep_geom = prep(city_block.geometry)
        my_random_points = _generate_random_tree_points_in_polygon(city_block.geometry, prep_geom,
                                                                   parameters.C2P_TREES_DIST_BETWEEN_TREES_GARDEN,
                                                                   parameters.C2P_TREES_SKIP_RATE_TREES_GARDEN)

        for point in my_random_points:
            exclude = False
            for park in parks:  # need to check for parks
                if point.within(park):
                    exclude = True
                    break
            if exclude:
                continue
            if not _test_point_in_building(point, {city_block}, 2.0):
                elev = fg_elev.probe_elev((point.x, point.y), False)
                my_tree = Tree(op.get_next_pseudo_osm_id(op.OSMFeatureType.generic_node),
                               point.x, point.y, elev)
                if tree_type is e.TreeType.suburban:
                    suburban_trees.append(my_tree)
                elif tree_type is e.TreeType.town:
                    town_trees.append(my_tree)
                else:
                    urban_trees.append(my_tree)

    garden_trees = dict()
    if suburban_trees:
        garden_trees[e.TreeType.suburban] = suburban_trees
    if town_trees:
        garden_trees[e.TreeType.town] = town_trees
    if urban_trees:
        garden_trees[e.TreeType.urban] = urban_trees
    logging.info('Number of trees added in gardens: %i', len(suburban_trees) + len(town_trees) + len(urban_trees))
    return garden_trees


def _generate_random_tree_points_in_polygon(my_polygon: shg.Polygon, prep_geom,
                                            default_distance: int, skip_rate: float) -> List[shg.Point]:
    """Creates a random set of points for trees within a polygon based on an average distance and a skip rate.

    This is not a very efficient algorithm, but it should be enough to give an ok distribution."""
    my_random_points = list()
    my_bounds = my_polygon.bounds
    max_x = int((my_bounds[2] - my_bounds[0]) // default_distance)
    max_y = int((my_bounds[3] - my_bounds[1]) // default_distance)
    for i in range(max_x):
        for j in range(max_y):
            if random.random() < skip_rate:
                continue
            x = my_bounds[0] + i * default_distance + random.uniform(-default_distance/3., default_distance/3.)
            y = my_bounds[1] + j * default_distance + random.uniform(-default_distance/3., default_distance/3.)
            my_point = shg.Point(x, y)
            if prep_geom.contains(my_point):
                my_random_points.append(my_point)
    return my_random_points


def _random_trees_in_area(my_polygon: shg.Polygon, prep_geom, city_blocks: Set[CityBlock],
                          default_distance: int, skip_rate: float) -> List[shg.Point]:
    """Creates random trees in an area respecting the presence of buildings.

    The trees are geometrically tested against the boundary box of buildings (not the whole tree, just the centre).
    NB: in parks trees are often around open spaces and not just randomly distributed - this heuristic does
    not take such things into account.
    """
    my_random_points = _generate_random_tree_points_in_polygon(my_polygon, prep_geom, default_distance, skip_rate)
    # now check against buildings
    if not my_random_points:
        return my_random_points

    # find the city blocks, which might have buildings which could interfere
    test_list = set()
    for city_block in city_blocks:
        if not prep_geom.disjoint(city_block.geometry):
            test_list.add(city_block)
    final_points = list()
    for point in my_random_points:
        if not _test_point_in_building(point, test_list, 3.0):
            final_points.append(point)
    return final_points


def _process_osm_tree_row(nodes_dict, ways_dict, trees: List[Tree], coords_transform: co.Transformation,
                          fg_elev: utilities.FGElev) -> None:
    """Trees in a row as mapped in OSM (natural=tree_row).

    NB: extends the existing list of trees from the input parameter.
    """
    potential_trees = list()
    for way in list(ways_dict.values()):
        my_geometry = way.line_string_from_osm_way(nodes_dict, coords_transform)
        if my_geometry.length / len(way.refs) > parameters.C2P_TREES_MAX_AVG_DIST_TREES_ROW:
            for i in range(0, int(my_geometry.length // parameters.C2P_TREES_DIST_TREES_ROW_CALCULATED)):
                my_point = my_geometry.interpolate(i * parameters.C2P_TREES_DIST_TREES_ROW_CALCULATED)
                my_id = op.get_next_pseudo_osm_id(op.OSMFeatureType.generic_node)
                elev = fg_elev.probe_elev((my_point.x, my_point.y), False)
                tree = Tree(my_id, my_point.x, my_point.y, elev)
                potential_trees.append(tree)
            # and then always the last node
            node = nodes_dict[way.refs[-1]]
            potential_trees.append(Tree.tree_from_node(node, coords_transform, fg_elev))
        else:
            for ref in way.refs:
                node = nodes_dict[ref]
                potential_trees.append(Tree.tree_from_node(node, coords_transform, fg_elev))
    _extend_trees_if_dist_ok(potential_trees, trees)


def _process_osm_trees_lined(nodes_dict, ways_dict, trees: List[Tree], coords_transform: co.Transformation,
                             fg_elev: utilities.FGElev) -> None:
    """Trees in a line as mapped in OSM (tree_lined=*).

    NB: extends the existing list of trees from the input parameter.
    """
    potential_trees = list()
    for way in list(ways_dict.values()):
        if s.K_NATURAL in way.tags and way.tags[s.K_NATURAL] == s.V_TREE_ROW:
            continue  # was already processed in _process_osm_tree_row()
        tag_value = way.tags[s.K_TREE_LINED]
        if tag_value == s.V_NO:
            continue
        orig_line = way.line_string_from_osm_way(nodes_dict, coords_transform)
        tree_lines = list()
        if tag_value != s.V_RIGHT:
            line_geoms = orig_line.parallel_offset(4.0, 'left')
            if isinstance(line_geoms, shg.LineString):
                tree_lines.append(line_geoms)
            elif isinstance(line_geoms, shg.MultiLineString):
                for geom in line_geoms.geoms:
                    tree_lines.append(geom)
        if tag_value != s.V_LEFT:
            line_geoms = orig_line.parallel_offset(4.0, 'right')
            if isinstance(line_geoms, shg.LineString):
                tree_lines.append(line_geoms)
            elif isinstance(line_geoms, shg.MultiLineString):
                for geom in line_geoms.geoms:
                    tree_lines.append(geom)
        for my_line in tree_lines:
            for i in range(0, int(my_line.length // parameters.C2P_TREES_DIST_TREES_ROW_CALCULATED) - 1):
                # i+0.5 such that start and end no direct tree -> often connect to other tree_lines or itself
                my_point = my_line.interpolate((i + 0.5) * parameters.C2P_TREES_DIST_TREES_ROW_CALCULATED)
                my_id = op.get_next_pseudo_osm_id(op.OSMFeatureType.generic_node)
                elev = fg_elev.probe_elev((my_point.x, my_point.y), False)
                tree = Tree(my_id, my_point.x, my_point.y, elev)
                potential_trees.append(tree)
    _extend_trees_if_dist_ok(potential_trees, trees)


def _extend_trees_if_dist_ok(potential_trees: List[Tree], trees: List[Tree]) -> None:
    """Extend the existing list of trees with new trees if the new trees have a minimal dest from the existing ones."""
    for a_tree in reversed(potential_trees):
        for other_tree in trees:
            if co.calc_distance_local(a_tree.x, a_tree.y, other_tree.x, other_tree.y) \
                    < parameters.C2P_TREES_DIST_MINIMAL:
                potential_trees.remove(a_tree)
                break
    trees.extend(potential_trees)


def _write_trees_in_list(coords_transform: co.Transformation, material_name: str,
                         trees: List[Tree], stg_manager: stg_io2.STGManager) -> None:
    file_shader = stg_manager.prefix + "_" + material_name + "_trees_shader.txt"
    path_to_stg = stg_manager.add_tree_list(file_shader, material_name, coords_transform.anchor, 0.)
    try:
        with open(os.path.join(path_to_stg, file_shader), 'w') as shader:
            for t in trees:
                line = '{:.1f} {:.1f} {:.1f}'.format(-t.y, t.x, t.elev)
                shader.write(line)
                shader.write('\n')
    except IOError as exc:
        logging.warning('Could not write trees in list to file %s', exc)
    logging.info("Total number of shader trees written to a tree_list: %d", len(trees))


def _test_point_in_building(point: shg.Point, city_blocks: Set[CityBlock], min_dist: float) -> bool:
    """Tests whether a point is within a building respectively not at least min_distance away.
    The use of CityBlocks should speed up the process considerably by using fewer geometric calculations."""
    for city_block in city_blocks:
        if city_block.geometry.bounds[0] < point.x < city_block.geometry.bounds[2] and \
                city_block.geometry.bounds[1] < point.y < city_block.geometry.bounds[3]:
            # point is within bounds of city block - now check each building of city block
            for b in city_block.osm_buildings:
                if b.geometry.bounds[0] - min_dist < point.x < b.geometry.bounds[2] + min_dist and \
                        b.geometry.bounds[1] - min_dist < point.y < b.geometry.bounds[3] + min_dist:
                    return True  # return immediately
    return False


def _prepare_city_blocks(the_buildings: List[bl.Building], coords_transform: co.Transformation) -> Set[CityBlock]:
    """Extracts all city blocks from existing buildings.
    If the zone linked to a building is not a CityBlock, then use a generic one spanning the whole tile.
    """
    city_blocks = set()
    bounds = Bounds.create_from_parameters(coords_transform)
    bounding_box = shg.box(bounds.min_point.x, bounds.min_point.y, bounds.max_point.x, bounds.max_point.y)
    remaining_block = CityBlock(0, bounding_box, e.BuildingZoneType.special_processing)
    if the_buildings != None:
        for building in the_buildings:
            if building.zone:
                if isinstance(building.zone, CityBlock):
                    city_blocks.add(building.zone)
                else:
                    remaining_block.relate_building(building)
    city_blocks.add(remaining_block)

    # in buildings._clean_building_zones_dangling_children there is also come cleanup of not valid buildings
    # However, that uses significant runtime and e.g. for Edinburgh out of ca. 110k buildings only ca.
    # 150 would be removed - which does not matter for what buildings are used here (collision detection)

    return city_blocks


def process_trees(coords_transform: co.Transformation, fg_elev: utilities.FGElev, the_buildings: List[bl.Building],
                  file_lock: mp.Lock = None):
    if parameters.C2P_PROCESS_TREES and parameters.FLAG_AFTER_2020_3:
        city_blocks = _prepare_city_blocks(the_buildings, coords_transform)
        logging.info("Working with %i city blocks", len(city_blocks))

        # start with trees tagged as node (we are not taking into account the few areas mapped as tree (wrong tagging)
        osm_nodes_dict = op.fetch_db_nodes_isolated(list(), [s.KV_NATURAL_TREE])
        trees = _process_osm_trees_nodes(osm_nodes_dict, coords_transform, fg_elev)
        logging.info("Number of manually mapped trees found: {}".format(len(trees)))

        # add trees in a row
        osm_way_result = op.fetch_osm_db_data_ways_key_values([s.KV_NATURAL_TREE_ROW])
        osm_nodes_dict = osm_way_result.nodes_dict
        osm_ways_dict = osm_way_result.ways_dict
        _process_osm_tree_row(osm_nodes_dict, osm_ways_dict, trees, coords_transform, fg_elev)
        logging.info("Total number of trees after trees in rows etc.: {}".format(len(trees)))
        # add tree_lined=* (https://wiki.openstreetmap.org/wiki/Key:tree_lined)
        osm_way_result = op.fetch_osm_db_data_ways_keys([s.K_TREE_LINED])
        osm_nodes_dict = osm_way_result.nodes_dict
        osm_ways_dict = osm_way_result.ways_dict
        _process_osm_trees_lined(osm_nodes_dict, osm_ways_dict, trees, coords_transform, fg_elev)
        logging.info("Total number of trees after trees in line etc.: {}".format(len(trees)))

        # add trees to potential areas
        # s.KV_LANDUSE_RECREATION_GROUND would be a possibility, but often has also swimming pools etc.
        # making it a bit difficult
        osm_way_result = op.fetch_osm_db_data_ways_key_values([s.KV_LEISURE_PARK])
        osm_nodes_dict = osm_way_result.nodes_dict
        osm_ways_dict = osm_way_result.ways_dict
        parks = list()
        for way in list(osm_ways_dict.values()):
            my_geometry = way.polygon_from_osm_way(osm_nodes_dict, coords_transform)
            if my_geometry and my_geometry.area > parameters.C2P_TREES_PARK_MIN_SIZE:
                parks.append(my_geometry)
        _process_osm_trees_parks(parks, trees, city_blocks, fg_elev)

        # garden_trees - key = TreeType, value = list of trees of TreeType
        garden_trees = _process_osm_trees_gardens(city_blocks, parks, fg_elev)
        logging.info("Total number of trees after artificial generation: {}".format(len(trees)))

        stg_manager = stg_io2.STGManager(parameters.get_output_path(), stg_io2.SceneryType.trees, TREES_MAGIC,
                                         parameters.PREFIX)
        if trees:
            _write_trees_in_list(coords_transform, e.TreeType.default.value, trees, stg_manager)
        for tree_type, tree_list in garden_trees.items():
            _write_trees_in_list(coords_transform, tree_type.value, tree_list, stg_manager)

        stg_manager.write(file_lock)
    else:
        logging.info('No trees generated due to parameter setup')
