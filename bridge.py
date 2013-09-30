#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# FIXME: check sign of angle

"""
Created on Sun Sep 29 10:42:12 2013

@author: tom
"""
import scipy.interpolate as interpolate
import matplotlib.pyplot as plt
import numpy as np
from vec2d import vec2d
import shapely.geometry as shg
import pdb

def param_interpolate():
    t = np.arange(0,1.1,.1)
    x = np.sin(2*np.pi*t)
    y = np.cos(np.pi*t)*2.
    tck,u = interpolate.splprep([x,y],s=0)
    unew = np.arange(0,1.01,0.05)
    out = interpolate.splev(unew,tck)
    xder, yder = interpolate.splev(unew,tck,der=1)
    xd = np.zeros_like(unew)
    yd = np.zeros_like(unew)
    s=0.1
    for i in range(len(xd)):
        xd[i] = out[0][i] - s*yder[i]
        yd[i] = out[1][i] + s*xder[i]

    plt.figure()
    #plt.plot(x,y,'x',out[0],out[1],np.sin(2*np.pi*unew),np.cos(2*np.pi*unew),x,y,'b')
    plt.plot(out[0],out[1], '-x', xd, yd, '-o')
    plt.legend(['Linear', 'a'])
    #plt.axis([-1.05,1.05,-1.05,1.05])
    plt.title('Spline of parametrically-defined curve')
    plt.show()

def plot_line(center, style='-x'):
    plt.plot(center.coords.xy[0], center.coords.xy[1], style)
    #plt.legend(['Linear'])
    #plt.title('Spline of parametrically-defined curve')


t = np.arange(0,1.1,.01)
x = np.sin(2*np.pi*t)
y = np.cos(np.pi*t)
z = np.sin(2*np.pi*t)
nodes = zip(x,y)
center = shg.LineString(nodes)
n = len(center.coords)
angle = np.zeros(n)
angle[0] = (vec2d(center.coords[1]) - vec2d(center.coords[0])).atan2()
for i in range(1, n-1):
    angle[i] = 0.5 * ( (vec2d(center.coords[i-1]) - vec2d(center.coords[i])).atan2()
                      +(vec2d(center.coords[i])   - vec2d(center.coords[i+1])).atan2())
angle[n-1] = (vec2d(center.coords[n-2]) - vec2d(center.coords[n-1])).atan2()

center = center.simplify(0.03)

offset_ul = center.parallel_offset(0.1, 'left', resolution=16, join_style=2, mitre_limit=5.0)
offset_ur = center.parallel_offset(0.1, 'right', resolution=16, join_style=2, mitre_limit=5.0)
offset_ll = center.parallel_offset(0.06, 'left', resolution=16, join_style=2, mitre_limit=5.0)
offset_lr = center.parallel_offset(0.06, 'right', resolution=16, join_style=2, mitre_limit=5.0)
# -- plot
plt.figure()
plot_line(center, 'k-o')
plot_line(offset_ul, 'b-x')
plot_line(offset_ur, 'b-x')
plt.axis([-1.5,1.5,-1.5,1.5])
plt.axes().set_aspect('equal')
#plt.show()

out = ""
# vertices
out += "AC3Db\n"
out += 'MATERIAL "" rgb 0.5   0.5   1 amb 1 1 1  emis 0.0 0.0 0.0  spec 0.5 0.5 0.5  shi 64  trans 0\n'
out += "OBJECT world\n"
out += "kids 1\n"
out += "OBJECT poly\n"
out += 'name "b6"\n'
out += 'texture "bridge.png"\n'
n_ul = len(offset_ul.coords)
n_ll = len(offset_ll.coords)
n_ur = len(offset_ul.coords)
n_lr = len(offset_ll.coords)

def succ_range(i, delta):
    return i + delta, range(i, i + delta)

i, nodes_ul = succ_range(0, n_ul)
i, nodes_ll = succ_range(i, n_ll)
i, nodes_ur = succ_range(i, n_ur)
i, nodes_lr = succ_range(i, n_lr)

