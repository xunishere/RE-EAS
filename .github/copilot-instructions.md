# SMART-LLM AI Coding Instructions

## Project Overview

SMART-LLM is a **runtime safety-assured multi-robot task execution system** that integrates LLM-based planning with formal safety verification. The system uses AI2-THOR simulation environments to execute household robot tasks with three-layer safety guarantees: Conformal Prediction (CP) for risk prediction, RTLola STL monitor for runtime verification, and RAG-based action repair.

## Architecture & Data Flow

```
LLM Planner (run_llm.py) → Executable Plans (logs/) → Safety Layer (RE-EAS) → AI2-THOR Execution
                                                              ↓
                                                    CP Predictor + RTLola Monitor
```

### Core Components

1. **Task Planning Pipeline** ([scripts/run_llm.py](scripts/run_llm.py))
   - Uses DeepSeek API to decompose tasks and allocate to robots
   - Reads task configs from `data/final_test/FloorPlan{N}_{task}.json`
   - Generates multi-threaded Python execution plans in `logs/{task_name}_plans_{timestamp}/code_plan.py`
   - FloorPlan format: "2" for environment or "2_1" for environment_task pairs

2. **Execution Engine** ([scripts/execute_plan.py](scripts/execute_plan.py))
   - Compiles plans by concatenating: imports → robot list → floor number → AI2-THOR connector → generated plan → termination code
   - Creates temporary CSV files for RTLola monitoring: `RTlola/safe_{timestamp}_{hash}.csv`
   - Final executable: `logs/{task}/executable_plan.py`

3. **AI2-THOR Interface** ([data/aithor_connect/aithor_connect.py](data/aithor_connect/aithor_connect.py))
   - Multi-agent controller with action functions: `GoToObject`, `PickupObject`, `PutObject`, `SwitchOn`, `ThrowObject`, etc.
   - `get_current_state()`: Returns 21 safety-critical signals aligned with RTLola predicates
   - `record_pre_action()` / `check_post_action()`: Safety monitoring hooks for CP/RAG integration
   - Global `action_log` tracks execution history for repair retrieval

4. **Safety Verification** ([RTlola/safe.spec](RTlola/safe.spec))
   - Monitors 5 hazard types:
     - Electronic devices in heating appliances (`cellphone_in_microwave`, `laptop_in_stove`)
     - Heating duration violations (`microwave_on_duration > T_max_heat`)
     - Water source timeouts (`faucet_on_duration > T_max_water`)
     - Electronics near water (`cellphone_to_faucet_dist < delta_safe` while `cellphone_voltage`)
     - Fragile object breakage (`throw_magnitude > theta_break` for breakable items)
   - Use `rtlola-cli monitor RTlola/safe.spec --offline relative --csv-in {csv_file}` to verify traces

5. **Risk Prediction** ([prediction/model.py](prediction/model.py))
   - Conformal Predictor with `alpha=0.1` (90% coverage guarantee)
   - Input: 21-dimensional state vector + action type string
   - Output: Prediction set `{'safe'}`, `{'unsafe'}`, or `{'safe', 'unsafe'}`
   - Training data collected via [scripts/execute_plan_with_data_collection.py](scripts/execute_plan_with_data_collection.py) with RTLola ground truth labels

6. **Repair Module** ([repair/rag-consens.py](repair/rag-consens.py))
   - RAG retrieves safe action sequences from `repair/database` when CP predicts `not {'safe'}`
   - Maximum 3 repair attempts before task termination

## Critical Workflows

### Generate 600 Task Configs
```bash
python generate_tasks.py  # Creates data/final_test/FloorPlan{1-30,201-230,301-330,401-430}_{1-5}.json
```

### Plan Generation
```bash
python scripts/run_llm.py --floor-plan 10_1  # Uses DEEPSEEK_API_KEY.txt
```
- Reads `data/final_test/FloorPlan10_1.json` 
- Queries AI2-THOR FloorPlan10 for object list
- Outputs `logs/{task}_plans_{timestamp}/code_plan.py` and `log.txt`

### Task Execution
```bash
python scripts/execute_plan.py --command "{task_folder_name}"  # Without safety
python RE-EAS/execute_plan_with_safety.py --task logs/{task}   # With RE-EAS safety
```

### Multi-Process Batch Execution
```bash
python run_all_tasks.py  # Auto-discovers logs/* folders, 10min timeout per task
```

