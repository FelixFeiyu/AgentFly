import argparse
import json
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence

from .deepseek import DeepSeekClient, DeepSeekPlanner


SCENARIOS = ("agriculture", "powerline", "security", "mapping")


@dataclass(frozen=True)
class InstructionTask:
    mission_id: str
    scenario: str
    instruction: str
    constraints: Sequence[str]
    difficulty: str


def generate_instruction_tasks(count: int, seed: int = 20260627) -> List[InstructionTask]:
    rng = random.Random(seed)
    tasks = []
    for index in range(count):
        scenario = SCENARIOS[index % 4]
        area = chr(ord("A") + index % 8)
        distance = rng.choice((8, 12, 16, 20))
        if scenario == "agriculture":
            instruction = (
                "巡检%s区农田，识别疑似病虫害区域；检测置信度低于0.65时补拍，"
                "避开西侧禁飞区，并保留25%%返航电量。" % area
            )
            constraints = ("geofence", "battery_reserve", "low_confidence_recapture")
        elif scenario == "powerline":
            instruction = (
                "按顺序检查%d号输电线路的%d座杆塔和绝缘子，保持至少%d米安全距离；"
                "发现高风险缺陷时请求人工确认，航点不可达时规划替代观察点。"
                % (index % 5 + 1, index % 4 + 3, distance)
            )
            constraints = ("asset_order", "safety_distance", "human_confirmation", "unreachable_recovery")
        elif scenario == "security":
            instruction = (
                "围绕%s栋建筑完成两圈安防巡逻，检查人员、车辆和烟火异常；"
                "不得进入隐私区域，低置信告警需人工确认，通信中断时安全返航。" % area
            )
            constraints = ("privacy_zone", "human_confirmation", "communication_loss")
        else:
            instruction = (
                "对%s区进行正射测绘，地面分辨率%d厘米，前向重叠80%%、旁向重叠70%%；"
                "检查覆盖率和图像模糊，缺失区域需要补采，电量不足时分架次执行。"
                % (area, rng.choice((2, 3, 5)))
            )
            constraints = ("coverage", "image_overlap", "quality_check", "battery_split")
        difficulty = ("medium", "hard", "long_horizon")[index % 3]
        tasks.append(
            InstructionTask(
                mission_id="ds-%s-%03d" % (scenario, index),
                scenario=scenario,
                instruction=instruction,
                constraints=constraints,
                difficulty=difficulty,
            )
        )
    return tasks


