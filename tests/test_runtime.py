from agentfly.domain import MissionGraph, MissionNode, NodeStatus
from agentfly.environment import MockUAVEnvironment
from agentfly.events import AgentState, Event, StateReducer
from agentfly.tools import SafetyGate, ToolCall, ToolManager


def test_state_reducer_applies_legal_node_transitions():
    graph = MissionGraph("m", (MissionNode("inspect", "inspect"),), 0.25)
    state = AgentState.create(graph)
    state = StateReducer.apply(state, Event("node_ready", "inspect"))
    state = StateReducer.apply(state, Event("node_started", "inspect"))
    state = StateReducer.apply(state, Event("node_succeeded", "inspect"))
    assert state.node_statuses["inspect"] == NodeStatus.SUCCEEDED
    assert state.event_count == 3


def test_duplicate_tool_call_is_idempotent():
    env = MockUAVEnvironment()
    manager = ToolManager(env, SafetyGate())
    call = ToolCall("takeoff", {"altitude_m": 10}, "same-key")
    first = manager.invoke(call)
    second = manager.invoke(call)
    assert first == second
    assert env.side_effect_counts["takeoff"] == 1


def test_safety_gate_rejects_takeoff_with_insufficient_reserve():
    env = MockUAVEnvironment(battery_ratio=0.2)
    result = ToolManager(env, SafetyGate(reserve_ratio=0.25)).invoke(
        ToolCall("takeoff", {"altitude_m": 10}, "k")
    )
    assert not result.success
    assert result.code == "safety_rejected"


def test_move_returns_structured_unreachable_observation():
    env = MockUAVEnvironment(unreachable_waypoints=("wp-2",))
    env.airborne = True
    result = ToolManager(env, SafetyGate()).invoke(
        ToolCall("move", {"waypoint": "wp-2", "distance": 10.0}, "move-1")
    )
    assert not result.success
    assert result.code == "waypoint_unreachable"
    assert result.data["waypoint"] == "wp-2"


def test_geofence_violation_is_rejected_before_environment_call():
    env = MockUAVEnvironment()
    env.airborne = True
    result = ToolManager(env, SafetyGate()).invoke(
        ToolCall("move", {"waypoint": "forbidden", "distance": 10.0, "in_geofence": False}, "m")
    )
    assert result.code == "safety_rejected"
    assert env.side_effect_counts.get("move", 0) == 0
