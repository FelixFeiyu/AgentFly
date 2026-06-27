# AgentFly

[English](README.md) | [简体中文](README.zh-CN.md)

**[Launch the interactive AgentFly Demo](https://felixfeiyu.github.io/AgentFly/)**

AgentFly is a research MVP for constraint-aware agentic task planning and tool use in UAV missions. It turns a mission into a validated mission graph, executes typed tools through a safety gate, and applies local graph-level recovery when an action fails.

The repository includes the research runtime, deterministic evaluation suite, DeepSeek planner adapter, and an interactive browser showcase.

## Implemented

- Constraint-aware Mission Graph dataclasses and validation;
- dependency, cycle, failure-route, return-node, and reserve checks;
- event-driven node state reducer;
- idempotent typed tool execution and deterministic Safety Gate;
- Mock UAV environment with battery and unreachable-waypoint faults;
- AgentFly local repair plus Rule, PDDL, Pure-LLM-style, and ReAct-style baselines;
- deterministic agriculture, powerline, security, and mapping task generation;
- 12 metrics from the research design;
- CSV/JSON/Markdown experiment outputs;
- 45 automated Python tests plus 5 browser-player tests.
- DeepSeek JSON-mode planner with local CMG validation.

## Research Positioning and Contributions

AgentFly targets **task-level agentic planning for long-horizon UAV operations**, rather than proposing a new low-level trajectory optimizer. It connects language-conditioned planning with deterministic execution boundaries that are usually studied separately in embodied agents and UAV planning.

Relative to skill-selection methods such as [SayCan](https://arxiv.org/abs/2204.01691), closed-loop agents such as [Inner Monologue](https://arxiv.org/abs/2207.05608) and [ReAct](https://arxiv.org/abs/2210.03629), executable-plan methods such as [ProgPrompt](https://arxiv.org/abs/2209.11302) and [LLM+P](https://arxiv.org/abs/2304.11477), and UAV-oriented systems such as [UAV-CodeAgents](https://arxiv.org/abs/2505.07236), the current research contributions are:

- **Constraint-aware Mission Graph (CMG):** represents dependencies, risk, failure routes, required nodes, typed tool arguments, return behavior, and battery reserve in one executable graph;
- **Validator-guided semantic repair:** converts missing language constraints into deterministic diagnostics and asks the model to repair only the incomplete grounding;
- **Local graph recovery:** preserves completed work and replaces only the failed action or route segment instead of regenerating and replaying the full mission;
- **Generative/deterministic separation:** the model proposes high-level plans, while graph validation, typed tools, Safety Gate checks, and flight-controller failsafes retain execution authority;
- **Task-level tool orchestration:** combines mapping, waypoint planning, inspection, evidence capture, monitoring, return, and reporting rather than evaluating navigation alone.

The strongest current paper direction is **CMG + validator-guided semantic repair + local graph recovery**. VLM perception, production RAG, measured cloud-edge scheduling, ROS 2/PX4/Gazebo integration, human-in-the-loop studies, multi-UAV coordination, and real-flight validation remain future work. The repository does not claim SOTA performance.

This MVP does **not** yet include VLM adapters, RAG indexing, ROS 2, PX4/Gazebo, cloud-edge deployment, or real-flight results. The browser UI is a deterministic showcase rather than a live flight console. The Pure-LLM and ReAct benchmark entries remain deterministic behavioral baselines; the DeepSeek adapter is currently used for mission graph generation, not the checked-in benchmark table.

## Quick Start

Python 3.9 or newer is sufficient and the runtime has no third-party dependencies.

```bash
python3 -m pytest -q
python3 -m agentfly.cli run \
  --tasks 120 \
  --seeds 13 42 97 \
  --output outputs/mvp
```

## Showcase Demo

The browser Demo plays a deterministic 90-second agriculture inspection mission with a synchronized task graph, UAV route, public Agent action trace, low-confidence recapture, local route recovery, and research-results view. It runs without an API key.

**Online:** [https://felixfeiyu.github.io/AgentFly/](https://felixfeiyu.github.io/AgentFly/)

```bash
python3 -m http.server 8000 --directory demos
```

Open [http://localhost:8000](http://localhost:8000). The public GitHub Pages deployment runs the same static Demo without an API key.

## DeepSeek Mission Planning

Create a new DeepSeek API key and expose it only through the process environment. Never commit it to `.env`, source code, shell scripts, experiment manifests, or logs.

```bash
export DEEPSEEK_API_KEY='your-new-rotated-key'
export DEEPSEEK_MODEL='deepseek-v4-flash'

python3 -m agentfly.cli plan \
  --mission-id agriculture-001 \
  --instruction '巡检 A 区域农田并标记疑似病虫害区域，低置信结果需要补拍' \
  --output outputs/deepseek/agriculture-001.json
```

The command calls `https://api.deepseek.com/chat/completions` in JSON mode. Generated nodes are rejected unless they pass the same dependency, cycle, failure-route, return-node, and battery-reserve checks used by deterministic plans. The default model is `deepseek-v4-flash`; override it with `DEEPSEEK_MODEL`.

## Current MVP Results

The checked-in run contains 120 tasks per seed, 3 seeds, 4 scenarios, 5 methods, and 1,800 method runs.

| Method | TSR | Plan validity | Tool accuracy | Recovery | Route efficiency | Cost |
|---|---:|---:|---:|---:|---:|---:|
| AgentFly | 0.914 | 1.000 | 0.853 | 0.909 | 0.914 | 4.452 |
| Rule | 0.758 | 1.000 | 0.806 | 0.446 | 0.758 | 3.939 |
| PDDL-style | 0.608 | 1.000 | 0.761 | 0.000 | 0.608 | 3.444 |
| Pure-LLM-style | 0.514 | 0.825 | 0.773 | 0.000 | 0.514 | 3.485 |
| ReAct-style | 0.608 | 1.000 | 0.710 | 0.000 | 0.608 | 3.780 |

These results establish that the implementation and evaluation protocol behave as designed under deterministic faults. They are not publication-grade comparisons. Reproduce them with the Quick Start command above.

## Real DeepSeek Planner Results

The `cmg-v4` experiment uses `deepseek-v4-flash`, JSON mode, `temperature=0`, disabled thinking, an empty cache, four-way concurrency, and 50 frozen instructions across agriculture, powerline, security, and mapping.

| Metric | Result |
|---|---:|
| First-pass executable Plan Validity | 1.000 |
| First-pass 95% Wilson CI | [0.929, 1.000] |
| Final Plan Validity | 1.000 |
| Average uncached API latency | 4.265 s |
| Total tokens | 48,437 |
| API response retries | 0 |

The validator rejects missing dependencies, cycles, missing recovery routes, unsafe reserve ratios, unsupported tool kinds, and missing runtime arguments for move/inspect/capture/return nodes. This result does **not** prove complete semantic coverage of every natural-language constraint. Constraint grounding, tool execution, and PX4 flight success require separate experiments.

## Semantic Constraint Repair Results

Structural validity was not sufficient: deterministic rule evaluation found that direct DeepSeek graphs covered only 125/175 annotated constraints. A paired experiment reused each direct graph and sent only the missing constraint diagnostics back to DeepSeek.

| Metric | Direct | Validator-guided repair |
|---|---:|---:|
| Constraint coverage | 0.714 | 0.886 |
| Fully grounded task rate | 0.240 | 0.700 |

Repair reached complete coverage in 60.5% of the 38 initially incomplete tasks. Agriculture improved from 0.872 to 1.000 and security from 0.333 to 0.722. Remaining failures were concentrated in minimum safety distance, communication-loss policy, privacy-zone grounding, and battery-based sortie splitting.

These constraint rules are deterministic research proxies, not expert labels. Publication-grade claims require independent annotation and inter-rater agreement.

Reproduce without reusing cached responses:

```bash
python3 -m agentfly.deepseek_benchmark \
  --tasks 50 \
  --seed 20260627 \
  --workers 4 \
  --max-revisions 2 \
  --cache outputs/deepseek/cache-new-run \
  --output outputs/deepseek/benchmark-new-run
```

Run the paired semantic repair experiment:

```bash
python3 -m agentfly.semantic_experiment \
  --tasks 50 \
  --workers 4 \
  --direct-cache outputs/deepseek/cache-cmg-v4 \
  --repair-cache outputs/deepseek/cache-semantic-new-run \
  --output outputs/deepseek/semantic-repair-new-run
```

## Package Layout

```text
agentfly/
├── agents.py       # Recovery and baseline policies
├── benchmark.py    # Four-scenario task generation and fair runner
├── cli.py          # Reproducible experiment entry point
├── deepseek.py     # DeepSeek HTTPS client and validated planner
├── constraint_eval.py # Deterministic language-constraint grounding checks
├── domain.py       # Mission graph and status types
├── environment.py  # Deterministic UAV environment
├── events.py       # State reducer
├── graph.py        # CMG validator
├── metrics.py      # Twelve evaluation metrics
├── runtime.py      # Shared mission execution loop
├── semantic_experiment.py # Paired direct-vs-repair evaluation
└── tools.py        # Safety gate, typed calls, idempotency
```

## Next Milestone

1. Replace deterministic model styles with provider-neutral LLM/VLM adapters and frozen prompts.
2. Add hybrid RAG plus executable policy rules.
3. Connect the shared tool layer to ROS 2 and PX4 SITL/Gazebo.
4. Implement communication fault injection and cloud-edge profiling.
5. Run paired bootstrap confidence intervals and external embodied/UAV baselines.

## Safety Scope

AgentFly operates at the task-planning layer. A generative model never produces motor commands and cannot bypass the deterministic Safety Gate or flight-controller failsafes. The current code is a simulator research MVP and must not be connected to a real aircraft without a separate safety review.
