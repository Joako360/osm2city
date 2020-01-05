# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Martin Herweg    m.herweg@gmx.de
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

import argparse
import logging
import os
from random import randint
import sys
from typing import Dict, List, Tuple

from osm2city import parameters
import osm2city.utils.json_io as jio
from osm2city.utils.utilities import FGElev, get_osm2city_directory
from osm2city.utils.vec2d import Vec2d
import osm2city.utils.stg_io2 as stg

MODEL_LIBRARY = "library.txt"

OUR_MAGIC = "dsf2stg"

CARPOOL = [
    "hatchback_red.ac",
    "hatchback_blue.ac",
    "hatchback_black.ac",
    "hatchback_black.ac",
    "hatchback_silver.ac",
    "hatchback_silver.ac",
    "hatchback_green.ac",
    "van_blue_dirty.ac",
    "van_red.ac",
    "van_silver.ac"
] 

CESSNAS = [
    "Cessna172.ac",
    "Cessna172_blue.ac",
    "Cessna172_green.ac",
    "Cessna172_red.ac",
    "Cessna172_sky.ac",
    "Cessna172_yellow.ac",
    "Cessna150_no_reg.ac"
]


class ObjectDefinition:
    def __init__(self, path: str, oid: int) -> None:
        path = path.replace('\\', '/')
        splitted = path.strip().split('/')
        self.oid = oid
        if len(splitted) > 1:
            self.prefix = os.sep.join(splitted[:-1]) + os.sep
        else:
            self.prefix = ''

        self.file, self.ext = os.path.splitext(splitted[-1])
        self.name = self.prefix + os.sep + self.file


class Object(object):
    def __init__(self, obj_def: ObjectDefinition, lon: float, lat: float, hdg: float, fgpath, zoff, msl=None) -> None:
        self.lon = lon
        self.lat = lat
        self.hdg = hdg
        self.msl = msl
        self.prefix = obj_def.prefix
        self.ext = obj_def.ext
        self.textures_list = []
        self.fgpath = fgpath
        self.zoff = zoff

    @property
    def pos(self) -> Vec2d:
        return Vec2d(self.lon, self.lat)


def _read_model_library() -> Dict[str, Tuple[str, float, float, float, float]]:
    """Reads the library.txt file with all the model definitions.

    Entries look like:
    lib/airport/aircraft/GA/Cessna_172.obj CESSNA 0 0 0 180
    lib/airport/aircraft/GA/KingAirC90B.obj Models/Aircraft/Citation-II-Type1.ac
    lib/airport/aircraft/GA/Osprey_GP5.obj Models/Aircraft/Zlin50xl_low_poly.xml
    lib/airport/aircraft/heavy_metal/747_United.obj Models/Aircraft/B747.xml 0 0 0 90
    """
    model_library = dict()
    with open(os.path.join(get_osm2city_directory(), MODEL_LIBRARY), 'r') as lib_file:
        try:
            for line in lib_file:
                line = line.strip()
                if line.startswith("#"):
                    pass
                else:
                    cols = line.split()
                    if len(cols) == 6:
                        key = cols[0]
                        value = (cols[1], cols[2], cols[3], cols[4], cols[5],)
                        model_library[key] = value
                    elif len(cols) == 2:
                        key = cols[0]
                        value = (cols[1], 0, 0, 0, 0,)
                        model_library[key] = value
                    else:
                        if line:
                            print("WARNING: can not parse this line from library:", line)
        except IOError:  # whatever reader errors you care about
            logging.exception('Library file %s not found', MODEL_LIBRARY)
            sys.exit()
    logging.info('%i entries in library.txt', len(model_library))
    return model_library


def _read_obj_def(infile, object_definition_paths: List[str], object_definitions: Dict[int, ObjectDefinition]):
    """Read airport specific object definitions.

    Content looks like:
    PROPERTY sim/west -180
    PROPERTY sim/east 180
    PROPERTY sim/north 90
    PROPERTY sim/south -90
    PROPERTY sim/planet earth
    PROPERTY sim/creation_agent WorldEditor1.4.0b2
    PROPERTY laminar/internal_revision 0
    PROPERTY sim/overlay 1
    OBJECT 0 8.119624565 46.738528618 105.481697
    OBJECT 1 8.117621028 46.738985834 196.470001
    OBJECT 2 8.117356449 46.739373796 2.970000
    OBJECT 3 8.115594672 46.740133116 184.929993
    OBJECT_DEF lib/airport/Common_Elements/Hangars/Long_Row_Beige.agp
    OBJECT_DEF lib/airport/Common_Elements/Hangars/Med_Blue_Hangar.agp
    OBJECT_DEF lib/airport/Modern_Airports/Control_Towers/Modern_Tower_3.agp
    OBJECT_DEF lib/airport/Common_Elements/Hangars/Med_Gray_Hangar.agp
    PROPERTY sim/require_agpoint 1/0
    PROPERTY sim/require_object 1/0
    """
    oid = 0
    for line in infile:
        if line.startswith("OBJECT_DEF"):
            cols = line.split()
            xpath = cols[1]
            object_definition_paths.append(xpath)
            obj = ObjectDefinition(line[11:], oid)
            object_definitions[oid] = obj
            oid += 1
    logging.info('%i object definitions in source', oid)


