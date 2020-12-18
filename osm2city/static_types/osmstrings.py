"""Holds string constants for OSM keys and values."""

from typing import Dict

# type aliases
KeyValueDict = Dict[str, str]

# ========================= NON OSM KEYS AND VALUES ==============================================================
K_OWBB_GENERATED = 'owbb_generated'
K_REPLACED_BRIDGE_KEY = 'replaced_bridge'  # a linear_obj that was originally a bridge, but due to length was changed

# ======================= KEYS ===================================================================================
K_AERIALWAY = 'aerialway'
K_AEROWAY = 'aeroway'
K_AMENITY = 'amenity'
K_AREA = 'area'
K_BRIDGE = 'bridge'
K_BUILDING = 'building'
K_BUILDING_COLOUR = 'building:colour'
K_BUILDING_HEIGHT = 'building:height'
K_BUILDING_LEVELS = 'building:levels'
K_BUILDING_MATERIAL = 'building:material'
K_BUILDING_PART = 'building:part'
K_CABLES = 'cables'
K_CONTENT = 'content'
K_CUTTING = 'cutting'
K_DENOMINATION = 'denomination'
K_DENOTATION = 'denotation'
K_ELECTRIFIED = 'electrified'
K_EMBANKMENT = 'embankment'
K_GAUGE = 'gauge'
K_GENERATOR_SOURCE = 'generator:source'
K_GENERATOR_TYPE = 'generator:type'
K_HEIGHT = 'height'
K_HIGHWAY = 'highway'
K_INDOOR = 'indoor'
K_JUNCTION = 'junction'
K_LANDUSE = 'landuse'
K_LANES = 'lanes'
K_LAYER = 'layer'
K_LEISURE = 'leisure'
K_LEVEL = 'level'
K_LEVELS = 'levels'
K_LIT = 'lit'
K_LOCATION = 'location'
K_MAN_MADE = 'man_made'
K_MANUFACTURER = 'manufacturer'
K_MANUFACTURER_TYPE = 'manufacturer_type'
K_MATERIAL = 'material'
K_MILITARY = 'military'
K_MIN_HEIGHT = 'min_height'
K_MIN_HEIGHT_COLON = 'min:height'  # Incorrect value, but sometimes used
K_NAME = 'name'
K_NATURAL = 'natural'
K_OFFSHORE = 'offshore'
K_ONEWAY = 'oneway'
K_PARKING = 'parking'
K_PLACE = 'place'
K_PLACE_NAME = 'place_name'
K_POPULATION = 'population'
K_POWER = 'power'
K_PUBLIC_TRANSPORT = 'public_transport'
K_RACK = 'rack'
K_RAILWAY = 'railway'
K_RELIGION = 'religion'
K_ROOF_ANGLE = 'roof:angle'
K_ROOF_COLOUR = 'roof:colour'
K_ROOF_HEIGHT = 'roof:height'
K_ROOF_MATERIAL = 'roof:material'
K_ROOF_ORIENTATION = 'roof:orientation'
K_ROOF_SHAPE = 'roof:shape'
K_ROOF_SLOPE_DIRECTION = 'roof:slope:direction'
K_ROTOR_DIAMETER = 'rotor_diameter'
K_ROUTE = 'route'
K_SEAMARK_LANDMARK_HEIGHT = 'seamark:landmark:height'
K_SEAMARK_LANDMARK_STATUS = 'seamark:landmark:status'
K_SEAMARK_STATUS = 'seamark:status'
K_SERVICE = 'service'
K_STRUCTURE = 'structure'
K_TOURISM = 'tourism'
K_TRACKS = 'tracks'
K_TREE_LINED = 'tree_lined'
K_TUNNEL = 'tunnel'
K_TYPE = 'type'
K_VOLTAGE = 'voltage'
K_WATERWAY = 'waterway'
K_WIKIDATA = 'wikidata'
K_WIRES = 'wires'

