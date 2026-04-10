"""Train the first-stage safety prediction model on dataset splits.

This script trains a binary classifier that maps:
    (pre_state, action) -> unsafe probability

The current stage focuses on a stable end-to-end baseline:
- load train/val/test data
- build feature matrices
- train a RandomForest classifier
- save the model and feature transformer
- write basic validation/test metrics
"""

import json
from pathlib import Path
from typing import Dict

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

try:
    from prediction.config import ARTIFACTS_DIR
    from prediction.dataset import load_all_dataset_splits
    from prediction.features import fit_transform_splits, save_feature_artifacts
except ImportError:
    from config import ARTIFACTS_DIR
    from dataset import load_all_dataset_splits
    from features import fit_transform_splits, save_feature_artifacts


def train_model(random_state: int = 7) -> Dict[str, object]:
    """Train the baseline safety classifier and save artifacts.

    Args:
        random_state: Random seed for reproducibility.

    Returns:
        Dictionary containing the trained model, metrics, and artifact paths.
    """
    splits = load_all_dataset_splits()
    transformer, transformed = fit_transform_splits(
        splits["train"],
        splits["val"],
        splits["test"],
    )
    feature_artifacts = save_feature_artifacts(transformer)

    y_train = splits["train"]["unsafe"].to_numpy()
    y_val = splits["val"]["unsafe"].to_numpy()
    y_test = splits["test"]["unsafe"].to_numpy()

    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(transformed["X_train"], y_train)

    val_metrics = evaluate_predictions(model, transformed["X_val"], y_val)
    test_metrics = evaluate_predictions(model, transformed["X_test"], y_test)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = ARTIFACTS_DIR / "model.joblib"
    metrics_path = ARTIFACTS_DIR / "metrics.json"
    joblib.dump(model, model_path)

    metrics_payload = {
        "model_type": "RandomForestClassifier",
        "validation": val_metrics,
        "test": test_metrics,
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "model": model,
        "metrics": metrics_payload,
        "artifacts": {
            "model": model_path,
            "metrics": metrics_path,
            **feature_artifacts,
        },
    }


def evaluate_predictions(model, X, y_true) -> Dict[str, float]:
    """Compute baseline binary-classification metrics.

    Args:
        model: Trained sklearn classifier with `predict` and `predict_proba`.
        X: Numeric feature matrix.
        y_true: Ground-truth labels.

    Returns:
        Dictionary with accuracy, precision, recall, f1, and probability stats.
    """
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 6),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 6),
        "avg_unsafe_probability": round(float(y_prob.mean()), 6),
        "max_unsafe_probability": round(float(y_prob.max()), 6),
        "min_unsafe_probability": round(float(y_prob.min()), 6),
    }


def main() -> None:
    """Train the baseline model and print saved artifact locations."""
    result = train_model()
    print("Training completed.")
    print("Artifacts:")
    for name, path in result["artifacts"].items():
        print(f"{name}: {path}")
    print("Validation metrics:", result["metrics"]["validation"])
    print("Test metrics:", result["metrics"]["test"])


if __name__ == "__main__":
    main()
