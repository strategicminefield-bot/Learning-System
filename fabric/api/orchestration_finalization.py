"""
Orchestration Finalization Service

Completes the learning loop between result submission and reusable organisational memory.

Responsible for:
1. Result → Completion (auto-complete assignment/task)
2. Completion → Verification (create validation candidates)
3. Verification → Outcome (record task outcome)
4. Outcome → Learning (extract worker learning)
5. Learning → Knowledge (promote to organisational memory)

This service bridges the gap between real node execution and organisational memory/knowledge.
It remains platform-independent and reuses all existing Fabric mechanisms.
"""

import os
import uuid
import json
import psycopg
from psycopg.types.json import Jsonb
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)
DATABASE_URL = os.environ["DATABASE_URL"]


def finalize_result_completion(result_id: str) -> Dict[str, Any]:
    """
    Finalize a completed result by:
    1. Completing the assignment
    2. Completing the task
    3. Returning node to available
    
    Called after result is successfully submitted and recorded.
    
    Returns: { status, assignment_id, task_id, node_id, errors }
    """
    try:
        result_uuid = uuid.UUID(result_id)
    except ValueError:
        return {"status": "error", "detail": "invalid result_id"}
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get result with attempt info
            cur.execute("""
                SELECT r.attempt_id, a.task_id, a.node_id, a.assignment_id, a.status as assignment_status
                FROM results r
                JOIN attempts a ON r.attempt_id = a.attempt_id
                WHERE r.result_id = %s
            """, (result_uuid,))
            
            row = cur.fetchone()
            if not row:
                return {"status": "error", "detail": "result not found"}
            
            attempt_id, task_id, node_id, assignment_id, assignment_status = row
            
            # Check if assignment is claimed (normal state for completing)
            if assignment_status != "claimed":
                return {
                    "status": "error",
                    "detail": f"assignment is {assignment_status}, cannot auto-complete",
                    "assignment_id": str(assignment_id)
                }
            
            # Complete assignment
            cur.execute("""
                UPDATE assignments 
                SET status='completed', completed_at=now()
                WHERE assignment_id=%s
            """, (assignment_id,))
            
            # Complete task
            cur.execute("""
                UPDATE tasks
                SET status='completed', completed_at=now()
                WHERE task_id=%s
            """, (task_id,))
            
            # Return node to available
            cur.execute("""
                UPDATE nodes
                SET status='available'
                WHERE node_id=%s
            """, (node_id,))
            
            # Record events
            cur.execute("""
                INSERT INTO audit_events
                (event_type, entity_type, entity_id, node_id, previous_state, current_state, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            """, (
                "completed",
                "assignment",
                assignment_id,
                node_id,
                Jsonb({"status": "claimed"}),
                Jsonb({"status": "completed"}),
                Jsonb({"action": "auto_completed_after_result", "result_id": str(result_uuid)})
            ))
            
            conn.commit()
    
    return {
        "status": "completed",
        "result_id": str(result_uuid),
        "assignment_id": str(assignment_id),
        "task_id": str(task_id),
        "node_id": str(node_id)
    }