# ======================= VALUES =================================================================================
V_ABANDONED = 'abandoned'
V_ACROSS = 'across'
V_AERODROME = 'aerodrome'
V_AERO_OTHER = 'aero_other'  # does not exist in OSM - used when it is unsure whether terminal, hangar or different
V_ALONG = 'along'
V_APARTMENTS = 'apartments'
V_APRON = 'apron'
V_ATTACHED = 'attached'  # does not exist in OSM - used as a proxy for apartment buildings attached e.g. in cities
V_BEACH_RESORT = 'beach_resort'
V_BOROUGH = 'borough'
V_BUNKER = 'bunker'
V_BRIDGE = 'bridge'
V_BRIDLEWAY = 'bridleway'
V_BUFFER_STOP = 'buffer_stop'
V_BUILDING = 'building'
V_CANAL = 'canal'
V_CATHEDRAL = 'cathedral'
V_CIRCULAR = 'circular'
V_CITY = 'city'
V_CHECKPOINT = 'checkpoint'
V_CHIMNEY = 'chimney'
V_CHRISTIAN = 'christian'
V_CHURCH = 'church'
V_COASTLINE = 'coastline'
V_COMMERCIAL = 'commercial'
V_COMMON = 'common'
V_COMMUNICATIONS_TOWER = 'communications_tower'
V_CONSTRUCTION = 'construction'
V_CONTACT_LINE = 'contact_line'
V_CYCLEWAY = 'cycleway'
V_DAM = 'dam'
V_DANGER_AREA = 'danger_area'
V_DETACHED = 'detached'
V_DIGESTER = 'digester'
V_DISUSED = 'disused'
V_DITCH = 'ditch'
V_DOG_PARK = 'dog_park'
V_DOME = 'dome'
V_DRAIN = 'drain'
V_DYKE = 'dyke'
V_FLAT = 'flat'
V_FERRY = 'ferry'
V_FOOTWAY = 'footway'
V_FUEL_STORAGE_TANK = 'fuel_storage_tank'  # deprecated tag in OSM
V_FUNICULAR = 'funicular'
V_GABLED = 'gabled'
V_GAMBREL = 'gambrel'
V_GARDEN = 'garden'
V_GLASSHOUSE = 'glasshouse'
V_GRAVE_YARD = 'grave_yard'
V_GREENHOUSE = 'greenhouse'
V_HALF_HIPPED = 'half-hipped'
V_HAMLET = 'hamlet'
V_HANGAR = 'hangar'
V_HELIPAD = 'helipad'
V_HELIPORT = 'heliport'
V_HIPPED = 'hipped'
V_HORSE_RIDING = 'horse_riding'
V_HOSPITAL = 'hospital'
V_HOUSE = 'house'
V_INDOOR = 'indoor'
V_INDUSTRIAL = 'industrial'
V_INNER = 'inner'
V_ISOLATED_DWELLING = 'isolated_dwelling'
V_LANDMARK = 'landmark'
V_LEAN_TO = 'lean_to'
V_LIGHT_RAIL = 'light_rail'
V_LIGHTHOUSE = 'lighthouse'
V_LIVING_STREET = 'living_street'
V_MANSARD = 'mansard'
V_MARINA = 'marina'
V_MONORAIL = 'monorail'
V_MOTORWAY = 'motorway'
V_MOTORWAY_LINK = 'motorway_link'
V_MULTIPOLYGON = 'multipolygon'
V_MULTISTOREY = 'multi-storey'
V_NARROW_GAUGE = 'narrow_gauge'
V_NAVAL_BASE = 'naval_base'
V_NATURE_RESERVE = 'nature_reserve'
V_NO = 'no'
V_OFFSHORE_PLATFORM = 'offshore_platform'
V_OIL_TANK = 'oil_tank'  # deprecated tag in OSM
V_ONION = 'onion'
V_ORTHODOX = 'orthodox'
V_OUTER = 'outer'
V_OUTLINE = 'outline'
V_PARK = 'park'
V_PARKING = 'parking'
V_PATH = 'path'
V_PEDESTRIAN = 'pedestrian'
V_PIER = 'pier'
V_PITCH = 'pitch'
V_PITCHED = 'pitched'
V_PLACE_OF_WORSHIP = 'place_of_worship'
V_PLANT = 'plant'
V_PLATFORM = 'platform'
V_PLAYGROUND = 'playground'
V_PRESERVED = 'preserved'
V_PRIMARY = 'primary'
V_PRIMARY_LINK = 'primary_link'
V_PYRAMIDAL = 'pyramidal'
V_RAIL = 'rail'
V_RAILWAY = 'railway'
V_RANGE = 'range'
V_RESIDENTIAL = 'residential'
V_RETAIL = 'retail'
V_RIVER = 'river'
V_ROAD = 'road'
V_ROUND = 'round'
V_ROUNDABOUT = 'roundabout'
V_SALTBOX = 'saltbox'
V_SECONDARY = 'secondary'
V_SECONDARY_LINK = 'secondary_link'
V_SERVICE = 'service'
V_SHED = 'shed'
V_SKILLION = 'skillion'
V_SLURRY_TANK = 'slurry_tank'
V_SPUR = 'spur'
V_STADIUM = 'stadium'
V_STATIC_CARAVAN = 'static_caravan'
V_STATION = 'station'
V_STEPS = 'steps'
V_STORAGE_TANK = 'storage_tank'
V_STREAM = 'stream'
V_STY = 'sty'
V_SUBURB = 'suburb'
V_SUBWAY = 'subway'
V_SWIMMING_AREA = 'swimming_area'
V_SWITCH = 'switch'
V_TANK = 'tank'  # deprecated tag in OSM
V_TERMINAL = 'terminal'
V_TERRACE = 'terrace'
V_TERTIARY = 'tertiary'
V_TERTIARY_LINK = 'tertiary_link'
V_TOWER = 'tower'
V_TOWN = 'town'
V_TRACK = 'track'
V_TRAINING_AREA = 'training_area'
V_TRAM = 'tram'
V_TREE = 'tree'
V_TRUNK = 'trunk'
V_TRUNK_LINK = 'trunk_link'
V_UNCLASSIFIED = 'unclassified'
V_UNDERGROUND = 'underground'
V_VILLAGE = 'village'
V_WADI = 'wadi'
V_WATER_TOWER = 'water_tower'
V_WAY = 'way'
V_WIND = 'wind'
V_YES = 'yes'
V_ZOO = 'zoo'


