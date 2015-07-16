# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""

import logging

import random
import numpy as np
import copy
# from pdb import pm
import math
import string

from vec2d import vec2d
import textures.manager as tm
import os
import re
import ac3d_fast
# nobjects = 0
nb = 0
out = ""

import shapely.geometry as shg
# from shapely.geometry import Polygon
# from shapely.geometry.polygon import LinearRing
import sys
import textwrap
# import plot
from math import sin, cos, radians
import tools
import parameters
import myskeleton
import roofs
import ac3d
import matplotlib.pyplot as plt


class random_number(object):
    def __init__(self, randtype, minimum, maximum):
        self.min = minimum
        self.max = maximum
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
    # FIXME: other places (e.g. village)

    return random.triangular(parameters.BUILDING_CITY_LEVEL_HEIGHT_LOW
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_HEIGH
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_MODE)


def random_levels(place="city", dist=None):
    """ Calculates the number of building levels based on place and random factor"""
    # FIXME: other places
    if dist:
        dist *= 2.
        if 1000. > dist:
            E = 15.
        elif 2000. > dist:
            E = (dist - 1000) / 1000.* 12 + 3
        else:
            E = 3.

        levels = int(round(random.gauss(E, 0.3 * E)))
#        print "dist %5.1f  %i levels" % (dist, levels)
        return levels

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
        # -- v-repeatable textures are rotated 90 deg in atlas.
        #    Face will be rotated later on, so his here will actually be u
        tex_y1 = 1.
        tex_y0 = 1 - building_height / t.v_size_meters
        return tex_y0, tex_y1
        # FIXME: respect v_cuts
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error

        # - error acceptable?
        if building_height >= t.v_cuts_meters[0] and building_height <= t.v_size_meters:
#            print "--->"
            if t.v_align_bottom or parameters.BUILDING_FAKE_AMBIENT_OCCLUSION:
                logging.verbose("from bottom")
                for i in range(len(t.v_cuts_meters)):
                    if t.v_cuts_meters[i] >= building_height:
#                        print "bot trying %g >= %g ?" % (t.v_cuts_meters[i],  building_height)
                        tex_y0 = 0
                        tex_y1 = t.v_cuts[i]
                        # print "# height %g storey %i" % (building_height, i)
                        return tex_y0, tex_y1
            else:
#                print "got", t.v_cuts_meters
                for i in range(len(t.v_cuts_meters)-2, -1, -1):
#                    print "%i top trying %g >= %g ?" % (i, t.v_cuts_meters[-1] - t.v_cuts_meters[i],  building_height)
                    if t.v_cuts_meters[-1] - t.v_cuts_meters[i] >= building_height:
                        # FIXME: probably a bug. Should use distance to height?
                        tex_y0 = t.v_cuts[i]
                        tex_y1 = 1
                        # logging.debug("from top %s y0=%4.2f y1=%4.2f" % (t.filename, tex_y0, tex_y1))

                        return tex_y0, tex_y1
            raise ValueError("SHOULD NOT HAPPEN! found no tex_y0, tex_y1 (building_height %g splits %s %g)" % (building_height, str(t.v_cuts_meters), t.v_size_meters))
        else:
           # raise ValueError("SHOULD NOT HAPPEN! building_height %g outside %g %g" % (building_height, t.v_cuts_meters[0], t.v_size_meters))
            return 0, 0


def reset_nb():
    global nb
    nb = 0


