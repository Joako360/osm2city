.. _chapter-generation-label:

############################
Scenery Generation [Builder]
############################

=============================
Setting the Working Directory
=============================

``osm2city`` needs to make some assumption about the absolute paths.

It is recommended to make conscious decisions about the :ref:`directory structure <chapter-creating-directory-structure-label>` and choosing the ``WORKING_DIRECTORY`` accordingly.

Therefore before running ``osm2city`` related programs please either:

* set the working directory explicitly if you are using an integrated development environment (e.g. PyCharm)
* change into the working directory in your console, e.g.

::

  $ cd /home/pingu/fg_customscenery/projects


.. _chapter-create-texture-atlas:

==========================
Creating the Texture Atlas
==========================

If you are creating sceneries to be consumed by others using a FG version 2017.2 or later, then please skip this chapter — unless you know what you are doing. Skipping will just use the texture atlas already provided by ``osm2city-data``.

In order to be able to use textures for buildings a texture atlas (a structured collection of textures stored in a single image file) needs to be created. Re-creating a texture atlas should only be done if the contained textures change. That is rarely the case. Also remember that if the texture atlas changes, then also the content has to be copied into FGData_ /Textures/osm2city (which has to be done either manually by the scenery user og by committing to the FlightGear FGData repository - meaning that it is first generally available with the next FlightGear release).

In most situations it is enough to call the following command once and then only if the textures have changed:

::

  /usr/bin/python3 /home/pingu/develop_vcs/osm2city/prepare_textures.py -f LSZS/params.ini


Chapter :ref:`Textures <chapter-parameters-textures>` has an overview of how roof and facade textures can be filtered to suit a given scenery's needs by means of parameters.

.. _FGData: http://wiki.flightgear.org/FGData


==================================================
Running the Generation Scripts with build_tiles.py
==================================================

As a first step you must :ref:`prepare OSM data in a database<chapter-osm-database-label>`. Be sure that the data in the database covers the whole area for batch processing.

Calling the batch process is then pretty easy in just one step:

::

    $ /usr/bin/python3 /home/pingu/develop_vcs/osm2city/batch_processing/build_tiles_db.py -f TEST/params.ini -b 8.25_47_8.5_47.2 -p 3

Mandatory command line arguments:

* ``-b``: the boundary as an underscore delimited string WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (use '.' as decimal separator). If the Western longitude is negative (e.g. in Americas), then use an asterisk character (``*``) in front (e.g. ``-b *-71.25_42.25_-70.75_42.5`` for the Boston Logan airport KBOS).
* ``-f``: the relative path to the main params.ini file. Remember that the paths are relative to the ``WORKING_DIRECTORY``.
* ``-p``: number of parallel processes (should not be more than the number of cores/CPUs) and might be constrained by memory

Optional arguments:

* ``-h``, ``--help``: show a help message and exit
* ``-l`` LOGLEVEL, ``--loglevel`` LOGLEVEL: sets the  loglevel. Valid levels are VERBOSE, DEBUG, INFO, WARNING, ERROR, CRITICAL
* ``-e`` PROCEDURE, ``--execute`` PROCEDURE: execute only the given procedure[s]. Otherwise everything is generated (subject to refinement by :ref:`parameters<chapter-parameters-pylons_details>`, not arguments):

  + ``buildings``: generates buildings
  + ``roads``: generates different types of roads and railway lines
  + ``pylons``: generates pylons and cables between them for (major) power lines. Also creates wind turbines, storage tanks and chimneys.
  + ``main``: all of the above
  + ``details``: generates (railway) platforms, piers and boats as well as minor power lines, aerial ways, railway overhead lines as well as street-lamps.


You might want to consider setting parameter ``FG_ELEV_CACHE`` to ``False`` in case you build a huge area due to disk usage.


===============================================
Consider Sharing Your Generated Scenery Objects
===============================================

Although this guide hopefully helps, not everybody might be able to generate scenery objects wih ``osm2city`` related programs. Therefore please consider sharing your generated scenery objects. You can do so by announcing it in the Sceneries_ part of the FlightGear Forums and linking from the bottom of the ``osm2city`` related Wiki_ article.

.. _Sceneries: http://forum.flightgear.org/viewforum.php?f=5
.. _Wiki: http://wiki.flightgear.org/Osm2city.py
