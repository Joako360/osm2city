.. _chapter-parameters-label:

##########
Parameters
##########

Please consider the following:

* Python does not recognize operating system environment variables, please use full paths in the parameters file (no ``$HOME`` etc).
* These parameters determine how scenery objects are generated offline as described in chapter :ref:`Scenery Generation <chapter-generation-label>`. There are no runtime parameters in FlightGear, that influence which ``osm2city`` generated scenery objects are shown — or how and how many [#]_.
* All decimals need to be with "." - i.e. local specific decimal separators like "," are not accepted.
* You do not have to specify all parameters in your ``params.ini`` file. Actually it is better only to specify those parameters, which you want to actively control — the rest just gets the defaults.


=========================
View a List of Parameters
=========================

The final truth about parameters is stored in ``parameters.py`` — unfortunately the content in this chapter might be out of date (including default values).

It might be easiest to read ``parameters.py`` directly. Python code is easy to read also for non-programmers. Otherwise you can run the following to see a listing:

::

    /usr/bin/python2.7 /home/vanosten/develop_vcs/osm2city/parameters.py -d

If you want to see a listing of the actual parameters used during scenery generation (i.e. a combination of the defaults with the overridden values in your ``params.ini`` file, then you can run the following command:

::

    /usr/bin/python2.7 --file /home/pingu/development/osm2city/parameters.py -f LSZS/params.ini


==================================
Detailed Description of Parameters
==================================


.. _chapter-param-minimal-label:

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

ELEV_MODE                                       String     n/a       Choose one of "FgelevCaching", "Fgelev", "Telnet", "Manual". See chapter
                                                                     :ref:`Available Elevation Probing Mode<chapter-elev-modes-label>` for more 
                                                                     details.

=============================================   ========   =======   ==============================================================================


.. _chapter-parameters-lod-label:

----------------
Level of Details
----------------

The more buildings you have in LOD detailed, the less resources for rendering are used. However you might find it "irritating" the more buildings suddenly appear. Experiment with the settings in FlightGear, see also :ref:`Adjusting Visibility of Scenery Objects <chapter-lod-label>`. 

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
LOD_ALWAYS_DETAIL_BELOW_AREA                    Integer    150       Below this area, buildings will always be LOD detailed

LOD_ALWAYS_ROUGH_ABOVE_AREA                     Integer    500       Above this area, buildings will always be LOD rough

LOD_ALWAYS_ROUGH_ABOVE_LEVELS                   Integer    6         Above this number of levels, buildings will always be LOD rough

LOD_ALWAYS_BARE_ABOVE_LEVELS                    Integer    10        Really tall buildings will be LOD bare

LOD_ALWAYS_DETAIL_BELOW_LEVELS                  Integer    3         Below this number of levels, buildings will always be LOD detailed

LOD_PERCENTAGE_DETAIL                           Decimal    0.5       Of the remaining buildings, this percentage will be LOD detailed,
                                                                     the rest will be LOD rough.

=============================================   ========   =======   ==============================================================================




.. [#] The only exception to the rule is the possibility to adjust the :ref:`Actual Distance of LOD Ranges <chapter-lod-label>`.
