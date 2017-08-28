.. _chapter-appendix-label:

####################
Appendix [Developer]
####################


.. _chapter-osm-database-label:

==============================
OSM Data in a PostGIS Database
==============================

The following chapters are dedicated to give some information and pointers to keeping OSM data in a database instead of files for processing in osm2city. This is not a complete guide and will concentrate on only one possible scenario: `PostGIS <http://www.postgis.net/>`_ on Ubuntu Linux.

Some overall pointers:

* PostGIS on OSM wiki: http://wiki.openstreetmap.org/wiki/PostGIS
* Book PostGIS in Action, especially chapter 4.4 of the 2nd edition: http://www.postgis.us/
* PostgreSQL on Ubuntu: https://help.ubuntu.com/community/PostgreSQL
* Volker Schatz's online manual of OSM tools: http://www.volkerschatz.com/net/osm/osmman.html
* HStore information in PostgreSQL: https://www.postgresql.org/docs/devel/static/hstore.html
* HStore and minutely OSM planet dump info in German: http://wiki.openstreetmap.org/wiki/DE:HowTo_minutely_hstore


------------------
Installed Packages
------------------

On Ubuntu 16.04 the following packages have amongst others been installed (not exhaustive list):

* postgresql-9.5
* postgresql-client-9.5
* postgresql-contrib-9.5
* pgadmin3
* postgis
* python-psycopg2

On top of that you also need a 0.6+ version of Osmosis_. Please be aware of the fact that you also need a related version of Java and that e.g. in Ubuntu 16.04 Osmosis is out of date.


------------------------------------
Creating a database and loading data
------------------------------------

* The following examples of usage will assume that the database name is ``kbos`` and the user is ``gisuser``. Of course your installation can differ and you can set different parameters foŕ :ref:`Database <chapter-parameters-database>`.
* See :ref:`Getting OpenStreetMap Data <chapter-getting-data-label>`. To get data for the whole planet go to Planet OSM (http://planet.osm.org/).
* Setting up a PostGIS database as described in `PostGIS setup`_ (replace ``pgsnapshot`` with whatever you named the database, e.g. ``osmogis``). For now schema support for linestrings does not have to be set up. However you need to run at least ``pgsnapshot_schema_0.6.sql`` and ``pgsimple_schema_0.6_bbox.sql``.
* Load data (see also `PostGIS Tasks (Snapshot Schema)`_)
* Update the indices in the database


Preparing the database might look as follows:

::

    $ sudo -u postgres createdb --encoding=UTF8 --owner=gisuser kbos

    $ psql --username=postgres --dbname=kbos -c "CREATE EXTENSION postgis;"
    $ psql --username=postgres --dbname=kbos -c "CREATE EXTENSION hstore;"'

    $ psql --username=postgres -d kbos -f /home/vanosten/bin/osmosis-latest/script/pgsnapshot_schema_0.6.sql
    $ psql --username=postgres -d kbos -f /home/vanosten/bin/osmosis-latest/script/pgsnapshot_schema_0.6_bbox.sql

The you might first cut down the downloaded OSM pbf-file to the needed area and finally import it to the database:

::

    $ /home/vanosten/bin/osmosis-latest/bin/osmosis --read-pbf file="/media/sf_fg_customscenery/projects/TEST/massachusetts-latest.osm.pbf" --bounding-box completeWays=yes top=42.625 left=-72 bottom=42.125 right=-70.5 --write-pbf file="/media/sf_fg_customscenery/projects/TEST/kbos.pbf"

    $ /home/vanosten/bin/osmosis-latest/bin/osmosis --read-pbf file="/media/sf_fg_customscenery/projects/TEST/kbos.pbf" --log-progress --write-pgsql database=kbos host=localhost:5433 user=gisuser password=!Password1

And finally you might want to index the tags in hstore to get some more query speed after loading the data (on a medium powered machine for the relatively small KBOS area this takes ca. 30 minutes):

::

    CREATE INDEX idx_nodes_tags ON nodes USING gist(tags);
    CREATE INDEX idx_ways_tags ON ways USING gist(tags);
    CREATE INDEX idx_relations_tags ON relations USING gist(tags);

.. _Osmosis: http://wiki.openstreetmap.org/wiki/Osmosis
.. _PostGIS setup: http://wiki.openstreetmap.org/wiki/Osmosis/PostGIS_Setup
.. _PostGIS Tasks (Snapshot Schema): http://wiki.openstreetmap.org/wiki/Osmosis/Detailed_Usage_0.45#PostGIS_Tasks_.28Snapshot_Schema.29


-------
Remarks
-------

* I have not found out how to add an additional region to an already populated database. Therefore you might need to run ``/home/pingu/bin/osmosis-latest/bin/osmosis --truncate-pgsql database=kbos`` before getting a new region into the database if you have only one database. The better approach is of course using several databases in parallel.


