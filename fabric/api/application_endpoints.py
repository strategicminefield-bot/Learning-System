"""
Section 10: Learning Application Layer API Endpoints
Execution guidance generation and worker access.
"""

import os
import psycopg
from psycopg.extras import RealDictCursor
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
from application import LearningApplicationEngine, ApplicationError

router = APIRouter(prefix="/api/v1", tags=["application"])
DATABASE_URL = os.environ.get("DATABASE_URL", "")


class ApplyLearningRequest(BaseModel):
    """Request to apply learning to an attempt."""

    attempt_id: str
    task_id: str
    node_id: str
    retrieval_trace_id: Optional[str] = None
    context_package_id: Optional[str] = None


class ApplyLearningResponse(BaseModel):
    """Response with execution guidance."""

    status: str
    guidance_id: str
    attempt_id: str
    trace_id: str
    guidance: Dict[str, Any]
    applied_learning_count: int
    statistics: Dict[str, Any]


@router.post("/attempts/{attempt_id}/guidance")
def apply_learning_to_attempt(
    attempt_id: str,
    task_id: str = Query(...),
    node_id: str = Query(...),
    retrieval_trace_id: Optional[str] = Query(None),
    context_package_id: Optional[str] = Query(None),
) -> ApplyLearningResponse:
    """
    Apply relevant learning to an attempt and generate execution guidance.

    This endpoint:
    1. Retrieves relevant prior learning (via Section 9)
    2. Selects applicable items based on relevance and confidence
    3. Creates applied learning records for traceability
    4. Generates structured execution guidance
    5. Returns guidance for worker consumption

    Query Parameters:
    - task_id: Task UUID (required)
    - node_id: Node UUID (required)
    - retrieval_trace_id: Optional pre-existing retrieval trace
    - context_package_id: Optional pre-existing context package

    Returns:
    - Complete execution guidance with applied learning records
    - Traceable through retrieval and application pipelines
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            engine = LearningApplicationEngine(conn)
            result = engine.apply_learning_to_attempt(
                attempt_id, task_id, node_id, retrieval_trace_id, context_package_id
            )

            return ApplyLearningResponse(
                status=result["status"],
                guidance_id=result["guidance_id"],
                attempt_id=result["attempt_id"],
                trace_id=result["trace_id"],
                guidance=result["guidance"],
                applied_learning_count=result["applied_learning_count"],
                statistics=result["statistics"],
            )

    except ApplicationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Learning application failed: {str(e)}")


@router.get("/attempts/{attempt_id}/guidance")
def get_execution_guidance(attempt_id: str) -> Dict[str, Any]:
    """
    Retrieve execution guidance for an attempt.

    Returns the complete structured guidance with all recommended approaches,
    patterns, warnings, constraints, insights, and knowledge items.

    This guidance is immutable once generated, providing a historical record
    of what guidance an attempt received at execution time.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            engine = LearningApplicationEngine(conn)
            guidance = engine.get_execution_guidance(attempt_id)

            if not guidance:
                raise HTTPException(status_code=404, detail=f"No guidance for attempt {attempt_id}")

            return guidance

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guidance: {str(e)}")


@router.get("/attempts/{attempt_id}/applied-learning")
def get_applied_learning(attempt_id: str) -> Dict[str, Any]:
    """
    Get all learning items applied to an attempt.

    Returns individual applied learning records with:
    - Learning type and ID
    - Relevance scores
    - Confidence levels
    - Applicability reasoning
    - Source outcome references
    - Application status

    Enables tracing from attempt back through learning to evidence.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            engine = LearningApplicationEngine(conn)
            applied = engine.get_applied_learning(attempt_id)

            return {
                "attempt_id": attempt_id,
                "applied_learning": applied,
                "count": len(applied),
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve applied learning: {str(e)}")


@router.get("/guidance/{guidance_id}")
def get_guidance_by_id(guidance_id: str) -> Dict[str, Any]:
    """
    Retrieve a guidance package by ID.

    Returns the complete guidance structure with metadata and timestamps.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT guidance_id, attempt_id, task_id, node_id,
                           guidance_data, generated_at, created_at
                    FROM execution_guidance WHERE guidance_id = %s
                    """,
                    (guidance_id,),
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Guidance {guidance_id} not found")

        return {
            "guidance_id": row["guidance_id"],
            "attempt_id": row["attempt_id"],
            "task_id": row["task_id"],
            "node_id": row["node_id"],
            "guidance": row["guidance_data"],
            "generated_at": str(row["generated_at"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve guidance: {str(e)}")


@router.get("/attempts/{attempt_id}/application-trace")
def get_application_trace(attempt_id: str) -> Dict[str, Any]:
    """
    Get complete application trace showing how learning was selected.

    Returns:
    - Retrieval → Application pipeline
    - Items considered vs applied
    - Decision rationale
    - Generation metrics
    - Full audit trail
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get guidance trace
                cur.execute(
                    """
                    SELECT trace_id, guidance_id, retrieval_trace_id,
                           learning_items_considered, learning_items_applied,
                           learning_items_rejected, total_decisions,
                           applied_decisions, rejected_decisions,
                           generation_time_ms, total_guidance_size_bytes,
                           trace_status
                    FROM guidance_traces WHERE attempt_id = %s
                    """,
                    (attempt_id,),
                )
                trace = cur.fetchone()

                if not trace:
                    raise HTTPException(
                        status_code=404, detail=f"No trace for attempt {attempt_id}"
                    )

                # Get application decisions
                cur.execute(
                    """
                    SELECT considered_type, decision, reason,
                           relevance_score, confidence_score
                    FROM application_decisions WHERE attempt_id = %s
                    ORDER BY created_at
                    """,
                    (attempt_id,),
                )
                decisions = [dict(row) for row in cur.fetchall()]

        return {
            "attempt_id": attempt_id,
            "trace_id": trace["trace_id"],
            "retrieval_trace_id": trace["retrieval_trace_id"],
            "learning_considered": {
                "total": trace["learning_items_considered"],
            },
            "learning_applied": trace["learning_items_applied"],
            "learning_rejected": trace["learning_items_rejected"],
            "decisions": {
                "total": trace["total_decisions"],
                "applied": trace["applied_decisions"],
                "rejected": trace["rejected_decisions"],
            },
            "decision_log": decisions,
            "metrics": {
                "generation_time_ms": trace["generation_time_ms"],
                "guidance_size_bytes": trace["total_guidance_size_bytes"],
            },
            "status": trace["trace_status"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve trace: {str(e)}")


@router.get("/tasks/{task_id}/applications")
def list_task_applications(
    task_id: str, limit: int = Query(50, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    List all learning applications for a task.

    Shows all attempts for task with their guidance and applied learning.
    Useful for understanding what guidance was provided across attempts.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT eg.guidance_id, eg.attempt_id, a.status,
                           COUNT(al.applied_id) as learning_count,
                           eg.generated_at
                    FROM execution_guidance eg
                    LEFT JOIN attempts a ON eg.attempt_id = a.attempt_id
                    LEFT JOIN applied_learning al ON a.attempt_id = al.attempt_id
                    WHERE eg.task_id = %s
                    GROUP BY eg.guidance_id, eg.attempt_id, a.status, eg.generated_at
                    ORDER BY eg.generated_at DESC
                    LIMIT %s
                    """,
                    (task_id, limit),
                )
                applications = [dict(row) for row in cur.fetchall()]

        return {
            "task_id": task_id,
            "applications": applications,
            "count": len(applications),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list applications: {str(e)}")
