"""Inference entrypoint for the safety prediction model.

This module loads the trained model stack and predicts:
- unsafe probability
- binary unsafe label
- confidence
- simple conformal prediction set
"""

import json
from pathlib import Path
from typing import Dict, Iterable, List

import joblib
import pandas as pd

try:
    from prediction.calibration import apply_calibration, probability_to_label
    from prediction.config import (
        ARTIFACTS_DIR,
        BOOLEAN_STATE_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
    )
    from prediction.features import load_feature_transformer, transform_for_inference
except ImportError:
    from calibration import apply_calibration, probability_to_label
    from config import (
        ARTIFACTS_DIR,
        BOOLEAN_STATE_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
    )
    from features import load_feature_transformer, transform_for_inference


ACTION_FIELDS = ["action", "action_object", "action_receptacle"]
REQUIRED_INPUT_FIELDS = [
    PRE_TIME_COLUMN,
    LABEL_TIME_COLUMN,
    *ACTION_FIELDS,
    *BOOLEAN_STATE_FEATURES,
    *NUMERIC_STATE_FEATURES,
]


def load_prediction_stack() -> Dict[str, object]:
    """Load the trained model, transformer, calibrator, and conformal summary.

    Returns:
        Dictionary containing all runtime artifacts required for inference.
    """
    model = joblib.load(ARTIFACTS_DIR / "model.joblib")
    transformer = load_feature_transformer()
    calibrator = joblib.load(ARTIFACTS_DIR / "calibrator.joblib")
    conformal_summary_path = ARTIFACTS_DIR / "conformal_summary.json"
    conformal_summary = json.loads(conformal_summary_path.read_text(encoding="utf-8"))
    return {
        "model": model,
        "transformer": transformer,
        "calibrator": calibrator,
        "conformal_summary": conformal_summary,
    }


def predict_one(sample: Dict[str, object]) -> Dict[str, object]:
    """Predict unsafe probability and label for one sample.

    Args:
        sample: One input sample following the cleaned monitor-trace schema.

    Returns:
        Dictionary with:
        - `unsafe_probability`
        - `unsafe_label`
        - `confidence`
        - `prediction_set`
    """
    stack = load_prediction_stack()
    frame = normalize_inference_input([sample])
    transformed = transform_for_inference(stack["transformer"], frame)
    raw_probability = stack["model"].predict_proba(transformed)[:, 1]
    calibrated_probability = apply_calibration(stack["calibrator"], raw_probability)
    unsafe_probability = float(calibrated_probability[0])
    unsafe_label = int(probability_to_label(calibrated_probability, threshold=0.5)[0])
    prediction_set = build_prediction_set(
        unsafe_probability=unsafe_probability,
        quantile=float(stack["conformal_summary"]["quantile"]),
    )
    confidence = float(max(unsafe_probability, 1.0 - unsafe_probability))
    return {
        "unsafe_probability": round(unsafe_probability, 6),
        "unsafe_label": unsafe_label,
        "confidence": round(confidence, 6),
        "prediction_set": prediction_set,
    }


def normalize_inference_input(samples: Iterable[Dict[str, object]]) -> pd.DataFrame:
    """Normalize one or more raw samples into inference-ready DataFrames.

    Args:
        samples: Iterable of raw sample dictionaries.

    Returns:
        A normalized DataFrame with stable column order and primitive types.

    Exceptions:
        ValueError: Raised when required fields are missing.
    """
    rows: List[Dict[str, object]] = []
    for sample in samples:
        missing = [field for field in REQUIRED_INPUT_FIELDS if field not in sample]
        if missing:
            raise ValueError(f"Missing required inference fields: {missing}")

        row = {
            PRE_TIME_COLUMN: float(sample[PRE_TIME_COLUMN]),
            LABEL_TIME_COLUMN: float(sample[LABEL_TIME_COLUMN]),
            "action": str(sample["action"]),
            "action_object": str(sample["action_object"]),
            "action_receptacle": str(sample["action_receptacle"]),
        }
        for field in BOOLEAN_STATE_FEATURES:
            row[field] = _normalize_bool_like(sample[field])
        for field in NUMERIC_STATE_FEATURES:
            row[field] = float(sample[field])
        rows.append(row)

    return pd.DataFrame(rows, columns=REQUIRED_INPUT_FIELDS)


def build_prediction_set(unsafe_probability: float, quantile: float) -> List[int]:
    """Build a simple binary conformal prediction set from calibrated probability.

    Args:
        unsafe_probability: Calibrated probability for class `1`.
        quantile: Stored nonconformity threshold from calibration.

    Returns:
        Prediction set containing one or both class labels.
    """
    include_zero = unsafe_probability <= quantile
    include_one = (1.0 - unsafe_probability) <= quantile

    prediction_set = []
    if include_zero:
        prediction_set.append(0)
    if include_one:
        prediction_set.append(1)
    if not prediction_set:
        prediction_set = [int(unsafe_probability >= 0.5)]
    return prediction_set


def _normalize_bool_like(value) -> int:
    """Convert a bool-like inference value into stable 0/1 integers."""
    text = str(value).strip().lower()
    if text in {"1", "true"}:
        return 1
    if text in {"0", "false"}:
        return 0
    return int(bool(value))


def main() -> None:
    """Run one small smoke-test inference using a representative unsafe sample."""
    sample = {
        "pre_time": 0.5,
        "label_time": 1.0,
        "action": "SwitchOn",
        "action_object": "Microwave",
        "action_receptacle": "0",
        "pre_microwave_on": 0,
        "pre_stove_on": 0,
        "pre_cellphone_in_microwave": 1,
        "pre_laptop_in_microwave": 0,
        "pre_microwave_on_duration": 0.0,
        "pre_stove_on_duration": 0.0,
        "pre_faucet_on": 0,
        "pre_faucet_on_duration": 0.0,
        "pre_cellphone_to_faucet_dist": 2.0,
        "pre_laptop_to_faucet_dist": 999.0,
        "pre_holding_fragile_obj": 0,
        "pre_fragile_throw_event": 0,
        "pre_throw_magnitude": 0.0,
    }
    result = predict_one(sample)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
