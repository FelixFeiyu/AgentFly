import json

from agentfly.constraint_eval import ConstraintEvaluator
from agentfly.deepseek import PlanningResult
from agentfly.deepseek_benchmark import InstructionTask
from agentfly.domain import MissionGraph, MissionNode
from agentfly.semantic_experiment import SemanticRepairBenchmark


class DirectPlanner:
    def plan_detailed(self, instruction, mission_id):
        graph = MissionGraph(
            mission_id,
            (
                MissionNode("move", "move", metadata={"waypoint": "A"}),
                MissionNode("recover", "recover", required=False, failure_target=None),
            ),
            0.25,
        )
        return PlanningResult(graph, True, 0, 10, (), True)


class RepairPlanner:
    def repair_detailed(self, instruction, mission_id, initial_graph, initial_errors, additional_validator, validation_version):
        nodes = initial_graph.nodes + (
            MissionNode("privacy", "report", metadata={"privacy_zone": "west"}),
        )
        graph = MissionGraph(mission_id, nodes, initial_graph.reserve_ratio)
        assert not additional_validator(graph)
        return PlanningResult(graph, False, 1, 8, initial_errors, False)


def test_semantic_benchmark_compares_direct_and_repaired_coverage(tmp_path):
    tasks = [
        InstructionTask("m1", "security", "避开隐私区", ("privacy_zone",), "hard"),
        InstructionTask("m2", "agriculture", "保留返航电量", ("battery_reserve",), "medium"),
    ]
    summary = SemanticRepairBenchmark(
        DirectPlanner(), RepairPlanner(), ConstraintEvaluator()
    ).run(tasks, tmp_path, workers=2)
    assert summary["direct_constraint_coverage"] == 0.5
    assert summary["repaired_constraint_coverage"] == 1.0
    assert summary["repair_task_success_rate"] == 1.0
    records = json.loads((tmp_path / "records.json").read_text())
    assert len(records) == 2
    assert (tmp_path / "report.md").exists()
