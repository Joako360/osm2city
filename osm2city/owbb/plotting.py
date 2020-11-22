# -*- coding: utf-8 -*-
import random
from typing import List

from descartes import PolygonPatch
from matplotlib import axes as maxs
from matplotlib import patches as pat
from matplotlib import pyplot as plt
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

import osm2city.building_lib as bl
import osm2city.owbb.models as m
import osm2city.static_types.enumerations as enu
import osm2city.utils.plot_utilities as pu


def _set_ax_limits_from_bounds(ax: maxs.Axes, bounds) -> None:
    x_min = bounds.min_point.x
    y_min = bounds.min_point.y
    x_max = bounds.max_point.x
    y_max = bounds.max_point.y
    pu.set_ax_limits(ax, x_min, y_min, x_max, y_max)


def _draw_highways(highways_dict, ax: maxs.Axes) -> None:
    for my_highway in highways_dict.values():
        if my_highway.is_sideway():
            pu.plot_line(ax, my_highway.geometry, "green", 1)
        else:
            pu.plot_line(ax, my_highway.geometry, "lime", 1)


def _draw_buildings(buildings: List[bl.Building], ax: maxs.Axes) -> None:
    for building in buildings:
        if isinstance(building.geometry, Polygon):
            patch = PolygonPatch(building.geometry, facecolor="black", edgecolor="black")
            ax.add_patch(patch)


def _add_patch_for_building_zone(building_zone: m.BuildingZone, face_color: str, edge_color: str, ax: maxs.Axes)  \
            -> None:
    if isinstance(building_zone.geometry, MultiPolygon):
        for polygon in building_zone.geometry.geoms:
            patch = PolygonPatch(polygon, facecolor=face_color, edgecolor=edge_color)
            ax.add_patch(patch)
    else:
        patch = PolygonPatch(building_zone.geometry, facecolor=face_color, edgecolor=edge_color)
        ax.add_patch(patch)


def _draw_settlement_zones(building_zones: List[m.BuildingZone], ax: maxs.Axes) -> None:
    for building_zone in building_zones:
        colour = 'grey'
        if building_zone.type_ is enu.BuildingZoneType.farmyard:
            colour = 'brown'
        _add_patch_for_building_zone(building_zone, colour, colour, ax)
        for block in building_zone.linked_city_blocks:
            if block.settlement_type is enu.SettlementType.centre:
                colour = 'blue'
            elif block.settlement_type is enu.SettlementType.block:
                colour = 'green'
            elif block.settlement_type is enu.SettlementType.dense:
                colour = 'magenta'
            elif block.settlement_type is enu.SettlementType.periphery:
                colour = 'yellow'
            patch = PolygonPatch(block.geometry, facecolor=colour, edgecolor=colour)
            if block.settlement_type_changed:
                patch.set_hatch('/')
            ax.add_patch(patch)


def _draw_zones_density(building_zones: List[m.BuildingZone], ax: maxs.Axes) -> None:
    for building_zone in building_zones:
        density = building_zone.density  # keeping value in order not to calculate the property all the time
        colour = 'black'
        if density < .05:
            colour = 'lightgrey'
        elif density < .1:
            colour = 'yellow'
        elif density < .15:
            colour = 'orange'
        elif density < .2:
            colour = 'red'
        elif density < .25:
            colour = 'darkred'
        elif density < .3:
            colour = 'lime'
        elif density < .35:
            colour = 'limegreen'
        elif density < .4:
            colour = 'green'
        elif density < .45:
            colour = 'darkgreen'
        _add_patch_for_building_zone(building_zone, colour, colour, ax)


def _draw_osm_zones(building_zones: List[m.BuildingZone], ax: maxs.Axes) -> None:
    for building_zone in building_zones:
        if not isinstance(building_zone, m.GeneratedBuildingZone):
            face_color = "red"
            if enu.BuildingZoneType.commercial is building_zone.type_:
                face_color = "blue"
            elif enu.BuildingZoneType.industrial is building_zone.type_:
                face_color = "green"
            elif enu.BuildingZoneType.retail is building_zone.type_:
                face_color = "darkorange"
            elif enu.BuildingZoneType.residential is building_zone.type_:
                face_color = "magenta"
            elif enu.BuildingZoneType.farmyard is building_zone.type_:
                face_color = "chocolate"
            elif enu.BuildingZoneType.aerodrome is building_zone.type_:
                face_color = 'purple'
            _add_patch_for_building_zone(building_zone, face_color, face_color, ax)


