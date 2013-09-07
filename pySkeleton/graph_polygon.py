#===============================================================================
#   File :      graph_polygon.py
#   Author :    Olivier Teboul olivier.teboul@ecp.fr
#   Date :      11 august 2008, 13:44
#   Class:      GPolygon
#===============================================================================

from point import Point
from point3D import Point3D
from graph import Graph,Node,Arc

import display
from segment import Segment
import sector
import events
import rainbow
import mesh

import copy
import math

class Edge(Arc,Segment):
    def __init__(self,p1,p2,w):
        Arc.__init__(self,p1,p2)
        Segment.__init__(p1,p2,w)

class GPolygon(Graph):
    """
    This class consider polygons as graphs, made of nodes and arcs
    An important difference is that a polygon is not any kind of graph, but a graph with
    at most two neighbors per node. We call them the 'next' arc and the 'previous' arc (we they exist)
    """
    
    #===========================================================================
    # Construction and copy
    #===========================================================================
    def __init__(self,vertices=[], edges=[], weights=[]):
        """
        @arg vertices
            list of 2-tuples representing the coordinates (x,y) of each vertex
        @arg edges
            a list of 2-tuples representing the indices of the ends of each edge
        @arg weights
            a list of weights for each arcs
        """
        #make a list of nodes from the vertices list
        ns = map(Node,map(Point,vertices))
        
        #make a list of Edge from edges and weights
        
        
        #instanciate the graph
        Graph.__init__(self,ns,es)
        
    def clone(self):pass
        
    #===========================================================================
    # Save and load
    #===========================================================================        
    def save(self,filename):pass
    
    def load(self,filename):pass
    
    #===========================================================================
    # Visualization
    #===========================================================================            
    def __repr__(self): pass
    
    def display(self,viewer): pass
    
    #===========================================================================
    # Get information about the polygon
    #===========================================================================
    def is_reflex_adjacent(self,sec1,sec2): pass
    
    #===========================================================================
    # Sectors
    #===========================================================================
    def get_sector(self,edge_index): pass
    
    def get_sectors(self): pass
    
    #===========================================================================
    # Change the geometric properties of the polygon
    #===========================================================================
    def move(self,index,location):pass
    
    def shrink(self,d):pass  
    
    #===========================================================================
    # Change the topology of the polygon
    #===========================================================================
    def collapse_edge(self,edge_index):
        """ Collapse the edge to its first point """
        pass
    
    def split_edge(self,edge_index,split_p):
        """ Split the edge 'edge_index' into two edges. split_p is the new end"""
        pass
    
    def fusion_vertices(self,ps,new_point):
        """ Fusion the points ps to the new_point """
        pass
    
    def clean(self):pass
    def clean_edges(self):pass
    def clean_components(self):pass
        
    
    



