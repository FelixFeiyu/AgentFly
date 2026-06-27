import random
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .agents import AgentFlyPolicy, PDDLPolicy, PureLLMPolicy, ReActPolicy, RulePolicy
from .domain import MissionGraph, MissionNode
from .environment import MockUAVEnvironment
from .runtime import MissionRuntime, RunResult


SCENARIOS = ("agriculture", "powerline", "security", "mapping")


@dataclass(frozen=True)
class TaskCase:
    graph: MissionGraph
    scenario: str
    unreachable_waypoints: Tuple[str, ...]
    battery_ratio: float
    optimal_distance: float
    ood: bool
    pure_llm_plan_valid: bool


@dataclass(frozen=True)
class ExperimentRecord:
    mission_id: str
    scenario: str
    method: str
    ood: bool
    plan_valid: bool
    optimal_distance: float
    result: Optional[RunResult]


def generate_tasks(count: int, seed: int) -> List[TaskCase]:
    rng = random.Random(seed)
    tasks = []
    for index in range(count):
        scenario = SCENARIOS[index % len(SCENARIOS)]
        mission_id = "%s-%d-%03d" % (scenario, seed, index)
        waypoint = "wp-%03d" % index
        fault = rng.random() < 0.35
        low_battery = rng.random() < 0.08
        distance = float(rng.randint(8, 24))
        known_rule = rng.random() < 0.5
        graph = MissionGraph(
            mission_id,
            (
                MissionNode("takeoff", "takeoff", metadata={"altitude_m": 12}),
                MissionNode(
                    "move",
                    "move",
                    dependencies=("takeoff",),
                    metadata={
                        "waypoint": waypoint,
                        "alternate": waypoint + "-alt",
                        "distance": distance,
                        "known_rule": known_rule,
                    },
                ),
                MissionNode(
                    "inspect",
                    "inspect",
                    dependencies=("move",),
                    metadata={"target": "%s-target-%03d" % (scenario, index)},
                ),
                MissionNode("recover", "recover", required=False, failure_target=None),
                MissionNode("return", "return", dependencies=("inspect",), metadata={"distance": distance}),
            ),
            reserve_ratio=0.25,
        )
        tasks.append(
            TaskCase(
                graph=graph,
                scenario=scenario,
                unreachable_waypoints=(waypoint,) if fault else (),
                battery_ratio=0.24 if low_battery else 1.0,
                optimal_distance=distance * 2.0,
                ood=index % 4 == 3,
                pure_llm_plan_valid=rng.random() >= 0.15,
            )
        )
    return tasks


class ExperimentRunner:
    POLICIES = {
        "agentfly": AgentFlyPolicy,
        "rule": RulePolicy,
        "pddl": PDDLPolicy,
        "pure_llm": PureLLMPolicy,
        "react": ReActPolicy,
    }

    def run(self, tasks: Iterable[TaskCase], methods: Sequence[str]) -> List[ExperimentRecord]:
        records: List[ExperimentRecord] = []
        for task in tasks:
            for method in methods:
                if method not in self.POLICIES:
                    raise ValueError("unknown method %s" % method)
                plan_valid = not (method == "pure_llm" and not task.pure_llm_plan_valid)
                result = None
                if plan_valid:
                    env = MockUAVEnvironment(
                        battery_ratio=task.battery_ratio,
                        unreachable_waypoints=task.unreachable_waypoints,
                    )
                    result = MissionRuntime(self.POLICIES[method]()).run(task.graph, env)
                records.append(
                    ExperimentRecord(
                        task.graph.mission_id,
                        task.scenario,
                        method,
                        task.ood,
                        plan_valid,
                        task.optimal_distance,
                        result,
                    )
                )
        return records
