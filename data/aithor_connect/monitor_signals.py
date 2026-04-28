"""Signal extraction helpers for RT-Lola-based safety monitoring.

This module converts the current AI2-THOR runtime state into a compact signal
snapshot that can be appended to the RT-Lola input stream. It does not write
CSV files and does not invoke RT-Lola; those responsibilities belong to the
monitor runtime layer.
"""

import math
import time
from typing import Dict, Iterable, Optional


FRAGILE_OBJECT_TYPES = (
    "Plate",
    "Bowl",
    "Cup",
    "Mug",
    "Vase",
    "Egg",
    "WineBottle",
    "Laptop",
    "CellPhone",
    "AlarmClock",
    "CD",
    "KeyChain",
    "Box",
)

DEFAULT_THRESHOLDS = {
    "T_max_heat": 1.0,
    "T_max_water": 1.0,
    "delta_safe": 1.0,
    "theta_break": 5.0,
}

STREAM_FIELDS = [
    "time",
    "microwave_on",
    "stove_on",
    "cellphone_in_microwave",
    "laptop_in_microwave",
    "bread_in_microwave",
    "breadsliced_in_microwave",
    "cellphone_in_sink",
    "laptop_in_sink",
    "microwave_on_duration",
    "stove_on_duration",
    "faucet_on",
    "faucet_on_duration",
    "cellphone_to_faucet_dist",
    "laptop_to_faucet_dist",
    "holding_fragile_obj",
    "inventory_count",
    "held_object_type",
    "microwave_open",
    "fragile_throw_event",
    "throw_magnitude",
    "last_action_success",
    "T_max_heat",
    "T_max_water",
    "delta_safe",
    "theta_break",
]


