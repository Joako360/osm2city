# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""
import random
import numpy as np
import copy

from vec2d import vec2d
from textures import find_matching_texture
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
default_height=12.
random_level_height = random_number(float, 3.1, 3.6)
random_levels = random_number(int, 2, 5)

def check_height(building_height, t):
    """check if a texture t fits the building height (h)
       v-repeatable textures are repeated to fit h
       For non-repeatable textures,
       - check if h is within the texture's limits (minheight, maxheight)
       -
    """
    if t.v_can_repeat:
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
            print "building_height %g outside %g %g" % (building_height, t.v_splits_meters[0], t.v_size_meters)
            return False, 0, 0



def reset_nb():
    global nb
    nb = 0

def write_building(b, out, elev, tile_elev, transform, offset, facades, roofs, LOD_lists):
    """offset accounts for cluster center"""
# am anfang geometrieanalyse
# - ort: urban, residential, rural
# - region: europe, asia...
# - layers: 1-2, 3-5, hi-rise
# - roof-shape: flat, gable
# - age: old, modern

# - facade raussuchen
#   requires: compat:flat-roof

    global first
    mat = random.randint(0,3)

    nnodes_ground = len(b.refs)
#    print nnodes_ground #, b.refs[0].lat, b.refs[0].lon

    level_height = random_level_height()

    # try height first
    # catch exceptions, since height might be "5 m" instead of "5"
    try:
        height = float(b.height)
        if height > 1.: b.levels = (height*1.)/level_height
    except:
        height = 0.
        pass

    if height < 1:
        # failing that, try levels
        if float(b.levels) > 0:
            pass
            print "have levels", b.levels
        else:
            # failing that, use random levels
            b.levels = random_levels()

    height = float(b.levels) * level_height
    print "hei", height, b.levels

    if height < 3.4:
        print "Skipping small building with height < 3.4"
        return

    global nb
    nb += 1
    print nb
    out.write("OBJECT poly\n")
    name = "b%i" % nb
    out.write("name \"%s\"\n" % name)

    lod = random_LOD()
    if b.levels > 5: lod = 2 # tall buildings always LOD bare
    if b.levels < 3: lod = 0 # small buildings always LOD detail
    # mat = lod
    LOD_lists[lod].append(name)

    # -- roof is controlled by two flags:
    #    bool roof_separate: whether or not to include roof as separate model
    #      useful for
    #      - gable roof
    #      - roof with add-ons: AC
    #    replace by roof_type? flat  --> no separate model
    #                          gable --> separate model
    #                          ACs         -"-

    roof_separate = False
    roof_flat = True

    # -- model roof if we have 4 ground nodes
    if nnodes_ground == 4:
        roof_separate = True
        roof_flat = False  # -- gable roof


    # -- no gable roof on tall buildings
    if b.levels > 5:
        roof_flat = True
        roof_separate = False
        # FIXME: roof_ACs = True

    requires = []
    if roof_separate and not roof_flat:
        requires.append('age:old')
        requires.append('compat:roof-gable')

    X = np.zeros((nnodes_ground+1,2))
    lenX = np.zeros((nnodes_ground))
    i = 0
    for r in b.refs:
        X[i,0], X[i,1] = transform.toLocal((r.lat, r.lon))
        X[i,0] -= offset.x # cluster coordinates
        X[i,1] -= offset.y

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

    ground_elev = elev(vec2d(X[0]) + offset) - tile_elev # -- interpolate ground elevation at building location
    #print b.refs[0].lon
    #ground_elev = 200. + (b.refs[0].lon-13.6483695)*5000.
    #print "ground_elev", ground_elev



#    if height > 1.: z = height
#    elif float(b.levels) > 0:
#        z = float(b.levels) * level_height
        #print "LEVEL", z

