"""Train runtime-compatible artifacts for temporal prediction baselines.

The original MultiDimSPCI and CPTC repositories are sequence-level conformal
predictors. For online SMART-LLM execution, we adapt them into action-level
repair triggers and save lightweight artifacts that can be loaded by the batch
pipeline without retraining for every task.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.mixture import GaussianMixture


ROOT = Path(__file__).resolve().parents[1]
SERVER_ARTIFACTS_DIR = ROOT / "baseline_model" / "server_prediction" / "artifacts"
SERVER_SPLITS_DIR = ROOT / "baseline_model" / "server_prediction" / "data" / "splits"
OUTPUT_DIR = ROOT / "baseline_model" / "temporal_prediction_artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train runtime temporal predictor artifacts.")
    parser.add_argument("--data-dir", type=Path, default=SERVER_SPLITS_DIR)
    parser.add_argument("--artifact-dir", type=Path, default=SERVER_ARTIFACTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument("--n-estimators", type=int, default=128)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--n-states", type=int, default=3)
    return parser.parse_args()


def load_split(data_dir: Path, split: str) -> pd.DataFrame:
    frame = pd.read_csv(data_dir / f"{split}.csv")
    frame["unsafe"] = frame["unsafe"].astype(int)
    return frame.sort_values(["task_id", "step_id", "pre_time", "label_time"], kind="stable").reset_index(drop=True)


def build_regressor(n_estimators: int, max_depth: int) -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=2,
        random_state=7,
        n_jobs=-1,
    )


def metrics(y_true: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    pred = (score >= threshold).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, pred)), 6),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 6),
        "avg_score": round(float(np.mean(score)), 6),
        "max_score": round(float(np.max(score)), 6),
        "min_score": round(float(np.min(score)), 6),
    }


def train_multidimspci(args: argparse.Namespace, transformer, train: pd.DataFrame, test: pd.DataFrame) -> Dict[str, object]:
    x_train = transformer.transform(train)
    x_test = transformer.transform(test)
    y_train = train["unsafe"].to_numpy(dtype=float)
    y_test = test["unsafe"].to_numpy(dtype=int)

    regressor = build_regressor(args.n_estimators, args.max_depth)
    regressor.fit(x_train, y_train)
    train_center = np.clip(regressor.predict(x_train), 0.0, 1.0)
    test_center = np.clip(regressor.predict(x_test), 0.0, 1.0)
    residual_quantile = float(np.quantile(np.abs(y_train - train_center), 1.0 - args.alpha))
    gate_score = np.clip(test_center + residual_quantile, 0.0, 1.0)

    return {
        "method": "MultiDimSPCI",
        "model": regressor,
        "threshold": 0.5,
        "alpha": args.alpha,
        "residual_quantile": residual_quantile,
        "test_metrics": metrics(y_test, gate_score),
        "point_metrics": metrics(y_test, test_center),
    }


def train_cptc(args: argparse.Namespace, transformer, train: pd.DataFrame, test: pd.DataFrame) -> Dict[str, object]:
    x_train = transformer.transform(train)
    x_test = transformer.transform(test)
    x_all = np.vstack([x_train, x_test])
    y_train = train["unsafe"].to_numpy(dtype=float)
    y_test = test["unsafe"].to_numpy(dtype=int)

    base = build_regressor(args.n_estimators, args.max_depth)
    base.fit(x_train, y_train)

    state_model = GaussianMixture(
        n_components=args.n_states,
        covariance_type="full",
        random_state=7,
        reg_covar=1e-4,
        init_params="random_from_data",
    )
    state_model.fit(x_train)
    z_train = state_model.predict_proba(x_train)
    train_state_ids = np.argmax(z_train, axis=1)

    state_models: List[RandomForestRegressor] = []
    state_quantiles: List[float] = []
    for state in range(args.n_states):
        mask = train_state_ids == state
        model = build_regressor(args.n_estimators, args.max_depth)
        if int(mask.sum()) >= 10:
            model.fit(x_train[mask], y_train[mask])
            train_pred = np.clip(model.predict(x_train[mask]), 0.0, 1.0)
            residuals = np.abs(y_train[mask] - train_pred)
        else:
            model.fit(x_train, y_train)
            train_pred = np.clip(model.predict(x_train), 0.0, 1.0)
            residuals = np.abs(y_train - train_pred)
        state_models.append(model)
        state_quantiles.append(float(np.quantile(residuals, 1.0 - args.alpha)))

    z_all = state_model.predict_proba(x_all)
    z_test = z_all[len(x_train):]
    state_means = np.column_stack([np.clip(model.predict(x_test), 0.0, 1.0) for model in state_models])
    point_score = np.sum(z_test * state_means, axis=1)
    upper_score = np.max(state_means + np.asarray(state_quantiles).reshape(1, -1), axis=1)
    upper_score = np.clip(upper_score, 0.0, 1.0)

    return {
        "method": "CPTC",
        "base_model": base,
        "state_model": state_model,
        "state_models": state_models,
        "state_quantiles": state_quantiles,
        "threshold": 0.5,
        "alpha": args.alpha,
        "n_states": args.n_states,
        "test_metrics": metrics(y_test, upper_score),
        "point_metrics": metrics(y_test, point_score),
    }


def serializable_summary(artifact: Dict[str, object]) -> Dict[str, object]:
    return {
        key: value
        for key, value in artifact.items()
        if key not in {"model", "base_model", "state_model", "state_models", "transformer"}
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    transformer = joblib.load(args.artifact_dir / "feature_transformer.joblib")
    train = load_split(args.data_dir, "train")
    test = load_split(args.data_dir, "test")

    multidimspci = train_multidimspci(args, transformer, train, test)
    multidimspci["transformer"] = transformer
    cptc = train_cptc(args, transformer, train, test)
    cptc["transformer"] = transformer

    joblib.dump(multidimspci, args.output_dir / "multidimspci_runtime.joblib")
    joblib.dump(cptc, args.output_dir / "cptc_runtime.joblib")
    summary = {
        "multidimspci": serializable_summary(multidimspci),
        "cptc": serializable_summary(cptc),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
    }
    (args.output_dir / "runtime_temporal_metrics.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
