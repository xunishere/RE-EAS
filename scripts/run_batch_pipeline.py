"""Batch runner for SMART-LLM full pipeline and runtime ablations.

This script reads a task JSON file, generates plans with `run_llm.py`, and then
executes each generated task either with:

- `full`: monitoring + prediction + repair
- `prediction_only` / `no_repair`: monitoring + prediction, but repair disabled
- `monitor_only`: monitoring enabled, prediction and repair disabled
- `*_adapted`: external released-code baselines with block-only intervention
- `*_paper`: paper-based baselines with block-only intervention

It is intended for controlled paper experiments where the same task set should
be executed under different system configurations.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
IMPORTS_FILE = ROOT / "data" / "aithor_connect" / "imports_aux_fn.py"
RUNTIME_FILE = ROOT / "data" / "aithor_connect" / "runtime_minimal.py"
END_FILE = ROOT / "data" / "aithor_connect" / "end_minimal.py"
UNRECOVERABLE_REPAIR_EXIT_CODE = 42


DISABLE_VISUAL_ARTIFACTS_PATCH = """
# Paper batch experiments only need structured logs/metrics. Disable visual
# frame/video artifacts to reduce disk usage and avoid ffmpeg overhead.
def _init_visual_recording(task_dir):
    global visual_task_dir
    global visual_recording_enabled
    global visual_frame_counter
    visual_task_dir = None
    visual_recording_enabled = False
    visual_frame_counter = 0

def _capture_visual_frame(event=None):
    return None

def finalize_visual_recording(frame_rate=5):
    return None
"""


NO_REPAIR_PRELUDE = """
import types
import sys

# Keep monitoring + prediction enabled, but disable repair by converting unsafe
# predictions into a block-only stop decision.
repair_runtime_stub = types.ModuleType("data.aithor_connect.repair_runtime")
repair_runtime_stub.action_matches = lambda *args, **kwargs: False
repair_runtime_stub.begin_repair = lambda *args, **kwargs: None
repair_runtime_stub.end_repair = lambda *args, **kwargs: None
def _init_repair_runtime(task_dir, *args, **kwargs):
    import pathlib
    path = pathlib.Path(task_dir) / "repair_trace.jsonl"
    path.write_text("", encoding="utf-8")
    return {"enabled": True, "trace_path": path}
repair_runtime_stub.record_executed_action = lambda *args, **kwargs: None
repair_runtime_stub.repair_allowed = lambda *args, **kwargs: True
def _request_repair(repair_state, pre_state, action_info, prediction_result):
    import json
    payload = {
        "blocked_action": action_info,
        "prediction_result": prediction_result,
        "replan_result": {
            "mode": "block_only",
            "reason": "prediction_only_no_repair",
            "repair_actions": [],
            "retry_required": True,
        },
        "retry_required": True,
        "repair_actions": [],
    }
    if repair_state and repair_state.get("trace_path"):
        with repair_state["trace_path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\\n")
    return payload
repair_runtime_stub.init_repair_runtime = _init_repair_runtime
repair_runtime_stub.request_repair = _request_repair
repair_runtime_stub.set_pending_skip_actions = lambda *args, **kwargs: None
repair_runtime_stub.should_skip_action = lambda *args, **kwargs: False
sys.modules["data.aithor_connect.repair_runtime"] = repair_runtime_stub
"""


EXTERNAL_PROXY_MODES = {
    "roboguard_proxy",
    "autort_proxy",
    "agentspec_proxy",
    "pro2guard_proxy",
    "probguard_proxy",
    "safeembodai_proxy",
    "trustagent_proxy",
}


EXTERNAL_BASELINE_MODES = {
    "roboguard_adapted",
    "autort_paper",
    "agentspec_adapted",
    "pro2guard_adapted",
    "probguard_adapted",
    "safeembodai_paper",
    "trustagent_adapted",
}


TEMPORAL_PREDICTOR_MODES = {
    "multidimspci_repair",
    "cptc_repair",
}


TEMPORAL_PREDICTOR_METHODS = {
    "multidimspci_repair": "multidimspci",
    "cptc_repair": "cptc",
}


RQ4_REPAIR_MODES = {
    "random_action_repair",
    "random_allowable_repair",
    "rule_based_repair",
    "unconstrained_llm_repair",
}


RQ4_REPAIR_STRATEGIES = {
    "random_action_repair": "random_action",
    "random_allowable_repair": "random_allowable",
    "rule_based_repair": "rule_based",
    "unconstrained_llm_repair": "unconstrained_llm",
}


RQ4_REPAIR_PRELUDE_TEMPLATE = """
import pathlib
import sys
import types

