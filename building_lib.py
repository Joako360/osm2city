"""
Created on Thu Feb 28 23:18:08 2013

@author: tom
"""

import copy
import logging
import random
from math import sin, cos, tan, sqrt, pi
from typing import List, Dict

import myskeleton
import numpy as np
import shapely.geometry as shg
from shapely.geometry.base import BaseGeometry
from shapely.geos import TopologicalError

import parameters
import prepare_textures as tm
import roofs
import textures.texture as tex
import utils.stg_io2
from utils import ac3d
import utils.osmparser
from utils.utilities import FGElev, progress, Stats
from utils.vec2d import Vec2d
from utils.stg_io2 import STGVerbType


class BuildingParent(object):
    """The parent of buildings that are part of a Simple3D building.
    Mostly used to coordinate textures for facades and roofs.
    The parts determine the common textures by a simple: the first to set the values wins the race.
    """
    def __init__(self, osm_id: int) -> None:
        self.osm_id = osm_id
        self.children = list()  # pointers to Building objects. Those building objects point back in self.parent

    def _sanitize_children(self):
        """Make sure all children have a reference to parent - otherwise delete them.
        They might have been removed during building_lib.analyse(...)."""
        for child in reversed(self.children):
            if child.parent is None:
                self.children.remove(child)
        if len(self.children) == 1:
            self.children[0].parent = None
            self.children = list()

    def align_textures_children(self) -> None:
        """Aligns the facade and roof textures for all the children belonging to this parent.
        Unless there are deviations in the use of tags, then the textures of the child with
        the largest longest_edge_len is chosen.
        It might be best if the one part with the most clear tags would win, but [A] it is highly probable
        that all children have similar tags (but maybe different values), and [B] it is safest to choose
        a texture matching the longest edge.
        If there is at least one deviation, then all parts keep their textures.
        """
        self._sanitize_children()
        if len(self.children) == 0:  # might be sanitize_children() has removed them all
            return

        default_child = None
        difference_found = False
        building_colour = None
        building_material = None
        building_facade_material = None
        for child in self.children:
            if default_child is None:
                default_child = child
                if 'building:colour' in child.tags:
                    building_colour = child.tags['building:colour']
                if 'building:material' in child.tags:
                    building_material = child.tags['building:material']
                if 'building:facade:material' in child.tags:
                    building_facade_material = child.tags['building:facade:material']
            else:
                if child.longest_edge_len > default_child.longest_edge_len:
                    default_child = child
                if 'building:colour' in child.tags:
                    if building_colour is None:
                        difference_found = True
                        break
                    elif building_colour != child.tags['building:colour']:
                        difference_found = True
                        break
                if 'building:material' in child.tags:
                    if building_material is None:
                        difference_found = True
                        break
                    elif building_material != child.tags['building:material']:
                        difference_found = True
                        break
                if 'building:facade:material' in child.tags:
                    if building_facade_material is None:
                        difference_found = True
                        break
                    elif building_facade_material != child.tags['building:facade:material']:
                        difference_found = True
                        break

        if difference_found:  # nothing to do - keep as is
            return

        # apply same textures to all children
        for child in self.children:
            child.facade_texture = default_child.facade_texture
            child.roof_texture = default_child.roof_texture


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
        if self.inner_rings_list:
            self.roll_inner_nodes()
        self.building_type = building_type
        self.parent = None  # BuildingParent if available
        self.ground_elev = None
        self.ground_elev_min = None
        self.ground_elev_max = None
        self.is_external_model = False
        if parameters.USE_EXTERNAL_MODELS:
            if 'model3d' in tags:
                self.is_external_model = True
                self.model3d = tags['model3d']
                self.angle3d = tags['angle3d']

    def roll_inner_nodes(self) -> None:
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
        # FIXME: simplify interiors
        return nnodes_simplified

    def _set_polygon(self, outer: shg.LinearRing, inner: List[shg.LinearRing]=list()) -> None:
        self.polygon = shg.Polygon(outer, inner)

    def _set_X(self, cluster_offset: Vec2d) -> None:
        """Given an cluster middle point changes all coordinates in x/y space."""
        self.X = np.array(self.X_outer + self.X_inner)
        for i in range(self.nnodes_ground):
            self.X[i, 0] -= cluster_offset.x
            self.X[i, 1] -= cluster_offset.y

    def set_ground_elev_and_offset(self, fg_elev: FGElev, cluster_elev: float, cluster_offset: Vec2d) -> None:
        """Sets the ground elevations as difference between real elevation and cluster elevation.
        Also calls method to correct x/y coordinates"""
        def local_elev(p):
            return fg_elev.probe_elev(p + cluster_offset) - cluster_elev

        self._set_X(cluster_offset)

        elevations = [local_elev(Vec2d(self.X[i])) for i in range(self.nnodes_ground)]

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
    def nnodes_ground(self):  # FIXME: changed behavior. Keep _ until all bugs found
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
    return random.triangular(parameters.BUILDING_CITY_LEVEL_HEIGHT_LOW,
                             parameters.BUILDING_CITY_LEVEL_HEIGHT_HEIGH,
                             parameters.BUILDING_CITY_LEVEL_HEIGHT_MODE)


