#!/usr/bin/env python

import json

class Params(object):
    # name, type, default    
    p = [['total_objects', 'int', 10],
         ['a_list', 'list', [1,2,3,'a']]]
    def __init__(self):
        pass
    def read_from_file(self, filename):
        pass
    def __str__(self):
        pass
    def defaults(self):
        pass

if __name__ == "__main__":
    pass
