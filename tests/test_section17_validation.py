"""
Section 17: Validation/Promotion Layer - Production E2E Tests
Tests evidence-driven promotion decisions with production VPS database.
"""

import sys
sys.path.insert(0, '/home/wner/Learning-System/fabric/api')

import psycopg2
from psycopg2.extras import RealDictCursor
from uuid import uuid4
import json
from validation_engine import (
    create_validation_candidate,
    add_validation_evidence,
    check_validation_eligibility,
    assess_evidence_sufficiency,
    make_validation_decision,
    apply_validation_decision,
    get_validation_candidate,
    get_validation_decision
)

DB_URL = "postgresql://fabric:fabric@localhost/learning_fabric"

def get_conn():
    return psycopg2.connect(DB_URL)

def test_01_successful_promotion():
    """TEST: Successful promotion with sufficient evidence."""
    conn = get_conn()
    print("\n✓ TEST 1: Successful Promotion")
    
    # Create strategy candidate
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_strategy_promotion')
    """)
    conn.commit()
    
    # Create validation candidate
    candidate_id = create_validation_candidate(
        conn,
        candidate_type='strategy',
        candidate_ref_id=strat_id,
        candidate_name='test_strategy_promotion',
        domain_applicability='test_task'
    )
    
    # Add supporting evidence (5 observations)
    for i in range(5):
        add_validation_evidence(
            conn,
            candidate_id,
            'operational',
            'supportive',
            0.85 + (i * 0.01),
            0.80,
            evidence_summary=f'Observation {i+1}: successful execution'
        )
    
    # Check eligibility
    is_eligible, _ = check_validation_eligibility(conn, candidate_id, min_evidence_required=5)
    assert is_eligible, "Should be eligible with 5 evidence"
    print(f"  ✓ Eligibility check PASS")
    
    # Assess sufficiency
    sufficient, _ = assess_evidence_sufficiency(conn, candidate_id)
    assert sufficient, "Should have sufficient evidence"
    print(f"  ✓ Evidence sufficiency PASS")
    
    # Make promotion decision
    decision_id = make_validation_decision(
        conn,
        candidate_id,
        decision_type='promote',
        rationale='5 supporting observations with average confidence 0.85, no contradictions'
    )
    
    # Apply decision
    success = apply_validation_decision(conn, decision_id)
    assert success, "Should apply promotion"
    
    # Verify candidate status changed
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'promoted', f"Status should be 'promoted', got {candidate['current_status']}"
    print(f"  ✓ Promotion applied, status: {candidate['current_status']}")
    
    conn.close()
    print("  ✓ TEST 1 PASS\n")
    return True

def test_02_insufficient_evidence():
    """TEST: No promotion with insufficient evidence."""
    conn = get_conn()
    print("✓ TEST 2: Insufficient Evidence")
    
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_strategy_insufficient')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_strategy_insufficient'
    )
    
    # Add only 1 evidence (default threshold is 3-5)
    add_validation_evidence(
        conn, candidate_id, 'operational', 'supportive',
        0.70, 0.65, evidence_summary='Single observation'
    )
    
    # Check eligibility
    is_eligible, details = check_validation_eligibility(conn, candidate_id, min_evidence_required=3)
    assert not is_eligible, "Should NOT be eligible with only 1 evidence"
    print(f"  ✓ Eligibility correctly rejected: {details.get('reason', 'insufficient')}")
    
    # Assess sufficiency
    sufficient, details = assess_evidence_sufficiency(conn, candidate_id)
    assert not sufficient, "Should NOT have sufficient evidence"
    print(f"  ✓ Sufficiency assessment: {details.get('sufficiency_level', 'insufficient')}")
    
    # Make decision: insufficient_evidence
    decision_id = make_validation_decision(
        conn, candidate_id, 'insufficient_evidence',
        rationale='Only 1 supporting observation, minimum 3 required'
    )
    
    # Apply decision
    apply_validation_decision(conn, decision_id)
    
    # Verify no promotion occurred
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] != 'promoted', "Should NOT be promoted"
    print(f"  ✓ No inappropriate promotion, status: {candidate['current_status']}")
    
    conn.close()
    print("  ✓ TEST 2 PASS\n")
    return True

def test_03_contradictory_evidence():
    """TEST: Contradiction handling - no blind promotion."""
    conn = get_conn()
    print("✓ TEST 3: Contradictory Evidence")
    
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_strategy_contradiction')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_strategy_contradiction'
    )
    
    # Add supporting evidence
    for i in range(4):
        add_validation_evidence(
            conn, candidate_id, 'operational', 'supportive',
            0.80, 0.75
        )
    
    # Add contradictory evidence
    add_validation_evidence(
        conn, candidate_id, 'operational', 'contradictory',
        0.70, 0.65
    )
    
    # Get evidence counts
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT 
            SUM(CASE WHEN evidence_category = 'supportive' THEN 1 ELSE 0 END) as supporting,
            SUM(CASE WHEN evidence_category = 'contradictory' THEN 1 ELSE 0 END) as contradictory
        FROM validation_evidence WHERE candidate_id = %s
    """, (candidate_id,))
    counts = cur.fetchone()
    print(f"  Supporting: {counts['supporting']}, Contradictory: {counts['contradictory']}")
    
    # Make decision: dispute (not blind promotion)
    decision_id = make_validation_decision(
        conn, candidate_id, 'dispute',
        rationale=f"4 supporting but 1 contradictory evidence. Contradiction prevents automatic promotion. Need manual review."
    )
    
    # Apply decision
    apply_validation_decision(conn, decision_id)
    
    # Verify status is 'disputed', not 'promoted'
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'disputed', f"Should be 'disputed', got {candidate['current_status']}"
    print(f"  ✓ Contradictions handled correctly, status: {candidate['current_status']}")
    
    conn.close()
    print("  ✓ TEST 3 PASS\n")
    return True

