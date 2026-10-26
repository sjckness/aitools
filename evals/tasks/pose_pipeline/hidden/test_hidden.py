import math
import unittest
from mockros import Bus
from odom_node import OdomNode


class TestHidden(unittest.TestCase):
    def test_turn_and_reset(self):
        bus = Bus()
        out = []
        bus.subscribe("odom", out.append)
        OdomNode(bus, dt=0.5)
        bus.publish("cmd_vel", {"linear": 0.0, "angular": math.pi})
        self.assertAlmostEqual(out[-1]["theta"], math.pi / 2)
        bus.publish("cmd_vel", {"linear": 2.0, "angular": 0.0})
        self.assertAlmostEqual(out[-1]["y"], 1.0)
        self.assertAlmostEqual(out[-1]["x"], 0.0, places=6)
        self.assertEqual(bus.call("odom/reset"), {"ok": True})
        bus.publish("cmd_vel", {"linear": 0.0, "angular": 0.0})
        self.assertEqual(out[-1], {"x": 0.0, "y": 0.0, "theta": 0.0})
