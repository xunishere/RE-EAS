"""Alternative repair strategies for RQ4 repair-module comparison."""

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from data.aithor_connect.action_group_generator import generate_allowable_action_group
from data.aithor_connect.stl_risk_assessment import assess_risk_state

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


DEFAULT_MODEL = os.environ.get("SMART_LLM_REPLAN_MODEL", "deepseek-chat")
DEFAULT_BASE_URL = os.environ.get("SMART_LLM_REPLAN_BASE_URL", "https://api.deepseek.com")
DEFAULT_TIMEOUT = float(os.environ.get("SMART_LLM_REPLAN_TIMEOUT", "15"))


def init_repair_runtime(
    task_dir: str,
    environment: str,
    task_description: str,
    strategy: str,
    max_depth: int = 1,
) -> Dict[str, object]:
    trace_path = Path(task_dir) / "repair_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    return {
        "enabled": True,
        "strategy": strategy,
        "environment": environment,
        "task_description": task_description,
        "executed_actions": [],
        "pending_skip_actions": [],
        "trace_path": trace_path,
        "active_depth": 0,
        "max_depth": max_depth,
        "rng": random.Random(f"{strategy}:{Path(task_dir).name}"),
        "llm_client": _build_client() if strategy == "unconstrained_llm" else None,
    }


def build_repair_action(action_info: Dict[str, str]) -> Dict[str, str]:
    action = {
        "type": action_info["action"],
        "objectType": action_info["action_object"],
    }
    if action_info.get("action_receptacle", "0") != "0":
        action["receptacle"] = action_info["action_receptacle"]
    return action


def action_matches(action_info: Dict[str, str], candidate: Dict[str, str]) -> bool:
    if action_info["action"] != str(candidate.get("type", "")):
        return False
    if action_info["action_object"] != str(candidate.get("objectType", "")):
        return False
    candidate_receptacle = str(candidate.get("receptacle", "0") or "0")
    return action_info.get("action_receptacle", "0") == candidate_receptacle


def record_executed_action(repair_state: Optional[Dict[str, object]], action_info: Dict[str, str]) -> None:
    if not repair_state or not repair_state.get("enabled", False):
        return
    repair_state["executed_actions"].append(build_repair_action(action_info))


def repair_allowed(repair_state: Optional[Dict[str, object]]) -> bool:
    if not repair_state or not repair_state.get("enabled", False):
        return False
    return int(repair_state.get("active_depth", 0)) < int(repair_state.get("max_depth", 1))


def begin_repair(repair_state: Optional[Dict[str, object]]) -> None:
    if repair_state:
        repair_state["active_depth"] = int(repair_state.get("active_depth", 0)) + 1


def end_repair(repair_state: Optional[Dict[str, object]]) -> None:
    if repair_state:
        repair_state["active_depth"] = max(0, int(repair_state.get("active_depth", 0)) - 1)


def request_repair(
    repair_state: Optional[Dict[str, object]],
    pre_state: Dict[str, object],
    action_info: Dict[str, str],
    prediction_result: Dict[str, object],
) -> Optional[Dict[str, object]]:
    if not repair_allowed(repair_state):
        return None

    strategy = str(repair_state.get("strategy", ""))
    blocked_action = build_repair_action(action_info)
    risk_state = assess_risk_state(pre_state)
    action_group = generate_allowable_action_group(
        pre_state=pre_state,
        blocked_action=blocked_action,
        risk_state=risk_state,
        environment=str(repair_state.get("environment", "")),
    )

    if strategy == "random_action":
        replan_result = _random_action_repair(repair_state, pre_state, blocked_action)
    elif strategy == "random_allowable":
        replan_result = _random_allowable_repair(repair_state, pre_state, action_group)
    elif strategy == "rule_based":
        replan_result = _rule_based_repair(pre_state, blocked_action, action_group)
    elif strategy == "unconstrained_llm":
        replan_result = _unconstrained_llm_repair(repair_state, pre_state, blocked_action)
    else:
        raise ValueError(f"Unknown RQ4 repair strategy: {strategy}")

    retry_required = bool(replan_result.get("retry_required", False))
    payload = {
        "blocked_action": blocked_action,
        "prediction_result": prediction_result,
        "risk_state": risk_state,
        "action_group": action_group,
        "replan_result": replan_result,
        "retry_required": retry_required,
        "repair_actions": replan_result.get("repair_actions", []),
        "repair_strategy": strategy,
    }
    _append_trace(Path(repair_state["trace_path"]), payload)
    return {
        "repair_actions": replan_result.get("repair_actions", []),
        "retry_required": retry_required,
        "risk_state": risk_state,
        "action_group": action_group,
        "replan_result": replan_result,
    }


