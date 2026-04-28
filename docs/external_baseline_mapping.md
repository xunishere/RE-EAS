# 外部 Baseline 映射

本文外部对比改为两类：

- **source-adapted baseline**：有公开源码的方法，下载原仓库并保留核心机制，只适配 AI2-THOR 输入输出。
- **paper-based baseline**：没有公开源码的方法，依据论文方法实现同类 safety gate/filter，并在论文中标注为 paper-based implementation。

不再使用 `proxy` 作为论文实验命名。

## Baseline 选择

| Method | 本地材料 | 实验定位 | 是否主实验 | 说明 |
|---|---|---|---|---|
| RoboGuard | `RoboGuard.pdf`, `RoboGuard_source/` | Source-adapted | Yes | 最直接的 embodied robot safety guardrail；对比 pre-execution LTL guardrail 与本文 continuous monitoring + repair。 |
| AutoRT | `AutoRT.pdf` | Paper-based | Yes | Robot constitution + affordance filtering；对比 constitution filter 与 runtime repair。 |
| AgentSpec | `AgentSpec.pdf`, `AgentSpec_source/` | Source-adapted | Yes | Runtime rule enforcement DSL；对比 explicit rule enforcement 与 physical-state repair。 |
| ProbGuard / Pro2Guard | `Pro2Guard.pdf`, `ProbGuard_source/` | Source-adapted | Yes/Supplementary | Proactive probabilistic runtime monitoring；对比 DTMC reachability risk gate 与本文 action-level calibrated prediction + repair。 |
| SafeEmbodAI | `SafeEmbodAI.pdf` | Paper-based | Supplementary | Embodied/mobile robot safety validation；不是强 repair baseline，但可代表 embodied safety validation。 |
| TrustAgent | `TrustAgent.pdf`, `TrustAgent_source/` | Source-adapted | Supplementary | Constitution-based LLM agent safety；更偏 digital/tool agent，但可作为 safety checker/planning baseline。 |

如果只能放 4 个主外部对比：`RoboGuard-adapted`、`AutoRT-paper`、`AgentSpec-adapted`、`ProbGuard-adapted`。
如果篇幅允许再加：`SafeEmbodAI-paper`、`TrustAgent-adapted`。

## 论文表名

| 实验名 | 含义 |
|---|---|
| `RoboGuard-adapted` | 使用 RoboGuard 官方源码，把 AI2-THOR scene/action 映射到 semantic graph + plan validation。 |
| `AutoRT-paper` | 按 AutoRT 论文实现 robot constitution / affordance filter。 |
| `AgentSpec-adapted` | 使用 AgentSpec 官方源码，把 household hazards 写成 AgentSpec rules/predicates。 |
| `ProbGuard-adapted` | 使用 ProbGuard 官方源码，从本文 traces 学 DTMC 并做 proactive reachability monitoring。 |
| `SafeEmbodAI-paper` | 按 SafeEmbodAI 论文实现 embodied safety validation gate。 |
| `TrustAgent-adapted` | 使用 TrustAgent 官方源码，把 household rules 写成 regulations/constitution safety checker。 |
| `Full SMART-LLM / RE-EAS` | 本文完整系统：prediction + risk assessment + allowable action group + constrained repair + RT-Lola monitoring。 |

## 与本文方法的差异

| Method | Embodied | Pre-exec safety | Runtime watch | Proactive risk | Structured repair | Human/constitution | Main contrast |
|---|---|---|---|---|---|---|---|
| RoboGuard-adapted | Yes | Yes | Limited | No | No | Rule/LLM grounding | Plan guardrail vs execution-time repair |
| AutoRT-paper | Yes | Yes | Limited | No | No | Robot constitution | Constitution filtering vs repair continuation |
| AgentSpec-adapted | Partial/Yes | Yes | Yes | No | Limited by enforcement action | User-defined rules | Rule enforcement vs STL-guided repair |
| ProbGuard-adapted | Partial/Yes | No/Partial | Yes | Yes | No | No | Probabilistic reachability vs calibrated trigger + repair |
| SafeEmbodAI-paper | Yes | Yes | Partial | No | No | Safety validation | Embodied validation vs manipulation repair |
| TrustAgent-adapted | Weak/No | Yes | Post-planning checker | No | Revision/checking | Agent constitution | Constitution checker vs physical-state monitor/repair |
| Full SMART-LLM / RE-EAS | Yes | Yes | Yes | Yes | Yes | Optional | Closed-loop runtime enforcement and repair |

## 每个 baseline 需要的数据

### RoboGuard-adapted

- AI2-THOR semantic graph generated for each task step;
- generated contextual safety specifications;
- validated plan/action sequence;
- safe/unsafe decision;
- rejected action index;
- violation rate and task completion.

### AutoRT-paper

- robot constitution rules used;
- affordance check result;
- rejected unsafe task/action;
- task continuation outcome;
- violation rate and task completion.

### AgentSpec-adapted

- rule text / rule id;
- trigger event;
- predicate result;
- enforcement action (`stop`, `llm_self_examine`, or replacement);
- blocked action;
- violation rate and task completion.

### ProbGuard-adapted

- abstraction predicates;
- DTMC training split;
- DTMC state/transition count;
- unsafe states;
- reachability probability;
- intervention threshold;
- warning lead time;
- violation rate and task completion.

### SafeEmbodAI-paper

- validation rule/category;
- state consistency result;
- unsafe command/action decision;
- rejected action;
- violation rate and task completion.

### TrustAgent-adapted

- safety regulations retrieved/injected;
- safety checker SAFE/UNSAFE output;
- unsafe regulation ids;
- critique/revision output;
- token/latency cost;
- violation rate and task completion.

## 推荐论文说明

英文：

> For methods with public implementations, we use their released source code and adapt only the domain interface to our AI2-THOR household tasks. The adaptation maps AI2-THOR object states, relations, and action traces into each method's expected representation while preserving its original safety-intervention mechanism. For AutoRT and SafeEmbodAI, whose source code is not publicly available in our collected artifacts, we implement paper-based baselines following their described robot-constitution/affordance filtering and embodied safety-validation procedures.

中文：

> 对公开源码方法，本文使用其发布源码，并仅将领域接口适配到 AI2-THOR household tasks，包括将 AI2-THOR 对象状态、对象关系和动作轨迹映射到各方法所需表示，同时保留其原始安全干预机制。对于 AutoRT 和 SafeEmbodAI，由于未获得公开源码，本文依据论文描述实现 paper-based baseline，分别对应 robot constitution/affordance filtering 和 embodied safety validation。
