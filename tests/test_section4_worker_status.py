#!/usr/bin/env python3
"""
Test Section 4: Worker Status and Health Tracking API

Tests:
1. Worker status updates and history
2. Heartbeat tracking
3. Worker capabilities management
4. Metrics collection and aggregation
5. Worker listing and filtering
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

def api_request(method, endpoint, payload=None):
    """Make an API request."""
    if method == "GET":
        query_string = urllib.parse.urlencode(payload or {})
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
    """Create test node and run lifecycle."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create node
            cur.execute(
                "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node_id = cur.fetchone()[0]
        
        conn.commit()
        return {"node_id": str(node_id)}
    finally:
        conn.close()

def test_worker_status_update(node_id):
    """Test updating worker status."""
    print("  • Testing worker status update...")
    
    # Update to busy
    resp = api_request("POST", f"/workers/{node_id}/status", {
        "status": "busy",
        "reason": "Processing assignment"
    })
    assert resp["status"] == "updated"
    assert resp["current_status"] == "busy"
    assert resp["previous_status"] == "available"
    print(f"    ✓ Status updated: {resp['previous_status']} → {resp['current_status']}")
    
    # Update back to available
    resp = api_request("POST", f"/workers/{node_id}/status", {
        "status": "available",
        "reason": "Task completed"
    })
    assert resp["current_status"] == "available"
    print(f"    ✓ Status reverted to available")

def test_worker_heartbeat(node_id):
    """Test heartbeat recording."""
    print("  • Testing worker heartbeat...")
    
    resp = api_request("POST", f"/workers/{node_id}/heartbeat", {})
    assert resp["status"] == "heartbeat_recorded"
    assert resp["node_id"] == node_id
    print(f"    ✓ Heartbeat recorded")

def test_worker_capabilities(node_id):
    """Test adding worker capabilities."""
    print("  • Testing worker capabilities...")
    
    # Add capability 1
    resp = api_request("POST", f"/workers/{node_id}/capabilities", {
        "capability_name": "text_analysis",
        "capability_version": "1.0",
        "enabled": True
    })
    assert resp["status"] == "capability_added"
    print(f"    ✓ Capability added: text_analysis")
    
    # Add capability 2
    api_request("POST", f"/workers/{node_id}/capabilities", {
        "capability_name": "code_generation",
        "capability_version": "2.1",
        "enabled": True
    })
    print(f"    ✓ Capability added: code_generation")

def test_get_worker_status(node_id):
    """Test getting worker status and details."""
    print("  • Testing get worker status...")
    
    resp = api_request("GET", f"/workers/{node_id}", {})
    
    assert resp["node_id"] == node_id
    assert resp["status"] == "available"
    assert resp["node_type"] == "ai_assistant"
    assert "created_at" in resp
    
    if resp["capabilities"]:
        print(f"    ✓ Worker has {len(resp['capabilities'])} capabilities")
        for cap in resp["capabilities"]:
            print(f"      - {cap['name']} v{cap['version']}: enabled={cap['enabled']}")
    
    if resp["metrics"]:
        print(f"    ✓ Metrics available: completed={resp['metrics']['tasks_completed']}, failed={resp['metrics']['tasks_failed']}")

def test_list_workers():
    """Test listing workers."""
    print("  • Testing list workers...")
    
    resp = api_request("GET", "/workers", {"limit": 100})
    
    assert "workers" in resp
    assert "total" in resp
    print(f"    ✓ Found {resp['total']} workers")
    
    # Filter by status
    resp = api_request("GET", "/workers", {"status": "available", "limit": 100})
    available_count = resp["total"]
    print(f"    ✓ Available workers: {available_count}")

def test_metrics_summary():
    """Test metrics summary endpoint."""
    print("  • Testing metrics summary...")
    
    resp = api_request("GET", "/workers/metrics/summary", {})
    
    assert "workers_by_status" in resp
    assert "aggregate_metrics" in resp
    
    print(f"    ✓ Workers by status: {resp['workers_by_status']}")
    print(f"    ✓ Aggregate metrics: total_completed={resp['aggregate_metrics']['total_tasks_completed']}")

def test_lifecycle_with_metrics():
    """Test that metrics are updated during lifecycle."""
    print("  • Testing metrics updates during lifecycle...")
    
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create workflow, task, node
            cur.execute("SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1")
            authority_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                       (authority_id, "test", json.dumps({})))
            request_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                       (request_id, "test", json.dumps({})))
            workflow_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                       (workflow_id, "test_task", json.dumps({})))
            task_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                       (uuid.uuid4(), "ai_assistant", "available"))
            node_id = cur.fetchone()[0]
        
        conn.commit()
        
        # Run through API lifecycle
        node_id_str = str(node_id)
        
        # Create assignment
        assign_resp = api_request("POST", "/assignments", {
            "task_id": str(task_id),
            "node_id": node_id_str
        })
        assignment_id = assign_resp["assignment_id"]
        
        # Claim
        api_request("POST", f"/assignments/{assignment_id}/claim", {"node_id": node_id_str})
        
        # Create attempt
        attempt_resp = api_request("POST", f"/assignments/{assignment_id}/attempts", {
            "node_id": node_id_str,
            "method": {}
        })
        attempt_id = attempt_resp["attempt_id"]
        
        # Submit result
        api_request("POST", f"/attempts/{attempt_id}/result", {
            "node_id": node_id_str,
            "result": {"success": True},
            "quality_score": 0.92
        })
        
        # Complete assignment
        api_request("POST", f"/assignments/{assignment_id}/complete", {"node_id": node_id_str})
        
        # Check metrics were updated
        status_resp = api_request("GET", f"/workers/{node_id_str}", {})
        
        if status_resp["metrics"]:
            assert status_resp["metrics"]["tasks_completed"] == 1
            assert status_resp["metrics"]["successful_attempts"] == 1
            print(f"    ✓ Metrics updated: completed_tasks=1, successful_attempts=1")
        
    finally:
        conn.close()

def main():
    """Run all Section 4 tests."""
    print("\n=== Section 4: Worker Status and Health Tracking Tests ===\n")
    
    try:
        print("1. Setup")
        data = setup()
        print(f"  ✓ Created node {data['node_id']}")
        
        print("\n2. Test worker status updates")
        test_worker_status_update(data["node_id"])
        
        print("\n3. Test heartbeat recording")
        test_worker_heartbeat(data["node_id"])
        
        print("\n4. Test worker capabilities")
        test_worker_capabilities(data["node_id"])
        
        print("\n5. Test get worker status")
        test_get_worker_status(data["node_id"])
        
        print("\n6. Test list workers")
        test_list_workers()
        
        print("\n7. Test metrics summary")
        test_metrics_summary()
        
        print("\n8. Test metrics updates during lifecycle")
        test_lifecycle_with_metrics()
        
        print("\n=== ✓ ALL TESTS PASSED ===\n")
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
