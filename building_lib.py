# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""

import logging

import random
import numpy as np
import copy
import pdb
import math

from vec2d import vec2d
from textures import find_matching_texture
#nobjects = 0
nb = 0
out = ""

import shapely.geometry as shg
#from shapely.geometry import Polygon
#from shapely.geometry.polygon import LinearRing
import sys
import textwrap
#import plot
from math import sin, cos, radians
import tools
import parameters
import myskeleton
import roofs

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
        elif randtype == 'gauss':
            self.callback = random.gauss
        else:
            raise TypeError("randtype must be 'float' or 'int'")
    def __call__(self):
        return self.callback(self.min, self.max)

def random_level_height(place="city"):
    """ Calculates the height for each level of a building based on place and random factor"""
    #FIXME: other places (e.g. village)
    return random.triangular(parameters.BUILDING_CITY_LEVEL_HEIGHT_LOW
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_HEIGH
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_MODE)

def random_levels(place="city"):
    """ Calculates the number of building levels based on place and random factor"""
    #FIXME: other places
    return int(round(random.triangular(parameters.BUILDING_CITY_LEVELS_LOW
                          , parameters.BUILDING_CITY_LEVELS_HEIGH
                          , parameters.BUILDING_CITY_LEVELS_MODE)))

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
        # FIXME: respect v_splits
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error
        # - error acceptable?
        if building_height >= t.v_splits_meters[0] and building_height <= t.v_size_meters:
#            print "--->"
            if t.v_split_from_bottom:
#                print "from bottom"
                for i in range(len(t.v_splits_meters)):
                    if t.v_splits_meters[i] >= building_height:
#                        print "bot trying %g >= %g ?" % (t.v_splits_meters[i],  building_height)
                        tex_y0 = 0
                        tex_y1 = t.v_splits[i]
                        #print "# height %g storey %i" % (building_height, i)
                        return tex_y0, tex_y1
            else:
#                print "from top"
#                print "got", t.v_splits_meters
                for i in range(len(t.v_splits_meters)-2, -1, -1):
#                    print "%i top trying %g >= %g ?" % (i, t.v_splits_meters[-1] - t.v_splits_meters[i],  building_height)
                    if t.v_splits_meters[-1] - t.v_splits_meters[i] >= building_height:
                        # FIXME: probably a bug. Should use distance to height?
                        tex_y0 = t.v_splits[i]
                        tex_y1 = 1.
                        return tex_y0, tex_y1
            #tex_filename = t.filename + '.png'
            raise ValueError("SHOULD NOT HAPPEN! found no tex_y0, tex_y1 (building_height %g splits %s %g)" % (building_height, str(t.v_splits_meters), t.v_size_meters))
        else:
            raise ValueError("SHOULD NOT HAPPEN! building_height %g outside %g %g" % (building_height, t.v_splits_meters[0], t.v_size_meters))
            return 0, 0



def reset_nb():
    global nb
    nb = 0

def get_nodes_from_acs(objs, own_prefix):
    """load all .ac and .xml, extract nodes, skipping own .ac starting with own_prefix"""
    # FIXME: use real ac3d reader: https://github.com/majic79/Blender-AC3D/blob/master/io_scene_ac3d/import_ac3d.py
    # FIXME: don't skip .xml
    # skip own .ac city-*.xml

    all_nodes = np.array([[0,0]])

    for b in objs:
        fname = b.name
        #print "in objs <%s>" % b.name
        if fname.endswith(".xml"):
            if fname.startswith(own_prefix): continue
            fname = fname.replace(".xml", ".ac")
        #print "now <%s> %s" % (fname, b.stg_typ)

        # FIXME: also read OBJECT_SHARED.
        if fname.endswith(".ac") and b.stg_typ == "OBJECT_STATIC":
            print "READ_AC", b.name
            try:
                ac = open(fname, 'r')
            except:
                print "can't open", fname
                continue
            angle = radians(b.stg_hdg)
            R = np.array([[cos(angle), -sin(angle)],
                          [sin(angle),  cos(angle)]])

            ac_nodes = np.array([[0,0]])
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
                        node = np.array([-float(splitted[2]),
                                         -float(splitted[0])])

                        node = np.dot(R, node).reshape(1,2)
                        ac_nodes = np.append(ac_nodes, node, 0)
                        #stg_hdg

                i += 1
            ac.close()

#            ac_nodes = R.dot(ac_nodes)
            ac_nodes += b.anchor.list()
            all_nodes = np.append(all_nodes, ac_nodes, 0)
            #print "------"

    return all_nodes

