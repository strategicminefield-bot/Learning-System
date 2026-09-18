"""
Objective Verification Module

Separates EXECUTION success from OBJECTIVE success.

Execution success: Did the node run and return a result?
Objective success: Did the result satisfy the task's acceptance criteria?

These are independently verifiable.
"""

import json
from typing import Tuple, Dict, Any, Optional
from uuid import UUID
import psycopg


def verify_objective_against_criteria(
    task_specification: Dict,
    result_data: Dict
) -> Tuple[str, Dict]:
    """
    Verify whether result satisfies task objective criteria.
    
    Returns: (verification_status, details)
    
    verification_status:
    - 'verified_success': Objective criteria satisfied
    - 'verified_failure': Objective criteria NOT satisfied
    - 'insufficient_evidence': Required evidence missing
    - 'unverified': Cannot determine (no criteria defined)
    """
    
    if not task_specification or not task_specification.get('acceptance_criteria'):
        return 'unverified', {
            'reason': 'No acceptance_criteria defined',
            'note': 'Task specification incomplete'
        }
    
    criteria = task_specification.get('acceptance_criteria')
    criteria_type = criteria.get('type')
    
    if not criteria_type:
        return 'unverified', {
            'reason': 'Criteria type not specified',
            'note': 'Cannot evaluate unknown criteria type'
        }
    
    # EQUALITY_CHECK: field == expected_value
    if criteria_type == 'equality_check':
        field_name = criteria.get('field')
        expected_value = criteria.get('expected_value')
        
        if not field_name or expected_value is None:
            return 'insufficient_evidence', {
                'reason': 'Equality check incomplete',
                'missing': [k for k in ['field', 'expected_value'] if k not in criteria or criteria.get(k) is None]
            }
        
        actual_value = result_data.get(field_name)
        
        if actual_value is None:
            return 'insufficient_evidence', {
                'reason': f'Required field "{field_name}" missing from result',
                'expected_field': field_name,
                'available_fields': list(result_data.keys())
            }
        
        if actual_value == expected_value:
            return 'verified_success', {
                'criteria_type': 'equality_check',
                'field': field_name,
                'expected': expected_value,
                'actual': actual_value,
                'satisfied': True
            }
        else:
            return 'verified_failure', {
                'criteria_type': 'equality_check',
                'field': field_name,
                'expected': expected_value,
                'actual': actual_value,
                'satisfied': False,
                'mismatch': True
            }
    
    # RANGE_CHECK: min <= field <= max
    if criteria_type == 'range_check':
        field_name = criteria.get('field')
        min_value = criteria.get('min')
        max_value = criteria.get('max')
        
        if not field_name or min_value is None or max_value is None:
            return 'insufficient_evidence', {
                'reason': 'Range check incomplete',
                'missing': [k for k in ['field', 'min', 'max'] if k not in criteria or criteria.get(k) is None]
            }
        
        actual_value = result_data.get(field_name)
        
        if actual_value is None:
            return 'insufficient_evidence', {
                'reason': f'Required field "{field_name}" missing from result'
            }
        
        in_range = min_value <= actual_value <= max_value
        
        if in_range:
            return 'verified_success', {
                'criteria_type': 'range_check',
                'field': field_name,
                'range': [min_value, max_value],
                'actual': actual_value,
                'satisfied': True
            }
        else:
            return 'verified_failure', {
                'criteria_type': 'range_check',
                'field': field_name,
                'range': [min_value, max_value],
                'actual': actual_value,
                'satisfied': False,
                'outside_range': True
            }
    
    # CONTAINS_CHECK: field contains expected_substring
    if criteria_type == 'contains_check':
        field_name = criteria.get('field')
        expected_substring = criteria.get('expected_substring')
        
        if not field_name or not expected_substring:
            return 'insufficient_evidence', {
                'reason': 'Contains check incomplete'
            }
        
        actual_value = result_data.get(field_name)
        
        if actual_value is None:
            return 'insufficient_evidence', {
                'reason': f'Required field "{field_name}" missing from result'
            }
        
        if str(expected_substring) in str(actual_value):
            return 'verified_success', {
                'criteria_type': 'contains_check',
                'field': field_name,
                'expected_substring': expected_substring,
                'actual': actual_value,
                'satisfied': True
            }
        else:
            return 'verified_failure', {
                'criteria_type': 'contains_check',
                'field': field_name,
                'expected_substring': expected_substring,
                'actual': actual_value,
                'satisfied': False,
                'substring_not_found': True
            }
    
    # Unknown criteria type
    return 'unverified', {
        'reason': f'Unknown criteria type: {criteria_type}',
        'supported_types': ['equality_check', 'range_check', 'contains_check']
    }


