"""Dataset loading and cleaning utilities for safety prediction training.

This module sits between raw CSV generation and feature encoding. It loads
split files, validates the schema, normalizes primitive types, sorts each task
trajectory, and enforces the hard rule that only the first unsafe sample per
task is kept.
"""

from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

try:
    from prediction.config import (
        ACTION_FEATURES,
        ALL_FEATURES,
        BOOLEAN_STATE_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
        STATE_FEATURES,
        STEP_ID_COLUMN,
        DATASET_DIR,
        TARGET_COLUMN,
        TASK_ID_COLUMN,
    )
except ImportError:
    from config import (
        ACTION_FEATURES,
        ALL_FEATURES,
        BOOLEAN_STATE_FEATURES,
        LABEL_TIME_COLUMN,
        NUMERIC_STATE_FEATURES,
        PRE_TIME_COLUMN,
        STATE_FEATURES,
        STEP_ID_COLUMN,
        DATASET_DIR,
        TARGET_COLUMN,
        TASK_ID_COLUMN,
    )


REQUIRED_COLUMNS: List[str] = [
    TASK_ID_COLUMN,
    STEP_ID_COLUMN,
    PRE_TIME_COLUMN,
    LABEL_TIME_COLUMN,
    *ACTION_FEATURES,
    *STATE_FEATURES,
    TARGET_COLUMN,
]


def load_dataset_split(split_name: str) -> pd.DataFrame:
    """Load and clean one dataset split.

    Args:
        split_name: One of `train`, `val`, or `test`.

    Returns:
        A cleaned DataFrame ready for feature encoding.

    Exceptions:
        FileNotFoundError: Raised when the split file does not exist.
        ValueError: Raised when required columns are missing.
    """
    split_path = DATASET_DIR / f"{split_name}.csv"
    if not split_path.exists():
        raise FileNotFoundError(f"Dataset split not found: {split_path}")

    frame = pd.read_csv(split_path)
    validate_schema(frame)
    cleaned = normalize_types(frame)
    cleaned = sort_trajectory_rows(cleaned)
    cleaned = keep_first_unsafe_only(cleaned)
    return cleaned.reset_index(drop=True)


def load_all_dataset_splits() -> Dict[str, pd.DataFrame]:
    """Load train/val/test datasets with the same cleaning pipeline.

    Returns:
        Mapping from split name to cleaned DataFrame.
    """
    return {
        "train": load_dataset_split("train"),
        "val": load_dataset_split("val"),
        "test": load_dataset_split("test"),
    }


def validate_schema(frame: pd.DataFrame) -> None:
    """Ensure the input DataFrame contains the required training columns.

    Args:
        frame: Raw DataFrame loaded from disk.

    Exceptions:
        ValueError: Raised when one or more required columns are missing.
    """
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")


def normalize_types(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize primitive dtypes so downstream modules see consistent values.

    Args:
        frame: Raw or partially processed DataFrame.

    Returns:
        A copy with stable dtypes for ids, times, booleans, numerics, and label.
    """
    normalized = frame.copy()

    normalized[TASK_ID_COLUMN] = normalized[TASK_ID_COLUMN].astype(str)
    normalized[STEP_ID_COLUMN] = normalized[STEP_ID_COLUMN].astype(int)
    normalized[PRE_TIME_COLUMN] = normalized[PRE_TIME_COLUMN].astype(float)
    normalized[LABEL_TIME_COLUMN] = normalized[LABEL_TIME_COLUMN].astype(float)
    normalized[TARGET_COLUMN] = normalized[TARGET_COLUMN].astype(int)

    for column in ACTION_FEATURES:
        normalized[column] = normalized[column].astype(str)

    for column in BOOLEAN_STATE_FEATURES:
        normalized[column] = normalized[column].apply(_normalize_bool_like)

    for column in NUMERIC_STATE_FEATURES:
        normalized[column] = normalized[column].astype(float)

    return normalized


def sort_trajectory_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort each task trajectory by the agreed temporal order.

    Args:
        frame: Cleaned DataFrame with normalized ids and times.

    Returns:
        DataFrame sorted by task id, step id, pre time, and label time.
    """
    return frame.sort_values(
        by=[TASK_ID_COLUMN, STEP_ID_COLUMN, PRE_TIME_COLUMN, LABEL_TIME_COLUMN],
        kind="stable",
    )


def keep_first_unsafe_only(frame: pd.DataFrame) -> pd.DataFrame:
    """Remove persistent unsafe tails while keeping the first unsafe sample.

    Args:
        frame: Task-sorted DataFrame.

    Returns:
        A filtered DataFrame where each task keeps all safe rows up to and
        including the first unsafe row, then drops the rest.
    """
    kept_rows = []
    for _, task_frame in frame.groupby(TASK_ID_COLUMN, sort=False):
        seen_unsafe = False
        for _, row in task_frame.iterrows():
            if seen_unsafe:
                break
            kept_rows.append(row.to_dict())
            if int(row[TARGET_COLUMN]) == 1:
                seen_unsafe = True
    return pd.DataFrame(kept_rows, columns=frame.columns)


def split_xy(frame: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """Split a cleaned DataFrame into features and label.

    Args:
        frame: Cleaned DataFrame produced by this module.

    Returns:
        A tuple `(X, y)` where:
        - `X` contains action and pre-state features plus aligned times.
        - `y` contains the binary unsafe label.
    """
    feature_columns = [
        PRE_TIME_COLUMN,
        LABEL_TIME_COLUMN,
        *ACTION_FEATURES,
        *STATE_FEATURES,
    ]
    X = frame[feature_columns].copy()
    y = frame[TARGET_COLUMN].copy()
    return X, y


def _normalize_bool_like(value) -> int:
    """Convert a mixed bool-like value into stable 0/1 integers.

    Args:
        value: Bool-like value coming from CSV or DataFrame.

    Returns:
        Integer `0` or `1`.
    """
    text = str(value).strip().lower()
    if text in {"1", "true"}:
        return 1
    if text in {"0", "false"}:
        return 0
    return int(bool(value))
