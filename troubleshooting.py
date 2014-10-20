#!/usr/bin/env python
"""Troubleshooting hints, to be shown to the user if we detect problems when 
running any of osm2city's modules.
""" 

import textwrap
import parameters

def no_elev():
    """ """

    msg = "Some objects were skipped because we could not obtain their elevation.\n"
    if parameters.ELEV_MODE == "FgelevCaching":
        msg += textwrap.dedent("""
        You're using ELEV_MODE = FgelevCaching. Make sure
        - you have FG's scenery tiles for your area installed
        - PATH_TO_SCENERY is correct
        """)
    else:
        parameters.ELEV_MODE == "Manual"
        msg += textwrap.dedent("""
        You're using ELEV_MODE = Manual. Consider using ELEV_MODE = FgelevCaching if
        you run FG >= 3.2 and have >= 4GB RAM. If that is not feasible, make sure
        - you have FG's scenery tiles for your area installed
        - your bounding box BOUNDARY_NORTH, _EAST etc. is big enough to cover all your
          OSM data. You might have to run the elev probing again. Note that depending
          on the clipping options used when you obtained the osm file, it may contain
          data well outside your bounding box.
        """)
    print msg
    
no_elev()
