.. _chapter-parameters-label:

##########
Parameters
##########

Please consider the following:

* Python does not recognize operating system environment variables, please use full paths in the parameters file (no ``$HOME`` etc).
* These parameters determine how syenery objects are generated offline as described in chapter :ref:`Scenery Generation <chapter-generation-label>`. There are no runtime parameters in FlightGear, which influence which and how ``osm2city`` generated scenery objects are shown — or how many [#]_.
* All decimals need to be with "." - i.e. local specific decimal separators like "," are not accepted.
* Some of the 


=========================
View a List of Parameters
=========================

The final truth about parameters is stored in ``parameters.py`` — unfortunately the content in this chapter might be out of date (including default values).

It might be easiest to read ``parameters.py`` directly. Phython code is easy to read also for non-programmers. Otherwise you can run the following to see a listing:

::

    /usr/bin/python2.7 /home/vanosten/develop_vcs/osm2city/parameters.py -d

If you want to see a listing of the actual parameters used during scenery generation (i.e. a compination of the defaults with the overridden values in your ``params.ini`` file, then you can run the following command:

::

    /usr/bin/python2.7 --file /home/pingu/development/osm2city/parameters.py -f LSZS/params.ini


.. _chapter-param-minimal-label:

==================================
Detailed Description of Parameters
==================================

-----------
Minimal Set
-----------

See also :ref:`Setting a Minimal Set of Parameters <chapter-setting-parameters-label>`


=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
PREFIX                                          String     n/a       Name of the scenery project. Do not use spaces in the name.

PATH_TO_SCENERY                                 Path       n/a       Full path to the scenery folder without trailing slash. This is where we will
                                                                     probe elevation and check for overlap with static objects. Most likely you'll
                                                                     want to use your TerraSync path here. 

PATH_TO_OUTPUT                                  Path       n/a       The generated scenery (.stg, .ac, .xml) will be written to this path. If empty
                                                                     then the correct location in PATH_TO_SCENERY is used. Note that if you use
                                                                     TerraSync for PATH_TO_SCENERY, you MUST choose a different path here. 
                                                                     Otherwise, TerraSync will overwrite the generated scenery. Unless you know 
                                                                     what you are doing, there is no reason not to specify a dedicated path here.
                                                                     While not absolutely needed it is good practice to name the output folder 
                                                                     the same as ``PREFIX``.

OSM_FILE                                        String     n/a       The file containing OpenStreetMap data. See chapter
                                                                     :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`. 

BOUNDARY_NORTH, BOUNDARY_EAST,                  Decimal    n/a       The longitude and latitude in degrees of the boundaries of the generated 
BOUNDARY_SOUTH, BOUNDARY_WEST                                        scenery. 
                                                                     The boundaries should correspond to the boundaries in the ``OSM_FILE`` 
                                                                     (open the \*.osm file in a text editor and check the data in ca. line 3). 
                                                                     The boundaries can be different, but then you might either miss data 
                                                                     (if the OSM boundaries are larger) or do more processing than necessary 
                                                                     (if the OSM boundaries are more narrow).

NO_ELEV                                         Boolean    False     Set this to ``False``. The only reason to set this to ``True`` would be for
                                                                     developers to check generated scenery objects a bit faster not caring about 
                                                                     the vertical position in the scenery.
                                                                     
ELEV_MODE                                       String     n/a       Choose one of "FgelevCaching", 2Fgelev", "Telnet", "Manual". See chapter
                                                                     :ref:`Available Elevation Probing Mode<chapter-elev-modes-label>` for more 
                                                                     details.

=============================================   ========   =======   ==============================================================================



-----

.. [#] The only exception to the rule is the possibility to adjust the :ref:`actual distance of LOD ranges <chapter-lod-label>`.
