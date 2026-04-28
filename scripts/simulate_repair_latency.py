"""Estimate proxy repair latency with repeated local repair-pipeline calls.

This script is intentionally a proxy for paper tables when online repair
latency was not recorded during the rollout. It disables the LLM replanner and
times the deterministic STL/action-group repair path for representative kitchen
and bathroom blocked actions.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SMART_LLM_DISABLE_REPLAN_LLM", "1")

from data.aithor_connect.replan_runtime import request_replan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate proxy repair latency for kitchen and bathroom repair calls."
    )
    parser.add_argument("--kitchen-count", type=int, default=39)
    parser.add_argument("--bathroom-count", type=int, default=36)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=ROOT / "prediction" / "artifacts" / "simulated_repair_latency.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = {
        "kitchen": _time_calls(
            count=args.kitchen_count,
            environment="kitchen",
            task_description="Pick up the bowl and put it aside.",
            blocked_action={"type": "GoToObject", "objectType": "Bowl"},
            pre_state=_base_state(stove_on="true", stove_on_duration=2.0),
        ),
        "bathroom": _time_calls(
            count=args.bathroom_count,
            environment="bathroom",
            task_description="Switch on the faucet and pick up the towel.",
            blocked_action={"type": "GoToObject", "objectType": "Towel"},
            pre_state=_base_state(faucet_on="true", faucet_on_duration=2.0),
        ),
    }
    total_calls = sum(item["count"] for item in results.values())
    all_latencies = [
        latency
        for item in results.values()
        for latency in item.pop("_latencies_ms")
    ]
    results["overall"] = _summarize_latencies(all_latencies, total_calls)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))


def _time_calls(
    count: int,
    environment: str,
    task_description: str,
    blocked_action: Dict[str, str],
    pre_state: Dict[str, object],
) -> Dict[str, object]:
    latencies_ms: List[float] = []
    last_result: Dict[str, object] = {}
    for _ in range(count):
        start = time.perf_counter()
        last_result = request_replan(
            pre_state=pre_state,
            blocked_action=blocked_action,
            executed_actions=[],
            remaining_goal=task_description,
            task_description=task_description,
            environment=environment,
        )
        latencies_ms.append((time.perf_counter() - start) * 1000.0)
    summary = _summarize_latencies(latencies_ms, count)
    summary["_latencies_ms"] = latencies_ms
    summary["proxy_note"] = "LLM disabled; deterministic STL/action-group repair path only."
    summary["last_repair_actions"] = last_result.get("replan_result", {}).get("repair_actions", [])
    return summary


def _summarize_latencies(latencies_ms: List[float], count: int) -> Dict[str, object]:
    if not latencies_ms:
        return {
            "count": count,
            "total_ms": 0.0,
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "std_ms": 0.0,
        }
    return {
        "count": count,
        "total_ms": round(sum(latencies_ms), 6),
        "mean_ms": round(statistics.mean(latencies_ms), 6),
        "median_ms": round(statistics.median(latencies_ms), 6),
        "std_ms": round(statistics.pstdev(latencies_ms), 6),
    }


def _base_state(**overrides) -> Dict[str, object]:
    state = {
        "time": 0.0,
        "microwave_on": "false",
        "stove_on": "false",
        "cellphone_in_microwave": "false",
        "laptop_in_microwave": "false",
        "bread_in_microwave": "false",
        "breadsliced_in_microwave": "false",
        "cellphone_in_sink": "false",
        "laptop_in_sink": "false",
        "microwave_on_duration": 0.0,
        "stove_on_duration": 0.0,
        "faucet_on": "false",
        "faucet_on_duration": 0.0,
        "cellphone_to_faucet_dist": 999.0,
        "laptop_to_faucet_dist": 999.0,
        "holding_fragile_obj": "false",
        "inventory_count": 0,
        "held_object_type": "0",
        "microwave_open": "false",
        "fragile_throw_event": "false",
        "throw_magnitude": 0.0,
        "last_action_success": "true",
        "T_max_heat": 1.0,
        "T_max_water": 1.0,
        "delta_safe": 1.0,
        "theta_break": 5.0,
    }
    state.update(overrides)
    return state


if __name__ == "__main__":
    main()
