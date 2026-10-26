import unittest
from mockros import Bus
from follower_node import FollowerNode


class TestHidden(unittest.TestCase):
    def test_sequence(self):
        bus = Bus()
        cmds = []
        bus.subscribe("cmd_vel", cmds.append)
        FollowerNode(bus, tolerance=0.1)
        self.assertFalse(bus.call("follower/status")["done"])
        bus.publish("path", {"waypoints": [{"x": 1, "y": 0}, {"x": 2, "y": 0}]})
        bus.publish("odom", {"x": 0, "y": 0})
        self.assertEqual(cmds, [{"linear": 1.0, "angular": 0.0}])
        bus.publish("odom", {"x": 1.0, "y": 0.0})
        self.assertEqual(bus.call("follower/status"),
                         {"index": 1, "remaining": 1, "done": False})
        bus.publish("odom", {"x": 2.0, "y": 0.0})
        bus.publish("odom", {"x": 2.0, "y": 0.0})
        self.assertEqual(cmds[-1], {"linear": 0.0, "angular": 0.0})
        self.assertEqual(cmds.count({"linear": 0.0, "angular": 0.0}), 1)
        self.assertTrue(bus.call("follower/status")["done"])
