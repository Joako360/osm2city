"""Utilities to plot for visual debugging purposes to pdf-files using matplotlib."""

import datetime
from typing import Tuple

from matplotlib import axes as maxs
from matplotlib import figure as mfig
from matplotlib import pyplot as plt

from matplotlib.backends.backend_pdf import PdfPages

import osm2city.parameters as p


def create_a4_landscape_figure() -> mfig.Figure:
    return plt.figure(figsize=(8.27, 11.69), dpi=600)


def create_a3_landscape_figure() -> mfig.Figure:
    return plt.figure(figsize=(11.69, 16.53), dpi=600)


def create_pdf_pages(title_part: str) -> PdfPages:
    today = datetime.datetime.now()
    date_string = today.strftime("%Y-%m-%d_%H%M")
    tile_index_str = str(p.get_tile_index())
    return PdfPages("osm2city_debug_{0}_{1}_{2}.pdf".format(title_part, tile_index_str, date_string))


def set_ax_limits_bounds(ax: maxs.Axes, bounds: Tuple[float, float, float, float]) -> None:
    set_ax_limits(ax, bounds[0], bounds[1], bounds[2], bounds[3])


def set_ax_limits(ax: maxs.Axes, x_min: float, y_min: float, x_max:  float, y_max: float) -> None:
    w = x_max - x_min
    h = y_max - y_min
    ax.set_xlim(x_min - 0.2*w, x_max + 0.2*w)
    ax.set_ylim(y_min - 0.2*h, y_max + 0.2*h)
    ax.set_aspect('equal')


def plot_line(ax: maxs.Axes, ob, my_color: str, my_width: int) -> None:
    x, y = ob.xy
    ax.plot(x, y, color=my_color, alpha=0.7, linewidth=my_width, solid_capstyle='round', zorder=2)
