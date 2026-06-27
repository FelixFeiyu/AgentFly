from agentfly.benchmark import ExperimentRunner, generate_tasks
from agentfly.metrics import aggregate_metrics


def test_task_generator_is_deterministic_and_covers_four_scenarios():
    first = generate_tasks(12, seed=42)
    second = generate_tasks(12, seed=42)
    assert [task.graph.mission_id for task in first] == [task.graph.mission_id for task in second]
    assert {task.scenario for task in first} == {"agriculture", "powerline", "security", "mapping"}


def test_experiment_runs_all_methods_on_identical_tasks():
    tasks = generate_tasks(8, seed=13)
    records = ExperimentRunner().run(tasks, methods=("agentfly", "rule", "pddl", "pure_llm", "react"))
    by_method = {}
    for record in records:
        by_method.setdefault(record.method, set()).add(record.mission_id)
    expected = {task.graph.mission_id for task in tasks}
    assert all(ids == expected for ids in by_method.values())


def test_metrics_expose_required_research_fields():
    records = ExperimentRunner().run(generate_tasks(16, seed=97), methods=("agentfly", "react"))
    metrics = aggregate_metrics(records)
    required = {
        "task_success_rate",
        "plan_validity",
        "subtask_completion_rate",
        "tool_use_accuracy",
        "route_efficiency",
        "constraint_violation_rate",
        "recovery_success_rate",
        "human_intervention_frequency",
        "average_reasoning_steps",
        "execution_cost",
        "report_quality",
        "generalization_performance",
    }
    assert set(metrics["agentfly"]) == required
    assert metrics["agentfly"]["recovery_success_rate"] >= metrics["react"]["recovery_success_rate"]
