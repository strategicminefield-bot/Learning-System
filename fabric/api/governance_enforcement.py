"""
GOVERNANCE ENFORCEMENT HELPER

Shared pre-execution enforcement point for all protected Section 15-19 actions.

Usage: Call enforce_protected_action() BEFORE any protected state mutation.
"""

import psycopg
from typing import Optional, Dict, Any
from governance_engine import evaluate_governance, verify_approval_valid


def enforce_protected_action(
    conn: psycopg.Connection,
    protected_action_code: str,
    actor_type: str,
    actor_reference: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    scope_context: Optional[Dict] = None,
    approval_request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    PRE-EXECUTION GOVERNANCE ENFORCEMENT BOUNDARY
    
    Called BEFORE any protected mutation in Sections 15-19.
    
    Returns:
    {
        'permitted': bool,           # ALLOW or REQUIRE_APPROVAL = True, DENY = False
        'effect': str,              # ALLOW, ALLOW_WITH_CONSTRAINTS, REQUIRE_APPROVAL, DENY
        'decision_id': str,
        'approval_request_id': str or None,
        'constraints': dict,
        'reason': str               # For logging
    }
    
    If permitted=False, DO NOT EXECUTE the protected action.
    If effect=REQUIRE_APPROVAL without approval_request_id, action blocked.
    If approval_request_id provided, verify it first.
    """
    
    # If approval was provided, verify it first (TOCTOU protection)
    if approval_request_id:
        approval_valid = verify_approval_valid(conn, approval_request_id)
        if not approval_valid:
            return {
                'permitted': False,
                'effect': 'DENY',
                'decision_id': None,
                'approval_request_id': approval_request_id,
                'constraints': {},
                'reason': 'Approval invalid/expired/revoked'
            }
    
    # Evaluate governance
    decision = evaluate_governance(
        conn,
        protected_action_code,
        actor_type,
        actor_reference,
        resource_type,
        resource_id,
        scope_context
    )
    
    if not decision['governance_success']:
        # Governance failure = fail-closed
        return {
            'permitted': False,
            'effect': 'DENY',
            'decision_id': decision.get('decision_id'),
            'approval_request_id': None,
            'constraints': {},
            'reason': f"Governance evaluation failed: {decision.get('governance_error')}"
        }
    
    effect = decision['effect']
    decision_id = decision['decision_id']
    
    # Apply decision
    if effect == 'DENY':
        return {
            'permitted': False,
            'effect': 'DENY',
            'decision_id': decision_id,
            'approval_request_id': None,
            'constraints': {},
            'reason': decision.get('reasoning', 'Action denied by governance')
        }
    
    elif effect == 'REQUIRE_APPROVAL':
        # If no approval provided, action blocked
        if not approval_request_id:
            return {
                'permitted': False,
                'effect': 'REQUIRE_APPROVAL',
                'decision_id': decision_id,
                'approval_request_id': decision.get('approval_request_id'),
                'constraints': {},
                'reason': 'Approval required but not provided'
            }
        # If approval provided, already verified above
        # Fall through to ALLOW
    
    # ALLOW or ALLOW_WITH_CONSTRAINTS
    return {
        'permitted': True,
        'effect': effect,
        'decision_id': decision_id,
        'approval_request_id': approval_request_id,
        'constraints': decision.get('constraints', {}),
        'reason': decision.get('reasoning', 'Action permitted by governance')
    }
