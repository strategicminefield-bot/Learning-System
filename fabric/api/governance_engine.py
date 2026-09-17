"""
GOVERNANCE ENGINE
Section 20: Governance & Safety Controls

Enforces governance and safety rules before protected actions execute.

Core principle: All protected actions must pass governance evaluation BEFORE execution.
Authority is NOT inferred from capability, role, or success history.
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import psycopg
from psycopg.types.json import Jsonb


def get_or_create_actor(conn, actor_type: str, actor_reference: str, created_by_actor_id: Optional[str] = None) -> str:
    """Get or create a governance actor."""
    with conn.cursor() as cur:
        # Try to find existing actor
        cur.execute(
            """
            SELECT actor_id FROM governance_actors
            WHERE actor_type = %s AND actor_reference = %s AND state = 'active'
            """,
            (actor_type, actor_reference)
        )
        result = cur.fetchone()
        if result:
            return str(result[0])
        
        # Create new actor
        actor_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO governance_actors
                (actor_id, actor_type, actor_reference, state, created_by_actor_id, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (str(actor_id), actor_type, actor_reference, 'active', created_by_actor_id)
        )
        return str(actor_id)


def evaluate_governance(
    conn,
    protected_action_code: str,
    actor_type: str,
    actor_reference: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    scope_context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Evaluate governance for a protected action.
    
    Returns a decision with:
    - effect: ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
    - reasoning: Explanation
    - constraints: Applicable constraints
    - approval_required: If approval is needed
    - governance_success: If evaluation succeeded
    - governance_error: Error if evaluation failed
    """
    
    decision_id = uuid.uuid4()
    scope_context = scope_context or {}
    
    try:
        with conn.cursor() as cur:
            # Get or create actor
            actor_id = get_or_create_actor(conn, actor_type, actor_reference)
            
            # Get protected action
            cur.execute(
                "SELECT action_id FROM protected_actions WHERE action_code = %s",
                (protected_action_code,)
            )
            action_result = cur.fetchone()
            if not action_result:
                action_id = None
                default_effect = 'REQUIRE_APPROVAL'
            else:
                action_id = action_result[0]
                cur.execute(
                    "SELECT default_effect FROM protected_actions WHERE action_id = %s",
                    (action_id,)
                )
                default_effect = cur.fetchone()[0]
            
            # Check emergency restrictions
            cur.execute(
                """
                SELECT restriction_id, name FROM governance_emergency_restrictions
                WHERE state = 'active'
                AND (expires_at IS NULL OR expires_at > NOW())
                AND (%s = ANY(restricted_action_codes) OR %s = ANY(restricted_actor_types))
                LIMIT 1
                """,
                (protected_action_code, actor_type)
            )
            restriction = cur.fetchone()
            if restriction:
                # Action is under emergency restriction
                effect = 'DENY'
                reasoning = f"Emergency restriction active: {restriction[1]}"
                approval_required = False
                applied_constraints = {}
                authority_sufficient = False
                policies_evaluated = []
            else:
                # Check for authority
                cur.execute(
                    """
                    SELECT authority_id, constraints FROM governance_authority
                    WHERE actor_id = %s
                    AND protected_action_id = %s
                    AND state = 'active'
                    AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    (actor_id, action_id) if action_id else (actor_id, None)
                )
                authority = cur.fetchone()
                authority_sufficient = authority is not None
                
                # If no authority and action has high/critical risk, require approval
                if not authority_sufficient:
                    if action_id:
                        cur.execute("SELECT risk_level FROM protected_actions WHERE action_id = %s", (action_id,))
                        risk_result = cur.fetchone()
                        risk_level = risk_result[0] if risk_result else 'medium'
                    else:
                        risk_level = 'medium'
                    
                    if risk_level in ('high', 'critical'):
                        effect = 'REQUIRE_APPROVAL'
                        approval_required = True
                        reasoning = f"High-risk action requires approval ({risk_level})"
                        applied_constraints = {}
                        policies_evaluated = []
                    else:
                        effect = 'DENY'
                        reasoning = "No authority found"
                        approval_required = False
                        applied_constraints = {}
                        policies_evaluated = []
                else:
                    effect = 'ALLOW'
                    approval_required = False
                    reasoning = "Authority confirmed"
                    applied_constraints = authority[1] if authority[1] else {}
                    policies_evaluated = []

            
            # Record decision
            cur.execute(
                """
                INSERT INTO governance_decisions
                    (decision_id, protected_action_id, actor_id, resource_type, resource_id,
                     scope_context, policies_evaluated, effect, reasoning, authority_found,
                     authority_sufficient, approval_required, governance_success, evaluated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING decision_id
                """,
                (
                    str(decision_id), str(action_id) if action_id else None, str(actor_id),
                    resource_type, str(resource_id) if resource_id else None,
                    Jsonb(scope_context), policies_evaluated,
                    effect, reasoning,
                    authority is not None,
                    authority_sufficient, approval_required, True
                )
            )
            
            # Record audit
            cur.execute(
                """
                INSERT INTO governance_audit_log
                    (event_type, decision_id, actor_id, protected_action_id, resource_type, resource_id, details, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    'governance_evaluated', str(decision_id), str(actor_id),
                    str(action_id) if action_id else None,
                    resource_type, str(resource_id) if resource_id else None,
                    Jsonb({'effect': effect, 'reasoning': reasoning})
                )
            )
            
            # If approval required, create approval request
            approval_request_id = None
            if approval_required:
                approval_request_id = str(uuid.uuid4())
                approval_expires = datetime.utcnow() + timedelta(hours=24)
                cur.execute(
                    """
                    INSERT INTO governance_approval_requests
                        (approval_request_id, decision_id, protected_action_id, actor_id,
                         resource_type, resource_id, required_approval_count,
                         requested_at, expires_at, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, 'pending')
                    """,
                    (
                        approval_request_id, str(decision_id), str(action_id) if action_id else None,
                        str(actor_id), resource_type, str(resource_id) if resource_id else None,
                        1, approval_expires
                    )
                )
                
                cur.execute(
                    """
                    INSERT INTO governance_audit_log
                        (event_type, approval_request_id, actor_id, protected_action_id,
                         resource_type, resource_id, details, recorded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        'approval_requested', approval_request_id, str(actor_id),
                        str(action_id) if action_id else None,
                        resource_type, str(resource_id) if resource_id else None,
                        Jsonb({'decision_id': str(decision_id)})
                    )
                )
            
            conn.commit()
            
            return {
                'decision_id': str(decision_id),
                'effect': effect,
                'reasoning': reasoning,
                'constraints': applied_constraints,
                'approval_required': approval_required,
                'approval_request_id': approval_request_id,
                'actor_id': actor_id,
                'action_id': str(action_id) if action_id else None,
                'governance_success': True,
                'governance_error': None,
                'authority_found': authority_sufficient,
                'policies_evaluated': len(policies_evaluated)
            }
    
    except Exception as e:
        conn.rollback()
        return {
            'decision_id': str(decision_id),
            'effect': 'DENY',
            'reasoning': 'Governance evaluation failed; failing closed',
            'constraints': {},
            'approval_required': False,
            'governance_success': False,
            'governance_error': str(e),
            'authority_found': False
        }


def approve_action(conn, approval_request_id: str, approver_type: str, approver_reference: str) -> Dict[str, Any]:
    """Approve a pending approval request."""
    try:
        with conn.cursor() as cur:
            # Get or create approver actor
            approver_id = get_or_create_actor(conn, approver_type, approver_reference)
            
            # Get approval request
            cur.execute(
                """
                SELECT approval_request_id, status, decision_id, actor_id FROM governance_approval_requests
                WHERE approval_request_id = %s
                """,
                (approval_request_id,)
            )
            approval = cur.fetchone()
            if not approval:
                return {'success': False, 'error': 'Approval request not found'}
            
            if approval[1] != 'pending':
                return {'success': False, 'error': f'Approval already {approval[1]}'}
            
            # Check for self-approval (proposer cannot approve themselves)
            if approver_id == approval[3]:
                return {'success': False, 'error': 'Actor cannot approve their own request (separation of duties)'}
            
            # Record approval decision
            cur.execute(
                """
                INSERT INTO governance_approval_decisions
                    (approval_decision_id, approval_request_id, approver_actor_id, decision, decided_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (str(uuid.uuid4()), approval_request_id, approver_id, 'approved')
            )
            
            # Update approval request
            cur.execute(
                """
                UPDATE governance_approval_requests
                SET status = 'approved', approval_count = approval_count + 1
                WHERE approval_request_id = %s
                """,
                (approval_request_id,)
            )
            
            # Record audit
            cur.execute(
                """
                INSERT INTO governance_audit_log
                    (event_type, approval_request_id, details, recorded_at)
                VALUES (%s, %s, %s, NOW())
                """,
                ('approved', approval_request_id, Jsonb({'approver': approver_reference}))
            )
            
            conn.commit()
            return {'success': True, 'decision_id': str(approval[2])}
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}


def revoke_authority(conn, authority_id: str, reason: str) -> Dict[str, Any]:
    """Revoke an authority grant."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE governance_authority
                SET state = 'revoked', revoked_at = NOW(), reason_for_revocation = %s
                WHERE authority_id = %s
                """,
                (reason, authority_id)
            )
            
            # Record audit
            cur.execute(
                """
                INSERT INTO governance_audit_log
                    (event_type, authority_id, details, recorded_at)
                VALUES (%s, %s, %s, NOW())
                """,
                ('authority_revoked', authority_id, Jsonb({'reason': reason}))
            )
            
            conn.commit()
            return {'success': True}
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}


