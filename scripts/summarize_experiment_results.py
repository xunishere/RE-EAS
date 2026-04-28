"""Summarize SMART-LLM experiment logs into task-level metrics.

This helper consumes one or more `*_batch_summary_*.jsonl` files produced by
`run_batch_baseline.py` or `run_batch_pipeline.py`, then reads each task log
directory to collect the fields needed by the paper tables:

- task completion and execution status
- post-action RT-Lola violation counts
- pre-action prediction/repair-trigger counts
- repair attempts and failure reasons
- elapsed runtime and generated execution logs

The script intentionally does not recompute low-level safety labels; it only
aggregates artifacts already written by the experiment runners.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary_files", nargs="+", type=Path)
    parser.add_argument("--output-jsonl", type=Path, default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    return parser.parse_args()


def iter_summary_rows(paths: Iterable[Path]) -> Iterable[Dict[str, object]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                payload["_summary_file"] = str(path)
                payload["_summary_line"] = line_no
                yield payload


def summarize_one(row: Dict[str, object]) -> Dict[str, object]:
    attempt = select_final_attempt(row)
    log_dir = Path(str(attempt.get("log_dir") or row.get("log_dir") or ""))
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir

    mode = str(row.get("mode") or row.get("requested_mode") or "direct")
    execution_log = Path(str(attempt.get("execution_log", ""))) if attempt.get("execution_log") else None
    if execution_log and not execution_log.is_absolute():
        execution_log = ROOT / execution_log

    monitor_metrics = summarize_monitor_trace(log_dir / "monitor_trace.csv")
    prediction_metrics = summarize_prediction_trace(log_dir / "prediction_trace.csv")
    repair_metrics = summarize_repair_trace(log_dir / "repair_trace.jsonl")
    execution_metrics = summarize_execution_log(execution_log)

    elapsed_seconds = attempt.get("elapsed_seconds")
    if elapsed_seconds is None:
        elapsed_seconds = row.get("elapsed_seconds")
    execution_elapsed_seconds = attempt.get("execution_elapsed_seconds")
    if execution_elapsed_seconds is None:
        execution_elapsed_seconds = row.get("execution_elapsed_seconds", elapsed_seconds)
    planner_elapsed_seconds = attempt.get("planner_elapsed_seconds")
    if planner_elapsed_seconds is None:
        planner_elapsed_seconds = row.get("planner_elapsed_seconds", "")
    total_elapsed_seconds = attempt.get("total_elapsed_seconds")
    if total_elapsed_seconds is None:
        total_elapsed_seconds = row.get("total_elapsed_seconds", "")
    if total_elapsed_seconds in (None, ""):
        total_elapsed_seconds = sum_known_seconds(planner_elapsed_seconds, execution_elapsed_seconds)

    return {
        "summary_file": row.get("_summary_file", ""),
        "summary_line": row.get("_summary_line", ""),
        "task_id": row.get("task_id", ""),
        "task": row.get("task", ""),
        "floor_plan": row.get("floor_plan", ""),
        "mode": mode,
        "planner_status": row.get("planner_status", ""),
        "execution_status": row.get("execution_status") or row.get("status", ""),
        "execution_returncode": attempt.get("execution_returncode", row.get("execution_returncode", "")),
        "elapsed_seconds": elapsed_seconds if elapsed_seconds is not None else "",
        "planner_elapsed_seconds": planner_elapsed_seconds if planner_elapsed_seconds is not None else "",
        "execution_elapsed_seconds": execution_elapsed_seconds if execution_elapsed_seconds is not None else "",
        "total_elapsed_seconds": total_elapsed_seconds if total_elapsed_seconds is not None else "",
        "log_dir": str(log_dir),
        "execution_log": str(execution_log) if execution_log else "",
        **execution_metrics,
        **monitor_metrics,
        **prediction_metrics,
        **repair_metrics,
    }


def select_final_attempt(row: Dict[str, object]) -> Dict[str, object]:
    attempts = row.get("execution_attempts")
    if isinstance(attempts, list) and attempts:
        return dict(attempts[-1])
    return dict(row)


def summarize_monitor_trace(path: Path) -> Dict[str, object]:
    metrics = {
        "monitor_trace_exists": path.exists(),
        "monitor_steps": 0,
        "unsafe_steps": 0,
        "final_unsafe": False,
        "safety_violation_rate": "",
    }
    if not path.exists():
        return metrics

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    metrics["monitor_steps"] = len(rows)
    unsafe_steps = sum(1 for row in rows if bool_text(row.get("unsafe", "")))
    metrics["unsafe_steps"] = unsafe_steps
    metrics["final_unsafe"] = bool_text(rows[-1].get("unsafe", "")) if rows else False
    metrics["safety_violation_rate"] = round(unsafe_steps / len(rows), 6) if rows else ""
    return metrics


def summarize_prediction_trace(path: Path) -> Dict[str, object]:
    metrics = {
        "prediction_trace_exists": path.exists(),
        "prediction_steps": 0,
        "repair_trigger_count": 0,
        "avg_unsafe_probability": "",
        "max_unsafe_probability": "",
        "proxy_baselines": "",
        "proxy_reasons": "",
        "baseline_models": "",
        "baseline_variants": "",
        "baseline_reasons": "",
        "baseline_source_status": "",
    }
    if not path.exists():
        return metrics

    probs: List[float] = []
    trigger_count = 0
    proxy_baselines: Dict[str, int] = {}
    proxy_reasons: Dict[str, int] = {}
    baseline_models: Dict[str, int] = {}
    baseline_variants: Dict[str, int] = {}
    baseline_reasons: Dict[str, int] = {}
    baseline_source_status: Dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            metrics["prediction_steps"] += 1
            if bool_text(row.get("pred_unsafe_label", "")):
                trigger_count += 1
            proxy_baseline = str(row.get("proxy_baseline", "")).strip()
            if proxy_baseline:
                proxy_baselines[proxy_baseline] = proxy_baselines.get(proxy_baseline, 0) + 1
            proxy_reason = str(row.get("proxy_reason", "")).strip()
            if proxy_reason:
                proxy_reasons[proxy_reason] = proxy_reasons.get(proxy_reason, 0) + 1
            baseline_model = str(row.get("baseline_model", "")).strip()
            if baseline_model:
                baseline_models[baseline_model] = baseline_models.get(baseline_model, 0) + 1
            baseline_variant = str(row.get("baseline_variant", "")).strip()
            if baseline_variant:
                baseline_variants[baseline_variant] = baseline_variants.get(baseline_variant, 0) + 1
            baseline_reason = str(row.get("baseline_reason", "")).strip()
            if baseline_reason:
                baseline_reasons[baseline_reason] = baseline_reasons.get(baseline_reason, 0) + 1
            source_status = str(row.get("source_status", "")).strip()
            if source_status:
                baseline_source_status[source_status] = baseline_source_status.get(source_status, 0) + 1
            prob = maybe_float(row.get("pred_unsafe_probability", ""))
            if prob is not None:
                probs.append(prob)

    metrics["repair_trigger_count"] = trigger_count
    if probs:
        metrics["avg_unsafe_probability"] = round(sum(probs) / len(probs), 6)
        metrics["max_unsafe_probability"] = round(max(probs), 6)
    metrics["proxy_baselines"] = compact_counts(proxy_baselines)
    metrics["proxy_reasons"] = compact_counts(proxy_reasons)
    metrics["baseline_models"] = compact_counts(baseline_models)
    metrics["baseline_variants"] = compact_counts(baseline_variants)
    metrics["baseline_reasons"] = compact_counts(baseline_reasons)
    metrics["baseline_source_status"] = compact_counts(baseline_source_status)
    return metrics


def summarize_repair_trace(path: Path) -> Dict[str, object]:
    metrics = {
        "repair_trace_exists": path.exists(),
        "repair_attempts": 0,
        "repair_actions_total": 0,
        "repair_retry_required": 0,
        "repair_modes": "",
        "repair_failure_reasons": "",
    }
    if not path.exists():
        return metrics

    modes: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            metrics["repair_attempts"] += 1
            actions = payload.get("repair_actions", [])
            if isinstance(actions, list):
                metrics["repair_actions_total"] += len(actions)
            replan = payload.get("replan_result", {})
            mode = str(replan.get("mode", "unknown"))
            reason = str(replan.get("reason", ""))
            modes[mode] = modes.get(mode, 0) + 1
            if replan.get("retry_required") or payload.get("retry_required"):
                metrics["repair_retry_required"] += 1
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1

    metrics["repair_modes"] = compact_counts(modes)
    metrics["repair_failure_reasons"] = compact_counts(reasons)
    return metrics


def summarize_execution_log(path: Optional[Path]) -> Dict[str, object]:
    metrics = {
        "task_action_total": "",
        "task_action_success": "",
        "task_action_failed": "",
        "task_sr": "",
        "database_update": "",
    }
    if not path or not path.exists():
        return metrics

    text = path.read_text(encoding="utf-8", errors="replace")
    for key in ["task_action_total", "task_action_success", "task_action_failed"]:
        match = re.search(rf"{key}=([0-9]+)", text)
        if match:
            metrics[key] = int(match.group(1))
    sr_match = re.search(r"SR:([0-9.]+)", text)
    if sr_match:
        metrics["task_sr"] = float(sr_match.group(1))
    db_match = re.search(r"database_update=(.+)", text)
    if db_match:
        metrics["database_update"] = db_match.group(1).strip()
    return metrics


def bool_text(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def maybe_float(value: object) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def sum_known_seconds(*values: object) -> object:
    total = 0.0
    seen = False
    for value in values:
        number = maybe_float(value)
        if number is None:
            continue
        total += number
        seen = True
    return round(total, 6) if seen else ""


def compact_counts(counts: Dict[str, int]) -> str:
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


def write_outputs(rows: List[Dict[str, object]], output_jsonl: Optional[Path], output_csv: Optional[Path]) -> None:
    if output_jsonl:
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with output_jsonl.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = sorted({key for row in rows for key in row})
        with output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows = [summarize_one(row) for row in iter_summary_rows(args.summary_files)]
    write_outputs(rows, args.output_jsonl, args.output_csv)
    print(json.dumps({"rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
