#!/usr/bin/env bash
set -euo pipefail

repo_dir="/root/projects/faq"
python_bin="/root/miniconda3/envs/faq/bin/python"

cd "$repo_dir"
"$python_bin" -m unittest -v \
  tests.test_request_admission \
  tests.benchmarks.test_mobile_talk_load_test
