.. _chapter-installation-label:

######################
Installation [Builder]
######################

The following specifies software and data requirements as part of the installation. Please be aware that different steps in scenery generation (e.g. generating elevation data, generating scenery objects) might require a lot of memory and are CPU intensive. Either use decent hardware or experiment with the size of the sceneries. However it is more probable that your computer gets at limits when flying around in FlightGear with sceneries using ``osm2city`` than when generating the sceneries.


==============
Pre-requisites
==============


.. _chapter-python-label:

------
Python
------

``osm2city`` is written in Python and needs Python for execution. Python is available on all major desktop operating systems — including but not limited to Windows, Linux and Mac OS X. See http://www.python.org.

Currently Python version 3.6 is used for development and is therefore the recommended version.


-------------------------
Python Extension Packages
-------------------------

osm2city uses the following Python extension packages, which must be installed on your system and be included in your ``PYTHONPATH``:

* descartes
* matplotlib
* networkx
* numpy (on Windows you need Numpy+MKL)
* pil (Pillow)
* pyproj
* requests
* scipy
* shapely
* psycopg2-binary

Please make sure to use Python 3.6+ compatible extensions. Often Python 3 compatible packages have a "3" in their name. Most Linux distributions come by default with the necessary packages — often they are prefixed with ``python-`` (e.g. ``python-numpy``). On Windows WinPython (https://winpython.github.io/) together with Christoph Gohlke's unofficial Windows binaries for Python extension packages (http://www.lfd.uci.edu/~gohlke/pythonlibs/) works well.


--------------------
Virtual Environments
--------------------
The following is optional respectively a better way to install Python extension packages then what was described above — however it might be a bit more difficult.

You might want to consider using a Python Virtualenv_ instead of using Python directly as installed in your OS. Once you have installed ``virtualenv`` on your system, you should create a base directory for your virtual environments (e.g. ``$HOME/bin/virtualenvs``).

Then:

::

    user$ python3 -m venv /home/vanosten/bin/virtualenvs/o2c36
    user$ source /home/vanosten/bin/virtualenvs/o2c36/bin/activate
    (o2c36) user$ pip install matplotlib
    (o2c36) user$ pip install networkx
    ...
    (o2c36) user$ pip freeze
    cffi==1.11.5
    cycler==0.10.0
    decorator==4.3.0
    descartes==1.1.0
    kiwisolver==1.0.1
    matplotlib==2.2.2
    networkx==2.1
    numpy==1.14.3
    Pillow==5.1.0
    pkg-resources==0.0.0
    psycopg2-binary==2.7.4
    pycparser==2.18
    pyparsing==2.2.0
    python-dateutil==2.7.3
    pytz==2018.4
    scipy==1.1.0
    Shapely==1.6.4.post1
    six==1.11.0


.. _Virtualenv: https://virtualenv.pypa.io/en/stable/


.. _chapter-osm2city-install:

========================
Installation of osm2city
========================

There is no installer package - neither on Windows nor Linux. ``osm2city`` consists of a set of Python programs and the related data in "osm2city-data_". You need both.

.. _osm2city: https://gitlab.com/fg-radi/osm2city
.. _osm2city-data: https://gitlab.com/fg-radi/osm2city-data

Do the following:

#. Download the packages either using Git_ or as a zip-package.
#. Add the ``osm2city`` directory to your ``PYTHONPATH`` (see :ref:`below <chapter-set-pythonpath-label>`).
#. Make sure that you have :ref:`set $FG_ROOT <chapter-set-fgroot-label>`.


.. _chapter-set-pythonpath-label:

------------------
Setting PYTHONPATH
------------------
You can read more about this at https://docs.python.org/3.5/using/cmdline.html#envvar-PYTHONPATH.

On Linux you would typically add something like the following to your ``.bashrc`` file:

::

    PYTHONPATH=$HOME/develop_vcs/python3/osm2city
    export PYTHONPATH


.. _Git: http://www.git-scm.com/


.. _chapter-set-fgroot-label:

------------------------------------------------------
Setting Operating System Environment Variable $FG_ROOT
------------------------------------------------------
The environment variable ``$FG_ROOT`` must be set in your operating system or at least your current session, such that ``fgelev`` can work optimally. How you set environment variables is depending on your operating system and not described here. I.e. this is NOT something you set as a parameter in ``params.ini``!

You might have to restart Windows to be able to read the environment variable that you set through the control panel. In Linux you might have to create a new console session.

`$FG_ROOT`_ is typically a path ending with directories ``data`` or ``fgdata`` (e.g. on Linux it could be ``/home/pingu/bin/fgfs_git/next/install/flightgear/fgdata``; on Windows it might be ``C:\flightGear\2017.3.1\data``).

BTW: you have to set the name of the variable in your operating system to ``FG_ROOT`` (not ``$FG_ROOT``).

.. _$FG_ROOT: http://wiki.flightgear.org/$FG_ROOT


==================
Setting up PostGIS
==================

---------------------------
Installed Packages on Linux
---------------------------

On Ubuntu 17.10 the following packages have amongst others been installed (not exhaustive list):

* postgresql-9.6
* postgresql-9.6-postgis-2.3
* postgresql-client-9.6
* postgresql-contrib-9.6
* pgadmin3
* postgis
* python3-psycopg2

---------------------
Installing on Windows
---------------------

For windows, the best way to get PostgreSQL and PostGI is to use this download page: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads: version 9.6 was tested and works well on Windows. After installation of PostgreSQL, use the Stackbuilder tool included with PostgreSQL to download and install PostGIS version 2.5, which is found under "spatial extensions".


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

.. _PostGIS setup: http://wiki.openstreetmap.org/wiki/Osmosis/PostGIS_Setup
.. _PostGIS Tasks (Snapshot Schema): http://wiki.openstreetmap.org/wiki/Osmosis/Detailed_Usage_0.45#PostGIS_Tasks_.28Snapshot_Schema.29


-------
Remarks
-------

* I have not found out how to add an additional region to an already populated database. Therefore you might need to run ``/home/pingu/bin/osmosis-latest/bin/osmosis --truncate-pgsql database=kbos`` before getting a new region into the database if you have only one database. The better approach is of course using several databases in parallel.



.. _chapter-helpers-install:

===========
Other Tools
===========

You might want to check out Sławek Mikuła's scripts_ for osm2city parsing and generation, which make some of the repetitive manual tasks involved in generating a scenery a bit easier.

.. _scripts: https://github.com/slawekmikula/scripts-osm2city


.. _chapter-josm-label:


-------
OSMOSIS
-------

You might also need a 0.6+ version of Osmosis_. Please be aware of the fact that you also need a related version of Java and that e.g. in Ubuntu 17.10 Osmosis is out of date — i.e. you should NOT use a (Linux) distribution package and instead use the one from the source.

.. _Osmosis: http://wiki.openstreetmap.org/wiki/Osmosis


----
JOSM
----

``JOSM`` is an offline editor for OSM-data. It is not strictly required for pre- or post-processing of ``osm2city``, but it might be handy for debugging and detailed investigations.

Information about JOSM including installation instructions can be found at https://josm.openstreetmap.de/.
