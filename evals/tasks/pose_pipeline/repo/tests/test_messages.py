import unittest
from messages import Pose2D, Twist


class TestMessages(unittest.TestCase):
    def test_roundtrip(self):
        p = Pose2D(1.0, 2.0, 0.5)
        self.assertEqual(Pose2D.from_dict(p.to_dict()), p)
        t = Twist(0.3, -0.1)
        self.assertEqual(Twist.from_dict(t.to_dict()), t)

    def test_missing_key(self):
        with self.assertRaises(ValueError):
            Pose2D.from_dict({"x": 1.0})