def create_verification_from_result(result_id: str, task_id: str) -> Tuple[bool, Optional[str], str]:
    """
    Create validation candidate from result for verification.
    
    Returns: (success, validation_candidate_id, error_or_note)
    """
    try:
        result_uuid = uuid.UUID(result_id)
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return False, None, "invalid uuid format"
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get task info
            cur.execute("""
                SELECT task_type, specification
                FROM tasks
                WHERE task_id = %s
            """, (task_uuid,))
            
            task_row = cur.fetchone()
            if not task_row:
                return False, None, "task not found"
            
            task_type, specification = task_row
            
            # Create validation candidate for this result
            candidate_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type, 
                 candidate_name, current_status, source_operational_evidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                RETURNING candidate_id
            """, (
                candidate_id,
                "operational_result",
                result_uuid,
                "result",
                f"Result verification for task {task_type}",
                "eligible",
                True
            ))
            
            candidate_id_ret = cur.fetchone()[0]
            
            # Create evidence record from result quality
            cur.execute("""
                SELECT quality_score, result
                FROM results
                WHERE result_id = %s
            """, (result_uuid,))
            
            result_row = cur.fetchone()
            if result_row:
                quality_score, result_data = result_row
                
                # Record as evidence
                evidence_id = uuid.uuid4()
                cur.execute("""
                    INSERT INTO validation_evidence
                    (evidence_id, candidate_id, evidence_type, evidence_category,
                     confidence_score, evidence_strength, source_operational_outcome_id,
                     evidence_summary, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                """, (
                    evidence_id,
                    candidate_id_ret,
                    "operational_result",
                    "execution_result",
                    quality_score if quality_score else 0.5,
                    quality_score if quality_score else 0.5,
                    None,
                    f"Result from task execution with quality_score={quality_score}"
                ))
            
            conn.commit()
    
    return True, str(candidate_id_ret), "validation_candidate_created"


def record_outcome_from_result(result_id: str, assignment_id: str, task_id: str, 
                                node_id: str, verification_id: Optional[str] = None) -> Tuple[bool, Optional[str], str]:
    """
    Record task outcome from result.
    
    Returns: (success, outcome_id, error_or_note)
    """
    try:
        result_uuid = uuid.UUID(result_id)
        task_uuid = uuid.UUID(task_id)
        node_uuid = uuid.UUID(node_id)
        assignment_uuid = uuid.UUID(assignment_id) if assignment_id else None
    except ValueError:
        return False, None, "invalid uuid format"
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get result details
            cur.execute("""
                SELECT quality_score, result, status
                FROM results
                WHERE result_id = %s
            """, (result_uuid,))
            
            result_row = cur.fetchone()
            if not result_row:
                return False, None, "result not found"
            
            quality_score, result_data, result_status = result_row
            
            # Determine outcome status based on result status
            # 'recorded' = successful execution, convert to 'success'
            outcome_status = "success" if result_status == "recorded" else "completed"
            
            # Create task outcome
            outcome_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO task_outcomes
                (outcome_id, task_id, assignment_id, node_id, outcome_status,
                 quality_score, execution_time_seconds, result_summary, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING outcome_id
            """, (
                outcome_id,
                task_uuid,
                assignment_uuid,
                node_uuid,
                outcome_status,
                quality_score,
                None,
                Jsonb(result_data if isinstance(result_data, dict) else {})
            ))
            
            outcome_id_ret = cur.fetchone()[0]
            
            # Update worker learning based on outcome
            success_value = 1.0 if outcome_status == "success" else 0.0
            
            # Get task type
            cur.execute("SELECT task_type FROM tasks WHERE task_id=%s", (task_uuid,))
            task_type_row = cur.fetchone()
            task_type = task_type_row[0] if task_type_row else "unknown"
            
            # Check if learning profile exists
            cur.execute("""
                SELECT learning_id FROM worker_learning
                WHERE node_id=%s AND task_type=%s AND skill_area='general'
            """, (node_uuid, task_type))
            
            existing = cur.fetchone()
            
            if existing:
                # Update: use incremental averages
                cur.execute("""
                    UPDATE worker_learning SET
                        tasks_completed = tasks_completed + 1,
                        success_rate = (COALESCE(success_rate, 0) * tasks_completed + %s) / (tasks_completed + 1),
                        quality_score = (COALESCE(quality_score, 0) * tasks_completed + %s) / (tasks_completed + 1),
                        proficiency_score = %s,
                        last_updated = now()
                    WHERE node_id=%s AND task_type=%s AND skill_area='general'
                """, (success_value, quality_score or 0.5, quality_score or 0.5, node_uuid, task_type))
            else:
                # Insert: first record
                cur.execute("""
                    INSERT INTO worker_learning
                    (learning_id, node_id, task_type, skill_area, proficiency_score,
                     tasks_completed, success_rate, quality_score, last_updated, created_at)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, now(), now())
                """, (uuid.uuid4(), node_uuid, task_type, "general", quality_score or 0.5, success_value, quality_score or 0.5))
            
            conn.commit()
    
    return True, str(outcome_id_ret), "outcome_recorded_with_learning_update"