def _random_levels() -> int:
    """ Calculates the number of building levels based on place and random factor"""
    # FIXME: other places
    return int(round(random.triangular(parameters.BUILDING_CITY_LEVELS_LOW,
                                       parameters.BUILDING_CITY_LEVELS_HEIGH,
                                       parameters.BUILDING_CITY_LEVELS_MODE)))


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


def _is_large_enough(b: Building) -> bool:
    """Checks whether a given building's area is too small for inclusion.
    Never drop tall buildings.
    FIXME: Exclusion might be skipped if the building touches another building (i.e. an annex)
    Returns true if the building should be included (i.e. area is big enough etc.)
    """
    if b.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS: 
        return True
    if b.inner_rings_list:  # never skip a building with inner rings
        return True
    if b.parent is not None:  # if we have a parent, then keep always
        return True
    if b.area < parameters.BUILDING_MIN_AREA or \
       (b.area < parameters.BUILDING_REDUCE_THRESHOLD and random.uniform(0, 1) < parameters.BUILDING_REDUCE_RATE):
        return False
    return True


def _compute_height_and_levels(b: Building) -> None:
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
            roof_height = utils.osmparser.parse_length(b.tags['roof:height'])
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
            angle00 = pi/2. - (((utils.osmparser.parse_direction(b.tags['roof:slope:direction'])) % 360.) * pi / 180.)
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
            b.roof_height = utils.osmparser.parse_length(b.tags['roof:height'])
            
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


def decide_lod(buildings: List[Building], stats: Stats) -> None:
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
        stats.count_LOD(lod)


