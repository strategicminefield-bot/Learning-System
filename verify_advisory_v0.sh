#!/bin/bash
# verify_advisory_v0.sh - Verify Push-Range Advisory Review V0 deployment
set -euo pipefail

echo "=== VERIFY: Push-Range Advisory Review V0 ==="
echo ""

# Test 1: All tables exist
echo "--- Test 1: Table existence ---"
for t in check_spec push_review_run advisory advisory_evidence advisory_observation incident; do
    result=$(docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -tAc "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='$t');" 2>/dev/null)
    if [ "$result" = "t" ]; then
        echo "  PASS: $t exists"
    else
        echo "  FAIL: $t not found (got: $result)"
        exit 1
    fi
done

# Test 2: Seed data loaded (6 check_specs, 6 incidents)
echo ""
echo "--- Test 2: Seed data counts ---"
CHECK_COUNT=$(docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -tAc "SELECT count(*) FROM check_spec;" 2>/dev/null)
echo "  check_spec count: $CHECK_COUNT"
if [ "$CHECK_COUNT" = "6" ]; then
    echo "  PASS: expected 6 check_specs"
else
    echo "  FAIL: expected 6, got $CHECK_COUNT"
    exit 1
fi

INCIDENT_COUNT=$(docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -tAc "SELECT count(*) FROM incident;" 2>/dev/null)
echo "  incident count: $INCIDENT_COUNT"
if [ "$INCIDENT_COUNT" = "6" ]; then
    echo "  PASS: expected 6 incidents"
else
    echo "  FAIL: expected 6, got $INCIDENT_COUNT"
    exit 1
fi

# Test 3: Migration registered
echo ""
echo "--- Test 3: Migration registration ---"
MIG_VER=$(docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -tAc "SELECT version FROM schema_migrations WHERE version='026-push-review-advisory';" 2>/dev/null)
echo "  migration version: $MIG_VER"
if [ "$MIG_VER" = "026-push-review-advisory" ]; then
    echo "  PASS: migration registered"
else
    echo "  FAIL: migration not registered"
    exit 1
fi

# Test 4: Python module loads
echo ""
echo "--- Test 4: Python module load ---"
DBURL=$(docker exec learning-fabric-api env | grep "^DATABASE_URL=" | cut -d= -f2-)
export DATABASE_URL="$DBURL"
if python3 -c "from fabric.api.advisory_engine import record_run, generate_advisories, record_observation, list_run; print('  PASS: module loads correctly')" 2>/dev/null; then
    :
else
    echo "  FAIL: module failed to load"
    exit 1
fi

# Test 5: Engine smoke test
echo ""
echo "--- Test 5: Engine smoke test ---"
DBURL=$(docker exec learning-fabric-api env | grep "^DATABASE_URL=" | cut -d= -f2-)
export DATABASE_URL="$DBURL"
SMOKE_OUTPUT=$(python3 -c "
from fabric.api.advisory_engine import record_run, generate_advisories, record_observation, list_run
import json
run_id = record_run('HEAD~1', 'HEAD')
advs = generate_advisories(run_id, 'HEAD~1', 'HEAD')
summary = list_run(run_id)
print(f'run_id={run_id}')
print(f'advisory_count={len(advs)}')
print(f'run_status={summary[\"status\"]}')
" 2>/dev/null)
echo "  $SMOKE_OUTPUT"
echo "  PASS: engine smoke test"

# Summary
echo ""
echo "=== VERIFY: All checks passed ==="
echo "  6 tables created"
echo "  6 check_specs seeded"
echo "  6 incidents seeded"
echo "  Migration 026 registered"
echo "  Python module loads and runs"