def promote_learning_to_organisational(node_id: str, task_type: Optional[str] = None,
                                       min_proficiency: float = 0.7) -> Tuple[bool, int, str]:
    """
    Promote high-confidence worker learning to organisational memory.
    
    Returns: (success, count_promoted, message)
    """
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        return False, 0, "invalid node_id"
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Find high-confidence learning
            query_params = [node_uuid, min_proficiency]
            where_clause = "WHERE node_id=%s AND proficiency_score >= %s AND tasks_completed >= 2"
            
            if task_type:
                where_clause += " AND task_type=%s"
                query_params.append(task_type)
            
            cur.execute(f"""
                SELECT learning_id, task_type, proficiency_score, success_rate, quality_score
                FROM worker_learning
                {where_clause}
            """, query_params)
            
            learnings = cur.fetchall()
            count = 0
            
            for learning_id, task_t, prof_score, success_rate, quality_score in learnings:
                # Check if already promoted
                cur.execute("""
                    SELECT org_learning_id FROM organisational_learning
                    WHERE source_learning_id=%s
                """, (learning_id,))
                
                if cur.fetchone():
                    continue  # Already promoted
                
                # Create organisational learning
                org_id = uuid.uuid4()
                cur.execute("""
                    INSERT INTO organisational_learning
                    (org_learning_id, source_learning_id, source_type, source_node_id,
                     source_task_type, task_type, content, promotion_confidence,
                     current_state, evidence_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                """, (
                    org_id,
                    learning_id,
                    "worker_learning",
                    node_uuid,
                    task_t,
                    task_t,
                    Jsonb({
                        "source_node_id": str(node_uuid),
                        "proficiency_score": float(prof_score),
                        "success_rate": float(success_rate),
                        "quality_score": float(quality_score),
                        "promoted_at": datetime.now(timezone.utc).isoformat()
                    }),
                    min(float(prof_score), 0.95),  # cap at 0.95
                    "organisational",
                    1
                ))
                
                count += 1
            
            conn.commit()
    
    return True, count, f"promoted {count} learning items to organisational memory"


def auto_finalize_result(result_id: str) -> Dict[str, Any]:
    """
    Automatically finalize a result by running the complete pipeline:
    1. Complete assignment/task
    2. Create verification
    3. Record outcome
    4. Promote learning if warranted
    
    This is the main entry point for orchestration finalization.
    Called after POST /attempts/{attempt_id}/result succeeds.
    
    Returns: { status, details }
    """
    result_info = {}
    errors = []
    
    # Step 1: Complete assignment/task
    completion_result = finalize_result_completion(result_id)
    if completion_result.get("status") != "completed":
        return {
            "status": "error",
            "phase": "completion",
            "detail": completion_result.get("detail", "unknown error")
        }
    
    result_info["completion"] = completion_result
    assignment_id = completion_result.get("assignment_id")
    task_id = completion_result.get("task_id")
    node_id = completion_result.get("node_id")
    
    # Step 2: Create verification
    success, verification_id, note = create_verification_from_result(result_id, task_id)
    result_info["verification"] = {
        "created": success,
        "candidate_id": verification_id,
        "note": note
    }
    if not success:
        errors.append(f"verification creation failed: {note}")
    
    # Step 3: Record outcome
    success, outcome_id, note = record_outcome_from_result(
        result_id, assignment_id, task_id, node_id, verification_id
    )
    result_info["outcome"] = {
        "created": success,
        "outcome_id": outcome_id,
        "note": note
    }
    if not success:
        errors.append(f"outcome recording failed: {note}")
    
    # Step 4: Promote learning if high-confidence
    success, promoted_count, note = promote_learning_to_organisational(node_id)
    result_info["learning_promotion"] = {
        "attempted": True,
        "promoted_count": promoted_count,
        "note": note
    }
    
    return {
        "status": "finalized",
        "result_id": result_id,
        "pipeline": result_info,
        "errors": errors if errors else None,
        "complete": len(errors) == 0
    }
