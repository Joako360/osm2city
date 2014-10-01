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
