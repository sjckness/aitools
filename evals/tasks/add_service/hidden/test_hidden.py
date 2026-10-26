import unittest
from mockros import Bus
from battery_node import BatteryNode


class TestHidden(unittest.TestCase):
    def test_reset(self):
        bus = Bus()
        BatteryNode(bus)
        bus.publish("battery/voltage", 9)
        self.assertEqual(bus.call("battery/reset"), {"ok": True})
        self.assertEqual(bus.call("battery/get_status")["count"], 0)

    def test_threshold(self):
        bus = Bus()
        BatteryNode(bus)
        bus.publish("battery/voltage", 11.0)
        self.assertFalse(bus.call("battery/get_status")["low"])
