"""
Created on Thu Feb 28 23:18:08 2013

@author: tom

Call hierarchy (as of summer 2017) - building_lib is called from building.py:

* building_lib.overlap_check_blocked_areas(...)
* building_lib.overlap_check_convex_hull(...)
* building_lib.analyse(...)
    for building in ...
        b.analyse_roof_shape(...)
        b.analyse_height_and_levels()
        b.analyse_large_enough()
        b.analyse_roof_check(...)
        b.analyse_textures()
* building_lib.decide_lod(...)
* building_lib.write(...)
    for building in ...
        b.write_to_ac(...)

"""

import copy
from enum import IntEnum, unique
import logging
import random
from math import sin, cos, tan, sqrt, pi
from typing import List, Dict, Tuple

import myskeleton
import numpy as np
import shapely.geometry as shg
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


@unique
class RoofShape(IntEnum):
    """Matches the roof:shape in OSM, see http://wiki.openstreetmap.org/wiki/Simple_3D_buildings.

    Some of the OSM types might not be directly supported and are mapped to a different type,
    which actually is supported in osm2city.

    The enumeration should match what is provided in roofs.py and referenced in _write_roof_for_ac().
    """
    flat = 0
    skillion = 1
    gabled = 2
    hipped = 3
    pyramidal = 4


def _map_osm_roof_shape(osm_roof_shape: str) -> RoofShape:
    """Maps OSM roof:shape tag to supported types in osm2city.

    See http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof_shape"""
    _shape = osm_roof_shape.strip()
    if len(_shape) == 0:
        return RoofShape.flat
    if _shape == 'flat':
        return RoofShape.flat
    if _shape == 'skillion':
        return RoofShape.skillion
    if _shape in ['gabled', 'half-hipped', 'gambrel', 'round', 'saltbox']:
        return RoofShape.gabled
    if _shape in ['hipped', 'mansard']:
        return RoofShape.hipped
    if _shape in ['pyramidal', 'dome', 'onion']:
        return RoofShape.pyramidal

    # fall back for all not directly handled OSM types
    logging.debug('Not handled roof shape found: %s. Therefore transformed to "flat".', _shape)
    return RoofShape.flat


def _random_roof_shape() -> RoofShape:
    ratio = random.uniform(0, 1)
    accumulated_ratio = parameters.BUILDING_ROOF_FLAT_RATIO
    if ratio <= accumulated_ratio:
        return RoofShape.flat
    accumulated_ratio += parameters.BUILDING_ROOF_SKILLION_RATIO
    if ratio <= accumulated_ratio:
        return RoofShape.skillion
    accumulated_ratio += parameters.BUILDING_ROOF_GABLED_RATIO
    if ratio <= accumulated_ratio:
        return RoofShape.gabled
    accumulated_ratio += parameters.BUILDING_ROOF_HIPPED_RATIO
    if ratio <= accumulated_ratio:
        return RoofShape.hipped
    else:
        return RoofShape.pyramidal


