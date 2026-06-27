from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class EnvironmentResult:
    success: bool
    code: str = "ok"
    data: Dict[str, Any] = field(default_factory=dict)


class MockUAVEnvironment:
    def __init__(
        self,
        battery_ratio: float = 1.0,
        unreachable_waypoints: Tuple[str, ...] = (),
        low_confidence_targets: Tuple[str, ...] = (),
    ):
        self.battery_ratio = battery_ratio
        self.unreachable_waypoints = set(unreachable_waypoints)
        self.low_confidence_targets = set(low_confidence_targets)
        self.airborne = False
        self.side_effect_counts = Counter()
        self.distance_flown = 0.0

    def execute(self, name: str, arguments: Dict[str, Any]) -> EnvironmentResult:
        self.side_effect_counts[name] += 1
        if name == "takeoff":
            self.airborne = True
            self.battery_ratio -= 0.03
            return EnvironmentResult(True, data={"airborne": True})
        if name == "move":
            waypoint = str(arguments["waypoint"])
            if waypoint in self.unreachable_waypoints:
                return EnvironmentResult(False, "waypoint_unreachable", {"waypoint": waypoint})
            distance = float(arguments.get("distance", 10.0))
            self.distance_flown += distance
            self.battery_ratio -= distance * 0.002
            return EnvironmentResult(True, data={"waypoint": waypoint, "distance": distance})
        if name == "inspect":
            target = str(arguments["target"])
            confidence = 0.45 if target in self.low_confidence_targets else 0.9
            return EnvironmentResult(True, data={"target": target, "confidence": confidence})
        if name == "return":
            distance = float(arguments.get("distance", 10.0))
            self.distance_flown += distance
            self.battery_ratio -= distance * 0.002
            return EnvironmentResult(True, data={"returned": True})
        if name == "land":
            self.airborne = False
            return EnvironmentResult(True, data={"airborne": False})
        if name in {"report", "human_confirm", "recover"}:
            return EnvironmentResult(True, data=dict(arguments))
        return EnvironmentResult(False, "unknown_tool", {"tool": name})
