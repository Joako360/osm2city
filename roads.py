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

Data structures
---------------


nodes_dict: contains all osmparser.Nodes, by OSM_ID
  nodes_dict[OSM_ID] -> Node
  KEEP, because we have a lot more nodes than junctions.
  
Roads.G: graph
  its nodes represent junctions. Indexed by OSM_ID of osmparser.Nodes
  edges represent roads between junctions, and have obj=osmparser.Way
  self.G[ref_1][ref_2]['obj'] -> osmparser.Way

attached_ways_dict: for each (true) junction node, store a list of tuples (attached way, is_first)
  basically, this duplicates Roads.G!
  need self.G[ref]['stubs'][4]
  self.G[ref][] -> Junction.stubs_list[2]
    


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

import argparse
import logging
import math
import os
import re
import random
import textwrap

import matplotlib.pyplot as plt
import numpy as np
import scipy.interpolate
import shapely.geometry as shg

import ac3d
import coordinates
import graph
import linear
import linear_bridge
import objectlist
import osmparser
import parameters
import stg_io2
import textures.road
import tools
import troubleshoot
from vec2d import vec2d
from cluster import Clusters

OUR_MAGIC = "osm2roads"  # Used in e.g. stg files to mark our edits


def no_transform((x, y)):
    return x, y


def is_bridge(way):
    return "bridge" in way.tags


def is_railway(way):
    return "railway" in way.tags


class Roads(objectlist.ObjectList):
    valid_node_keys = []

    req_keys = ['highway', 'railway', 'amenity']

    def __init__(self, transform, elev):
        super(Roads, self).__init__(transform)
        self.elev = elev
        self.ways_list = []
        self.bridges_list = []
        self.roads_list = self.objects  # alias
        self.nodes_dict = {}

    def __str__(self):
        return "%i ways, %i roads, %i bridges" % (len(self.ways_list), len(self.roads_list), len(self.bridges_list))

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

        if len(self.ways_list) >= parameters.MAX_OBJECTS: 
            return

        if way.osm_id in parameters.SKIP_LIST:
            logging.info("SKIPPING OSM_ID %i" % way.osm_id)
            return

        #if not 'railway' in way.tags: # -- keep only railways
        #    return
            
        #if 'railway' in way.tags and (not 'highway' in way.tags):
        #    return
        if 'railway' in way.tags:
            pass
            #return # -- don't use railways
            #if way.tags['railway'] != 'rail':
            #    return
            
        try:
            if self.prio(way.tags['highway'], True) == 0:
                return
        except:
            pass
        self.ways_list.append(way)
        #self.create_and_append(way.osm_id, way.tags, way.refs)
    
#    self.transform, self.elev, way.osm_id, way.tags, way.refs, nodes_dict, 
#    width=width, tex_y0=tex_y0, tex_y1=tex_y1, AGL=0.1+0.005*prio+AGL_ofs
        
    def probe_elev_at_nodes(self):
        """add elevation info to all nodes"""
        for the_node in self.nodes_dict.values():
            if math.isnan(the_node.lon) or math.isnan(the_node.lat):
                logging.error("Nan encountered while probing elevation")
                continue
            the_node.MSL = self.elev((the_node.lon, the_node.lat), is_global=True)
            the_node.h_add = 0.
    
    def propagate_h_add_over_edge(self, ref0, ref1, args):
        """propagate h_add over edges of graph"""
        obj = self.G[ref0][ref1]['obj']
        dh_dx = linear.max_slope_for_road(obj)
        n0 = self.nodes_dict[ref0]
        n1 = self.nodes_dict[ref1]
        if n1.h_add > 0:
            return False
            # FIXME: should we really just stop here? Probably yes.
#        if label: self.debug_label_node(ref0, n0.h_add)
        #n1.h_add = max(0, n0.h_add - obj.center.length * parameters.DH_DX)
        n1.h_add = max(0, n0.MSL + n0.h_add - obj.center.length * dh_dx - n1.MSL)
