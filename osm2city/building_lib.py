"""
Created on Thu Feb 28 23:18:08 2013

@author: tom

Call hierarchy (as of summer 2017) - building_lib is called from building.py:

* building_lib.overlap_check_blocked_areas(...)
* building_lib.overlap_check_convex_hull(...)
* building_lib.analyse(...)
    for building in ...
        b.analyse_elev_and_water(..)
        b.analyse.edge_lengths(...)
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

from enum import IntEnum, unique
import logging
import random
from math import fabs, sin, cos, tan, sqrt, pi, radians
from typing import List, Dict, Optional, Set, Tuple

import numpy as np
from shapely import affinity
import shapely.geometry as shg

from osm2city import myskeleton, parameters, roofs
import osm2city.textures.managers as mgr
import osm2city.static_types.enumerations as enu
from osm2city.utils import coordinates as co
from osm2city.utils import osmparser as op
from osm2city.utils import utilities, ac3d
from osm2city.static_types import osmstrings as s
from osm2city.utils import stg_io2


def _random_roof_shape() -> enu.RoofShape:
    random_shape = utilities.random_value_from_ratio_dict_parameter(parameters.BUILDING_ROOF_SHAPE_RATIO)
    return enu.map_osm_roof_shape(random_shape)


# Based on lines 476 ff in simgear/scene/tgdb/SGBuildingBin.cxx
BUILDING_LIST_SMALL_MIN_SIDE = 3.
BUILDING_LIST_MEDIUM_MIN_SIDE = 10.
BUILDING_LIST_LARGE_MIN_SIDE = 20.
BUILDING_LIST_SMALL_MAX_LEVELS = 3
BUILDING_LIST_MEDIUM_MAX_LEVELS = 8
BUILDING_LIST_LARGE_MAX_LEVELS = 22


@unique
class BuildingListType(IntEnum):
    """Available Random Building BUILDING_LIST types."""
    small = 0  # typically a family house
    medium = 1  # large house or smaller apartment
    large = 2  # larger apartment or industrial/commercial/retail ...


def calc_levels_for_settlement_type(settlement_type: enu.SettlementType, building_class: enu.BuildingClass) -> int:
    if settlement_type is enu.SettlementType.centre:
        ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_CENTRE
    elif settlement_type is enu.SettlementType.block:
        ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_BLOCK
    else:
        # now check residential vs. others
        if building_class in [building_class.residential, building_class.residential_small]:
            if settlement_type is enu.SettlementType.dense:
                ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_DENSE
            elif settlement_type is enu.SettlementType.periphery:
                ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_PERIPHERY
            else:
                ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_RURAL
        elif building_class is enu.BuildingClass.apartments:
            ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_APARTMENTS
        elif building_class in [enu.BuildingClass.industrial, enu.BuildingClass.warehouse]:
            ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_INDUSTRIAL
        else:
            ratio_parameter = parameters.BUILDING_NUMBER_LEVELS_OTHER
    return utilities.random_value_from_ratio_dict_parameter(ratio_parameter)


def calc_level_height_for_settlement_type(settlement_type: enu.SettlementType) -> float:
    if settlement_type in [enu.SettlementType.periphery, enu.SettlementType.rural]:
        return enu.BUILDING_LEVEL_HEIGHT_RURAL
    return enu.BUILDING_LEVEL_HEIGHT_URBAN


class Building(object):
    """Central object class.
    Holds all data relevant for a building. Coordinates, type, area, ...
    Read-only access to node coordinates via self.pts[node][0|1]

    Trying to keep naming consistent:
        * Node: from OSM ans OSM way
        * Vertex: in ac-file
        * Point (abbreviated to pt and pts): local coordinates for points on building (inner and outer)
    """
    __slots__ = ('osm_id', 'tags', 'is_owbb_model', 'stg_typ',
                 'street_angle', 'anchor', 'width', 'depth', 'zone',
                 'body_height', 'levels', 'min_height', 'roof_shape', 'roof_height', 'roof_hint',
                 'refs', 'refs_inner', 'refs_shared', 'inner_rings_list', 'outer_nodes_closest', 'polygon', 'geometry',
                 'parent', 'pts_all', 'roof_height_pts', 'edge_length_pts', 'facade_texture',
                 'roof_texture', 'roof_requires',
                 'ground_elev', 'diff_elev'
                 )

    def __init__(self, osm_id: int, tags: Dict[str, str], outer_ring: shg.LinearRing,
                 anchor: Optional[co.Vec2d],
                 stg_typ: stg_io2.STGVerbType = None, street_angle=0, inner_rings_list=None,
                 refs: List[int] = None, refs_inner: List[List[int]] = None,
                 is_owbb_model: bool = False, width: float = 0., depth: float = 0.) -> None:
        # assert empty lists if default None
        if inner_rings_list is None:
            inner_rings_list = list()
        if refs is None:
            refs = list()

        # set during init and methods called by init
        self.osm_id = osm_id
        self.tags = tags
        self.is_owbb_model = is_owbb_model
        self.stg_typ = stg_typ  # STGVerbType

        # For buildings drawn by shader in BUILDING_LIST
        self.street_angle = street_angle  # the angle from the front-door looking at the street
        self.anchor = anchor  # local Vec2d object
        self.width = width
        self.depth = depth

        # set during owbb land-use zone processing or owbb building generation
        self.zone = None  # either a owbb.model.(Generated)BuildingZone or owbb.model.CityBlock

        # For definition of '*height' see method analyse_height_and_levels(..)
        self.body_height = 0.0
        self.levels = 0
        self.min_height = 0.0  # the height over ground relative to ground_elev of the facade. See min_height in OSM
        self.roof_shape = enu.RoofShape.flat
        self.roof_height = 0.0  # the height of the roof (0 if flat), not the elevation over ground of the roof
        self.roof_hint = None  # roofs.RoofHint object

        # set during method called by init(...) through self.update_geometry and related sub-calls
        self.refs = None  # contains only the refs of the outer_ring
        self.refs_inner = None
        self.refs_shared = dict()  # refs shared with other buildings (key: neighbour building, value: set of positions)
        self.inner_rings_list = None
        self.outer_nodes_closest = None
        self.polygon = None  # can have inner and outer rings, i.e. the real polygon
        self.geometry = None  # only the outer ring - for convenience and faster processing in some analysis
        self.update_geometry(outer_ring, inner_rings_list, refs, refs_inner)

        # set in buildings.py for building relations prior to building_lib.analyse(...)
        # - from building._process_building_parts(...)
        self.parent = None  # BuildingParent if available

        # set after init(...)
        self.pts_all = None
        self.roof_height_pts = []  # roof height at pt - only set and used for type=skillion
        self.edge_length_pts = None  # numpy array of side length between pt and pt+1
        self.facade_texture = None  # mgr.FacadeTexture
        self.roof_texture = None  # mgr.RoofTexture
        self.roof_requires = list()

        self.ground_elev = 0.0  # the lowest elevation over sea of any point in the outer ring of the building
        self.diff_elev = 0.0  # the difference between the lowest elevation and the highest ground elevation og building

    def make_building_from_part(self) -> None:
        """Make sure a former building_part gets tagged correctly"""
        if s.K_BUILDING_PART in self.tags:
            part_value = self.tags[s.K_BUILDING_PART]
            del self.tags[s.K_BUILDING_PART]
            if s.K_BUILDING not in self.tags:
                self.tags[s.K_BUILDING] = part_value

    def update_geometry(self, outer_ring: shg.LinearRing, inner_rings_list: List[shg.LinearRing] = None,
                        refs: List[int] = None, refs_inner: List[List[int]] = None) -> None:
        """Updates the geometry of the building. This can also happen after the building has been initialized.
        Makes also sure, that inner and outer rings have correct orientation.
        """
        if inner_rings_list is None:
            inner_rings_list = list()
        if refs is None:
            refs = list()

        # make sure that outer ring is ccw
        self.refs = refs
        if outer_ring.is_ccw is False:
            outer_ring.coords = list(outer_ring.coords)[::-1]
            self.refs = self.refs[::-1]

        # handle inner rings
        self.inner_rings_list = inner_rings_list
        if self.inner_rings_list:
            # make sure that inner rings are not ccw
            index_pos = 0
            for inner_ring in self.inner_rings_list:
                if inner_ring.is_ccw:
                    inner_ring.coords = list(inner_ring.coords)[::-1]
                    refs_inner[index_pos] = refs_inner[index_pos][::-1]
                index_pos += 1
        self.outer_nodes_closest = []
        if len(outer_ring.coords) > 2:
            self._set_polygon(outer_ring, self.inner_rings_list)
        else:
            self.polygon = None
        if self.inner_rings_list:
            self.roll_inner_nodes()
        self.update_anchor(False)

    def update_geometry_from_refs(self, nodes_dict: Dict[int, op.Node],
                                  coords_transform: co.Transformation) -> None:
        """Make it possible to update geometry based on refs already stored in the building.

        E.g. to make sure that after different geometry operations sequence of nodes vs. refs is still consistent."""
        outer_ring = op.refs_to_ring(coords_transform, self.refs, nodes_dict)
        inner_rings_list = list()
        if self.refs_inner:
            for inner_ring_refs in self.refs_inner:
                inner_rings_list.append(op.refs_to_ring(coords_transform, inner_ring_refs.refs, nodes_dict))
        self.update_geometry(outer_ring, inner_rings_list, self.refs, self.refs_inner)

    def update_anchor(self, recalculate: bool) -> None:
        """Determines the anchor point of a building.
        The anchor point is used in 2 situations:
        * For buildings in meshes it just determines in which cluster a building is. Therefore it does basically not
          matter.
        * For shader buildings in lists, it matters a lot, because it determines the orientation. Here 0,0,0 is
          defined as the bottom center of the front face of the building. The "front face" is the facade of the
          building facing the street. "Bottom center" is on ground level vertically and centre means that it is
          horizontally between the left and right edge of the front face. Still: the rotation is relative to this
          point and not the geometric or centre of gravity.
        """
        if not recalculate:
            if self.anchor is not None:  # keep what we have. Even after a simplification for a mesh it is good enough
                return

            if self.zone is None:  # zone is first set after building has been created
                # just use the first point of the outside of the building
                self.anchor = co.Vec2d(self.pts_outer[0])
                self.street_angle = 0
                return

        # Apparently we deal with a OSM building that is not to be drawn in a mesh, but in building list.
        # As anchor candidates we choose the middle points of the sides of the convex hull of the building.
        # Then we search for the candidate which has the shortest distance to the zone/block border.
        # The candidate with the shortest distance is chosen and the
        # street angle is based on the side of the convex hull, where the chosen candidate is situated.
        try:
            hull = self.polygon.convex_hull
            hull_points = list(hull.exterior.coords)
            shortest_distance = 99999.
            shortest_node = 0
            for j in range(len(hull_points) - 1):
                x, y = co.calc_point_on_line_local(hull_points[j][0], hull_points[j][1],
                                                   hull_points[j + 1][0], hull_points[j + 1][1], 0.5)
                distance = shg.Point(x, y).distance(self.zone.geometry.exterior)
                if distance < shortest_distance:
                    shortest_node = j
                    shortest_distance = distance

            i = shortest_node
            x, y = co.calc_point_on_line_local(hull_points[i][0], hull_points[i][1],
                                               hull_points[i + 1][0], hull_points[i + 1][1], 0.5)
            angle = co.calc_angle_of_line_local(hull_points[i][0], hull_points[i][1],
                                                hull_points[i + 1][0], hull_points[i + 1][1])
            self.anchor = co.Vec2d(x, y)
            self.street_angle = co.normal_degrees(angle + 90)

            # to get the width depth we must rotate the hull and then calculate the distance of the most distant points.
            # we could calculate the width based on the following, but that is not accurate if e.g. the building in OSM
            # is modelled with a small front door entrance just 1 meter wide (happens e.g. in the Netherlands)
            # self.width = co.calc_distance_local(hull_points[i][0], hull_points[i][1],
            #                                    hull_points[i + 1][0], hull_points[i + 1][1])
            rotated_hull = affinity.rotate(hull, angle, hull_points[i])
            rotated_hull_points = list(rotated_hull.exterior.coords)
            longest_1 = 0.
            longest_2 = 0.
            widest_1 = 0.
            widest_2 = 0.
            for k in range(len(rotated_hull_points) - 1):
                distance = fabs(rotated_hull_points[i][0] - rotated_hull_points[k][0])
                if distance > longest_1:
                    longest_2 = longest_1
                    longest_1 = distance
                elif distance > longest_2:
                    longest_2 = distance
                distance = fabs(rotated_hull_points[i][1] - rotated_hull_points[k][1])
                if distance > widest_1:
                    widest_2 = widest_1
                    widest_1 = distance
                elif distance > widest_2:
                    widest_2 = distance

            if longest_1 * parameters.BUILDING_LIST_DIST_DEVIATION > longest_2:
                self.depth = longest_1
            else:
                self.depth = (longest_1 + longest_2) / 2
            if widest_1 * parameters.BUILDING_LIST_DIST_DEVIATION > widest_2:
                self.width = widest_1
            else:
                self.width = (widest_1 + widest_2) / 2

        except AttributeError:
            logging.exception('Problem to calc anchor for building osm_id=%i in zone of type=%s and settlement type=%s',
                              self.osm_id, self.zone, self.zone.settlement_type)

    def roll_inner_nodes(self) -> None:
        """Roll inner rings such that for each inner ring the node closest to an outer node goes first.

        Also, create a list of outer corresponding outer nodes.
        """
        new_inner_rings_list = []
        self.outer_nodes_closest = []
        outer_nodes_avail = list(range(self.pts_outer_count))
        for inner in self.polygon.interiors:
            min_r = 1e99  # minimum distance between inner node i and outer node o
            min_i = 0  # index position of the inner node
            min_o = 0  # index position of the outer node
            for i, node_i in enumerate(list(inner.coords)[:-1]):
                node_i = co.Vec2d(node_i)
                for o in outer_nodes_avail:
                    r = node_i.distance_to(co.Vec2d(self.pts_outer[o]))
                    if r <= min_r:
                        min_r = r
                        min_i = i
                        min_o = o
            new_inner = shg.polygon.LinearRing(np.roll(np.array(inner.coords)[:-1], -min_i, axis=0))
            new_inner_rings_list.append(new_inner)
            self.outer_nodes_closest.append(min_o)
            outer_nodes_avail.remove(min_o)
            if len(outer_nodes_avail) == 0:
                break  # cannot have more inner rings than outer points. So just discard the other inner rings
        # -- sort inner rings by index of closest outer node
        yx = sorted(zip(self.outer_nodes_closest, new_inner_rings_list))
        self.inner_rings_list = [x for (y, x) in yx]
        self.outer_nodes_closest = [y for (y, x) in yx]
        self._set_polygon(self.polygon.exterior, self.inner_rings_list)

    def simplify(self, nodes_dict: Dict[int, op.Node], coords_transform: co.Transformation) -> int:
        """Simplifies the geometry, but only if no inners."""
        if self.has_inner:
            return 0
        count_simplified = 0
        while True:
            to_remove = utilities.simplify_balconies(self.polygon, parameters.BUILDING_SIMPLIFY_TOLERANCE_LINE,
                                                     parameters.BUILDING_SIMPLIFY_TOLERANCE_AWAY, self.refs_shared)
            if len(to_remove) == 0:
                break
            else:
                count_simplified += 1
                new_refs = list()
                for i in range(0, len(self.refs)):
                    if i not in to_remove:
                        new_refs.append(self.refs[i])
                self.refs = new_refs
                self.update_geometry_from_refs(nodes_dict, coords_transform)
        return count_simplified

    def _set_polygon(self, outer: shg.LinearRing, inner: List[shg.LinearRing] = None) -> None:
        if inner is None:
            inner = list()
        self.polygon = shg.Polygon(outer, inner)
        self.geometry = shg.Polygon(outer)

    def _set_pts_all(self, cluster_offset: co.Vec2d) -> None:
        """Given an cluster middle point changes all coordinates in x/y space."""
        self.pts_all = np.array(self.pts_outer + self.pts_inner)
        for i in range(self.pts_all_count):
            self.pts_all[i, 0] -= cluster_offset.x
            self.pts_all[i, 1] -= cluster_offset.y
        # adapt the coordinates of roof hints if any
        if self.roof_hint is not None and self.roof_hint.inner_node is not None:
            self.roof_hint.inner_node = (self.roof_hint.inner_node[0] - cluster_offset.x,
                                         self.roof_hint.inner_node[1] - cluster_offset.y)

    def set_ground_elev_and_offset(self, cluster_offset: co.Vec2d) -> None:
        """Sets the ground elevations as difference between real elevation and cluster elevation.
        Additionally it takes into consideration that the world is round.
        Also translates x/y coordinates"""
        self._set_pts_all(cluster_offset)
        self.ground_elev -= co.calc_horizon_elev(self.pts_all[0, 0], self.pts_all[0, 1])

    def calc_building_list_type(self) -> Optional[BuildingListType]:
        """Determines the buildings list type. A return of None means it should be be handled in a mesh."""
        # first make the obvious choices
        if s.K_AEROWAY in self.tags:
            return None
        if s.K_MIN_HEIGHT in self.tags:
            return None
        if s.K_MAN_MADE in self.tags and self.tags[s.K_MAN_MADE] == s.V_TOWER:
            return None
        if s.K_BUILDING in self.tags and self.tags[s.K_BUILDING] == s.V_WATER_TOWER:
            return None
        if self.has_parent:  # mostly detailed buildings in OSM, which might be landmarks
            return None
        if self.has_neighbours and not parameters.BUILDING_LIST_ALLOW_NEIGHBOURS:
            return None
        if self.has_inner:
            return None
        if self.pts_outer_count == 3:  # triangles
            return None
        if self.pts_outer_count >= 7 and self.area > parameters.BUILDING_COMPLEX_ROOFS_MIN_RATIO_AREA:
            return None  # keep larger buildings with many edges
        if self.area < parameters.BUILDING_LIST_AREA_DEVIATION * self.width * self.depth:  # L-buildings or trapeze
            return None

        # now determine in details
        min_side = min(self.width, self.depth)
        if min_side < BUILDING_LIST_SMALL_MIN_SIDE:
            return None
        if self.levels > BUILDING_LIST_LARGE_MAX_LEVELS:
            return None
        list_type = BuildingListType.small
        if min_side < BUILDING_LIST_MEDIUM_MIN_SIDE:
            if self.levels > BUILDING_LIST_SMALL_MAX_LEVELS:
                self.levels = BUILDING_LIST_SMALL_MAX_LEVELS
                self.body_height = self.levels * self._calculate_level_height()
            return list_type
        building_class = enu.get_building_class(self.tags)
        if building_class in [enu.BuildingClass.residential, enu.BuildingClass.residential_small,
                              enu.BuildingClass.terrace]:
            if self.area > 800:
                list_type = BuildingListType.medium
            if self.levels > BUILDING_LIST_SMALL_MAX_LEVELS:
                list_type = BuildingListType.medium
            if self.levels > BUILDING_LIST_MEDIUM_MAX_LEVELS:
                list_type = BuildingListType.large
        elif building_class in [enu.BuildingClass.apartments] and self.levels <= BUILDING_LIST_SMALL_MAX_LEVELS:
            list_type = BuildingListType.small

        if list_type is BuildingListType.medium:
            if min_side < BUILDING_LIST_MEDIUM_MIN_SIDE:
                return None
            if self.area > 1000 or self.levels > BUILDING_LIST_MEDIUM_MAX_LEVELS:
                list_type = BuildingListType.large

        if list_type is BuildingListType.large:
            if min_side < BUILDING_LIST_LARGE_MIN_SIDE:
                return None

        return list_type

    @property
    def roof_complex(self) -> bool:
        """Proxy to see whether the roof is flat or not.
        Skillion is also kind of flat, but is not horizontal and therefore would also return false."""
        if self.roof_shape is enu.RoofShape.flat:
            return False
        return True

    @property
    def pts_outer(self) -> List[Tuple[float, float]]:
        return list(self.polygon.exterior.coords)[:-1]

    @property
    def has_neighbours(self) -> bool:
        """To know whether this building shares at least 2 references (nodes) with another building."""
        if self.refs_shared:
            for pos_list in self.refs_shared.values():
                if len(pos_list) > 1:
                    return True
        return False

    @property
    def has_parent(self) -> bool:
        if self.parent is None:
            return False
        return True

    @property
    def has_inner(self) -> bool:
        return len(self.polygon.interiors) > 0

    @property
    def pts_inner(self) -> List[Tuple[float, float]]:
        return [coord for interior in self.polygon.interiors for coord in list(interior.coords)[:-1]]

    @property
    def pts_outer_count(self) -> int:
        return len(self.polygon.exterior.coords) - 1

    @property
    def pts_all_count(self) -> int:
        n = self.pts_outer_count
        for item in self.polygon.interiors:
            n += len(item.coords) - 1
        return n

    @property
    def area(self):
        """The area of the building only taking into account the outer ring, not inside holes."""
        return self.geometry.area

    @property
    def circumference(self):
        return self.polygon.length

    @property
    def longest_edge_length(self):
        return max(self.edge_length_pts)

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

    def analyse_textures(self, facade_mgr: mgr.FacadeManager, roof_mgr: mgr.RoofManager, body_height: float) -> bool:
        """Determine the facade and roof textures. Return False if anomaly is found.

        Body height is a parameter such that it can be set from outside instead of from building object directly.
        """
        self.facade_texture = facade_mgr.find_matching_facade(list(), self.tags, body_height,
                                                              self.longest_edge_length)
        if not self.facade_texture:
            logging.warning("Skipping building with osm_id %d: (no matching facade texture)" % self.osm_id)
            return False
        self.roof_texture = roof_mgr.find_matching_roof(self.roof_requires, self.longest_edge_length)
        if not self.roof_texture:
            logging.warning('WARNING: no matching roof texture for osm_id {} <{}>'.format(self.osm_id,
                                                                                          str(self.roof_requires)))
            return False

        return True

    def analyse_elev_and_water(self, fg_elev: utilities.FGElev) -> bool:
        """Get the elevation of the node lowest node on the outer ring.
        If a node is in water or at -9999, then return False."""
        min_ground_elev, diff_elev = fg_elev.probe_list_of_points(self.pts_outer)
        if min_ground_elev != -9999:
            self.ground_elev = min_ground_elev
            self.diff_elev = diff_elev
            return True
        return False

    def analyse_edge_lengths(self) -> None:
        # -- compute edge length
        pts_outer = np.array(self.pts_outer)
        self.edge_length_pts = np.zeros(self.pts_all_count)
        for i in range(self.pts_outer_count - 1):
            self.edge_length_pts[i] = ((pts_outer[i + 1, 0] - pts_outer[i, 0]) ** 2 +
                                       (pts_outer[i + 1, 1] - pts_outer[i, 1]) ** 2) ** 0.5
        n = self.pts_outer_count
        self.edge_length_pts[n - 1] = ((pts_outer[0, 0] - pts_outer[n - 1, 0]) ** 2 +
                                       (pts_outer[0, 1] - pts_outer[n - 1, 1]) ** 2) ** 0.5

        if self.inner_rings_list:
            index = self.pts_outer_count
            for interior in self.polygon.interiors:
                pts_inner = np.array(interior.coords)[:-1]
                n = len(pts_inner)
                for i in range(n - 1):
                    self.edge_length_pts[index + i] = ((pts_inner[i + 1, 0] - pts_inner[i, 0]) ** 2 +
                                                       (pts_inner[i + 1, 1] - pts_inner[i, 1]) ** 2) ** 0.5
                self.edge_length_pts[index + n - 1] = ((pts_inner[0, 0] - pts_inner[n - 1, 0]) ** 2 +
                                                       (pts_inner[0, 1] - pts_inner[n - 1, 1]) ** 2) ** 0.5
                index += n

        # -- re-number nodes such that longest edge is first -- only on simple buildings
        # FIXME: why? We can and do calculate longest edge and can use that for texture
        if self.pts_outer_count == 4 and not self.pts_inner:
            if self.edge_length_pts[0] < self.edge_length_pts[1]:
                pts_outer = np.roll(pts_outer, 1, axis=0)
                self.edge_length_pts = np.roll(self.edge_length_pts, 1)
                self._set_polygon(pts_outer, self.inner_rings_list)

    def analyse_street_angle(self) -> None:
        if self.is_owbb_model:
            # the angle is already given by the model
            return

        pts_outer = np.array(self.pts_outer)
        longest_edge_length = 0
        for i in range(self.pts_outer_count - 1):
            my_edge_length = ((pts_outer[i + 1, 0] - pts_outer[i, 0]) ** 2 +
                              (pts_outer[i + 1, 1] - pts_outer[i, 1]) ** 2) ** 0.5
            if my_edge_length > longest_edge_length:
                longest_edge_length = my_edge_length
                self.street_angle = co.calc_angle_of_line_local(pts_outer[i, 0], pts_outer[i, 1],
                                                                pts_outer[i + 1, 0], pts_outer[i + 1, 1])

    def analyse_roof_shape(self, building_parent: Optional['BuildingParent']) -> None:
        """See also description in manual for European Style parameters.

        Be aware that these tags could be overwritten later in the processing again. It just increases probability.
        """
        if s.K_ROOF_SHAPE in self.tags:
            self.roof_shape = enu.map_osm_roof_shape(self.tags[s.K_ROOF_SHAPE])
        else:
            # use some parameters and randomize to assign optimistically a roof shape
            # in analyse_roof_shape_check it is double checked whether e.g. building height or area exceed limits
            # and then it will be corrected back to flat roof.
            if parameters.BUILDING_COMPLEX_ROOFS and building_parent is None:
                if self.has_neighbours and parameters.BUILDING_FORCE_EUROPEAN_INNER_CITY_STYLE:
                    self.roof_shape = enu.RoofShape.gabled
                else:
                    self.roof_shape = _random_roof_shape()
                if parameters.BUILDING_FORCE_EUROPEAN_INNER_CITY_STYLE:
                    # now apply some tags to increase European style
                    if s.K_ROOF_COLOUR not in self.tags:
                        self.tags[s.K_ROOF_COLOUR] = 'red'
            else:
                self.roof_shape = enu.RoofShape.flat

    def analyse_building_type(self) -> None:
        building_class = enu.get_building_class(self.tags)
        if building_class.undefined:
            # FIXME do stuff with amenities and land-use

            # if still residential, then check floor area if in peripheral or rural area - > apartments
            # what about terraces -> should we check how long vs. width?
            if self.area > 250:
                building_class = enu.BuildingClass.apartments
                if s.K_BUILDING in self.tags:
                    self.tags[s.K_BUILDING] = s.V_APARTMENTS
                else:
                    self.tags[s.K_BUILDING_PART] = s.V_APARTMENTS

    def analyse_height_and_levels(self, building_parent: Optional['BuildingParent']) -> None:
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

        Simple (silly?) heuristics to 'respect' layers (http://wiki.openstreetmap.org/wiki/Key:layer) is NOT used,
        as it would be wrong and only a last resort method like: proxy_levels = layer + 2
        """
        proxy_total_height = 0.  # something that mimics the OSM 'height'
        proxy_body_height = 0.
        proxy_roof_height = 0.

        if s.K_HEIGHT in self.tags:
            proxy_total_height = op.parse_length(self.tags[s.K_HEIGHT])
        if s.K_BUILDING_HEIGHT in self.tags:
            proxy_body_height = op.parse_length(self.tags[s.K_BUILDING_HEIGHT])
        if s.K_ROOF_HEIGHT in self.tags:
            proxy_roof_height = op.parse_length(self.tags[s.K_ROOF_HEIGHT])

        if s.K_MIN_HEIGHT_COLON in self.tags and (s.K_MIN_HEIGHT not in self.tags):  # very few values, wrong tagging
            self.tags[s.K_MIN_HEIGHT] = self.tags[s.K_MIN_HEIGHT_COLON]
            del self.tags[s.K_MIN_HEIGHT_COLON]
        if s.K_MIN_HEIGHT in self.tags:
            self.min_height = op.parse_length(self.tags[s.K_MIN_HEIGHT])

        # a bit of sanity
        if proxy_roof_height == 0. and self.roof_complex:
            proxy_roof_height = calc_level_height_for_settlement_type(self.zone.settlement_type)
            if proxy_total_height > 0.:  # a bit of sanity
                proxy_roof_height = min(proxy_roof_height, proxy_total_height / 2)
        if proxy_body_height > 0. and proxy_total_height == 0.:
            pass  # proxy_total_height = proxy_roof_height + proxy_body_height + self.min_height
        elif proxy_body_height == 0. and proxy_total_height > 0.:
            proxy_body_height = proxy_total_height - proxy_roof_height - self.min_height

        proxy_levels = _parse_building_levels(self.tags)

        # Now that we have all what OSM provides, use some heuristics, if we are missing height/levels.
        # The most important distinction is whether the building is in a relationship, because if yes then the
        # height given needs to be respected to make sure that e.g. a building:part dome actually sits a the right
        # position on the top
        level_height = self._calculate_level_height()
        if building_parent and proxy_body_height > 0.:
            # set proxy levels as a float without rounding and disregard if level would be defined at all
            proxy_levels = proxy_body_height / level_height

        else:
            if proxy_body_height == 0.:
                if proxy_levels == 0:  # else just go with the existing levels
                    proxy_levels = self._calculate_levels()
            else:
                # calculate the levels rounded based on height if levels is undefined
                # else just use the existing levels as they have precedence over height
                if proxy_levels == 0:
                    proxy_levels = round(proxy_body_height / level_height)
            proxy_body_height = level_height * proxy_levels

        self.body_height = proxy_body_height
        self.levels = proxy_levels

        # now respect building min height parameter
        proxy_total_height = self.body_height + self.min_height + proxy_roof_height
        if parameters.BUILDING_MIN_HEIGHT > 0.0 and proxy_total_height < parameters.BUILDING_MIN_HEIGHT:
            raise ValueError('The height given or calculated is less then the BUILDING_MIN_HEIGHT parameter.')

    def _calculate_levels(self) -> int:
        from osm2city.owbb import models as m
        if isinstance(self.zone, m.CityBlock) and self.zone.building_levels > 0:
            return self.zone.building_levels
        elif isinstance(self.zone, m.BuildingZone) \
                and self.zone.type_ is enu.BuildingZoneType.aerodrome:
            return parameters.BUILDING_NUMBER_LEVELS_AEROWAY
        else:
            building_class = enu.get_building_class(self.tags)
            my_levels = calc_levels_for_settlement_type(self.zone.settlement_type, building_class)
            # make corrections for steep slopes
            if building_class in [enu.BuildingClass.residential, enu.BuildingClass.residential_small,
                                  enu.BuildingClass.apartments]:
                if self.diff_elev >= 0.5 and my_levels == 1:
                    my_levels += 1
                elif self.diff_elev >= 1.0 and my_levels > 1:
                    my_levels += 1
            return my_levels

    def _calculate_level_height(self) -> float:
        from osm2city.owbb import models as m
        if isinstance(self.zone, m.BuildingZone) \
                and self.zone.type_ is enu.BuildingZoneType.aerodrome:
            return parameters.BUILDING_LEVEL_HEIGHT_AEROWAY

        building_class = enu.get_building_class(self.tags)
        if building_class in [enu.BuildingClass.industrial, enu.BuildingClass.warehouse]:
            return enu.BUILDING_LEVEL_HEIGHT_INDUSTRIAL
        elif building_class in [enu.BuildingClass.commercial, enu.BuildingClass.retail, enu.BuildingClass.public,
                                enu.BuildingClass.parking_house]:
            return enu.BUILDING_LEVEL_HEIGHT_URBAN
        return calc_level_height_for_settlement_type(self.zone.settlement_type)

    def analyse_roof_shape_check(self) -> None:
        """Check whether we actually may use something else than a flat roof."""
        # roof_shape from OSM is already set in analyse_height_and_levels(...)
        if self.roof_complex:
            allow_complex_roofs = False
            if parameters.BUILDING_COMPLEX_ROOFS:  # Attention: due to elif's the sequence is important!
                allow_complex_roofs = True
                # no complex roof on tall buildings
                if self.levels > parameters.BUILDING_COMPLEX_ROOFS_MAX_LEVELS and s.K_ROOF_SHAPE not in self.tags:
                    allow_complex_roofs = False
                # no complex roof on tiny buildings.
                elif self.levels < parameters.BUILDING_COMPLEX_ROOFS_MIN_LEVELS and s.K_ROOF_SHAPE not in self.tags:
                    allow_complex_roofs = False
                # no complex roof on large buildings
                elif self.area > parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA:
                    allow_complex_roofs = False
                # if the area is between thresholds, then have a look at the ratio between area and circumference:
                # the smaller the ratio, the less deep the building is compared to its length.
                # It is more common to have long houses with complex roofs than a square once it is a big building.
                elif parameters.BUILDING_COMPLEX_ROOFS_MIN_RATIO_AREA < self.area < \
                        parameters.BUILDING_COMPLEX_ROOFS_MAX_AREA:
                    if roofs.roof_looks_square(self.circumference, self.area):
                        allow_complex_roofs = False
                # no complex roof on buildings with inner rings
                elif self.polygon.interiors:
                    if len(self.polygon.interiors) == 1:
                        self.roof_shape = enu.RoofShape.skeleton
                    else:
                        allow_complex_roofs = False
                elif self.roof_shape not in [enu.RoofShape.pyramidal, enu.RoofShape.dome, enu.RoofShape.onion,
                                             enu.RoofShape.skillion] \
                        and self.pts_all_count > parameters.BUILDING_SKEL_MAX_NODES:
                    allow_complex_roofs = False

            # make sure roof shape is flat if we are not allowed to use it
            if allow_complex_roofs is False:
                self.roof_shape = enu.RoofShape.flat

    def _calc_ridge_orientation(self, nodes_dict: Dict[int, op.Node], transformation: co.Transformation) -> None:
        """Calculates the roof orientation for roofs with neighbours for OSM buildings.

        (Only used for buildings in meshes. Generated buildings do not have neighbours, but have a street angle.)

        There is a possibility that the there is more than one neighbour or that the same neighbour
        has more than 2 edges shared. Therefore we assume that the longest shared edge is representative
        for the side of the roof, which is 90 degrees to the ridge respectively is a gable end.
        """
        longest_distance = 0
        for node_positions in self.refs_shared.values():
            if len(node_positions) < 2:  # not interested in neighbours with only one common node
                continue
            for i in node_positions:
                first_pos = -1
                second_pos = -1
                # if we have the last node, then try to connect it with the first
                if i == (len(self.refs) - 1) and 0 in node_positions:
                    first_pos = i
                    second_pos = 0
                elif (i + 1) in node_positions:
                    first_pos = i
                    second_pos = i + 1
                if first_pos > -1:
                    first_node = nodes_dict[self.refs[first_pos]]
                    second_node = nodes_dict[self.refs[second_pos]]
                    orientation = co.calc_angle_of_line_global(first_node.lon, first_node.lat,
                                                               second_node.lon, second_node.lat, transformation)
                    distance = co.calc_distance_global(first_node.lon, first_node.lat,
                                                       second_node.lon, second_node.lat)
                    if distance > longest_distance:
                        longest_distance = distance
                        if self.roof_hint is None:
                            self.roof_hint = roofs.RoofHint()
                        self.roof_hint.ridge_orientation = orientation + 90  # add 90 to the gable end orient. -> ridge
                        if self.roof_hint.ridge_orientation > 180:
                            self.roof_hint.ridge_orientation -= 180

    def _calc_inner_node(self, nodes_dict: Dict[int, op.Node], transformation: co.Transformation) -> None:
        """For L-shaped roofs with at least one neighbour or a 4-edge building with 2 neighbours around a corner.
        See description in roofs.RoofHint.
        There are lots of situations, when it does not get an L-shaped roof, e.g. depending on where the neighbours
        are.
        """
        diff_degs = 20  # maximum allowed difference in degrees
        # exclude all irrelevant
        if len(self.refs) < 4 or len(self.refs) > 6:
            return
        if len(self.refs_shared) == 0 or len(self.refs_shared) > 2:
            return

        # make sure that the shared sides of other buildings are a whole side and not just part of a side of another
        # building and that max 2 points are shared.
        refs_shared_ok = dict()
        for neighbour_building in self.refs_shared.keys():
            if self in neighbour_building.refs_shared:
                refs_shared = list(neighbour_building.refs_shared[self])
                if len(refs_shared) != 2:
                    continue
                # check whether the node before the first shared is at least diff_degs away
                prev_index = refs_shared[0] - 1
                if prev_index < 0:
                    prev_index = len(neighbour_building.refs) - 1
                next_index = refs_shared[0] + 1
                if next_index == len(neighbour_building.refs):
                    next_index = 0
                delta = calc_angle_of_nodes(neighbour_building.refs[prev_index],
                                            neighbour_building.refs[refs_shared[0]],
                                            neighbour_building.refs[next_index],
                                            nodes_dict, transformation)
                if fabs(delta) < diff_degs:
                    continue
                # check whether the node after the second shared is at least diff_degs away
                prev_index = refs_shared[1] - 1
                if prev_index < 0:
                    prev_index = len(neighbour_building.refs) - 1
                next_index = refs_shared[1] + 1
                if next_index == len(neighbour_building.refs):
                    next_index = 0
                delta = calc_angle_of_nodes(neighbour_building.refs[prev_index],
                                            neighbour_building.refs[refs_shared[1]],
                                            neighbour_building.refs[next_index],
                                            nodes_dict, transformation)
                if fabs(delta) < diff_degs:
                    continue
                # shared refs op neighbour fulfills all criteria -> copy
                refs_shared_ok[neighbour_building] = self.refs_shared[neighbour_building]

        # test whether there is a common reference position if there are two neighbours
        # the outcome is used differently for 4, 5 or nodes
        common_set = set()
        neighbours_common_set = set()
        if len(refs_shared_ok) == 2:
            first_set = None
            second_set = None
            for ref_list in refs_shared_ok.values():
                if first_set is None:
                    first_set = set(ref_list)
                    if len(first_set) != 2:  # only interested if a neighbour shares 2 points
                        first_set = set()
                else:
                    second_set = set(ref_list)
                    if len(second_set) != 2:
                        second_set = set()
            common_set = first_set.intersection(second_set)

            first_set = None
            second_set = None
            for key in refs_shared_ok.keys():
                if first_set is None:
                    first_set = set(key.refs)
                else:
                    second_set = set(key.refs)
            neighbours_common_set = first_set.intersection(second_set)

        if len(self.refs) == 4 and len(refs_shared_ok) == 2:  # theoretically there could be 3 or 4 neighbours
            # Just need to find the node, which is shared with two buildings - if any
            if len(common_set) == 1 and len(neighbours_common_set) == 1:
                if self.roof_hint is None:
                    self.roof_hint = roofs.RoofHint()
                node = nodes_dict[self.refs[common_set.pop()]]
                self.roof_hint.inner_node = transformation.to_local((node.lon, node.lat))

        elif (len(self.refs) == 5 or len(self.refs) == 6) and 1 <= len(refs_shared_ok) <= 2 and len(common_set) == 0:
            # find the inner node - if +/- 10 deg limits of straight line
            for index in range(0, len(self.refs)):
                pref_index = len(self.refs) - 1 if index == 0 else index - 1
                if index == 0:
                    prev_ref = self.refs[-1]
                else:
                    prev_ref = self.refs[index - 1]
                next_index = 0 if index == len(self.refs) - 1 else index + 1
                if index == len(self.refs) - 1:
                    next_ref = self.refs[0]
                else:
                    next_ref = self.refs[index + 1]
                corner_ref = self.refs[index]
                corner_node = nodes_dict[corner_ref]
                corner_local = transformation.to_local(corner_node.lon_lat_tuple)
                delta = calc_angle_of_nodes(prev_ref, corner_ref, next_ref, nodes_dict, transformation)
                if len(self.refs) == 5 and fabs(delta) < diff_degs:
                    # test that it actually is shared with a neighbour
                    all_good = 0
                    before_inner_is_shared = False
                    index_in_ref_list = True
                    for ref_list in refs_shared_ok.values():
                        if pref_index in ref_list or next_index in ref_list:
                            if len(refs_shared_ok) == 1:
                                all_good = 2
                            else:
                                all_good += 1
                        if index in ref_list:
                            index_in_ref_list = True
                            if pref_index in ref_list:
                                before_inner_is_shared = True
                    if all_good == 2 and index_in_ref_list:
                        if self.roof_hint is None:
                            self.roof_hint = roofs.RoofHint()
                        self.roof_hint.inner_node = corner_local
                        self.roof_hint.node_before_inner_is_shared = before_inner_is_shared
                    break  # there can only be one such situation if the shape is kind of rectangular
                elif len(self.refs) == 6 and delta > 0 and fabs(delta - 90) < diff_degs:  # with clock
                    # test that it is not shared with a neighbour
                    found = False
                    for ref_list in refs_shared_ok.values():
                        if index in ref_list:
                            found = True
                            break  # it is shared and therefor if cannot be a valid L-shape roof
                    if not found:
                        # test that neighbours just before and just after inner node
                        all_good = 0
                        for ref_list in refs_shared_ok.values():
                            if pref_index in ref_list or next_index in ref_list:
                                if len(refs_shared_ok) == 1:
                                    all_good = 2
                                else:
                                    all_good += 1
                        if all_good == 2:
                            if self.roof_hint is None:
                                self.roof_hint = roofs.RoofHint()
                            self.roof_hint.inner_node = corner_local
                    break  # there can only be one such situation if the shape is kind of L-shaped

    def calc_roof_hints(self, nodes_dict: Dict[int, op.Node], transformation: co.Transformation) -> None:
        if self.has_inner or self.has_neighbours is False:
            return
        self._calc_ridge_orientation(nodes_dict, transformation)
        self._calc_inner_node(nodes_dict, transformation)

    def calc_roof_list_orientation(self) -> int:
        """Roof orientation for buildings in lists: 0 = parallel to front, 1 = orthogonal to front.

        See README.scenery in FGDATA/docs.

        For buildings in meshes the orientation was calculated in analyse_roof_neighbour_orientation.
        """
        front_is_longest = self.width >= self.depth
        if s.K_ROOF_ORIENTATION in self.tags:  # if OSM data has hints, use them
            osm_roof_orientation = str(self.tags[s.K_ROOF_ORIENTATION])
            if osm_roof_orientation == s.V_ALONG:
                if front_is_longest:
                    return 0
                else:
                    return 1
            elif osm_roof_orientation == s.V_ACROSS:
                if front_is_longest:
                    return 1
                else:
                    return 0
            # else follow through next checks
        if self.has_neighbours:  # assume like in European inner cities and most row houses
            return 0
        # just look at the width/depth
        if front_is_longest:
            return 0
        return 1

    def is_too_small_building(self) -> bool:
        """Checks whether a given building's area is too small for inclusion.
        Never drop tall buildings.
        Returns true if the building should be included (i.e. area is big enough etc.)
        """
        if self.inner_rings_list:  # never skip a building with inner rings
            return False
        if self.has_parent:
            if self.area < parameters.BUILDING_MIN_AREA:
                return True
            if self.area < parameters.BUILDING_REDUCE_THRESHOLD and (
                    random.uniform(0, 1) < parameters.BUILDING_REDUCE_RATE):
                proxy_levels = _parse_building_levels(self.tags)
                if proxy_levels > 0:
                    if proxy_levels >= parameters.BUILDING_NEVER_REDUCE_LEVELS:
                        return False
                return True
        return False

    def compute_roof_height(self, in_building_list: bool = False) -> None:
        """Compute roof_height for each node"""

        self.roof_height = 0.
        temp_roof_height = 0.  # temp variable before assigning to self

        if self.roof_shape is enu.RoofShape.skillion and (in_building_list is False):
            # get global roof_height and height for each vertex
            if s.K_ROOF_HEIGHT in self.tags:
                # force clean of tag if the unit is given
                temp_roof_height = op.parse_length(self.tags[s.K_ROOF_HEIGHT])
            else:
                if s.K_ROOF_ANGLE in self.tags and op.is_parsable_float(self.tags[s.K_ROOF_ANGLE]):
                    angle = float(self.tags[s.K_ROOF_ANGLE])
                    while angle > 0:
                        temp_roof_height = tan(np.deg2rad(angle)) * (self.edge_length_pts[1] / 2)
                        if temp_roof_height < parameters.BUILDING_SKILLION_ROOF_MAX_HEIGHT:
                            break
                        angle -= 1
                else:
                    temp_roof_height = calc_level_height_for_settlement_type(self.zone.settlement_type)

            if s.K_ROOF_SLOPE_DIRECTION in self.tags:
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
                angle00 = pi / 2. - (((op.parse_direction(self.tags[s.K_ROOF_SLOPE_DIRECTION])) % 360.)
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

            p0 = (self.pts_all[0][0], self.pts_all[0][1])
            for i in range(0, len(self.pts_all)):
                # compute coord in new referential
                vecA = (self.pts_all[i][0] - p0[0], self.pts_all[i][1] - p0[1])
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
                           range(0, len(self.pts_all))]  # oriented norm
            else:
                norms_o = nXN

            # compute height for each point with thales
            L = float(max(norms_o))

            self.roof_height_pts = [temp_roof_height * l / L for l in norms_o]
            self.roof_height = temp_roof_height

        else:  # roof types other than skillion
            if s.K_ROOF_HEIGHT in self.tags:
                # get roof:height given by osm
                self.roof_height = op.parse_length(self.tags[s.K_ROOF_HEIGHT])

            else:  # roof:height based on heuristics
                if self.roof_shape is enu.RoofShape.flat:
                    self.roof_height = 0.
                else:
                    if s.K_ROOF_ANGLE in self.tags and op.is_parsable_float(self.tags[s.K_ROOF_ANGLE]):
                        angle = float(self.tags[s.K_ROOF_ANGLE])
                        while angle > 0:
                            temp_roof_height = tan(np.deg2rad(angle)) * (self.edge_length_pts[1] / 2)
                            if temp_roof_height < parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT:
                                break
                            angle -= 5
                        if temp_roof_height > parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT:
                            temp_roof_height = parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT
                    else:  # use the same as level height
                        temp_roof_height = calc_level_height_for_settlement_type(self.zone.settlement_type)
                    self.roof_height = temp_roof_height

    def write_vertices_for_ac_ground(self, ac_object: ac3d.Object) -> None:
        """Write the vertices for each node along bottom of the building to the ac3d object."""
        z = self.ground_elev + self.min_height

        # ground nodes
        for pt in self.pts_all:
            ac_object.node(-pt[1], z, -pt[0])

    def write_vertices_for_ac_under_roof(self, ac_object: ac3d.Object) -> None:
        """Write the vertices for each node under the roof of the building to the ac3d object."""
        if self.roof_shape is enu.RoofShape.skillion:
            # skillion
            #           __ -+
            #     __-+--    |
            #  +--          |
            #  |            |
            #  +-----+------+
            #
            if self.roof_height_pts:
                for i in range(len(self.pts_all)):
                    ac_object.node(-self.pts_all[i][1],
                                   self.beginning_of_roof_above_sea_level + self.roof_height_pts[i],
                                   -self.pts_all[i][0])
        else:
            # others roofs
            #
            #  +-----+------+
            #  |            |
            #  +-----+------+
            #
            for pt in self.pts_all:
                ac_object.node(-pt[1], self.beginning_of_roof_above_sea_level, -pt[0])

    def write_faces_for_ac(self, ac_object: ac3d.Object, ring: shg.LinearRing,
                           index_first_node_in_ac_obj: int, number_prev_ring_nodes: int, mat_idx: int) -> int:
        """Writes all the faces for one building's exterior or interior ring to an ac3d object."""
        tex_coord_bottom, tex_coord_top = _calculate_vertical_texture_coords(self.body_height, self.facade_texture)
        tex_coord_bottom = self.facade_texture.y(tex_coord_bottom)  # -- to atlas coordinates
        tex_coord_top_input = tex_coord_top
        tex_coord_top = self.facade_texture.y(tex_coord_top)

        number_ring_nodes = len(ring.coords) - 1

        for ioff in range(0, number_ring_nodes):
            i = number_prev_ring_nodes + ioff

            if ioff < number_ring_nodes - 1:
                ipp = i + 1
            else:
                ipp = number_prev_ring_nodes
            # FIXME: respect facade texture split_h
            # FIXME: there is a nan in textures.h_splits of tex/facade_modern36x36_12
            tex_coord_right = self.facade_texture.x(self.edge_length_pts[i] / self.facade_texture.h_size_meters)
            if self.facade_texture.v_can_repeat:
                if not (tex_coord_right <= 1.):
                    logging.debug('FIXME: v_can_repeat: need to check in analyse')

            if self.roof_shape is enu.RoofShape.skillion and tex_coord_top_input != 0:
                tex_y12 = self.facade_texture.y((self.body_height + self.roof_height_pts[i]) /
                                                self.body_height * tex_coord_top_input)
                tex_y11 = self.facade_texture.y((self.body_height + self.roof_height_pts[ipp]) /
                                                self.body_height * tex_coord_top_input)
            else:
                tex_y12 = tex_coord_top
                tex_y11 = tex_coord_top

            tex_coord_left = self.facade_texture.x(0)

            ac_object.face([(i + index_first_node_in_ac_obj, tex_coord_left, tex_coord_bottom),
                            (ipp + index_first_node_in_ac_obj, tex_coord_right, tex_coord_bottom),
                            (ipp + index_first_node_in_ac_obj + self.pts_all_count, tex_coord_right, tex_y11),
                            (i + index_first_node_in_ac_obj + self.pts_all_count, tex_coord_left, tex_y12)],
                           mat_idx=mat_idx,
                           swap_uv=self.facade_texture.v_can_repeat)
        return number_ring_nodes

    def _write_flat_roof(self, ac_object: ac3d.Object, roof_mgr: mgr.RoofManager, roof_mat_idx: int) -> None:
        self.roof_shape = enu.RoofShape.flat  # shape might have been reset to flat
        node_index = ac_object.next_node_index()
        self.write_vertices_for_ac_under_roof(ac_object)
        roofs.flat(ac_object, node_index, self, roof_mgr, roof_mat_idx)

    def _write_skillion_roof(self, ac_object: ac3d.Object, roof_mat_idx: int) -> None:
        self.write_vertices_for_ac_under_roof(ac_object)
        print('skillion', self.osm_id)
        roofs.separate_skillion(ac_object, self, roof_mat_idx)

    def write_roof_for_ac(self, ac_object: ac3d.Object,
                          roof_mgr: mgr.RoofManager, roof_mat_idx: int, facade_mat_idx: int,
                          cluster_offset: co.Vec2d) -> None:
        """Writes the roof vertices and faces to an ac3d object."""
        if self.roof_shape is enu.RoofShape.flat:
            self._write_flat_roof(ac_object, roof_mgr, roof_mat_idx)
        elif 4 <= self.pts_all_count <= 6 and (
                    self.roof_hint is not None and self.roof_hint.inner_node is not None):
            roofs.separate_gable_with_corner(ac_object, self, roof_mat_idx, facade_mat_idx)
        else:
            my_cluster_offset = cluster_offset
            # try to see whether we can reduce the number of nodes - and maybe get the count down - such that fewer
            # gabled and gambrel get changed to skeleton.
            # skillion may not be changed due to numbers from _compute_roof_height
            if (self.pts_all_count > 4) and (self.has_inner is False) and \
                    (self.roof_shape is not enu.RoofShape.skillion):
                roof_polygon = shg.Polygon(self.pts_all)  # because the current polygon is not current anymore
                my_number = len(roof_polygon.exterior.coords) - 1
                roof_polygon_new = roof_polygon.simplify(parameters.BUILDING_ROOF_SIMPLIFY_TOLERANCE, True)
                my_new_number = len(roof_polygon_new.exterior.coords) - 1
                # if the node to be removed would be the first, then topology would be changed. So change sequence
                # and try again
                if my_number == my_new_number:
                    alternative_points = self.pts_all[1:].tolist()
                    alternative_points.append(self.pts_all[0].tolist())
                    roof_polygon = shg.Polygon(alternative_points)
                    roof_polygon_new = roof_polygon.simplify(parameters.BUILDING_ROOF_SIMPLIFY_TOLERANCE, True)
                    my_new_number = len(roof_polygon_new.exterior.coords) - 1

                if my_number > my_new_number:
                    self.pts_all = np.array(roof_polygon_new.exterior.coords)[:-1]
                    self.polygon = roof_polygon_new  # needed to get correct .pts_all_count
                    # reset cluster offset as we are using translated clusters
                    my_cluster_offset = co.Vec2d(0, 0)
            # -- pitched roof for exactly 4 ground nodes
            if self.pts_all_count == 4:
                if self.roof_shape in [enu.RoofShape.gabled, enu.RoofShape.gambrel]:
                    roofs.separate_gable(ac_object, self, roof_mat_idx, facade_mat_idx)
                elif self.roof_shape is enu.RoofShape.hipped:
                    roofs.separate_hipped(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.pyramidal:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.dome:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.onion:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.skillion:
                    self._write_skillion_roof(ac_object, roof_mat_idx)
                else:
                    logging.warning("Roof type %s seems to be unsupported, but is mapped: replaced by flat roof",
                                    self.roof_shape.name)
                    self._write_flat_roof(ac_object, roof_mgr, roof_mat_idx)
            # -- pitched roof for > 4 ground nodes
            elif self.pts_all_count > 4:
                if self.roof_shape is enu.RoofShape.skillion:
                    self._write_skillion_roof(ac_object, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.pyramidal:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.dome:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                elif self.roof_shape is enu.RoofShape.onion:
                    roofs.separate_pyramidal(ac_object, self, roof_mat_idx)
                else:
                    skeleton_possible = myskeleton.myskel(ac_object, self, offset_xy=my_cluster_offset,
                                                          offset_z=self.beginning_of_roof_above_sea_level,
                                                          max_height=parameters.BUILDING_SKEL_ROOF_MAX_HEIGHT)
                    if not skeleton_possible:  # something went wrong - fall back to flat roof
                        self._write_flat_roof(ac_object, roof_mgr, roof_mat_idx)
            else:  # fall back to pyramidal
                self.roof_shape = enu.RoofShape.pyramidal
                roofs.separate_pyramidal(ac_object, self, roof_mat_idx)

    def __str__(self):
        return "<OSM_ID %d at %s>" % (self.osm_id, hex(id(self)))


def calc_angle_of_nodes(pref_ref: int, corner_ref: int, next_ref: int,
                        nodes_dict: Dict[int, op.Node], transformation: co.Transformation) -> float:
    prev_node = nodes_dict[pref_ref]
    corner_node = nodes_dict[corner_ref]
    next_node = nodes_dict[next_ref]
    prev_local = transformation.to_local(prev_node.lon_lat_tuple)
    corner_local = transformation.to_local(corner_node.lon_lat_tuple)
    next_local = transformation.to_local(next_node.lon_lat_tuple)
    angle_1 = co.calc_angle_of_line_local(prev_local[0], prev_local[1], corner_local[0], corner_local[1])
    angle_2 = co.calc_angle_of_line_local(corner_local[0], corner_local[1], next_local[0], next_local[1])
    return co.calc_delta_bearing(angle_1, angle_2)


class BuildingParent(object):
    """The parent of buildings that are part of a Simple3D building with an outline building.
    Alternatively virtual parent for combinations of OSM building and OSM building:part.
    Mostly used to coordinate textures for facades and roofs.
    The parts determine the common textures by a simple rule: the first to set the values wins the race.
    """
    __slots__ = ('osm_id', 'outline', 'children', 'tags')

    def __init__(self, osm_id: int, outline: bool) -> None:
        self.osm_id = osm_id  # By convention the osm_id of the outline building, not the relation id from OSM!
        self.outline = outline  # True if based on a Simple3D building. False if based on building:part
        self.children = list()  # pointers to Building objects. Those building objects point back in self.parent
        self.tags = dict()

    def add_child(self, child: Building) -> None:
        """Adds the building to the children and adds a pointer back from the child"""
        self.children.append(child)
        child.parent = self

    def remove_child(self, child: Building) -> None:
        self.children.remove(child)
        child.parent = None

    def contains_child(self, child: Building) -> bool:
        return child in self.children

    def add_tags(self, tags: Dict[str, str]) -> None:
        """The added tags are either from the outline if simple3d or otherwise from the original building
        used as a parent for building_parts, if not relation was given."""
        self.tags = tags

    def align_textures_children(self, facade_mgr: mgr.FacadeManager, roof_mgr: mgr.RoofManager) -> bool:
        """Aligns the facade and roof textures for all the children belonging to this parent.
        Per default the building colour and building material of the child with the largest longest_edge_len is chosen.
        Then the rest of the children are searched for colour/material and the first one wins.
        Finally the default is used to analyse for textures again with whatever colour/material was there, and this
        time the height of the highest child is used.
        If the analysis does return a result, then the texture is used for all children. Otherwise False is
        returned and the whole BuildingParent with all its buildings is removed.
        """
        if len(self.children) == 0:  # might be sanitize_children() has removed them all
            return True

        # first find the child with the longest edge
        default_child = None
        for child in self.children:
            if default_child is None:
                default_child = child
            elif child.longest_edge_length > default_child.longest_edge_length:
                default_child = child

        # find out if we can find hints for real material
        largest_body_height = default_child.body_height
        building_colour = None
        building_material = None
        if s.K_BUILDING_COLOUR in default_child.tags:
            building_colour = default_child.tags[s.K_BUILDING_COLOUR]
        if s.K_BUILDING_MATERIAL in default_child.tags:
            building_material = default_child.tags[s.K_BUILDING_MATERIAL]

        for child in self.children:
            if child is default_child:
                continue
            if building_colour is None and s.K_BUILDING_COLOUR in child.tags:
                building_colour = child.tags[s.K_BUILDING_COLOUR]
            if building_material is None and s.K_BUILDING_MATERIAL in child.tags:
                building_material = child.tags[s.K_BUILDING_MATERIAL]
            largest_body_height = max(largest_body_height, child.body_height)

        if s.K_BUILDING_COLOUR not in default_child.tags and building_colour:
            default_child.tags[s.K_BUILDING_COLOUR] = building_colour
        if s.K_BUILDING_MATERIAL not in default_child.tags and building_material:
            default_child.tags[s.K_BUILDING_MATERIAL] = building_material

        # now that everything is in place, analyse for texture again
        try:
            default_child.analyse_textures(facade_mgr, roof_mgr, largest_body_height)
            if default_child.facade_texture is None:
                return False
        except Exception:
            pass

        # apply same textures to all children
        for child in self.children:
            if child is default_child:
                continue
            child.facade_texture = default_child.facade_texture
            child.roof_texture = default_child.roof_texture
        return True

    @staticmethod
    def get_building_parents(my_buildings: List[Building]) -> Set['BuildingParent']:
        building_parents = set()
        for building in my_buildings:
            if building.parent:
                building_parents.add(building.parent)
        return building_parents

    def transfer_children(self, other_parent: 'BuildingParent') -> None:
        """Transfer all children from this parent to another.
        Once all children have a new parent then there will be no pointers to this one -> no del of children necessary.
        """
        for child in self.children:
            other_parent.add_child(child)
            self.remove_child(child)

    @staticmethod
    def clean_building_parents_dangling_children(my_buildings: List[Building]) -> None:
        """Make sure that buildings with a parent, which only has this child, gets no parent.
        There is no point in BuildingParent, if there is only one child."""
        building_parents = BuildingParent.get_building_parents(my_buildings)

        for parent in building_parents:
            # remove no longer valid children
            for child in reversed(parent.children):
                if child not in my_buildings:
                    parent.remove_child(child)

            parent.make_sure_lone_building_in_parent_stands_alone()

    def make_sure_lone_building_in_parent_stands_alone(self) -> None:
        """If only one child left, then inherit tags from parent and make it stand alone"""
        if len(self.children) == 1:
            building = self.children[0]
            building.make_building_from_part()
            for key, value in building.parent.tags.items():
                if key not in building.tags:
                    building.tags[key] = value
            building.parent = None


def _parse_building_levels(tags: Dict[str, str]) -> float:
    proxy_levels = 0.
    if s.K_BUILDING_LEVELS in tags:
        if ';' in tags[s.K_BUILDING_LEVELS]:
            proxy_levels = float(op.parse_multi_int_values(tags[s.K_BUILDING_LEVELS]))
        elif op.is_parsable_float(tags[s.K_BUILDING_LEVELS]):
            proxy_levels = float(tags[s.K_BUILDING_LEVELS])
    if s.K_LEVELS in tags:
        if ';' in tags[s.K_LEVELS]:
            proxy_levels = float(op.parse_multi_int_values(tags[s.K_LEVELS]))
        elif op.is_parsable_float(tags[s.K_LEVELS]):
            proxy_levels = float(tags[s.K_LEVELS])
    return proxy_levels


def _calculate_vertical_texture_coords(body_height: float, t: mgr.FacadeTexture) -> Tuple[float, float]:
    """Check if a texture t fits the building's body_height (h) and return bottom and top relative position of the tex.
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
                logging.debug("from bottom")
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


def analyse(buildings: List[Building], fg_elev: utilities.FGElev, stg_manager: stg_io2.STGManager,
            coords_transform: co.Transformation,
            facade_mgr: mgr.FacadeManager, roof_mgr: mgr.RoofManager) -> List[Building]:
    """Analyse all buildings and either link directly static models or specify Building objects.
    The static models are directly added to stg_manager. The Building objects get properties set and will later
    get transformed to dynamically created AC3D files containing a cluster of buildings.
    Some OSM buildings are excluded from analysis, as they get processed in pylons.py.
    """
    new_buildings = []
    for b in buildings:
        if b.parent is None:
            building_parent = None
        else:
            building_parent = b.parent
            building_parent.remove_child(b)

        # handle places of worship
        if s.K_BUILDING in b.tags and parameters.BUILDING_USE_SHARED_WORSHIP:
            if _analyse_worship_building(b, building_parent, stg_manager, fg_elev, coords_transform):
                continue

        try:
            b.roll_inner_nodes()
        except Exception as reason:
            logging.warning("Roll_inner_nodes failed (OSM ID %i, %s)", b.osm_id, reason)
            continue

        if not b.analyse_elev_and_water(fg_elev):
            continue

        b.analyse_edge_lengths()

        b.analyse_street_angle()

        b.analyse_roof_shape(building_parent)

        b.analyse_building_type()

        try:
            b.analyse_height_and_levels(building_parent)
        except ValueError as e:
            logging.debug('Skipping building osm_id = {}: {}'.format(b.osm_id, e))
            continue

        b.analyse_roof_shape_check()

        if not b.analyse_textures(facade_mgr, roof_mgr, b.body_height):
            continue

        # -- finally: append building to new list
        new_buildings.append(b)
        if building_parent is not None:
            building_parent.add_child(b)

    # work with parents to align textures and stuff
    BuildingParent.clean_building_parents_dangling_children(new_buildings)

    building_parents = BuildingParent.get_building_parents(new_buildings)
    for parent in building_parents:
        found = parent.align_textures_children(facade_mgr, roof_mgr)
        if not found:
            for building in parent.children:
                building.parent = None
                try:
                    new_buildings.remove(building)
                except ValueError:
                    pass  # building might not have been added to new_buildings, but have been referenced to parent
                logging.warning('Removing building osm_id=%i due to no matching texture in parent', building.osm_id)

    # make sure that min_height is only used if there is a real parent (not pseudo_parents)
    # i.e. for all others we just set it to 0.0
    for building in new_buildings:
        if building.parent is None:
            building.min_height = 0.0

    return new_buildings


def _buildings_after_remove_with_parent_children(orig_buildings: List[Building],
                                                 buildings_to_remove: List[Building]) -> List[Building]:
    """Returns a list of buildings, which are in the original list, but which are neither in the list
    to remove or those buildings' parents' related children.

    We do this such that there are no dangling children, which somehow are still related to a parent, but not
    through a direct link in the final list of buildings, which later gets analyzed.
    And because most probably if part of a buildings relation is overlapped, then the whole Simple3D
    building should go away."""
    all_buildings_to_remove = set()

    for building in buildings_to_remove:
        if building.parent:
            for child in building.parent.children:
                all_buildings_to_remove.add(child)
        all_buildings_to_remove.add(building)

    cleared_buildings = list()
    for building in orig_buildings:
        if building not in all_buildings_to_remove:
            cleared_buildings.append(building)

    return cleared_buildings


def overlap_check_blocked_areas(orig_buildings: List[Building], blocked_areas: List[shg.Polygon]) -> List[Building]:
    """Checks each building whether it overlaps with a blocked area and excludes it from the returned list of True.
    Uses intersection checking - i.e. not touches or disjoint."""
    buildings_to_remove = list()
    for building in orig_buildings:
        is_intersected = False
        for blocked_area in blocked_areas:
            if building.geometry.intersects(blocked_area) or building.geometry.within(blocked_area):
                logging.debug("Building osm_id=%d intersects with blocked area.", building.osm_id)
                is_intersected = True
                break
        if is_intersected:
            buildings_to_remove.append(building)
    return _buildings_after_remove_with_parent_children(orig_buildings, buildings_to_remove)


def update_building_tags_in_aerodromes(my_buildings: List[Building]) -> None:
    """Make sure that buildings in aerodromes are tagged such that they look kind of modern."""

    # first run the parents to make sure that all buildings below a building parent get same aeroway tag
    from osm2city.owbb import models as m
    my_parents = set()
    for building in my_buildings:
        if building.parent is not None and isinstance(building.zone, m.BuildingZone) \
                and building.zone.type_ is enu.BuildingZoneType.aerodrome:
            my_parents.add(building.parent)

    for building_parent in my_parents:
        aeroway_values = list()
        for child in building_parent.children:
            if s.K_AEROWAY in child.tags:
                aeroway_values.append(child.tags[s.K_AEROWAY])

        settled_value = s.V_AERO_OTHER
        if len(aeroway_values) == 1:
            settled_value = aeroway_values[0]  # in all other situations (0 or > 1) we do not know what to apply
        for child in building_parent.children:
            if s.K_AEROWAY not in child.tags:
                child.tags[s.K_AEROWAY] = settled_value

    # now do all buildings including roof to make stuff easy in processing
    for building in my_buildings:
        if isinstance(building.zone, m.BuildingZone) \
                and building.zone.type_ is enu.BuildingZoneType.aerodrome:
            if s.K_ROOF_SHAPE not in building.tags:
                building.tags[s.K_ROOF_SHAPE] = s.V_FLAT
            if s.K_AEROWAY not in building.tags:
                building.tags[s.K_AEROWAY] = s.V_AERO_OTHER


def _analyse_worship_building(building: Building, building_parent: BuildingParent,
                              stg_manager: stg_io2.STGManager, fg_elev: utilities.FGElev,
                              coords_transform: co.Transformation) -> bool:
    """Returns True and adds shared model if the building is a worship place and there is a shared model for it.
    If the building has a parent, then it is not handled as it is assumed, that then there is a OSM 3D
    representation, which might be more accurate than a generic shared model.
    """
    if building_parent:
        return False
    worship_building_type = WorshipBuilding.screen_worship_building_type(building.tags)
    if worship_building_type:
        if s.K_NAME in building.tags:
            name = building.tags[s.K_NAME]
        else:
            name = 'No Name'
        # check dimensions and then whether we have an adequate building
        hull = building.polygon.convex_hull
        angle, length, width = utilities.minimum_circumference_rectangle_for_polygon(hull)
        model = WorshipBuilding.find_matching_worship_building(worship_building_type, length, width)
        if model:
            if not model.length_largest:
                angle += 90
            angle = co.normal_degrees(angle)
            x, y = utilities.fit_offsets_for_rectangle_with_hull(angle, hull, model.length, model.width,
                                                                 model.length_offset, model.width_offset,
                                                                 model.length_largest,
                                                                 str(model), building.osm_id)
            lon, lat = coords_transform.to_global((x, y))
            model.lon = lon
            model.lat = lat
            model.angle = angle
            model.elevation, _ = fg_elev.probe_list_of_points(list(hull.exterior.coords)[:-1])
            model.elevation -= model.height_offset
            if model.elevation == -9999:
                logging.debug('Worship building "%s" with osm_id %i is in water or unknown elevation',
                              name, building.osm_id)
                return False

            logging.info('Found static model for worship building "%s" with osm_id %i: %s at angle %d',
                         name, building.osm_id, model.file_name, angle)
            model.make_stg_entry(stg_manager)
            return True
        logging.debug('No static model found for worship building "%s" with osm_id %i', name, building.osm_id)
        return False


class WorshipBuilding(object):
    """Buildings for worshipping.
    The building=* should be applied in tagging according to the architectural style, often such religious buildings
    are recognisable landmarks.
    Whereas WorshipBuildingType describes the architectural category, Architecture style,
    the actual style can be described with building:architecture=*.

    For example, a catholic church can be tagged on the building outline with amenity=place_of_worship +
    religion=christian + denomination=catholic + building=church.
    """
    def __init__(self, file_name: str, has_texture: bool, type_: enu.WorshipBuildingType, style: enu.ArchitectureStyle,
                 number_towers: int, length: float, width: float, height: float,
                 length_offset: float = 0., width_offset: float = 0., height_offset: float = 0.) -> None:
        self.file_name = file_name  # without path - see property shared_model
        self.has_texture = has_texture
        self.type_ = type_
        self.style = style
        self.number_towers = number_towers
        self.length = length
        self.width = width
        self.height = height
        self.length_offset = length_offset
        self.width_offset = width_offset
        self.height_offset = height_offset

        # will be set later
        self.lon = 0.
        self.lat = 0.
        self.elevation = 0.
        self.angle = 0.

    def __str__(self) -> str:
        return self.shared_model

    @property
    def shared_model(self) -> str:
        """The full path to the shared model"""
        return '/Models/Misc/' + self.file_name

    @property
    def length_largest(self) -> bool:
        """Return  True if the lengths is larger than the width. Length is along x-axis.
        Happens to be False (i.e. width along y-axis is longer) if model in AC3D has been done so.
        """
        if self.length >= self.width:
            return True
        return False

    @staticmethod
    def screen_worship_building_type(tags: Dict[str, str]) -> Optional[enu.WorshipBuildingType]:
        """Returns a type if the building is a worship building, for which there might be a shared model.

        This method needs to be in sync with list available_worship_buildings"""
        worship_building_type = enu.deduct_worship_building_type(tags)
        if worship_building_type is not None:
            # now make sure that we actually have a mapped building
            for building in _available_worship_buildings:
                if building.type_ is worship_building_type:
                    return worship_building_type
        return None

    @staticmethod
    def find_matching_worship_building(requested_type: enu.WorshipBuildingType, max_length: float, max_width: float) \
            -> Optional['WorshipBuilding']:
        """Finds a worship building of a given type which satisfies the length/widt constraints.

        Satisfying meaning that the one building is chosen, which has the largest circumference
        measured by a rectangle with the building's length/with.
        """
        best_fit_building = None
        best_fit_circumference = 0
        for model in _available_worship_buildings:
            if model.type_ is requested_type:
                circumference = 2 * (model.length + model.width)
                if (model.length_largest and model.length <= max_length and model.width <= max_width) or (
                        model.length_largest is False and model.width <= max_length and model.length <= max_width):
                    if circumference > best_fit_circumference:
                        best_fit_building = model
                        best_fit_circumference = circumference
        return best_fit_building

    def make_stg_entry(self, my_stg_mgr: stg_io2.STGManager) -> None:
        """Returns a stg entry for this pylon.
        E.g. OBJECT_SHARED Models/Airport/ils.xml 5.313108 45.364122 374.49 268.92
        """
        angle_correction = 0
        if self.length_largest:
            angle_correction = 90
        my_stg_mgr.add_object_shared(self.shared_model, co.Vec2d(self.lon, self.lat),
                                     self.elevation, self.angle - angle_correction)


_available_worship_buildings = [WorshipBuilding('big-church.ac', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.romanesque, 1, 30., 26., 40., width_offset=5.5),
                                WorshipBuilding('breton-church.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 50., 28., 43., length_offset=25.),
                                # WorshipBuilding('Church_generic_twintower_oniondome.ac', False,
                                #                enu.WorshipBuildingType.church,
                                #                enu.ArchitectureStyle.unknown, 2, 22., 37., 34., width_offset=12.5),
                                WorshipBuilding('church36m_blue.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 10., 36.2, 34.5, width_offset=0.9),
                                WorshipBuilding('church36m_blue2.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 10., 36.2, 34.5, width_offset=0.9),
                                WorshipBuilding('church36m_green.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 10., 36.2, 34.5, width_offset=0.9),
                                WorshipBuilding('church36m_red.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 10., 36.2, 34.5, width_offset=0.9),
                                WorshipBuilding('GenChurch_rd.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 46., 110., 120.),
                                WorshipBuilding('generic_cathedral.xml', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.romanesque, 2, 67., 37., 51.),
                                WorshipBuilding('generic_church_01.ac', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.gothic, 1, 68., 124.4, 100., width_offset=11.2),
                                WorshipBuilding('generic_church_02.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 32.4, 71.8, 63.5, width_offset=-1.5),
                                WorshipBuilding('generic_church_03.ac', False, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.unknown, 1, 38., 89.8, 95.),
                                WorshipBuilding('gothical_church.xml', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.gothic, 1, 44., 24.8, 46., length_offset=22.),
                                WorshipBuilding('NDBoulogne.ac', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.romanesque, 3, 42., 82., 81.5),
                                WorshipBuilding('roman_church.xml', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.romanesque, 1, 44., 24.8, 25., length_offset=22.),
                                WorshipBuilding('StVaast.ac', True, enu.WorshipBuildingType.church,
                                                enu.ArchitectureStyle.romanesque, 0, 58., 98., 36.)
                                ]

# WorshipBuilding(eglise.xml, True, church, gothic)  # not aligned to x-axis
# WorshipBuilding(corp-cathedrale.xml, True, cathedral, gothic)  # is not complete: one wall missing
# WorshipBuilding(gen_orthodox_church.ac, True, church_orthodox, unknown)  # not aligned to any axis


@unique
class RectifyBlockedType(IntEnum):
    """Some nodes (RectifyNodes) shall be blocked from changing their angle / position during processing.
    multiple_buildings: if the node is part of more than one building
    ninety_degrees: if the node already is 90 degrees
    corner_to_bow: if the next node(s) is between 180 and 180 - 2*MAX_90_DEVIATIOM, then probably the node
    is part of a curved wall in at least two parts - the more parts the closer the angles in the curve are
    to 180 degrees."""
    multiple_buildings = 10
    ninety_degrees = 20
    corner_to_bow = 30


class RectifyNode(object):
    __slots__ = ('osm_id', 'x', 'original_x', 'y', 'original_y', 'is_updated', 'rectify_building_refs')

    """Represents a OSM Node feature used for rectifying building angles."""
    def __init__(self, osm_id: int, local_x: float, local_y: float) -> None:
        self.osm_id = osm_id
        self.x = local_x  # in local coordinates
        self.original_x = self.x  # should not get updated -> for reference/comparison
        self.y = local_y
        self.original_y = self.y
        self.is_updated = False
        self.rectify_building_refs = list()  # osm_ids

    @property
    def has_related_buildings(self) -> bool:
        return len(self.rectify_building_refs) > 0

    def relates_to_several_buildings(self) -> bool:
        return len(self.rectify_building_refs) > 1

    def update_point(self, new_x: float, new_y: float) -> False:
        self.x = new_x
        self.y = new_y
        self.is_updated = True

    def append_building_ref(self, osm_id: int) -> None:
        self.rectify_building_refs.append(osm_id)


class NodeInRectifyBuilding(object):
    __slots__ = ('angle', 'my_node', 'prev_node', 'next_node', 'blocked_types')

    """Links RectifyNode and RectifyBuilding because a RectifyNode can be linked to multiple buildings."""
    def __init__(self, rectify_node: RectifyNode) -> None:
        self.angle = 0.0  # in degrees. Not guaranteed to be up to date
        self.my_node = rectify_node  # directly linked RectifyNode in this building context (nodes can be shared)
        self.prev_node = None  # type NodeInRectifyBuilding
        self.next_node = None  # type NodeInRectifyBuilding
        self.blocked_types = list()  # list of RectifyBlockedType

    def within_rectify_deviation(self) -> bool:
        return fabs(self.angle - 90) <= parameters.RECTIFY_MAX_90_DEVIATION

    def within_rectify_90_tolerance(self) -> bool:
        return fabs(self.angle - 90) <= parameters.RECTIFY_90_TOLERANCE

    def append_blocked_type(self, append_type: RectifyBlockedType) -> None:
        needs_append = True
        for my_type in self.blocked_types:
            if my_type is append_type:
                needs_append = False
                break
        if needs_append:
            self.blocked_types.append(append_type)

    def is_blocked(self) -> bool:
        return len(self.blocked_types) > 0

    def node_needs_change(self) -> bool:
        if not self.is_blocked():
            if self.within_rectify_deviation():
                if not (self.prev_node.is_blocked() and self.next_node.is_blocked()):
                    return True
        return False

    def update_angle(self) -> None:
        self.angle = co.calc_angle_of_corner_local(self.prev_node.my_node.x, self.prev_node.my_node.y,
                                                   self.my_node.x, self.my_node.y,
                                                   self.next_node.my_node.x, self.next_node.my_node.y)


class RectifyBuilding(object):
    __slots__ = ('osm_id', 'node_refs')

    def __init__(self, osm_id: int, node_refs: List[RectifyNode]) -> None:
        self.osm_id = osm_id
        self.node_refs = list()  # NodeInRectifyBuilding objects
        for ref in node_refs:
            self._append_node_ref(ref)

    def _append_node_ref(self, node: RectifyNode) -> None:
        """Appends a RectifyNode to the node references of this building - and vice versa.
        However do not process last node in way, which is the same as the first one."""
        my_node = NodeInRectifyBuilding(node)
        if not ((len(self.node_refs) > 0) and (node.osm_id == self.node_refs[0].my_node.osm_id)):
            self.node_refs.append(my_node)
            node.append_building_ref(self.osm_id)

    def is_relevant(self) -> bool:
        """Only relevant for rectify processing if at least 4 corners."""
        return len(self.node_refs) > 3

    def classify_and_relate_unchanged_nodes(self) -> bool:
        """Returns True if at least one node is not blocked and falls within deviation."""
        # relate nodes and calculate angle
        for position in range(len(self.node_refs)):
            prev_node = self.node_refs[position - 1]
            corner_node = self.node_refs[position]
            if len(self.node_refs) - 1 == position:
                next_node = self.node_refs[0]
            else:
                next_node = self.node_refs[position + 1]
            corner_node.prev_node = prev_node
            corner_node.next_node = next_node
            corner_node.update_angle()

        # classify nodes
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            if corner_node.my_node.relates_to_several_buildings():
                corner_node.append_blocked_type(RectifyBlockedType.multiple_buildings)
            if corner_node.within_rectify_90_tolerance():
                corner_node.append_blocked_type(RectifyBlockedType.ninety_degrees)
            elif corner_node.within_rectify_deviation():
                max_angle = 180 - 2 * parameters.RECTIFY_MAX_90_DEVIATION
                if corner_node.prev_node.angle >= max_angle or corner_node.next_node.angle >= max_angle:
                    corner_node.append_blocked_type(RectifyBlockedType.corner_to_bow)

        # finally find out whether there is something to change at all
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            if corner_node.node_needs_change():
                return True
        return False

    def rectify_nodes(self):
        """Rectifies all those nodes, which can and shall be changed.

        The algorithm looks at the current node angle and the blocked type of the next node.
        If the next node is blocked, then the current node is moved along the line prev_node-current_node until there
        are 90 degrees.
        If the next node is not blocked then in order to keep as much of the area/geometry similar,
        both the current and the next node are moved a bit. The current node is only moved half the distance,
        and the next node is moved the same distance in the opposite direction.
        Basically a triangle with prev_node (a), current_node (b) and next_node (c)."""
        for position in range(len(self.node_refs)):
            corner_node = self.node_refs[position]
            my_next_node = corner_node.next_node
            my_prev_node = corner_node.prev_node
            corner_node.update_angle()
            if corner_node.node_needs_change():
                dist_bc = co.calc_distance_local(corner_node.my_node.x, corner_node.my_node.y,
                                                 my_next_node.my_node.x, my_next_node.my_node.y)
                my_angle = corner_node.angle
                angle_ab = co.calc_angle_of_line_local(my_prev_node.my_node.x, my_prev_node.my_node.y,
                                                       corner_node.my_node.x, corner_node.my_node.y)
                is_add = False  # whether the distance from prev_node (a) to corner_node (b) shall be longer
                if my_angle > 90:
                    my_angle = 180 - my_angle
                    is_add = True
                dist_add = dist_bc * cos(radians(my_angle))
                if not my_next_node.is_blocked():
                    dist_add /= 2
                if not is_add:
                    dist_add *= -1
                new_x, new_y = co.calc_point_angle_away(corner_node.my_node.x, corner_node.my_node.y,
                                                        dist_add, angle_ab)
                corner_node.my_node.update_point(new_x, new_y)
                if not my_next_node.is_blocked():
                    dist_add *= -1
                    new_x, new_y = co.calc_point_angle_away(my_next_node.my_node.x, my_next_node.my_node.y,
                                                            dist_add, angle_ab)
                    my_next_node.my_node.update_point(new_x, new_y)
