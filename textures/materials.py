"""This module is about AC3D materials and OSM colours as well as OSM materials.

A material in AC3D is kind of colour and its definition can be found at http://www.inivis.com/resources.html.

In OSM colour is used in tagging - with a preference for British English spelling.
See https://wiki.openstreetmap.org/wiki/Key:colour.

osm2city only supports the following two keys (cf. method screen_osm_keys_for_colour_spelling(...)):
* building:colour
* roof:colour

From version 2018.2 of FlightGear roof and facade textures will be partly transparent and therefore the colour is
taken more or less directly from the OSM tagging. I.e. the colour of a facade / roof is determined by the shader,
which multiplies the surface colour value in AC3D (based on material) with the texture colour value.
A colour value of white will result in no change to the texture's colour value.

"""
from typing import Dict
import unittest


def screen_texture_tags_for_colour_spelling(original: str) -> str:
    """Replaces all occurrences of color with colour and gray with grey"""
    if "color" in original or "gray" in original:
        new_string = original.replace("color", "colour")
        new_string = new_string.replace("gray", "grey")
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
    """Makes sure colour and material is spelled correctly in key and reduces to known keys in osm2city"""
    for wrong, correct in OSM_MATERIAL_KEY_MAPPING:
        if wrong in tags:
            if correct not in tags:
                tags[correct] = tags[wrong]
            del (tags[wrong])


def map_hex_colour(value):
    colour_map = {
                  "#000000": "black",
                  "#FFFFFF": "white",
                  "#808080": "grey",
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

# TODO: map from short hex colours to long hex colours
# An abbreviated, three (hexadecimal)-digit form is used.[5] Expanding this form to the six-digit form is as simple as
# doubling each digit: 09C becomes 0099CC as presented on the following CSS example:
#
# .threedigit { color: #09C;    }
# .sixdigit   { color: #0099CC; } /* same color as above */

# TODO: map from hex colours without # to real hex colours
# TODO: map from hex colours to rgb -> materials
# TODO: map from colour names to hex colours
# TODO: make light_gray -> lightgray
# TODO: support named 16 colour values in HTML 4.01:
#   cf. https://en.wikipedia.org/wiki/Web_colors: white, silver, gray, black, red, maroon, yellow, olive, lime, green,
#       navy, fuchsia, purple
# TODO: additionally support OSM most used colour names as of January 2018:
#   cf. https://taginfo.openstreetmap.org/keys/building%3Acolour#values:
#       brown, beige, silver, lightgrey, orange, lightyellow, snow, firebrick, pink, tan, lightbrown, lightgray, wheat,
#       lightblue, cream, floralwhite, moccasin, gold, fuchsia
#   cf. https://taginfo.openstreetmap.org/keys/roof%3Acolour#values:
#       cf. included above, salmon, darkgray, darksalmon, dimgray, lightsalmon, darkred, sand, indianred, orangered,
#       lightblue, darkgreen, brick


# ================ UNITTESTS =======================

class TestOSMParser(unittest.TestCase):

    def test_screen_osm_keys_for_colour_material_variants(self):
        my_tags = {'foo': '1', 'building:color': 'red', 'building:colour': 'blue', 'building:roof:material': 'stone'}
        screen_osm_keys_for_colour_material_variants(my_tags)
        self.assertEqual(3, len(my_tags), '# of element reduced to 3')
        self.assertEqual('blue', my_tags['building:colour'], 'original key/value preserved')
        self.assertEqual('stone', my_tags['roof:material'], 'original key replaced and value preserved')
