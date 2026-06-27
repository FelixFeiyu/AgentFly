from collections import defaultdict
from statistics import mean
from typing import Dict, Iterable, List

from .benchmark import ExperimentRecord
from .domain import MissionStatus


METRIC_NAMES = (
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
)


def _safe_mean(values: List[float]) -> float:
    return mean(values) if values else 0.0


def aggregate_metrics(records: Iterable[ExperimentRecord]) -> Dict[str, Dict[str, float]]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record.method].append(record)
    output = {}
    for method, rows in grouped.items():
        valid_results = [row.result for row in rows if row.result is not None]
        successes = [
            1.0 if row.result and row.result.status == MissionStatus.SUCCEEDED else 0.0 for row in rows
        ]
        completion = [
            (row.result.completed_nodes / row.result.required_nodes) if row.result else 0.0 for row in rows
        ]
        tool_accuracy = [
            (result.successful_tool_calls / result.tool_calls) if result.tool_calls else 0.0
            for result in valid_results
        ]
        route_efficiency = [
            min(1.0, row.optimal_distance / row.result.distance_flown)
            if row.result and row.result.distance_flown > 0
            else 0.0
            for row in rows
        ]
        fault_runs = [row.result for row in rows if row.result and row.result.fault_present]
        recovery = [
            (result.recovery_successes / result.recovery_attempts) if result.recovery_attempts else 0.0
            for result in fault_runs
        ]
        ood = [
            1.0 if row.result and row.result.status == MissionStatus.SUCCEEDED else 0.0
            for row in rows
            if row.ood
        ]
        output[method] = {
            "task_success_rate": _safe_mean(successes),
            "plan_validity": _safe_mean([1.0 if row.plan_valid else 0.0 for row in rows]),
            "subtask_completion_rate": _safe_mean(completion),
            "tool_use_accuracy": _safe_mean(tool_accuracy),
            "route_efficiency": _safe_mean(route_efficiency),
            "constraint_violation_rate": _safe_mean([float(r.constraint_violations) for r in valid_results]),
            "recovery_success_rate": _safe_mean(recovery),
            "human_intervention_frequency": 0.0,
            "average_reasoning_steps": _safe_mean([float(r.reasoning_steps) for r in valid_results]),
            "execution_cost": _safe_mean([r.tool_calls + 0.1 * r.reasoning_steps for r in valid_results]),
            "report_quality": _safe_mean(completion),
            "generalization_performance": _safe_mean(ood),
        }
    return output