#        if label: self.debug_label_node(ref1, n1.h_add)
        if n1.h_add <= 0.:
            return False
        return True
    
    def propagate_h_add(self):
        """start at bridges, propagate h_add through nodes"""
        for the_bridge in self.bridges_list:
            # build tree starting at node0
            node0 = the_bridge.refs[0]
            node1 = the_bridge.refs[-1]

            node0s = set([node1])
            visited = set([node0, node1])
            graph.for_edges_in_bfs_call(self.propagate_h_add_over_edge, None, self.G, node0s, visited)
            node0s = set([node0])
            visited = set([node0, node1])
            graph.for_edges_in_bfs_call(self.propagate_h_add_over_edge, None, self.G, node0s, visited)

    def build_graph(self, source_iterable):
        self.G = graph.Graph()
        for the_way in source_iterable:
            self.G.add_edge(the_way.refs[0], the_way.refs[-1], obj=the_way)

    def split_long_roads_between_bridges(self):
        """UNUSED.
           Split long roads between bridges."""

        def find_edges(node0):
            """start at given node, find next-to-next edge. If that is a bridge, add to list"""
            N1 = nx.all_neighbors(self.G, node0)
            new_ways_to_split = []
            for node1 in N1:
                N2 = nx.all_neighbors(self.G, node1)
                for node2 in N2:
                    if node2 == node0: continue
                    obj = self.G[node1][node2]['obj'] 
                    if is_bridge(obj):
                        obj = self.G[node0][node1]['obj']
                        new_ways_to_split.append(obj)
                        break
            return new_ways_to_split

        ways_to_split = set()
        for the_way in self.ways_list:
            if not is_bridge(the_way): continue
            if the_way.osm_id == 24797900:
                pass
            # take out bridge edge
            bridge_node0 = the_way.refs[0]
            bridge_node1 = the_way.refs[-1]
            self.G.remove_edge(bridge_node0, bridge_node1)
            a = find_edges(bridge_node0)
            [ways_to_split.add(i) for i in a]
            a = find_edges(bridge_node1)
            [ways_to_split.add(i) for i in a]
            self.G.add_edge(bridge_node0, bridge_node1, obj=the_way)

        for the_way in ways_to_split:
            if 0:            
                osm_nodes = [self.nodes_dict[r] for r in the_way.refs]
                nodes = np.array([transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
                n = len(nodes)
                for i in range(n-1):
                    dx, dy = nodes[n+1] - nodes[n]
                    bla
            else:
                n = len(the_way.refs)
                if n < 3: continue
                split_index = n/2
                
            self.ways_list.remove(the_way)
            self.G.remove_edge(the_way.refs[0], the_way.refs[-1])
            new_way1 = self.init_way_from_existing(the_way, the_way.refs[:split_index+1])
            new_way2 = self.init_way_from_existing(the_way, the_way.refs[split_index:])
            self.ways_list += [new_way1, new_way2]
            self.G.add_edge(new_way1.refs[0], new_way1.refs[-1], obj=new_way1)
            self.G.add_edge(new_way2.refs[0], new_way2.refs[-1], obj=new_way2)


    def LineString_from_way(self, way):
        osm_nodes = [self.nodes_dict[r] for r in way.refs]
        nodes = np.array([self.transform.toLocal((n.lon, n.lat)) for n in osm_nodes])
        return shg.LineString(nodes)

    def cleanup_topo(self):
        logging.debug("len before %i" % len(self.ways_list))
        self.attached_ways_dict = self.find_junctions(self.ways_list)
        #self.debug_plot_junctions('ks')
        #self.count_inner_junctions('bs')
        self.split_ways_at_inner_junctions()
        #self.debug_print_refs_of_way(239806431)
        self.join_degree2_junctions() 
        #self.debug_print_refs_of_way(239806431)
        #self.find_junctions(self.ways_list, 3)
        del self.attached_ways_dict
    #        self.print_junctions_stats()
    #        self.count_inner_junctions('rs')
        #bla
        #self.debug_print_dict()
        #self.debug_plot_junctions('k.')
        #sys.exit(0)
    
        logging.debug("len after %i" % len(self.ways_list))

    def remove_tunnels(self):
        """remove tunnels"""
        for the_way in self.ways_list:
            if "tunnel" in the_way.tags:
                self.ways_list.remove(the_way)

    def replace_short_bridges_with_ways(self):
        """remove bridge tag from short bridges, making them a simple way"""
        for the_way in self.ways_list:
            if is_bridge(the_way):
                center = self.LineString_from_way(the_way)
                if center.length < parameters.BRIDGE_MIN_LENGTH:
                    the_way.tags.pop('bridge')
    
    def keep_only_bridges_and_embankments(self):
        """remove everything that is not elevated""" 
        for the_way in self.roads_list:
            h_add = np.array([abs(self.nodes_dict[the_ref].h_add) for the_ref in the_way.refs])
            if h_add.sum() == 0:
                self.roads_list.remove(the_way)
                logging.debug("kick %i", the_way.osm_id)

    def prio(self, highway_tag, access):
        if highway_tag == 'motorway':
            prio = 5
        elif highway_tag == 'primary' or highway_tag == 'trunk':
            prio = 4
        elif highway_tag == 'secondary':
            prio = 3
        elif highway_tag == 'tertiary' or highway_tag == 'unclassified'  or highway_tag == 'motorway_link':
            prio = 2
        elif highway_tag == 'residential':
            prio = 1
        elif highway_tag == 'service' and access:
            prio = 0 # None
        else:
            prio = 0
        return prio
    
    def create_linear_objects(self):
        self.G = graph.Graph()

        for the_way in self.ways_list:
            prio = None
            try:
                access = not (the_way.tags['access'] == 'no')
            except:
                access = 'yes'
    
            width = 9
            tex = textures.road.ROAD_3
            AGL_ofs = random.uniform(0.01, 0.1)
            #AGL_ofs = 0.0
            #if way.tags.has_key('layer'):
            #    AGL_ofs = 20.*float(way.tags['layer'])
            #print way.tags
    
            if 'highway' in the_way.tags:
                prio = self.prio(the_way.tags['highway'], access)
            elif 'railway' in the_way.tags:
                if the_way.tags['railway'] in ['rail']:
                    prio = 6
                    width = 2.87
                    tex = textures.road.TRACK
                elif the_way.tags['railway'] in ['tram']:
                    prio = 6
                    width = 2.87
                    tex = textures.road.TRAMWAY
#            TA: disabled parking for now. While certainly good to have,
#                parking in OSM is not a linear feature in general.
#                We'd need to add areas.    
#            elif 'amenity' in the_way.tags:
#                if the_way.tags['amenity'] in ['parking']:
#                    prio = 7
    
            if prio in [5]:
                tex = textures.road.ROAD_3
                width=6
            elif prio in [3, 4]:
                tex = textures.road.ROAD_2
                width=6
            elif prio in [0, 1, 2]:
                tex = textures.road.ROAD_1
                width=6
    
            if prio == 0 or prio == None:
    #            print "got", osm_id,
    #            for t in tags.keys():
    #                print (t), "=", (tags[t])+" ",
    #            print "(rejected)"
                continue
    
            try:
                if is_bridge(the_way):
                    obj = linear_bridge.LinearBridge(self.transform, self.elev, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex=tex, AGL=0.01+0.005*prio+AGL_ofs)
                    obj.typ = prio
                    self.bridges_list.append(obj)
                else:
                    obj = linear.LinearObject(self.transform, the_way.osm_id, the_way.tags, the_way.refs, self.nodes_dict, width=width, tex=tex, AGL=0.01+0.005*prio+AGL_ofs)
                    obj.typ = prio
                    self.roads_list.append(obj)
            except ValueError, reason:
                logging.warn("skipping OSM_ID %i: %s" % (the_way.osm_id, reason))
                continue

            self.G.add_edge(obj)

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
        - one way ends, other way starts: also a junction
        FIXME: use quadtree/kdtree
        """
        
        logging.info('Finding junctions...')
        attached_ways_dict = {} # a dict: for each ref (aka node) hold a list of attached ways
        for j, the_way in enumerate(ways_list):
            tools.progress(j, len(ways_list))
            for i, ref in enumerate(the_way.refs):
                try:
                    attached_ways_dict[ref].append((the_way, i == 0)) # store tuple (the_way, is_first)
                    # -- check if ways are actually distinct before declaring
                    #    an junction?
                    # not an junction if
                    # - only 2 ways && one ends && other starts
                    # easier?: only 2 ways, at least one node is middle node
#                        self.junctions_set.add(ref)
                except KeyError:
                    attached_ways_dict[ref] = [(the_way, i == 0)]  # initialize node

        # kick nodes that belong to one way only
        for ref, the_ways in attached_ways_dict.items():
#            if len(value) >= 2: self.nodes_dict[ref].n_attached_ways = len(value)
            if len(the_ways) < degree: # FIXME: join_ways, then return 2 here
                attached_ways_dict.pop(ref)
#            else:
#                pass
#                check if one is first node and one last node. If so, join_ways
        return attached_ways_dict
        
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

    def init_way_from_existing(self, way, ref):
        """return copy of way. The copy will have same osm_id and tags, but
           only given refs"""
        new_way = osmparser.Way(way.osm_id)
        new_way.tags = way.tags
        try:
            new_way.refs += ref
        except TypeError:
            new_way.refs.append(ref)
        return new_way
        
    def split_ways_at_inner_junctions(self):
        """split ways such that none of the interiour nodes are junctions.
           I.e., each way object connects to at most two junctions.
        """
        logging.info('Splitting ways at inner junctions...')
        # FIXME: auch splitten, wenn Weg1 von Weg2 erst abzweigt und später wieder hinzukommt 
        #        i.e. way1 and way2 share TWO nodes, both end nodes of one of them 
        new_list = []
        for i, the_way in enumerate(self.ways_list):
            tools.progress(i, len(self.ways_list))
            self.debug_plot_way(the_way, '-', lw=2, color='0.90', show_label=0)
#            self.ways_list.remove(the_way)

            new_way = self.init_way_from_existing(the_way, the_way.refs[0])
            for the_ref in the_way.refs[1:]:
                new_way.refs.append(the_ref)
                if the_ref in self.attached_ways_dict:
                    new_list.append(new_way)
                    self.debug_plot_way(new_way, '-', lw=1)
                    new_way = self.init_way_from_existing(the_way, the_ref)
            if the_ref not in self.attached_ways_dict: # FIXME: store previous test?
                new_list.append(new_way)
                self.debug_plot_way(new_way, '--', lw=1)
#            new_way.refs.append(the_way.refs[-1])
#            self.ways_list.append(new_way)
#            self.debug_plot_way(new_way, "--", lw=2, mark_nodes=True)

        self.ways_list = new_list

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
        if not parameters.DEBUG_PLOT: return
        plt.plot(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, style)
#        plt.text(self.nodes_dict[ref].lon, self.nodes_dict[ref].lat, ref.osm_id)

    def debug_plot_way(self, way, ls, lw, color=False, ends_marker=False, show_label=False, show_ends=False):
        if not parameters.DEBUG_PLOT: return
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
        if ends_marker:
            plt.plot(a[0,0], a[0,1], ends_marker, linewidth=lw, color=color)
            plt.plot(a[-1,0], a[-1,1], ends_marker, linewidth=lw, color=color)
        if show_label:
            plt.text(0.5*(a[0,0]+a[-1,0]), 0.5*(a[0,1]+a[-1,1]), way.osm_id, color="b")
    
    def debug_plot_junctions(self, style):
        if not parameters.DEBUG_PLOT: return
        for ref in self.attached_ways_dict:
            node = self.nodes_dict[ref]
            plt.plot(node.lon, node.lat, style, mfc='None')
            #plt.text(node.lon, node.lat, node.osm_id, color='r')

    def debug_label_node(self, ref, text=""):
        if not parameters.DEBUG_PLOT: return

        node = self.nodes_dict[ref]
        plt.plot(node.lon, node.lat, 'rs', mfc='None', ms=10)
        plt.text(node.lon+0.0001, node.lat, str(node.osm_id) + " h" + str(text))

    def debug_plot(self, save=False, plot_junctions=False, show=False, label_nodes=[], label_all_ways=False, clusters=None):
        if not parameters.DEBUG_PLOT: return
        plt.clf()
        if plot_junctions:
            self.debug_plot_junctions('o')            
        for ref in label_nodes:
            self.debug_label_node(ref)
        col = ['b', 'r', 'y', 'g', '0.75', '0.5', 'k', 'c']
        col = ['0.5', '0.75', 'y', 'g', 'r', 'b', 'k']
        lw    = [1, 1, 1, 1.2, 1.5, 2, 1]
        lw_w  = np.array([1, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]) * 0.1

        if clusters:
            for i, cl in enumerate(clusters):
                if len(cl.objects): 
                    cluster_color = col[random.randint(0, len(col)-1)]
                    c = np.array([[cl.min.x, cl.min.y], 
                                  [cl.max.x, cl.min.y], 
                                  [cl.max.x, cl.max.y], 
                                  [cl.min.x, cl.max.y],
                                  [cl.min.x, cl.min.y]])
                    c = np.array([self.transform.toGlobal(p) for p in c])
                    plt.plot(c[:,0], c[:,1], '-', color=cluster_color)
                for r in cl.objects:
                    random_color = col[random.randint(0, len(col)-1)]
                    osmid_color = col[(r.osm_id + len(r.refs)) % len(col)]                
                    a = np.array(r.center.coords)
                    a = np.array([self.transform.toGlobal(p) for p in a])
                    #color = col[r.typ]
                    try:
                        lw = lw_w[r.typ]
                    except:
                        lw = lw_w[0]
                        
                    plt.plot(a[:,0], a[:,1], color=cluster_color, linewidth=lw+2)

        for the_way in self.ways_list:
            self.debug_plot_way(the_way, '-', lw=0.5, show_label=True, ends_marker='x')
            
            if 1:
                ref = the_way.refs[0]
                self.debug_label_node(ref)
                ref = the_way.refs[-1]
                self.debug_label_node(ref)

        if save:
            plt.savefig(save)
        if show:
            plt.show()

    def debug_show_h_add(self, label=""):
        return
        print "====", label
        IDs=[473886072]
        for the_id in IDs:
            print "> ID %i h_add %g" % (the_id, self.nodes_dict[the_id].h_add)
        return
        for the_node in self.nodes_dict.itervalues():
            print "n %12i h_add %5.2f" % (the_node.osm_id, the_node.h_add)

    def cleanup_junctions(self):
        """Remove junctions that
           - have less than 3 ways attached
        """
        pass

    def compatible_ways(self, way1, way2):
        logging.debug("trying join %i %i" % (way1.osm_id, way2.osm_id))
        if is_railway(way1) != is_railway(way2):
            logging.debug("Nope, either both or none must be railway")
            return False
        if is_bridge(way1) != is_bridge(way2):
            logging.debug("Nope, either both or none must be a bridge")
            return False
        return True

    def attached_ways_dict_remove(self, the_ref, the_way, ignore_missing_ref=False):
        """remove given way from given node in attached_ways_dict"""
        if ignore_missing_ref and the_ref not in self.attached_ways_dict:
            logging.debug("not removing way from the ref %i because the ref is not in attached_ways_dict" % the_ref)
            return
        for way, boolean in self.attached_ways_dict[the_ref]:
            if way == the_way:
                logging.debug("removing way %s from node %i", the_way, the_ref)
                self.attached_ways_dict[the_ref].remove((the_way, boolean))

    def attached_ways_dict_append(self, the_ref, the_way, is_first, ignore_missing_ref=False):
        """append given way to attached_ways_dict. If ignore_non_existing is True, silently
           do nothing in case the_ref does not exist. Otherwise we may get a KeyError."""
        if ignore_missing_ref and the_ref not in self.attached_ways_dict:
            return
        self.attached_ways_dict[the_ref].append((the_way, is_first))

    def join_ways(self, way1, way2):
        """join ways that
           - don't make an junction and
           - are of compatible type
           must share exactly one node
        """
        logging.debug("Joining %i and %i" % (way1.osm_id, way2.osm_id))
        if way1.osm_id == way2.osm_id:
            logging.warn("  Not joining way %i with itself" % way1.osm_id)
            return
        if way1.refs[0] == way2.refs[0]:
            new_refs = way1.refs[::-1] + way2.refs[1:]
        elif way1.refs[0] == way2.refs[-1]:
            new_refs = way2.refs + way1.refs[1:]
        elif way1.refs[-1] == way2.refs[0]:
            new_refs = way1.refs + way2.refs[1:]
        elif way1.refs[-1] == way2.refs[-1]:
            new_refs = way1.refs[:-1] + way2.refs[::-1]
        else:
            logging.warn("not joining ways that share no endpoint %i %i" % (way1.osm_id, way2.osm_id))
            return
            
        new_way = self.init_way_from_existing(way1, new_refs)
        logging.debug("old and new" + str(way1) + str(new_way))

        self.attached_ways_dict_remove(way1.refs[0],  way1, ignore_missing_ref=True)
        self.attached_ways_dict_remove(way1.refs[-1], way1, ignore_missing_ref=True)
        self.attached_ways_dict_remove(way2.refs[0],  way2, ignore_missing_ref=True)
        self.attached_ways_dict_remove(way2.refs[-1], way2, ignore_missing_ref=True)

        self.attached_ways_dict_append(new_way.refs[0], new_way, is_first=True, ignore_missing_ref=True)
        self.attached_ways_dict_append(new_way.refs[-1], new_way, is_first=False, ignore_missing_ref=True)

        try:
            self.ways_list.remove(way1)
            logging.debug("1ok ")
        except ValueError:
            self.ways_list.remove(self.debug_find_way_by_osm_id(way1.osm_id))
            logging.debug("1not ")
        try:
            self.ways_list.remove(way2)
            logging.debug("2ok")
        except ValueError:
            self.ways_list.remove(self.debug_find_way_by_osm_id(way2.osm_id))
            logging.debug("2not")
        self.ways_list.append(new_way)

    def join_degree2_junctions(self):
        """bla"""
        for ref, ways_tuple_list in self.attached_ways_dict.iteritems():
            if len(ways_tuple_list) == 2:
                if self.compatible_ways(ways_tuple_list[0][0], ways_tuple_list[1][0]):
                    self.join_ways(ways_tuple_list[0][0], ways_tuple_list[1][0])
                    
    def debug_find_way_by_osm_id(self, osm_id):
        for the_way in self.ways_list:
            if the_way.osm_id == osm_id:
                return the_way
        raise ValueError("way %i not found" % osm_id)

    def debug_is_osm_id_in_ways_list(self, osm_id):
        for the_way in self.ways_list:
            if the_way.osm_id == osm_id:
                return True
        return False
    
    def debug_test(self):
        print "138: ", self.nodes_dict[1401732138].h_add
        print "139: ", self.nodes_dict[1401732138].h_add
        
    def debug_keep_only(self, osm_id_list):
        """keep only ways of given osm_id"""
        new_list = []
        for the_obj in self.ways_list:
            if the_obj.osm_id in osm_id_list:
                print "keeping", the_obj.osm_id
                new_list.append(the_obj)
        self.ways_list = new_list

    def debug_drop_unused_nodes(self):
        new_nodes_dict = {}
        for the_list in [self.ways_list, self.bridges_list, self.roads_list]:
            for the_obj in the_list:
                for the_ref in the_obj.refs:
                    new_nodes_dict[the_ref] = self.nodes_dict[the_ref]
        self.nodes_dict = new_nodes_dict
                
    def debug_label_nodes(self, stg_manager, file_name="labels"):
        """write OSM_ID for nodes"""
        # -- write OSM_ID label
        ac = ac3d.File(stats=tools.stats, show_labels=True)
#        ac3d_obj = ac.new_object(file_name, '', default_swap_uv=True)

        for way in self.bridges_list + self.roads_list:
            # -- label center with way ID
            the_node = self.nodes_dict[way.refs[len(way.refs)/2]]
            anchor = vec2d(self.transform.toLocal(vec2d(the_node.lon, the_node.lat)))
#            anchor.x += random.uniform(-1,1)
            if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                logging.error("Nan encountered while probing anchor elevation")
                continue

            e = self.elev(anchor) + the_node.h_add + 1.
            ac.add_label('way %i' % (way.osm_id), -anchor.y, e, -anchor.x, scale=1.)

            # -- label first node
            the_node = self.nodes_dict[way.refs[0]]
            anchor = vec2d(self.transform.toLocal(vec2d(the_node.lon, the_node.lat)))
#            anchor.x += random.uniform(-1,1)
            if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                logging.error("Nan encountered while probing anchor elevation")
                continue

            e = self.elev(anchor) + the_node.h_add + 3.
            ac.add_label(' %i h=%1.1f' % (the_node.osm_id, the_node.h_add), -anchor.y, e, -anchor.x, scale=1.)

            # -- label last node
            if 1:
                the_node = self.nodes_dict[way.refs[-1]]
                anchor = vec2d(self.transform.toLocal(vec2d(the_node.lon, the_node.lat)))
#                anchor.x += random.uniform(-1,1)
                if math.isnan(anchor.lon) or math.isnan(anchor.lat):
                    logging.error("Nan encountered while probing anchor elevation")
                    continue

                e = self.elev(anchor) + the_node.h_add + 3.
                ac.add_label(' %i h=%1.1f' % (the_node.osm_id, the_node.h_add), -anchor.y, e, -anchor.x, scale=1.)
        path_to_stg = stg_manager.add_object_static(file_name + '.ac', vec2d(self.transform.toGlobal((0,0))), 0, 0)
        ac.write(path_to_stg + file_name + '.ac')

    def debug_print_ways_at_node(self, node_osm_id):
        """print ways that connect to given node OSM_ID"""
        #print "ID", node_osm_id
        for the_way in self.ways_list:
            if node_osm_id in the_way.refs:
                print "+", the_way.osm_id

    def debug_print_refs_of_way(self, way_osm_id):
        """print refs of given way"""
        for the_way in self.ways_list:
            if the_way.osm_id == way_osm_id:
                print "found", the_way
                for the_ref in the_way.refs:
                    print "+", the_ref

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
        """create cluster.
           put objects in clusters based on their centroid
        """
        lmin, lmax = [vec2d(self.transform.toLocal(c)) for c in parameters.get_extent_global()]
        self.clusters = Clusters(lmin, lmax, parameters.TILE_SIZE, parameters.PREFIX)

        for the_object in self.bridges_list + self.roads_list:
            cluster_ref = self.clusters.append(vec2d(the_object.center.centroid.coords[0]), the_object)
            the_object.cluster_ref = cluster_ref


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
    """ % (file_name, shader_str, object_name)))


