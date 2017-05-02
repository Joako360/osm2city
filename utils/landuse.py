import logging
from typing import Dict, List

import shapely.geometry as shg

import parameters


class Landuse(object):
    TYPE_COMMERCIAL = 10
    TYPE_INDUSTRIAL = 20
    TYPE_RESIDENTIAL = 30
    TYPE_RETAIL = 40
    TYPE_NON_OSM = 50  # used for land-uses constructed with heuristics and not in original data from OSM

    def __init__(self, osm_id):
        self.osm_id = osm_id
        self.type_ = 0
        self.polygon = None  # the polygon defining its outer boundary
        self.number_of_buildings = 0  # only set for generated TYPE_NON_OSM land-uses during generation


def process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator) -> Dict[int, Landuse]:
    my_landuses = dict()  # osm_id as key, Landuse as value

    for way in list(ways_dict.values()):
        my_landuse = Landuse(way.osm_id)
        valid_landuse = False
        for key in way.tags:
            value = way.tags[key]
            if "landuse" == key:
                if value == "commercial":
                    my_landuse.type_ = Landuse.TYPE_COMMERCIAL
                    valid_landuse = True
                elif value == "industrial":
                    my_landuse.type_ = Landuse.TYPE_INDUSTRIAL
                    valid_landuse = True
                elif value == "residential":
                    my_landuse.type_ = Landuse.TYPE_RESIDENTIAL
                    valid_landuse = True
                elif value == "retail":
                    my_landuse.type_ = Landuse.TYPE_RETAIL
                    valid_landuse = True
        if valid_landuse:
            # Process the Nodes
            my_coordinates = list()
            for ref in way.refs:
                if ref in nodes_dict:
                    my_node = nodes_dict[ref]
                    x, y = my_coord_transformator.toLocal((my_node.lon, my_node.lat))
                    my_coordinates.append((x, y))
            if len(my_coordinates) >= 3:
                my_landuse.polygon = shg.Polygon(my_coordinates)
                if my_landuse.polygon.is_valid and not my_landuse.polygon.is_empty:
                    my_landuses[my_landuse.osm_id] = my_landuse

    logging.debug("OSM land-uses found: %s", len(my_landuses))
    return my_landuses


def process_osm_landuse_as_areas(nodes_dict, ways_dict, my_coord_transformator) -> List[shg.Polygon]:
    """Just a wrapper around process_osm_landuse_refs(...) to get the list of polygons."""
    landuse_refs = process_osm_landuse_refs(nodes_dict, ways_dict, my_coord_transformator)
    landuse_areas = list()
    for key, value in landuse_refs.items():
        landuse_areas.append(value.polygon.buffer(parameters.BUILT_UP_AREA_LIT_BUFFER))
    return landuse_areas
