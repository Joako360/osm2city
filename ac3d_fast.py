'''
Performing reader for vertices of a ac3d file
Created on 06.04.2015

@author: keith.paterson
'''
from re import split
import numpy as np


'''
Fast dedicated vertice reader for ac3d files
'''
class File(object):
    
    def __init__(self, file_name, stats):
        self.vertices = []
        if file_name != None:
            self.read(file_name)

    def read(self, file_name):
        with open(file_name) as f:
            lines = f.readlines()
        num_vertices = 0
        for line in lines:
            if line.startswith("numvert"):
                num_vertices = int(line[8:])
                continue
            if num_vertices>0:
                num_vertices-=1
                vertice = map(float,split(" ",line))
                self.vertices.append(vertice)
                        
    def nodes_as_array(self):
        return np.array(self.vertices)
