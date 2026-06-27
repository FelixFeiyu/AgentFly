import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .benchmark import ExperimentRunner, generate_tasks
from .deepseek import DeepSeekClient, DeepSeekPlanner
from .metrics import aggregate_metrics


METHODS = ("agentfly", "rule", "pddl", "pure_llm", "react")


def plan_with_deepseek(
    instruction: str,
    mission_id: str,
    output: Path,
    planner: Optional[Any] = None,
) -> Dict[str, object]:
    planner = planner or DeepSeekPlanner(DeepSeekClient.from_env())
    graph = planner.plan(instruction, mission_id)
    data = {
        "mission_id": graph.mission_id,
        "version": graph.version,
        "reserve_ratio": graph.reserve_ratio,
        "nodes": [
            {
                "id": node.id,
                "kind": node.kind,
                "dependencies": list(node.dependencies),
                "failure_target": node.failure_target,
                "risk": node.risk,
                "required": node.required,
                "metadata": node.metadata,
            }
            for node in graph.nodes
        ],
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return data


def run_experiment(task_count: int, seeds: Sequence[int], output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_records = []
    runner = ExperimentRunner()
    for seed in seeds:
        all_records.extend(runner.run(generate_tasks(task_count, seed), METHODS))
    metrics = aggregate_metrics(all_records)
    summary = {
        "manifest": {
            "task_count_per_seed": task_count,
            "seeds": list(seeds),
            "methods": list(METHODS),
            "total_method_runs": len(all_records),
            "benchmark": "deterministic_mock_mvp",
        },
        "metrics": metrics,
    }
    with (output_dir / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "mission_id", "scenario", "method", "ood", "plan_valid", "status",
                "completed_nodes", "required_nodes", "tool_calls", "recovery_attempts",
                "recovery_successes", "distance_flown", "reasoning_steps",
            ),
        )
        writer.writeheader()
        for row in all_records:
            result = row.result
            writer.writerow(
                {
                    "mission_id": row.mission_id,
                    "scenario": row.scenario,
                    "method": row.method,
                    "ood": row.ood,
                    "plan_valid": row.plan_valid,
                    "status": result.status.value if result else "invalid_plan",
                    "completed_nodes": result.completed_nodes if result else 0,
                    "required_nodes": result.required_nodes if result else 0,
                    "tool_calls": result.tool_calls if result else 0,
                    "recovery_attempts": result.recovery_attempts if result else 0,
                    "recovery_successes": result.recovery_successes if result else 0,
                    "distance_flown": result.distance_flown if result else 0,
                    "reasoning_steps": result.reasoning_steps if result else 0,
                }
            )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (output_dir / "report.md").write_text(_render_report(summary))
    return summary


def _render_report(summary: Dict[str, object]) -> str:
    metrics = summary["metrics"]
    lines = [
        "# AgentFly MVP Experiment Report",
        "",
        "This is a deterministic MockEnv systems experiment, not a PX4/Gazebo or real-LLM SOTA result.",
        "",
        "| Method | TSR | Plan validity | Tool accuracy | Recovery | Route efficiency | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        row = metrics[method]
        lines.append(
            "| %s | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |"
            % (
                method,
                row["task_success_rate"],
                row["plan_validity"],
                row["tool_use_accuracy"],
                row["recovery_success_rate"],
                row["route_efficiency"],
                row["execution_cost"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The MVP validates the software protocol and expected recovery behavior. Formal research claims require real model adapters, PX4/Gazebo runs, confidence intervals, and external baselines.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Tuple[str, ...] = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic AgentFly MVP experiments")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--tasks", type=int, default=120)
    run_parser.add_argument("--seeds", type=int, nargs="+", default=[13, 42, 97])
    run_parser.add_argument("--output", type=Path, default=Path("outputs/mvp"))
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--instruction", required=True)
    plan_parser.add_argument("--mission-id", default="deepseek-mission")
    plan_parser.add_argument("--output", type=Path, default=Path("outputs/deepseek/mission.json"))
    args = parser.parse_args(argv)
    if args.command == "run":
        run_experiment(args.tasks, args.seeds, args.output)
    elif args.command == "plan":
        plan_with_deepseek(args.instruction, args.mission_id, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
