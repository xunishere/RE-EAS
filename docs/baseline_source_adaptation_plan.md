# Source-Adapted Baseline Plan

本文外部对比不再写作 proxy baseline。对于有公开源码的方法，实验应写成 **source-adapted baselines**：下载原仓库，保留其核心执行机制，只把输入输出适配到本文的 AI2-THOR household action/state interface。对于没有源码的方法，写成 **paper-based reimplementation**，明确依据论文描述实现其主要安全检查流程。

## 本地源码

| Method | Local source path | Upstream source | Adaptation status |
|---|---|---|---|
| RoboGuard | `baseline_model/RoboGuard_source` | `https://github.com/KumarRobotics/RoboGuard.git` | Use official contextual grounding + LTL control synthesis; adapt AI2-THOR scene graph and action sequence. |
| AgentSpec | `baseline_model/AgentSpec_source` | `https://github.com/haoyuwang99/AgentSpec.git` | Use official rule/check/enforce runtime executor; add AI2-THOR household predicates/rules. |
| ProbGuard / Pro2Guard | `baseline_model/ProbGuard_source` | `https://github.com/haoyuwang99/ProbGuard.git` | Use official predicate abstraction, DTMC learning, PRISM monitor; adapt state abstraction from our traces. |
| TrustAgent | `baseline_model/TrustAgent_source` | `https://github.com/agiresearch/TrustAgent.git` | Use official constitution/safety-checker prompt pipeline; adapt regulations and tool/action representation. |
| AutoRT | `baseline_model/AutoRT.pdf` | No public source found locally | Paper-based robot constitution / affordance-filter reimplementation. |
| SafeEmbodAI | `baseline_model/SafeEmbodAI.pdf` | No public source found locally | Paper-based embodied safety validation reimplementation. |

## 论文命名

实验表里不要写 `proxy`。建议名称：

- `RoboGuard-adapted`
- `AutoRT-paper`
- `AgentSpec-adapted`
- `ProbGuard-adapted`
- `SafeEmbodAI-paper`
- `TrustAgent-adapted`
- `Full SMART-LLM / RE-EAS`

推荐实验说明：

> For methods with public implementations, we use their released source code and adapt only the domain interface to our AI2-THOR household tasks. Specifically, the adaptation maps AI2-THOR states, object relations, and action traces into each method's expected representation while preserving its original safety-intervention mechanism. For AutoRT and SafeEmbodAI, whose source code is not publicly available in our collected artifacts, we implement paper-based baselines following their described robot-constitution/affordance filtering and embodied safety-validation procedures.

中文：

> 对于公开源码方法，本文使用其官方发布代码，并仅将领域接口适配到 AI2-THOR household tasks，包括将 AI2-THOR 状态、对象关系和动作轨迹映射到各方法所需表示，同时保留原方法的安全干预机制。对于 AutoRT 和 SafeEmbodAI，由于未获得公开源码，本文依据论文描述实现 paper-based baseline，分别对应 robot constitution/affordance filtering 和 embodied safety validation。

## 逐方法适配方式

### RoboGuard-adapted

源码关键点：

- `src/roboguard/roboguard.py`: `RoboGuard.update_context(graph)` 和 `RoboGuard.validate_plan(plan)`;
- `src/roboguard/generator.py`: 用 root-of-trust LLM 把 scene graph + rules grounding 为 LTL constraints;
- `src/roboguard/synthesis.py`: 用 Spot 将 LTL constraints 转成 Buchi automaton，并验证 action sequence。

适配到本文：

- 将 AI2-THOR `pre_state` 和对象关系转换成 RoboGuard semantic graph；
- 将 SMART-LLM 动作序列转换成 RoboGuard plan tuples；
- rules 使用本文 household safety rules；
- 输出为 plan/action 是否 safe，unsafe 时停止或要求 planner 重新生成计划；
- 不加入本文 constrained repair，否则会混入我们的方法贡献。

需要记录：

- generated contextual specifications；
- action-sequence validation result；
- unsafe plan/action rejection；
- false rejection；
- completion and violation rate。

### AgentSpec-adapted

源码关键点：

- `src/controlled_agent_excector.py`: 在 LangChain agent action 进入工具前调用 `validate_and_enforce`;
- `src/rules/manual/embodied.py`: 已经包含 household/embodied predicates，如 unsafe put、microwave、fragile 等；
- enforcement 支持 `stop`、`user_inspection`、`invoke_action`、`llm_self_examine`。

