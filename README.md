# SMART-LLM: A Safety-Aware Single-Robot Framework for AI2-THOR

SMART-LLM is a safety-aware embodied task execution framework for AI2-THOR.  
It combines:

- LLM-based task planning
- executable action-code generation
- online safety prediction
- RT-Lola runtime monitoring
- retrieval-augmented repair
- continual maintenance of a safe execution database

The framework is designed for household manipulation tasks in which a robot must complete a task while avoiding unsafe behaviors involving heating appliances, water sources, electronic devices, and fragile objects.

## 1. Framework Overview

The framework follows a closed-loop architecture:

```text
task description + floor plan
  -> planner
  -> executable task code
  -> action-level execution in AI2-THOR
     -> pre-action safety prediction
     -> post-action RT-Lola monitoring
     -> retrieval-based repair when unsafe actions are predicted
     -> safe-trace database maintenance after qualified safe runs
```

This design supports both proactive safety intervention and long-term improvement through database growth.

## 2. Core Components

### 2.1 Planner

The planner converts a natural-language task into executable AI2-THOR-oriented action code.

Main entry:

- `scripts/run_llm.py`

The planner input is intentionally minimal:

```json
{
  "task": "Pick up the cellphone and use the microwave to heat an object.",
  "floor_plan": "FloorPlan2"
}
```

### 2.2 Execution Runtime

The execution layer runs planner-generated action code inside AI2-THOR.

Main files:

- `scripts/execute_plan.py`
- `data/aithor_connect/runtime_minimal.py`
- `data/aithor_connect/end_minimal.py`

The runtime exposes planner-visible action APIs including:

- `GoToObject`
- `PickupObject`
- `PutObject`
- `OpenObject`
- `CloseObject`
- `SwitchOn`
- `SwitchOff`
- `SliceObject`
- `BreakObject`
- `ThrowObject`

These action boundaries are also the units used for prediction, monitoring, repair, and success-rate accounting.

### 2.3 RT-Lola Monitoring

The monitoring layer observes the post-action environment state and evaluates safety constraints using RT-Lola.

Main files:

- `data/aithor_connect/monitor_signals.py`
- `data/aithor_connect/monitor_runtime.py`
- `RTlola/safe.spec`

The current specification models five safety categories:

1. heating an electronic object inside a heating appliance
2. heating appliances remaining on for too long
3. water sources remaining on for too long
4. unsafe proximity between water and electronic objects
5. excessive force on fragile objects

Monitoring results are written during execution and provide the runtime safety label for each action sample.

### 2.4 Safety Prediction

The prediction layer estimates whether the next planner-visible action will lead to an unsafe state.

Main files:

- `data/aithor_connect/prediction_runtime.py`
- `prediction/config.py`
- `prediction/dataset.py`
- `prediction/features.py`
- `prediction/train.py`
- `prediction/calibration.py`
- `prediction/evaluate.py`
- `prediction/infer.py`

The prediction task is formulated as:

```text
(pre_state, action) -> unsafe
```

The deployed prediction stack includes:

- feature transformation
- probabilistic classification
- probability calibration
- prediction-set support

### 2.5 Retrieval-Augmented Repair

When an action is predicted unsafe, the framework blocks the original action before execution and queries a safe-trace database for a repair sequence.

Main files:

- `repair/rag_consens.py`
- `data/aithor_connect/repair_runtime.py`
- `repair/database`

RAG repair uses:

- task description
- environment
- executed action history
- blocked action

to retrieve similar safe traces and produce a local repair sequence that can replace the unsafe action online.

### 2.6 Safe Database Maintenance

The framework maintains a database of safe execution traces for future retrieval.

Main file:

- `repair/database_runtime.py`

After each completed run, the runtime evaluates whether the executed trajectory qualifies as a safe record and, if so, appends it to the database while avoiding exact duplicates.

## 3. Execution Policy

For each planner-visible action, the framework follows this policy:

1. build the pre-action state representation
2. run safety prediction
3. if the action is predicted safe, execute it normally
4. if the action is predicted unsafe, block the original action
5. query the repair module
6. execute the returned repair actions instead
7. monitor the post-action state with RT-Lola

This ensures that unsafe actions are intercepted before they reach the environment.

## 4. Success and Safety Signals

The framework distinguishes between task execution success and safety:

- `SR` measures whether planner-visible task actions succeed operationally
- monitoring measures whether the resulting execution remains safe

This separation allows successful-but-unsafe and failed-but-safe cases to be distinguished explicitly.

## 5. Data and Runtime Outputs

Each task execution directory under `logs/` may contain:

- `log.txt`
- `raw_code_plan.py`
- `code_plan.py`
- `decomposed_plan.py`
- `validation_report.json`
- `executable_plan.py`
- `rtlola_stream.csv`
- `monitor_trace.csv`
- `prediction_trace.csv`
- `repair_trace.jsonl`

These files together capture planning, execution, prediction, monitoring, and repair behavior for a task.

## 6. Prediction Pipeline

The prediction stack is trained from action-level samples aligned with the runtime format.

Current training pipeline:

```text
dataset splits
  -> dataset normalization
  -> first-unsafe truncation
  -> feature transformation
  -> classifier training
  -> calibration
  -> evaluation
  -> deployable inference artifacts
```

Training and evaluation commands:

```bash
python3 prediction/train.py
python3 prediction/calibration.py
python3 prediction/evaluate.py
```

Inference:

```bash
python3 prediction/infer.py
```

Artifacts are stored in:

- `prediction/artifacts`

## 7. Safe Database Schema

Each record in the repair database uses the following schema:

```json
{
  "record_id": "record_0001",
  "environment": "FloorPlan2",
  "task_description": "...",
  "actions": [...]
}
```

This minimal schema is sufficient for retrieval based on task, environment, and action history while remaining easy to maintain online.

## 8. Running the Framework

Generate plans:

```bash
python3 scripts/run_llm.py --floor-plan 2
```

Execute a task:

```bash
python3 scripts/execute_plan.py --command <log_folder_name>
```

Prediction training:

```bash
python3 prediction/train.py
python3 prediction/calibration.py
python3 prediction/evaluate.py
```

Standalone inference:

```bash
python3 prediction/infer.py
```

## 9. Dependencies

Python dependencies are listed in:

- `requirements.txt`

In addition, the framework expects:

- `rtlola-cli` as an external runtime dependency
- `ffmpeg` if video generation is used

## 10. Summary

SMART-LLM provides a unified framework for:

- LLM-based embodied task planning
- executable AI2-THOR action programs
- online safety prediction
- formal runtime monitoring with RT-Lola
- retrieval-augmented local repair
- continual accumulation of safe execution knowledge

The result is a practical safety-aware embodied agent framework that supports both online intervention and long-term improvement.
