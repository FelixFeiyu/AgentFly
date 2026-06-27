from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class MissionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    ABORTED_SAFE = "aborted_safe"
    FAILED = "failed"


@dataclass(frozen=True)
class MissionNode:
    id: str
    kind: str
    dependencies: Tuple[str, ...] = ()
    failure_target: Optional[str] = "recover"
    risk: str = "low"
    required: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionGraph:
    mission_id: str
    nodes: Tuple[MissionNode, ...]
    reserve_ratio: float = 0.25
    version: int = 1

    def by_id(self) -> Dict[str, MissionNode]:
        return {node.id: node for node in self.nodes}


@dataclass(frozen=True)
class ValidationReport:
    errors: Tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors
