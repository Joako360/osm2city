# -*- coding: utf-8 -*-
"""
Parser for OpenStreetMap data based on standard Python SAX library for processing XML.
Other formats than XML are not available for parsing OSM input data.
Use a tool like Osmosis to pre-process data.

@author: vanosten
"""

import copy
from collections import namedtuple
import logging
from typing import Dict, List, Optional, Tuple
import time
import unittest
import xml.sax

import psycopg2
import shapely.geometry as shg

import parameters


class OSMElement(object):
    def __init__(self, osm_id: int) -> None:
        self.osm_id = osm_id
        self.tags = {}

    def add_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def __str__(self):
        return "<%s OSM_ID %i at %s>" % (type(self).__name__, self.osm_id, hex(id(self)))


class Node(OSMElement):
    def __init__(self, osm_id: int, lat: float, lon: float) -> None:
        OSMElement.__init__(self, osm_id)
        self.lat = lat  # float value
        self.lon = lon  # float value


class Way(OSMElement):
    def __init__(self, osm_id: int) -> None:
        OSMElement.__init__(self, osm_id)
        self.refs = []
        self.pseudo_osm_id = 0  # can be assigned if existing way gets split

    def add_ref(self, ref: int) -> None:
        self.refs.append(ref)


class Member(object):
    def __init__(self, ref: int, type_: str, role: str) -> None:
        self.ref = ref
        self.type_ = type_
        self.role = role


class Relation(OSMElement):
    def __init__(self, osm_id: int):
        OSMElement.__init__(self, osm_id)
        self.members = []

    def add_member(self, member: Member) -> None:
        self.members.append(member)


OSMReadResult = namedtuple("OSMReadResult", "nodes_dict, ways_dict, relations_dict, rel_nodes_dict, rel_ways_dict")


class OSMContentHandler(xml.sax.ContentHandler):
    """
    A Specialized SAX ContentHandler for OpenStreetMap data to be processed by
    osm2city.

    All nodes will be accepted. However, to save memory, we strip out those
    tags not present in valid_node_keys.

    By contrast, not all ways and relations will be accepted. We accept a
    way/relation only if at least one of its tags is in req_??_keys.
    An accepted way/relation is handed over to the callback. It is then up to
    the callback to discard certain tags.

    The valid_??_keys and req_??_keys are a primitive way to save memory and
    reduce the number of further processed elements. A better way is to have
    the input file processed by e.g. Osmosis first.
    """

    def __init__(self, valid_node_keys, border=None):
        xml.sax.ContentHandler.__init__(self)
        self.border = border
        self._way_callbacks = []
        self._relation_callbacks = []
        self._uncategorized_way_callback = None
        self._valid_node_keys = valid_node_keys
        self.nodes_dict = {}
        self.ways_dict = {}
        self.relations_dict = {}
        self._current_node = None
        self._current_way = None
        self._current_relation = None
        self._within_element = None

    def parse(self, source):
        xml.sax.parse(source, self)

    def register_way_callback(self, callback, req_keys=None):
        if req_keys is None:
            req_keys = []
        self._way_callbacks.append((callback, req_keys))

    def register_relation_callback(self, callback, req_keys):
        self._relation_callbacks.append((callback, req_keys))

    def register_uncategorized_way_callback(self, callback):
        self._uncategorized_way_callback = callback

    def startElement(self, name, attrs):
        if name == "node":
            self._within_element = name
            lat = float(attrs.getValue("lat"))
            lon = float(attrs.getValue("lon"))
            osm_id = int(attrs.getValue("id"))
            self._current_node = Node(osm_id, lat, lon)
        elif name == "way":
            self._within_element = name
            osm_id = int(attrs.getValue("id"))
            self._current_way = Way(osm_id)
        elif name == "relation":
            self._within_element = name
            osm_id = int(attrs.getValue("id"))
            self._current_relation = Relation(osm_id)
        elif name == "tag":
            key = attrs.getValue("k")
            value = attrs.getValue("v")
            if "node" == self._within_element:
                if key in self._valid_node_keys:
                    self._current_node.add_tag(key, value)
            elif "way" == self._within_element:
                self._current_way.add_tag(key, value)
            elif "relation" == self._within_element:
                self._current_relation.add_tag(key, value)
        elif name == "nd":
            ref = int(attrs.getValue("ref"))
            self._current_way.add_ref(ref)
        elif name == "member":
            ref = int(attrs.getValue("ref"))
            type_ = attrs.getValue("type")
            role = attrs.getValue("role")
            self._current_relation.add_member(Member(ref, type_, role))

    def endElement(self, name):
        if name == "node":
            if self.border is None or self.border.contains(shg.Point(self._current_node.lon, self._current_node.lat)):        
                self.nodes_dict[self._current_node.osm_id] = self._current_node
            else:
                logging.debug("Ignored Osmid %d outside clipping", self._current_node.osm_id)
        elif name == "way":
            cb = find_callback_for(self._current_way.tags, self._way_callbacks)
            # no longer filter valid_way_keys here. That's up to the callback.
            if cb is not None:
                cb(self._current_way, self.nodes_dict)
            try:
                self._uncategorized_way_callback(self._current_way, self.nodes_dict)
            except TypeError:
                pass
        elif name == "relation":
            cb = find_callback_for(self._current_relation.tags, self._relation_callbacks)
            if cb is not None:
                cb(self._current_relation)

    def characters(self, content):
        pass