def create_emergency_restriction(conn, name: str, action_codes: List[str], actor_types: List[str], 
                                creator_type: str, creator_reference: str, duration_hours: int = 24) -> Dict[str, Any]:
    """Create an emergency restriction on autonomous operations."""
    try:
        with conn.cursor() as cur:
            # Get or create creator actor
            creator_id = get_or_create_actor(conn, creator_type, creator_reference)
            
            restriction_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
            
            cur.execute(
                """
                INSERT INTO governance_emergency_restrictions
                    (restriction_id, name, restricted_action_codes, restricted_actor_types,
                     created_by_actor_id, created_at, expires_at, state)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, 'active')
                """,
                (restriction_id, name, action_codes, actor_types, creator_id, expires_at)
            )
            
            # Record audit
            cur.execute(
                """
                INSERT INTO governance_audit_log
                    (event_type, details, recorded_at)
                VALUES (%s, %s, NOW())
                """,
                ('emergency_restriction', Jsonb({'name': name, 'action_codes': action_codes}))
            )
            
            conn.commit()
            return {'success': True, 'restriction_id': restriction_id}
    
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}


def verify_approval_valid(conn, approval_request_id: str) -> bool:
    """Verify that an approval is still valid before execution."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, expires_at FROM governance_approval_requests
            WHERE approval_request_id = %s
            """,
            (approval_request_id,)
        )
        result = cur.fetchone()
        if not result:
            return False
        
        status, expires_at = result
        if status != 'approved':
            return False
        
        if expires_at and expires_at < datetime.utcnow():
            return False
        
        return True
