from agentfly.constraint_eval import ConstraintEvaluator
from agentfly.deepseek_benchmark import InstructionTask
from agentfly.domain import MissionGraph, MissionNode


def graph(*nodes, reserve=0.25):
    return MissionGraph("m", tuple(nodes), reserve)


def task(*constraints, instruction="测试任务"):
    return InstructionTask("m", "test", instruction, constraints, "hard")


def test_evaluator_detects_battery_and_geofence_grounding():
    mission = graph(
        MissionNode("move", "move", metadata={"waypoint": "A", "avoid_zone": "west"}),
        reserve=0.3,
    )
    result = ConstraintEvaluator().evaluate(task("battery_reserve", "geofence"), mission)
    assert result.coverage == 1.0
    assert not result.missing


def test_evaluator_requires_low_confidence_recapture_branch():
    mission = graph(
        MissionNode("inspect", "inspect", metadata={"target": "crop", "confidence_threshold": 0.65}),
        MissionNode("confirm", "human_confirm", metadata={"condition": "confidence < 0.65"}),
        MissionNode("recapture", "capture", metadata={"target": "crop"}),
    )
    result = ConstraintEvaluator().evaluate(task("low_confidence_recapture"), mission)
    assert result.coverage == 1.0


def test_evaluator_reports_missing_privacy_and_communication_policy():
    mission = graph(
        MissionNode("return", "return", metadata={"distance": 20}),
        MissionNode("recover", "recover", required=False, failure_target=None),
    )
    result = ConstraintEvaluator().evaluate(task("privacy_zone", "communication_loss"), mission)
    assert result.coverage == 0.0
    assert {item.constraint for item in result.missing} == {"privacy_zone", "communication_loss"}


def test_evaluator_checks_mapping_overlap_quality_and_battery_split():
    mission = graph(
        MissionNode(
            "capture",
            "capture",
            metadata={"target": "map", "forward_overlap": 0.8, "side_overlap": 0.7},
        ),
        MissionNode("coverage", "report", metadata={"type": "coverage_check"}),
        MissionNode("quality", "report", metadata={"type": "blur_check"}),
        MissionNode("split", "recover", required=False, failure_target=None, metadata={"condition": "battery low", "strategy": "split_sortie"}),
    )
    result = ConstraintEvaluator().evaluate(
        task("coverage", "image_overlap", "quality_check", "battery_split"), mission
    )
    assert result.coverage == 1.0