def test_ac_load():
    import stg_io
    # FIXME: this is probably broken
    #static_objects = stg_io.read("e010n50/e013n51", ["3171138.stg", "3171139.stg"], parameters.PREFIX, parameters.PATH_TO_SCENERY)
    #s = get_nodes_from_acs(static_objects.objs, "e013n51/")
    #np.savetxt("nodes.dat", s)
#    out = open("nodes.dat", "w")
#    for n in s:
#            out.write("\n")
#        else: out.write("%g %g\n" % (n[0], n[1]))

#    out.close()
    #print s

def is_static_object_nearby(b, X, static_tree):
    """check for static/shared objects close to given building"""
    # FIXME: which radius? Or use centroid point? make radius a parameter
    radius = parameters.OVERLAP_RADIUS # alternative: radius = max(lenX)

    # -- query_ball_point may return funny lists [[], [], .. ]
    #    filter these
    nearby = static_tree.query_ball_point(X, radius)
    nearby = [x for x in nearby if x]

    if len(nearby):
        for i in range(b.nnodes_outer):
            tools.stats.debug2.write("%g %g\n" % (X[i,0], X[i,1]))
#            print "nearby:", nearby
#            for n in nearby:
#                print "-->", s[n]
        try:
            print "Static objects nearby. Skipping ", b.name, len(nearby)
        except:
            print "FIXME: Encoding problem", b.name.encode('ascii', 'ignore')
        #for n in nearby:
        #    print static_objects.objs[n].name,
        #print
        return True
    return False


def is_large_enough(b, buildings):
    """Checks whether a given building's area is too small for inclusion.
    Never drop tall buildings.
    FIXME: Exclusion might be skipped if the building touches another building (i.e. an annex)
    Returns true if the building should be included (i.e. area is big enough etc.)
    """
    if b.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS: return True
    if b.area < parameters.BUILDING_MIN_AREA or \
       (b.area < parameters.BUILDING_REDUCE_THRESHOLD and random.uniform(0,1) < parameters.BUILDING_REDUCE_RATE):
        #if parameters.BUILDING_REDUCE_CHECK_TOUCH:
            #for k in buildings:
                #if k.touches(b): # using Shapely, but buildings have no polygon currently
                    #return True
        return False
    return True

def compute_height_and_levels(b):
    """Determines total height (and number of levels) of a building based on
       OSM values and other logic"""
    try:
        if isinstance(b.height, (int, long)):
            b.height = float(b.height)
        assert(isinstance(b.height, float))
    except AssertionError:
        logging.warning("Building height has wrong type. Value is: %s", b.height)
        b.height = 0
    # -- try OSM height and levels first
    if b.height > 0: return

    level_height = random_level_height()
    if b.height > 0:
        b.levels = int(b.height/level_height)
        return
    elif b.levels > 0:
        pass
    else:
        # -- neither height nor levels given: use random levels
        b.levels = random_levels()
        if b.area < parameters.BUILDING_MIN_AREA:
            b.levels = min(b.levels, 2)
    b.height = float(b.levels) * level_height

def make_lightmap_dict(buildings):
    """make a dictionary: map texture to objects"""
    lightmap_dict = {}
    for b in buildings:
        key = b.facade_texture
        if not lightmap_dict.has_key(key):
            lightmap_dict[key] = []
        lightmap_dict[key].append(b)
    return lightmap_dict

def decide_LOD(buildings):
    """Decide on the building's LOD based on area, number of levels, and some randomness."""
    for b in buildings:
        r = random.uniform(0,1)
        if r < parameters.LOD_PERCENTAGE_DETAIL: lod = 2  # -- detail
        else: lod = 1                                     #    rough

        if b.levels > parameters.LOD_ALWAYS_ROUGH_ABOVE_LEVELS:  lod = 1  #    tall buildings        -> rough
        if b.levels > parameters.LOD_ALWAYS_BARE_ABOVE_LEVELS:   lod = 0  # -- really tall buildings -> bare
        if b.levels < parameters.LOD_ALWAYS_DETAIL_BELOW_LEVELS: lod = 2  #    small buildings       -> detail

        if b.area < parameters.LOD_ALWAYS_DETAIL_BELOW_AREA:     lod = 2
        if b.area > parameters.LOD_ALWAYS_ROUGH_ABOVE_AREA:      lod = 1
        # mat = lod
        b.LOD = lod
        tools.stats.count_LOD(lod)


