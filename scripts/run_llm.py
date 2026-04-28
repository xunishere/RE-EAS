"""Generate single-robot AI2-THOR plans with DeepSeek.

This script implements the planner entrypoint for SMART-LLM. It converts
natural-language household tasks into Pythonic plans in three steps:
1. Decompose the task into ordered or parallel subtasks.
2. Generate a single-robot executable Python plan.
3. Normalize and validate the generated code before persisting it.
"""

import argparse
import importlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ai2thor.controller
from openai import OpenAI

sys.path.append(".")

import resources.actions as actions
import resources.robots as robots


def build_openai_client(api_key_file: str) -> OpenAI:
    """Create a DeepSeek-compatible OpenAI client.

    Args:
        api_key_file: Base file name without the trailing `.txt`.

    Returns:
        An initialized OpenAI client configured for DeepSeek.

    Exceptions:
        FileNotFoundError: Raised when the API key file does not exist.
    """
    return OpenAI(
        api_key=Path(f"{api_key_file}.txt").read_text().strip(),
        base_url="https://api.deepseek.com",
    )


def lm(
    client: OpenAI,
    messages,
    model: str,
    temperature: float = 0,
    stop=None,
    frequency_penalty: float = 0,
):
    """Execute a single chat completion request.

    Args:
        client: Initialized DeepSeek client.
        messages: Chat messages sent to the model.
        model: Model identifier.
        temperature: Sampling temperature.
        stop: Optional stop sequences.
        frequency_penalty: Frequency penalty forwarded to the API.

    Returns:
        A tuple of `(response, content)`.

    Exceptions:
        openai.OpenAIError: Propagated when the API call fails.
    """
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stop=stop,
        frequency_penalty=frequency_penalty,
    )
    return response, response.choices[0].message.content


def convert_to_dict_objprop(objs, obj_mass):
    """Convert AI2-THOR object metadata into prompt-friendly dictionaries.

    Args:
        objs: Object type names from AI2-THOR.
        obj_mass: Corresponding masses for each object.

    Returns:
        A list of dictionaries with `name` and `mass`.
    """
    objs_dict = []
    for i, obj in enumerate(objs):
        objs_dict.append({"name": obj, "mass": obj_mass[i]})
    return objs_dict


def get_ai2_thor_objects(floor_plan_num):
    """Load object names and masses from an AI2-THOR floor plan.

    Args:
        floor_plan_num: Numeric scene identifier such as `2` or `201`.

    Returns:
        A list of prompt-friendly object dictionaries.

    Exceptions:
        RuntimeError: Propagated if AI2-THOR fails to load the scene.
    """
    controller = ai2thor.controller.Controller(scene="FloorPlan" + str(floor_plan_num))
    obj = [entry["objectType"] for entry in controller.last_event.metadata["objects"]]
    obj_mass = [entry["mass"] for entry in controller.last_event.metadata["objects"]]
    controller.stop()
    return convert_to_dict_objprop(obj, obj_mass)


def load_text_file(file_path: Path) -> str:
    """Read a UTF-8 text file into memory.

    Args:
        file_path: Absolute or relative path to the source file.

    Returns:
        File content as a string.

    Exceptions:
        FileNotFoundError: Raised when the file does not exist.
    """
    return file_path.read_text(encoding="utf-8")


def sanitize_task_name(task: str) -> str:
    """Create a stable folder-safe task name.

    Args:
        task: Natural-language task description.

    Returns:
        A filesystem-safe string.
    """
    collapsed = "_".join(task.split()).replace("\n", "")
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", collapsed).strip("_") or "task"


def normalize_floor_plan_id(floor_plan_value: str) -> Tuple[str, str]:
    """Normalize floor-plan identifiers for file lookup and AI2-THOR loading.

    Args:
        floor_plan_value: Values like `1`, `1_1`, `FloorPlan1`, or `FloorPlan1_1`.

    Returns:
        A tuple of `(full_id, numeric_scene_id)`.

    Exceptions:
        ValueError: Raised when the input is empty.
    """
    if not floor_plan_value:
        raise ValueError("floor_plan must not be empty.")

    normalized = floor_plan_value.replace("FloorPlan", "")
    if "_" in normalized:
        return normalized, normalized.split("_")[0]
    return normalized, normalized


