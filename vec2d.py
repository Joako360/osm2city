# -*- coding: utf-8 -*-
"""
Created on Sat Mar  2 12:04:17 2013

@author: tom
"""

class vec2d(object):
    """A simple 2d vector class. Supports basic arithmetics."""
    def __init__(self, x, y = None):
        #print "got x", x
        #print "got y", y
        if y == None:
            y = x[1]
            x = x[0]
        self.x = x
        self.y = y

    def __fixtype(self, other):
        if type(other) == type(self): return other
        return vec2d(other, other)

    def __add__(self, other):
        other = self.__fixtype(other)
        return vec2d(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        other = self.__fixtype(other)
        return vec2d(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        other = self.__fixtype(other)
        return vec2d(self.x * other.x, self.y * other.y)

    def __div__(self, other):
        other = self.__fixtype(other)
        return vec2d(self.x / other.x, self.y / other.y)

    def __str__(self):
        return "%g %g" % (self.x, self.y)

    def __neg__(self):
        return vec2d(-self.x, -self.y)

    def list(self):
        return self.x, self.y

    def swap(self):
        return vec2d(self.y, self.x)

    def int(self):
        return vec2d(int(self.x), int(self.y))

if __name__ == "__main__":
    a = vec2d(1,2)
    b = vec2d(10,10)
    print "a   ", a
    print "b   ", b
    print "a+b ", a+b
    print "a-b ", a-b
    print "a+2 ", a+2
    print "a*b ", a * b
    print "a*2 ", a*2
    print "a/2 ", a/2
    print "a/2.", a/2.