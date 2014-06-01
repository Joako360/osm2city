# -*- coding: utf-8 -*-
"""
Parser for OpenStreetMap data based on standard Python SAX library for processing XML.
Other formats than XML are not available for parsing OSM input data.
Use a tool like Osmosis to pre-process data.

@author: vanosten
"""

import xml.sax
import logging
import unittest

class OSMElement(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.tags = {}

    def addTag(self, key, value):
        self.tags[key] = value


class Node(OSMElement):
    def __init__(self, osm_id, lat, lon):
        OSMElement.__init__(self, osm_id)
        self.lat = lat  # float value
        self.lon = lon  # float value


class Way(OSMElement):
    def __init__(self, osm_id):
        OSMElement.__init__(self, osm_id)
        self.refs = []

    def addRef(self, ref):
        self.refs.append(ref)


class Relation(OSMElement):
    def __init__(self, osm_id):
        OSMElement.__init__(self, osm_id)
        self.members = []

    def addMember(self, member):
        self.members.append(member)


class Member(object):
    def __init__(self, ref, type_, role):
        self.ref = ref
        self.type_ = type_
        self.role = role

#class Callback(object):
#    def __init__(self, callback, **kwargs):
#        self.callback = callback
#        self.kwargs = kwargs

class OSMContentHandler(xml.sax.ContentHandler):
    """
    A Specialized SAX ContentHandler for OpenStreetMap data to be processed by osm2city.
    The valid_??_keys are those tag keys, which will be accepted and added to an element's tags.
    The req_??_keys are those tag keys, of which at least one must be present to add an element to the saved elements.

    The valid_??_keys and req_??_keys are a primitive way to save memory and reduce the number of further processed elements.
    A better way is to have the input file processed by e.g. Osmosis first.
    """

    def __init__(self, valid_node_keys): #, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys):
        xml.sax.ContentHandler.__init__(self)
        self._way_callbacks = []
        self._relation_callbacks = []
        self._uncategorized_way_callback = None
        self._valid_node_keys = valid_node_keys
        #self._valid_way_keys = valid_way_keys
        #self._req_way_keys = req_way_keys
        #self._valid_relation_keys = valid_relation_keys
        #self._req_relation_keys = req_relation_keys
        self.nodes_dict = {}
        self.ways_dict = {}
        self.relations_dict = {}
        self._current_node = None
        self._current_way = None
        self._current_relation = None
        self._within_element = None

    def parse(self, source):
        xml.sax.parse(source, self)
#, valid_relation_keys=[], req_relation_keys=[]

    def register_way_callback(self, callback, req_keys=[]):
        self._way_callbacks.append((callback, req_keys))

    def register_relation_callback(self, callback, req_keys=[]):
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
                    self._current_node.addTag(key, value)
            elif "way" == self._within_element:
                if 1: #key in self._valid_way_keys:
                    self._current_way.addTag(key, value)
            elif "relation" == self._within_element:
                if 1: # key in self._valid_relation_keys:
                    self._current_relation.addTag(key, value)
        elif name == "nd":
            ref = int(attrs.getValue("ref"))
            self._current_way.addRef(ref)
        elif name == "member":
            ref = int(attrs.getValue("ref"))
            type_ = attrs.getValue("type")
            role = attrs.getValue("role")
            self._current_relation.addMember(Member(ref, type_, role))

    def endElement(self, name):
        if name == "node":
            self.nodes_dict[self._current_node.osm_id] = self._current_node
        elif name == "way":
            cb = self.find_callback_for(self._current_way.tags, self._way_callbacks)
            # -- no longer filter valid_way_keys here. That's up to the callback
            if cb:
                cb(self._current_way, self.nodes_dict)
            else:
                try:
                    self._uncategorized_way_callback(self._current_way, self.nodes_dict)
                except TypeError:
                    pass
            #if has_required_tag_keys(self._current_way.tags, self._req_way_keys):
            #    self.ways_dict[self._current_way.osm_id] = self._current_way
        elif name == "relation":
            cb = self.find_callback_for(self._current_relation.tags, self._relation_callbacks)
            #print "tags", self._current_relation.tags
            if cb:
                cb(self._current_relation)
            #if has_required_tag_keys(self._current_relation.tags, self._req_relation_keys):
            #    self.relations_dict[self._current_relation.osm_id] = self._current_relation

    def find_callback_for(self, tags, callbacks):
        for (callback, req_keys) in callbacks:
            for key in tags.keys():
                if key in req_keys:
                    return callback
        return False

    def characters(self, content):
        pass


def has_required_tag_keys(my_tags, my_required_keys):
    """ Checks whether a given set of actual tags contains at least one of the required tags """
    for key in my_tags.keys():
        if key in my_required_keys:
            return True
    return False


def parse_length(str_length):
    """
    Transform length to meters if not yet default. Input is a string, output is a float. If the string cannot be parsed, then 0 is returned.
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


def is_parsable_float(str_float):
    try:
        x = float(str_float)
        return True
    except ValueError:
        return False


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
        self.assertAlmostEqual(1.2, parse_length(' 1.2 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(1.2, parse_length(' 1.2 m'), 2, "Correct number with meter unit incl. space")
        self.assertAlmostEqual(1.2, parse_length(' 1.2m'), 2, "Correct number with meter unit without space")
        self.assertAlmostEqual(1200, parse_length(' 1.2 km'), 2, "Correct number with km unit incl. space")
        self.assertAlmostEqual(2092.1472, parse_length(' 1.3mi'), 2, "Correct number with mile unit without space")
        self.assertAlmostEqual(3.048, parse_length("10'"), 2, "Correct number with feet unit without space")
        self.assertAlmostEqual(3.073, parse_length('10\'1"'), 2, "Correct number with feet unit without space")
        self.assertEquals(0, parse_length('m'), "Only valid unit")
        self.assertEquals(0, parse_length('"'), "Only inches, no feet")


    def test_is_parsable_float(self):
        self.assertFalse(is_parsable_float('1,2'))
        self.assertFalse(is_parsable_float('x'))
        self.assertTrue(is_parsable_float('1.2'))