def get_nodes_from_acs(objs, own_prefix):
    """load all .ac and .xml, extract nodes, skipping own .ac starting with own_prefix"""
    # FIXME: don't skip .xml
    # skip own .ac city-*.xml

    all_nodes = np.array([[0, 0]])
    
    read_objects = {}

    for b in objs:
        fname = b.name
        # print "in objs <%s>" % b.name
        if fname.endswith(".xml"):
            if fname.startswith(own_prefix):
                continue
            if os.path.exists(fname.replace(".xml", ".ac")):
                fname = fname.replace(".xml", ".ac")
            else:
                if not os.path.exists(fname):
                    continue
                with open(fname) as f:
                    content = f.readlines()
                    for line in content:
                        if "<path>" in line:
                            path = os.path.dirname(fname)
                            fname = path + os.sep + re.split("</?path>",line)[1]
                            break
        # print "now <%s> %s" % (fname, b.stg_typ)

        # Path to shared objects is built elsewhere
        if fname.endswith(".ac"):
            try:
                if fname in read_objects:
                    logging.verbose( "CACHED_AC %s" % fname)
                    ac = read_objects[fname]
                else:
                    logging.info( "READ_AC %s" % fname)
                    ac = ac3d_fast.File(file_name=fname, stats=None)
                    read_objects[fname] = ac
                                
                angle = radians(b.stg_hdg)
                Rot_mat = np.array([[cos(angle), -sin(angle)],
                                    [sin(angle), cos(angle)]])
    
                transposed_ac_nodes = -np.delete(ac.nodes_as_array().transpose(), 1, 0)[::-1]
                transposed_ac_nodes = np.dot(Rot_mat, transposed_ac_nodes)
                transposed_ac_nodes += b.anchor.as_array().reshape(2,1)
                all_nodes = np.append(all_nodes, transposed_ac_nodes.transpose(), 0)
            except Exception, e:
                logging.error("Error reading %s %s"%(fname,e))

    return all_nodes


def test_ac_load():
    import stg_io
    # FIXME: this is probably broken
    # static_objects = stg_io.read("e010n50/e013n51", ["3171138.stg", "3171139.stg"], parameters.PREFIX, parameters.PATH_TO_SCENERY)
    # s = get_nodes_from_acs(static_objects.objs, "e013n51/")
    # np.savetxt("nodes.dat", s)
#    out = open("nodes.dat", "w")
#    for n in s:
#            out.write("\n")
#        else: out.write("%g %g\n" % (n[0], n[1]))

#    out.close()
    # print s


def is_static_object_nearby(b, X, static_tree):
    """check for static/shared objects close to given building"""
    # FIXME: which radius? Or use centroid point? make radius a parameter
    radius = parameters.OVERLAP_RADIUS  # alternative: radius = max(lenX)

    # -- query_ball_point may return funny lists [[], [], .. ]
    #    filter these
    nearby = static_tree.query_ball_point(X, radius)
    nearby = [x for x in nearby if x]
    nearby = [item for sublist in nearby for item in sublist]
    nearby = list(set(nearby))
    d = static_tree.data
    
    

    if len(nearby):
        if parameters.OVERLAP_CHECK_INSIDE:
            for i in nearby:
                inside = False
                inside = b.polygon.contains(shg.Point(d[i]))
                if inside:
                    break        
    #        for i in range(b.nnodes_outer):
    #            tools.stats.debug2.write("%g %g\n" % (X[i,0], X[i,1]))
    #            print "nearby:", nearby
    #            for n in nearby:
    #                print "-->", s[n]
            if not inside:
                return False
        try:
            if b.name is None or len(b.name) == 0:
                logging.info( "Static objects nearby. Skipping %d is near %d building nodes"%( b.osm_id, len(nearby)))
            else:
                logging.info( "Static objects nearby. Skipping %s (%d) is near %d building nodes"%( b.name, b.osm_id, len(nearby)))
        except RuntimeError as e:
            logging.error( "FIXME: %s %s ID %d" % (e, b.name.encode('ascii', 'ignore'), b.osm_id))
        # for n in nearby:
        #    print static_objects.objs[n].name,
        # print
        return True
    return False


def is_large_enough(b, buildings):
    """Checks whether a given building's area is too small for inclusion.
    Never drop tall buildings.
    FIXME: Exclusion might be skipped if the building touches another building (i.e. an annex)
    Returns true if the building should be included (i.e. area is big enough etc.)
    """
    if b.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS: 
        return True
    if not b.parent is None:
        #Check parent if we're a part
        b = b.parent
    if b.area < parameters.BUILDING_MIN_AREA or \
       (b.area < parameters.BUILDING_REDUCE_THRESHOLD and random.uniform(0, 1) < parameters.BUILDING_REDUCE_RATE):
        # if parameters.BUILDING_REDUCE_CHECK_TOUCH:
            # for k in buildings:
                # if k.touches(b): # using Shapely, but buildings have no polygon currently
                    # return True
        return False
    return True


