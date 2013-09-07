#!/usr/bin/env python
#===============================================================================
#   File :      straight_skeleton.py
#   Author :    Olivier Teboul olivier.teboul@ecp.fr
#   Date :      11 august 2008, 12151
#   Class:      StraightSkeleton
#===============================================================================

import polygon
import events
from graph import Graph

class StraightSkeleton(Graph):
    """
    A straight skeleton is a graph that represent the straight skeleton of
    a polygon. The polygon can be made of several connected components.
    
    The straight skeleton algorithm, first developped by O. Aichholzer,
    F. Aurenhammer, D. Alberts and B. Gartner in 1995 processes by shrinking
    the edges of the polygon perpendiculary to their direction. The algorithm is driven
    by a sequence of degenerated events that can happen while shrinking the polygon such as :
        - edge event : an edge collapse to a single point
        - split event : a (reflex) vertex split an edge into two
        - vertex event : some split event occur at the same time at the same place
    Each event will change the topology of the polygon
    
    The current implementation of the straight skeleton does not follow the optimization tricks
    developped in the literature, such as the priority queue. Nonetheless, such improvements will be
    taken into account in the next versions.
    
    Know bugs :
    The current implementation does not support simultaneous split events.
    """
    
    def __init__(self,poly): pass
    
    def first_split_event(self): pass
    
    def first_event(self): pass
    
    def update_vertex_event(self): pass
    
    def update_split_event(self): pass
    
    def shrink(self) : pass
    
    def straight_skeleton(self): pass
    
    def straight_skeleton_faces(self): pass
        
    def straight_skeleton_get_face(self,skeleton,i): pass
    