#!/usr/bin/env bash
set -euo pipefail

active_env="/root/projects/faq/.env"
backup="${1:-}"

if [[ -z "$backup" || ! -f "$backup" ]]; then
  printf 'Usage: %s /absolute/path/to/env.backup\n' "$0" >&2
  exit 2
fi
backup="$(realpath "$backup")"

printf 'This restores the active .env byte-for-byte from a selected backup.\n'
printf 'No service will be restarted automatically.\n'
read -r -p 'Type RESTORE STAGING ENV to continue: ' confirmation
if [[ "$confirmation" != "RESTORE STAGING ENV" ]]; then
  printf 'Confirmation did not match; nothing changed.\n' >&2
  exit 2
fi

before_hash="$(sha256sum "$active_env" | awk '{print $1}')"
backup_hash="$(sha256sum "$backup" | awk '{print $1}')"
cp -- "$backup" "$active_env"
chmod 600 "$active_env"
after_hash="$(sha256sum "$active_env" | awk '{print $1}')"
if [[ "$after_hash" != "$backup_hash" ]]; then
  printf 'Restore verification failed.\n' >&2
  exit 1
fi
printf 'Restored .env. Previous hash: %s; restored hash: %s\n' "$before_hash" "$after_hash"
printf 'FastAPI was not restarted. Use the reviewed manual procedure if needed.\n'
