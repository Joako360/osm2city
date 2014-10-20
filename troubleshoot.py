#!/usr/bin/env python
"""check tools.stats after running any of osm2city's modules and show troubleshooting
hints if we detect problems.
""" 

import textwrap
import parameters
import logging
from pdb import pm

class Troubleshoot():
    def __init__(self):
        self.msg = ""
        self.n_problems = 0
        
    def skipped_no_elev(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not obtain their elevation.\n" % self.n_problems
        if parameters.ELEV_MODE == "FgelevCaching":
            msg += textwrap.dedent("""
            You're using ELEV_MODE = FgelevCaching. Make sure
            - you have FG's scenery tiles for your area installed
            - PATH_TO_SCENERY is correct\n            
            """)
        else:
            parameters.ELEV_MODE == "Manual"
            msg += textwrap.dedent("""
            You're using ELEV_MODE = Manual. Consider using ELEV_MODE = FgelevCaching if
            you run FG >= 3.2 and have >= 4GB RAM. If that is not feasible, make sure
            - you have FG's scenery tiles for your area installed
            - your bounding box BOUNDARY_NORTH, _EAST etc. is big enough to cover all your
              OSM data. You might have to run the elev probing again. Note that depending
              on the clipping options used when you obtained the OSM file, it may contain
              data well outside your bounding box.\n
            """)
        return msg
        
    def skipped_no_texture(self):
        self.n_problems += 1
        msg = "%i. Some objects were skipped because we could not find a matching texture.\n\n" % self.n_problems
        return msg
    
def troubleshoot(stats):
    msg = ""
    t = Troubleshoot()
    if stats.skipped_no_elev:
        msg += t.skipped_no_elev()
    if stats.skipped_texture:
        msg += t.skipped_no_texture()
    
    if t.n_problems > 0:
        logging.warn("We've detected %i problem(s):\n\n%s" % (t.n_problems, msg))


class Stats:
    """a fake stats object for testing"""
    skipped_no_elev = 1
    skipped_texture = 1
    
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = Stats()
    troubleshoot(stats)
    