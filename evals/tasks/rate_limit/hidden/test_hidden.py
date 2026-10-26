import unittest
from mockros import Bus
from velocity_node import VelocityNode


class TestHidden(unittest.TestCase):
    def test_limits_apply(self):
        bus = Bus()
        out = []
        bus.subscribe("cmd_vel_safe", out.append)
        VelocityNode(bus, max_angular=0.2)
        bus.call("velocity/set_limits", {"max_linear": 1.5})
        bus.publish("cmd_vel", {"linear": 9, "angular": 9})
        self.assertEqual(out[-1], {"linear": 1.5, "angular": 0.2})
