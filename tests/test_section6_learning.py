#!/usr/bin/env python3
"""
Test Section 6: Learning and Pattern Analysis System

Tests:
1. Task outcome recording
2. Worker learning profile development
3. Pattern detection and analysis
4. Knowledge artifact storage and retrieval
5. Performance insights and recommendations
6. Learning workflow integration
"""

import os
import sys
import json
import uuid
import psycopg
import urllib.request
import urllib.parse
from datetime import datetime

API_URL = os.environ.get("API_URL", "http://localhost:8000")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://fabric:***@postgres:5432/learning_fabric")

def connect():
    return psycopg.connect(DATABASE_URL)

def api_request(method, endpoint, payload=None, params=None):
    """Make an API request."""
    if method == "GET":
        query_string = urllib.parse.urlencode(params or {})
        url = f"{API_URL}{endpoint}" + (f"?{query_string}" if query_string else "")
        req = urllib.request.Request(url, method="GET")
    else:  # POST
        url = f"{API_URL}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload else None,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"API error on {method} {endpoint}: {e}")
        raise

def setup():
    """Create test workflow, tasks, and nodes."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Get authority
            cur.execute("SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1")
            authority_id = cur.fetchone()[0]
            
            # Create request
            cur.execute(
                "INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                (authority_id, "test", json.dumps({}))
            )
            request_id = cur.fetchone()[0]
            
            # Create workflow
            cur.execute(
                "INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                (request_id, "test", json.dumps({}))
            )
            workflow_id = cur.fetchone()[0]
            
            # Create multiple tasks
            task_ids = []
            for i in range(3):
                cur.execute(
                    "INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                    (workflow_id, "analysis_task", json.dumps({"index": i}))
                )
                task_ids.append(str(cur.fetchone()[0]))
            
            # Create worker node
            cur.execute(
                "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node_id = str(cur.fetchone()[0])
        
        conn.commit()
        return {
            "task_ids": task_ids,
            "node_id": node_id,
        }
    finally:
        conn.close()

def test_record_outcome(data):
    """Test recording task outcomes."""
    print("  • Testing outcome recording...")
    
    task_id = data["task_ids"][0]
    node_id = data["node_id"]
    
    resp = api_request("POST", f"/outcomes/{task_id}", {
        "status": "success",
        "quality_score": 0.95,
        "execution_time_seconds": 30,
        "result_summary": {"items_processed": 100, "success_rate": 1.0},
        "learning_points": ["high accuracy", "efficient processing"]
    }, None)
    
    assert resp["status"] == "recorded"
    print(f"    ✓ Outcome recorded with quality score {resp['quality_score']}")

def test_get_outcomes(data):
    """Test retrieving task outcomes."""
    print("  • Testing get outcomes...")
    
    resp = api_request("GET", f"/outcomes/{data['node_id']}", None, {"limit": 100})
    
    assert "outcomes" in resp
    print(f"    ✓ Retrieved {resp['total']} outcomes")

def test_learning_profile(data):
    """Test worker learning profile."""
    print("  • Testing learning profile...")
    
    # Record multiple outcomes to build profile
    for i, task_id in enumerate(data["task_ids"][:2]):
        quality = 0.85 + (i * 0.05)
        api_request("POST", f"/outcomes/{task_id}",
            {
                "status": "success",
                "quality_score": quality,
                "execution_time_seconds": 25 + i * 5,
                "result_summary": {"batch": i}
            }, None)
    
    # Get learning profile
    resp = api_request("GET", f"/learning/{data['node_id']}", None, {})
    
    assert "skills" in resp
    assert resp["total_skills"] > 0
    print(f"    ✓ Learning profile retrieved: {resp['total_skills']} skills")

def test_patterns(data):
    """Test pattern creation and retrieval."""
    print("  • Testing patterns...")
    
    # Create a pattern
    pattern_resp = api_request("POST", "/patterns", {
        "task_type": "analysis_task",
        "pattern_name": "high_quality_analysis",
        "pattern_rule": {"quality_threshold": 0.9, "time_limit": 60},
        "success_rate": 0.95,
        "occurrence_count": 5
    }, None)
    
    assert pattern_resp["status"] == "created"
    print(f"    ✓ Pattern created: {pattern_resp['pattern_name']}")
    
    # Get patterns
    patterns_resp = api_request("GET", "/patterns", None,
        {"task_type": "analysis_task", "min_success_rate": 0.8})
    
    assert "patterns" in patterns_resp
    print(f"    ✓ Retrieved {patterns_resp['total']} patterns")

def test_insights(data):
    """Test performance insights."""
    print("  • Testing insights...")
    
    node_id = data["node_id"]
    
    # Create an insight
    insight_resp = api_request("POST", f"/insights/{node_id}", {
        "insight_type": "strength",
        "description": "Excellent quality consistency",
        "recommendation": {"focus_area": "speed_optimization", "next_steps": ["practice_speed_drills"]},
        "confidence_score": 0.92,
        "task_type": "analysis_task",
        "evidence_count": 5,
        "actionable": True
    }, None)
    
    assert insight_resp["status"] == "created"
    print(f"    ✓ Insight created with confidence {insight_resp['confidence_score']:.2f}")
    
    # Get insights
    insights_resp = api_request("GET", f"/insights/{node_id}", None,
        {"actionable_only": "true"})
    
    assert "insights" in insights_resp
    print(f"    ✓ Retrieved {insights_resp['total']} insights")

def test_knowledge_artifacts(data):
    """Test knowledge artifact storage and retrieval."""
    print("  • Testing knowledge artifacts...")
    
    # Store an artifact
    artifact_resp = api_request("POST", "/knowledge", {
        "task_type": "analysis_task",
        "artifact_type": "template",
        "content": {"analysis_steps": ["step1", "step2", "step3"], "expected_output": "summary"},
        "quality_score": 0.9,
        "node_id": data["node_id"]
    }, None)
    
    assert artifact_resp["status"] == "stored"
    print(f"    ✓ Knowledge artifact stored: {artifact_resp['artifact_type']}")
    
    # Get artifacts
    artifacts_resp = api_request("GET", "/knowledge", None,
        {"artifact_type": "template", "task_type": "analysis_task", "limit": 100})
    
    assert "artifacts" in artifacts_resp
    print(f"    ✓ Retrieved {artifacts_resp['total']} artifacts")

def test_learning_workflow(data):
    """Test complete learning workflow."""
    print("  • Testing complete learning workflow...")
    
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create a fresh workflow
            cur.execute("SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1")
            authority_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                       (authority_id, "test", json.dumps({})))
            request_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                       (request_id, "learning_test", json.dumps({})))
            workflow_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                       (workflow_id, "classification", json.dumps({"items": 50})))
            task_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                       (uuid.uuid4(), "ai_assistant", "available"))
            worker_node_id = cur.fetchone()[0]
        
        conn.commit()
        
        task_id_str = str(task_id)
        worker_node_id_str = str(worker_node_id)
        
        # Complete assignment
        assign_resp = api_request("POST", "/assignments", {
            "task_id": task_id_str,
            "node_id": worker_node_id_str
        }, None)
        assignment_id = assign_resp["assignment_id"]
        
        # Claim it
        api_request("POST", f"/assignments/{assignment_id}/claim", {
            "node_id": worker_node_id_str
        }, None)
        
        # Complete it
        api_request("POST", f"/assignments/{assignment_id}/complete", {
            "node_id": worker_node_id_str
        }, None)
        
        # Record outcome
        outcome_resp = api_request("POST", f"/outcomes/{task_id_str}",
            {
                "status": "success",
                "quality_score": 0.92,
                "execution_time_seconds": 45,
                "result_summary": {"classified": 50, "accuracy": 0.98}
            }, None)
        
        assert outcome_resp["status"] == "recorded"
        print(f"    ✓ Outcome recorded in workflow")
        
        # Get learning profile
        learning_resp = api_request("GET", f"/learning/{worker_node_id_str}", None, {})
        assert learning_resp["total_skills"] > 0
        print(f"    ✓ Learning profile updated: {learning_resp['total_skills']} skills developed")
        
    finally:
        conn.close()

def main():
    """Run all Section 6 tests."""
    print("\n=== Section 6: Learning and Pattern Analysis Tests ===\n")
    
    try:
        print("1. Setup")
        data = setup()
        print(f"  ✓ Created 3 tasks and 1 worker node")
        
        print("\n2. Test outcome recording")
        test_record_outcome(data)
        
        print("\n3. Test get outcomes")
        test_get_outcomes(data)
        
        print("\n4. Test learning profile")
        test_learning_profile(data)
        
        print("\n5. Test patterns")
        test_patterns(data)
        
        print("\n6. Test insights")
        test_insights(data)
        
        print("\n7. Test knowledge artifacts")
        test_knowledge_artifacts(data)
        
        print("\n8. Test learning workflow")
        test_learning_workflow(data)
        
        print("\n=== ✓ ALL TESTS PASSED ===\n")
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
