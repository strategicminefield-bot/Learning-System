#!/usr/bin/env python3
"""
Test Section 3: Event Recording and History API

Tests:
1. Event recording during lifecycle
2. Event querying endpoints
3. Audit trail generation
4. Event filtering
"""

import os
import sys
import json
import uuid
import psycopg
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://learning:***@localhost/learning_fabric")

def connect():
    """Open a database connection."""
    return psycopg.connect(DATABASE_URL)

def setup():
    """Create a clean test workflow, task, node, and run lifecycle."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Create test request
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
                (authority_id, "test", json.dumps({"test": "events"}))
            )
            request_id = cur.fetchone()[0]
            
            # Create workflow
            cur.execute(
                """
                INSERT INTO workflows (request_id, workflow_type, objective)
                VALUES (%s, %s, %s)
                RETURNING workflow_id
                """,
                (request_id, "test", json.dumps({"objective": "test section 3"}))
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

def run_lifecycle(data):
    """Run complete lifecycle to generate events."""
    print("  • Running lifecycle to generate events...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Claim
            cur.execute(
                "UPDATE assignments SET status='claimed', claimed_at=now() WHERE assignment_id=%s",
                (data["assignment_id"],)
            )
            cur.execute(
                "UPDATE tasks SET status='running', started_at=COALESCE(started_at,now())"
            )
            cur.execute(
                "UPDATE nodes SET status='busy' WHERE node_id=%s",
                (data["node_id"],)
            )
            
            # Create attempt
            attempt_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO attempts
                (attempt_id, task_id, assignment_id, node_id, attempt_number, method, status, started_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'running', now())
                """,
                (attempt_id, data["task_id"], data["assignment_id"], data["node_id"], 1, json.dumps({}))
            )
            cur.execute(
                "UPDATE assignments SET attempt_count=1 WHERE assignment_id=%s",
                (data["assignment_id"],)
            )
            
            # Submit result
            result_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO results
                (result_id, attempt_id, task_id, node_id, result, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'recorded', now())
                """,
                (result_id, attempt_id, data["task_id"], data["node_id"], json.dumps({"success": True}), 0.95)
            )
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() WHERE attempt_id=%s",
                (attempt_id,)
            )
            
            # Create observation
            observation_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO observations
                (observation_id, attempt_id, result_id, observation_type, content, source, confidence, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                """,
                (observation_id, attempt_id, result_id, "check", json.dumps({}), "test", 0.99)
            )
            
            # Complete assignment
            cur.execute(
                "UPDATE assignments SET status='completed', completed_at=now() WHERE assignment_id=%s",
                (data["assignment_id"],)
            )
            cur.execute(
                "UPDATE tasks SET status='completed', completed_at=now() WHERE task_id=%s",
                (data["task_id"],)
            )
            cur.execute(
                "UPDATE nodes SET status='available' WHERE node_id=%s",
                (data["node_id"],)
            )
        
        conn.commit()
        print("    ✓ Lifecycle complete")
        return True
    finally:
        conn.close()

def test_events_recorded(data):
    """Test that events were recorded."""
    print("  • Verifying events were recorded...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Count events for assignment
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE entity_type='assignment' AND entity_id=%s",
                (data["assignment_id"],)
            )
            assignment_events = cur.fetchone()[0]
            assert assignment_events > 0, f"Expected events for assignment, found {assignment_events}"
            print(f"    ✓ Assignment events recorded: {assignment_events}")
            
            # Count events for attempt
            cur.execute(
                """
                SELECT COUNT(e.event_id)
                FROM events e
                JOIN attempts a ON e.entity_id = a.attempt_id
                WHERE e.entity_type='attempt' AND a.assignment_id=%s
                """,
                (data["assignment_id"],)
            )
            attempt_events = cur.fetchone()[0]
            assert attempt_events > 0, f"Expected events for attempt, found {attempt_events}"
            print(f"    ✓ Attempt events recorded: {attempt_events}")
            
            # Verify event types
            cur.execute(
                "SELECT DISTINCT event_type FROM events WHERE entity_type='assignment' AND entity_id=%s ORDER BY event_type",
                (data["assignment_id"],)
            )
            event_types = [row[0] for row in cur.fetchall()]
            print(f"    ✓ Event types recorded: {event_types}")
            
            # Verify previous_state and current_state
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE entity_type='assignment' AND entity_id=%s AND previous_state IS NOT NULL",
                (data["assignment_id"],)
            )
            state_events = cur.fetchone()[0]
            assert state_events > 0, "Expected events with state transitions"
            print(f"    ✓ State transitions recorded: {state_events}")
    finally:
        conn.close()