def _draw_generated_zones(building_zones, ax: maxs.Axes) -> None:
    for building_zone in building_zones:
        if isinstance(building_zone, m.GeneratedBuildingZone):
            face_color = "red"
            if enu.BuildingZoneType.commercial is building_zone.type_:
                face_color = "lightblue"
            elif enu.BuildingZoneType.industrial is building_zone.type_:
                face_color = "lightgreen"
            elif enu.BuildingZoneType.retail is building_zone.type_:
                face_color = "orange"
            elif enu.BuildingZoneType.residential is building_zone.type_:
                face_color = "pink"
            elif enu.BuildingZoneType.farmyard is building_zone.type_:
                face_color = "sandybrown"
            elif building_zone.type_ in [enu.BuildingZoneType.btg_construction, enu.BuildingZoneType.btg_industrial,
                                         enu.BuildingZoneType.btg_port]:
                face_color = "cyan"
            elif building_zone.type_ in [enu.BuildingZoneType.btg_urban, enu.BuildingZoneType.btg_town]:
                face_color = "gold"
            elif building_zone.type_ in [enu.BuildingZoneType.btg_builtupcover, enu.BuildingZoneType.btg_suburban]:
                face_color = "yellow"
            edge_color = face_color
            _add_patch_for_building_zone(building_zone, face_color, edge_color, ax)


def _draw_btg_building_zones(btg_building_zones, ax: maxs.Axes) -> None:
    for item in btg_building_zones:
        if item.type_ in [enu.BuildingZoneType.btg_builtupcover, enu.BuildingZoneType.btg_urban]:
            my_color = "magenta"
        elif item.type_ in [enu.BuildingZoneType.btg_town, enu.BuildingZoneType.btg_suburban]:
            my_color = "gold"
        else:
            my_color = "yellow"
        patch = PolygonPatch(item.geometry, facecolor=my_color, edgecolor=my_color)
        ax.add_patch(patch)


def _draw_btg_water_areas(btg_water_areas: List[Polygon], ax: maxs.Axes) -> None:
    for item in btg_water_areas:
        my_color = 'lightskyblue'
        patch = PolygonPatch(item, facecolor=my_color, edgecolor=my_color)
        ax.add_patch(patch)


def _draw_lit_areas(lit_areas: List[Polygon], ax: maxs.Axes) -> None:
    for item in lit_areas:
        my_color = "cyan"
        patch = PolygonPatch(item, facecolor=my_color, edgecolor="black")
        ax.add_patch(patch)


def _draw_city_blocks(building_zones: List[m.BuildingZone], ax: maxs.Axes) -> None:
    for zone in building_zones:
        city_blocks = zone.linked_city_blocks
        for item in city_blocks:
            red = random.random()
            green = random.random()
            blue = random.random()
            patch = PolygonPatch(item.geometry, facecolor=(red, green, blue), edgecolor=(red, green, blue))
            ax.add_patch(patch)


def _draw_background_zones(building_zones, ax: maxs.Axes) -> None:
    for building_zone in building_zones:
        my_color = "lightgray"
        if isinstance(building_zone, m.GeneratedBuildingZone):
            my_color = "darkgray"
        if isinstance(building_zone.geometry, MultiPolygon):
            for polygon in building_zone.geometry.geoms:
                patch = PolygonPatch(polygon, facecolor=my_color, edgecolor="white")
                ax.add_patch(patch)
        else:
            patch = PolygonPatch(building_zone.geometry, facecolor=my_color, edgecolor="white")
            ax.add_patch(patch)


