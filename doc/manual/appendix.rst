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
* Volker Schatz's online manual of OSM tools: http://www.volkerschatz.com/net/osm/osmman.html
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