def get_single_robot(robots_list):
    """Select the single robot used by the planner.

    Args:
        robots_list: Numeric robot ids from the dataset.

    Returns:
        A single robot configuration dictionary renamed to `robot1`.

    Exceptions:
        ValueError: Raised when the dataset does not provide any robot.
    """
    if not robots_list:
        raise ValueError("Expected at least one robot in the dataset.")

    robot_config = dict(robots.robots[robots_list[0] - 1])
    robot_config["name"] = "robot1"
    return robot_config


def load_planner_input(input_path: Path, floor_plan_override: Optional[str]):
    """Load minimal planner inputs from JSON.

    Supported item shape:
    {
      "task": "...",
      "floor_plan": "FloorPlan1"
    }

    Args:
        input_path: Path to the planner input JSON file.
        floor_plan_override: Optional CLI override for the floor plan.

    Returns:
        A list of planner input items with normalized floor-plan metadata.

    Exceptions:
        KeyError: Raised when a task entry misses required keys.
        ValueError: Raised when the file content is empty or inconsistent.
    """
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]

    if not data:
        raise ValueError(f"No planner inputs found in {input_path}.")

    planner_items = []

    for item in data:
        if "task" not in item:
            raise KeyError("Each planner input item must contain `task`.")

        task_floor_plan = floor_plan_override or item.get("floor_plan")
        if not task_floor_plan:
            raise KeyError(
                "Each planner input item must contain `floor_plan` unless "
                "`--floor-plan` is provided."
            )

        item_floor_plan_full, item_floor_plan_num = normalize_floor_plan_id(task_floor_plan)
        planner_items.append(
            {
                "task": item["task"],
                "floor_plan_full": item_floor_plan_full,
                "floor_plan_num": item_floor_plan_num,
            }
        )

    return planner_items


def fallback_postprocess(raw_text: str) -> Tuple[str, Dict]:
    """Apply a minimal local cleanup when the dedicated postprocessor is absent.

    Args:
        raw_text: Raw model output.

    Returns:
        A tuple of `(normalized_code, validation_report)`.
    """
    normalized = raw_text.strip()
    normalized = re.sub(r"^```python\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^```\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*```$", "", normalized)
    report = {
        "processor": "fallback",
        "valid": True,
        "warnings": ["Dedicated plan_postprocess module not found; fallback cleanup used."],
    }
    return normalized + "\n", report


def normalize_code_plan(raw_text: str, scene_objects, task: str) -> Tuple[str, Dict]:
    """Normalize model output and produce a validation report.

    Args:
        raw_text: Raw generated code from the model.
        scene_objects: Objects available in the current floor plan.
        task: Natural-language task description for diagnostics.

    Returns:
        A tuple of `(normalized_code, validation_report)`.

    Exceptions:
        RuntimeError: Raised if the external postprocessor fails.
    """
    try:
        processor_module = importlib.import_module("scripts.plan_postprocess")
    except ModuleNotFoundError:
        return fallback_postprocess(raw_text)

    if not hasattr(processor_module, "normalize_single_robot_code"):
        raise RuntimeError(
            "scripts.plan_postprocess exists but does not define "
            "`normalize_single_robot_code`."
        )

    return processor_module.normalize_single_robot_code(
        raw_text=raw_text,
        scene_objects=scene_objects,
        task=task,
    )


def build_decomposition_prompt(base_prompt: str, task: str) -> str:
    """Create the task decomposition prompt payload.

    Args:
        base_prompt: Shared prompt prefix and examples.
        task: Natural-language task description.

    Returns:
        Prompt text for the decomposition stage.
    """
    return f"{base_prompt}\n\n# Task Description: {task}"


