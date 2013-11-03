# -*- coding: utf-8 -*-
"""
Central place for unit tests of osm2city modules
"""

import osmparser
import unittest


class TestOSMParser(unittest.TestCase):
    def test_parse_length(self):
        self.assertAlmostEqual(1.2, osmparser.parse_length(' 1.2 '), 2, "Correct number with trailing spaces")
        self.assertAlmostEqual(1.2, osmparser.parse_length(' 1.2 m'), 2, "Correct number with meter unit incl. space")
        self.assertAlmostEqual(1.2, osmparser.parse_length(' 1.2m'), 2, "Correct number with meter unit without space")
        self.assertAlmostEqual(1200, osmparser.parse_length(' 1.2 km'), 2, "Correct number with km unit incl. space")
        self.assertAlmostEqual(2092.1472, osmparser.parse_length(' 1.3mi'), 2, "Correct number with mile unit without space")
        self.assertAlmostEqual(3.048, osmparser.parse_length("10'"), 2, "Correct number with feet unit without space")
        self.assertAlmostEqual(3.073, osmparser.parse_length('10\'1"'), 2, "Correct number with feet unit without space")
        self.assertEquals(0, osmparser.parse_length('m'), "Only valid unit")
        self.assertEquals(0, osmparser.parse_length('"'), "Only inches, no feet")


    def test_is_parseable_float(self):
        self.assertFalse(osmparser.is_parseable_float('1,2'))
        self.assertFalse(osmparser.is_parseable_float('x'))
        self.assertTrue(osmparser.is_parseable_float('1.2'))


if __name__ == '__main__':
    unittest.main()