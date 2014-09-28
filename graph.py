#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
graph support stuff
"""
import networkx as nx

def for_edges_in_bfs(func, args, G, node0_set, visited_set):
    """Start at node0. Breadth-first search, excluding nodes in visited. For each edge,
       call func(node0, node1). Stop search on this branch if func returns False.   
    """
    i = 0
    while True:
        print "round", i, "node0s", node0_set
        # get neighbors not visited        
        out = {}
        for node0 in node0_set:
            neighbours = [n for n in nx.all_neighbors(G, node0) if n not in visited_set]
            out[node0] = neighbours
        
        node0_set = set()
        for n0, n1s in out.iteritems():
            print "node0:", n0
            for n1 in n1s:
                cont = func(n0, n1, args)            
                print "   %i - %i" % (n0, n1), cont
                visited_set.add(n1)
                if cont: 
                    node0_set.add(n1)
        print "after round, visited", visited_set, "next round visit", len(node0_set)
        print
        if len(node0_set) == 0:
            break
