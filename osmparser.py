# -*- coding: utf-8 -*-
"""
Parser for OpenStreetMap data based on standard Python SAX library for processing XML.
Other formats than XML are not available for parsing OSM input data.
Use a tool like Osmosis to pre-process data.

@author: vanosten
"""

import xml.sax


class OSMElement(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.tags = []
        
    def addTag(self, tag):
        self.tags.append(tag)


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


class Tag(object):
    def __init__(self, key, value):
        self.key = key
        self.value = value


class Member(object):
    def __init__(self, ref, mtype, role):
        self.ref = ref
        self.mtype = mtype
        self.role = role


class OSMContentHandler(xml.sax.ContentHandler):
    """
    A Specialized SAX ContentHandler for OpenStreetMap data to be processed by osm2city.
    The valid_??_keys are those tag keys, which will be accepted and added to an element's tags.
    The req_??_keys are those tag keys, of which at least one must be present to add an element to the saved elements.
    
    The valid_??_keys and req_??_keys are a primitive way to save memory and reduce the number of further processed elements.
    A better way is to have the input file processed by e.g. Osmosis first.
    """
    def __init__(self, valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys):
        xml.sax.ContentHandler.__init__(self)
        self.valid_node_keys = valid_node_keys
        self.valid_way_keys = valid_way_keys
        self.req_way_keys = req_way_keys
        self.valid_relation_keys = valid_relation_keys
        self.req_relation_keys = req_relation_keys
        self.nodes_dict = {}
        self.ways_dict = {}
        self.relations_dict = {}
        self.current_node = None
        self.current_way = None
        self.current_relation = None
        self.within_element = None

    def startElement(self, name, attrs):
        if name == "node":
            self.within_element = name
            lat = float(attrs.getValue("lat"))
            lon = float(attrs.getValue("lon"))
            osm_id = attrs.getValue("id")
            self.current_node = Node(osm_id, lat, lon)
        elif name == "way":
            self.within_element = name
            osm_id = attrs.getValue("id")
            self.current_way = Way(osm_id)
        elif name == "relation":
            osm_id = attrs.getValue("id")
            self.current_relation = Relation(osm_id)
        elif name == "tag":
            key = attrs.getValue("k")
            value = attrs.getValue("v")
            if "node" == self.within_element:
                if key in self.valid_node_keys: 
                    self.current_node.addTag(Tag(key, value))
            elif "way" == self.within_element:
                if key in self.valid_way_keys:
                    self.current_way.addTag(Tag(key, value))
            elif "relation" == self.within_element:
                if key in self.valid_relation_keys:
                    self.current_relation.addTag(Tag(key, value))
        elif name == "nd":
            ref = attrs.getValue("ref")
            self.current_way.addRef(ref)
        elif name == "member":
            ref = attrs.getValue("ref")
            mtype = attrs.getValue("type")
            role = attrs.getValue("role")
            self.current_relation.addMember(Member(ref, mtype, role))

    def endElement(self, name):
        if name == "node":
            self.nodes_dict[self.current_node.osm_id] = self.current_node
        elif name == "way":
            if has_required_tag_keys(self.current_way.tags, self.req_way_keys):
                self.ways_dict[self.current_way.osm_id] = self.current_way
        elif name == "relation":
            if has_required_tag_keys(self.current_relation.tags, self.req_relation_keys):
                self.relations_dict[self.current_relation.osm_id] = self.current_relation
            
    def characters(self, content):
        pass


def has_required_tag_keys(my_tags, my_required_keys):
    """ Checks whether a given set of actual tags contains at least one of the required tags """
    for tag in my_tags:
        if tag.key in my_required_keys:
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
        if is_parseable_float(_split[0]):
            _f_length = float(_split[0])*12
            _processed = str(_f_length)
            if 2 == len(_split):
                if is_parseable_float(_split[1]):
                    _processed = str(_f_length + float(_split[1]))
    else:  # assumed that no unit characters are in the string
        _factor = 1
    if is_parseable_float(_processed):
        return float(_processed)*_factor
    else:
        print "Unable to parse for length from:", str_length
        return 0


def is_parseable_float(str_float):
    try:
        x = float(str_float)
        return True
    except ValueError:
        return False


def main(source_file_name):
    source = open(source_file_name)
    valid_node_keys = []
    valid_way_keys = ["building", "height", "building:levels"]
    req_way_keys = ["building"]
    valid_relation_keys = ["building"]
    req_relation_keys = ["building"]
    handler = OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys)
    xml.sax.parse(source, handler)
    print "nodes:", len(handler.nodes_dict)
    print "ways:", len(handler.ways_dict)
    print "relations:", len(handler.relations_dict)
 
if __name__ == "__main__":
    main("C:\\FlightGear\\customscenery2\\LSZS\\ch.osm")
