"""Runtime helpers for integrating standalone RAG repair into execution.

This module does not execute AI2-THOR actions directly. It provides a thin
runtime around ``repair/rag_consens.py`` so the main runtime can:
- keep a history of completed planner-visible actions
- ask RAG for a repair sequence when prediction blocks an action
- log each repair request for later inspection
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from repair.rag_consens import RAGRepairModule, SafeExecutionDatabase


def init_repair_runtime(
    task_dir: str,
    environment: str,
    task_description: str,
    max_depth: int = 1,
) -> Dict[str, object]:
    """Initialize standalone RAG repair for one task execution."""
    trace_path = Path(task_dir) / "repair_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    database = SafeExecutionDatabase()
    module = RAGRepairModule(database=database, top_k=3, history_window=6, future_window=4)
    return {
        "enabled": len(database) > 0,
        "module": module,
        "environment": environment,
        "task_description": task_description,
        "executed_actions": [],
        "pending_skip_actions": [],
        "trace_path": trace_path,
        "active_depth": 0,
        "max_depth": max_depth,
    }


def build_repair_action(action_info: Dict[str, str]) -> Dict[str, str]:
    """Convert normalized runtime action metadata into the RAG action schema."""
    action = {
        "type": action_info["action"],
        "objectType": action_info["action_object"],
    }
    if action_info.get("action_receptacle", "0") != "0":
        action["receptacle"] = action_info["action_receptacle"]
    return action


def action_matches(action_info: Dict[str, str], candidate: Dict[str, str]) -> bool:
    """Compare one runtime action descriptor against one repair action."""
    if action_info["action"] != str(candidate.get("type", "")):
        return False
    if action_info["action_object"] != str(candidate.get("objectType", "")):
        return False
    candidate_receptacle = str(candidate.get("receptacle", "0") or "0")
    return action_info.get("action_receptacle", "0") == candidate_receptacle


def record_executed_action(
    repair_state: Optional[Dict[str, object]],
    action_info: Dict[str, str],
) -> None:
    """Append one completed planner-visible action to the repair history."""
    if not repair_state or not repair_state.get("enabled", False):
        return
    repair_state["executed_actions"].append(build_repair_action(action_info))


def repair_allowed(repair_state: Optional[Dict[str, object]]) -> bool:
    """Whether a new repair can be started from the current runtime state."""
    if not repair_state or not repair_state.get("enabled", False):
        return False
    return int(repair_state.get("active_depth", 0)) < int(repair_state.get("max_depth", 1))


def begin_repair(repair_state: Optional[Dict[str, object]]) -> None:
    """Increment the active repair depth."""
    if not repair_state:
        return
    repair_state["active_depth"] = int(repair_state.get("active_depth", 0)) + 1


def end_repair(repair_state: Optional[Dict[str, object]]) -> None:
    """Decrement the active repair depth."""
    if not repair_state:
        return
    repair_state["active_depth"] = max(0, int(repair_state.get("active_depth", 0)) - 1)


def request_repair(
    repair_state: Optional[Dict[str, object]],
    action_info: Dict[str, str],
    prediction_result: Dict[str, object],
) -> Optional[Dict[str, object]]:
    """Run RAG repair for one blocked action and log the result."""
    if not repair_allowed(repair_state):
        return None

    blocked_action = build_repair_action(action_info)
    result = repair_state["module"].repair_action(
        blocked_action=blocked_action,
        executed_actions=list(repair_state["executed_actions"]),
        environment=str(repair_state["environment"]),
        task_description=str(repair_state["task_description"]),
    )
    if result is None:
        return None

    _append_trace(
        repair_state["trace_path"],
        {
            "blocked_action": blocked_action,
            "prediction_result": prediction_result,
            "retrieved_records": result.get("retrieved_records", []),
            "repair_actions": result.get("repair_actions", []),
        },
    )
    return result


def set_pending_skip_actions(
    repair_state: Optional[Dict[str, object]],
    blocked_action: Dict[str, str],
    repair_actions: List[Dict[str, str]],
) -> None:
    """Store the repair suffix that should replace upcoming original actions."""
    if not repair_state:
        return
    suffix: List[Dict[str, str]] = []
    matched_blocked = False
    for action in repair_actions:
        if not matched_blocked and _repair_signature(action) == _repair_signature(blocked_action):
            matched_blocked = True
            continue
        if matched_blocked:
            suffix.append(dict(action))
    repair_state["pending_skip_actions"] = suffix


def should_skip_action(
    repair_state: Optional[Dict[str, object]],
    action_info: Dict[str, str],
) -> bool:
    """Whether the next original action has already been executed by repair."""
    if not repair_state:
        return False
    pending = repair_state.get("pending_skip_actions", [])
    if not pending:
        return False
    if action_matches(action_info, pending[0]):
        pending.pop(0)
        return True
    repair_state["pending_skip_actions"] = []
    return False


def _repair_signature(action: Dict[str, str]) -> tuple:
    return (
        str(action.get("type", "")),
        str(action.get("objectType", "")),
        str(action.get("receptacle", "0") or "0"),
    )


def _append_trace(path: Path, payload: Dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
