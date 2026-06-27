from dataclasses import dataclass, replace
from typing import Dict, Optional

from .domain import MissionGraph, MissionStatus, NodeStatus


@dataclass(frozen=True)
class Event:
    kind: str
    node_id: Optional[str] = None


@dataclass(frozen=True)
class AgentState:
    graph: MissionGraph
    mission_status: MissionStatus
    node_statuses: Dict[str, NodeStatus]
    event_count: int = 0

    @classmethod
    def create(cls, graph: MissionGraph) -> "AgentState":
        return cls(
            graph=graph,
            mission_status=MissionStatus.CREATED,
            node_statuses={node.id: NodeStatus.PENDING for node in graph.nodes},
        )


class StateReducer:
    TRANSITIONS = {
        "node_ready": (NodeStatus.PENDING, NodeStatus.READY),
        "node_started": (NodeStatus.READY, NodeStatus.RUNNING),
        "node_succeeded": (NodeStatus.RUNNING, NodeStatus.SUCCEEDED),
        "node_failed": (NodeStatus.RUNNING, NodeStatus.FAILED),
        "node_skipped": (NodeStatus.PENDING, NodeStatus.SKIPPED),
    }

    @classmethod
    def apply(cls, state: AgentState, event: Event) -> AgentState:
        statuses = dict(state.node_statuses)
        if event.kind in cls.TRANSITIONS:
            if event.node_id is None:
                raise ValueError("node event requires node_id")
            expected, target = cls.TRANSITIONS[event.kind]
            if statuses[event.node_id] != expected:
                raise ValueError("illegal transition for %s" % event.node_id)
            statuses[event.node_id] = target
        return replace(state, node_statuses=statuses, event_count=state.event_count + 1)
