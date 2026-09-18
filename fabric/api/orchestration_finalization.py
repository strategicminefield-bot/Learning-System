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
            # NOTE: Read assignment status from assignments table, NOT from attempts
            # attempts.status is stale and reflects the state when the attempt was created
            cur.execute("""
                SELECT r.result_id, r.attempt_id, a.attempt_id, a.task_id, a.node_id, a.assignment_id, 
                       aa.status as assignment_status
                FROM results r
                JOIN attempts a ON r.attempt_id = a.attempt_id
                JOIN assignments aa ON a.assignment_id = aa.assignment_id
                WHERE r.result_id = %s
            """, (result_uuid,))
            
            row = cur.fetchone()
            if not row:
                return {"status": "error", "detail": "result not found"}
            
            result_id_check, attempt_id_from_result, attempt_id_from_attempts, task_id, node_id, assignment_id, assignment_status = row
            
            print(f"DEBUG: Finalization: result={result_id_check}, attempt_result={attempt_id_from_result}, attempt_attempts={attempt_id_from_attempts}, assignment={assignment_id}, status={assignment_status}", flush=True)
            logger.warning(f"Finalization: result={result_id_check}, attempt_result={attempt_id_from_result}, attempt_attempts={attempt_id_from_attempts}, assignment={assignment_id}, status={assignment_status}")
            
            attempt_id = attempt_id_from_result
            
            # Check if assignment is claimed (normal state for completing)
            if assignment_status != "claimed":
                logger.error(f"Assignment state mismatch: expected 'claimed', got '{assignment_status}'")
                return {
                    "status": "error",
                    "phase": "completion",
                    "detail": f"assignment is {assignment_status}, cannot auto-complete",
                    "assignment_id": str(assignment_id),
                    "expected_state": "claimed"
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



def create_bounded_learning_from_outcome(outcome_id: str, task_id: str, result_id: str, verification_result: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
    """
    Create bounded learning from verified outcome with full provenance.
    Bounded state = not yet promoted to universal organisational truth.
    Governance can promote bounded→active based on accumulated evidence.
    """
    try:
        outcome_uuid = uuid.UUID(outcome_id)
        task_uuid = uuid.UUID(task_id)
        result_uuid = uuid.UUID(result_id)
    except ValueError as e:
        logger.error(f"Invalid UUID: {e}")
        return False, None, f"invalid uuid: {str(e)}"
    
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT task_type FROM tasks WHERE task_id=%s", (task_uuid,))
                task_row = cur.fetchone()
                if not task_row:
                    return False, None, "task not found"
                task_type = task_row[0]
                
                verification_status = verification_result.get('verification_status', 'unverified')
                evidence_category = verification_result.get('evidence_category', 'neutral')
                
                if verification_status == 'verified_success':
                    stmt = f"Verified: {task_type} method achieved objective"
                    basis = "verified_success"
                elif verification_status == 'verified_failure':
                    stmt = f"Verified: {task_type} method did not achieve objective"
                    basis = "verified_failure (contradictory)"
                else:
                    stmt = f"Observation: {task_type} insufficient evidence"
                    basis = verification_status
                
                learning_id = uuid.uuid4()
                cur.execute("""
                    INSERT INTO organisational_learning
                    (org_learning_id, source_task_type, task_type, content, promotion_confidence, current_state, evidence_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
                """, (
                    learning_id, task_type, task_type,
                    Jsonb({
                        "bounded": True,
                        "verification_status": verification_status,
                        "evidence_category": evidence_category,
                        "statement": stmt,
                        "outcome_id": str(outcome_uuid),
                        "task_id": str(task_uuid),
                        "result_id": str(result_uuid),
                        "provenance": {
                            "outcome_id": str(outcome_uuid),
                            "verification_status": verification_status,
                            "evidence_category": evidence_category
                        }
                    }),
                    0.5, 'bounded', 1
                ))
                conn.commit()
                logger.info(f"Bounded learning {learning_id} from outcome {outcome_id}")
                return True, str(learning_id), f"bounded ({basis})"
    except Exception as e:
        logger.error(f"Bounded learning error: {str(e)}", exc_info=True)
        return False, None, str(e)

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
                     evidence_summary, recorded_at)
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
            
            # CRITICAL SEPARATION: Objective success is NOT determined by quality_score or execution status
            # 
            # result_status == 'recorded' means: attempt was executed and result was saved
            # This does NOT mean: objective was achieved
            #
            # For outcome_status, we determine actual success from:
            # - task specification (acceptance criteria)
            # - observed result data
            # - required evidence
            # NOT from: result_status, quality_score, or node self-assessment
            #
            # Since task specs are currently empty/undefined, we cannot verify objective success.
            # Safest interpretation: result_status='recorded' = execution occurred, but outcome unverified
            # When domain adapters provide acceptance_criteria, this can be properly evaluated.
            #
            # For now:
            # - 'recorded' status + non-empty result = execution_completed (unverified)
            # - If future: criteria in task spec, outcome depends on criteria verification
            outcome_status = "execution_completed" if result_status == "recorded" else "execution_attempted"
            
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
            
            # CRITICAL SEPARATION: Learning confidence ≠ Objective success
            # 
            # success_value for worker_learning represents: experience and learning confidence
            # This should be based on:
            # - Whether the outcome is verified (has required evidence)
            # - Quality of that verification (evidence_strength)
            # - Consistency across repetitions
            #
            # NOT based on:
            # - Node's self-assessment (quality_score)
            # - Task execution status alone
            # - Generic proficiency thresholds
            #
            # For now: Track execution as experience (1.0) regardless of unverified outcome
            # When objective verification is added, use verified_outcome + evidence_strength
            success_value = 1.0  # Execution occurred - counts as learning experience
            
            # Note: outcome_status is now unverified, so it shouldn't affect learning confidence
            # Learning confidence should come from validation_evidence assessment instead
            
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
                # Update: increment experience counter and average metadata scores
                # 
                # CRITICAL: proficiency_score represents learning confidence from evidence,
                # NOT objective success rate or quality_score.
                # 
                # We track:
                # - tasks_completed: execution experience (not outcome success)
                # - success_rate: execution success (whether it ran without error)
                # - quality_score: node's self-assessment (metadata, for reference)
                # - proficiency_score: to be determined by validation_engine assessment
                #
                # Do NOT let quality_score determine proficiency_score.
                # Proficiency comes from validation of outcomes via evidence.
                #
                # For now, proficiency_score = 0.5 (neutral) until validation_engine assesses
                cur.execute("""
                    UPDATE worker_learning SET
                        tasks_completed = tasks_completed + 1,
                        success_rate = (COALESCE(success_rate, 0) * tasks_completed + %s) / (tasks_completed + 1),
                        quality_score = (COALESCE(quality_score, 0) * tasks_completed + %s) / (tasks_completed + 1),
                        proficiency_score = 0.5,
                        last_updated = now()
                    WHERE node_id=%s AND task_type=%s AND skill_area='general'
                """, (success_value, quality_score or 0.5, node_uuid, task_type))
            else:
                # Insert: first record for this node+task_type
                # proficiency_score starts at 0.5 (neutral) pending validation evidence
                cur.execute("""
                    INSERT INTO worker_learning
                    (learning_id, node_id, task_type, skill_area, proficiency_score,
                     tasks_completed, success_rate, quality_score, last_updated, created_at)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, now(), now())
                """, (uuid.uuid4(), node_uuid, task_type, "general", 0.5, success_value, quality_score or 0.5))
            
            conn.commit()
    
    return True, str(outcome_id_ret), "outcome_recorded_with_learning_update"


def propose_learning_promotion_via_evidence(learning_id: str, worker_node_id: str, 
                                           task_type: str) -> Tuple[bool, Optional[str], str]:
    """
    EVIDENCE-BASED PROMOTION PROPOSAL
    
    Creates validation candidate and evidence for worker learning to be considered for
    organisational knowledge promotion. Does NOT automatically promote.
    
    Promotion decision is made through governance_engine via validation_engine,
    respecting validation_rule_configs thresholds and approval requirements.
    
    Returns: (success, validation_candidate_id, message)
    """
    try:
        learning_uuid = uuid.UUID(learning_id)
        node_uuid = uuid.UUID(worker_node_id)
    except ValueError:
        return False, None, "invalid uuid format"
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get worker learning details
            cur.execute("""
                SELECT proficiency_score, tasks_completed, success_rate, quality_score
                FROM worker_learning
                WHERE learning_id=%s
            """, (learning_uuid,))
            
            learning_row = cur.fetchone()
            if not learning_row:
                return False, None, "learning not found"
            
            prof_score, tasks_completed, success_rate, quality_score = learning_row
            
            # Create validation candidate for this learning
            # This makes the learning evidence-eligible for promotion consideration
            candidate_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO validation_candidates
                (candidate_id, candidate_type, candidate_ref_id, candidate_ref_type,
                 candidate_name, current_status, source_operational_evidence, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            """, (
                candidate_id,
                "worker_learning",
                learning_uuid,
                "worker_learning",
                f"Worker learning promotion: {task_type} (node={str(node_uuid)[:8]}...)",
                "eligible",
                True
            ))
            
            # Create evidence record from aggregated learning
            # 
            # CRITICAL SEPARATION:
            # Execution success_rate does NOT determine objective evidence category.
            # Learning confidence comes from VERIFIED OBJECTIVE OUTCOMES, not execution.
            #
            # This evidence reflects LEARNING EXPERIENCE ROBUSTNESS:
            # - How many verified successes?
            # - How many verified failures?
            # - Independent confirmation?
            # - Aggregate evidence strength?
            #
            # NOT: execution_success_rate >= 0.9 = supportive
            # (that would conflate execution with objective success)
            
            evidence_id = uuid.uuid4()
            
            # Evidence category is NEUTRAL by default
            # It should only become SUPPORTIVE or CONTRADICTORY if we have
            # objective verification records from validation_evidence table.
            #
            # For now (without objective verification in task outcomes):
            # - This evidence reflects execution experience robustness
            # - NOT objective success/failure
            # - Marked as NEUTRAL to prevent false generalization
            
            evidence_category = "neutral"  # Conservative: execution ≠ objective success
            confidence = 0.5  # Neutral confidence for aggregated experience
            
            # Evidence strength reflects robustness of aggregate (experience base)
            # More tasks = more robust learning foundation
            # BUT: only if those tasks have verified objectives
            # For now: limited strength since objectives are unverified
            evidence_strength = min(float(tasks_completed) / 10.0, 1.0)  # normalize to 10 tasks
            
            cur.execute("""
                INSERT INTO validation_evidence
                (evidence_id, candidate_id, evidence_type, evidence_category,
                 confidence_score, evidence_strength, source_operational_outcome_id,
                 evidence_summary, evidence_detail, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            """, (
                evidence_id,
                candidate_id,
                "operational_aggregate",
                evidence_category,
                confidence,
                evidence_strength,
                learning_uuid,
                f"Worker learning aggregate for {task_type}: {tasks_completed} tasks (NEUTRAL - no objective verification available)",
                Jsonb({
                    "tasks_completed": int(tasks_completed),
                    "execution_success_rate": float(success_rate),
                    "quality_score_avg": float(quality_score) if quality_score else None,
                    "note": "CRITICAL: This evidence is NEUTRAL because it reflects EXECUTION consistency, NOT OBJECTIVE SUCCESS. Execution success_rate cannot determine objective evidence category. Supportive/contradictory evidence must come from VERIFIED OBJECTIVE OUTCOMES (objective_verification validation_evidence). Execution reliability is a separate learning concern.",
                    "evidence_basis": "execution_experience_only",
                    "objective_verification_required": "Objective outcomes must be verified separately via task acceptance_criteria"
                })
            ))
            
            conn.commit()
            logger.info(f"Created promotion proposal via evidence: candidate={str(candidate_id)[:8]}..., evidence_category={evidence_category}")
    
    return True, str(candidate_id), f"Promotion proposal created with evidence category={evidence_category}. Governance/validation will assess for actual promotion."


# NOTE: promote_learning_to_organisational() function removed.
# This function implemented naive 0.7 threshold promotion,
# bypassing validation_engine and governance framework.
#
# REPLACED BY: propose_learning_promotion_via_evidence()
# which creates evidence for governance to assess properly.
#
# Core principle: evidence → verification → decision → action
# NOT: quality_score >= 0.7 → automatic promotion


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
    
    # Step 4: Create bounded learning from verified outcome
    if success and outcome_id and verification_id:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT evidence_category FROM validation_evidence
                        WHERE candidate_id=%s ORDER BY created_at DESC LIMIT 1
                    """, (uuid.UUID(verification_id),))
                    ev_row = cur.fetchone()
                    
                    if ev_row and ev_row[0] == 'supportive':
                        v_status = 'verified_success'
                    elif ev_row and ev_row[0] == 'contradictory':
                        v_status = 'verified_failure'
                    else:
                        v_status = 'insufficient_evidence'
                    
                    verification_result = {
                        'verification_status': v_status,
                        'evidence_category': ev_row[0] if ev_row else 'neutral'
                    }
            
            success_bl, learning_id, note = create_bounded_learning_from_outcome(
                outcome_id, task_id, result_id, verification_result
            )
            result_info['bounded_learning'] = {
                'created': success_bl,
                'learning_id': learning_id,
                'note': note
            }
        except Exception as e:
            logger.error(f"Bounded learning error: {e}")
            result_info['bounded_learning'] = {'created': False, 'note': str(e)}
    else:
        result_info['bounded_learning'] = {'created': False, 'note': 'outcome incomplete'}
    
    # Step 5: Propose learning for governance assessment
    # Get the worker_learning record to propose for promotion
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Find recent worker_learning for this node and task
                cur.execute("""
                    SELECT task_type FROM tasks WHERE task_id=%s
                """, (uuid.UUID(task_id),))
                task_row = cur.fetchone()
                task_type = task_row[0] if task_row else None
                
                if task_type:
                    # Get the most recent learning for this task type and node
                    cur.execute("""
                        SELECT learning_id FROM worker_learning
                        WHERE node_id=%s AND task_type=%s
                        ORDER BY last_updated DESC
                        LIMIT 1
                    """, (uuid.UUID(node_id), task_type))
                    
                    learning_row = cur.fetchone()
                    if learning_row:
                        learning_id = learning_row[0]
                        success, proposal_candidate_id, note = propose_learning_promotion_via_evidence(
                            str(learning_id), node_id, task_type
                        )
                        result_info["learning_promotion_proposal"] = {
                            "proposed": success,
                            "proposal_candidate_id": proposal_candidate_id,
                            "note": note,
                            "governance_required": "Validation/governance engine must assess"
                        }
                    else:
                        result_info["learning_promotion_proposal"] = {
                            "proposed": False,
                            "note": "No worker_learning found for this task type"
                        }
                else:
                    result_info["learning_promotion_proposal"] = {
                        "proposed": False,
                        "note": "Task type not found"
                    }
    except Exception as e:
        logger.error(f"Learning promotion proposal failed: {str(e)}")
        result_info["learning_promotion_proposal"] = {
            "proposed": False,
            "note": f"Exception: {str(e)}"
        }
    
    return {
        "status": "finalized",
        "result_id": result_id,
        "pipeline": result_info,
        "errors": errors if errors else None,
        "complete": len(errors) == 0
    }
