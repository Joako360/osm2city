.. _chapter-preparation-label:

#####################
Preparation [Builder]
#####################

Before ``osm2city`` related programs can be run to generate FlightGear scenery objects, the following steps need to be done:

#. :ref:`Creating a Directory Structure <chapter-creating-directory-structure-label>`
#. :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`
#. :ref:`Setting Minimal Parameters <chapter-setting-parameters-label>`
#. :ref:`Generating elevation data <chapter-generating-elevation-data-label>`

It is recommended to start with generating scenery objects for a small area around a smaller airport outside of big cities, such that manual errors are found fast. Once you are acquainted with all process steps, you can experiment with larger and denser areas.


.. _chapter-creating-directory-structure-label:

==============================
Creating a Directory Structure
==============================

The following shows a directory structure, which one of the developers is using — feel free to use any other structure.

::

    HOME/
        flightgear/
            fgfs_terrasync/
                Airports/
                Models/
                Objects/
                Terrain/
                terrasync-cache.xml
        development
            osm2city/
            osm2city-data/
            ...
        fg_customscenery/
            KBOS/
                Buildings/
                    w080n40/
                        w071n42/
                            3105315.btg
                            w080n40_w071n42_1794312city00000.ac
                            ...
                Pylons/
                    ...
                Roads/
                    ...
            LSME/
                Buildings/
                    ...
            projects/
                KBOS/
                    kbos_narrow.osm          (not needed it database is used)
                    params.ini
                LSME/
                    ...


The directory ``flightgear`` contains folder ``fgfs_terrasync``. This is where you have your default FlightGear scenery. The FlightGear Wiki has extensive information about TerraSync_ and how to get data. You need this data in folder, as ``osm2city`` only enhances the scenery with e.g. additional buildings or power pylons.

.. _TerraSync: http://wiki.flightgear.org/TerraSync

The directory ``development`` contains the ``osm2city`` programs and data after installation as explained in :ref:`Installation <chapter-parameters-label>`.

In the example directory structure above the directory ``fg_customscenery`` hosts the input and output information — here two sceneries for airports KBOS and LSME (however there is no need to structure sceneries by airports). The output of ``osm2city`` scenery generation goes into e.g. ``fg_customscenery/KBOS`` while the input to the scenery generation is situated in e.g. ``fg_customscenery/projects/KBOS`` (how to get the input files in this folder is discussed in the following chapters).

The directory structure in the output folders (e.g. ``fg_customscenery/KBOS``) is created by ``osm2city`` related programs, i.e. you do not need to create it manually.

The directory ``.../fg_customscenery/projects`` will be called ``WORKING_DIRECTORY`` in the following. This is important because ``osm2city`` related programs will have assumptions about this.


.. _chapter-getting-data-label:

==========================
Getting OpenStreetMap Data
==========================

The OpenStreetMap Wiki has comprehensive information_ about how to get OSM data. An easy way to start is using Geofabrik's extracts (http://download.geofabrik.de/).

