"""Batch runner for baseline experiments without monitoring/prediction/repair.

This script consumes one of the balanced task JSON files and runs the full
planner + execution pipeline for each task while explicitly disabling the
SMART-LLM safety sidecars. It is intended for the baseline branch of the paper
experiments.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"
IMPORTS_FILE = ROOT / "data" / "aithor_connect" / "imports_aux_fn.py"
RUNTIME_FILE = ROOT / "data" / "aithor_connect" / "runtime_minimal.py"
END_FILE = ROOT / "data" / "aithor_connect" / "end_minimal.py"


STUB_PRELUDE = """
import types
import sys

# Disable SMART-LLM safety sidecars for baseline execution.
sys.modules["monitor_runtime"] = types.ModuleType("monitor_runtime")
sys.modules["data.aithor_connect.prediction_runtime"] = types.ModuleType("data.aithor_connect.prediction_runtime")
sys.modules["data.aithor_connect.repair_runtime"] = types.ModuleType("data.aithor_connect.repair_runtime")
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--display", type=str, default=":0.0")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--deepseek-api-key-file", type=str, default="DEEPSEEK_API_KEY")
    parser.add_argument("--summary-file", type=Path, default=None)
    parser.add_argument("--planner-only", action="store_true")
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
        json.dump([{"task": task["task"], "floor_plan": task["floor_plan"]}], handle, ensure_ascii=False, indent=2)
    return Path(handle.name)


def list_log_dirs() -> set[str]:
    if not LOGS_DIR.exists():
        return set()
    return {p.name for p in LOGS_DIR.iterdir() if p.is_dir()}


def detect_new_log_dir(before: set[str], after: set[str]) -> Path:
    new_dirs = sorted(after - before)
    if len(new_dirs) != 1:
        raise RuntimeError(f"Expected 1 new log directory, found {len(new_dirs)}: {new_dirs}")
    return LOGS_DIR / new_dirs[0]


def run_planner(task: Dict[str, str], args: argparse.Namespace, env: Dict[str, str]) -> Path:
    temp_input = build_temp_input(task)
    before = list_log_dirs()
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
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True)
        after = list_log_dirs()
        return detect_new_log_dir(before, after)
    finally:
        temp_input.unlink(missing_ok=True)


def compile_baseline_executable(log_dir: Path, display: str) -> Path:
    import_file = IMPORTS_FILE.read_text(encoding="utf-8")
    import_file = import_file.replace(
        "os.environ['DISPLAY'] = ':99'",
        "os.environ['DISPLAY'] = os.environ.get('DISPLAY', %r)" % display,
    )

    runtime_file = RUNTIME_FILE.read_text(encoding="utf-8")
    log_lines = (log_dir / "log.txt").read_text(encoding="utf-8").splitlines()
    floor_plan_value = extract_prefixed_value(log_lines, "Floor Plan:")
    floor_no = parse_floor_number(floor_plan_value)
    robot = parse_robot_from_log(log_lines)
    task_description = parse_task_description(log_lines)
    code_plan = (log_dir / "code_plan.py").read_text(encoding="utf-8")
    end_file = END_FILE.read_text(encoding="utf-8")

    executable_plan = []
    executable_plan.append(import_file)
    executable_plan.append(STUB_PRELUDE)
    executable_plan.append(f"floor_no = {floor_no!s}")
    executable_plan.append(f"task_description = {task_description!r}")
    executable_plan.append(f"robot = {robot!r}")
    executable_plan.append("robots = [robot]\n")
    executable_plan.append(runtime_file)
    executable_plan.append(code_plan)
    executable_plan.append(end_file)

    executable_path = log_dir / "executable_plan_baseline.py"
    executable_path.write_text("\n".join(executable_plan), encoding="utf-8")
    return executable_path


def run_baseline_execution(log_dir: Path, display: str, env: Dict[str, str]) -> int:
    executable_path = compile_baseline_executable(log_dir, display)
    proc = subprocess.run([sys.executable, str(executable_path)], cwd=ROOT, env=env, check=False)
    return int(proc.returncode)


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
    import ast

    robot_expr = extract_prefixed_value(log_lines, "robot =")
    return ast.literal_eval(robot_expr)


def parse_task_description(log_lines: Sequence[str]) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped:
            return stripped
    raise ValueError("Cannot parse task description from log.txt")


def append_summary_line(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    tasks = load_tasks(args.task_file)
    selected = tasks[args.start:]
    if args.limit is not None:
        selected = selected[: args.limit]

    summary_path = args.summary_file
    if summary_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_path = ROOT / "logs" / f"baseline_batch_summary_{stamp}.jsonl"

    env = dict(os.environ)
    env["DISPLAY"] = args.display

    for idx, task in enumerate(selected, start=1):
        result: Dict[str, object] = {
            "task_id": task["id"],
            "task": task["task"],
            "floor_plan": task["floor_plan"],
            "display": args.display,
            "planner_status": "not_started",
            "execution_status": "not_started",
        }
        try:
            log_dir = run_planner(task, args, env)
            result["planner_status"] = "ok"
            result["log_dir"] = str(log_dir)
            if args.planner_only:
                result["execution_status"] = "skipped"
            else:
                return_code = run_baseline_execution(log_dir, args.display, env)
                result["execution_returncode"] = return_code
                result["execution_status"] = "ok" if return_code == 0 else "failed"
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
        print(f"[{idx}/{len(selected)}] {task['id']} planner={result['planner_status']} execution={result['execution_status']}")

    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
