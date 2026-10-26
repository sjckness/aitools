import unittest
from mockros import Bus
from velocity_node import VelocityNode


class TestVelocity(unittest.TestCase):
    def setUp(self):
        self.bus = Bus()
        self.out = []
        self.bus.subscribe("cmd_vel_safe", self.out.append)
        self.node = VelocityNode(self.bus)

    def test_linear_clamped(self):
        self.bus.publish("cmd_vel", {"linear": 2.0, "angular": 0.0})
        self.assertEqual(self.out[-1]["linear"], 0.5)

    def test_angular_clamped(self):
        self.bus.publish("cmd_vel", {"linear": 0.0, "angular": -3.0})
        self.assertEqual(self.out[-1]["angular"], -1.0)

    def test_set_limits(self):
        res = self.bus.call("velocity/set_limits", {"max_angular": 2.0})
        self.assertEqual(res, {"max_linear": 0.5, "max_angular": 2.0})
