import unittest
from params import parse_params, parse_value


class TestParams(unittest.TestCase):
    def test_scalar(self):
        self.assertEqual(parse_value("7"), 7)

    def test_list(self):
        self.assertEqual(parse_value("[1, 2.5, abc]"), [1, 2.5, "abc"])
        self.assertEqual(parse_value("[]"), [])

    def test_in_doc(self):
        doc = "n:\n  ros__parameters:\n    gains: [0.1, 0.2, 3]\n"
        self.assertEqual(parse_params(doc)["n"]["ros__parameters"]["gains"], [0.1, 0.2, 3])
