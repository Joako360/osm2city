#!/usr/bin/env python

# Copyright (C) 2011: Thomas Albrecht
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# --------------------------------------------------------------------------

# x switch order: always use lon, lat instead of lat, lon
# ? use vec2d, with vec2d.x = lon and vec2d.y = lat

import math
import copy
import os.path
import logging
from vec2d import vec2d
log = logging.getLogger('myapp')
#import numpy as np

class OldTransformation(object):
    """global <-> local coordinate system transformation"""
    def __init__(self, (lon, lat) = (0,0), hdg = 0):
        #self._originLat, self._originLon = (0,0)
        self._R = 6370000.  # earth's radius
        self._m2lat = 360. / (2. * math.pi * self._R)
        self.setOrigin((lon, lat))
        self.setHdg(hdg)

    def setOrigin(self, (lon, lat)):
        """set origin to given global coordinates (lon, lat)"""
        self._originLon, self._originLat = lon, lat
        self._m2lon = 360. / (2. * math.pi * self._R \
                              * math.cos(math.radians(self._originLat)))

    def getOrigin(self):
        """return origin in global coordinates"""
        return self._originLat, self._originLon

    def setHdg(self, hdg):
        """set hdg in deg"""
        self._hdgDeg = hdg
        self._hdgRad = math.radians(hdg)
        self._cos = math.cos(self._hdgRad)
        self._sin = math.sin(self._hdgRad)

    def getHdg(self):
        """return hdg in deg"""
        return self._hdgDeg

    def toLocal(self, (lon, lat)):
        """transform global -> local coordinates"""
        mlat = (lat - self._originLat) / self._m2lat
        mlon = (lon - self._originLon) / self._m2lon

        x = self._cos * mlon - self._sin * mlat
        y = self._sin * mlon + self._cos * mlat

        return x, y

    def toGlobal(self, (x, y)):
        """transform local -> global coordinates"""
        lon = (  self._cos * x + self._sin * y) * self._m2lon + self._originLon
        lat = (- self._sin * x + self._cos * y) * self._m2lat + self._originLat
        return lon, lat

    origin = property(getOrigin, setOrigin)
    hdg = property(getHdg, setHdg)

    def __str__(self):
        return "(%g %g) hdg %g" % (self._originLat, self._originLon, self.hdg)

class Position(object):
    """Holds the position and orientation of an object.
       Supports local and global coordinates.
       Change of its attributes can trigger update().
       Can return delta vector.
       Can move when given delta vector.
    """
    def __init__(self, transform, observers, lon, lat, alt=0, hdg=0, pit=0, rol=0):
        self._observers = []
        self._transform = transform
        self._lon = lon
        self._lat = lat
        self._x = 0
        self._y = 0
        self._updateLocal()
        self._alt = alt
        self._hdg = hdg
        self._pit = pit
        self._rol = rol
        self._observers = observers

    def copyWithoutObservers(self):
        """return a copy of self without observers"""
        c = copy.copy(self)
        c._observers = []
        return c

    def _update(self):
        for item in self._observers:
            item(self)

    def _updateLocal(self):
        """update (x,y) when (lat,lon) has changed"""
        if self._transform != None:
            self._x, self._y = self._transform.toLocal((self._lat, self._lon))

    def _updateGlobal(self):
        """update (lat,lon) when (x,y) has changed"""
        if self._transform == None:
            raise RuntimeError('No transform given.')
        self._lat, self._lon = self._transform.toGlobal((self._x, self._y))

    def setOrigin(self, (lon, lat)):
        """set origin to given global coordinates (lon, lat)"""
        self._lon, self._lat = lon, lat
        self._update()

    def getOrigin(self):
        """return origin in global coordinates"""
        return self._lat, self._lon

    def getLat(self):
        return self._lat
    def setLat(self, lat):
        self._lat = lat
        self._updateLocal()
        self._update()

    def getLon(self):
        return self._lon
    def setLon(self, lon):
        self._lon = lon
        self._updateLocal()
        self._update()

    def getX(self):
        self._updateLocal() # -- transform may have changed
        return self._x
    def setX(self, x):
        self._x = x
        self._updateGlobal()
        self._update()

    def getY(self):
        self._updateLocal()
        return self._y
    def setY(self, y):
        self._y = y
        self._updateGlobal()
        self._update()

    def getAlt(self):
        return self._alt
    def setAlt(self, alt):
        self._alt = alt
        self._update()

    def getHdg(self):
        return self._hdg
    def setHdg(self, hdg):
        self._hdg = hdg
        self._update()

    def getPit(self):
        return self._pit
    def setPit(self, pit):
        self._pit = pit
        self._update()

    def getRol(self):
        return self._rol
    def setRol(self, rol):
        self._rol = rol
        self._update()

    lat = property(getLat, setLat)
    lon = property(getLon, setLon)
    origin = property(getOrigin, setOrigin)
    x   = property(getX, setX)
    y   = property(getY, setY)
    alt = property(getAlt, setAlt)
    hdg = property(getHdg, setHdg)
    pit = property(getPit, setPit)
    rot = property(getRol, setRol)

    def move(self, delta):
        """move by given delta. Lat/lon overrides x/y"""
        if delta.isZero():
            log.debug("zero delta, not moving.")
            return True

        self._alt += delta.alt
        self._hdg += delta.hdg
        log.debug("FIXME: clip heading")
        if delta.lat != 0 or delta.lon != 0:
            self._lat += delta.lat
            self._lon += delta.lon
            self._updateLocal()
        else:
            self._updateLocal() # -- transform may have changed
            self._x += delta.x
            self._y += delta.y
            self._updateGlobal()
        self._update()
        return True

    def __sub__(a, b):
        return Delta(a.lat - b.lat, a.lon - b.lon, a.x - b.x, a.y - b.y, \
                     a.alt - b.alt, a.hdg - b.hdg)

    def __str__(self):
        return "(%g %g) (%g %g)  alt %g  hdg %g  pit %g  rol %g" \
           % (self._lat, self._lon, self._x, self._y, self._alt, self._hdg, \
              self._pit, self._rol)

    def _setSpherical(self, other, radius, brg, elevation=0):
        """move relative to other position.
           Offset given in spherical coordinates.
        """
        if other == None: return
        transform = Transformation((other.lat, other.lon))
        alpha = math.radians(brg + 90.)
        x = radius * math.cos(alpha)
        y = radius * math.sin(alpha)
        self._alt = other.alt + elevation
        log.debug("FIXME: setPolar.")
        self._lat, self._lon = transform.toGlobal((x, y))

    def setSpherical(self, other, radius, brg, elevation=0):
        """wrapper for _setSpherical"""
        self._setSpherical(other, radius, brg, elevation)
        self._update()

