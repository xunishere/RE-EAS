"""Compile and execute planner-generated AI2-THOR code plans.

This script assembles a minimal executable runtime around a generated
`code_plan.py`. It intentionally avoids safety monitoring and success metrics so
that planner outputs can be run in isolation.
"""

import argparse
import ast
import os
import subprocess
from pathlib import Path


def append_trans_ctr(code_plan):
    """Count top-level action-like code segments for debugging only.

    Args:
        code_plan: Generated planner code.

    Returns:
        A rough count of action-like code segments.
    """
    brk_ctr = 0
    code_segs = code_plan.split("\n\n")
    for cd in code_segs:
        segment = cd.strip()
        if not segment:
            continue
        if "def" not in segment and "threading.Thread" not in segment and "join" not in segment:
            if segment.endswith(")"):
                brk_ctr += 1
    print("No Breaks:", brk_ctr)
    return brk_ctr


def _extract_prefixed_value(log_lines, prefix):
    """Extract the suffix of the first log line matching a prefix.

    Args:
        log_lines: Lines read from `log.txt`.
        prefix: Expected textual prefix.

    Returns:
        The trimmed suffix string.

    Exceptions:
        ValueError: Raised when the prefix is not found.
    """
    for line in log_lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    raise ValueError("Missing log field with prefix: %s" % prefix)


def _parse_floor_number(floor_plan_value):
    """Extract the numeric AI2-THOR scene id from a floor-plan label."""
    normalized = floor_plan_value.replace("FloorPlan", "")
    if "_" in normalized:
        return normalized.split("_")[0]
    return normalized


def _parse_robot_from_log(log_lines):
    """Parse the single robot dictionary from `log.txt`."""
    robot_expr = _extract_prefixed_value(log_lines, "robot =")
    return ast.literal_eval(robot_expr)


def _parse_task_description(log_lines):
    """Read the first non-empty line of `log.txt` as the task description."""
    for line in log_lines:
        stripped = line.strip()
        if stripped:
            return stripped
    raise ValueError("Cannot parse task description from log.txt")


def compile_aithor_exec_file(expt_name):
    """Build an executable AI2-THOR script for a planner output.

    Args:
        expt_name: Log folder name under `logs/`.

    Returns:
        Absolute path to the generated executable plan.

    Exceptions:
        FileNotFoundError: Raised when the required log files are missing.
        ValueError: Raised when required log fields cannot be parsed.
    """
    log_path = Path(os.getcwd()) / "logs" / expt_name
    executable_plan = ""

    import_file = (Path(os.getcwd()) / "data" / "aithor_connect" / "imports_aux_fn.py").read_text()
    executable_plan += import_file + "\n"

    log_lines = (log_path / "log.txt").read_text(encoding="utf-8").splitlines()
    floor_plan_value = _extract_prefixed_value(log_lines, "Floor Plan:")
    floor_no = _parse_floor_number(floor_plan_value)
    robot = _parse_robot_from_log(log_lines)
    task_description = _parse_task_description(log_lines)

    executable_plan += "floor_no = %s\n" % floor_no
    executable_plan += "task_description = %s\n" % repr(task_description)
    executable_plan += "robot = %s\n" % repr(robot)
    executable_plan += "robots = [robot]\n\n"

    runtime_file = (Path(os.getcwd()) / "data" / "aithor_connect" / "runtime_minimal.py").read_text()
    executable_plan += runtime_file + "\n"

    code_plan = (log_path / "code_plan.py").read_text(encoding="utf-8")
    append_trans_ctr(code_plan)
    executable_plan += code_plan + "\n"

    end_file = (Path(os.getcwd()) / "data" / "aithor_connect" / "end_minimal.py").read_text()
    executable_plan += end_file + "\n"

    executable_path = log_path / "executable_plan.py"
    executable_path.write_text(executable_plan, encoding="utf-8")
    return str(executable_path)


parser = argparse.ArgumentParser()
parser.add_argument("--command", type=str, required=True)
args = parser.parse_args()

expt_name = args.command
print(expt_name)

ai_exec_file = compile_aithor_exec_file(expt_name)
subprocess.run(["python3", ai_exec_file], check=False)