class BuildingParent(object):
    """The parent of buildings that are part of a Simple3D building.
    Mostly used to coordinate textures for facades and roofs.
    The parts determine the common textures by a simple rule: the first to set the values wins the race.
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
                if child.longest_edge_length > default_child.longest_edge_length:
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

    def __init__(self, osm_id: int, tags: Dict[str, str], outer_ring: shg.LinearRing, name: str,
                 stg_typ: STGVerbType=None, stg_hdg=None, inner_rings_list=list(),
                 refs: List[int]=list()) -> None:
        # set during init and methods called by init
        self.osm_id = osm_id
        self.tags = tags
        self.is_external_model = False
        if parameters.USE_EXTERNAL_MODELS:
            if 'model3d' in tags:
                self.is_external_model = True
                self.model3d = tags['model3d']
                self.angle3d = tags['angle3d']
        self.name = name
        self.stg_typ = stg_typ  # STGVerbType
        self.stg_hdg = stg_hdg
        self.building_type = _map_building_type(self.tags)

        # For definition of '*height' see method analyse_height_and_levels(..)
        self.body_height = 0.0
        self.levels = 0
        self.min_height = 0.0  # the height over ground relative to ground_elev of the facade. See min_height in OSM
        self.roof_shape = RoofShape.flat
        self.roof_height = 0.0  # the height of the roof (0 if flat), not the elevation over ground of the roof

        # set during method called by init(...) through self.update_geometry and related sub-calls
        self.refs = None
        self.inner_rings_list = None
        self.outer_nodes_closest = None
        self.anchor = None
        self.polygon = None
        self.update_geometry(outer_ring, inner_rings_list, refs)

        # set in buildings.py for building relations prior to building_lib.analyse(...)
        # - from building._process_simple_3d_building(...)
        self.parent = None  # BuildingParent if available
        # - from building._process_lonely_building_parts(...)
        self.pseudo_parents = list()  # list of Building: only set for building:part without a real parent

        # set after init(...)
        self.roof_height_x = []  # roof height at ground-node x - only set and used for type=skillion
        self.edge_length_x = None  # numpy array of side length between ground-node X and X+1
        self.index_first_node_in_ac3d_obj = 0  # index of first node in final OBJECT node list
        self.facade_texture = None
        self.roof_texture = None
        self.roof_requires = list()
        self.LOD = None  # see utils.utilities.LOD for values

        self.ground_elev = 0.0  # the lowest elevation over sea of any point in the outer ring of the building

    def update_geometry(self, outer_ring: shg.LinearRing, inner_rings_list=list(), refs: List[int]=list()) -> None:
        self.refs = refs
        self.inner_rings_list = inner_rings_list
        self.outer_nodes_closest = []
        self.anchor = Vec2d(list(outer_ring.coords[0]))
        if len(outer_ring.coords) > 2:
            self._set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list:
            self.roll_inner_nodes()

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

    def set_ground_elev_and_offset(self, cluster_elev: float, cluster_offset: Vec2d) -> None:
        """Sets the ground elevations as difference between real elevation and cluster elevation.
        Also translates x/y coordinates"""
        self._set_X(cluster_offset)
        self.ground_elev -= cluster_elev

    @property
    def roof_complex(self) -> bool:
        """Proxy to see whether the roof is flat or not.
        Skillion is also kind of flat, but is not horisontal and therfore would also return false."""
        if self.roof_shape is RoofShape.flat:
            return False
        return True

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

    @property
    def circumference(self):
        return self.polygon.length

    @property
    def longest_edge_length(self):
        return max(self.edge_length_x)

    @property
    def building_height(self) -> float:
        """ The total height of the building corresponding to the OSM definition of 'height' resp. 'building:height'"""
        return self.min_height + self.body_height + self.roof_height

    @property
    def top_of_roof_above_sea_level(self) -> float:
        """Top of the building's roof above main sea level"""
        return self.ground_elev + self.building_height

    @property
    def beginning_of_roof_above_sea_level(self) -> float:
        """The point above main sea level, where the roof starts"""
        return self.ground_elev + self.min_height + self.body_height

    def _analyse_facade_roof_requirements(self) -> List[str]:
        """Determines the requirements for facade (textures) and depending on requirements found updates roof reqs."""
        facade_requires = []

        if self.roof_complex:
            facade_requires.append('age:old')
            facade_requires.append('compat:roof-pitched')
        else:
            facade_requires.append('compat:roof-flat')

        try:
            if 'terminal' in self.tags['aeroway'].lower():
                facade_requires.append('facade:shape:terminal')
        except KeyError:
            pass
        try:
            if 'building:material' not in self.tags:
                if self.tags['building:part'] == "column":
                    facade_requires.append(str('facade:building:material:stone'))
        except KeyError:
            pass
        try:
            facade_requires.append('facade:building:colour:' + self.tags['building:colour'].lower())
        except KeyError:
            pass
        try:
            material_type = self.tags['building:material'].lower()
            if str(material_type) in ['stone', 'brick', 'timber_framing', 'concrete', 'glass']:
                facade_requires.append(str('facade:building:material:' + str(material_type)))

            # stone white default
            if str(material_type) == 'stone' and 'building:colour' not in self.tags:
                self.tags['building:colour'] = 'white'
                facade_requires.append(str('facade:building:colour:white'))
            try:
                # stone use for
                if str(material_type) in ['stone', 'concrete', ]:
                    try:
                        _roof_material = str(self.tags['roof:material']).lower()
                    except KeyError:
                        _roof_material = None

                    try:
                        _roof_colour = str(self.tags['roof:colour']).lower()
                    except KeyError:
                        _roof_colour = None

                    if not (_roof_colour or _roof_material):
                        self.tags['roof:material'] = str(material_type)
                        self.roof_requires.append('roof:material:' + str(material_type))
                        try:
                            self.roof_requires.append('roof:colour:' + str(self.tags['roof:colour']))
                        except KeyError:
                            pass
            except:
                logging.warning('checking roof material')
                pass
        except KeyError:
            pass

        return facade_requires

    def analyse_textures(self, facade_mgr: tex.FacadeManager, roof_mgr: tex.RoofManager, stats: Stats) -> bool:
        """Determine the facade and roof textures. Return False if anomaly is found."""
        facade_requires = self._analyse_facade_roof_requirements()
        longest_edge_length = self.longest_edge_length  # keep for performance
        self.facade_texture = facade_mgr.find_matching_facade(facade_requires, self.tags, self.body_height,
                                                              longest_edge_length, stats)
        if self.facade_texture:
            logging.debug('Facade texture for osm_id {}: {} - {}'.format(self.osm_id, str(self.facade_texture),
                                                                         str(self.facade_texture.provides)))
        else:
            stats.skipped_texture += 1
            logging.debug("Skipping building with osm_id %d: (no matching facade texture)" % self.osm_id)
            return False
        if longest_edge_length > self.facade_texture.width_max:
            logging.debug(
                "Skipping building with osm_id %d: longest_edge_len > b.facade_texture.width_max" % self.osm_id)
            return False

        self.roof_requires.extend(copy.copy(self.facade_texture.requires))

        if self.roof_complex:
            self.roof_requires.append('compat:roof-pitched')
        else:
            self.roof_requires.append('compat:roof-flat')

        # Try to match materials and colors defined in OSM with available roof textures
        try:
            if 'roof:material' in self.tags:
                if str(self.tags['roof:material']) in roof_mgr.available_materials:
                    self.roof_requires.append(str('roof:material:') + str(self.tags['roof:material']))
        except KeyError:
            pass
        try:
            self.roof_requires.append('roof:colour:' + str(self.tags['roof:colour']))
        except KeyError:
            pass

        # force use of default roof texture, don't want too weird things
        if ('roof:material' not in self.tags) and ('roof:colour' not in self.tags):
            self.roof_requires.append(str('roof:default'))

        self.roof_requires = list(set(self.roof_requires))

        # Find roof texture
        logging.debug("___find roof for building %i" % self.osm_id)
        self.roof_texture = roof_mgr.find_matching_roof(self.roof_requires, longest_edge_length, stats)
        if not self.roof_texture:
            stats.skipped_texture += 1
            logging.debug('WARNING: no matching roof texture for osm_id {} <{}>'.format(self.osm_id,
                                                                                        str(self.roof_requires)))
            return False

        if self.roof_texture:
            logging.debug("__done" + str(self.roof_texture) + str(self.roof_texture.provides))

        else:
            stats.skipped_texture += 1
            logging.debug('WARNING: no matching roof texture for OsmID {} <{}>'.format(self.osm_id,
                                                                                       str(self.roof_requires)))
            return False

        return True

    def analyse_roof_shape(self) -> None:
        if 'roof:shape' in self.tags:
            self.roof_shape = _map_osm_roof_shape(self.tags['roof:shape'])
        else:
            # use some parameters and randomize to assign optimistically a roof shape
            # in analyse_roof_shape_check it is double checked whether e.g. building height or area exceed limits
            # and then it will be corrected back to flat roof.
            if parameters.BUILDING_COMPLEX_ROOFS:
                self.roof_shape = _random_roof_shape()
            else:
                self.roof_shape = RoofShape.flat

    def analyse_height_and_levels(self):
        """Determines total height (and number of levels) of a building based on OSM values and other logic.
        Raises ValueError if the height is less than the building min height parameter or layer OSM attribute
        cannot be interpreted if needed.
        
        The OSM key 'height' is defined as: Distance between the lowest possible position with ground contact and 
        the top of the roof of the building, excluding antennas, spires and other equipment mounted on the roof. 
        
        The OSM key 'min_height' is for raising a facade. Even if this 'min_height' is > 0, then the height
        of the building remains the same - the facade just gets shorter.
        See http://wiki.openstreetmap.org/wiki/Key:min_height and http://wiki.openstreetmap.org/wiki/Simple_3D_buildings

        In order to make stuff more obvious in processing, the code will use the following properties:
        * min_height - as described above and therefore mostly 0.0
        * body_height - the height of the main building body (corpus) without the roof-height and maybe
                        min_height above ground
        * roof_height - only the height between where the roof starts on top of the 'body' and where the roof end.
                        For flat roofs it is 0.0

        Therefore what is called 'height' is min_height + body_height + roof_height
        """
        layer = 9999

        proxy_total_height = 0.  # something that mimics the OSM 'height'
        proxy_levels = 0.

        if 'height' in self.tags:
            proxy_total_height = utils.osmparser.parse_length(self.tags['height'])
        elif 'building:height' in self.tags:
            proxy_total_height = utils.osmparser.parse_length(self.tags['building:height'])
        if 'building:levels' in self.tags:
            proxy_levels = float(self.tags['building:levels'])
        if 'levels' in self.tags:
            proxy_levels = float(self.tags['levels'])
        if 'layer' in self.tags:
            layer = int(self.tags['layer'])

        proxy_roof_height = 0.
        if 'roof:height' in self.tags:
            try:
                proxy_roof_height = utils.osmparser.parse_length(self.tags['roof:height'])
            except:
                proxy_roof_height = 0.
        if proxy_roof_height == 0. and self.roof_complex:
            proxy_roof_height = parameters.BUILDING_SKEL_ROOF_DEFAULT_HEIGHT

        # OSM key min_value is used to raise ("hover") a facade above ground
        # -- no complex roof on tiny buildings.
        if "min_height" in self.tags:
            self.min_height = utils.osmparser.parse_length(self.tags['min_height'])

        # Now that we have all what OSM provides, use some heuristics, if we are missing height/levels

        if proxy_total_height == 0. and proxy_levels == 0.:
            # Simple (silly?) heuristics to 'respect' layers (http://wiki.openstreetmap.org/wiki/Key:layer)
            # Basically the use of layers is wrong, so this is a last resort method
            if 0 < layer < 99:
                proxy_levels = layer + 2

        if proxy_total_height == 0. or proxy_levels == 0:  # otherwise both are already set and therefore nothing to do
            level_height = _random_level_height()
            if proxy_total_height > 0.0:
                # calculate body_height
                self.body_height = proxy_total_height - proxy_roof_height - self.min_height
                # handle levels
                self.levels = int(self.body_height / level_height)
            else:
                if proxy_levels == 0.:
                    proxy_levels = _random_levels()
                    if self.area < parameters.BUILDING_MIN_AREA:
                        proxy_levels = min(proxy_levels, 2)
                self.body_height = float(proxy_levels) * level_height  # no need for min_height and proxy_roof_height
                self.levels = proxy_levels

        proxy_total_height = self.body_height + self.min_height + proxy_roof_height
        if parameters.BUILDING_MIN_HEIGHT > 0.0 and proxy_total_height < parameters.BUILDING_MIN_HEIGHT:
            raise ValueError('The height given or calculated is less then the BUILDING_MIN_HEIGHT parameter.')

    def analyse_roof_shape_check(self) -> None:
        """Check whether we actually may use something else than a flat roof."""
        # roof_shape from OSM is already set in analyse_height_and_levels(...)
        if self.roof_complex:
            allow_complex_roofs = False
            if parameters.BUILDING_COMPLEX_ROOFS:
                allow_complex_roofs = True
                # no complex roof on buildings with inner rings
                if self.polygon.interiors:
                    allow_complex_roofs = False
                # no complex roof on large buildings
                elif self.area > parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA:
                    allow_complex_roofs = False
                # if area between thresholds, then have a look at the ratio between area and circumference
                # the smaller the ratio, the less deep the building is compared to its length
                # it is more common to have long houses with complex roofs than a square once it is a big building
                # the formula basically states that if it was a rectangle, then the ratio between the long side length
                # and the short side length should be at least 2.
                elif (parameters.BUILDING_COMPLEX_ROOFS_MIN_RATIO_AREA < self.area <
                        parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA) and (self.circumference > 3 * sqrt(2 * self.area)):
                    allow_complex_roofs = False
                # no complex roof on tall buildings
                elif self.levels > parameters.BUILDING_COMPLEX_ROOFS_MAX_LEVELS and 'roof:shape' not in self.tags:
                    allow_complex_roofs = False
                # no complex roof on tiny buildings.
                elif self.levels < parameters.BUILDING_COMPLEX_ROOFS_MIN_LEVELS and 'roof:shape' not in self.tags:
                    allow_complex_roofs = False
                elif self.nnodes_ground > 4:
                    allow_complex_roofs = False
                    # Now lets see whether we can allow complex nevertheless when more than 4 corners
                    # a bit more relaxed, if we do skeleton roofs
                    if (parameters.BUILDING_SKEL_ROOFS and
                                self.nnodes_ground in range(4, parameters.BUILDING_SKEL_MAX_NODES)):
                        allow_complex_roofs = True
                    # even more relaxed if it is a skillion
                    if self.roof_shape is RoofShape.skillion:
                        allow_complex_roofs = True

            # make sure roof shape is flat if we are not allowed to use it
            if allow_complex_roofs is False:
                self.roof_shape = RoofShape.flat

    def analyse_large_enough(self) -> bool:
        """Checks whether a given building's area is too small for inclusion.
        Never drop tall buildings.
        Returns true if the building should be included (i.e. area is big enough etc.)
        """
        if self.levels >= parameters.BUILDING_NEVER_SKIP_LEVELS:
            return True
        if self.inner_rings_list:  # never skip a building with inner rings
            return True
        if self.area < parameters.BUILDING_MIN_AREA or \
                (self.area < parameters.BUILDING_REDUCE_THRESHOLD and
                 random.uniform(0, 1) < parameters.BUILDING_REDUCE_RATE):
            return False
        return True

    def _compute_roof_height(self) -> None:
        """Compute roof_height for each node"""
        self.roof_height = 0.
        temp_roof_height = 0.  # temp variable before assigning to self

        if self.roof_shape is RoofShape.skillion:
            # get global roof_height and height for each vertex
            if 'roof:height' in self.tags:
                # force clean of tag if the unit is given
                temp_roof_height = utils.osmparser.parse_length(self.tags['roof:height'])
            else:
                if 'roof:angle' in self.tags:
                    angle = float(self.tags['roof:angle'])
                else:
                    angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE,
                                           parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)

                while angle > 0:
                    temp_roof_height = tan(np.deg2rad(angle)) * (self.edge_length_x[1] / 2)
                    if temp_roof_height < parameters.BUILDING_SKILLION_ROOF_MAX_HEIGHT:
                        break
                    angle -= 1

            if 'roof:slope:direction' in self.tags:
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
                angle00 = pi / 2. - (((utils.osmparser.parse_direction(self.tags['roof:slope:direction'])) % 360.)
                                     * pi / 180.)
            else:
                angle00 = 0

            angle90 = angle00 + pi / 2.
            # assume that first point is on the bottom side of the roof
            # and is a reference point (0,0)
            # compute line slope*x

            slope = sin(angle90)

            dir1n = (cos(angle90), slope)  # (1/ndir1, slope/ndir1)

            # keep in mind direction
            # if angle90 < 270 and angle90 >= 90 :
            #    #dir1, dir1n = -dir1, -dir1n
            #    dir1=(-dir1[0],-dir1[1])
            #    dir1n=(-dir1n[0],-dir1n[1])

            # compute distance from points to line slope*x
            X2 = list()
            XN = list()
            nXN = list()
            vprods = list()

            X = self.X

            p0 = (X[0][0], X[0][1])
            for i in range(0, len(X)):
                # compute coord in new referentiel
                vecA = (X[i][0] - p0[0], X[i][1] - p0[1])
                X2.append(vecA)
                #
                norm = vecA[0] * dir1n[0] + vecA[1] * dir1n[1]
                vecN = (vecA[0] - norm * dir1n[0], vecA[1] - norm * dir1n[1])
                nvecN = sqrt(vecN[0] ** 2 + vecN[1] ** 2)
                # store vec and norms
                XN.append(vecN)
                nXN.append(nvecN)
                # compute ^ product
                vprod = dir1n[0] * vecN[1] - dir1n[1] * vecN[0]
                vprods.append(vprod)

            # if first point was not on bottom side, one must find the right point
            # and correct distances
            if min(vprods) < 0:
                ibottom = vprods.index(min(vprods))
                offset = nXN[ibottom]
                norms_o = [nXN[i] + offset if vprods[i] >= 0 else -nXN[i] + offset for i in
                           range(0, len(X))]  # oriented norm
            else:
                norms_o = nXN

            # compute height for each point with thales
            L = float(max(norms_o))

            self.roof_height_x = [temp_roof_height * l / L for l in norms_o]
            self.roof_height = temp_roof_height

        else:  # roof types other than skillion
            if 'roof:height' in self.tags:
                # get roof:height given by osm
                self.roof_height = utils.osmparser.parse_length(self.tags['roof:height'])

            else:
                # random roof:height
                if self.roof_shape is RoofShape.flat:
                    self.roof_height = 0.
                else:
                    if 'roof:angle' in self.tags:
                        angle = float(self.tags['roof:angle'])
                    else:
                        angle = random.uniform(parameters.BUILDING_SKEL_ROOFS_MIN_ANGLE,
                                               parameters.BUILDING_SKEL_ROOFS_MAX_ANGLE)
                    while angle > 0:
                        temp_roof_height = tan(np.deg2rad(angle)) * (self.edge_length_x[1] / 2)
                        if temp_roof_height < parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT:
                            break
                        angle -= 5
                    if temp_roof_height > parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT:
                        temp_roof_height = parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT
                    self.roof_height = temp_roof_height

    def write_to_ac(self, ac_object: ac3d.Object, cluster_elev: float, cluster_offset: Vec2d,
                    roof_mgr: tex.RoofManager, stats: Stats) -> None:
        # get local medium ground elevation for each building
        self.set_ground_elev_and_offset(cluster_elev, cluster_offset)

        self._compute_roof_height()

        self._write_vertices_for_ac(ac_object)

        self._write_faces_for_ac(ac_object, self.polygon.exterior, True)
        if not parameters.EXPERIMENTAL_INNER and len(self.polygon.interiors) > 1:
            raise NotImplementedError("Can't yet handle relations with more than one inner way")
        for inner in self.polygon.interiors:
            self._write_faces_for_ac(ac_object, inner, False)

        self._write_roof_for_ac(ac_object, roof_mgr, cluster_offset, stats)

    def _write_vertices_for_ac(self, ac_object: ac3d.Object) -> None:
        """Write the vertices for each node along bottom and roof edges to the ac3d object."""

        self.index_first_node_in_ac3d_obj = ac_object.next_node_index()

        z = self.ground_elev + self.min_height

        # ground nodes
        for x in self.X:
            ac_object.node(-x[1], z, -x[0])
        # under the roof nodes
        if self.roof_shape is RoofShape.skillion:
            # skillion
            #           __ -+
            #     __-+--    |
            #  +--          |
            #  |            |
            #  +-----+------+
            #
            if self.roof_height_x:
                for i in range(len(self.X)):
                    ac_object.node(-self.X[i][1], self.beginning_of_roof_above_sea_level + self.roof_height_x[i],
                                   -self.X[i][0])
        else:
            # others roofs
            #
            #  +-----+------+
            #  |            |
            #  +-----+------+
            #
            for x in self.X:
                ac_object.node(-x[1], self.beginning_of_roof_above_sea_level, -x[0])

    def _write_faces_for_ac(self, ac_object: ac3d.Object, ring: shg.LinearRing, is_exterior_ring: bool) -> None:
        """Writes all the faces for one building's exterior or interior ring to an ac3d object."""
        tex_coord_bottom, tex_coord_top = _calculate_vertical_texture_coords(self.body_height, self.facade_texture)
        tex_coord_bottom = self.facade_texture.y(tex_coord_bottom)  # -- to atlas coordinates
        tex_coord_top_input = tex_coord_top
        tex_coord_top = self.facade_texture.y(tex_coord_top)

        number_outer_ring_nodes = self.nnodes_outer
        if is_exterior_ring:
            number_outer_ring_nodes = 0

        number_ring_nodes = len(ring.coords) - 1

        for ioff in range(0, number_ring_nodes):
            i = number_outer_ring_nodes + ioff

            if ioff < number_ring_nodes - 1:
                ipp = i + 1
            else:
                ipp = number_outer_ring_nodes
            # FIXME: respect facade texture split_h
            # FIXME: there is a nan in textures.h_splits of tex/facade_modern36x36_12
            a = self.edge_length_x[i] / self.facade_texture.h_size_meters
            ia = int(a)
            frac = a - ia
            tex_coord_right = self.facade_texture.x(self.facade_texture.closest_h_match(frac) + ia)
            if self.facade_texture.v_can_repeat:
                if not (tex_coord_right <= 1.):
                    logging.debug('FIXME: v_can_repeat: need to check in analyse')

            if self.roof_shape is RoofShape.skillion:
                tex_y12 = self.facade_texture.y((self.body_height + self.roof_height_x[i]) /
                                                self.body_height * tex_coord_top_input)
                tex_y11 = self.facade_texture.y((self.body_height + self.roof_height_x[ipp]) /
                                                self.body_height * tex_coord_top_input)
            else:
                tex_y12 = tex_coord_top
                tex_y11 = tex_coord_top

            tex_coord_left = self.facade_texture.x(0)

            ac_object.face([(i + self.index_first_node_in_ac3d_obj, tex_coord_left, tex_coord_bottom),
                            (ipp + self.index_first_node_in_ac3d_obj, tex_coord_right, tex_coord_bottom),
                            (ipp + self.index_first_node_in_ac3d_obj + self.nnodes_ground, tex_coord_right, tex_y11),
                            (i + self.index_first_node_in_ac3d_obj + self.nnodes_ground, tex_coord_left, tex_y12)],
                           swap_uv=self.facade_texture.v_can_repeat)

    def _write_roof_for_ac(self, ac_object: ac3d.Object, roof_mgr: tex.RoofManager,
                           cluster_offset: Vec2d, stats: Stats) -> None:
        """Writes the roof vertices and faces to an ac3d object."""
        if self.roof_shape is RoofShape.flat:
            roofs.flat(ac_object, self, roof_mgr, stats)

        else:
            # -- pitched roof for > 4 ground nodes
            if self.nnodes_ground > 4 and parameters.BUILDING_SKEL_ROOFS:
                if self.roof_shape is RoofShape.skillion:
                    roofs.separate_skillion(ac_object, self)
                elif self.roof_shape is RoofShape.pyramidal:
                    roofs.separate_pyramidal(ac_object, self)
                else:
                    s = myskeleton.myskel(ac_object, self, stats, offset_xy=cluster_offset,
                                          offset_z=self.beginning_of_roof_above_sea_level,
                                          max_height=parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT)
                    if s:
                        stats.have_complex_roof += 1

                    else:  # something went wrong - fall back to flat roof
                        self.roof_shape = RoofShape.flat
                        roofs.flat(ac_object, self, roof_mgr, stats)
            # -- pitched roof for exactly 4 ground nodes
            else:
                if self.roof_shape is RoofShape.gabled:
                    roofs.separate_gable(ac_object, self)
                elif self.roof_shape is RoofShape.hipped:
                    roofs.separate_hipped(ac_object, self)
                elif self.roof_shape is RoofShape.pyramidal:
                    roofs.separate_pyramidal(ac_object, self)
                elif self.roof_shape is RoofShape.skillion:
                    roofs.separate_skillion(ac_object, self)
                elif self.roof_shape is RoofShape.flat:
                    roofs.flat(ac_object, self, roof_mgr, stats)
                else:
                    logging.warning("Roof type %s seems to be unsupported, but is mapped ", self.roof_shape.name)
                    roofs.flat(ac_object, self, roof_mgr, stats)


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


