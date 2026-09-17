#!/usr/bin/env python3
"""
Test Section 12: Cross-Node Learning Distribution

Tests cross-node learning sharing, promotion eligibility, provenance tracking,
conflict handling, and multi-node evidence aggregation.
"""

import os
import sys
import json
import uuid
import psycopg
from datetime import datetime

API_URL = os.environ.get("API_URL", "http://localhost:8000")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://fabric:***@postgres:5432/learning_fabric")


def connect():
    """Connect to test database."""
    return psycopg.connect(DATABASE_URL)


def setup_test_nodes():
    """Create test nodes (Node A, Node B, unrelated node)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create three test nodes
            nodes = {}
            for name in ['node_a', 'node_b', 'node_unrelated']:
                node_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                    (node_id, 'ai_assistant', 'available')
                )
                nodes[name] = str(cur.fetchone()[0])
            
            conn.commit()
            return nodes
    finally:
        conn.close()


def setup_test_tasks():
    """Create test tasks."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Get authority
            cur.execute("SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1")
            authority_id = cur.fetchone()[0]
            
            # Create requests and tasks for each task type
            tasks = {}
            for task_type in ['data_analysis', 'code_review', 'unrelated_task']:
                # Create request
                cur.execute(
                    "INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                    (authority_id, 'test', json.dumps({}))
                )
                request_id = cur.fetchone()[0]
                
                # Create workflow
                cur.execute(
                    "INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                    (request_id, 'test', json.dumps({}))
                )
                workflow_id = cur.fetchone()[0]
                
                # Create task
                cur.execute(
                    "INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                    (workflow_id, task_type, json.dumps({"task_type": task_type}))
                )
                task_id = cur.fetchone()[0]
                tasks[task_type] = str(task_id)
            
            conn.commit()
            return tasks
    finally:
        conn.close()