class DeepSeekBenchmark:
    def __init__(self, planner: DeepSeekPlanner):
        self.planner = planner

    def run(
        self, tasks: Sequence[InstructionTask], output_dir: Path, workers: int = 1
    ) -> Dict[str, Any]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if workers < 1:
            raise ValueError("workers must be at least 1")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(executor.map(self._run_one, tasks))
        invalid_first = [row for row in records if not row["first_pass_valid"]]
        uncached = [row for row in records if not row["cache_hit"]]
        first_successes = sum(row["first_pass_valid"] for row in records)
        final_successes = sum(row["final_valid"] for row in records)
        summary = {
            "task_count": len(records),
            "first_pass_plan_validity": _rate(row["first_pass_valid"] for row in records),
            "final_plan_validity": _rate(row["final_valid"] for row in records),
            "first_pass_plan_validity_95ci": list(wilson_interval(first_successes, len(records))),
            "final_plan_validity_95ci": list(wilson_interval(final_successes, len(records))),
            "repair_success_rate": _rate(row["final_valid"] for row in invalid_first),
            "average_revisions": _average(row["revisions"] for row in records),
            "average_tokens": _average(row["total_tokens"] for row in records),
            "total_tokens": sum(row["total_tokens"] for row in records),
            "average_latency_s": _average(row["latency_s"] for row in records),
            "average_uncached_latency_s": _average(row["latency_s"] for row in uncached),
            "cache_hit_rate": _rate(row["cache_hit"] for row in records),
            "api_response_retries": sum(row["api_response_retries"] for row in records),
            "model": self.planner.client.model,
            "prompt_version": self.planner.PROMPT_VERSION,
        }
        (output_dir / "tasks.json").write_text(
            json.dumps([asdict(task) for task in tasks], ensure_ascii=False, indent=2) + "\n"
        )
        (output_dir / "records.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        )
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        (output_dir / "report.md").write_text(_render_report(summary, records))
        return summary

    def _run_one(self, task: InstructionTask) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = self.planner.plan_detailed(task.instruction, task.mission_id)
            return {
                "mission_id": task.mission_id,
                "scenario": task.scenario,
                "difficulty": task.difficulty,
                "first_pass_valid": result.first_pass_valid,
                "final_valid": result.graph is not None,
                "revisions": result.revisions,
                "total_tokens": result.total_tokens,
                "latency_s": round(time.perf_counter() - started, 6),
                "cache_hit": result.cache_hit,
                "api_response_retries": result.api_response_retries,
                "validation_errors": list(result.validation_errors),
                "node_count": len(result.graph.nodes) if result.graph else 0,
                "api_error": None,
            }
        except Exception as exc:
            return {
                "mission_id": task.mission_id,
                "scenario": task.scenario,
                "difficulty": task.difficulty,
                "first_pass_valid": False,
                "final_valid": False,
                "revisions": 0,
                "total_tokens": 0,
                "latency_s": round(time.perf_counter() - started, 6),
                "cache_hit": False,
                "api_response_retries": 0,
                "validation_errors": [],
                "node_count": 0,
                "api_error": "%s: %s" % (type(exc).__name__, str(exc)[:500]),
            }


def _rate(values: Any) -> float:
    values = list(values)
    return mean(1.0 if value else 0.0 for value in values) if values else 0.0


def _average(values: Any) -> float:
    values = list(values)
    return mean(values) if values else 0.0


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Sequence[float]:
    if total == 0:
        return (0.0, 0.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def _render_report(summary: Dict[str, Any], records: Sequence[Dict[str, Any]]) -> str:
    failures = [row for row in records if not row["final_valid"]]
    return "\n".join(
        [
            "# DeepSeek Planner Benchmark",
            "",
            "- Model: `%s`" % summary["model"],
            "- Tasks: %d" % summary["task_count"],
            "- First-pass Plan Validity: %.3f" % summary["first_pass_plan_validity"],
            "- First-pass 95%% CI: [%.3f, %.3f]"
            % tuple(summary["first_pass_plan_validity_95ci"]),
            "- Final Plan Validity: %.3f" % summary["final_plan_validity"],
            "- Final 95%% CI: [%.3f, %.3f]" % tuple(summary["final_plan_validity_95ci"]),
            "- Repair Success Rate: %.3f" % summary["repair_success_rate"],
            "- Average Revisions: %.3f" % summary["average_revisions"],
            "- Total Tokens: %d" % summary["total_tokens"],
            "- Average Uncached API Latency: %.3fs" % summary["average_uncached_latency_s"],
            "- Cache Hit Rate: %.3f" % summary["cache_hit_rate"],
            "- API Response Retries: %d" % summary["api_response_retries"],
            "- Final Failures: %d" % len(failures),
            "",
            "This evaluates language-to-CMG generation and validator-guided repair. It does not evaluate PX4 flight execution.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real DeepSeek CMG benchmark")
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260627)
    parser.add_argument("--output", type=Path, default=Path("outputs/deepseek/benchmark-50"))
    parser.add_argument("--cache", type=Path, default=Path("outputs/deepseek/cache"))
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    planner = DeepSeekPlanner(
        DeepSeekClient.from_env(), max_revisions=args.max_revisions, cache_dir=args.cache
    )
    DeepSeekBenchmark(planner).run(
        generate_instruction_tasks(args.tasks, args.seed), args.output, workers=args.workers
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
