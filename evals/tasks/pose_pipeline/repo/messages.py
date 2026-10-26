from dataclasses import dataclass


@dataclass
class Twist:
    linear: float = 0.0
    angular: float = 0.0

    def to_dict(self):
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d):
        raise NotImplementedError


@dataclass
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0

    def to_dict(self):
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d):
        raise NotImplementedError
