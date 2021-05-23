"""
Parser for OpenStreetMap data based on standard Python SAX library for processing XML.
Other formats than XML are not available for parsing OSM input data.
Use a tool like Osmosis to pre-process data.

@author: vanosten
"""

from collections import namedtuple
from enum import IntEnum, unique
import logging
import multiprocessing as mp
from typing import Dict, List, Optional, Tuple
import time
import unittest

import networkx as nx
import psycopg2
import shapely.geometry as shg

from osm2city import parameters
from osm2city.utils.coordinates import Transformation


PSEUDO_OSM_ID = -1  # For those nodes and ways, which get added as part of processing. Not written back to OSM.


@unique
class OSMFeatureType(IntEnum):
    building_relation = 0
    building_generated = 1
    building_owbb = 3
    landuse = 5
    road = 6
    pylon_way = 7
    generic_node = 8
    generic_way = 9


def get_next_pseudo_osm_id(osm_feature: OSMFeatureType) -> int:
    """Constructs a pseudo id for OSM as a negative value and therefore never a real OSM value.

    Depending on which OSM feature is requesting, a different number range is returned.
    In order not to have conflicts between different processes in multiprocessing, the number range is adapted.

    In Osmosis Ids have to be sorted from low to high.
    The highest ID value will be different for each type of object (nodes, ways and relations)
    The IDs are all 64 bit signed integers at the moment, so have a theoretical limit of 2^63-1
    or 9,223,372,036,854,775,807
    See http://gis.stackexchange.com/questions/17242/what-is-the-highest-possible-value-of-osm-id
    """

    global PSEUDO_OSM_ID
    PSEUDO_OSM_ID -= 1
    type_factor = 1000000000000 * osm_feature.value
    pid_factor = mp.current_process().pid * 1000000
    return PSEUDO_OSM_ID + type_factor + pid_factor


class OSMElement(object):
    __slots__ = ('osm_id', 'tags')

    def __init__(self, osm_id: int) -> None:
        self.osm_id = osm_id
        self.tags = {}

    def add_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def __str__(self) -> str:
        return "<%s OSM_ID %i at %s>" % (type(self).__name__, self.osm_id, hex(id(self)))


def combine_tags(first_tags: Dict[str, str], second_tags: Dict[str, str]) -> Dict[str, str]:
    """Combines the tags of the first with the second, in such a way that the first wins in case of same keys"""
    if len(second_tags) == 0:
        return first_tags.copy()
    if len(first_tags) == 0:
        return second_tags.copy()

    combined_tags = first_tags.copy()
    for key, value in second_tags.items():
        if key not in combined_tags:
            combined_tags[key] = value
    return combined_tags


class Node(OSMElement):
    __slots__ = ('lat', 'lon', 'msl', 'v_add', 'layers')  # the last three are written from roads.py

    def __init__(self, osm_id: int, lat: float, lon: float) -> None:
        OSMElement.__init__(self, osm_id)
        self.lat = lat  # float value
        self.lon = lon  # float value
        # the following are mostly used in roads and linear objects/bridges
        self.msl = None  # metres above sea level (from FGElev, but might get updated)
        self.v_add = 0.  # vertical add, such that there is some smoothness of roads despite bumpiness of FG elevation
        self.layers = dict()  # key=way, value = int [the higher the number, the more on top])

    def layer_for_way(self, way) -> int:
        """Returns -1 if there is no entry in layers dict for the given way"""
        if way in self.layers:
            return self.layers[way]

        return -1

    @property
    def lon_lat_tuple(self) -> Tuple[float, float]:
        return self.lon, self.lat

    def __str__(self):
        return 'Node with osm_id: {}'.format(self.osm_id)


