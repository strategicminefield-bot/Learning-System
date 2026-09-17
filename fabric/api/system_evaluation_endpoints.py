"""
SECTION 21: SYSTEM EVALUATION API ENDPOINTS

Provides read-only evaluation interface. No execution authority.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID
import psycopg
import os
import json

from system_evaluation_engine import SystemEvaluationEngine

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation-v21"])

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://fabric@localhost/learning_fabric')


def get_db():
    """Database connection."""
    return psycopg.connect(DATABASE_URL)


@router.post("/baseline")
def run_baseline_evaluation(
    population_type: str = "task",
    days_lookback: int = 30
):
    """Run baseline evaluation on a population."""
    try:
        conn = get_db()
        engine = SystemEvaluationEngine(conn)
        
        # Define population
        population_definition = {
            "population_type": population_type,
            "time_window_days": days_lookback
        }
        
        # Calculate time window
        time_window_end = datetime.utcnow()
        time_window_start = time_window_end - timedelta(days=days_lookback)
        
        # Run evaluation
        result = engine.run_baseline_evaluation(
            population_definition=population_definition,
            time_window_start=time_window_start,
            time_window_end=time_window_end
        )
        
        conn.close()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs/{evaluation_id}")
def get_evaluation(evaluation_id: str):
    """Get evaluation run details."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT evaluation_id, evaluation_type, status, evaluation_rule_version,
                   population_definition, conclusion, evidence_sufficiency,
                   created_at, completed_at, result
            FROM system_evaluation_runs
            WHERE evaluation_id = %s
            """,
            (evaluation_id,)
        )
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Evaluation not found")
        
        return {
            "evaluation_id": row[0],
            "evaluation_type": row[1],
            "status": row[2],
            "rule_version": row[3],
            "population_definition": json.loads(row[4]) if row[4] else {},
            "conclusion": row[5],
            "evidence_sufficiency": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "completed_at": row[8].isoformat() if row[8] else None,
            "result": json.loads(row[9]) if row[9] else {}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs")
def list_evaluations(
    evaluation_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List evaluations."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        query = "SELECT evaluation_id, evaluation_type, status, conclusion, created_at FROM system_evaluation_runs WHERE 1=1"
        params = []
        
        if evaluation_type:
            query += " AND evaluation_type = %s"
            params.append(evaluation_type)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        
        return {
            "evaluations": [
                {
                    "evaluation_id": row[0],
                    "evaluation_type": row[1],
                    "status": row[2],
                    "conclusion": row[3],
                    "created_at": row[4].isoformat() if row[4] else None
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/findings/{evaluation_id}")
def get_findings(evaluation_id: str):
    """Get findings for evaluation."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT finding_id, finding_type, scope, direction, explanation, 
                   evidence_sufficiency, confidence_level
            FROM system_evaluation_findings
            WHERE evaluation_id = %s
            """,
            (evaluation_id,)
        )
        
        rows = cur.fetchall()
        conn.close()
        
        return {
            "evaluation_id": evaluation_id,
            "findings": [
                {
                    "finding_id": row[0],
                    "finding_type": row[1],
                    "scope": row[2],
                    "direction": row[3],
                    "explanation": row[4],
                    "evidence_sufficiency": row[5],
                    "confidence_level": row[6]
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/metrics/{evaluation_id}")
def get_metrics(evaluation_id: str):
    """Get metrics for evaluation."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute(
            """
            SELECT metric_id, metric_name, metric_category, value, sample_count, 
                   independent_entities, data_sources
            FROM system_evaluation_metrics
            WHERE evaluation_id = %s
            """,
            (evaluation_id,)
        )
        
        rows = cur.fetchall()
        conn.close()
        
        return {
            "evaluation_id": evaluation_id,
            "metrics": [
                {
                    "metric_id": row[0],
                    "metric_name": row[1],
                    "metric_category": row[2],
                    "value": float(row[3]) if row[3] else None,
                    "sample_count": row[4],
                    "independent_entities": row[5],
                    "data_sources": json.loads(row[6]) if row[6] else {}
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
def evaluation_health():
    """Check evaluation system health."""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Check if tables exist
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema='public' AND table_name LIKE 'system_evaluation%'
            """
        )
        table_count = cur.fetchone()[0]
        
        # Check evaluations
        cur.execute("SELECT COUNT(*) FROM system_evaluation_runs")
        eval_count = cur.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "ok" if table_count > 0 else "error",
            "evaluation_tables": table_count,
            "evaluations": eval_count
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