bridge_body_h = 0.05
npi = 4
ipfeiler = range(len(x))[::1]
npfeiler = len(ipfeiler)
out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr + 2*npi*npfeiler)

#out += "numvert %i\n" %  (2*npi)

# -- body verts
if True:
    for i, v in enumerate(offset_ul.coords):
        out += "%g %g %g\n" % (v[0], v[1], z[i])
    for i, v in enumerate(offset_ll.coords):
        out += "%g %g %g\n" % (v[0], v[1], z[i] - bridge_body_h)
    for i, v in enumerate(offset_ur.coords[::-1]):
        out += "%g %g %g\n" % (v[0], v[1], z[i])
    for i, v in enumerate(offset_lr.coords[::-1]):
        out += "%g %g %g\n" % (v[0], v[1], z[i] - bridge_body_h)
# -- pillars
#for u in linspace(0, 1., 4):


def pillar(x, y, h0, h1, ofs, angle):
    rx = 0.05
    ry = 0.01
    n = npi
    nodes_list = []
    vert = ""
    R = np.array([[np.cos(-angle), -np.sin(-angle)],
                  [np.sin(-angle),  np.cos(-angle)]])
    for a in np.linspace(0, 2*np.pi, n, endpoint = False):
        a += np.pi/npi
        node = np.array([rx*np.cos(a), ry*np.sin(a)])
        node = np.dot(R, node)
        vert += "%1.6f %1.6f %1.6f\n" % (x+node[1], y+node[0], h1)
    for a in np.linspace(0, 2*np.pi, n, endpoint = False):
        a += np.pi/npi
        node = np.array([rx*np.cos(a), ry*np.sin(a)])
        node = np.dot(R, node)
        vert += "%1.6f %1.6f %1.6f\n" % (x+node[1], y+node[0], h0)

    for i in range(npi-1):
        face = [ofs+i, ofs+i+1, ofs+i+1+npi, ofs+i+npi][::-1]
        nodes_list.append(face)
    i = npi - 1
    face = [ofs+i, ofs, ofs+npi, ofs+i+npi][::-1]
    nodes_list.append(face)

    return ofs + 2*npi, vert, nodes_list
    
#out  += "# pil\n"
# -- pillar verts
i0 = n_ul + n_ll + n_ur + n_lr
p_nodes = []
for j, i in enumerate(ipfeiler):
    i0, verts, nodes = pillar(x[i], y[i], z[j], 0, i0, angle[i])
    out += verts
    p_nodes.append(nodes)

ns = 4*(len(nodes_ul)-1) 
ns += npi*len(p_nodes)
out += "numsurf %i\n" % (ns)

# -- body nodes
def surf_between_lines(l1, l2, t0, t1):
    out = ""
    for i in range(len(l1)-1):
        out += "SURF 0x0\n"
        out += "mat 0\n"
        out += "refs 4\n"
        out += "%i 0 %g\n" % (l1[i],   t0)
        out += "%i 1 %g\n" % (l1[i+1], t0)
        out += "%i 1 %g\n" % (l2[i+1], t1)
        out += "%i 0 %g\n" % (l2[i],   t1)
    return out

out += surf_between_lines(nodes_ul, nodes_ll, 1, 0.75)
out += surf_between_lines(nodes_ur[::-1], nodes_lr[::-1], 1, 0.75)
out += surf_between_lines(nodes_ul[::-1], nodes_ur[::-1], 0.75, 0.5)
out += surf_between_lines(nodes_ll, nodes_lr, 0.5, 0.25)

for pillar in p_nodes:
    for face in pillar:
        out += "SURF 0x0\n"
        out += "mat 0\n"
        out += "refs %i\n" % (len(face))
#        for n in face:
#            out += "%i 0 0\n" % n

        out += "%i 0 0.5\n" % face[0]
        out += "%i 1 0.5\n" % face[1]
        out += "%i 1 0\n" % face[2]
        out += "%i 0 0\n" % face[3]
    

out += "kids 0\n"
#print out

ac = open("bridge.ac", "w")
ac.write(out)
ac.close()
