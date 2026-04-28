#!/usr/bin/env bash
set -euo pipefail

TASK_FILE="${1:-data/generated_tasks_balanced/kitchen_tasks_balanced.json}"
LIMIT="${2:-10}"
DISPLAY_VALUE="${DISPLAY_VALUE:-:0.0}"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/bin/python}"
MODEL="${MODEL:-deepseek-reasoner}"
KEY_FILE="${KEY_FILE:-DEEPSEEK_API_KEY}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-7200}"

export DISPLAY="${DISPLAY_VALUE}"
export PATH="/root/.cargo/bin:${PATH}"

MODES=(
  roboguard_adapted
  agentspec_adapted
  probguard_adapted
  trustagent_adapted
  autort_paper
  safeembodai_paper
)

STAMP="$(date +%Y%m%d_%H%M%S)"
SUMMARY_FILES=()

mkdir -p logs

for MODE in "${MODES[@]}"; do
  SUMMARY="logs/${MODE}_${STAMP}_summary.jsonl"
  SUMMARY_FILES+=("${SUMMARY}")
  echo "=== Running ${MODE} on ${TASK_FILE} limit=${LIMIT} ==="
  timeout "${TIMEOUT_SECONDS}" "${PYTHON_BIN}" scripts/run_batch_pipeline.py \
    --task-file "${TASK_FILE}" \
    --mode "${MODE}" \
    --display "${DISPLAY_VALUE}" \
    --limit "${LIMIT}" \
    --model "${MODEL}" \
    --deepseek-api-key-file "${KEY_FILE}" \
    --summary-file "${SUMMARY}"
done

"${PYTHON_BIN}" scripts/summarize_experiment_results.py \
  "${SUMMARY_FILES[@]}" \
  --output-csv "logs/external_baselines_${STAMP}_summary.csv" \
  --output-jsonl "logs/external_baselines_${STAMP}_summary.jsonl"

echo "Done."
echo "CSV: logs/external_baselines_${STAMP}_summary.csv"
echo "JSONL: logs/external_baselines_${STAMP}_summary.jsonl"
