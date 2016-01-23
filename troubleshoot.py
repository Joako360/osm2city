#!/usr/bin/env python
"""Checks tools.stats after running any of osm2city's modules and shows troubleshooting
hints if we detect problems.
""" 

import logging
import textwrap

import parameters
import tools


class Troubleshoot:
    def __init__(self):
        self.msg = ""
        self.n_problems = 0
        
    def skipped_no_elev(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not obtain their elevation.\n" % self.n_problems
        msg += "You are using ELEV_MODE = %s.\n" % parameters.ELEV_MODE
        if parameters.ELEV_MODE == "FgelevCaching":
            msg += textwrap.dedent("""
            Make sure
            - you have FG's scenery tiles for your area installed
            - PATH_TO_SCENERY is correct\n            
            """)
        elif parameters.ELEV_MODE == "Manual":
            msg += textwrap.dedent("""
            Consider using ELEV_MODE = FgelevCaching if
            you run FG >= 3.2 and have >= 4GB RAM. If that is not feasible, make sure
            - you have FG's scenery tiles for your area installed
            - your bounding box BOUNDARY_NORTH, _EAST etc. is big enough to cover all your
              OSM data. You might have to run the elev probing again. Note that depending
              on the clipping options used when you obtained the OSM file, it may contain
              data well outside your bounding box.\n
            """)
        else:
            msg += "Unfortunately not all elevation data is available. consider using ELEV_MODE = FgelevCaching."
        return msg

    def skipped_no_texture(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not find a matching texture.\n\n" % self.n_problems
        return msg


def troubleshoot(stats):
    """Analyzes statistics from tools.Stats objects and prints out logging information"""
    msg = ""
    t = Troubleshoot()
    if stats.skipped_no_elev:
        msg += t.skipped_no_elev()
    if stats.skipped_texture:
        msg += t.skipped_no_texture()
    
    if t.n_problems > 0:
        logging.warn("We've detected %i problem(s):\n\n%s" % (t.n_problems, msg))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = tools.Stats()
    stats.skipped_no_elev = 1
    stats.skipped_texture = 1
    troubleshoot(stats)