class Way(OSMElement):
    __slots__ = ('refs', 'pseudo_osm_id', 'was_split_at_end')

    def __init__(self, osm_id: int) -> None:
        OSMElement.__init__(self, osm_id)
        self.refs = []
        self.pseudo_osm_id = 0  # can be assigned if existing way gets split
        # if this way was split at the end - important for power lines, railway lines etc.
        # see also method split_way_at_boundary
        self.was_split_at_end = False

    def add_ref(self, ref: int) -> None:
        self.refs.append(ref)

    def polygon_from_osm_way(self, nodes_dict: Dict[int, Node], my_coord_transformator: Transformation) \
            -> Optional[shg.Polygon]:
        """Creates a shapely polygon in local coordinates. Or None is something is not valid."""
        my_coordinates = list()
        for ref in self.refs:
            if ref in nodes_dict:
                my_node = nodes_dict[ref]
                x, y = my_coord_transformator.to_local((my_node.lon, my_node.lat))
                my_coordinates.append((x, y))
        if len(my_coordinates) >= 3:
            my_polygon = shg.Polygon(my_coordinates)
            if not my_polygon.is_valid:  # it might be self-touching or self-crossing polygons
                clean = my_polygon.buffer(0)  # cf. http://toblerity.org/shapely/manual.html#constructive-methods
                if clean.is_valid:
                    my_polygon = clean  # it is now a Polygon or a MultiPolygon
            if my_polygon.is_valid and not my_polygon.is_empty:
                return my_polygon
        return None

    def line_string_from_osm_way(self, nodes_dict: Dict[int, Node], transformer: Transformation) \
            -> Optional[shg.LineString]:
        my_coordinates = list()
        for ref in self.refs:
            if ref in nodes_dict:
                my_node = nodes_dict[ref]
                x, y = transformer.to_local((my_node.lon, my_node.lat))
                my_coordinates.append((x, y))
        if len(my_coordinates) >= 2:
            my_geometry = shg.LineString(my_coordinates)
            if my_geometry.is_valid and not my_geometry.is_empty:
                return my_geometry
        return None

    def simplify(self, nodes_dict: Dict[int, Node], transformer: Optional[Transformation],
                 tolerance: float) -> None:
        """Simplifies a Way. The only topology that is preserved are the start and end points.
        If the way is e.g. a road and some notes inside the way are related to other roads, then those
        intersections will topologically go away, since all inner nodes will be new."""
        if len(self.refs) < 3:
            return
        if transformer is None:
            lon_1 = nodes_dict[self.refs[0]].lon
            lon_2 = nodes_dict[self.refs[-1]].lon
            lat_1 = nodes_dict[self.refs[0]].lat
            lat_2 = nodes_dict[self.refs[-1]].lat
            transformer = Transformation((lon_2 - (lon_2 - lon_1) / 2, lat_2 - (lat_2 - lat_1) / 2))
        # create a line_string in local coordinates
        line_string = self.line_string_from_osm_way(nodes_dict, transformer)
        # simplify it
        line_simplified = line_string.simplify(tolerance, preserve_topology=True)
        # port the simplification back
        old_refs = self.refs[:]
        self.refs = list()
        line_coords = list(line_simplified.coords)
        for i, x_y in enumerate(line_coords):
            if i == 0:
                self.refs.append(old_refs[0])
            elif i == len(line_coords) - 1:
                self.refs.append(old_refs[-1])
            else:
                lon, lat = transformer.to_global((x_y[0], x_y[1]))
                new_node = Node(get_next_pseudo_osm_id(OSMFeatureType.generic_node), lat, lon)
                nodes_dict[new_node.osm_id] = new_node
                self.refs.append(new_node.osm_id)

    def is_closed(self) -> bool:
        if len(self.refs) < 3:
            return False
        if self.refs[0] == self.refs[-1]:
            return True
        return False

    def __str__(self):
        return 'Way with osm_id: {}'.format(self.osm_id)


class Member(object):
    __slots__ = ('ref', 'type_', 'role')

    def __init__(self, ref: int, type_: str, role: str) -> None:
        self.ref = ref
        self.type_ = type_
        self.role = role


class Relation(OSMElement):
    __slots__ = 'members'

    def __init__(self, osm_id: int):
        OSMElement.__init__(self, osm_id)
        self.members = []

    def add_member(self, member: Member) -> None:
        self.members.append(member)

    def __str__(self):
        return 'Relation with osm_id: {}'.format(self.osm_id)


def refs_to_ring(coords_transform: Transformation, refs: List[int],
                 nodes_dict: Dict[int, Node]) -> shg.LinearRing:
    """Accept a list of OSM refs, return a linear ring."""
    coords = []
    for ref in refs:
        c = nodes_dict[ref]
        coords.append(coords_transform.to_local((c.lon, c.lat)))

    ring = shg.polygon.LinearRing(coords)
    return ring


