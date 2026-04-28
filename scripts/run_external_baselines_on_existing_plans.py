"""Run external baselines on already-generated plans.

This runner avoids calling `run_llm.py`. It reuses successful `code_plan.py`
directories from existing batch summaries and executes each external baseline
on the same fixed plans, which is the fair comparison setting for safety gates.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from run_batch_pipeline import execute_generated_task, trace_file_status


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"


REQUIRED_PLAN_FILES = ("log.txt", "code_plan.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-summary", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "roboguard_adapted",
            "agentspec_adapted",
            "probguard_adapted",
            "trustagent_adapted",
            "autort_paper",
            "safeembodai_paper",
        ],
        required=True,
    )
    parser.add_argument("--display", type=str, default=":0.0")
    parser.add_argument("--summary-file", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=0)
    return parser.parse_args()


def iter_summary_rows(paths: Iterable[Path]) -> Iterable[Dict[str, object]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def select_plan_rows(paths: Iterable[Path]) -> List[Dict[str, object]]:
    """Return one successful generated plan per task id."""
    selected: Dict[str, Dict[str, object]] = {}
    for row in iter_summary_rows(paths):
        if row.get("planner_status") != "ok":
            continue
        log_dir = row.get("log_dir")
        attempts = row.get("execution_attempts")
        if not log_dir and isinstance(attempts, list) and attempts:
            log_dir = attempts[-1].get("log_dir")
        if not log_dir:
            continue
        log_path = Path(str(log_dir))
        if not log_path.is_absolute():
            log_path = ROOT / log_path
        if not all((log_path / name).exists() for name in REQUIRED_PLAN_FILES):
            continue
        task_id = str(row.get("task_id", ""))
        if not task_id or task_id in selected:
            continue
        copied = dict(row)
        copied["log_dir"] = str(log_path)
        selected[task_id] = copied
    return [selected[key] for key in sorted(selected)]


def source_planner_time(row: Dict[str, object]) -> float:
    value = row.get("planner_elapsed_seconds")
    if value not in (None, ""):
        return float(value)
    attempts = row.get("execution_attempts")
    if isinstance(attempts, list) and attempts:
        value = attempts[-1].get("planner_elapsed_seconds")
        if value not in (None, ""):
            return float(value)
    return 0.0


def prepare_plan_dir(source_dir: Path, output_root: Path, mode: str, task_id: str) -> Path:
    target_dir = output_root / mode / task_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_PLAN_FILES:
        shutil.copy2(source_dir / name, target_dir / name)
    for optional_name in ("raw_code_plan.py", "decomposed_plan.py", "validation_report.json"):
        optional_path = source_dir / optional_name
        if optional_path.exists():
            shutil.copy2(optional_path, target_dir / optional_name)
    return target_dir


def append_summary_line(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = args.summary_file or LOGS_DIR / f"{args.mode}_existing_plans_{stamp}_summary.jsonl"
    output_root = args.output_root or LOGS_DIR / f"existing_plan_runs_{stamp}"

    rows = select_plan_rows(args.source_summary)
    rows = rows[args.start:]
    if args.limit is not None:
        rows = rows[: args.limit]

    env = dict(os.environ)
    env["DISPLAY"] = args.display
    env["PATH"] = "/root/.cargo/bin:" + env.get("PATH", "")

    for idx, row in enumerate(rows, start=1):
        task_id = str(row.get("task_id", f"task_{idx:04d}"))
        result: Dict[str, object] = {
            "task_id": task_id,
            "task": row.get("task", ""),
            "floor_plan": row.get("floor_plan", ""),
            "mode": args.mode,
            "source_log_dir": row.get("log_dir", ""),
            "planner_status": "reused_existing_plan",
            "planner_elapsed_seconds": source_planner_time(row),
            "execution_status": "not_started",
            "execution_attempts": [],
        }
        try:
            source_dir = Path(str(row["log_dir"]))
            plan_dir = prepare_plan_dir(source_dir, output_root, args.mode, task_id)
            execution_result = execute_generated_task(plan_dir, args.mode, args.display, env)
            return_code = int(execution_result["returncode"])
            attempt = {
                "attempt": 1,
                "log_dir": str(plan_dir),
                "planner_elapsed_seconds": result["planner_elapsed_seconds"],
                **execution_result,
                "execution_returncode": return_code,
            }
            attempt["execution_elapsed_seconds"] = execution_result.get("elapsed_seconds")
            attempt["total_elapsed_seconds"] = round(
                float(result["planner_elapsed_seconds"]) + float(execution_result.get("elapsed_seconds", 0.0)),
                6,
            )
            attempt.update(trace_file_status(plan_dir))
            result["execution_attempts"].append(attempt)
            result["log_dir"] = str(plan_dir)
            result["execution_returncode"] = return_code
            result["execution_status"] = "ok" if return_code == 0 else "failed"
            result["execution_elapsed_seconds"] = execution_result.get("elapsed_seconds")
            result["total_elapsed_seconds"] = attempt["total_elapsed_seconds"]
            result.update(trace_file_status(plan_dir))
        except Exception as exc:  # noqa: BLE001
            result["execution_status"] = "failed"
            result["error"] = str(exc)
        append_summary_line(summary_file, result)
        print(f"[{idx}/{len(rows)}] {task_id} execution={result['execution_status']}")

    print(f"Summary written to {summary_file}")


if __name__ == "__main__":
    main()