class SphericalRelativePosition(Position):
    """describe position relative to another object
       given in spherical coordinates
    """
    def __init__(self, transform, observers, other=None, radius=50., brg=0, elevation=0):
        self.observers = observers
        self._other = other
        self._radius = radius
        self._brg = brg
        self._elevation = elevation
        Position.__init__(self, transform, observers, 0, 0, 0, 0)
        self._setSpherical(self._other, self._radius, self._brg, self._elevation)

    def _update(self):
        self._setSpherical(self._other, self._radius, self._brg, self._elevation)
        for item in self.observers:
            item(self)

    def getRadius(self):
        return self._radius
    def setRadius(self, radius):
        if radius != self._radius:
            self._radius = radius
            self._update()

    def getBrg(self):
        return self._brg
    def setBrg(self, brg):
        if brg != self._brg:
            self._brg = brg
            self._update()

    def getElevation(self):
        return self._elevation
    def setElevation(self, elevation):
        if elevation != self._elevation:
            self._elevation = elevation
            self._update()

    def getOther(self):
        return self._other
    def setOther(self, other):
        if other != self._other:
            self._other = other
            self._update()

    other     = property(getOther,     setOther)
    radius    = property(getRadius,    setRadius)
    brg       = property(getBrg,       setBrg)
    elevation = property(getElevation, setElevation)

class Transformation(Position):
    """global <-> local coordinate system transformation"""
    def __init__(self, (lon, lat) = (0,0), hdg = 0):
    #def __init__(self, transform, observers, lon, lat, alt=0, hdg=0, pit=0, rol=0):

        Position.__init__(self, None, [], lon, lat, hdg = hdg)
        self._transform = self
        self.type = "COORD"
        self.path = ""
        #self._originLat, self._originLon = (0,0)
        self._a = 6378137.
        self._b = 6356752.3142
#        self._R = 6371010.  # earth's radius
        self._lat = lat
        self._lon = lon
        self._hdg = hdg
        self._offset_x = 0
        self._offset_y = 0

        self._update()

    def radius_at_lat(self, lat):
        """Earth radius at given lat. Lat in degrees."""
        #Das Koordinatensystem, in dem das Referenzellipsoid,
        #ein kartesisches Rechtssystem (
        #Z weist zum Nordpol,
        #X in Richtung 0 grad Laenge und Breite,
        #Y nach 90 grad Ost)
        #grosse Halbachse a = 6 378 137 Meter,
        #abplattung f = 1 / 298,257 223 563, also
        #kleinen Halbachse b = a(1-f) von etwa 6 356 752,3142 Metern,
        #
        #    \frac{x^2}{a^2} + \frac{y^2}{b^2} = 1
        #    x^2/a^2 + y^2/b^2 = 1
        #
        #var a = 6378137, b = 6356752.314245,  f = 1/298.257223563;  // WGS-84 ellipsoid params

        cosp = math.cos(math.radians(lat))
        sinp = math.sin(math.radians(lat))
        return math.sqrt( ( (self._a**2 * cosp)**2 + (self._b**2 * sinp)**2) \
                        / ( (self._a    * cosp)**2 + (self._b    * sinp)**2) )

    def _update(self):
        # if lat has changed
        R = self.radius_at_lat(self._lat)
        self._m2lat = 360. / (2. * math.pi * R)

        self._m2lon = 360. / (2. * math.pi * R \
                              * math.cos(math.radians(self._lat)))
        # if hdg has changed
        self._hdgRad = math.radians(self._hdg)
        self._cos = math.cos(self._hdgRad)
        self._sin = math.sin(self._hdgRad)

        if self._transform == self:
            self._x = 0
            self._y = 0

        Position._update(self)

    # getOrigin() inherited from Position

    def setHdg(self, hdg):
        """set hdg in deg"""
        self._hdg = hdg
        self._update()

    def getHdg(self):
        """return hdg in deg"""
        return self._hdg

