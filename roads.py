#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Experimental code.
python -m cProfile -o prof ./roads.py -f LOWI/params-small
python -m cProfile -s 'cumtime' ./roads.py -f LOWI/params-small

Created on Sun Sep 29 10:42:12 2013

@author: tom
TODO:
x clusterize (however, you don't see residential roads in cities from low alt anyway. LOD?)
  - a road meandering along a cluster boarder should not be clipped all the time.
  - only clip if on next-to-next tile?
  - clip at next tile center?
- LOD
  - major roads - LOD rough
  - minor roads - LOD detail
  - roads LOD? road_rough, road_detail?
- handle junctions
- handle layers/bridges

junctions:
- currently, we get false positives: one road ends, another one begins.
- loop junctions:
    for the_node in nodes:
    if the_node is not endpoint: put way into splitting list
    #if only 2 nodes, and both end nodes, and road types compatible:
    #put way into joining list

we have
   attached_ways_dict: for each (true) junction node, store a list of tuples (attached way, is_first)

Render junction:
  if 2 ways:
    simply join here. Or ignore for now.
  else:
                              
              
      for the_way in ways:
        left_neighbor = compute from angles and width
        store end nodes coords separately
        add to object, get node index
        - store end nodes index in way
        - way does not write end node coords, central method does it
      write junction face

Splitting:
  find all junctions for the_way
  normally a way would have exactly two junctions (at the ends)
  sort junctions in way's node order:
    add junction node index to dict
    sort list
  split into njunctions-1 ways
Now each way's end node is either junction or dead-end.

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
from linear import LinearObject, max_slope_for_road
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
import networkx as nx

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
        if self.prio(way.tags['highway'], True) == 0:
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
        
    def probe_elev_at_nodes(self):
        """add elevation info to all nodes"""
        for the_node in self.nodes_dict.values():
            the_node.MSL = self.elev((the_node.lon, the_node.lat), is_global=True)
            the_node.h_add = 0.
    
    
    def propagate_h_add(self):
        """start at bridges, propagate h_add through nodes"""
        for the_bridge in self.bridges_list:
            if the_bridge.osm_id == 126452863:
#                print "here"
                label=True
                continue
            else:
                label=False
            # build tree starting at node0
            # take out bridge edge
            node0 = the_bridge.refs[0]
            node1 = the_bridge.refs[-1]
            self.G.remove_edge(node0, node1)

            for ref0, ref1 in nx.bfs_edges(self.G, node0):
                obj = self.G[ref0][ref1]['obj']
                dh_dx = max_slope_for_road(obj) 
                n0 = self.nodes_dict[ref0]
                n1 = self.nodes_dict[ref1]
                if n1.h_add > 0:
                    break
                if label: self.debug_label_node(ref0, n0.h_add)
                #n1.h_add = max(0, n0.h_add - obj.center.length * parameters.DH_DX)
                n1.h_add = max(0, n0.MSL + n0.h_add - obj.center.length * dh_dx - n1.MSL)
                if label: self.debug_label_node(ref1, n1.h_add)
                if n1.h_add <= 0.:
                    break

            for ref0, ref1 in nx.bfs_edges(self.G, node1):
                obj = self.G[ref0][ref1]['obj']
                dh_dx = max_slope_for_road(obj) 
                n0 = self.nodes_dict[ref0]
                n1 = self.nodes_dict[ref1]
                if n1.h_add > 0:
                    break
                if label: self.debug_label_node(ref0, n0.h_add)
                n1.h_add = max(0, n0.MSL + n0.h_add - obj.center.length * dh_dx - n1.MSL)
                if label: self.debug_label_node(ref1, n1.h_add)
                if n1.h_add <= 0.:
                    break

            # traverse tree:
#            bla
            #   h_add_0 at start node
            # if h_add_1 == 0:
            #   h_add_1 at end node = max(0, h_add_0 - edge_len * dh_dl)
            # else:
            #   bla
            # same with node1
            self.G.add_edge(node0, node1, obj=the_bridge)
    
    def create_linear_objects(self):
        self.G=nx.Graph()

        for the_way in self.ways_list:
            prio = None
            try:
                access = not (the_way.tags['access'] == 'no')
            except:
                access = 'yes'
    
            width = 9
            tex_y0 = 2/8.
            tex_y1 = 3/8.
            AGL_ofs = 1.0 + random.uniform(0.01, 0.1)
            AGL_ofs = 0.05
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
                    tex_y1 = 1/8.
    
            if prio in [1, 2]:
                tex_y0 = 1/8.
                tex_y1 = 2/8.
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
                obj = LinearBridge(self.transform, self.elev, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
                self.bridges_list.append(obj)
            else:
                obj = LinearObject(self.transform, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs)
    
                if obj.has_large_angle():
                    print "skipping OSM_ID %i: large angle. OSM error?" % obj.osm_id
                    continue
    
                obj.typ = prio
                self.roads_list.append(obj)
            self.G.add_edge(the_way.refs[0], the_way.refs[-1], obj=obj)

        # debug: plot graph
        if 0:
            pos = {}
            for ref, the_node in self.nodes_dict.iteritems():
                pos[ref] = (the_node.lon, the_node.lat)
            nx.draw(self.G, pos)
            plt.show() # display

    
    
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

    def find_junctions(self, ways_list, degree=2):
        """
        N = number of nodes
        find junctions by brute force:
        - for each node, store attached ways in a dict                O(N)
        - if a node has 2 ways, store that node as a candidate
        - remove entries/nodes that have less than 2 ways attached    O(N)
        - one way ends, other way starts: also an junction
        FIXME: use quadtree/kdtree
        """
        logging.info('Finding junctions...')
        self.attached_ways_dict = {} # a dict: for each ref (aka node) hold a list of attached ways
        for the_way in ways_list:
#            if the_way.osm_id == 4888143:
#                print "got 4888143"
            for i, ref in enumerate(the_way.refs):
#                if ref == 1132288594:
#                    print "F (%i)" % (the_way.osm_id), the_way.refs
                try:
#                    if the_way.osm_id == 4888143:
#                        print "  ref", self.nodes_dict[ref].osm_id
                    self.attached_ways_dict[ref].append((the_way, i == 0)) # store tuple (the_way, is_first)
#                    if len(self.attached_ways_dict[ref]) == 2:
                        # -- check if ways are actually distinct before declaring
                        #    an junction?
                        # not an junction if
                        # - only 2 ways && one ends && other starts
                        # easier?: only 2 ways, at least one node is middle node
#                        self.junctions_set.add(ref)
                except KeyError:
                    self.attached_ways_dict[ref] = [(the_way, i == 0)]  # initialize node

        # kick nodes that belong to one way only
        # TODO: is there something like dict comprehension?
        for ref, value in self.attached_ways_dict.items():
#            if len(value) >= 2: self.nodes_dict[ref].n_attached_ways = len(value)
            if len(value) < degree: # FIXME: join_ways, then return 2 here
                self.attached_ways_dict.pop(ref)
#            else:
#                pass
#                check if one is first node and one last node. If so, join_ways

    def count_inner_junctions(self, style):
        """count inner nodes which are junctions"""
        count = 0        
        for the_way in self.ways_list:
            for the_ref in the_way.refs[1:-1]:
                if the_ref in self.attached_ways_dict:
                    count += 1
                    self.debug_plot_ref(the_ref, style)
                    
        logging.debug("inner junctions %i" % count)
        return count

    def print_junctions_stats(self):
        num = np.zeros(10)
        for key, value in self.attached_ways_dict.items():
            num[len(value)] += 1
            if len(value) >= 5:
                print "m", len(value), key

        print "stats"
        for i, v in enumerate(num):
            print i, v

    def split_ways(self):
        """split ways such that none of the interiour nodes are junctions.
           I.e., each way object connects to at most two junctions.
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
                if the_ref in self.attached_ways_dict:
                    new_list.append(new_way)
                    self.debug_plot_way(new_way, '-', lw=1, mark_nodes=0)
                    new_way = init_from_existing(the_way, the_ref)
            if the_ref not in self.attached_ways_dict: # FIXME: store previous test?
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

    def compute_junction_nodes(self):
        """ac3d nodes that belong to an junction need special treatment to make sure
           the ways attached to an junction join exactly, i.e., without gaps or overlap. 
        """
        def pr_angle(a):
            print "%5.1f " % (a * 57.3),

        def angle_from(lin_obj, is_first):
            """if IS_FIRST, the way is pointing away from us, and we can use the angle straight away.
               Otherwise, add 180 deg.
            """
            if is_first:
                angle = lin_obj.angle[0]
            else:
                angle = lin_obj.angle[-1] + np.pi
                if angle > np.pi: angle -= np.pi * 2
            return angle

        for the_ref, ways_list in self.attached_ways_dict.items():
            # each junction knows about the attached ways
            # -- Sort (the_junction.ways) by angle, taking into account is_first. 
            #    This is tricky. x[0] is our linear_object (which has a property "angle").
            #    x[1] is our IS_FIRST flag.
            #    According to IS_FIRST use either first or last angle in list,
            #    (-1 + is_first) evaluates to 0 or -1.
            #    Sorting results in LHS neighbours.
            ways_list.sort(key=lambda x: angle_from(x[0], x[1])) 

            # testing            
            if 1:
                pref_an = -999
    #            print the_ref, " : ",
                for way, is_first in ways_list:
                    an = angle_from(way, is_first)
    
    #                print " (%i)" % way.osm_id, is_first,
    #                pr_angle(an)
                    assert(an > pref_an)
                    pref_an = an
                    
    #            if len(ways_list) > 3: bla
                #if the_ref == 290863179: bla

            our_node = np.array(ways_list[0][0].center.coords[-1 + ways_list[0][1]])
            for i, (way_a, is_first_a) in enumerate(ways_list):
                (way_b, is_first_b) = ways_list[(i+1) % len(ways_list)] # wrap around
                # now we have two neighboring ways
                print way_a, is_first_a, "joins with", way_b, is_first_b
                # compute their joining node
                index_a = -1 + is_first_a                
                index_b = -1 + is_first_b                
                if 1:
                    va = way_a.vectors[index_a]
                    na = way_a.normals[index_a] * way_a.width / 2.
                    vb = way_b.vectors[index_b]
                    nb = way_b.normals[index_b] * way_b.width / 2.
                    if not is_first_a:
                        va *= -1
                        na *= -1
                    if is_first_b:
                        vb *= -1
                        nb *= -1
                    
                    Ainv = 1./(va[1]*vb[0]-va[0]*vb[1]) * np.array([[-vb[1], vb[0]], [-va[1], va[0]]])
                    RHS = (nb - na)
                    s = np.dot(Ainv, RHS)
    # FIXME: check which is faster
                    A = np.vstack((va, -vb)).transpose()
                    s = scipy.linalg.solve(A, RHS)
                    q = our_node + na * s[0]

                way_a_lr = way_a.edge[1-is_first_a] #.coords [index_a]
                way_b_lr = way_b.edge[is_first_b]  #.coords[index_b]

                q1 = way_a_lr.junction(way_b_lr)
                print q, q1
                way_a.plot(center=False, left=True, right=True, show=False)
                way_b.plot(center=False, left=True, right=True, clf=False, show=False)
                plt.plot(q[0], q[1], 'b+')
                plt.plot(q1.coords[0][0], q1.coords[0][1], 'bo')
                plt.show()
                
                
                # create ac3d node, insert, get index                
                # store index for junction area polygon
                # store that node index in each way as first_left, first_right, last_left, last_right

            # write junction area polygon


    def debug_plot_ref(self, ref, style): 
        plt.plot(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, style)
#        plt.text(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, ref.osm_id)


    def debug_plot_way(self, way, ls, lw, color=False, mark_nodes=False, show_label=False):
#        return
        col = ['b', 'r', 'y', 'g', '0.25', 'k', 'c']
        if not color:
            color = col[random.randint(0, len(col)-1)]
            #color = col[(way.osm_id + len(way.refs)) % len(col)]
            #color = col[self.prio(way.tags['highway'], True) % len(col)]

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
    
    def debug_plot_junctions(self, style):
        for ref in self.attached_ways_dict:
            node = self.nodes_dict[ref]
            plt.plot(node.lon, node.lat, style, mfc='None')
            #plt.text(node.lon, node.lat, node.osm_id, color='r')
    def debug_label_node(self, ref, text=""):
            node = self.nodes_dict[ref]
            plt.plot(node.lon, node.lat, 'rs', mfc='None', ms=10)
            plt.text(node.lon+0.0001, node.lat, str(node.osm_id) + " h" + str(text))

    def debug_plot(self, save=False, plot_junctions=False, show=False, label_nodes=[]):
        if plot_junctions:
            self.debug_plot_junctions('o')            
        for ref in label_nodes:
            self.debug_label_node(ref)
            
        for the_way in self.ways_list:
            self.debug_plot_way(the_way, '-', lw=0.5)
            
            if 0:
                ref = the_way.refs[0]
                self.debug_label_node(ref)
                ref = the_way.refs[-1]
                self.debug_label_node(ref)

        if save:
            plt.savefig(save)
        if show:
            plt.show()
            

    def cleanup_junctions(self):
        """Remove junctions that
           - have less than 3 ways attached
        """
        pass

    def join_ways(self):
        """join ways that
           - don't make an junction and
           - are of compatible type
        """
        pass


    def join_degree2_junctions(self):
        """bla"""
        for ref, ways in self.attached_ways_dict.iteritems():
            if len(ways) == 2:
#                bla
                pass

    def debug_test(self):
        print "138: ", self.nodes_dict[1401732138].h_add
        print "139: ", self.nodes_dict[1401732138].h_add
        
    def debug_label_nodes(self, stg_manager):
        """write OSM_ID for nodes"""
        # -- write OSM_ID label
        ac = ac3d.Writer(tools.stats, show_labels=True)
        file_name = "labels"
#        ac3d_obj = ac.new_object(file_name, '', default_swap_uv=True)
        
        for way in self.bridges_list:
            the_node = self.nodes_dict[way.refs[0]]
            anchor = vec2d(self.transform.toLocal(vec2d(the_node.lon, the_node.lat)))
            anchor.x += random.uniform(-1,1)
            e = self.elev(anchor) + 20.
            ac.add_label('   ' + str(the_node.osm_id) + " h="+str(the_node.h_add), -anchor.y, e, -anchor.x, scale=2)

            the_node = self.nodes_dict[way.refs[-1]]
            anchor = vec2d(self.transform.toLocal(vec2d(the_node.lon, the_node.lat)))
            anchor.x += random.uniform(-1,1)
            e = self.elev(anchor)
            ac.add_label('   ' + str(the_node.osm_id) + " h="+str(the_node.h_add), -anchor.y, e, -anchor.x, scale=2)
#            bla            
        path_to_stg = stg_manager.add_object_static(file_name + '.ac', vec2d(self.transform.toGlobal((0,0))), 0, 0)
        ac.write_to_file(path_to_stg + file_name)

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

        for the_object in self.bridges_list + self.roads_list:
            self.clusters.append(vec2d(the_object.center.centroid.coords[0]), the_object)
        #self.objects = None
        

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
    if 0:
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

    if 1:
        logging.debug("len before %i" % len(roads.ways_list))
        roads.find_junctions(roads.ways_list)
        #roads.debug_plot_junctions('ks')
        #roads.count_inner_junctions('bs')
        roads.split_ways()
        roads.find_junctions(roads.ways_list, 3)
#        roads.print_junctions_stats()
        plt.clf()
#        roads.count_inner_junctions('rs')
        #bla
        #roads.debug_print_dict()
        #roads.debug_plot_junctions('k.')
        #sys.exit(0)

    #    roads.join_ways()
        logging.debug("len after %i" % len(roads.ways_list))

    roads.probe_elev_at_nodes()
    roads.create_linear_objects()
    roads.debug_test()
    roads.join_degree2_junctions()
    roads.debug_test()
    roads.propagate_h_add()
    roads.debug_test()
#    roads.debug_plot(show=True, plot_junctions=True)#, label_nodes=[1132288594, 1132288612])
#    print "before", len(roads.attached_ways_dict)

#    roads.find_junctions(roads.roads_list)
    if 0:
        roads.compute_junction_nodes()
#    print "after", len(roads.attached_ways_dict)
    
#        sys.exit(0)

    #roads.cleanup_junctions()
#    roads.objects = [roads.objects[0]]
    roads.clusterize()
#    scale_test(transform, elev)

    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, overwrite=True)
    roads.debug_label_nodes(stg_manager)

    # -- write stg
    for cl in roads.clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS: continue # skip almost empty clusters

        replacement_prefix = re.sub('[\/]','_', parameters.PREFIX)
        file_name = replacement_prefix + "roads%02i%02i" % (cl.I.x, cl.I.y)
        center_global = vec2d(tools.transform.toGlobal(cl.center))
        offset_local = cl.center
        cluster_elev = elev(center_global, True)
        #cluster_elev = 0.
        # -- Now write cluster to disk.
        #    First create ac object. Write cluster's objects. Register stg object.
        #    Write ac to file.
        ac = ac3d.Writer(tools.stats, show_labels=True)
        ac3d_obj = ac.new_object(file_name, 'tex/roads.png', default_swap_uv=True)
        for rd in cl.objects:
            if rd.osm_id == 98659369:
                print "hhhhh", file_name
            rd.write_to(ac3d_obj, elev, cluster_elev, ac, offset=offset_local) # fixme: remove .ac, needed only for adding debug labels

        path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, cluster_elev, 0)
        ac.write_to_file(path_to_stg + file_name)
        write_xml(path_to_stg, file_name, file_name)
        tools.install_files(['roads.eff'], path_to_stg)

    debug_create_eps(roads, roads.clusters, elev, plot_cluster_borders=1)
    stg_manager.write()

    elev.save_cache()
    logging.info('Done.')


if __name__ == "__main__":
    main()