def closed_ways_from_multiple_ways(way_parts: List[Way]) -> List[Way]:
    """Create closed ways from multiple not closed ways where possible.
    See http://wiki.openstreetmap.org/wiki/Relation:multipolygon.
    If parts of ways cannot be used, they just get disregarded.
    The new Ways gets the osm_id from a way reused and all tags removed.
    """
    closed_ways = list()

    graph = nx.Graph()
    for way in way_parts:
        for i in range(len(way.refs) - 1):
            graph.add_edge(way.refs[i], way.refs[i + 1])

    cycles = nx.cycle_basis(graph)
    for cycle in cycles:  # we just reuse ways - it does not really matter
        way = Way(0)
        way.refs = cycle
        way.refs.append(way.refs[0])  # cycles from networkx are not closed
        closed_ways.append(way)

        # now make sure we have the original tags
        way.tags = dict()
        ways_set = set()
        for node in cycle:
            for wp in way_parts:
                if node in wp.refs:
                    ways_set.add(wp)
                    if way.osm_id == 0:
                        way.osm_id = wp.osm_id  # reuse the id from an existing way
        for wp in ways_set:
            for key, value in wp.tags.items():
                if key not in way.tags:
                    way.tags[key] = value

    return closed_ways


OSMReadResult = namedtuple("OSMReadResult", "nodes_dict, ways_dict, relations_dict, rel_nodes_dict, rel_ways_dict")


def parse_length(str_length: str) -> float:
    """
    Transform length to meters if not yet default. Input is a string, output is a float.
    If the string cannot be parsed, then 0 is returned.
    Length (and width/height) in OSM is per default meters cf. OSM Map Features / Units.
    Possible units can be "m" (metre), "km" (kilometre -> 0.001), "mi" (mile -> 0.00062137) and
    <feet>' <inch>" (multiply feet by 12, add inches and then multiply by 0.0254).
    Theoretically there is a blank between the number and the unit, practically there might not be.
    """
    _processed = str_length.strip().lower()
    _processed = _processed.replace(',', '.')  # decimals are sometimes with comma (e.g. in European languages)
    if _processed.endswith("km"):
        _processed = _processed.rstrip("km").strip()
        _factor = 1000
    elif _processed.endswith("m"):
        _processed = _processed.rstrip("m").strip()
        _factor = 1
    elif _processed.endswith("mi"):
        _processed = _processed.rstrip("mi").strip()
        _factor = 1609.344
    elif _processed.endswith('ft'):
        _processed = _processed.rstrip('ft').strip()
        _factor = 0.3048
    elif _processed.endswith('yrd'):
        _processed = _processed.rstrip('yrd').strip()
        _factor = 0.9144
    elif "'" in _processed:
        _processed = _processed.replace('"', '')
        _split = _processed.split("'", 1)
        _factor = 0.0254
        if is_parsable_float(_split[0]):
            _f_length = float(_split[0])*12
            _processed = str(_f_length)
            if 2 == len(_split):
                if is_parsable_float(_split[1]):
                    _processed = str(_f_length + float(_split[1]))
    else:  # assumed that no unit characters are in the string
        _factor = 1.0
    if is_parsable_float(_processed):
        return float(_processed) * _factor
    else:
        logging.warning('Unable to parse for length from value: %s', str_length)
        return 0.0


def parse_direction(str_dir: str) -> float:
    _processed = str_dir.strip().lower()
    if _processed == 'n':
        _processed = 0
    elif _processed == 'ne':
        _processed = 45
    elif _processed == 'e':
        _processed = 90
    elif _processed == 'se':
        _processed = 135
    elif _processed == 's':
        _processed = 180
    elif _processed == 'sw':
        _processed = 225
    elif _processed == 'w':
        _processed = 270
    elif _processed == 'nv':
        _processed = 315
    if is_parsable_float(_processed):
        return float(_processed)
    else:
        logging.warning('Unable to parse for direction from value: %s', str_dir)
        return 0.0


def parse_generator_output(str_output: str) -> float:
    """Transforms energy output from generators to a float value of Watt.
    See https://wiki.openstreetmap.org/wiki/Key:generator:output"""
    _processed = str_output.strip().lower()
    if _processed == "yes":
        return 0
    _factor = 0.
    if _processed.endswith("gw"):
        _processed = _processed.rstrip("gw").strip()
        _factor = 1000000000
    elif _processed.endswith("mw"):
        _processed = _processed.rstrip("mw").strip()
        _factor = 1000000
    elif _processed.endswith("kw"):
        _processed = _processed.rstrip("kw").strip()
        _factor = 1000
    elif _processed.endswith("w"):
        _processed = _processed.rstrip("w").strip()
        _factor = 1.
    if is_parsable_float(_processed):
        return float(_processed) * _factor
    else:
        logging.warning('Unable to parse for generator output from value: %s', str_output)
        return 0.


