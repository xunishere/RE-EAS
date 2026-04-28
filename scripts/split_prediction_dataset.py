"""Split the collected monitor dataset into train/val/test CSV files.

This script performs a task-level split so that all rows from the same task
trajectory stay in the same partition. The default output locations match the
existing training pipeline under `prediction/data/splits/`.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import List, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "prediction" / "data" / "splits" / "train.csv"
DEFAULT_SPLIT_DIR = ROOT / "prediction" / "data" / "splits"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.7142857)
    parser.add_argument("--val-ratio", type=float, default=0.1428571)
    parser.add_argument("--test-ratio", type=float, default=0.1428572)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Split ratios must sum to 1.0, got {total}")


def compute_split_sizes(n: int, train_ratio: float, val_ratio: float) -> Tuple[int, int, int]:
    train_n = int(round(n * train_ratio))
    val_n = int(round(n * val_ratio))
    if train_n >= n:
        train_n = max(1, n - 2)
    if train_n + val_n >= n:
        val_n = max(1, n - train_n - 1)
    test_n = n - train_n - val_n
    if test_n <= 0:
        test_n = 1
        if val_n > 1:
            val_n -= 1
        else:
            train_n -= 1
    return train_n, val_n, test_n


def main() -> None:
    args = parse_args()
    validate_ratios(args.train_ratio, args.val_ratio, args.test_ratio)

    frame = pd.read_csv(args.input)
    if "task_id" not in frame.columns:
        raise ValueError("Input dataset must contain a task_id column.")

    task_ids: List[str] = sorted(frame["task_id"].astype(str).unique().tolist())
    if len(task_ids) < 3:
        raise ValueError("Need at least 3 task trajectories to create train/val/test splits.")

    random.seed(args.seed)
    random.shuffle(task_ids)

    train_n, val_n, test_n = compute_split_sizes(len(task_ids), args.train_ratio, args.val_ratio)
    train_ids = set(task_ids[:train_n])
    val_ids = set(task_ids[train_n : train_n + val_n])
    test_ids = set(task_ids[train_n + val_n :])

    train_df = frame[frame["task_id"].astype(str).isin(train_ids)].copy()
    val_df = frame[frame["task_id"].astype(str).isin(val_ids)].copy()
    test_df = frame[frame["task_id"].astype(str).isin(test_ids)].copy()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    train_path = args.output_dir / "train.csv"
    val_path = args.output_dir / "val.csv"
    test_path = args.output_dir / "test.csv"

    train_df.to_csv(train_path, index=False, encoding="utf-8")
    val_df.to_csv(val_path, index=False, encoding="utf-8")
    test_df.to_csv(test_path, index=False, encoding="utf-8")

    print(f"input={args.input}")
    print(f"train={train_path} rows={len(train_df)} tasks={len(train_ids)}")
    print(f"val={val_path} rows={len(val_df)} tasks={len(val_ids)}")
    print(f"test={test_path} rows={len(test_df)} tasks={len(test_ids)}")


if __name__ == "__main__":
    main()