适配到本文：

- 为 AI2-THOR 动作封装一个 AgentSpec tool/action wrapper；
- 使用 AgentSpec rule 格式写本文 hazard rules；
- predicate 读取本文 `pre_state`、held object、object receptacle、toggle state、liquid state；
- enforcement 主实验用 `stop`，补充实验可测 `llm_self_examine`；
- 不使用本文 risk assessment/action-group/constrained repair。

需要记录：

- triggered rule；
- predicate result；
- enforcement mode；
- blocked action；
- runtime overhead；
- completion and violation rate。

### ProbGuard-adapted

源码关键点：

- `src/safereach/embodied/abstraction.py`: `EmbodiedAbstraction.encode` 把 embodied object observations 编码为 predicate bitstrings；
- `src/safereach/embodied/build.py`: 从 traces/specs 学习 DTMC；
- `src/safereach/runtime_monitor.py`: 调用 PRISM 计算到达 unsafe states 的概率；
- `src/safereach/embodied/monitor.py`: embodied runtime monitoring evaluation。

适配到本文：

- 从本文 action traces 导出 ProbGuard 所需 `s_trans` state sequence；
- 按 household hazards 定义 unsafe predicates/specs；
- 学习每类 hazard 或每类 task split 的 DTMC；
- runtime 时把当前 AI2-THOR state 编码为 bitstring，计算 reachability/risk probability；
- 超过阈值则 intervention/stop；
- 阈值做 sensitivity analysis。

需要记录：

- abstraction predicates；
- DTMC state count / transition count；
- unsafe-state set；
- reachability probability；
- threshold；
- lead time before violation；
- completion and violation rate。

### TrustAgent-adapted

源码关键点：

- `safeagi/agent_executor_builder.py`: 组合 planner、simulator、safety checker、regulation retrieval；
- `safeagi/prompts/safety_checker/standard.py`: safety checker prompt，按 regulation 判断 action/trajectory safe/unsafe；
- `safeagi/prompts/agent/agent_helpful_ss.py`: 将 safety/security requirements 注入 planning。

适配到本文：

- 把 AI2-THOR action API 写成 TrustAgent tool specification；
- 将 household hazard rules 写成 agent constitution / safety regulations；
- 主实验使用 post-planning/post-action safety checker 对下一动作或局部计划打 SAFE/UNSAFE；
- 可选加 pre-planning regulation prompting；
- unsafe 时停止或要求 planner 重写，但不使用本文 constrained repair。

需要记录：

- retrieved/used regulations；
- safety checker result；
- unsafe regulation IDs；
- criticism/revision；
- LLM latency and token usage；
- completion and violation rate。

### AutoRT-paper

无公开源码时，按论文方法实现：

- VLM/scene description 可由 AI2-THOR symbolic state 替代；
- robot constitution 包含本文 household safety constraints；
- affordance filter 检查动作是否物理可执行、是否违反 constitution；
- unsafe/not allowed 时拒绝任务或拒绝动作。

论文中写作 `paper-based implementation following AutoRT's robot constitution and affordance filtering`，不要称为官方复现。

### SafeEmbodAI-paper

无公开源码时，按论文方法实现：

- 输入为 command/action + current embodied state；
- state management 使用 AI2-THOR symbolic state；
- safety validation 检查恶意/危险命令、状态不一致、碰撞/损坏类风险；
- unsafe 时拒绝动作。

论文中写作 `paper-based implementation following SafeEmbodAI's embodied safety validation pipeline`，不要称为官方复现。

## 实验公平性边界

- 所有 baseline 跑同一批 AI2-THOR tasks、同一 hazards、同一 task success 判定和同一 RT-Lola safety labels。
- 外部 baseline 不允许调用本文 constrained repair，否则无法证明 repair 是我们自己的贡献。
- 对有源码方法，保留原核心机制，但领域适配代码需要公开描述：state mapping、action mapping、rule/spec mapping、threshold setting。
- 对无源码方法，在实验表脚注标注 `paper-based implementation`。
- 不再使用 `proxy` 命名；如果保留临时工程脚本，也只作为开发 scaffold，不写入论文。
