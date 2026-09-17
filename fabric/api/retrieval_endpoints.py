"""
Section 9: Retrieval & Context Layer API Endpoints
Task-aware context retrieval and delivery for execution nodes.
"""

import os
import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
from retrieval import ContextRetriever, RetrieverError

router = APIRouter(prefix="/api/v1", tags=["retrieval"])
DATABASE_URL = os.environ.get("DATABASE_URL", "")


class ContextRequest(BaseModel):
    """Request for task execution context."""

    task_id: str
    node_id: Optional[str] = None
    assignment_id: Optional[str] = None


class ContextResponse(BaseModel):
    """Retrieved execution context response."""

    status: str
    package_id: str
    trace_id: str
    query_id: str
    task_id: str
    context: Dict[str, Any]
    retrieval_stats: Dict[str, Any]


class RetrievalFeedbackRequest(BaseModel):
    """Feedback on retrieval usefulness."""

    package_id: str
    node_id: str
    usefulness_score: float
    used_items: Optional[List[str]] = None
    assignment_id: Optional[str] = None
    outcome_id: Optional[str] = None
    feedback_text: Optional[str] = None


class RetrievalFeedbackResponse(BaseModel):
    """Feedback recording response."""

    feedback_id: str
    package_id: str
    node_id: str
    usefulness_score: float
    status: str


