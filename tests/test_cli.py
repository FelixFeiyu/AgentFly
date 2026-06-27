import json

from agentfly.cli import run_experiment


def test_run_experiment_writes_reproducible_outputs(tmp_path):
    summary = run_experiment(task_count=8, seeds=(13,), output_dir=tmp_path)
    assert (tmp_path / "results.csv").stat().st_size > 0
    assert (tmp_path / "summary.json").stat().st_size > 0
    assert (tmp_path / "report.md").stat().st_size > 0
    saved = json.loads((tmp_path / "summary.json").read_text())
    assert saved == summary
    assert saved["manifest"]["task_count_per_seed"] == 8
    assert set(saved["metrics"]) == {"agentfly", "rule", "pddl", "pure_llm", "react"}