def debug_create_eps(roads, clusters, elev, plot_cluster_borders=0):
    """debug: plot roads map to .eps"""
    if not parameters.DEBUG_PLOT: return
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
    random.seed(42)
    parser = argparse.ArgumentParser(description="bridge.py reads OSM data and creates bridge models for use with FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE")
    parser.add_argument("-e", dest="e", action="store_true", help="skip elevation interpolation")
    parser.add_argument("-b", "--bridges-only", action="store_true", help="create only bridges and embankments")
    parser.add_argument("-l", "--loglevel", help="set loglevel. Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL")

    args = parser.parse_args()
    # -- command line args override paramters
    if args.filename is not None:
        parameters.read_from_file(args.filename)
    parameters.set_loglevel(args.loglevel)

    if args.e:
        parameters.NO_ELEV = True
    if args.bridges_only:
        parameters.CREATE_BRIDGES_ONLY = True

    #parameters.show()
    center_global = parameters.get_center_global()
    transform = coordinates.Transformation(center_global, hdg=0)
    tools.init(transform)
    elev = tools.get_interpolator(fake=parameters.NO_ELEV)
    roads = Roads(transform, elev)
    handler = osmparser.OSMContentHandler(valid_node_keys=[])
    logging.info("Reading the OSM file might take some time ...")

