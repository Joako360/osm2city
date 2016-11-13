# -*- coding: utf-8 -*-
"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""

import copy
import logging
import os
import random
import re
from math import sin, cos, radians, tan, sqrt, pi
from typing import List, Dict, Optional

import myskeleton
import numpy as np
from shapely import affinity
import shapely.geometry as shg
from shapely.geometry.base import BaseGeometry

import parameters
import prepare_textures as tm
import roofs
import textures.texture as tex
import tools
import utils.stg_io2
from utils import ac3d, ac3d_fast, calc_tile
from utils.coordinates import Transformation
from utils.utilities import FGElev, progress
from utils.vec2d import Vec2d
from utils.stg_io2 import STGVerbType, read_stg_entries


class Building(object):
    """Central object class.
       Holds all data relevant for a building. Coordinates, type, area, ...
       Read-only access to node coordinates via self.X[node][0|1]
    """

    def __init__(self, osm_id: int, tags: Dict[str, str], outer_ring: BaseGeometry, name: str,
                 height: float, levels: int,
                 stg_typ: STGVerbType=None, stg_hdg=None, inner_rings_list=list(), building_type='unknown',
                 roof_type: str='flat', roof_height: int=0, refs: List[int]=list()) -> None:
        self.osm_id = osm_id
        self.tags = tags
        self.refs = refs
        self.inner_rings_list = inner_rings_list
        self.name = name
        self.stg_typ = stg_typ  # STGVerbType
        self.stg_hdg = stg_hdg
        self.height = height
        self.roof_height = roof_height
        self.roof_height_X = []
        self.longest_edge_len = 0.
        self.levels = levels
        self.first_node = 0  # index of first node in final OBJECT node list
        self.anchor = Vec2d(list(outer_ring.coords[0]))
        self.facade_texture = None
        self.roof_texture = None
        self.roof_complex = False  # if False then compat:roof-flat; else compat:roof-pitched
        self.roof_requires = list()
        self.roof_type = roof_type  # str: flat, skillion, pyramidal, dome, gabled, half-hipped, hipped
        self.ceiling = 0.
        self.LOD = None  # see utils.utilities.LOD for values
        self.outer_nodes_closest = []
        if len(outer_ring.coords) > 2:
            self._set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list: self._roll_inner_nodes()
        self.building_type = building_type
        self.parent = None
        self.parent_part = []
        self.parents_parts = []
        self.cand_buildings = []
        self.children = []
        self.ground_elev = None
        self.ground_elev_min = None
        self.ground_elev_max = None
        self.is_external_model = False
        if parameters.USE_EXTERNAL_MODELS:
            if 'model3d' in tags:
                self.is_external_model = True
                self.model3d = tags['model3d']
                self.angle3d = tags['angle3d']

    def _roll_inner_nodes(self) -> None:
        """Roll inner rings such that the node closest to an outer node goes first.

           Also, create a list of outer corresponding outer nodes.
        """
        new_inner_rings_list = []
        self.outer_nodes_closest = []
        outer_nodes_avail = list(range(self.nnodes_outer))
        for inner in self.polygon.interiors:
            min_r = 1e99
            for i, node_i in enumerate(list(inner.coords)[:-1]):
                node_i = Vec2d(node_i)
                for o in outer_nodes_avail:
                    r = node_i.distance_to(Vec2d(self.X_outer[o]))
                    if r <= min_r:
                        min_r = r
                        min_i = i
                        min_o = o
            new_inner = shg.polygon.LinearRing(np.roll(np.array(inner.coords)[:-1], -min_i, axis=0))
            new_inner_rings_list.append(new_inner)
            self.outer_nodes_closest.append(min_o)
            outer_nodes_avail.remove(min_o)
        # -- sort inner rings by index of closest outer node
        yx = sorted(zip(self.outer_nodes_closest, new_inner_rings_list))
        self.inner_rings_list = [x for (y, x) in yx]
        self.outer_nodes_closest = [y for (y, x) in yx]
        self._set_polygon(self.polygon.exterior, self.inner_rings_list)

    def simplify(self, tolerance):
        original_nodes = self.nnodes_outer + len(self.X_inner)
        self.polygon = self.polygon.simplify(tolerance)
        nnodes_simplified = original_nodes - (self.nnodes_outer + len(self.X_inner))
        # FIXME: simplifiy interiors
        return nnodes_simplified

    def _set_polygon(self, outer, inner=list()) -> None:
        self.polygon = shg.Polygon(outer, inner)

    def _set_X(self, cluster_offset: Vec2d) -> None:
        """Given an cluster middle point changes all coordinates in x/y space."""
        self.X = np.array(self.X_outer + self.X_inner)
        for i in range(self._nnodes_ground):
            self.X[i, 0] -= cluster_offset.x
            self.X[i, 1] -= cluster_offset.y

    def set_ground_elev_and_offset(self, fg_elev: FGElev, cluster_elev: float, cluster_offset: Vec2d) -> None:
        """Sets the ground elevations as difference between real elevation and cluster elevation.
        Also calls method to correct x/y coordinates"""
        def local_elev(p):
            return fg_elev.probe_elev(p + cluster_offset) - cluster_elev

        self._set_X(cluster_offset)

        elevations = [local_elev(Vec2d(self.X[i])) for i in range(self._nnodes_ground)]

        self.ground_elev_min = min(elevations)
        self.ground_elev_max = max(elevations)
        self.ground_elev = self.ground_elev_min

    @property
    def X_outer(self):
        return list(self.polygon.exterior.coords)[:-1]

    @property
    def X_inner(self):
        return [coord for interior in self.polygon.interiors for coord in list(interior.coords)[:-1]]

    @property
    def _nnodes_ground(self):  # FIXME: changed behavior. Keep _ until all bugs found
        n = len(self.polygon.exterior.coords) - 1
        for item in self.polygon.interiors:
            n += len(item.coords) - 1
        return n

    @property
    def nnodes_outer(self):
        return len(self.polygon.exterior.coords) - 1

    @property
    def area(self):
        return self.polygon.area