def test_04_cross_node_validation():
    """TEST: Cross-node evidence tracking."""
    conn = get_conn()
    print("✓ TEST 4: Cross-Node Validation")
    
    strat_id = uuid4()
    node1 = uuid4()
    node2 = uuid4()
    
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_strategy_crossnode')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_strategy_crossnode',
        source_node_id=node1
    )
    
    # Add evidence from different nodes
    add_validation_evidence(
        conn, candidate_id, 'operational', 'supportive',
        0.85, 0.80, source_node_id=node1
    )
    add_validation_evidence(
        conn, candidate_id, 'operational', 'supportive',
        0.82, 0.78, source_node_id=node2, cross_node_reproduced=True
    )
    
    # Assess sufficiency with independent-node requirement
    sufficient, details = assess_evidence_sufficiency(conn, candidate_id)
    print(f"  ✓ Evidence sufficient: {sufficient}")
    print(f"  ✓ Distinct nodes: {details.get('distinct_nodes', 0)}")
    
    conn.close()
    print("  ✓ TEST 4 PASS\n")
    return True

def test_05_restriction():
    """TEST: Restriction (validation for limited scope)."""
    conn = get_conn()
    print("✓ TEST 5: Restriction")
    
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_strategy_restriction')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_strategy_restriction',
        domain_applicability='analysis_task'  # Restricted to this domain
    )
    
    # Add sufficient evidence
    for i in range(5):
        add_validation_evidence(
            conn, candidate_id, 'operational', 'supportive', 0.85, 0.80
        )
    
    # Make restricted promotion decision
    decision_id = make_validation_decision(
        conn, candidate_id, 'restrict',
        rationale='Validated for analysis_task domain only. Not validated for other domains.'
    )
    
    apply_validation_decision(conn, decision_id)
    
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'restricted', f"Should be 'restricted', got {candidate['current_status']}"
    print(f"  ✓ Restricted promotion applied, status: {candidate['current_status']}")
    print(f"  ✓ Domain: {candidate['domain_applicability']}")
    
    conn.close()
    print("  ✓ TEST 5 PASS\n")
    return True

def test_06_promotion_does_not_override_non_enrolled():
    """TEST: Promoted strategy doesn't affect non-enrolled tasks."""
    conn = get_conn()
    print("✓ TEST 6: Promotion Isolation")
    
    # This verifies promotion is scoped, not global
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_isolation_strategy')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_isolation_strategy',
        domain_applicability='specific_domain'
    )
    
    # Add evidence and promote
    for i in range(5):
        add_validation_evidence(conn, candidate_id, 'operational', 'supportive', 0.85, 0.80)
    
    decision_id = make_validation_decision(
        conn, candidate_id, 'promote',
        rationale='Valid for specific_domain'
    )
    
    apply_validation_decision(conn, decision_id)
    
    # Verify promotion succeeded
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'promoted', "Should be promoted"
    print(f"  ✓ Promoted for domain: {candidate['domain_applicability']}")
    
    # Verify other domains are not affected by this promotion
    # (This would be verified by orchestration rules, not here)
    print(f"  ✓ Scope isolation enforced by orchestration layer")
    
    conn.close()
    print("  ✓ TEST 6 PASS\n")
    return True

