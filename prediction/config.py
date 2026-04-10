"""Shared configuration for safety-prediction training data.

This module centralizes the fixed feature schema, action space, template names,
and train/validation/test dataset sizes used by the prediction pipeline.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATASET_DIR = DATA_DIR / "splits"
ARTIFACTS_DIR = BASE_DIR / "artifacts"


STATE_FEATURES: List[str] = [
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
]

ACTION_FEATURES: List[str] = [
    "action",
    "action_object",
    "action_receptacle",
]

TARGET_COLUMN = "unsafe"
TASK_ID_COLUMN = "task_id"
STEP_ID_COLUMN = "step_id"
PRE_TIME_COLUMN = "pre_time"
LABEL_TIME_COLUMN = "label_time"

ALL_FEATURES: List[str] = [*ACTION_FEATURES, *STATE_FEATURES]

BOOLEAN_STATE_FEATURES: List[str] = [
    "pre_microwave_on",
    "pre_stove_on",
    "pre_cellphone_in_microwave",
    "pre_laptop_in_microwave",
    "pre_faucet_on",
    "pre_holding_fragile_obj",
    "pre_fragile_throw_event",
]

NUMERIC_STATE_FEATURES: List[str] = [
    "pre_microwave_on_duration",
    "pre_stove_on_duration",
    "pre_faucet_on_duration",
    "pre_cellphone_to_faucet_dist",
    "pre_laptop_to_faucet_dist",
    "pre_throw_magnitude",
]

CATEGORICAL_ACTION_FEATURES: List[str] = [
    "action",
    "action_object",
    "action_receptacle",
]

ACTION_SPACE: List[str] = [
    "GoToObject",
    "PickupObject",
    "PutObject",
    "OpenObject",
    "CloseObject",
    "SwitchOn",
    "SwitchOff",
    "SliceObject",
    "BreakObject",
    "ThrowObject",
]

OBJECT_SPACE: List[str] = [
    "0",
    "Microwave",
    "StoveKnob",
    "Faucet",
    "Sink",
    "CellPhone",
    "Laptop",
    "Bowl",
    "Bread",
    "Plate",
    "Cup",
    "Mug",
    "Egg",
    "WineBottle",
]

RECEPTACLE_SPACE: List[str] = [
    "0",
    "Microwave",
    "CounterTop",
    "Sink",
]

SCENARIO_TEMPLATES: List[str] = [
    "microwave_cellphone",
    "microwave_laptop",
    "microwave_timeout",
    "stove_timeout",
    "water_timeout",
    "cellphone_water_proximity",
    "laptop_water_proximity",
    "fragile_throw",
    "faucet_quick_toggle_safe",
    "stove_quick_toggle_safe",
    "microwave_open_safe",
    "sink_approach_safe",
]

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "T_max_heat": 1.0,
    "T_max_water": 1.0,
    "delta_safe": 1.0,
    "theta_break": 5.0,
}


@dataclass(frozen=True)
class SyntheticSplitSize:
    """Dataset size configuration for one pipeline run.

    Args:
        train_tasks: Number of task trajectories for training.
        val_tasks: Number of task trajectories for validation.
        test_tasks: Number of task trajectories for testing.
    """

    train_tasks: int = 4000
    val_tasks: int = 800
    test_tasks: int = 800


DEFAULT_SPLIT_SIZE = SyntheticSplitSize()


def ensure_prediction_dirs() -> None:
    """Create the directory layout required by the new prediction pipeline."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