def _random_level_height() -> float:
    """ Calculates the height for each level of a building based on place and random factor"""
    # FIXME: other places (e.g. village)
    return random.triangular(parameters.BUILDING_CITY_LEVEL_HEIGHT_LOW
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_HEIGH
                          , parameters.BUILDING_CITY_LEVEL_HEIGHT_MODE)


def _random_levels() -> int:
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
                    logging.debug("READ_AC %s" % fname)
                    ac = ac3d_fast.File(file_name=fname)
                    read_objects[fname] = ac
                                
                angle = radians(b.stg_hdg)
                rotation_matrix = np.array([[cos(angle), -sin(angle)],
                                    [sin(angle), cos(angle)]])
    
                transposed_ac_nodes = -np.delete(ac.nodes_as_array().transpose(), 1, 0)[::-1]
                transposed_ac_nodes = np.dot(rotation_matrix, transposed_ac_nodes)
                transposed_ac_nodes += b.anchor.as_array().reshape(2, 1)
                all_nodes = np.append(all_nodes, transposed_ac_nodes.transpose(), 0)
            except Exception as e:
                logging.error("Error reading %s %s" % (fname, e))

    return all_nodes


def _is_static_object_nearby(b: Building, X, static_tree) -> bool:  # X is ndarray, static_tree is KDTree
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


def _is_large_enough(b: Building) -> bool:
    """Checks whether a given building's area is too small for inclusion.
    Never drop tall buildings.
    FIXME: Exclusion might be skipped if the building touches another building (i.e. an annex)
    Returns true if the building should be included (i.e. area is big enough etc.)
    """
    if b.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS: 
        return True
    if b.parent is not None:  # Check parent if we're a part
        b = b.parent
    if b.area < parameters.BUILDING_MIN_AREA or \
       (b.area < parameters.BUILDING_REDUCE_THRESHOLD and random.uniform(0, 1) < parameters.BUILDING_REDUCE_RATE):
        return False
    return True


def _compute_height_and_levels(b: Building) -> float:
    """Determines total height (and number of levels) of a building based on
       OSM values and other logic"""
    try:
        if isinstance(b.height, int):
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


