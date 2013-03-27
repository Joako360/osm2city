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

from shapely.geometry import Polygon
from shapely.geometry.polygon import LinearRing
import sys
import textwrap
import plot

import tools

def write_and_count_numvert(out, building, numvert):
    """write numvert tag to .ac, update stats"""
    out.write("numvert %i\n" % numvert)
    building.vertices += numvert

def write_and_count_numsurf(out, building, numsurf):
    """write numsurf tag to .ac, update stats"""
    out.write("numsurf %i\n" % numsurf)
    building.surfaces += numsurf

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
        return tex_y0, tex_y1
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error
        # - error acceptable?
        if building_height >= t.v_splits_meters[0] and building_height <= t.v_size_meters:
            for i in range(len(t.v_splits_meters)):
                if t.v_splits_meters[i] >= building_height:
                    tex_y0 = 1-t.v_splits[i]
                    #print "# height %g storey %i" % (building_height, i)
                    break
            tex_y1 = 1.
            #tex_filename = t.filename + '.png'
            return tex_y0, tex_y1
        else:
            raise ValueError("SHOULD NOT HAPPEN! building_height %g outside %g %g" % (building_height, t.v_splits_meters[0], t.v_size_meters))
            return 0, 0



def reset_nb():
    global nb
    nb = 0

def get_nodes_from_acs(objs, path_prefix):
    """load all .ac, extract nodes"""
    # FIXME: use real ac3d reader: https://github.com/majic79/Blender-AC3D/blob/master/io_scene_ac3d/import_ac3d.py
    # FIXME: don't skip .xml

    nodes=np.array([[0,0]])

    for b in objs:
        if b.name.endswith(".ac") and b.stg_typ == "OBJECT_STATIC":
            print "READ", b.name
            try:
                ac = open(path_prefix + b.name, 'r')
            except:
                continue
            lines = ac.readlines()
            i = 0
            while (i < len(lines)):
                if lines[i].startswith('numvert'):
                    line = lines[i]
                    numvert = int(line.split()[1])
                    #print "numvert", numvert
                    for j in range(numvert):
                        i += 1
                        splitted = lines[i].split()
                        node = np.array([[float(splitted[0]),
                                          float(splitted[2])]])
                        #stg_hdg

                        node += b.anchor.list()
                        nodes = np.append(nodes, node,0)
                i += 1

            ac.close()
            #print "------"
    print "nodes: ", nodes.shape

    return nodes



def analyse(buildings, static_objects, transform, elev, facades, roofs):
    """analyse all buildings
    - calculate area
    - location clash with stg static models? drop building
    - analyze surrounding: similar shaped buildings nearby? will get same texture
    - set building type, roof type etc
    - decide LOD

    We're in global coordinates
    """
    # -- build KDtree for static models
    from scipy.spatial import KDTree

    s = get_nodes_from_acs(static_objects.objs, "e013n51/")
