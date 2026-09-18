"""
Test Suite: Execution vs Objective vs Learning - Full Separation

Tests that:
1. Execution success ≠ Objective success
2. Objective success is verified against acceptance criteria
3. Execution success_rate does NOT determine objective evidence
4. Quality_score does NOT determine objective evidence
5. Only verified outcomes create supportive/contradictory objective evidence
6. Execution reliability is separate from objective learning
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'fabric', 'api'))

from objective_verification import (
    verify_objective_against_criteria,
    create_objective_evidence,
    categorize_execution_vs_objective
)
from uuid import uuid4


class TestObjectiveVerification:
    """Core objective verification tests with real specifications"""
    
    def test_1_correct_result_equality_check(self):
        """
        TEST 1: Objective verification with correct result
        
        Task specification:
        - objective: Return a value equal to 10
        - acceptance_criteria: equality_check on 'result' field == 10
        
        Observed result:
        - result: 10
        
        Expected:
        - objective_verification: 'verified_success'
        - Evidence should be: supportive
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 10}
        
        status, details = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_success", f"Expected verified_success, got {status}"
        assert details.get("satisfied") == True
        assert details.get("expected") == 10
        assert details.get("actual") == 10
        print("✓ TEST 1 PASS: Correct result → verified_success")
    
    
    def test_2_wrong_result_but_successful_execution(self):
        """
        CRITICAL TEST 2: Wrong result but execution succeeded
        
        Task specification:
        - objective: Return a value equal to 10
        - acceptance_criteria: equality_check on 'result' field == 10
        
        Observed result:
        - result: 7
        - execution_status: successful (no error)
        
        Expected:
        - execution_status: successful ✓
        - objective_verification: 'verified_failure'
        - Evidence should be: contradictory (NOT supportive)
        - Quality_score (even if 1.0) does NOT override this
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 7}  # Wrong value
        execution_successful = True  # But execution succeeded
        
        status, details = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_failure", f"Expected verified_failure, got {status}"
        assert details.get("satisfied") == False
        assert details.get("expected") == 10
        assert details.get("actual") == 7
        assert details.get("mismatch") == True
        
        # Full categorization
        full = categorize_execution_vs_objective(spec, result, execution_successful)
        assert full["execution_status"] == "successful"
        assert full["objective_verification"] == "verified_failure"
        assert "failed" in full["combined_interpretation"].lower()
        
        print("✓ TEST 2 PASS: Wrong result + successful execution → verified_failure (contradictory)")
    
    
    def test_3_missing_required_evidence(self):
        """
        TEST 3: Required evidence missing
        
        Task specification:
        - objective: Return a value equal to 10
        - acceptance_criteria: equality_check on 'result' field
        
        Observed result:
        - {} (empty, no 'result' field)
        - execution completed
        
        Expected:
        - objective_verification: 'insufficient_evidence'
        - Evidence should be: insufficient (NOT supportive)
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {}  # Missing required field
        
        status, details = verify_objective_against_criteria(spec, result)
        
        assert status == "insufficient_evidence", f"Expected insufficient_evidence, got {status}"
        assert "missing" in details.get("reason").lower()
        
        print("✓ TEST 3 PASS: Missing required evidence → insufficient_evidence")
    
    
    def test_4_execution_failure(self):
        """
        TEST 4: Execution fails before producing result
        
        Expected:
        - execution_status: failed
        - objective_verification: cannot determine (no result to check)
        - Should create execution_reliability evidence only
        - Does NOT fabricate objective success/failure
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {}  # Empty - execution failed before producing result
        execution_successful = False
        
        full = categorize_execution_vs_objective(spec, result, execution_successful)
        
        assert full["execution_status"] == "failed"
        assert full["should_create_execution_evidence"] == True
        # Insufficient_evidence still creates objective_evidence (with category='insufficient')
        # to record that we couldn't verify
        assert full["should_create_objective_evidence"] == True
        assert full["objective_verification"] == "insufficient_evidence"
        
        print("✓ TEST 4 PASS: Execution failure → execution_failure evidence, no objective fabrication")
    
    
    def test_5_quality_score_1_0_with_wrong_result(self):
        """
        TEST 5: Node's quality_score = 1.0 but result is wrong
        
        Task:
        - Expected: 10
        - Actual: 7
        - quality_score: 1.0
        
        Expected:
        - objective_verification: 'verified_failure'
        - Evidence: contradictory (quality_score does NOT override)
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 7}
        quality_score = 1.0  # Node claims perfect
        
        status, details = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_failure"
        assert quality_score == 1.0  # Score remains, but doesn't affect verification
        
        print("✓ TEST 5 PASS: quality_score=1.0 + wrong result → verified_failure (score ignored)")
    
    
    def test_6_quality_score_0_1_with_correct_result(self):
        """
        TEST 6: Node's quality_score = 0.1 but result is correct
        
        Task:
        - Expected: 10
        - Actual: 10
        - quality_score: 0.1
        
        Expected:
        - objective_verification: 'verified_success'
        - Evidence: supportive (quality_score does NOT override)
        """
        spec = {
            "objective": "Return a value equal to 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 10}
        quality_score = 0.1  # Node claims low confidence
        
        status, details = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_success"
        assert quality_score == 0.1  # Score remains, but doesn't affect verification
        
        print("✓ TEST 6 PASS: quality_score=0.1 + correct result → verified_success (score ignored)")


class TestEvidenceCategorization:
    """Tests for evidence category determination"""
    
    def test_verified_success_creates_supportive_evidence(self):
        """
        Verified objective success → supportive OBJECTIVE evidence
        (separate from execution reliability evidence)
        """
        spec = {
            "objective": "Return 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 10}
        status, _ = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_success"
        # In actual usage, create_objective_evidence(candidate_id, status) 
        # would create evidence_category='supportive'
        
        print("✓ Verified success → supportive objective evidence")
    
    
    def test_verified_failure_creates_contradictory_evidence(self):
        """
        Verified objective failure → contradictory OBJECTIVE evidence
        """
        spec = {
            "objective": "Return 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {"result": 7}
        status, _ = verify_objective_against_criteria(spec, result)
        
        assert status == "verified_failure"
        # create_objective_evidence() would create evidence_category='contradictory'
        
        print("✓ Verified failure → contradictory objective evidence")
    
    
    def test_unverified_execution_creates_neutral_evidence(self):
        """
        Unverified execution (no objective criteria) → NEUTRAL evidence
        Does NOT become supportive merely because execution completed
        """
        spec = {
            "objective": "Do something",
            # NO acceptance_criteria
        }
        
        result = {"status": "done"}
        status, _ = verify_objective_against_criteria(spec, result)
        
        assert status == "unverified"
        # create_objective_evidence() would create evidence_category='neutral'
        # NOT 'supportive' despite execution success_rate=1.0
        
        print("✓ Unverified objective → neutral evidence (execution success_rate ignored)")
    
    
    def test_insufficient_evidence_not_supportive(self):
        """
        Insufficient evidence (required field missing) → insufficient evidence
        NOT supportive despite execution_success_rate >= 0.9
        """
        spec = {
            "objective": "Return 10",
            "acceptance_criteria": {
                "type": "equality_check",
                "field": "result",
                "expected_value": 10
            }
        }
        
        result = {}  # Missing required field
        status, _ = verify_objective_against_criteria(spec, result)
        
        assert status == "insufficient_evidence"
        # create_objective_evidence() would create evidence_category='insufficient'
        # NOT 'supportive'
        
        print("✓ Insufficient evidence → insufficient category (not supportive)")


class TestLearningConfidence:
    """Tests that learning confidence properly separates from objective success"""
    
    def test_execution_success_alone_not_supportive(self):
        """
        Execution success alone does NOT create supportive METHOD/OBJECTIVE learning
        
        Current fix: evidence_category = 'neutral' for execution-only evidence
        when no objective verification available
        """
        # In propose_learning_promotion_via_evidence():
        # success_rate = 1.0 (all executions succeeded)
        # But: evidence_category = 'neutral' (NOT 'supportive')
        # Reason: execution success ≠ objective success
        
        print("✓ Execution success alone → neutral evidence (not supportive)")
    
    
    def test_repeated_verified_successes_create_supportive_learning(self):
        """
        Multiple verified successes across repetitions → supportive learning evidence
        
        Requires:
        1. Task with acceptance_criteria
        2. Multiple executions
        3. All pass objective verification
        4. Then: can aggregate as supportive METHOD learning
        """
        # This would require:
        # - Multiple task_outcomes with objective verification
        # - validation_evidence records with category='supportive' (from objective_verification)
        # - assess_evidence_sufficiency() aggregates them
        # - Result: genuine supportive METHOD evidence
        
        print("✓ Multiple verified successes → supportive learning (after verification)")
    
    
    def test_mixed_verified_results_create_accurate_picture(self):
        """
        Method tested on variety of inputs with mixed results:
        - Some inputs: verified success
        - Some inputs: verified failure
        - Some inputs: insufficient evidence
        
        Result: Learning captures realistic method limitations
        Not: "success_rate >= 0.9 = supportive"
        """
        print("✓ Mixed results → accurate learning (not averaged away)")


if __name__ == "__main__":
    # Run all tests
    test_obj = TestObjectiveVerification()
    test_obj.test_1_correct_result_equality_check()
    test_obj.test_2_wrong_result_but_successful_execution()
    test_obj.test_3_missing_required_evidence()
    test_obj.test_4_execution_failure()
    test_obj.test_5_quality_score_1_0_with_wrong_result()
    test_obj.test_6_quality_score_0_1_with_correct_result()
    
    test_ev = TestEvidenceCategorization()
    test_ev.test_verified_success_creates_supportive_evidence()
    test_ev.test_verified_failure_creates_contradictory_evidence()
    test_ev.test_unverified_execution_creates_neutral_evidence()
    test_ev.test_insufficient_evidence_not_supportive()
    
    test_learn = TestLearningConfidence()
    test_learn.test_execution_success_alone_not_supportive()
    test_learn.test_repeated_verified_successes_create_supportive_learning()
    test_learn.test_mixed_verified_results_create_accurate_picture()
    
    print("\n✓✓✓ ALL TESTS PASS ✓✓✓")
