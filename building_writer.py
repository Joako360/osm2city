# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""
import random
import numpy as np
import copy
#nobjects = 0
nb = 0
out = ""

class random_number(object):
    def __init__(self, randtype, min, max):
        self.min = min
        self.max = max
        if randtype == float:
            self.callback = random.uniform
        elif randtype == int:
            self.callback = random.randint
        else:
            raise TypeError("randtype must be 'float' or 'int'")
    def __call__(self):
        return self.callback(self.min, self.max)

random_LOD = random_number(int, 0, 2)
default_height=12
random_level_height = random_number(float, 3.1, 3.6)
random_levels = random_number(int, 2, 5)

def check_height(building_height, t):
    if t.v_repeat:
        tex_y1 = 1.
        tex_y0 = 1 - building_height / t.v_size_meters
        return True, tex_y0, tex_y1
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error
        # - error acceptable?
        if building_height >= t.v_splits_meters[0] and building_height <= t.v_size_meters:
            for i in range(len(t.v_splits_meters)):
                if t.v_splits_meters[i] >= building_height:
                    tex_y0 = 1-t.v_splits[i]
                    print "# height %g storey %i" % (building_height, i)
                    break
            tex_y1 = 1.
            #tex_filename = t.filename + '.png'
            return True, tex_y0, tex_y1
        else:
            return False, 0, 0



def reset_nb():
    global nb
    nb = 0

def write_building(b, out, elev, transform, textures, LOD_lists):
    global first
    mat = random.randint(0,3)
    mat = 0

    nnodes_ground = len(b.refs)
#    print nnodes_ground #, b.refs[0].lat, b.refs[0].lon

#for building in allbuildings:
    global nb
#    global nobjects

    nb += 1
    print nb

    #global elev
#  if building[0] == 332:
#    if first: first = False
#    else:     out.write("kids 1\n")


    out.write("OBJECT poly\n")
    name = "b%i" % nb
    out.write("name \"%s\"\n" % name)

    lod = random_LOD()
    mat = lod
    LOD_lists[lod].append(name)

    if nnodes_ground == 4:
        include_roof = False
    else: include_roof = True

#    if separate_roof:
#    out.write('texture "facade_modern1.png"\n')
#    out.write('texture "facade_modern36x36_12.png"\n')

    X = np.zeros((nnodes_ground+1,2))
    lenX = np.zeros((nnodes_ground))
    i = 0
    for r in b.refs:
        X[i,0], X[i,1] = transform.toLocal((r.lat, r.lon))
        i += 1
    X[-1] = X[0] # -- we duplicate last node!

    # -- check for inverted faces
    crossX = 0.
    for i in range(nnodes_ground):
        crossX += X[i,0]*X[i+1,1] - X[i+1,0]*X[i,1]
        lenX[i] = ((X[i+1,0]-X[i,0])**2 + (X[i+1,1]-X[i,1])**2)**0.5

    if crossX < 0:
        X = X[::-1]
        lenX = lenX[::-1]

    # -- renumber nodes such that longest edge is first edge
    if nnodes_ground == 4:

        if lenX[0] < lenX[1]:
            #print lenX
            #print X
            X = np.roll(X, 1, axis=0)
            lenX = np.roll(lenX, 1)
            #print lenX
            X[0] = X[-1]
            #print X
            #sys.exit(0)

    ground_elev = 3.*elev(X[0,0], X[0,1]) # -- interpolate ground elevation at building location
    print "ground_elev", ground_elev

    try:
        height = float(b.height)
    except:
        height = 0.
    if height < 1. and float(b.levels) > 0:
        height = float(b.levels) * random_level_height()
    if height < 1.:
        height = random_levels() * random_level_height()
    # -- try height or levels
#    if height > 1.: z = height
#    elif float(b.levels) > 0:
#        z = float(b.levels) * level_height
        #print "LEVEL", z

#    for r in b.refs:
#        x, y = transform.toLocal((r.lat, r.lon))
#        out.write("%g %g %g\n" % (y, z, x))

    nsurf = nnodes_ground
    if include_roof: nsurf += 1

    #repeat_vert = int(height/3)

    # -- texturing facade
    # - check all walls -- min length?
    #global textures
    # loop all textures
    # award points for good matches
    # pick best match?
    building_height = height
    # -- check v: height

    shuffled_t = copy.copy(textures)
    random.shuffle(shuffled_t)
    have_texture = False
    for t in shuffled_t:
        ok, tex_y0, tex_y1 = check_height(building_height, t)
        if ok:
            have_texture = True
            break

    if have_texture:
        out.write('texture "%s"\n' % (t.filename+'.png'))
    else:
        print "WARNING: no texture height", building_height

    # -- check h: width

    # building shorter than facade texture
    # layers > facade_min_layers
    # layers < facade_max_layers
