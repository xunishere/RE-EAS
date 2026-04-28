"""Collect monitor traces from logs and overwrite the training CSV.

This script scans task directories under `logs/`, reads each `monitor_trace.csv`,
keeps only the prefix up to and including the first unsafe row, enriches rows
with `task_id` and `step_id`, and writes the merged dataset to a single CSV.

By default, the output overwrites `prediction/data/splits/train.csv`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS_DIR = ROOT / "logs"
DEFAULT_OUTPUT = ROOT / "prediction" / "data" / "splits" / "train.csv"
DEFAULT_BACKUP = ROOT / "prediction" / "data" / "splits" / "train.csv.bak"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-dir", type=Path, default=DEFAULT_LOGS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--contains", type=str, default=None)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--no-backup", action="store_true")
    return parser.parse_args()


def extract_prefixed_value(log_lines: List[str], prefix: str) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    raise ValueError(f"Missing log field with prefix: {prefix}")


def parse_task_description(log_lines: List[str]) -> str:
    for line in log_lines:
        stripped = line.strip()
        if stripped:
            return stripped
    raise ValueError("Cannot parse task description from log.txt")


def load_log_metadata(log_dir: Path) -> Dict[str, str]:
    log_path = log_dir / "log.txt"
    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    return {
        "task_description": parse_task_description(log_lines),
        "floor_plan": extract_prefixed_value(log_lines, "Floor Plan:"),
    }


def keep_first_unsafe_only(frame: pd.DataFrame) -> pd.DataFrame:
    kept_rows = []
    seen_unsafe = False
    for _, row in frame.iterrows():
        if seen_unsafe:
            break
        kept_rows.append(row.to_dict())
        if int(row["unsafe"]) == 1:
            seen_unsafe = True
    return pd.DataFrame(kept_rows, columns=frame.columns)


def collect_one_log_dir(log_dir: Path) -> Optional[pd.DataFrame]:
    trace_path = log_dir / "monitor_trace.csv"
    if not trace_path.exists():
        return None

    frame = pd.read_csv(trace_path)
    if frame.empty:
        return None

    metadata = load_log_metadata(log_dir)
    frame = keep_first_unsafe_only(frame)
    frame = frame.reset_index(drop=True)
    frame.insert(0, "task_id", log_dir.name)
    frame.insert(1, "step_id", range(len(frame)))
    frame["task_description"] = metadata["task_description"]
    frame["floor_plan"] = metadata["floor_plan"]
    return frame


def find_log_dirs(logs_dir: Path, contains: Optional[str]) -> List[Path]:
    candidates = [path for path in logs_dir.iterdir() if path.is_dir()]
    candidates.sort(key=lambda path: path.name)
    if contains:
        candidates = [path for path in candidates if contains in path.name]
    return candidates


def main() -> None:
    args = parse_args()
    log_dirs = find_log_dirs(args.logs_dir, args.contains)

    frames: List[pd.DataFrame] = []
    used_dirs: List[str] = []
    dropped_dirs: List[str] = []

    for log_dir in log_dirs:
        try:
            frame = collect_one_log_dir(log_dir)
        except Exception:
            dropped_dirs.append(log_dir.name)
            continue
        if frame is None or frame.empty:
            dropped_dirs.append(log_dir.name)
            continue
        frames.append(frame)
        used_dirs.append(log_dir.name)

    if not frames:
        raise ValueError("No usable monitor_trace.csv files were found.")

    merged = pd.concat(frames, ignore_index=True)
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists() and not args.no_backup:
        args.backup.write_bytes(output.read_bytes())

    merged.to_csv(output, index=False, encoding="utf-8")

    summary = {
        "logs_dir": str(args.logs_dir),
        "output": str(output),
        "num_task_dirs_scanned": len(log_dirs),
        "num_task_dirs_used": len(used_dirs),
        "num_task_dirs_dropped": len(dropped_dirs),
        "num_rows_written": int(len(merged)),
        "used_dirs": used_dirs,
        "dropped_dirs": dropped_dirs,
    }

    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
