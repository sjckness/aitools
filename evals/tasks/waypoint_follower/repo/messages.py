from dataclasses import dataclass, field
from typing import List


@dataclass
class Waypoint:
    x: float
    y: float


@dataclass
class Path:
    waypoints: List[Waypoint] = field(default_factory=list)

    def length(self):
        raise NotImplementedError

    def to_dict(self):
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d):
        raise NotImplementedError