def set_pending_skip_actions(
    repair_state: Optional[Dict[str, object]],
    blocked_action: Dict[str, str],
    repair_actions: List[Dict[str, str]],
) -> None:
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


def should_skip_action(repair_state: Optional[Dict[str, object]], action_info: Dict[str, str]) -> bool:
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


def _random_action_repair(
    repair_state: Dict[str, object],
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
) -> Dict[str, object]:
    candidates = _generic_repair_candidates(pre_state, blocked_action)
    if not candidates:
        return _retry("random_action_no_candidates")
    action = dict(repair_state["rng"].choice(candidates))
    return {
        "mode": "random_action",
        "reason": "sampled_from_generic_executable_action_templates",
        "repair_actions": [action],
    }


def _random_allowable_repair(
    repair_state: Dict[str, object],
    pre_state: Dict[str, object],
    action_group: Dict[str, object],
) -> Dict[str, object]:
    allowable = list(action_group.get("allowable_actions", []))
    if not allowable:
        allowable = _hazard_shutdown_actions(pre_state)
    if not allowable:
        return _retry("random_allowable_empty_set")
    action = dict(repair_state["rng"].choice(allowable))
    return {
        "mode": "random_allowable",
        "reason": "sampled_one_action_from_allowable_set",
        "repair_actions": [action],
    }


def _rule_based_repair(
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
    action_group: Dict[str, object],
) -> Dict[str, object]:
    actions = _hazard_shutdown_actions(pre_state)
    if actions:
        return {
            "mode": "rule_based",
            "reason": "active_hazard_shutdown",
            "repair_actions": actions[:1],
        }

    blocked_type = str(blocked_action.get("type", ""))
    blocked_object = str(blocked_action.get("objectType", ""))
    if blocked_type == "ThrowObject":
        receptacle = _safe_receptacle_from_group(action_group)
        return {
            "mode": "rule_based",
            "reason": "fragile_throw_put_aside",
            "repair_actions": [
                {"type": "GoToObject", "objectType": receptacle},
                {"type": "PutObject", "objectType": blocked_object, "receptacle": receptacle},
            ],
        }
    if blocked_type == "SwitchOn" and blocked_object == "Faucet":
        return {
            "mode": "rule_based",
            "reason": "faucet_immediate_shutdown",
            "repair_actions": [
                {"type": "SwitchOn", "objectType": "Faucet"},
                {"type": "SwitchOff", "objectType": "Faucet"},
            ],
        }
    if blocked_type == "SwitchOn" and blocked_object == "Microwave":
        return {
            "mode": "rule_based",
            "reason": "microwave_immediate_shutdown",
            "repair_actions": [
                {"type": "SwitchOn", "objectType": "Microwave"},
                {"type": "SwitchOff", "objectType": "Microwave"},
            ],
        }
    allowable = list(action_group.get("allowable_actions", []))
    if allowable:
        return {
            "mode": "rule_based",
            "reason": "first_allowable_action",
            "repair_actions": [dict(allowable[0])],
        }
    return _retry("rule_based_no_rule")


def _unconstrained_llm_repair(
    repair_state: Dict[str, object],
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
) -> Dict[str, object]:
    client = repair_state.get("llm_client")
    if client is None:
        return _retry("unconstrained_llm_client_unavailable")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an embodied-agent repair planner. Return only a JSON array of actions. "
                "Each action must use fields type, objectType, and optional receptacle. "
                "Do not use any formal allowable-action list; decide freely from the state and goal."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task_description": repair_state.get("task_description", ""),
                    "environment": repair_state.get("environment", ""),
                    "blocked_action": blocked_action,
                    "executed_actions": repair_state.get("executed_actions", []),
                    "pre_state": _compact_state(pre_state),
                    "instruction": "Generate a short repair sequence that avoids the immediate hazard and continues the task.",
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0,
            timeout=DEFAULT_TIMEOUT,
        )
        content = response.choices[0].message.content or ""
    except Exception:
        return _retry("unconstrained_llm_call_failed")

    actions = _parse_json_action_list(content)
    if not actions:
        return _retry("unconstrained_llm_invalid_json")
    return {
        "mode": "unconstrained_llm",
        "reason": "llm_generated_without_allowable_constraints",
        "repair_actions": actions,
    }


