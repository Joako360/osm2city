#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Sun Sep 29 10:42:12 2013

@author: tom
"""
import scipy.interpolate as interpolate
import matplotlib.pyplot as plt
import numpy as np

import shapely.geometry as shg

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
nodes = zip(x,y)
center = shg.LineString(nodes)
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
#out += 'texture "roof_tiled_red.png"\n'
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

h = 0.05
npi = 4
ipfeiler = range(len(x))[::15]
npfeiler = len(ipfeiler)
out += "numvert %i\n" %  (n_ul + n_ll + n_ur + n_lr + 2*npi*npfeiler)

#out += "numvert %i\n" %  (2*npi)

# -- body verts
if True:
    for v in offset_ul.coords:
        out += "%g %g %g\n" % (v[0], v[1], h)
    for v in offset_ll.coords:
        out += "%g %g %g\n" % (v[0], v[1], 0)
    for v in offset_ur.coords:
        out += "%g %g %g\n" % (v[0], v[1], h)
    for v in offset_lr.coords:
        out += "%g %g %g\n" % (v[0], v[1], 0)
# -- pillars
#for u in linspace(0, 1., 4):


def pillar(x, y, ofs):
    rx = 0.02
    ry = 0.01
    h0 = -0.3
    h1 = 0
    n = npi
    nodes_list = []
    vert = ""
    for a in np.linspace(0, 2*np.pi, n, endpoint = False):
        a += np.pi/npi
        vert += "%1.6f %1.6f %1.6f\n" % (x + rx*np.cos(a), y + ry*np.sin(a), h0)
    for a in np.linspace(0, 2*np.pi, n, endpoint = False):
        a += np.pi/npi
        vert += "%1.6f %1.6f %1.6f\n" % (x + rx*np.cos(a), y + ry*np.sin(a), h1)
    for i in range(npi-1):
        face = [ofs+i, ofs+i+1, ofs+i+1+npi, ofs+i+npi]
        nodes_list.append(face)
    i = npi - 1
    face = [ofs+i, ofs, ofs+npi, ofs+i+npi]
    nodes_list.append(face)
    return ofs + 2*npi, vert, nodes_list
    
#out  += "# pil\n"
i0 = n_ul + n_ll + n_ur + n_lr
p_nodes = []
for i in ipfeiler:
    px = x[i]
    py = y[i]
    i0, verts, nodes = pillar(px, py, i0)
    out += verts
    p_nodes.append(nodes)

out += "numsurf %i\n" % (4 + npi*len(p_nodes))

if True:
    out += "SURF 0x0\n"
    out += "mat 0\n"
    out += "refs %i\n" % (n_ul + n_ll)
    for n in nodes_ul + nodes_ll[::-1]:
        out += "%i 0 0\n" % n

    out += "SURF 0x0\n"
    out += "mat 0\n"
    out += "refs %i\n" % (n_ul + n_ur)
    for n in nodes_ur + nodes_lr[::-1]:
        out += "%i 0 0\n" % n

    out += "SURF 0x0\n"
    out += "mat 0\n"
    out += "refs %i\n" % (n_ul + n_ur)
    for n in nodes_ur[::-1] + nodes_ul[::-1]:
        out += "%i 0 0\n" % n

    out += "SURF 0x0\n"
    out += "mat 0\n"
    out += "refs %i\n" % (n_ll + n_lr)
    for n in nodes_ll + nodes_lr:
        out += "%i 0 0\n" % n

for pillar in p_nodes:
    for face in pillar:
        out += "SURF 0x0\n"
        out += "mat 0\n"
        out += "refs %i\n" % (len(face))
        for n in face:
            out += "%i 0 0\n" % n

out += "kids 0\n"
#print out

ac = open("bridge.ac", "w")
ac.write(out)
ac.close()
