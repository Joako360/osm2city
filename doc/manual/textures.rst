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

-----------------------
Needed Texture Atlasses
-----------------------

......................................
Ideas, Constraints and Random Thoughts
......................................

* Older graphic cards might have difficulties with textures larger than 4k x 4k. On the other hand side the current texture atlas is 16k x 256 without people complaining. By the time new osm2city atlasses get mainstream (i.e. next LTS after 2020.3) another year or so will have passed and "older" graphics cards still can manage 8k x 8k. Whoever runs osm2city might not have an old PC anyway. => Going with 8k per dimension max.
* Using a transparent texture and underlying model colours is very bad for performance, unless a shader is used. I.e. using a few textures and then doing the variety by using colours in the ac-file is not a viable way.
* Bigger objects/meshes are better for graphics cards. Level of details settings in FG rendering preferences can play a bit against it. So there is a sweet spot between mesh dimensions (as large as possible) and LOD settings.
* FG seems to support only one texture per ac-file - even though the ``AC3D file format <https://www.inivis.com/ac3d/man/ac3dfileformat.html>``_ does support several textures (one texture per object, but there can be many objects).
* In cities and centres of towns the ground floor has often shops/bars - even though the next floors might be inhabited. And therefore facade has more glas, more "signs" / "colours", and more diverse lighting during night -> should be possible to texture map explicitely based on distance from centre etc.
* There are two options for compatibility between FG versions (as the texture atlasses reside within FG and not within scenery folders a new scenery generated with the latest atlas might not work on an FG version referencing an older texture, which will lead to funny rendering):
    * Put new BUILDING_LIST buildings and new texture atlasses in a new scenery directories to avoid compatibility issues. Each FG version then knows which directory to reference.
    * Put the files into Terrasync/Models instead and make sure that as the atlas evolves only new stuff is added and each sub-texture has a "known FG minimal version" number.


.....................................
High Office Buildings and Skyscrapers
.....................................

For all but very high buildings we can manage vertical scale within texture. Therefore it makes sense to have the texture for high and very high buildings separate. That texture can also in general be used for office buildings. Horisontal scale is not know - and therefore these skyscraper textures should be x-repeatable. Skyscrapers should have possibility for special bottom (often ca. 2 times floor height) and special handling of top (often also 2-3 times floor height).

Proposal:

* 1 special atlas file
* 20 cm per pixel
* Normal floors: 4 metres / floor height => 20 pixels
* Ground floor: 6 metres height => 30 pixels
* Top floor: x metres => 26 pixels, which can be stretched (allowing some variations between buildings). Often no top floor for buildings with relatively few floors
* Use 10 floors per texture, which should fit most commercial buildings / industry offices etc.
* Resulting in 10*20 pixels plus 30 pixels plus 26 pixels = 256 pixels per texture => 32 different textures in 8k
* Use a width of 256 pixels, i.e. ca. 50 metres should allow to repeat in x-direction without looking wrong


----------------
Todo's and PoC's
----------------

* Inclusion of ac-objects into mesh: read electrical pylons and combine them into mesh of cables. Significantly reduces number of nodes in scenery and proofs possibility. As a side effect if at some point the object would be removed from terrasync (or renamed), then the program would at least abort.
* Split roofs into own texture atlas: structure program such that it "remembers" facades vs. roofs
* Split buildings using skyscraper texture atlas into own mesh - but then generate tile-size meshes (one for facades and one for roofs): horisontal repeat, vertical extra nodes if very high building 