def analyse(buildings, static_objects, transform, elev, facades, roofs):
    """analyse all buildings
    - calculate area
    - location clash with stg static models? drop building
    - analyze surrounding: similar shaped buildings nearby? will get same texture
    - set building type, roof type etc

    On entry, we're in global coordinates. Change to local coordinates.
    """
    # -- build KDtree for static models
    from scipy.spatial import KDTree

    #s = get_nodes_from_acs(static_objects.objs, "e013n51/")
    if static_objects:
        s = get_nodes_from_acs(static_objects, parameters.PREFIX + "city")

        np.savetxt("nodes.dat", s)
        static_tree = KDTree(s, leafsize=10) # -- switch to brute force at 10

    new_buildings = []
    for b in buildings:
        # am anfang geometrieanalyse
        # - ort: urban, residential, rural
        # - region: europe, asia...
        # - levels: 1-2, 3-5, hi-rise
        # - roof-shape: flat, gable
        # - age: old, modern

        # - facade raussuchen
        #   requires: compat:flat-roof

        #if len(b.inner_rings_list) < 1: continue

        #mat = random.randint(1,4)
        b.mat = 0
        b.roof_mat = 0

        # -- get geometry right
        #    - simplify
        #    - compute edge lengths

        try:
            tools.stats.nodes_simplified += b.simplify(parameters.BUILDING_SIMPLIFY_TOLERANCE)
            b.roll_inner_nodes()
        except Exception, reason:
            print "simplify or roll_inner_nodes failed (OSM ID %i, %s)" % (b.osm_id, reason)
            continue

        # -- array of local outer coordinates
        Xo = np.array(b.X_outer)

        # -- write nodes to separate debug file
        for i in range(b.nnodes_outer):
            tools.stats.debug1.write("%g %g\n" % (Xo[i,0], Xo[i,1]))

        tools.stats.nodes_ground += b._nnodes_ground

        # -- compute edge length
        b.lenX = np.zeros((b._nnodes_ground))
        for i in range(b.nnodes_outer-1):
            b.lenX[i] = ((Xo[i+1,0]-Xo[i,0])**2 + (Xo[i+1,1]-Xo[i,1])**2)**0.5
        n = b.nnodes_outer
        b.lenX[n-1] = ((Xo[0,0]-Xo[n-1,0])**2 + (Xo[0,1]-Xo[n-1,1])**2)**0.5

        if b.inner_rings_list:
            i0 = b.nnodes_outer
            for interior in b.polygon.interiors:
                Xi = np.array(interior.coords)[:-1]
                n = len(Xi)
                for i in range(n-1):
                    b.lenX[i0 + i] = ((Xi[i+1,0]-Xi[i,0])**2 + (Xi[i+1,1]-Xi[i,1])**2)**0.5
                b.lenX[i0 + n - 1] = ((Xi[0,0]-Xi[n-1,0])**2 + (Xi[0,1]-Xi[n-1,1])**2)**0.5
                i0 += n

        # -- re-number nodes such that longest edge is first -- only on simple buildings
        if b.nnodes_outer == 4 and not b.X_inner:
            if b.lenX[0] < b.lenX[1]:
                Xo = np.roll(Xo, 1, axis=0)
                b.lenX = np.roll(b.lenX, 1)
                b.set_polygon(Xo, b.inner_rings_list)

        b.lenX = b.lenX   # FIXME: compute on the fly, or on set_polygon()?
                        #        Or is there a shapely equivalent?

        # -- skip buildings outside elevation raster
        if elev(vec2d(Xo[0])) == -9999:
            print "-9999"
            tools.stats.skipped_no_elev += 1
            continue

        # -- check for nearby static objects
        if static_objects and is_static_object_nearby(b, Xo, static_tree):
            tools.stats.skipped_nearby += 1
            continue

        # -- work on height and levels

        # -- LOWI year 2525: generate a 'futuristic' city of skyscrapers
        if False:
            if b.area >= 1500:
                b.levels = int(random.gauss(35, 10)) # random_number(int, 10, 60)
                b.height = float(b.levels) * random_level_height()
            if b.area < 1500:
            #if b.area < 200. or (b.area < 500. and random.uniform(0,1) < 0.5):
                tools.stats.skipped_small += 1
                continue

        compute_height_and_levels(b)

        # -- check area
        if not is_large_enough(b, buildings):
            tools.stats.skipped_small += 1
            continue

        if b.height < parameters.BUILDING_MIN_HEIGHT:
            print "Skipping small building with height < building_min_height parameter"
            tools.stats.skipped_small += 1
            continue

        # -- Work on roof
        #    roof is controlled by two flags:
        #    bool b.roof_complex: whether or not to include roof as separate model
        #      useful for
        #      - pitched roof
        #      - roof with add-ons: AC (TODO)
        #    replace by roof_type? flat  --> no separate model
        #                          gable --> separate model
        #                          ACs         -"-
        b.roof_complex = False
        if parameters.BUILDING_COMPLEX_ROOFS:
            # -- pitched, separate roof if we have 4 ground nodes and area below 1000m2
            if not b.polygon.interiors and b.area < 2000:
                if b._nnodes_ground == 4:
                   b.roof_complex = True
                elif (parameters.EXPERIMENTAL_USE_SKEL and \
                   b._nnodes_ground in range(4, parameters.SKEL_MAX_NODES)):
                   b.roof_complex = True

            # -- no pitched roof on tall buildings
            if b.levels > 5:
                b.roof_complex = False
                # FIXME: roof_ACs = True

        requires = []
        if b.roof_complex:
            requires.append('age:old')
            requires.append('compat:roof-pitched')

        # -- determine facade and roof textures
        b.facade_texture = facades.find_matching(requires, b.height)
        if not b.facade_texture:
            tools.stats.skipped_texture += 1
            print "Skipping building (no matching texture)"
            continue
        if b.roof_complex:
            b.roof_texture = roofs.find_matching(b.facade_texture.requires)

