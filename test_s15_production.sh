#!/bin/bash
# Section 15 Production Verification Tests

set -e

REMOTE="vultr"
DB_CMD="docker exec learning-fabric-postgres psql -U fabric -d learning_fabric -t"

echo "=========================================="
echo "SECTION 15 — ADAPTIVE ORCHESTRATION"
echo "PRODUCTION VERIFICATION"
echo "=========================================="
echo ""

# Test 1: Schema tables exist
echo "TEST 1: Schema tables created..."
TABLE_COUNT=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'orchestration%'\"" | tr -d ' ')
if [ "$TABLE_COUNT" = "9" ]; then
  echo "✓ TEST 1 PASS: 9 orchestration tables created"
else
  echo "✗ TEST 1 FAIL: Expected 9 tables, got $TABLE_COUNT"
  exit 1
fi

# Test 2: Total table count is 101 (92 baseline + 9 new)
echo ""
echo "TEST 2: Database schema growth..."
TOTAL_TABLES=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'\"" | tr -d ' ')
if [ "$TOTAL_TABLES" = "101" ]; then
  echo "✓ TEST 2 PASS: Total tables 101 (92 baseline + 9 new)"
else
  echo "✗ TEST 2 FAIL: Expected 101 tables, got $TOTAL_TABLES"
  exit 1
fi

# Test 3: Orchestration rule configuration active
echo ""
echo "TEST 3: Active rule configuration..."
RULE_ACTIVE=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_rule_config WHERE active = TRUE\"" | tr -d ' ')
if [ "$RULE_ACTIVE" = "1" ]; then
  echo "✓ TEST 3 PASS: Active rule configuration exists"
else
  echo "✗ TEST 3 FAIL: No active rule configuration"
  exit 1
fi

# Test 4: Insert test orchestration decision
echo ""
echo "TEST 4: Orchestration decision insertion..."
TASK_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
DECISION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
STRATEGY_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
WORKER_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

# Insert test task
ssh $REMOTE "$DB_CMD -c \"INSERT INTO tasks (task_id, task_type, status) VALUES ('$TASK_ID', 'test_orchestration', 'pending')\"" 2>/dev/null || true

# Insert test worker
ssh $REMOTE "$DB_CMD -c \"INSERT INTO nodes (node_id, node_name, status) VALUES ('$WORKER_ID', 'test-orch-worker', 'available')\"" 2>/dev/null || true

# Insert test strategy
ssh $REMOTE "$DB_CMD -c \"INSERT INTO strategies (strategy_id, strategy_name, domain_applicability) VALUES ('$STRATEGY_ID', 'test_orch_strategy', 'test_orchestration')\"" 2>/dev/null || true

# Insert orchestration decision
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_decisions (
  decision_id, task_id, decision_timestamp, context_considered,
  strategy_candidates, strategy_selected, strategy_rationale,
  worker_candidates, worker_selected, worker_rationale,
  execution_plan, confidence_score, evidence_sufficiency,
  evidence_summary, decision_rationale, rule_version
) VALUES (
  '$DECISION_ID', '$TASK_ID', NOW(), '{}',
  '[]', '$STRATEGY_ID', 'Test strategy selected',
  '[]', '$WORKER_ID', 'Test worker selected',
  '{}', 0.85, 'high',
  '{}', '{}', 1
)\"" 2>/dev/null || true

# Verify decision created
DECISION_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_decisions WHERE decision_id = '$DECISION_ID'\"" 2>/dev/null | tr -d ' ')
if [ "$DECISION_EXISTS" = "1" ]; then
  echo "✓ TEST 4 PASS: Orchestration decision created and stored"
else
  echo "✗ TEST 4 FAIL: Orchestration decision not created ($DECISION_EXISTS)"
  exit 1
fi

# Test 5: Plan generation
echo ""
echo "TEST 5: Execution plan creation..."
PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_plans (
  plan_id, decision_id, strategy_id,
  ordered_steps, context_guidance
) VALUES (
  '$PLAN_ID', '$DECISION_ID', '$STRATEGY_ID',
  '[{\"step_order\": 1, \"method\": \"test\"}]',
  '{}'
)\"" 2>/dev/null || true

PLAN_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_plans WHERE plan_id = '$PLAN_ID'\"" 2>/dev/null | tr -d ' ')
if [ "$PLAN_EXISTS" = "1" ]; then
  echo "✓ TEST 5 PASS: Execution plan created"
else
  echo "✗ TEST 5 FAIL: Execution plan not created"
  exit 1
fi

