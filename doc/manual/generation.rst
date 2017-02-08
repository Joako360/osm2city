.. _chapter-generation-label:

##################
Scenery Generation
##################

=============================
Setting the Working Directory
=============================

``osm2city`` needs to make some assumption about the absolute paths. Unfortunately there are still some residuals assuming the the information is processed relative to a specific directory (e.g. the root folder of ``osm2city``). Please report if you cannot find generated or copied files (e.g. textures) respectively get file related exceptions.

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

In order to be able to use textures for buildings a texture atlas (a structured collection of textures stored in a single image file) needs to be created. As this is a bit of a time consuming task, re-creating a texture atlas should only be done if the contained textures change. That is rarely the case. Also remember that if the texture atlas changes, then also the content has to be copied separately (see :ref:`chapter-copy-textures-label`).

In most situations it is enough to call the following command once and then only if the textures have changed:

::

  /usr/bin/python3 /home/pingu/develop_vcs/osm2city/prepare_textures.py -f LSZS/params.ini


Chapter :ref:`Textures <chapter-parameters-textures>` has an overview of how roof and facade textures can be filtered to suit a given scenery's needs by means of parameters.


====================
Overview of Programs
====================

``osm2city`` contains the following programs to generate scenery objects based on OSM data:

* ``buildings.py``: generates buildings. See also the related `Wiki osm2city article <http://wiki.flightgear.org/Osm2city.py>`_.
* ``pylons.py``: generates pylons and cables between them for power lines, aerial ways, railway overhead lines as well as street-lamps. See also the related `Wiki osm2pylon article <http://wiki.flightgear.org/Osm2pylons.py>`_.
* ``roads.py``: generates different types of roads. See also the related `Wiki roads article <http://wiki.flightgear.org/Osm2roads.py>`_.
* ``piers.py``: generates piers and boats. See also the related `Wiki piers article <http://wiki.flightgear.org/OsmPiers.py>`_.
* ``platforms.py``: generates (railway) platforms. See also the related `Wiki platforms article <http://wiki.flightgear.org/OsmPlatforms.py>`_.

Calling one of these programs only with command line option ``--help`` or ``-h`` will present all available parameters. E.g.

::

  /usr/bin/python3 /home/pingu/develop_vcs/osm2city/platforms.py --help
  usage: platforms.py [-h] [-f FILE] [-l LOGLEVEL]

  platform.py reads OSM data and creates platform models for use with FlightGear

  optional arguments:
    -h, --help            show this help message and exit
    -f FILE, --file FILE  read parameters from FILE (e.g. params.ini)
    -l LOGLEVEL, --loglevel LOGLEVEL
                        set loglevel. Valid levels are VERBOSE, DEBUG, INFO,
                        WARNING, ERROR, CRITICAL

In most situations you may want to at least provide command line parameter ``-f`` and point to a ``params.ini`` file. E.g.

::

  /usr/bin/python3 /home/pingu/develop_vcs/osm2city/buildings.py -f LSZS/params.ini -l DEBUG