def _draw_blocked_areas(building_zones, ax: maxs.Axes) -> None:
    for my_building_zone in building_zones:
        for blocked in my_building_zone.linked_blocked_areas:
            if m.BlockedAreaType.open_space == blocked.type_:
                my_facecolor = 'darkgreen'
                my_edgecolor = 'darkgreen'
            elif m.BlockedAreaType.gen_building == blocked.type_:
                my_facecolor = 'yellow'
                my_edgecolor = 'yellow'
            elif m.BlockedAreaType.osm_building == blocked.type_:
                my_facecolor = 'blue'
                my_edgecolor = 'blue'
            else:
                my_facecolor = 'orange'
                my_edgecolor = 'orange'
            patch = PolygonPatch(blocked.polygon, facecolor=my_facecolor, edgecolor=my_edgecolor)
            ax.add_patch(patch)


def _draw_blocked_nodes(blocked_nodes: List[bl.NodeInRectifyBuilding], ax: maxs.Axes) -> None:
    for node in blocked_nodes:
        if bl.RectifyBlockedType.ninety_degrees in node.blocked_types:
            my_color = 'blue'
        else:
            my_color = 'red'
        if bl.RectifyBlockedType.corner_to_bow in node.blocked_types:
            my_fill = True
        else:
            my_fill = False
        if bl.RectifyBlockedType.multiple_buildings in node.blocked_types:
            my_alpha = 0.3
        else:
            my_alpha = 1.0

        my_circle = pat.Circle((node.my_node.original_x, node.my_node.original_y), radius=0.4, linewidth=2,
                               color=my_color, fill=my_fill, alpha=my_alpha)
        ax.add_patch(my_circle)


def _draw_nodes_to_change(nodes_to_change: List[bl.NodeInRectifyBuilding], ax: maxs.Axes) -> None:
    for node in nodes_to_change:
        ax.add_patch(pat.Circle((node.my_node.original_x, node.my_node.original_y), radius=0.4, linewidth=2,
                                color='green', fill=False))


