"""Section 18: Node Evolution API Endpoints"""
from fastapi import APIRouter, HTTPException, Body, Query
from uuid import UUID
from node_evolution_engine import *
from db import get_connection

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])

@router.post("/definitions")
async def create_node_def(node_type: str = Body(...), display_name: str = Body(...), provider_type: str = Body(None), capabilities: list = Body(...)):
    try:
        conn = get_connection()
        def_id = create_node_definition(conn, node_type, display_name, provider_type, capabilities=capabilities)
        conn.close()
        return {"definition_id": str(def_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/definitions/{definition_id}/versions")
async def create_version(definition_id: UUID, capabilities: list = Body(...), description: str = Body(...)):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(version_number), 0) + 1 FROM node_definition_versions WHERE definition_id = %s", (definition_id,))
        version_num = cur.fetchone()[0]
        cur.close()
        version_id = create_node_definition_version(conn, definition_id, version_num, None, description, capabilities)
        conn.close()
        return {"version_id": str(version_id), "version_number": version_num}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/capability-gaps")
async def detect_gap(required_capability: str = Body(...), task_type: str = Body(None), domain_context: str = Body(None)):
    try:
        conn = get_connection()
        gap_id = record_capability_gap(conn, required_capability, task_type, domain_context)
        conn.close()
        return {"gap_id": str(gap_id), "status": "recorded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/proposals")
async def create_proposal(proposal_type: str = Body(...), existing_definition_id: UUID = Body(...), proposed_change: dict = Body(...), expected_benefit: str = Body(...)):
    try:
        conn = get_connection()
        proposal_id = create_evolution_proposal(conn, proposal_type, None, existing_definition_id, None, proposed_change, expected_benefit)
        conn.close()
        return {"proposal_id": str(proposal_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/proposals/{proposal_id}/candidate-definition")
async def create_candidate(proposal_id: UUID, existing_definition_id: UUID = Body(...), capabilities: list = Body(...), description: str = Body(...)):
    try:
        conn = get_connection()
        def_id, ver_id = create_candidate_node_definition(conn, proposal_id, existing_definition_id, capabilities, description)
        conn.close()
        return {"definition_id": str(def_id), "version_id": str(ver_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/instances")
async def create_instance(definition_id: UUID = Body(...), version_id: UUID = Body(...)):
    try:
        conn = get_connection()
        instance_id = create_node_instance(conn, definition_id, version_id)
        conn.close()
        return {"instance_id": str(instance_id), "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions")
async def make_decision(proposal_id: UUID = Body(...), definition_id: UUID = Body(...), version_id: UUID = Body(...), decision_type: str = Body(...), rationale: str = Body(...)):
    try:
        conn = get_connection()
        decision_id = make_evolution_decision(conn, proposal_id, definition_id, version_id, decision_type, rationale)
        conn.close()
        return {"decision_id": str(decision_id), "status": "made"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions/{decision_id}/apply")
async def apply_decision(
    decision_id: UUID,
    actor_type: str = Body("system"),
    actor_reference: str = Body("node_evolution_engine"),
    approval_request_id: Optional[str] = Body(None)
):
    try:
        from governance_enforcement import enforce_protected_action
        from typing import Optional
        from pydantic import Body
        
        conn = get_connection()
        
        # PRE-EXECUTION GOVERNANCE CHECK for node_definition_change
        governance_check = enforce_protected_action(
            conn,
            protected_action_code='node_definition_change',
            actor_type=actor_type,
            actor_reference=actor_reference,
            resource_type='evolution_decision',
            resource_id=str(decision_id),
            scope_context={},
            approval_request_id=approval_request_id
        )
        
        if not governance_check['permitted']:
            conn.close()
            return {
                "applied": False,
                "status": "governance_denied",
                "governance_decision": governance_check,
                "reason": governance_check['reason']
            }
        
        success = apply_evolution_decision(conn, decision_id)
        conn.close()
        return {
            "applied": success,
            "status": "applied" if success else "failed",
            "governance_decision": governance_check
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/definitions/{definition_id}")
async def get_definition(definition_id: UUID):
    try:
        conn = get_connection()
        defn = get_node_definition(conn, definition_id)
        conn.close()
        if not defn:
            raise HTTPException(status_code=404, detail="Not found")
        return dict(defn)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/capability-gaps")
async def list_gaps(status: str = Query("open")):
    try:
        conn = get_connection()
        gaps = get_capability_gaps(conn, status)
        conn.close()
        return {"gaps": [dict(g) for g in gaps]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/definitions/{definition_id}/history")
async def get_history(definition_id: UUID):
    try:
        conn = get_connection()
        history = get_node_evolution_history(conn, definition_id)
        conn.close()
        return {"definition_id": str(definition_id), "history": [dict(h) for h in history]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
