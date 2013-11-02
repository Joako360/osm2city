# -*- coding: utf-8 -*-
"""
Script part of osm2city which takes OpenStreetMap data for overground power lines and aerialways
as input and generates data to be used in FlightGear sceneries.

* Cf. OSM Power: 
    http://wiki.openstreetmap.org/wiki/Map_Features#Power
    http://wiki.openstreetmap.org/wiki/Tag:power%3Dtower
* Cf. OSM Aerialway: http://wiki.openstreetmap.org/wiki/Map_Features#Aerialway

@author: vanosten
"""

import osmparser
import xml.sax

class Pylon(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.p_type = 0 # 11 = electric pole, 12 = electric tower, 21 = aerialway pylon, 22 = aerialway station
        self.height = 0
        self.structure = None
        self.material = None
        self.colour = None
        self.line = None # a reference to the way - either an electrical line or an aerialway
        self.prev_pylon = None
        self.next_pylon = None

class Line(object):
    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.pylons = []
        self.l_type = 0 # 11 = power line, 12 = power minor line, 21 = cable_car, 22 = chair_lift/mixed_lift, 23 = drag_lift/t-bar/platter, 24 = gondola, 25 = goods

def transformOSMElements(nodes_dict, ways_dict):
    """
    Transforms a dict of Node and a dict of Way OSMElements from osmparser.py to a dict of Line objects for electrical power
    lines and a dict of Line objects for aerialways.
    """
    my_powerlines = {}
    my_aerialways = {}
    for way in ways_dict.values():
        my_line = Line(way.osm_id)
        for tag in way.tags:
            if "power" == tag.key:
                if "line" == tag.value:
                    my_line.l_type = 11
                elif "minor_line" == tag.value:
                    my_line.l_type = 12
            elif "aerialway" == tag.key:
                if "cable_car" == tag.value:
                    my_line.l_type = 21
                elif tag.value in ["chair_lift", "mixed_lift"]:
                    my_line.l_type = 22
                elif tag.value in ["drag_lift","t-bar","platter"]:
                    my_line.l_type = 23
                elif "gondola" == tag.value:
                    my_line.l_type = 24
                elif "goods" == tag.value:
                    my_line.l_type = 25
        if 0 != my_line.l_type:
            prev_pylon = None
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    my_pylon = Pylon(my_node.osm_id)
                    my_pylon.line = my_line
                    for tag in my_node.tags:
                        if "power" == tag.key:
                            if "tower" == tag.value:
                                my_pylon.p_type = 12
                            elif "pole" == tag.value:
                                my_pylon.p_type = 11
                        elif "aerialway" == tag.key:
                            if "pylon" == tag.value:
                                my_pylon.p_type = 21
                            elif "station" == tag.value:
                                my_pylon.p_type = 22
                        elif "height" == tag.key:
                            my_pylon.height = tag.value
                        elif "structure" == tag.key:
                            my_pylon.structure = tag.value
                        elif "material" == tag.key:
                            my_pylon.material = tag.value
                    my_line.pylons.append(my_pylon)
                    if None != prev_pylon:
                        prev_pylon.next_pylon = my_pylon
                        my_pylon.prev_pylon = prev_pylon
                    prev_pylon = my_pylon
            if 1 < len(my_line.pylons):
                if "power" == tag.key:
                    my_powerlines[my_line.osm_id] = my_line
                else:
                    my_aerialways[my_line.osm_id] = my_line
    return (my_powerlines, my_aerialways)

if __name__ == "__main__":
    source = open("C:\\FlightGear\\customscenery2\\LSZS\\lszs_narrow.osm")
    valid_node_keys = ["power", "structure", "material", "height", "colour", "aerialway"]
    valid_way_keys = ["power", "aerialway"]
    req_way_keys = ["power", "aerialway"]
    valid_relation_keys = []
    req_relation_keys = []
    handler = osmparser.OSMContentHandler(valid_node_keys, valid_way_keys, req_way_keys, valid_relation_keys, req_relation_keys)
    xml.sax.parse(source, handler)
    print "nodes:", len(handler.nodes_dict)
    print "ways:", len(handler.ways_dict)
    print "relations:", len(handler.relations_dict)
    
    my_powerlines, my_aerialways = transformOSMElements(handler.nodes_dict, handler.ways_dict)

    print "powerlines: ", len(my_powerlines)
    print "aerialways: ", len(my_aerialways)


