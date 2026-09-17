"""
Section 11: Feedback & Validation REST Endpoints

Provides API for recording, querying, and auditing learning feedback.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from sqlalchemy import text
import json

from fabric.api.feedback import LearningFeedbackEngine

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post("/attempts/{attempt_id}/feedback")
async def record_attempt_feedback(
    attempt_id: str,
    task_id: str,
    node_id: str,
    outcome_id: Optional[str] = None,
    quality_score: float = 0.5,
    outcome_status: str = "partial",
    execution_time_seconds: Optional[int] = None,
    applied_learning: Optional[List[Dict[str, Any]]] = None,
    result: Optional[Dict[str, Any]] = None,
    db=None
) -> Dict[str, Any]:
    """
    Record feedback for attempt with applied learning.

    Creates immutable feedback records linking applied learning to outcomes.
    Updates evidence accumulation, confidence scores, and validation states.

    Applied learning format:
    [
        {
            'applied_id': uuid,
            'type': 'outcome|pattern|insight|artifact|graph_entity',
            'id': uuid,
            'relevance_score': 0-1
        }
    ]
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    engine = LearningFeedbackEngine(db)

    try:
        result_obj = record_feedback = engine.record_feedback(
            attempt_id=attempt_id,
            task_id=task_id,
            node_id=node_id,
            outcome_id=outcome_id,
            applied_learning_list=applied_learning or [],
            result=result or {},
            quality_score=quality_score,
            outcome_status=outcome_status,
            execution_time_seconds=execution_time_seconds,
        )

        return {
            'success': True,
            'feedback_records_created': result_obj['feedback_records_created'],
            'evidence_updated': result_obj['evidence_updated'],
            'confidence_adjustments': len(result_obj['confidence_adjustments']),
            'state_transitions': len(result_obj['state_transitions']),
            'duplicate_detected': result_obj['duplicate_detected'],
            'processing_log': result_obj.get('processing_trace')
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/attempts/{attempt_id}/feedback-trace")
async def get_attempt_feedback_trace(
    attempt_id: str,
    db=None
) -> Dict[str, Any]:
    """
    Retrieve complete feedback trace for attempt.

    Traces path: attempt → applied learning → feedback → validation state changes
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    engine = LearningFeedbackEngine(db)

    try:
        trace = engine.get_feedback_trace(attempt_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Attempt not found")

        return {
            'success': True,
            'trace': trace
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/learning/{learning_id}/evidence")
async def get_learning_evidence(
    learning_id: str,
    learning_type: str,
    db=None
) -> Dict[str, Any]:
    """
    Get accumulated evidence for learning item.

    Returns:
    - Evidence counts (supportive, contradictory, neutral, insufficient)
    - Confidence score and validation state
    - Historical transitions
    - Feedback records
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        # Get evidence accumulation
        query = """
            SELECT * FROM evidence_accumulation
            WHERE learning_id = :learning_id AND learning_type = :learning_type
        """
        accum = db.execute(
            text(query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchone()

        if not accum:
            raise HTTPException(status_code=404, detail="Learning item not found")

        accum = dict(accum)

        # Get feedback records
        feedback_query = """
            SELECT feedback_id, effect_classification, quality_score, quality_delta, created_at
            FROM feedback_records
            WHERE learning_id = :learning_id AND learning_type = :learning_type
            ORDER BY created_at DESC
        """
        feedback_rows = db.execute(
            text(feedback_query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchall()

        feedback = [
            {
                'feedback_id': row[0],
                'effect_classification': row[1],
                'quality_score': row[2],
                'quality_delta': row[3],
                'created_at': row[4]
            }
            for row in feedback_rows
        ]

        # Get confidence adjustments
        adj_query = """
            SELECT adjustment_id, previous_confidence, new_confidence, adjusted_at
            FROM confidence_adjustments
            WHERE learning_id = :learning_id AND learning_type = :learning_type
            ORDER BY adjusted_at DESC
        """
        adj_rows = db.execute(
            text(adj_query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchall()

        adjustments = [
            {
                'adjustment_id': row[0],
                'previous_confidence': row[1],
                'new_confidence': row[2],
                'adjusted_at': row[3]
            }
            for row in adj_rows
        ]

        # Get state transitions
        trans_query = """
            SELECT transition_id, from_state, to_state, transitioned_at
            FROM validation_transitions
            WHERE learning_id = :learning_id AND learning_type = :learning_type
            ORDER BY transitioned_at DESC
        """
        trans_rows = db.execute(
            text(trans_query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchall()

        transitions = [
            {
                'transition_id': row[0],
                'from_state': row[1],
                'to_state': row[2],
                'transitioned_at': row[3]
            }
            for row in trans_rows
        ]

        return {
            'success': True,
            'evidence': {
                'learning_id': accum['learning_id'],
                'learning_type': accum['learning_type'],
                'times_applied': accum['times_applied'],
                'supportive_count': accum['supportive_count'],
                'contradictory_count': accum['contradictory_count'],
                'neutral_count': accum['neutral_count'],
                'insufficient_evidence_count': accum['insufficient_evidence_count'],
                'supportive_ratio': float(accum['supportive_ratio']),
                'contradictory_ratio': float(accum['contradictory_ratio']),
                'confidence_score': float(accum['confidence_score']),
                'validation_state': accum['current_validation_state'],
                'last_evaluated': accum['last_evaluated'],
            },
            'feedback_records': feedback,
            'confidence_adjustments': adjustments,
            'state_transitions': transitions
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/learning/{learning_id}/feedback-history")
async def get_learning_feedback_history(
    learning_id: str,
    learning_type: str,
    limit: int = 100,
    db=None
) -> Dict[str, Any]:
    """
    Get all feedback records for learning item.

    Pagination for detailed inspection of evidence accumulation.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    if limit > 1000:
        limit = 1000

    try:
        query = """
            SELECT
                feedback_id, attempt_id, effect_classification, quality_score,
                baseline_quality, quality_delta, outcome_status, created_at
            FROM feedback_records
            WHERE learning_id = :learning_id AND learning_type = :learning_type
            ORDER BY created_at DESC
            LIMIT :limit
        """

        rows = db.execute(
            text(query),
            {'learning_id': learning_id, 'learning_type': learning_type, 'limit': limit}
        ).fetchall()

        feedback = [
            {
                'feedback_id': row[0],
                'attempt_id': row[1],
                'effect_classification': row[2],
                'quality_score': row[3],
                'baseline_quality': row[4],
                'quality_delta': row[5],
                'outcome_status': row[6],
                'created_at': row[7]
            }
            for row in rows
        ]

        return {
            'success': True,
            'feedback_records': feedback,
            'count': len(feedback),
            'limit': limit
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/{task_type}/learning-effectiveness")
async def get_task_learning_effectiveness(
    task_type: str,
    db=None
) -> Dict[str, Any]:
    """
    Get aggregate learning effectiveness for task type.

    Shows which learning items are being applied to this task type
    and their validation/effectiveness status.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        query = """
            SELECT DISTINCT
                ea.learning_id,
                ea.learning_type,
                ea.times_applied,
                ea.supportive_count,
                ea.contradictory_count,
                ea.confidence_score,
                ea.current_validation_state
            FROM evidence_accumulation ea
            WHERE ea.task_types ->> :task_type IS NOT NULL
            ORDER BY ea.confidence_score DESC
        """

        rows = db.execute(
            text(query),
            {'task_type': task_type}
        ).fetchall()

        items = [
            {
                'learning_id': row[0],
                'learning_type': row[1],
                'times_applied': row[2],
                'supportive_count': row[3],
                'contradictory_count': row[4],
                'confidence_score': float(row[5]),
                'validation_state': row[6]
            }
            for row in rows
        ]

        return {
            'success': True,
            'task_type': task_type,
            'learning_items': items,
            'count': len(items)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/validation/state/{learning_id}")
async def get_validation_state_history(
    learning_id: str,
    learning_type: str,
    db=None
) -> Dict[str, Any]:
    """
    Get complete validation state change history.

    Shows all transitions and evidence at time of transition.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        query = """
            SELECT
                transition_id, from_state, to_state, trigger_type, trigger_reason,
                evidence_state, thresholds_checked, transitioned_at
            FROM validation_transitions
            WHERE learning_id = :learning_id AND learning_type = :learning_type
            ORDER BY transitioned_at DESC
        """

        rows = db.execute(
            text(query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchall()

        transitions = [
            {
                'transition_id': row[0],
                'from_state': row[1],
                'to_state': row[2],
                'trigger_type': row[3],
                'trigger_reason': row[4],
                'evidence_state': row[5],
                'thresholds_checked': row[6],
                'transitioned_at': row[7]
            }
            for row in rows
        ]

        return {
            'success': True,
            'learning_id': learning_id,
            'learning_type': learning_type,
            'transitions': transitions,
            'count': len(transitions)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/feedback/processing-status/{attempt_id}")
async def get_feedback_processing_status(
    attempt_id: str,
    db=None
) -> Dict[str, Any]:
    """
    Get feedback processing status for attempt.

    Shows whether feedback has been recorded, processed, or had errors.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    try:
        query = """
            SELECT
                log_id, processing_status, feedback_records_created,
                evidence_updated, confidence_adjustments_made,
                state_transitions_made, processed_at, processing_error
            FROM feedback_processing_log
            WHERE attempt_id = :attempt_id
            ORDER BY created_at DESC
            LIMIT 1
        """

        result = db.execute(
            text(query),
            {'attempt_id': attempt_id}
        ).fetchone()

        if not result:
            return {
                'success': True,
                'attempt_id': attempt_id,
                'processing_status': 'not_processed'
            }

        return {
            'success': True,
            'attempt_id': attempt_id,
            'processing_status': result[1],
            'feedback_records_created': result[2],
            'evidence_updated': result[3],
            'confidence_adjustments': result[4],
            'state_transitions': result[5],
            'processed_at': result[6],
            'processing_error': result[7]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
