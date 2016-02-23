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

* set the working directory explicitely if you are using an integrated development environment (e.g. PyCharm)
* change into the working directory in your console, e.g.

::
  $ cd /home/pingu/fg_customscenery/projects


====================
Overview of Programs
====================

``osm2city`` contains the following programs to generate scenery objects based on OSM data:

* ``osm2city.py``: generates buildings. See also the related `Wiki osm2city article <http://wiki.flightgear.org/Osm2city.py>`_.
* ``osm2pylon.py``: generates pylons and cables between them for power lines, aerial ways, railway overhead lines as well as streetlamps. See also the related `Wiki osm2pylon article <http://wiki.flightgear.org/Osm2pylons.py>`_.
* ``roads.py``: generates different types of roads. See also the related `Wiki roads article <http://wiki.flightgear.org/Osm2roads.py>`_.
* ``piers.py``: generates piers and boats. See also the related `Wiki piers article <http://wiki.flightgear.org/OsmPiers.py>`_.
* ``platforms.py``: generates (railway) platforms. See also the related `Wiki platforms article <http://wiki.flightgear.org/OsmPlatforms.py>`_.

Calling one of these programs only with command line option ``--help`` or ``-h`` will present all available parameters. E.g.

::

  /usr/bin/python2.7 /home/pingu/develop_vcs/osm2city/platforms.py --help
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

  /usr/bin/python2.7 /home/pingu/develop_vcs/osm2city/osm2city.py -f LSZS/params.ini -l DEBUG -a

Remember that the paths are relative to the ``WORKING_DIRECTORY``. Alternatively provide the full path to your ``params.ini`` [#]_ file.


=====================
Working in Batch Mode
=====================

As described in chapter :ref:`Getting OpenStreetMap data <chapter-getting-data-label>` FlightGear works with tiles and you should not cross tiles boundaries. So in order to cover most of Switzerland you need to run ``osm2city`` related programs for 4 degrees longitude and 2 degrees latitude. In this case there are 4 tiles per longitude and 8 tiles per latitude, i.e. a total of 4*2*4*8 = 256 times. In order to make this process a bit easier, you can use ``build_tiles.py``.

The default work flow is based on the sub-chapters of :ref:`Preparation <chapter-preparation-label>`.
#. :ref:`Run setup.py <chapter-run-setup-label>`
#. Adapt ``params.ini``. This will get copied to several subdirectories as part of the next process steps. Most importantly apapt the parameter ``PATH_TO_OUTPUT`` (in the example below "/home/fg_customscenery/CH_OSM"). The ``PREFIX`` and ``BOUNDARY_*`` parameters will automatically be updated.
#. :ref:`Call build_tiles.py <chapter-build-tiles-label>`. This step creates subdirectories including a set of shell / command scripts. The top directory will be created in your ``WORKING_DIRECTORY`` and have the same name as the lon/lat area specified with parameter ``-t``
#. If needed adapt the params.ini files in the subdirectories if you need to change specific characteristics within one tile (e.g. parameters for building height etc.). In a lot of situations this will not be needed.
#. Call the FIXME scripts
#. :ref:`Copy textures <chapter-copy-textures-label>`


.. _chapter-build-tiles-label:

----------------------
Calling build_tiles.py
----------------------

::

    /usr/bin/python2.7 /home/pingu/develop_vcs/osm2city/batch_processing/build_tiles.py -t e009n47 -f CH_OSM/params_kp.ini -o params.ini

Mandatory command line arguments:
* -t: the name of the 1-degree lon/lat-area, e.g. w003n60 or e012s06 (you need to provide 3 digits for longitude and 2 digits for latitude). The lon/lat position is the lower left corner (e.g. e009n47 to cover most of the Lake of Constance region).
* -f: the relative path to the main params.ini file, which is the template copied to all sub-directories. Be sure to make a decision about parameter ``PATH_TO_OUTPUT``.
* -o: the name of the copied params.ini files in the sub-directories

Optional command line arguments:
* -p: You can use this option on linux and mac in order to generate scripts with parallel processing support and specify the max number of parallel processes when calling the generated scripts. 
* --url: Which API to use to download OSM data on the fly
* -n: FIXME
* -x: If ``python`` is not on your executable path or you want to specify a specific Python version if you have installed different versions, then use this argument (e.g. ``/usr/bin/python2.7``).



tools[ew]XXX[ns][YY].[sh|cmd]

Generated by build-tiles.py and contains the calls to all subdirectories of the tile [ew]XXX[ns][YY].
downloadXXXX.[sh|cmd]

Generated by build-tiles.py and contains wget calls to download all the subtiles of [ew]XXX[ns][YY] into the subdirectories.
osm2cityXXXX.[sh|cmd]

Generated by build-tiles.py and contains the calls to all subdirectories of the tile [ew]XXX[ns][YY].

Example

python osm2city.py -f w010n60/w003n60/2909568/params.ini
python osm2city.py -f w010n60/w003n60/2909569/params.ini
python osm2city.py -f w010n60/w003n60/2909570/params.ini
python osm2city.py -f w010n60/w003n60/2909571/params.ini
python osm2city.py -f w010n60/w003n60/2909576/params.ini
python osm2city.py -f w010n60/w003n60/2909577/params.ini
python osm2city.py -f w010n60/w003n60/2909578/params.ini
python osm2city.py -f w010n60/w003n60/2909579/params.ini
python osm2city.py -f w010n60/w003n60/2909584/params.ini
python osm2city.py -f w010n60/w003n60/2909585/params.ini
python osm2city.py -f w010n60/w003n60/2909586/params.ini
python osm2city.py -f w010n60/w003n60/2909587/params.ini
python osm2city.py -f w010n60/w003n60/2909592/params.ini
python osm2city.py -f w010n60/w003n60/2909593/params.ini
python osm2city.py -f w010n60/w003n60/2909594/params.ini
python osm2city.py -f w010n60/w003n60/2909595/params.ini
python osm2city.py -f w010n60/w003n60/2909600/params.ini
python osm2city.py -f w010n60/w003n60/2909601/params.ini
python osm2city.py -f w010n60/w003n60/2909602/params.ini
python osm2city.py -f w010n60/w003n60/2909603/params.ini
python osm2city.py -f w010n60/w003n60/2909608/params.ini
python osm2city.py -f w010n60/w003n60/2909609/params.ini
python osm2city.py -f w010n60/w003n60/2909610/params.ini
python osm2city.py -f w010n60/w003n60/2909611/params.ini
python osm2city.py -f w010n60/w003n60/2909616/params.ini
python osm2city.py -f w010n60/w003n60/2909617/params.ini
python osm2city.py -f w010n60/w003n60/2909618/params.ini
python osm2city.py -f w010n60/w003n60/2909619/params.ini
python osm2city.py -f w010n60/w003n60/2909624/params.ini
python osm2city.py -f w010n60/w003n60/2909625/params.ini
python osm2city.py -f w010n60/w003n60/2909626/params.ini
python osm2city.py -f w010n60/w003n60/2909627/params.ini

.. [#] ou can name this file whatever you want — "params.ini" is just a convenience / convention.

