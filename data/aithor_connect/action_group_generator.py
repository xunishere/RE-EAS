"""Allowable action generation under STL risk constraints.

This module maps:
    (pre_state, blocked_action, risk_state)
into:
    an allowable action group that excludes risk-increasing actions.
"""

from __future__ import annotations

from typing import Dict, List


def generate_allowable_action_group(
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
    risk_state: Dict[str, object],
    environment: str = "",
) -> Dict[str, object]:
    """Generate allowable and forbidden action groups for constrained replanning.

    Args:
        pre_state: Monitoring snapshot before the blocked action.
        blocked_action: Normalized action dictionary with `type`, `objectType`,
            and optional `receptacle`.
        risk_state: Output from `assess_risk_state(...)`.

    Returns:
        Structured action-group dictionary.
    """
    blocked_type = str(blocked_action.get("type", ""))
    blocked_object = str(blocked_action.get("objectType", ""))
    active_risks = set(risk_state.get("active_risks", []))

    allowed: List[Dict[str, str]] = []
    forbidden: List[Dict[str, str]] = []
    rationale: List[str] = []

    if blocked_type == "SwitchOn" and blocked_object == "Faucet":
        allowed = _faucet_switchon_group(pre_state)
        forbidden = [
            {"type": "SwitchOn", "objectType": "Faucet"},
            {"type": "PutObject", "objectType": "CellPhone", "receptacle": "Sink"},
            {"type": "PutObject", "objectType": "Laptop", "receptacle": "Sink"},
        ]
        rationale.append("blocked_action_is_faucet_switch_on")

    elif blocked_type == "GoToObject" and blocked_object in {"Bread", "Bowl", "Mug", "Plate", "CellPhone", "Laptop"}:
        if _is_faucet_risk_active(pre_state, active_risks):
            allowed = [{"type": "SwitchOff", "objectType": "Faucet"}]
            rationale.append("water_risk_requires_switch_off_first")
        elif _is_stove_risk_active(pre_state, active_risks):
            allowed = [{"type": "SwitchOff", "objectType": "StoveKnob"}]
            rationale.append("stove_risk_requires_switch_off_first")

    elif blocked_type == "SwitchOn" and blocked_object == "Microwave":
        allowed = _microwave_switchon_group(pre_state)
        forbidden = [{"type": "SwitchOn", "objectType": "Microwave"}]
        rationale.append("blocked_action_is_microwave_switch_on")

    elif blocked_type == "ThrowObject":
        target_object = str(blocked_action.get("objectType", ""))
        safe_receptacle = _safe_throw_receptacle(environment)
        allowed = [
            {"type": "GoToObject", "objectType": safe_receptacle},
            {"type": "PutObject", "objectType": target_object, "receptacle": safe_receptacle},
        ]
        forbidden = [{"type": "ThrowObject", "objectType": target_object}]
        rationale.append("fragile_throw_replaced_by_safe_put_aside")

    elif blocked_type == "GoToObject" and blocked_object == "Bowl" and _is_stove_risk_active(pre_state, active_risks):
        allowed = [
            {"type": "SwitchOff", "objectType": "StoveKnob"},
            {"type": "GoToObject", "objectType": "Bowl"},
            {"type": "PickupObject", "objectType": "Bowl"},
        ]
        rationale.append("stove_timeout_local_repair")

    if not allowed and risk_state.get("composite_risk") == "critical":
        if _bool_value(pre_state.get("faucet_on", False)):
            allowed.append({"type": "SwitchOff", "objectType": "Faucet"})
        if _bool_value(pre_state.get("microwave_on", False)):
            allowed.append({"type": "SwitchOff", "objectType": "Microwave"})
        if _bool_value(pre_state.get("stove_on", False)):
            allowed.append({"type": "SwitchOff", "objectType": "StoveKnob"})
        if allowed:
            rationale.append("fallback_to_risk_mitigation_actions")

    return {
        "blocked_action": blocked_action,
        "risk_state": risk_state.get("composite_risk", "safe"),
        "active_risks": list(active_risks),
        "allowable_actions": _dedupe_actions(allowed),
        "forbidden_actions": _dedupe_actions(forbidden),
        "rationale": rationale,
    }