Remember that the paths are relative to the ``WORKING_DIRECTORY``. Alternatively provide the full path to your ``params.ini`` [#]_ file.


.. _chapter-batch-mode:

=====================
Working in Batch Mode
=====================

As described in chapter :ref:`Getting OpenStreetMap data <chapter-getting-data-label>` FlightGear works with tiles and scenery objects should not excessively cross tiles boundaries. So in order to cover most of Switzerland you would need to run ``osm2city`` related programs for 4 degrees longitude and 2 degrees latitude. Given the geographic location of Switzerland there are 4 tiles per longitude and 8 tiles per latitude. I.e. a total of 4*2*4*8 = 256 tiles. In order to make this process a bit easier, you can use 2 types of batch modes:

* ``build_tiles.py``, which creates a set of shell scripts and a suitable directory structure
* ``build_tiles_db``, which works on top of data in a database

Working with a database requires additional steps in setting up data in a database, however all subsequent steps require much less work - especially if working across several degrees of latitude or longitude.


---------------------------------------------
Database Based Batches with build_tiles_db.py
---------------------------------------------

As a first step you must :ref:`prepare OSM data in a database<chapter-osm-database-label>`. Be sure that the data in the database covers the whole area for batch processing.

Calling the batch process is then pretty easy in just one step:

::

    $ /usr/bin/python3 /home/pingu/develop_vcs/osm2city/batch_processing/build_tiles_db.py -f TEST/params.ini -b 8.25_47_8.5_47.2 -p 3

Mandatory command line arguments:

* -b: the boundary as an underscore delimitted string WEST_SOUTH_EAST_NORTH like 9.1_47.0_11_48.8 (use '.' as decimal separator).
* -f: the relative path to the main params.ini file, which is the template copied to all sub-directories.
* -p: number of parallel processes (should not be more than the number of cores/CPUs) and might be constrained by memory

You need to have set parameter ``USE_DATABASE`` to ``True`` and might want to consider setting parameter ``FG_ELEV_CACHE`` to ``False`` in case you build a huge area due to disk usage.


--------------------------------------
File Based Batches with build_tiles.py
--------------------------------------

The default work flow is based on the sub-chapters of :ref:`Preparation <chapter-preparation-label>`:

#. Adapt ``params.ini``. This will get copied to several subdirectories as part of the next process steps. Most importantly adapt the parameter ``PATH_TO_OUTPUT`` (in the example below "/home/fg_customscenery/CH_OSM"). The ``PREFIX`` and ``BOUNDARY_*`` parameters will automatically be updated.
#. In most situations you might want to :ref:`create a texture atlas<chapter-create-texture-atlas>` first, so it corresponds to the the chosen parameters.
#. :ref:`Call build_tiles.py <chapter-build-tiles-label>`. This step creates sub-directories including a set of shell / command scripts. The top directory will be created in your ``WORKING_DIRECTORY`` and have the same name as the lon/lat area specified with argument ``-t``
#. If needed adapt the params.ini files in the sub-directories if you need to change specific characteristics within one tile (e.g. parameters for building height etc.). In most situations this will not be needed.
#. It is imperative that you call ``download_xxxxx.sh`` first. Make sure you are still in the correct working directory, because path names are relative.
#. Afterwards call ``buildings_xxxxx.sh``, ``pylons_xxxxx.sh`` etc. depending on your requirements.
#. :ref:`Copy textures, effects and other data <chapter-copy-textures-label>`


.. _chapter-build-tiles-label:

......................
Calling build_tiles.py
......................

::

    $ /usr/bin/python3 /home/pingu/develop_vcs/osm2city/batch_processing/build_tiles.py -t e009n47 -f CH_OSM/params_kp.ini -o params.ini

Mandatory command line arguments:

* -t: the name of the 1-degree lon/lat-area, e.g. w003n60 or e012s06 (you need to provide 3 digits for longitude and 2 digits for latitude). The lon/lat position is the lower left corner (e.g. e009n47 to cover most of the Lake of Constance region in Europe).
* -f: the relative path to the main params.ini file, which is the template copied to all sub-directories.

Optional command line arguments:

* -p: You can use this option on Linux and Mac in order to generate scripts with parallel processing support and specify the max number of parallel processes when calling the generated scripts. 
* -u: The URL of the API to use to download OSM data on the fly (e.g. http://www.overpass-api.de/api/xapi_meta?). Only useful if argument ``-d`` is not used.
* -n: There are two implementations of downloading data on the fly. If this option is used, then a download program is used, which has better support for retries (FIXME: does this work?)
* -x: If ``python`` is not in your executable path or you want to specify a specific Python version if you have installed several versions, then use this argument (e.g. ``/usr/bin/python3.5``).
* -d: Instead of dynamic download an existing OSM data file as specified in the overall ``params.ini`` will be used. This can be used if e.g. ``curl`` is not available (mostly on Windows) or if you have problems with dynamic download or if you need to manipulate the OSM data after download and before processing. A pre-requisite for this is that you have Osmosis installed on your computer (see also :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`) — the path to the Osmosis executable needs to be specified with this command line argument.
* -o: the name of the copied params.ini files in the sub-directories. There is rarely a reason to deviate from the standard and therefore using this parameter.

Calling build_tiles.py with optional argument ``-d`` could look like the following:

::

    $ /usr/bin/python3 /home/pingu/develop_vcs/osm2city/batch_processing/build_tiles.py -t e009n47 -f CH_OSM/params.ini -o params.ini -x /usr/bin/python3 -d /home/pingu/bin/osmosis-latest/bin/osmosis


``build_tiles.py`` creates a directory layout like the following:

::

    HOME/
        fg_customscenery/
            projects/
                e000n40/
                    download_e009n47.sh        # If option -d was chosen, then the commands within will call Osmosis and not download stuff
                    buildings_e009n47.sh
                    pylons_e009n47.sh
                    piers_e009n47.sh
                    platforms_e009n47.sh
                    roads_e009n47.sh


The contents of ``buildings_e009n47.sh`` looks like the following if argument ``-p`` was not used. Otherwise the file would start with bash instructions for parallelization.

::

    #!/bin/bash
    python buildings.py -f w010n60/w003n60/2909568/params.ini
    python buildings.py -f w010n60/w003n60/2909569/params.ini
    ...
    python buildings.py -f w010n60/w003n60/2909627/params.ini


If you used argument ``-p`` during generation of the shell / command files, then you would add the number of parallel processes like the following (in the example 4 processes):

::

    $ ./e000n40/buildings_e009n47.sh 4


.. [#] you can name this file whatever you want — "params.ini" is just a convenience / convention.
