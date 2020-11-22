from enum import unique, IntEnum
import logging
from typing import Dict, Optional, Union

from osm2city.static_types import osmstrings as s


KeyValueDict = Dict[str, str]


@unique
class ArchitectureStyle(IntEnum):
    """http://wiki.openstreetmap.org/wiki/Key:building:architecture"""
    romanesque = 1
    gothic = 2
    unknown = 99


@unique
class WorshipBuildingType(IntEnum):
    """See http://wiki.openstreetmap.org/wiki/Key:building or
    http://wiki.openstreetmap.org/wiki/Tag:building%3Dchurch

    cathedral is not supported, because too close to church in shared models etc. Size of building should be enough.
    """
    church = 10
    # not supportedOSM value = cathedral
    chapel = 12
    church_orthodox = 20  # not official tag - just to make it easier to distinguish from catholoic / protestant
    mosque = 40
    synagogue = 50
    temple = 60
    shrine = 70


def deduct_worship_building_type(tags: KeyValueDict) -> Optional['WorshipBuildingType']:
    """Return a type if the building is a worship building, Otherwise return None."""
    worship_building_type = None
    if tags[s.K_BUILDING] == s.V_CATHEDRAL:
        tags[s.K_BUILDING] = s.V_CHURCH
    try:
        worship_building_type = WorshipBuildingType.__members__[tags[s.K_BUILDING]]
    except KeyError:  # e.g. building=yes
        if s.K_AMENITY in tags and tags[s.K_AMENITY] == s.V_PLACE_OF_WORSHIP:
            if s.K_RELIGION in tags and tags[s.K_RELIGION] == s.V_CHRISTIAN:
                worship_building_type = WorshipBuildingType.church
                if s.K_DENOMINATION in tags and tags[s.K_DENOMINATION].find(s.V_ORTHODOX) > 0:
                    worship_building_type = WorshipBuildingType.church_orthodox
    return worship_building_type


@unique
class BuildingClass(IntEnum):
    """Used to classify buildings for processing on zone level and defining height per level in some cases"""
    residential = 100
    residential_small = 110
    terrace = 120
    apartments = 130
    commercial = 200
    industrial = 300
    warehouse = 301
    retail = 400
    parking_house = 1000
    religion = 2000
    public = 3000
    farm = 4000
    airport = 5000
    undefined = 9999  # mostly because BuildingType can only be approximated to "yes"


@unique
class BuildingType(IntEnum):
    """Mostly match value of a tag with k=building.
    If changed, then also check use in get_building_class() as well as is_...() methods in osmstrings.py."""
    yes = 1  # default
    parking = 10  # k="parking" v="multi-storey"
    apartments = 21
    attached = 210  # an apartment in a city block without space between buildings. Does not exist in OSM
    house = 22
    detached = 23
    residential = 24
    dormitory = 25
    terrace = 26
    bungalow = 31
    static_caravan = 32
    cabin = 33
    hut = 34
    commercial = 41
    office = 42
    retail = 51
    industrial = 61
    warehouse = 62
    cathedral = 71
    chapel = 72
    church = 73
    mosque = 74
    temple = 75
    synagogue = 76
    public = 81
    civic = 82
    school = 83
    hospital = 84
    hotel = 85
    farm = 101
    barn = 102
    cowshed = 103
    farm_auxiliary = 104
    greenhouse = 105
    glasshouse = 106
    stable = 107
    sty = 108
    riding_hall = 109
    slurry_tank = 110
    hangar = 201
    stadium = 301
    sports_hall = 302


def parse_building_tags_for_type(tags_dict: KeyValueDict) -> Union[None, BuildingType]:
    if (s.K_PARKING in tags_dict) and (tags_dict[s.K_PARKING] == s.V_MULTISTOREY):
        return BuildingType.parking
    else:
        value = None
        if s.K_BUILDING in tags_dict:
            value = tags_dict[s.K_BUILDING]
        elif s.K_BUILDING_PART in tags_dict:
            value = tags_dict[s.K_BUILDING_PART]
        if value is not None:
            for member in BuildingType:
                if value == member.name:
                    return member
            return BuildingType.yes
    return None


def get_building_class(tags: KeyValueDict) -> BuildingClass:
    type_ = parse_building_tags_for_type(tags)
    if type_ is None:
        return BuildingClass.undefined
    if type_ in [BuildingType.house, BuildingType.detached, BuildingType.residential]:
        return BuildingClass.residential
    elif type_ in [BuildingType.bungalow, BuildingType.static_caravan, BuildingType.cabin, BuildingType.hut]:
        return BuildingClass.residential_small
    elif type_ in [BuildingType.apartments, BuildingType.dormitory, BuildingType.hotel]:
        return BuildingClass.apartments
    elif type_ in [BuildingType.terrace]:
        return BuildingClass.terrace
    elif type_ in [BuildingType.commercial, BuildingType.office]:
        return BuildingClass.commercial
    elif type_ in [BuildingType.retail]:
        return BuildingClass.retail
    elif type_ in [BuildingType.industrial]:
        return BuildingClass.industrial
    elif type_ in [BuildingType.warehouse]:
        return BuildingClass.warehouse
    elif type_ in [BuildingType.parking]:
        return BuildingClass.parking_house
    elif type_ in [BuildingType.cathedral, BuildingType.chapel, BuildingType.church,
                   BuildingType.mosque, BuildingType.temple, BuildingType.synagogue]:
        return BuildingClass.religion
    elif type_ in [BuildingType.public, BuildingType.civic, BuildingType.school, BuildingType.hospital]:
        return BuildingClass.public
    elif type_ in [BuildingType.farm, BuildingType.barn, BuildingType.cowshed, BuildingType.farm_auxiliary,
                   BuildingType.greenhouse, BuildingType.stable, BuildingType.sty, BuildingType.riding_hall,
                   BuildingType.slurry_tank]:
        return BuildingClass.farm
    elif type_ in [BuildingType.hangar]:
        return BuildingClass.airport
    return BuildingClass.undefined  # the default / fallback, e.g. for "yes"