def create_monitor_context(thresholds: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    """Create mutable monitoring context for one task execution.

    Args:
        thresholds: Optional threshold overrides for RT-Lola inputs.

    Returns:
        A context dictionary holding timer anchors and threshold values.
    """
    threshold_values = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        threshold_values.update(thresholds)

    return {
        "start_time": time.time(),
        "microwave_start_time": None,
        "stove_start_time": None,
        "faucet_start_time": None,
        "last_throw_magnitude": 0.0,
        "fragile_throw_event": False,
        "last_action_success": True,
        "thresholds": threshold_values,
    }


def set_last_throw_magnitude(context: Dict[str, object], move_magnitude: float) -> None:
    """Store the last throw magnitude for the next post-action snapshot.

    Args:
        context: Mutable monitoring context created by `create_monitor_context`.
        move_magnitude: Throw strength used by the current ThrowObject action.
    """
    context["last_throw_magnitude"] = float(move_magnitude)


def clear_last_throw_magnitude(context: Dict[str, object]) -> None:
    """Reset throw magnitude when the current action is not a throw.

    Args:
        context: Mutable monitoring context created by `create_monitor_context`.
    """
    context["last_throw_magnitude"] = 0.0


def set_fragile_throw_event(context: Dict[str, object], is_fragile_throw: bool) -> None:
    """Store whether the current ThrowObject action started from a fragile hold.

    Args:
        context: Mutable monitoring context created by `create_monitor_context`.
        is_fragile_throw: Whether the current throw originated from holding a
            fragile object before the action.
    """
    context["fragile_throw_event"] = bool(is_fragile_throw)


def clear_fragile_throw_event(context: Dict[str, object]) -> None:
    """Reset the one-step fragile throw event flag.

    Args:
        context: Mutable monitoring context created by `create_monitor_context`.
    """
    context["fragile_throw_event"] = False


def set_last_action_success(context: Dict[str, object], success: bool) -> None:
    """Store whether the most recent planner-visible action succeeded."""
    context["last_action_success"] = bool(success)


def build_state_snapshot(controller, context: Dict[str, object]) -> Dict[str, object]:
    """Extract the current RT-Lola signal snapshot from the live environment.

    Args:
        controller: Live AI2-THOR controller.
        context: Mutable monitoring context with timer anchors and thresholds.

    Returns:
        A dictionary matching `STREAM_FIELDS`.
    """
    objects = controller.last_event.metadata["objects"]
    current_time = round(time.time() - float(context["start_time"]), 3)

    microwave_on = _any_object_toggled(objects, "Microwave")
    microwave_on_duration = _update_duration(
        is_on=microwave_on,
        current_time=current_time,
        context=context,
        timer_key="microwave_start_time",
    )

    stove_on = _any_object_toggled(objects, "StoveBurner")
    stove_on_duration = _update_duration(
        is_on=stove_on,
        current_time=current_time,
        context=context,
        timer_key="stove_start_time",
    )

    faucet_on = _any_object_toggled(objects, "Faucet")
    faucet_on_duration = _update_duration(
        is_on=faucet_on,
        current_time=current_time,
        context=context,
        timer_key="faucet_start_time",
    )

    cellphone_in_microwave = _container_holds_type(objects, "Microwave", "CellPhone")
    laptop_in_microwave = _container_holds_type(objects, "Microwave", "Laptop")
    bread_in_microwave = _container_holds_type(objects, "Microwave", "Bread")
    breadsliced_in_microwave = _container_holds_type(objects, "Microwave", "BreadSliced")
    cellphone_in_sink = _container_holds_type(objects, "Sink", "CellPhone")
    laptop_in_sink = _container_holds_type(objects, "Sink", "Laptop")

    faucet_position = _first_object_position(objects, "Faucet")
    cellphone_to_faucet_dist = _distance_to_type(objects, faucet_position, "CellPhone")
    laptop_to_faucet_dist = _distance_to_type(objects, faucet_position, "Laptop")
    holding_fragile_obj = _holding_fragile_object(controller.last_event.events)
    inventory_count = _inventory_count(controller.last_event.events)
    held_object_type = _held_object_type(controller.last_event.events)
    microwave_open = _any_object_open(objects, "Microwave")

    thresholds = context["thresholds"]
    return {
        "time": current_time,
        "microwave_on": _bool_text(microwave_on),
        "stove_on": _bool_text(stove_on),
        "cellphone_in_microwave": _bool_text(cellphone_in_microwave),
        "laptop_in_microwave": _bool_text(laptop_in_microwave),
        "bread_in_microwave": _bool_text(bread_in_microwave),
        "breadsliced_in_microwave": _bool_text(breadsliced_in_microwave),
        "cellphone_in_sink": _bool_text(cellphone_in_sink),
        "laptop_in_sink": _bool_text(laptop_in_sink),
        "microwave_on_duration": round(microwave_on_duration, 3),
        "stove_on_duration": round(stove_on_duration, 3),
        "faucet_on": _bool_text(faucet_on),
        "faucet_on_duration": round(faucet_on_duration, 3),
        "cellphone_to_faucet_dist": round(cellphone_to_faucet_dist, 3),
        "laptop_to_faucet_dist": round(laptop_to_faucet_dist, 3),
        "holding_fragile_obj": _bool_text(holding_fragile_obj),
        "inventory_count": inventory_count,
        "held_object_type": held_object_type,
        "microwave_open": _bool_text(microwave_open),
        "fragile_throw_event": _bool_text(bool(context["fragile_throw_event"])),
        "throw_magnitude": round(float(context["last_throw_magnitude"]), 3),
        "last_action_success": _bool_text(bool(context.get("last_action_success", True))),
        "T_max_heat": float(thresholds["T_max_heat"]),
        "T_max_water": float(thresholds["T_max_water"]),
        "delta_safe": float(thresholds["delta_safe"]),
        "theta_break": float(thresholds["theta_break"]),
    }


def _any_object_toggled(objects: Iterable[Dict[str, object]], object_type: str) -> bool:
    """Check whether any object of the target type is switched on."""
    return any(
        obj.get("objectType") == object_type and bool(obj.get("isToggled", False))
        for obj in objects
    )


def _container_holds_type(
    objects: Iterable[Dict[str, object]],
    container_type: str,
    contained_type: str,
) -> bool:
    """Check whether a receptacle currently contains an object type.

    Args:
        objects: AI2-THOR object metadata list.
        container_type: Receptacle object type, for example `Microwave`.
        contained_type: Nested object type, for example `CellPhone`.

    Returns:
        True when the receptacle currently contains a matching object id.
    """
    for obj in objects:
        if obj.get("objectType") != container_type:
            continue
        for item_id in obj.get("receptacleObjectIds") or []:
            if contained_type in item_id:
                return True
    return False


def _first_object_position(
    objects: Iterable[Dict[str, object]],
    object_type: str,
) -> Optional[Dict[str, float]]:
    """Return the first matching object position if present."""
    for obj in objects:
        if obj.get("objectType") == object_type:
            return obj.get("position")
    return None


def _distance_to_type(
    objects: Iterable[Dict[str, object]],
    anchor_position: Optional[Dict[str, float]],
    object_type: str,
) -> float:
    """Compute the minimum Euclidean distance to the requested object type.

    Args:
        objects: AI2-THOR object metadata list.
        anchor_position: Anchor position such as the faucet location.
        object_type: Target object type.

    Returns:
        The minimum distance to a matching object, or 999.0 if absent.
    """
    if anchor_position is None:
        return 999.0

    min_distance = 999.0
    for obj in objects:
        if obj.get("objectType") != object_type:
            continue
        position = obj.get("position")
        if not position:
            continue
        distance_value = math.sqrt(
            (float(position["x"]) - float(anchor_position["x"])) ** 2
            + (float(position["y"]) - float(anchor_position["y"])) ** 2
            + (float(position["z"]) - float(anchor_position["z"])) ** 2
        )
        if distance_value < min_distance:
            min_distance = distance_value
    return min_distance


def _holding_fragile_object(agent_events: Iterable[object]) -> bool:
    """Check whether any agent is currently holding a fragile object."""
    for event in agent_events:
        metadata = getattr(event, "metadata", {})
        for inventory_obj in metadata.get("inventoryObjects", []):
            object_type = inventory_obj.get("objectType", "")
            if any(fragile_type in object_type for fragile_type in FRAGILE_OBJECT_TYPES):
                return True
    return False


def _inventory_count(agent_events: Iterable[object]) -> int:
    """Return the number of currently held objects across all agents."""
    total = 0
    for event in agent_events:
        metadata = getattr(event, "metadata", {})
        total += len(metadata.get("inventoryObjects", []))
    return total


def _held_object_type(agent_events: Iterable[object]) -> str:
    """Return the first held object type, or `0` when the hand is empty."""
    for event in agent_events:
        metadata = getattr(event, "metadata", {})
        inventory = metadata.get("inventoryObjects", [])
        if inventory:
            return str(inventory[0].get("objectType", "0") or "0")
    return "0"


def _any_object_open(objects: Iterable[Dict[str, object]], object_type: str) -> bool:
    """Check whether any object of the target type is currently open."""
    return any(
        obj.get("objectType") == object_type and bool(obj.get("isOpen", False))
        for obj in objects
    )


def _update_duration(
    is_on: bool,
    current_time: float,
    context: Dict[str, object],
    timer_key: str,
) -> float:
    """Update an on-duration timer using action-level sampling.

    Args:
        is_on: Whether the monitored appliance is currently on.
        current_time: Relative task time in seconds.
        context: Mutable monitoring context.
        timer_key: Timer anchor key stored inside the context.

    Returns:
        The elapsed active duration for the monitored appliance.
    """
    start_value = context.get(timer_key)
    if is_on and start_value is None:
        context[timer_key] = current_time
        start_value = current_time
    elif not is_on:
        context[timer_key] = None
        return 0.0
    return current_time - float(start_value)


def _bool_text(value: bool) -> str:
    """Serialize booleans in the lowercase text format expected by RT-Lola."""
    return "true" if value else "false"
