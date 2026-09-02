#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
exec python3 -m evaluation_system.backend.scripts.start_api
