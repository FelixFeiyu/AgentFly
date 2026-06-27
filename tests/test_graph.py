from agentfly.domain import MissionGraph, MissionNode
from agentfly.graph import GraphValidator


def node(node_id, kind="inspect", dependencies=(), failure_target="recover", metadata=None):
    return MissionNode(
        id=node_id,
        kind=kind,
        dependencies=tuple(dependencies),
        failure_target=failure_target,
        metadata=metadata or {},
    )


def test_valid_graph_passes_validation():
    graph = MissionGraph(
        mission_id="m1",
        nodes=(
            node("takeoff", "takeoff"),
            node("inspect", dependencies=("takeoff",), metadata={"target": "asset"}),
            node("recover", "recover", failure_target=None),
            node("return", "return", dependencies=("inspect",), metadata={"distance": 10}),
        ),
        reserve_ratio=0.25,
    )
    assert GraphValidator().validate(graph).valid


def test_missing_dependency_is_rejected():
    graph = MissionGraph("m", (node("inspect", dependencies=("missing",)),), 0.25)
    report = GraphValidator().validate(graph)
    assert not report.valid
    assert "missing dependency" in report.errors[0]


def test_cycle_is_rejected():
    graph = MissionGraph(
        "m", (node("a", dependencies=("b",)), node("b", dependencies=("a",))), 0.25
    )
    assert "cycle" in " ".join(GraphValidator().validate(graph).errors)


def test_execution_node_requires_failure_route():
    graph = MissionGraph("m", (node("inspect", failure_target=None),), 0.25)
    assert "failure route" in " ".join(GraphValidator().validate(graph).errors)


def test_takeoff_requires_return_node_and_reserve():
    graph = MissionGraph("m", (node("takeoff", "takeoff"),), 0.1)
    errors = " ".join(GraphValidator().validate(graph).errors)
    assert "return node" in errors
    assert "reserve ratio" in errors


def test_unknown_tool_kind_is_rejected():
    graph = MissionGraph("m", (node("magic", "teleport", failure_target=None),), 0.25)
    assert "unsupported node kind" in " ".join(GraphValidator().validate(graph).errors)


def test_execution_nodes_require_runtime_arguments():
    graph = MissionGraph(
        "m",
        (
            node("move", "move"),
            node("inspect", "inspect"),
            node("return", "return"),
            node("recover", "recover", failure_target=None),
        ),
        0.25,
    )
    errors = " ".join(GraphValidator().validate(graph).errors)
    assert "move requires metadata.waypoint" in errors
    assert "inspect requires metadata.target" in errors
    assert "return requires metadata.distance" in errors
