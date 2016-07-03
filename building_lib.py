# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""

import copy
import logging
import math
from math import sin, cos, radians, tan, sqrt, pi
import os
import random
import re
import string

import matplotlib.pyplot as plt
import numpy as np
import shapely.geometry as shg

import ac3d
import ac3d_fast
import myskeleton
import osm2city
import parameters
import roofs
import textures.manager as tm
import tools
from vec2d import vec2d

nb = 0
out = ""


def _random_level_height():
    """ Calculates the height for each level of a building based on place and random factor"""
    # FIXME: other places (e.g. village)
    return random.triangular(parameters.BUILDING_CITY_LEVEL_HEIGHT_LOW
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_HEIGH
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_MODE)


def _random_levels():
    """ Calculates the number of building levels based on place and random factor"""
    # FIXME: other places
    return int(round(random.triangular(parameters.BUILDING_CITY_LEVELS_LOW
                          , parameters.BUILDING_CITY_LEVELS_HEIGH
                          , parameters.BUILDING_CITY_LEVELS_MODE)))


def _check_height(building_height, t):
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
        if t.v_cuts_meters[0] <= building_height <= t.v_size_meters:
            if t.v_align_bottom or parameters.BUILDING_FAKE_AMBIENT_OCCLUSION:
                logging.verbose("from bottom")
                for i in range(len(t.v_cuts_meters)):
                    if t.v_cuts_meters[i] >= building_height:
                        tex_y0 = 0
                        tex_y1 = t.v_cuts[i]
                        return tex_y0, tex_y1
            else:
                for i in range(len(t.v_cuts_meters)-2, -1, -1):
                    if t.v_cuts_meters[-1] - t.v_cuts_meters[i] >= building_height:
                        # FIXME: probably a bug. Should use distance to height?
                        tex_y0 = t.v_cuts[i]
                        tex_y1 = 1

                        return tex_y0, tex_y1
            raise ValueError("SHOULD NOT HAPPEN! found no tex_y0, tex_y1 (building_height %g splits %s %g)" %
                             (building_height, str(t.v_cuts_meters), t.v_size_meters))
        else:
            return 0, 0


def _get_nodes_from_acs(objs, own_prefix):
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
                            fname = path + os.sep + re.split("</?path>", line)[1]
                            break
        # print "now <%s> %s" % (fname, b.stg_typ)

        # Path to shared objects is built elsewhere
        if fname.endswith(".ac"):
            try:
                if fname in read_objects:
                    logging.verbose("CACHED_AC %s" % fname)
                    ac = read_objects[fname]
                else:
                    logging.info("READ_AC %s" % fname)
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
                logging.error("Error reading %s %s" % (fname,e))

    return all_nodes


def _is_static_object_nearby(b, X, static_tree):
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
            inside = False
            for i in nearby:
                inside = b.polygon.contains(shg.Point(d[i]))
                if inside:
                    break        
            if not inside:
                return False
        try:
            if b.name is None or len(b.name) == 0:
                logging.info("Static objects nearby. Skipping %d is near %d building nodes",
                             b.osm_id, len(nearby))
            else:
                logging.info("Static objects nearby. Skipping %s (%d) is near %d building nodes",
                             b.name, b.osm_id, len(nearby))
        except RuntimeError as e:
            logging.error("FIXME: %s %s ID %d", e, b.name.encode('ascii', 'ignore'), b.osm_id)
        return True
    return False


def _is_large_enough(b):
    """Checks whether a given building's area is too small for inclusion.
    Never drop tall buildings.
    FIXME: Exclusion might be skipped if the building touches another building (i.e. an annex)
    Returns true if the building should be included (i.e. area is big enough etc.)
    """
    if b.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS: 
        return True
    if b.parent is not None:
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


def _compute_height_and_levels(b):
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
    if b.height > 0 and b.levels > 0:
        return

    level_height = _random_level_height()
    if b.height > 0:
        b.levels = int(b.height / level_height)
        return
    elif b.levels > 0:
        pass
    else:
        # -- neither height nor levels given: use random levels
        b.levels = _random_levels()
        # b.levels = random_levels(dist=b.anchor.magnitude())  # gives CBD-like distribution

        if b.area < parameters.BUILDING_MIN_AREA:
            b.levels = min(b.levels, 2)
    b.height = float(b.levels) * level_height


