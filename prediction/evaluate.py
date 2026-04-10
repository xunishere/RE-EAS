"""Evaluation entrypoint for the safety prediction pipeline.

This module evaluates the trained model with calibrated probabilities and
conformal summaries on the validation and test splits.
"""

import json
from pathlib import Path
from typing import Dict

import joblib
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

try:
    from prediction.calibration import (
        apply_calibration,
        compute_conformal_summary,
        probability_to_label,
    )
    from prediction.config import ARTIFACTS_DIR
    from prediction.dataset import load_all_dataset_splits
    from prediction.features import fit_transform_splits
except ImportError:
    from calibration import (
        apply_calibration,
        compute_conformal_summary,
        probability_to_label,
    )
    from config import ARTIFACTS_DIR
    from dataset import load_all_dataset_splits
    from features import fit_transform_splits


def evaluate_pipeline() -> Dict[str, object]:
    """Evaluate the full prediction pipeline on validation and test splits.

    Returns:
        Dictionary containing validation/test metrics and artifact output path.
    """
    splits = load_all_dataset_splits()
    _, transformed = fit_transform_splits(splits["train"], splits["val"], splits["test"])

    model = joblib.load(ARTIFACTS_DIR / "model.joblib")
    calibrator = joblib.load(ARTIFACTS_DIR / "calibrator.joblib")

    val_prob_raw = model.predict_proba(transformed["X_val"])[:, 1]
    test_prob_raw = model.predict_proba(transformed["X_test"])[:, 1]

    val_prob = apply_calibration(calibrator, val_prob_raw)
    test_prob = apply_calibration(calibrator, test_prob_raw)

    val_true = splits["val"]["unsafe"].to_numpy()
    test_true = splits["test"]["unsafe"].to_numpy()

    val_summary = evaluate_one_split("validation", val_true, val_prob, val_prob)
    test_summary = evaluate_one_split("test", test_true, test_prob, val_prob, val_true)

    payload = {
        "validation": val_summary,
        "test": test_summary,
    }
    output_path = ARTIFACTS_DIR / "evaluation.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "metrics": payload,
        "artifact": output_path,
    }


def evaluate_one_split(
    split_name: str,
    y_true,
    y_prob,
    calibration_prob,
    calibration_true=None,
) -> Dict[str, object]:
    """Evaluate one split with calibrated probabilities and conformal summary.

    Args:
        split_name: Human-readable split label.
        y_true: Ground-truth labels for the evaluated split.
        y_prob: Calibrated unsafe probabilities for the evaluated split.
        calibration_prob: Probabilities used to build the conformal summary.
        calibration_true: Ground-truth labels for the calibration split.
            Defaults to `y_true` when omitted.

    Returns:
        Dictionary with classification metrics and conformal summary statistics.
    """
    if calibration_true is None:
        calibration_true = y_true

    y_pred = probability_to_label(y_prob, threshold=0.5)
    conformal_summary = compute_conformal_summary(
        calibration_prob=calibration_prob,
        calibration_true=calibration_true,
        target_prob=y_prob,
    )

    return {
        "split": split_name,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 6),
        "avg_unsafe_probability": round(float(y_prob.mean()), 6),
        "max_unsafe_probability": round(float(y_prob.max()), 6),
        "min_unsafe_probability": round(float(y_prob.min()), 6),
        "conformal": {
            "alpha": conformal_summary["alpha"],
            "quantile": conformal_summary["quantile"],
            "avg_interval_width": conformal_summary["avg_interval_width"],
            "avg_confidence": conformal_summary["avg_confidence"],
        },
    }


def main() -> None:
    """Run the evaluation pipeline and print the stored results path."""
    result = evaluate_pipeline()
    print("Evaluation completed.")
    print("artifact:", result["artifact"])
    print("validation:", result["metrics"]["validation"])
    print("test:", result["metrics"]["test"])


if __name__ == "__main__":
    main()
