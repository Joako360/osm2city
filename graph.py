#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
graph support stuff
"""
import networkx as nx

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

class Graph(nx.Graph):
    """Inherit from nx.Graph, make accessing graph node attributes easier"""
    #def __init__(self, graph):
    def junction(self, the_ref):
        """return object attached to node"""
        self.node[the_ref]['obj']
    def add_node(self, the_ref, obj):
        super(Graph, self).add_node(the_ref, obj=obj)
    def add_edge(self, the_ref1, the_ref2, obj):
        super(Graph, self).add_edge(the_ref1, the_ref2, obj=obj)
#        for the_way in source_iterable:
#            self.G.add_edge(the_way.refs[0], the_way.refs[-1], obj=the_way)

if __name__ == "__main__":
    
    G=Graph()
    
    junction1 = 'j1'
    junction2 = 'j2'
    G.add_node("a", junction1)
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