#    def setOffset(self, (offset_x, offset_y)):
#        """set local offset"""
#        self._offset_x = offset_x
#        self._offset_y = offset_y

    def toLocal(self, (lon, lat)):
        """transform global -> local coordinates"""
        mlat = (lat - self._lat) / self._m2lat
        mlon = (lon - self._lon) / self._m2lon

        x = self._cos * mlon - self._sin * mlat
        y = self._sin * mlon + self._cos * mlat

#        x += self._offset_x
#        y += self._offset_y

        return x, y

    def toGlobal(self, (x, y)):
        """transform local -> global coordinates"""

#        x -= self._offset_x
#        y -= self._offset_y

        lon = (  self._cos * x + self._sin * y) * self._m2lon + self._lon
        lat = (- self._sin * x + self._cos * y) * self._m2lat + self._lat
        return lon, lat

    hdg = property(getHdg, setHdg)

    def __str__(self):
        return "(%f %f) hdg %f m2 %1.10f %1.10f" % (self._lat, self._lon, self.hdg, self._m2lat, self._m2lon)


class Delta:
    def __init__(self, lat=0., lon=0., x=0., y=0., alt=0., hdg=0.):
        self.lat = lat
        self.lon = lon
        self.x = x
        self.y = y
        self.alt = alt
        self.hdg = hdg

    def __neg__(self):
        r = copy.copy(self)
        r.lat = - self.lat
        r.lon = - self.lon
        r.x   = - self.x
        r.y   = - self.y
        r.alt = - self.alt
        r.hdg = - self.hdg
        return r

    def isZero(self):
        if self.lat == 0 and self.lon == 0 and self.x == 0 and self.y == 0 \
            and self.alt == 0 and self.hdg == 0:
            return True
        return False

    def __str__(self):
        return "(%g %g) (%g %g) alt %g  hdg %g" \
            % (self.lat, self.lon, self.x, self.y, self.alt, self.hdg)

inf="/usr/share/games/FlightGear/Scenery/Objects/w130n30/w122n37/958440.stg"

class Object(Position):
    def __init__(self, transform, observers, line=None, lat=0, lon=0, alt=0, hdg=0, typ="", path=""):
        if line != None:
            splitted = line.split()
            self.type, self.path  = splitted[0:2]
            lon = float(splitted[2])
            lat = float(splitted[3])
            alt = float(splitted[4])
            hdg = float(splitted[5])
        else:
            self.type = typ
            self.path = path
        self.stgPath = ''
        Position.__init__(self, transform, observers, lon, lat, alt, hdg)

    def __str__(self):
        return "%s %s %g %g %g %g" % (self.type, self.path, self.lon, self.lat,\
            self.alt, self.hdg)

class stg:
    def __init__(self, filename, observers, transform=None):
        self.objs = self.read(filename, observers, transform)

    def read(self, filename, observers, transform):
        objs = []
        dirName, tmp = os.path.split(os.path.abspath(filename))
        print "dirname", dirName
        f = open(filename)
        for line in f.readlines():
            if line.strip() == "" or line.startswith('#') : continue
            o = Object(transform, observers, line)
            o.stgPath = dirName
            objs.append(o)
        f.close()
        return objs


if __name__ == "__main__":
    t = Transformation((1,1))
    lon, lat = 1, 1
    print lon, lat
    x, y = t.toLocal((lon, lat))
    print x, y
    print t.toGlobal((x,y))

    p = Position(t,0,0)
    print p
    p.x = 1
    print p
    p.alt = 5
    print p
    p.lon = 0
    print p

    diff = Delta(lat = 1.)
    print "diff", diff
    a = - diff
    print diff
    print a

    print "delta"
    a = copy.copy(p)
    p.lat += 2
    print "p=", p
    print "a=", a
    delta = p - a
    print delta
    a.move(delta)
    print "a=", a
    print "delta", p - a
