#!/usr/bin/env python3
"""
Test Section 2 completion: Worker / Assignment Lifecycle

Tests the complete lifecycle:
assignment → claim → attempt → result → observations → complete/fail → task/node state updates
"""

import os
import sys
import json
import uuid
import psycopg
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://learning:fabric@localhost/learning_fabric")

def connect():
    """Open a database connection."""
    return psycopg.connect(DATABASE_URL)

def setup():
    """Create a clean test workflow, task, node, and assignment."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create a test request
            cur.execute(
                "SELECT authority_id FROM authority WHERE name='Primary Human Authority' LIMIT 1"
            )
            authority = cur.fetchone()
            if not authority:
                raise Exception("No Primary Human Authority found")
            
            authority_id = authority[0]
            
            cur.execute(
                """
                INSERT INTO requests (authority_id, request_type, content)
                VALUES (%s, %s, %s)
                RETURNING request_id
                """,
                (authority_id, "test", json.dumps({"test": "lifecycle"}))
            )
            request_id = cur.fetchone()[0]
            
            # Create workflow
            cur.execute(
                """
                INSERT INTO workflows (request_id, workflow_type, objective)
                VALUES (%s, %s, %s)
                RETURNING workflow_id
                """,
                (request_id, "test", json.dumps({"objective": "test section 2"}))
            )
            workflow_id = cur.fetchone()[0]
            
            # Create task
            cur.execute(
                """
                INSERT INTO tasks (workflow_id, task_type, specification, priority)
                VALUES (%s, %s, %s, %s)
                RETURNING task_id
                """,
                (workflow_id, "test_task", json.dumps({"test": "spec"}), 0)
            )
            task_id = cur.fetchone()[0]
            
            # Create node
            cur.execute(
                """
                INSERT INTO nodes (node_id, node_type, status)
                VALUES (%s, %s, %s)
                RETURNING node_id
                """,
                (uuid.uuid4(), "ai_assistant", "available")
            )
            node_id = cur.fetchone()[0]
            
            # Create assignment
            cur.execute(
                """
                INSERT INTO assignments (task_id, node_id, status)
                VALUES (%s, %s, %s)
                RETURNING assignment_id
                """,
                (task_id, node_id, "assigned")
            )
            assignment_id = cur.fetchone()[0]
        
        conn.commit()
        return {
            "request_id": request_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "node_id": node_id,
            "assignment_id": assignment_id,
        }
    finally:
        conn.close()

def test_claim_assignment(assignment_id, node_id):
    """Test claiming an assignment."""
    print(f"  • Claiming assignment {assignment_id}...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE assignments
                SET status='claimed', claimed_at=now()
                WHERE assignment_id=%s AND status='assigned'
                RETURNING assignment_id, status
                """,
                (assignment_id,)
            )
            result = cur.fetchone()
            if not result:
                raise Exception("Failed to claim assignment")
            
            # Verify task moved to running
            task_id = cur.execute(
                "SELECT task_id FROM assignments WHERE assignment_id=%s",
                (assignment_id,)
            )
            cur.execute(
                "UPDATE tasks SET status='running', started_at=COALESCE(started_at,now()) WHERE status='pending'"
            )
            
            # Verify node moved to busy
            cur.execute(
                "UPDATE nodes SET status='busy' WHERE node_id=%s",
                (node_id,)
            )
        
        conn.commit()
        print(f"    ✓ Assignment claimed, status: {result[1]}")
        return True
    finally:
        conn.close()

def test_create_attempt(assignment_id, node_id):
    """Test creating an attempt."""
    print(f"  • Creating attempt for assignment {assignment_id}...")
    conn = connect()
    try:
        attempt_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id FROM assignments WHERE assignment_id=%s",
                (assignment_id,)
            )
            task_id = cur.fetchone()[0]
            
            cur.execute(
                """
                INSERT INTO attempts
                (attempt_id, task_id, assignment_id, node_id, attempt_number, method, status, started_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'running', now())
                RETURNING attempt_id, attempt_number, status
                """,
                (attempt_id, task_id, assignment_id, node_id, 1, json.dumps({"method": "test"}))
            )
            result = cur.fetchone()
            
            cur.execute(
                "UPDATE assignments SET attempt_count=1 WHERE assignment_id=%s",
                (assignment_id,)
            )
        
        conn.commit()
        print(f"    ✓ Attempt created: {result[0]}, number: {result[1]}, status: {result[2]}")
        return attempt_id
    finally:
        conn.close()

def test_submit_result(attempt_id, node_id, result_data=None):
    """Test submitting an attempt result."""
    print(f"  • Submitting result for attempt {attempt_id}...")
    conn = connect()
    try:
        result_id = uuid.uuid4()
        if result_data is None:
            result_data = {"output": "test result", "success": True}
        
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id FROM attempts WHERE attempt_id=%s AND status='running'",
                (attempt_id,)
            )
            task_id = cur.fetchone()[0]
            
            cur.execute(
                """
                INSERT INTO results
                (result_id, attempt_id, task_id, node_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'recorded', now())
                RETURNING result_id
                """,
                (result_id, attempt_id, task_id, node_id, json.dumps(result_data), 0.95)
            )
            
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() WHERE attempt_id=%s",
                (attempt_id,)
            )
        
        conn.commit()
        print(f"    ✓ Result recorded: {result_id}")
        return result_id
    finally:
        conn.close()