def _calculate_vertical_texture_coords(body_height: float, t: tex.Texture) -> Tuple[float, float]:
    """Check if a texture t fits the building' body_height (h) and return the bottom and top relative position of the tex.
    I.e. return numbers between 0 and 1, where 1 is at the top.
    v-repeatable textures are repeated to fit h
    For non-repeatable textures,
       - check if h is within the texture's limits (min_height, max_height)
    """
    if t.v_can_repeat:
        # -- v-repeatable textures are rotated 90 deg in atlas.
        #    Face will be rotated later on, so his here will actually be u
        tex_coord_top = 1.
        tex_coord_bottom = 1 - body_height / t.v_size_meters
        return tex_coord_bottom, tex_coord_top
        # FIXME: respect v_cuts
    else:
        # x min_height < height < max_height
        # x find closest match
        # - evaluate error

        # - error acceptable?
        if t.v_cuts_meters[0] <= body_height <= t.v_size_meters:
            if t.v_align_bottom or parameters.BUILDING_FAKE_AMBIENT_OCCLUSION:
                logging.verbose("from bottom")
                for i in range(len(t.v_cuts_meters)):
                    if t.v_cuts_meters[i] >= body_height:
                        tex_coord_bottom = 0
                        tex_coord_top = t.v_cuts[i]
                        return tex_coord_bottom, tex_coord_top
            else:
                for i in range(len(t.v_cuts_meters)-2, -1, -1):
                    if t.v_cuts_meters[-1] - t.v_cuts_meters[i] >= body_height:
                        # FIXME: probably a bug. Should use distance to height?
                        tex_coord_bottom = t.v_cuts[i]
                        tex_coord_top = 1

                        return tex_coord_bottom, tex_coord_top
            raise ValueError("SHOULD NOT HAPPEN! found no tex_y0, tex_y1 (building_height %g splits %s %g)" %
                             (body_height, str(t.v_cuts_meters), t.v_size_meters))
        else:
            return 0, 0


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
        b.parent = None  # will be reset again if actually all is ok at end

        # make sure we have a flat roof in parent:child situation. By using tag instead of direct b.roof_shape
        # property we make sure, that it is not overwritten in analysis later
        if building_parent is not None:
            b.tags['roof:shape'] = 'flat'

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
        temp_ground_elev = 9999
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
            temp_ground_elev = min([temp_ground_elev, elev_is_solid_tuple[0]])  # we are looking for the lowest value
        if not elev_water_ok:
            continue
        b.ground_elev = temp_ground_elev

        if b.is_external_model:
            new_buildings.append(b)
            continue

        stats.nodes_ground += b.nnodes_ground

        # -- compute edge length
        b.edge_length_x = np.zeros((b.nnodes_ground))
        for i in range(b.nnodes_outer - 1):
            b.edge_length_x[i] = ((Xo[i + 1, 0] - Xo[i, 0]) ** 2 + (Xo[i + 1, 1] - Xo[i, 1]) ** 2) ** 0.5
        n = b.nnodes_outer
        b.edge_length_x[n - 1] = ((Xo[0, 0] - Xo[n - 1, 0]) ** 2 + (Xo[0, 1] - Xo[n - 1, 1]) ** 2) ** 0.5

        if b.inner_rings_list:
            i0 = b.nnodes_outer
            for interior in b.polygon.interiors:
                Xi = np.array(interior.coords)[:-1]
                n = len(Xi)
                for i in range(n - 1):
                    b.edge_length_x[i0 + i] = ((Xi[i + 1, 0] - Xi[i, 0]) ** 2 + (Xi[i + 1, 1] - Xi[i, 1]) ** 2) ** 0.5
                b.edge_length_x[i0 + n - 1] = ((Xi[0, 0] - Xi[n - 1, 0]) ** 2 + (Xi[0, 1] - Xi[n - 1, 1]) ** 2) ** 0.5
                i0 += n

        # -- re-number nodes such that longest edge is first -- only on simple buildings
        # FIXME: why? We can and do calculate longest edge and can use that for texture
        if b.nnodes_outer == 4 and not b.X_inner:
            if b.edge_length_x[0] < b.edge_length_x[1]:
                Xo = np.roll(Xo, 1, axis=0)
                b.edge_length_x = np.roll(b.edge_length_x, 1)
                b._set_polygon(Xo, b.inner_rings_list)

        # - find the roof_shape
        b.analyse_roof_shape()

        # -- work on height and levels
        try:
            b.analyse_height_and_levels()
        except ValueError as e:
            logging.debug('Skipping building osm_id = {}: {}'.format(b.osm_id, e))
            stats.skipped_small += 1
            continue

        # -- check area, but if has parent then always keep
        if not building_parent:
            if not b.analyse_large_enough():
                stats.skipped_small += 1
                continue
        b.analyse_roof_shape_check()

        if not b.analyse_textures(facade_mgr, roof_mgr, stats):
            continue

        # -- finally: append building to new list
        new_buildings.append(b)
        if building_parent is not None:
            b.parent = building_parent
            building_parents[building_parent.osm_id] = building_parent

    # align textures etc. for buildings with parents or pseudo-parents
    for key, parent in building_parents.items():
        parent.align_textures_children()

    for building_part in new_buildings:
        if building_part.pseudo_parents:
            # FIXME there should be some checks whether the part is really the highest / most levels
            # to determine whether the pseudo_parent really should pick the part's texture
            for pseudo_parent in building_part.pseudo_parents:
                pseudo_parent.facade_texture = building_part.facade_texture
                pseudo_parent.roof_texture = building_part.roof_texture

    # make sure that min_height is only used if there is a real parent (not pseudo_parents)
    # i.e. for all others we just set it to 0.0
    for building in new_buildings:
        if building.parent is None:
            building.min_height = 0.0

    return new_buildings


