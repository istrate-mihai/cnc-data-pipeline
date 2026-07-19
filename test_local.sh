#!/usr/bin/env bash
# test_local.sh — full local smoke test for cnc-data-pipeline
#
# Run from the project root, with your venv active:
#   bash test_local.sh
#
# What it checks:
#   1. Demo data seeding (SQLite)
#   2. modbus_server.py starts + data_logger.py connects and writes
#      correctly-scaled values (catches the /100 vs /1000 + coil-vs-register bugs)
#   3. opcua_server.py starts cleanly (catches missing config constants)
#   4. FastAPI dashboard + every API endpoint returns 200
#      (/, /api/measurements, /api/stats, /api/fmea, /api/count,
#       /api/spc_chart, /api/distribution_chart)
#   5. FMEA RPN CLI
#   6. SPC Analysis CLI, including the --limit flag
#   7. Slack alert — only if SLACK_WEBHOOK_URL is already set in your shell
#
# Every background process it starts is killed on exit, even on failure/Ctrl+C.

set -uo pipefail

PASS=0
FAIL=0
pass() { echo "✅ $1"; PASS=$((PASS + 1)); }
fail() { echo "❌ $1"; FAIL=$((FAIL + 1)); }

MODBUS_PID=""
API_PID=""

cleanup() {
    echo ""
    echo "Cleaning up background processes..."
    [[ -n "$MODBUS_PID" ]] && kill "$MODBUS_PID" 2>/dev/null
    [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null
}
trap cleanup EXIT

PY=python
command -v python3 >/dev/null 2>&1 && PY=python3

if [[ ! -f "config/settings.py" ]]; then
    echo "❌ Run this script from the project root (config/settings.py not found here)."
    exit 1
fi

echo "=== 0. Fresh database ==="
mkdir -p db
rm -f db/measurements.db
pass "cleared db/measurements.db"

echo ""
echo "=== 1. Seed demo data ==="
if $PY -m data_ingestion.seed_demo_data > /tmp/seed_test.log 2>&1; then
    pass "seed_demo_data"
else
    fail "seed_demo_data (see /tmp/seed_test.log)"
fi

echo ""
echo "=== 2. Modbus server + data logger ==="
$PY data_ingestion/modbus_server.py > /tmp/modbus_test.log 2>&1 &
MODBUS_PID=$!
sleep 2
if grep -q "Server listening" /tmp/modbus_test.log; then
    pass "modbus_server.py starts"
else
    fail "modbus_server.py did not start (see /tmp/modbus_test.log)"
fi

timeout 5 $PY data_ingestion/data_logger.py > /tmp/logger_test.log 2>&1
if grep -q "Data logger started" /tmp/logger_test.log; then
    pass "data_logger.py connects to modbus_server.py"
else
    fail "data_logger.py failed to start (see /tmp/logger_test.log)"
fi

kill "$MODBUS_PID" 2>/dev/null
MODBUS_PID=""

# Sanity-check the values data_logger actually wrote — catches the
# /100 vs /1000 scaling bug and the coil-vs-holding-register bug.
if $PY - <<'EOF'
import sqlite3, sys
conn = sqlite3.connect("db/measurements.db")
cur = conn.cursor()
cur.execute("SELECT diameter FROM measurements ORDER BY id DESC LIMIT 5")
rows = [r[0] for r in cur.fetchall()]
conn.close()
if not rows:
    print("no rows written by data_logger")
    sys.exit(1)
bad = [d for d in rows if not (8.0 < d < 12.0)]
if bad:
    print(f"diameters out of expected mm range: {bad}")
    sys.exit(1)
print(f"diameters in expected range: {rows}")
EOF
then
    pass "data_logger diameter scaling correct (values in ~10mm range)"
else
    fail "data_logger diameter scaling incorrect — check data_logger.py"
fi

echo ""
echo "=== 3. OPC UA server starts cleanly ==="
timeout 4 $PY data_ingestion/opcua_server.py > /tmp/opcua_test.log 2>&1
if grep -q "Starting OPC UA server" /tmp/opcua_test.log; then
    pass "opcua_server.py starts"
else
    fail "opcua_server.py did not start (see /tmp/opcua_test.log)"
fi

echo ""
echo "=== 4. FastAPI dashboard + all endpoints ==="
$PY -m uvicorn app.api:app --port 8000 > /tmp/api_test.log 2>&1 &
API_PID=$!
sleep 3

if $PY - <<'EOF'
import requests, sys
endpoints = {
    "/": "Dashboard",
    "/api/measurements?limit=5": "Measurements",
    "/api/stats": "Stats (Cp/Cpk)",
    "/api/fmea": "FMEA RPN",
    "/api/count": "Count",
    "/api/spc_chart": "SPC control chart",
    "/api/distribution_chart": "Distribution chart",
}
ok = True
for path, name in endpoints.items():
    try:
        r = requests.get(f"http://localhost:8000{path}", timeout=8)
        if r.status_code == 200:
            print(f"OK   {name} ({path}) -> 200")
        else:
            print(f"FAIL {name} ({path}) -> {r.status_code}")
            ok = False
    except Exception as e:
        print(f"FAIL {name} ({path}) -> {e}")
        ok = False
sys.exit(0 if ok else 1)
EOF
then
    pass "all API endpoints return 200"
else
    fail "one or more API endpoints failed (see output above)"
fi

kill "$API_PID" 2>/dev/null
API_PID=""

echo ""
echo "=== 5. FMEA RPN CLI ==="
if $PY -m app.fmea_rpn > /tmp/fmea_test.log 2>&1; then
    pass "app.fmea_rpn CLI runs"
    cat /tmp/fmea_test.log
else
    fail "app.fmea_rpn CLI failed (see /tmp/fmea_test.log)"
fi

echo ""
echo "=== 6. SPC Analysis CLI (full history + --limit) ==="
if $PY -m app.spc_analysis --output /tmp/test_control_chart.png > /tmp/spc_test.log 2>&1 \
    && [[ -f /tmp/test_control_chart.png ]]; then
    pass "spc_analysis generates chart (full history)"
else
    fail "spc_analysis chart not generated (see /tmp/spc_test.log)"
fi

$PY -m app.spc_analysis --limit 20 --output /tmp/test_control_chart_windowed.png > /tmp/spc_test2.log 2>&1
if grep -q "Number of readings: 20" /tmp/spc_test2.log; then
    pass "spc_analysis --limit windows correctly"
else
    fail "spc_analysis --limit did not window correctly (see /tmp/spc_test2.log)"
fi

echo ""
echo "=== 7. Slack alert (optional) ==="
if [[ -n "${SLACK_WEBHOOK_URL:-}" ]]; then
    $PY -c "from data_ingestion.data_logger import log_measurement; log_measurement(10.6, 1)"
    echo "⚠  Alert sent — check your Slack channel manually to confirm delivery."
else
    echo "⏭  SKIPPED (SLACK_WEBHOOK_URL not set in this shell). To test:"
    echo '    export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."'
    echo "    then re-run this script."
fi

echo ""
echo "======================================"
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "======================================"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
