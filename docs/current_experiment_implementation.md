# 当前实验实现记录

更新时间：2026-04-28

本文档记录最近一次实验代码和论文实验设计的实际状态。以后论文实验部分以这里为准，旧文档中仍出现的 database/RAG、过多组件消融、intervention rate 等内容不再作为当前主实验设计。

## 1. 当前模型主线

当前 RE-EAS / SMART-LLM 主线是三模块运行时闭环：

1. Runtime Monitoring：执行后 RT-Lola / monitor trace 给出 unsafe verdict。
2. Prediction Gate：动作执行前根据 monitored pre-state + proposed action 触发风险拦截。
3. Constrained Repair：预测为 unsafe 后进入修复，内部使用 risk assessment、allowable action set、constrained repair / fallback。

注意：

- `repair/database_runtime.py` 和 `rag_consens.py` 仍可能作为历史残留存在，但当前模型和实验不再把 database/RAG 当作核心修复机制。
- Repair 不再写成“检索相似案例替代动作”，而是“风险评估 -> allowable action set -> 受限修复/兜底动作”。
- `unsafe_label` 在实验语义上对应 prediction gate 的 unsafe trigger，可视为 `unsafe in P_alpha(z_i)` 的运行时触发结果。

## 2. RQ 结构

当前实验固定为四个 RQ：

| RQ | 目标 | 实现入口 |
|---|---|---|
| RQ1 | 整体系统 vs 外部方法 | `scripts/run_batch_pipeline.py` 和 external baseline runner |
| RQ2 | 完整系统 vs 去掉三大模块 | `scripts/run_rq2_ablation.py --variant-set rq2` |
| RQ3 | 当前预测策略 vs 时序预测策略 | `scripts/run_rq2_ablation.py --variant-set rq3` |
| RQ4 | 当前修复策略 vs 其他修复策略 | `scripts/run_rq2_ablation.py --variant-set rq4` |

旧想法中删除或不作为主实验的内容：

- 不再把 `w/o Risk Assessment`、`w/o Allowable Action Set`、`w/o Fallback`、`w/o Database Update` 作为 RQ2 主消融，因为论文里只强调三个主模块。
- 不再把 database leakage / retrieved trace similarity 作为当前主实验，因为当前修复逻辑已经不是 RAG/database。
- 不再把 `Block / Intervention Rate`、`Safety Stop Rate`、`Avg Unsafe Steps per Task` 放进 RQ1 主表，因为外部 baseline 的框架和干预语义不同，不公平。

## 3. RQ1 指标

RQ1 只保留四个所有方法公平可比的任务级指标：

| 指标 | 含义 |
|---|---|
| Task Success / Completion Rate | 任务最终是否完成 |
| Unsafe-task Rate | 一个任务中是否出现过至少一次 unsafe |
| Avg Execution Time | 平均执行耗时，可用执行时间或总时间 |
| Execution Failure Rate | 计划/动作执行失败比例 |

新增时间字段：

- `planner_elapsed_seconds`：`run_llm.py` 规划耗时。
- `execution_elapsed_seconds`：执行生成代码的耗时，等价于旧的 `elapsed_seconds`。
- `total_elapsed_seconds`：规划 + 执行。

外部 baseline 如果复用已有 plan，会继承 source summary 中的 `planner_elapsed_seconds`。如果旧 summary 没有规划时间，则该字段为 `0.0` 或空值，旧实验不能强行写成总时间。

## 4. RQ2 三模块消融

RQ2 只比较三个主模块：

| Variant | Mode | 解释 |
|---|---|---|
| Full RE-EAS | `full` | monitor + prediction + constrained repair |
| w/o Runtime Monitoring | `no_runtime_monitor` | 监测 sidecar 整体禁用，prediction/repair 因无 monitored pre-state 也不启动，退化为 direct execution |
| w/o Prediction Gate | `monitor_only` | 不做动作前预测，危险只能执行后由 monitor 记录 |
| w/o Constrained Repair | `prediction_only` | 有预测拦截，但 unsafe 后 block/stop，不修复 |

关键修正：

- `w/o Runtime Monitoring` 不是“只关闭 RT-Lola verdict”。它现在是真正关闭 monitor sidecar，因此 prediction 和 repair 都不可用。
- `w/o Prediction Gate` 不是“危险后再修复”。没有 prediction trigger，就不会提前进入 repair；unsafe 只能由 post-action monitor 记录。

## 5. RQ3 预测模型对比

RQ3 只替换 prediction gate，monitor 和 repair 保持一致。

| Variant | Mode | 含义 |
|---|---|---|
| Current RF + calibration/conformal | `full` | 当前主模型，来自 RQ1/RQ2 已有结果 |
| MultiDimSPCI + Repair | `multidimspci_repair` | MultiDimSPCI-style temporal conformal gate + 原 repair |
| CPTC + Repair | `cptc_repair` | CPTC-style temporal conformal gate + 原 repair |