# ======================= LISTS ==================================================================================
L_GLASS_H = [V_GLASSHOUSE, V_GREENHOUSE]
L_STORAGE_TANK = [V_STORAGE_TANK, V_TANK, V_OIL_TANK, V_FUEL_STORAGE_TANK, V_DIGESTER]


# ======================= KEY-VALUE PAIRS ========================================================================
KV_GENERATOR_SOURCE_WIND = 'generator:source=>wind'
KV_LANDUSE_RECREATION_GROUND = 'landuse=>recreation_ground'
KV_LEISURE_PARK = 'leisure=>park'
KV_MAN_MADE_CHIMNEY = 'man_made=>chimney'
KV_NATURAL_TREE = 'natural=>tree'
KV_TREE_ROW = 'natural=>tree_row'
KV_ROUTE_FERRY = 'route=>ferry'


# ======================= VALUE PARSING ==========================================================================


def parse_int(str_int: str, default_value: int) -> int:
    """If string can be parsed then return int, otherwise return the default value."""
    try:
        x = int(str_int)
        return x
    except ValueError:
        return default_value


# ========================= CHECKS TO DIFFERENTIATE STUFF, e.g. processing in buildings vs. pylons ===============
def _is_glasshouse(tags: KeyValueDict, is_building_part: bool) -> bool:
    """Whether this is a glasshouse or a greenhouse.
    Is not yet processed cf. https://gitlab.com/osm2city/osm2city/-/issues/37."""
    building_key = K_BUILDING_PART if is_building_part else K_BUILDING
    return (building_key in tags and tags[building_key] in L_GLASS_H) or (
            K_AMENITY in tags and tags[K_AMENITY] in L_GLASS_H)


def is_storage_tank(tags: KeyValueDict, is_building_part: bool) -> bool:
    """Whether this is a storage tank (or similar) and processed in pylons.py."""
    building_key = K_BUILDING_PART if is_building_part else K_BUILDING
    return (building_key in tags and tags[building_key] in L_STORAGE_TANK) or (
            K_MAN_MADE in tags and tags[K_MAN_MADE] in L_STORAGE_TANK)