def _compute_roof_height(b, max_height=1e99):
    """Compute roof_height for each node"""

    b.roof_height = 0
    
    if b.roof_type == 'skillion':
        # get global roof_height and height for each vertex
            if 'roof:height' in b.tags:
                # force clean of tag if the unit is given 
                roof_height = float(re.sub(' .*', ' ', b.tags['roof:height'].strip()))
            else:
                if 'roof:angle' in b.tags:
                    angle = float(b.tags['roof:angle'])
                else:
                    angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE,
                                           parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
            
                while angle > 0:
                    roof_height = tan(np.deg2rad(angle)) * (b.lenX[1]/2)
                    if roof_height < max_height:
                        break
                    angle -= 1

            if 'roof:slope:direction' in b.tags:
                # Input angle
                # angle are given clock wise with reference 0 as north
                # 
                # angle 0 north
                # angle 90 east
                # angle 180 south
                # angle 270 west
                # angle 360 north
                #
                # here we works with trigo angles 
                angle00 = (pi/2. - (((float(b.tags['roof:slope:direction'])) % 360.)*pi/180.))
            else:
                angle00 = 0
                
            angle90 = angle00 + pi/2.
            ibottom = 0
            # assume that first point is on the bottom side of the roof
            # and is a reference point (0,0)
            # compute line slope*x
            
            slope = sin(angle90)
            
            dir1n = (cos(angle90), slope)  # (1/ndir1, slope/ndir1)
            
            # keep in mind direction
            #if angle90 < 270 and angle90 >= 90 :
            #    #dir1, dir1n = -dir1, -dir1n
            #    dir1=(-dir1[0],-dir1[1])
            #    dir1n=(-dir1n[0],-dir1n[1])

            # compute distance from points to line slope*x
            X2 = list()
            XN = list()
            nXN = list()
            vprods = list()
            
            X = b.X
            
            p0 = (X[0][0], X[0][1])
            for i in range(0,len(X)):
                # compute coord in new referentiel
                vecA = (X[i][0]-p0[0], X[i][1]-p0[1])
                X2.append(vecA)
                # 
                norm = vecA[0]*dir1n[0] + vecA[1]*dir1n[1]
                vecN = (vecA[0] - norm*dir1n[0], vecA[1] - norm*dir1n[1])
                nvecN = sqrt(vecN[0]**2 + vecN[1]**2)
                # store vec and norms
                XN.append(vecN)
                nXN.append(nvecN)
                # compute ^ product
                vprod = dir1n[0]*vecN[1]-dir1n[1]*vecN[0]
                vprods.append(vprod)

            # if first point was not on bottom side, one must find the right point
            # and correct distances
            if min(vprods) < 0:
                ibottom = vprods.index(min(vprods))
                offset = nXN[ibottom]
                norms_o = [nXN[i] + offset if vprods[i] >= 0 else -nXN[i] + offset for i in range(0, len(X))]  # oriented norm
            else:
                norms_o = nXN

            # compute height for each point with thales
            L = float(max(norms_o)) 

            #try :
            b.roof_height_X = [roof_height*l/L for l in norms_o]
            b.roof_height = roof_height

    else:
        #
        # others roofs type
        #
        try:
            # get roof:height given by osm
            b.roof_height = float(re.sub(' .*', ' ', b.tags['roof:height'].strip()))
            
        except:
            # random roof:height
            if b.roof_type == 'flat':
                b.roof_height = 0
            #if b.roof_type in ['gabled', 'pyramidal','half] :
            else:
                if 'roof:angle' in b.tags:
                    angle = float(b.tags['roof:angle'])
                else:
                    angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE, parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
                while angle > 0:
                    roof_height = tan(np.deg2rad(angle)) * (b.lenX[1]/2)
                    if roof_height < max_height:
                        break
                    angle -= 5
                if roof_height > max_height:
                    logging.warn("roof too high %g > %g" % (roof_height, max_height))
                    return False
                    
                b.roof_height = roof_height
            #else :
            # should compute roof height for others roof type
            #    b.roof_height = 0
    return


