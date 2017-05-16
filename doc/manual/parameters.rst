.. _chapter-parameters-label:

##########
Parameters
##########

Please consider the following:

* Python does not recognize operating system environment variables, please use full paths in the parameters file (no ``$HOME`` etc).
* These parameters determine how scenery objects are generated offline as described in chapter :ref:`Scenery Generation <chapter-generation-label>`. There are as of version 2016.4 no runtime parameters in FlightGear, that influence which ``osm2city`` generated scenery objects are shown — or how and how many [#]_.
* All decimals need to be with "." — i.e. local specific decimal separators like "," are not accepted.
* You do not have to specify all parameters in your ``params.ini`` file. Actually it is better only to specify those parameters, which you want to actively control — the rest just gets the defaults.


=========================
View a List of Parameters
=========================

The final truth about parameters is stored in ``parameters.py`` — unfortunately the content in this chapter of the manual might be out of date (including default values).

It might be easiest to read ``parameters.py`` directly. Python code is easy to read also for non-programmers. Otherwise you can run the following to see a listing:

::

    /usr/bin/python3 /home/vanosten/develop_vcs/osm2city/parameters.py -d

If you want to see a listing of the actual parameters used during scenery generation (i.e. a combination of the defaults with the overridden values in your ``params.ini`` file, then you can run the following command:

::

    /usr/bin/python3 --file /home/pingu/development/osm2city/parameters.py -f LSZS/params.ini


==================================
Detailed Description of Parameters
==================================


.. _chapter-param-minimal-label:

-----------
Minimal Set
-----------

See also :ref:`Setting a Minimal Set of Parameters <chapter-setting-parameters-label>`.


=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
PREFIX                                          String     n/a       Name of the scenery project. Do not use spaces in the name.

PATH_TO_SCENERY                                 Path       n/a       Full path to the scenery folder without trailing slash. This is where we will
                                                                     probe elevation and check for overlap with static objects. Most likely you'll
                                                                     want to use your TerraSync path here.

PATH_TO_SCENERY_OPT                             Path       None      Optional additional path to a scenery folder (e.g. for `Project3000`_).
                                                                     Only used for overlap checking for buildings against static and shared
                                                                     objects.

PATH_TO_OUTPUT                                  Path       n/a       The generated scenery (.stg, .ac, .xml) will be written to this path. If empty
                                                                     then the correct location in PATH_TO_SCENERY is used. Note that if you use
                                                                     TerraSync for PATH_TO_SCENERY, you MUST choose a different path here. 
                                                                     Otherwise, TerraSync will overwrite the generated scenery. Unless you know 
                                                                     what you are doing, there is no reason not to specify a dedicated path here.
                                                                     While not absolutely needed it is good practice to name the output folder 
                                                                     the same as ``PREFIX``.

PATH_TO_OSM2CITY_DATA                           Path       n/a       Full path to the folder with osm2city-data. See chapter
                                                                     :ref:`Installation of osm2city <chapter-osm2city-install>` (e.g.
                                                                     "/home/user/osm2city-data").

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

FG_ELEV                                         String     n/a       Points to the full path of the fgelev executable. On Linux it could be
                                                                     something like ``.../bin/fgfs_git/next/install/flightgear/bin/fgelev'``.
                                                                     On Windows you might have to put quotes around the path due to whitespace
                                                                     e.g. ``'"D:/Program Files/FlightGear/bin/Win64/fgelev.exe"'``.

PROBE_FOR_WATER                                 Boolean    False     Checks the scenery in ``PATH_TO_SCENERY`` whether points are in the water or
                                                                     not. The Flightgear scenery's water boundaries might be different from OSM.
                                                                     E.g. removes buildings if at least one corner is in the water. And removes
                                                                     or splits (parts of) roads/railways, if at least 1 point is in the water.
                                                                     Only possible with FGElev version after 9th of November 2016 / FG 2016.4.1.

=============================================   ========   =======   ==============================================================================

.. _`Project3000`: http://wiki.flightgear.org/Project3000


.. _chapter-parameters-lod-label:

-----------------------------
Level of Details of Buildings
-----------------------------

The more buildings you have in LOD detailed, the less resources for rendering are used. However you might find it "irritating" the more buildings suddenly appear. Experiment with the settings in FlightGear, see also :ref:`Adjusting Visibility of Scenery Objects <chapter-lod-label>`. 

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
LOD_ALWAYS_DETAIL_BELOW_AREA                    Integer    150       Below this area, buildings will always be LOD detailed

LOD_ALWAYS_ROUGH_ABOVE_AREA                     Integer    500       Above this area, buildings will always be LOD rough

LOD_ALWAYS_ROUGH_ABOVE_LEVELS                   Integer    6         Above this number of levels, buildings will always be LOD rough

LOD_ALWAYS_DETAIL_BELOW_LEVELS                  Integer    3         Below this number of levels, buildings will always be LOD detailed

LOD_PERCENTAGE_DETAIL                           Decimal    0.5       Of the remaining buildings, this percentage will be LOD detailed,
                                                                     the rest will be LOD rough.

=============================================   ========   =======   ==============================================================================


.. _chapter-parameters-overlap-label:

---------------------------
Overlap Check for Buildings
---------------------------

Overlap checks try to omit overlap of buildings generated based on OSM data with static object as well as shared objects (depending on parameter ``OVERLAP_CHECK_CONSIDER_SHARED``) in the default scenery (defined by ``PATH_TO_SCENERY``).

If parameter ``PATH_TO_SCENERY_OPT`` is not None, then also object from that path are considered (e.g. for Project3000).

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
OVERLAP_CHECK_CONVEX_HULL                       Bool       False     Reads all points from static (not shared) objects and creates a convex hull
                                                                     around all points. This is a brute force algorithm only taking into account
                                                                     the firsts object's vertices.

OVERLAP_CHECK_CH_BUFFER_STATIC                  Decimal    0.0       Buffer around static objects to extend the overlap area. In general convex
                                                                     hull is already a conservative approach, so using 0 (zero) should be fine.

OVERLAP_CHECK_CH_BUFFER_SHARED                  Decimal    0.0       Same as above but for shared objects.

OVERLAP_CHECK_CONSIDER_SHARED                   Bool       True      Whether only static objects (i.e. a unique representation of a real world
                                                                     thing) should be taken into account — or also shared objects (i.e. generic
                                                                     models reused in different places like a church model).
                                                                     For this to work ``PATH_TO_SCENERY`` must point to the TerraSync directory.

=============================================   ========   =======   ==============================================================================

Examples of overlap objects based on static objects at LSZS (light grey structures at bottom of buildings):

.. image:: lszs_hull_front.png


.. image:: lszs_hull_back.png



.. _chapter-parameters-light:

-------------
Light Effects
-------------

Parameters for some light effects / shaders.

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
TRAFFIC_SHADER_ENABLE                           Boolean    False     If True then the traffic shader gets enabled, otherwise the light-map shader.
                                                                     These effects are only for roads, not railways. The traffic shader has moving
                                                                     cars, however it only works with the default renderer — ALS/Rembrandt must be
                                                                     off.
OBSTRUCTION_LIGHT_MIN_LEVELS                    Integer    15        Puts obstruction lights on buildings >= the specified number levels.

LIGHTMAP_ENABLE                                 Boolean    True      Creates simulated light effects on buildings from street lights.

=============================================   ========   =======   ==============================================================================


.. _chapter-parameters-textures:

--------
Textures
--------

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
ATLAS_SUFFIX                                    String     (empty)   Add the the suffix to the texture atlas (also light-map) in ``osm2city-data``
                                                                     including an underscore (e.g. 'foo' leads to atlas_facades_foo.png).

TEXTURES_ROOFS_NAME_EXCLUDE                     List       []        List of roof file names to exclude, e.g. ["roof_red3.png", "roof_orange.png"].
                                                                     The file names must be relative paths to the ``tex.src`` directory within
                                                                     ``PATH_TO_OSM2CITY_DATA``.
                                                                     Be aware the excluding roofs can lead to indirectly excluding facade textures,
                                                                     which might be depending on provided roof types.
                                                                     An empty list means that no filtering is done.

TEXTURES_FACADES_NAME_EXCLUDE                   List       []        Same as ``TEXTURES_ROOFS_EXCLUDE`` but for facades — e.g.
                                                                     ["de/commercial/facade_modern_21x42m.jpg"].

TEXTURES_ROOFS_PROVIDE_EXCLUDE                  List       []        List of provided features for roofs to exclude, e.g. ["colour:red"].

TEXTURES_FACADES_PROVIDE_EXCLUDE                List       []        Ditto for facades.

TEXTURES_REGIONS_EXPLICIT                       List       []        Explicit list of regions to include. If list is empty, then all regions are
                                                                     accepted.
                                                                     There is also a special region "generic", which corresponds to
                                                                     top directory structure. In many situations it might not make sense to include
                                                                     "generic", as it provides a lot of colours etc. (which however could be
                                                                     filtered with the other parameters).

TEXTURES_EMPTY_LM_RGB_VALUE                     Integer    35        If a texture does not have an explicit light-map (i.e. same file name plus
                                                                     "_LM", then a default light-map is constructed with RGB(VALUE, VALUE, VALUE).

=============================================   ========   =======   ==============================================================================


.. _chapter-parameters-clipping:

---------------
Clipping Region
---------------

The boundary of a scenery as specified by the parameters ``BOUNDARY_*`` is not necessarily sharp. As described in :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>` it is recommended to use ``completeWays=yes``, when manipulating/getting OSM data - this happens also to be the case when using the `OSM Extended API`_ to retrieve data e.g. as part of :ref:`working in batch mode <chapter-batch-mode>`. However there are no parameters to influence the processing of OSM nodes and OSM ways depending on whether they are inside / outside the boundary or intersecting.

NB: in most situations the boundary should correspond to FG tiles or be entirely inside a tile boundary.

The processing is as follows:

* buildings.py: if the first node is inside the boundary, then the whole building is processed — otherwise not
* roads.py: if not entirely inside then split at boundary, such that the first node is always inside and the last is either inside by default or the first node outside for splitting.
* piers.py: as above for piers
* platforms.py: as above for platforms
* pylons.py

  * storage tanks: if the centroid is inside the boundary, then the whole storage tank is processed — otherwise not
  * wind turbines: no checking because the source data for OSM should already be extracted correctly
  * aerial ways: if the first node is inside the boundary, then the whole aerial way is processed — otherwise not (assuming that aerial ways are short)
  * power lines and railway overhead lines: as for roads. If the last node was split, then no shared model is placed assuming it is continued in another tile (i.e. optimized for batch processing across tiles)


.. _`OSM Extended API`: http://wiki.openstreetmap.org/wiki/Xapi


.. _chapter-parameters-roads:

--------------------------------
Linear Objects (Roads, Railways)
--------------------------------

Parameters for roads, railways and related bridges. One of the challenges to show specific textures based on OSM data is to fit the texture such that it drapes ok on top of the scenery. Therefore several parameters relate to enabling proper draping.

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
BRIDGE_MIN_LENGTH                               Decimal    20.       Discard short bridges and draw roads or railways instead.

MIN_ABOVE_GROUND_LEVEL                          Decimal    0.01      How much a highway / railway is at least hovering above ground

HIGHWAY_TYPE_MIN                                Integer    4         The lower the number, the smaller ways in the highway hierarchy are added.
                                                                     Currently the numbers are as follows (see roads.py -> HighwayType).
                                                                     motorway = 12
                                                                     trunk = 11
                                                                     primary = 10
                                                                     secondary = 9
                                                                     tertiary = 8
                                                                     unclassified = 7
                                                                     road = 6
                                                                     residential = 5
                                                                     living_street = 4
                                                                     service = 3
                                                                     pedestrian = 2
                                                                     slow = 1 (cycle ways, tracks, footpaths etc).

POINTS_ON_LINE_DISTANCE_MAX                     Integer    1000      The maximum distance between two points on a line. If longer, then new points
                                                                     are added. This parameter might need to get set to a smaller value in order to
                                                                     have enough elevation probing along a road/highway. Together with parameter
                                                                     MIN_ABOVE_GROUND_LEVEL it makes sure that fewer residuals of ways are below 
                                                                     the scenery ground. The more uneven a scenery ground is, the smaller this 
                                                                     value should be chosen. The drawback of small values are that the number
                                                                     of faces gets bigger affecting frame rates.

MAX_SLOPE_ROAD, MAX_SLOPE_*                     Decimal    0.08      The maximum allowed slope. It is used for ramps to bridges, but it is also
                                                                     used for other ramps. Especially in mountainous areas you might want to set
                                                                     higher values (e.g. 0.15 for roads works fine in Switzeland). This leads to
                                                                     steeper ramps to bridges, but give much fewer residuals with embankments.

=============================================   ========   =======   ==============================================================================

With residuals:

.. image:: elev_residuals.png

After adjusted MAX_SLOPE_* and POINTS_ON_LINE_DISTANCE_MAX parameters:

.. image:: no_elev_residuals.png



.. _chapter-parameters-database:

--------
Database
--------

Instead of reading from OSM files it is possible to use a PostGIS database as OSM data storage. See also :ref:`OSM Data in Database <chapter-osm-database-label>`.

=============================================   ========   =======   ==============================================================================
Parameter                                       Type       Default   Description / Example
=============================================   ========   =======   ==============================================================================
USE_DATABASE                                    Boolean    False     If True then the OSM data is read from a database instead of
                                                                     PATH_TO_OSM2CITY_DATA.
DB_HOST                                         String     n/a       The host name of the computer running PostGIS (e.g. localhost).
DB_PORT                                         Integer    5432      The port used to connect to the host
DB_NAME                                         String     n/a       The name of the database (e.g osmogis).
DB_USER                                         String     n/a       The name of the user to be used to read from the database. Can be read-only.
DB_USER_PASSWORD                                String     n/a       The password for the DB_USER.

=============================================   ========   =======   ==============================================================================




.. FIXME missing explanations for MAX_TRANSVERSE_GRADIENT = 0.1   #
   DEBUG_PLOT = 0
   CREATE_BRIDGES_ONLY = 0         # create only bridges and embankments
   BRIDGE_LAYER_HEIGHT = 4.         # bridge height per layer
   BRIDGE_BODY_HEIGHT = 0.9         # height of bridge body
   EMBANKMENT_TEXTURE = textures.road.EMBANKMENT_1  # Texture for the embankment


.. [#] The only exception to the rule is the possibility to adjust the :ref:`Actual Distance of LOD Ranges <chapter-lod-label>`.
