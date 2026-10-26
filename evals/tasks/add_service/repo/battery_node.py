from mockros import Node

LOW_THRESHOLD = 11.0


class BatteryNode(Node):
    def __init__(self, bus):
        super().__init__("battery_node", bus)
        self.readings = []
        self.create_subscription("battery/voltage", self._on_voltage)

    def _on_voltage(self, msg):
        self.readings.append(float(msg))