def write(ac_file_name: str, buildings: List[Building], cluster_elev: float, cluster_offset: Vec2d,
          roof_mgr: tex.RoofManager, stats: Stats) -> None:
    """Write buildings across LOD for given tile.
       While writing, accumulate some statistics (totals stored in global stats object, individually also in building).
       Offset accounts for cluster center
       All LOD in one file. Plus roofs. One ac3d.Object per LOD
    """
    ac = ac3d.File(stats=stats)
    texture_name = tm.atlas_file_name + '.png'
    if parameters.FLAG_2017_2:
        texture_name = 'Textures/osm2city/atlas_facades.png'
    lod_objects = list()  # a list of meshes, where each LOD has one mesh
    lod_objects.append(ac.new_object('LOD_rough', texture_name, default_mat_idx=ac3d.MAT_IDX_LIT))
    lod_objects.append(ac.new_object('LOD_detail', texture_name, default_mat_idx=ac3d.MAT_IDX_LIT))

    for ib, b in enumerate(buildings):
        progress(ib, len(buildings))
        ac_object = lod_objects[b.LOD]

        b.write_to_ac(ac_object, cluster_elev, cluster_offset, roof_mgr, stats)

    ac.write(ac_file_name)


def _map_building_type(tags: Dict[str, str]) -> str:
    if 'building' in tags and not tags['building'] == 'yes':
        return tags['building']
    return 'unknown'


def overlap_check_blocked_areas(buildings: List[Building], blocked_areas: List[shg.Polygon]) -> List[Building]:
    """Checks each building whether it overlaps with a blocked area and excludes it from the returned list of True.
    Uses intersection checking - i.e. not touches or disjoint."""
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
    """Checks for all buildings whether their polygon intersects with a static or shared object's convex hull."""
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
            except TopologicalError:
                logging.exception('Convex hull could not be checked due to topology problem - building osm_id: %d',
                                  building.osm_id)

        if not is_intersecting:
            cleared_buildings.append(building)
    return cleared_buildings
