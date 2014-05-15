#!/usr/bin/env python2
"""abstract way extractor. To be inherited.

class Road(object):
   # holds data for one road
   def init(...)

class Roads(object):
   #holds all roads. OSM parser calls back our create_from_way().
   self.roads = []
   self.valid_node_keys = ..
   self.valid_way_keys = ..
   def create_from_way(way, refs, nodes):
       road = Road(...)
       self.roads.append(road)

def __main__():
   roads = Roads()
   handler = osmparser.OSMContentHandler()

   # -- handler hält eine Liste von callbacks. Wenn der handler beim parsen
   #    valid_keys trifft, wird der entsprechende callback aufgerufen.

   handler.register_way_callback(roads.create_from_way, roads.valid_node_keys, ...)
   # -- add node or relation callbacks if needed

   pylons = Pylons()
   handler.register_way_callback(pylons.create_from_way, pylons.valid_node_keys, ...)

   handler.parse(osm_file)

"""

import shapely.geometry as shg
import osmparser

class Coord(object):
    def __init__(self, lon, lat):
        self.lon = lon
        self.lat = lat
    def __str__(self):
        return "%g %g" % (self.lon, self.lat)

class Way(object):
    def __init__(self, osm_id, tags, refs):
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs

class OsmExtract(object):
    def __init__(self, ways_callback = None, nodes_callback = None, relations_callback = None, transform = None):
        self.coord_dict = {}
        self.way_list = []
        self.minlon = 181.
        self.maxlon = -181.
        self.minlat = 91.
        self.maxlat = -91.
        self.way_callbacks = {}
        self.transform = transform

    def parse(self, osm_fname):
        p = OSMParser(coords_callback=self.coords)
        print "start parsing coords"
        p.parse(osm_fname)
        print "done parsing"
        print "ncords:", len(self.coord_dict)
        print "bounds:", self.minlon, self.minlat, self.maxlon, self.maxlat

        print "start parsing ways and relations"
        p = OSMParser(ways_callback=self.ways)
        p.parse(osm_fname)
        #    p = OSMParser(relations_callback=way.relations)
        #    p.parse(osm_fname)
        self.process_ways()
        #tools.stats.print_summary()


    def register_way_callback(self, tag, func):
        self.way_callbacks[tag] = func


    def refs_to_coords(self, refs):
        """accept a list of OSM refs, return a list of coords.
        """
        coords = []
        for ref in refs:
                c = self.coord_dict[ref]
                coords.append(self.transform((c.lon, c.lat)))
        return coords

    def refs_to_ring(self, refs, inner = False):
        """accept a list of OSM refs, return a linear ring. Also
           fixes face orientation, depending on inner/outer.
        """
        coords = []
        for ref in refs:
                c = self.coord_dict[ref]
                coords.append(self.transform((c.lon, c.lat)))

        #print "before inner", refs
#        print "cord", coords
        ring = shg.polygon.LinearRing(coords)
        # -- outer -> CCW, inner -> not CCW
        if ring.is_ccw == inner:
            ring.coords = list(ring.coords)[::-1]
        return ring

    def ways(self, ways):
        """callback method for ways"""
        for osm_id, tags, refs in ways:
#            if tools.stats.objects >= parameters.MAX_OBJECTS: return
            self.way_list.append(Way(osm_id, tags, refs))

    def process_ways(self):
        for way in self.way_list:
            for tag in self.way_callbacks:
                if tag in way.tags:
                    coords = self.refs_to_coords(way.refs)
                    self.way_callbacks[tag](way.osm_id, way.tags, coords)

    def coords(self, coords):
        for osm_id, lon, lat in coords:
            #print '%s %.4f %.4f' % (osm_id, lon, lat)
            self.coord_dict[osm_id] = Coord(lon, lat)
            if lon > self.maxlon: self.maxlon = lon
            if lon < self.minlon: self.minlon = lon
            if lat > self.maxlat: self.maxlat = lat
            if lat < self.minlat: self.minlat = lat