def parse_multi_int_values(str_value: str) -> int:
    """Parse int values for tags, where values can be separated by semi-colons.
    E.g. for building levels, 'cables' and 'voltage' for power cables, which can have multiple values.
    If only one value is present, then that value is used, otherwise the max value as int.
    Separator for multiple values is ';'.
    If it cannot be parsed, then 0 is returned.
    For 'cables' it is assumed that if several values are submitted, then the largest number are the real cables
    and not other stuff - see http://wiki.openstreetmap.org/wiki/Key:cables how this tag should be used (never multi!).
    For 'voltage it is assumed that the highest value determines the type of pylons etc."""
    sub_values = str_value.split(';')
    return_value = 0.0
    for sub_value in sub_values:
        if is_parsable_float(sub_value.strip()):
            return_value = max(return_value, float(sub_value.strip()))
    return int(return_value)


def is_parsable_float(str_float: str) -> bool:
    try:
        float(str_float)
        return True
    except ValueError:
        return False


def _parse_hstore_tags(tags_string: str, osm_id: int) -> Dict[str, str]:
    """Parses the content of a string representation of a PostGIS hstore content for tags.
    Returns a dict of key value pairs as string."""
    tags_dict = dict()
    if tags_string.strip():  # else we return the empty dict as is
        elements = tags_string.strip().split('", "')
        for element in elements:
            if element.strip():
                subs = element.strip().split("=>")
                if len(subs) in [2, 3] and len(subs[0].strip()) > 1:
                    key = subs[0].strip().strip('"')
                    if key not in tags_dict:
                        if len(subs) == 2 and len(subs[1].strip()) > 1:
                            tags_dict[key] = subs[1].strip().strip('"')
                        elif len(subs) == 3 and len((subs[1] + subs[2]).strip()) > 1:
                            tags_dict[key] = (subs[1] + '=>' + subs[2]).strip('"')
                        else:
                            msg = "hstore for osm_id={} has not valid key/value pair: '{}' in '{}'.".format(osm_id,
                                                                                                            subs,
                                                                                                            tags_string)
                            logging.warning(msg)

                    else:
                        message = "hstore for osm_id={} has same key twice: key={}, tags='{}'.".format(osm_id,
                                                                                                       key,
                                                                                                       tags_string)
                        logging.warning(message)
                else:
                    message = "hstore for osm_id={} has not valid key/value pair: '{}' in '{}'.".format(osm_id,
                                                                                                        subs,
                                                                                                        tags_string)
                    logging.warning(message)
    return tags_dict


def fetch_db_way_data(req_way_keys: List[str], req_way_key_values: List[str], db_connection) -> Dict[int, Way]:
    """Fetches Way objects out of database given required tag keys and boundary in parameters."""
    query = """SELECT id, tags, nodes
    FROM ways AS w
    WHERE
    """
    query += construct_tags_query(req_way_keys, req_way_key_values)
    query += " AND "
    query += construct_intersect_bbox_query()
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    ways_dict = dict()
    for result in result_tuples:
        my_way = Way(result[0])
        my_way.tags = _parse_hstore_tags(result[1], my_way.osm_id)
        my_way.refs = result[2]
        ways_dict[my_way.osm_id] = my_way

    return ways_dict


def fetch_db_nodes_for_way(req_way_keys: List[str], req_way_key_values: List[str], db_connection) -> Dict[int, Node]:
    """Fetches Node objects for ways out of database given same constraints as for Way.
    Constraints for way: see fetch_db_way_data"""
    query = """SELECT n.id, ST_X(n.geom) as lon, ST_Y(n.geom) as lat
    FROM ways AS w, way_nodes AS r, nodes AS n
    WHERE
    r.way_id = w.id
    AND r.node_id = n.id
    AND """
    query += construct_tags_query(req_way_keys, req_way_key_values)
    query += " AND "
    query += construct_intersect_bbox_query()
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    nodes_dict = dict()
    for result in result_tuples:
        my_node = Node(result[0], result[2], result[1])
        nodes_dict[my_node.osm_id] = my_node

    return nodes_dict