Unless you are using a PostGIS database as input, then be aware that ``osm2city`` only accepts OSM data in xml-format, i.e. ``*.osm`` files. Therefore you might need to translate data from the binary ``*.pbf`` format using e.g. Osmosis_. It is highly recommend to limit the area covered as much as possible: it leads to faster processing and it is easier to experiment with smaller areas until you found suitable parameters. If you use Osmosis to cut the area with ``--bounding-box``, then you need to use ``completeWays=yes`` [#]_. E.g. on Windows it could look as follows:

::

    c:\> "C:\FlightGear\osmosis-latest\bin\osmosis.bat" --read-pbf file="C:\FlightGear\fg_customscenery\raw_data\switzerland-latest.osm.pbf"
         --bounding-box completeWays=yes top=46.7 left=9.75 bottom=46.4 right=10.0 --wx file="C:\FlightGear\fg_customscenery\projects\LSZS\lszs_wider.osm"

The exception to the requirement of using OSM data in xml-format is if you use batch processing with the optional ``-d`` command line argument (see :ref:`Calling build_tiles.py <chapter-build-tiles-label>`). In that situation you might want to consider using the pbf-format_.

Please be aware of the `Tile Index Schema`_ in FlightGear. It is advised to set boundaries, which do not cross tiles. Otherwise the scenery objects can jitter and disappear / re-appear due to the clusters of facades crossing tiles. Another reason to keep within boundaries is the sheer amount of data that needs to be kept in memory.

E.g. Switzerland is around 46 degrees of latitude, therefore the boundary can be set in increments of 0.125 degrees of latitude and 0.25 degrees of longitude. Smaller works fine. If you are using the recommended approach of :ref:`batch processing <chapter-batch-mode>`, then these details will be taken care of for you automatically.

.. _information: http://wiki.openstreetmap.org/wiki/Downloading_data
.. _Osmosis: http://wiki.openstreetmap.org/wiki/Osmosis
.. _`Tile Index Schema`: http://wiki.flightgear.org/Tile_Index_Scheme
.. _pbf-format: http://wiki.openstreetmap.org/wiki/PBF_Format


.. _chapter-setting-parameters-label:

===================================
Setting a Minimal Set of Parameters
===================================

``osm2city`` has a large amount of parameters, by which the generation of scenery objects based on OSM data can be influenced. Chapter :ref:`Parameters <chapter-parameters-label>` has detailed information about the most important of these parameters[#]_. However to get started only a few parameters must be specified — actually it is generally recommended only to specify those parameters, which need to get a different value from the default values, so as to have a better understanding for which parameters you have taken an active decision.

Create a ``params.ini`` file with your favorite text editor. In our example it would get stored in ``fg_customscenery/projects/LSZS`` and the minimal content could be as follows:

::

    PREFIX = "LSZS"
    PATH_TO_SCENERY = "/home/flightgear/fgfs_terrasync"
    PATH_TO_OUTPUT = "/home/fg_customscenery/LSZS"
    PATH_TO_OSM2CITY_DATA = "/home/user/osm2city-data"
    OSM_FILE = "lszs_narrow.osm"

    BOUNDARY_WEST = 9.81
    BOUNDARY_SOUTH = 46.51
    BOUNDARY_EAST = 9.90
    BOUNDARY_NORTH = 46.54

    NO_ELEV = False
    FG_ELEV = '/home/pingu/bin/fgfs_git/next/install/flightgear/bin/fgelev'


A few comments on the parameters:

PREFIX
    Needs to be the same as the specific folder below ``fg_customscenery/projects/``. Do not use spaces in the name.

PATH_TO_SCENERY
    Full path to the scenery folder without trailing slash. This is where we will probe elevation and check for overlap with static objects. Most
    likely you'll want to use your TerraSync path here.

PATH_TO_OUTPUT
    The generated scenery files (.stg, .ac) will be written to this path — specified without trailing slash. If empty then the correct location in PATH_TO_SCENERY is used. Note that if you use TerraSync for PATH_TO_SCENERY, you MUST choose a different path here. Otherwise, TerraSync will overwrite the generated scenery. Unless you know what you are doing, there is no reason not to specify a dedicated path here. While not absolutely needed, it is good practice to name the output folder the same as ``PREFIX``.
OSM_FILE
    The file containing OpenStreetMap data. See previous chapter :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`. The file should reside in $PREFIX and no path components are allowed (i.e. pure file name). If you have your data in PostGIS, then instead you need to specify the :ref:`database parameters <chapter-parameters-database>`.
BOUNDARY_*
    The longitude and latitude of the boundaries of the generated scenery. The boundaries should correspond to the boundaries in the ``OSM_FILE`` (open the \*.osm file in a text editor and check the data in ca. line 3) respectively the data in PostGIS. The boundaries can be different, but then you might either miss data (if the OSM boundaries are larger) or do more processing than necessary (if the OSM boundaries are more narrow and you use a fiel based approach — not an issue when using a database).
NO_ELEV
    Set this to ``False``. The only reason to set this to ``True`` would be for builders to check generated scenery objects a bit faster not caring about the vertical position in the scenery.
FG_ELEV
    Set parameter ``FG_ELEV`` to point to the full path of the fgelev executable. On Linux it could be something like ``FG_ELEV = '/home/pingu/bin/fgfs_git/next/install/flightgear/bin/fgelev'``. On Windows you might have to put quotes around the path due to whitespace e.g. ``FG_ELEV = '"D:/Program Files/FlightGear/bin/Win64/fgelev.exe"'`` (yes, both single and double quotes).


.. _chapter-generating-elevation-data-label:

=========================
Generating Elevation Data
=========================

``osm2city`` uses scenery elevation data from the FlightGear sceneries (TerraSync) for two reasons:

* No need to get additional data from elsewhere.
* The elevation of the generated scenery objects need to be aligned with the underlying scenery data (otherwise houses could hover over the ground or be invisible because below ground level).

This comes at the cost that elevation data must be obtained by "flying" through the scenery, which can be a time consuming process for larger areas — especially if you need a good spatial resolution e.g. in mountain areas like Switzerland.

Please be aware that the scenery data needed for your area might not have been downloaded yet by TerraSync, e.g. if you have not yet "visited" a specific tile. An easy way to download large areas of data is by using TerraMaster_. If you are exclusively using TerraMaster_ to download data, then make sure that you in TerraMaster also use button "Synchronise shared models".

.. _TerraMaster: http://wiki.flightgear.org/TerraMaster

.. _chapter-elev-modes-label:


.. [#] Failing to do so might result in an exception, where the stack trace might contain something like ``KeyError: 1227981870``.
.. [#] Many parameters are self-explanatory by their name. Otherwise have a look at the comments in parameters.py