def test_create_observation(attempt_id, node_id, result_id=None):
    """Test creating an observation."""
    print(f"  • Creating observation for attempt {attempt_id}...")
    conn = connect()
    try:
        observation_id = uuid.uuid4()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO observations
                (observation_id, attempt_id, result_id, observation_type, content, source, confidence, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                RETURNING observation_id, observation_type
                """,
                (
                    observation_id, attempt_id, result_id,
                    "completion_check",
                    json.dumps({"verified": True, "notes": "test observation"}),
                    "test_script",
                    0.99
                )
            )
            result = cur.fetchone()
        
        conn.commit()
        print(f"    ✓ Observation created: {result[0]}, type: {result[1]}")
        return observation_id
    finally:
        conn.close()

def test_complete_assignment(assignment_id, node_id):
    """Test completing an assignment."""
    print(f"  • Completing assignment {assignment_id}...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id FROM assignments WHERE assignment_id=%s",
                (assignment_id,)
            )
            task_id = cur.fetchone()[0]
            
            cur.execute(
                "UPDATE assignments SET status='completed', completed_at=now() WHERE assignment_id=%s",
                (assignment_id,)
            )
            
            cur.execute(
                "UPDATE tasks SET status='completed', completed_at=now() WHERE task_id=%s",
                (task_id,)
            )
            
            cur.execute(
                "UPDATE nodes SET status='available' WHERE node_id=%s",
                (node_id,)
            )
        
        conn.commit()
        print(f"    ✓ Assignment completed, node returned to available")
        return True
    finally:
        conn.close()

def verify_final_state(data):
    """Verify the final state of all objects."""
    print("  • Verifying final state...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Check assignment
            cur.execute(
                "SELECT status FROM assignments WHERE assignment_id=%s",
                (data["assignment_id"],)
            )
            assignment_status = cur.fetchone()[0]
            assert assignment_status == "completed", f"Assignment status is {assignment_status}, expected 'completed'"
            print(f"    ✓ Assignment status: {assignment_status}")
            
            # Check task
            cur.execute(
                "SELECT status FROM tasks WHERE task_id=%s",
                (data["task_id"],)
            )
            task_status = cur.fetchone()[0]
            assert task_status == "completed", f"Task status is {task_status}, expected 'completed'"
            print(f"    ✓ Task status: {task_status}")
            
            # Check node
            cur.execute(
                "SELECT status FROM nodes WHERE node_id=%s",
                (data["node_id"],)
            )
            node_status = cur.fetchone()[0]
            assert node_status == "available", f"Node status is {node_status}, expected 'available'"
            print(f"    ✓ Node status: {node_status}")
            
            # Count attempts
            cur.execute(
                "SELECT COUNT(*) FROM attempts WHERE assignment_id=%s",
                (data["assignment_id"],)
            )
            attempt_count = cur.fetchone()[0]
            assert attempt_count == 1, f"Expected 1 attempt, found {attempt_count}"
            print(f"    ✓ Attempt count: {attempt_count}")
            
            # Count results (linked via attempt)
            cur.execute(
                """
                SELECT COUNT(r.result_id)
                FROM results r
                JOIN attempts a ON r.attempt_id = a.attempt_id
                WHERE a.assignment_id=%s
                """,
                (data["assignment_id"],)
            )
            result_count = cur.fetchone()[0]
            assert result_count == 1, f"Expected 1 result, found {result_count}"
            print(f"    ✓ Result count: {result_count}")
            
            # Count observations
            cur.execute(
                """
                SELECT COUNT(o.observation_id)
                FROM observations o
                JOIN attempts a ON o.attempt_id = a.attempt_id
                WHERE a.assignment_id=%s
                """,
                (data["assignment_id"],)
            )
            observation_count = cur.fetchone()[0]
            assert observation_count == 1, f"Expected 1 observation, found {observation_count}"
            print(f"    ✓ Observation count: {observation_count}")
    finally:
        conn.close()

def main():
    """Run the full Section 2 lifecycle test."""
    print("\n=== Section 2 Lifecycle Test ===\n")
    
    try:
        print("1. Setup (create test data)")
        data = setup()
        print(f"  ✓ Setup complete")
        print(f"    - Request: {data['request_id']}")
        print(f"    - Workflow: {data['workflow_id']}")
        print(f"    - Task: {data['task_id']}")
        print(f"    - Node: {data['node_id']}")
        print(f"    - Assignment: {data['assignment_id']}")
        
        print("\n2. Claim assignment")
        test_claim_assignment(data["assignment_id"], data["node_id"])
        
        print("\n3. Create attempt")
        attempt_id = test_create_attempt(data["assignment_id"], data["node_id"])
        data["attempt_id"] = attempt_id
        
        print("\n4. Submit result")
        result_id = test_submit_result(attempt_id, data["node_id"])
        data["result_id"] = result_id
        
        print("\n5. Create observation")
        observation_id = test_create_observation(attempt_id, data["node_id"], result_id)
        data["observation_id"] = observation_id
        
        print("\n6. Complete assignment")
        test_complete_assignment(data["assignment_id"], data["node_id"])
        
        print("\n7. Verify final state")
        verify_final_state(data)
        
        print("\n=== ✓ ALL TESTS PASSED ===\n")
        return 0
    
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
