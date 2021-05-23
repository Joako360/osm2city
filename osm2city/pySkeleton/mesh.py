# ===============================================================================
#   File :      mesh.py
#   Author :    Olivier Teboul, olivier.teboul@ecp.fr
#   Date :      31 july 2008, 14:03
#   Class :     Mesh
# ===============================================================================

import numpy as np
from osm2city import roofs
from osm2city.utils.coordinates import Vec2d
import osm2city.utils.ac3d


class Mesh:
    """
    A mesh is represented by an indexed face structure (IFS):
        * a list of vertices
            -> a vertex is a 3D point
        * a list of faces
            -> a face is a list of indices from the vertices list

    This class provides methods to :
        * create a 3D Mesh
        * save it as a sketchup file
        * save and load (with a internal format)
    """

    def __init__(self, vertices=None, faces=None):
        self.vertices = vertices
        if self.vertices is None:
            self.vertices = list()
        self.faces = faces
        if self.faces is None:
            self.faces = list()
        self.nv = len(self.vertices)
        self.nf = len(self.faces)

    def add_vertex(self, p):
        """
        add a vertex into the list of vertices if the vertex is not already in the list
        @return the index of the vertex in the vertices list
        """
        try:
            return self.vertices.index(p)
        except ValueError:
            self.vertices.append(p)
            self.nv += 1
            return self.nv-1

    def add_face(self, face):
        """ add a face an return the index of the face in the list """
        self.faces.append(face)
        self.nf += 1
        return self.nf-1

    def to_out(self, out: osm2city.utils.ac3d.File, b, offset_xy=Vec2d(0, 0), offset_z=0.) -> bool:
        """create 3d object"""
        X = []
        o = out.next_node_index()
        for p in self.vertices:
            x = -(p.x - offset_xy.x)
            y = -(p.y - offset_xy.y)
            X.append([x, y])
            out.node(y, p.z + offset_z, x)

        for face in self.faces:
            face = np.roll(face[::-1], 1)  # -- make outer edge the first
            uv = roofs.face_uv(face, np.array(X), b.roof_texture)
            i = 0
            l = []
            for index in face:
                l.append((o + index, uv[i, 0], uv[i, 1]))
                i += 1
            out.face(l)

        return True