def _compute_roof_height(b: Building, max_height: float=1e99):
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
        for i in range(0, len(X)):
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

        b.roof_height_X = [roof_height*l/L for l in norms_o]
        b.roof_height = roof_height

    else:  # roof types other than skillion
        try:
            # get roof:height given by osm
            b.roof_height = float(re.sub(' .*', ' ', b.tags['roof:height'].strip()))
            
        except:
            # random roof:height
            if b.roof_type == 'flat':
                b.roof_height = 0
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
                    logging.warning("roof too high %g > %g" % (roof_height, max_height))
                    return False
                    
                b.roof_height = roof_height
    return


def decide_lod(buildings: List[Building]) -> None:
    """Decide on the building's LOD based on area, number of levels, and some randomness."""
    for b in buildings:
        r = random.uniform(0, 1)
        if r < parameters.LOD_PERCENTAGE_DETAIL:
            lod = utils.stg_io2.LOD.detail
        else:
            lod = utils.stg_io2.LOD.rough

        if b.levels > parameters.LOD_ALWAYS_ROUGH_ABOVE_LEVELS:
            lod = utils.stg_io2.LOD.rough  # tall buildings        -> rough
        if b.levels < parameters.LOD_ALWAYS_DETAIL_BELOW_LEVELS:
            lod = utils.stg_io2.LOD.detail  # small buildings       -> detail

        if b.area < parameters.LOD_ALWAYS_DETAIL_BELOW_AREA:
            lod = utils.stg_io2.LOD.detail
        elif b.area > parameters.LOD_ALWAYS_ROUGH_ABOVE_AREA:
            lod = utils.stg_io2.LOD.rough

        b.LOD = lod
        tools.stats.count_LOD(lod)


