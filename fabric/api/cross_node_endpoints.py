"""
Section 12: Cross-Node Learning Distribution API Endpoints
"""

import os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import psycopg
import json
from cross_node_learning import get_cross_node_service

router = APIRouter(prefix="/api/v1", tags=["cross-node"])
DATABASE_URL = os.environ.get("DATABASE_URL", "")


class PromotionEligibilityRequest(BaseModel):
    """Request to check learning promotion eligibility."""
    learning_id: str
    learning_type: str
    confidence: float
    evidence_count: int
    validation_state: str
    task_type: str
    contradictions: Optional[List[Dict[str, Any]]] = None


class PromotionEligibilityResponse(BaseModel):
    """Response for promotion eligibility check."""
    learning_id: str
    eligible: bool
    rules_passed: List[str]
    rules_failed: List[Dict[str, str]]
    overall_promotion_confidence: float


class PromotionRequest(BaseModel):
    """Request to promote learning to organisational level."""
    learning_id: str
    learning_type: str
    source_node_id: str
    task_type: str
    content: Dict[str, Any]
    confidence: float = 0.8
    promotion_reason: str = "automated_promotion"


class CrossNodeDistributionRequest(BaseModel):
    """Record cross-node distribution."""
    org_learning_id: str
    source_node_id: str
    target_node_id: str
    retrieval_trace_id: Optional[str] = None
    context_package_id: Optional[str] = None


class EvidenceLinkRequest(BaseModel):
    """Record evidence link from cross-node learning application."""
    org_learning_id: str
    outcome_id: str
    source_node_id: str
    consuming_node_id: str
    agreement_type: str  # 'supportive', 'contradictory', 'neutral'
    agreement_confidence: float
    evidence_summary: Optional[Dict[str, Any]] = None
    distribution_id: Optional[str] = None


