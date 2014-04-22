#!/usr/bin/env python
import string

class Node(object):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
    def __str__(self):
        return "%1.2f %1.2f %1.2f\n" % (self.x, self.y, self.z)

class Face(object):
    def __init__(self, nodes_uv_list, typ, mat):
        assert len(nodes_uv_list) >= 3
        for n in nodes_uv_list:
            assert len(n) == 3
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
    def __init__(self, name, texture=None, default_type=0x0, default_mat=0):
        self._nodes = []
        self._faces = []
        self.name = str(name)
        assert name != ""
        self.texture = texture
        self.default_type = default_type
        self.default_mat = default_mat

    def close(self):
        pass

    def node(self, x, y, z):
        """Add new node. Return its index."""
        self._nodes.append(Node(x, y, z))
        return len(self._nodes) - 1

    def next_node_index(self):
        return len(self._nodes)

    def face(self, nodes_uv_list, typ=None, mat=None):
        """Add new face. Return its index."""
        if not typ:
            typ = self.default_type
        if not mat:
            mat = self.default_mat
        self._faces.append(Face(nodes_uv_list, typ, mat))
        return len(self._faces) - 1

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

class Writer(object):
    """
    Hold a number of objects. Each object holds nodes and faces.
    Count nodes/surfaces etc internally, thereby eliminating a common source of bugs.
    Provides a unified interface.
    """
    def __init__(self, stats):
        self.objects = []
        self._current_object = None

    def new_object(self, name, texture, **kwargs):
        o = Object(name, texture, **kwargs)
        self.objects.append(o)
        self._current_object = o

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
        s += 'OBJECT world\nkids %i\n' % (len(self.objects))
        s += string.join([str(o) for o in self.objects])
        return s

if __name__ == "__main__":
    a = Writer(None)
    a.new_object('bla', '')
    a.node(0,0,0)
    a.node(0,1,0)
    a.node(1,1,0)
    a.node(1,0,0)
    a.face([(0,0,0), (1,0,0), (2,0,0), (3,0,0)])
    print a

