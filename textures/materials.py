"""This module is about AC3D materials and OSM colours as well as OSM materials.

A material in AC3D is kind of colour and its definition can be found at http://www.inivis.com/resources.html.
MATERIAL (name) rgb %f %f %f  amb %f %f %f  emis %f %f %f  spec %f %f %f  shi %d  trans %f

Single line describing a material.  These are referenced by the "mat"
token of a surface.  The first "MATERIAL" in the file will be indexed as
zero.

Cf. https://wiki.openstreetmap.org/wiki/Key:material for use of materials in OSM.


In OSM "colour" instead of "color" is used in tagging - with a preference for British English spelling.
See https://wiki.openstreetmap.org/wiki/Key:colour.

osm2city only supports the following two keys (cf. method screen_osm_keys_for_colour_spelling(...)):
* building:colour
* roof:colour

Then again "gray" is used instead of "grey" due to W3C naming.

From version 2018.2 of FlightGear roof and facade textures will be partly transparent and therefore the colour is
taken more or less directly from the OSM tagging. I.e. the colour of a facade / roof is determined by the shader,
which multiplies the surface colour value in AC3D (based on material) with the texture colour value.
A colour value of white will result in no change to the texture's colour value.

"""
import logging
from typing import Dict, List
import unittest

import parameters


def screen_texture_tags_for_colour_spelling(original: str) -> str:
    """Replaces all occurrences of color with colour and grey with gray"""
    if "color" in original or "grey" in original:
        new_string = original.replace("color", "colour")
        new_string = new_string.replace("grey", "gray")
        return new_string
    else:
        return original


OSM_MATERIAL_KEY_MAPPING = [('building:color', 'building:colour'),
                            ('building:facade:color', 'building:colour'),
                            ('building:facade:colour', 'building:colour'),
                            ('wall:colour', 'building:colour'),
                            ('wall:color', 'building:colour'),
                            ('building:colour_1', 'building:colour'),
                            ('roof:color', 'roof:colour'),
                            ('building:roof:color', 'roof:colour'),
                            ('building:roof:colour', 'roof:colour'),
                            ('roof:colour_1', 'roof:colour'),
                            ('building:facade:material', 'building:material'),
                            ('building:roof:material', 'roof:material')
                            ]


def screen_osm_keys_for_colour_material_variants(tags: Dict[str, str]) -> None:
    """Makes sure colour and material is spelled correctly in key and reduces to known keys in osm2city.
    And for the correct ones it makes sure that the values are recognizabl."""
    for wrong, correct in OSM_MATERIAL_KEY_MAPPING:
        if wrong in tags:
            if correct not in tags:
                tags[correct] = tags[wrong]
            del (tags[wrong])

    # now make sure that the values are correct
    if parameters.FLAG_COLOUR_TEX:
        if 'building:colour' in tags:
            tags['building:colour'] = map_osm_colour_value_to_hex(tags['building:colour'], True)
        if 'roof:colour' in tags:
            tags['roof:colour'] = map_osm_colour_value_to_hex(tags['roof:colour'], True)


def map_hex_colour(value):
    # FIXME can be removed once textures are transparent without colour
    colour_map = {
                  "#000000": "black",
                  "#FFFFFF": "white",
                  "#808080": "gray",
                  "#C0C0C0": "silver",
                  "#800000": "maroon",
                  "#FF0000": "red",
                  "#808000": "olive",
                  "#FFFF00": "yellow",
                  "#008000": "green",
                  "#00FF00": "lime",
                  "#008080": "teal",
                  "#00FFFF": "aqua",
                  "#000080": "navy",
                  "#0000FF": "blue",
                  "#800080": "purple",
                  "#FF00FF": "fuchsia"
    }
    hash_pos = value.find("#")
    if (value.startswith("roof:colour") or value.startswith("facade:building:colour")) and hash_pos > 0:
        try:
            tag_string = value[:hash_pos]
            colour_hex_string = value[hash_pos:].upper()

            return tag_string + colour_map[colour_hex_string]
        except KeyError:
            return value
    return value


COLOUR_NAME_TO_HEX_MAP = {
    # See https://www.w3.org/TR/css-color-3/#html4 16 basic colours.
    'black': '#000000',
    'silver': '#C0C0C0',
    'gray': '#808080',
    'white': '#FFFFFF',
    'maroon': '#800000',
    'red': '#FF0000',
    'purple': '#800080',
    'fuchsia': '#FF00FF',
    'green': '#008000',
    'lime': '#00FF00',
    'olive': '#808000',
    'yellow': '#FFFF00',
    'navy': '#000080',
    'blue': '#0000FF',
    'teal': '#008080',
    'aqua': '#00FFFF',
    # Additional named colours most used cf. https://taginfo.openstreetmap.org/keys/building%3Acolour#values
    # and https://taginfo.openstreetmap.org/keys/roof%3Acolour#values
    # for colour card see https://www.w3.org/TR/css-color-3/#svg-color
    'brown': '#A52A2A',
    'beige': '#F5F5DC',
    'lightgray': '#D3D3D3',
    'orange': '#FFA500',
    'lightyellow': '#FFFFE0',
    'snow': '#FFFAFA',
    'firebrick': '#B22222',
    'pink': '#FFC0CB',
    'tan': '#D2B48C',
    'wheat': '#F5DEB3',
    'lightblue': '#ADD8E6',
    'floralwhite': '#FFFAF0',
    'moccasin': '#FFE4B5',
    'gold': '#FFD700',
    'salmon': '#FA8072',
    'darkgray': '#A9A9A9',
    'darksalmon': '#E9967A',
    'dimgray': '#696969',
    'lightsalmon': '#FFA07A',
    'darkred': '#8B0000',
    'indianred': '#CD5C5C',
    'orangered': '#FF4500',
    'darkgreen': '#006400'
}