def compute_height_and_levels(b):
    """Determines total height (and number of levels) of a building based on
       OSM values and other logic"""
    if 0:
        b.levels = 13
        b.height = b.levels * 3.
        return

    try:
        if isinstance(b.height, (int, long)):
            b.height = float(b.height)
        assert(isinstance(b.height, float))
    except AssertionError:
        logging.warning("Building height has wrong type. Value is: %s", b.height)
        b.height = 0
    # -- try OSM height and levels first
    if b.height > 0 and b.levels > 0:
        return

    level_height = random_level_height()
    if b.height > 0:
        b.levels = int(b.height / level_height)
        return
    elif b.levels > 0:
        pass
    else:
        # -- neither height nor levels given: use random levels
        b.levels = random_levels()
        # b.levels = random_levels(dist=b.anchor.magnitude())  # gives CBD-like distribution

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
        r = random.uniform(0, 1)
        if r < parameters.LOD_PERCENTAGE_DETAIL: lod = 2  # -- detail
        else: lod = 1  #    rough

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

    # s = get_nodes_from_acs(static_objects.objs, "e013n51/")
    if static_objects:
        s = get_nodes_from_acs(static_objects, parameters.PREFIX + "city")

        np.savetxt(parameters.PREFIX + os.sep + "nodes.dat", s)
        static_tree = KDTree(s, leafsize=10)  # -- switch to brute force at 10

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

        # if len(b.inner_rings_list) < 1: continue

        # mat = random.randint(1,4)
        b.mat = 0
        b.roof_mat = 0

        # -- get geometry right
        #    - simplify
        #    - compute edge lengths

        try:
            tools.stats.nodes_simplified += b.simplify(parameters.BUILDING_SIMPLIFY_TOLERANCE)
            b.roll_inner_nodes()
        except Exception, reason:
            logging.warn( "simplify or roll_inner_nodes failed (OSM ID %i, %s)" % (b.osm_id, reason))
            continue

        # -- array of local outer coordinates
        Xo = np.array(b.X_outer)

        # -- write nodes to separate debug file
