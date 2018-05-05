# -*- coding: utf-8 -*-
import datetime
import random
from typing import Dict, List

from descartes import PolygonPatch
from matplotlib import axes as maxs
from matplotlib import figure as mfig
from matplotlib import patches as pat
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from owbb import models as m
import building_lib as bl
import parameters


def _create_a3_landscape_figure() -> mfig.Figure:
    return plt.figure(figsize=(11.69, 16.53), dpi=600)


def _create_a4_landscape_figure() -> mfig.Figure:
    return plt.figure(figsize=(8.27, 11.69), dpi=600)


def _create_pdf_pages(title_part: str) -> PdfPages:
    today = datetime.datetime.now()
    date_string = today.strftime("%Y-%m-%d_%H%M")
    tile_index_str = str(parameters.get_tile_index())
    return PdfPages("osm2city_debug_{0}_{1}_{2}.pdf".format(title_part, tile_index_str, date_string))


def _plot_line(ax: maxs.Axes, ob, my_color, my_width) -> None:
    x, y = ob.xy
    ax.plot(x, y, color=my_color, alpha=0.7, linewidth=my_width, solid_capstyle='round', zorder=2)


def _set_ax_limits_from_bounds(ax: maxs.Axes, bounds) -> None:
    x_min = bounds.min_point.x
    y_min = bounds.min_point.y
    x_max = bounds.max_point.x
    y_max = bounds.max_point.y
    _set_ax_limits(ax, x_min, x_max, y_min, y_max)


def _set_ax_limits(ax: maxs.Axes, x_min: float, x_max:  float, y_min: float, y_max: float) -> None:
    w = x_max - x_min
    h = y_max - y_min
    ax.set_xlim(x_min - 0.2*w, x_max + 0.2*w)
    ax.set_ylim(y_min - 0.2*h, y_max + 0.2*h)
    ax.set_aspect(1)


def _draw_highways(highways_dict, ax: maxs.Axes) -> None:
    for my_highway in highways_dict.values():
        if my_highway.is_sideway():
            _plot_line(ax, my_highway.geometry, "green", 1)
        else:
            _plot_line(ax, my_highway.geometry, "lime", 1)


def _draw_buildings(buildings: List[m.Building], ax: maxs.Axes) -> None:
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
        if building_zone.type_ is m.BuildingZoneType.farmyard:
            colour = 'brown'
        _add_patch_for_building_zone(building_zone, colour, colour, ax)
        for block in building_zone.linked_city_blocks:
            if block.settlement_type is m.SettlementType.centre:
                colour = 'blue'
            elif block.settlement_type is m.SettlementType.block:
                colour = 'green'
            elif block.settlement_type is m.SettlementType.dense:
                colour = 'magenta'
            patch = PolygonPatch(block.geometry, facecolor=colour, edgecolor=colour)
            ax.add_patch(patch)


def _draw_osm_zones(building_zones: List[m.BuildingZone], ax: maxs.Axes) -> None:
    edge_color = "red"
    for building_zone in building_zones:
        if not isinstance(building_zone, m.GeneratedBuildingZone):
            face_color = "red"
            if m.BuildingZoneType.commercial is building_zone.type_:
                face_color = "blue"
            elif m.BuildingZoneType.industrial is building_zone.type_:
                face_color = "green"
            elif m.BuildingZoneType.retail is building_zone.type_:
                face_color = "darkorange"
            elif m.BuildingZoneType.residential is building_zone.type_:
                face_color = "magenta"
            elif m.BuildingZoneType.farmyard is building_zone.type_:
                face_color = "chocolate"
            _add_patch_for_building_zone(building_zone, face_color, edge_color, ax)


def _draw_generated_zones(building_zones, ax: maxs.Axes) -> None:
    edge_color = "red"
    for building_zone in building_zones:
        if isinstance(building_zone, m.GeneratedBuildingZone):
            face_color = "red"
            if m.BuildingZoneType.commercial is building_zone.type_:
                face_color = "lightblue"
            elif m.BuildingZoneType.industrial is building_zone.type_:
                face_color = "lightgreen"
            elif m.BuildingZoneType.retail is building_zone.type_:
                face_color = "orange"
            elif m.BuildingZoneType.residential is building_zone.type_:
                face_color = "pink"
            elif m.BuildingZoneType.farmyard is building_zone.type_:
                face_color = "sandybrown"
            elif m.BuildingZoneType.corine_ind_com is building_zone.type_:
                face_color = "cyan"
            elif m.BuildingZoneType.corine_continuous is building_zone.type_:
                face_color = "gold"
            elif m.BuildingZoneType.corine_discontinuous is building_zone.type_:
                face_color = "yellow"
            _add_patch_for_building_zone(building_zone, face_color, edge_color, ax)


