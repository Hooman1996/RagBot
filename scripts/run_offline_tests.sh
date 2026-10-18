#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

app_pid=''
cleanup() {
    if [[ -n "$app_pid" ]]; then
        kill "$app_pid" 2>/dev/null || true
        wait "$app_pid" 2>/dev/null || true
        app_pid=''
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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

stage='browser harnesses'
if [[ -z "${BROWSER_NODE_DIR:-}" ]]; then
    printf 'browser harnesses: NOT RUN (BROWSER_NODE_DIR unset)\n'
    if [[ "${REQUIRE_BROWSER:-0}" == 1 ]]; then exit 1; fi
else
    BROWSER_NODE_DIR="$(cd "$BROWSER_NODE_DIR" && pwd)"
    for pair in \
        'knowledge_coverage.browser.cjs knowledge_coverage_browser_app' \
        'knowledge_execution.browser.cjs knowledge_execution_browser_app' \
        'knowledge_operations.browser.cjs knowledge_operations_browser_app' \
        'knowledge_recommendations.browser.cjs knowledge_recommendation_browser_app' \
        'knowledge_run_export.browser.cjs knowledge_run_export_browser_app'; do
        read -r harness app <<< "$pair"
        stage="browser $harness"
        port="$(python - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    print(sock.getsockname()[1])
PY
)"
        output="$(mktemp -d)"
        printf 'browser %s artifacts: %s\n' "$harness" "$output"
        python -m "tests.$app" --port "$port" > "$output/app.log" 2>&1 &
        app_pid=$!
        python - "$port" "$app_pid" <<'PY'
import os
import sys
import time
from urllib.request import build_opener, ProxyHandler

port, pid = map(int, sys.argv[1:])
opener = build_opener(ProxyHandler({}))
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        os.kill(pid, 0)
        with opener.open(f'http://127.0.0.1:{port}/', timeout=min(1, max(.01, deadline - time.monotonic()))):
            break
    except ProcessLookupError:
        raise SystemExit('Synthetic browser app exited before readiness')
    except OSError:
        time.sleep(min(.2, max(0, deadline - time.monotonic())))
else:
    raise SystemExit('Synthetic browser app readiness timed out after 30 seconds')
PY
        node "tests/$harness" "$BROWSER_NODE_DIR" "http://127.0.0.1:$port" "$output"
        cleanup
        printf 'browser %s: PASS\n' "$harness"
    done
    printf 'browser harnesses: PASS (5 harnesses)\n'
fi
