from agentfly.agents import AgentFlyPolicy, NoRecoveryPolicy
from agentfly.domain import MissionGraph, MissionNode, MissionStatus
from agentfly.environment import MockUAVEnvironment
from agentfly.runtime import MissionRuntime


def mission_graph():
    return MissionGraph(
        "powerline-1",
        (
            MissionNode("takeoff", "takeoff", metadata={"altitude_m": 12}),
            MissionNode(
                "move-wp-2",
                "move",
                dependencies=("takeoff",),
                metadata={"waypoint": "wp-2", "alternate": "wp-2-alt", "distance": 10.0},
            ),
            MissionNode(
                "inspect-tower",
                "inspect",
                dependencies=("move-wp-2",),
                metadata={"target": "tower-3"},
            ),
            MissionNode("recover", "recover", required=False, failure_target=None),
            MissionNode("return", "return", dependencies=("inspect-tower",), metadata={"distance": 10.0}),
        ),
        0.25,
    )


def test_agentfly_repairs_unreachable_waypoint_and_preserves_progress():
    env = MockUAVEnvironment(unreachable_waypoints=("wp-2",))
    result = MissionRuntime(AgentFlyPolicy()).run(mission_graph(), env)
    assert result.status == MissionStatus.SUCCEEDED
    assert result.recovery_attempts == 1
    assert result.completed_nodes >= 4
    assert env.side_effect_counts["takeoff"] == 1
    assert "wp-2-alt" in result.visited_waypoints


def test_no_recovery_policy_fails_same_recoverable_mission():
    env = MockUAVEnvironment(unreachable_waypoints=("wp-2",))
    result = MissionRuntime(NoRecoveryPolicy()).run(mission_graph(), env)
    assert result.status == MissionStatus.FAILED
    assert result.completed_nodes == 1


def test_agentfly_safely_aborts_when_return_reserve_is_insufficient():
    env = MockUAVEnvironment(battery_ratio=0.24)
    result = MissionRuntime(AgentFlyPolicy()).run(mission_graph(), env)
    assert result.status == MissionStatus.ABORTED_SAFE
    assert result.constraint_violations == 0