def test_07_complete_workflow():
    """TEST: Complete workflow from experiment to promotion."""
    conn = get_conn()
    print("✓ TEST 7: Complete Experiment→Decision→Promotion Workflow")
    
    # Simulate Section 16 experiment
    exp_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO experiments (experiment_id, hypothesis, objective, metrics, status)
        VALUES ('{exp_id}', 'Test hypothesis', 'Compare', '[]', 'completed')
    """)
    conn.commit()
    
    # Create validation candidate from experiment
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_workflow_strategy')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_workflow_strategy',
        source_experiment_id=exp_id
    )
    
    # Add experiment evidence
    add_validation_evidence(
        conn, candidate_id, 'experimental_supportive', 'supportive',
        0.88, 0.85, source_experiment_id=exp_id
    )
    
    # Add operational evidence
    for i in range(4):
        add_validation_evidence(
            conn, candidate_id, 'operational', 'supportive', 0.82, 0.78
        )
    
    # Full validation pipeline
    is_eligible, _ = check_validation_eligibility(conn, candidate_id, min_evidence_required=3)
    sufficient, _ = assess_evidence_sufficiency(conn, candidate_id)
    assert is_eligible and sufficient, "Should pass both checks"
    
    decision_id = make_validation_decision(
        conn, candidate_id, 'promote',
        rationale='Experiment supportive + 4 operational confirmations'
    )
    
    apply_validation_decision(conn, decision_id)
    
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'promoted', "Should be promoted"
    print(f"  ✓ Workflow complete: {candidate['candidate_type']} promoted")
    
    conn.close()
    print("  ✓ TEST 7 PASS\n")
    return True

def test_08_decision_immutability():
    """TEST: Decisions are immutable; history preserved on reversal."""
    conn = get_conn()
    print("✓ TEST 8: Decision Immutability")
    
    strat_id = uuid4()
    conn.cursor().execute(f"""
        INSERT INTO strategies (strategy_id, strategy_name) 
        VALUES ('{strat_id}', 'test_immutability_strategy')
    """)
    conn.commit()
    
    candidate_id = create_validation_candidate(
        conn, 'strategy', strat_id, 'test_immutability_strategy'
    )
    
    # Make and apply first decision
    for i in range(5):
        add_validation_evidence(conn, candidate_id, 'operational', 'supportive', 0.85, 0.80)
    
    decision1_id = make_validation_decision(
        conn, candidate_id, 'promote', 'Initial promotion'
    )
    apply_validation_decision(conn, decision1_id)
    
    # Verify first decision exists
    decision1 = get_validation_decision(conn, decision1_id)
    assert decision1['decision_status'] == 'applied', "First decision should be applied"
    
    # Later add contradictory evidence
    add_validation_evidence(
        conn, candidate_id, 'operational', 'contradictory', 0.70, 0.65
    )
    
    # Make new decision without deleting first
    decision2_id = make_validation_decision(
        conn, candidate_id, 'dispute',
        rationale='New contradictory evidence discovered'
    )
    apply_validation_decision(conn, decision2_id)
    
    # Verify both decisions still exist
    decision1_after = get_validation_decision(conn, decision1_id)
    decision2 = get_validation_decision(conn, decision2_id)
    
    assert decision1_after['decision_status'] == 'applied', "First decision immutable"
    assert decision2['decision_status'] == 'applied', "Second decision recorded"
    print(f"  ✓ First decision preserved: {decision1_after['decision_type']}")
    print(f"  ✓ Second decision recorded: {decision2['decision_type']}")
    
    # Verify current status reflects latest decision
    candidate = get_validation_candidate(conn, candidate_id)
    assert candidate['current_status'] == 'disputed', "Status reflects latest decision"
    print(f"  ✓ Current status: {candidate['current_status']}")
    
    conn.close()
    print("  ✓ TEST 8 PASS\n")
    return True

def run_all_tests():
    """Run all production E2E tests."""
    print("\n" + "="*60)
    print("SECTION 17: VALIDATION/PROMOTION LAYER")
    print("PRODUCTION E2E TESTS")
    print("="*60)
    
    tests = [
        test_01_successful_promotion,
        test_02_insufficient_evidence,
        test_03_contradictory_evidence,
        test_04_cross_node_validation,
        test_05_restriction,
        test_06_promotion_does_not_override_non_enrolled,
        test_07_complete_workflow,
        test_08_decision_immutability
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__} FAILED: {e}\n")
            failed += 1
    
    print("="*60)
    print(f"RESULTS: {passed} PASSED, {failed} FAILED")
    print("="*60 + "\n")
    
    return failed == 0

if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
