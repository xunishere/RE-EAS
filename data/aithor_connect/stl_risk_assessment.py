"""STL-guided risk assessment over action pre-state signals.

This module turns the existing monitoring pre-state into:
- signal-wise safety margins
- discrete risk levels
- one composite risk state

It is designed to sit between pre-action prediction and constrained replanning.
"""

from __future__ import annotations

from typing import Dict


RISK_SAFE = "safe"
RISK_WARNING = "warning"
RISK_CRITICAL = "critical"

SENSITIVE_THROW_OBJECT_TYPES = {
    "Plate",
    "Bowl",
    "Cup",
    "Mug",
    "Vase",
    "Egg",
    "WineBottle",
    "Laptop",
    "CellPhone",
    "AlarmClock",
    "CD",
    "KeyChain",
    "Box",
}

DEFAULT_WARNING_BUFFER = {
    "duration": 0.25,
    "distance": 0.25,
    "throw": 1.0,
}


def assess_risk_state(pre_state: Dict[str, object]) -> Dict[str, object]:
    """Assess STL-related risk state from one action pre-state snapshot.

    Args:
        pre_state: Monitoring snapshot before executing one planner-visible action.

    Returns:
        Dictionary with signal margins, signal-wise risk levels, and a composite
        risk state.
    """
    thresholds = {
        "T_max_heat": _float_value(pre_state.get("T_max_heat", 1.0)),
        "T_max_water": _float_value(pre_state.get("T_max_water", 1.0)),
        "delta_safe": _float_value(pre_state.get("delta_safe", 1.0)),
        "theta_break": _float_value(pre_state.get("theta_break", 5.0)),
    }

    margins = {
        "microwave_duration": thresholds["T_max_heat"]
        - _float_value(pre_state.get("microwave_on_duration", 0.0)),
        "stove_duration": thresholds["T_max_heat"]
        - _float_value(pre_state.get("stove_on_duration", 0.0)),
        "faucet_duration": thresholds["T_max_water"]
        - _float_value(pre_state.get("faucet_on_duration", 0.0)),
        "cellphone_faucet_distance": _float_value(pre_state.get("cellphone_to_faucet_dist", 999.0))
        - thresholds["delta_safe"],
        "laptop_faucet_distance": _float_value(pre_state.get("laptop_to_faucet_dist", 999.0))
        - thresholds["delta_safe"],
        "throw_force": thresholds["theta_break"]
        - _float_value(pre_state.get("throw_magnitude", 0.0)),
    }

    levels = {
        "microwave_duration": _margin_to_level(margins["microwave_duration"], DEFAULT_WARNING_BUFFER["duration"]),
        "stove_duration": _margin_to_level(margins["stove_duration"], DEFAULT_WARNING_BUFFER["duration"]),
        "faucet_duration": _margin_to_level(margins["faucet_duration"], DEFAULT_WARNING_BUFFER["duration"]),
        "cellphone_faucet_distance": _margin_to_level(
            margins["cellphone_faucet_distance"],
            DEFAULT_WARNING_BUFFER["distance"],
        ),
        "laptop_faucet_distance": _margin_to_level(
            margins["laptop_faucet_distance"],
            DEFAULT_WARNING_BUFFER["distance"],
        ),
        "throw_force": _margin_to_level(margins["throw_force"], DEFAULT_WARNING_BUFFER["throw"]),
        "microwave_contents": _microwave_content_level(pre_state),
        "fragile_throw": _fragile_throw_level(pre_state),
    }

    composite = _aggregate_composite_level(levels)
    active_risks = [signal for signal, level in levels.items() if level != RISK_SAFE]

    return {
        "thresholds": thresholds,
        "margins": {name: round(value, 6) for name, value in margins.items()},
        "levels": levels,
        "active_risks": active_risks,
        "composite_risk": composite,
    }


def _aggregate_composite_level(levels: Dict[str, str]) -> str:
    if any(level == RISK_CRITICAL for level in levels.values()):
        return RISK_CRITICAL
    if any(level == RISK_WARNING for level in levels.values()):
        return RISK_WARNING
    return RISK_SAFE


def _microwave_content_level(pre_state: Dict[str, object]) -> str:
    microwave_on = _bool_value(pre_state.get("microwave_on", False))
    bad_content = _bool_value(pre_state.get("cellphone_in_microwave", False)) or _bool_value(
        pre_state.get("laptop_in_microwave", False)
    )
    if microwave_on and bad_content:
        return RISK_CRITICAL
    if bad_content:
        return RISK_WARNING
    return RISK_SAFE


def _fragile_throw_level(pre_state: Dict[str, object]) -> str:
    holding_fragile = _bool_value(pre_state.get("holding_fragile_obj", False))
    held_object_type = str(pre_state.get("held_object_type", ""))
    holding_sensitive = holding_fragile or _is_sensitive_throw_object(held_object_type)
    throw_magnitude = _float_value(pre_state.get("throw_magnitude", 0.0))
    theta_break = _float_value(pre_state.get("theta_break", 5.0))
    if holding_sensitive and throw_magnitude >= theta_break:
        return RISK_CRITICAL
    if holding_sensitive:
        return RISK_WARNING
    return RISK_SAFE


def _is_sensitive_throw_object(object_type: str) -> bool:
    normalized = str(object_type).replace(" ", "").lower()
    return any(
        sensitive_type.replace(" ", "").lower() in normalized
        for sensitive_type in SENSITIVE_THROW_OBJECT_TYPES
    )


def _margin_to_level(margin: float, warning_buffer: float) -> str:
    if margin <= 0.0:
        return RISK_CRITICAL
    if margin <= warning_buffer:
        return RISK_WARNING
    return RISK_SAFE


def _bool_value(value) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def _float_value(value) -> float:
    return float(value)