#        if b.nnodes_outer != 4:
#            print "!=4",
#            continue

        # -- finally: append building to new list
        new_buildings.append(b)

    return new_buildings


def write(b, out, elev, tile_elev, transform, offset, LOD_lists):
    """now actually write building.
       While writing, accumulate some statistics
       (totals stored in global stats object, individually also in building)
       offset accounts for cluster center
    """

    def write_and_count_vert(out, b):
        """write numvert tag to .ac, update stats"""
        numvert = 2 * b._nnodes_ground
        out.write("numvert %i\n" % numvert)
        b.vertices += numvert

        b.ground_elev = elev(vec2d(X[0]) + offset) - tile_elev # -- interpolate ground elevation at building location
        #print b.refs[0].lon
        #ground_elev = 200. + (b.refs[0].lon-13.6483695)*5000.
        #print "ground_elev", ground_elev

        #print "LEN", b._nnodes_ground
        #print "X  ", len(X)
        #print "Xo  ", len(b.X_outer), b.nnodes_outer
        #print "Xi  ", len(b.X_inner)
        #bla

        for x in X:
            z = b.ground_elev - 1
            out.write("%1.2f %1.2f %1.2f\n" % (-x[1], z, -x[0]))
        for x in X:
            out.write("%1.2f %1.2f %1.2f\n" % (-x[1], b.ground_elev + b.height, -x[0]))
        b.ceiling = b.ground_elev + b.height
    # ----
    def write_ring(out, b, ring, v0, inner = False):
        nnodes_ring = len(ring.coords) - 1

        v1 = v0 + nnodes_ring
        for i in range(v0, v1 - 1):
            if False:
                tex_x1 = b.lenX[i] / facade_texture.h_size_meters # -- simply repeat texture to fit length
            else:
                # FIXME: respect facade texture split_h
                #FIXME: there is a nan in facade_textures.h_splits of tex/facade_modern36x36_12
                a = b.lenX[i] / facade_texture.h_size_meters
                ia = int(a)
                frac = a - ia
                tex_x1 = facade_texture.closest_h_match(frac) + ia
                if tex_x1 > 1.:
                    tools.stats.texture_x_repeated += 1
                else:
                    tools.stats.texture_x_simple += 1

            out.write("SURF 0x0\n")
            mat = b.mat
            #if inner:
            #    mat = 1
            out.write("mat %i\n" % mat)
            out.write("refs %i\n" % 4)
            out.write("%i %g %g\n" % (i,                     0,          tex_y0))
            out.write("%i %g %g\n" % (i + 1,                 tex_x1, tex_y0))
            out.write("%i %g %g\n" % (i + 1 + b._nnodes_ground, tex_x1, tex_y1))
            out.write("%i %g %g\n" % (i     + b._nnodes_ground,     0,          tex_y1))

        #return OK

        # -- closing wall
        tex_x1 = b.lenX[v1-1] /  facade_texture.h_size_meters
        if tex_x1 > 1.:
            tools.stats.texture_x_repeated += 1
        else:
            tools.stats.texture_x_simple += 1
        out.write("SURF 0x0\n")
        out.write("mat %i\n" % mat)
        out.write("refs %i\n" % 4)
        out.write("%i %g %g\n" % (v1 - 1, 0,          tex_y0))
        out.write("%i %g %g\n" % (v0,                 tex_x1, tex_y0))
        out.write("%i %g %g\n" % (v0     + b._nnodes_ground,     tex_x1, tex_y1))
        out.write("%i %g %g\n" % (v1 - 1 + b._nnodes_ground, 0,          tex_y1))

        return v1
    # ---
    X = np.array(b.X_outer + b.X_inner)
