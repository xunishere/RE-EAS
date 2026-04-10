"""Normalize and validate single-robot planner outputs.

This module post-processes raw LLM output before execution. It removes common
formatting noise, validates action usage against the AI2-THOR connector
contract, detects multi-robot artifacts, and emits a structured validation
report for downstream logging.
"""

from __future__ import annotations

import ast
import re
from typing import Any


ACTION_ARG_POSITIONS = {
    "GoToObject": [1],
    "PickupObject": [1],
    "PutObject": [1, 2],
    "OpenObject": [1],
    "CloseObject": [1],
    "SwitchOn": [1],
    "SwitchOff": [1],
    "SliceObject": [1],
    "BreakObject": [1],
    "ThrowObject": [1],
}

ALLOWED_ACTION_CALLS = set(ACTION_ARG_POSITIONS.keys())
ALLOWED_HELPER_CALLS = {"sleep"}
ALLOWED_MODULE_CALLS = {("time", "sleep")}
DISALLOWED_PATTERNS = {
    "multi_robot_token": r"\brobots\s*\[",
    "robot_list_param": r"\brobot_list\b",
    "team_reference": r"\bteam\b",
    "allocation_section": r"#\s*TASK\s+ALLOCATION",
    "solution_section": r"#\s*SOLUTION\b",
    "threading_usage": r"\bthreading\.Thread\b",
    "join_usage": r"\.join\s*\(",
}


def strip_markdown_fences(raw_text: str) -> str:
    """Remove top-level markdown code fences from model output.

    Args:
        raw_text: Raw LLM output text.

    Returns:
        Text without surrounding markdown fences.
    """
    text = raw_text.strip()
    text = re.sub(r"^```python\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_python_region(text: str) -> str:
    """Trim obvious explanation preambles and keep the Python region.

    Args:
        text: Fence-free planner output.

    Returns:
        Best-effort Python source text.
    """
    lines = text.splitlines()
    start_idx = 0
    code_markers = ("def ", "GoToObject(", "PickupObject(", "PutObject(", "OpenObject(", "CloseObject(")

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith(code_markers) or "=" in stripped:
            start_idx = idx
            break

    cleaned_lines = []
    for line in lines[start_idx:]:
        if line.strip().startswith("```"):
            continue
        cleaned_lines.append(line.rstrip())

    return "\n".join(cleaned_lines).strip()


def build_scene_object_set(scene_objects: list[dict[str, Any]]) -> set[str]:
    """Build a unique object-name set from AI2-THOR metadata.

    Args:
        scene_objects: Prompt-friendly object dictionaries.

    Returns:
        Unique object names available in the scene.
    """
    return {entry["name"] for entry in scene_objects if isinstance(entry, dict) and "name" in entry}


def get_call_name(node: ast.Call) -> tuple[str | None, tuple[str, str] | None]:
    """Resolve a call expression into simple and qualified names.

    Args:
        node: AST call node.

    Returns:
        A tuple of `(simple_name, qualified_name)`.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id, None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.attr, (func.value.id, func.attr)
    return None, None


def format_call_target(node: ast.Call) -> str:
    """Build a stable textual representation for a call target.

    Args:
        node: AST call node.

    Returns:
        A best-effort function name for diagnostics.
    """
    simple_name, qualified_name = get_call_name(node)
    if qualified_name is not None:
        return ".".join(qualified_name)
    if simple_name is not None:
        return simple_name
    return "<unknown>"


def get_defined_function_names(tree: ast.AST) -> set[str]:
    """Collect function definitions declared in the generated code.

    Args:
        tree: Parsed AST for the normalized code.

    Returns:
        A set of locally defined function names.
    """
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def get_string_arg(node: ast.Call, arg_index: int) -> str | None:
    """Extract a literal string positional argument if present.

    Args:
        node: AST call node.
        arg_index: Zero-based positional argument index.

    Returns:
        The literal string value, or `None` when absent or non-literal.
    """
    if len(node.args) <= arg_index:
        return None
    arg = node.args[arg_index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def detect_disallowed_patterns(source: str) -> list[str]:
    """Find textual artifacts that violate the single-robot contract.

    Args:
        source: Normalized planner output.

    Returns:
        A list of violation labels.
    """
    violations = []
    for label, pattern in DISALLOWED_PATTERNS.items():
        if re.search(pattern, source, flags=re.IGNORECASE):
            violations.append(label)
    return violations


def validate_ast(tree: ast.AST, scene_object_names: set[str]) -> dict[str, list[str]]:
    """Validate calls and object literals against the execution contract.

    Args:
        tree: Parsed AST for the normalized code.
        scene_object_names: Valid object names for the current scene.

    Returns:
        A dictionary containing categorized validation errors.
    """
    defined_functions = get_defined_function_names(tree)
    invalid_calls = []
    invalid_objects = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        simple_name, qualified_name = get_call_name(node)

        if qualified_name in ALLOWED_MODULE_CALLS:
            continue

        if simple_name in defined_functions:
            continue

        if simple_name in ALLOWED_ACTION_CALLS:
            for arg_index in ACTION_ARG_POSITIONS[simple_name]:
                literal = get_string_arg(node, arg_index)
                if literal is not None and literal not in scene_object_names:
                    invalid_objects.append(
                        f"{simple_name} uses unknown object '{literal}' at line {node.lineno}"
                    )
            continue

        if simple_name in ALLOWED_HELPER_CALLS:
            continue

        invalid_calls.append(
            f"Disallowed call '{format_call_target(node)}' detected at line {node.lineno}"
        )

    return {
        "invalid_calls": invalid_calls,
        "invalid_objects": invalid_objects,
    }


def normalize_single_robot_code(
    raw_text: str,
    scene_objects: list[dict[str, Any]],
    task: str,
) -> tuple[str, dict[str, Any]]:
    """Normalize and validate a single-robot code plan.

    Args:
        raw_text: Raw LLM response text.
        scene_objects: Available objects in the current AI2-THOR scene.
        task: Natural-language task used for diagnostics.

    Returns:
        A tuple of `(normalized_code, validation_report)`.

    Exceptions:
        ValueError: Raised when the generated code cannot satisfy the contract.
        SyntaxError: Raised when the normalized code is not valid Python.
    """
    stripped = strip_markdown_fences(raw_text)
    normalized = extract_python_region(stripped)
    normalized = normalized.strip() + "\n"

    if not normalized.strip():
        raise ValueError(f"Empty code output after normalization for task: {task}")

    scene_object_names = build_scene_object_set(scene_objects)
    textual_violations = detect_disallowed_patterns(normalized)

    tree = ast.parse(normalized)
    ast_validation = validate_ast(tree, scene_object_names)

    errors = []
    errors.extend(f"Single-robot contract violation: {item}" for item in textual_violations)
    errors.extend(ast_validation["invalid_calls"])
    errors.extend(ast_validation["invalid_objects"])

    report = {
        "processor": "plan_postprocess",
        "task": task,
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "stats": {
            "line_count": len([line for line in normalized.splitlines() if line.strip()]),
            "scene_object_count": len(scene_object_names),
        },
    }

    if errors:
        raise ValueError(report)

    return normalized, report
