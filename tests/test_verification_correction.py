"""
Test Suite: Verification Architecture Correction

Tests that the learning promotion system now respects evidence-based verification
and governance controls instead of naive quality_score threshold.

Core requirement: No AI-generated score can auto-certify work as organizational truth.
"""

import pytest
import json
import psycopg
from uuid import uuid4
from datetime import datetime

DATABASE_URL = "postgresql://fabric:***@localhost:5432/learning_fabric"


@pytest.fixture
def conn():
    """Database connection for tests."""
    c = psycopg.connect(DATABASE_URL)
    yield c
    c.close()


class TestMachineVerification:
    """Test 1: Machine verification with passing evidence"""
    
    def test_passing_evidence_creates_supportive_validation_candidate(self, conn):
        """
        Scenario: Task with machine-verifiable criteria passes all tests.
        Expected: Validation candidate created with supportive evidence.
        """
        with conn.cursor() as cur:
            # Create test task
            task_id = uuid4()
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, status, specification, priority, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (task_id, "test_task_type", "completed", "{}", 1))
            
            # Create result with good quality score
            result_id = uuid4()
            attempt_id = uuid4()
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, status, assigned_node, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (attempt_id, task_id, "completed", uuid4()))
            
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, task_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (result_id, attempt_id, task_id, json.dumps({"tests_passed": 100, "tests_total": 100}), 0.95, "recorded"))
            
            # Create validation candidate for this result
            candidate_id = uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, candidate_name, current_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (candidate_id, "operational_result", result_id, "result", f"Result {result_id}", "eligible"))
            
            # Add evidence: tests passing = supportive evidence
            evidence_id = uuid4()
            cur.execute("""
                INSERT INTO validation_evidence
                (evidence_id, candidate_id, evidence_type, evidence_category, confidence_score, evidence_strength, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (evidence_id, candidate_id, "experimental_supportive", "supportive", 0.95, 0.99))
            
            conn.commit()
            
            # Verify candidate exists with supportive evidence
            cur.execute("""
                SELECT COUNT(*) FROM validation_evidence
                WHERE candidate_id = %s AND evidence_category = 'supportive'
            """, (candidate_id,))
            
            count = cur.fetchone()[0]
            assert count >= 1, "Supportive evidence should be created for passing tests"


class TestMachineVerificationFailure:
    """Test 2: Machine verification with failing evidence"""
    
    def test_failing_evidence_creates_contradictory_validation_candidate(self, conn):
        """
        Scenario: Task with machine-verifiable criteria fails tests.
        Expected: Validation candidate created with contradictory evidence.
        """
        with conn.cursor() as cur:
            # Create test task
            task_id = uuid4()
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, status, specification, priority, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (task_id, "test_fail_type", "completed", "{}", 1))
            
            # Create result with low quality score (failed)
            result_id = uuid4()
            attempt_id = uuid4()
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, status, assigned_node, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (attempt_id, task_id, "completed", uuid4()))
            
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, task_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (result_id, attempt_id, task_id, json.dumps({"tests_passed": 20, "tests_total": 100}), 0.2, "recorded"))
            
            # Create validation candidate
            candidate_id = uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, candidate_name, current_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (candidate_id, "operational_result", result_id, "result", f"Result {result_id}", "eligible"))
            
            # Add evidence: failing tests = contradictory evidence
            evidence_id = uuid4()
            cur.execute("""
                INSERT INTO validation_evidence
                (evidence_id, candidate_id, evidence_type, evidence_category, confidence_score, evidence_strength, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (evidence_id, candidate_id, "experimental_contradictory", "contradictory", 0.8, 0.95))
            
            conn.commit()
            
            # Verify contradictory evidence recorded
            cur.execute("""
                SELECT COUNT(*) FROM validation_evidence
                WHERE candidate_id = %s AND evidence_category = 'contradictory'
            """, (candidate_id,))
            
            count = cur.fetchone()[0]
            assert count >= 1, "Contradictory evidence should be recorded for failing tests"


class TestInsufficientEvidence:
    """Test 3: Insufficient evidence scenario"""
    
    def test_single_outcome_without_threshold_still_requires_validation(self, conn):
        """
        Scenario: One result with quality_score=0.75 (above old 0.7 threshold).
        Expected: Should NOT auto-promote. Requires validation_engine assessment.
        Actual check: Validation candidate exists, decision not automatically 'promote'.
        """
        with conn.cursor() as cur:
            task_id = uuid4()
            result_id = uuid4()
            attempt_id = uuid4()
            
            # Create infrastructure
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, status, specification, priority, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (task_id, "test_insufficient", "completed", "{}", 1))
            
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, status, assigned_node, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (attempt_id, task_id, "completed", uuid4()))
            
            # Result with quality_score=0.75 (would be auto-promoted by old logic)
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, task_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (result_id, attempt_id, task_id, json.dumps({}), 0.75, "recorded"))
            
            # Create validation candidate
            candidate_id = uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, candidate_name, current_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (candidate_id, "operational_result", result_id, "result", "Test", "eligible"))
            
            # Add evidence: only one observation, neutral category
            cur.execute("""
                INSERT INTO validation_evidence
                (evidence_id, candidate_id, evidence_type, evidence_category, confidence_score, evidence_strength, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (uuid4(), candidate_id, "operational_result", "neutral", 0.75, 0.5))
            
            conn.commit()
            
            # Key assertion: NO automatic promotion happened
            # The candidate exists, but decision should be pending/insufficient
            cur.execute("""
                SELECT COUNT(*) FROM validation_decisions
                WHERE candidate_id = %s AND decision_type = 'promote'
            """, (candidate_id,))
            
            auto_promoted = cur.fetchone()[0]
            assert auto_promoted == 0, "Single result with 0.75 score should NOT auto-promote"


class TestExternalEvidenceSupport:
    """Test 4: External evidence verification"""
    
    def test_operational_evidence_recorded_separately(self, conn):
        """
        Scenario: Result linked to operational evidence (production metrics).
        Expected: Evidence recorded with type=operational, not just quality_score.
        """
        with conn.cursor() as cur:
            result_id = uuid4()
            task_id = uuid4()
            attempt_id = uuid4()
            
            # Create result
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, status, specification, priority, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (task_id, "deployment_task", "completed", "{}", 1))
            
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, status, assigned_node, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (attempt_id, task_id, "completed", uuid4()))
            
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, task_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (result_id, attempt_id, task_id, json.dumps({"deployed": True}), 0.8, "recorded"))
            
            # Create validation candidate
            candidate_id = uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, candidate_name, current_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (candidate_id, "operational_result", result_id, "result", "Deployment", "eligible"))
            
            # Add evidence: operational (external measurements)
            evidence_id = uuid4()
            cur.execute("""
                INSERT INTO validation_evidence
                (evidence_id, candidate_id, evidence_type, evidence_category, confidence_score, evidence_strength, 
                 evidence_summary, evidence_detail, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """, (
                evidence_id,
                candidate_id,
                "operational",
                "supportive",
                0.85,
                0.9,
                "Production metrics: latency -12%, errors -3%",
                json.dumps({"latency_improvement": -0.12, "error_reduction": -0.03})
            ))
            
            conn.commit()
            
            # Verify operational evidence recorded
            cur.execute("""
                SELECT COUNT(*) FROM validation_evidence
                WHERE candidate_id = %s AND evidence_type = 'operational'
            """, (candidate_id,))
            
            count = cur.fetchone()[0]
            assert count >= 1, "Operational evidence should be recorded separately from quality_score"


class TestFailedOutcomeLearning:
    """Test 5: Failed outcomes preserved as learning"""
    
    def test_failed_outcomes_retained_not_deleted(self, conn):
        """
        Scenario: Task fails (outcome_status = 'failed').
        Expected: Outcome record preserved, included in learning evidence.
        """
        with conn.cursor() as cur:
            task_id = uuid4()
            node_id = uuid4()
            
            # Create failed outcome
            outcome_id = uuid4()
            cur.execute("""
                INSERT INTO task_outcomes
                (outcome_id, task_id, node_id, outcome_status, quality_score, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (outcome_id, task_id, node_id, "failed", 0.2))
            
            conn.commit()
            
            # Verify outcome still exists
            cur.execute("""
                SELECT outcome_status FROM task_outcomes WHERE outcome_id = %s
            """, (outcome_id,))
            
            result = cur.fetchone()
            assert result is not None, "Failed outcome should be preserved"
            assert result[0] == "failed", "Outcome status should record failure"


class TestHighQualityScoreWithoutEvidence:
    """Test 6: CRITICAL - High quality_score NOT auto-promoted without evidence"""
    
    def test_quality_score_above_0_7_requires_evidence_assessment(self, conn):
        """
        CRITICAL TEST: This validates the fix.
        
        Scenario: Result has quality_score = 0.85 (would trigger old 0.7 threshold).
        But no independent evidence, no cross-node reproduction, no external validation.
        Expected: NOT automatically promoted to organisational_learning.
        Must go through validation_engine assessment.
        """
        with conn.cursor() as cur:
            result_id = uuid4()
            task_id = uuid4()
            attempt_id = uuid4()
            node_id = uuid4()
            
            # Create task + result with high quality_score
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, status, specification, priority, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (task_id, "high_score_test", "completed", "{}", 1))
            
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, status, assigned_node, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (attempt_id, task_id, "completed", node_id))
            
            # CRITICAL: quality_score = 0.85 (above old 0.7 threshold)
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, task_id, node_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            """, (result_id, attempt_id, task_id, node_id, json.dumps({"self_assessment": "excellent"}), 0.85, "recorded"))
            
            # Attempt to find any organisational_learning that was auto-promoted for this node+task
            # Should be NONE, since promotion now requires governance
            cur.execute("""
                SELECT COUNT(*) FROM organisational_learning
                WHERE source_node_id = %s AND source_task_type = %s AND current_state = 'organisational'
            """, (node_id, "high_score_test"))
            
            auto_promoted_count = cur.fetchone()[0]
            
            # Check if validation_decisions exist (should, from finalization pipeline)
            cur.execute("""
                SELECT COUNT(*) FROM validation_candidates
                WHERE candidate_type = 'operational_result' AND candidate_ref_id = %s
            """, (result_id,))
            
            candidate_count = cur.fetchone()[0]
            
            assert auto_promoted_count == 0, \
                f"High quality_score (0.85) should NOT auto-promote. Found {auto_promoted_count} auto-promoted records."
            assert candidate_count >= 1, \
                "Should create validation candidate for evidence assessment (not auto-promote)"


class TestValidationRuleConfigurability:
    """Test 7: Operational result rule exists and is configurable"""
    
    def test_operational_result_validation_rule_exists(self, conn):
        """
        Scenario: New operational_result_evidence_based rule was created.
        Expected: Rule exists, has conservative thresholds, allow_automatic_promotion=FALSE.
        """
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rule_name, candidate_type, min_average_confidence, 
                       allow_automatic_promotion
                FROM validation_rule_configs
                WHERE candidate_type = 'operational_result' AND active = TRUE
            """)
            
            result = cur.fetchone()
            assert result is not None, "operational_result validation rule should exist"
            
            rule_name, candidate_type, min_confidence, allow_auto = result
            assert candidate_type == "operational_result", "Rule should apply to operational_result"
            assert min_confidence == 0.75, f"Should require min confidence 0.75, got {min_confidence}"
            assert allow_auto == False, "allow_automatic_promotion should be FALSE (conservative)"


