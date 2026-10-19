#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

stage='pytest'
trap 'printf "%s: FAIL\n" "$stage" >&2' ERR
timeout 1800 python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
printf 'pytest: PASS (0 failed)\n'

stage='node frontend tests'
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
printf 'node frontend tests: PASS (3 harnesses)\n'

stage='offline frontend audit'
python scripts/audit_offline_frontend.py
printf 'offline frontend audit: PASS\n'

stage='tracked secrets'
python scripts/check_tracked_secrets.py
printf 'tracked-secret check: PASS\n'