def find_callback_for(tags, callbacks):
    for (callback, req_keys) in callbacks:
        for key in list(tags.keys()):
            if key in req_keys:
                return callback
    return None


class OSMContentHandlerOld(xml.sax.ContentHandler):
    """
    This is a wrapper for OSMContentHandler, enabling backwards compatibility.
    It registers way and relation callbacks with the actual handler. During parsing,
    these callbacks fill dictionaries of ways and relations.

    The valid_??_keys are those tag keys, which will be accepted and added to an element's tags.
    The req_??_keys are those tag keys, of which at least one must be present to add an element to the saved elements.

    The valid_??_keys and req_??_keys are a primitive way to save memory and reduce the number of further processed
    elements. A better way is to have the input file processed by e.g. Osmosis first.
    """
    def __init__(self, valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys,
                 border=None):
        super(OSMContentHandlerOld, self).__init__()
        self.valid_way_keys = valid_way_keys
        self.valid_relation_keys = valid_relation_keys
        self._handler = OSMContentHandler(valid_node_keys, border)
        self._handler.register_way_callback(self.process_way, req_way_keys)
        if req_relation_keys is not None:
            self._handler.register_relation_callback(self.process_relation, req_relation_keys)
            self._handler.register_uncategorized_way_callback(self.process_relation_way)
        self.nodes_dict = None
        self.ways_dict = {}
        self.relations_dict = {}
        self.rel_ways_dict = {}
        self.rel_nodes_dict = None

    def parse(self, source):
        xml.sax.parse(source, self)

    def startElement(self, name, attrs):
        self._handler.startElement(name, attrs)

    def endElement(self, name):
        self._handler.endElement(name)

    def process_way(self, current_way, nodes_dict):
        if not self.nodes_dict:
            self.nodes_dict = nodes_dict
        all_tags = current_way.tags
        current_way.tags = {}
        for key in list(all_tags.keys()):
            if len(self.valid_way_keys) > 0:
                if key in self.valid_way_keys:
                    current_way.add_tag(key, all_tags[key])
            else:
                current_way.add_tag(key, all_tags[key])
        self.ways_dict[current_way.osm_id] = current_way

    def process_relation(self, current_relation):
        all_tags = current_relation.tags
        current_relation.tags = {}
        for key in list(all_tags.keys()):
            if len(self.valid_way_keys) > 0:
                if key in self.valid_way_keys:
                    current_relation.add_tag(key, all_tags[key])
            else:
                if key in self.valid_way_keys:
                    current_relation.add_tag(key, all_tags[key])
        self.relations_dict[current_relation.osm_id] = current_relation

    def process_relation_way(self, uncategorized_way, nodes_dict):
        """Only used in buildings for ways in relations.
        This method adds way too many due to linear processing of xml-file instead of relational DB access.
        Taking copies because original nodes and ways might get changed / deleted before relations get processed
        in the consuming processes."""
        if not self.rel_nodes_dict:
            self.rel_nodes_dict = copy.deepcopy(nodes_dict)
        my_rel_way = Way(uncategorized_way.osm_id)
        my_rel_way.refs = copy.deepcopy(uncategorized_way.refs)
        self.rel_ways_dict[my_rel_way.osm_id] = my_rel_way


