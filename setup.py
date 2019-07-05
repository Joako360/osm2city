from distutils.core import setup

setup(
    name='osm2city',
    version='beta',
    author='Rick Gruber-Riemer',
    author_email='rick@vanosten.net',
    packages=[],
    license='LICENSE',
    description='osm2city is a set of procedures, which create plausible FlightGear scenery objects based on OSM data.',
    long_description=open('README.md').read(),
    # url='http://pypi.python.org/pypi/TowelStuff/',
    # install_requires=[
    #    "Django >= 1.1.1",
    #    "caldav == 0.1.4",
    # ],
    # from Cython.Build import cythonize
    # ext_modules=cythonize(['buildings.py', 'owbb/landuse.py', 'owbb/models.py'],
    #                      compiler_directives={'language_level': "3"}),
)