def decide_LOD(buildings):
    """Decide on the building's LOD based on area, number of levels, and some randomness."""
    for b in buildings:
        r = random.uniform(0, 1)
        if r < parameters.LOD_PERCENTAGE_DETAIL:
            lod = osm2city.Building.LOD_DETAIL
        else:
            lod = osm2city.Building.LOD_ROUGH

        if b.levels > parameters.LOD_ALWAYS_ROUGH_ABOVE_LEVELS:
            lod = osm2city.Building.LOD_ROUGH  # tall buildings        -> rough
        if b.levels > parameters.LOD_ALWAYS_BARE_ABOVE_LEVELS:
            lod = osm2city.Building.LOD_BARE  # really tall buildings -> bare
        if b.levels < parameters.LOD_ALWAYS_DETAIL_BELOW_LEVELS:
            lod = osm2city.Building.LOD_DETAIL  # small buildings       -> detail

        if b.area < parameters.LOD_ALWAYS_DETAIL_BELOW_AREA:
            lod = osm2city.Building.LOD_DETAIL
        elif b.area > parameters.LOD_ALWAYS_ROUGH_ABOVE_AREA:
            lod = osm2city.Building.LOD_ROUGH

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

    if static_objects:
        s = _get_nodes_from_acs(static_objects, parameters.PREFIX + "city")

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
            logging.warn("simplify or roll_inner_nodes failed (OSM ID %i, %s)", b.osm_id, reason)
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
        if static_objects and _is_static_object_nearby(b, Xo, static_tree):
            tools.stats.skipped_nearby += 1
            continue

        # -- work on height and levels

        # -- LOWI year 2525: generate a 'futuristic' city of skyscrapers
        if False:
            if b.area >= 1500:
                b.levels = int(random.gauss(35, 10))  # random_number(int, 10, 60)
                b.height = float(b.levels) * _random_level_height()
            if b.area < 1500:
            # if b.area < 200. or (b.area < 500. and random.uniform(0,1) < 0.5):
                tools.stats.skipped_small += 1
                continue

        _compute_height_and_levels(b)

        # -- check area
        if not _is_large_enough(b):
            tools.stats.skipped_small += 1
            continue

        if b.height < parameters.BUILDING_MIN_HEIGHT:
            logging.verbose("Skipping small building with height < building_min_height parameter")
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
                try:
                    if str(b.tags['roof:shape']) == 'skillion' :
                        b.roof_complex = True
                except:
                    pass

            # -- no pitched roof on tall buildings
            if b.levels > parameters.BUILDING_COMPLEX_ROOFS_MAX_LEVELS:
                b.roof_complex = False
                # FIXME: roof_ACs = True

            # -- no complex roof on tiny buildings
            min_height = 0
            if "min_height" in b.tags:
                try:
                    min_height = float(b.tags['min_height'])
                except:
                    min_height = 0
            if b.height - min_height < parameters.BUILDING_COMPLEX_MIN_HEIGHT and 'roof:shape' not in b.tags:
                b.roof_complex = False

        facade_requires = []
        roof_requires = []
        
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
        try:
            if 'building:material' not in b.tags :
                if b.tags['building:part'] == "column" :
                    facade_requires.append(str('facade:building:material:stone'))
        except KeyError:
            pass
        try:
            # cleanup building:colour and use it
            if 'building:color' in b.tags and 'building:colour' not in b.tags:
                logging.warning('osm_id %i uses color instead of colour' % b.osm_id)
                b.tags['building:colour'] = b.tags['building:color']
                del(b.tags['building:color'])
            elif 'building:color' in b.tags and 'building:colour' in b.tags:
                del(b.tags['building:color'])
            facade_requires.append('facade:building:colour:'+string.lower(b.tags['building:colour']))
        except KeyError:
            pass    
        try:
            material_type = string.lower(b.tags['building:material'])
            if str(material_type) in ['stone', 'brick', 'timber_framing', 'concrete', 'glass']:
                facade_requires.append(str('facade:building:material:' + str(material_type)))
                
            # stone white default
            if str(material_type) == 'stone' and 'building:colour' not in b.tags:
                    b.tags['building:colour'] = 'white'
                    facade_requires.append(str('facade:building:colour:white'))
            try:
                # stone use for
                if str(material_type) in ['stone', 'concrete', ]:
                    try:
                        _roof_material = str(b.tags['roof:material']).lower()
                    except:
                        _roof_material = None

                    try:
                        _roof_colour = str(b.tags['roof:colour']).lower()
                    except:
                        _roof_colour = None

                    if not (_roof_colour or _roof_material):
                        b.tags['roof:material'] = str(material_type)
                        roof_requires.append('roof:material:' + str(material_type))
                        try:
                            roof_requires.append('roof:colour:' + str(b.tags['roof:colour']))
                        except:
                            pass

                    try:
                        _roof_shape = str(b.tags['roof:shape']).lower()
                    except:
                        _roof_shape = None

                    if not _roof_shape:
                        b.tags['roof:shape'] = 'flat' 
                        b.roof_type = 'flat'
                        b.roof_complex = False
            except:
                logging.warning('checking roof material')
                pass                
        except KeyError:
            pass