def _read_obj(infile, library,
              object_definition_paths: List[str],
              object_definitions: Dict[int, ObjectDefinition]) -> List[Object]:
    """Read airport specific objects.

    Same file format as in _read_obj_def.
    """
    objects = list()
    for line in infile:
        line = line.strip()

        if line.startswith("OBJECT "):
            col = line.split()
            index = int(col[1])
            if object_definition_paths[index] in library:
                model_tupel = library[object_definition_paths[index]]
                fgpath = model_tupel[0]
                # xoff = float(model_tupel[1])
                # yoff = float(model_tupel[2])
                zoff = float(model_tupel[3])
                hoff = float(model_tupel[4])
                lon = float(col[2])
                lat = float(col[3])
                heading = (360 - float(col[4])) + hoff

                if heading >= 360:
                    heading = heading - 360

                o = Object(object_definitions[index], lon, lat, heading, fgpath, zoff)
                objects.append(o)
            else:
                logging.debug("No model for %s", object_definition_paths[index])
    return objects


def _jw_init(icao: str):
    path = "Airports"
    for i in range(len(icao)-1):
        path = os.path.join(path, icao[i])
        if os.path.exists(path):
            pass
        else:
            os.mkdir(path)
    gf = '.'.join([icao, 'jetways.xml'])
    path = os.path.join(path, gf)
    f = open(path, 'w')
    f.write('<?xml version="1.0"?>\n')
    f.write('<PropertyList>\n')
    return(f)


def _jw_entry(o, f, jw_count):

    f.write('<jetway n="%d">\n' % (jw_count))
    f.write('  <model type="string">generic</model>\n')
    f.write('  <gate type="string">%s</gate>\n' % (jw_count))
    f.write('  <door type="int">1</door>\n')
    f.write('  <airline type="string">FGFS</airline>\n')
    f.write('  <latitude-deg type="double">%s</latitude-deg>\n' % (o.lat))
    f.write('  <longitude-deg type="double">%s</longitude-deg>\n' % (o.lon))
    f.write('  <elevation-m type="double">%s</elevation-m>\n' % (o.msl))
    f.write('  <heading-deg type="double">%s</heading-deg>\n' % (o.hdg))
    f.write('  <initial-position>\n')
    f.write('    <jetway-extension-m type="double">0</jetway-extension-m>\n')
    f.write('    <jetway-heading-deg type="double">0</jetway-heading-deg>\n')
    f.write('    <jetway-pitch-deg type="double">0</jetway-pitch-deg>\n')
    f.write('    <entrance-heading-deg type="double">0</entrance-heading-deg>\n')
    f.write('  </initial-position>\n')
    f.write('</jetway>\n')


def main(icao: str) -> None:
    scenery_id = jio.query_airport_xplane(icao)
    if scenery_id is not None:
        file_name = jio.query_scenery_xplane(scenery_id, icao)
        with open(file_name, 'r') as infile:
            try:
                object_definition_paths = list()
                object_definitions = dict()

                model_library = _read_model_library()
                _read_obj_def(infile, object_definition_paths, object_definitions)
                infile.seek(0)
                objects = _read_obj(infile, model_library, object_definition_paths, object_definitions)
                linecount = 0
                jw_count = 0
                jw_init_flag = False

                tile_index = 11111  # FIXME make it real
                my_fg_elev = FGElev(None, tile_index)
                stg_manager = stg.STGManager(parameters.PATH_TO_OUTPUT, stg.SceneryType.details, OUR_MAGIC)
                for o in objects:
                    if o.msl is None:
                        o.msl = my_fg_elev.probe_elev((o.lon, o.lat), True) + o.zoff
                        logging.debug("object %s: elev probed %s" % (o.fgpath, str(o.msl)))
                    else:
                        logging.debug("object %s: using provided MSL=%g" % (o.fgpath, o.msl))

                    if o.fgpath in ("Models/Airport/Jetway/jetway.xml", "Models/Airport/Jetway/jetway-movable.xml"):
                        if not jw_init_flag:
                            f = _jw_init(icao)
                            jw_init_flag = True
                        _jw_entry(o, f, jw_count)
                        jw_count += 1
                    elif o.fgpath == "CAR":
                        numcars = len(CARPOOL)
                        index = (randint(0, numcars-1))
                        fgpath = ("Models/Transport/" + CARPOOL[index])
                        stg_manager.add_object_shared(fgpath, o.pos, o.msl, o.hdg)
                    elif o.fgpath == "CESSNA":
                        numplanes = len(CESSNAS)
                        index = (randint(0, numplanes-1))
                        fgpath = ("Models/Aircraft/" + CESSNAS[index])
                        stg_manager.add_object_shared(fgpath, o.pos, o.msl, o.hdg)
                    else:
                        stg_manager.add_object_shared(o.fgpath, o.pos, o.msl, o.hdg)

                    linecount += 1
                my_fg_elev.close()

                stg_manager.write()
                logging.info('Wrote %i stg lines for %s', linecount, icao)

                if jw_init_flag:
                    f.write('</PropertyList>\n')
                    logging.info('Wrote %i jetway.xml entries for %s', jw_count, icao)
                    f.close()
                logging.info("Done.")
            except IOError:
                logging.exception('Input file %s not found', file_name)
                sys.exit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert X-plane gateway scenery package to FlightGear")
    parser.add_argument("-f", "--file", dest="filename",
                        help="read parameters from FILE (e.g. params.ini)", metavar="FILE", required=True)
    parser.add_argument("-i", "--icao", help="ICAO of airport", required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    parameters.read_from_file(args.filename)

    main(args.icao)
