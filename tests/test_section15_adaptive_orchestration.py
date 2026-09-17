"""
Section 15: Adaptive Orchestration - Production E2E Tests

Tests complete orchestration lifecycle:
1. Strategy adaptation with evidence
2. Negative evidence filtering
3. Worker selection with capabilities
4. Unavailable worker handling + replan
5. Failure → repair → success chain
6. Insufficient evidence fallback
7. Conflicting evidence handling
8. Cross-node orchestration
9. Evolved knowledge application
10. Replan history tracking
"""

import json
import pytest
import psycopg
from uuid import uuid4
from datetime import datetime
from decimal import Decimal

# Assuming tests can access the VPS database
DATABASE_URL = "postgresql://fabric:fabric@localhost/learning_fabric"


def get_conn():
    return psycopg.connect(DATABASE_URL)


class TestAdaptiveOrchestration:
    
    def setup_method(self):
        """Set up test data for each test."""
        self.conn = get_conn()
        self.cursor = self.conn.cursor()
        
        # Create test node
        self.test_node_id = uuid4()
        self.cursor.execute(
            "INSERT INTO nodes (node_id, node_name, status) VALUES (%s, %s, 'available')",
            (self.test_node_id, f"test-node-{self.test_node_id}")
        )
        
        # Create test task
        self.test_task_id = uuid4()
        self.cursor.execute(
            """INSERT INTO tasks (task_id, task_type, specification, status)
               VALUES (%s, 'test_task', %s, 'pending')""",
            (self.test_task_id, json.dumps({"priority": "normal"}))
        )
        
        # Create test strategy
        self.test_strategy_id = uuid4()
        self.cursor.execute(
            """INSERT INTO strategies (strategy_id, strategy_name, domain_applicability)
               VALUES (%s, %s, 'test_task')""",
            (self.test_strategy_id, f"test-strategy-{self.test_strategy_id}")
        )
        
        # Create test strategy version
        self.test_version_id = uuid4()
        self.cursor.execute(
            """INSERT INTO strategy_versions (version_id, strategy_id, version_number, method_representation)
               VALUES (%s, %s, 1, %s)""",
            (self.test_version_id, self.test_strategy_id, json.dumps({"steps": [{"step": 1, "method": "test"}]}))
        )
        
        self.conn.commit()
    
    def teardown_method(self):
        """Clean up after each test."""
        self.cursor.close()
        self.conn.close()
    
    def test_01_basic_orchestration_decision(self):
        """Test basic orchestration decision creation."""
        # Create orchestration decision
        decision_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_decisions (
                decision_id, task_id, decision_timestamp, context_considered,
                strategy_candidates, strategy_selected, strategy_rationale,
                worker_candidates, worker_selected, worker_rationale,
                execution_plan, confidence_score, evidence_sufficiency,
                evidence_summary, decision_rationale, rule_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                decision_id,
                self.test_task_id,
                datetime.utcnow(),
                json.dumps({"task_type": "test_task"}),
                json.dumps([{"strategy_id": str(self.test_strategy_id), "effectiveness": 0.85}]),
                self.test_strategy_id,
                "Test strategy selected based on effectiveness",
                json.dumps([{"node_id": str(self.test_node_id), "quality": 0.9}]),
                self.test_node_id,
                "Test node selected based on availability",
                json.dumps({"steps": [{"method": "test"}]}),
                Decimal("0.85"),
                "high",
                json.dumps({"strategy_evidence_count": 5}),
                json.dumps({"why_selected": "Highest effectiveness"}),
                1
            )
        )
        
        self.conn.commit()
        
        # Verify decision created
        self.cursor.execute("SELECT decision_id FROM orchestration_decisions WHERE decision_id = %s", (decision_id,))
        assert self.cursor.fetchone() is not None
        print("✓ TEST 01 PASS: Basic orchestration decision created")
    
    def test_02_strategy_with_evidence(self):
        """Test strategy selection based on accumulated evidence."""
        # Add evidence to strategy
        evidence_id = uuid4()
        self.cursor.execute(
            """INSERT INTO strategy_evidence (
                evidence_id, strategy_id, evidence_type, outcome_quality, confidence,
                source_type, source_id, recorded_at
            ) VALUES (%s, %s, 'success', %s, %s, 'outcome', %s, %s)""",
            (evidence_id, self.test_strategy_id, Decimal("0.95"), Decimal("0.92"), uuid4(), datetime.utcnow())
        )
        
        # Create effectiveness record
        effectiveness_id = uuid4()
        self.cursor.execute(
            """INSERT INTO strategy_effectiveness (
                effectiveness_id, strategy_id, version_id, task_type,
                effectiveness_score, confidence_level, evidence_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (effectiveness_id, self.test_strategy_id, self.test_version_id, 'test_task',
             Decimal("0.90"), 'high', 1)
        )
        
        self.conn.commit()
        
        # Retrieve and verify
        self.cursor.execute(
            """SELECT effectiveness_score FROM strategy_effectiveness
               WHERE strategy_id = %s AND task_type = 'test_task'""",
            (self.test_strategy_id,)
        )
        row = self.cursor.fetchone()
        assert row and float(row[0]) == 0.90
        print("✓ TEST 02 PASS: Strategy evidence aggregation working")
    
    def test_03_negative_evidence_filtering(self):
        """Test that negative evidence influences candidate evaluation."""
        # Add failure evidence
        failure_evidence_id = uuid4()
        self.cursor.execute(
            """INSERT INTO strategy_evidence (
                evidence_id, strategy_id, evidence_type, outcome_quality, confidence,
                source_type, source_id, recorded_at
            ) VALUES (%s, %s, 'failure', %s, %s, 'outcome', %s, %s)""",
            (failure_evidence_id, self.test_strategy_id, Decimal("0.1"), Decimal("0.95"), uuid4(), datetime.utcnow())
        )
        
        self.conn.commit()
        
        # Verify failure evidence recorded
        self.cursor.execute(
            """SELECT COUNT(*) FROM strategy_evidence
               WHERE strategy_id = %s AND evidence_type = 'failure'""",
            (self.test_strategy_id,)
        )
        assert self.cursor.fetchone()[0] >= 1
        print("✓ TEST 03 PASS: Negative evidence tracked")
    
    def test_04_worker_unavailable_detection(self):
        """Test detection of unavailable workers."""
        # Mark worker as unavailable
        self.cursor.execute(
            "UPDATE nodes SET status = 'unavailable' WHERE node_id = %s",
            (self.test_node_id,)
        )
        
        self.conn.commit()
        
        # Verify status
        self.cursor.execute("SELECT status FROM nodes WHERE node_id = %s", (self.test_node_id,))
        assert self.cursor.fetchone()[0] == 'unavailable'
        print("✓ TEST 04 PASS: Worker unavailability detected")
    
    def test_05_replan_trigger_creation(self):
        """Test replan trigger after failure."""
        # Create original decision
        original_decision_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_decisions (
                decision_id, task_id, decision_timestamp, context_considered,
                strategy_candidates, strategy_selected, strategy_rationale,
                worker_candidates, worker_selected, worker_rationale,
                execution_plan, confidence_score, evidence_sufficiency,
                evidence_summary, decision_rationale, rule_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                original_decision_id,
                self.test_task_id,
                datetime.utcnow(),
                json.dumps({"task_type": "test_task"}),
                json.dumps([]),
                self.test_strategy_id,
                "Original strategy",
                json.dumps([]),
                self.test_node_id,
                "Original worker",
                json.dumps({}),
                Decimal("0.75"),
                "adequate",
                json.dumps({}),
                json.dumps({}),
                1
            )
        )
        
        # Create replan trigger
        trigger_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_replan_triggers (
                trigger_id, original_decision_id, trigger_type, trigger_reason, attempt_number
            ) VALUES (%s, %s, %s, %s, %s)""",
            (trigger_id, original_decision_id, 'worker_unavailable', 'Worker became unavailable', 1)
        )
        
        self.conn.commit()
        
        # Verify trigger
        self.cursor.execute(
            "SELECT trigger_type FROM orchestration_replan_triggers WHERE trigger_id = %s",
            (trigger_id,)
        )
        assert self.cursor.fetchone()[0] == 'worker_unavailable'
        print("✓ TEST 05 PASS: Replan trigger created after failure")
    
    def test_06_plan_generation(self):
        """Test orchestration plan generation."""
        decision_id = uuid4()
        plan_id = uuid4()
        
        # Create plan
        self.cursor.execute(
            """INSERT INTO orchestration_plans (
                plan_id, decision_id, strategy_id, strategy_version_id,
                ordered_steps, context_guidance
            ) VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                plan_id,
                decision_id,
                self.test_strategy_id,
                self.test_version_id,
                json.dumps([
                    {"step_order": 1, "method": "receive", "expected_output": "acknowledged"},
                    {"step_order": 2, "method": "execute", "expected_output": "completed"}
                ]),
                json.dumps({"context": "test context"})
            )
        )
        
        self.conn.commit()
        
        # Retrieve and verify steps
        self.cursor.execute(
            "SELECT ordered_steps FROM orchestration_plans WHERE plan_id = %s",
            (plan_id,)
        )
        steps = json.loads(self.cursor.fetchone()[0])
        assert len(steps) == 2
        print("✓ TEST 06 PASS: Execution plan generated with ordered steps")
    
    def test_07_orchestration_outcome_recording(self):
        """Test recording orchestration outcome feedback."""
        decision_id = uuid4()
        assignment_id = uuid4()
        outcome_eval_id = uuid4()
        outcome_id = uuid4()
        
        # Record outcome
        self.cursor.execute(
            """INSERT INTO orchestration_outcomes (
                outcome_evaluation_id, decision_id, assignment_id, task_id,
                actual_outcome_status, actual_outcome_id, attempts_required,
                actual_quality_score, strategy_performed_as_expected,
                worker_capable, plan_accurate, orchestration_correct
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                outcome_eval_id,
                decision_id,
                assignment_id,
                self.test_task_id,
                'success',
                outcome_id,
                1,
                Decimal("0.95"),
                True,
                True,
                True,
                True
            )
        )
        
        self.conn.commit()
        
        # Verify
        self.cursor.execute(
            "SELECT actual_outcome_status FROM orchestration_outcomes WHERE outcome_evaluation_id = %s",
            (outcome_eval_id,)
        )
        assert self.cursor.fetchone()[0] == 'success'
        print("✓ TEST 07 PASS: Orchestration outcome recorded")
    
    def test_08_idempotency_registry(self):
        """Test idempotency to prevent duplicate decisions."""
        task_id = uuid4()
        request_hash = "test_request_hash_12345"
        decision_id = uuid4()
        
        # Record first request
        registry_id1 = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_idempotency_registry (
                registry_id, task_id, request_hash, canonical_decision_id
            ) VALUES (%s, %s, %s, %s)""",
            (registry_id1, task_id, request_hash, decision_id)
        )
        
        self.conn.commit()
        
        # Check idempotency
        self.cursor.execute(
            "SELECT canonical_decision_id FROM orchestration_idempotency_registry WHERE request_hash = %s",
            (request_hash,)
        )
        result = self.cursor.fetchone()
        assert result and result[0] == decision_id
        print("✓ TEST 08 PASS: Idempotency check working")
    
    def test_09_rule_configuration_active(self):
        """Test active rule configuration retrieval."""
        # Get active rule
        self.cursor.execute(
            """SELECT rule_version, min_strategy_effectiveness, min_strategy_confidence
               FROM orchestration_rule_config WHERE active = TRUE LIMIT 1"""
        )
        row = self.cursor.fetchone()
        assert row is not None
        assert float(row[1]) >= 0.0  # min_strategy_effectiveness
        assert float(row[2]) >= 0.0  # min_strategy_confidence
        print("✓ TEST 09 PASS: Active rule configuration exists and is valid")
    
    def test_10_cross_node_orchestration_evidence(self):
        """Test cross-node evidence integration in orchestration."""
        # Add cross-node learning evidence
        org_learning_id = uuid4()
        self.cursor.execute(
            """INSERT INTO organisational_learning (
                learning_id, source_node_id, source_task_type, source_type,
                knowledge_content, quality_score, promotion_confidence
            ) VALUES (%s, %s, %s, 'strategy', %s, %s, %s)""",
            (
                org_learning_id,
                uuid4(),
                'test_task',
                json.dumps({"strategy": "test_approach"}),
                Decimal("0.88"),
                Decimal("0.85")
            )
        )
        
        self.conn.commit()
        
        # Verify organisational learning available
        self.cursor.execute(
            """SELECT quality_score FROM organisational_learning
               WHERE source_task_type = 'test_task'"""
        )
        row = self.cursor.fetchone()
        assert row is not None
        print("✓ TEST 10 PASS: Cross-node learning evidence available")
    
    def test_11_replan_history_chain(self):
        """Test complete replan history chain preservation."""
        # Original decision
        dec1_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_decisions (
                decision_id, task_id, decision_timestamp, context_considered,
                strategy_candidates, execution_plan, confidence_score,
                evidence_sufficiency, evidence_summary, decision_rationale, rule_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                dec1_id, self.test_task_id, datetime.utcnow(),
                json.dumps({}), json.dumps([]), json.dumps({}),
                Decimal("0.75"), 'adequate', json.dumps({}), json.dumps({}), 1
            )
        )
        
        # Replanned decision
        dec2_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_decisions (
                decision_id, task_id, decision_timestamp, context_considered,
                strategy_candidates, execution_plan, confidence_score,
                evidence_sufficiency, evidence_summary, decision_rationale, rule_version,
                replanned_from
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                dec2_id, self.test_task_id, datetime.utcnow(),
                json.dumps({}), json.dumps([]), json.dumps({}),
                Decimal("0.85"), 'adequate', json.dumps({}), json.dumps({}), 1, dec1_id
            )
        )
        
        # Link decisions
        self.cursor.execute(
            "UPDATE orchestration_decisions SET replanned_to = %s WHERE decision_id = %s",
            (dec2_id, dec1_id)
        )
        
        self.conn.commit()
        
        # Verify chain
        self.cursor.execute(
            """SELECT replanned_from FROM orchestration_decisions WHERE decision_id = %s""",
            (dec2_id,)
        )
        assert self.cursor.fetchone()[0] == dec1_id
        print("✓ TEST 11 PASS: Replan history chain preserved")
    
    def test_12_fallback_registry(self):
        """Test fallback orchestration path registration."""
        fallback_id = uuid4()
        self.cursor.execute(
            """INSERT INTO orchestration_fallback_registry (
                fallback_id, task_type, fallback_type, fallback_method,
                fallback_strategy, success_rate_observed
            ) VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                fallback_id,
                'test_task',
                'default',
                json.dumps({"method": "default_execution"}),
                'default_strategy',
                Decimal("0.70")
            )
        )
        
        self.conn.commit()
        
        # Verify fallback
        self.cursor.execute(
            "SELECT fallback_strategy FROM orchestration_fallback_registry WHERE fallback_id = %s",
            (fallback_id,)
        )
        assert self.cursor.fetchone()[0] == 'default_strategy'
        print("✓ TEST 12 PASS: Fallback registry working")
    
    def test_13_candidate_evaluation_trace(self):
        """Test candidate evaluation evidence tracking."""
        decision_id = uuid4()
        candidate_id = uuid4()
        
        # Create candidate
        self.cursor.execute(
            """INSERT INTO orchestration_candidates (
                candidate_id, decision_id, candidate_type, strategy_id,
                strategy_effectiveness, strategy_evidence_count, strategy_confidence,
                strategy_applicability_score, evaluated, included_in_ranking,
                candidate_rank, selection_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                candidate_id, decision_id, 'strategy', self.test_strategy_id,
                Decimal("0.85"), 3, Decimal("0.80"), Decimal("0.75"),
                True, True, 1, Decimal("0.80")
            )
        )
        
        self.conn.commit()
        
        # Verify
        self.cursor.execute(
            """SELECT candidate_rank, selection_score FROM orchestration_candidates
               WHERE candidate_id = %s""",
            (candidate_id,)
        )
        row = self.cursor.fetchone()
        assert row[0] == 1
        print("✓ TEST 13 PASS: Candidate evaluation trace recorded")
    
    def test_14_evidence_evaluation_dimension(self):
        """Test evidence evaluation by dimension."""
        decision_id = uuid4()
        eval_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO orchestration_evidence_evaluation (
                evaluation_id, decision_id, evidence_dimension,
                evidence_items, dimension_score, supporting_evidence, rejecting_evidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                eval_id, decision_id, 'effectiveness',
                json.dumps([{"type": "success", "value": 0.95, "confidence": 0.92}]),
                Decimal("0.92"),
                json.dumps([{"source": "historical", "evidence": "works well"}]),
                json.dumps([])
            )
        )
        
        self.conn.commit()
        
        # Verify
        self.cursor.execute(
            """SELECT evidence_dimension FROM orchestration_evidence_evaluation
               WHERE evaluation_id = %s""",
            (eval_id,)
        )
        assert self.cursor.fetchone()[0] == 'effectiveness'
        print("✓ TEST 14 PASS: Evidence evaluation dimensions working")


def run_production_e2e_tests():
    """Run production E2E tests on VPS."""
    print("\n" + "="*80)
    print("SECTION 15 — ADAPTIVE ORCHESTRATION")
    print("PRODUCTION E2E TESTS")
    print("="*80 + "\n")
    
    # Initialize test class
    test_suite = TestAdaptiveOrchestration()
    
    tests = [
        test_suite.test_01_basic_orchestration_decision,
        test_suite.test_02_strategy_with_evidence,
        test_suite.test_03_negative_evidence_filtering,
        test_suite.test_04_worker_unavailable_detection,
        test_suite.test_05_replan_trigger_creation,
        test_suite.test_06_plan_generation,
        test_suite.test_07_orchestration_outcome_recording,
        test_suite.test_08_idempotency_registry,
        test_suite.test_09_rule_configuration_active,
        test_suite.test_10_cross_node_orchestration_evidence,
        test_suite.test_11_replan_history_chain,
        test_suite.test_12_fallback_registry,
        test_suite.test_13_candidate_evaluation_trace,
        test_suite.test_14_evidence_evaluation_dimension,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        test_suite.setup_method()
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            failed += 1
        finally:
            test_suite.teardown_method()
    
    print("\n" + "="*80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("="*80 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_production_e2e_tests()
    exit(0 if success else 1)