PROJECT_ROOT = pathlib.Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.aithor_connect import repair_strategy_runtime as repair_strategy

RQ4_REPAIR_STRATEGY = {strategy!r}

repair_runtime_stub = types.ModuleType("data.aithor_connect.repair_runtime")
def _init_repair_runtime(task_dir, environment, task_description, max_depth=1, *args, **kwargs):
    return repair_strategy.init_repair_runtime(
        task_dir=task_dir,
        environment=environment,
        task_description=task_description,
        strategy=RQ4_REPAIR_STRATEGY,
        max_depth=max_depth,
    )
repair_runtime_stub.action_matches = repair_strategy.action_matches
repair_runtime_stub.begin_repair = repair_strategy.begin_repair
repair_runtime_stub.end_repair = repair_strategy.end_repair
repair_runtime_stub.init_repair_runtime = _init_repair_runtime
repair_runtime_stub.record_executed_action = repair_strategy.record_executed_action
repair_runtime_stub.repair_allowed = repair_strategy.repair_allowed
repair_runtime_stub.request_repair = repair_strategy.request_repair
repair_runtime_stub.set_pending_skip_actions = repair_strategy.set_pending_skip_actions
repair_runtime_stub.should_skip_action = repair_strategy.should_skip_action
sys.modules["data.aithor_connect.repair_runtime"] = repair_runtime_stub
"""


TEMPORAL_PREDICTOR_PRELUDE_TEMPLATE = """
import pathlib
import sys
import types

PROJECT_ROOT = pathlib.Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.aithor_connect import temporal_prediction_runtime as temporal_prediction

TEMPORAL_PREDICTOR_METHOD = {method!r}

prediction_runtime_stub = types.ModuleType("data.aithor_connect.prediction_runtime")
def _init_prediction_runtime(task_dir, *args, **kwargs):
    return temporal_prediction.init_prediction_runtime(
        task_dir=task_dir,
        method=TEMPORAL_PREDICTOR_METHOD,
    )
def _record_prediction(prediction_state, pre_state, action_info):
    return temporal_prediction.record_prediction(
        prediction_state=prediction_state,
        pre_state=pre_state,
        action_info=action_info,
    )
prediction_runtime_stub.init_prediction_runtime = _init_prediction_runtime
prediction_runtime_stub.record_prediction = _record_prediction
sys.modules["data.aithor_connect.prediction_runtime"] = prediction_runtime_stub
"""


EXTERNAL_PROXY_PRELUDE_TEMPLATE = """
import json
import pathlib
import sys
import types

PROJECT_ROOT = pathlib.Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.aithor_connect import external_proxy_prediction_runtime as proxy_prediction

PROXY_BASELINE = {baseline!r}

prediction_runtime_stub = types.ModuleType("data.aithor_connect.prediction_runtime")
def _init_prediction_runtime(task_dir, *args, **kwargs):
    return proxy_prediction.init_prediction_runtime(task_dir=task_dir, baseline=PROXY_BASELINE)
def _record_prediction(prediction_state, pre_state, action_info):
    return proxy_prediction.record_prediction(
        prediction_state=prediction_state,
        pre_state=pre_state,
        action_info=action_info,
    )
prediction_runtime_stub.init_prediction_runtime = _init_prediction_runtime
prediction_runtime_stub.record_prediction = _record_prediction
sys.modules["data.aithor_connect.prediction_runtime"] = prediction_runtime_stub