def draw_buildings(building_zones, bounds) -> None:
    pdf_pages = pu.create_pdf_pages("would-be-buildings")

    # Generated buildings
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Generated buildings (yellow) and other blocked areas \n[yellow=generated building" +
                       ", blue=OSM building, dark green=open space, orange=other blocked area]")
    ax = my_figure.add_subplot(111)
    _draw_background_zones(building_zones, ax)
    _draw_blocked_areas(building_zones, ax)
    for building_zone in building_zones:
        _draw_buildings(building_zone.osm_buildings, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")


def draw_zones(buildings: List[bl.Building], building_zones: List[m.BuildingZone],
               btg_building_zones: List[m.BTGBuildingZone], btg_water_areas: List[Polygon],
               lit_areas: List[Polygon], bounds: m.Bounds) -> None:
    pdf_pages = pu.create_pdf_pages("landuse")

    # OSM building zones original
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Original OpenStreetMap building zones \n[blue=commercial, green=industrial, dark orange=retail\
, magenta=residential, brown=farmyard, purple=aerodrome, red=error]")
    ax = my_figure.add_subplot(111)
    _draw_osm_zones(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # Only water from BTG
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Water from FlightGear BTG files")
    ax = my_figure.add_subplot(111)
    _draw_btg_water_areas(btg_water_areas, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # External land use from BTG
    if btg_building_zones:
        my_figure = pu.create_a3_landscape_figure()
        my_figure.suptitle("Land-use types from FlightGear BTG files \n[magenta=builtupcover and urban, \
gold=town and suburban, yellow=construction and industrial and port, light blue=water]")
        ax = my_figure.add_subplot(111)
        ax.grid(True, linewidth=1, linestyle="--", color="silver")
        _draw_btg_water_areas(btg_water_areas, ax)
        _draw_btg_building_zones(btg_building_zones, ax)
        _draw_buildings(buildings, ax)
        _set_ax_limits_from_bounds(ax, bounds)
        pdf_pages.savefig(my_figure)

    # All land-use
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Original OpenStreetMap and generated building zones \n[blue=commercial, green=industrial\
, dark orange=retail, magenta=residential, brown=farmyard, purple=aerodrome, red=error;\n \
lighter variants=generated from buildings;\
\ncyan=commercial and industrial, gold=continuous urban, yellow=discontinuous urban]")
    ax = my_figure.add_subplot(111)
    _draw_btg_water_areas(btg_water_areas, ax)
    _draw_osm_zones(building_zones, ax)
    _draw_generated_zones(building_zones, ax)
    _draw_buildings(buildings, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # Lit areas
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Lit areas from building zones")
    ax = my_figure.add_subplot(111)
    ax.grid(True, linewidth=1, linestyle="--", color="silver")
    _draw_btg_water_areas(btg_water_areas, ax)
    _draw_lit_areas(lit_areas, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # Settlement type
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Built-up areas by settlement type \n[blue=centre (city), green=block, magenta=dense, \n \
    yellow=periphery, grey=rural, brown=farmyard]. If hatched, then type upgraded or downgraded for sanity.")
    ax = my_figure.add_subplot(111)
    _draw_btg_water_areas(btg_water_areas, ax)
    _draw_settlement_zones(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # Density of zones
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("Density (ratio of building floor plan area to total area).\n \
    Light grey up to .05, Yellow up to .1, orange up to 0.15, red up to .2,\n \
    dark red up to .25, lime up to .3, green up to .4, dark green up to .45, black afterwards")
    ax = my_figure.add_subplot(111)
    _draw_btg_water_areas(btg_water_areas, ax)
    _draw_zones_density(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # City blocks
    my_figure = pu.create_a3_landscape_figure()
    my_figure.suptitle("City blocks random pattern")
    ax = my_figure.add_subplot(111)
    ax.grid(True, linewidth=1, linestyle="--", color="silver")
    _draw_city_blocks(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")


def draw_rectify(rectify_buildings: List[bl.RectifyBuilding], max_samples: int, seed_sample: bool) -> None:
    number_of_samples = len(rectify_buildings)
    if number_of_samples > max_samples:
        number_of_samples = max_samples
    if seed_sample:
        random.seed()
    samples_list = random.sample(rectify_buildings, number_of_samples)

    pdf_pages = pu.create_pdf_pages("rectify_buildings")

    for sample in samples_list:
        my_figure = pu.create_a4_landscape_figure()
        my_figure.suptitle("Building with OSM id = %i. \nIf green then node to change;\nif blue then 90 degrees;\
\n else red;\nif filled then corner of a bow; \nif light color then part of multiple buildings.\
\nOriginal boundary is red, new boundary is green."
                           % sample.osm_id)
        ax = my_figure.add_subplot(111)
        original_x_array = np.zeros(len(sample.node_refs) + 1)  # because we need to close the loop
        original_y_array = np.zeros(len(sample.node_refs) + 1)
        updated_x_array = np.zeros(len(sample.node_refs) + 1)
        updated_y_array = np.zeros(len(sample.node_refs) + 1)
        blocked_nodes = list()
        nodes_to_change = list()
        for position in range(len(sample.node_refs) + 1):
            node_position = position
            if position == len(sample.node_refs):
                node_position = 0
            node = sample.node_refs[node_position]
            rectify_node = node.my_node
            original_x_array[position] = rectify_node.original_x
            original_y_array[position] = rectify_node.original_y
            updated_x_array[position] = rectify_node.x
            updated_y_array[position] = rectify_node.y
            if node.is_blocked():
                blocked_nodes.append(node)
            elif node.within_rectify_deviation():
                nodes_to_change.append(node)
        pu.set_ax_limits(ax, min(original_x_array), min(original_y_array), max(original_x_array), max(original_y_array))
        ax.plot(original_x_array, original_y_array, color='red', linewidth=1,
                solid_capstyle='round', zorder=2)
        ax.plot(updated_x_array, updated_y_array, color='green', linewidth=1,
                solid_capstyle='round', zorder=3)
        _draw_blocked_nodes(blocked_nodes, ax)
        _draw_nodes_to_change(nodes_to_change, ax)
        pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")
