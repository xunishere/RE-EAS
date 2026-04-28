"""Execute existing log tasks with monitoring enabled and prediction/repair disabled.

This runner scans the `logs/` directory, rebuilds an executable plan for each
task directory, and runs it in a monitor-only mode. It preserves monitoring
artifacts such as `monitor_trace.csv`, `rtlola_stream.csv`, and visual outputs,
while disabling prediction and repair sidecars.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
IMPORTS_FILE = ROOT / "data" / "aithor_connect" / "imports_aux_fn.py"
RUNTIME_FILE = ROOT / "data" / "aithor_connect" / "runtime_minimal.py"
END_FILE = ROOT / "data" / "aithor_connect" / "end_minimal.py"


MONITOR_ONLY_PRELUDE = """
import types
import sys

# Prediction is disabled but monitor remains enabled.
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--display", type=str, default=":0.0")
    parser.add_argument("--logs-dir", type=Path, default=LOGS_DIR)
    parser.add_argument("--contains", type=str, default=None)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--summary-file", type=Path, default=None)
    return parser.parse_args()


def find_task_dirs(logs_dir: Path, contains: str | None) -> List[Path]:
    task_dirs = [path for path in logs_dir.iterdir() if path.is_dir()]
    task_dirs.sort(key=lambda path: path.name)
    if contains:
        task_dirs = [path for path in task_dirs if contains in path.name]
    return task_dirs


def extract_prefixed_value(log_lines: Iterable[str], prefix: str) -> str:
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


def parse_robot_from_log(log_lines: List[str]):
    robot_expr = extract_prefixed_value(log_lines, "robot =")
    return ast.literal_eval(robot_expr)


def parse_task_description(log_lines: List[str]) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped:
            return stripped
    raise ValueError("Cannot parse task description from log.txt")


def compile_monitor_only_executable(log_dir: Path, display: str) -> Path:
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

    executable_parts = [
        import_file,
        MONITOR_ONLY_PRELUDE,
        f"floor_no = {floor_no}",
        f"task_description = {task_description!r}",
        f"robot = {robot!r}",
        "robots = [robot]\n",
        runtime_file,
        code_plan,
        end_file,
    ]
    executable_path = log_dir / "executable_plan_monitor_only.py"
    executable_path.write_text("\n".join(executable_parts), encoding="utf-8")
    return executable_path


def append_summary_line(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    task_dirs = find_task_dirs(args.logs_dir, args.contains)
    selected = task_dirs[args.start:]
    if args.limit is not None:
        selected = selected[: args.limit]

    summary_path = args.summary_file
    if summary_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = ROOT / "logs" / f"monitor_only_summary_{stamp}.jsonl"

    env = dict(os.environ)
    env["DISPLAY"] = args.display

    for idx, log_dir in enumerate(selected, start=1):
        payload: Dict[str, object] = {
            "log_dir": str(log_dir),
            "task_name": log_dir.name,
            "display": args.display,
            "status": "not_started",
        }
        try:
            executable_path = compile_monitor_only_executable(log_dir, args.display)
            proc = subprocess.run(
                [sys.executable, str(executable_path)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            payload["returncode"] = int(proc.returncode)
            payload["status"] = "ok" if proc.returncode == 0 else "failed"
            payload["monitor_trace_exists"] = (log_dir / "monitor_trace.csv").exists()
            payload["rtlola_stream_exists"] = (log_dir / "rtlola_stream.csv").exists()
            payload["prediction_trace_exists"] = (log_dir / "prediction_trace.csv").exists()
            payload["repair_trace_exists"] = (log_dir / "repair_trace.jsonl").exists()
        except Exception as exc:  # noqa: BLE001
            payload["status"] = "failed"
            payload["error"] = str(exc)

        append_summary_line(summary_path, payload)
        print(
            f"[{idx}/{len(selected)}] {log_dir.name} "
            f"status={payload['status']} "
            f"monitor={payload.get('monitor_trace_exists', False)} "
            f"rtlola={payload.get('rtlola_stream_exists', False)}"
        )

    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