def build_single_robot_code_prompt(
    prompt_prefix: str,
    decomposition: str,
    single_robot,
    contract_prompt: str,
) -> str:
    """Create the final code-generation prompt for a single robot.

    Args:
        prompt_prefix: Shared prompt prefix and few-shot examples.
        decomposition: Generated decomposition plan for the current task.
        single_robot: Selected robot metadata.
        contract_prompt: Output contract injected into the prompt.

    Returns:
        Prompt text for the code generation stage.
    """
    prompt = prompt_prefix + decomposition
    prompt += "\n# SINGLE ROBOT EXECUTION"
    prompt += f"\nrobot = {single_robot}"
    prompt += "\n# Constraint: All actions must be executed by the single available robot."
    prompt += "\n# Constraint: Do not create robot teams, robot allocation sections, or robot_list arguments."
    prompt += "\n\n# OUTPUT CONTRACT"
    prompt += "\n" + contract_prompt.strip()
    prompt += "\n\n# CODE Solution\n"
    return prompt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--floor-plan",
        type=str,
        default=None,
        help="Optional floor-plan override. Format: 2, 2_1, FloorPlan2, or FloorPlan2_1.",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        default="data/final_test/planner_input.json",
        help="Planner input JSON containing only `task` and `floor_plan`.",
    )
    parser.add_argument("--deepseek-api-key-file", type=str, default="DEEPSEEK_API_KEY")
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek-reasoner",
        choices=["deepseek-reasoner"],
    )
    parser.add_argument(
        "--prompt-decompse-set",
        type=str,
        default="train_task_decompose",
        choices=["train_task_decompose"],
    )
    parser.add_argument(
        "--prompt-code-set",
        type=str,
        default="train_task_single_robot_code",
        choices=["train_task_single_robot_code"],
    )
    parser.add_argument(
        "--output-contract-set",
        type=str,
        default="output_contract",
        choices=["output_contract"],
    )
    parser.add_argument(
        "--log-root",
        type=str,
        default="logs",
        help="Directory where generated planner log folders are written.",
    )
    parser.add_argument("--log-results", type=bool, default=True)

    args = parser.parse_args()

    client = build_openai_client(args.deepseek_api_key_file)

    log_root = Path(args.log_root)
    if not log_root.is_absolute():
        log_root = Path(os.getcwd()) / log_root
    log_root.mkdir(parents=True, exist_ok=True)

    planner_items = load_planner_input(
        input_path=Path(args.input_file),
        floor_plan_override=args.floor_plan,
    )
    test_tasks = [item["task"] for item in planner_items]

    print(f"\n----Test set tasks----\n{test_tasks}\nTotal: {len(test_tasks)} tasks\n")

    single_robot = get_single_robot([1])
    single_robots = [single_robot for _ in test_tasks]

    print("Generating Decomposed Plans...")

    decomposed_plan = []
    scene_objects_by_task = []
    objects_ai_by_task = []
    floor_plan_full_by_task = []
    floor_plan_num_by_task = []
    decomposition_examples = load_text_file(
        Path(os.getcwd()) / "data" / "pythonic_plans" / f"{args.prompt_decompse_set}.py"
    )
    for item in planner_items:
        task = item["task"]
        floor_plan_full = item["floor_plan_full"]
        floor_plan_num = item["floor_plan_num"]
        scene_objects = get_ai2_thor_objects(floor_plan_num)
        objects_ai = f"\n\nobjects = {scene_objects}"
        decomposition_prompt_prefix = f"from skills import {actions.ai2thor_actions}"
        decomposition_prompt_prefix += "\nimport time"
        decomposition_prompt_prefix += "\nimport threading"
        decomposition_prompt_prefix += objects_ai
        decomposition_prompt_prefix += "\n\n" + decomposition_examples
        curr_prompt = build_decomposition_prompt(decomposition_prompt_prefix, task)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an AI2-THOR task planner. Decompose the task into "
                    "subtasks and emit deterministic Pythonic pseudo-plan text. "
                    "Output plain text only. Do not use markdown bold markers, "
                    "bullet lists, or fenced code blocks. Follow the training "
                    "examples exactly using comment-style sections like "
                    "'# Task Description', '# GENERAL TASK DECOMPOSITION', and "
                    "'# CODE'. If the task says 'put it aside', 'throw it aside', "
                    "or 'move it away' without explicitly naming a receptacle, "
                    "interpret it as a throw-away action rather than placing the "
                    "object on a countertop or other receptacle."
                ),
            },
            {"role": "user", "content": curr_prompt},
        ]
        _, text = lm(client, messages, args.model, frequency_penalty=0.15)
        decomposed_plan.append(text)
        scene_objects_by_task.append(scene_objects)
        objects_ai_by_task.append(objects_ai)
        floor_plan_full_by_task.append(floor_plan_full)
        floor_plan_num_by_task.append(floor_plan_num)

    print("Generating Single-Robot Code...")

    code_examples = load_text_file(
        Path(os.getcwd()) / "data" / "pythonic_plans" / f"{args.prompt_code_set}.py"
    )
    contract_prompt = load_text_file(
        Path(os.getcwd()) / "data" / "pythonic_plans" / f"{args.output_contract_set}.py"
    )

    raw_code_plan = []
    normalized_code_plan = []
    validation_reports = []

    for i, plan in enumerate(decomposed_plan):
        code_prompt_prefix = f"from skills import {actions.ai2thor_actions}"
        code_prompt_prefix += "\nimport time"
        code_prompt_prefix += "\nimport threading"
        code_prompt_prefix += objects_ai_by_task[i]
        code_prompt_prefix += "\n\n" + code_examples
        curr_prompt = build_single_robot_code_prompt(
            prompt_prefix=code_prompt_prefix + "\n\n",
            decomposition=plan,
            single_robot=single_robots[i],
            contract_prompt=contract_prompt,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a single-robot AI2-THOR code generator. Output only "
                    "clean Python code. Never include markdown fences, allocation "
                    "sections, team reasoning, or multiple robots. If the task says "
                    "'put it aside', 'throw it aside', or 'move it away' without "
                    "explicitly naming a receptacle, interpret it as ThrowObject "
                    "rather than PutObject. When washing objects, use SinkBasin "
                    "instead of Sink as the receptacle target. When heating bread, "
                    "slice Bread with a knife first, put down the knife, then pick "
                    "up BreadSliced and place BreadSliced into the microwave."
                ),
            },
            {"role": "user", "content": curr_prompt},
        ]
        _, text = lm(client, messages, args.model, frequency_penalty=0.2)
        normalized_text, validation_report = normalize_code_plan(
            raw_text=text,
            scene_objects=scene_objects_by_task[i],
            task=test_tasks[i],
        )
        raw_code_plan.append(text)
        normalized_code_plan.append(normalized_text)
        validation_reports.append(validation_report)

    if args.log_results:
        now = datetime.now()
        date_time = now.strftime("%m-%d-%Y-%H-%M-%S-%f")

        for idx, task in enumerate(test_tasks):
            folder_name = f"{sanitize_task_name(task)}_plans_{date_time}"
            task_log_dir = log_root / folder_name
            task_log_dir.mkdir()

            with (task_log_dir / "log.txt").open("w", encoding="utf-8") as f:
                f.write(task)
                f.write(f"\n\nGPT Version: {args.model}")
                f.write(f"\n\nFloor Plan: {floor_plan_full_by_task[idx]}")
                f.write(f"\n{objects_ai_by_task[idx]}")
                f.write(f"\nrobot = {single_robots[idx]}")

            with (task_log_dir / "decomposed_plan.py").open("w", encoding="utf-8") as d:
                d.write(decomposed_plan[idx])

            with (task_log_dir / "raw_code_plan.py").open("w", encoding="utf-8") as x:
                x.write(raw_code_plan[idx])

            with (task_log_dir / "code_plan.py").open("w", encoding="utf-8") as x:
                x.write(normalized_code_plan[idx])

            with (task_log_dir / "validation_report.json").open("w", encoding="utf-8") as report_file:
                json.dump(validation_reports[idx], report_file, indent=2, ensure_ascii=False)
