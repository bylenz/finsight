#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

run_suite() {
    local name="$1"
    local testpath="$2"
    echo "=== Running $name tests ==="
    (cd "$ROOT" && uv run pytest -v --cov --cov-report=term-missing "$testpath" "$@") || FAILED=1
    echo ""
}

run_suite "backend"  "backend/tests"  "$@"
run_suite "frontend" "frontend/tests" "$@"

if [ $FAILED -ne 0 ]; then
    echo "One or more test suites failed."
    exit 1
fi

echo "All test suites passed."
