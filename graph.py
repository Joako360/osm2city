#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
graph support stuff
"""
import networkx as nx
from pdb import pm

def for_edges_in_bfs_call(func, args, G, node0_set, visited_set):
    """Start at nodes in node0_set. Breadth-first search, excluding nodes 
       in visited_set. 
       For each edge, call func(node0, node1, args). 
       Stop search on one branch if func returns False.
    """
    while True:
        # get neighbors not visited        
        next_nodes = {}
        for node0 in node0_set:
            neighbours = [n for n in nx.all_neighbors(G, node0) if n not in visited_set]
            next_nodes[node0] = neighbours
        
        node0_set = set()
        for n0, n1s in next_nodes.iteritems():
            for n1 in n1s:
                if func(n0, n1, args):
                    node0_set.add(n1)
                visited_set.add(n1)
        if len(node0_set) == 0:
            break


class Stub(object):
    def __init__(self, attached_way, is_first, joint_nodes=[]):
        self.attached_way = attached_way
        self.is_first = is_first
        self.joint_nodes = joint_nodes

class Junction(object):
    """store attached ways, joint_node indices
       current usage of attached_ways_dict:
          for the_ref, ways_list in attached_ways_dict.items()
          -> for the_ref, the_junction in attached_ways_dict.items()
          for ref in self.attached_ways_dict
          -> unchanged
          for way, boolean in self.attached_ways_dict[the_ref]:
          -> junction = self.attached_ways_dict[the_ref].attached_ways
          OR __items__()
          for ref, ways_tuple_list in self.attached_ways_dict.iteritems()
          -> for ref, junction in self.attached_ways_dict.iteritems():
               junction.attached_ways
    - 
    """
    def __init__(self, way, is_first, joint_nodes=[]):
        self._attached_ways = [way]
        self._is_first = [is_first]
        self.joint_nodes = joint_nodes # list of tuples
        self._left_node = None
        self._right_node = None
        
    def __len__(self):
        return len(self._attached_ways)

    def append_way(self, way, is_first):
        self._attached_ways.append(way)
        self._is_first.append(is_first)
    
    def _use_left_node(self, way, is_left):
        i = self._attached_ways.index(way)
        assert(i==0 or i==1)
        return (i + self._is_first[i] + is_left) % 2 == 0
    
    def get_other_node(self, way, is_left):
        if self._use_left_node(way, is_left):
            if self._left_node == None:
                raise KeyError
            return self._left_node
        else:
            if self._right_node == None:
                raise KeyError
            return self._right_node

    def set_other_node(self, way, is_left, node):
        if self._use_left_node(way, is_left):
            if self._left_node != None:
                raise ValueError("other node already set")
            self._left_node = node
        else:
            if self._right_node != None:
                raise ValueError("other node already set")
            self._right_node = node

class Graph(nx.Graph):
    """Inherit from nx.Graph, make accessing graph node attribute (Junction) easier"""
    #def __init__(self, graph):
    def junction(self, the_ref):
        """return object attached to node"""
        return self.node[the_ref]['obj']

    def add_node(self, the_ref, obj):
        super(Graph, self).add_node(the_ref, obj=obj)

    def add_edge(self, way):
        ref0 = way.refs[0]
        ref1 = way.refs[-1]
        try:
            junction0 = self.junction(ref0)
            junction0.append_way(way, is_first = True)
        except KeyError:
            #assert(the_ref1 == the_way.refs[0] and the_ref2 == the_way.refs[-1] )
            junction0 = Junction(way, is_first=True) # IS_FIRST
            super(Graph, self).add_node(ref0, obj=junction0)

        try:
            junction1 = self.junction(ref1)
            junction1.append_way(way, is_first = False)
        except KeyError:
            #assert(the_ref1 == the_way.refs[0] and the_ref2 == the_way.refs[-1] )
            junction1 = Junction(way, is_first=False)
            super(Graph, self).add_node(ref1, obj=junction1)
            
        super(Graph, self).add_edge(ref0, ref1, obj=way)

        way.junction0 = junction0
        way.junction1 = junction1

#        for the_way in source_iterable:
#            self.G.add_edge(the_way.refs[0], the_way.refs[-1], obj=the_way)

if __name__ == "__main__":
    
    G=Graph()
    
    junction1 = 'j1'
    junction2 = 'j2'
    G.add_node("a", junction1)
    G.add_node("a", junction1)
    
    bla
    G.add_node(2, junction2)
    G.add_node(3, "hj")
    G.add_edge(3, 2)
    G.add_edge("a", 2)
    print "aa", G.node["a"]['obj']
    print "cur"
    print G["a"]
    print G[2]
    print "nodes:"
    print G.junction(2)
    for the_node in G.nodes(data=True):
        print the_node[0], " --",
        print the_node[1]['obj']