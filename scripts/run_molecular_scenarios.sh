#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

common_args=(
  --llm-mode openai
  --decision-model Qwen3.6-27B-UD-Q4_K_XL.gguf
  --case-id SIM_MOL_KIT_query
  "$@"
)

echo "[1/2] MOLECULAR：开启基因匹配历史病例"
python agent.py "${common_args[@]}" \
  --output-dir results/molecular_scenarios/with_cases

echo "[2/2] MOLECULAR：关闭历史病例"
python agent.py "${common_args[@]}" \
  --disable-case-retrieval \
  --output-dir results/molecular_scenarios/no_cases

echo "完成：结果位于 results/molecular_scenarios/"
