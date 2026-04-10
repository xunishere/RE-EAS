"""Runtime maintenance helpers for the RAG safe database.

This module appends new safe execution traces into ``repair/database`` after a
task finishes successfully and remains safe under monitoring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


DATABASE_PATH = Path(__file__).resolve().parent / "database"


def load_database(database_path: Path = DATABASE_PATH) -> List[Dict[str, object]]:
    """Load the current safe database."""
    if not database_path.exists():
        return []
    raw = database_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"Safe database must be a JSON list: {database_path}")
    return data


def save_database(records: List[Dict[str, object]], database_path: Path = DATABASE_PATH) -> None:
    """Persist the safe database with stable JSON formatting."""
    database_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_monitor_trace(monitor_trace_path: str) -> List[Dict[str, object]]:
    """Load monitor trace rows from CSV into dictionaries."""
    import csv

    path = Path(monitor_trace_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def is_safe_run_qualified(
    sr_value: object,
    monitor_rows: List[Dict[str, object]],
    executed_actions: List[Dict[str, object]],
) -> bool:
    """Whether one completed run can be promoted into the safe database."""
    if str(sr_value) != "1":
        return False
    if not executed_actions:
        return False
    if len(executed_actions) < 2 or len(executed_actions) > 30:
        return False
    for row in monitor_rows:
        unsafe_value = str(row.get("unsafe", "")).strip().lower()
        if unsafe_value in {"1", "true"}:
            return False
    return True


def build_record(
    executed_actions: List[Dict[str, object]],
    environment: str,
    task_description: str,
    record_id: str,
) -> Dict[str, object]:
    """Build one safe-record payload from a completed real execution."""
    return {
        "record_id": record_id,
        "environment": str(environment),
        "task_description": str(task_description),
        "actions": [normalize_action(action) for action in executed_actions],
    }


def normalize_action(action: Dict[str, object]) -> Dict[str, str]:
    """Normalize one runtime action into the database schema."""
    normalized = {
        "type": str(action.get("type", "")),
        "objectType": str(action.get("objectType", "")),
    }
    receptacle = str(action.get("receptacle", "0") or "0")
    if receptacle != "0":
        normalized["receptacle"] = receptacle
    return normalized


def record_exists(records: List[Dict[str, object]], candidate: Dict[str, object]) -> bool:
    """Exact duplicate check on environment, task text, and action sequence."""
    candidate_key = (
        str(candidate.get("environment", "")),
        str(candidate.get("task_description", "")),
        json.dumps(candidate.get("actions", []), ensure_ascii=False, sort_keys=True),
    )
    for record in records:
        record_key = (
            str(record.get("environment", "")),
            str(record.get("task_description", "")),
            json.dumps(record.get("actions", []), ensure_ascii=False, sort_keys=True),
        )
        if record_key == candidate_key:
            return True
    return False


def next_record_id(records: List[Dict[str, object]]) -> str:
    """Allocate the next neutral record identifier."""
    max_id = 0
    for record in records:
        record_id = str(record.get("record_id", ""))
        if record_id.startswith("record_"):
            suffix = record_id.split("_", 1)[1]
            if suffix.isdigit():
                max_id = max(max_id, int(suffix))
    return f"record_{max_id + 1:04d}"


def append_record_if_qualified(
    executed_actions: List[Dict[str, object]],
    environment: str,
    task_description: str,
    sr_value: object,
    monitor_trace_path: str,
    database_path: Path = DATABASE_PATH,
) -> Dict[str, object]:
    """Append one new safe record when a completed run qualifies."""
    monitor_rows = load_monitor_trace(monitor_trace_path)
    if not is_safe_run_qualified(sr_value, monitor_rows, executed_actions):
        return {"appended": False, "reason": "run_not_qualified"}

    records = load_database(database_path)
    candidate = build_record(
        executed_actions=executed_actions,
        environment=environment,
        task_description=task_description,
        record_id=next_record_id(records),
    )
    if record_exists(records, candidate):
        return {"appended": False, "reason": "duplicate", "record_id": candidate["record_id"]}

    records.append(candidate)
    save_database(records, database_path)
    return {
        "appended": True,
        "reason": "ok",
        "record_id": candidate["record_id"],
        "database_size": len(records),
    }

