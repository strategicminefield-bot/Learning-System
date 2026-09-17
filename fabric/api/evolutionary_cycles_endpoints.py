"""
Section 23: Evolutionary Cycles API Endpoints
Exposes cycle management, stage retrieval, and traceability.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
import json
import logging
import os
import psycopg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://fabric@learning-fabric-postgres:5432/learning_fabric"
)


def get_db():
    """Database connection dependency."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


router = APIRouter(prefix="/api/v1/evolution", tags=["evolution-cycles"])


# ===== Models =====

class CreateCycleRequest(BaseModel):
    trigger_source: str
    trigger_reference: Optional[UUID] = None
    objective: Optional[str] = None
    work_population: Optional[Dict[str, Any]] = None
    scope: Optional[str] = None


class CycleResponse(BaseModel):
    cycle_id: str
    trigger_source: str
    status: str
    current_stage: Optional[str]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    termination_reason: Optional[str] = None


class CycleStageResponse(BaseModel):
    stage_record_id: str
    stage: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    input_references: Optional[Dict[str, Any]]
    output_references: Optional[Dict[str, Any]]
    decision_references: Optional[Dict[str, Any]]


class CycleTraceResponse(BaseModel):
    cycle_id: str
    stages: List[CycleStageResponse]
    evidence_links: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]


# ===== Endpoints =====

@router.post("/cycles", response_model=Dict[str, Any])
def create_cycle(req: CreateCycleRequest, db_conn=Depends(get_db)):
    """Create new evolutionary cycle"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)

        cycle_id = orchestrator.create_cycle(
            trigger_source=req.trigger_source,
            trigger_reference=req.trigger_reference,
            objective=req.objective,
            work_population=req.work_population,
            scope=req.scope,
        )

        return {
            "cycle_id": str(cycle_id),
            "status": "created",
            "trigger_source": req.trigger_source,
        }
    except Exception as e:
        logger.error(f"Failed to create cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cycles/{cycle_id}/start", response_model=Dict[str, Any])
def start_cycle(cycle_id: UUID, db_conn=Depends(get_db)):
    """Start evolutionary cycle"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)
        orchestrator.start_cycle(cycle_id)

        return {
            "cycle_id": str(cycle_id),
            "status": "running",
        }
    except Exception as e:
        logger.error(f"Failed to start cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles/{cycle_id}", response_model=CycleResponse)
def get_cycle(cycle_id: UUID, db_conn=Depends(get_db)):
    """Retrieve cycle state"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)
        cycle = orchestrator.get_cycle(cycle_id)

        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found")

        return CycleResponse(**cycle)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cycle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles", response_model=List[Dict[str, Any]])
def list_cycles(status: Optional[str] = None, limit: int = 100, db_conn=Depends(get_db)):
    """List evolutionary cycles"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)
        cycles = orchestrator.list_cycles(status=status, limit=limit)
        return cycles
    except Exception as e:
        logger.error(f"Failed to list cycles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cycles/{cycle_id}/trace", response_model=CycleTraceResponse)
def get_cycle_trace(cycle_id: UUID, db_conn=Depends(get_db)):
    """Retrieve complete evolutionary cycle trace (closed-loop traceability)"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)

        # Get cycle
        cycle = orchestrator.get_cycle(cycle_id)
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found")

        # Get stages
        stages = orchestrator.get_cycle_trace(cycle_id)

        # Get evidence links
        orchestrator.cursor.execute(
            """
            SELECT link_id, stage, evidence_type, evidence_id,
                   evidence_table, sequence_order
            FROM evolution_cycle_evidence_links
            WHERE cycle_id = %s
            ORDER BY sequence_order ASC
            """,
            (cycle_id,),
        )
        evidence_links = [
            {
                "link_id": str(row[0]),
                "stage": row[1],
                "evidence_type": row[2],
                "evidence_id": str(row[3]),
                "evidence_table": row[4],
                "sequence_order": row[5],
            }
            for row in orchestrator.cursor.fetchall()
        ]

        # Get decisions
        orchestrator.cursor.execute(
            """
            SELECT decision_id, stage, what_was_observed,
                   change_proposed, governance_result, system_evaluation_result
            FROM evolution_cycle_decisions
            WHERE cycle_id = %s
            """,
            (cycle_id,),
        )
        decisions = [
            {
                "decision_id": str(row[0]),
                "stage": row[1],
                "observation": row[2],
                "change_proposed": row[3],
                "governance_result": row[4],
                "system_evaluation": row[5],
            }
            for row in orchestrator.cursor.fetchall()
        ]

        return CycleTraceResponse(
            cycle_id=str(cycle_id),
            stages=[CycleStageResponse(**s) for s in stages],
            evidence_links=evidence_links,
            decisions=decisions,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cycle trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cycles/{cycle_id}/check-management-protection")
def check_management_protection(
    cycle_id: UUID, proposed_action: str, target: str, db_conn=Depends(get_db)
):
    """Check if proposed action targets protected management plane"""
    from evolutionary_cycles import EvolutionaryCycleOrchestrator

    try:
        orchestrator = EvolutionaryCycleOrchestrator(db_conn)
        allowed, reason = orchestrator.check_management_plane_protection(
            proposed_action, target
        )

        return {
            "cycle_id": str(cycle_id),
            "allowed": allowed,
            "reason": reason,
            "blocked_as_management_plane": not allowed,
        }
    except Exception as e:
        logger.error(f"Management plane check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def register_evolutionary_cycles_endpoints(app):
    """Register router with FastAPI app"""
    app.include_router(router)