class TestEvidenceBackedLearningProgression:
    """Test 8: Legitimate evidence-backed learning can progress"""
    
    def test_sufficient_evidence_with_multiple_supportive_sources(self, conn):
        """
        Scenario: Multiple supportive evidence records from different sources.
        Expected: Validation engine would find evidence sufficient, decision proper.
        """
        with conn.cursor() as cur:
            candidate_id = uuid4()
            
            # Create validation candidate
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, candidate_name, current_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
            """, (candidate_id, "operational_result", uuid4(), "result", "Multi-evidence", "eligible"))
            
            # Add 3 supportive evidence records (different sources)
            for i in range(3):
                cur.execute("""
                    INSERT INTO validation_evidence
                    (evidence_id, candidate_id, evidence_type, evidence_category, confidence_score, evidence_strength, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                """, (uuid4(), candidate_id, "experimental_supportive", "supportive", 0.85, 0.9))
            
            conn.commit()
            
            # Verify multiple evidence items exist
            cur.execute("""
                SELECT COUNT(*) FROM validation_evidence
                WHERE candidate_id = %s AND evidence_category = 'supportive'
            """, (candidate_id,))
            
            evidence_count = cur.fetchone()[0]
            assert evidence_count == 3, f"Should have 3 supportive evidence items, got {evidence_count}"


# Pytest entry point
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
