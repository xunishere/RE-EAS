"""Run RQ2 three-module ablation experiments.

RQ2 compares the full RE-EAS loop against variants that remove one of the
three top-level modules: runtime monitoring, pre-action prediction, and
constrained repair. This script only orchestrates existing batch modes; it does
not modify the core runtime model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs"

DEFAULT_TASK_FILES = [
    ROOT / "data" / "generated_tasks_balanced" / "kitchen_tasks_balanced.json",
    ROOT / "data" / "generated_tasks_balanced" / "living_room_tasks_balanced.json",
    ROOT / "data" / "generated_tasks_balanced" / "bedroom_tasks_balanced.json",
    ROOT / "data" / "generated_tasks_balanced" / "bathroom_tasks_balanced.json",
]

RQ2_VARIANTS = [
    {
        "variant": "full_reeas",
        "mode": "full",
        "paper_label": "Full RE-EAS",
        "monitoring": True,
        "prediction_gate": True,
        "constrained_repair": True,
        "note": "Complete runtime loop.",
    },
    {
        "variant": "without_runtime_monitoring",
        "mode": "no_runtime_monitor",
        "paper_label": "w/o Runtime Monitoring",
        "monitoring": False,
        "prediction_gate": False,
        "constrained_repair": False,
        "note": "Monitoring sidecar disabled; prediction and repair are inactive because no monitored pre-state is available.",
    },
    {
        "variant": "without_prediction_gate",
        "mode": "monitor_only",
        "paper_label": "w/o Prediction Gate",
        "monitoring": True,
        "prediction_gate": False,
        "constrained_repair": True,
        "note": "Pre-action prediction is disabled; repair is present but not triggered by prediction.",
    },
    {
        "variant": "without_constrained_repair",
        "mode": "prediction_only",
        "paper_label": "w/o Constrained Repair",
        "monitoring": True,
        "prediction_gate": True,
        "constrained_repair": False,
        "note": "Risky actions are blocked/fail-closed instead of repaired.",
    },
]


RQ3_PREDICTOR_VARIANTS = [
    {
        "variant": "multidimspci_repair",
        "mode": "multidimspci_repair",
        "paper_label": "MultiDimSPCI + Repair",
        "monitoring": True,
        "prediction_gate": "MultiDimSPCI",
        "constrained_repair": True,
        "note": "Temporal conformal prediction gate; monitoring and constrained repair unchanged.",
    },
    {
        "variant": "cptc_repair",
        "mode": "cptc_repair",
        "paper_label": "CPTC + Repair",
        "monitoring": True,
        "prediction_gate": "CPTC",
        "constrained_repair": True,
        "note": "Change-point temporal conformal prediction gate; monitoring and constrained repair unchanged.",
    },
]


RQ4_REPAIR_VARIANTS = [
    {
        "variant": "block_only",
        "mode": "prediction_only",
        "paper_label": "Block-only",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "none",
        "note": "Unsafe actions are blocked/stopped without repair.",
    },
    {
        "variant": "random_action_repair",
        "mode": "random_action_repair",
        "paper_label": "Random Action Replacement",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "random_action",
        "note": "Replace blocked action with one sampled generic action.",
    },
    {
        "variant": "random_allowable_repair",
        "mode": "random_allowable_repair",
        "paper_label": "Random Allowable Action",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "random_allowable",
        "note": "Sample one action from the allowable action set.",
    },
    {
        "variant": "rule_based_repair",
        "mode": "rule_based_repair",
        "paper_label": "Rule-based Local Repair",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "rule_based",
        "note": "Use fixed hazard-specific local repair rules.",
    },
    {
        "variant": "unconstrained_llm_repair",
        "mode": "unconstrained_llm_repair",
        "paper_label": "Unconstrained LLM Repair",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "unconstrained_llm",
        "note": "Let an LLM generate repair actions without allowable-action constraints.",
    },
    {
        "variant": "full_reeas_repair",
        "mode": "full",
        "paper_label": "Full RE-EAS Repair",
        "monitoring": True,
        "prediction_gate": True,
        "repair_strategy": "constrained_repair",
        "note": "Risk assessment plus allowable action set plus constrained repair.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RQ2 module ablation experiments.")
    parser.add_argument(
        "--task-files",
        type=Path,
        nargs="*",
        default=None,
        help="Task JSON files. Defaults to the four balanced room files.",
    )
    parser.add_argument("--display", default=":0.0")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--deepseek-api-key-file", default="DEEPSEEK_API_KEY")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--log-root", type=Path, default=LOGS_DIR)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--variant-set",
        choices=["rq2", "rq3", "rq4", "all"],
        default="rq2",
        help="Run RQ2 ablations, RQ3 predictor replacements, RQ4 repair strategies, or all.",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Launch all room/variant jobs concurrently. Use with care on AI2-THOR.",
    )
    return parser.parse_args()


def resolve_task_files(args: argparse.Namespace) -> List[Path]:
    task_files = args.task_files if args.task_files else DEFAULT_TASK_FILES
    resolved = []
    for path in task_files:
        candidate = path if path.is_absolute() else ROOT / path
        if not candidate.exists():
            raise FileNotFoundError(f"Task file not found: {candidate}")
        resolved.append(candidate)
    return resolved


def select_variants(variant_set: str) -> List[Dict[str, object]]:
    if variant_set == "rq3":
        return RQ3_PREDICTOR_VARIANTS
    if variant_set == "rq4":
        return RQ4_REPAIR_VARIANTS
    if variant_set == "all":
        return [*RQ2_VARIANTS, *RQ3_PREDICTOR_VARIANTS, *RQ4_REPAIR_VARIANTS]
    return RQ2_VARIANTS


def build_command(
    task_file: Path,
    variant: Dict[str, object],
    args: argparse.Namespace,
    stamp: str,
) -> tuple[List[str], Path]:
    room_name = task_file.stem.replace("_tasks_balanced", "")
    summary_path = LOGS_DIR / f"rq2_{variant['variant']}_{room_name}_{stamp}_summary.jsonl"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_batch_pipeline.py"),
        "--task-file",
        str(task_file),
        "--mode",
        str(variant["mode"]),
        "--display",
        args.display,
        "--start",
        str(args.start),
        "--model",
        args.model,
        "--deepseek-api-key-file",
        args.deepseek_api_key_file,
        "--max-retries",
        str(args.max_retries),
        "--log-root",
        str(args.log_root),
        "--summary-file",
        str(summary_path),
    ]
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    return command, summary_path


def write_manifest(payload: Dict[str, object], stamp: str) -> Path:
    manifest_path = LOGS_DIR / f"rq2_ablation_manifest_{stamp}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def main() -> None:
    args = parse_args()
    stamp = args.stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    task_files = resolve_task_files(args)
    variants = select_variants(args.variant_set)

    jobs = []
    for task_file in task_files:
        for variant in variants:
            command, summary_path = build_command(task_file, variant, args, stamp)
            jobs.append(
                {
                    "task_file": str(task_file),
                    "variant": variant,
                    "command": command,
                    "summary_file": str(summary_path),
                }
            )

    manifest_path = write_manifest(
        {
            "stamp": stamp,
            "variant_set": args.variant_set,
            "variants": variants,
            "jobs": jobs,
        },
        stamp,
    )

    if args.dry_run:
        print(f"Manifest written to {manifest_path}")
        for job in jobs:
            print(" ".join(job["command"]))
        return

    if args.parallel:
        processes = []
        for job in jobs:
            log_path = Path(str(job["summary_file"]).replace("_summary.jsonl", ".out"))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = log_path.open("w", encoding="utf-8")
            proc = subprocess.Popen(job["command"], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            processes.append((job, proc, handle, log_path))
            print(f"Started {job['variant']['paper_label']} on {Path(job['task_file']).name}: pid={proc.pid}")
        failed = 0
        for job, proc, handle, log_path in processes:
            returncode = proc.wait()
            handle.close()
            if returncode != 0:
                failed += 1
            print(
                f"Finished {job['variant']['paper_label']} on {Path(job['task_file']).name}: "
                f"returncode={returncode}, log={log_path}"
            )
        if failed:
            raise SystemExit(f"{failed} RQ2 jobs failed")
    else:
        for job in jobs:
            print(f"Running {job['variant']['paper_label']} on {Path(job['task_file']).name}")
            subprocess.run(job["command"], cwd=ROOT, check=True)

    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