@unique
class SettlementType(IntEnum):
    centre = 9  # elsewhere in the code the value is used for comparison, so centre should be highest
    block = 8
    dense = 7
    periphery = 6  # default within lit area
    rural = 5  # only implicitly used for building zones without city blocks.


@unique
class RoofShape(IntEnum):
    """Matches the roof:shape in OSM, see http://wiki.openstreetmap.org/wiki/Simple_3D_buildings.

    Some of the OSM types might not be directly supported and are mapped to a different type,
    which actually is supported in osm2city.

    The enumeration should match what is provided in roofs.py and referenced in _write_roof_for_ac().

    The values need to correspond to the S value in FG BUILDING_LIST
    """
    flat = 0
    skillion = 1
    gabled = 2
    half_hipped = 3
    hipped = 4
    pyramidal = 5
    gambrel = 6
    mansard = 7
    dome = 8
    onion = 9
    round = 10
    saltbox = 11
    skeleton = 99  # does not exist in OSM


def map_osm_roof_shape(osm_roof_shape: str) -> RoofShape:
    """Maps OSM roof:shape tag to supported types in osm2city.

    See http://wiki.openstreetmap.org/wiki/Simple_3D_buildings#Roof_shape"""
    _shape = osm_roof_shape.strip()
    if len(_shape) == 0:
        return RoofShape.flat
    if _shape == s.V_FLAT:
        return RoofShape.flat
    if _shape in [s.V_SKILLION, s.V_LEAN_TO, s.V_PITCHED, s.V_SHED]:
        return RoofShape.skillion
    if _shape in [s.V_GABLED, s.V_HALF_HIPPED, s.V_SALTBOX]:
        return RoofShape.gabled
    if _shape in [s.V_GAMBREL, s.V_ROUND]:
        return RoofShape.gambrel
    if _shape in [s.V_HIPPED, s.V_MANSARD]:
        return RoofShape.hipped
    if _shape == s.V_PYRAMIDAL:
        return RoofShape.pyramidal
    if _shape == s.V_DOME:
        return RoofShape.dome
    if _shape == s.V_ONION:
        return RoofShape.onion

    # fall back for all not directly handled OSM types. The rational for using "hipped" as default is that most
    # probably if someone actually has tried to specify a shape, then 'flat' is unlikely to be misspelled and
    # most probably a form with a ridge was meant.
    logging.debug('Not handled roof shape found: %s. Therefore transformed to "hipped".', _shape)
    return RoofShape.skeleton


@unique
class PlaceType(IntEnum):
    """See https://wiki.openstreetmap.org/wiki/Key:place - only used for city and town as well as farm.
    Rest is ignored - including:
    * isolated_dwelling and allotments -> too small
    * borough: administrative and very few mappings
    * quarter; not used much in OSM and might be better off just using neighbourhood in osm2city
    * city_block and plot: too small
    """
    city = 10
    town = 20
    farm = 50  # only type allowed to remain as area as it is used to recognize land-use type


@unique
class BuildingZoneType(IntEnum):  # element names must match OSM values apart from non_osm
    residential = 10
    commercial = 20
    industrial = 30
    retail = 40
    farmyard = 50  # for generated land-use zones this is not correctly applied, as several farmyards might be
    # interpreted as one. See GeneratedBuildingZone.guess_building_zone_type
    port = 60

    aerodrome = 90  # key = aeroway, not landuse

    non_osm = 100  # used for land-uses constructed with heuristics and not in original data from OSM

    # FlightGear in BTG files
    # must be in line with SUPPORTED_MATERIALS in btg_io.py (except from water)
    btg_builtupcover = 201
    btg_urban = 202
    btg_town = 211
    btg_suburban = 212
    btg_construction = 221
    btg_industrial = 222
    btg_port = 223


# ================================ CONSTANTS =========================================
# Should not be changed unless all dependencies have been thoroughly checked.

# The height per level. This value should not be changed unless special textures are used.
# For settlement types ``centre``, ``block`` and ``dense``.
# If a building is of class ``commercial``, ``retail``, ``public`` or
# ``parking_house``, then this height is always used.
BUILDING_LEVEL_HEIGHT_URBAN = 3.5
BUILDING_LEVEL_HEIGHT_RURAL = 2.5  # ditto including periphery and rural
BUILDING_LEVEL_HEIGHT_INDUSTRIAL = 4.  # for industrial and warehouse
