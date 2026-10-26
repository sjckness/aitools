import unittest
from params import parse_params, parse_value


class TestParams(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_value("3"), 3)
        self.assertEqual(parse_value("-2.5"), -2.5)

    def test_bool(self):
        self.assertIs(parse_value("true"), True)
        self.assertIs(parse_value("False"), False)

    def test_quoted(self):
        self.assertEqual(parse_value('"base_link"'), "base_link")
        self.assertEqual(parse_value("'odom'"), "odom")

    def test_nested(self):
        doc = "node:\n  ros__parameters:\n    use_sim_time: true\n    frame: \"map\"\n    rate: 10\n"
        self.assertEqual(
            parse_params(doc),
            {"node": {"ros__parameters": {"use_sim_time": True, "frame": "map", "rate": 10}}},
        )
