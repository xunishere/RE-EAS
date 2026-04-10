"""Runtime helpers for action-level RT-Lola safety monitoring.

This module owns the monitoring execution flow agreed for prediction data:
1. Initialize ``rtlola_stream.csv`` and ``monitor_trace.csv``.
2. After scene initialization, capture one initial state and append it only to
   ``rtlola_stream.csv``.
3. For each planner-visible task action:
   - read ``pre_state`` from the cached current state
   - execute the action externally
   - capture ``post_state``
   - append ``post_state`` to ``rtlola_stream.csv``
   - run RT-Lola immediately
   - append ``(pre_state, action, unsafe)`` to ``monitor_trace.csv``
   - cache ``current_state = post_state``

This module does not execute AI2-THOR actions itself. It coordinates state
snapshots, CSV persistence, and RT-Lola invocation around actions.
"""

import csv
import subprocess
from pathlib import Path
from typing import Dict, Optional

from monitor_signals import (
    STREAM_FIELDS,
    build_state_snapshot,
    clear_fragile_throw_event,
    clear_last_throw_magnitude,
    create_monitor_context,
    set_fragile_throw_event,
    set_last_throw_magnitude,
)


TRACE_FIELDS = [
    "pre_time",
    "label_time",
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
    "unsafe",
]


def init_monitoring(task_dir: str, controller, thresholds: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    """Initialize CSV files and capture the initial monitoring state.

    Args:
        task_dir: Log directory for the current task execution.
        controller: Live AI2-THOR controller.
        thresholds: Optional RT-Lola threshold overrides.

    Returns:
        A mutable monitoring runtime dictionary used by the action wrappers.
    """
    monitor_dir = Path(task_dir)
    stream_path = monitor_dir / "rtlola_stream.csv"
    trace_path = monitor_dir / "monitor_trace.csv"
    context = create_monitor_context(thresholds)
    initial_state = build_state_snapshot(controller, context)

    _write_csv_header(stream_path, STREAM_FIELDS)
    _write_csv_header(trace_path, TRACE_FIELDS)
    _append_row(stream_path, STREAM_FIELDS, initial_state)

    return {
        "enabled": True,
        "context": context,
        "stream_path": stream_path,
        "trace_path": trace_path,
        "current_state": initial_state,
        "last_unsafe": False,
        "last_rtlola_output": "",
    }


def build_action_info(
    action_name: str,
    action_object: str,
    action_receptacle: str = "0",
) -> Dict[str, str]:
    """Create normalized action metadata for one planner-visible action.

    Args:
        action_name: Planner-visible action label.
        action_object: Primary operated object.
        action_receptacle: Secondary receptacle target. Use ``"0"`` when absent.

    Returns:
        A normalized action descriptor dictionary.
    """
    return {
        "action": action_name,
        "action_object": action_object,
        "action_receptacle": action_receptacle or "0",
    }


def record_post_action(
    monitor_state: Optional[Dict[str, object]],
    controller,
    action_info: Dict[str, str],
    throw_magnitude: float = 0.0,
) -> Dict[str, object]:
    """Record one completed task action using the prediction-oriented workflow.

    Args:
        monitor_state: Mutable monitoring runtime returned by `init_monitoring`.
        controller: Live AI2-THOR controller.
        action_info: Normalized action metadata built by `build_action_info`.
        throw_magnitude: Throw strength for `ThrowObject`, else `0.0`.

    Returns:
        A dictionary containing:
        - `unsafe`: Whether RT-Lola reports the current stream as unsafe.
        - `pre_state`: Cached state before the action.
        - `post_state`: Newly captured state after the action.
        - `rtlola_output`: Raw RT-Lola stdout/stderr for debugging.
    """
    if not monitor_state or not monitor_state.get("enabled", False):
        return {
            "unsafe": False,
            "pre_state": None,
            "post_state": None,
            "rtlola_output": "",
        }

    pre_state = dict(monitor_state["current_state"])
    context = monitor_state["context"]
    if float(throw_magnitude) > 0.0:
        set_last_throw_magnitude(context, throw_magnitude)
        set_fragile_throw_event(
            context,
            pre_state["holding_fragile_obj"] == "true",
        )
    else:
        clear_last_throw_magnitude(context)
        clear_fragile_throw_event(context)

    post_state = build_state_snapshot(controller, context)
    _append_row(monitor_state["stream_path"], STREAM_FIELDS, post_state)

    unsafe, rtlola_output = run_rtlola(monitor_state["stream_path"])
    trace_row = _build_trace_row(
        pre_state=pre_state,
        label_time=post_state["time"],
        action_info=action_info,
        unsafe=unsafe,
    )
    _append_row(monitor_state["trace_path"], TRACE_FIELDS, trace_row)

    monitor_state["current_state"] = post_state
    monitor_state["last_unsafe"] = unsafe
    monitor_state["last_rtlola_output"] = rtlola_output
    clear_last_throw_magnitude(context)
    clear_fragile_throw_event(context)
    return {
        "unsafe": unsafe,
        "pre_state": pre_state,
        "post_state": post_state,
        "rtlola_output": rtlola_output,
    }


def run_rtlola(stream_path: Path) -> tuple:
    """Run RT-Lola on the current state stream.

    Args:
        stream_path: Path to ``rtlola_stream.csv``.

    Returns:
        A tuple ``(unsafe, raw_output)`` where `unsafe` is derived from the
        presence of ``[UNSAFE]`` in RT-Lola output.
    """
    proc = subprocess.run(
        ["rtlola-cli", "monitor", "RTlola/safe.spec", "--offline", "relative", "--csv-in", str(stream_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    return "[UNSAFE]" in output, output


def _build_trace_row(
    pre_state: Dict[str, object],
    label_time: float,
    action_info: Dict[str, str],
    unsafe: bool,
) -> Dict[str, object]:
    """Create one prediction sample row for ``monitor_trace.csv``.

    Args:
        pre_state: State snapshot captured before the action.
        label_time: Timestamp of the state captured after the action.
        action_info: Action metadata dictionary.
        unsafe: RT-Lola safety label after executing the action.

    Returns:
        A dictionary matching `TRACE_FIELDS`.
    """
    return {
        "pre_time": pre_state["time"],
        "label_time": label_time,
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
        "unsafe": unsafe,
    }


def _write_csv_header(path: Path, fieldnames) -> None:
    """Create an empty CSV file with a header row.

    Args:
        path: Destination CSV path.
        fieldnames: Ordered field list for the CSV file.
    """
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()


def _append_row(path: Path, fieldnames, row: Dict[str, object]) -> None:
    """Append one row to a CSV file using a stable field order.

    Args:
        path: Destination CSV path.
        fieldnames: Ordered field list for the CSV file.
        row: Row dictionary to append.
    """
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writerow(row)