#    s = np.zeros((len(static_objects.objs), 2))
#    i = 0
#    for b in static_objects.objs:
#        s[i] = b.anchor.list()
#        i += 1
    static_tree = KDTree(s, leafsize=10) # -- switch to brute force at 10

    new_buildings = []
    for b in buildings:
    # am anfang geometrieanalyse
    # - ort: urban, residential, rural
    # - region: europe, asia...
    # - layers: 1-2, 3-5, hi-rise
    # - roof-shape: flat, gable
    # - age: old, modern

    # - facade raussuchen
    #   requires: compat:flat-roof

    #    global first
        #global stats

        #mat = random.randint(1,4)
        b.mat = 0
        b.roof_mat = 0

        b.nnodes_ground = len(b.refs)
    #    print nnodes_ground #, b.refs[0].lat, b.refs[0].lon

        level_height = random_level_height()

        # try OSM height first
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
                #print "have levels", b.levels
            else:
                # failing that, use random levels
                b.levels = random_levels()

        b.height = float(b.levels) * level_height
        #print "hei", b.height, b.levels

        if b.height < 3.4:
            print "Skipping small building with height < 3.4"
            tools.stats.skipped_small += 1
            continue


        # -- roof is controlled by two flags:
        #    bool b.roof_separate: whether or not to include roof as separate model
        #      useful for
        #      - gable roof
        #      - roof with add-ons: AC
        #    replace by roof_type? flat  --> no separate model
        #                          gable --> separate model
        #                          ACs         -"-

        b.roof_separate = False
        b.roof_flat = True

        # -- model roof if we have 4 ground nodes
        if b.nnodes_ground == 4:
            b.roof_separate = True
            b.roof_flat = False  # -- gable roof


        # -- no gable roof on tall buildings
        if b.levels > 5:
            roof_flat = True
            b.roof_separate = False
            # FIXME: roof_ACs = True

        requires = []
        if b.roof_separate and not b.roof_flat:
            requires.append('age:old')
            requires.append('compat:roof-gable')

        # -- get geometry right
        #    - transform to global coord
        #    - compute edge lengths
        #    - fix inverted faces
        #    - compute area
        X = np.zeros((b.nnodes_ground+1,2))
        lenX = np.zeros((b.nnodes_ground))
        i = 0
        for r in b.refs:
            X[i,0], X[i,1] = transform.toLocal((r.lat, r.lon))
            i += 1

        X[-1] = X[0] # -- we duplicate last node!

        # -- fix inverted faces
        crossX = 0.
        for i in range(b.nnodes_ground):
            crossX += X[i,0]*X[i+1,1] - X[i+1,0]*X[i,1]
            lenX[i] = ((X[i+1,0]-X[i,0])**2 + (X[i+1,1]-X[i,1])**2)**0.5
        if crossX < 0:
            X = X[::-1]
            lenX = lenX[::-1]

        # -- renumber nodes such that longest edge is first
        if b.nnodes_ground == 4:
            if lenX[0] < lenX[1]:
                X = np.roll(X, 1, axis=0)
                lenX = np.roll(lenX, 1)
                X[0] = X[-1]

        # -- static objects nearby?
        # FIXME: which radius? Or use centroid point?
        #radius = max(lenX)
        radius = 1.
        #nearby = static_tree.query_ball_point(X, radius)
        nearby = []
        # FIXME: why now all nearby??

        if b.name == "Semperoper":
            bla

        if len(nearby):
            try:
                print "Static objects nearby. Skipping ", b.name
            except:
                print "FIXME: Encoding problem", b.name.encode('ascii', 'ignore')
            #for n in nearby:
            #    print static_objects.objs[n].name,
            #print
            tools.stats.skipped_nearby += 1
            continue


        # -- shapely stuff
        #    - compute area
        r = LinearRing(list(X))
        p = Polygon(r)
        b.area = p.area

        if b.area < 10.: # FIXME use limits.area_min:
            print "Skipping small building (area)"
            tools.stats.skipped_small += 1
            continue


        #tools.stats.print_summary()
    #    if p.area < 200.:
    #        print "small?", p.area
    #
    #        mat = 1
    #        roof_mat = 1
    #        roof_flat = True
    #        b.roof_separate = False
            #plot.linear_ring(LinearRing(X))
            #sys.exit(0)

        # FIXME: again facade stuff?
        b.facade_texture = facades.find_matching(requires, b.height)
        if not b.facade_texture:
            tools.stats.skipped_texture += 1
            print "Skipping building (no matching texture)"
            continue

        if b.roof_separate:
            b.roof_texture = roofs.find_matching(b.facade_texture.requires)

        # -- finally: append building to new list
        b.X = X
        b.lenX = lenX
        new_buildings.append(b)

    return new_buildings

def write(b, out, elev, tile_elev, transform, offset, LOD_lists):
    """offset accounts for cluster center
       now actually write building.
       While writing, accumulate some statistics
       (totals stored in global stats object, individually also in building)
    """
    X = b.X
    lenX = b.lenX
    height = b.height
    roof_texture = b.roof_texture
    facade_texture = b.facade_texture
    nnodes_ground = b.nnodes_ground
    roof_separate = b.roof_separate

    global nb
    nb += 1
    #print nb
    if nb % 100 == 0: print nb
    else: print ".",

    out.write("OBJECT poly\n")
    name = "b%i" % nb
    out.write("name \"%s\"\n" % name)

    lod = random_LOD()
    if b.area < 150: lod = 0
    if b.area > 1000: lod = 2
    if b.levels > 5: lod = 2 # tall buildings always LOD bare
    #if b.levels < 3: lod = 0 # small buildings always LOD detail
    # mat = lod
    LOD_lists[lod].append(name)


    nsurf = nnodes_ground
    if not roof_separate: nsurf += 1 # -- because roof will be part of base model

    #repeat_vert = int(height/3)

    # -- texturing facade
    # - check all walls -- min length?
    #global textures
    # loop all textures
    # award points for good matches
    # pick best match?

    # -- check v: height

