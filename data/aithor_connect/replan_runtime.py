"""Runtime wrapper for STL-guided constrained replanning."""

from __future__ import annotations

from typing import Dict, Sequence

from data.aithor_connect.action_group_generator import generate_allowable_action_group
from data.aithor_connect.constrained_replanner import replan_suffix
from data.aithor_connect.stl_risk_assessment import assess_risk_state


def request_replan(
    pre_state: Dict[str, object],
    blocked_action: Dict[str, str],
    executed_actions: Sequence[Dict[str, str]],
    remaining_goal: str,
    task_description: str,
    environment: str,
) -> Dict[str, object]:
    """Run the STL-guided replan pipeline for one blocked action."""
    risk_state = assess_risk_state(pre_state)
    action_group = generate_allowable_action_group(
        pre_state=pre_state,
        blocked_action=blocked_action,
        risk_state=risk_state,
        environment=environment,
    )
    replan_result = replan_suffix(
        pre_state=pre_state,
        executed_actions=executed_actions,
        blocked_action=blocked_action,
        remaining_goal=remaining_goal,
        action_group=action_group,
        task_description=task_description,
        environment=environment,
    )
    return {
        "risk_state": risk_state,
        "action_group": action_group,
        "replan_result": replan_result,
    }