#    for r in b.refs:
#        x, y = transform.toLocal((r.lat, r.lon))
#        out.write("%g %g %g\n" % (y, z, x))

    nsurf = nnodes_ground
    if not roof_separate: nsurf += 1 # -- because roof will be part of base model

    #repeat_vert = int(height/3)

    # -- texturing facade
    # - check all walls -- min length?
    #global textures
    # loop all textures
    # award points for good matches
    # pick best match?
    building_height = height
    # -- check v: height

    facade_candidates = facades.find_candidates(requires, 0.)
    shuffled_t = copy.copy(facade_candidates)
    random.shuffle(shuffled_t)
    facade_texture = None
    for t in shuffled_t:
        ok, tex_y0, tex_y1 = check_height(building_height, t)
        if ok:
            facade_texture = t
            break

    if facade_texture:
        out.write('texture "%s"\n' % (facade_texture.filename+'.png'))
    else:
        print "WARNING: no texture height", building_height, requires

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
        tex_x1 = lenX[i] / facade_texture.h_size_meters # -- just repeat texture to fit length

        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (i,                     0,          tex_y0))
        out.write("%i %g %g\n" % (i + 1,                 tex_x1, tex_y0))
        out.write("%i %g %g\n" % (i + 1 + nnodes_ground, tex_x1, tex_y1))
        out.write("%i %g %g\n" % (i + nnodes_ground,     0,          tex_y1))

    # -- closing wall
    tex_x1 = lenX[nnodes_ground-1] /  facade_texture.h_size_meters
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % mat)
    out.write("refs %i\n" % 4)
    out.write("%i %g %g\n" % (nnodes_ground - 1, 0,          tex_y0))
    out.write("%i %g %g\n" % (0,                 tex_x1, tex_y0))
    out.write("%i %g %g\n" % (nnodes_ground,     tex_x1, tex_y1))
    out.write("%i %g %g\n" % (2*nnodes_ground-1, 0,          tex_y1))

    # -- roof
    if not roof_separate:
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % nnodes_ground)
        for i in range(nnodes_ground):
            out.write("%i %g %g\n" % (i+nnodes_ground, 0, 0))
        out.write("kids 0\n")
    else:
        # -- textured roof, a separate object
        roof_texture = roofs.find_matching(facade_texture.requires)

        out.write("kids 1\n")
        out.write("OBJECT poly\n")
        out.write("name \"b%i-roof\"\n" % nb)

        if roof_flat:
            roof_texture = 'roof_flat' # FIXME: use requires!
            out.write('texture "%s"\n' % 'roof_flat.png')
        else:
            out.write('texture "%s"\n' % (roof_texture.filename + '.png'))

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
            # -- 4 corners
            for x in X[:-1]:
                z = ground_elev - 1
                #out.write("%g %g %g\n" % (y, z, x))
                out.write("%g %g %g\n" % (x[1], ground_elev + height, x[0]))
            # --
            #mid_short_x = 0.5*(X[3][1]+X[0][1])
            #mid_short_z = 0.5*(X[3][0]+X[0][0])
            # -- tangential vector of long edge
            inward = 4. # will shift roof top 4m inward
            roof_height = 3. # 3m
            tang = (X[1]-X[0])/lenX[0] * inward

            len_roof_top = lenX[0] - 2.*inward
            len_roof_bottom = 1.*lenX[0]

            out.write("%g %g %g\n" % (0.5*(X[3][1]+X[0][1]) + tang[1], ground_elev + height + roof_height, 0.5*(X[3][0]+X[0][0]) + tang[0]))
            out.write("%g %g %g\n" % (0.5*(X[1][1]+X[2][1]) - tang[1], ground_elev + height + roof_height, 0.5*(X[1][0]+X[2][0]) - tang[0]))

            roof_texture_size_x = roof_texture.h_size_meters # size of roof texture in meters
            roof_texture_size_y = roof_texture.v_size_meters
            repeatx = len_roof_bottom / roof_texture_size_x
            len_roof_hypo = ((0.5*lenX[1])**2 + roof_height**2)**0.5
            repeaty = len_roof_hypo / roof_texture_size_y

            out.write("numsurf %i\n" % 4)
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (0, 0, 0))
            out.write("%i %g %g\n" % (1, repeatx, 0))
            out.write("%i %g %g\n" % (5, repeatx*(1-inward/len_roof_bottom), repeaty))
            out.write("%i %g %g\n" % (4, repeatx*(inward/len_roof_bottom), repeaty))

            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (2, 0, 0))
            out.write("%i %g %g\n" % (3, repeatx, 0))
            out.write("%i %g %g\n" % (4, repeatx*(1-inward/len_roof_bottom), repeaty))
            out.write("%i %g %g\n" % (5, repeatx*(inward/len_roof_bottom), repeaty))

            repeatx = lenX[1]/roof_texture_size_x
            len_roof_hypo = (inward**2 + roof_height**2)**0.5
            repeaty = len_roof_hypo/roof_texture_size_y
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (1, 0, 0))
            out.write("%i %g %g\n" % (2, repeatx, 0))
            out.write("%i %g %g\n" % (5, 0.5*repeatx, repeaty))

            repeatx = lenX[3]/roof_texture_size_x
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (3, 0, 0))
            out.write("%i %g %g\n" % (0, repeatx, 0))
            out.write("%i %g %g\n" % (4, 0.5*repeatx, repeaty))

            out.write("kids 0\n")

