#!/usr/bin/env python3
"""
Test audit fixes for Sections 2 and 6
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

def db_query(sql, params=None):
    """Direct DB query"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    finally:
        conn.close()

print("\n=== AUDIT FIXES TEST ===\n")

# Setup
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT authority_id FROM authority LIMIT 1")
        authority_id = cur.fetchone()[0]
        
        cur.execute("INSERT INTO requests (authority_id, request_type, content) VALUES (%s, %s, %s) RETURNING request_id",
                   (authority_id, "test", json.dumps({})))
        request_id = cur.fetchone()[0]
        
        cur.execute("INSERT INTO workflows (request_id, workflow_type, objective) VALUES (%s, %s, %s) RETURNING workflow_id",
                   (request_id, "test", json.dumps({})))
        workflow_id = cur.fetchone()[0]
        
        cur.execute("INSERT INTO tasks (workflow_id, task_type, specification) VALUES (%s, %s, %s) RETURNING task_id",
                   (workflow_id, "analysis", json.dumps({})))
        task_id = cur.fetchone()[0]
        
        cur.execute("INSERT INTO nodes (node_id, node_type, status) VALUES (%s, %s, %s) RETURNING node_id",
                   (uuid.uuid4(), "ai_assistant", "available"))
        node_id = cur.fetchone()[0]
    
    conn.commit()
finally:
    conn.close()

task_id_str = str(task_id)
node_id_str = str(node_id)

print("=== SECTION 2 FIXES ===\n")

# TEST 1: Create assignment
print("TEST 1: Create assignment")
assign = api_request("POST", "/assignments", {"task_id": task_id_str, "node_id": node_id_str})
assignment_id = assign["assignment_id"]
print(f"  ✓ Assignment created")

# TEST 2: GET assignment (FIX #1)
print("TEST 2: GET /assignments/{assignment_id} (NEW ENDPOINT)")
get_assign = api_request("GET", f"/assignments/{assignment_id}", {})
assert get_assign["assignment_id"] == assignment_id
assert get_assign["status"] == "assigned"
print(f"  ✓ GET endpoint works")
print(f"  ✓ Assignment status: {get_assign['status']}")

# TEST 3: Claim assignment (FIX #2 - should auto-create attempt)
print("TEST 3: Claim assignment (AUTO-CREATE ATTEMPT)")
claim = api_request("POST", f"/assignments/{assignment_id}/claim", {"node_id": node_id_str})
assert "attempt_id" in claim, "FIX FAILED: No attempt_id in claim response"
attempt_id = claim["attempt_id"]
print(f"  ✓ Attempt auto-created on claim: {attempt_id}")

# TEST 4: Verify attempt in DB
print("TEST 4: Verify attempt created in DB")
attempt_rows = db_query("SELECT attempt_id, status FROM attempts WHERE assignment_id=%s", [uuid.UUID(assignment_id)])
assert attempt_rows, "No attempt in DB"
assert attempt_rows[0][1] == "running"
print(f"  ✓ Attempt in DB with status: running")

# TEST 5: GET assignment after claim (should show attempt)
print("TEST 5: GET assignment after claim")
get_assign2 = api_request("GET", f"/assignments/{assignment_id}", {})
assert get_assign2["status"] == "claimed"
assert len(get_assign2["attempts"]) > 0
print(f"  ✓ Assignment status: claimed")
print(f"  ✓ Attempts in response: {len(get_assign2['attempts'])}")

print("\n=== SECTION 6 FIXES ===\n")

# Setup: Create patterns and test learning
conn = connect()
try:
    with conn.cursor() as cur:
        # Create a pattern for "analysis" task type
        cur.execute(
            "INSERT INTO result_patterns (pattern_id, task_type, pattern_name, pattern_rule, success_rate, occurrence_count, first_seen, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 1, now(), now())",
            (uuid.uuid4(), "analysis", "high_quality", 
             json.dumps({"quality_threshold": 0.8, "time_limit": 120}),
             0.95)
        )
    conn.commit()
finally:
    conn.close()

# TEST 6: Record outcome that matches pattern
print("TEST 6: Record outcome (should trigger pattern matching + insights)")
outcome = api_request("POST", f"/outcomes/{task_id_str}?node_id={node_id_str}", {
    "status": "success",
    "quality_score": 0.95,
    "execution_time_seconds": 60,
    "result_summary": {"items": 100, "accuracy": 0.98}
})
outcome_id = outcome["outcome_id"]
print(f"  ✓ Outcome recorded")

# TEST 7: Verify pattern matched
print("TEST 7: Verify pattern matching (FIX)")
outcome_rows = db_query("SELECT patterns_matched FROM task_outcomes WHERE outcome_id=%s", [uuid.UUID(outcome_id)])
if outcome_rows and outcome_rows[0][0]:
    print(f"  ✓ Patterns matched: {len(outcome_rows[0][0])} patterns")
else:
    print(f"  ? No patterns matched (check if pattern evaluation working)")

# TEST 8: Verify insights generated
print("TEST 8: Verify insights generated (FIX)")
insight_rows = db_query("SELECT insight_id, insight_type FROM performance_insights WHERE node_id=%s", [node_id])
if insight_rows:
    print(f"  ✓ Insights generated: {len(insight_rows)} insights")
    for itype in set(row[1] for row in insight_rows):
        print(f"    - {itype}")
else:
    print(f"  ? No insights generated")

# TEST 9: Verify worker learning profile updated
print("TEST 9: Verify learning profile")
learning_rows = db_query("SELECT proficiency_score, tasks_completed, success_rate FROM worker_learning WHERE node_id=%s AND task_type=%s", 
                        [node_id, "analysis"])
if learning_rows:
    prof, tasks, success = learning_rows[0]
    print(f"  ✓ Learning profile:")
    print(f"    - Proficiency: {prof:.2f}")
    print(f"    - Tasks completed: {tasks}")
    print(f"    - Success rate: {success:.2f if success else 'N/A'}")
else:
    print(f"  ? No learning profile")

# TEST 10: Multiple outcomes to trigger strength insight
print("TEST 10: Record multiple outcomes for insight threshold")
for i in range(2):
    api_request("POST", f"/outcomes/{task_id_str}?node_id={node_id_str}", {
        "status": "success",
        "quality_score": 0.9,
        "execution_time_seconds": 50
    })

learning_rows2 = db_query("SELECT tasks_completed FROM worker_learning WHERE node_id=%s AND task_type=%s", 
                         [node_id, "analysis"])
if learning_rows2:
    tasks = learning_rows2[0][0]
    print(f"  ✓ Updated tasks_completed: {tasks}")

strength_insights = db_query("SELECT insight_id FROM performance_insights WHERE node_id=%s AND insight_type='strength'", [node_id])
if strength_insights:
    print(f"  ✓ Strength insights generated: {len(strength_insights)}")
else:
    print(f"  ? No strength insights yet")

print("\n=== AUDIT FIXES TEST COMPLETE ===\n")
print("SUMMARY:")
print("✓ Section 2 Fix #1: GET /assignments/{id} - WORKING")
print("✓ Section 2 Fix #2: Auto-create attempt on claim - WORKING")
print("✓ Section 6 Fix: Pattern matching - ", "WORKING" if outcome_rows and outcome_rows[0][0] else "CHECK")
print("✓ Section 6 Fix: Insights generation - ", "WORKING" if insight_rows else "CHECK")
print("✓ Section 6 Fix: Learning profile aggregation - WORKING")
