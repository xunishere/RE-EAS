"""Runtime adapters for temporal prediction baselines used in RQ3."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Optional

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "baseline_model" / "temporal_prediction_artifacts"

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
    "temporal_predictor",
]


def init_prediction_runtime(task_dir: str, method: str) -> Dict[str, object]:
    trace_path = Path(task_dir) / "prediction_trace.csv"
    _write_csv_header(trace_path, PREDICTION_TRACE_FIELDS)
    artifact_path = ARTIFACT_DIR / f"{method}_runtime.joblib"
    if not artifact_path.exists():
        raise FileNotFoundError(
            f"Missing temporal predictor artifact: {artifact_path}. "
            "Run scripts/train_temporal_prediction_runtimes.py first."
        )
    artifact = joblib.load(artifact_path)
    return {
        "enabled": True,
        "method": method,
        "trace_path": trace_path,
        "artifact": artifact,
        "threshold": float(artifact.get("threshold", 0.5)),
    }


def record_prediction(
    prediction_state: Optional[Dict[str, object]],
    pre_state: Dict[str, object],
    action_info: Dict[str, str],
) -> Dict[str, object]:
    if not prediction_state or not prediction_state.get("enabled", False):
        return _safe_result()

    method = str(prediction_state["method"])
    artifact = prediction_state["artifact"]
    frame = _build_prediction_frame(pre_state, action_info)
    transformed = artifact["transformer"].transform(frame)

    if method == "multidimspci":
        center = float(np.clip(artifact["model"].predict(transformed)[0], 0.0, 1.0))
        unsafe_probability = float(np.clip(center + float(artifact["residual_quantile"]), 0.0, 1.0))
    elif method == "cptc":
        state_prob = artifact["state_model"].predict_proba(transformed)[0]
        state_scores = []
        for model, quantile in zip(artifact["state_models"], artifact["state_quantiles"]):
            state_scores.append(float(np.clip(model.predict(transformed)[0] + float(quantile), 0.0, 1.0)))
        unsafe_probability = float(np.clip(max(state_scores), 0.0, 1.0))
        point_probability = float(
            np.clip(
                sum(
                    prob * float(np.clip(model.predict(transformed)[0], 0.0, 1.0))
                    for prob, model in zip(state_prob, artifact["state_models"])
                ),
                0.0,
                1.0,
            )
        )
        unsafe_probability = max(unsafe_probability, point_probability)
    else:
        raise ValueError(f"Unknown temporal predictor method: {method}")

    threshold = float(prediction_state["threshold"])
    unsafe_label = 1 if unsafe_probability >= threshold else 0
    if _hazard_requires_repair(pre_state, action_info):
        unsafe_probability = max(unsafe_probability, threshold)
        unsafe_label = 1
    confidence = float(max(unsafe_probability, 1.0 - unsafe_probability))
    prediction_set = [1] if unsafe_label else [0]

    result = {
        "unsafe_probability": round(unsafe_probability, 6),
        "unsafe_label": unsafe_label,
        "confidence": round(confidence, 6),
        "prediction_set": prediction_set,
    }
    row = _build_prediction_row(pre_state, action_info, result, method)
    _append_row(prediction_state["trace_path"], PREDICTION_TRACE_FIELDS, row)
    return result


def _safe_result() -> Dict[str, object]:
    return {
        "unsafe_probability": 0.0,
        "unsafe_label": 0,
        "confidence": 1.0,
        "prediction_set": [0],
    }


def _build_prediction_frame(pre_state: Dict[str, object], action_info: Dict[str, str]) -> pd.DataFrame:
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
    method: str,
) -> Dict[str, object]:
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
        "temporal_predictor": method,
    }


def _write_csv_header(path: Path, fieldnames) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writeheader()


def _append_row(path: Path, fieldnames, row: Dict[str, object]) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writerow(row)


def _bool_to_int(value) -> int:
    return 1 if str(value).strip().lower() in {"1", "true"} else 0


def _hazard_requires_repair(pre_state: Dict[str, object], action_info: Dict[str, str]) -> bool:
    action = str(action_info.get("action", ""))
    action_object = str(action_info.get("action_object", ""))
    if action == "ThrowObject" and _is_sensitive_throw_object(action_object):
        return True
    if _bool_to_int(pre_state.get("faucet_on", False)):
        return not (action == "SwitchOff" and action_object == "Faucet")
    if _bool_to_int(pre_state.get("stove_on", False)):
        return not (action == "SwitchOff" and action_object == "StoveKnob")
    if _bool_to_int(pre_state.get("microwave_on", False)):
        return not (action == "SwitchOff" and action_object == "Microwave")
    return False


def _is_sensitive_throw_object(object_type: str) -> bool:
    normalized = str(object_type).replace(" ", "").lower()
    sensitive_types = {
        "plate",
        "bowl",
        "cup",
        "mug",
        "vase",
        "egg",
        "winebottle",
        "laptop",
        "cellphone",
        "alarmclock",
        "cd",
        "keychain",
        "box",
    }
    return any(sensitive in normalized for sensitive in sensitive_types)
