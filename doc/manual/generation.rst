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
  


