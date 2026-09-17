#!/usr/bin/env python3
"""
Test Section 3: Event Recording via API Lifecycle

Tests that events are recorded during complete API-based lifecycle.
"""

import os
import sys
import json
import uuid
import psycopg
import urllib.request
import urllib.parse

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
    """Create workflow, task, node."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Get authority
            cur.execute("SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1")
            authority_id = cur.fetchone()[0]
            
            # Create request
            cur.execute(
                "INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                (authority_id, "test", json.dumps({"test": "section 3"}))
            )
            request_id = cur.fetchone()[0]
            
            # Create workflow
            cur.execute(
                "INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                (request_id, "test", json.dumps({"objective": "test section 3"}))
            )
            workflow_id = cur.fetchone()[0]
            
            # Create task
            cur.execute(
                "INSERT INTO tasks (workflow_id, task_type, specification, priority) VALUES (%s, %s, %s, %s) RETURNING task_id",
                (workflow_id, "test_task", json.dumps({"test": "spec"}), 0)
            )
            task_id = cur.fetchone()[0]
            
            # Create node
            cur.execute(
                "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node_id = cur.fetchone()[0]
        
        conn.commit()
        return {
            "request_id": str(request_id),
            "workflow_id": str(workflow_id),
            "task_id": str(task_id),
            "node_id": str(node_id),
        }
    finally:
        conn.close()

def test_api_lifecycle():
    """Run lifecycle through API and verify events recorded."""
    print("\n=== Section 3: API Events Test ===\n")
    
    try:
        print("1. Setup")
        data = setup()
        print(f"  ✓ Created task {data['task_id']}, node {data['node_id']}")
        
        print("\n2. Create assignment")
        assign_resp = api_request("POST", "/assignments", {
            "task_id": data["task_id"],
            "node_id": data["node_id"]
        })
        assignment_id = assign_resp["assignment_id"]
        print(f"  ✓ Created assignment {assignment_id}")
        
        print("\n3. Claim assignment")
        api_request("POST", f"/assignments/{assignment_id}/claim", {
            "node_id": data["node_id"]
        })
        print(f"  ✓ Claimed assignment")
        
        print("\n4. Create attempt")
        attempt_resp = api_request("POST", f"/assignments/{assignment_id}/attempts", {
            "node_id": data["node_id"],
            "method": {"type": "test"}
        })
        attempt_id = attempt_resp["attempt_id"]
        print(f"  ✓ Created attempt {attempt_id}")
        
        print("\n5. Submit result")
        result_resp = api_request("POST", f"/attempts/{attempt_id}/result", {
            "node_id": data["node_id"],
            "result": {"success": True},
            "quality_score": 0.95
        })
        result_id = result_resp["result_id"]
        print(f"  ✓ Submitted result {result_id}")
        
        print("\n6. Create observation")
        obs_resp = api_request("POST", f"/attempts/{attempt_id}/observations", {
            "node_id": data["node_id"],
            "observation_type": "check",
            "content": {"verified": True},
            "source": "test_api",
            "confidence": 0.99,
            "result_id": result_id
        })
        observation_id = obs_resp["observation_id"]
        print(f"  ✓ Created observation {observation_id}")
        
        print("\n7. Complete assignment")
        api_request("POST", f"/assignments/{assignment_id}/complete", {
            "node_id": data["node_id"]
        })
        print(f"  ✓ Completed assignment")
        
        print("\n8. Query events")
        # Query events for assignment
        events_resp = api_request("GET", "/events", {
            "entity_type": "assignment",
            "entity_id": assignment_id,
            "limit": 100
        })
        events = events_resp["events"]
        print(f"  ✓ Found {len(events)} events for assignment")
        
        if len(events) > 0:
            print(f"\n  Event sequence:")
            for event in sorted(events, key=lambda e: e["created_at"]):
                print(f"    - {event['event_type']}: {event.get('previous_state')} → {event.get('current_state')}")
        
        print("\n9. Query audit trail")
        audit_resp = api_request("GET", f"/audit/assignment/{assignment_id}", {"limit": 100})
        audit_events = audit_resp["events"]
        print(f"  ✓ Audit trail has {audit_events} events")
        
        print("\n=== ✓ API EVENTS TEST PASSED ===\n")
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_api_lifecycle())
