'''
Created on 22.08.2014

@author: keith.paterson
'''
import math


def calc_bearing(node1, node2):
    """
    Calculate the bearing between two points
    """
    dLon = node2.lon - node1.lon
    y = math.sin(dLon) * math.cos(node2.lat)
    x = math.cos(node1.lat) * math.sin(node2.lat) \
        - math.sin(node1.lat) * math.cos(node2.lat) * math.cos(dLon)
    return math.degrees(math.atan2(y, x))


def calc_distance(node1, node2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # haversine formula
    dlon = math.radians(node2.lon) - math.radians(node1.lon)
    dlat = math.radians(node2.lat) - math.radians(node1.lat)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(node1.lat)) * math.cos(math.radians(node2.lat)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # 6367 km is the radius of the Earth
    km = 6367 * c
    return km
