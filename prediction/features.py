"""Feature preparation utilities for the safety prediction model.

This module transforms cleaned DataFrames into model-ready numeric feature
matrices. It keeps the feature pipeline reusable for both training and future
inference so that categorical encoding stays consistent across splits.
"""

import json
from pathlib import Path
from typing import Dict, Tuple

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

try:
    from prediction.config import (
        ACTION_FEATURES,
        ARTIFACTS_DIR,
        BOOLEAN_STATE_FEATURES,
        CATEGORICAL_ACTION_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
    )
except ImportError:
    from config import (
        ACTION_FEATURES,
        ARTIFACTS_DIR,
        BOOLEAN_STATE_FEATURES,
        CATEGORICAL_ACTION_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
    )


TIME_FEATURES = [PRE_TIME_COLUMN, LABEL_TIME_COLUMN]


def build_feature_pipeline() -> ColumnTransformer:
    """Build the shared column transformer for training and inference.

    Returns:
        A `ColumnTransformer` that one-hot encodes action fields and passes
        numeric/binary features through unchanged.
    """
    passthrough_features = [
        *TIME_FEATURES,
        *BOOLEAN_STATE_FEATURES,
        *NUMERIC_STATE_FEATURES,
    ]
    return ColumnTransformer(
        transformers=[
            (
                "categorical_action",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_ACTION_FEATURES,
            ),
            (
                "passthrough_state",
                "passthrough",
                passthrough_features,
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def fit_transform_splits(
    train_frame: pd.DataFrame,
    val_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
) -> Tuple[ColumnTransformer, Dict[str, object]]:
    """Fit the feature transformer on train and transform all splits.

    Args:
        train_frame: Cleaned training DataFrame.
        val_frame: Cleaned validation DataFrame.
        test_frame: Cleaned testing DataFrame.

    Returns:
        A tuple `(transformer, transformed)` where:
        - `transformer` is the fitted `ColumnTransformer`
        - `transformed` is a mapping with `X_train`, `X_val`, `X_test`
    """
    transformer = build_feature_pipeline()
    X_train = transformer.fit_transform(_select_feature_frame(train_frame))
    X_val = transformer.transform(_select_feature_frame(val_frame))
    X_test = transformer.transform(_select_feature_frame(test_frame))
    return transformer, {
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
    }


def transform_for_inference(
    transformer: ColumnTransformer,
    frame: pd.DataFrame,
):
    """Transform one or more samples using an already fitted transformer.

    Args:
        transformer: Previously fitted feature transformer.
        frame: Cleaned input frame containing the required feature columns.

    Returns:
        Transformed numeric feature matrix.
    """
    return transformer.transform(_select_feature_frame(frame))


def save_feature_artifacts(transformer: ColumnTransformer) -> Dict[str, Path]:
    """Persist the fitted transformer and its feature schema.

    Args:
        transformer: Fitted `ColumnTransformer`.

    Returns:
        Paths of the saved artifacts.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    transformer_path = ARTIFACTS_DIR / "feature_transformer.joblib"
    schema_path = ARTIFACTS_DIR / "feature_schema.json"

    joblib.dump(transformer, transformer_path)
    feature_schema = {
        "input_columns": [
            *TIME_FEATURES,
            *ACTION_FEATURES,
            *BOOLEAN_STATE_FEATURES,
            *NUMERIC_STATE_FEATURES,
        ],
        "output_columns": list(transformer.get_feature_names_out()),
        "categorical_action_features": CATEGORICAL_ACTION_FEATURES,
        "boolean_state_features": BOOLEAN_STATE_FEATURES,
        "numeric_state_features": NUMERIC_STATE_FEATURES,
        "time_features": TIME_FEATURES,
    }
    schema_path.write_text(json.dumps(feature_schema, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "transformer": transformer_path,
        "schema": schema_path,
    }


def load_feature_transformer(path: Path = None) -> ColumnTransformer:
    """Load a previously saved feature transformer.

    Args:
        path: Optional transformer path. Defaults to the standard artifact path.

    Returns:
        The loaded `ColumnTransformer`.
    """
    transformer_path = path or (ARTIFACTS_DIR / "feature_transformer.joblib")
    return joblib.load(transformer_path)


def _select_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Select and order the exact feature columns expected by the transformer.

    Args:
        frame: Cleaned DataFrame containing at least the required feature columns.

    Returns:
        A feature-only DataFrame with stable column ordering.
    """
    feature_columns = [
        *TIME_FEATURES,
        *ACTION_FEATURES,
        *BOOLEAN_STATE_FEATURES,
        *NUMERIC_STATE_FEATURES,
    ]
    return frame[feature_columns].copy()