#        for i in range(b.nnodes_outer):
#            tools.stats.debug1.write("%g %g\n" % (Xo[i,0], Xo[i,1]))

        tools.stats.nodes_ground += b._nnodes_ground

        # -- compute edge length
        b.lenX = np.zeros((b._nnodes_ground))
        for i in range(b.nnodes_outer - 1):
            b.lenX[i] = ((Xo[i + 1, 0] - Xo[i, 0]) ** 2 + (Xo[i + 1, 1] - Xo[i, 1]) ** 2) ** 0.5
        n = b.nnodes_outer
        b.lenX[n - 1] = ((Xo[0, 0] - Xo[n - 1, 0]) ** 2 + (Xo[0, 1] - Xo[n - 1, 1]) ** 2) ** 0.5
        b.longest_edge_len = max(b.lenX)

        if b.inner_rings_list:
            i0 = b.nnodes_outer
            for interior in b.polygon.interiors:
                Xi = np.array(interior.coords)[:-1]
                n = len(Xi)
                for i in range(n - 1):
                    b.lenX[i0 + i] = ((Xi[i + 1, 0] - Xi[i, 0]) ** 2 + (Xi[i + 1, 1] - Xi[i, 1]) ** 2) ** 0.5
                b.lenX[i0 + n - 1] = ((Xi[0, 0] - Xi[n - 1, 0]) ** 2 + (Xi[0, 1] - Xi[n - 1, 1]) ** 2) ** 0.5
                i0 += n

        # -- re-number nodes such that longest edge is first -- only on simple buildings
        if b.nnodes_outer == 4 and not b.X_inner:
            if b.lenX[0] < b.lenX[1]:
                Xo = np.roll(Xo, 1, axis=0)
                b.lenX = np.roll(b.lenX, 1)
                b.set_polygon(Xo, b.inner_rings_list)

        b.lenX = b.lenX  # FIXME: compute on the fly, or on set_polygon()?
                        #        Or is there a shapely equivalent?

        # -- skip buildings outside elevation raster
        if elev(vec2d(Xo[0])) == -9999:
            logging.debug("-9999")
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
                b.levels = int(random.gauss(35, 10))  # random_number(int, 10, 60)
                b.height = float(b.levels) * random_level_height()
            if b.area < 1500:
            # if b.area < 200. or (b.area < 500. and random.uniform(0,1) < 0.5):
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
        #    bool b.roof_complex: flat or pitched?
        #    bool b.roof_separate_LOD
        #      useful for
        #      - pitched roof
        #      - roof with add-ons: AC (TODO)
        #    replace by roof_type? flat  --> no separate model
        #                          gable --> separate model
        #                          ACs         -"-
        b.roof_complex = False
        if parameters.BUILDING_COMPLEX_ROOFS:
            # -- pitched, separate roof if we have 4 ground nodes and area below 1000m2
            if not b.polygon.interiors and b.area < parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA:
                if b._nnodes_ground == 4:
                    b.roof_complex = True
                if (parameters.BUILDING_SKEL_ROOFS and \
                    b._nnodes_ground in range(4, parameters.BUILDING_SKEL_MAX_NODES)):
                    b.roof_complex = True

            # -- no pitched roof on tall buildings
            if b.levels > parameters.BUILDING_COMPLEX_ROOFS_MAX_LEVELS:
                b.roof_complex = False
                # FIXME: roof_ACs = True

        facade_requires = []
        if b.roof_complex:
            facade_requires.append('age:old')
            facade_requires.append('compat:roof-pitched')
        else:
            facade_requires.append('compat:roof-flat')
            
        try:
            if 'terminal' in string.lower(b.tags['aeroway']):
                facade_requires.append('facade:shape:terminal')
        except KeyError:
            pass
        try :
            material_type = string.lower(b.tags['building:material'])
            if str(material_type) in ['stone', 'brick', 'timber_framing' ] :
                facade_requires.append(str('facade:building:material:'+ str(material_type)))
            try :
                # stone use for 
                if str(material_type) == 'stone' :
                    if 'roof:shape' not in b.tags :
                        b.roof_type = 'flat'
            except KeyError:
                pass
        try :
            # cleanup building:colour and use it
            if   'building:color' in b.tags and 'building:colour' not in b.tags :
                b.tags['building:colour'] = b.tags['building:color']
                del(b.tags['building:color'])
            elif 'building:color' in b.tags and 'building:colour'     in b.tags :
                del(b.tags['building:color'])
            facade_requires.append('facade:building:colour:'+string.lower(b.tags['building:colour']))
        except KeyError:
            pass    
#
        # -- determine facade and roof textures
        logging.verbose("___find facade")
        if b.parent is None:
            b.facade_texture = facades.find_matching(facade_requires, b.tags, b.height, b.longest_edge_len)
        else:
            if b.parent.facade_texture is None:
