"""
Section 17: Validation/Promotion Engine
Determines whether accumulated evidence is sufficient to change operational status of strategies, methods, knowledge.
"""

import json
import hashlib
from typing import Optional, Dict, List, Tuple, Any
from uuid import uuid4, UUID
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

def create_validation_candidate(
    conn,
    candidate_type: str,  # strategy, strategy_version, knowledge_entity, orchestration_config
    candidate_ref_id: UUID,
    candidate_name: str,
    domain_applicability: Optional[str] = None,
    applicable_task_types: Optional[List[str]] = None,
    source_node_id: Optional[UUID] = None,
    source_experiment_id: Optional[UUID] = None,
    source_operational_evidence: bool = False
) -> UUID:
    """Create immutable validation candidate."""
    candidate_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO validation_candidates (
                candidate_id, candidate_type, candidate_ref_id, candidate_name,
                domain_applicability, applicable_task_types,
                source_node_id, source_experiment_id, source_operational_evidence,
                current_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            candidate_id, candidate_type, candidate_ref_id, candidate_name,
            domain_applicability, json.dumps(applicable_task_types) if applicable_task_types else None,
            source_node_id, source_experiment_id, source_operational_evidence,
            'eligible'
        ))
        
        # Record creation in history
        cur.execute("""
            INSERT INTO validation_history (candidate_id, event_type, new_status)
            VALUES (%s, %s, %s)
        """, (candidate_id, 'candidate_created', 'eligible'))
        
        conn.commit()
        return candidate_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def add_validation_evidence(
    conn,
    candidate_id: UUID,
    evidence_type: str,  # experimental_supportive, experimental_contradictory, operational, cross_node
    evidence_category: str,  # supportive, contradictory, neutral, insufficient
    confidence_score: float,  # 0-1
    evidence_strength: float,  # 0-1
    source_experiment_id: Optional[UUID] = None,
    source_experiment_analysis_id: Optional[UUID] = None,
    source_operational_outcome_id: Optional[UUID] = None,
    source_node_id: Optional[UUID] = None,
    cross_node_reproduced: bool = False,
    evidence_summary: Optional[str] = None,
    evidence_detail: Optional[Dict] = None,
    observation_counts: Optional[Dict[str, int]] = None
) -> UUID:
    """Record evidence supporting or contradicting a validation candidate."""
    evidence_id = uuid4()
    cur = conn.cursor()
    try:
        observation_counts = observation_counts or {}
        supporting_count = observation_counts.get('supporting', 0)
        contradictory_count = observation_counts.get('contradictory', 0)
        
        cur.execute("""
            INSERT INTO validation_evidence (
                evidence_id, candidate_id, evidence_type, evidence_category,
                source_experiment_id, source_experiment_analysis_id,
                source_operational_outcome_id, source_node_id,
                cross_node_reproduced, confidence_score, evidence_strength,
                supporting_observation_count, contradictory_observation_count,
                evidence_summary, evidence_detail
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            evidence_id, candidate_id, evidence_type, evidence_category,
            source_experiment_id, source_experiment_analysis_id,
            source_operational_outcome_id, source_node_id,
            cross_node_reproduced, confidence_score, evidence_strength,
            supporting_count, contradictory_count,
            evidence_summary, json.dumps(evidence_detail) if evidence_detail else None
        ))
        conn.commit()
        return evidence_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def check_validation_eligibility(
    conn,
    candidate_id: UUID,
    min_evidence_required: int = 1
) -> Tuple[bool, Dict]:
    """Check if candidate is eligible for validation."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    eligibility_id = uuid4()
    
    try:
        # Check candidate exists and is not retired/superseded
        cur.execute("""
            SELECT candidate_id, current_status, retired_at, superseded_by_candidate_id
            FROM validation_candidates WHERE candidate_id = %s
        """, (candidate_id,))
        candidate = cur.fetchone()
        
        if not candidate:
            result = {
                'is_eligible': False,
                'candidate_exists': False,
                'reason': 'Candidate does not exist'
            }
            cur.execute("""
                INSERT INTO validation_eligibility (
                    eligibility_id, candidate_id, is_eligible,
                    candidate_exists, ineligibility_reason
                ) VALUES (%s, %s, %s, %s, %s)
            """, (eligibility_id, candidate_id, False, False, 'Candidate does not exist'))
            conn.commit()
            return False, result
        
        candidate_exists = True
        not_retired = candidate['retired_at'] is None
        not_superseded = candidate['superseded_by_candidate_id'] is None
        
        # Count evidence
        cur.execute("""
            SELECT COUNT(*) as cnt FROM validation_evidence
            WHERE candidate_id = %s
        """, (candidate_id,))
        evidence_count = cur.fetchone()['cnt']
        evidence_sufficient = evidence_count >= min_evidence_required
        
        # Check experimental results complete if from experiment
        cur.execute("""
            SELECT source_experiment_id FROM validation_candidates WHERE candidate_id = %s
        """, (candidate_id,))
        source_exp = cur.fetchone()['source_experiment_id']
        
        exp_complete = True
        if source_exp:
            cur.execute("""
                SELECT status FROM experiments WHERE experiment_id = %s
            """, (source_exp,))
            exp = cur.fetchone()
            exp_complete = exp and exp['status'] in ['completed', 'concluded']
        
        is_eligible = (
            candidate_exists and not_retired and not_superseded and
            evidence_sufficient and exp_complete
        )
        
        result = {
            'is_eligible': is_eligible,
            'candidate_exists': candidate_exists,
            'not_retired': not_retired,
            'not_superseded': not_superseded,
            'evidence_count': evidence_count,
            'evidence_sufficient': evidence_sufficient,
            'experiment_complete': exp_complete
        }
        
        # Record eligibility check
        cur.execute("""
            INSERT INTO validation_eligibility (
                eligibility_id, candidate_id, is_eligible,
                candidate_exists, evidence_count_sufficient,
                actual_evidence_count, experimental_results_complete,
                ineligibility_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            eligibility_id, candidate_id, is_eligible,
            candidate_exists, evidence_sufficient, evidence_count,
            exp_complete,
            None if is_eligible else f"Eligibility failed: {result}"
        ))
        conn.commit()
        return is_eligible, result
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def assess_evidence_sufficiency(
    conn,
    candidate_id: UUID,
    rule_config_version_id: Optional[UUID] = None
) -> Tuple[bool, Dict]:
    """Assess whether evidence is sufficient for promotion decision."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    sufficiency_id = uuid4()
    
    try:
        # Get applicable rule config
        if not rule_config_version_id:
            cur.execute("""
                SELECT config_id FROM validation_rule_configs
                WHERE active = TRUE ORDER BY created_at DESC LIMIT 1
            """)
            rule = cur.fetchone()
            rule_config_version_id = rule['config_id'] if rule else None
        
        if not rule_config_version_id:
            # No rules configured, insufficient by default
            return False, {'reason': 'No validation rules configured', 'sufficiency_level': 'insufficient'}
        
        cur.execute("""
            SELECT * FROM validation_rule_configs WHERE config_id = %s
        """, (rule_config_version_id,))
        rule = cur.fetchone()
        
        # Get evidence summary
        cur.execute("""
            SELECT 
                evidence_category, COUNT(*) as cnt,
                AVG(confidence_score) as avg_confidence,
                AVG(evidence_strength) as avg_strength,
                COUNT(DISTINCT source_node_id) as distinct_nodes,
                MAX(evidence_timestamp) as most_recent
            FROM validation_evidence
            WHERE candidate_id = %s
            GROUP BY evidence_category
        """, (candidate_id,))
        
        evidence_by_category = {row['evidence_category']: row for row in cur.fetchall()}
        
        supporting = evidence_by_category.get('supportive', {})
        contradictory = evidence_by_category.get('contradictory', {})
        
        supporting_count = supporting.get('cnt', 0)
        contradictory_count = contradictory.get('cnt', 0)
        avg_confidence = float(supporting.get('avg_confidence', 0) or 0)
        avg_strength = float(supporting.get('avg_strength', 0) or 0)
        distinct_nodes = supporting.get('distinct_nodes', 0) or 0
        
        # Check sufficiency against thresholds
        min_obs_met = supporting_count >= rule['min_supporting_observations']
        min_conf_met = avg_confidence >= float(rule['min_average_confidence'])
        min_strength_met = avg_strength >= float(rule['min_evidence_strength'])
        independent_met = rule['independent_node_requirement'] == 0 or distinct_nodes >= rule['independent_node_requirement']
        contradiction_met = contradictory_count <= rule['max_contradictions_allowed']
        
        # Determine sufficiency level
        if min_obs_met and min_conf_met and min_strength_met and independent_met and contradiction_met:
            sufficient = True
            level = 'high' if supporting_count >= rule['min_supporting_observations'] * 2 else 'adequate'
        elif supporting_count > 0 and min_conf_met:
            sufficient = False
            level = 'low'
        else:
            sufficient = False
            level = 'insufficient'
        
        result = {
            'evidence_sufficient': sufficient,
            'sufficiency_level': level,
            'supporting_count': supporting_count,
            'contradictory_count': contradictory_count,
            'avg_confidence': avg_confidence,
            'avg_strength': avg_strength,
            'distinct_nodes': distinct_nodes,
            'checks': {
                'min_observations_met': min_obs_met,
                'min_confidence_met': min_conf_met,
                'min_strength_met': min_strength_met,
                'independent_nodes_met': independent_met,
                'contradictions_acceptable': contradiction_met
            }
        }
        
        # Record assessment
        cur.execute("""
            INSERT INTO validation_evidence_sufficiency (
                sufficiency_id, candidate_id, rule_config_version_id,
                min_supporting_observations, actual_supporting_observations,
                min_average_confidence, actual_average_confidence,
                min_evidence_strength, actual_evidence_strength,
                independent_node_requirement, distinct_nodes_supporting,
                independent_requirement_met,
                max_contradictions_allowed, actual_contradictions,
                evidence_sufficient, sufficiency_level, sufficiency_detail
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            sufficiency_id, candidate_id, rule_config_version_id,
            rule['min_supporting_observations'], supporting_count,
            rule['min_average_confidence'], avg_confidence,
            rule['min_evidence_strength'], avg_strength,
            rule['independent_node_requirement'], distinct_nodes,
            independent_met,
            rule['max_contradictions_allowed'], contradictory_count,
            sufficient, level, json.dumps(result)
        ))
        conn.commit()
        return sufficient, result
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def make_validation_decision(
    conn,
    candidate_id: UUID,
    decision_type: str,  # promote, retain_candidate, restrict, dispute, reject, retire, repeat_experiment, insufficient_evidence
    rationale: str,
    evidence_summary: Optional[Dict] = None,
    authority: str = 'system',
    requires_approval: bool = False
) -> UUID:
    """Create immutable validation decision."""
    decision_id = uuid4()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get evidence counts
        cur.execute("""
            SELECT 
                SUM(CASE WHEN evidence_category = 'supportive' THEN 1 ELSE 0 END) as supporting,
                SUM(CASE WHEN evidence_category = 'contradictory' THEN 1 ELSE 0 END) as contradictory,
                SUM(CASE WHEN evidence_category = 'neutral' THEN 1 ELSE 0 END) as neutral
            FROM validation_evidence WHERE candidate_id = %s
        """, (candidate_id,))
        counts = cur.fetchone()
        
        supporting_count = counts['supporting'] or 0
        contradictory_count = counts['contradictory'] or 0
        neutral_count = counts['neutral'] or 0
        contradictions_present = contradictory_count > 0
        
        # Insert decision
        cur.execute("""
            INSERT INTO validation_decisions (
                decision_id, candidate_id, decision_type,
                supporting_evidence_count, contradictory_evidence_count, neutral_evidence_count,
                contradictions_present, rationale, decision_authority,
                requires_approval
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            decision_id, candidate_id, decision_type,
            supporting_count, contradictory_count, neutral_count,
            contradictions_present, rationale, authority,
            requires_approval
        ))
        
        # Update candidate status
        cur.execute("""
            UPDATE validation_candidates
            SET last_validation_decision_id = %s
            WHERE candidate_id = %s
        """, (decision_id, candidate_id))
        
        # Record in history
        cur.execute("""
            INSERT INTO validation_history (candidate_id, event_type, decision_id, new_status)
            VALUES (%s, %s, %s, %s)
        """, (candidate_id, 'decision_made', decision_id, decision_type))
        
        conn.commit()
        return decision_id
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def apply_validation_decision(
    conn,
    decision_id: UUID,
    applied_by: str = 'system'
) -> bool:
    """Apply validation decision to production state."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get decision and candidate
        cur.execute("""
            SELECT vd.*, vc.current_status, vc.candidate_type, vc.candidate_ref_id
            FROM validation_decisions vd
            JOIN validation_candidates vc ON vd.candidate_id = vc.candidate_id
            WHERE vd.decision_id = %s
        """, (decision_id,))
        
        decision = cur.fetchone()
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")
        
        decision_type = decision['decision_type']
        candidate_id = decision['candidate_id']
        
        # Apply decision based on type
        if decision_type == 'promote':
            new_status = 'promoted'
        elif decision_type == 'restrict':
            new_status = 'restricted'
        elif decision_type == 'retire':
            new_status = 'retired'
        elif decision_type == 'dispute':
            new_status = 'disputed'
        elif decision_type == 'insufficient_evidence':
            new_status = 'eligible'  # Remains eligible, not promoted
        elif decision_type == 'retain_candidate':
            new_status = decision['current_status']
        else:
            new_status = decision['current_status']
        
        # Update candidate status
        update_time = datetime.utcnow() if new_status == 'retired' else None
        cur.execute("""
            UPDATE validation_candidates
            SET current_status = %s, retired_at = %s
            WHERE candidate_id = %s
        """, (new_status, update_time, candidate_id))
        
        # Mark decision as applied
        cur.execute("""
            UPDATE validation_decisions
            SET decision_status = %s, applied_at = %s, applied_by = %s
            WHERE decision_id = %s
        """, (
            'applied', datetime.utcnow(), applied_by, decision_id
        ))
        
        # Record in history
        cur.execute("""
            INSERT INTO validation_history (
                candidate_id, event_type, decision_id,
                previous_status, new_status
            ) VALUES (%s, %s, %s, %s, %s)
        """, (candidate_id, 'decision_applied', decision_id, decision['current_status'], new_status))
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def request_repeat_experiment(
    conn,
    candidate_id: UUID,
    decision_id: UUID,
    hypothesis: str,
    objective: str,
    min_sample_size: int = 10,
    max_enrolled_tasks: int = 100
) -> UUID:
    """Request a repeat experiment when validation is inconclusive."""
    repeat_request_id = uuid4()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO validation_repeat_experiments (
                repeat_request_id, candidate_id, validation_decision_id,
                experiment_hypothesis, experiment_objective,
                min_sample_size, max_enrolled_tasks,
                request_status, reason_for_repeat
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            repeat_request_id, candidate_id, decision_id,
            hypothesis, objective,
            min_sample_size, max_enrolled_tasks,
            'requested', 'Validation inconclusive; repeat experiment requested'
        ))
        conn.commit()
        return repeat_request_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def get_validation_candidate(conn, candidate_id: UUID) -> Optional[Dict]:
    """Retrieve complete validation candidate with history."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM validation_candidates WHERE candidate_id = %s
        """, (candidate_id,))
        return cur.fetchone()
    finally:
        cur.close()

def get_validation_decision(conn, decision_id: UUID) -> Optional[Dict]:
    """Retrieve complete validation decision with full context."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM validation_decisions WHERE decision_id = %s
        """, (decision_id,))
        return cur.fetchone()
    finally:
        cur.close()

def get_candidate_history(conn, candidate_id: UUID) -> List[Dict]:
    """Get complete audit trail for a candidate."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM validation_history
            WHERE candidate_id = %s
            ORDER BY recorded_at ASC
        """, (candidate_id,))
        return cur.fetchall()
    finally:
        cur.close()
