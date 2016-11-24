"""Handles reading from apt.dat airport files and read/write to pickle file for minimized representation.
See http://developer.x-plane.com/?article=airport-data-apt-dat-file-format-specification for the specification.

Currently only reading runway data in order to avoid roads/railways to cross a runway.

There is also data available in apt.dat for taxiways an apron, but is not used at current point in time.

Flightgear 2016.4 can read multiple apt.data files - see e.g. http://wiki.flightgear.org/FFGo
and https://sourceforge.net/p/flightgear/flightgear/ci/516a5cf016a7d504b09aaac2e0e66c7e9efd42b2/.
However this module does only support reading from one apt.dat.gz by the user's choice (normally in
$FG_ROOT/Airports/apt.dat.gz).

"""

import gzip
import logging
import time
from typing import List

from utils.vec2d import Vec2d


class LandRunway(object):
    def __init__(self, width: float, start: Vec2d, end: Vec2d) -> None:
        self.width = width
        self.start = start
        self.end = end


class Airport(object):
    def __init__(self, code: str) -> None:
        self.code = code
        self.land_runways= list()  # of LandRunways

    def has_runways(self) -> bool:
        return len(self.land_runways) > 0

    def append_runway(self, runway: LandRunway) -> None:
        self.land_runways.append(runway)


def read_apt_dat_gz_file(file_name: str) -> List[Airport]:
    start_time = time.time()
    airports = list()
    total_airports = 0
    with gzip.open(file_name, 'rt', encoding="latin-1") as f:
        my_airport = None
        for line in f:
            parts = line.split()
            if len(parts) == 0:
                continue
            if parts[0] in ['1', '16', '17', '99']:
                if (my_airport is not None) and (my_airport.has_runways()):
                    airports.append(my_airport)
                if not parts[0] == '99':
                    my_airport = Airport(parts[4])
                    total_airports += 1
            elif parts[0] == '100':
                my_runway = LandRunway(float(parts[1]), Vec2d(float(parts[10]), float(parts[9])),
                                       Vec2d(float(parts[19]), float(parts[18])))
                my_airport.append_runway(my_runway)

    end_time = time.time()
    logging.info("Read %d airports, %d having land runways", total_airports, len(airports))
    logging.info("Execution time: %f", end_time - start_time)
    return airports


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    read_apt_dat_gz_file('/home/vanosten/bin/fgfs_git/install/flightgear/fgdata/Airports/apt.dat.gz')