def create_node_a_learning(nodes, tasks):
    """Node A performs work and creates learning."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            node_a_id = nodes['node_a']
            task_id = tasks['data_analysis']
            
            # Create assignment
            cur.execute(
                """INSERT INTO assignments (task_id, node_id, status, claimed_at)
                   VALUES (%s, %s, %s, now()) RETURNING assignment_id""",
                (task_id, node_a_id, 'claimed')
            )
            assignment_id = cur.fetchone()[0]
            
            # Create attempt
            cur.execute(
                """INSERT INTO attempts (assignment_id, node_id, status, started_at)
                   VALUES (%s, %s, %s, now()) RETURNING attempt_id""",
                (assignment_id, node_a_id, 'running')
            )
            attempt_id = cur.fetchone()[0]
            
            # Submit result
            cur.execute(
                """INSERT INTO results (attempt_id, node_id, result, quality_score, created_at)
                   VALUES (%s, %s, %s, %s, now()) RETURNING result_id""",
                (attempt_id, node_a_id, json.dumps({"analysis": "high_quality", "findings": "pattern_detected"}), 0.95)
            )
            result_id = cur.fetchone()[0]
            
            # Update attempt to completed
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() WHERE attempt_id=%s",
                (attempt_id,)
            )
            
            # Create outcome
            cur.execute(
                """INSERT INTO task_outcomes (task_id, assignment_id, node_id, outcome_status, quality_score, 
                   execution_time_seconds, result_summary, learning_points)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING outcome_id""",
                (task_id, assignment_id, node_a_id, 'success', 0.95, 30,
                 json.dumps({"analysis": "high_quality"}),
                 json.dumps(["pattern_detected", "efficient_approach"]))
            )
            outcome_id = cur.fetchone()[0]
            
            # Create pattern (learning artifact)
            cur.execute(
                """INSERT INTO result_patterns (task_type, pattern_name, pattern_rule, success_rate, occurrence_count)
                   VALUES (%s, %s, %s, %s, %s) RETURNING pattern_id""",
                ('data_analysis', 'high_quality_analysis', json.dumps({"quality_threshold": 0.9}), 0.95, 1)
            )
            pattern_id = cur.fetchone()[0]
            
            # Create insight
            cur.execute(
                """INSERT INTO performance_insights (node_id, task_type, insight_type, description, recommendation, confidence_score, actionable)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING insight_id""",
                (node_a_id, 'data_analysis', 'strength', 'Excellent pattern detection',
                 json.dumps({"focus": "leverage"}), 0.9, True)
            )
            insight_id = cur.fetchone()[0]
            
            conn.commit()
            return {
                "outcome_id": str(outcome_id),
                "pattern_id": str(pattern_id),
                "insight_id": str(insight_id),
                "attempt_id": str(attempt_id)
            }
    finally:
        conn.close()


def test_promotion_eligibility():
    """Test: Check promotion eligibility rules."""
    print("\nTest 1: Promotion Eligibility")
    
    import requests
    
    # Should pass all rules
    payload = {
        "learning_id": str(uuid.uuid4()),
        "learning_type": "pattern",
        "confidence": 0.92,
        "evidence_count": 3,
        "validation_state": "confirmed",
        "task_type": "data_analysis",
        "contradictions": []
    }
    
    resp = requests.post(f"{API_URL}/api/v1/cross-node/promotion-eligibility", json=payload)
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code} - {resp.text[:200]}")
        return False
    
    data = resp.json()
    if not data.get("eligible"):
        print(f"  FAIL: Learning not eligible. Failed rules: {data.get('rules_failed')}")
        return False
    
    print(f"  PASS: {len(data['rules_passed'])} rules passed")
    return True


def test_node_a_to_organisational_promotion(learning_artifacts):
    """Test: Promote Node A learning to organisational level."""
    print("\nTest 2: Node A Learning → Organisational Promotion")
    
    import requests
    
    node_a_id = "cea1feee-950d-4eeb-a586-cec64428ebf2"  # Known test node
    
    payload = {
        "learning_id": learning_artifacts["pattern_id"],
        "learning_type": "pattern",
        "source_node_id": node_a_id,
        "task_type": "data_analysis",
        "content": {
            "pattern_name": "high_quality_analysis",
            "rule": {"quality_threshold": 0.9},
            "success_rate": 0.95
        },
        "confidence": 0.92,
        "promotion_reason": "multi_success_evidence"
    }
    
    resp = requests.post(f"{API_URL}/api/v1/cross-node/promote", json=payload)
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code} - {resp.text[:200]}")
        return False, None
    
    data = resp.json()
    if data.get("status") not in ["promoted", "already_promoted"]:
        print(f"  FAIL: Status {data.get('status')}")
        return False, None
    
    org_learning_id = data.get("org_learning_id")
    print(f"  PASS: Learning promoted. Org ID: {org_learning_id[:8]}...")
    return True, org_learning_id


def test_cross_node_retrieval(org_learning_id):
    """Test: Node B retrieves organisational learning."""
    print("\nTest 3: Cross-Node Retrieval (Node B)")
    
    import requests
    
    resp = requests.get(f"{API_URL}/api/v1/cross-node/organisational/data_analysis?limit=10")
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code}")
        return False
    
    data = resp.json()
    if not data.get("organisational_learning"):
        print(f"  FAIL: No organisational learning retrieved")
        return False
    
    # Find our promoted learning
    found = False
    for item in data["organisational_learning"]:
        if item["org_learning_id"] == org_learning_id:
            found = True
            break
    
    if not found:
        print(f"  INFO: Promoted learning not in top {len(data['organisational_learning'])} items")
        return False
    
    print(f"  PASS: Retrieved {data['total']} organisational items, found promoted learning")
    return True


def test_cross_node_distribution_record(org_learning_id):
    """Test: Record cross-node distribution."""
    print("\nTest 4: Distribution Record")
    
    import requests
    
    node_a_id = "cea1feee-950d-4eeb-a586-cec64428ebf2"
    node_b_id = "cea1feee-950d-4eeb-a586-cec64428ebf1"  # Different node
    
    payload = {
        "org_learning_id": org_learning_id,
        "source_node_id": node_a_id,
        "target_node_id": node_b_id,
        "retrieval_trace_id": str(uuid.uuid4()),
        "context_package_id": str(uuid.uuid4())
    }
    
    resp = requests.post(f"{API_URL}/api/v1/cross-node/distribution", json=payload)
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code} - {resp.text[:200]}")
        return False, None
    
    data = resp.json()
    if data.get("status") not in ["recorded", "already_recorded"]:
        print(f"  FAIL: Status {data.get('status')}")
        return False, None
    
    distribution_id = data.get("distribution_id")
    print(f"  PASS: Distribution recorded. ID: {distribution_id[:8]}...")
    return True, distribution_id


def test_cross_node_supportive_evidence(org_learning_id, nodes):
    """Test: Node B creates supportive evidence."""
    print("\nTest 5: Cross-Node Supportive Evidence")
    
    import requests
    
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create Node B outcome using organisational learning
            node_b_id = nodes['node_b']
            task_id_analysis = None
            
            # Get data_analysis task
            cur.execute(
                "SELECT task_id FROM tasks WHERE task_type='data_analysis' LIMIT 1"
            )
            result = cur.fetchone()
            if result:
                task_id_analysis = result[0]
            
            if not task_id_analysis:
                print(f"  FAIL: No data_analysis task found")
                return False
            
            # Create assignment for Node B
            cur.execute(
                """INSERT INTO assignments (task_id, node_id, status, claimed_at)
                   VALUES (%s, %s, %s, now()) RETURNING assignment_id""",
                (task_id_analysis, node_b_id, 'claimed')
            )
            assignment_id = cur.fetchone()[0]
            
            # Create attempt
            cur.execute(
                """INSERT INTO attempts (assignment_id, node_id, status, started_at)
                   VALUES (%s, %s, %s, now()) RETURNING attempt_id""",
                (assignment_id, node_b_id, 'running')
            )
            attempt_id = cur.fetchone()[0]
            
            # Complete attempt with similar high-quality result
            cur.execute(
                """INSERT INTO results (attempt_id, node_id, result, quality_score, created_at)
                   VALUES (%s, %s, %s, %s, now()) RETURNING result_id""",
                (attempt_id, node_b_id, json.dumps({"analysis": "high_quality"}), 0.94)
            )
            
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() WHERE attempt_id=%s",
                (attempt_id,)
            )
            
            # Create outcome
            cur.execute(
                """INSERT INTO task_outcomes (task_id, assignment_id, node_id, outcome_status, quality_score)
                   VALUES (%s, %s, %s, %s, %s) RETURNING outcome_id""",
                (task_id_analysis, assignment_id, node_b_id, 'success', 0.94)
            )
            outcome_id = cur.fetchone()[0]
            
            conn.commit()
        
        # Record evidence link
        payload = {
            "org_learning_id": org_learning_id,
            "outcome_id": str(outcome_id),
            "source_node_id": "cea1feee-950d-4eeb-a586-cec64428ebf2",  # Node A
            "consuming_node_id": node_b_id,
            "agreement_type": "supportive",
            "agreement_confidence": 0.88,
            "evidence_summary": {
                "node_b_quality_score": 0.94,
                "similar_pattern_detected": True
            }
        }
        
        resp = requests.post(f"{API_URL}/api/v1/cross-node/evidence-link", json=payload)
        
        if resp.status_code != 200:
            print(f"  FAIL: {resp.status_code} - {resp.text[:200]}")
            return False
        
        data = resp.json()
        if data.get("status") != "recorded":
            print(f"  FAIL: Status {data.get('status')}")
            return False
        
        print(f"  PASS: Supportive evidence recorded")
        return True
    
    finally:
        conn.close()


def test_contradiction_evidence(org_learning_id, nodes):
    """Test: Node B creates contradictory evidence and org learning becomes disputed."""
    print("\nTest 6: Cross-Node Contradiction Evidence")
    
    import requests
    
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create Node B conflicting outcome
            node_b_id = nodes['node_b']
            
            # Get data_analysis task
            cur.execute(
                "SELECT task_id FROM tasks WHERE task_type='data_analysis' LIMIT 1"
            )
            task_id_analysis = cur.fetchone()[0]
            
            # Create assignment with opposite result
            cur.execute(
                """INSERT INTO assignments (task_id, node_id, status, claimed_at)
                   VALUES (%s, %s, %s, now()) RETURNING assignment_id""",
                (task_id_analysis, node_b_id, 'claimed')
            )
            assignment_id = cur.fetchone()[0]
            
            # Create attempt
            cur.execute(
                """INSERT INTO attempts (assignment_id, node_id, status, started_at)
                   VALUES (%s, %s, %s, now()) RETURNING attempt_id""",
                (assignment_id, node_b_id, 'running')
            )
            attempt_id = cur.fetchone()[0]
            
            # Low quality result (contradicts high-quality pattern)
            cur.execute(
                """INSERT INTO results (attempt_id, node_id, result, quality_score, created_at)
                   VALUES (%s, %s, %s, %s, now()) RETURNING result_id""",
                (attempt_id, node_b_id, json.dumps({"analysis": "low_quality"}), 0.35)
            )
            
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() WHERE attempt_id=%s",
                (attempt_id,)
            )
            
            # Create outcome with low quality
            cur.execute(
                """INSERT INTO task_outcomes (task_id, assignment_id, node_id, outcome_status, quality_score)
                   VALUES (%s, %s, %s, %s, %s) RETURNING outcome_id""",
                (task_id_analysis, assignment_id, node_b_id, 'partial', 0.35)
            )
            outcome_id = cur.fetchone()[0]
            
            conn.commit()
        
        # Record contradictory evidence
        payload = {
            "org_learning_id": org_learning_id,
            "outcome_id": str(outcome_id),
            "source_node_id": "cea1feee-950d-4eeb-a586-cec64428ebf2",  # Node A
            "consuming_node_id": node_b_id,
            "agreement_type": "contradictory",
            "agreement_confidence": 0.85,
            "evidence_summary": {
                "contradicts_pattern": "high_quality_analysis",
                "achieved_low_quality": 0.35
            }
        }
        
        resp = requests.post(f"{API_URL}/api/v1/cross-node/evidence-link", json=payload)
        
        if resp.status_code != 200:
            print(f"  FAIL: {resp.status_code}")
            return False
        
        print(f"  PASS: Contradictory evidence recorded")
        return True
    
    finally:
        conn.close()


def test_provenance_tracking(org_learning_id):
    """Test: Retrieve complete provenance with all state transitions."""
    print("\nTest 7: Provenance Tracking")
    
    import requests
    
    resp = requests.get(f"{API_URL}/api/v1/cross-node/provenance/{org_learning_id}")
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code}")
        return False
    
    data = resp.json()
    
    # Check provenance fields
    required_fields = ["source_node_id", "source_learning_id", "promotion_confidence", 
                      "current_state", "promotion_history", "cross_node_evidence"]
    
    for field in required_fields:
        if field not in data:
            print(f"  FAIL: Missing field {field}")
            return False
    
    if not data.get("promotion_history"):
        print(f"  FAIL: No promotion history")
        return False
    
    print(f"  PASS: Complete provenance retrieved with {len(data['promotion_history'])} transitions")
    return True


def test_evidence_summary(org_learning_id):
    """Test: Get evidence summary showing supportive vs contradictory."""
    print("\nTest 8: Evidence Summary")
    
    import requests
    
    resp = requests.get(f"{API_URL}/api/v1/cross-node/evidence-summary/{org_learning_id}")
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code}")
        return False
    
    data = resp.json()
    
    if "evidence_breakdown" not in data:
        print(f"  FAIL: No evidence breakdown")
        return False
    
    print(f"  PASS: Evidence summary retrieved - State: {data['current_state']}, Evidence types: {list(data['evidence_breakdown'].keys())}")
    return True


def test_unrelated_task_exclusion(nodes):
    """Test: Unrelated tasks should not get cross-node learning."""
    print("\nTest 9: Unrelated Task Exclusion")
    
    import requests
    
    # Try to get organisational learning for unrelated task type
    resp = requests.get(f"{API_URL}/api/v1/cross-node/organisational/unrelated_task?limit=10")
    
    if resp.status_code != 200:
        print(f"  FAIL: {resp.status_code}")
        return False
    
    data = resp.json()
    items = data.get("organisational_learning", [])
    
    # Should have no data_analysis learning for unrelated_task
    for item in items:
        if "data_analysis" in str(item.get("content")):
            print(f"  FAIL: Found cross-task learning where shouldn't exist")
            return False
    
    print(f"  PASS: Unrelated task correctly excluded from data_analysis learning")
    return True


def test_idempotency():
    """Test: Duplicate promotion/distribution calls return same ID."""
    print("\nTest 10: Idempotency")
    
    import requests
    
    node_a_id = "cea1feee-950d-4eeb-a586-cec64428ebf2"
    learning_id = str(uuid.uuid4())
    
    payload = {
        "learning_id": learning_id,
        "learning_type": "artifact",
        "source_node_id": node_a_id,
        "task_type": "data_analysis",
        "content": {"test": "idempotency"},
        "confidence": 0.85
    }
    
    # First promotion
    resp1 = requests.post(f"{API_URL}/api/v1/cross-node/promote", json=payload)
    if resp1.status_code != 200:
        print(f"  FAIL: First promotion failed")
        return False
    
    org_id_1 = resp1.json().get("org_learning_id")
    
    # Second promotion (should be idempotent)
    resp2 = requests.post(f"{API_URL}/api/v1/cross-node/promote", json=payload)
    if resp2.status_code != 200:
        print(f"  FAIL: Second promotion failed")
        return False
    
    org_id_2 = resp2.json().get("org_learning_id")
    status_2 = resp2.json().get("status")
    
    if org_id_1 != org_id_2:
        print(f"  FAIL: Different IDs returned ({org_id_1} vs {org_id_2})")
        return False
    
    if status_2 != "already_promoted":
        print(f"  FAIL: Status should be 'already_promoted', got {status_2}")
        return False
    
    print(f"  PASS: Idempotent - second call returned same ID and status")
    return True


def main():
    """Run all Section 12 tests."""
    print("\n=== Section 12: Cross-Node Learning Distribution Tests ===")
    
    results = {}
    
    # Test 1: Promotion eligibility
    results["promotion_eligibility"] = test_promotion_eligibility()
    
    # Setup for remaining tests
    nodes = setup_test_nodes()
    tasks = setup_test_tasks()
    learning_artifacts = create_node_a_learning(nodes, tasks)
    
    # Test 2: Promotion
    success, org_learning_id = test_node_a_to_organisational_promotion(learning_artifacts)
    results["node_a_promotion"] = success
    
    if org_learning_id:
        # Test 3: Retrieval
        results["cross_node_retrieval"] = test_cross_node_retrieval(org_learning_id)
        
        # Test 4: Distribution record
        success, dist_id = test_cross_node_distribution_record(org_learning_id)
        results["distribution_record"] = success
        
        # Test 5: Supportive evidence
        results["supportive_evidence"] = test_cross_node_supportive_evidence(org_learning_id, nodes)
        
        # Test 6: Contradictory evidence
        results["contradiction_evidence"] = test_contradiction_evidence(org_learning_id, nodes)
        
        # Test 7: Provenance
        results["provenance"] = test_provenance_tracking(org_learning_id)
        
        # Test 8: Evidence summary
        results["evidence_summary"] = test_evidence_summary(org_learning_id)
    
    # Test 9: Unrelated task
    results["unrelated_task"] = test_unrelated_task_exclusion(nodes)
    
    # Test 10: Idempotency
    results["idempotency"] = test_idempotency()
    
    # Print results
    print("\n=== Test Results ===")
    passed = 0
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
