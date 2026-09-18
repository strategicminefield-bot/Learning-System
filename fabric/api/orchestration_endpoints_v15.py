"""
Section 15: Adaptive Orchestration - API Endpoints
Exposes orchestration decision-making, candidate generation, planning, and feedback.
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import json
from datetime import datetime
import logging

from adaptive_orchestration import AdaptiveOrchestrationEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration-v15"])


# ===== Request/Response Models =====

class OrchestrationRequest(BaseModel):
    task_id: UUID
    context: Optional[Dict[str, Any]] = None
    node_id: Optional[UUID] = None
    explicit_constraints: Optional[Dict[str, Any]] = None
    force_replan_from: Optional[UUID] = None


class OrchestrationResponse(BaseModel):
    decision_id: str
    strategy_selected: Optional[str]
    worker_selected: Optional[str]
    execution_plan: Dict
    confidence: float
    evidence_sufficiency: str
    rationale: Dict
    assignment_id: Optional[str]
    plan_id: str
    candidates_considered: Dict


class DecisionQueryResponse(BaseModel):
    decision_id: str
    task_id: str
    strategy_selected: Optional[str]
    worker_selected: Optional[str]
    confidence: float
    rationale: Dict
    candidates_evaluated: int
    created_at: str


class ReplanRequest(BaseModel):
    original_decision_id: UUID
    trigger_type: str  # failed_attempt, worker_unavailable, strategy_invalidated, constraint_conflict
    trigger_reason: str
    attempt_number: Optional[int] = 1


class OutcomeRecordingRequest(BaseModel):
    decision_id: UUID
    assignment_id: UUID
    task_id: UUID
    outcome_status: str  # success, failure, partial
    outcome_id: Optional[UUID] = None
    attempts_required: int = 1
    quality_score: Optional[float] = None
    strategy_performed_as_expected: Optional[bool] = None
    worker_capable: Optional[bool] = None
    plan_accurate: Optional[bool] = None


# ===== Endpoints =====

@router.post("/decide", response_model=OrchestrationResponse)
def create_orchestration_decision(
    request: OrchestrationRequest,
    db_conn
):
    """
    Main orchestration entry point.
    
    Given a task, retrieve relevant learning and evidence, generate and evaluate candidates,
    select best strategy and worker, generate execution plan, and create assignment if applicable.
    
    Returns complete orchestration decision with rationale, evidence, and assigned worker/plan.
    """
    try:
        engine = AdaptiveOrchestrationEngine(db_conn)
        
        result = engine.orchestrate_task(
            task_id=request.task_id,
            context=request.context or {},
            node_id=request.node_id,
            explicit_constraints=request.explicit_constraints,
            force_replan_from=request.force_replan_from
        )
        
        return OrchestrationResponse(**result)
    
    except Exception as e:
        logger.error(f"Orchestration error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}", response_model=DecisionQueryResponse)
def get_orchestration_decision(
    decision_id: UUID,
    db_conn
):
    """
    Retrieve an orchestration decision with full details.
    
    Returns: decision metadata, strategy/worker selection, rationale, evidence evaluation.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT od.decision_id, od.task_id, od.strategy_selected, od.worker_selected,
                      od.confidence_score, od.decision_rationale,
                      (SELECT COUNT(*) FROM orchestration_candidates WHERE decision_id = %s),
                      od.created_at
               FROM orchestration_decisions od
               WHERE od.decision_id = %s""",
            (decision_id, decision_id)
        )
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
        
        return DecisionQueryResponse(
            decision_id=str(row[0]),
            task_id=str(row[1]),
            strategy_selected=str(row[2]) if row[2] else None,
            worker_selected=str(row[3]) if row[3] else None,
            confidence=float(row[4]),
            rationale=row[5] or {},
            candidates_evaluated=int(row[6]) if row[6] else 0,
            created_at=row[7].isoformat() if row[7] else ""
        )
    
    except Exception as e:
        logger.error(f"Error retrieving decision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/task/{task_id}")
def list_orchestration_decisions_for_task(
    task_id: UUID,
    include_replanning: bool = Query(True),
    limit: int = Query(100, le=1000),
    db_conn=None
):
    """
    List all orchestration decisions for a task.
    
    If include_replanning=true, returns full decision chains including replan history.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT od.decision_id, od.strategy_selected, od.worker_selected,
                      od.confidence_score, od.final_outcome_status, od.created_at,
                      od.replanned_from, od.replanned_to
               FROM orchestration_decisions od
               WHERE od.task_id = %s
               ORDER BY od.created_at DESC
               LIMIT %s""",
            (task_id, limit)
        )
        
        decisions = []
        for row in cursor.fetchall():
            decisions.append({
                "decision_id": str(row[0]),
                "strategy_selected": str(row[1]) if row[1] else None,
                "worker_selected": str(row[2]) if row[2] else None,
                "confidence": float(row[3]),
                "final_outcome": row[4],
                "created_at": row[5].isoformat(),
                "replanned_from": str(row[6]) if row[6] else None,
                "replanned_to": str(row[7]) if row[7] else None
            })
        
        return {
            "task_id": str(task_id),
            "decisions": decisions,
            "count": len(decisions)
        }
    
    except Exception as e:
        logger.error(f"Error listing decisions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}/candidates")
def get_decision_candidates(
    decision_id: UUID,
    limit: int = Query(10, le=50),
    db_conn=None
):
    """
    Retrieve candidates evaluated for a decision.
    
    Shows strategy candidates, worker candidates, ranking scores, and rejection reasons.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT candidate_id, candidate_type, strategy_id, node_id,
                      selection_score, rejection_reason, included_in_ranking, candidate_rank
               FROM orchestration_candidates
               WHERE decision_id = %s
               ORDER BY candidate_rank ASC NULLS LAST
               LIMIT %s""",
            (decision_id, limit)
        )
        
        candidates = []
        for row in cursor.fetchall():
            candidates.append({
                "candidate_id": str(row[0]),
                "candidate_type": row[1],
                "strategy_id": str(row[2]) if row[2] else None,
                "node_id": str(row[3]) if row[3] else None,
                "selection_score": float(row[4]) if row[4] else 0.0,
                "rejection_reason": row[5],
                "included_in_ranking": row[6],
                "rank": row[7]
            })
        
        return {
            "decision_id": str(decision_id),
            "candidates": candidates,
            "count": len(candidates)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving candidates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}/evidence")
def get_decision_evidence_evaluation(
    decision_id: UUID,
    db_conn=None
):
    """
    Retrieve evidence evaluation for all candidates in a decision.
    
    Shows what evidence supported/rejected each candidate and why.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT evidence_dimension, evidence_items, dimension_score,
                      supporting_evidence, rejecting_evidence, conflicting_evidence
               FROM orchestration_evidence_evaluation
               WHERE decision_id = %s
               ORDER BY evaluation_order ASC""",
            (decision_id,)
        )
        
        evaluations = []
        for row in cursor.fetchall():
            evaluations.append({
                "dimension": row[0],
                "evidence_items": row[1] or [],
                "dimension_score": float(row[2]) if row[2] else 0.0,
                "supporting_evidence": row[3] or [],
                "rejecting_evidence": row[4] or [],
                "conflicting_evidence": row[5] or []
            })
        
        return {
            "decision_id": str(decision_id),
            "evidence_evaluations": evaluations,
            "count": len(evaluations)
        }
    
    except Exception as e:
        logger.error(f"Error retrieving evidence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans/{plan_id}")
def get_execution_plan(
    plan_id: UUID,
    db_conn=None
):
    """
    Retrieve structured execution plan.
    
    Returns: Ordered steps, constraints, expected verification, context guidance, fallback.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT decision_id, strategy_id, strategy_version_id,
                      ordered_steps, context_guidance, constraints,
                      expected_verification, fallback_path
               FROM orchestration_plans
               WHERE plan_id = %s""",
            (plan_id,)
        )
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
        
        return {
            "plan_id": str(plan_id),
            "decision_id": str(row[0]),
            "strategy_id": str(row[1]) if row[1] else None,
            "strategy_version_id": str(row[2]) if row[2] else None,
            "ordered_steps": row[3] or [],
            "context_guidance": row[4] or {},
            "constraints": row[5] or {},
            "expected_verification": row[6] or {},
            "fallback_path": row[7] or {}
        }
    
    except Exception as e:
        logger.error(f"Error retrieving plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/replan")
def trigger_replan(
    request: ReplanRequest,
    db_conn=None
):
    """
    Trigger replanning after failure, unavailability, or constraint conflict.
    
    Creates new orchestration decision, links to original, preserves history.
    
    Returns new orchestration decision.
    """
    try:
        engine = AdaptiveOrchestrationEngine(db_conn)
        
        new_decision_id = engine.trigger_replan(
            original_decision_id=request.original_decision_id,
            trigger_type=request.trigger_type,
            trigger_reason=request.trigger_reason,
            attempt_number=request.attempt_number or 1
        )
        
        # Retrieve and return new decision
        engine.cursor.execute(
            """SELECT decision_id, task_id, strategy_selected, worker_selected,
                      confidence_score, decision_rationale, assignment_id
               FROM orchestration_decisions WHERE decision_id = %s""",
            (new_decision_id,)
        )
        row = engine.cursor.fetchone()
        
        return {
            "original_decision_id": str(request.original_decision_id),
            "new_decision_id": str(new_decision_id),
            "trigger_type": request.trigger_type,
            "trigger_reason": request.trigger_reason,
            "new_strategy": str(row[2]) if row[2] else None,
            "new_worker": str(row[3]) if row[3] else None,
            "new_assignment_id": str(row[6]) if row[6] else None,
            "new_confidence": float(row[4])
        }
    
    except Exception as e:
        logger.error(f"Error triggering replan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outcomes")
def record_orchestration_outcome(
    request: OutcomeRecordingRequest,
    db_conn=None
):
    """
    Record the outcome of an orchestration decision execution.
    
    Links assignment result back to orchestration decision for learning feedback.
    
    Returns outcome evaluation metadata.
    """
    try:
        engine = AdaptiveOrchestrationEngine(db_conn)
        
        outcome_eval_id = engine._record_orchestration_attempt_outcome(
            decision_id=request.decision_id,
            assignment_id=request.assignment_id,
            task_id=request.task_id,
            outcome_status=request.outcome_status,
            outcome_id=request.outcome_id,
            attempts_required=request.attempts_required,
            quality_score=request.quality_score
        )
        
        db_conn.commit()
        
        return {
            "outcome_evaluation_id": str(outcome_eval_id),
            "decision_id": str(request.decision_id),
            "assignment_id": str(request.assignment_id),
            "outcome_status": request.outcome_status,
            "attempts_required": request.attempts_required,
            "quality_score": request.quality_score,
            "recorded_at": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error recording outcome: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/outcomes/{outcome_eval_id}")
def get_orchestration_outcome(
    outcome_eval_id: UUID,
    db_conn=None
):
    """
    Retrieve orchestration outcome evaluation.
    
    Shows strategy performance, worker performance, plan accuracy, and feedback for learning.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT decision_id, assignment_id, task_id, actual_outcome_status,
                      attempts_required, actual_quality_score, strategy_performed_as_expected,
                      worker_capable, plan_accurate, orchestration_correct,
                      evidence_for_strategy_learning, evidence_for_worker_learning
               FROM orchestration_outcomes
               WHERE outcome_evaluation_id = %s""",
            (outcome_eval_id,)
        )
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Outcome {outcome_eval_id} not found")
        
        return {
            "outcome_evaluation_id": str(outcome_eval_id),
            "decision_id": str(row[0]),
            "assignment_id": str(row[1]),
            "task_id": str(row[2]),
            "actual_outcome_status": row[3],
            "attempts_required": row[4],
            "actual_quality_score": float(row[5]) if row[5] else 0.0,
            "strategy_performed_as_expected": row[6],
            "worker_capable": row[7],
            "plan_accurate": row[8],
            "orchestration_correct": row[9],
            "evidence_for_strategy_learning": row[10] or {},
            "evidence_for_worker_learning": row[11] or {}
        }
    
    except Exception as e:
        logger.error(f"Error retrieving outcome: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/replan-history/{original_decision_id}")
def get_replan_history(
    original_decision_id: UUID,
    db_conn=None
):
    """
    Get complete replan history starting from original decision.
    
    Shows: Original decision → Trigger 1 → New Decision 1 → Trigger 2 → New Decision 2, etc.
    """
    try:
        cursor = db_conn.cursor()
        
        # Build chain of decisions and triggers
        history = []
        current_decision_id = original_decision_id
        max_depth = 10  # Prevent infinite loops
        
        for _ in range(max_depth):
            # Get current decision
            cursor.execute(
                """SELECT decision_id, strategy_selected, worker_selected, confidence_score, final_outcome_status,
                          replanned_to, created_at
                   FROM orchestration_decisions WHERE decision_id = %s""",
                (current_decision_id,)
            )
            dec_row = cursor.fetchone()
            if not dec_row:
                break
            
            decision_info = {
                "decision_id": str(dec_row[0]),
                "strategy": str(dec_row[1]) if dec_row[1] else None,
                "worker": str(dec_row[2]) if dec_row[2] else None,
                "confidence": float(dec_row[3]),
                "outcome": dec_row[4],
                "created_at": dec_row[6].isoformat() if dec_row[6] else None
            }
            
            # Get replan trigger if replanned_to exists
            if dec_row[5]:  # replanned_to
                cursor.execute(
                    """SELECT trigger_type, trigger_reason, attempt_number FROM orchestration_replan_triggers
                       WHERE original_decision_id = %s AND new_decision_id = %s""",
                    (current_decision_id, dec_row[5])
                )
                trig_row = cursor.fetchone()
                if trig_row:
                    decision_info["replan_trigger"] = {
                        "type": trig_row[0],
                        "reason": trig_row[1],
                        "attempt": trig_row[2]
                    }
            
            history.append(decision_info)
            
            # Move to next decision
            if dec_row[5]:
                current_decision_id = dec_row[5]
            else:
                break
        
        return {
            "original_decision_id": str(original_decision_id),
            "replan_history": history,
            "replan_depth": len(history) - 1,
            "final_decision_id": str(history[-1]["decision_id"]) if history else None,
            "final_outcome": history[-1]["outcome"] if history else None
        }
    
    except Exception as e:
        logger.error(f"Error retrieving replan history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules/active")
def get_active_rule_config(db_conn=None):
    """
    Retrieve the active orchestration rule configuration.
    
    Shows thresholds, weights, limits, and strategies currently in use.
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute(
            """SELECT rule_version, min_strategy_effectiveness, min_strategy_confidence,
                      min_worker_applicability, min_evidence_count_high_confidence,
                      min_evidence_count_adequate_confidence, explicit_constraints_override_learned_preference,
                      respect_negative_evidence, max_replan_attempts, replan_backoff_ms,
                      conflicting_evidence_default_strategy, prefer_worker_health_over_evidence,
                      require_worker_availability, created_at
               FROM orchestration_rule_config
               WHERE active = TRUE
               ORDER BY created_at DESC LIMIT 1"""
        )
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No active rule configuration")
        
        return {
            "rule_version": row[0],
            "thresholds": {
                "min_strategy_effectiveness": float(row[1]),
                "min_strategy_confidence": float(row[2]),
                "min_worker_applicability": float(row[3])
            },
            "evidence_requirements": {
                "high_confidence_threshold": row[4],
                "adequate_confidence_threshold": row[5]
            },
            "constraint_handling": {
                "explicit_constraints_override": row[6],
                "respect_negative_evidence": row[7]
            },
            "replanning": {
                "max_attempts": row[8],
                "backoff_ms": row[9]
            },
            "conflict_resolution": {
                "strategy": row[10],
                "prefer_worker_health": row[11],
                "require_worker_availability": row[12]
            },
            "activated_at": row[13].isoformat() if row[13] else None
        }
    
    except Exception as e:
        logger.error(f"Error retrieving rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def register_orchestration_endpoints(app):
    """Register orchestration endpoints with FastAPI app."""
    app.include_router(router)