def fetch_db_nodes_isolated(req_node_keys: List[str], req_node_key_values: List[str]) -> Dict[int, Node]:
    """Fetches Node objects isolated without relation to way etc."""
    start_time = time.time()

    db_connection = make_db_connection()

    query = """SELECT n.id, ST_X(n.geom) as lon, ST_Y(n.geom) as lat, n.tags
    FROM nodes AS n
    WHERE """
    query += construct_tags_query(req_node_keys, req_node_key_values, table_alias="n")
    query += " AND "
    query += construct_intersect_bbox_query(is_way=False)
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    nodes_dict = dict()
    for result in result_tuples:
        my_node = Node(result[0], result[2], result[1])
        my_node.tags = _parse_hstore_tags(result[3], my_node.osm_id)
        nodes_dict[my_node.osm_id] = my_node
    db_connection.close()

    used_list = req_node_key_values
    if len(req_node_keys) > 0:
        used_list = req_node_keys
    logging.info("Reading OSM node data for {0!s} from db took {1:.4f} seconds.".format(used_list,
                                                                                        time.time() - start_time))

    return nodes_dict


def fetch_all_query_into_tuple(query: str, db_connection) -> List[Tuple]:
    """Given a query string and a db connection execute fetch all and return the result as a list of tuples"""
    cur = db_connection.cursor()
    logging.debug("Query string for execution in database: " + query)
    cur.execute(query)
    return cur.fetchall()


def _fetch_osm_db_data_ways(required: List[str], is_key_values: bool = False) -> OSMReadResult:
    """Given a list of required keys or key/value pairs get the ways plus the linked nodes from an OSM database."""
    start_time = time.time()

    db_connection = make_db_connection()
    if is_key_values:
        ways_dict = fetch_db_way_data(list(), required, db_connection)
        nodes_dict = fetch_db_nodes_for_way(list(), required, db_connection)
    else:
        ways_dict = fetch_db_way_data(required, list(), db_connection)
        nodes_dict = fetch_db_nodes_for_way(required, list(), db_connection)
    db_connection.close()

    logging.info("Reading OSM way data for {0!s} from db took {1:.4f} seconds.".format(required,
                                                                                       time.time() - start_time))
    return OSMReadResult(nodes_dict=nodes_dict, ways_dict=ways_dict,
                         relations_dict=None, rel_nodes_dict=None, rel_ways_dict=None)


def fetch_osm_db_data_ways_key_values(req_key_values: List[str]) -> OSMReadResult:
    """Given a list of required key/value pairs get the ways plus the linked nodes from an OSM database."""
    return _fetch_osm_db_data_ways(req_key_values, True)


def fetch_osm_db_data_ways_keys(req_keys: List[str]) -> OSMReadResult:
    """Given a list of required keys get the ways plus the linked nodes from an OSM database."""
    return _fetch_osm_db_data_ways(req_keys, False)


def fetch_osm_db_data_relations_keys(input_read_result: OSMReadResult, first_part: str,
                                     relation_debug_string: str) -> OSMReadResult:
    """Updates an OSMReadResult with relation data based on required keys"""
    start_time = time.time()

    db_connection = make_db_connection()

    # common subquery
    sub_query = first_part + " AND r.id = rm.relation_id"
    sub_query += " AND rm.member_type = 'W'"
    sub_query += " AND rm.member_id = w.id"
    sub_query += " AND "
    sub_query += construct_intersect_bbox_query()

    # == Relations and members and ways
    # Getting related way data might add a bit of  volume, but reduces number of queries and might be seldom that
    # same way is in different relations for buildings.
    query = """SELECT r.id, r.tags, rm.member_id, rm.member_role, w.nodes, w.tags
    FROM relations AS r, relation_members AS rm, ways AS w
    WHERE
    """
    query += sub_query
    query += " ORDER BY rm.relation_id, rm.sequence_id"
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    relations_dict = dict()
    rel_ways_dict = dict()

    for result in result_tuples:
        relation_id = result[0]
        member_id = result[2]
        if relation_id not in relations_dict:
            relation = Relation(relation_id)
            relation.tags = _parse_hstore_tags(result[1], relation_id)
            relations_dict[relation_id] = relation
        else:
            relation = relations_dict[relation_id]

        my_member = Member(member_id, "way", result[3])
        relation.add_member(my_member)

        if member_id not in rel_ways_dict:
            my_way = Way(member_id)
            my_way.refs = result[4]
            my_way.tags = _parse_hstore_tags(result[5], my_way.osm_id)
            rel_ways_dict[my_way.osm_id] = my_way

    # == Nodes for the ways
    query = """SELECT n.id, ST_X(n.geom) as lon, ST_Y(n.geom) as lat
    FROM relations AS r, relation_members AS rm, ways AS w, way_nodes AS wn, nodes AS n
    WHERE
    """
    query += sub_query
    query += " AND wn.way_id = w.id"
    query += " AND wn.node_id = n.id"
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    rel_nodes_dict = dict()
    for result in result_tuples:
        my_node = Node(result[0], result[2], result[1])
        rel_nodes_dict[my_node.osm_id] = my_node

    logging.info("Reading OSM relation data for {0!s} from db took {1:.4f} seconds.".format(relation_debug_string,
                                                                                            time.time() - start_time))

    return OSMReadResult(nodes_dict=input_read_result.nodes_dict, ways_dict=input_read_result.ways_dict,
                         relations_dict=relations_dict, rel_nodes_dict=rel_nodes_dict, rel_ways_dict=rel_ways_dict)


