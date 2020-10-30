.. _chapter-how-texturing-works-label:

###################
How Texturing Works
###################

===================================
Implementation 2020.3.x and Earlier
===================================


----------------
Texture Atlasses
----------------

There are 2 atlas: one for roads and one for facades and roofs. Both of them have a light map and are in .png format.

........................
Roads and Railway Tracks
........................

The atlas for roads is a fixed file. Any change needs to be done directly in the file. The corresponding data object understanding the format is ``osm2city/textures/roads.py``.


.................
Facades and Roofs
.................

The atlas for facades and roofs is fixed in size and content, because code restructuring has necessitated a freeze plus compatibility between FG versions needs to be guaranteed. Theoretically the atlas is dynamically created based on:

* Image files in osm2city-data representing 1 facade or one roof. For facades there can be a corresponding light-map image, which shows which parts should shine at night (e.g. individual windows).
* Python files in osm2city-data describing the images (e.g. colour, time epoch, material, size, repeatability) based on class ``Texture`` in ``osm2city\textures\texture.py``.
* ``osm2city\prepare_textures.py`` reads the Python files and creates the atlas package structure according to `osm2city\textures\atlas.py``
* The result is an atlas image for facades/roofs, an atlas image for the corresponding lightmap as well as a Python datastructure of the embedded textures (position, properties) saved as a Python *.pkl file.


------------------------
FGData Effects and Stuff
------------------------

``osm2city`` has dependencies in FGData for effects etc. to work. This means that changes in those parts might break osm2city — and osm2city might not work correctly if new features disregard those dependencies.

* fgdata/Textures/osm2city/ contains the texture atlas for road and facades including the respective lightmaps.
* fgdata/Textures/ has buildings-lightmap.png and the related lightmap, which are used for list based shader buildings.
* fgdata/Shaders/road-ALS-ultra.frag: mapping with road texture, generates traffic and night lighting etc.
* fgdata/Shaders/urban-ALS.frag and urban.frag
* fgdata/Shaders/building-*.vert
* fgdata/Effects/cityLM.eff: lightmap for facades texture atlas (so there is no need for xml-files wrapping the ac-file containing the meshes)
* fgdata/Effects/road.eff: road and traffic effect incl. snow
* fgdata/Effects/urban.eff: incl. snow for osm-buildings


===============================
Proposal Renewed Implementation
===============================

-----------------
Texture Size Etc.
-----------------

On 12 May 2020 Stuart Buchanan wrote:

Just to document what we discussed:

#. Creating a new texture atlas is fine. Keeping it to 4K x 4K would be better than 8K x 8K as some older graphics cards may not support it.
#. Creating and referencing a new file is fine - we can put the new BUILDING_LIST buildings and the new texture atlas in a new scenery directory to avoid compatibility issues.
#. Using a transparent texture and underlying model colours is very bad for performance, unless you use a shader, which you want to avoid.
#. If you use a separate texture for the walls compared with the roof you should try to create a series of big objects containing all the walls or roofs for multiple buildings, as the .ac format only supports a single texture per object. Bigger objects are better for graphics cards.

On 16 May 2020 Rick wrote:

Wouldn't it be better, if the files would reside in TerraSync/Models instead? Then the newest would always be available even for older FG versions -> the atlas could evolve as intended with no version compatibility issues of scenery generated. The only guarantee would have to be that the pods in the atlas always would have to be reserved for the same thing (geometry, properties, etc).

This should be done for both facades/roofs and roads as well as other textures.

