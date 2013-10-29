# -*- coding: utf-8 -*-
"""
http://www.knowthytools.com/2010/03/sax-parsing-with-python.html

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
        self.lat = lat
        self.lon = lon

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
            lat = attrs.getValue("lat")
            lon = attrs.getValue("lon")
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
            if True == hasRequiredTagKeys(self.current_way.tags, self.req_way_keys):
                self.ways_dict[self.current_way.osm_id] = self.current_way
        elif name == "relation":
            if True == hasRequiredTagKeys(self.current_relation.tags, self.req_relation_keys):
                self.relations_dict[self.current_relation.osm_id] = self.current_relation
            
    def characters(self, content):
        pass
    
def hasRequiredTagKeys(my_tags, my_required_keys):
    for tag in my_tags:
        if tag.key in my_required_keys:
            return True
    return False
 
def main(sourceFileName):
    source = open(sourceFileName)
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
    main("C:\\FlightGear\\customscenery2\\LSZS\\ch_at.osm")

