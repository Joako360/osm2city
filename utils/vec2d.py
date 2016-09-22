# -*- coding: utf-8 -*-
"""
Created on Sat Mar  2 12:04:17 2013

@author: tom
"""
import numpy as np
from math import atan2


class Vec2d(object):
    """A simple 2d vector class. Supports basic arithmetics."""
    def __init__(self, x, y=None):
        if y is None:
            if len(x) != 2:
                raise ValueError('Need exactly two values to create Vec2d from list.')
            y = x[1]  # -- Yes, we need to process y first.
            x = x[0]
        self.x = x
        self.y = y

    @property
    def lon(self):
        return self.x

    @lon.setter
    def lon(self, value):
        self.x = value

    @property
    def lat(self):
        return self.y

    @lat.setter
    def lat(self, value):
        self.y = value
        
    def __getitem__(self, key):
        return (self.x, self.y)[key]

    def __fixtype(self, other):
        if isinstance(other, type(self)):
            return other
        return Vec2d(other, other)

    def __add__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x * other.x, self.y * other.y)

    def __floordiv__(self, other):
        other = self.__fixtype(other)
        return Vec2d(self.x // other.x, self.y // other.y)

    def __str__(self):
        return "%1.7f %1.7f" % (self.x, self.y)

    def __neg__(self):
        return Vec2d(-self.x, -self.y)

    def __abs__(self):
        return Vec2d(abs(self.x), abs(self.y))

    def sign(self):
        return Vec2d(np.sign((self.x, self.y)))

    def __lt__(self, other):
        return Vec2d(self.x < other.x, self.y < other.y)

    def list(self):
        print("deprecated call to Vec2d.list(). Iterate instead.")
        return self.x, self.y

    def as_array(self):
        """return as numpy array"""
        return np.array((self.x, self.y))

    def __iter__(self):
        yield(self.x)
        yield(self.y)

    def swap(self):
        return Vec2d(self.y, self.x)

    def int(self):
        return Vec2d(int(self.x), int(self.y))

    def distance_to(self, other):
        d = self - other
        return (d.x**2 + d.y**2)**0.5

    def magnitude(self):
        return (self.x**2 + self.y**2)**0.5

    def normalize(self):
        mag = self.magnitude()
        self.x /= mag
        self.y /= mag

    def rot90ccw(self):
        return Vec2d(-self.y, self.x)

    def atan2(self):
        return atan2(self.y, self.x)
