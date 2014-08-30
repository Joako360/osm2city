#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Experimental code.

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
- clusterize
  - a road meandering along a cluster boarder should not be clipped all the time.
  - only clip if on next-to-next tile?
  - clip at next tile center?
- LOD
  - major roads - LOD rough
  - minor roads - LOD detail
  - roads LOD? road_rough, road_detail?
- handle intersections
- handle layers/bridges

Intersections:
- currently, we get false positives: one road ends, another one begins.
- loop intersections:
    for the_node in nodes:
    if the_node is not endpoint: put way into splitting list
    #if only 2 nodes, and both end nodes, and road types compatible:
    #put way into joining list

Render intersection:
  if 2 ways:
    simply join here. Or ignore for now.
  else:
      for the_way in ways:
        left_neighbor = compute from angles and width
        store end nodes coords separately
        add to object, get node index
        - store end nodes index in way
        - way does not write end node coords, central method does it
      write intersection face

Splitting:
  find all intersections for the_way
  normally a way would have exactly two intersections (at the ends)
  sort intersections in way's node order:
    add intersection node index to dict
    sort list
  split into nintersections-1 ways
Now each way's end node is either intersection or dead-end.

Joining:

required graph functions:
- find neighbours
-
"""

import scipy.interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import textwrap
import coordinates
import tools
import parameters
import sys
import math
import calc_tile
import os
import ac3d
from linear import LinearObject
from linear_bridge import LinearBridge

import logging
import osmparser
import stg_io2
import objectlist
import tools
from cluster import Clusters
# debug stuff
import test
from pdb import pm
#from memory_profiler import profile
import mem
import gc
import time
import re
import random

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark our edits

# -----------------------------------------------------------------------------
def no_transform((x, y)):
    return x, y

class Roads(objectlist.ObjectList):
    valid_node_keys = []

    #req_and_valid_keys = {"valid_way_keys" : ["highway"], "req_way_keys" : ["highway"]}
    req_keys = ['highway', 'railway']

    def __init__(self, transform, elev):
        super(Roads, self).__init__(transform)
        self.elev = elev
        self.ways_list = []
        self.bridges_list = []
        self.roads_list = []

    def store_uncategorized(self, way, nodes_dict):
        pass

    def store_way(self, way, nodes_dict):
        """take one osm way, store it. A linear object is created later."""
        if not self.min_max_scanned:
            self._process_nodes(nodes_dict)
            logging.info("len of nodes_dict %i" % len(nodes_dict))
            self.min_max_scanned = True
            cmin = vec2d(self.minlon, self.minlat)
            cmax = vec2d(self.maxlon, self.maxlat)
            logging.info("min/max " + str(cmin) + " " + str(cmax))
#            center_global = (cmin + cmax)*0.5
            #center_global = vec2d(1.135e1+0.03, 0.02+4.724e1)
            #self.transform = coordinates.Transformation(center_global, hdg = 0)
            #tools.init(self.transform) # FIXME. Not a nice design.

        #    pass
        #else: return
        if len(self.ways_list) >= parameters.MAX_OBJECTS: 
            return
        if 'railway' in way.tags and (not 'highway' in way.tags):
            return
        self.ways_list.append(way)
        #self.create_and_append(way.osm_id, way.tags, way.refs)
    
#    self.transform, self.elev, way.osm_id, way.tags, way.refs, nodes_dict, 
#    width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs
    def prio(self, highway_tag, access):
        if highway_tag == 'motorway' or highway_tag == 'motorway_link':
            prio = 5
        elif highway_tag == 'primary' or highway_tag == 'trunk':
            prio = 4
        elif highway_tag == 'secondary':
            prio = 3
        elif highway_tag == 'tertiary' or highway_tag == 'unclassified':
            prio = 2
        elif highway_tag == 'residential':
            prio = 1
        elif highway_tag == 'service' and access:
            prio = 0 # None
        else:
            prio = 0
        return prio
        
    
    def create_linear_objects(self):
        for the_way in self.ways_list:
            prio = None
            try:
                access = not (the_way.tags['access'] == 'no')
            except:
                access = 'yes'
    
            width = 9
            tex_y0 = 0.5
            tex_y1 = 0.75
            AGL_ofs = 1.0
            #if way.tags.has_key('layer'):
            #    AGL_ofs = 20.*float(way.tags['layer'])
            #print way.tags
            #bla
    
            if 'highway' in the_way.tags:
                prio = self.prio(the_way.tags['highway'], access)
            elif 'railway' in the_way.tags:
                if the_way.tags['railway'] in ['rail']:
                    prio = 6
                    width = 2.87
                    tex_y0 = 0
                    tex_y1 = 0.25
    
            if prio in [1, 2]:
                tex_y0 = 0.25
                tex_y1 = 0.5
                width=6
    
            #if prio != 1: prio = None
    
            if prio == 0:
    #            print "got", osm_id,
    #            for t in tags.keys():
    #                print (t), "=", (tags[t])+" ",
    #            print "(rejected)"
                continue
    
            #print "(accepted)"
            is_bridge = "bridge" in the_way.tags
            if is_bridge:
                bridge = LinearBridge(self.transform, self.elev, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
                self.bridges_list.append(bridge)
            else:
                road = LinearObject(self.transform, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
    
            if road.has_large_angle():
                print "skipping OSM_ID %i: large angle. OSM error?" % road.osm_id
                continue
    
            road.typ = prio
            self.roads_list.append(road)
    
    #        if self.has_duplicate_nodes(refs):
    #            print "dup nodes in", osm_id
                #road.plot(left=False, right=False, angle=False)

    def has_duplicate_nodes(self, refs):
        for i, r in enumerate(refs):
            if r in refs[i+1:]:
                return True

    def debug_print_dict(self):
        for key, value in self.attached_ways_dict.iteritems():
            print key, ": ",
            for way in value:
                print way.osm_id, "(", hex(id(way)), ")",
            print

    def find_intersections(self):
        """
        find intersections by brute force:
        - for each node, store attached ways in a dict
        - if a node has 2 ways, store that node as a candidate
        - one way ends, other way starts: also an intersection
        FIXME: use quadtree/kdtree
        """
        logging.info('Finding intersections...')
        self.intersections = []
        self.attached_ways_dict = {} # a dict: for each ref hold a list of attached ways
        for the_way in self.ways_list:
#            if the_way.osm_id == 4888143:
#                print "got 4888143"
            for ref in the_way.refs:
                try:
#                    if the_way.osm_id == 4888143:
#                        print "  ref", self.nodes_dict[ref].osm_id
                    self.attached_ways_dict[ref].append(the_way)
                    if len(self.attached_ways_dict[ref]) == 2:
                        # -- check if ways are actually distinct before declaring
                        #    an intersection?
                        # not an intersection if
                        # - only 2 ways && one ends && other starts
                        # easier?: only 2 ways, at least one node is middle node
                        self.intersections.append(ref)
                except KeyError:
                    self.attached_ways_dict[ref] = [the_way]  # initialize node

        # kick nodes that belong to one way only
        # TODO: is there something like dict comprehension?
        for key, value in self.attached_ways_dict.items():
            if len(value) < 2:
                self.attached_ways_dict.pop(key)
#            else:
#                pass
#                check if one is first node and one last node. If so, join_ways

#        for key, value in attached_ways_dict.items():
#            print key, value

    def count_inner_intersections(self, style):
        """count inner nodes which are intersections"""
        count = 0        
        for the_way in self.ways_list:
            for the_ref in the_way.refs[1:-1]:
#                if the_ref in self.attached_ways_dict:
                if the_ref in self.intersections:
                    count += 1
                    self.debug_plot_ref(the_ref, style)
                    
        logging.debug("inner intersections %i" % count)
        return count

    def split_ways(self):
        """split ways such that none of the interiour nodes are intersections.
           I.e., each way object connects to at most two intersections.
        """
            
        #plt.clf()
#        plt.xlim(0.002+1.138e1, 0.016+1.138e1)
#        plt.ylim(0.006+4.725e1, 0.013+4.725e1)

        #self.ways_list = self.ways_list[0:100]

#        for the_way in self.ways_list:
#            self.debug_plot_way(the_way, '-', lw=2, color='0.90', mark_nodes=False)
            #for the_ref in the_way.refs:
            #    if the_ref in self.attached_ways_dict:
            #        plt.plot(self.nodes_dict[the_ref].lon, self.nodes_dict[the_ref].lat, 'rx')

        def init_from_existing(way, ref):
            """return copy of way. The copy will have same osm_id and tags, but only given refs"""
            new_way = osmparser.Way(way.osm_id)
            new_way.tags = way.tags
            new_way.refs.append(ref)
            return new_way

        new_list = []
        for the_way in self.ways_list:
            self.debug_plot_way(the_way, '-', lw=2, color='0.90', show_label=0)
#            self.ways_list.remove(the_way)

            new_way = init_from_existing(the_way, the_way.refs[0])
            for the_ref in the_way.refs[1:]:
                new_way.refs.append(the_ref)
                if the_ref in self.intersections: #attached_ways_dict:
                    new_list.append(new_way)
                    self.debug_plot_way(new_way, '-', lw=1, mark_nodes=0)
                    new_way = init_from_existing(the_way, the_ref)
            if the_ref not in self.intersections: #attached_ways_dict:
                new_list.append(new_way)
                self.debug_plot_way(new_way, '--', lw=1, mark_nodes=0)
#            new_way.refs.append(the_way.refs[-1])
#            self.ways_list.append(new_way)
#            self.debug_plot_way(new_way, "--", lw=2, mark_nodes=True)

        self.ways_list = new_list
#            plt.show()
#            plt.clf()
#            break
                
        if 0:
            for key, value in self.attached_ways.items():
                if len(value) > 1:
                    print key
                    for way in value:
                        try:
                            print "  ", way.tags['name']
                        except:
                            print "  ", way

    def debug_plot_ref(self, ref, style): 
        plt.plot(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, style)
#        plt.text(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, ref.osm_id)


    def debug_plot_way(self, way, ls, lw, color=False, mark_nodes=False, show_label=False):
#        return
        col = ['b', 'r', 'y', 'g', '0.25', 'k', 'c']
        if not color:
            #color = col[random.randint(0, len(col)-1)]
            #color = col[(way.osm_id + len(way.refs)) % len(col)]
            color = col[self.prio(way.tags['highway'], True) % len(col)]

        osm_nodes = np.array([(self.nodes_dict[r].lon, self.nodes_dict[r].lat) for r in way.refs])
        a = osm_nodes
#        a = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])

#        a = np.array(way.center.coords)
#        a = np.array([transform.toGlobal(p) for p in a])
        #color = col[r.typ]
        plt.plot(a[:,0], a[:,1], ls, linewidth=lw, color=color)
        if mark_nodes:
            plt.plot(a[0,0], a[0,1], 'o', linewidth=lw, color=color)
            plt.plot(a[-1,0], a[-1,1], 'o', linewidth=lw, color=color)
        if show_label:
            plt.text(0.5*(a[0,0]+a[-1,0]), 0.5*(a[0,1]+a[-1,1]), way.osm_id)
    
    def debug_plot_intersections(self, style):
        for ref in self.intersections:
            node = self.nodes_dict[ref]
            plt.plot(node.lon, node.lat, style, mfc='None')
            #plt.text(node.lon, node.lat, node.osm_id, color='r')

    def cleanup_intersections(self):
        """Remove intersections that
           - have less than 3 ways attached
        """
        pass


    def join_ways(self):
        """join ways that
           - don't make an intersection and
           - are of compatible type
        """
        pass

    def clip_at_cluster_border(self):
        """
               - loop all objects
                 - intersects cluster border?
                   - remove it, insert splitted 
                 - put into cluster
        """
        for the_object in self.roads_list + self.bridges_list:
            print the_object

    def clusterize(self):
        lmin, lmax = [vec2d(self.transform.toLocal(c)) for c in parameters.get_extent_global()]
        self.clusters = Clusters(lmin, lmax, parameters.TILE_SIZE)

        for the_object in self.roads_list + self.bridges_list:
            self.clusters.append(vec2d(the_object.center.centroid.coords[0]), the_object)
        #self.objects = None
        
def create_ac(file_name, objects, center_global, elev, stg_manager):
    """unused ATM"""    
    ac = ac3d.Writer(tools.stats, show_labels=False)
    
    # -- debug: write individual .ac for every road
    if 0:
        for i, rd in enumerate(self.objects[:]):
            if rd.osm_id != 205546090: continue
            ac = ac3d.Writer(tools.stats, show_labels=False)
            obj = ac.new_object('roads_%s' % rd.osm_id, 'tex/roads.png')

            if not rd.write_to(obj, self.elev, ac): continue
            #print "write", rd.osm_id
            #ac.center()
            f = open('roads_%i_%03i.ac' % (rd.osm_id, i), 'w')
            f.write(str(ac))
            f.close()
        return
    
    # -- create ac object, then write obj to file
    # TODO: try emis for night lighting? Didnt look too bad, and gave better range
    # MATERIAL "" rgb 1 1 1 amb 1 1 1 emis 0.4 0.2 0.05 spec 0.5 0.5 0.5 shi 64 trans 0

    path = calc_tile.construct_path_to_stg(parameters.PATH_TO_SCENERY, center_global)
    stg_fname = calc_tile.construct_stg_file_name(center_global)


    obj = ac.new_object(file_name, 'tex/roads.png', default_swap_uv=True)
    for rd in objects:
        rd.write_to(obj, elev, ac)

    if 0:
        for ref in self.intersections:
            node = self.nodes_dict[ref]
            x, y = self.transform.toLocal((node.lon, node.lat))
            e = self.elev(vec2d(x, y)) + 5
            ac.add_label('I', -y, e, -x, scale=10)

    path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, 0, 0)
    stg_manager.write()
    ac.write_to_file(path_to_stg + file_name)
    write_xml(path_to_stg, file_name, 'roads')
    tools.install_files(['roads.eff'], path_to_stg)


def write_xml(path_to_stg, file_name, object_name):
    xml = open(path_to_stg + file_name + '.xml', "w")
    if parameters.TRAFFIC_SHADER_ENABLE:
        shader_str = "<inherits-from>Effects/road-high</inherits-from>"
    else:
        shader_str = "<inherits-from>roads</inherits-from>"
    xml.write(textwrap.dedent("""        <?xml version="1.0"?>
        <PropertyList>
        <path>%s.ac</path>
        <effect>
        <!--
            EITHER enable the traffic shader
                <inherits-from>Effects/road-high</inherits-from>
            OR the lightmap shader
                <inherits-from>roads</inherits-from>
        -->
                %s
                <object-name>%s</object-name>
        </effect>
        </PropertyList>
    """  % (file_name, shader_str, object_name)))


def debug_create_eps(roads, clusters, elev, plot_cluster_borders=0):
    """debug: plot roads map to .eps"""
    plt.clf()
    transform = tools.transform
    if 1:
        c = np.array([[elev.min.x, elev.min.y], 
                      [elev.max.x, elev.min.y], 
                      [elev.max.x, elev.max.y], 
                      [elev.min.x, elev.max.y],
                      [elev.min.x, elev.min.y]])
        #c = np.array([transform.toGlobal(p) for p in c])
        plt.plot(c[:,0], c[:,1],'r-', label="elev")
    

    col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k', 'c']
    col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
    lw    = [1, 1, 1, 1.2, 1.5, 2, 1]
    lw_w  = np.array([1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]) * 0.1

    if 1:
        for i, cl in enumerate(clusters):
            if plot_cluster_borders and len(cl.objects): 
                cluster_color = col[random.randint(0, len(col)-1)]
                c = np.array([[cl.min.x, cl.min.y], 
                              [cl.max.x, cl.min.y], 
                              [cl.max.x, cl.max.y], 
                              [cl.min.x, cl.max.y],
                              [cl.min.x, cl.min.y]])
                c = np.array([transform.toGlobal(p) for p in c])
                plt.plot(c[:,0], c[:,1], '-', color=cluster_color)
            for r in cl.objects:
                random_color = col[random.randint(0, len(col)-1)]
                osmid_color = col[(r.osm_id + len(r.refs)) % len(col)]                
                a = np.array(r.center.coords)
                a = np.array([transform.toGlobal(p) for p in a])
                #color = col[r.typ]
                try:
                    lw = lw_w[r.typ]
                except:
                    lw = lw_w[0]
                    
                plt.plot(a[:,0], a[:,1], color=cluster_color, linewidth=lw)

    #plt.show()
    #sys.exit(0)
        
    if 0:
        for r in roads:
            a = np.array(r.center.coords)
            a = np.array([transform.toGlobal(p) for p in a])
            plt.plot(a[:,0], a[:,1], color=col[r.typ], linewidth=lw[r.typ])
            #plt.plot(a[:,0], a[:,1], color='w', linewidth=lw_w[r.typ], ls=":")

    plt.axes().set_aspect('equal')
    #plt.show()
    plt.legend()
#    plt.xlim(0+1.138e1, 0.04+1.138e1)
#    plt.ylim(0+4.725e1, 0.03+4.725e1)
    plt.savefig('roads.eps')
    plt.clf()

def main():
    
    #logging.basicConfig(level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)
    
    import argparse
    parser = argparse.ArgumentParser(description="bridge.py reads OSM data and creates bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                      help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
    args = parser.parse_args()

    if args.filename is not None:
        parameters.read_from_file(args.filename)

    if args.e:
        parameters.NO_ELEV = True

    #parameters.show()

    center_global = parameters.get_center_global()
    osm_fname = parameters.get_OSM_file_name()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    elev = tools.get_interpolator(fake=parameters.NO_ELEV)
    print "tr 0", transform
    roads = Roads(transform, elev)
    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    source = open(osm_fname)
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.from_way, **roads.req_and_valid_keys)
#    roads.register_callbacks_in(handler)
    handler.register_way_callback(roads.store_way, req_keys=roads.req_keys)
    handler.register_uncategorized_way_callback(roads.store_uncategorized)
    handler.parse(source)
    
    logging.info("ways: %i", len(roads))
    
    
    if parameters.PATH_TO_OUTPUT:
        path_to_output = parameters.PATH_TO_OUTPUT
    else:
        path_to_output = parameters.PATH_TO_SCENERY


#    roads.objects = roads.objects[0:1000]
    #roads.clip_at_cluster_border()

    for the_way in roads.ways_list:
        roads.debug_plot_way(the_way, '-', lw=0.5)
#    plt.savefig("r_org.eps")

    if 1:
        logging.debug("len before %i" % len(roads.ways_list))
        roads.find_intersections()
        #roads.debug_plot_intersections('ks')
        roads.count_inner_intersections('bs')
        plt.savefig("r_org.eps")
        plt.clf()
        roads.split_ways()
        roads.find_intersections()
        #roads.debug_print_dict()
        #roads.debug_plot_intersections('k.')
        roads.count_inner_intersections('rs')
        plt.savefig("r_spl.eps")

    #    roads.join_ways()
        logging.debug("len after %i" % len(roads.ways_list))
#        sys.exit(0)
    roads.create_linear_objects()

    #roads.cleanup_intersections()
#    roads.objects = [roads.objects[0]]
    roads.clusterize()
#    scale_test(transform, elev)

    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, overwrite=True)

    # -- write stg
    for cl in roads.clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS: continue # skip almost empty clusters

        replacement_prefix = re.sub('[\/]','_', parameters.PREFIX)
        file_name = replacement_prefix + "roads%02i%02i" % (cl.I.x, cl.I.y)
        center_global = vec2d(tools.transform.toGlobal(cl.center))
        offset = cl.center

        ac = ac3d.Writer(tools.stats, show_labels=False)
        ac3d_obj = ac.new_object(file_name, 'tex/roads.png', default_swap_uv=True)
        for rd in cl.objects:
            rd.write_to(ac3d_obj, elev, ac, offset=offset) # fixme: remove .ac, needed only for adding debug labels

        path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, 0, 0)
        ac.write_to_file(path_to_stg + file_name)
        write_xml(path_to_stg, file_name, file_name)
        tools.install_files(['roads.eff'], path_to_stg)

    debug_create_eps(roads, roads.clusters, elev, plot_cluster_borders=1)
    stg_manager.write()

    elev.save_cache()
    logging.info('Done.')


if __name__ == "__main__":
    main()
