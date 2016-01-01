#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Transform global (aka geodetic) coordinates to a local cartesian, in meters.
A flat earth approximation (http://williams.best.vwh.net/avform.htm) seems good
enough if distances are up to a few km.

Alternatively, use UTM, but that fails if the origin is near an UTM zone boundary.
Also, this requires the utm python package (pip install utm).

The correct approach, though, is probably to do exactly what FG does, which I think is
- transform geodetic to geocentric coordinates (find a python lib for that)
- from there, compute the (geocentric) Cartesian coordinates as described here:
    http://www.flightgear.org/Docs/Scenery/CoordinateSystem/CoordinateSystem.html
- project them onto local Cartesian (including correct up vector etc)

Created on Sat Jun  7 22:38:59 2014
@author: albrecht
"""
#http://williams.best.vwh.net/avform.htm
#Local, flat earth approximation
# If you stay in the vicinity of a given fixed point (lat0,lon0), it may be a 
# good enough approximation to consider the earth as "flat", and use a North,
# East, Down rectangular coordinate system with origin at the fixed point. If
# we call the changes in latitude and longitude dlat=lat-lat0, dlon=lon-lon0 
# (Here treating North and East as positive!), then
#
#       distance_North=R1*dlat
#       distance_East=R2*cos(lat0)*dlon
#
# R1 and R2 are called the meridional radius of curvature and the radius of 
# curvature in the prime vertical, respectively.
#
#      R1=a(1-e^2)/(1-e^2*(sin(lat0))^2)^(3/2)
#      R2=a/sqrt(1-e^2*(sin(lat0))^2)
#
# a is the equatorial radius of the earth (=6378.137000km for WGS84), and
# e^2=f*(2-f) with the flattening f=1/298.257223563 for WGS84.
#
# In the spherical model used elsewhere in the Formulary, R1=R2=R, the earth's
# radius. (using R=1 we get distances in radians, using R=60*180/pi distances are in nm.)
#
# In the flat earth approximation, distances and bearings are given by the
# usual plane trigonometry formulae, i.e:
#
#    distance = sqrt(distance_North^2 + distance_East^2)
#    bearing to (lat,lon) = mod(atan2(distance_East, distance_North), 2*pi)
#                        (= mod(atan2(cos(lat0)*dlon, dlat), 2*pi) in the spherical case)
#
# These approximations fail in the vicinity of either pole and at large 
# distances. The fractional errors are of order (distance/R)^2.


from math import acos, asin, atan2, sin, cos, sqrt, radians, degrees, pi
import logging
import unittest


NAUTICAL_MILES_METERS = 1852


class Transformation(object):
    """global <-> local coordinate system transformation, using flat earth approximation
       http://williams.best.vwh.net/avform.htm#flat
    """
    def __init__(self, (lon, lat)=(0, 0), hdg=0):
        if hdg != 0.:
            logging.error("heading != 0 not yet implemented.")
            raise NotImplemented
        self._lon = lon
        self._lat = lat
        self._update()

    def _update(self):
        """compute radii for local origin"""
        a = 6378137.000 # m for WGS84
        f=1./298.257223563
        e2 = f*(2.-f)

        self._coslat = cos(radians(self._lat))
        sinlat = sin(radians(self._lat))
        self._R1 = a*(1.-e2)/(1.-e2*(sinlat**2))**(3./2.)
        self._R2 = a/sqrt(1-e2*sinlat**2)

    def setOrigin(self, (lon, lat)):
        """set origin to given global coordinates (lon, lat)"""
        self._lon, self._lat = lon, lat
        self._update()

    def getOrigin(self):
        """return origin in global coordinates"""
        return self._lat, self._lon

    origin = property(getOrigin, setOrigin)

    def toLocal(self, (lon, lat)):
        """transform global -> local coordinates"""
        y = self._R1 * radians(lat - self._lat)
        x = self._R2 * radians(lon - self._lon) * self._coslat
        return x, y

    def toGlobal(self, (x, y)):
        """transform local -> global coordinates"""
        lat = degrees(y / self._R1) + self._lat
        lon = degrees(x / (self._R2 * self._coslat)) + self._lon
        return lon, lat

    def __str__(self):
        return "(%f %f)" % (self._lon, self._lat)


def calc_angle_of_line_local(x1, y1, x2, y2):
    """Returns the angle in degrees of a line relative to North.
    Based on local coordinates (x,y) of two points.
    """
    angle = atan2(x2 - x1, y2 - y1)
    degree = degrees(angle)
    if degree < 0:
        degree += 360
    return degree


def calc_distance_local(x1, y1, x2, y2):
    """Returns the distance between two points based on local coordindates (x,y)."""
    return sqrt(pow(x1 - x2, 2) + pow(y1 - y2, 2))


def calc_distance_global(lon1, lat1, lon2, lat2):
    lon1_r = radians(lon1)
    lat1_r = radians(lat1)
    lon2_r = radians(lon2)
    lat2_r = radians(lat2)
    distance_radians = calc_distance_global_radians(lon1_r, lat1_r, lon2_r, lat2_r)
    return distance_radians*((180*60)/pi) * NAUTICAL_MILES_METERS


def calc_distance_global_radians(lon1_r, lat1_r, lon2_r, lat2_r):
    return 2*asin(sqrt(pow(sin((lat1_r-lat2_r)/2), 2) + cos(lat1_r)*cos(lat2_r)*pow(sin((lon1_r-lon2_r)/2), 2)))


def calc_angle_of_line_global(lon1, lat1, lon2, lat2):
    lon1_r = radians(lon1)
    lat1_r = radians(lat1)
    lon2_r = radians(lon2)
    lat2_r = radians(lat2)
    d = calc_distance_global_radians(lon1_r, lat1_r, lon2_r, lat2_r)
    if sin(lon2_r-lon1_r) > 0:
        angle = acos((sin(lat2_r)-sin(lat1_r)*cos(d))/(sin(d)*cos(lat1_r)))
    else:
        angle = 2*pi-acos((sin(lat2_r)-sin(lat1_r)*cos(d))/(sin(d)*cos(lat1_r)))
    angle = degrees(angle)
    return angle


if __name__ == "__main__":
    t = Transformation((0, 0))
    print t.toLocal((0., 0))
    print t.toLocal((1., 0))
    print t.toLocal((0, 1.))
    print
    print t.toGlobal((100., 0))
    print t.toGlobal((1000., 0))
    print t.toGlobal((10000., 0))
    print t.toGlobal((100000., 0))

# ================ UNITTESTS =======================


class TestCoordinates(unittest.TestCase):
    def test_calc_angle_of_line_local(self):
        self.assertEqual(0, calc_angle_of_line_local(0, 0, 0, 1), "North")
        self.assertEqual(90, calc_angle_of_line_local(0, 0, 1, 0), "East")
        self.assertEqual(180, calc_angle_of_line_local(0, 1, 0, 0), "South")
        self.assertEqual(270, calc_angle_of_line_local(1, 0, 0, 0), "West")
        self.assertEqual(45, calc_angle_of_line_local(0, 0, 1, 1), "North East")
        self.assertEqual(315, calc_angle_of_line_local(1, 0, 0, 1), "North West")
        self.assertEqual(225, calc_angle_of_line_local(1, 1, 0, 0), "South West")

    def test_calc_angle_of_line_global(self):
        self.assertAlmostEqual(360, calc_angle_of_line_global(1, 46, 1, 47), delta=0.5)  # "North"
        self.assertAlmostEqual(90, calc_angle_of_line_global(1, -46, 2, -46), delta=0.5)  # "East"
        self.assertAlmostEqual(180, calc_angle_of_line_global(-1, -33, -1, -34), delta=0.5)  # "South"
        self.assertAlmostEqual(270, calc_angle_of_line_global(-29, 20, -30, 20), delta=0.5)  # "West"
        self.assertAlmostEqual(45, calc_angle_of_line_global(0, 0, 1, 1), delta=0.5)  # "North East"
        self.assertAlmostEqual(315, calc_angle_of_line_global(1, 0, 0, 1), delta=0.5)  # "North West"
        self.assertAlmostEqual(225, calc_angle_of_line_global(1, 1, 0, 0), delta=0.5)  # "South West"

    def test_calc_distance_local(self):
        self.assertEqual(5, calc_distance_local(0, -1, -4, 2))

    def test_calc_distance_global(self):
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, 46, 1, 47), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, -33, 1, -34), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60, calc_distance_global(1, 0, 2, 0), delta=10)
        self.assertAlmostEqual(NAUTICAL_MILES_METERS * 60 * sqrt(2), calc_distance_global(1, 0, 2, 1), delta=10)
