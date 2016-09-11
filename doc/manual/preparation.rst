.. _chapter-preparation-label:

###########
Preparation
###########

Before ``osm2city`` related programs can be run to generate FlightGear scenery objects, the following steps need to be done:

#. :ref:`Creating a Directory Structure <chapter-creating-directory-structure-label>`
#. :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`
#. :ref:`Setting Minimal Parameters <chapter-setting-parameters-label>`
#. :ref:`Generating Elevation Data <chapter-generating-elevation-data-label>`

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
            LSZS/
                Objects/
                    e000n0040/
                        e009n46/
                            3105315.btg
                            LSZScity0418.ac
                            LSZScity0418.xml
                            ...
            LSMM/
                Objects/
                    ...
            projects/
                LSZS/
                    lszs_narrow.osm
                    params.ini
                    elev.in                  (not always present)
                    elev.out                 (not always present)
                    elev.pkl                 (not always present)
                LSMM/
                    ...


The directory ``flightgear`` contains folder ``fgfs_terrasync``. This is where you have your default FlightGear scenery. The FlightGear Wiki has extensive information about TerraSync_ and how to get data. You need this data in folder, as ``osm2city`` only enhances the scenery with e.g. additional buildings or power pylons.

.. _TerraSync: http://wiki.flightgear.org/TerraSync

The directory ``development`` contains the ``osm2city`` programs and data after installation as explained in :ref:`Installation <chapter-parameters-label>`.

In the example directory structure above the directory ``fg_customscenery`` hosts the input and output information — here two sceneries for airports LSZS and LSMM (however there is no need to structure sceneries by airports). The output of ``osm2city`` scenery generation goes into e.g. ``fg_customscenery/LSZS`` while the input to the scenery generation is situated in e.g. ``fg_customscenery/projects/LSZS`` (how to get the input files in this folder is discussed in the following chapters).

