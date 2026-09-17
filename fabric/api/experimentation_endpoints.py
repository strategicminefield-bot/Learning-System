"""Section 16: Experimentation API Endpoints"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
import json

from .experimentation_engine import ExperimentationEngine

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments-v16"])


class ExperimentRequest(BaseModel):
    hypothesis: str
    objective: str
    control_strategy_id: UUID
    treatment_strategy_id: UUID
    task_domain: str
    metrics: List[Dict]
    min_sample_size: Optional[int] = 10


class ObservationRequest(BaseModel):
    experiment_id: UUID
    assignment_id: UUID
    arm_id: UUID
    orchestration_decision_id: UUID
    strategy_used_id: UUID
    worker_node_id: UUID
    final_outcome_status: str
    metric_values: Dict
    quality_score: Optional[float] = None


@router.post("/create")
def create_experiment(req: ExperimentRequest, db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        exp_id = engine.create_experiment(
            hypothesis=req.hypothesis,
            objective=req.objective,
            control_strategy_id=req.control_strategy_id,
            treatment_strategy_id=req.treatment_strategy_id,
            task_domain=req.task_domain,
            metrics=req.metrics,
            min_sample_size=req.min_sample_size
        )
        return {"experiment_id": str(exp_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{experiment_id}")
def approve_experiment(experiment_id: UUID, db_conn=None):
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "UPDATE experiments SET status = 'approved' WHERE experiment_id = %s",
            (experiment_id,)
        )
        db_conn.commit()
        return {"experiment_id": str(experiment_id), "status": "approved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start/{experiment_id}")
def start_experiment(experiment_id: UUID, db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        success, msg = engine.start_experiment(experiment_id)
        if success:
            return {"experiment_id": str(experiment_id), "status": "running"}
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assign")
def assign_task_to_experiment(
    experiment_id: UUID, task_id: UUID, arm_id: UUID, db_conn=None
):
    try:
        engine = ExperimentationEngine(db_conn)
        success, assign_id, msg = engine.assign_task_to_arm(experiment_id, task_id, arm_id)
        if success:
            return {"assignment_id": str(assign_id), "status": "assigned"}
        else:
            raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/observe")
def record_observation(req: ObservationRequest, db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        obs_id = engine.record_observation(
            experiment_id=req.experiment_id,
            assignment_id=req.assignment_id,
            arm_id=req.arm_id,
            orchestration_decision_id=req.orchestration_decision_id,
            strategy_used_id=req.strategy_used_id,
            worker_node_id=req.worker_node_id,
            final_outcome_status=req.final_outcome_status,
            metric_values=req.metric_values,
            quality_score=req.quality_score
        )
        return {"observation_id": str(obs_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/{experiment_id}")
def analyze_experiment(experiment_id: UUID, db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        result = engine.analyze_experiment(experiment_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities")
def identify_opportunities(db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        opps = engine.identify_experiment_opportunities()
        return {"opportunities": opps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/propose-autonomous")
def propose_autonomous(opportunity: Dict, db_conn=None):
    try:
        engine = ExperimentationEngine(db_conn)
        success, exp_id, msg = engine.propose_autonomous_experiment(opportunity)
        if success:
            return {"experiment_id": str(exp_id), "status": "proposed"}
        else:
            return {"status": "rejected", "reason": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{experiment_id}")
def get_experiment(experiment_id: UUID, db_conn=None):
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            """SELECT experiment_id, hypothesis, objective, status, autonomous_initiated,
                      created_at FROM experiments WHERE experiment_id = %s""",
            (experiment_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return {
            "experiment_id": str(row[0]),
            "hypothesis": row[1],
            "objective": row[2],
            "status": row[3],
            "autonomous_initiated": row[4],
            "created_at": row[5].isoformat() if row[5] else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{experiment_id}/conclusion")
def get_experiment_conclusion(experiment_id: UUID, db_conn=None):
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            """SELECT conclusion_status, ready_for_promotion, evidence_summary
               FROM experiment_conclusions WHERE experiment_id = %s""",
            (experiment_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {"status": "no_conclusion"}
        return {
            "conclusion": row[0],
            "ready_for_promotion": row[1],
            "evidence": row[2] or {}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def register_experimentation_endpoints(app):
    """Register endpoints with FastAPI app."""
    app.include_router(router)
