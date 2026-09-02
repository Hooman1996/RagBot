#!/usr/bin/env bash
set -euo pipefail

repo_dir="/root/projects/faq"
python_bin="/root/miniconda3/envs/faq/bin/python"
result_dir="${1:-/tmp/faq-admission-mock-$(date -u +%Y%m%dT%H%M%SZ)}"

cd "$repo_dir"
mkdir -p "$result_dir"
"$python_bin" benchmarks/admission/mock_admission_benchmark.py \
  --capacity 50 \
  --tasks 100 \
  --acquire-timeout 12 \
  --minimum-hold-seconds 2 \
  --maximum-hold-seconds 10 \
  --output "$result_dir/summary.json"
printf 'Mock admission result: %s\n' "$result_dir/summary.json"