def fetch_osm_db_data_relations_places(input_read_result: OSMReadResult) -> OSMReadResult:
    first_part = "((r.tags @> 'type=>multipolygon' OR r.tags @> 'type=>boundary')"
    first_part += " AND (r.tags @> 'place=>city' OR r.tags @> 'place=>town'))"
    return fetch_osm_db_data_relations_keys(input_read_result, first_part, 'places')


def fetch_osm_db_data_relations_buildings(input_read_result: OSMReadResult) -> OSMReadResult:
    first_part = "((r.tags @> 'type=>multipolygon'"
    first_part += " AND " + construct_tags_query(["building", "building:part"], list(), "r")
    first_part += ") OR r.tags @> 'type=>building')"
    return fetch_osm_db_data_relations_keys(input_read_result, first_part, 'buildings')


def fetch_osm_db_data_relations_riverbanks(input_read_result: OSMReadResult) -> OSMReadResult:
    first_part = "(r.tags @> 'type=>multipolygon'"
    first_part += " AND r.tags @> 'waterway=>riverbank')"
    return fetch_osm_db_data_relations_keys(input_read_result, first_part, 'riverbanks')


def fetch_osm_db_data_relations_routes(input_read_result: OSMReadResult) -> OSMReadResult:
    first_part = "(r.tags @> 'type=>route'"
    first_part += " AND r.tags @> 'route=>ferry')"
    return fetch_osm_db_data_relations_keys(input_read_result, first_part, 'ferry_route')


def make_db_connection():
    """"Create connection to the database based on parameters."""
    connection = psycopg2.connect(database=parameters.DB_NAME, host=parameters.DB_HOST, port=parameters.DB_PORT,
                                  user=parameters.DB_USER, password=parameters.DB_USER_PASSWORD)
    return connection


def construct_intersect_bbox_query(is_way: bool = True) -> str:
    """Constructs the part of a sql where clause, which constrains to bounding box."""
    query_part = "ST_Intersects("
    if is_way:
        query_part += "w.bbox"
    else:
        query_part += "n.geom"
    query_part += ", ST_SetSRID(ST_MakeBox2D(ST_Point({}, {}), ST_Point({}, {})), 4326))"
    return query_part.format(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                             parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)


def construct_tags_query(req_tag_keys: List[str], req_tag_key_values: List[str], table_alias: str = "w") -> str:
    """Constructs the part of a sql WHERE clause, which constrains the result based on required tag keys.
    In req_tag_keys at least one of the key needs to be present in the tags of a given record.
    In req_tag_key_values at least one key/value pair must be present (e.g. 'railway=>platform') - the key
    must be separated without blanks from the value by a '=>'."""
    tags_query = ""
    if len(req_tag_keys) == 1:
        tags_query += table_alias + ".tags ? '" + req_tag_keys[0] + "'"
    elif len(req_tag_keys) > 1:
        is_first = True
        tags_query += table_alias + ".tags ?| ARRAY["
        for key in req_tag_keys:
            if is_first:
                is_first = False
            else:
                tags_query += ", "
            tags_query += "'" + key + "'"
        tags_query += "]"

    if req_tag_key_values:
        if tags_query:
            tags_query += " AND "
        if len(req_tag_key_values) == 1:
            tags_query += table_alias + ".tags @> '" + req_tag_key_values[0] + "'"
        else:
            tags_query += "("
            is_first = True
            for key_value in req_tag_key_values:
                if is_first:
                    is_first = False
                else:
                    tags_query += " OR "
                tags_query += table_alias + ".tags @> '" + key_value + "'"
            tags_query += ")"

    return tags_query