# External proxy baselines are guard/intervention systems, not repair systems.
# Unsafe proxy decisions therefore block and stop the task.
repair_runtime_stub = types.ModuleType("data.aithor_connect.repair_runtime")
repair_runtime_stub.action_matches = lambda *args, **kwargs: False
repair_runtime_stub.begin_repair = lambda *args, **kwargs: None
repair_runtime_stub.end_repair = lambda *args, **kwargs: None
def _init_repair_runtime(task_dir, *args, **kwargs):
    path = pathlib.Path(task_dir) / "repair_trace.jsonl"
    path.write_text("", encoding="utf-8")
    return {{"enabled": True, "trace_path": path, "baseline": PROXY_BASELINE}}
repair_runtime_stub.record_executed_action = lambda *args, **kwargs: None
repair_runtime_stub.repair_allowed = lambda *args, **kwargs: True
def _request_repair(repair_state, pre_state, action_info, prediction_result):
    payload = {{
        "blocked_action": action_info,
        "prediction_result": prediction_result,
        "replan_result": {{
            "mode": PROXY_BASELINE,
            "reason": "external_proxy_block_only",
            "repair_actions": [],
            "retry_required": True,
        }},
        "retry_required": True,
        "repair_actions": [],
    }}
    if repair_state and repair_state.get("trace_path"):
        with repair_state["trace_path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\\n")
    return payload
repair_runtime_stub.init_repair_runtime = _init_repair_runtime
repair_runtime_stub.request_repair = _request_repair
repair_runtime_stub.set_pending_skip_actions = lambda *args, **kwargs: None
repair_runtime_stub.should_skip_action = lambda *args, **kwargs: False
sys.modules["data.aithor_connect.repair_runtime"] = repair_runtime_stub
"""


EXTERNAL_BASELINE_PRELUDE_TEMPLATE = """
import json
import pathlib
import sys
import types

PROJECT_ROOT = pathlib.Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.aithor_connect import external_baseline_prediction_runtime as baseline_prediction

EXTERNAL_BASELINE = {baseline!r}

prediction_runtime_stub = types.ModuleType("data.aithor_connect.prediction_runtime")
def _init_prediction_runtime(task_dir, *args, **kwargs):
    return baseline_prediction.init_prediction_runtime(task_dir=task_dir, baseline=EXTERNAL_BASELINE)
def _record_prediction(prediction_state, pre_state, action_info):
    return baseline_prediction.record_prediction(
        prediction_state=prediction_state,
        pre_state=pre_state,
        action_info=action_info,
    )
prediction_runtime_stub.init_prediction_runtime = _init_prediction_runtime
prediction_runtime_stub.record_prediction = _record_prediction
sys.modules["data.aithor_connect.prediction_runtime"] = prediction_runtime_stub

# External baselines are evaluated as block-only safety interventions. They do
# not call SMART-LLM/RE-EAS constrained repair, keeping our model untouched.
repair_runtime_stub = types.ModuleType("data.aithor_connect.repair_runtime")
repair_runtime_stub.action_matches = lambda *args, **kwargs: False
repair_runtime_stub.begin_repair = lambda *args, **kwargs: None
repair_runtime_stub.end_repair = lambda *args, **kwargs: None
def _init_repair_runtime(task_dir, *args, **kwargs):
    path = pathlib.Path(task_dir) / "repair_trace.jsonl"
    path.write_text("", encoding="utf-8")
    return {{"enabled": True, "trace_path": path, "baseline": EXTERNAL_BASELINE}}
repair_runtime_stub.record_executed_action = lambda *args, **kwargs: None
repair_runtime_stub.repair_allowed = lambda *args, **kwargs: True
def _request_repair(repair_state, pre_state, action_info, prediction_result):
    payload = {{
        "blocked_action": action_info,
        "prediction_result": prediction_result,
        "replan_result": {{
            "mode": EXTERNAL_BASELINE,
            "reason": "external_baseline_block_only",
            "repair_actions": [],
            "retry_required": True,
        }},
        "retry_required": True,
        "repair_actions": [],
    }}
    if repair_state and repair_state.get("trace_path"):
        with repair_state["trace_path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\\n")
    return payload
