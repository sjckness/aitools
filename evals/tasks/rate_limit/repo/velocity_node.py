from mockros import Node
from util import clamp


class VelocityNode(Node):
    def __init__(self, bus, max_linear=0.5):
        super().__init__("velocity_node", bus)
        self.max_linear = max_linear
        self._pub = self.create_publisher("cmd_vel_safe")
        self.create_subscription("cmd_vel", self._on_cmd)

    def _on_cmd(self, msg):
        out = dict(msg)
        out["linear"] = clamp(msg["linear"], -self.max_linear, self.max_linear)
        self._pub(out)