#    Xo = np.array(b.X_outer)
    for i in range(b._nnodes_ground):
        X[i,0] -= offset.x # -- cluster coordinates. NB: this changes building coordinates!
        X[i,1] -= offset.y

    #lenX = b.lenX
    #height = b.height
    #roof_texture = b.roof_texture
    facade_texture = b.facade_texture
    #roof_complex = b.roof_complex

    global nb
    nb += 1
    #print nb
    if nb % 70 == 0: print nb
    else: sys.stdout.write(".")

    out.write("OBJECT poly\n")
    b.ac_name = "b%i" % nb
    out.write("name \"%s\"\n" % b.ac_name)
    LOD_lists[b.LOD].append(b.ac_name)

    nsurf = b._nnodes_ground
    #nsurf = b.nnodes_outer


    no_roof = False
    #if not b.roof_complex: no_roof = True
#    if len(b.polygon.interiors) < 2:
#        no_roof = False
#    else:
#        no_roof = True

    if (not no_roof) and (not b.roof_complex): nsurf += 1 # -- because roof will be part of base model

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
    tex_y0, tex_y1 = check_height(b.height, facade_texture)

    if facade_texture:
        out.write('texture "%s"\n' % (facade_texture.filename+'.png'))
    else:
        print "WARNING: no texture height", b.height, requires

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
    write_and_count_vert(out, b)

    write_and_count_numsurf(out, b, nsurf)

    # -- outer and inner walls (if any)
    write_ring(out, b, b.polygon.exterior, 0)
    if True:
        v0 = b.nnodes_outer
        for inner in b.polygon.interiors:
            v0 = write_ring(out, b, inner, v0, True)

    # -- roof
    if no_roof:  # -- a debug thing
        out.write("kids 0\n")
        tools.stats.count(b)
        return

    if not parameters.EXPERIMENTAL_INNER and len(b.polygon.interiors) > 1:
        raise NotImplementedError("Can't yet handle relations with more than one inner way")


    if not b.roof_complex:
        if len(b.polygon.interiors):
            out.write(roofs.flat(b, X))
            tools.stats.count(b)
        else:
            # -- plain flat roof
            out.write(roofs.flat(b, X))
        out.write("kids 0\n")
    # -- roof
    #    We can have complex and non-complex roofs:
    #       - non-complex will be included in base object
    #         - relations with 1 inner -> special flat roof
    #         - all other -> flat roof
    #       - complex will be separate object, go into LOD roof
    #         - 4 nodes pitched: gable, hipped, half-hipped?, gambrel, mansard, ...
    #         - 5+ nodes: skeleton
    #         - 5+ mansard
    #         - all will have additional flat roof for base model LOD

    else:  # -- roof is a separate object, in LOD roof
        out.write("kids 0\n")
        #b.roof_mat = 1 # -- different color
        b.roof_ac_name = "b%i-roof" % nb
#        print "roof name", b.roof_ac_name,
        LOD_lists[3].append(b.roof_ac_name)
#        LOD_lists[b.LOD].append(roof_ac_name)

        # -- pitched roof for > 4 ground nodes
        if b._nnodes_ground > 4 and parameters.EXPERIMENTAL_USE_SKEL:
            s = myskeleton.myskel(b, offset_xy = offset,
                                  offset_z = b.ground_elev + b.height,
                                  max_height = b.height * parameters.SKEL_MAX_HEIGHT_RATIO)
            if not s: # -- fall back to flat roof
                s = roofs.flat(b, X, b.roof_ac_name)
                b.roof_type = 'flat'
#                print "FAIL"
                # FIXME: move to analyse. If we fall back, don't require separate LOD
            else:
#                print "COMPLEX"
                tools.stats.have_complex_roof += 1
            out.write(s)

        # -- pitched roof for exactly 4 ground nodes
        else:
            if b.roof_type=='gabled':
                out.write(roofs.separate_gable(b, X))
            else:
                out.write(roofs.separate_hipped(b, X))
                
#            print "4 GROUND", b._nnodes_ground
        out.write("kids 0\n")

        # -- LOD flat model
        if True:
            roof_ac_name_flat = "b%i-flat" % nb
            LOD_lists[4].append(roof_ac_name_flat)
            out.write(roofs.flat(b, X, roof_ac_name_flat))
            out.write("kids 0\n")

    tools.stats.count(b)
    
#
# Maps the Type of the building 
#    
def mapType(tags):
    if 'building' in tags and not tags['building'] == 'yes':
        return tags['building']
    return 'unknown'

if __name__ == "__main__":
    test_ac_load()
