import unittest
from params import parse_value


class TestHidden(unittest.TestCase):
    def test_edge(self):
        self.assertIs(parse_value("  TRUE "), True)
        self.assertEqual(parse_value("truex"), "truex")
        self.assertEqual(parse_value('"true"'), "true")
        self.assertEqual(parse_value("1e3"), 1000.0)