def has_required_tag_keys(my_tags, my_required_keys):
    """ Checks whether a given set of actual tags contains at least one of the required tags """
    for key in list(my_tags.keys()):
        if key in my_required_keys:
            return True
    return False


def parse_length(str_length):
    """
    Transform length to meters if not yet default. Input is a string, output is a float.
    If the string cannot be parsed, then 0 is returned.
    Length (and width/height) in OSM is per default meters cf. OSM Map Features / Units.
    Possible units can be "m" (metre), "km" (kilometre -> 0.001), "mi" (mile -> 0.00062137) and
    <feet>' <inch>" (multiply feet by 12, add inches and then multiply by 0.0254).
    Theoretically there is a blank between the number and the unit, practically there might not be.
    """
    _processed = str_length.strip().lower()
    if _processed.endswith("km"):
        _processed = _processed.rstrip("km").strip()
        _factor = 1000
    elif _processed.endswith("m"):
        _processed = _processed.rstrip("m").strip()
        _factor = 1
    elif _processed.endswith("mi"):
        _processed = _processed.rstrip("mi").strip()
        _factor = 1609.344
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
        _factor = 1
    if is_parsable_float(_processed):
        return float(_processed)*_factor
    else:
        logging.warning('Unable to parse for length from value: %s', str_length)
        return 0


def is_parsable_float(str_float: str) -> bool:
    try:
        float(str_float)
        return True
    except ValueError:
        return False


def is_parsable_int(str_int: str) -> bool:
    try:
        int(str_int)
        return True
    except ValueError:
        return False


def parse_hstore_tags(tags_string: str, osm_id: int) -> Dict[str, str]:
    """Parses the content of a string representation of a PostGIS hstore content for tags.
    Returns a dict of key value pairs as string."""
    tags_dict = dict()
    if len(tags_string.strip()) > 0:  # else we return the empty dict as is
        elements = tags_string.strip().split('", "')
        for element in elements:
            if len(element.strip()) > 0:
                sub_elements = element.strip().split("=>")
                if len(sub_elements) == 2 and len(sub_elements[0].strip()) > 1 and len(sub_elements[1].strip()) > 1:
                    key = sub_elements[0].strip().strip('"')
                    if key not in tags_dict:
                        tags_dict[key] = sub_elements[1].strip().strip('"')
                    else:
                        message = "hstore for osm_id={} has same key twice: key={}, tags='{}'.".format(osm_id,
                                                                                                       key,
                                                                                                       tags_string)
                        logging.warning(message)
                else:
                    message = "hstore for osm_id={} has not valid key/value pair: '{}' in '{}'.".format(osm_id,
                                                                                                        sub_elements,
                                                                                                        tags_string)
                    logging.warning(message)
    return tags_dict


def fetch_db_way_data(req_way_keys: List[str], req_way_key_values: List[str],
                      db_connection: psycopg2.extensions.connection) -> Dict[int, Way]:
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
        my_way.tags = parse_hstore_tags(result[1], my_way.osm_id)
        my_way.refs = result[2]
        ways_dict[my_way.osm_id] = my_way

    return ways_dict


def fetch_db_nodes_for_way(req_way_keys: List[str], req_way_key_values: List[str],
                           db_connection: psycopg2.extensions.connection) -> Dict[int, Node]:
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


def fetch_all_query_into_tuple(query: str, db_connection: psycopg2.extensions.connection) -> List[Tuple]:
    """Given a query string and a db connection execute fetch all and return the result as a list of tuples"""
    cur = db_connection.cursor()
    logging.debug("Query string for execution in database: " + query)
    cur.execute(query)
    return cur.fetchall()