#                 if b.parent.osm_id == 3825399:
#                     print b.parent
                b.facade_texture = facades.find_matching(facade_requires, b.parent.tags, b.height, b.longest_edge_len)
                b.parent.facade_texture = b.facade_texture
            else:
                b.facade_texture = b.parent.facade_texture
        logging.verbose("__done" + str(b.facade_texture))
        if not b.facade_texture:
            tools.stats.skipped_texture += 1
            logging.info("Skipping building OsmID %d (no matching texture)" % b.osm_id)
            continue
        if(b.longest_edge_len > b.facade_texture.width_max):
            logging.error("OsmID : %d b.longest_edge_len <= b.facade_texture.width_max"%b.osm_id)
            continue
        # print "long", b.longest_edge_len, b.facade_texture.width_max, str(b.facade_texture)

        roof_requires = copy.copy(b.facade_texture.requires)
        if b.roof_complex:
            roof_requires.append('compat:roof-pitched')
        else:
            roof_requires.append('compat:roof-flat')

        # make roof equal across parts
        if b.parent is None:
            b.roof_texture = roofs.find_matching(roof_requires)
            if not b.roof_texture:
                tools.stats.skipped_texture += 1
                logging.warn("WARNING: no matching texture for OsmID %d <%s>" % (b.osm_id,str(roof_requires)))
                continue
        else:
            if b.parent.roof_texture is None:
                b.roof_texture = roofs.find_matching(roof_requires)
                b.parent.roof_texture = b.roof_texture
                if not b.roof_texture:
                    tools.stats.skipped_texture += 1
                    logging.warn("WARNING: no matching texture for OsmID %d <%s>" % (b.osm_id,str(roof_requires)))
                    continue
            else:
                b.roof_texture = b.parent.roof_texture

        # -- finally: append building to new list
        new_buildings.append(b)

    return new_buildings


def write_and_count_vert(out, b, elev, offset, tile_elev):
    """write numvert tag to .ac, update stats"""
#    numvert = 2 * b._nnodes_ground
    # out.write("numvert %i\n" % numvert)

    # b.n_verts += numvert

    # print b.refs[0].lon
    # ground_elev = 200. + (b.refs[0].lon-13.6483695)*5000.
    # print "ground_elev", ground_elev

    # print "LEN", b._nnodes_ground
    # print "X  ", len(X)
    # print "Xo  ", len(b.X_outer), b.nnodes_outer
    # print "Xi  ", len(b.X_inner)
    # bla

    b.first_node = out.next_node_index()

    for x in b.X:
        z = b.ground_elev - 1
        out.node(-x[1], z, -x[0])
    for x in b.X:
        out.node(-x[1], b.ground_elev + b.height, -x[0])
    b.ceiling = b.ground_elev + b.height
# ----


def write_ground(out, b, elev):
    # align smallest rectangle
    d = 0

    # align x/y
    if 1:
        x0 = b.X[:, 0].min() - d
        x1 = b.X[:, 0].max() + d
        y0 = b.X[:, 1].min() - d
        y1 = b.X[:, 1].max() + d

    if 0:
        Xo = np.array([[x0, y0], [x1, y1]])
        angle = 1. / 57.3
        R = np.array([[cos(angle), sin(angle)],
                      [-sin(angle), cos(angle)]])
        Xo_rot = np.dot(Xo, R)
        x0 = Xo_rot[0, 0]
        x1 = Xo_rot[1, 0]
        y0 = Xo_rot[0, 1]
        y1 = Xo_rot[1, 1]

    # align along longest side
    if 0:
        # Xo = np.array(b.X_outer)
        Xo = b.X.copy()
        # origin = Xo[0].copy()
        # Xo -= origin

        # rotate such that longest side is parallel with x
        i = b.lenX[:b.nnodes_outer].argmax()  # longest side
        i1 = i + 1
        if i1 == b.nnodes_outer:
            i1 = 0
        angle = math.atan2(Xo[i1, 1] - Xo[i, 1], Xo[i1, 0] - Xo[i, 0])

        l = ((Xo[i1, 1] - Xo[i, 1]) ** 2 + (Xo[i1, 0] - Xo[i, 0]) ** 2) ** 0.5
        print l, b.lenX[i]
        # assert (l == b.lenX[i])
        # angle = 10./57.3
        R = np.array([[cos(angle), sin(angle)],
                      [-sin(angle), cos(angle)]])
        Xo_rot = np.dot(Xo, R)
        x0 = Xo_rot[:, 0].min() - d
        x1 = Xo_rot[:, 0].max() + d
        y0 = Xo_rot[:, 1].min() - d
        y1 = Xo_rot[:, 1].max() + d
        # rotate back
        if 1:
            R = np.array([[cos(angle), -sin(angle)],
                          [sin(angle), cos(angle)]])
            Xnew = np.array([[x0, y0], [x1, y1]])
            Xnew_rot = np.dot(Xnew, R)
            x0 = Xnew_rot[0, 0]
            x1 = Xnew_rot[1, 0]
            y0 = Xnew_rot[0, 1]
            y1 = Xnew_rot[1, 1]

            if x0 > x1:
                x0, x1 = x1, x0
            if y0 > y1:
                y0, y1 = y1, y0

        # print x0, y0, x1, y1
        # print x0_, y0_, x1_, y1_
        # bla

    offset_z = 0.05
    z0 = elev(vec2d(x0, y0)) + offset_z
    z1 = elev(vec2d(x1, y0)) + offset_z
    z2 = elev(vec2d(x1, y1)) + offset_z
    z3 = elev(vec2d(x0, y1)) + offset_z

    o = out.next_node_index()
    out.node(-y0, z0, -x0)
    out.node(-y0, z1, -x1)
    out.node(-y1, z2, -x1)
    out.node(-y1, z3, -x0)
    out.face([(o, 0, 0),
               (o + 1, 0, 0),
               (o + 2, 0, 0),
               (o + 3, 0, 0)], mat=1)