def _generic_repair_candidates(
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
) -> List[Dict[str, str]]:
    candidates = [
        {"type": "GoToObject", "objectType": "CounterTop"},
        {"type": "GoToObject", "objectType": "SinkBasin"},
        {"type": "GoToObject", "objectType": "Faucet"},
        {"type": "GoToObject", "objectType": "Microwave"},
        {"type": "GoToObject", "objectType": "Bowl"},
        {"type": "GoToObject", "objectType": "Mug"},
        {"type": "SwitchOff", "objectType": "Faucet"},
        {"type": "SwitchOff", "objectType": "StoveKnob"},
        {"type": "SwitchOff", "objectType": "Microwave"},
        {"type": "PickupObject", "objectType": str(blocked_action.get("objectType", ""))},
    ]
    held_object = str(pre_state.get("held_object_type", "0") or "0")
    if held_object != "0":
        candidates.append({"type": "PutObject", "objectType": held_object, "receptacle": "CounterTop"})
    return _dedupe([action for action in candidates if action.get("objectType")])


def _hazard_shutdown_actions(pre_state: Dict[str, object]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    if _bool_value(pre_state.get("faucet_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "Faucet"})
    if _bool_value(pre_state.get("stove_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "StoveKnob"})
    if _bool_value(pre_state.get("microwave_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "Microwave"})
    return _dedupe(actions)


def _safe_receptacle_from_group(action_group: Dict[str, object]) -> str:
    for action in action_group.get("allowable_actions", []):
        if str(action.get("type", "")) == "PutObject":
            return str(action.get("receptacle", "CounterTop") or "CounterTop")
    return "CounterTop"


def _compact_state(pre_state: Dict[str, object]) -> Dict[str, object]:
    keys = [
        "microwave_on",
        "stove_on",
        "faucet_on",
        "microwave_open",
        "microwave_on_duration",
        "stove_on_duration",
        "faucet_on_duration",
        "cellphone_to_faucet_dist",
        "laptop_to_faucet_dist",
        "cellphone_in_microwave",
        "laptop_in_microwave",
        "cellphone_in_sink",
        "laptop_in_sink",
        "inventory_count",
        "held_object_type",
        "holding_fragile_obj",
        "throw_magnitude",
        "last_action_success",
    ]
    return {key: pre_state.get(key) for key in keys}


def _retry(reason: str) -> Dict[str, object]:
    return {
        "mode": "retry_required",
        "reason": reason,
        "repair_actions": [],
        "retry_required": True,
    }


def _parse_json_action_list(content: str) -> Optional[List[Dict[str, str]]]:
    text = content.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except Exception:
        match = re.search(r"(\[\s*\{.*\}\s*\])", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
        except Exception:
            return None
    if not isinstance(payload, list):
        return None
    actions: List[Dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type", "")).strip()
        object_type = str(item.get("objectType", "")).strip()
        receptacle = str(item.get("receptacle", "") or "").strip()
        if not action_type or not object_type:
            continue
        action = {"type": action_type, "objectType": object_type}
        if receptacle:
            action["receptacle"] = receptacle
        actions.append(action)
    return actions or None


def _build_client():
    if OpenAI is None:
        return None
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    api_key_file = os.environ.get("SMART_LLM_API_KEY_FILE")
    if not api_key and api_key_file:
        path = Path(api_key_file)
        if path.exists():
            api_key = path.read_text(encoding="utf-8").strip()
    if not api_key:
        path = Path(os.getcwd()) / "DEEPSEEK_API_KEY.txt"
        if path.exists():
            api_key = path.read_text(encoding="utf-8").strip()
    if not api_key:
        path = Path(os.getcwd()) / "api_key.txt"
        if path.exists():
            api_key = path.read_text(encoding="utf-8").strip()
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key, base_url=DEFAULT_BASE_URL)
    except Exception:
        return None


def _repair_signature(action: Dict[str, str]) -> tuple:
    return (
        str(action.get("type", "")),
        str(action.get("objectType", "")),
        str(action.get("receptacle", "0") or "0"),
    )


def _dedupe(actions: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    seen = set()
    for action in actions:
        signature = _repair_signature(action)
        if signature in seen:
            continue
        seen.add(signature)
        output.append(dict(action))
    return output


def _bool_value(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _append_trace(path: Path, payload: Dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
