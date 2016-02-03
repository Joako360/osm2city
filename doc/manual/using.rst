.. _chapter-using-label:

#######################
Using Generated Scenery
#######################

FIXME: Add to path

FIXME: consider sharing

FIXME: copy texture stuff


.. _chapter-lod-label:

=======================================
Adjusting Visibility of Scenery Objects
=======================================

The ``osm2city`` related programs and especially ``osm2city.py`` itself are using heuristics and parameters to determine at what level of detail (LOD) scenery objects should be visible. This is done by adding the objects to one of the three FlightGear LOD schemes: "bare", "rough" and "detailed".

In ``osm2city.py`` you can influence into which of the three LOD ranges the objects are placed by using the following :ref:`Parameters <chapter-parameters-label>`:

* LOD_ALWAYS_DETAIL_BELOW_AREA
* LOD_ALWAYS_ROUGH_ABOVE_AREA
* LOD_ALWAYS_ROUGH_ABOVE_LEVELS
* LOD_ALWAYS_BARE_ABOVE_LEVELS
* LOD_ALWAYS_DETAIL_BELOW_LEVELS
* LOD_PERCENTAGE_DETAIL

In FlightGear you can influence the actual distance (in meters) for the respective ranges by one of the following ways:

#. In The FlightGear user interface use menu ``View`` > menu item ``Adjust LOD Ranges`` and then change the values manually.
#. Include command line options into your fgfsrc_ file or `Properties in FGRun`_ like follows:

::

    --prop:double:/sim/rendering/static-lod/detailed=5000
    --prop:double:/sim/rendering/static-lod/rough=10000
    --prop:double:/sim/rendering/static-lod/bare=15000

.. _fgfsrc: http://wiki.flightgear.org/Fgfsrc
.. _`Properties in FGRun`: http://wiki.flightgear.org/FlightGear_Launch_Control#Properties

(Note: previously there was also a osm2city specific LOD range "roof", however that has been abandoned since clustering was introduced. An therefore setting ``--prop:double:/sim/rendering/static-lod/roof=2000`` is not necessary anymore.)


=========================================
Disable Urban Shader and Random Buildings
=========================================

There is no point in having both OSM building scenery objects and dynamically generated buildings in FlightGear. Therefore it is recommended to turn off the ranom building and urban shader features in FlightGear. Please be aware that this will also affect those areas in FlightGear, where there are no generated scenery objects from OSM.

There are two possibilities to disable random buildings:

#. Use command line option ``--disable-random-buildings`` in your fgfsrc_ file — and while you are at it ``--disable-random-objects``.
#. Use the FlightGear menu ``View``, menu item ``Rendering Options``. Tick off ``Random buildings`` and ``Random objects``.

.. image:: fgfs_rendering_options.png

In the same dialog press the ``Shader Options`` button and set the slider for ``Urban`` to the far left in order to disable the urban shader.

.. image:: fgfs_shader_options.png


.. _chapter-hide-urban-textures-label:

=======================================
Change Materials to Hide Urban Textures
=======================================

FlightGear allows to change the texture used for a given landclass. More information is available in ``$FG_ROOT/Docs/README.materials`` as well as in the FlightGear Forum thread regarding `New Regional Textures`_. There is not yet a good base texture replacing the urban textures. However many users find it more visually appealing to use a uniform texture like grass under the generated buildings etc. instead of urban textures.

E.g. for the airport ``LSZS`` in Engadina in Switzerland you would have to go to ``$FG_ROOT/Materials/regions`` and edit file ``europe.xml`` in a text editor: add name-tags for e.g. ``BuiltUpCover``, ``Urban``, ``Town``, ``SubUrban`` to a material as shown below and comment out the existing name-tags using ``<!-- -->``. Basically all name-tags, which relate to a material using ``<effect>Effects/urban</effect>``. The outcome before and after edit (you need to restart FlightGear in between!) can be seen in the screenshots below (for illustration purposes the buildings and roads do not have textures).

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

Depending on your region and your shader settings you might want to search for e.g. ``GrassCover`` in file ``global-summer.xml`` instead (shown in screenshot below with ALS_ and more random vegetation). However be aware that you still need to outcomment in e.g. ``europe.xml`` and within ``global-summer.xml``.

.. image:: fgfs_materials_grass.png


.. _`New Regional Textures`: http://forum.flightgear.org/viewtopic.php?f=5&t=26031

.. _ALS: http://wiki.flightgear.org/Atmospheric_light_scattering