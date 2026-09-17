#!/usr/bin/env python3
"""
Test Section 5: Task Messaging and Inter-Worker Communication API

Tests:
1. Message sending and retrieval
2. Message status tracking
3. Topic subscriptions
4. Task notifications
5. Task details queries
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
    """Create test workflow, task, and nodes."""
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
            
            # Create task
            cur.execute(
                "INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                (workflow_id, "test_task", json.dumps({"test": "spec"}))
            )
            task_id = cur.fetchone()[0]
            
            # Create nodes
            cur.execute(
                "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node1_id = cur.fetchone()[0]
            
            cur.execute(
                "INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node2_id = cur.fetchone()[0]
        
        conn.commit()
        return {
            "task_id": str(task_id),
            "node1_id": str(node1_id),
            "node2_id": str(node2_id),
        }
    finally:
        conn.close()

def test_send_message(data):
    """Test sending messages between workers."""
    print("  • Testing message sending...")
    
    resp = api_request("POST", "/messages", {
        "sender_node_id": data["node1_id"],
        "recipient_node_id": data["node2_id"],
        "message_type": "task_update",
        "subject": "Progress update",
        "content": {"progress": 50, "status": "in_progress"},
        "priority": 1
    })
    
    assert resp["status"] == "sent"
    message_id = resp["message_id"]
    print(f"    ✓ Message sent: {message_id}")
    return message_id

def test_get_messages(data):
    """Test retrieving messages for a worker."""
    print("  • Testing get messages...")
    
    resp = api_request("GET", f"/messages/{data['node2_id']}", params={"limit": 100})
    
    assert "messages" in resp
    print(f"    ✓ Retrieved {resp['total']} messages for node2")
    
    if resp["messages"]:
        msg = resp["messages"][0]
        assert msg["message_type"] == "task_update"
        print(f"    ✓ Message type: {msg['message_type']}, priority: {msg['priority']}")

def test_mark_message_read(data):
    """Test marking messages as read."""
    print("  • Testing mark message as read...")
    
    # First get a message
    resp = api_request("GET", f"/messages/{data['node2_id']}", params={"limit": 1})
    
    if resp["messages"]:
        message_id = resp["messages"][0]["message_id"]
        
        # Mark as read
        read_resp = api_request("POST", f"/messages/{message_id}/read", {})
        assert read_resp["status"] == "read"
        print(f"    ✓ Message marked as read")

def test_subscriptions(data):
    """Test topic subscriptions."""
    print("  • Testing subscriptions...")
    
    # Subscribe to topic
    resp = api_request("POST", "/subscriptions", {
        "node_id": data["node1_id"],
        "topic": "task_updates",
        "filter_criteria": {"task_type": "test_task"}
    })
    
    assert resp["status"] == "subscribed"
    print(f"    ✓ Subscribed to topic: {resp['topic']}")
    
    # Get subscriptions
    subs_resp = api_request("GET", f"/subscriptions/{data['node1_id']}")
    assert subs_resp["total"] > 0
    print(f"    ✓ Retrieved {subs_resp['total']} subscriptions")

def test_get_task_details(data):
    """Test getting task details."""
    print("  • Testing get task details...")
    
    resp = api_request("GET", f"/tasks/{data['task_id']}", {})
    
    assert resp["task_id"] == data["task_id"]
    assert resp["type"] == "test_task"
    assert resp["status"] == "pending"
    print(f"    ✓ Task details retrieved: type={resp['type']}, status={resp['status']}")

def test_task_notifications(data):
    """Test task notifications."""
    print("  • Testing task notifications...")
    
    # Create notification for task change
    notify_resp = api_request("POST", f"/tasks/{data['task_id']}/notify", {
        "node_id": data["node1_id"]
    })
    
    assert notify_resp["status"] == "notified"
    print(f"    ✓ Notification sent to {notify_resp['total_notified']} nodes")
    
    # Get notifications
    notifs_resp = api_request("GET", f"/tasks/{data['task_id']}/notifications", 
                             params={"node_id": data["node1_id"], "limit": 100})
    
    assert "notifications" in notifs_resp
    print(f"    ✓ Retrieved {notifs_resp['total']} notifications")

def test_messaging_workflow(data):
    """Test complete messaging workflow with lifecycle."""
    print("  • Testing complete messaging workflow...")
    
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create workflow, task
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
            worker_node_id = cur.fetchone()[0]
        
        conn.commit()
        
        task_id_str = str(task_id)
        worker_node_id_str = str(worker_node_id)
        
        # Run API lifecycle
        assign_resp = api_request("POST", "/assignments", {
            "task_id": task_id_str,
            "node_id": worker_node_id_str
        })
        assignment_id = assign_resp["assignment_id"]
        
        # Subscribe to task updates
        api_request("POST", "/subscriptions", {
            "node_id": worker_node_id_str,
            "topic": "task_updates"
        })
        
        # Get task details
        task_resp = api_request("GET", f"/tasks/{task_id_str}", {})
        assert task_resp["status"] == "pending"
        print(f"    ✓ Task created and retrieved")
        
        # Claim assignment
        api_request("POST", f"/assignments/{assignment_id}/claim", {
            "node_id": worker_node_id_str
        })
        
        # Send progress message
        msg_resp = api_request("POST", "/messages", {
            "sender_node_id": worker_node_id_str,
            "task_id": task_id_str,
            "message_type": "progress",
            "content": {"progress": 75}
        })
        
        assert msg_resp["status"] == "sent"
        print(f"    ✓ Progress message sent during assignment")
        
    finally:
        conn.close()

def main():
    """Run all Section 5 tests."""
    print("\n=== Section 5: Task Messaging and Communication Tests ===\n")
    
    try:
        print("1. Setup")
        data = setup()
        print(f"  ✓ Created task and 2 nodes")
        
        print("\n2. Test message sending")
        test_send_message(data)
        
        print("\n3. Test get messages")
        test_get_messages(data)
        
        print("\n4. Test mark message as read")
        test_mark_message_read(data)
        
        print("\n5. Test subscriptions")
        test_subscriptions(data)
        
        print("\n6. Test get task details")
        test_get_task_details(data)
        
        print("\n7. Test task notifications")
        test_task_notifications(data)
        
        print("\n8. Test messaging workflow")
        test_messaging_workflow(data)
        
        print("\n=== ✓ ALL TESTS PASSED ===\n")
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
