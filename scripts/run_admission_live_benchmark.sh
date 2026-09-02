#!/usr/bin/env bash
set -euo pipefail

repo_dir="/root/projects/faq"
candidate="${1:-$repo_dir/.env.test.admission-baseline}"

if [[ "${2:-}" != "--execute" ]]; then
  printf 'Review-only mode. This matrix would run 20 state-changing waves:\n'
  printf '  50 burst x 5\n  75 burst x 5\n  100 burst x 5\n  100 arrival-rate 10/s x 5\n'
  printf 'Candidate: %s\n' "$candidate"
  printf 'Re-run with --execute only after staging-owner approval.\n'
  exit 0
fi

read -r -p 'Type RUN FULL STAGING ADMISSION MATRIX to continue: ' confirmation
if [[ "$confirmation" != "RUN FULL STAGING ADMISSION MATRIX" ]]; then
  printf 'Confirmation did not match; nothing was started.\n' >&2
  exit 2
fi

export RAGBOT_ADMISSION_CONFIRMED='RUN STAGING ADMISSION TEST'
"$repo_dir/scripts/test_admission_configuration.sh" "$candidate" 50 burst
"$repo_dir/scripts/test_admission_configuration.sh" "$candidate" 75 burst
"$repo_dir/scripts/test_admission_configuration.sh" "$candidate" 100 burst
"$repo_dir/scripts/test_admission_configuration.sh" "$candidate" 100 arrival-rate 10
