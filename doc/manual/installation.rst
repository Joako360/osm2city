.. _chapter-installation-label:

############
Installation
############

The following specifies software and data requirements as part of the installation. Please be aware that different steps in scenery generation (e.g. generating elevation data, generating scenery objects) might require a lot of memory and are CPU intensive. Either use decent hardware or experiment with the size of the sceneries. However it is more probable that your computer gets at limits when flying around in FlightGear with sceneries using ``osm2city`` than when generating the sceneries.


==============
Pre-requisites
==============

------
Python
------

``osm2city`` is written in Python and needs Python for execution. Python is available on all major desktop operating systems — including but not limited to Windows, Linux and Mac OS X. See http://www.python.org.

Currently Python version 2.7 is used for development and is therefore the recommended version.


-------------------------
Python Extension Packages
-------------------------

osm2city uses the following Python extension packages, which must be installed on your system and be included in your ``PYTHONPATH``:

* curl
* enum34
* matplotlib
* networkx
* numpy
* pil
* scipy
* shapely

Please make sure to use Python 2.7 compatible extensions. Often Python 3 compatible packages have a "3" in their name. Most Linux distributions come by default with the necessary packages — often they are prefixed with ``python-`` (e.g. ``python-numpy``). On Windows WinPython (https://winpython.github.io/) together with Christoph Gohlke's unofficial Windows binaries for Python extension packages (http://www.lfd.uci.edu/~gohlke/pythonlibs/) works well.


========================
Installation of osm2city
========================

There is no installer package - neither on Windows nor Linux. ``osm2city`` consists of a set of Python programs "osm2city_"  and the related data in "osm2city-data_". You need both.

.. _osm2city: https://gitlab.com/fg-radi/osm2city
.. _osm2city-data: https://gitlab.com/fg-radi/osm2city-data

Do the following:

#. Download the packages either using Git_ or as a zip-package.
#. Add the ``osm2city`` directory to your ``PYTHONPATH``. You can read more about this at https://docs.python.org/2/using/cmdline.html#envvar-PYTHONPATH.
#. Create soft links between as described in the following sub-chapter.

.. _Git: http://www.git-scm.com/


-----------------------------------
Creating Soft Links to Texture Data
-----------------------------------
Many of the ``osm2city`` programs must have access to texture data in ``osm2city-data``. The following assumes that both the ``osm2city`` and ``osm2city-data`` are stored within the same directory.

On a Linux workstation do the following:

::

    $ cd osm2city
    $ ln -sf ../osm2city-data/tex
    $ ln -sf ../osm2city-data/tex

On a Windows computer do the following (path may differ):

::

    > mklink /J C:\development\osm2city\tex.src C:\development\osm2city-data\tex.src 
    > mklink /J C:\development\osm2city\tex C:\development\osm2city-data\tex