#
        # -- determine facade and roof textures
        logging.verbose("___find facade for building %i" % b.osm_id)
        #
        # -- find local texture if infos different from parent
        #
        if b.parent is None:
            b.facade_texture = facades.find_matching(facade_requires, b.tags, b.height, b.longest_edge_len)
        else:
            # 1 - Check if building and building parent infos are the same
            
            # 1.1 Infos about colour
            try:
                b_color = b.tags['building:colour']
            except:
                b_color = None
                
            try:
                b_parent_color = b.parent.tags['building:colour']
            except:
                b_parent_color = None
            
            # 1.2 Infos about material
            try:
                b_material = b.tags['building:material']
            except:
                b_material = None
                
            try:
                b_parent_material = b.parent.tags['building:material']
            except:
                b_parent_material = None
               
            # could extend to building:facade:material ?
        
            # 2 - If same infos use building parent facade else find new texture
            if b_color == b_parent_color and b_material == b_parent_material:
                    if b.parent.facade_texture is None:
                        b.facade_texture = facades.find_matching(facade_requires, b.parent.tags, b.height, b.longest_edge_len)
                        b.parent.facade_texture = b.facade_texture
                    else:
                        b.facade_texture = b.parent.facade_texture
            else:
                b.facade_texture = facades.find_matching(facade_requires, b.tags, b.height, b.longest_edge_len)

        if b.facade_texture:
            logging.verbose("__done" + str(b.facade_texture) + str(b.facade_texture.provides))
        else:
            logging.verbose("__done None")
        
        if not b.facade_texture:
            tools.stats.skipped_texture += 1
            logging.info("Skipping building OsmID %d (no matching facade texture)" % b.osm_id)
            continue
        if b.longest_edge_len > b.facade_texture.width_max:
            logging.error("OsmID : %d b.longest_edge_len <= b.facade_texture.width_max" % b.osm_id)
            continue
        # print "long", b.longest_edge_len, b.facade_texture.width_max, str(b.facade_texture)
        #
        # roof search
        #
        roof_requires.extend(copy.copy(b.facade_texture.requires))
        
        if b.roof_complex:
            roof_requires.append('compat:roof-pitched')
        else:
            roof_requires.append('compat:roof-flat')

        try:
            if 'roof:material' in b.tags:
                if str(b.tags['roof:material']) in ['roof_tiles', 'copper', 'glass', 'grass', 'metal', 'concrete', 'stone', 'slate', ]:
                    roof_requires.append(str('roof:material:') + str(b.tags['roof:material']))
            
        except KeyError:
            pass
            
        try:
            roof_requires.append('roof:colour:' + str(b.tags['roof:colour']))
        except KeyError:
            pass

        # force use of default roof texture, don't want too weird things
        if ('roof:material' not in b.tags) and ('roof:color' not in b.tags) and ('roof:colour' not in b.tags):
            roof_requires.append(str('roof:default'))

        roof_requires = list(set(roof_requires))

        #
        # -- find local texture for roof if infos different from parent
        #
        logging.verbose("___find roof for building %i" % b.osm_id)
        if b.parent is None:
            b.roof_texture = roofs.find_matching(roof_requires)
            if not b.roof_texture:
                tools.stats.skipped_texture += 1
                logging.warn("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(roof_requires)))
                continue
        else:
            # 1 - Check if building and building parent infos are the same
            
            # 1.1 Infos about colour
            try:
                r_color = b.tags['roof:colour']
            except:
                r_color = None
                
            try:
                r_parent_color = b.parent.tags['roof:colour']
            except:
                r_parent_color = None
            
            # 1.2 Infos about material
            try:
                r_material = b.tags['roof:material']
            except:
                r_material = None
                
            try:
                r_parent_material = b.parent.tags['roof:material']
            except:
                r_parent_material = None


            #
            # Special for stone
            #
            if (r_material == 'stone') and ( r_color is None):
                # take colour of building 
                try:
                    if b.tags['building:material'] == 'stone':
                        r_color = b.tags['building:colour']
                except:
                    pass
                    
                # try parent
                if not r_color:
                    try:
                        if b.parent.tags['building:material'] == 'stone':
                            r_color = b.parent.tags['building:colour']
                    except:
                        r_color = 'white'
                        
                b.tags['roof:colour'] = r_color


            # 2 - If same infos use building parent facade else find new texture
            if r_color == r_parent_color and r_material == r_parent_material:
                if b.parent.roof_texture is None:
                    b.roof_texture = roofs.find_matching(roof_requires)
                    if not b.roof_texture:
                        tools.stats.skipped_texture += 1
                        logging.warn("WARNING: no matching texture for OsmID %d <%s>" % (b.osm_id, str(roof_requires)))
                        continue
                    b.parent.roof_texture = b.roof_texture
                else:
                    b.roof_texture = b.parent.roof_texture
            else :
                b.roof_texture = roofs.find_matching(roof_requires)
                if not b.roof_texture:
                    tools.stats.skipped_texture += 1
                    logging.warn("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(roof_requires)))
                    continue
        
        if b.roof_texture:
            logging.verbose("__done" + str(b.roof_texture) + str(b.roof_texture.provides))

        else:
            tools.stats.skipped_texture += 1
            logging.warn("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(roof_requires)))
            continue

        # -- finally: append building to new list
        new_buildings.append(b)

    return new_buildings


def _write_and_count_vert(out, b, elev, offset, tile_elev):
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

    z = b.ground_elev - 0.1
    try:
        z -= b.correct_ground  # FIXME Rick
    except:
        pass
    
    try:
        if 'min_height' in b.tags:
            min_height = float(b.tags['min_height'])
            z = b.ground_elev + min_height
    except:
        logging.warning("Error reading min_height for building" + b.osm_id)
        pass

    # ground nodes        
    for x in b.X:
        #z = b.ground_elev - 1
        out.node(-x[1], z, -x[0])
    # under the roof nodes
    if b.roof_type == 'skillion':
        # skillion       
        #           __ -+ 
        #     __-+--    |
        #  +--          |
        #  |            |
        #  +-----+------+
        #
        if b.roof_height_X:
            for i in range(len(b.X)):
                out.node(-b.X[i][1], b.ground_elev + b.height - b.roof_height + b.roof_height_X[i], -b.X[i][0])
    else:
        # others roofs
        #  
        #  +-----+------+
        #  |            |
        #  +-----+------+
        #
        for x in b.X:
            out.node(-x[1], b.ground_elev + b.height - b.roof_height, -x[0])
    b.ceiling = b.ground_elev + b.height
# ----


def _write_ground(out, b, elev):  # not used anywhere
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


def _write_ring(out, b, ring, v0, texture, tex_y0, tex_y1):
    tex_y0 = texture.y(tex_y0)  # -- to atlas coordinates
    tex_y1_input = tex_y1
    tex_y1 = texture.y(tex_y1)

    nnodes_ring = len(ring.coords) - 1
    v1 = v0 + nnodes_ring
    
    # print "v0 %i v1 %i lenX %i" % (v0, v1, len(b.lenX))
    for ioff in range(0, v1-v0):  # range(0, v1-v0-1):
        i = v0 + ioff
        if False:
            tex_x1 = texture.x(b.lenX[i] / texture.h_size_meters)  # -- simply repeat texture to fit length
        else:
            ipp = i+1 if ioff < v1-v0-1 else v0
            # FIXME: respect facade texture split_h
            # FIXME: there is a nan in textures.h_splits of tex/facade_modern36x36_12
            a = b.lenX[i] / texture.h_size_meters
            ia = int(a)
            frac = a - ia
            tex_x1 = texture.x(texture.closest_h_match(frac) + ia)
            if texture.v_can_repeat:
                if not (tex_x1 <= 1.):
                    logging.debug('FIXME: v_can_repeat: need to check in analyse')

            if b.roof_type == 'skillion':
                tex_y12 = texture.y((b.height - b.roof_height + b.roof_height_X[i])/b.height * tex_y1_input)
                tex_y11 = texture.y((b.height - b.roof_height + b.roof_height_X[ipp])/b.height * tex_y1_input)
            else:
                tex_y12 = tex_y1
                tex_y11 = tex_y1

        tex_x0 = texture.x(0)
        # compute indices to handle closing wall
        j = i + b.first_node
        jpp = ipp + b.first_node  

        out.face([ (j                       , tex_x0, tex_y0),
                   (jpp                     , tex_x1, tex_y0),
                   (jpp   + b._nnodes_ground, tex_x1, tex_y11),
                   (j +     b._nnodes_ground, tex_x0, tex_y12) ],
                 swap_uv=texture.v_can_repeat)     
    return v1


def write(ac_file_name, buildings, elev, tile_elev, transform, offset):
    """now actually write buildings of one LOD for given tile.
       While writing, accumulate some statistics
       (totals stored in global stats object, individually also in building)
       offset accounts for cluster center
       - all LOD in one file. Plus roofs. One Object per LOD
    """
    ac = ac3d.File(stats=tools.stats)
    LOD_objects = list()
    LOD_objects.append(ac.new_object('LOD_bare', tm.atlas_file_name + '.png'))
    LOD_objects.append(ac.new_object('LOD_rough', tm.atlas_file_name + '.png'))
    LOD_objects.append(ac.new_object('LOD_detail', tm.atlas_file_name + '.png'))

    global nb  # FIXME: still need this?

    #
    # get local medium ground elevation for each building
    #
    for ib, b in enumerate(buildings):
        b.set_ground_elev(elev, tile_elev)
    
    #
    # Exchange informations
    #
    for ib, b in enumerate(buildings):
        if b.parent:
            if not b.parent.ground_elev:
                b.parent.set_ground_elev(elev, tile_elev)

            b.ground_elev_min = min(b.parent.ground_elev, b.ground_elev)
            b.ground_elev_max = max(b.parent.ground_elev, b.ground_elev)
            
            b.ground_elev = b.ground_elev_min
            
            if b.parent.children:
                for child in b.parent.children:
                    if not child.ground_elev:
                        child.set_ground_elev(elev, tile_elev)
                            
                for child in b.parent.children:
                    b.ground_elev_min = min(child.ground_elev_min, b.ground_elev)
                    b.ground_elev_max = max(child.ground_elev_max, b.ground_elev)
                    
                b.ground_elev = b.ground_elev_min
                    
                for child in b.parent.children:
                    child.ground_elev = b.ground_elev
        
        if b.children:
            for child in b.parent.children:
                if not child.ground_elev:
                    child.set_ground_elev(elev, tile_elev)
            
            for child in b.children:
                b.ground_elev_min = min(child.ground_elev_min, b.ground_elev)
                b.ground_elev_max = max(child.ground_elev_max, b.ground_elev)
                
            b.ground_evel = b.ground_elev_min
                
            for child in b.children:
                child.ground_elev = b.ground_elev
                
        try:
            b.ground_elev = float(b.ground_elev)
        except:
            logging.fatal("non float elevation for building %" % b.osm_id)
            exit(1)
    
    #
    # Correct height
    #
    for ib, b in enumerate(buildings):
        autocorrect = True
        try:
            b.ground_elev += b.correct_ground
            autocorrect = False
        except:
            try:
                b.ground_elev += b.parent.correct_ground
                autocorrect = False
            except:
                pass
                
        # auto-correct
        if autocorrect:
            if b.children:
                ground_elev_max = b.ground_elev_max  # max( [ child.ground_elev_max for child in b.children ] )
                min_roof = min([child.height - child.roof_height for child in b.children])
            
                if ground_elev_max > (min_roof - 2):
                    b.correct_ground = ground_elev_max - min_roof
                    b.ground_elev = ground_elev_max
                    
                    for child in b.children:
                        child.correct_ground = b.correct_ground
                        child.ground_elev = b.ground_elev
                
            elif b.ground_elev_max > (b.height - b.roof_height - 2):
                b.correct_ground = b.ground_elev_max - b.ground_elev_min
                b.ground_elev = b.ground_elev_max

    for ib, b in enumerate(buildings):
        tools.progress(ib, len(buildings))
        out = LOD_objects[b.LOD]

        _compute_roof_height(b, max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
        
        _write_and_count_vert(out, b, elev, offset, tile_elev)

        nb += 1
#        if nb % 70 == 0: print nb
#        else: sys.stdout.write(".")

        b.ac_name = "b%i" % nb

#        if (not no_roof) and (not b.roof_complex): nsurf += 1 # -- because roof will be part of base model

        tex_y0, tex_y1 = _check_height(b.height, b.facade_texture)

        if b.facade_texture != 'wall_no':
            _write_ring(out, b, b.polygon.exterior, 0, b.facade_texture, tex_y0, tex_y1)
            v0 = b.nnodes_outer
            for inner in b.polygon.interiors:
                v0 = _write_ring(out, b, inner, v0, b.facade_texture, tex_y0, tex_y1)

        if not parameters.EXPERIMENTAL_INNER and len(b.polygon.interiors) > 1:
            raise NotImplementedError("Can't yet handle relations with more than one inner way")

        if not b.roof_complex:
            if b.roof_type == 'skillion':
                roofs.separate_skillion2(out, b, b.X, max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
            elif b.roof_type in ['pyramidal', 'dome', ]:
                roofs.separate_pyramidal(out, b, b.X)
            else:
                roofs.flat(out, b, b.X)

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
                if b.roof_type == 'skillion':
                    roofs.separate_skillion2(out, b, b.X, max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
                elif b.roof_type in ['pyramidal', 'dome']:
                    roofs.separate_pyramidal(out, b, b.X)
                else:
                    s = myskeleton.myskel(out, b, offset_xy=offset,
                                          offset_z=b.ground_elev + b.height - b.roof_height,
                                        max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
                    if s:
                        tools.stats.have_complex_roof += 1

                    else:  # -- fall back to flat roof
                        roofs.flat(out, b, b.X)
                    # FIXME: move to analyse. If we fall back, don't require separate LOD
            # -- pitched roof for exactly 4 ground nodes
            else:
                max_height = b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO
                if b.roof_type == 'gabled' or b.roof_type == 'half-hipped':
                    roofs.separate_gable(out, b, b.X, max_height=max_height)
                elif b.roof_type == 'hipped':
                    roofs.separate_hipped(out, b, b.X, max_height=max_height)
                elif b.roof_type in ['pyramidal', 'dome']:
                    roofs.separate_pyramidal(out, b, b.X)
                elif b.roof_type == 'skillion':
                    roofs.separate_skillion2(out, b, b.X, max_height=max_height)
                elif b.roof_type == 'flat':
                    roofs.flat(out, b, b.X)
                else:
                    logging.debug("FIXME simple rooftype %s unsupported ", b.roof_type)
                    roofs.flat(out, b, b.X)
            # out_surf.write("kids 0\n")

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
