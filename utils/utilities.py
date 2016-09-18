"""
Diverse utility methods used throughout osm2city and not having a clear other home.
"""

import enum
import os.path as osp
import sys
import os


def get_osm2city_directory():
    """Determines the absolute path of the osm2city root directory.

    Used e.g. when copying roads.eff, elev.nas and other resources.
    """
    my_file = osp.realpath(__file__)
    my_dir = osp.split(my_file)[0]  # now we are in the osm2city/utils directory
    my_dir = osp.split(my_dir)[0]
    return my_dir


def get_fg_home() -> str:
    """Constructs the path to FGHome.

    See also http://wiki.flightgear.org/$FG_HOME
    If the operating system cannot be determined the function returns None.
    Otherwise a platform specific path.
    """
    home_dir = osp.expanduser("~")
    my_os_type = get_os_type()
    if my_os_type is OSType.windows:
        home = os.getenv("APPDATA", "APPDATA_NOT_FOUND") + os.sep + "flightgear.org" + os.sep
        return home.replace("\\", "/")
    elif my_os_type is OSType.linux:
        return home_dir + "/.fgfs/"
    elif my_os_type is OSType.mac:
        return home_dir + "/Library/Application Support/FlightGear/"
    else:
        return None


@enum.unique
class OSType(enum.IntEnum):
    windows = 1
    linux = 2
    mac = 3
    other = 4


def get_os_type() -> OSType:
    if sys.platform.startswith("win"):
        return OSType.windows
    elif sys.platform.startswith("linux"):
        return OSType.linux
    elif sys.platform.startswith("darwin"):
        return OSType.mac
    else:
        return OSType.other


def is_linux_or_mac() -> bool:
    my_os_type = get_os_type()
    if my_os_type is OSType.linux or my_os_type is OSType.mac:
        return True
    return False


def get_elev_in_path(home_path) -> str:
    return home_path + "elev.in"


def get_elev_out_dir(home_path) -> str:
    return home_path + "Export/"


def get_elev_out_path(home_path) -> str:
    return get_elev_out_dir(home_path) + "elev.out"


def get_original_elev_nas_path() -> str:
    my_dir = get_osm2city_directory()
    return my_dir + os.sep + "elev.nas"


def assert_trailing_slash(path):
    """Takes a path and makes sure it has an os_specific trailing slash unless the path is empty."""
    my_path = path
    if len(my_path) > 0:
        if not my_path.endswith(os.sep):
            my_path += os.sep
    return my_path
