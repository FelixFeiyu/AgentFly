import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence

from .domain import MissionGraph


@dataclass(frozen=True)
class MissingConstraint:
    constraint: str
    reason: str


@dataclass(frozen=True)
class ConstraintEvaluation:
    total: int
    satisfied: int
    missing: Sequence[MissingConstraint]

    @property
    def coverage(self) -> float:
        return self.satisfied / self.total if self.total else 1.0


class ConstraintEvaluator:
    VERSION = "constraint-v1"

    def __init__(self):
        self.rules: Dict[str, Callable[[Any, MissionGraph], bool]] = {
            "battery_reserve": self._battery_reserve,
            "geofence": self._geofence,
            "low_confidence_recapture": self._low_confidence_recapture,
            "asset_order": self._asset_order,
            "safety_distance": self._safety_distance,
            "human_confirmation": self._human_confirmation,
            "unreachable_recovery": self._unreachable_recovery,
            "privacy_zone": self._privacy_zone,
            "communication_loss": self._communication_loss,
            "coverage": self._coverage,
            "image_overlap": self._image_overlap,
            "quality_check": self._quality_check,
            "battery_split": self._battery_split,
        }

    def evaluate(self, task: Any, graph: MissionGraph) -> ConstraintEvaluation:
        missing: List[MissingConstraint] = []
        for constraint in task.constraints:
            rule = self.rules.get(constraint)
            if rule is None or not rule(task, graph):
                missing.append(
                    MissingConstraint(
                        constraint,
                        self._reason(constraint),
                    )
                )
        return ConstraintEvaluation(
            total=len(task.constraints),
            satisfied=len(task.constraints) - len(missing),
            missing=tuple(missing),
        )

    @staticmethod
    def _reason(constraint: str) -> str:
        reasons = {
            "geofence": "add geofence/avoid_zone metadata to movement nodes",
            "battery_reserve": "set mission reserve_ratio to at least 0.25",
            "low_confidence_recapture": "add confidence condition and recapture node",
            "asset_order": "add at least three ordered asset inspection nodes",
            "safety_distance": "bind the requested minimum distance to inspection metadata",
            "human_confirmation": "add a human_confirm node",
            "unreachable_recovery": "route movement failures to a recover node",
            "privacy_zone": "encode privacy_zone/avoid_zone on movement nodes",
            "communication_loss": "encode communication-loss condition with return/recovery action",
            "coverage": "add a coverage_check report node",
            "image_overlap": "bind forward_overlap >= 0.8 and side_overlap >= 0.7",
            "quality_check": "add blur/image-quality check node",
            "battery_split": "add low-battery split_sortie recovery strategy",
        }
        return reasons.get(constraint, "unsupported constraint rule")

    @staticmethod
    def _metadata_text(graph: MissionGraph) -> str:
        parts = []
        for node in graph.nodes:
            parts.append(node.id)
            for key, value in node.metadata.items():
                parts.extend((str(key), str(value)))
        return " ".join(parts).lower()

    def _battery_reserve(self, task: Any, graph: MissionGraph) -> bool:
        return graph.reserve_ratio >= 0.25

    def _geofence(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        return any(term in text for term in ("geofence", "avoid_zone", "禁飞", "绕开"))

    def _low_confidence_recapture(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        targets = [node.metadata.get("target") for node in graph.nodes if node.kind in {"inspect", "capture"}]
        repeated = any(target and targets.count(target) >= 2 for target in targets)
        has_capture = any(node.kind == "capture" or "recapture" in node.id for node in graph.nodes)
        has_condition = any(term in text for term in ("confidence", "置信", "confidence_threshold"))
        return has_condition and (repeated or has_capture)

    def _asset_order(self, task: Any, graph: MissionGraph) -> bool:
        inspections = [node for node in graph.nodes if node.kind == "inspect"]
        return len(inspections) >= 3 and all(any(char.isdigit() for char in str(node.metadata.get("target", ""))) for node in inspections)

    def _safety_distance(self, task: Any, graph: MissionGraph) -> bool:
        match = re.search(r"至少(\d+)米", task.instruction)
        expected = float(match.group(1)) if match else 0.0
        inspections = [node for node in graph.nodes if node.kind == "inspect"]
        values = [
            float(node.metadata.get("safe_distance_m", node.metadata.get("safe_distance", -1)))
            for node in inspections
        ]
        return bool(values) and all(value >= expected for value in values)

    def _human_confirmation(self, task: Any, graph: MissionGraph) -> bool:
        return any(node.kind == "human_confirm" for node in graph.nodes)

    def _unreachable_recovery(self, task: Any, graph: MissionGraph) -> bool:
        recover_ids = {node.id for node in graph.nodes if node.kind == "recover"}
        moves = [node for node in graph.nodes if node.kind == "move"]
        return bool(recover_ids and moves) and all(node.failure_target in recover_ids for node in moves)

    def _privacy_zone(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        return any(term in text for term in ("privacy", "隐私", "avoid_zone"))

    def _communication_loss(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        has_condition = any(term in text for term in ("communication", "link_loss", "失联", "通信中断"))
        has_safe_action = any(node.kind in {"return", "recover"} for node in graph.nodes)
        return has_condition and has_safe_action

    def _coverage(self, task: Any, graph: MissionGraph) -> bool:
        return "coverage_check" in self._metadata_text(graph)

    def _image_overlap(self, task: Any, graph: MissionGraph) -> bool:
        for node in graph.nodes:
            forward = float(node.metadata.get("forward_overlap", 0))
            side = float(node.metadata.get("side_overlap", 0))
            if forward >= 0.8 and side >= 0.7:
                return True
        return False

    def _quality_check(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        return any(term in text for term in ("blur_check", "quality_check", "模糊", "图像质量"))

    def _battery_split(self, task: Any, graph: MissionGraph) -> bool:
        text = self._metadata_text(graph)
        has_battery = any(term in text for term in ("battery", "电量"))
        has_split = any(term in text for term in ("split_sortie", "分架次", "split mission"))
        return has_battery and has_split