新增文件：

- `scripts/train_temporal_prediction_runtimes.py`
- `data/aithor_connect/temporal_prediction_runtime.py`
- `baseline_model/temporal_prediction_artifacts/multidimspci_runtime.joblib`
- `baseline_model/temporal_prediction_artifacts/cptc_runtime.joblib`
- `baseline_model/temporal_prediction_artifacts/runtime_temporal_metrics.json`

训练数据来源：

- 使用服务器拉回的 `baseline_model/server_prediction/data/splits/{train,val,test}.csv`。
- 不使用本地重新生成的数据。

## 6. RQ4 修复策略对比

RQ4 固定 prediction gate 和 monitor，只替换 repair strategy。

| Variant | Mode | 含义 |
|---|---|---|
| Block-only | `prediction_only` | unsafe 后直接 block/stop |
| Random Action Replacement | `random_action_repair` | 从通用动作模板随机选替代动作 |
| Random Allowable Action | `random_allowable_repair` | 从 allowable action set 中随机选一个动作 |
| Rule-based Local Repair | `rule_based_repair` | 按 hazard 类型使用固定局部规则 |
| Unconstrained LLM Repair | `unconstrained_llm_repair` | LLM 自由生成修复动作，不使用 allowable-action constraint |
| Full RE-EAS Repair | `full` | risk assessment + allowable action set + constrained repair / fallback |

新增文件：

- `data/aithor_connect/repair_strategy_runtime.py`

实现边界：

- Random Action 是弱下限，允许暴露对象不存在、动作不合适等失败。
- Random Allowable 用同一个 allowable set，但不做目标保持排序。
- Rule-based 只处理固定 hazard family，不声称泛化。
- Unconstrained LLM 不使用 formal allowable set，用于证明自由 LLM repair 可能完成任务但更容易 unsafe。

## 7. 外部 baseline 当前定位

RQ1 外部方法按方法类型解释，不再写 proxy。

| Method | 当前定位 |
|---|---|
| RoboGuard-adapted | source-adapted embodied robot safety guardrail |
| AutoRT-paper | paper-based robot constitution / affordance filter |
| AgentSpec-adapted | source-adapted runtime rule enforcement |
| ProbGuard-adapted | source-adapted proactive probabilistic runtime enforcement |
| SafeEmbodAI-paper | paper-based embodied safety validation |
| TrustAgent-adapted | source-adapted constitution/safety-checking LLM agent baseline |

RQ1 主表只比较 Completion、Unsafe-task、Time、Execution Failure，不比较内部 block/intervention，因为不同 baseline 的安全机制不一致。

## 8. 运行命令

RQ2：

```bash
python3 scripts/run_rq2_ablation.py --variant-set rq2 --model deepseek-reasoner --deepseek-api-key-file DEEPSEEK_API_KEY
```

RQ3：

```bash
python3 scripts/run_rq2_ablation.py --variant-set rq3 --model deepseek-reasoner --deepseek-api-key-file DEEPSEEK_API_KEY
```

RQ4：

```bash
python3 scripts/run_rq2_ablation.py --variant-set rq4 --model deepseek-reasoner --deepseek-api-key-file DEEPSEEK_API_KEY
```

汇总：

```bash
python3 scripts/summarize_experiment_results.py logs/*summary*.jsonl --output-csv logs/summary.csv
```

## 9. 最近代码修改清单

新增或启用：

- `scripts/run_batch_pipeline.py`：
  - 增加 `no_runtime_monitor` 真正关闭 monitor sidecar；
  - 增加 `multidimspci_repair`、`cptc_repair`；
  - 增加 RQ4 repair modes；
  - 增加 `planner_elapsed_seconds`、`execution_elapsed_seconds`、`total_elapsed_seconds`。
- `scripts/run_rq2_ablation.py`：
  - 增加 `--variant-set rq2/rq3/rq4/all`；
  - RQ2/RQ3/RQ4 共用同一个任务与 summary 机制。
- `scripts/run_external_baselines_on_existing_plans.py`：
  - 复用已有 plan 时携带 source planner time。
- `scripts/summarize_experiment_results.py`：
  - 输出 planner/execution/total time。
- `data/aithor_connect/temporal_prediction_runtime.py`：
  - RQ3 temporal predictor runtime adapter。
- `scripts/train_temporal_prediction_runtimes.py`：
  - 训练并保存 RQ3 runtime artifacts。
- `data/aithor_connect/repair_strategy_runtime.py`：
  - RQ4 alternative repair strategies。

废弃或不写进论文主实验：

- `proxy` 命名；
- database/RAG repair 主线；
- database update ablation；
- RQ1 的 intervention/safety-stop/unsafe-step 主指标；
- RQ2 的细粒度内部组件消融。
