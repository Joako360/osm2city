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


----------
Developing
----------

An unstructured list of stuff you might need to know as a developer:

* The code has evolved over time by contributions from persons, who are not necessarily professional Python developers. Whenever you touch or even only read a piece of code, please leave the place in a better state by adding comments with your understanding, refactoring etc.
* The level of unit testing is minimal and below what is achievable. There is no system testing. All system testing is done in a visual way - one of the reasons being that the scenery generation has randomising elements plus parametrisation, which means there is not deterministic right solution even from a regression point of view.
* Use an editor, which supports `PEP 08`_. However the current main developer prefers a line length of 120 instead. You should be able to live with that.
* Use Python `type hints`_ as far as possible — and help improve the current situation. It might make the code a bit harder to read, but it gets so much easier to understand.
* Try to stick to the Python version as referenced in :ref:`Python<chapter-python-label>`.


.. _PEP 08: https://www.python.org/dev/peps/pep-0008/
.. _type hints: https://docs.python.org/3/library/typing.html