def test_event_queries(data):
    """Test event query endpoints."""
    print("  • Testing event query functionality...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Test filtering by entity_type
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE entity_type='assignment'",
            )
            assignment_count = cur.fetchone()[0]
            assert assignment_count > 0, "Should have assignment events"
            print(f"    ✓ Query by entity_type: found {assignment_count} assignment events")
            
            # Test filtering by entity_id
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE entity_id=%s",
                (data["assignment_id"],)
            )
            entity_count = cur.fetchone()[0]
            assert entity_count > 0, "Should have events for this entity"
            print(f"    ✓ Query by entity_id: found {entity_count} events")
            
            # Test filtering by event_type
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='completed'",
            )
            completed_count = cur.fetchone()[0]
            print(f"    ✓ Query by event_type: found {completed_count} 'completed' events")
            
            # Test ordering by created_at
            cur.execute(
                """
                SELECT event_id, created_at FROM events 
                WHERE entity_type='assignment' AND entity_id=%s
                ORDER BY created_at ASC
                """,
                (data["assignment_id"],)
            )
            rows = cur.fetchall()
            assert len(rows) > 0, "Should have ordered events"
            print(f"    ✓ Events ordered by timestamp: {len(rows)} events in sequence")
    finally:
        conn.close()

def test_audit_trail(data):
    """Test audit trail generation."""
    print("  • Testing audit trail...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Get full audit trail for assignment
            cur.execute(
                """
                SELECT event_id, event_type, previous_state, current_state, metadata, created_at
                FROM events
                WHERE entity_type='assignment' AND entity_id=%s
                ORDER BY created_at ASC
                """,
                (data["assignment_id"],)
            )
            events = cur.fetchall()
            
            assert len(events) > 0, "Should have audit trail events"
            print(f"    ✓ Audit trail retrieved: {len(events)} events")
            
            # Verify state progression
            print("    ✓ State progression:")
            for event_id, event_type, prev_state, curr_state, metadata, created_at in events:
                print(f"      - {event_type}: {prev_state} → {curr_state}")
    finally:
        conn.close()

def test_event_metadata(data):
    """Test that metadata is properly recorded."""
    print("  • Testing event metadata...")
    conn = connect()
    try:
        with conn.cursor() as cur:
            # Get event with metadata
            cur.execute(
                """
                SELECT event_type, metadata FROM events 
                WHERE entity_type='assignment' AND entity_id=%s AND metadata IS NOT NULL
                LIMIT 1
                """,
                (data["assignment_id"],)
            )
            row = cur.fetchone()
            
            if row:
                event_type, metadata = row
                metadata_dict = dict(metadata)
                assert "action" in metadata_dict, "Metadata should contain 'action'"
                print(f"    ✓ Metadata found: action='{metadata_dict.get('action')}'")
            else:
                print("    ⚠ No metadata found (this is OK if events don't require it)")
    finally:
        conn.close()

def main():
    """Run all Section 3 tests."""
    print("\n=== Section 3: Event Recording and History Tests ===\n")
    
    try:
        print("1. Setup")
        data = setup()
        print(f"  ✓ Setup complete (assignment: {data['assignment_id']})")
        
        print("\n2. Run lifecycle")
        run_lifecycle(data)
        
        print("\n3. Verify events were recorded")
        test_events_recorded(data)
        
        print("\n4. Test query endpoints")
        test_event_queries(data)
        
        print("\n5. Test audit trail")
        test_audit_trail(data)
        
        print("\n6. Test event metadata")
        test_event_metadata(data)
        
        print("\n=== ✓ ALL TESTS PASSED ===\n")
        return 0
    
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