def _faucet_switchon_group(pre_state: Dict[str, object]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    actions.extend(_put_aside_if_holding_unrelated(pre_state, {"CellPhone", "Mug"}))
    if _bool_value(pre_state.get("cellphone_in_sink", False)):
        actions.extend(
            [
                {"type": "GoToObject", "objectType": "CellPhone"},
                {"type": "PickupObject", "objectType": "CellPhone"},
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": "CellPhone", "receptacle": "CounterTop"},
            ]
        )
    elif _float_value(pre_state.get("cellphone_to_faucet_dist", 999.0)) < _float_value(pre_state.get("delta_safe", 1.0)):
        actions.extend(
            [
                {"type": "GoToObject", "objectType": "CellPhone"},
                {"type": "PickupObject", "objectType": "CellPhone"},
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": "CellPhone", "receptacle": "CounterTop"},
            ]
        )
    actions.extend(
        [
            {"type": "GoToObject", "objectType": "Mug"},
            {"type": "PickupObject", "objectType": "Mug"},
            {"type": "GoToObject", "objectType": "SinkBasin"},
            {"type": "PutObject", "objectType": "Mug", "receptacle": "SinkBasin"},
            {"type": "SwitchOn", "objectType": "Faucet"},
            {"type": "SwitchOff", "objectType": "Faucet"},
        ]
    )
    return actions


def _safe_throw_receptacle(environment: str) -> str:
    normalized = str(environment).strip().lower()
    if normalized == "living_room" or normalized.startswith("floorplan2"):
        return "Sofa"
    if normalized == "bedroom" or normalized.startswith("floorplan3"):
        return "Bed"
    return "CounterTop"


def _microwave_switchon_group(pre_state: Dict[str, object]) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    held_object = str(pre_state.get("held_object_type", "0") or "0")
    inventory_count = int(float(pre_state.get("inventory_count", 0) or 0))
    if inventory_count > 0 and held_object not in {"0", "Knife", "BreadSliced"}:
        actions.extend(
            [
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": held_object, "receptacle": "CounterTop"},
            ]
        )
        held_object = "0"

    microwave_open = _bool_value(pre_state.get("microwave_open", False))
    bread_ready_in_microwave = _bool_value(pre_state.get("bread_in_microwave", False)) or _bool_value(
        pre_state.get("breadsliced_in_microwave", False)
    )
    breadsliced_held = held_object == "BreadSliced"

    hazardous_inside = _microwave_hazard_object(pre_state)
    if hazardous_inside:
        if not microwave_open:
            actions.append({"type": "OpenObject", "objectType": "Microwave"})
            microwave_open = True
        actions.extend(
            [
                {"type": "PickupObject", "objectType": hazardous_inside},
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": hazardous_inside, "receptacle": "CounterTop"},
            ]
        )
        held_object = "0"
        breadsliced_held = False

    if held_object == "Knife":
        actions.extend(
            [
                {"type": "GoToObject", "objectType": "Bread"},
                {"type": "SliceObject", "objectType": "Bread"},
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": "Knife", "receptacle": "CounterTop"},
                {"type": "GoToObject", "objectType": "BreadSliced"},
                {"type": "PickupObject", "objectType": "BreadSliced"},
            ]
        )
        held_object = "BreadSliced"
        breadsliced_held = True

    if not breadsliced_held and not bread_ready_in_microwave:
        actions.extend(
            [
                {"type": "GoToObject", "objectType": "Knife"},
                {"type": "PickupObject", "objectType": "Knife"},
                {"type": "GoToObject", "objectType": "Bread"},
                {"type": "SliceObject", "objectType": "Bread"},
                {"type": "GoToObject", "objectType": "CounterTop"},
                {"type": "PutObject", "objectType": "Knife", "receptacle": "CounterTop"},
                {"type": "GoToObject", "objectType": "BreadSliced"},
                {"type": "PickupObject", "objectType": "BreadSliced"},
            ]
        )
        held_object = "BreadSliced"
        breadsliced_held = True

    if not bread_ready_in_microwave:
        actions.append({"type": "GoToObject", "objectType": "Microwave"})
        if not microwave_open:
            actions.append({"type": "OpenObject", "objectType": "Microwave"})
            microwave_open = True
        actions.append({"type": "PutObject", "objectType": "BreadSliced", "receptacle": "Microwave"})
        held_object = "0"
        breadsliced_held = False
        bread_ready_in_microwave = True
        actions.append({"type": "CloseObject", "objectType": "Microwave"})
        microwave_open = False
    elif microwave_open:
        actions.append({"type": "CloseObject", "objectType": "Microwave"})
        microwave_open = False

    actions.extend(
        [
            {"type": "SwitchOn", "objectType": "Microwave"},
            {"type": "SwitchOff", "objectType": "Microwave"},
        ]
    )
    return actions


def _microwave_hazard_object(pre_state: Dict[str, object]) -> str:
    if _bool_value(pre_state.get("cellphone_in_microwave", False)):
        return "CellPhone"
    if _bool_value(pre_state.get("laptop_in_microwave", False)):
        return "Laptop"
    return ""


def _is_faucet_risk_active(pre_state: Dict[str, object], active_risks) -> bool:
    return _bool_value(pre_state.get("faucet_on", False)) or any(
        risk in active_risks for risk in {"faucet_duration", "cellphone_faucet_distance", "laptop_faucet_distance"}
    )


def _is_stove_risk_active(pre_state: Dict[str, object], active_risks) -> bool:
    return _bool_value(pre_state.get("stove_on", False)) or "stove_duration" in active_risks


def _put_aside_if_holding_unrelated(pre_state: Dict[str, object], allowed_types) -> List[Dict[str, str]]:
    held_object = str(pre_state.get("held_object_type", "0") or "0")
    inventory_count = int(float(pre_state.get("inventory_count", 0) or 0))
    if inventory_count <= 0 or held_object == "0" or held_object in allowed_types:
        return []
    return [
        {"type": "GoToObject", "objectType": "CounterTop"},
        {"type": "PutObject", "objectType": held_object, "receptacle": "CounterTop"},
    ]


def _dedupe_actions(actions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    deduped = []
    last_signature = None
    for action in actions:
        signature = (
            str(action.get("type", "")),
            str(action.get("objectType", "")),
            str(action.get("receptacle", "0") or "0"),
        )
        if signature == last_signature:
            continue
        deduped.append(action)
        last_signature = signature
    return deduped


def _bool_value(value) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def _float_value(value) -> float:
    return float(value)
