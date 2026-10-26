from mockros import Node
from messages import Path


class FollowerNode(Node):
    def __init__(self, bus, tolerance=0.1):
        super().__init__("follower_node", bus)
        self.tolerance = tolerance
        raise NotImplementedError