def is_chimney(tags: KeyValueDict) -> bool:
    """Whether this is a chimney and processed in pylons.py."""
    return K_MAN_MADE in tags and tags[K_MAN_MADE] in [V_CHIMNEY]


def is_small_building_land_use(tags: KeyValueDict, is_building_part: bool) -> bool:
    """Whether this is a building used for determining land-use, but not used in rendering.

    See also enumerations.py -> BuildingType and get_building_class()."""
    building_key = K_BUILDING_PART if is_building_part else K_BUILDING
    return building_key in tags and tags[building_key] in [V_STY, V_SLURRY_TANK, V_STATIC_CARAVAN] or (
        _is_glasshouse(tags, is_building_part))


def is_small_building_detail(tags: KeyValueDict, is_building_part: bool) -> bool:
    """Small buildings, which are not rendered as buildings (but might get rendered as 'Details' some day).
    As they are not used for land-use either, they can be excluded immediately."""
    building_key = K_BUILDING_PART if is_building_part else K_BUILDING
    return building_key in tags and tags[building_key] in ['garage', 'garages', 'carport', 'car_port',
                                                           'kiosk', 'toilets', 'service',
                                                           'shed', 'tree_house',
                                                           'roof']


def is_highway(tags: KeyValueDict) -> bool:
    return K_HIGHWAY in tags


def is_railway(tags: KeyValueDict) -> bool:
    return K_RAILWAY in tags


def is_lit(tags: KeyValueDict) -> bool:
    if K_LIT in tags and tags[K_LIT] == V_YES:
        return True
    return False


def is_rack_railway(tags: KeyValueDict) -> bool:
    """Rack can have different values, so just excluding no.

    cf. https://wiki.openstreetmap.org/wiki/Key:rack?uselang=en
    """
    if K_RACK in tags and tags[K_RACK] != V_NO:
        return True
    return False


def is_electrified_railway(tags: KeyValueDict) -> bool:
    """Whether this is an electrified railway with overhead contact line.

    Cf. https://wiki.openstreetmap.org/wiki/Key:electrified?uselang=en
    'yes' is taken into account in case not more info is available.
    """
    if K_ELECTRIFIED in tags and tags[K_ELECTRIFIED] in [V_CONTACT_LINE, V_YES]:
        return True
    return False


def is_oneway(tags_dict: KeyValueDict, is_motorway: bool = False) -> bool:
    if is_motorway:
        if (K_ONEWAY in tags_dict) and (tags_dict[K_ONEWAY] == V_NO):
            return False
        else:
            return True  # in motorways oneway is implied
    elif (K_ONEWAY in tags_dict) and (tags_dict[K_ONEWAY] == V_YES):
        return True
    return False


def is_roundabout(tags: KeyValueDict) -> bool:
    return K_JUNCTION in tags and tags[K_JUNCTION] in [V_ROUNDABOUT, V_CIRCULAR]


def parse_tags_lanes(tags_dict: KeyValueDict, default_lanes: int = 1) -> int:
    my_lanes = default_lanes
    if K_LANES in tags_dict:
        my_lanes = parse_int(tags_dict[K_LANES], default_lanes)
    return my_lanes


def is_tunnel(tags: KeyValueDict) -> bool:
    return K_TUNNEL in tags and tags[K_TUNNEL] not in [V_NO]


def is_bridge(tags: KeyValueDict) -> bool:
    """Returns true if the tags for this linear_obj contains the OSM key for bridge."""
    if K_MAN_MADE in tags and tags[K_MAN_MADE] == V_BRIDGE:
        return True
    if K_BRIDGE in tags and tags not in [V_NO]:
        return True
    return False


def is_replaced_bridge(tags: KeyValueDict) -> bool:
    """Returns true is this linear_obj was originally a bridge, but was changed to a non-bridge due to length.
    See method Roads._replace_short_bridges_with_ways.
    The reason to keep a replaced_tag is because else the linear_obj might be split if a node is in the water."""
    return K_REPLACED_BRIDGE_KEY in tags
