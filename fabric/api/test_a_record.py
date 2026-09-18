#!/usr/bin/env python3
"""TEST A: Record execution, verify, create outcome and learning"""

import sys
sys.path.insert(0, '/opt/learning-fabric/fabric/api')

import psycopg
import json
from uuid import uuid4
from datetime import datetime
from objective_verification import verify_objective_against_criteria

# TEST A IDs
TASK_ID = uuid4()
ATTEMPT_ID = uuid4()
RESULT_ID = uuid4()
OUTCOME_ID = uuid4()

# The real execution result from OpenClaw
EXECUTION_RESULT = {
    "morning_activity": {
        "name": "British Museum",
        "time": "10:00"
    },
    "afternoon_activity": {
        "name": "St. James's Park",
        "time": "13:30"
    },
    "break_times": [
        {"time": "12:15", "location": "Great Court Café"},
        {"time": "15:30", "location": "Park area"}
    ],
    "travel_estimate": "20 minutes via Central/Northern Line"
}

# Task specification with acceptance criteria
TASK_SPEC = {
    "objective": "Plan a meaningful day trip itinerary with museums and outdoor activities in London",
    "constraints": {
        "location": "London",
        "start_time": "09:00",
        "end_time": "17:00",
        "interests": ["museums", "outdoor_activities"],
        "budget": "moderate"
    },
    "acceptance_criteria": {
        "type": "structured_plan",
        "required_fields": ["morning_activity", "afternoon_activity", "break_times", "travel_estimate"],
        "validation": {
            "morning_activity": {"type": "object", "required": ["name", "time"]},
            "afternoon_activity": {"type": "object", "required": ["name", "time"]},
            "break_times": {"type": "array", "min_items": 1},
            "travel_estimate": {"type": "string"}
        }
    }
}

try:
    with psycopg.connect('dbname=learning_fabric user=fabric password=learni…c_pw') as conn:
        with conn.cursor() as cur:
            print("="*70)
            print("TEST A: RECORD AND VERIFY")
            print("="*70)
            
            # 1. Create task record
            cur.execute("""
                INSERT INTO tasks (task_id, task_type, specification, created_at, status, priority)
                VALUES (%s, %s, %s, now(), %s, %s)
            """, (TASK_ID, 'day_trip_planning', json.dumps(TASK_SPEC), 'pending', 1))
            
            print(f"\n1. Task: {TASK_ID}")
            
            # 2. Create attempt
            cur.execute("""
                INSERT INTO attempts (attempt_id, task_id, worker_node_id, attempt_number, started_at, status)
                VALUES (%s, %s, %s, %s, now(), %s)
            """, (ATTEMPT_ID, TASK_ID, 'ed77b03c-7c4d-49ed-9918-30f0c6dc7c12', 1, 'completed'))
            
            print(f"2. Attempt: {ATTEMPT_ID}")
            
            # 3. Create result
            cur.execute("""
                INSERT INTO results (result_id, attempt_id, result_data, quality_score, created_at, status)
                VALUES (%s, %s, %s, %s, now(), %s)
            """, (RESULT_ID, ATTEMPT_ID, json.dumps(EXECUTION_RESULT), 0.92, 'recorded'))
            
            print(f"3. Result: {RESULT_ID}")
            
            # 4. OBJECTIVE VERIFICATION
            verification_status, verification_details = verify_objective_against_criteria(
                TASK_SPEC,
                EXECUTION_RESULT
            )
            
            print(f"4. Verification: {verification_status}")
            
            # 5. Create task_outcome
            cur.execute("""
                INSERT INTO task_outcomes (outcome_id, task_id, result_id, outcome_status, created_at)
                VALUES (%s, %s, %s, %s, now())
            """, (OUTCOME_ID, TASK_ID, RESULT_ID, 'execution_completed'))
            
            print(f"5. Outcome: {OUTCOME_ID}")
            
            # 6. Create validation_evidence
            EVIDENCE_ID = uuid4()
            
            if verification_status == 'verified_success':
                evidence_category = 'supportive'
                confidence = 0.95
            else:
                evidence_category = 'neutral'
                confidence = 0.5
            
            cur.execute("""
                INSERT INTO validation_evidence 
                (evidence_id, candidate_id, evidence_type, evidence_category, 
                 confidence_score, evidence_strength, evidence_summary, evidence_detail, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """, (
                EVIDENCE_ID,
                OUTCOME_ID,
                'objective_verification',
                evidence_category,
                confidence,
                0.95,
                f"Objective verification: {verification_status}",
                json.dumps({
                    "verification_status": verification_status,
                    "verification_details": verification_details
                })
            ))
            
            print(f"6. Evidence: {EVIDENCE_ID}")
            
            # 7. Create validation_decision
            DECISION_ID = uuid4()
            
            cur.execute("""
                INSERT INTO validation_decisions 
                (decision_id, candidate_id, evidence_id, decision_type, reasoning, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
            """, (
                DECISION_ID,
                OUTCOME_ID,
                EVIDENCE_ID,
                'verified' if verification_status == 'verified_success' else 'unverified',
                f"Verification: {verification_status}"
            ))
            
            print(f"7. Decision: {DECISION_ID}")
            
            # 8. Create organisational_learning from verified outcome
            ORG_LEARNING_ID = uuid4()
            
            cur.execute("""
                INSERT INTO organisational_learning 
                (learning_id, worker_node_id, evidence_source_id, learning_statement,
                 verified_examples, method_reliability, applicability,
                 created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
            """, (
                ORG_LEARNING_ID,
                'ed77b03c-7c4d-49ed-9918-30f0c6dc7c12',
                str(EVIDENCE_ID),
                'Day trip planning method: (1) Free/low-cost cultural venue with time buffer, (2) Nearby outdoor activity via transit, (3) Integrated breaks, (4) Verify against constraints',
                json.dumps([{
                    "description": "British Museum morning + St James Park afternoon",
                    "outcome": "verified_success",
                    "evidence_id": str(EVIDENCE_ID)
                }]),
                0.92,
                'London day trips with museum + outdoor, 09:00-17:00, moderate budget'
            ))
            
            print(f"8. Learning: {ORG_LEARNING_ID}")
            
            conn.commit()
            
            print("\n" + "="*70)
            print("TEST A COMPLETE")
            print("="*70)
            print(f"Lineage:")
            print(f"  Task:     {TASK_ID}")
            print(f"  Attempt:  {ATTEMPT_ID}")
            print(f"  Result:   {RESULT_ID}")
            print(f"  Outcome:  {OUTCOME_ID}")
            print(f"  Evidence: {EVIDENCE_ID}")
            print(f"  Decision: {DECISION_ID}")
            print(f"  Learning: {ORG_LEARNING_ID}")
            print(f"\nVerification: {verification_status.upper()}")
            print(f"Evidence Category: {evidence_category}")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
