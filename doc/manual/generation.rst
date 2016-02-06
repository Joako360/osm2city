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


.. [#] ou can name this file whatever you want — "params.ini" is just a convenience / convention.

