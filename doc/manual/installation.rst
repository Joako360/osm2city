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

Currently Python version 3.5 is used for development and is therefore the recommended version.


-------------------------
Python Extension Packages
-------------------------

osm2city uses the following Python extension packages, which must be installed on your system and be included in your ``PYTHONPATH``:

* curl
* matplotlib
* networkx
* numpy
* pil
* scipy
* shapely

Please make sure to use Python 3.5 compatible extensions. Often Python 3 compatible packages have a "3" in their name. Most Linux distributions come by default with the necessary packages — often they are prefixed with ``python-`` (e.g. ``python-numpy``). On Windows WinPython (https://winpython.github.io/) together with Christoph Gohlke's unofficial Windows binaries for Python extension packages (http://www.lfd.uci.edu/~gohlke/pythonlibs/) works well.


.. _chapter-osm2city-install:

========================
Installation of osm2city
========================

There is no installer package - neither on Windows nor Linux. ``osm2city`` consists of a set of Python programs "osm2city_"  and the related data in "osm2city-data_". You need both.

.. _osm2city: https://gitlab.com/fg-radi/osm2city
.. _osm2city-data: https://gitlab.com/fg-radi/osm2city-data

Do the following:

#. Download the packages either using Git_ or as a zip-package.
#. Add the ``osm2city`` directory to your ``PYTHONPATH`` (see :ref:`below <chapter-set-pythonpath-label>`).
#. Make sure that you have :ref:`set $FG_ROOT <chapter-set-fgroot-label>`

You might as well check your installation and :ref:`create a texture atlas <chapter-create-texture-atlas>` — doing so makes sure your installation works and you do not run into the problem of having an empty texture atlas.

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

-------------------------------------
Setting Environment Variable $FG_ROOT
-------------------------------------
The environment variable ``$FG_ROOT`` must be set in your operating system or at least your current session, such that ``fgelev`` can work optimally. How you set environment variables is depending on your operating system and not described here. I.e. this is NOT something you set as a parameter in ``params.ini``!

You might have to restart Windows to be able to read the environment variable that you set through the control panel. In Linux you might have to create a new console session.

`$FG_ROOT`_ is typically a path ending with directories ``data`` or ``fgdata`` (e.g. on Linux it could be ``/home/pingu/bin/fgfs_git/next/install/flightgear/fgdata``).
