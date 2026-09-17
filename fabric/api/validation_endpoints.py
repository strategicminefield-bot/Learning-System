"""
Section 17: Validation/Promotion API Endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict, Any
from uuid import UUID
import psycopg2
from datetime import datetime
from validation_engine import (
    create_validation_candidate,
    add_validation_evidence,
    check_validation_eligibility,
    assess_evidence_sufficiency,
    make_validation_decision,
    apply_validation_decision,
    request_repeat_experiment,
    get_validation_candidate,
    get_validation_decision,
    get_candidate_history
)
from db import get_connection

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])

@router.post("/candidates")
async def create_candidate(
    candidate_type: str = Body(...),
    candidate_ref_id: UUID = Body(...),
    candidate_name: str = Body(...),
    domain_applicability: Optional[str] = Body(None),
    applicable_task_types: Optional[List[str]] = Body(None),
    source_node_id: Optional[UUID] = Body(None),
    source_experiment_id: Optional[UUID] = Body(None),
    source_operational_evidence: bool = Body(False)
):
    """Create validation candidate for eligible strategy/method/knowledge."""
    try:
        conn = get_connection()
        candidate_id = create_validation_candidate(
            conn,
            candidate_type,
            candidate_ref_id,
            candidate_name,
            domain_applicability,
            applicable_task_types,
            source_node_id,
            source_experiment_id,
            source_operational_evidence
        )
        conn.close()
        return {"candidate_id": str(candidate_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/candidates/{candidate_id}/evidence")
async def add_evidence(
    candidate_id: UUID,
    evidence_type: str = Body(...),
    evidence_category: str = Body(...),
    confidence_score: float = Body(...),
    evidence_strength: float = Body(...),
    source_experiment_id: Optional[UUID] = Body(None),
    source_experiment_analysis_id: Optional[UUID] = Body(None),
    source_operational_outcome_id: Optional[UUID] = Body(None),
    source_node_id: Optional[UUID] = Body(None),
    cross_node_reproduced: bool = Body(False),
    evidence_summary: Optional[str] = Body(None),
    evidence_detail: Optional[Dict] = Body(None),
    observation_counts: Optional[Dict] = Body(None)
):
    """Record evidence supporting or contradicting candidate."""
    try:
        conn = get_connection()
        evidence_id = add_validation_evidence(
            conn,
            candidate_id,
            evidence_type,
            evidence_category,
            confidence_score,
            evidence_strength,
            source_experiment_id,
            source_experiment_analysis_id,
            source_operational_outcome_id,
            source_node_id,
            cross_node_reproduced,
            evidence_summary,
            evidence_detail,
            observation_counts
        )
        conn.close()
        return {"evidence_id": str(evidence_id), "status": "recorded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/candidates/{candidate_id}/check-eligibility")
async def check_eligibility(
    candidate_id: UUID,
    min_evidence_required: int = Query(1)
):
    """Check if candidate is eligible for validation."""
    try:
        conn = get_connection()
        is_eligible, details = check_validation_eligibility(conn, candidate_id, min_evidence_required)
        conn.close()
        return {
            "candidate_id": str(candidate_id),
            "is_eligible": is_eligible,
            "details": details
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/candidates/{candidate_id}/assess-sufficiency")
async def assess_sufficiency(
    candidate_id: UUID,
    rule_config_version_id: Optional[UUID] = Body(None)
):
    """Assess whether evidence is sufficient for promotion."""
    try:
        conn = get_connection()
        sufficient, details = assess_evidence_sufficiency(conn, candidate_id, rule_config_version_id)
        conn.close()
        return {
            "candidate_id": str(candidate_id),
            "evidence_sufficient": sufficient,
            "assessment": details
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/candidates/{candidate_id}/decide")
async def make_decision(
    candidate_id: UUID,
    decision_type: str = Body(...),
    rationale: str = Body(...),
    authority: str = Body("system"),
    requires_approval: bool = Body(False),
    evidence_summary: Optional[Dict] = Body(None)
):
    """Make validation decision (promote/restrict/retire/etc)."""
    try:
        conn = get_connection()
        decision_id = make_validation_decision(
            conn,
            candidate_id,
            decision_type,
            rationale,
            evidence_summary,
            authority,
            requires_approval
        )
        conn.close()
        return {
            "decision_id": str(decision_id),
            "candidate_id": str(candidate_id),
            "decision_type": decision_type,
            "status": "made"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions/{decision_id}/apply")
async def apply_decision(
    decision_id: UUID,
    applied_by: str = Body("system")
):
    """Apply validation decision to production state."""
    try:
        conn = get_connection()
        success = apply_validation_decision(conn, decision_id, applied_by)
        conn.close()
        return {
            "decision_id": str(decision_id),
            "applied": success,
            "status": "applied" if success else "failed"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/candidates/{candidate_id}/request-repeat-experiment")
async def request_repeat(
    candidate_id: UUID,
    hypothesis: str = Body(...),
    objective: str = Body(...),
    min_sample_size: int = Body(10),
    max_enrolled_tasks: int = Body(100)
):
    """Request repeat experiment when validation is inconclusive."""
    try:
        conn = get_connection()
        
        # Get latest decision
        cur = conn.cursor()
        cur.execute("""
            SELECT decision_id FROM validation_decisions
            WHERE candidate_id = %s
            ORDER BY made_at DESC LIMIT 1
        """, (candidate_id,))
        decision_row = cur.fetchone()
        cur.close()
        
        if not decision_row:
            raise ValueError("No decision found for candidate")
        
        decision_id = decision_row[0]
        
        repeat_request_id = request_repeat_experiment(
            conn,
            candidate_id,
            decision_id,
            hypothesis,
            objective,
            min_sample_size,
            max_enrolled_tasks
        )
        conn.close()
        
        return {
            "repeat_request_id": str(repeat_request_id),
            "candidate_id": str(candidate_id),
            "status": "requested"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: UUID):
    """Retrieve validation candidate."""
    try:
        conn = get_connection()
        candidate = get_validation_candidate(conn, candidate_id)
        conn.close()
        
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        return {
            "candidate_id": str(candidate['candidate_id']),
            "candidate_type": candidate['candidate_type'],
            "candidate_name": candidate['candidate_name'],
            "current_status": candidate['current_status'],
            "created_at": candidate['created_at'].isoformat() if candidate['created_at'] else None
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: UUID):
    """Retrieve validation decision."""
    try:
        conn = get_connection()
        decision = get_validation_decision(conn, decision_id)
        conn.close()
        
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")
        
        return {
            "decision_id": str(decision['decision_id']),
            "candidate_id": str(decision['candidate_id']),
            "decision_type": decision['decision_type'],
            "rationale": decision['rationale'],
            "made_at": decision['made_at'].isoformat() if decision['made_at'] else None,
            "applied_at": decision['applied_at'].isoformat() if decision['applied_at'] else None
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/candidates/{candidate_id}/history")
async def get_history(candidate_id: UUID):
    """Get complete audit trail for candidate."""
    try:
        conn = get_connection()
        history = get_candidate_history(conn, candidate_id)
        conn.close()
        
        return {
            "candidate_id": str(candidate_id),
            "history": [
                {
                    "event_type": h['event_type'],
                    "new_status": h['new_status'],
                    "recorded_at": h['recorded_at'].isoformat() if h['recorded_at'] else None
                }
                for h in history
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/candidates/{candidate_id}/decisions")
async def get_candidate_decisions(candidate_id: UUID):
    """Get all validation decisions for candidate."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT decision_id, decision_type, rationale, made_at
            FROM validation_decisions
            WHERE candidate_id = %s
            ORDER BY made_at DESC
        """, (candidate_id,))
        
        decisions = []
        for row in cur.fetchall():
            decisions.append({
                "decision_id": str(row[0]),
                "decision_type": row[1],
                "rationale": row[2],
                "made_at": row[3].isoformat() if row[3] else None
            })
        
        cur.close()
        conn.close()
        
        return {
            "candidate_id": str(candidate_id),
            "decisions": decisions
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
