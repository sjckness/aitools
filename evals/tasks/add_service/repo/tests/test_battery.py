import unittest
from mockros import Bus
from battery_node import BatteryNode


class TestBattery(unittest.TestCase):
    def setUp(self):
        self.bus = Bus()
        self.node = BatteryNode(self.bus)

    def test_status_empty(self):
        self.assertEqual(self.bus.call("battery/get_status"),
                         {"count": 0, "last": None, "low": False})

    def test_status_low(self):
        self.bus.publish("battery/voltage", 12.4)
        self.bus.publish("battery/voltage", 10.9)
        self.assertEqual(self.bus.call("battery/get_status"),
                         {"count": 2, "last": 10.9, "low": True})
