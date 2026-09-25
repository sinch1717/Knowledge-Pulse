#!/usr/bin/env bash
# KnowledgePulse test runner (Linux, macOS, WSL, Git Bash).
#
#   ./run-tests.sh                 everything except live: frontend, integration, acceptance, regression
#   ./run-tests.sh acceptance      one layer
#   ./run-tests.sh integration acceptance
#   ./run-tests.sh live            real embedding model and LLM (needs API keys in backend/.env)
#
# Layers: frontend integration acceptance regression tenancy smoke live e2e all
# Reports: backend/test-reports/ (JUnit XML, JSON results, traceability.md)
# Needs:   pip install -r backend/requirements-dev.txt ; npm ci in frontend/ (for the frontend layer)

set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
REPORTS="$BACKEND/test-reports"
GENERATED="$BACKEND/tests/suites/.generated"
export KP_REPORT_DIR="$REPORTS"

# ---- python ----------------------------------------------------------------------
if [ -n "${PYTHON:-}" ]; then PY="$PYTHON"
elif [ -x "$BACKEND/.venv/bin/python" ]; then PY="$BACKEND/.venv/bin/python"
elif [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then PY="$BACKEND/.venv/Scripts/python.exe"
else PY="$(command -v python3 || command -v python)"; fi

if ! "$PY" -c "import pytest" 2>/dev/null; then
  echo "pytest is not installed for $PY. Run: pip install -r backend/requirements-dev.txt"
  exit 2
fi

LAYERS=("$@")
[ ${#LAYERS[@]} -eq 0 ] && LAYERS=(all)
if [ "${LAYERS[0]}" = "all" ]; then LAYERS=(frontend integration acceptance regression); fi

mkdir -p "$REPORTS"
declare -a SUMMARY
FAILED=0

record() {  # layer, exit code
  if [ "$2" -eq 0 ]; then SUMMARY+=("  PASS  $1"); else SUMMARY+=("  FAIL  $1"); FAILED=1; fi
}

export_types() {
  if command -v node >/dev/null && [ -d "$FRONTEND/node_modules/typescript" ]; then
    mkdir -p "$GENERATED"
    node "$FRONTEND/scripts/export-api-types.mjs" > "$GENERATED/frontend_types.json"
  fi
}

run_pytest() {  # layer
  echo; echo "==== $1 ===================================================="
  (cd "$BACKEND" && "$PY" -m pytest -m "$1" --junitxml="$REPORTS/$1-junit.xml")
  record "$1" $?
}

for layer in "${LAYERS[@]}"; do
  case "$layer" in
    frontend)
      echo; echo "==== frontend ================================================"
      if ! command -v npm >/dev/null; then echo "npm not found; skipping"; SUMMARY+=("  SKIP  frontend"); continue; fi
      (
        cd "$FRONTEND" || exit 1
        [ -d node_modules ] || npm ci --no-audit --no-fund || exit 1
        echo "-- type check";  npx tsc --noEmit || exit 1
        echo "-- build";       npm run build || exit 1
        echo "-- export API types for the contract test"
        mkdir -p "$GENERATED" && node scripts/export-api-types.mjs > "$GENERATED/frontend_types.json" || exit 1
      )
      record frontend $?
      ;;
    integration)
      export_types
      run_pytest integration
      ;;
    acceptance|regression)
      run_pytest "$layer"
      ;;
    live)
      echo; echo "==== live (real models, uses backend/.env) ===================="
      (cd "$BACKEND" && KP_LIVE=1 "$PY" -m pytest -m live -s --junitxml="$REPORTS/live-junit.xml")
      record live $?
      ;;
    e2e)
      echo; echo "==== e2e (browser) ============================================"
      (cd "$BACKEND" && "$PY" tests/e2e/run_e2e.py)
      record e2e $?
      ;;
    tenancy)
      echo; echo "==== tenancy (standalone unittest) ==========================="
      (cd "$BACKEND" && "$PY" -m unittest tests/test_multitenancy.py)
      record tenancy $?
      ;;
    smoke)
      echo; echo "==== smoke ===================================================="
      (cd "$BACKEND" && "$PY" scripts/smoke_test.py)
      record smoke $?
      ;;
    *)
      echo "Unknown layer: $layer (frontend integration acceptance regression tenancy smoke live e2e all)"
      exit 2
      ;;
  esac
done

echo; echo "==== summary ================================================="
printf '%s\n' "${SUMMARY[@]}"
echo "Reports: $REPORTS"
[ -f "$REPORTS/traceability.md" ] && echo "Traceability: $REPORTS/traceability.md"
exit $FAILED
