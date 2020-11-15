"""This module contains the data structures for the next generation textures (ca. FG version 2021.x LTS).
"""
from enum import IntEnum, unique


@unique
class AtlasTypes(IntEnum):
    building_large_skyscrapers = 0
    building_large_modern = 10
    building_large_bricks = 11
    building_large_roofs = 20
    building_rest = 30  #
    details = 40
    # currently nothing for roads, as it has already its own atlas -> see road.py


class Pod:
    pass


class Sector:
    pass


class Atlas:
    pass
