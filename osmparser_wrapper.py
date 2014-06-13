# -*- coding: utf-8 -*-
"""
A wrapper for OSMContentHandler, enabling backwards compatibility.
"""

import xml.sax
import logging
import unittest
import osmparser as op


class OSMContentHandler(xml.sax.ContentHandler):
    """
    A Specialized SAX ContentHandler for OpenStreetMap data to be processed by osm2city.
    This is a wrapper for OSMContentHandler, enabling backwards compatibility.
    It registers way and relation callbacks with the actual handler. During parsing,
    these callbacks fill dictionaries of ways and relations.

    The valid_??_keys are those tag keys, which will be accepted and added to an element's tags.
    The req_??_keys are those tag keys, of which at least one must be present to add an element to the saved elements.

    The valid_??_keys and req_??_keys are a primitive way to save memory and reduce the number of further processed
    elements. A better way is to have the input file processed by e.g. Osmosis first.
    """
    def __init__(self, valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys):
        self.valid_way_keys = valid_way_keys
        self.valid_relation_keys = valid_relation_keys
        self._handler = op.OSMContentHandler(valid_node_keys)
        self._handler.register_way_callback(self.process_way, req_way_keys)
        self._handler.register_relation_callback(self.process_relation, req_relation_keys)
        self.nodes_dict = None
        self.ways_dict = {}
        self.relations_dict = {}

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
        for key, value in all_tags.items():
            if key in self.valid_way_keys:
                current_way.addTag(key, value)
        self.ways_dict[current_way.osm_id] = current_way

    def process_relation(self, current_relation):
        all_tags = current_relation.tags
        current_relation.tags = {}
        for key, value in all_tags.items():
            if key in self.valid_way_keys:
                current_relation.addTag(key, value)
        self.relations_dict[current_relation.osm_id] = current_relation


def main(source_file_name):
    """Only for test of parser. Normally Parser should be instantiated from other module and then run"""
    logging.basicConfig(level=logging.INFO)
    source = open(source_file_name)
    valid_node_keys = []
    valid_way_keys = ["building", "height", "building:levels"]
    req_way_keys = ["building"]
    valid_relation_keys = ["building"]
    req_relation_keys = ["building"]
    handler = OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys)
    xml.sax.parse(source, handler)
    logging.info('Number of nodes: %s', len(handler.nodes_dict))
    logging.info('Number of ways: %s', len(handler.ways_dict))
    logging.info('Number of relations: %s', len(handler.relations_dict))

if __name__ == "__main__":
    main("C:\\FlightGear\\customscenery2\\LSZS\\ch.osm")

# ================ UNITTESTS =======================


class TestOSMParser(unittest.TestCase):
    def test_parse_length(self):
        self.assertAlmostEqual(1.2, op.parse_length(' 1.2 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(1.2, op.parse_length(' 1.2 m'), 2, "Correct number with meter unit incl. space")
        self.assertAlmostEqual(1.2, op.parse_length(' 1.2m'), 2, "Correct number with meter unit without space")
        self.assertAlmostEqual(1200, op.parse_length(' 1.2 km'), 2, "Correct number with km unit incl. space")
        self.assertAlmostEqual(2092.1472, op.parse_length(' 1.3mi'), 2, "Correct number with mile unit without space")
        self.assertAlmostEqual(3.048, op.parse_length("10'"), 2, "Correct number with feet unit without space")
        self.assertAlmostEqual(3.073, op.parse_length('10\'1"'), 2, "Correct number with feet unit without space")
        self.assertEquals(0, op.parse_length('m'), "Only valid unit")
        self.assertEquals(0, op.parse_length('"'), "Only inches, no feet")

    def test_is_parsable_float(self):
        self.assertFalse(op.is_parsable_float('1,2'))
        self.assertFalse(op.is_parsable_float('x'))
        self.assertTrue(op.is_parsable_float('1.2'))

