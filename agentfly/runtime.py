from dataclasses import dataclass
from typing import List, Set, Tuple

from .agents import AgentPolicy
from .domain import MissionGraph, MissionStatus
from .environment import MockUAVEnvironment
from .graph import GraphValidator
from .tools import SafetyGate, ToolCall, ToolManager


@dataclass(frozen=True)
class RunResult:
    mission_id: str
    method: str
    status: MissionStatus
    completed_nodes: int
    required_nodes: int
    tool_calls: int
    successful_tool_calls: int
    recovery_attempts: int
    recovery_successes: int
    constraint_violations: int
    reasoning_steps: int
    distance_flown: float
    initial_battery: float
    final_battery: float
    visited_waypoints: Tuple[str, ...]
    fault_present: bool


class MissionRuntime:
    def __init__(self, policy: AgentPolicy):
        self.policy = policy

    def run(self, graph: MissionGraph, env: MockUAVEnvironment) -> RunResult:
        report = GraphValidator().validate(graph)
        if not report.valid:
            raise ValueError("invalid graph: %s" % "; ".join(report.errors))
        initial_battery = env.battery_ratio
        manager = ToolManager(env, SafetyGate(graph.reserve_ratio))
        completed: Set[str] = set()
        visited: List[str] = []
        tool_calls = 0
        successful_calls = 0
        recovery_attempts = 0
        recovery_successes = 0
        reasoning_steps = 0
        status = MissionStatus.RUNNING
        fault_present = bool(env.unreachable_waypoints or env.low_confidence_targets)

        while True:
            ready = [
                node
                for node in graph.nodes
                if node.id not in completed
                and node.kind != "recover"
                and all(dependency in completed for dependency in node.dependencies)
            ]
            if not ready:
                break
            node = ready[0]
            reasoning_steps += 1
            arguments = dict(node.metadata)
            arguments.pop("alternate", None)
            call = ToolCall(node.kind, arguments, "%s:%s" % (graph.mission_id, node.id))
            result = manager.invoke(call)
            tool_calls += 1
            if result.success:
                successful_calls += 1
                completed.add(node.id)
                if node.kind == "move":
                    visited.append(str(call.arguments["waypoint"]))
                continue
            if result.code == "safety_rejected":
                status = MissionStatus.ABORTED_SAFE
                break
            recovery_attempts += 1
            repaired = self.policy.recover(node, call, result, recovery_attempts)
            if repaired is None:
                status = MissionStatus.FAILED
                break
            reasoning_steps += 1
            repaired_result = manager.invoke(repaired)
            tool_calls += 1
            if not repaired_result.success:
                status = MissionStatus.FAILED
                break
            successful_calls += 1
            recovery_successes += 1
            completed.add(node.id)
            if node.kind == "move":
                visited.append(str(repaired.arguments["waypoint"]))

        required = sum(1 for node in graph.nodes if node.required and node.kind != "recover")
        if status == MissionStatus.RUNNING:
            status = MissionStatus.SUCCEEDED if len(completed) >= required else MissionStatus.FAILED
        return RunResult(
            mission_id=graph.mission_id,
            method=self.policy.name,
            status=status,
            completed_nodes=sum(1 for node in graph.nodes if node.id in completed and node.required),
            required_nodes=required,
            tool_calls=tool_calls,
            successful_tool_calls=successful_calls,
            recovery_attempts=recovery_attempts,
            recovery_successes=recovery_successes,
            constraint_violations=0,
            reasoning_steps=reasoning_steps,
            distance_flown=env.distance_flown,
            initial_battery=initial_battery,
            final_battery=env.battery_ratio,
            visited_waypoints=tuple(visited),
            fault_present=fault_present,
        )