def fetch_osm_db_data_ways(required: List[str], is_key_values: bool=False) -> OSMReadResult:
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
    return fetch_osm_db_data_ways(req_key_values, True)


def fetch_osm_db_data_ways_keys(req_keys: List[str]) -> OSMReadResult:
    """Given a list of required keys get the ways plus the linked nodes from an OSM database."""
    return fetch_osm_db_data_ways(req_keys, False)


def fetch_osm_db_data_relations_keys(req_keys: List[str], input_read_result: OSMReadResult) -> OSMReadResult:
    """Updates an OSMReadResult with relation data based on required keys"""
    start_time = time.time()

    db_connection = make_db_connection()

    # == Relations and members and ways
    # Getting related way data might add a bit of  volume, but reduces number of queries and might be seldom that
    # same way is in different relations for buildings.
    query = """SELECT r.id, r.tags, rm.member_id, rm.member_role, w.nodes, w.tags
    FROM relations AS r, relation_members AS rm, ways AS w
    WHERE
    """
    query += "r.tags @> 'type=>multipolygon'"
    query += " AND " + construct_tags_query(req_keys, list(), "r")
    query += " AND r.id = rm.relation_id"
    query += " AND rm.member_type = 'W'"
    query += " AND rm.member_id = w.id"
    query += " AND "
    query += construct_intersect_bbox_query()
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
            relation.tags = parse_hstore_tags(result[1], relation_id)
            relations_dict[relation_id] = relation
        else:
            relation = relations_dict[relation_id]

        my_member = Member(member_id, "way", result[3])
        relation.add_member(my_member)

        if member_id not in rel_ways_dict:
            my_way = Way(member_id)
            my_way.refs = result[4]
            my_way.tags = parse_hstore_tags(result[5], my_way.osm_id)
            rel_ways_dict[my_way.osm_id] = my_way

    # == Nodes for the ways
    query = """SELECT n.id, ST_X(n.geom) as lon, ST_Y(n.geom) as lat
    FROM relations AS r, relation_members AS rm, ways AS w, way_nodes AS wn, nodes AS n
    WHERE
    """
    query += "r.tags @> 'type=>multipolygon'"
    query += " AND " + construct_tags_query(req_keys, list(), "r")
    query += " AND r.id = rm.relation_id"
    query += " AND rm.member_type = 'W'"
    query += " AND rm.member_id = w.id"
    query += " AND "
    query += construct_intersect_bbox_query()
    query += " AND wn.way_id = w.id"
    query += " AND wn.node_id = n.id"
    query += ";"

    result_tuples = fetch_all_query_into_tuple(query, db_connection)

    rel_nodes_dict = dict()
    for result in result_tuples:
        my_node = Node(result[0], result[2], result[1])
        rel_nodes_dict[my_node.osm_id] = my_node

    logging.info("Reading OSM relation data for {0!s} from db took {1:.4f} seconds.".format(req_keys,
                                                                                            time.time() - start_time))

    return OSMReadResult(nodes_dict=input_read_result.nodes_dict, ways_dict=input_read_result.ways_dict,
                         relations_dict=relations_dict, rel_nodes_dict=rel_nodes_dict, rel_ways_dict=rel_ways_dict)


def fetch_osm_file_data(valid_way_keys: List[str], req_way_keys: List[str], req_rel_keys: Optional[List[str]]=None) \
        -> OSMReadResult:
    """Given a list of valid keys and a list of required keys get the ways plus the linked nodes from an OSM file."""
    start_time = time.time()
    valid_node_keys = []
    valid_relation_keys = []

    border = None
    if parameters.BOUNDARY_CLIPPING_COMPLETE_WAYS is False and parameters.BOUNDARY_CLIPPING:
        border = shg.Polygon(parameters.get_clipping_extent())

    handler = OSMContentHandlerOld(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys,
                                   req_rel_keys, border)
    osm_file_name = parameters.get_OSM_file_name()
    source = open(osm_file_name, encoding="utf8")
    xml.sax.parse(source, handler)
    logging.info("Reading OSM data from xml took {0:.4f} seconds.".format(time.time() - start_time))
    return OSMReadResult(nodes_dict=handler.nodes_dict, ways_dict=handler.ways_dict,
                         relations_dict=handler.relations_dict,
                         rel_nodes_dict=handler.rel_nodes_dict, rel_ways_dict=handler.rel_ways_dict)


