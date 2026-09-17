"""
SECTION 19: SELF-ORGANISATION API ENDPOINTS

FastAPI routes for structure definitions, roles, team formation, and orchestration.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from .self_organisation_engine import (
    create_structure_definition,
    create_structure_version,
    create_role,
    create_team_instantiation,
    assign_role_to_team_member,
    generate_structure_candidates,
    select_structure_for_task,
    create_execution_plan,
    record_handoff,
    record_organisational_evidence,
    create_organisational_decision,
    replace_team_member,
    dissolve_temporary_team,
    get_historical_structure_state,
    get_team_historical_state,
    check_duplicate_proposal,
)
from fabric.db import get_db_connection

router = APIRouter(prefix="/api/v1/organisation", tags=["self-organisation"])

# ============================================================================
# STRUCTURE DEFINITIONS
# ============================================================================

@router.post("/structures")
def create_structure(
    name: str,
    structure_type: str,
    purpose: str,
    applicability_scope: Dict,
    required_capabilities: Dict,
    coordination_pattern: str,
    task_workflow_constraints: Optional[Dict] = None,
    fallback_structure_id: Optional[str] = None,
    created_by: Optional[str] = None,
):
    """Create a new organisational structure definition."""
    try:
        structure_id = create_structure_definition(
            name=name,
            structure_type=structure_type,
            purpose=purpose,
            applicability_scope=applicability_scope,
            required_capabilities=required_capabilities,
            coordination_pattern=coordination_pattern,
            task_workflow_constraints=task_workflow_constraints,
            fallback_structure_id=fallback_structure_id,
            created_by=created_by,
        )
        return {
            "status": "created",
            "structure_id": structure_id,
            "name": name,
            "structure_type": structure_type,
            "lifecycle_state": "candidate"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/structures/{structure_id}")
def get_structure(structure_id: str):
    """Retrieve structure definition."""
    conn = get_db_connection()
    try:
        struct = conn.execute("""
            SELECT structure_id, name, structure_type, purpose, lifecycle_state,
                   applicability_scope, required_capabilities, coordination_pattern,
                   created_at
            FROM organisational_structures WHERE structure_id = %s
        """, (structure_id,)).fetchone()
        
        if not struct:
            raise HTTPException(status_code=404, detail="Structure not found")
        
        return {
            "structure_id": struct[0],
            "name": struct[1],
            "structure_type": struct[2],
            "purpose": struct[3],
            "lifecycle_state": struct[4],
            "applicability_scope": struct[5],
            "required_capabilities": struct[6],
            "coordination_pattern": struct[7],
            "created_at": struct[8]
        }
    finally:
        conn.close()

# ============================================================================
# VERSIONS
# ============================================================================

@router.post("/structures/{structure_id}/versions")
def create_version(
    structure_id: str,
    name: str,
    change_type: str,
    rationale: Optional[str] = None,
    triggered_by_proposal_id: Optional[str] = None,
):
    """Create a new structure version."""
    try:
        version_id = create_structure_version(
            structure_id=structure_id,
            name=name,
            change_type=change_type,
            rationale=rationale,
            triggered_by_proposal_id=triggered_by_proposal_id,
        )
        return {
            "status": "created",
            "version_id": version_id,
            "structure_id": structure_id,
            "change_type": change_type
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/structures/{structure_id}/versions")
def get_versions(structure_id: str):
    """Get version history for structure."""
    conn = get_db_connection()
    try:
        versions = conn.execute("""
            SELECT version_id, version_number, version_change_type,
                   change_rationale, created_at
            FROM organisational_structure_versions
            WHERE structure_id = %s
            ORDER BY version_number ASC
        """, (structure_id,)).fetchall()
        
        return {
            "structure_id": structure_id,
            "versions": [
                {
                    "version_id": v[0],
                    "version_number": v[1],
                    "change_type": v[2],
                    "rationale": v[3],
                    "created_at": v[4]
                }
                for v in versions
            ]
        }
    finally:
        conn.close()

# ============================================================================
# ROLES
# ============================================================================

@router.post("/roles")
def create_organisational_role(
    role_name: str,
    description: str,
    required_capabilities: List[str],
    required_attributes: Optional[Dict] = None,
):
    """Create an organisational role."""
    try:
        role_id = create_role(
            role_name=role_name,
            description=description,
            required_capabilities=required_capabilities,
            required_attributes=required_attributes,
        )
        return {
            "status": "created",
            "role_id": role_id,
            "role_name": role_name
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/roles/{role_name}")
def get_role(role_name: str):
    """Get role definition."""
    conn = get_db_connection()
    try:
        role = conn.execute("""
            SELECT role_id, role_name, description, required_capabilities
            FROM organisational_roles WHERE role_name = %s
        """, (role_name,)).fetchone()
        
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        
        return {
            "role_id": role[0],
            "role_name": role[1],
            "description": role[2],
            "required_capabilities": role[3]
        }
    finally:
        conn.close()

# ============================================================================
# TEAMS
# ============================================================================

@router.post("/teams")
def create_team(
    structure_id: str,
    task_id: Optional[str] = None,
    team_type: str = "temporary",
    expected_duration_seconds: Optional[int] = None,
    created_by: Optional[str] = None,
    actor_type: str = "system",
    actor_reference: str = "self_organisation_engine",
    approval_request_id: Optional[str] = None,
):
    """Create a team from a structure with governance enforcement."""
    try:
        from governance_enforcement import enforce_protected_action
        from db import get_connection
        
        conn = get_connection()
        
        # PRE-EXECUTION GOVERNANCE CHECK for org_restructuring
        governance_check = enforce_protected_action(
            conn,
            protected_action_code='org_restructuring',
            actor_type=actor_type,
            actor_reference=actor_reference,
            resource_type='structure',
            resource_id=structure_id,
            scope_context={'team_type': team_type, 'task_id': task_id},
            approval_request_id=approval_request_id
        )
        
        if not governance_check['permitted']:
            conn.close()
            return {
                "status": "governance_denied",
                "team_id": None,
                "structure_id": structure_id,
                "governance_decision": governance_check,
                "reason": governance_check['reason']
            }
        
        team_id = create_team_instantiation(
            structure_id=structure_id,
            structure_version_id=None,
            task_id=task_id,
            team_type=team_type,
            expected_duration_seconds=expected_duration_seconds,
            created_by=created_by,
        )
        conn.close()
        return {
            "status": "created",
            "team_id": team_id,
            "structure_id": structure_id,
            "team_type": team_type,
            "team_status": "forming",
            "governance_decision": governance_check
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/teams/{team_id}")
def get_team(team_id: str):
    """Get team information."""
    conn = get_db_connection()
    try:
        team = conn.execute("""
            SELECT team_id, structure_id, task_id, team_type, team_status,
                   created_at, end_time
            FROM team_instantiations WHERE team_id = %s
        """, (team_id,)).fetchone()
        
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # Get memberships
        memberships = conn.execute("""
            SELECT tm.membership_id, tm.node_definition_id, or.role_name,
                   tm.membership_status
            FROM team_memberships tm
            JOIN organisational_roles or ON tm.role_id = or.role_id
            WHERE tm.team_id = %s
        """, (team_id,)).fetchall()
        
        return {
            "team_id": team[0],
            "structure_id": team[1],
            "task_id": team[2],
            "team_type": team[3],
            "team_status": team[4],
            "created_at": team[5],
            "end_time": team[6],
            "members": [
                {
                    "membership_id": m[0],
                    "node_definition_id": m[1],
                    "role": m[2],
                    "status": m[3]
                }
                for m in memberships
            ]
        }
    finally:
        conn.close()

@router.post("/teams/{team_id}/members")
def add_team_member(
    team_id: str,
    node_definition_id: str,
    role_name: str,
    selection_rationale: Optional[Dict] = None,
    eligibility_score: float = 0.8,
):
    """Add member to team."""
    conn = get_db_connection()
    try:
        # Get role ID
        role = conn.execute(
            "SELECT role_id FROM organisational_roles WHERE role_name = %s",
            (role_name,)
        ).fetchone()
        
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        
        membership_id = assign_role_to_team_member(
            team_id=team_id,
            node_definition_id=node_definition_id,
            role_id=role[0],
            selection_rationale=selection_rationale,
            eligibility_score=eligibility_score,
        )
        
        return {
            "status": "member_added",
            "membership_id": membership_id,
            "team_id": team_id,
            "role": role_name
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============================================================================
# CANDIDATE GENERATION AND SELECTION
# ============================================================================

@router.post("/decisions/candidates")
def get_candidates(
    task_id: str,
    capability_requirements: Dict,
    role_requirements: List[str],
    max_candidates: int = 5,
):
    """Generate candidate structures for task."""
    try:
        candidates = generate_structure_candidates(
            task_id=task_id,
            capability_requirements=capability_requirements,
            role_requirements=role_requirements,
            max_candidates=max_candidates,
        )
        return {
            "task_id": task_id,
            "candidates": candidates,
            "count": len(candidates)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/decisions/select")
def select_structure(
    task_id: str,
    candidates: List[str],
    capability_requirements: Dict,
    role_requirements: List[str],
    explicit_constraints: Optional[Dict] = None,
):
    """Evidence-based structure selection."""
    try:
        selected_id, rationale, confidence, sufficiency = select_structure_for_task(
            task_id=task_id,
            candidates=candidates,
            capability_requirements=capability_requirements,
            role_requirements=role_requirements,
            explicit_constraints=explicit_constraints,
        )
        
        return {
            "task_id": task_id,
            "selected_structure_id": selected_id,
            "rationale": rationale,
            "confidence": confidence,
            "evidence_sufficiency": sufficiency
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# EXECUTION PLANS
# ============================================================================

@router.post("/plans")
def create_plan(
    team_id: str,
    task_id: str,
    selected_structure_id: str,
    objective: str,
    members: List[Dict],
):
    """Create execution plan for team."""
    try:
        plan_id = create_execution_plan(
            team_id=team_id,
            task_id=task_id,
            selected_structure_id=selected_structure_id,
            selected_version_id=None,
            objective=objective,
            members=members,
        )
        return {
            "status": "created",
            "plan_id": plan_id,
            "team_id": team_id,
            "objective": objective
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/plans/{plan_id}")
def get_plan(plan_id: str):
    """Get execution plan."""
    conn = get_db_connection()
    try:
        plan = conn.execute("""
            SELECT plan_id, team_id, task_id, objective,
                   selected_structure_id, members, steps,
                   plan_status, created_at
            FROM execution_plans WHERE plan_id = %s
        """, (plan_id,)).fetchone()
        
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        return {
            "plan_id": plan[0],
            "team_id": plan[1],
            "task_id": plan[2],
            "objective": plan[3],
            "selected_structure_id": plan[4],
            "members": plan[5],
            "steps": plan[6],
            "plan_status": plan[7],
            "created_at": plan[8]
        }
    finally:
        conn.close()

# ============================================================================
# HANDOFFS
# ============================================================================

@router.post("/handoffs")
def record_team_handoff(
    team_id: str,
    source_role_name: str,
    target_role_name: str,
    artifact_description: str,
    handoff_type: str,
    context_supplied: Optional[Dict] = None,
):
    """Record a handoff between team members."""
    conn = get_db_connection()
    try:
        # Get role IDs
        source_role = conn.execute(
            "SELECT role_id FROM organisational_roles WHERE role_name = %s",
            (source_role_name,)
        ).fetchone()
        
        target_role = conn.execute(
            "SELECT role_id FROM organisational_roles WHERE role_name = %s",
            (target_role_name,)
        ).fetchone()
        
        if not source_role or not target_role:
            raise HTTPException(status_code=404, detail="Role not found")
        
        handoff_id = record_handoff(
            team_id=team_id,
            source_role_id=source_role[0],
            target_role_id=target_role[0],
            artifact_description=artifact_description,
            handoff_type=handoff_type,
            context_supplied=context_supplied,
        )
        
        return {
            "status": "recorded",
            "handoff_id": handoff_id,
            "team_id": team_id,
            "handoff_type": handoff_type
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ============================================================================
# EVIDENCE AND LEARNING
# ============================================================================

@router.post("/evidence")
def record_evidence(
    structure_id: str,
    evidence_type: str,
    outcome_status: str,
    applicable_context: Dict,
    team_id: Optional[str] = None,
    quality_assessment: Optional[float] = None,
):
    """Record organisational evidence."""
    try:
        evidence_id = record_organisational_evidence(
            structure_id=structure_id,
            team_id=team_id,
            task_id=None,
            evidence_type=evidence_type,
            outcome_status=outcome_status,
            applicable_context=applicable_context,
            quality_assessment=quality_assessment,
        )
        return {
            "status": "recorded",
            "evidence_id": evidence_id,
            "structure_id": structure_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# DECISIONS
# ============================================================================

@router.post("/decisions")
def record_decision(
    task_id: str,
    work_objective: str,
    capability_requirements: Dict,
    role_requirements: List[str],
    candidate_structures: List[str],
    selected_structure_id: str,
    decision_rationale: str,
):
    """Record organisational decision."""
    try:
        decision_id = create_organisational_decision(
            task_id=task_id,
            work_objective=work_objective,
            capability_requirements=capability_requirements,
            role_requirements=role_requirements,
            candidate_structures=candidate_structures,
            selected_structure_id=selected_structure_id,
            decision_rationale=decision_rationale,
        )
        return {
            "status": "recorded",
            "decision_id": decision_id,
            "task_id": task_id,
            "selected_structure_id": selected_structure_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# MEMBER REPLACEMENT
# ============================================================================

@router.post("/teams/{team_id}/replace-member")
def replace_member(
    team_id: str,
    original_membership_id: str,
    new_node_definition_id: str,
    replacement_reason: str,
):
    """Replace unavailable team member."""
    try:
        new_membership_id = replace_team_member(
            original_membership_id=original_membership_id,
            new_node_definition_id=new_node_definition_id,
            replacement_reason=replacement_reason,
        )
        return {
            "status": "replaced",
            "original_membership_id": original_membership_id,
            "new_membership_id": new_membership_id,
            "team_id": team_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# DISSOLUTION
# ============================================================================

@router.post("/teams/{team_id}/dissolve")
def dissolve_team(team_id: str, reason: str):
    """Dissolve a temporary team."""
    try:
        dissolution_id = dissolve_temporary_team(
            team_id=team_id,
            reason=reason,
        )
        return {
            "status": "dissolved",
            "dissolution_id": dissolution_id,
            "team_id": team_id,
            "reason": reason
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ============================================================================
# HISTORICAL STATE
# ============================================================================

@router.get("/structures/{structure_id}/history")
def get_structure_history(
    structure_id: str,
    at_timestamp: Optional[str] = None,
):
    """Get historical structure state at timestamp."""
    try:
        timestamp = None
        if at_timestamp:
            timestamp = datetime.fromisoformat(at_timestamp)
        
        state = get_historical_structure_state(structure_id, timestamp)
        
        if not state:
            raise HTTPException(status_code=404, detail="No history found")
        
        return state
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/teams/{team_id}/history")
def get_team_history(
    team_id: str,
    at_timestamp: Optional[str] = None,
):
    """Get historical team state at timestamp."""
    try:
        timestamp = None
        if at_timestamp:
            timestamp = datetime.fromisoformat(at_timestamp)
        
        state = get_team_historical_state(team_id, timestamp)
        
        if not state:
            raise HTTPException(status_code=404, detail="No history found")
        
        return state
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
