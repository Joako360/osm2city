"""owbb stands for OSM would-be-world: does some of the main heuristics to tie land-use data and building data.

Most often the data source and the relation between land-use, settlements and buildings is weak in OSM.
The module contains amongst others the code to generate buildings in places, where there should be buildings,
but no buildings have been mapped. The 'how it works' section in the manual has a description of how it is
meant to work.
"""