def _draw_btg_building_zones(btg_building_zones, ax: maxs.Axes) -> None:
    for item in btg_building_zones:
        if item.type_ in [m.BuildingZoneType.btg_builtupcover, m.BuildingZoneType.btg_urban]:
            my_color = "cyan"
        elif item.type_ in [m.BuildingZoneType.btg_town, m.BuildingZoneType.btg_suburban]:
            my_color = "gold"
        else:
            my_color = "yellow"
        patch = PolygonPatch(item.geometry, facecolor=my_color, edgecolor=my_color)
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
    pdf_pages = _create_pdf_pages("would-be-buildings")

    # Generated buildings
    my_figure = _create_a3_landscape_figure()
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


def draw_zones(highways_dict: Dict[int, m.Highway], buildings: List[m.Building],
               building_zones: List[m.BuildingZone], btg_building_zones: List[m.BTGBuildingZone],
               lit_areas: List[Polygon], bounds: m.Bounds) -> None:
    pdf_pages = _create_pdf_pages("landuse")

    # OSM building zones original
    my_figure = _create_a3_landscape_figure()
    my_figure.suptitle("Original OpenStreetMap building zones \n[blue=commercial, green=industrial, dark orange=retail\
, magenta=residential, brown=farmyard, red=error]")
    ax = my_figure.add_subplot(111)
    _draw_osm_zones(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # External land use
    if btg_building_zones:
        my_figure = _create_a3_landscape_figure()
        my_figure.suptitle("Land-use types from FlightGear BTG Files \n[cyan=builtupcover and urban\
, gold=town and suburban, yellow=construction and industrial and port]")
        ax = my_figure.add_subplot(111)
        ax.grid(True, linewidth=1, linestyle="--", color="silver")
        _draw_btg_building_zones(btg_building_zones, ax)
        _draw_highways(highways_dict, ax)
        _draw_buildings(buildings, ax)
        _set_ax_limits_from_bounds(ax, bounds)
        pdf_pages.savefig(my_figure)

    # Lit areas
    my_figure = _create_a3_landscape_figure()
    my_figure.suptitle("Lit areas from building zones")
    ax = my_figure.add_subplot(111)
    ax.grid(True, linewidth=1, linestyle="--", color="silver")
    _draw_lit_areas(lit_areas, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # All land-use
    my_figure = _create_a3_landscape_figure()
    my_figure.suptitle("Original OpenStreetMap and generated building zones \n[blue=commercial, green=industrial\
, dark orange=retail, magenta=residential, brown=farmyard, red=error;\n lighter variants=generated from buildings;\
\ncyan=commercial and industrial, gold=continuous urban fabric, yellow=discontinuous urban fabric]")
    ax = my_figure.add_subplot(111)
    _draw_osm_zones(building_zones, ax)
    _draw_generated_zones(building_zones, ax)
    _draw_buildings(buildings, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # Settlement type
    my_figure = _create_a3_landscape_figure()
    my_figure.suptitle("Built-up areas by settlement type \n[blue=centre (city), green=block, magenta=dense, \
    ,  brown=farmyard]")
    ax = my_figure.add_subplot(111)
    _draw_settlement_zones(building_zones, ax)
    _set_ax_limits_from_bounds(ax, bounds)
    pdf_pages.savefig(my_figure)

    # City blocks
    my_figure = _create_a3_landscape_figure()
    my_figure.suptitle("City blocks")
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

    pdf_pages = _create_pdf_pages("rectify_buildings")

    for sample in samples_list:
        my_figure = _create_a4_landscape_figure()
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
        _set_ax_limits(ax, min(original_x_array), max(original_x_array), min(original_y_array), max(original_y_array))
        ax.plot(original_x_array, original_y_array, color='red', linewidth=1,
                solid_capstyle='round', zorder=2)
        ax.plot(updated_x_array, updated_y_array, color='green', linewidth=1,
                solid_capstyle='round', zorder=3)
        _draw_blocked_nodes(blocked_nodes, ax)
        _draw_nodes_to_change(nodes_to_change, ax)
        pdf_pages.savefig(my_figure)

    pdf_pages.close()
    plt.close("all")
