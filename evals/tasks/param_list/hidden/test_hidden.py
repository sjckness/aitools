import unittest
from params import parse_value


class TestHidden(unittest.TestCase):
    def test_edge(self):
        self.assertEqual(parse_value("[ 1 ,2,  3 ]"), [1, 2, 3])
        self.assertEqual(parse_value("[a]"), ["a"])
        self.assertEqual(parse_value("abc"), "abc")