The directory structure in the output folders (e.g. `fg_customscenery/LSZS``) is created by ``osm2city`` related programs, i.e. you do not need to create it manually.

The directory ``.../fg_customscenery/projects`` will be called ``WORKING_DIRECTORY`` in the following. This is important because ``osm2city`` related programs will have assumptions about this.


.. _chapter-getting-data-label:

==========================
Getting OpenStreetMap Data
==========================

The OpenStreetMap Wiki has comprehensive information_ about how to get OSM data. An easy way to start is using Geofabrik's extracts (http://download.geofabrik.de/).

Be aware that ``osm2city`` only accepts OSM data in xml-format, i.e. ``*.osm`` files. Therefore you might need to translate data from the binary ``*.pbf`` format using e.g. Osmosis_. It is highly recommend to limit the area covered as much as possible: it leads to faster processing and it is easier to experiment with smaller areas until you found suitable parameters. If you use Osmosis to cut the area with ``--bounding-box``, then you need to use ``completeWays=yes`` [#]_. E.g. on Windows it could look as follows:

::

    c:\> "C:\FlightGear\osmosis-latest\bin\osmosis.bat" --read-pbf file="C:\FlightGear\fg_customscenery\raw_data\switzerland-latest.osm.pbf"
         --bounding-box completeWays=yes top=46.7 left=9.75 bottom=46.4 right=10.0 --wx file="C:\FlightGear\fg_customscenery\projects\LSZS\lszs_wider.osm"

The exception to the requirement of using OSM data in xml-format is if you use batch processing with the optional ``-d`` command line argument (see :ref:`Calling build_tiles.py <chapter-build-tiles-label>`). In that situation you might want to consider using the pbf-format_.

Please be aware of the `Tile Index Schema`_ in FlightGear. It is advised to set boundaries, which do not cross tiles. Otherwise the scenery objects can jitter and disappear / re-appear due to the clusters of facades crossing tiles. Another reason to keep within boundaries is the sheer amount of data that needs to be kept in memory.

.. _information: http://wiki.openstreetmap.org/wiki/Downloading_data
.. _Osmosis: http://wiki.openstreetmap.org/wiki/Osmosis
.. _`Tile Index Schema`: http://wiki.flightgear.org/Tile_Index_Scheme
.. _pbf-format: http://wiki.openstreetmap.org/wiki/PBF_Format


.. _chapter-setting-parameters-label:

===================================
Setting a Minimal Set of Parameters
===================================

``osm2city`` has a large amount of parameters, by which the generation of scenery objects based on OSM data can be influenced. Chapter :ref:`Parameters <chapter-parameters-label>` has detailed information about all these parameters. However to get started only a few parameters must be specified — actually it is generally recommended only to specify those parameters, which need to get a different value from the default values, so as to have a better understanding for which parameters you have taken an active decision.

Create a ``params.ini`` file with your favorite text editor. In our example it would get stored in ``fg_customscenery/projects/LSZS`` and the minimal content could be as follows:

::

    PREFIX = "LSZS"
    PATH_TO_SCENERY = "/home/flightgear/fgfs_terrasync"
    PATH_TO_OUTPUT = "/home/fg_customscenery/LSZS"
    OSM_FILE = "lszs_narrow.osm"

    BOUNDARY_WEST = 9.81
    BOUNDARY_SOUTH = 46.51
    BOUNDARY_EAST = 9.90
    BOUNDARY_NORTH = 46.54

    NO_ELEV = False
    ELEV_MODE = "Manual"


A few comments on the parameters:

PREFIX
    Needs to be the same as the specific folder below ``fg_customscenery/projects/``. Do not use spaces in the name.

PATH_TO_SCENERY
    Full path to the scenery folder without trailing slash. This is where we will probe elevation and check for overlap with static objects. Most
    likely you'll want to use your TerraSync path here.

PATH_TO_OUTPUT
    The generated scenery (.stg, .ac, .xml) will be written to this path — specified without trailing slash. If empty then the correct location in PATH_TO_SCENERY is used. Note that if you use TerraSync for PATH_TO_SCENERY, you MUST choose a different path here. Otherwise, TerraSync will overwrite the generated scenery. Unless you know what you are doing, there is no reason not to specify a dedicated path here. While not absolutely needed it is good practice to name the output folder the same as ``PREFIX``.
OSM_FILE
    The file containing OpenStreetMap data. See previous chapter :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`. The file should reside in $PREFIX and no path components are allowed (i.e. pure file name).
BOUNDARY_*
    The longitude and latitude of the boundaries of the generated scenery. The boundaries should correspond to the boundaries in the ``OSM_FILE`` (open the \*.osm file in a text editor and check the data in ca. line 3). The boundaries can be different, but then you might either miss data (if the OSM boundaries are larger) or do more processing than necessary (if the OSM boundaries are more narrow).
NO_ELEV
    Set this to ``False``. The only reason to set this to ``True`` would be for developers to check generated scenery objects a bit faster not caring about the vertical position in the scenery.
ELEV_MODE
    See chapter :ref:`Available Elevation Probing Mode<chapter-elev-modes-label>`.


.. _chapter-generating-elevation-data-label:

=========================
Generating Elevation Data
=========================

---------
TerraSync
---------

``osm2city`` uses existing scenery elevation data for two reasons:

* No need to get additional data from elsewhere.
* The elevation of the generated scenery objects need to be align with the underlying scenery data.

This comes at the cost that elevation data must be obtained by "flying" through the scenery, which can be a time consuming process for larger areas — especially if you need a good spatial resolution e.g. in mountain areas like Switzerland. The good part is that you only need to do this once and then only whenever the underlying scenery's elevation data changes (which is quite seldom in the case of scenery from TerraSync_).

Please be aware that the scenery data needed for your area might not have been downloaded yet by TerraSync, e.g. if you have not yet "visited" a specific tile. An easy way to download large areas of data is by using TerraMaster_.

.. _TerraMaster: http://wiki.flightgear.org/TerraMaster

.. _chapter-elev-modes-label:

---------------------------------
Available Elevation Probing Modes
---------------------------------

There are a few different possibilities to generate elevation data, each of which is discussed in details in sub-chapters below. This is what is specified in parameter ``ELEV_MODE`` in the ``params.ini`` file:

* :ref:`ELEV_MODE = "FgelevCaching" <chapter-elev-fgelevcaching-label>`: most automated and convenient
* :ref:`ELEV_MODE = "Fgelev" <chapter-elev-fgelev-label>`: use this instead of ``FgelevCaching`` if you have clear memory or speed limitations
* :ref:`ELEV_MODE = "Telnet" <chapter-elev-telnet-label>`: use this if you cannot compile C++ or use an older FlightGear version
* :ref:`ELEV_MODE = "Manual" <chapter-elev-manual-label>`: fallback method — doing a lot of stuff manually

The two methods using ``Fgelev`` require a bit less manual setup and intervention, however you need to be able to compile a C++ class with dependencies. ``FgelevCaching`` might give the best accuracy, be fastest and most automated. However memory requirements, speed etc. might vary depending on your parameter settings (e.g. ``ELEV_RASTER_*``) and the ratio between scenery area and the number of OSM objects.

All methods apart from ``FgelevCaching`` will generate a file ``elev.out`` to be put into your input folder. ``FgelevCaching`` can also keep data cached (in a file called ``elev.pkl`` in the input directory) — so from a caching perspective there is not much of a difference [#]_.

The next chapters describe each elevation probing mode and link to a :ref:`detailed description of sub-tasks <chapter-subtasks-label>`.

.. FIXME: provide runtime data for each mode for comparison


.. _chapter-elev-fgelevcaching-label:

---------------------------
ELEV_MODE = "FgelevCaching"
---------------------------
In this mode elevation probing happens while running ``osm2city`` related scenery generation — instead of a data preparation task. There are 2 pre-requisites:

#. :ref:`Compile a patched fgelev program <chapter-compile-fgelev-label>`
#. :ref:`Setting parameter FG_ELEV <chapter-set-fgelev-path-label>`
#. :ref:`Setting environment variable FG_ROOT <chapter-set-fgroot-label>`


.. _chapter-elev-fgelev-label:

--------------------
ELEV_MODE = "Fgelev"
--------------------

This elevation probing mode and the next modes generate a file ``elev.out``, which is put or needs to be put into your input folder. Use the following steps:

#. :ref:`Compile a patched fgelev program <chapter-compile-fgelev-label>`
#. :ref:`Setting parameter FG_ELEV <chapter-set-fgelev-path-label>`
#. :ref:`Setting parameters ELEV_RASTER_* <chapter-set-elev-raster-label>`
#. :ref:`Setting environment variable FG_ROOT <chapter-set-fgroot-label>`
#. :ref:`Run tools.py to generate elevation data <chapter-run-tools-label>`


.. _chapter-elev-telnet-label:

--------------------
ELEV_MODE = "Telnet"
--------------------

This mode requires FlightGear to be running and uses a data connection to get elevation data.

#. :ref:`Hide scenery objects <chapter-hide-label>`
#. :ref:`Setting parameters ELEV_RASTER_* <chapter-set-elev-raster-label>`
#. :ref:`Setting parameter TELNET_PORT <chapter-set-telnet-port-label>`
#. :ref:`Run setup.py to prepare elevation probing through Nasal <chapter-run-setup-label>`
#. :ref:`Start FlightGear <chapter-start-fgfs-label>`
#. :ref:`Run tools.py to generate elevation data <chapter-run-tools-label>`
#. Exit FlightGear
#. :ref:`Unhide scenery objects <chapter-unhide-label>`


.. _chapter-elev-manual-label:

--------------------
ELEV_MODE = "Manual"
--------------------

This mode can be used with older FlightGear versions and is save, but also needs a lot of manual steps, which might be error prone. The following steps are needed:

#. :ref:`Hide scenery Objects <chapter-hide-label>`
#. :ref:`Setting parameters ELEV_RASTER_* <chapter-set-elev-raster-label>`
#. :ref:`Adapt file elev.nas <chapter-elev.nas-label>`
#. :ref:`Run tools.py to generate elevation input data <chapter-elev.in-label>`
#. :ref:`Copy file elev.in <chapter-elev.in-copy-label>`
#. :ref:`Start FlightGear <chapter-start-fgfs-label>`
#. Execute a Nasal script (see below)
#. Exit FlightGear
#. :ref:`Copy file elev.out <chapter-elev.out-copy-label>`
#. :ref:`Unhide scenery objects <chapter-unhide-label>`

While FlightGear is running, open menu ``Debug/Nasal Console`` in the FlightGear user interface. Write ``elev.get_elevation()`` and hit the "Execute" button. Be patient as it might seem as nothing is happening for many minutes. At the end you might get output like the following in the ``Nasal Console``:

::

    Checking if tile is loaded
    Position 46.52710817536379 9.878004489017634
    Reading file /home/pingu/.fgfs/elev.in
    Splitting file /home/pingu/.fgfs/elev.in
    Read 231130 records
    Writing 231130 records
    Wrote 231130 records
    Signalled Success



.. _chapter-subtasks-label:

---------------------------------
Detailed Description of Sub-Tasks
---------------------------------

(Note: you need to follow only those sub-tasks, which were specified for the specific elevation probing mode as described above.)

.. _chapter-compile-fgelev-label:

++++++++++++++++++++++
Compile Patched fgelev
++++++++++++++++++++++

``osm2city`` comes with a patched version of ``fgelev``, which by means of a parameter ``expire`` drastically can improve the speed and avoid hanging. The patched version can be found in 
``osm2city`` subdirectory ``fgelev`` as source file ``fgelev.cxx``. Before using it, you need to compile it and then replace the version, which comes with your FlightGear installation in the same directory as ``fgfs``/``fgfs.exe``. In Windows it might be in "D:/Program Files/FlightGear/bin/Win64/fgelev.exe".

Compilation depends on your operating system and hardware. On a Linux Debian derivative you might use the following:

#. Download and compile according to `Scripted Compilation on Linux Debian/Ubuntu`_

#. Replace ``fgelev.cxx`` in e.g. ``./next/flightgear/utils/fgelev`` with the one from ``osm2city/fgelev``

#. Recompile e.g. using the following command:

::

    ./download_and_compile.sh -p n -d n -r n FGFS

.. _`Scripted Compilation on Linux Debian/Ubuntu`: http://wiki.flightgear.org/Scripted_Compilation_on_Linux_Debian/Ubuntu


.. _chapter-set-fgelev-path-label:

+++++++++++++++++++++++++
Setting Parameter FG_ELEV
+++++++++++++++++++++++++

Set parameter ``FG_ELEV`` to point to the full path of the executable. On Linux it could be something like ``FG_ELEV = '/home/pingu/bin/fgfs_git/next/install/flightgear/bin/fgelev'``. On Windows you might have to put quotes around the path due to whitespace e.g. ``FG_ELEV = '"D:/Program Files/FlightGear/bin/Win64/fgelev.exe"'``.


.. _chapter-set-fgroot-label:

+++++++++++++++++++++++++++++++++++++
Setting Environment Variable $FG_ROOT
+++++++++++++++++++++++++++++++++++++

The environment variable ``$FG_ROOT`` must be set in your operating system or at least your current session, such that ``fgelev`` can work optimally. How you set environment variables is depending on your operating system and not described here. I.e. this is NOT something you set as a parameter in ``params.ini``!

`$FG_ROOT`_ is typically a path ending with directories ``data`` or ``fgdata`` (e.g. on Linux it could be ``/home/pingu/bin/fgfs_git/next/install/flightgear/fgdata``).


.. _chapter-set-elev-raster-label:

++++++++++++++++++++++++++++++++
Setting Parameters ELEV_RASTER_*
++++++++++++++++++++++++++++++++

The parameters ``ELEV_RASTER_X`` and ``ELEV_RASTER_Y`` control the spatial resolution of the generated elevation data for all other methods than ``FgelevCaching``. Most of the times it is a good idea to keep the X/Y values aligned. The smaller the values, the better the vertical alignment of generated scenery objects with the underlying scenery, but the more memory and time is used during the generation of elevation data and when using the generated elevation data in ``osm2city``. The smoother the scenery elevation is, the larger values can be chosen for ``ELEV_RASTER_*``. In Switzerland 10 is sufficiently narrow. Keep in mind that the spatial resolution of typical FlightGear elevation data [#]_ is limited and therefore setting small values here will not noticeably improve the visual alignment.


.. _chapter-set-telnet-port-label:

+++++++++++++++++++++++++++++
Setting Parameter TELNET_PORT
+++++++++++++++++++++++++++++

You need to set parameter ``TELNET_PORT`` to the same value as specified in FlightGear parameter ``--telnet`` (e.g. 5501).


.. _chapter-hide-label:

++++++++++++++++++++
Hide Scenery Objects
++++++++++++++++++++

This step is necessary as otherwise the elevation probing might be on top of an existing static or shared object (like an airport hangar). In chapter :ref:`Setting a Minimal Set of Parameters <chapter-setting-parameters-label>` parameter ``PATH_TO_SCENERY`` is described. Below that path is a directory ``Objects``. Rename that directory to e.g. ``Objects_hidden``. Most of the time you might want to do the same for the ``Objects`` directory in ``PATH_TO_OUTPUT`` - unless the ``Objects`` directory does not yet exist.

In rare cases you might have more scenery object folders specified in the FlightGear parameter ``--fg-scenery`` — however you need only to take those into consideration, which place objects into the same area (which is very rare).

PS: this step is not necessary when using mode ``FgelevCaching`` or ``Fgelev``, because data is read directly from scenery elevation information instead of "flying through the scenery".


.. _chapter-unhide-label:

++++++++++++++++++++++
Unhide Scenery Objects
++++++++++++++++++++++

Just do the reverse of what is specified in chapter :ref:`Hide Scenery Objects <chapter-hide-label>`


.. _chapter-start-fgfs-label:

++++++++++++++++
Start FlightGear
++++++++++++++++

Start FlightGear at an airport close to where you want to generate ``osm2city`` scenery objects. You might want to start up with an aircraft using few resources (e.g. Ufo) and a `minimal startup profile <http://wiki.flightgear.org/Troubleshooting_crashes#Minimal_startup_profile>`_ in order to speed things up a bit.

If you use ``ELEV_MODE = "Telnet"` then make sure to you specify command-line parameter ``--telnet`` in FlightGear.


.. _chapter-run-tools-label:

+++++++++++++++++++++++++++++++++++++++
Run tools.py to Generate Elevation Data
+++++++++++++++++++++++++++++++++++++++

Change the work directory to e.g. ``fg_customscenery/projects`` and then run tools.py. On Linux this might look like the following:

::

    $ cd fg_customscenery/projects
    
    $ ls LSZS
    lszs_narrow.osm  params.ini
    
    $ /usr/bin/python3 /home/pingu/development/osm2city/tools.py -f LSZS/params.ini
    ...
    
    $ ls LSZS
    elev.out lszs_narrow.osm  params.ini

At the end of the process there is a new file ``elev.out`` containing the elevation data. If you use command-line option ``-o``, then existing data is not overwritten.


.. _chapter-run-setup-label:

+++++++++++++++++++++++++++++++++++++++++++++++++++++++
Run setup.py to Prepare Elevation Probing through Nasal
+++++++++++++++++++++++++++++++++++++++++++++++++++++++

Change the work directory to e.g. ``fg_customscenery/projects`` and then run setup.py. On Linux this might look like the following:

::

    $ cd fg_customscenery/projects
    
    $ /usr/bin/python3 /home/pingu/development/osm2city/setup.py --fg_root=/home/pingu/bin/fgfs_git/next/install/flightgear/fgdata
    ...

The command-line option ``--fg_root`` is essential and points to `$FG_ROOT`_ (see also :ref:`Setting environment variable $FG_ROOT <chapter-set-fgroot-label>`).

.. _chapter-elev.nas-label:

+++++++++++++++++++
Adapt File elev.nas
+++++++++++++++++++

The root directory of ``osm2city`` contains a file ``elev.nas``. First copy the file into the ``Nasal`` directory in `$FG_ROOT`_ (see also :ref:`Setting environment variable $FG_ROOT <chapter-set-fgroot-label>`).

Then open ``elev.nas`` in a text editor. Change the ``in`` variable as well as the ``out`` variable to a directory with write access (e.g. $FG_HOME/Export). See IORules_ and `$FG_HOME`_.

``elev.nas`` might look as follows BEFORE editing:

::

    var get_elevation = func {
      #Set via setup.py
        setprop("/osm2city/tiles", 0);
        var in = "WILL_BE_SET_BY_SETUP.PY";
        var out = "WILL_BE_SET_BY_SETUP.PY";

        print( "Checking if tile is loaded");
        ...

AFTER editing ``elev.nas`` might look as follows on Windows:

::

    ...
        var in = "C:/Users/Bill/AppData/Roaming/flightgear.org/elev.in";
        var out = "C:/Users/Bill/AppData/Roaming/flightgear.org/Export/";
        ...

AFTER editing ``elev.nas`` might look as follows on Linux:

::

    ...
        var in = "/home/pingu/.fgfs/elev.in";
        var out = "/home/pingu/.fgfs/Export/";
        ...


.. _IORules: http://wiki.flightgear.org/IORules
.. _$FG_HOME: http://wiki.flightgear.org/$FG_HOME
.. _$FG_ROOT: http://wiki.flightgear.org/$FG_ROOT

(Note: the description in this sub-task is basically what :ref:`running setup.py <chapter-run-setup-label>` does automatically.)


.. _chapter-elev.in-label:

+++++++++++++++++++++++++++++++++++++++++++++
Run tools.py to Generate Elevation Input Data
+++++++++++++++++++++++++++++++++++++++++++++

Change the work directory to e.g. ``fg_customscenery/projects`` and then run tools.py. On Linux this might look like the following:

::

    $ cd fg_customscenery/projects
    
    $ ls LSZS
    lszs_narrow.osm  params.ini
    
    $ /usr/bin/python3 /home/pingu/development/osm2city/tools.py -f LSZS/params.ini
    ...
    
    $ ls LSZS
    elev.in  lszs_narrow.osm  params.ini


.. _chapter-elev.in-copy-label:

+++++++++++++++++
Copy File elev.in
+++++++++++++++++

Copy file ``elev.in`` from the input directory to the path specified in the edited ``elev.nas`` file (see :ref:`Adapt File elev.nas <chapter-elev.nas-label>`).


.. _chapter-elev.out-copy-label:

++++++++++++++++++
Copy File elev.out
++++++++++++++++++

Finally copy file ``elev.out`` from the path specified in the edited ``elev.nas`` file (see :ref:`Adapt File elev.nas <chapter-elev.nas-label>`) to the input directory (e.g. ``fg_customscenery/projects/LSZS``).



.. [#] Failing to do so might result in an exception, where the stack trace might contain something like ``KeyError: 1227981870``.

.. [#] It is a bit more complicated than that. The three other methods keep data in a grid — and the grid stays the same across e.g. ``osm2city`` and ``osm2pylon``. That is different for ``FgelevCaching``, because it will get the position for every object, which by nature is different between e.g. ``osm2city`` and ``osm2pylon``.

.. [#] See `Using TerraGear <http://wiki.flightgear.org/Using_TerraGear#Elevation_data>`_.