#    handler.register_way_callback(roads.from_way, **roads.req_and_valid_keys)
#    roads.register_callbacks_in(handler)
    handler.register_way_callback(roads.store_way, req_keys=roads.req_keys)
    handler.register_uncategorized_way_callback(roads.store_uncategorized)
    handler.parse(parameters.get_OSM_file_name())
    logging.info("ways: %i", len(roads))
        
    if parameters.PATH_TO_OUTPUT:
        path_to_output = parameters.PATH_TO_OUTPUT
    else:
        path_to_output = parameters.PATH_TO_SCENERY

    #roads.clip_at_cluster_border()
    #roads.debug_keep_only([24768143, 24960785, 24960872, 4531757, 24960872])
    #roads.debug_keep_only([24768144, 204383347, 204383366, 204383384, 204383376])
    #roads.debug_keep_only([24768144, 204383376])
#    roads.debug_keep_only([159102469, 204383356, 204383372, 149964565, 149964564])
    #roads.debug_keep_only([199894698, 239806431, 239806435, 199894356, 199894361, 199894352])
    #roads.debug_drop_unused_nodes()
    logging.debug("before linear " + str(roads))

#    roads.debug_print_ways_at_node(2098788640)

    # -- First, clean up topo. We work on ways_list:
    #    remove tunnels, short bridges, also remove inner junctions
    # 
    roads.remove_tunnels()
    roads.replace_short_bridges_with_ways()
    roads.cleanup_topo()
    # disabling this moves bridge/embankment nodes together. No h diff then.

    roads.debug_print_ways_at_node(2098788640)
    roads.debug_print_refs_of_way(239806431)
    roads.probe_elev_at_nodes()
    elev.save_cache()
