import json

from agentfly.deepseek import PlanningResult
from agentfly.deepseek_benchmark import DeepSeekBenchmark, generate_instruction_tasks, wilson_interval
from agentfly.domain import MissionGraph, MissionNode


class FakePlanner:
    PROMPT_VERSION = "test-v1"

    def __init__(self):
        self.calls = 0
        self.client = type("Client", (), {"model": "fake-model"})()

    def plan_detailed(self, instruction, mission_id):
        self.calls += 1
        graph = MissionGraph(
            mission_id,
            (MissionNode("recover", "recover", required=False, failure_target=None),),
            0.25,
        )
        return PlanningResult(graph, self.calls % 2 == 0, self.calls % 2, 10, (), False)


def test_instruction_tasks_are_deterministic_and_cover_four_scenarios():
    tasks = generate_instruction_tasks(50, seed=20260627)
    again = generate_instruction_tasks(50, seed=20260627)
    assert tasks == again
    assert len({task.mission_id for task in tasks}) == 50
    counts = {scenario: sum(task.scenario == scenario for task in tasks) for scenario in {t.scenario for t in tasks}}
    assert counts == {"agriculture": 13, "powerline": 13, "security": 12, "mapping": 12}
    assert all(task.instruction and task.constraints for task in tasks)


def test_benchmark_writes_records_summary_and_manifest(tmp_path):
    planner = FakePlanner()
    summary = DeepSeekBenchmark(planner).run(
        generate_instruction_tasks(4, seed=1), output_dir=tmp_path
    )
    assert planner.calls == 4
    assert summary["task_count"] == 4
    assert summary["final_plan_validity"] == 1.0
    assert summary["first_pass_plan_validity"] == 0.5
    assert (tmp_path / "tasks.json").exists()
    assert len(json.loads((tmp_path / "records.json").read_text())) == 4
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "report.md").exists()


def test_parallel_benchmark_preserves_manifest_order(tmp_path):
    tasks = generate_instruction_tasks(8, seed=9)
    DeepSeekBenchmark(FakePlanner()).run(tasks, output_dir=tmp_path, workers=2)
    records = json.loads((tmp_path / "records.json").read_text())
    assert [row["mission_id"] for row in records] == [task.mission_id for task in tasks]


def test_wilson_interval_handles_perfect_and_near_perfect_rates():
    perfect = wilson_interval(50, 50)
    near = wilson_interval(49, 50)
    assert 0.92 < perfect[0] < 0.94
    assert perfect[1] == 1.0
    assert near[0] < 0.9
    assert near[1] < 1.0
