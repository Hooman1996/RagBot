#!/usr/bin/env bash
# Review this script and the audit documentation before running it.
# Every removal is index-only: local files remain on disk.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

printf '%s\n' 'Removing verified secrets, private datasets, and local metadata from the Git index...'
git rm --cached -- \
  .env \
  .env.server_git \
  env.example \
  .qdrant-initialized \
  minio \
  't -q' \
  'FAQ - end of 23031405 (v2).csv' \
  'تحویل هومن - خانم اله_بداشتی2.csv'

printf '%s\n' 'Removing verified generated/runtime directories from the Git index...'
git rm -r --cached -- \
  .idea \
  benchmarks/results \
  data_insertion_chunks/CHUNKS/General_FAQ \
  data_insertion_chunks/DOCUMENTS \
  docs/performance/runtime \
  storage

printf '%s\n' 'Adding the reviewed hygiene policy and required directory placeholders...'
git add -- \
  .gitignore \
  benchmarks/results/.gitkeep \
  data_insertion_chunks/CHUNKS/General_FAQ/.gitkeep \
  data_insertion_chunks/DOCUMENTS/.gitkeep \
  docs/repository/GIT_REPOSITORY_AUDIT.md \
  docs/repository/GIT_HYGIENE_GUIDE.md \
  docs/repository/DATA_DIRECTORY_LAYOUT.md \
  scripts/review_git_untracking.sh

printf '%s\n' 'Review the staged index removals carefully. Local files have not been deleted.'
git status --short

printf '%s\n' \
  'WARNING: these paths also exist in local-only commits. Do not push this branch yet.' \
  'Use the clean-history procedure in docs/repository/GIT_REPOSITORY_AUDIT.md.'