#    building_height = height
#    texture_height = 12*3.
#    if building_height < texture_height:
#    if 1:
#        tex_y0 = 1 - building_height / texture_height
#        tex_y1 = 1
#    else:
#        tex_y0 = 0
#        tex_y1 = building_height / texture_height # FIXME

    #out.write("loc 0 0 0\n")
    out.write("numvert %i\n" % (2*nnodes_ground))

    for x in X[:-1]:
        z = ground_elev - 1
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], z, x[0]))

    for x in X[:-1]:
        #out.write("%g %g %g\n" % (y, z, x))
        out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))

    out.write("numsurf %i\n" % nsurf)
    # -- walls

    for i in range(nnodes_ground - 1):
        tex_x1 = lenX[i] / t.h_size_meters

        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (i,                     0,          tex_y0))
        out.write("%i %g %g\n" % (i + 1,                 tex_x1, tex_y0))
        out.write("%i %g %g\n" % (i + 1 + nnodes_ground, tex_x1, tex_y1))
        out.write("%i %g %g\n" % (i + nnodes_ground,     0,          tex_y1))

    # -- closing wall
    tex_x1 = lenX[nnodes_ground-1] /  t.h_size_meters
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % mat)
    out.write("refs %i\n" % 4)
    out.write("%i %g %g\n" % (nnodes_ground - 1, 0,          tex_y0))
    out.write("%i %g %g\n" % (0,                 tex_x1, tex_y0))
    out.write("%i %g %g\n" % (nnodes_ground,     tex_x1, tex_y1))
    out.write("%i %g %g\n" % (2*nnodes_ground-1, 0,          tex_y1))

    roof_flat = False

    # -- roof
    if include_roof:
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % nnodes_ground)
        for i in range(nnodes_ground):
            out.write("%i %g %g\n" % (i+nnodes_ground, 0, 0))
        out.write("kids 0\n")
    else:
        # -- textured roof, a separate object
        out.write("kids 1\n")
        out.write("OBJECT poly\n")
        #nb += 1
        out.write("name \"b%i-roof\"\n" % nb)
        out.write('texture "roof.png"\n')

        if roof_flat:
            #out.write("loc 0 0 0\n")
            out.write("numvert %i\n" % (nnodes_ground))
            for x in X[:-1]:
                z = ground_elev - 1
                #out.write("%g %g %g\n" % (y, z, x))
                out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))
            out.write("numsurf %i\n" % 1)
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (0, 0, 0))
            out.write("%i %g %g\n" % (1, 1, 0))
            out.write("%i %g %g\n" % (2, 1, 1))
            out.write("%i %g %g\n" % (3, 0, 1))

            out.write("kids 0\n")
        else:
            # -- gable roof
            out.write("numvert %i\n" % (nnodes_ground + 2))
            for x in X[:-1]:
                z = ground_elev - 1
                #out.write("%g %g %g\n" % (y, z, x))
                out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))
            mid_short_x = 0.5*(X[3][1]+X[0][1])
            mid_short_z = 0.5*(X[3][0]+X[0][0])
            # -- normal vector
            norm = (X[1]-X[0])/lenX[0] * 4.

            out.write("%g %g %g\n" % (0.5*(X[3][1]+X[0][1]) + norm[1], ground_elev + height + 3, 0.5*(X[3][0]+X[0][0]) + norm[0]))
            out.write("%g %g %g\n" % (0.5*(X[1][1]+X[2][1]) - norm[1], ground_elev + height + 3, 0.5*(X[1][0]+X[2][0]) - norm[0]))


            out.write("numsurf %i\n" % 4)
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (0, 0, 0))
            out.write("%i %g %g\n" % (1, 1, 0))
            out.write("%i %g %g\n" % (5, 1, 1))
            out.write("%i %g %g\n" % (4, 0, 1))

            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (2, 0, 0))
            out.write("%i %g %g\n" % (3, 1, 0))
            out.write("%i %g %g\n" % (4, 1, 1))
            out.write("%i %g %g\n" % (5, 0, 1))

            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (1, 0, 0))
            out.write("%i %g %g\n" % (2, 1, 0))
            out.write("%i %g %g\n" % (5, 1, 1))

            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (3, 0, 0))
            out.write("%i %g %g\n" % (0, 1, 0))
            out.write("%i %g %g\n" % (4, 1, 1))

            out.write("kids 0\n")
