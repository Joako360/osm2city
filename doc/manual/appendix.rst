.. _chapter-appendix-label:

########
Appendix
########


.. _chapter-osm-database-label:

========================================
OSM Data in a PostGIS Database [Builder]
========================================

The following chapters are dedicated to give some information and pointers to keeping OSM data in a database instead of files for processing in osm2city. This is not a complete guide and will concentrate on only one possible scenario: `PostGIS <http://www.postgis.net/>`_ on Ubuntu Linux.

Some overall pointers:

* PostGIS on OSM wiki: http://wiki.openstreetmap.org/wiki/PostGIS
* Book PostGIS in Action, especially chapter 4.4 of the 2nd edition: http://www.postgis.us/
* PostgreSQL on Ubuntu: https://help.ubuntu.com/community/PostgreSQL
* Volker Schatz's online manual of OSM tools: http://www.volkerschatz.com/net/osm/osmman.html, e.g. osm2pgsql `database format <http://www.volkerschatz.com/net/osm/osm2pgsql-db.html>`_ and `usage <http://www.volkerschatz.com/net/osm/osm2pgsql-usage.html>`_.
* HStore information in PostgreSQL: https://www.postgresql.org/docs/devel/static/hstore.html
* HStore and minutely OSM planet dump info in German: http://wiki.openstreetmap.org/wiki/DE:HowTo_minutely_hstore


=====================
Developer Information
=====================

-------------
Documentation
-------------

You need to install Sphinx_. All documentation is written using reStructuredText_ and then made available on `Read the Docs`_.

Change into ``docs/manual`` and then run the following command to test on your local machine:

::

    $ sphinx-build -b html . build


.. _Sphinx: http://www.sphinx-doc.org
.. _reStructuredText: http://docutils.sourceforge.net/rst.html
.. _Read the Docs: https://readthedocs.org/


----------
Developing
----------

An unstructured list of stuff you might need to know as a developer:

* The code has evolved over time by contributions from persons, who are not necessarily professional Python developers. Whenever you touch or even only read a piece of code, please leave the place in a better state by adding comments with your understanding, refactoring etc.
* The level of unit testing is minimal and below what is achievable. There is no system testing. All system testing is done in a visual way - one of the reasons being that the scenery generation has randomising elements plus parametrisation, which means there is not deterministic right solution even from a regression point of view.
* Apart from testing the results in FlightGear by flying around with e.g. the UFO_, a few operations make use of a parameter ``DEBUG_PLOT_*``, which plots results to a pdf-file:

  * ``DEBUG_PLOT_RECTIFY``: Examples of rectified building floor plans
  * ``DEBUG_PLOT_GENBUILDINGS``: Result of generating buildings
  * ``DEBUG_PLOT_LANDUSE``: Different aspects of land-use
  * ``DEBUG_PLOT_ROADS``: Different plots for aspects of roads processing
  * ``DEBUG_PLOT_OFFSETS``: Showing offsets when placing rectangle (utility function)
* Use an editor, which supports `PEP 08`_. However the current main developer prefers a line length of 120 instead. You should be able to live with that.
* Use Python `type hints`_ as far as possible ??? and help improve the current situation. It might make the code a bit harder to read, but it gets so much easier to understand.
* Try to stick to the Python version as referenced in requirements.txt (cf. :ref:`Python<chapter-python-label>`).
* All code in utf-8. On Windows please make sure that line endings get correct in git (core.autocrlf)
* Coordinate systems:

  * FlightGear uses a set of different `coordinate systems`_. The most important for referencing models in stg-files is WGS84_, which uses lon/lat. In the Cartesian coordinate system in a tile +X is North, +Y is East and +Z is up.
  * OSM references WGS84_ as the datum.
  * The Ac3D format uses x-axis to the right, y-axis upwards and z-axis forward, meaning that the bottom of an object is in x-z space and the front is in x-y. I.e. a right-handed coordinate system.
  * osm2city uses a local cartesian coordinate system in meters close enough for measurements within a tile, where x is lon-direction and y is lat-direction. The object height is then in z-direction (see module ``utils/coordinates.py``). I.e. x pointing to the right and y pointing inwards in a right-handed coordinate system. Meaning the bottom of an object i in x-y space. Therefore a node in the local (cartographic) coordinate system gets translated as follows to a node in a AC3D object in osm2city: x_ac3d = - y_local, y_ac3d = height_above_ground, z_ac3d = - x_local



.. _UFO: http://wiki.flightgear.org/UFO_from_the_%27White_Project%27_of_the_UNESCO
.. _PEP 08: https://www.python.org/dev/peps/pep-0008/
.. _type hints: https://docs.python.org/3/library/typing.html
.. _coordinate systems: http://wiki.flightgear.org/Geographic_Coordinate_Systems
.. _WGS84: https://en.wikipedia.org/wiki/World_Geodetic_System