repair_runtime_stub.init_repair_runtime = _init_repair_runtime
repair_runtime_stub.request_repair = _request_repair
repair_runtime_stub.set_pending_skip_actions = lambda *args, **kwargs: None
repair_runtime_stub.should_skip_action = lambda *args, **kwargs: False
sys.modules["data.aithor_connect.repair_runtime"] = repair_runtime_stub
"""


MONITOR_ONLY_PRELUDE = """
import types
import sys

# Keep post-action RT-Lola monitoring enabled, but disable pre-action
# prediction and repair. This corresponds to the Monitor Only baseline.
prediction_runtime_stub = types.ModuleType("data.aithor_connect.prediction_runtime")
def _init_prediction_runtime(*args, **kwargs):
    return None
def _record_prediction(*args, **kwargs):
    return {
        "unsafe_probability": 0.0,
        "unsafe_label": 0,
        "confidence": 1.0,
        "prediction_set": [0],
    }
prediction_runtime_stub.init_prediction_runtime = _init_prediction_runtime
prediction_runtime_stub.record_prediction = _record_prediction
sys.modules["data.aithor_connect.prediction_runtime"] = prediction_runtime_stub

# Repair is disabled but the runtime still expects these symbols to exist.
repair_runtime_stub = types.ModuleType("data.aithor_connect.repair_runtime")
repair_runtime_stub.action_matches = lambda *args, **kwargs: False
repair_runtime_stub.begin_repair = lambda *args, **kwargs: None
repair_runtime_stub.end_repair = lambda *args, **kwargs: None
repair_runtime_stub.init_repair_runtime = lambda *args, **kwargs: None
repair_runtime_stub.record_executed_action = lambda *args, **kwargs: None
repair_runtime_stub.repair_allowed = lambda *args, **kwargs: False
repair_runtime_stub.request_repair = lambda *args, **kwargs: None
repair_runtime_stub.set_pending_skip_actions = lambda *args, **kwargs: None
repair_runtime_stub.should_skip_action = lambda *args, **kwargs: False
sys.modules["data.aithor_connect.repair_runtime"] = repair_runtime_stub
"""


NO_RUNTIME_MONITOR_PRELUDE = """
import types
import sys

# True w/o runtime monitoring ablation. The monitoring sidecar is unavailable,
# so prediction and repair cannot consume monitored pre-state and are inactive.
sys.modules["monitor_runtime"] = types.ModuleType("monitor_runtime")
sys.modules["data.aithor_connect.prediction_runtime"] = types.ModuleType(
    "data.aithor_connect.prediction_runtime"
)
sys.modules["data.aithor_connect.repair_runtime"] = types.ModuleType(
    "data.aithor_connect.repair_runtime"
)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "full",
            "no_repair",
            "prediction_only",
            "monitor_only",
            "no_runtime_monitor",
            "multidimspci_repair",
            "cptc_repair",
            "random_action_repair",
            "random_allowable_repair",
            "rule_based_repair",
            "unconstrained_llm_repair",
            "roboguard_proxy",
            "autort_proxy",
            "agentspec_proxy",
            "pro2guard_proxy",
            "probguard_proxy",
            "safeembodai_proxy",
            "trustagent_proxy",
            "roboguard_adapted",
            "autort_paper",
            "agentspec_adapted",
            "pro2guard_adapted",
            "probguard_adapted",
            "safeembodai_paper",
            "trustagent_adapted",
        ],
        required=True,
    )
    parser.add_argument("--display", type=str, default=":0.0")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--deepseek-api-key-file", type=str, default="DEEPSEEK_API_KEY")
    parser.add_argument("--summary-file", type=Path, default=None)
    parser.add_argument("--planner-only", action="store_true")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--log-root", type=Path, default=LOGS_DIR)
    return parser.parse_args()


