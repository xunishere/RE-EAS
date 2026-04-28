"""LLM-assisted constrained replanner with deterministic fallback.

This module converts:
    current state + blocked action + allowable action group
into:
    a repaired suffix plan

The planner first tries an LLM constrained by the allowable action set. When no
LLM client is available or the response is invalid, it falls back to a
deterministic local suffix derived from the allowable actions.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional during local import
    OpenAI = None  # type: ignore


DEFAULT_MODEL = os.environ.get("SMART_LLM_REPLAN_MODEL", "deepseek-chat")
DEFAULT_BASE_URL = os.environ.get("SMART_LLM_REPLAN_BASE_URL", "https://api.deepseek.com")
DEFAULT_TIMEOUT = float(os.environ.get("SMART_LLM_REPLAN_TIMEOUT", "15"))


def replan_suffix(
    pre_state: Dict[str, object],
    executed_actions: Sequence[Dict[str, str]],
    blocked_action: Dict[str, str],
    remaining_goal: str,
    action_group: Dict[str, object],
    task_description: str,
    environment: str,
) -> Dict[str, object]:
    """Single-call helper for constrained suffix replanning."""
    replanner = ConstrainedReplanner()
    return replanner.plan_suffix(
        pre_state=pre_state,
        executed_actions=executed_actions,
        blocked_action=blocked_action,
        remaining_goal=remaining_goal,
        action_group=action_group,
        task_description=task_description,
        environment=environment,
    )


class ConstrainedReplanner:
    """Constrained suffix replanner."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.client = self._build_client()

    def plan_suffix(
        self,
        pre_state: Dict[str, object],
        executed_actions: Sequence[Dict[str, str]],
        blocked_action: Dict[str, str],
        remaining_goal: str,
        action_group: Dict[str, object],
        task_description: str,
        environment: str,
    ) -> Dict[str, object]:
        """Plan a repaired suffix under an allowable action constraint."""
        allowable_actions = list(action_group.get("allowable_actions", []))
        if not allowable_actions:
            shutdown_actions = _hazard_shutdown_actions(pre_state)
            if shutdown_actions:
                return {
                    "mode": "local_fallback",
                    "reason": "hazard_shutdown_without_allowable_group",
                    "repair_actions": shutdown_actions,
                }
            return {
                "mode": "retry_required",
                "reason": "empty_allowable_action_group",
                "repair_actions": [],
                "retry_required": True,
            }

        llm_result = self._try_llm_replan(
            pre_state=pre_state,
            executed_actions=executed_actions,
            blocked_action=blocked_action,
            remaining_goal=remaining_goal,
            allowable_actions=allowable_actions,
            task_description=task_description,
            environment=environment,
        )
        if llm_result is not None:
            return {
                "mode": "local_llm",
                "reason": "llm_success",
                "repair_actions": llm_result,
            }

        fallback_actions = self._fallback_local_suffix(
            blocked_action=blocked_action,
            allowable_actions=allowable_actions,
        )
        if fallback_actions:
            return {
                "mode": "local_fallback",
                "reason": "deterministic_fallback",
                "repair_actions": fallback_actions,
            }

        shutdown_actions = _hazard_shutdown_actions(pre_state)
        if shutdown_actions:
            return {
                "mode": "local_fallback",
                "reason": "hazard_shutdown_after_empty_suffix",
                "repair_actions": shutdown_actions,
            }

        return {
            "mode": "retry_required",
            "reason": "no_local_suffix",
            "repair_actions": [],
            "retry_required": True,
        }

    def _try_llm_replan(
        self,
        pre_state: Dict[str, object],
        executed_actions: Sequence[Dict[str, str]],
        blocked_action: Dict[str, str],
        remaining_goal: str,
        allowable_actions: Sequence[Dict[str, str]],
        task_description: str,
        environment: str,
    ) -> Optional[List[Dict[str, str]]]:
        if self.client is None:
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a constrained embodied replanner. "
                    "Return only a JSON array of actions. "
                    "Each action must be chosen from the allowable action set. "
                    "Do not repeat already executed actions. "
                    "Produce a minimal safe suffix plan that still completes the remaining task goal. "
                    "The repair suffix must complete the blocked action's remaining goal, not just mitigate risk. "
                    "If the blocked action is SwitchOn Microwave, the final plan must include SwitchOn Microwave. "
                    "For microwave heating tasks, the final plan must also include the subsequent SwitchOff Microwave. "
                    "Do not stop after only removing the hazard or placing the food; finish the heating subroutine."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task_description": task_description,
                        "environment": environment,
                        "remaining_goal": remaining_goal,
                        "blocked_action": blocked_action,
                        "executed_actions": list(executed_actions),
                        "pre_state": _compact_state(pre_state),
                        "allowable_actions": list(allowable_actions),
                        "constraints": [
                            "repair suffix must satisfy the remaining task goal",
                            "repair suffix must not stop at partial hazard mitigation",
                            "if blocked_action is SwitchOn Microwave, include SwitchOn Microwave in the output",
                            "for microwave heating tasks, include the subsequent SwitchOff Microwave in the output",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                timeout=self.timeout,
            )
            content = response.choices[0].message.content or ""
        except Exception:
            return None

        parsed = _parse_json_action_list(content)
        if not parsed:
            return None

        filtered = _filter_to_allowable(parsed, allowable_actions)
        if not filtered:
            return None
        return filtered

    def _fallback_local_suffix(
        self,
        blocked_action: Dict[str, str],
        allowable_actions: Sequence[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Deterministic suffix fallback for the current action families."""
        blocked_type = str(blocked_action.get("type", ""))
        blocked_object = str(blocked_action.get("objectType", ""))

        if blocked_type == "ThrowObject":
            return list(allowable_actions)

        if blocked_type == "SwitchOn" and blocked_object in {"Faucet", "Microwave"}:
            return list(allowable_actions)

        if blocked_type == "GoToObject":
            return list(allowable_actions)

        return list(allowable_actions)

    def _build_client(self):
        if OpenAI is None:
            return None
        if os.environ.get("SMART_LLM_DISABLE_REPLAN_LLM", "").strip().lower() in {"1", "true", "yes"}:
            return None

        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        api_key_file = os.environ.get("SMART_LLM_API_KEY_FILE")
        if not api_key and api_key_file:
            key_path = Path(api_key_file)
            if key_path.exists():
                api_key = key_path.read_text(encoding="utf-8").strip()
        if not api_key:
            deepseek_key = Path(os.getcwd()) / "DEEPSEEK_API_KEY.txt"
            if deepseek_key.exists():
                api_key = deepseek_key.read_text(encoding="utf-8").strip()
        if not api_key:
            default_key = Path(os.getcwd()) / "api_key.txt"
            if default_key.exists():
                api_key = default_key.read_text(encoding="utf-8").strip()
        if not api_key:
            return None

        try:
            return OpenAI(api_key=api_key, base_url=self.base_url)
        except Exception:
            return None


def _compact_state(pre_state: Dict[str, object]) -> Dict[str, object]:
    return {
        "microwave_on": pre_state.get("microwave_on"),
        "stove_on": pre_state.get("stove_on"),
        "faucet_on": pre_state.get("faucet_on"),
        "microwave_open": pre_state.get("microwave_open"),
        "microwave_on_duration": pre_state.get("microwave_on_duration"),
        "stove_on_duration": pre_state.get("stove_on_duration"),
        "faucet_on_duration": pre_state.get("faucet_on_duration"),
        "cellphone_to_faucet_dist": pre_state.get("cellphone_to_faucet_dist"),
        "laptop_to_faucet_dist": pre_state.get("laptop_to_faucet_dist"),
        "cellphone_in_microwave": pre_state.get("cellphone_in_microwave"),
        "laptop_in_microwave": pre_state.get("laptop_in_microwave"),
        "bread_in_microwave": pre_state.get("bread_in_microwave"),
        "breadsliced_in_microwave": pre_state.get("breadsliced_in_microwave"),
        "cellphone_in_sink": pre_state.get("cellphone_in_sink"),
        "laptop_in_sink": pre_state.get("laptop_in_sink"),
        "inventory_count": pre_state.get("inventory_count"),
        "held_object_type": pre_state.get("held_object_type"),
        "holding_fragile_obj": pre_state.get("holding_fragile_obj"),
        "throw_magnitude": pre_state.get("throw_magnitude"),
        "last_action_success": pre_state.get("last_action_success"),
    }


def _hazard_shutdown_actions(pre_state: Dict[str, object]) -> List[Dict[str, str]]:
    """Return minimal risk-mitigation actions when constrained groups are empty."""
    actions: List[Dict[str, str]] = []
    if _bool_value(pre_state.get("faucet_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "Faucet"})
    if _bool_value(pre_state.get("stove_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "StoveKnob"})
    if _bool_value(pre_state.get("microwave_on", False)):
        actions.append({"type": "SwitchOff", "objectType": "Microwave"})
    return _dedupe(actions)


def _bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


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
    normalized: List[Dict[str, str]] = []
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
        normalized.append(action)
    return normalized or None


def _filter_to_allowable(
    planned_actions: Sequence[Dict[str, str]],
    allowable_actions: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    allowed_signatures = {
        (
            str(action.get("type", "")),
            str(action.get("objectType", "")),
            str(action.get("receptacle", "") or ""),
        )
        for action in allowable_actions
    }
    filtered: List[Dict[str, str]] = []
    for action in planned_actions:
        signature = (
            str(action.get("type", "")),
            str(action.get("objectType", "")),
            str(action.get("receptacle", "") or ""),
        )
        if signature in allowed_signatures:
            filtered.append(dict(action))
    return _dedupe(filtered)


def _dedupe(actions: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    previous = None
    for action in actions:
        signature = (
            str(action.get("type", "")),
            str(action.get("objectType", "")),
            str(action.get("receptacle", "") or ""),
        )
        if signature == previous:
            continue
        output.append(dict(action))
        previous = signature
    return output