def map_osm_colour_value_to_hex(colour_value: str, facade_colour: bool) -> str:
    """Maps a colour value from OSM to a hex colour value.

    If the value cannot be interpreted, then a default colour based on parameters is used.
    """
    # make light_gray -> lightgray and remove #
    my_value = colour_value.replace('_', '').replace('#', '')
    # now let us see whether it can be interpreted as a known colour name
    if my_value in COLOUR_NAME_TO_HEX_MAP:
        return COLOUR_NAME_TO_HEX_MAP[my_value].upper()
    # now try to interpret it as a hex value
    if len(my_value) == 3:  # transform abbreviated, three (hexadecimal)-digit
        my_value = my_value[0] + my_value[0] + my_value[1] + my_value[1] + my_value[2] + my_value[2]
    if len(my_value) == 6:
        try:
            int(my_value, 16)
            return ('#' + my_value).upper()
        except ValueError:
            pass  # nothing to do - it is not a pure hex colour value

    # nothing worked. Log the value and then return based on parameters.
    logging.debug('OSM colour value cannot be interpreted - using default value instead: %s', colour_value)
    if facade_colour:
        return parameters.BUILDING_FACADE_DEFAULT_COLOUR
    else:
        return parameters.BUILDING_ROOF_DEFAULT_COLOUR


def transform_hex_colour_int_rgb_values(hex_colour: str) -> List[int]:
    value = hex_colour.lstrip('#')
    return [int(value[i:i + 2], 16) for i in range(0, 6, 2)]


# amb has to be 1 1 1 no matter the colour when textures are involved
MATERIAL_FORMAT = ('MATERIAL "{0}" rgb {1:05.3f} {2:05.3f} {3:05.3f} amb 1 1 1 '  # {1:05.3f} {2:05.3f} {3:05.3f} '
                   'emis 0 0 0 spec 0.0 0.0 0.0 shi 0 trans 0')


def create_material(name: str, red: float, green: float, blue: float) -> str:
    """Creates a material line in AC3D format.
    See also http://wiki.flightgear.org/AC_files:_Basic_changes_to_textures_and_colors#Textures"""
    return MATERIAL_FORMAT.format(name, red, green, blue)


def create_materials_list_from_hex_colours(hex_colours: Dict[str, int]) -> List[str]:
    # FIXME: make sure that the sequence is absolutely correct as input
    materials_list = list()
    for key, value in hex_colours.items():
        rgb_int = transform_hex_colour_int_rgb_values(key)
        materials_list.append(create_material(key, rgb_int[0] / 255, rgb_int[1] / 255, rgb_int[2] / 255))
    return materials_list


def create_materials_list_roads() -> List[str]:
    materials_list = list()
    materials_list.append(create_material('unlit', 0.0, 0.0, 0.0))
    materials_list.append(create_material('lit', 1.0, 1.0, 1.0))
    return materials_list


# ================ UNITTESTS =======================

class TestOSMParser(unittest.TestCase):

    def test_screen_osm_keys_for_colour_material_variants(self):
        my_tags = {'foo': '1', 'building:color': 'red', 'building:colour': 'blue', 'building:roof:material': 'stone'}
        screen_osm_keys_for_colour_material_variants(my_tags)
        self.assertEqual(3, len(my_tags), '# of element reduced to 3')
        self.assertEqual('blue', my_tags['building:colour'], 'original key/value preserved')
        self.assertEqual('stone', my_tags['roof:material'], 'original key replaced and value preserved')

    def test_map_osm_colour_value_to_hex(self):
        self.assertEqual(map_osm_colour_value_to_hex('lightgray', True), '#D3D3D3', 'Direct name mapping')
        self.assertEqual(map_osm_colour_value_to_hex('light_gray', True), '#D3D3D3', 'Name mapping with underscore')
        self.assertEqual(map_osm_colour_value_to_hex('D3D3D3', True), '#D3D3D3', 'Valid hex without #')
        self.assertEqual(map_osm_colour_value_to_hex('#D3D3D3', True), '#D3D3D3', 'Valid hex with #')
        self.assertEqual(map_osm_colour_value_to_hex('#ABC', True), '#AABBCC', 'Valid 3-digit hex with #')
        self.assertEqual(map_osm_colour_value_to_hex('', True), parameters.BUILDING_FACADE_DEFAULT_COLOUR, 'Empty')
        self.assertEqual(map_osm_colour_value_to_hex('x', False), parameters.BUILDING_ROOF_DEFAULT_COLOUR, 'Not valid')

    def test_create_material_(self):
        black = 'MATERIAL "black" rgb 0.000 0.000 0.000 amb 0.000 0.000 0.000 spec 0.5 0.5 0.5 shi 64 trans 0'
        self.assertEqual(black, create_material('black', 0.0, 0.0, 0.0))

    def test_transform_hex_colour_int_rgb_values(self):
        self.assertEqual(0, transform_hex_colour_int_rgb_values('#000000')[0], 'black')
        self.assertEqual(255, transform_hex_colour_int_rgb_values('ffffff')[0], 'white without #')
