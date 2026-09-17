"""
GOVERNANCE ENDPOINTS
Section 20: Governance & Safety Controls API

Provides HTTP endpoints for governance management and enforcement.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg
import os
from governance_engine import (
    evaluate_governance,
    approve_action,
    revoke_authority,
    create_emergency_restriction,
    verify_approval_valid,
    get_or_create_actor
)

router = APIRouter(prefix='/api/v1/governance', tags=['governance'])

DATABASE_URL = os.environ['DATABASE_URL']


def get_db():
    """Database connection dependency."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class GovernanceEvaluationRequest(BaseModel):
    protected_action_code: str
    actor_type: str
    actor_reference: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    scope_context: Optional[Dict[str, Any]] = None


class GovernanceDecision(BaseModel):
    decision_id: str
    effect: str  # ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
    reasoning: str
    constraints: Dict = {}
    approval_required: bool
    approval_request_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    approval_request_id: str
    approver_type: str
    approver_reference: str


class RevocationRequest(BaseModel):
    authority_id: str
    reason: str


class EmergencyRestrictionRequest(BaseModel):
    name: str
    action_codes: List[str]
    actor_types: List[str]
    creator_type: str
    creator_reference: str
    duration_hours: int = 24


# ============================================================================
# CORE GOVERNANCE ENDPOINTS
# ============================================================================

@router.post('/evaluate')
def evaluate_protected_action(req: GovernanceEvaluationRequest):
    """Evaluate governance for a protected action."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            result = evaluate_governance(
                conn,
                req.protected_action_code,
                req.actor_type,
                req.actor_reference,
                req.resource_type,
                req.resource_id,
                req.scope_context
            )
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/approve')
def approve_pending_action(req: ApprovalRequest):
    """Approve a pending governed action."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            result = approve_action(
                conn,
                req.approval_request_id,
                req.approver_type,
                req.approver_reference
            )
            if not result['success']:
                raise HTTPException(status_code=400, detail=result['error'])
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/authority/revoke')
def revoke_actor_authority(req: RevocationRequest):
    """Revoke an authority grant."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            result = revoke_authority(conn, req.authority_id, req.reason)
            if not result['success']:
                raise HTTPException(status_code=400, detail=result['error'])
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/emergency-restriction/create')
def create_emergency(req: EmergencyRestrictionRequest):
    """Create an emergency restriction on autonomous operations."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            result = create_emergency_restriction(
                conn,
                req.name,
                req.action_codes,
                req.actor_types,
                req.creator_type,
                req.creator_reference,
                req.duration_hours
            )
            if not result['success']:
                raise HTTPException(status_code=400, detail=result['error'])
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# QUERY ENDPOINTS
# ============================================================================

@router.get('/decisions/{decision_id}')
def get_governance_decision(decision_id: str):
    """Get a specific governance decision."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT decision_id, protected_action_id, actor_id, effect, reasoning,
                           authority_found, approval_required, evaluated_at
                    FROM governance_decisions
                    WHERE decision_id = %s
                    """,
                    (decision_id,)
                )
                result = cur.fetchone()
                if not result:
                    raise HTTPException(status_code=404, detail='Decision not found')
                
                return {
                    'decision_id': str(result[0]),
                    'protected_action_id': str(result[1]),
                    'actor_id': str(result[2]),
                    'effect': result[3],
                    'reasoning': result[4],
                    'authority_found': result[5],
                    'approval_required': result[6],
                    'evaluated_at': result[7].isoformat()
                }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/approvals/pending')
def get_pending_approvals():
    """Get pending approval requests."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT approval_request_id, actor_id, protected_action_id,
                           resource_type, requested_at, expires_at
                    FROM governance_approval_requests
                    WHERE status = 'pending'
                    ORDER BY requested_at DESC
                    LIMIT 100
                    """
                )
                results = cur.fetchall()
                
                return {
                    'pending_approvals': [
                        {
                            'approval_request_id': str(r[0]),
                            'actor_id': str(r[1]),
                            'protected_action_id': str(r[2]),
                            'resource_type': r[3],
                            'requested_at': r[4].isoformat(),
                            'expires_at': r[5].isoformat() if r[5] else None
                        }
                        for r in results
                    ],
                    'count': len(results)
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/emergency-restrictions')
def get_active_restrictions():
    """Get active emergency restrictions."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT restriction_id, name, restricted_action_codes, restricted_actor_types,
                           created_at, expires_at
                    FROM governance_emergency_restrictions
                    WHERE state = 'active'
                    AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY created_at DESC
                    """
                )
                results = cur.fetchall()
                
                return {
                    'restrictions': [
                        {
                            'restriction_id': str(r[0]),
                            'name': r[1],
                            'action_codes': r[2],
                            'actor_types': r[3],
                            'created_at': r[4].isoformat(),
                            'expires_at': r[5].isoformat() if r[5] else None
                        }
                        for r in results
                    ],
                    'count': len(results)
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/health')
def governance_health():
    """Get governance system health status."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Check tables exist
                cur.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name IN (
                        'governance_actors', 'protected_actions', 'governance_policies',
                        'governance_authority', 'governance_decisions'
                    )
                    """
                )
                tables_found = cur.fetchone()[0]
                
                # Check active restrictions
                cur.execute(
                    """
                    SELECT COUNT(*) FROM governance_emergency_restrictions
                    WHERE state = 'active' AND (expires_at IS NULL OR expires_at > NOW())
                    """
                )
                active_restrictions = cur.fetchone()[0]
                
                # Check pending approvals
                cur.execute(
                    """
                    SELECT COUNT(*) FROM governance_approval_requests
                    WHERE status = 'pending'
                    """
                )
                pending_approvals = cur.fetchone()[0]
                
                return {
                    'status': 'ok' if tables_found == 5 else 'degraded',
                    'governance_operational': tables_found == 5,
                    'tables_found': tables_found,
                    'active_restrictions': active_restrictions,
                    'pending_approvals': pending_approvals,
                    'timestamp': psycopg.sql.SQL('NOW()').as_string(conn)
                }
    except Exception as e:
        return {
            'status': 'error',
            'governance_operational': False,
            'error': str(e)
        }


@router.get('/audit/recent')
def get_recent_audit_events(limit: int = 100):
    """Get recent governance audit events."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT audit_id, event_type, actor_id, protected_action_id,
                           resource_type, recorded_at
                    FROM governance_audit_log
                    ORDER BY recorded_at DESC
                    LIMIT %s
                    """,
                    (min(limit, 1000),)
                )
                results = cur.fetchall()
                
                return {
                    'events': [
                        {
                            'audit_id': str(r[0]),
                            'event_type': r[1],
                            'actor_id': str(r[2]) if r[2] else None,
                            'protected_action_id': str(r[3]) if r[3] else None,
                            'resource_type': r[4],
                            'recorded_at': r[5].isoformat()
                        }
                        for r in results
                    ],
                    'count': len(results)
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/verify-approval')
def verify_approval_status(approval_request_id: str):
    """Verify that an approval is still valid."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            valid = verify_approval_valid(conn, approval_request_id)
            return {
                'approval_request_id': approval_request_id,
                'valid': valid
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