def create_objective_evidence(
    conn: psycopg.Connection,
    candidate_id: UUID,
    verification_status: str,
    verification_details: Dict,
    task_type: Optional[str] = None
) -> UUID:
    """
    Create validation_evidence record from objective verification result.
    
    CRITICAL: Evidence category depends ONLY on verification_status.
    NOT on execution_success_rate, quality_score, or node proficiency.
    """
    
    evidence_id = UUID.__new__(UUID)
    evidence_id.int = int.from_bytes(b'\x00' * 16, 'big')
    from uuid import uuid4
    evidence_id = uuid4()
    
    # Map verification status to evidence category
    if verification_status == 'verified_success':
        evidence_category = 'supportive'
        evidence_strength = 0.95  # Strong evidence: objective explicitly satisfied
        confidence = 0.95
        evidence_type = 'objective_verification'
    elif verification_status == 'verified_failure':
        evidence_category = 'contradictory'
        evidence_strength = 0.95  # Strong evidence: objective explicitly contradicted
        confidence = 0.95
        evidence_type = 'objective_verification'
    elif verification_status == 'insufficient_evidence':
        evidence_category = 'insufficient'
        evidence_strength = 0.3  # Weak: cannot determine
        confidence = 0.3
        evidence_type = 'objective_verification'
    else:  # 'unverified' or unknown
        evidence_category = 'neutral'  # Cannot conclude anything
        evidence_strength = 0.1
        confidence = 0.1
        evidence_type = 'objective_verification'
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO validation_evidence
            (evidence_id, candidate_id, evidence_type, evidence_category,
             confidence_score, evidence_strength, evidence_summary, evidence_detail, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
        """, (
            evidence_id,
            candidate_id,
            evidence_type,
            evidence_category,
            confidence,
            evidence_strength,
            f"Objective verification: {verification_status}",
            json.dumps({
                "verification_status": verification_status,
                "verification_details": verification_details,
                "evidence_basis": "Objective criteria verification (NOT execution success or quality_score)",
                "task_type": task_type
            })
        ))
        conn.commit()
    
    return evidence_id


def categorize_execution_vs_objective(
    task_specification: Dict,
    result_data: Dict,
    execution_successful: bool
) -> Dict[str, Any]:
    """
    Comprehensive categorization separating execution from objective outcomes.
    
    Returns:
    {
        'execution_status': 'successful' | 'failed',
        'objective_verification': 'verified_success' | 'verified_failure' | 'insufficient_evidence' | 'unverified',
        'execution_evidence_type': 'execution_reliability',
        'objective_evidence_type': 'objective_verification',
        'combined_interpretation': <explanation>
    }
    """
    
    execution_status = 'successful' if execution_successful else 'failed'
    objective_status, objective_details = verify_objective_against_criteria(task_specification, result_data)
    
    combinations = {
        ('successful', 'verified_success'): "Execution OK + Objective met: POSITIVE learning evidence",
        ('successful', 'verified_failure'): "Execution OK + Objective failed: Method/approach failed, NEGATIVE evidence",
        ('successful', 'insufficient_evidence'): "Execution OK but cannot verify objective: INCONCLUSIVE",
        ('successful', 'unverified'): "Execution OK but no criteria defined: NO objective evidence",
        ('failed', 'verified_success'): "Execution failed but objective somehow met: INCONSISTENT (investigate)",
        ('failed', 'verified_failure'): "Execution failed + Objective failed: Cannot determine causality",
        ('failed', 'insufficient_evidence'): "Execution failed + Missing evidence: EXECUTION_FAILURE evidence only",
        ('failed', 'unverified'): "Execution failed + No criteria: EXECUTION_FAILURE evidence only",
    }
    
    interpretation = combinations.get(
        (execution_status, objective_status),
        "Unknown combination"
    )
    
    return {
        'execution_status': execution_status,
        'objective_verification': objective_status,
        'objective_verification_details': objective_details,
        'execution_evidence_type': 'execution_reliability',
        'objective_evidence_type': 'objective_verification',
        'combined_interpretation': interpretation,
        'should_create_execution_evidence': True,
        'should_create_objective_evidence': objective_status != 'unverified'
    }