def write_ring(out, b, ring, v0, texture, tex_y0, tex_y1, inner=False):
    tex_y0 = texture.y(tex_y0)  # -- to atlas coordinates
    tex_y1 = texture.y(tex_y1)

    nnodes_ring = len(ring.coords) - 1
    v1 = v0 + nnodes_ring
    # print "v0 %i v1 %i lenX %i" % (v0, v1, len(b.lenX))
    for i in range(v0, v1 - 1):
        if False:
            tex_x1 = texture.x(b.lenX[i] / texture.h_size_meters)  # -- simply repeat texture to fit length
        else:
            # FIXME: respect facade texture split_h
            # FIXME: there is a nan in textures.h_splits of tex/facade_modern36x36_12
            a = b.lenX[i] / texture.h_size_meters
            ia = int(a)
            frac = a - ia
            tex_x1 = texture.x(texture.closest_h_match(frac) + ia)
            if texture.v_can_repeat:
                # assert(tex_x1 <= 1.)
                if not (tex_x1 <= 1.):
                    logging.debug('FIXME: v_can_repeat: need to check in analyse')
        tex_x0 = texture.x(0)
        # print "texx", tex_x0, tex_x1
        j = i + b.first_node
        out.face([ (j, tex_x0, tex_y0),
                   (j + 1, tex_x1, tex_y0),
                   (j + 1 + b._nnodes_ground, tex_x1, tex_y1),
                   (j + b._nnodes_ground, tex_x0, tex_y1) ],
                   swap_uv=texture.v_can_repeat)

    # -- closing wall
    tex_x1 = texture.x(b.lenX[v1 - 1] / texture.h_size_meters)

    j0 = v0 + b.first_node
    j1 = v1 + b.first_node

    out.face([(j1 - 1, tex_x0, tex_y0),
               (j0, tex_x1, tex_y0),
               (j0 + b._nnodes_ground, tex_x1, tex_y1),
               (j1 - 1 + b._nnodes_ground, tex_x0, tex_y1)],
               swap_uv=texture.v_can_repeat)
    return v1
    # ---
    # need numvert
    # numsurf


