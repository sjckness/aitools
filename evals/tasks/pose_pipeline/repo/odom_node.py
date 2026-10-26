from mockros import Node
from messages import Pose2D, Twist


class OdomNode(Node):
    def __init__(self, bus, dt=0.1):
        super().__init__("odom_node", bus)
        self.dt = dt
        self.pose = Pose2D()
        raise NotImplementedError