def load_tasks(path: Path) -> List[Dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"No tasks found in {path}")
    return tasks


def build_temp_input(task: Dict[str, str]) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    with handle:
        json.dump(
            [{"task": task["task"], "floor_plan": task["floor_plan"]}],
            handle,
            ensure_ascii=False,
            indent=2,
        )
    return Path(handle.name)


def resolve_log_root(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def list_log_dirs(log_root: Path) -> set[str]:
    if not log_root.exists():
        return set()
    return {path.name for path in log_root.iterdir() if path.is_dir()}


def detect_new_log_dir(log_root: Path, before: set[str], after: set[str]) -> Path:
    new_dirs = sorted(after - before)
    if len(new_dirs) != 1:
        raise RuntimeError(f"Expected 1 new log directory, found {len(new_dirs)}: {new_dirs}")
    return log_root / new_dirs[0]


def run_planner(task: Dict[str, str], args: argparse.Namespace, env: Dict[str, str]) -> Dict[str, object]:
    temp_input = build_temp_input(task)
    log_root = resolve_log_root(args.log_root)
    log_root.mkdir(parents=True, exist_ok=True)
    before = list_log_dirs(log_root)
    started = time.perf_counter()
    try:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_llm.py"),
            "--input-file",
            str(temp_input),
            "--model",
            args.model,
            "--deepseek-api-key-file",
            args.deepseek_api_key_file,
            "--log-root",
            str(log_root),
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        elapsed = time.perf_counter() - started
        after = list_log_dirs(log_root)
        return {
            "log_dir": detect_new_log_dir(log_root, before, after),
            "planner_elapsed_seconds": round(float(elapsed), 6),
        }
    finally:
        temp_input.unlink(missing_ok=True)


def extract_prefixed_value(log_lines: Sequence[str], prefix: str) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    raise ValueError(f"Missing log field with prefix: {prefix}")


def parse_floor_number(floor_plan_value: str) -> str:
    normalized = floor_plan_value.replace("FloorPlan", "")
    if "_" in normalized:
        return normalized.split("_")[0]
    return normalized


def parse_robot_from_log(log_lines: Sequence[str]):
    robot_expr = extract_prefixed_value(log_lines, "robot =")
    return ast.literal_eval(robot_expr)


def parse_task_description(log_lines: Sequence[str]) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped:
            return stripped
    raise ValueError("Cannot parse task description from log.txt")


def compile_executable(log_dir: Path, display: str, mode: str) -> Path:
    import_file = IMPORTS_FILE.read_text(encoding="utf-8")
    import_file = import_file.replace(
        "os.environ['DISPLAY'] = ':99'",
        f'os.environ["DISPLAY"] = os.environ.get("DISPLAY", "{display}")',
    )

    log_lines = (log_dir / "log.txt").read_text(encoding="utf-8").splitlines()
    floor_plan_value = extract_prefixed_value(log_lines, "Floor Plan:")
    floor_no = parse_floor_number(floor_plan_value)
    robot = parse_robot_from_log(log_lines)
    task_description = parse_task_description(log_lines)
    runtime_file = RUNTIME_FILE.read_text(encoding="utf-8")
    code_plan = (log_dir / "code_plan.py").read_text(encoding="utf-8")
    end_file = END_FILE.read_text(encoding="utf-8")

    prelude = ""
    normalized_mode = normalize_mode(mode)
    if normalized_mode == "prediction_only":
        prelude = NO_REPAIR_PRELUDE
    elif normalized_mode == "monitor_only":
        prelude = MONITOR_ONLY_PRELUDE
    elif normalized_mode == "no_runtime_monitor":
        prelude = NO_RUNTIME_MONITOR_PRELUDE
    elif normalized_mode in TEMPORAL_PREDICTOR_MODES:
        prelude = TEMPORAL_PREDICTOR_PRELUDE_TEMPLATE.format(
            method=TEMPORAL_PREDICTOR_METHODS[normalized_mode]
        )
    elif normalized_mode in RQ4_REPAIR_MODES:
        prelude = RQ4_REPAIR_PRELUDE_TEMPLATE.format(
            strategy=RQ4_REPAIR_STRATEGIES[normalized_mode]
        )
    elif normalized_mode in EXTERNAL_PROXY_MODES:
        prelude = EXTERNAL_PROXY_PRELUDE_TEMPLATE.format(baseline=normalized_mode)
    elif normalized_mode in EXTERNAL_BASELINE_MODES:
        prelude = EXTERNAL_BASELINE_PRELUDE_TEMPLATE.format(baseline=normalized_mode)

    executable_parts = [
        import_file,
        prelude,
        f"floor_no = {floor_no}",
        f"task_description = {task_description!r}",
        f"robot = {robot!r}",
        "robots = [robot]\n",
        runtime_file,
        DISABLE_VISUAL_ARTIFACTS_PATCH,
        code_plan,
        end_file,
    ]

    suffix = mode_suffix(normalized_mode)
    executable_path = log_dir / f"executable_plan_{suffix}.py"
    executable_path.write_text("\n".join(executable_parts), encoding="utf-8")
    return executable_path


def normalize_mode(mode: str) -> str:
    """Return the canonical experiment mode name."""
    if mode == "no_repair":
        return "prediction_only"
    if mode == "pro2guard_proxy":
        return "probguard_proxy"
    if mode == "pro2guard_adapted":
        return "probguard_adapted"
    return mode


def mode_suffix(mode: str) -> str:
    """Return stable file-name suffixes for generated executable/log files."""
    if mode == "prediction_only":
        return "prediction_only"
    return mode


def execute_generated_task(log_dir: Path, mode: str, display: str, env: Dict[str, str]) -> Dict[str, object]:
    executable_path = compile_executable(log_dir, display, mode)
    normalized_mode = normalize_mode(mode)
    suffix = mode_suffix(normalized_mode)
    execution_log_path = log_dir / f"execution_{suffix}.log"
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(executable_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    execution_log_path.write_text(
        "STDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr,
        encoding="utf-8",
    )
    cleanup_visual_artifacts(log_dir)
    return {
        "returncode": int(proc.returncode),
        "elapsed_seconds": round(float(elapsed), 6),
        "execution_log": str(execution_log_path),
        "executable": str(executable_path),
    }


def cleanup_visual_artifacts(log_dir: Path) -> None:
    """Remove visual artifacts from batch experiments."""
    for folder_name in ("agent_1", "top_view"):
        folder_path = log_dir / folder_name
        if folder_path.exists():
            shutil.rmtree(folder_path, ignore_errors=True)
    for video_path in log_dir.glob("video_*.mp4"):
        try:
            video_path.unlink()
        except OSError:
            pass


def trace_file_status(log_dir: Path) -> Dict[str, bool]:
    return {
        "monitor_trace_exists": (log_dir / "monitor_trace.csv").exists(),
        "prediction_trace_exists": (log_dir / "prediction_trace.csv").exists(),
        "repair_trace_exists": (log_dir / "repair_trace.jsonl").exists(),
    }


def read_retry_reason(log_dir: Path) -> str:
    trace_path = log_dir / "repair_trace.jsonl"
    if not trace_path.exists():
        return ""
    reason = ""
    try:
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            replan_result = payload.get("replan_result", {})
            if replan_result.get("retry_required"):
                reason = str(replan_result.get("reason", "retry_required"))
    except Exception:
        return ""
    return reason


def append_summary_line(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    mode = normalize_mode(args.mode)
    tasks = load_tasks(args.task_file)
    selected = tasks[args.start:]
    if args.limit is not None:
        selected = selected[: args.limit]

    summary_path = args.summary_file
    if summary_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = ROOT / "logs" / f"{mode}_batch_summary_{stamp}.jsonl"

    env = dict(os.environ)
    env["DISPLAY"] = args.display

    for idx, task in enumerate(selected, start=1):
        result: Dict[str, object] = {
            "task_id": task["id"],
            "task": task["task"],
            "floor_plan": task["floor_plan"],
            "mode": mode,
            "requested_mode": args.mode,
            "display": args.display,
            "planner_status": "not_started",
            "execution_status": "not_started",
            "retry_count": 0,
            "execution_attempts": [],
        }
        try:
            max_retries = max(0, int(args.max_retries))
            max_attempts = 1 if args.planner_only or mode != "full" else max_retries + 1

            for attempt_index in range(max_attempts):
                planner_result = run_planner(task, args, env)
                log_dir = Path(str(planner_result["log_dir"]))
                planner_elapsed_seconds = float(planner_result["planner_elapsed_seconds"])
                result["planner_status"] = "ok"
                result["log_dir"] = str(log_dir)
                attempt_payload: Dict[str, object] = {
                    "attempt": attempt_index + 1,
                    "log_dir": str(log_dir),
                    "planner_elapsed_seconds": planner_elapsed_seconds,
                }
                result["execution_attempts"].append(attempt_payload)

                if args.planner_only:
                    attempt_payload["execution_status"] = "skipped"
                    result["execution_status"] = "skipped"
                    result["planner_elapsed_seconds"] = planner_elapsed_seconds
                    result["total_elapsed_seconds"] = planner_elapsed_seconds
                    break

                execution_result = execute_generated_task(log_dir, mode, args.display, env)
                return_code = int(execution_result["returncode"])
                attempt_payload.update(execution_result)
                attempt_payload["execution_returncode"] = return_code
                attempt_payload["execution_elapsed_seconds"] = execution_result.get("elapsed_seconds")
                attempt_payload["total_elapsed_seconds"] = round(
                    planner_elapsed_seconds + float(execution_result.get("elapsed_seconds", 0.0)),
                    6,
                )
                attempt_payload.update(trace_file_status(log_dir))

                if return_code == UNRECOVERABLE_REPAIR_EXIT_CODE and mode == "full":
                    retry_reason = read_retry_reason(log_dir) or "unrecoverable_repair"
                    attempt_payload["execution_status"] = "retry_required"
                    attempt_payload["retry_reason"] = retry_reason
                    result["retry_reason"] = retry_reason
                    result["retry_count"] = attempt_index
                    if attempt_index < max_attempts - 1:
                        continue
                    result["execution_returncode"] = return_code
                    result["execution_status"] = "retry_exhausted"
                    result["planner_elapsed_seconds"] = planner_elapsed_seconds
                    result["execution_elapsed_seconds"] = execution_result.get("elapsed_seconds")
                    result["total_elapsed_seconds"] = attempt_payload["total_elapsed_seconds"]
                    result.update(trace_file_status(log_dir))
                    break

                attempt_payload["execution_status"] = "ok" if return_code == 0 else "failed"
                result["execution_returncode"] = return_code
                result["execution_status"] = attempt_payload["execution_status"]
                result["retry_count"] = attempt_index
                result["planner_elapsed_seconds"] = planner_elapsed_seconds
                result["execution_elapsed_seconds"] = execution_result.get("elapsed_seconds")
                result["total_elapsed_seconds"] = attempt_payload["total_elapsed_seconds"]
                result.update(trace_file_status(log_dir))
                break
        except subprocess.CalledProcessError as exc:
            result["planner_status"] = "failed"
            result["execution_status"] = "skipped"
            result["error"] = f"subprocess failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
            if result["planner_status"] == "not_started":
                result["planner_status"] = "failed"
                result["execution_status"] = "skipped"
            elif result["execution_status"] == "not_started":
                result["execution_status"] = "failed"

        append_summary_line(summary_path, result)
        print(
            f"[{idx}/{len(selected)}] {task['id']} "
            f"planner={result['planner_status']} "
            f"execution={result['execution_status']}"
        )

    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