def analyse(buildings: List[Building], fg_elev: FGElev,
            facade_mgr: tex.FacadeManager, roof_mgr: tex.RoofManager, stats: Stats) -> List[Building]:
    """Analyse all buildings:
    - calculate area
    - location clash with stg static models? drop building
    - analyze surrounding: similar shaped buildings nearby? will get same texture
    - set building type, roof type etc

    On entry, we're in global coordinates. Change to local coordinates.
    """
    new_buildings = []
    building_parents = dict()
    for b in buildings:
        building_parent = b.parent
        b.parent = None  # will reset again if actually all is ok at end

        # am Anfang Geometrieanalyse
        # - ort: urban, residential, rural
        # - region: europe, asia...
        # - levels: 1-2, 3-5, hi-rise
        # - roof-shape: flat, gable
        # - age: old, modern

        # - facade raussuchen

        if 'building' in b.tags:  # not if 'building:part'
            # temporarily exclude greenhouses / glasshouses
            if b.tags['building'] in ['glasshouse', 'greenhouse'] or (
                            'amenity' in b.tags and b.tags['amenity'] in ['glasshouse', 'greenhouse']):
                logging.debug("Excluded greenhouse with osm_id={}".format(b.osm_id))
                continue
            # exclude storage tanks -> pylons.py
            if b.tags['building'] in ['storage_tank', 'tank'] or (
                    'man_made' in b.tags and b.tags['man_made'] in ['storage_tank', 'tank']):
                logging.debug("Excluded storage tank with osm_id={}".format(b.osm_id))
                continue
        b.mat = 0
        b.roof_mat = 0

        # -- get geometry right
        #    - simplify
        #    - compute edge lengths

        if not b.is_external_model:
            try:
                # FIXME RICK stats.nodes_simplified += b.simplify(parameters.BUILDING_SIMPLIFY_TOLERANCE)
                b.roll_inner_nodes()
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
                stats.skipped_no_elev += 1
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

        stats.nodes_ground += b.nnodes_ground

        # -- compute edge length
        b.lenX = np.zeros((b.nnodes_ground))
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

        b.lenX = b.lenX  # FIXME: compute on the fly, or on set_polygon()? Or is there a shapely equivalent?

        # -- work on height and levels

        _compute_height_and_levels(b)

        # -- check area
        if not _is_large_enough(b):
            stats.skipped_small += 1
            continue

        if b.height < parameters.BUILDING_MIN_HEIGHT:
            logging.verbose("Skipping small building with height < building_min_height parameter")
            stats.skipped_small += 1
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
                if b.nnodes_ground == 4:
                    b.roof_complex = True
                if (parameters.BUILDING_SKEL_ROOFS and
                            b.nnodes_ground in range(4, parameters.BUILDING_SKEL_MAX_NODES)):
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
                    min_height = utils.osmparser.parse_length(b.tags['min_height'])
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

        # ****** determine facade and roof textures *******
        logging.verbose("___find facade for building %i" % b.osm_id)

        b.facade_texture = facade_mgr.find_matching_facade(facade_requires, b.tags, b.height, b.longest_edge_len, stats)
        if b.facade_texture:
            logging.verbose("__done" + str(b.facade_texture) + str(b.facade_texture.provides))
        else:
            stats.skipped_texture += 1
            logging.debug("Skipping building with osm_id %d (no matching facade texture)" % b.osm_id)
            continue
        if b.longest_edge_len > b.facade_texture.width_max:
            logging.debug("Skipping building with osm_id : %d b.longest_edge_len > b.facade_texture.width_max" % b.osm_id)
            continue

        # roof search
        if building_parent is not None:
            b.tags['roof:shape'] = 'flat'
            b.roof_type = 'flat'
            b.roof_complex = False

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
        b.roof_texture = roof_mgr.find_matching_roof(b.roof_requires, b.longest_edge_len, stats)
        if not b.roof_texture:
            stats.skipped_texture += 1
            logging.debug("WARNING: no matching roof texture for osm_id %d <%s>" % (b.osm_id, str(b.roof_requires)))
            continue

        if b.roof_texture:
            logging.verbose("__done" + str(b.roof_texture) + str(b.roof_texture.provides))

        else:
            stats.skipped_texture += 1
            logging.debug("WARNING: no matching roof texture for OsmID %d <%s>" % (b.osm_id, str(b.roof_requires)))
            continue

        # -- finally: append building to new list
        new_buildings.append(b)
        if building_parent is not None:
            b.parent = building_parent
            building_parents[building_parent.osm_id] = building_parent

    for key, parent in building_parents.items():
        parent.align_textures_children()

    return new_buildings


def _write_and_count_vert(ac_object: ac3d.Object, b: Building) -> None:
    """Write numvert tag to .ac, update stats."""

    b.first_node = ac_object.next_node_index()

    z = b.ground_elev - 0.1  # FIXME: instead maybe we should have 1 meter of "bottom" texture
    try:
        z -= b.correct_ground
    except:
        pass
    
    try:
        if 'min_height' in b.tags:
            min_height = utils.osmparser.parse_length(b.tags['min_height'])
            z = b.ground_elev + min_height
    except:
        logging.warning("Error reading min_height for building %d", b.osm_id)
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


def _write_ring(out: ac3d.Object, b, ring, v0, texture, tex_y0, tex_y1):
    tex_y0 = texture.y(tex_y0)  # -- to atlas coordinates
    tex_y1_input = tex_y1
    tex_y1 = texture.y(tex_y1)

    nnodes_ring = len(ring.coords) - 1
    v1 = v0 + nnodes_ring
    
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
                  (jpp + b.nnodes_ground, tex_x1, tex_y11),
                  (j + b.nnodes_ground, tex_x0, tex_y12)],
                 swap_uv=texture.v_can_repeat)     
    return v1


