.. _chapter-using-label:

##############################
Using Generated Scenery [User]
##############################

==========================================
Finding and Downloading a osm2city Scenery
==========================================

The FlightGear wiki article `Howto: Install Scenery <http://wiki.flightgear.org/Howto:Install_scenery>`_ has a general overview over installing scenery in FlightGear.

`Areas populated with osm2city scenery <http://wiki.flightgear.org/Areas_populated_with_osm2city_scenery>`_ is the best way currently to find osm2city generated sceneries. That wiki page also list which sceneries can be downloaded in Terrasync and for which FlightGear version. The plan for the future is to have the whole world available in constantly updated versions — however as of spring 2017 this is not yet a reality.

Even though a scenery might be available for download in TerraSync, you might want to download offline by using a tool like `TerraMaster <http://wiki.flightgear.org/TerraMaster>`_ or `terrasync.py <http://wiki.flightgear.org/TerraSync#terrasync.py>`_, because the volume of data can be quite comprehensive — the faster you fly and the slower your internet connection, the rougher the experience will be.


=========================
Adding to FG_SCENERY Path
=========================

You need to add the directory containing the ``Buildings``, ``Pylons`` and ``Roads`` folders to the path, where FlightGear searches for scenery. You can to this either through the command line option ``--fg-scenery`` or setting the FG_SCENERY environment variable. This is extensively described in the ``README.scenery`` and the ``getstart.pdf`` [#]_ documents found in $FG_ROOT/Docs as part of your FlightGear installation.

If you followed the :ref:`directory structure <chapter-creating-directory-structure-label>` presented in chapter :ref:`Preparation <chapter-preparation-label>` and we take the example of ``LSZS`` then you would e.g. use the following command line option:

::

    --fg-scenery=/home/pingu/fg_customscenery/LSZS


.. [#] As of November 2016: chapters 3.1 and 4.2.2

.. _chapter-lod-label:

=======================================
Adjusting Visibility of Scenery Objects
=======================================

The ``osm2city`` related programs and especially ``buildings.py`` are using heuristics and parameters to determine at what level of detail (LOD) scenery objects should be visible. This is done by adding the objects to one of the three FlightGear LOD schemes: "rough" and "detailed".

For ``buildings.py`` before creating a scenery you can influence into which of the two LOD ranges the objects are placed by using the following :ref:`Parameters <chapter-parameters-lod-label>`:

* LOD_ALWAYS_DETAIL_BELOW_AREA
* LOD_ALWAYS_ROUGH_ABOVE_AREA
* LOD_ALWAYS_ROUGH_ABOVE_LEVELS
* LOD_ALWAYS_DETAIL_BELOW_LEVELS
* LOD_PERCENTAGE_DETAIL

In FlightGear as a scenery user you influence the actual distance (in meters) for the respective ranges by one of the following ways:

#. In The FlightGear user interface use menu ``View`` > menu item ``Adjust LOD Ranges`` and then change the values manually.
#. Include command line options into your fgfsrc_ file or `Properties in FGRun`_ like follows (adjust the values to your needs and depending on your hardware capabilities):

::

    --prop:double:/sim/rendering/static-lod/detailed=5000
    --prop:double:/sim/rendering/static-lod/rough=10000
    --prop:/sim/rendering/max-paged-lod=400

See also PagedLOD_.

.. _fgfsrc: http://wiki.flightgear.org/Fgfsrc
.. _`Properties in FGRun`: http://wiki.flightgear.org/FlightGear_Launch_Control#Properties
.. _PagedLOD: http://wiki.flightgear.org/PagedLOD


=========================================
Disable Urban Shader and Random Buildings
=========================================

There is no point in having both OSM building scenery objects and dynamically generated buildings in FlightGear. Therefore it is recommended to turn off the random building and urban shader features in FlightGear. Please be aware that this will also affect those areas in FlightGear, where there are no generated scenery objects from OSM.

Use the FlightGear menu ``View``, menu item ``Rendering Options``.

* Scenery layers:
  * Buildings: Choose ``OpenStreetMap Data`` (i.e. ``Randomly Generated`` is turned off)
  * Pylons and power lines: not only used for electrical power pylons and cables, but also e.g. wind turbines
  * Detailed Roads and Railways: draped over the grey roads and railways lines in the default scenery.
* If you also enable ``Atmospheric Light Scattering (ALS)`` you also get better effects during day and night as well as moving cars. Not using ALS might give odd graphical effects.

.. image:: fgfs_rendering_options.png

In the same dialog press the ``Shader Options`` button and set the slider for ``Urban`` to the far left in order to disable the urban shader.

.. image:: fgfs_shader_options.png


========================
Showing Detailed Objects
========================
Some of the generated sceneries might contain a sub-folder ``Details`` apart from e.g. ``Buildings``. If you want to show more scenery details (and accept that this might drain some system resources), then rename the folder to ``Objects``.


.. _chapter-hide-urban-textures-label:

=======================================
Change Materials to Hide Urban Textures
=======================================

FlightGear allows to change the texture used for a given land-class. More information is available in ``$FG_ROOT/Docs/README.materials`` as well as in the FlightGear Forum thread regarding `New Regional Textures <http://forum.flightgear.org/viewtopic.php?f=5&t=26031>`_. There is not yet a good base texture replacing the urban textures. However many users find it more visually appealing to use a uniform texture like grass under the generated buildings etc. instead of urban textures (because urban textures interfere visually with ways, houses etc.). A drawback of using different textures is the absence of trees — however in many regions of the world there are lot of trees / vegetation in urban areas. An important drawback is that you will find the texturing missing when flying high over ground (due to level of distance not loading OSM objects) or for stuff far in the distance, where OSM data has not yet been loaded.

E.g. for the airport ``LSZS`` in Engadin in Switzerland you would have to go to ``$FG_ROOT/Materials/regions`` and edit file ``europe.xml`` in a text editor: add name-tags for e.g. ``BuiltUpCover``, ``Urban``, ``Town``, ``SubUrban`` to a material as shown below and comment out the existing name-tags using ``<!-- -->``. Basically all name-tags, which relate to a material using ``<effect>Effects/urban</effect>``. The outcome before and after edit (you need to restart FlightGear in between!) can be seen in the screenshots below (for illustration purposes the buildings and roads do not have textures).

::

  ...
  <material>
    <effect>Effects/cropgrass</effect>
    <tree-effect>Effects/tree-european-mixed</tree-effect>
    <name>CropGrassCover</name>
    <name>CropGrass</name>
    <name>BuiltUpCover</name>
    <name>Urban</name>
    <name>Town</name>
    <name>SubUrban</name>    
    <texture>Terrain/cropgrass-hires-autumn.png</texture>
    <object-mask>Terrain/cropgrass-hires.mask.png</object-mask>
  ...
  
  ...
  <material>
    <!-- <name>Town</name> -->
    <!-- <name>SubUrban</name> -->
    <effect>Effects/urban</effect>
    <texture-set>
  ...

.. image:: fgfs_materials_urban.png


.. image:: fgfs_materials_cropgrass.png

Depending on your region and your shader settings you might want to search for e.g. ``GrassCover`` in file ``global-summer.xml`` instead (shown in screenshot below with ALS_ and more random vegetation). However be aware that you still need to comment out in e.g. ``europe.xml`` and within ``global-summer.xml``.

.. image:: fgfs_materials_grass.png


.. _ALS: http://wiki.flightgear.org/Atmospheric_light_scattering