def split_way_at_boundary(nodes_dict: Dict[int, Node], complete_way: Way, clipping_border: shg.Polygon,
                          osm_feature: OSMFeatureType) -> List[Way]:
    """Splits a way (e.g. road) at the clipping border into 0 to n ways.
    A way can be totally inside a boundary, totally outside a boundary, intersect once or several times.
    Splitting is tested at existing nodes of the way. A split way's first node is always inside the boundary.
    A split way's last point can be inside the boundary (the last node of the original way) or
    the first node outside of the boundary (such that across tile boundaries there is a continuation)."""
    split_ways = list()
    current_way = Way(complete_way.osm_id)  # the first (and maybe only) does not get a pseudo_id
    current_way.tags = complete_way.tags
    previous_inside = False
    for node_ref in complete_way.refs:
        current_node = nodes_dict[node_ref]
        if clipping_border.contains(shg.Point(current_node.lon, current_node.lat)):
            current_way.refs.append(node_ref)
            previous_inside = True
        else:
            if previous_inside:
                current_way.refs.append(node_ref)
                current_way.was_split_at_end = True
                if len(current_way.refs) >= 2:
                    split_ways.append(current_way)
                current_way = Way(complete_way.osm_id)
                current_way.tags = complete_way.tags
                current_way.pseudo_osm_id = get_next_pseudo_osm_id(osm_feature)
                previous_inside = False
            # nothing to do if previous also outside

    if len(current_way.refs) >= 2:
        split_ways.append(current_way)
    return split_ways


def create_key_value_pair(key: str, value: str) -> str:
    """A string combining a key and a value for query in PostGIS"""
    return '{}=>{}'.format(key, value)


# ================ UNITTESTS =======================