def write(ac_file_name, buildings, elev, tile_elev, transform, offset):
    """now actually write buildings of one LOD for given tile.
       While writing, accumulate some statistics
       (totals stored in global stats object, individually also in building)
       offset accounts for cluster center
       - all LOD in one file. Plus roofs. One Object per LOD
    """
    def local_elev(p):
        return elev(p + offset) - tile_elev

    ac = ac3d.File(stats=tools.stats)
    LOD_objects = []
    LOD_objects.append(ac.new_object('LOD_bare', tm.atlas_file_name + '.png'))
    LOD_objects.append(ac.new_object('LOD_rough', tm.atlas_file_name + '.png'))
    LOD_objects.append(ac.new_object('LOD_detail', tm.atlas_file_name + '.png'))

    global nb  # FIXME: still need this?

    for ib, b in enumerate(buildings):
        tools.progress(ib, len(buildings))
        out = LOD_objects[b.LOD]
        b.X = np.array(b.X_outer + b.X_inner)
    #    Xo = np.array(b.X_outer)
        for i in range(b._nnodes_ground):
            b.X[i, 0] -= offset.x  # -- cluster coordinates. NB: this changes building coordinates!
            b.X[i, 1] -= offset.y


        b.ground_elev = local_elev(vec2d(b.X[0]))  # -- interpolate ground elevation at building location
        # b.ground_elev = elev(vec2d(b.X[0]) + offset) - tile_elev # -- interpolate ground elevation at building location
        # write_ground(out, b, local_elev)
        write_and_count_vert(out, b, elev, offset, tile_elev)

        nb += 1
#        if nb % 70 == 0: print nb
#        else: sys.stdout.write(".")

        b.ac_name = "b%i" % nb

#        if (not no_roof) and (not b.roof_complex): nsurf += 1 # -- because roof will be part of base model

        tex_y0, tex_y1 = check_height(b.height, b.facade_texture)


        # -- outer and inner walls (if any)
        # print "--1"
        write_ring(out, b, b.polygon.exterior, 0, b.facade_texture, tex_y0, tex_y1)
        if True:
            v0 = b.nnodes_outer
            for inner in b.polygon.interiors:
                # print "--2"
                v0 = write_ring(out, b, inner, v0, b.facade_texture, tex_y0, tex_y1, True)
# def write_ring(out, b, ring, v0, texture, tex_y0, tex_y1, inner = False):

        # -- roof
        if False:  # -- a debug thing
            tools.stats.count(b)
            continue

        if not parameters.EXPERIMENTAL_INNER and len(b.polygon.interiors) > 1:
            raise NotImplementedError("Can't yet handle relations with more than one inner way")

        if not b.roof_complex:
        # if True:
            roofs.flat(out, b, b.X)
            continue

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
            # out.close_object()
            # FIXME: put roofs again into seperate LOD
            # -- pitched roof for > 4 ground nodes

            if b._nnodes_ground > 4 and parameters.BUILDING_SKEL_ROOFS:
                s = myskeleton.myskel(out, b, offset_xy=offset,
                                      offset_z=b.ground_elev + b.height,
                                      max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
                if s:
                    tools.stats.have_complex_roof += 1
                else:  # -- fall back to flat roof
                    roofs.flat(out, b, b.X)
                    # FIXME: move to analyse. If we fall back, don't require separate LOD
            # -- pitched roof for exactly 4 ground nodes
            else:
                max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO
                if b.roof_type == 'gabled' or b.roof_type == 'half_hipped' :
                    roofs.separate_gable(out, b, b.X, max_height=max_height)
                elif b.roof_type == 'hipped':
                    roofs.separate_hipped(out, b, b.X, max_height=max_height)
                elif b.roof_type == 'pyramidal' :
                    roofs.separate_pyramidal(out, b, b.X, max_height=max_height)
                elif b.roof_type == 'flat':
                    roofs.flat(out, b, b.X)
                else:
                    logging.debug("FIXME simple rooftype %s unsupported "%b.roof_type)
                    roofs.flat(out, b, b.X)
            # out_surf.write("kids 0\n")

            # -- LOD flat model
            if False:
                roof_ac_name_flat = "b%i-flat" % nb
                LOD_lists[4].append(roof_ac_name_flat)
                out_surf.write(roofs.flat(b, X, roof_ac_name_flat))
                out_surf.write("kids 0\n")

    ac.write(ac_file_name)
    # plot on-screen using matplotlib
    if 0:
        ac.plot()
        plt.show()


# Maps the Type of the building
#
def mapType(tags):
    if 'building' in tags and not tags['building'] == 'yes':
        return tags['building']
    return 'unknown'


if __name__ == "__main__":
    test_ac_load()