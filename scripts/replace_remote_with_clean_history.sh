#!/usr/bin/env bash

set -euo pipefail

expected_branch="clean-main"
expected_origin="ssh://git@ssh.github.com:443/Hooman1996/RagBot.git"
required_confirmation="REPLACE Hooman1996/RagBot main"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

branch="$(git branch --show-current)"
if [[ "$branch" != "$expected_branch" ]]; then
  printf 'ERROR: expected branch %s, found %s\n' "$expected_branch" "$branch" >&2
  exit 1
fi

commit_count="$(git rev-list --count HEAD)"
root_count="$(git rev-list --max-parents=0 HEAD | wc -l)"
if [[ "$commit_count" != "1" || "$root_count" != "1" ]]; then
  printf 'ERROR: clean-main must contain exactly one root commit.\n' >&2
  exit 1
fi

origin_url="$(git remote get-url origin)"
if [[ "$origin_url" != "$expected_origin" ]]; then
  printf 'ERROR: unexpected origin URL: %s\n' "$origin_url" >&2
  exit 1
fi

prohibited="$({
  git ls-tree -r --name-only HEAD | awk '
    $0 == ".env" || $0 == ".env.server_git" ||
    $0 == ".qdrant-initialized" || $0 == "t -q" ||
    $0 ~ /^\.idea\// || $0 ~ /^\.codex\// ||
    $0 ~ /^data_insertion_chunks\/DOCUMENTS\// && $0 != "data_insertion_chunks/DOCUMENTS/.gitkeep" ||
    $0 ~ /^data_insertion_chunks\/CHUNKS\// && $0 != "data_insertion_chunks/CHUNKS/General_FAQ/.gitkeep" ||
    $0 ~ /^benchmarks\/results\// && $0 != "benchmarks/results/.gitkeep" ||
    $0 ~ /^(storage|qdrant_storage|snapshots|qdrant-snapshots|minio-data|minio_data|postgres-data|postgres_data|docker-volumes)\// ||
    $0 ~ /(^|\/)(node_modules|__pycache__|\.pytest_cache|\.cache)\// ||
    $0 ~ /(^|\/)(uploads?|downloads?|outputs?)\// ||
    $0 ~ /\.(safetensors|pt|pth|onnx|gguf|ckpt|pyc|log)$/ ||
    index($0, "/") == 0 && tolower($0) ~ /\.(csv|xlsx?|pdf|docx?)$/ {
      print
    }
  '
} || true)"
if [[ -n "$prohibited" ]]; then
  printf 'ERROR: prohibited paths are tracked:\n%s\n' "$prohibited" >&2
  exit 1
fi

token_pattern='g''hp_|github_''pat_|g''ho_'
key_word="KEY"
key_pattern="BEGIN OPENSSH PRIVATE ${key_word}|BEGIN PRIVATE ${key_word}"
secret_hits="$({
  git grep -nI -E "${token_pattern}|${key_pattern}" HEAD -- . 2>/dev/null |
    awk -F: '{print $2 ":" $3}'
} || true)"
if [[ -n "$secret_hits" ]]; then
  printf 'ERROR: high-confidence secret patterns found at:\n%s\n' "$secret_hits" >&2
  exit 1
fi

git fetch origin main
old_sha="$(git rev-parse origin/main)"
new_sha="$(git rev-parse HEAD)"

printf 'Old origin/main: %s\n' "$old_sha"
printf 'New clean-main:  %s\n' "$new_sha"
printf 'Review: git diff --stat %s %s\n' "$old_sha" "$new_sha"
printf 'Type exactly: %s\n> ' "$required_confirmation"
IFS= read -r confirmation
if [[ "$confirmation" != "$required_confirmation" ]]; then
  printf 'Confirmation did not match; nothing was pushed.\n' >&2
  exit 1
fi

git push --force-with-lease origin clean-main:main

printf '%s\n' 'Push completed. Verify with:'
printf '%s\n' \
  'git fetch origin main' \
  'git rev-parse clean-main origin/main' \
  'git rev-list --count origin/main' \
  'git ls-tree -r --name-only origin/main | sort'