@router.post("/cross-node/promotion-eligibility")
def check_promotion_eligibility(request: PromotionEligibilityRequest) -> PromotionEligibilityResponse:
    """
    Check if learning is eligible for organisational promotion.
    
    Uses deterministic rules to evaluate:
    - Confidence threshold
    - Evidence count
    - Validation state
    - Task type specification
    - Contradiction analysis
    """
    try:
        service = get_cross_node_service()
        result = service.check_promotion_eligibility(
            learning_id=request.learning_id,
            learning_type=request.learning_type,
            confidence=request.confidence,
            evidence_count=request.evidence_count,
            validation_state=request.validation_state,
            task_type=request.task_type,
            contradictions=request.contradictions
        )
        
        return PromotionEligibilityResponse(
            learning_id=request.learning_id,
            eligible=result["eligible"],
            rules_passed=result["rules_passed"],
            rules_failed=result["rules_failed"],
            overall_promotion_confidence=result["overall_promotion_confidence"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eligibility check failed: {str(e)}")


@router.post("/cross-node/promote")
def promote_learning(request: PromotionRequest) -> Dict[str, Any]:
    """
    Promote learning to organisational level for cross-node sharing.
    
    Idempotent: repeated promotions of the same learning return the same
    org_learning_id and status 'already_promoted'.
    """
    try:
        service = get_cross_node_service()
        result = service.promote_learning_to_organisational(
            learning_id=request.learning_id,
            learning_type=request.learning_type,
            source_node_id=request.source_node_id,
            task_type=request.task_type,
            content=request.content,
            confidence=request.confidence,
            promotion_reason=request.promotion_reason
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Promotion failed: {str(e)}")


@router.get("/cross-node/organisational/{task_type}")
def get_organisational_learning(
    task_type: str,
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    Retrieve organisational learning applicable to a task type.
    
    Returns learning that has been promoted to organisational level,
    filtered by applicability task type.
    """
    try:
        service = get_cross_node_service()
        result = service.get_organisational_learning_for_task_type(task_type, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve organisational learning: {str(e)}")


@router.post("/cross-node/distribution")
def record_distribution(request: CrossNodeDistributionRequest) -> Dict[str, Any]:
    """
    Record when a node retrieves organisational learning.
    
    Creates audit trail of cross-node knowledge sharing.
    Idempotent: prevents duplicate distribution records within 1 hour.
    """
    try:
        service = get_cross_node_service()
        result = service.record_cross_node_distribution(
            org_learning_id=request.org_learning_id,
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            retrieval_trace_id=request.retrieval_trace_id,
            context_package_id=request.context_package_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record distribution: {str(e)}")


@router.post("/cross-node/evidence-link")
def record_evidence_link(request: EvidenceLinkRequest) -> Dict[str, Any]:
    """
    Record evidence from a consuming node using organisational learning.
    
    Supports supportive, contradictory, or neutral evidence.
    Automatically updates organisational learning state based on
    accumulated evidence (e.g., marks as 'disputed' if high-confidence
    contradictions accumulate).
    """
    try:
        service = get_cross_node_service()
        result = service.record_cross_node_evidence_link(
            org_learning_id=request.org_learning_id,
            outcome_id=request.outcome_id,
            source_node_id=request.source_node_id,
            consuming_node_id=request.consuming_node_id,
            agreement_type=request.agreement_type,
            agreement_confidence=request.agreement_confidence,
            evidence_summary=request.evidence_summary,
            distribution_id=request.distribution_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record evidence link: {str(e)}")


@router.get("/cross-node/provenance/{org_learning_id}")
def get_provenance(org_learning_id: str) -> Dict[str, Any]:
    """
    Retrieve complete provenance for organisational learning.
    
    Returns:
    - Original source (node, learning type)
    - Promotion history (state transitions)
    - Cross-node evidence (supportive and contradictory)
    - Current validation state
    """
    try:
        service = get_cross_node_service()
        result = service.get_organisational_learning_provenance(org_learning_id)
        
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Organisational learning {org_learning_id} not found")
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provenance: {str(e)}")


@router.get("/cross-node/distribution-history/{org_learning_id}")
def get_distribution_history(org_learning_id: str) -> Dict[str, Any]:
    """
    Get complete distribution history for organisational learning.
    
    Shows which nodes have accessed this learning and when.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT distribution_id, source_node_id, target_node_id,
                              retrieved_at, applied_attempt_id, distribution_status
                       FROM cross_node_distribution
                       WHERE org_learning_id=%s
                       ORDER BY retrieved_at DESC""",
                    (org_learning_id,)
                )
                
                distributions = []
                for row in cur.fetchall():
                    distributions.append({
                        "distribution_id": str(row[0]),
                        "source_node_id": str(row[1]),
                        "target_node_id": str(row[2]),
                        "retrieved_at": row[3].isoformat() if hasattr(row[3], 'isoformat') else str(row[3]),
                        "applied_attempt_id": str(row[4]) if row[4] else None,
                        "status": row[5]
                    })
                
                return {
                    "org_learning_id": org_learning_id,
                    "distributions": distributions,
                    "total": len(distributions)
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve distribution history: {str(e)}")


@router.get("/cross-node/evidence-summary/{org_learning_id}")
def get_evidence_summary(org_learning_id: str) -> Dict[str, Any]:
    """
    Get evidence summary for organisational learning.
    
    Shows breakdown of supportive vs contradictory evidence,
    and their confidence levels.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Get organisational learning
                cur.execute(
                    "SELECT current_state, evidence_count FROM organisational_learning WHERE org_learning_id=%s",
                    (org_learning_id,)
                )
                org_row = cur.fetchone()
                if not org_row:
                    raise HTTPException(status_code=404, detail="Organisational learning not found")
                
                current_state, total_evidence = org_row
                
                # Get evidence breakdown
                cur.execute(
                    """SELECT agreement_type, COUNT(*), AVG(agreement_confidence)
                       FROM cross_node_evidence_links
                       WHERE org_learning_id=%s
                       GROUP BY agreement_type""",
                    (org_learning_id,)
                )
                
                evidence_breakdown = {}
                for row in cur.fetchall():
                    agreement_type, count, avg_confidence = row
                    evidence_breakdown[agreement_type] = {
                        "count": count,
                        "average_confidence": float(avg_confidence) if avg_confidence else 0.0
                    }
                
                return {
                    "org_learning_id": org_learning_id,
                    "current_state": current_state,
                    "total_evidence_links": total_evidence,
                    "evidence_breakdown": evidence_breakdown
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get evidence summary: {str(e)}")
