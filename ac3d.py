#!/usr/bin/env python
import string
import matplotlib.pyplot as plt
import numpy as np

class Node(object):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
    def __str__(self):
        return "%1.2f %1.2f %1.2f\n" % (self.x, self.y, self.z)

class Face(object):
    def __init__(self, nodes_uv_list, typ, mat, rotate):
        assert len(nodes_uv_list) >= 3
        for n in nodes_uv_list:
            assert len(n) == 3
        if rotate:
            # -- roll (u, v) along node axis
            a = np.array(nodes_uv_list)
            a[:,1:] = np.roll(a[:,1:],1, axis=0)
            nodes_uv_list = list(a)
        self.nodes_uv_list = nodes_uv_list
        self.typ = typ
        self.mat = mat

    def __str__(self):
        s = "SURF %s\n" % self.typ
        s += "mat %i\n" % self.mat
        s += "refs %i\n" % len(self.nodes_uv_list)
        s += string.join(["%i %g %g\n" % (n[0], n[1], n[2]) for n in self.nodes_uv_list], '')
        return s


class Object(object):
    def __init__(self, name, stats, texture=None, default_type=0x0, default_mat=0):
        self._nodes = []
        self._faces = []
        self.name = str(name)
        assert name != ""
        self.stats = stats
        self.texture = texture
        self.default_type = default_type
        self.default_mat = default_mat

    def close(self):
        pass

    def node(self, x, y, z):
        """Add new node. Return its index."""
        self._nodes.append(Node(x, y, z))
        self.stats.vertices += 1
        return len(self._nodes) - 1

    def next_node_index(self):
        return len(self._nodes)

    def face(self, nodes_uv_list, typ=None, mat=None, rotate=None):
        """Add new face. Return its index."""
        if not typ:
            typ = self.default_type
        if not mat:
            mat = self.default_mat
        self._faces.append(Face(nodes_uv_list, typ, mat, rotate))
        self.stats.surfaces += 1
        return len(self._faces) - 1

    def is_empty(self):
        return not self._nodes

    def __str__(self):
        s = 'OBJECT poly\n'
        s += 'name "%s"\n' % self.name
        if self.texture:
            s += 'texture "%s"\n' %self.texture
        s += 'numvert %i\n' % len(self._nodes)
        s += string.join([str(n) for n in self._nodes], '')
        s += 'numsurf %i\n' % len(self._faces)
        s += string.join([str(f) for f in self._faces], '')
        s += 'kids 0\n'
        return s

    def plot(self):
        """note: here, Z is height."""
        for f in self._faces:
            X = [self._nodes[n[0]].x for n in f.nodes_uv_list]
            Y = [self._nodes[n[0]].z for n in f.nodes_uv_list]
            Z = [self._nodes[n[0]].y for n in f.nodes_uv_list]
            X.append(self._nodes[f.nodes_uv_list[0][0]].x)
            Y.append(self._nodes[f.nodes_uv_list[0][0]].z)
            #Z.append(self._nodes[f.nodes_uv_list[0][0]].y)
            #if max(Z) > 1.: break
            #print "MAX", max(Z)
            plt.plot(X, Y)
            for i in range(len(X)-1):
                x = 0.5*(X[i] + X[i+1])
                y = 0.5*(Y[i] + Y[i+1])
                plt.text(x+Z[i], y+Z[i], "%i" % i)


class Writer(object):
    """
    Hold a number of objects. Each object holds nodes and faces.
    Count nodes/surfaces etc internally, thereby eliminating a common source of bugs.
    Provides a unified interface.
    """
    def __init__(self, stats):
        self.objects = []
        self.stats = stats
        self._current_object = None

    def new_object(self, name, texture, **kwargs):
        o = Object(name, self.stats, texture, **kwargs)
        self.objects.append(o)
        self._current_object = o
        return o

    def close_object(self):
        self._current_object.close()
        self._current_object = None

    def node(self, *args):
        return self._current_object.node(*args)

    def next_node_index(self):
        return self._current_object.next_node_index()

    def face(self, *args):
        return self._current_object.face(*args)

    def __str__(self):
        s = 'AC3Db\n'
        s += 'MATERIAL "" rgb 1 1 1 amb 1 1 1 emis 0 0 0 spec 0.5 0.5 0.5 shi 64 trans 0\n'
        s += 'MATERIAL "" rgb 0 1 0 amb 1 1 1 emis 0 0 0 spec 0.5 0.5 0.5 shi 64 trans 0\n'
        non_empty = [o for o in self.objects if not o.is_empty()]
        s += 'OBJECT world\nkids %i\n' % len(non_empty)
        s += string.join([str(o) for o in non_empty])
        return s

    def plot(self):
        non_empty = [o for o in self.objects if not o.is_empty()]
        for o in non_empty:
            o.plot()

if __name__ == "__main__":
    a = Writer(None)
    a.new_object('bla', '')
    a.node(0,0,0)
    a.node(0,1,0)
    a.node(1,1,0)
    a.node(1,0,0)
    a.face([(0,0,0), (1,0,0), (2,0,0), (3,0,0)])
    print a

