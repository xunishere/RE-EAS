"""Runtime helpers for action-level safety prediction.

This module runs the trained prediction model before each planner-visible
action. It mirrors the monitor-trace schema so that prediction logs and
post-action RT-Lola labels can be compared row by row.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Optional

from prediction.calibration import apply_calibration
from prediction.infer import build_prediction_set, load_prediction_stack


PREDICTION_THRESHOLD = 0.75

PREDICTION_TRACE_FIELDS = [
    "pre_time",
    "action",
    "action_object",
    "action_receptacle",
    "pre_microwave_on",
    "pre_stove_on",
    "pre_cellphone_in_microwave",
    "pre_laptop_in_microwave",
    "pre_microwave_on_duration",
    "pre_stove_on_duration",
    "pre_faucet_on",
    "pre_faucet_on_duration",
    "pre_cellphone_to_faucet_dist",
    "pre_laptop_to_faucet_dist",
    "pre_holding_fragile_obj",
    "pre_fragile_throw_event",
    "pre_throw_magnitude",
    "pred_unsafe_probability",
    "pred_unsafe_label",
    "pred_confidence",
    "pred_prediction_set",
]


def init_prediction_runtime(task_dir: str) -> Dict[str, object]:
    """Initialize the action-level prediction runtime.

    Args:
        task_dir: Task-specific log directory.

    Returns:
        Runtime dictionary holding model artifacts and output file paths.
    """
    prediction_dir = Path(task_dir)
    trace_path = prediction_dir / "prediction_trace.csv"
    _write_csv_header(trace_path, PREDICTION_TRACE_FIELDS)
    return {
        "enabled": True,
        "trace_path": trace_path,
        "stack": load_prediction_stack(),
        "threshold": PREDICTION_THRESHOLD,
    }


def record_prediction(
    prediction_state: Optional[Dict[str, object]],
    pre_state: Dict[str, object],
    action_info: Dict[str, str],
) -> Dict[str, object]:
    """Predict safety risk for one planner-visible action and append one row.

    Args:
        prediction_state: Runtime dictionary returned by `init_prediction_runtime`.
        pre_state: Current action pre-state from the monitoring runtime.
        action_info: Normalized action descriptor.

    Returns:
        Prediction dictionary containing probability, label, confidence, and set.
    """
    if not prediction_state or not prediction_state.get("enabled", False):
        return {
            "unsafe_probability": 0.0,
            "unsafe_label": 0,
            "confidence": 1.0,
            "prediction_set": [0],
        }

    stack = prediction_state["stack"]
    threshold = float(prediction_state["threshold"])

    frame = _build_prediction_frame(pre_state, action_info)
    transformed = stack["transformer"].transform(frame)
    raw_probability = stack["model"].predict_proba(transformed)[:, 1]
    calibrated_probability = apply_calibration(stack["calibrator"], raw_probability)
    unsafe_probability = float(calibrated_probability[0])
    unsafe_label = 1 if unsafe_probability >= threshold else 0
    confidence = float(max(unsafe_probability, 1.0 - unsafe_probability))
    prediction_set = build_prediction_set(
        unsafe_probability=unsafe_probability,
        quantile=float(stack["conformal_summary"]["quantile"]),
    )

    result = {
        "unsafe_probability": round(unsafe_probability, 6),
        "unsafe_label": unsafe_label,
        "confidence": round(confidence, 6),
        "prediction_set": prediction_set,
    }
    trace_row = _build_prediction_row(pre_state, action_info, result)
    _append_row(prediction_state["trace_path"], PREDICTION_TRACE_FIELDS, trace_row)
    return result


def _build_prediction_frame(pre_state: Dict[str, object], action_info: Dict[str, str]):
    """Convert one runtime state/action pair into the inference input frame."""
    import pandas as pd

    row = {
        "pre_time": float(pre_state["time"]),
        "label_time": float(pre_state["time"]),
        "action": action_info["action"],
        "action_object": action_info["action_object"],
        "action_receptacle": action_info["action_receptacle"],
        "pre_microwave_on": _bool_to_int(pre_state["microwave_on"]),
        "pre_stove_on": _bool_to_int(pre_state["stove_on"]),
        "pre_cellphone_in_microwave": _bool_to_int(pre_state["cellphone_in_microwave"]),
        "pre_laptop_in_microwave": _bool_to_int(pre_state["laptop_in_microwave"]),
        "pre_microwave_on_duration": float(pre_state["microwave_on_duration"]),
        "pre_stove_on_duration": float(pre_state["stove_on_duration"]),
        "pre_faucet_on": _bool_to_int(pre_state["faucet_on"]),
        "pre_faucet_on_duration": float(pre_state["faucet_on_duration"]),
        "pre_cellphone_to_faucet_dist": float(pre_state["cellphone_to_faucet_dist"]),
        "pre_laptop_to_faucet_dist": float(pre_state["laptop_to_faucet_dist"]),
        "pre_holding_fragile_obj": _bool_to_int(pre_state["holding_fragile_obj"]),
        "pre_fragile_throw_event": _bool_to_int(pre_state["fragile_throw_event"]),
        "pre_throw_magnitude": float(pre_state["throw_magnitude"]),
    }
    return pd.DataFrame([row])


def _build_prediction_row(
    pre_state: Dict[str, object],
    action_info: Dict[str, str],
    result: Dict[str, object],
) -> Dict[str, object]:
    """Create one row for `prediction_trace.csv`."""
    return {
        "pre_time": pre_state["time"],
        "action": action_info["action"],
        "action_object": action_info["action_object"],
        "action_receptacle": action_info["action_receptacle"],
        "pre_microwave_on": pre_state["microwave_on"],
        "pre_stove_on": pre_state["stove_on"],
        "pre_cellphone_in_microwave": pre_state["cellphone_in_microwave"],
        "pre_laptop_in_microwave": pre_state["laptop_in_microwave"],
        "pre_microwave_on_duration": pre_state["microwave_on_duration"],
        "pre_stove_on_duration": pre_state["stove_on_duration"],
        "pre_faucet_on": pre_state["faucet_on"],
        "pre_faucet_on_duration": pre_state["faucet_on_duration"],
        "pre_cellphone_to_faucet_dist": pre_state["cellphone_to_faucet_dist"],
        "pre_laptop_to_faucet_dist": pre_state["laptop_to_faucet_dist"],
        "pre_holding_fragile_obj": pre_state["holding_fragile_obj"],
        "pre_fragile_throw_event": pre_state["fragile_throw_event"],
        "pre_throw_magnitude": pre_state["throw_magnitude"],
        "pred_unsafe_probability": result["unsafe_probability"],
        "pred_unsafe_label": result["unsafe_label"],
        "pred_confidence": result["confidence"],
        "pred_prediction_set": json.dumps(result["prediction_set"]),
    }


def _write_csv_header(path: Path, fieldnames) -> None:
    """Create an empty CSV file with a header row."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()


def _append_row(path: Path, fieldnames, row: Dict[str, object]) -> None:
    """Append one row using a stable field order."""
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writerow(row)


def _bool_to_int(value) -> int:
    """Normalize bool-like runtime values into 0/1 integers for inference."""
    text = str(value).strip().lower()
    return 1 if text in {"1", "true"} else 0