#    roads.build_graph(roads.ways_list)
#    roads.split_long_roads_between_bridges()
    logging.debug("before linear " + str(roads))
    roads.debug_show_h_add("before linear ob")
    
    # -- no change in topo beyond create_linear_objects() !
    roads.create_linear_objects()
    roads.debug_show_h_add("after linear ob")

#    roads.debug_test()
#    roads.debug_test()
    roads.propagate_h_add()
    roads.debug_show_h_add("after propagate")
    logging.debug("after linear" + str(roads))

#    roads.debug_test()
#    roads.debug_plot(show=True, plot_junctions=True)#, label_nodes=[1132288594, 1132288612])
#    print "before", len(roads.attached_ways_dict)

#    roads.find_junctions(roads.roads_list)
    if 0:
        roads.compute_junction_nodes()
#    print "after", len(roads.attached_ways_dict)
    
#        sys.exit(0)

    #roads.cleanup_junctions()
#    roads.objects = [roads.objects[0]]
    if parameters.CREATE_BRIDGES_ONLY:
        roads.keep_only_bridges_and_embankments()
    roads.clusterize()
#    scale_test(transform, elev)

    replacement_prefix = re.sub('[\/]', '_', parameters.PREFIX)        
    stg_manager = stg_io2.STG_Manager(path_to_output, OUR_MAGIC, replacement_prefix, overwrite=True)