class TestOSMParser(unittest.TestCase):
    def test_parse_length(self):
        self.assertAlmostEqual(1.2, parse_length(' 1.2 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(1.2, parse_length(' 1,2 '), 2, "Correct number with comma as decimal separator")
        self.assertAlmostEqual(1.2, parse_length(' 1.2 m'), 2, "Correct number with meter unit incl. space")
        self.assertAlmostEqual(1.2, parse_length(' 1.2m'), 2, "Correct number with meter unit without space")
        self.assertAlmostEqual(1200, parse_length(' 1.2 km'), 2, "Correct number with km unit incl. space")
        self.assertAlmostEqual(2092.1472, parse_length(' 1.3mi'), 2, "Correct number with mile unit without space")
        self.assertAlmostEqual(3.048, parse_length("10'"), 2, "Correct number with feet unit without space")
        self.assertAlmostEqual(3.073, parse_length('10\'1"'), 2, "Correct number with feet unit without space")
        self.assertEqual(0, parse_length('m'), "Only valid unit")
        self.assertEqual(0, parse_length('"'), "Only inches, no feet")

    def test_parse_direction(self):
        self.assertAlmostEqual(180.0, parse_direction('s '), 2)
        self.assertAlmostEqual(125.5, parse_direction(' 125.5 '), 2)
        self.assertAlmostEqual(0.0, parse_direction(' foo '), 2)

    def test_parse_generator_output(self):
        self.assertAlmostEqual(0, parse_generator_output(' 2.3 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(2.3, parse_generator_output(' 2.3 W'), 2, "Correct number with Watt unit incl. space")
        self.assertAlmostEqual(2.3, parse_generator_output('2.3W'), 2, "Correct number with Watt unit without space")
        self.assertAlmostEqual(2300, parse_generator_output(' 2.3 kW'), 2, "Correct number with kW unit incl. space")
        self.assertAlmostEqual(2300000, parse_generator_output(' 2.3 MW'), 2, "Correct number with MW unit incl. space")
        self.assertAlmostEqual(300000000, parse_generator_output(' 0.3GW'), 2, "Correct number with GW unit w/o space")
        self.assertAlmostEqual(0, parse_generator_output(' 0.3 XW'), 2, "Correct number with unknown unit")

    def test_parse_multi_int_values(self):
        self.assertEqual(99, parse_multi_int_values(' 99 '), 'Correct value to start with')
        self.assertEqual(0, parse_multi_int_values(' a'), 'Not a number')
        self.assertEqual(0, parse_multi_int_values(' ;'), 'Empty with semicolon')
        self.assertEqual(99, parse_multi_int_values(' 99.1'), 'Float')
        self.assertEqual(88, parse_multi_int_values(' 88; 4'), 'Two valid numbers')
        self.assertEqual(0, parse_multi_int_values(''), 'Empty')

    def test_is_parsable_float(self):
        self.assertFalse(is_parsable_float('1,2'))
        self.assertFalse(is_parsable_float('x'))
        self.assertTrue(is_parsable_float('1.2'))

    def test_parse_hstore_tags(self):
        self.assertEqual(0, len(_parse_hstore_tags('', 1)), "Empty string")
        self.assertEqual(0, len(_parse_hstore_tags('  ', 1)), "Empty truncated string")
        my_dict = _parse_hstore_tags('"foo"=>"goo"', 1)
        self.assertEqual(1, len(my_dict), "One element tags")
        self.assertEqual("goo", my_dict["foo"], "One element tags validate value")
        my_dict = _parse_hstore_tags('"foo"=>"goo", "alpha"=> "1"', 1)
        self.assertEqual(2, len(my_dict), "Two element tags")
        self.assertEqual("1", my_dict["alpha"])
        my_dict = _parse_hstore_tags('"foo"=>"goo", "alpha"=> "1", ', 1)
        self.assertEqual(2, len(my_dict), "Last element empty")
        my_dict = _parse_hstore_tags('"foo"=>"goo", "foo"=> "1"', 1)
        self.assertEqual(1, len(my_dict), "Repeated key ignored")
        my_dict = _parse_hstore_tags('"foo"=>"goo", "foo"=> ""', 1)
        self.assertEqual(1, len(my_dict), "Invalid value ignored")
        my_dict = _parse_hstore_tags('"foo"=>"go,o", "ho,o"=>"i,"', 1)
        self.assertEqual(2, len(my_dict), "Keys and values with comma")
        self.assertEqual("go,o", my_dict["foo"], "Keys and values with comma validate first value")
        self.assertEqual("i,", my_dict["ho,o"], "Keys and values with comma validate first value")
        my_dict = _parse_hstore_tags('"note"=>"parking => rework required", "highway"=>"service"', 1)
        self.assertEqual(2, len(my_dict), '=> inside value')

    def test_closed_ways_from_multiple_ways(self):
        way_unrelated = Way(1)
        way_unrelated.refs = [90, 91]

        way_no_ring0 = Way(2)
        way_no_ring0.refs = [80, 81, 82]
        way_no_ring1 = Way(3)
        way_no_ring1.refs = [80, 83]

        way_a_0 = Way(4)
        way_a_0.refs = [1, 2, 3, 4]
        way_a_0.tags = {'ring0': 'a_0', 'building': 'yes'}
        way_a_1 = Way(5)
        way_a_1.refs = [4, 5, 6, 1]
        way_a_1.tags = {'ring1': 'a_1', 'building': 'yes'}

        way_b_0 = Way(6)
        way_b_0.refs = [11, 12, 13, 14]
        way_b_0.tags = {'ring0': 'b_0', 'building': 'yes'}
        way_b_1 = Way(7)
        way_b_1.refs = [16, 15, 14]
        way_b_1.tags = {'ring1': 'b_1', 'building': 'yes'}
        way_b_2 = Way(8)
        way_b_2.refs = [16, 17, 18, 11]
        way_b_2.tags = {'ring2': 'b_2', 'building': 'yes'}

        closed_ways = closed_ways_from_multiple_ways([way_b_0, way_a_1, way_unrelated, way_a_0, way_b_2, way_no_ring1,
                                                      way_b_1, way_no_ring0])
        self.assertEqual(2, len(closed_ways))

    def test_combine_tags(self):
        first_dict = {'1': '1', '2': '2', '3': '3'}
        second_dict = {'3': '99', '4': '4'}
        combined_tags = combine_tags(first_dict, second_dict)
        self.assertEqual(4, len(combined_tags))