def make_db_connection() -> psycopg2.extensions.connection:
    """"Create connection to the database based on parameters."""
    return psycopg2.connect(database=parameters.DB_NAME, host=parameters.DB_HOST, port=parameters.DB_PORT,
                            user=parameters.DB_USER, password=parameters.DB_USER)


def construct_intersect_bbox_query() -> str:
    """Constructs the part of a sql where clause, which constrains to bounding box."""
    query_part = "ST_Intersects(w.bbox, ST_SetSRID(ST_MakeBox2D(ST_Point({}, {}), ST_Point({}, {})), 4326))"
    return query_part.format(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH,
                             parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH)


def construct_tags_query(req_tag_keys: List[str], req_tag_key_values: List[str], table_alias: str="w") -> str:
    """Constructs the part of a sql where clause, which constrains the result based on required tag keys.
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

    if len(req_tag_key_values) > 0:
        if len(tags_query) > 0:
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


# ================ UNITTESTS =======================

class TestOSMParser(unittest.TestCase):
    def test_parse_length(self):
        self.assertAlmostEqual(1.2, parse_length(' 1.2 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(1.2, parse_length(' 1.2 m'), 2, "Correct number with meter unit incl. space")
        self.assertAlmostEqual(1.2, parse_length(' 1.2m'), 2, "Correct number with meter unit without space")
        self.assertAlmostEqual(1200, parse_length(' 1.2 km'), 2, "Correct number with km unit incl. space")
        self.assertAlmostEqual(2092.1472, parse_length(' 1.3mi'), 2, "Correct number with mile unit without space")
        self.assertAlmostEqual(3.048, parse_length("10'"), 2, "Correct number with feet unit without space")
        self.assertAlmostEqual(3.073, parse_length('10\'1"'), 2, "Correct number with feet unit without space")
        self.assertEqual(0, parse_length('m'), "Only valid unit")
        self.assertEqual(0, parse_length('"'), "Only inches, no feet")

    def test_is_parsable_float(self):
        self.assertFalse(is_parsable_float('1,2'))
        self.assertFalse(is_parsable_float('x'))
        self.assertTrue(is_parsable_float('1.2'))

    def test_is_parsable_int(self):
        self.assertFalse(is_parsable_int('1.2'))
        self.assertFalse(is_parsable_int('x'))
        self.assertTrue(is_parsable_int('1'))

    def test_parse_hstore_tags(self):
        self.assertEqual(0, len(parse_hstore_tags('', 1)), "Empty string")
        self.assertEqual(0, len(parse_hstore_tags('  ', 1)), "Empty truncated string")
        my_dict = parse_hstore_tags('"foo"=>"goo"', 1)
        self.assertEqual(1, len(my_dict), "One element tags")
        self.assertEqual("goo", my_dict["foo"], "One element tags validate value")
        my_dict = parse_hstore_tags('"foo"=>"goo", "alpha"=> "1"', 1)
        self.assertEqual(2, len(my_dict), "Two element tags")
        self.assertEqual("1", my_dict["alpha"])
        my_dict = parse_hstore_tags('"foo"=>"goo", "alpha"=> "1", ', 1)
        self.assertEqual(2, len(my_dict), "Last element empty")
        my_dict = parse_hstore_tags('"foo"=>"goo", "foo"=> "1"', 1)
        self.assertEqual(1, len(my_dict), "Repeated key ignored")
        my_dict = parse_hstore_tags('"foo"=>"goo", "foo"=> ""', 1)
        self.assertEqual(1, len(my_dict), "Invalid value ignored")
        my_dict = parse_hstore_tags('"foo"=>"go,o", "ho,o"=>"i,"', 1)
        self.assertEqual(2, len(my_dict), "Keys and values with comma")
        self.assertEqual("go,o", my_dict["foo"], "Keys and values with comma validate first value")
        self.assertEqual("i,", my_dict["ho,o"], "Keys and values with comma validate first value")
