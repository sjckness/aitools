import unittest
from messages import Path, Waypoint


class TestPath(unittest.TestCase):
    def test_length(self):
        p = Path([Waypoint(0, 0), Waypoint(3, 4), Waypoint(3, 6)])
        self.assertAlmostEqual(p.length(), 7.0)
        self.assertEqual(Path().length(), 0.0)

    def test_roundtrip(self):
        p = Path([Waypoint(1, 2), Waypoint(3, 4)])
        self.assertEqual(Path.from_dict(p.to_dict()), p)
