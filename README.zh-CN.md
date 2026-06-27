# AgentFly

[English](README.md) | [简体中文](README.zh-CN.md)

**[在线体验 AgentFly 交互式演示](https://felixfeiyu.github.io/AgentFly/)**

AgentFly 是一个面向无人机长程作业的 Agentic AI 研究原型。系统可以理解自然语言任务，将复杂作业拆解为带依赖关系和安全约束的任务图，通过类型化工具完成航线规划、视觉巡检、状态监测和报告生成，并在航点不可达等异常发生后执行局部任务修复。

这个仓库包含任务规划与执行框架、确定性模拟评测、DeepSeek 规划器适配器，以及一个无需 API Key 即可访问的浏览器演示。

## 项目解决什么问题

传统无人机作业通常依赖人工规划航线和固定任务流程。当任务包含自然语言指令、多阶段作业、安全规则、视觉反馈和动态异常时，静态流程很难同时处理任务理解、工具协同和在线恢复。

AgentFly 将大模型放在高层任务规划位置，而不是让模型直接控制电机：

```text
自然语言指令
    ↓
约束感知任务图（CMG）
    ↓
Planner / Reasoner / Executor
    ↓
地图、航点、视觉、状态和报告工具
    ↓
Safety Gate 与模拟飞行环境
    ↓
执行反馈、局部重规划和任务报告
```

生成式模型负责理解和规划，确定性验证器与 Safety Gate 负责检查依赖关系、故障路由、电量储备和工具参数。模型不会生成飞控指令，也不能绕过安全检查。

## 核心能力

- **约束感知任务图**：使用结构化数据描述子任务、依赖关系、风险等级、故障分支和返航节点；
- **分层 Agent 执行**：通过 Planner、Reasoner 和 Executor 分离高层规划、状态判断与工具执行；
- **类型化工具调用**：统一封装地图、航点、视觉、电量、返航和报告工具，并提供幂等调用机制；
- **确定性安全检查**：在执行前验证任务图，在工具调用前检查安全约束和最低返航电量；
- **异常恢复**：遇到航点不可达或视觉置信度不足时，保留已完成任务，只修复受影响的局部任务图；
- **DeepSeek 规划接入**：通过 JSON Mode 生成任务图，并使用本地验证器拒绝结构无效或缺少运行参数的计划；
- **可复现实验**：覆盖农业巡检、电力巡线、安防巡逻和区域测绘，并提供五类方法的统一评测；
- **交互式演示**：以 90 秒固定剧情展示任务图、航线动画、Agent 行动日志、视觉补拍和异常恢复。

当前实现包含 45 个 Python 自动化测试和 5 个浏览器播放器测试。

## 研究定位与创新点

AgentFly 研究的是**长程无人机作业中的任务级 Agentic Planning**，不是提出新的底层航迹优化算法。它试图连接两个通常分开研究的方向：一边是具身 Agent 的语言理解、推理和工具调用，另一边是无人机系统的安全约束、任务执行和异常恢复。

与 [SayCan](https://arxiv.org/abs/2204.01691) 的技能选择、[Inner Monologue](https://arxiv.org/abs/2207.05608) 和 [ReAct](https://arxiv.org/abs/2210.03629) 的反馈闭环、[ProgPrompt](https://arxiv.org/abs/2209.11302) 和 [LLM+P](https://arxiv.org/abs/2304.11477) 的可执行计划，以及 [UAV-CodeAgents](https://arxiv.org/abs/2505.07236) 的无人机多 Agent 规划相比，AgentFly 当前可以主张的创新主要有五点：

- **约束感知任务图（CMG）**：用同一张可执行任务图表示依赖关系、风险、故障路由、必须完成节点、工具参数、返航行为和电量储备；
- **验证器引导的语义约束修复**：把未落实的自然语言约束转成确定性诊断，只让模型修复缺失部分，而不是重新生成整个计划；
- **局部任务图修复**：保留已经完成的任务，只替换失败动作或失效航段，避免长程任务从头执行；
- **生成式规划与确定性执行解耦**：模型提出高层计划，任务图验证、类型化工具、Safety Gate 和飞控失效保护保留最终执行权；
- **任务级多工具编排**：统一组织地图、航点、视觉巡检、证据补拍、状态监测、安全返航和报告生成，不把任务简化为单一导航问题。

当前最适合发展的论文主线是 **CMG + 验证器引导的语义修复 + 局部任务图恢复**。完整 VLM 感知、生产级 RAG、真实云边调度、ROS 2/PX4/Gazebo、人机协同、多无人机和实飞验证仍属于后续工作。项目目前不声称达到或超过 SOTA。

## 快速开始

运行环境要求 Python 3.9 或更高版本，核心运行时不依赖第三方库。

```bash
python3 -m pytest -q

python3 -m agentfly.cli run \
  --tasks 120 \
  --seeds 13 42 97 \
  --output outputs/mvp
```

上述命令会生成确定性 MockEnv 实验结果，包括 CSV 明细、JSON 汇总和 Markdown 报告。

## 在线演示

直接访问：**[https://felixfeiyu.github.io/AgentFly/](https://felixfeiyu.github.io/AgentFly/)**

演示以农业巡检为主线，依次展示：

1. 理解自然语言任务并检索安全规则；
2. 生成和验证任务图；
3. 按规划航线执行区域巡检；
4. 发现低置信度视觉结果后降低高度补拍；
5. 航点不可达时由 Safety Gate 阻止继续执行；
6. 替换失效航段并保留已完成任务；
7. 安全返航、生成任务报告并展示实验结果。

Demo 使用固定剧情数据，不会调用 DeepSeek API，也不会读取本地 `.env`。如需在本地运行：

```bash
python3 -m http.server 8000 --directory demos
```

然后打开 [http://localhost:8000](http://localhost:8000)。

## 使用 DeepSeek 生成任务图

先在环境变量中配置新创建的 API Key。不要将真实密钥写入源码、脚本、实验配置或 Git 历史。

```bash
export DEEPSEEK_API_KEY='your-new-rotated-key'
export DEEPSEEK_MODEL='deepseek-v4-flash'

python3 -m agentfly.cli plan \
  --mission-id agriculture-001 \
  --instruction '巡检 A 区域农田并标记疑似病虫害区域，低置信结果需要补拍' \
  --output outputs/deepseek/agriculture-001.json
```

规划器通过 `https://api.deepseek.com/chat/completions` 调用 JSON Mode。模型生成的任务图必须通过本地验证，检查内容包括依赖缺失、任务环路、故障恢复路径、返航节点、电量储备、工具类型和运行参数。

默认模型为 `deepseek-v4-flash`，可通过 `DEEPSEEK_MODEL` 修改。

## 实验结果

### 1. 确定性 MockEnv 对比

当前实验每个随机种子包含 120 个任务，共使用 3 个随机种子、4 类场景和 5 种方法，累计得到 1,800 次方法运行结果。

| 方法 | 任务成功率 | 计划有效率 | 工具调用准确率 | 恢复成功率 | 路径效率 | 执行成本 |
|---|---:|---:|---:|---:|---:|---:|
| AgentFly | 0.914 | 1.000 | 0.853 | 0.909 | 0.914 | 4.452 |
| Rule | 0.758 | 1.000 | 0.806 | 0.446 | 0.758 | 3.939 |
| PDDL-style | 0.608 | 1.000 | 0.761 | 0.000 | 0.608 | 3.444 |
| Pure-LLM-style | 0.514 | 0.825 | 0.773 | 0.000 | 0.514 | 3.485 |
| ReAct-style | 0.608 | 1.000 | 0.710 | 0.000 | 0.608 | 3.780 |

这组实验说明当前软件协议、工具执行和局部恢复机制能够按照设计运行。它是确定性模拟实验，不是 PX4/Gazebo 实验，也不能作为真实飞行或 SOTA 对比结论。

### 2. DeepSeek 真实 API 规划实验

`cmg-v4` 实验使用 `deepseek-v4-flash`、JSON Mode、`temperature=0`、关闭思考模式和四路并发，在农业、电力、安防和测绘场景上评测 50 条固定指令。

| 指标 | 结果 |
|---|---:|
| 首次生成可执行计划的有效率 | 1.000 |
| 首次有效率 95% Wilson 置信区间 | [0.929, 1.000] |
| 最终计划有效率 | 1.000 |
| 平均非缓存 API 延迟 | 4.265 秒 |
| Token 总量 | 48,437 |
| API 响应重试次数 | 0 |

这里的计划有效率（Plan Validity）只表示任务图通过结构和运行参数验证，不表示任务完整理解、工具执行成功或真实无人机飞行成功。

### 3. 语义约束修复实验

结构有效并不意味着自然语言中的每项约束都已落实。确定性规则评估发现，DeepSeek 直接生成的任务图只覆盖 175 条约束中的 125 条。系统将缺失约束诊断反馈给模型，并执行配对修复实验。

| 指标 | 直接生成 | 验证器引导修复 |
|---|---:|---:|
| 约束覆盖率 | 0.714 | 0.886 |
| 完整落实约束的任务比例 | 0.240 | 0.700 |

在最初不完整的 38 个任务中，60.5% 经修复后达到完整覆盖。剩余问题主要集中在最小安全距离、通信丢失策略、隐私区域约束和按电量拆分架次。

这些规则是研究阶段的确定性代理指标，不是行业专家标注。若用于论文结论，还需要独立人工标注和标注者一致性分析。

复现 DeepSeek 规划实验：

```bash
python3 -m agentfly.deepseek_benchmark \
  --tasks 50 \
  --seed 20260627 \
  --workers 4 \
  --max-revisions 2 \
  --cache outputs/deepseek/cache-new-run \
  --output outputs/deepseek/benchmark-new-run
```

复现语义约束修复实验：

```bash
python3 -m agentfly.semantic_experiment \
  --tasks 50 \
  --workers 4 \
  --direct-cache outputs/deepseek/cache-cmg-v4 \
  --repair-cache outputs/deepseek/cache-semantic-new-run \
  --output outputs/deepseek/semantic-repair-new-run
```

## 代码结构

```text
AgentFly/
├── agentfly/
│   ├── agents.py                # AgentFly 恢复策略和 baseline 策略
│   ├── benchmark.py             # 四类场景任务生成与统一实验运行器
│   ├── cli.py                   # 命令行入口
│   ├── constraint_eval.py       # 自然语言约束的确定性检查
│   ├── deepseek.py              # DeepSeek 客户端和任务图规划器
│   ├── deepseek_benchmark.py    # DeepSeek 规划实验
│   ├── domain.py                # 任务图与状态数据结构
│   ├── environment.py           # 确定性无人机模拟环境
│   ├── events.py                # Agent 状态归约器
│   ├── graph.py                 # 任务图验证器
│   ├── metrics.py               # 十二项评估指标
│   ├── runtime.py               # 共享任务执行循环
│   ├── semantic_experiment.py   # 直接生成与语义修复配对实验
│   └── tools.py                 # Safety Gate 和类型化工具调用
├── demos/                       # GitHub Pages 交互式演示
├── tests/                       # Python 自动化测试
└── pyproject.toml
```

## 当前范围

目前已经完成的是任务规划层研究原型和确定性模拟验证。以下能力尚未接入：

- VLM 图像理解适配器；
- 可扩展 RAG 知识索引；
- ROS 2、PX4 SITL、Gazebo 或 AirSim；
- 真实端云协同部署；
- 实机飞行实验。

Pure-LLM-style 和 ReAct-style 是确定性行为 baseline，不是真实在线模型运行结果。DeepSeek 适配器目前用于任务图生成和语义修复实验，尚未接入当前 MockEnv 方法对比表。

## 后续计划

1. 增加统一的 LLM/VLM Provider 接口和冻结提示词；
2. 将行业规范 RAG 与可执行安全规则结合；
3. 通过 ROS 2 接入 PX4 SITL 和 Gazebo；
4. 注入通信中断、定位漂移和动态禁飞区等故障；
5. 增加端云调度延迟、带宽和能耗分析；
6. 引入外部具身智能与无人机任务规划 baseline，并使用配对 Bootstrap 置信区间。

## 安全边界

AgentFly 只工作在高层任务规划与工具调度层。生成式模型不会产生电机控制量，也不能绕过确定性 Safety Gate 或飞控自身的安全机制。

当前代码是模拟环境中的研究原型。在完成独立安全审查、飞控适配、失效保护和监管合规验证之前，不应直接连接真实无人机。