#    shuffled_t = copy.copy(facade_candidates)
#    random.shuffle(shuffled_t)
#    for t in shuffled_t:
    tex_y0, tex_y1 = check_height(height, facade_texture)

    if facade_texture:
        out.write('texture "%s"\n' % (facade_texture.filename+'.png'))
    else:
        print "WARNING: no texture height", height, requires

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
    write_and_count_numvert(out, b, 2*nnodes_ground)

    i = 0
    for r in b.refs:
        X[i,0] -= offset.x # cluster coordinates
        X[i,1] -= offset.y
        i += 1

    ground_elev = elev(vec2d(X[0]) + offset) - tile_elev # -- interpolate ground elevation at building location
    #print b.refs[0].lon
    #ground_elev = 200. + (b.refs[0].lon-13.6483695)*5000.
    #print "ground_elev", ground_elev


    for x in X[:-1]:
        z = ground_elev - 1
        out.write("%g %g %g\n" % (-x[1], z, -x[0]))


    for x in X[:-1]:
        out.write("%g %g %g\n" % (-x[1], ground_elev + b.height, -x[0]))

    write_and_count_numsurf(out, b, nsurf)
    # -- walls

    for i in range(nnodes_ground - 1):
        tex_x1 = lenX[i] / facade_texture.h_size_meters # -- just repeat texture to fit length

        out.write("SURF 0x0\n")
        out.write("mat %i\n" % b.mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (i,                     0,          tex_y0))
        out.write("%i %g %g\n" % (i + 1,                 tex_x1, tex_y0))
        out.write("%i %g %g\n" % (i + 1 + nnodes_ground, tex_x1, tex_y1))
        out.write("%i %g %g\n" % (i + nnodes_ground,     0,          tex_y1))

    # -- closing wall
    tex_x1 = lenX[nnodes_ground-1] /  facade_texture.h_size_meters
    out.write("SURF 0x0\n")
    out.write("mat %i\n" % b.mat)
    out.write("refs %i\n" % 4)
    out.write("%i %g %g\n" % (nnodes_ground - 1, 0,          tex_y0))
    out.write("%i %g %g\n" % (0,                 tex_x1, tex_y0))
    out.write("%i %g %g\n" % (nnodes_ground,     tex_x1, tex_y1))
    out.write("%i %g %g\n" % (2*nnodes_ground-1, 0,          tex_y1))

    # -- roof
    if not b.roof_separate:
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % b.roof_mat)
        out.write("refs %i\n" % nnodes_ground)
        for i in range(nnodes_ground):
            out.write("%i %g %g\n" % (i+nnodes_ground, 0, 0))
        out.write("kids 0\n")
    else:
        # -- textured roof, a separate object

        out.write("kids 1\n")
        out.write("OBJECT poly\n")
        out.write("name \"b%i-roof\"\n" % nb)

        if b.roof_flat:
            roof_texture = 'roof_flat' # FIXME: use requires!
            out.write('texture "%s"\n' % 'roof_flat.png')
        else:
            out.write('texture "%s"\n' % (roof_texture.filename + '.png'))

        if b.roof_flat:
            #out.write("loc 0 0 0\n")
            write_and_count_numvert(out, b, nnodes_ground)
            for x in X[:-1]:
                z = ground_elev - 1
                out.write("%g %g %g\n" % (-x[1], ground_elev + height, -x[0]))
            write_and_count_numsurf(out, b, 1)
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
            write_and_count_numvert(out, b, nnodes_ground + 2)
            # -- 4 corners
            for x in X[:-1]:
                z = ground_elev - 1
                #out.write("%g %g %g\n" % (y, z, x))
                out.write("%g %g %g\n" % (x[1], ground_elev + b.height, x[0]))
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

            write_and_count_numsurf(out, b, 4)
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % b.mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (0, 0, 0))
            out.write("%i %g %g\n" % (1, repeatx, 0))
            out.write("%i %g %g\n" % (5, repeatx*(1-inward/len_roof_bottom), repeaty))
            out.write("%i %g %g\n" % (4, repeatx*(inward/len_roof_bottom), repeaty))

            out.write("SURF 0x0\n")
            out.write("mat %i\n" % b.mat)
            out.write("refs %i\n" % nnodes_ground)
            out.write("%i %g %g\n" % (2, 0, 0))
            out.write("%i %g %g\n" % (3, repeatx, 0))
            out.write("%i %g %g\n" % (4, repeatx*(1-inward/len_roof_bottom), repeaty))
            out.write("%i %g %g\n" % (5, repeatx*(inward/len_roof_bottom), repeaty))

            repeatx = lenX[1]/roof_texture_size_x
            len_roof_hypo = (inward**2 + roof_height**2)**0.5
            repeaty = len_roof_hypo/roof_texture_size_y
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % b.mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (1, 0, 0))
            out.write("%i %g %g\n" % (2, repeatx, 0))
            out.write("%i %g %g\n" % (5, 0.5*repeatx, repeaty))

            repeatx = lenX[3]/roof_texture_size_x
            out.write("SURF 0x0\n")
            out.write("mat %i\n" % b.mat)
            out.write("refs %i\n" % 3)
            out.write("%i %g %g\n" % (3, 0, 0))
            out.write("%i %g %g\n" % (0, repeatx, 0))
            out.write("%i %g %g\n" % (4, 0.5*repeatx, repeaty))

            out.write("kids 0\n")

    tools.stats.count(b)