#    roads.debug_label_nodes(stg_manager)

    # -- write stg
    stg_paths = set()

    for cl in roads.clusters:
        if len(cl.objects) < parameters.CLUSTER_MIN_OBJECTS: continue # skip almost empty clusters

        replacement_prefix = re.sub('[\/]', '_', parameters.PREFIX)
        file_name = replacement_prefix + "roads%02i%02i" % (cl.I.x, cl.I.y)
        center_global = vec2d(tools.transform.toGlobal(cl.center))
        offset_local = cl.center
        cluster_elev = elev(center_global, True)

        # -- Now write cluster to disk.
        #    First create ac object. Write cluster's objects. Register stg object.
        #    Write ac to file.
        ac = ac3d.File(stats=tools.stats, show_labels=True)
        ac3d_obj = ac.new_object(file_name, 'tex/roads.png', default_swap_uv=True)
        for rd in cl.objects:
            rd.write_to(ac3d_obj, elev, cluster_elev, ac, offset=offset_local)  # FIXME: remove .ac, needed only for adding debug labels

        path_to_stg = stg_manager.add_object_static(file_name + '.xml', center_global, cluster_elev, 0)
        stg_paths.add(path_to_stg)
        ac.write(path_to_stg + file_name + '.ac')
        write_xml(path_to_stg, file_name, file_name)

        for the_way in cl.objects:
            the_way.junction0.reset()
            the_way.junction1.reset()

    # copy roads.eff into scenery folders
    for stg_path in stg_paths:
        roads_eff_file_name = tools.get_osm2city_directory() + os.sep + 'roads.eff'
        tools.install_files([roads_eff_file_name], stg_path)

    roads.debug_plot(show=True, plot_junctions=False, clusters=roads.clusters) #, label_nodes=self.nodes_dict.keys())#, label_nodes=[1132288594, 1132288612])
    
    debug_create_eps(roads, roads.clusters, elev, plot_cluster_borders=1)
    stg_manager.write()

    elev.save_cache()
    troubleshoot.troubleshoot(tools.stats)
    logging.info('Done.')
    roads.debug_show_h_add()
    logging.debug("final " + str(roads))

if __name__ == "__main__":
    main()