def analyse(buildings: List[Building], static_objects: Optional[List[Building]], fg_elev: FGElev,
            facade_mgr: tex.FacadeManager, roof_mgr: tex.RoofManager) -> List[Building]:
    """Analyse all buildings:
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

        if not b.is_external_model:
            try:
                tools.stats.nodes_simplified += b.simplify(parameters.BUILDING_SIMPLIFY_TOLERANCE)
                b._roll_inner_nodes()
            except Exception as reason:
                logging.warning("simplify or roll_inner_nodes failed (OSM ID %i, %s)", b.osm_id, reason)
                continue

        # -- array of local outer coordinates
        Xo = np.array(b.X_outer)

        elev_water_ok = True
        for i in range(len(Xo)):
            elev_is_solid_tuple = fg_elev.probe(Vec2d(Xo[i]))
            b.ground_elev = elev_is_solid_tuple[0]  # temporarily set - will be overwritten later
            if elev_is_solid_tuple[0] == -9999:
                logging.debug("-9999")
                tools.stats.skipped_no_elev += 1
                elev_water_ok = False
                break
            elif not elev_is_solid_tuple[1]:
                logging.debug("in water")
                elev_water_ok = False
                break
        if not elev_water_ok:
            continue

        if b.is_external_model:
            new_buildings.append(b)
            continue

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
                b._set_polygon(Xo, b.inner_rings_list)

        b.lenX = b.lenX  # FIXME: compute on the fly, or on set_polygon()?
                        #        Or is there a shapely equivalent?

        # -- check for nearby static objects
        if static_objects and _is_static_object_nearby(b, Xo, static_tree):
            tools.stats.skipped_nearby += 1
            continue

        # -- work on height and levels

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
        #      useful for
        #      - pitched roof
        #    replace by roof_type? flat  --> no separate model
        #                          gable --> separate model
        b.roof_complex = False
        if parameters.BUILDING_COMPLEX_ROOFS:
            # -- pitched, separate roof if we have 4 ground nodes and area below 1000m2
            if not b.polygon.interiors and b.area < parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA:
                if b._nnodes_ground == 4:
                    b.roof_complex = True
                if (parameters.BUILDING_SKEL_ROOFS and
                            b._nnodes_ground in range(4, parameters.BUILDING_SKEL_MAX_NODES)):
                    b.roof_complex = True
                try:
                    if str(b.tags['roof:shape']) == 'skillion':
                        b.roof_complex = True
                except:
                    pass

            # -- no complex roof on tall buildings
            if b.levels > parameters.BUILDING_COMPLEX_ROOFS_MAX_LEVELS:
                b.roof_complex = False

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

        if b.roof_complex:
            facade_requires.append('age:old')
            facade_requires.append('compat:roof-pitched')
        else:
            facade_requires.append('compat:roof-flat')
            
        try:
            if 'terminal' in b.tags['aeroway'].lower():
                facade_requires.append('facade:shape:terminal')
        except KeyError:
            pass
        try:
            if 'building:material' not in b.tags:
                if b.tags['building:part'] == "column":
                    facade_requires.append(str('facade:building:material:stone'))
        except KeyError:
            pass
        try:
            facade_requires.append('facade:building:colour:' + b.tags['building:colour'].lower())
        except KeyError:
            pass    
        try:
            material_type = b.tags['building:material'].lower()
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
                        b.roof_requires.append('roof:material:' + str(material_type))
                        try:
                            b.roof_requires.append('roof:colour:' + str(b.tags['roof:colour']))
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

        # -- determine facade and roof textures
        logging.verbose("___find facade for building %i" % b.osm_id)
        #
        # -- find local texture if infos different from parent
        #
        if b.parent is None:
            b.facade_texture = facade_mgr.find_matching_facade(facade_requires, b.tags, b.height, b.longest_edge_len)
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
                        b.facade_texture = facade_mgr.find_matching_facade(facade_requires, b.parent.tags,
                                                                           b.height, b.longest_edge_len)
                        b.parent.facade_texture = b.facade_texture
                    else:
                        b.facade_texture = b.parent.facade_texture
            else:
                b.facade_texture = facade_mgr.find_matching_facade(facade_requires, b.tags,
                                                                   b.height, b.longest_edge_len)

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

        #
        # roof search
        #
        b.roof_requires.extend(copy.copy(b.facade_texture.requires))
        
        if b.roof_complex:
            b.roof_requires.append('compat:roof-pitched')
        else:
            b.roof_requires.append('compat:roof-flat')

        # Try to match materials and colors defined in OSM with available roof textures
        try:
            if 'roof:material' in b.tags:
                if str(b.tags['roof:material']) in roof_mgr.available_materials:
                    b.roof_requires.append(str('roof:material:') + str(b.tags['roof:material']))
        except KeyError:
            pass
        try:
            b.roof_requires.append('roof:colour:' + str(b.tags['roof:colour']))
        except KeyError:
            pass

        # force use of default roof texture, don't want too weird things
        if ('roof:material' not in b.tags) and ('roof:colour' not in b.tags):
            b.roof_requires.append(str('roof:default'))

        b.roof_requires = list(set(b.roof_requires))

        # Find roof texture
        logging.verbose("___find roof for building %i" % b.osm_id)
        if b.parent is None:
            b.roof_texture = roof_mgr.find_matching_roof(b.roof_requires, b.longest_edge_len)
            if not b.roof_texture:
                tools.stats.skipped_texture += 1
                logging.warning("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(b.roof_requires)))
                continue
        else:
            # 1 - Check if building and building parent information is the same
            # 1.1 Information about colour
            try:
                r_color = b.tags['roof:colour']
            except:
                r_color = None
            try:
                r_parent_color = b.parent.tags['roof:colour']
            except:
                r_parent_color = None
            
            # 1.2 Information about material
            try:
                r_material = b.tags['roof:material']
            except:
                r_material = None
            try:
                r_parent_material = b.parent.tags['roof:material']
            except:
                r_parent_material = None

            # Special for stone
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

            # 2 - If same info use building parent facade else find new texture
            if r_color == r_parent_color and r_material == r_parent_material:
                if b.parent.roof_texture is None:
                    b.roof_texture = roof_mgr.find_matching_roof(b.roof_requires, b.longest_edge_len)
                    if not b.roof_texture:
                        tools.stats.skipped_texture += 1
                        logging.warning("WARNING: no matching texture for OsmID %d <%s>" % (b.osm_id, str(b.roof_requires)))
                        continue
                    b.parent.roof_texture = b.roof_texture
                else:
                    b.roof_texture = b.parent.roof_texture
            else:
                b.roof_texture = roof_mgr.find_matching_roof(b.roof_requires, b.longest_edge_len)
                if not b.roof_texture:
                    tools.stats.skipped_texture += 1
                    logging.warning("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(b.roof_requires)))
                    continue
        
        if b.roof_texture:
            logging.verbose("__done" + str(b.roof_texture) + str(b.roof_texture.provides))

        else:
            tools.stats.skipped_texture += 1
            logging.warning("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(b.roof_requires)))
            continue

        # -- finally: append building to new list
        new_buildings.append(b)

    return new_buildings


def _write_and_count_vert(ac_object: ac3d.Object, b: Building) -> None:
    """Write numvert tag to .ac, update stats."""

    b.first_node = ac_object.next_node_index()

    z = b.ground_elev - 0.1  # FIXME: instead maybe we should have 1 meter of "bottom" texture
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
        ac_object.node(-x[1], z, -x[0])
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
                ac_object.node(-b.X[i][1], b.ground_elev + b.height - b.roof_height + b.roof_height_X[i], -b.X[i][0])
    else:
        # others roofs
        #  
        #  +-----+------+
        #  |            |
        #  +-----+------+
        #
        for x in b.X:
            ac_object.node(-x[1], b.ground_elev + b.height - b.roof_height, -x[0])
    b.ceiling = b.ground_elev + b.height


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

        out.face([(j, tex_x0, tex_y0),
                  (jpp, tex_x1, tex_y0),
                  (jpp + b._nnodes_ground, tex_x1, tex_y11),
                  (j + b._nnodes_ground, tex_x0, tex_y12)],
                 swap_uv=texture.v_can_repeat)     
    return v1


def write(ac_file_name: str, buildings: List[Building], fg_elev: FGElev,
          cluster_elev: float, cluster_offset: Vec2d, roof_mgr: tex.RoofManager) -> None:
    """Write buildings across LOD for given tile.
       While writing, accumulate some statistics (totals stored in global stats object, individually also in building).
       Offset accounts for cluster center
       All LOD in one file. Plus roofs. One ac3d.Object per LOD
    """
    ac = ac3d.File(stats=tools.stats)
    lod_objects = list()
    lod_objects.append(ac.new_object('LOD_rough', tm.atlas_file_name + '.png'))
    lod_objects.append(ac.new_object('LOD_detail', tm.atlas_file_name + '.png'))

    number_of_buildings = 0

    # get local medium ground elevation for each building
    for ib, b in enumerate(buildings):
        b.set_ground_elev_and_offset(fg_elev, cluster_elev, cluster_offset)
    
    # Update building hierarchy information
    for ib, b in enumerate(buildings):
        if b.parent:
            if not b.parent.ground_elev:
                b.parent.set_ground_elev_and_offset(fg_elev, cluster_elev, cluster_offset)

            b.ground_elev_min = min(b.parent.ground_elev, b.ground_elev)
            b.ground_elev_max = max(b.parent.ground_elev, b.ground_elev)
            
            b.ground_elev = b.ground_elev_min
            
            if b.parent.children:
                for child in b.parent.children:
                    if not child.ground_elev:
                        child.set_ground_elev_and_offset(fg_elev, cluster_elev, cluster_offset)
                            
                for child in b.parent.children:
                    b.ground_elev_min = min(child.ground_elev_min, b.ground_elev)
                    b.ground_elev_max = max(child.ground_elev_max, b.ground_elev)
                    
                b.ground_elev = b.ground_elev_min
                    
                for child in b.parent.children:
                    child.ground_elev = b.ground_elev
        
        if b.children:
            for child in b.parent.children:
                if not child.ground_elev:
                    child.set_ground_elev_and_offset(fg_elev, cluster_elev, cluster_offset)
            
            for child in b.children:
                b.ground_elev_min = min(child.ground_elev_min, b.ground_elev)
                b.ground_elev_max = max(child.ground_elev_max, b.ground_elev)
                
            b.ground_evel = b.ground_elev_min
                
            for child in b.children:
                child.ground_elev = b.ground_elev
                
        try:
            b.ground_elev = float(b.ground_elev)
        except:
            logging.fatal("non float elevation for building %d" % b.osm_id)
            exit(1)

    # Correct height
    for ib, b in enumerate(buildings):
        auto_correct = True
        try:
            b.ground_elev += b.correct_ground
            auto_correct = False
        except:
            try:
                b.ground_elev += b.parent.correct_ground
                auto_correct = False
            except:
                pass
                
        # auto-correct
        if auto_correct:
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
        progress(ib, len(buildings))
        ac_object = lod_objects[b.LOD]

        _compute_roof_height(b, max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
        
        _write_and_count_vert(ac_object, b)

        tex_y0, tex_y1 = _check_height(b.height, b.facade_texture)

        if b.facade_texture != 'wall_no':
            _write_ring(ac_object, b, b.polygon.exterior, 0, b.facade_texture, tex_y0, tex_y1)
            v0 = b.nnodes_outer
            for inner in b.polygon.interiors:
                v0 = _write_ring(ac_object, b, inner, v0, b.facade_texture, tex_y0, tex_y1)

        if not parameters.EXPERIMENTAL_INNER and len(b.polygon.interiors) > 1:
            raise NotImplementedError("Can't yet handle relations with more than one inner way")

        if not b.roof_complex:
            roofs.flat(ac_object, b, roof_mgr)

        else:
            # -- pitched roof for > 4 ground nodes
            if b._nnodes_ground > 4 and parameters.BUILDING_SKEL_ROOFS:
                if b.roof_type == 'skillion':
                    roofs.separate_skillion(ac_object, b)
                elif b.roof_type in ['pyramidal', 'dome']:
                    roofs.separate_pyramidal(ac_object, b)
                else:
                    s = myskeleton.myskel(ac_object, b, offset_xy=cluster_offset,
                                          offset_z=b.ground_elev + b.height - b.roof_height,
                                          max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
                    if s:
                        tools.stats.have_complex_roof += 1

                    else:  # -- fall back to flat roof
                        roofs.flat(ac_object, b, roof_mgr)
            # -- pitched roof for exactly 4 ground nodes
            else:
                if b.roof_type == 'gabled' or b.roof_type == 'half-hipped':
                    roofs.separate_gable(ac_object, b)
                elif b.roof_type == 'hipped':
                    roofs.separate_hipped(ac_object, b)
                elif b.roof_type in ['pyramidal', 'dome']:
                    roofs.separate_pyramidal(ac_object, b)
                elif b.roof_type == 'skillion':
                    roofs.separate_skillion(ac_object, b)
                elif b.roof_type == 'flat':
                    roofs.flat(ac_object, b, roof_mgr)
                else:
                    logging.debug("FIXME simple roof type %s unsupported ", b.roof_type)
                    roofs.flat(ac_object, b, roof_mgr)

    ac.write(ac_file_name)


def map_building_type(tags) -> str:
    if 'building' in tags and not tags['building'] == 'yes':
        return tags['building']
    return 'unknown'


def read_buildings_from_stg_entries(path: str, stg_fname: str, our_magic: str) -> List[Building]:
    """Same as read_stg_entries, but returns osm2city.Building objects"""
    stg_entries = read_stg_entries(path + stg_fname, parameters.OVERLAP_CHECK_CONSIDER_SHARED, our_magic)
    building_objs = list()
    for entry in stg_entries:
        point = shg.Point(tools.transform.toLocal((entry.lon, entry.lat)))
        building_objs.append(Building(osm_id=-1, tags=dict(), outer_ring=point,
                                      name=entry.get_obj_path_and_name(),
                                      height=0, levels=0, stg_typ=entry.verb_type,
                                      stg_hdg=entry.hdg))
    return building_objs


# ======================= New overlap detection ==========================

def overlap_check_convex_hull(buildings: List[Building], my_coord_transformation: Transformation) -> List[Building]:
    """Checks for all buildings whether their polygon intersects with a static or shared object's convex hull.
    Be aware that method 'analyse' also makes overlap checks based on circles around static/shared
    object's anchor point.
    """
    boundaries = _create_static_obj_boundaries(my_coord_transformation)

    cleared_buildings = list()

    for building in buildings:
        is_intersecting = False
        for key, value in boundaries.items():
            if value.intersects(building.polygon):
                is_intersecting = True
                tools.stats.skipped_nearby += 1
                if building.name is None or len(building.name) == 0:
                    logging.info("Convex hull of object '%s' is intersecting. Skipping building with osm_id %d",
                                 key, building.osm_id)
                else:
                    logging.info("Convex hull of object '%s' is intersecting. Skipping building '%s' (osm_id %d)",
                                 key, building.name, building.osm_id)
                break
        if not is_intersecting:
            cleared_buildings.append(building)
    return cleared_buildings


def _parse_ac_file_name(xml_string: str) -> str:
    """Finds the corresponding ac-file in an xml-file"""
    try:
        x1 = xml_string.index("<path>")
        x2 = xml_string.index("</path>", x1)
    except ValueError as e:
        raise e
    ac_file_name = (xml_string[x1+6:x2]).strip()
    return ac_file_name


def _extract_boundary(ac_filename: str) -> shg.Polygon:
    """Reads an ac-file and constructs a convex hull as a proxy to the real boundary.
    No attempt is made to follow rotations and translations.
    Returns a tuple (x_min, y_min, x_max, y_max) in meters."""
    numvert = 0
    points = list()
    try:
        with open(ac_filename, 'r') as my_file:
            for my_line in my_file:
                if 0 == my_line.find("numvert"):
                    numvert = int(my_line.split()[1])
                elif numvert > 0:
                    vertex_values = my_line.split()
                    # minus factor in y-axis due to ac3d coordinate system. Switch of y_min and y_max for same reason
                    points.append((float(vertex_values[0]), -1 * float(vertex_values[2])))
                    numvert -= 1
    except IOError as e:
        raise e

    hull_polygon = shg.MultiPoint(points).convex_hull
    return hull_polygon


def _create_static_obj_boundaries(my_coord_transformation: Transformation) -> Dict[str, shg.Polygon]:
    """
    Finds all static objects referenced in stg-files within the scenery boundaries and returns them as a list of
    Shapely polygon objects (convex hull of all points in ac-files) in the local x/y coordinate system.
    """
    boundaries = dict()
    stg_files = calc_tile.get_stg_files_in_boundary(parameters.BOUNDARY_WEST, parameters.BOUNDARY_SOUTH
                                                    , parameters.BOUNDARY_EAST, parameters.BOUNDARY_NORTH
                                                    , parameters.PATH_TO_SCENERY)
    for filename in stg_files:
        stg_entries = read_stg_entries(filename, parameters.OVERLAP_CHECK_CONSIDER_SHARED)
        for entry in stg_entries:
            if entry.verb_type in [STGVerbType.object_static, STGVerbType.object_shared]:
                try:
                    ac_filename = entry.obj_filename
                    if ac_filename.endswith(".xml"):
                        with open(entry.get_obj_path_and_name(), 'r') as f:
                            xml_data = f.read()
                            ac_filename = _parse_ac_file_name(xml_data)
                            entry.overwrite_filename(ac_filename)
                    boundary_polygon = _extract_boundary(entry.get_obj_path_and_name())
                    rotated_polygon = affinity.rotate(boundary_polygon, entry.hdg - 90, (0, 0))
                    x_y_point = my_coord_transformation.toLocal(Vec2d(entry.lon, entry.lat))
                    translated_polygon = affinity.translate(rotated_polygon, x_y_point[0], x_y_point[1])
                    if entry.verb_type is STGVerbType.object_static and parameters.OVERLAP_CHECK_CH_BUFFER_STATIC > 0.01:
                        boundaries[ac_filename] = translated_polygon.buffer(
                            parameters.OVERLAP_CHECK_CH_BUFFER_STATIC, shg.CAP_STYLE.square)
                    elif entry.verb_type is STGVerbType.object_shared and parameters.OVERLAP_CHECK_CH_BUFFER_SHARED > 0.01:
                        boundaries[ac_filename] = translated_polygon.buffer(
                            parameters.OVERLAP_CHECK_CH_BUFFER_SHARED, shg.CAP_STYLE.square)
                    else:
                        boundaries[ac_filename] = translated_polygon
                except IOError as reason:
                    logging.warning("Ignoring unreadable stg_entry %s", reason)

    return boundaries