@router.post("/tasks/{task_id}/context")
def get_task_context(
    task_id: str,
    node_id: Optional[str] = Query(None),
    assignment_id: Optional[str] = Query(None),
) -> ContextResponse:
    """
    Retrieve and assemble relevant learning context for task execution.

    Given a task, this endpoint:
    1. Identifies the task type and specification
    2. Queries all relevant learning sources (outcomes, patterns, insights, artifacts, graph)
    3. Deduplicates and filters by relevance
    4. Assembles structured context package with provenance
    5. Returns context suitable for consumption by executing node

    The context includes complete provenance information for each item,
    enabling traceability back to source outcomes and confidence metrics.

    Query Parameters:
    - node_id: Optional worker node requesting context (for node-specific insights)
    - assignment_id: Optional assignment context

    Returns:
    - Complete context package with outcomes, patterns, insights, artifacts
    - Provenance and evidence for each item
    - Retrieval trace for correlation with outcomes
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            retriever = ContextRetriever(conn)
            result = retriever.query_task_context(task_id, node_id, assignment_id)

            return ContextResponse(
                status=result["status"],
                package_id=result["package_id"],
                trace_id=result["trace_id"],
                query_id=result["query_id"],
                task_id=result["task_id"],
                context=result["context"],
                retrieval_stats=result["retrieval_stats"],
            )

    except RetrieverError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Context retrieval failed: {str(e)}")


@router.get("/context/{package_id}")
def get_context_package(package_id: str) -> Dict[str, Any]:
    """
    Retrieve a previously-generated context package by ID.

    Returns the full structured context that was delivered,
    useful for auditing or re-examining retrieved learning.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT cp.package_id, cp.task_id, cp.node_id, cp.context_data,
                           cp.context_size_bytes, cp.item_count, cp.assembly_time_ms,
                           cp.created_at, rt.trace_id, rq.query_id
                    FROM context_packages cp
                    JOIN retrieval_traces rt ON cp.trace_id = rt.trace_id
                    JOIN retrieval_queries rq ON rt.query_id = rq.query_id
                    WHERE cp.package_id = %s
                    """,
                    (package_id,),
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Context package {package_id} not found")

        return {
            "package_id": row[0],
            "task_id": row[1],
            "node_id": row[2],
            "context": row[3],
            "context_size_bytes": row[4],
            "item_count": row[5],
            "assembly_time_ms": row[6],
            "created_at": str(row[7]),
            "trace_id": row[8],
            "query_id": row[9],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve context: {str(e)}")


@router.get("/retrieval/{trace_id}")
def get_retrieval_trace(trace_id: str) -> Dict[str, Any]:
    """
    Retrieve detailed retrieval trace showing what was considered and selected.

    Returns metrics for auditing and understanding retrieval behavior,
    including deduplication, filtering, and ranking decisions.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT trace_id, query_id,
                           outcomes_considered, patterns_considered, insights_considered,
                           artifacts_considered, graph_entities_considered,
                           outcomes_selected, patterns_selected, insights_selected,
                           artifacts_selected, graph_entities_selected,
                           total_items_returned, deduplication_count,
                           filtered_by_threshold, execution_time_ms,
                           trace_status, trace_error, created_at
                    FROM retrieval_traces
                    WHERE trace_id = %s
                    """,
                    (trace_id,),
                )
                trace = cur.fetchone()

        if not trace:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

        # Retrieve individual items
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item_id, source_type, source_id, relevance_score,
                           is_duplicate, canonical_item_id, item_metadata
                    FROM retrieved_items
                    WHERE trace_id = %s
                    ORDER BY relevance_score DESC
                    """,
                    (trace_id,),
                )
                items = [{
                    "item_id": row[0],
                    "source_type": row[1],
                    "source_id": row[2],
                    "relevance_score": row[3],
                    "is_duplicate": row[4],
                    "canonical_item_id": row[5],
                    "item_metadata": row[6],
                } for row in cur.fetchall()]

        return {
            "trace_id": trace[0],
            "query_id": trace[1],
            "considered": {
                "outcomes": trace[2],
                "patterns": trace[3],
                "insights": trace[4],
                "artifacts": trace[5],
                "graph_entities": trace[6],
            },
            "selected": {
                "outcomes": trace[7],
                "patterns": trace[8],
                "insights": trace[9],
                "artifacts": trace[10],
                "graph_entities": trace[11],
            },
            "metrics": {
                "total_items": trace[12],
                "deduplication_count": trace[13],
                "filtered_by_threshold": trace[14],
                "execution_time_ms": trace[15],
            },
            "status": trace[16],
            "error": trace[17],
            "created_at": str(trace[18]),
            "items": items,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve trace: {str(e)}")


@router.get("/retrieval/query/{query_id}")
def get_retrieval_query(query_id: str) -> Dict[str, Any]:
    """
    Retrieve the original retrieval query parameters and results.

    Shows what was requested and links to resulting context package.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rq.query_id, rq.task_id, rq.node_id, rq.assignment_id,
                           rq.query_params, rq.query_time_ms, rq.created_at,
                           rt.trace_id, cp.package_id
                    FROM retrieval_queries rq
                    LEFT JOIN retrieval_traces rt ON rq.query_id = rt.query_id
                    LEFT JOIN context_packages cp ON rt.trace_id = cp.trace_id
                    WHERE rq.query_id = %s
                    """,
                    (query_id,),
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Query {query_id} not found")

        return {
            "query_id": row[0],
            "task_id": row[1],
            "node_id": row[2],
            "assignment_id": row[3],
            "query_params": row[4],
            "query_time_ms": row[5],
            "created_at": str(row[6]),
            "trace_id": row[7],
            "package_id": row[8],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve query: {str(e)}")


@router.post("/retrieval/feedback")
def record_retrieval_feedback(request: RetrievalFeedbackRequest) -> RetrievalFeedbackResponse:
    """
    Record feedback on retrieval usefulness for learning and model improvement.

    This endpoint enables:
    - Measuring whether retrieved context was useful
    - Tracking which items were actually used
    - Correlating retrieval quality with execution outcomes
    - Iterative improvement of ranking algorithms

    Returns feedback_id for tracking.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            retriever = ContextRetriever(conn)
            result = retriever.record_retrieval_feedback(
                package_id=request.package_id,
                node_id=request.node_id,
                usefulness_score=request.usefulness_score,
                used_items=request.used_items,
                assignment_id=request.assignment_id,
                outcome_id=request.outcome_id,
                feedback_text=request.feedback_text,
            )

        return RetrievalFeedbackResponse(
            feedback_id=result["feedback_id"],
            package_id=result["package_id"],
            node_id=result["node_id"],
            usefulness_score=result["usefulness_score"],
            status=result["status"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.get("/retrieval/feedback/{feedback_id}")
def get_retrieval_feedback(feedback_id: str) -> Dict[str, Any]:
    """
    Retrieve recorded feedback about a context package's usefulness.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT feedback_id, package_id, node_id, usefulness_score,
                           used_items, assignment_id, outcome_id,
                           feedback_text, feedback_timestamp
                    FROM retrieval_feedback
                    WHERE feedback_id = %s
                    """,
                    (feedback_id,),
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Feedback {feedback_id} not found")

        return {
            "feedback_id": row[0],
            "package_id": row[1],
            "node_id": row[2],
            "usefulness_score": float(row[3]) if row[3] else None,
            "used_items": row[4] or [],
            "assignment_id": row[5],
            "outcome_id": row[6],
            "feedback_text": row[7],
            "created_at": str(row[8]),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve feedback: {str(e)}")


@router.get("/retrieval/task/{task_id}")
def list_task_retrievals(
    task_id: str, limit: int = Query(50, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    List all retrieval operations for a task with their traces and outcomes.

    Useful for auditing what context was provided and how it correlated
    with actual task execution and outcomes.
    """
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rq.query_id, rq.node_id, rq.created_at,
                           rt.trace_id, rt.total_items_returned,
                           rt.execution_time_ms, rt.trace_status,
                           cp.package_id, cp.item_count,
                           rf.feedback_id, rf.usefulness_score
                    FROM retrieval_queries rq
                    LEFT JOIN retrieval_traces rt ON rq.query_id = rt.query_id
                    LEFT JOIN context_packages cp ON rt.trace_id = cp.trace_id
                    LEFT JOIN retrieval_feedback rf ON cp.package_id = rf.package_id
                    WHERE rq.task_id = %s
                    ORDER BY rq.created_at DESC
                    LIMIT %s
                    """,
                    (task_id, limit),
                )
                rows = [{
                    "query_id": row[0],
                    "node_id": row[1],
                    "created_at": str(row[2]),
                    "trace_id": row[3],
                    "total_items_returned": row[4],
                    "execution_time_ms": row[5],
                    "trace_status": row[6],
                    "package_id": row[7],
                    "item_count": row[8],
                    "feedback_id": row[9],
                    "usefulness_score": row[10],
                } for row in cur.fetchall()]

        return {
            "task_id": task_id,
            "retrievals": rows,
            "count": len(rows),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list retrievals: {str(e)}")