def write(ac_file_name: str, buildings: List[Building], fg_elev: FGElev,
          cluster_elev: float, cluster_offset: Vec2d, roof_mgr: tex.RoofManager, stats: Stats) -> None:
    """Write buildings across LOD for given tile.
       While writing, accumulate some statistics (totals stored in global stats object, individually also in building).
       Offset accounts for cluster center
       All LOD in one file. Plus roofs. One ac3d.Object per LOD
    """
    ac = ac3d.File(stats=stats)
    lod_objects = list()
    texture_name = tm.atlas_file_name + '.png'
    if parameters.FLAG_2017_2:
        texture_name = 'Textures/osm2city/atlas_facades.png'
    lod_objects.append(ac.new_object('LOD_rough', texture_name, default_mat_idx=ac3d.MAT_IDX_LIT))
    lod_objects.append(ac.new_object('LOD_detail', texture_name, default_mat_idx=ac3d.MAT_IDX_LIT))

    # get local medium ground elevation for each building
    for ib, b in enumerate(buildings):
        b.set_ground_elev_and_offset(fg_elev, cluster_elev, cluster_offset)
    
    # Update building hierarchy information
    for ib, b in enumerate(buildings):
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
            pass
                
        # auto-correct
        if auto_correct:
            if b.ground_elev_max > (b.height - b.roof_height - 2):
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
            roofs.flat(ac_object, b, roof_mgr, stats)

        else:
            # -- pitched roof for > 4 ground nodes
            if b.nnodes_ground > 4 and parameters.BUILDING_SKEL_ROOFS:
                if b.roof_type == 'skillion':
                    roofs.separate_skillion(ac_object, b)
                elif b.roof_type in ['pyramidal', 'dome']:
                    roofs.separate_pyramidal(ac_object, b)
                else:
                    s = myskeleton.myskel(ac_object, b, stats, offset_xy=cluster_offset,
                                          offset_z=b.ground_elev + b.height - b.roof_height,
                                          max_height=b.height * parameters.BUILDING_SKEL_MAX_HEIGHT_RATIO)
                    if s:
                        stats.have_complex_roof += 1

                    else:  # -- fall back to flat roof
                        roofs.flat(ac_object, b, roof_mgr, stats)
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
                    roofs.flat(ac_object, b, roof_mgr, stats)
                else:
                    logging.debug("FIXME simple roof type %s unsupported ", b.roof_type)
                    roofs.flat(ac_object, b, roof_mgr, stats)

    ac.write(ac_file_name)


def map_building_type(tags) -> str:
    if 'building' in tags and not tags['building'] == 'yes':
        return tags['building']
    return 'unknown'


def overlap_check_blocked_areas(buildings: List[Building], blocked_areas: List[shg.Polygon]) -> List[Building]:
    cleared_buildings = list()
    for building in buildings:
        is_intersected = False
        for blocked_area in blocked_areas:
            if building.polygon.intersects(blocked_area):
                logging.debug("Building osm_id=%d intersects with blocked area.", building.osm_id)
                is_intersected = True
                break
        if not is_intersected:
            cleared_buildings.append(building)
    return cleared_buildings


def overlap_check_convex_hull(buildings: List[Building], stg_entries: List[utils.stg_io2.STGEntry],
                              stats: Stats) -> List[Building]:
    """Checks for all buildings whether their polygon intersects with a static or shared object's convex hull.
    """
    cleared_buildings = list()

    for building in buildings:
        is_intersecting = False
        for entry in stg_entries:
            try:
                if entry.convex_hull is not None and entry.convex_hull.intersects(building.polygon):
                    is_intersecting = True
                    stats.skipped_nearby += 1
                    if building.name is None or len(building.name) == 0:
                        logging.debug("Convex hull of object '%s' is intersecting. Skipping building with osm_id %d",
                                      entry.obj_filename, building.osm_id)
                    else:
                        logging.debug("Convex hull of object '%s' is intersecting. Skipping building '%s' (osm_id %d)",
                                      entry.obj_filename, building.name, building.osm_id)
                    break
            except TopologicalError as e:
                logging.exception('Convex hull could not be checked due to topology problem - building osm_id: %d',
                                  building.osm_id)

        if not is_intersecting:
            cleared_buildings.append(building)
    return cleared_buildings