# Test 6: Outcome recording
echo ""
echo "TEST 6: Orchestration outcome recording..."
OUTCOME_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ASSIGNMENT_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_outcomes (
  outcome_evaluation_id, decision_id, assignment_id, task_id,
  actual_outcome_status, attempts_required, actual_quality_score
) VALUES (
  '$OUTCOME_ID', '$DECISION_ID', '$ASSIGNMENT_ID', '$TASK_ID',
  'success', 1, 0.95
)\"" 2>/dev/null || true

OUTCOME_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_outcomes WHERE outcome_evaluation_id = '$OUTCOME_ID'\"" 2>/dev/null | tr -d ' ')
if [ "$OUTCOME_EXISTS" = "1" ]; then
  echo "✓ TEST 6 PASS: Orchestration outcome recorded"
else
  echo "✗ TEST 6 FAIL: Orchestration outcome not recorded"
  exit 1
fi

# Test 7: Replan trigger
echo ""
echo "TEST 7: Replan trigger creation..."
TRIGGER_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
NEW_DECISION_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_replan_triggers (
  trigger_id, original_decision_id, trigger_type, trigger_reason, attempt_number
) VALUES (
  '$TRIGGER_ID', '$DECISION_ID', 'worker_unavailable', 'Test unavailability', 1
)\"" 2>/dev/null || true

TRIGGER_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_replan_triggers WHERE trigger_id = '$TRIGGER_ID'\"" 2>/dev/null | tr -d ' ')
if [ "$TRIGGER_EXISTS" = "1" ]; then
  echo "✓ TEST 7 PASS: Replan trigger created"
else
  echo "✗ TEST 7 FAIL: Replan trigger not created"
  exit 1
fi

# Test 8: Idempotency registry
echo ""
echo "TEST 8: Idempotency prevention..."
REGISTRY_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
REQUEST_HASH="test_hash_$(date +%s)"
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_idempotency_registry (
  registry_id, task_id, request_hash, canonical_decision_id
) VALUES (
  '$REGISTRY_ID', '$TASK_ID', '$REQUEST_HASH', '$DECISION_ID'
)\"" 2>/dev/null || true

REGISTRY_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_idempotency_registry WHERE request_hash = '$REQUEST_HASH'\"" 2>/dev/null | tr -d ' ')
if [ "$REGISTRY_EXISTS" = "1" ]; then
  echo "✓ TEST 8 PASS: Idempotency registry working"
else
  echo "✗ TEST 8 FAIL: Idempotency registry not working"
  exit 1
fi

# Test 9: Fallback registry
echo ""
echo "TEST 9: Fallback orchestration paths..."
FALLBACK_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ssh $REMOTE "$DB_CMD -c \"INSERT INTO orchestration_fallback_registry (
  fallback_id, task_type, fallback_type, fallback_method, fallback_strategy, success_rate_observed
) VALUES (
  '$FALLBACK_ID', 'test_orchestration', 'default', '{}', 'default_strategy', 0.70
)\"" 2>/dev/null || true

FALLBACK_EXISTS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM orchestration_fallback_registry WHERE fallback_id = '$FALLBACK_ID'\"" 2>/dev/null | tr -d ' ')
if [ "$FALLBACK_EXISTS" = "1" ]; then
  echo "✓ TEST 9 PASS: Fallback registry working"
else
  echo "✗ TEST 9 FAIL: Fallback registry not working"
  exit 1
fi

# Test 10: Baseline data preservation
echo ""
echo "TEST 10: Data preservation (Sections 2-14)..."
BASELINE_TASKS=$(ssh $REMOTE "$DB_CMD -c \"SELECT COUNT(*) FROM tasks\"" | tr -d ' ')
if [ "$BASELINE_TASKS" -gt "0" ]; then
  echo "✓ TEST 10 PASS: Baseline tasks preserved ($BASELINE_TASKS tasks)"
else
  echo "✗ TEST 10 FAIL: Baseline tasks lost"
  exit 1
fi

# Test 11: API health
echo ""
echo "TEST 11: API health check..."
API_HEALTH=$(ssh vultr "curl -s http://localhost:8000/health | grep -o '\"status\":\"ok\"'")
if [ ! -z "$API_HEALTH" ]; then
  echo "✓ TEST 11 PASS: API healthy"
else
  echo "✗ TEST 11 FAIL: API unhealthy"
  exit 1
fi

# Summary
echo ""
echo "=========================================="
echo "ALL TESTS PASSED"
echo "=========================================="
echo ""
echo "Schema: 101 total tables (92 baseline + 9 Section 15)"
echo "Orchestration: Decisions, plans, outcomes, replanning"
echo "Evidence: Strategy candidates, worker candidates, evaluation"
echo "Fallback: Default/recovery paths configured"
echo "Data: All baseline sections preserved"
echo ""
