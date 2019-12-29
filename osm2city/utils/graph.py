# -*- coding: utf-8 -*-

"""
graph support stuff
"""
import networkx as nx


def for_edges_in_bfs_call(func, args, graph, node0_set, visited_set):
    """Start at nodes in node0_set. Breadth-first search, excluding nodes 
       in visited_set. 
       For each edge, call func(node0, node1, args). 
       Stop search on one branch if func returns False.
    """
    while True:
        # get neighbors not visited        
        next_nodes = {}
        for node0 in node0_set:
            neighbours = [n for n in nx.all_neighbors(graph, node0) if n not in visited_set]
            next_nodes[node0] = neighbours
        
        node0_set = set()
        for n0, n1s in next_nodes.items():
            for n1 in n1s:
                if func(n0, n1, args):
                    node0_set.add(n1)
                visited_set.add(n1)
        if not node0_set:
            break


class Stub(object):
    def __init__(self, attached_way, is_first, joint_nodes=None):
        if joint_nodes is None:
            joint_nodes = list()
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
          for linear_obj, boolean in self.attached_ways_dict[the_ref]:
          -> junction = self.attached_ways_dict[the_ref].attached_ways
          OR __items__()
          for ref, ways_tuple_list in self.attached_ways_dict.iteritems()
          -> for ref, junction in self.attached_ways_dict.iteritems():
               junction.attached_ways
    - 
    """
    def __init__(self, way, is_first, joint_nodes=None):
        self._attached_ways = [way]
        self._is_first = [is_first]
        if joint_nodes is None:
            joint_nodes = list()
        self.joint_nodes = joint_nodes  # list of tuples -- unused?
        self._left_node = None
        self._right_node = None
        self._cluster_ref = None
        self.reset()
        
    def reset(self):
        self._left_node = None
        self._right_node = None
        self._cluster_ref = None
        
    def __len__(self):
        return len(self._attached_ways)

    def append_way(self, way, is_first):
        self._attached_ways.append(way)
        self._is_first.append(is_first)
    
    def _use_left_node(self, way, is_left):
        i = self._attached_ways.index(way)
        assert(i == 0 or i == 1)
        return (i + self._is_first[i] + is_left) % 2 == 0
    
    def get_other_node(self, way, is_left, cluster_ref):
        if self._cluster_ref != cluster_ref:
            raise KeyError
        if self._use_left_node(way, is_left):
            if self._left_node is None:
                raise KeyError
            return self._left_node
        else:
            if self._right_node is None:
                raise KeyError
            return self._right_node

    def set_other_node(self, way, is_left, node, cluster_ref):
        """We also store cluster reference to avoid using nodes from other clusters"""
        self._cluster_ref = cluster_ref
        if self._use_left_node(way, is_left):
            if self._left_node is not None:
                raise ValueError("other node already set")
            self._left_node = node
        else:
            if self._right_node is not None:
                raise ValueError("other node already set")
            self._right_node = node


class Graph(nx.Graph):
    """Inherit from nx.Graph, make accessing graph node attribute (Junction) easier"""
    def junction(self, the_ref):
        """return object attached to node"""
        return self.nodes[the_ref]['obj']

    def add_linear_object_edge(self, linear_obj):
        ref0 = linear_obj.way.refs[0]
        ref1 = linear_obj.way.refs[-1]
        try:
            junction0 = self.junction(ref0)
            junction0.append_way(linear_obj, is_first=True)
        except KeyError:
            junction0 = Junction(linear_obj, is_first=True)  # IS_FIRST
            super().add_node(ref0, obj=junction0)

        try:
            junction1 = self.junction(ref1)
            junction1.append_way(linear_obj, is_first=False)
        except KeyError:
            junction1 = Junction(linear_obj, is_first=False)
            super().add_node(ref1, obj=junction1)
            
        super().add_edge(ref0, ref1, obj=linear_obj)

        linear_obj.junction0 = junction0
        linear_obj.junction1 = junction1