### Collect Training Data for CP
```bash
python scripts/execute_plan_with_data_collection.py --command "{task}"
# Labels each action safe/unsafe based on RTLola verdict, continues on violations (no termination)
```

### Train Prediction Model
```bash
cd prediction
python model.py  # Trains RandomForest on data/training.csv, saves to models/
```

## Project Conventions

### Robot Definitions ([resources/robots.py](resources/robots.py))
- All robots support 13 actions: `GoToObject`, `OpenObject`, `CloseObject`, `BreakObject`, `SliceObject`, `SwitchOn`, `SwitchOff`, `PickupObject`, `PutObject`, `DropHandObject`, `ThrowObject`, `PushObject`, `PullObject`
- Robots 1-4: Infinite mass capacity (`mass: 100`)
- Robots 5-10: Mass-limited (0.02-5.0 kg capacity)
- Specialized robots (11-17): Subset of skills (e.g., robot11 lacks Open/Close)

### Action Signature Format
- Template: `{Action} <robot><object>[<receptacle>]`
- Examples: `PickupObject robot1 CellPhone`, `PutObject robot1 Bowl Sink`

### Environment Types
- Kitchen: FloorPlan 1-30
- LivingRoom: FloorPlan 201-230
- Bedroom: FloorPlan 301-330
- Bathroom: FloorPlan 401-430

### Log Structure
Each `logs/{task}_plans_{timestamp}/` contains:
- `code_plan.py`: LLM-generated multi-threaded plan
- `log.txt`: Metadata (floor_no, robots, object_states, trans limits)
- `executable_plan.py`: Compiled full execution script
- Agent images: `agent_{1,2}/Action_{n}_0_normal.png`

### State Representation
The `get_current_state()` function returns a dict with keys:
```python
{
    "microwave_on", "stove_on", "cellphone_in_microwave", "laptop_in_microwave",
    "cellphone_in_stove", "laptop_in_stove", "microwave_on_duration", "stove_on_duration",
    "cellphone_voltage", "laptop_voltage", "faucet_on", "faucet_on_duration",
    "cellphone_to_faucet_dist", "laptop_to_faucet_dist", "holding_fragile_obj",
    "throw_magnitude", "T_max_heat", "T_max_water", "delta_safe", "theta_break", "time"
}
```

## Common Pitfalls

1. **FloorPlan Parameter Confusion**: AI2-THOR needs numeric-only ID ("10"), but file paths use full ID ("10_1")
2. **CSV Cleanup**: Execute plan generates temp CSV files—ensure cleanup in `finally` blocks
3. **Action Execution Model**: Plans use Python `threading.Thread` for concurrent robot actions
4. **Object State Queries**: Use `receptacleObjectIds` to check container contents after `PutObject`/heating
5. **Fragile Items**: Only objects with `breakable=True` can break; check `salientMaterials` for glass/ceramic
6. **Water Activation**: Use `SwitchOn` on `Faucet` objects, not `Sink` objects
7. **Heating Requirements**: Microwave needs `OpenObject` → `PutObject` → `CloseObject` → `ToggleObjectOn`; Stove needs `PutObject(Pan)` first

## Development Tips

- **API Key**: Stored in plain text at root: `DEEPSEEK_API_KEY.txt`
- **Dependencies**: Install via `pip install -r requirments.txt` (note typo in filename)
- **Debugging**: Check `logs/{task}/log.txt` for robot assignments and object states
- **Video Generation**: Uncomment `generate_video()` calls in [data/aithor_connect/imports_aux_fn.py](data/aithor_connect/imports_aux_fn.py)
- **Monitoring Output**: RTLola CSV files accumulate in `RTlola/monitor_*.csv`—clean periodically

## Key Integration Points

- **LLM ↔ Simulator**: [scripts/run_llm.py](scripts/run_llm.py) calls `get_ai2_thor_objects()` to query available objects per FloorPlan
- **Plan ↔ Execution**: [scripts/execute_plan.py](scripts/execute_plan.py) reads `log.txt` lines 4,8-11 to extract floor/robots/constraints
- **Safety ↔ Actions**: Every action in [data/aithor_connect/aithor_connect.py](data/aithor_connect/aithor_connect.py) calls `get_current_state()` and updates global monitoring CSV
- **CP ↔ Repair**: [RE-EAS/execute_plan_with_safety.py](RE-EAS/execute_plan_with_safety.py) intercepts unsafe predictions and queries [repair/rag-consens.py](repair/rag-consens.py)
