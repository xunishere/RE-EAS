"""Probability calibration and simple conformal utilities for safety prediction.

This module adds the post-training layer required by the project:
- calibrate unsafe probabilities
- convert probabilities into binary labels
- compute first-stage conformal/confidence summaries
"""

import json
from pathlib import Path
from typing import Dict, Tuple

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression

try:
    from prediction.config import ARTIFACTS_DIR
except ImportError:
    from config import ARTIFACTS_DIR


def fit_isotonic_calibrator(y_prob: np.ndarray, y_true: np.ndarray) -> IsotonicRegression:
    """Fit an isotonic calibrator on validation probabilities.

    Args:
        y_prob: Raw unsafe probabilities from the base classifier.
        y_true: Ground-truth binary labels for the same validation samples.

    Returns:
        Fitted `IsotonicRegression` calibrator.
    """
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit(y_prob, y_true)
    return calibrator


def apply_calibration(calibrator: IsotonicRegression, y_prob: np.ndarray) -> np.ndarray:
    """Apply a fitted calibrator to probability scores.

    Args:
        calibrator: Previously fitted isotonic regression model.
        y_prob: Raw unsafe probabilities to calibrate.

    Returns:
        Calibrated unsafe probabilities clipped into `[0, 1]`.
    """
    calibrated = calibrator.predict(y_prob)
    return np.clip(np.asarray(calibrated, dtype=float), 0.0, 1.0)


def probability_to_label(y_prob: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Convert unsafe probabilities into hard binary predictions.

    Args:
        y_prob: Unsafe probabilities.
        threshold: Positive-class decision threshold.

    Returns:
        Integer array of `0/1` predictions.
    """
    return (np.asarray(y_prob) >= float(threshold)).astype(int)


def compute_conformal_summary(
    calibration_prob: np.ndarray,
    calibration_true: np.ndarray,
    target_prob: np.ndarray,
    alpha: float = 0.1,
) -> Dict[str, object]:
    """Compute simple conformal confidence statistics for binary predictions.

    The current implementation uses a probability-margin nonconformity score:
    `score = 1 - p(correct_label)`.

    Args:
        calibration_prob: Calibrated probabilities on the calibration split.
        calibration_true: Ground-truth labels on the calibration split.
        target_prob: Calibrated probabilities on the target split.
        alpha: Miscoverage rate.

    Returns:
        A summary dictionary with:
        - `alpha`
        - `quantile`
        - `avg_interval_width`
        - `avg_confidence`
        - `prediction_sets`
    """
    calibration_prob = np.asarray(calibration_prob, dtype=float)
    calibration_true = np.asarray(calibration_true, dtype=int)
    target_prob = np.asarray(target_prob, dtype=float)

    correct_class_prob = np.where(calibration_true == 1, calibration_prob, 1.0 - calibration_prob)
    scores = 1.0 - correct_class_prob
    quantile = float(np.quantile(scores, 1.0 - alpha, method="higher"))

    prediction_sets = []
    interval_widths = []
    confidences = []
    for prob in target_prob:
        include_zero = (1.0 - (1.0 - prob)) <= quantile
        include_one = (1.0 - prob) <= quantile
        label_set = []
        if include_zero:
            label_set.append(0)
        if include_one:
            label_set.append(1)
        if not label_set:
            label_set = [int(prob >= 0.5)]

        prediction_sets.append(label_set)
        interval_widths.append(len(label_set))
        confidences.append(float(max(prob, 1.0 - prob)))

    return {
        "alpha": float(alpha),
        "quantile": round(quantile, 6),
        "avg_interval_width": round(float(np.mean(interval_widths)), 6),
        "avg_confidence": round(float(np.mean(confidences)), 6),
        "prediction_sets": prediction_sets,
    }


def save_calibration_artifacts(
    calibrator: IsotonicRegression,
    summary: Dict[str, object],
) -> Dict[str, Path]:
    """Persist the fitted calibrator and conformal summary artifacts.

    Args:
        calibrator: Fitted isotonic calibrator.
        summary: Conformal summary dictionary.

    Returns:
        Mapping of saved artifact paths.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    calibrator_path = ARTIFACTS_DIR / "calibrator.joblib"
    summary_path = ARTIFACTS_DIR / "conformal_summary.json"
    joblib.dump(calibrator, calibrator_path)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "calibrator": calibrator_path,
        "conformal_summary": summary_path,
    }
