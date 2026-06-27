import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Sequence

from .constraint_eval import ConstraintEvaluator
from .deepseek import DeepSeekClient, DeepSeekPlanner
from .deepseek_benchmark import InstructionTask, generate_instruction_tasks


class SemanticRepairBenchmark:
    def __init__(
        self,
        direct_planner: Any,
        repair_planner: Any,
        evaluator: ConstraintEvaluator,
    ):
        self.direct_planner = direct_planner
        self.repair_planner = repair_planner
        self.evaluator = evaluator

    def run(
        self,
        tasks: Sequence[InstructionTask],
        output_dir: Path,
        workers: int = 1,
    ) -> Dict[str, Any]:
        if workers < 1:
            raise ValueError("workers must be at least 1")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(executor.map(self._run_one, tasks))
        summary = self._summarize(records)
        (output_dir / "records.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        )
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        (output_dir / "report.md").write_text(self._render_report(summary))
        return summary

    def _run_one(self, task: InstructionTask) -> Dict[str, Any]:
        direct = self.direct_planner.plan_detailed(task.instruction, task.mission_id)
        if direct.graph is None:
            raise RuntimeError("direct graph missing for %s" % task.mission_id)
        before = self.evaluator.evaluate(task, direct.graph)
        missing_before = [item.constraint for item in before.missing]
        final_graph = direct.graph
        revisions = 0
        tokens = 0
        latency = 0.0
        cache_hit = True
        repair_error = None
        if before.missing:
            initial_errors = tuple(
                "%s: %s" % (item.constraint, item.reason) for item in before.missing
            )

            def validate(graph):
                result = self.evaluator.evaluate(task, graph)
                return tuple(
                    "%s: %s" % (item.constraint, item.reason) for item in result.missing
                )

            started = time.perf_counter()
            try:
                repaired = self.repair_planner.repair_detailed(
                    task.instruction,
                    task.mission_id,
                    direct.graph,
                    initial_errors,
                    validate,
                    self.evaluator.VERSION,
                )
                latency = time.perf_counter() - started
                revisions = repaired.revisions
                tokens = repaired.total_tokens
                cache_hit = repaired.cache_hit
                if repaired.graph is not None:
                    final_graph = repaired.graph
            except Exception as exc:
                latency = time.perf_counter() - started
                repair_error = "%s: %s" % (type(exc).__name__, str(exc)[:500])
        after = self.evaluator.evaluate(task, final_graph)
        return {
            "mission_id": task.mission_id,
            "scenario": task.scenario,
            "difficulty": task.difficulty,
            "constraints": list(task.constraints),
            "constraint_count": before.total,
            "direct_satisfied": before.satisfied,
            "direct_coverage": before.coverage,
            "direct_missing": missing_before,
            "repaired_satisfied": after.satisfied,
            "repaired_coverage": after.coverage,
            "repaired_missing": [item.constraint for item in after.missing],
            "repair_attempted": bool(before.missing),
            "repair_success": bool(before.missing) and not after.missing,
            "revisions": revisions,
            "repair_tokens": tokens,
            "repair_latency_s": round(latency, 6),
            "repair_cache_hit": cache_hit,
            "repair_error": repair_error,
        }

    @staticmethod
    def _summarize(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        total_constraints = sum(row["constraint_count"] for row in records)
        attempted = [row for row in records if row["repair_attempted"]]
        by_scenario = defaultdict(lambda: {"total": 0, "direct": 0, "repaired": 0})
        by_constraint = defaultdict(lambda: {"total": 0, "direct": 0, "repaired": 0})
        for row in records:
            bucket = by_scenario[row["scenario"]]
            bucket["total"] += row["constraint_count"]
            bucket["direct"] += row["direct_satisfied"]
            bucket["repaired"] += row["repaired_satisfied"]
            direct_missing = set(row["direct_missing"])
            repaired_missing = set(row["repaired_missing"])
            for constraint in row["constraints"]:
                rule = by_constraint[constraint]
                rule["total"] += 1
                rule["direct"] += constraint not in direct_missing
                rule["repaired"] += constraint not in repaired_missing
        scenario_metrics = {
            name: {
                "direct_coverage": value["direct"] / value["total"],
                "repaired_coverage": value["repaired"] / value["total"],
                "constraint_count": value["total"],
            }
            for name, value in by_scenario.items()
        }
        return {
            "task_count": len(records),
            "constraint_count": total_constraints,
            "direct_constraint_coverage": sum(row["direct_satisfied"] for row in records)
            / total_constraints,
            "repaired_constraint_coverage": sum(row["repaired_satisfied"] for row in records)
            / total_constraints,
            "direct_fully_grounded_task_rate": mean(
                1.0 if row["direct_coverage"] == 1.0 else 0.0 for row in records
            ),
            "repaired_fully_grounded_task_rate": mean(
                1.0 if row["repaired_coverage"] == 1.0 else 0.0 for row in records
            ),
            "repair_task_count": len(attempted),
            "repair_task_success_rate": mean(
                1.0 if row["repair_success"] else 0.0 for row in attempted
            )
            if attempted
            else 0.0,
            "repair_total_tokens": sum(row["repair_tokens"] for row in attempted),
            "repair_average_latency_s": mean(row["repair_latency_s"] for row in attempted)
            if attempted
            else 0.0,
            "repair_api_errors": sum(bool(row["repair_error"]) for row in attempted),
            "scenario_metrics": scenario_metrics,
            "constraint_metrics": {
                name: {
                    "direct_coverage": value["direct"] / value["total"],
                    "repaired_coverage": value["repaired"] / value["total"],
                    "count": value["total"],
                }
                for name, value in by_constraint.items()
            },
        }

    @staticmethod
    def _render_report(summary: Dict[str, Any]) -> str:
        lines = [
            "# Semantic Constraint Repair Experiment",
            "",
            "- Tasks: %d" % summary["task_count"],
            "- Annotated constraints: %d" % summary["constraint_count"],
            "- Direct constraint coverage: %.3f" % summary["direct_constraint_coverage"],
            "- Repaired constraint coverage: %.3f" % summary["repaired_constraint_coverage"],
            "- Direct fully-grounded task rate: %.3f"
            % summary["direct_fully_grounded_task_rate"],
            "- Repaired fully-grounded task rate: %.3f"
            % summary["repaired_fully_grounded_task_rate"],
            "- Repair task success rate: %.3f" % summary["repair_task_success_rate"],
            "- Repair total tokens: %d" % summary["repair_total_tokens"],
            "- Repair average latency: %.3fs" % summary["repair_average_latency_s"],
            "- Repair API errors: %d" % summary["repair_api_errors"],
            "",
            "| Scenario | Direct | Repaired | Constraints |",
            "|---|---:|---:|---:|",
        ]
        for scenario, metrics in sorted(summary["scenario_metrics"].items()):
            lines.append(
                "| %s | %.3f | %.3f | %d |"
                % (
                    scenario,
                    metrics["direct_coverage"],
                    metrics["repaired_coverage"],
                    metrics["constraint_count"],
                )
            )
        lines.extend(
            [
                "",
                "| Constraint | Direct | Repaired | Count |",
                "|---|---:|---:|---:|",
            ]
        )
        for constraint, metrics in sorted(summary["constraint_metrics"].items()):
            lines.append(
                "| %s | %.3f | %.3f | %d |"
                % (
                    constraint,
                    metrics["direct_coverage"],
                    metrics["repaired_coverage"],
                    metrics["count"],
                )
            )
        lines.extend(
            [
                "",
                "Constraint rules are deterministic proxies and must be validated against expert annotations before publication.",
                "",
            ]
        )
        return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paired DeepSeek semantic repair experiment")
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260627)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--direct-cache", type=Path, default=Path("outputs/deepseek/cache-cmg-v4"))
    parser.add_argument("--repair-cache", type=Path, default=Path("outputs/deepseek/cache-semantic-v1"))
    parser.add_argument("--output", type=Path, default=Path("outputs/deepseek/semantic-repair-50"))
    args = parser.parse_args()
    client = DeepSeekClient.from_env()
    direct = DeepSeekPlanner(client, cache_dir=args.direct_cache)
    repair = DeepSeekPlanner(client, max_revisions=2, cache_dir=args.repair_cache)
    SemanticRepairBenchmark(direct, repair, ConstraintEvaluator()).run(
        generate_instruction_tasks(args.tasks, args.seed), args.output, args.workers
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
