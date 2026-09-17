"""
SECTION 19: SELF-ORGANISATION ENGINE

Core functions for:
- Organisational structure definition and versioning
- Role assignment and team formation
- Structure candidate generation from evidence
- Evidence-based structure selection
- Execution plan generation
- Team coordination and handoffs
- Organisational learning and feedback
- Structural evolution and reorganisation
- Authority boundary enforcement
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import uuid

from fabric.db import get_db_connection

# ============================================================================
# 1. STRUCTURE DEFINITION AND MANAGEMENT
# ============================================================================

def create_structure_definition(
    name: str,
    structure_type: str,
    purpose: str,
    applicability_scope: Dict[str, Any],
    required_capabilities: Dict[str, Any],
    coordination_pattern: str,
    task_workflow_constraints: Optional[Dict] = None,
    fallback_structure_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> str:
    """Create a new organisational structure definition."""
    conn = get_db_connection()
    try:
        structure_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO organisational_structures (
                structure_id, name, structure_type, purpose, applicability_scope,
                required_capabilities, coordination_pattern, task_workflow_constraints,
                fallback_structure_id, lifecycle_state, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'candidate', %s
            )
        """, (
            structure_id, name, structure_type, purpose,
            json.dumps(applicability_scope),
            json.dumps(required_capabilities),
            coordination_pattern,
            json.dumps(task_workflow_constraints) if task_workflow_constraints else None,
            fallback_structure_id,
            created_by
        ))
        conn.commit()
        return structure_id
    finally:
        conn.close()

def create_structure_version(
    structure_id: str,
    name: str,
    change_type: str,  # new, refinement, specialisation, generalisation, supersession
    rationale: Optional[str] = None,
    triggered_by_proposal_id: Optional[str] = None,
    triggered_by_evidence: Optional[Dict] = None,
    snapshot_data: Optional[Dict] = None,
) -> str:
    """Create a new immutable version of a structure."""
    conn = get_db_connection()
    try:
        version_id = str(uuid.uuid4())
        
        # Get current structure info
        struct = conn.execute(
            "SELECT name, structure_type, purpose, coordination_pattern, required_capabilities, task_workflow_constraints FROM organisational_structures WHERE structure_id = %s",
            (structure_id,)
        ).fetchone()
        
        if not struct:
            raise ValueError(f"Structure {structure_id} not found")
        
        # Get next version number
        version_num = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM organisational_structure_versions WHERE structure_id = %s",
            (structure_id,)
        ).fetchone()[0]
        
        # Get parent version
        parent_version = conn.execute(
            "SELECT version_id FROM organisational_structure_versions WHERE structure_id = %s ORDER BY version_number DESC LIMIT 1",
            (structure_id,)
        ).fetchone()
        
        conn.execute("""
            INSERT INTO organisational_structure_versions (
                version_id, structure_id, version_number, parent_version_id,
                name, structure_type, purpose, coordination_pattern,
                required_capabilities, task_workflow_constraints,
                version_change_type, change_rationale, triggered_by_proposal_id,
                triggered_by_evidence
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            version_id, structure_id, version_num,
            parent_version[0] if parent_version else None,
            struct[0], struct[1], struct[2], struct[3],
            struct[4], struct[5],
            change_type, rationale, triggered_by_proposal_id,
            json.dumps(triggered_by_evidence) if triggered_by_evidence else None
        ))
        conn.commit()
        return version_id
    finally:
        conn.close()

# ============================================================================
# 2. ROLE MANAGEMENT
# ============================================================================

def create_role(
    role_name: str,
    description: str,
    required_capabilities: List[str],
    required_attributes: Optional[Dict] = None,
    responsibility_scope: Optional[Dict] = None,
    authority_scope: Optional[Dict] = None,
) -> str:
    """Create an organisational role."""
    conn = get_db_connection()
    try:
        role_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO organisational_roles (
                role_id, role_name, description, required_capabilities,
                required_attributes, responsibility_scope, authority_scope
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            role_id, role_name, description,
            required_capabilities,
            json.dumps(required_attributes) if required_attributes else None,
            json.dumps(responsibility_scope) if responsibility_scope else None,
            json.dumps(authority_scope) if authority_scope else None
        ))
        conn.commit()
        return role_id
    finally:
        conn.close()

# ============================================================================
# 3. TEAM FORMATION
# ============================================================================

def create_team_instantiation(
    structure_id: str,
    structure_version_id: Optional[str],
    task_id: Optional[str],
    team_type: str = "temporary",  # temporary, persistent
    expected_duration_seconds: Optional[int] = None,
    created_by: Optional[str] = None,
) -> str:
    """Instantiate a team from a structure definition."""
    conn = get_db_connection()
    try:
        team_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO team_instantiations (
                team_id, structure_id, structure_version_id, task_id,
                team_type, team_status, expected_duration_seconds, created_by
            ) VALUES (%s, %s, %s, %s, %s, 'forming', %s, %s)
        """, (
            team_id, structure_id, structure_version_id, task_id,
            team_type, expected_duration_seconds, created_by
        ))
        
        # Record in history
        conn.execute("""
            INSERT INTO organisational_history (history_id, team_id, event_type, new_state, recorded_by)
            VALUES (%s, %s, 'team_instantiated', 'forming', %s)
        """, (str(uuid.uuid4()), team_id, created_by))
        
        conn.commit()
        return team_id
    finally:
        conn.close()

def assign_role_to_team_member(
    team_id: str,
    node_definition_id: str,
    role_id: str,
    assignment_id: Optional[str] = None,
    selection_rationale: Optional[Dict] = None,
    eligibility_score: float = 0.0,
) -> str:
    """Assign a role to a team member."""
    conn = get_db_connection()
    try:
        membership_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO team_memberships (
                membership_id, team_id, node_definition_id, role_id,
                assignment_id, membership_status, selection_rationale, eligibility_score
            ) VALUES (%s, %s, %s, %s, %s, 'assigned', %s, %s)
        """, (
            membership_id, team_id, node_definition_id, role_id,
            assignment_id,
            json.dumps(selection_rationale) if selection_rationale else None,
            eligibility_score
        ))
        
        # Record in history
        team = conn.execute("SELECT structure_id FROM team_instantiations WHERE team_id = %s", (team_id,)).fetchone()
        if team:
            conn.execute("""
                INSERT INTO organisational_history (history_id, team_id, event_type, new_state)
                VALUES (%s, %s, 'member_joined', 'assigned')
            """, (str(uuid.uuid4()), team_id))
        
        conn.commit()
        return membership_id
    finally:
        conn.close()

# ============================================================================
# 4. STRUCTURE CANDIDATE GENERATION
# ============================================================================

def generate_structure_candidates(
    task_id: str,
    capability_requirements: Dict[str, Any],
    role_requirements: List[str],
    max_candidates: int = 5,
) -> List[Dict[str, Any]]:
    """
    Generate candidate organisational structures for a task.
    
    Considers:
    - Available validated node definitions (Section 18)
    - Required capabilities
    - Historical structure effectiveness
    - Complexity/overhead tradeoffs
    """
    conn = get_db_connection()
    try:
        candidates = []
        
        # Find all validated structures applicable to this task
        task = conn.execute("SELECT task_type FROM tasks WHERE task_id = %s", (task_id,)).fetchone()
        if not task:
            return candidates
        
        task_type = task[0]
        
        # Get applicable structures
        applicable = conn.execute("""
            SELECT os.structure_id, os.structure_type, os.name, os.lifecycle_state,
                   COUNT(oe.evidence_id) as evidence_count,
                   AVG(CASE WHEN oe.outcome_status = 'success' THEN 1 ELSE 0 END) as success_rate
            FROM organisational_structures os
            LEFT JOIN organisational_evidence oe ON os.structure_id = oe.structure_id
            WHERE os.lifecycle_state IN ('validated', 'active')
              AND os.applicability_scope::text LIKE %s
            GROUP BY os.structure_id, os.structure_type, os.name, os.lifecycle_state
            ORDER BY evidence_count DESC, success_rate DESC
            LIMIT %s
        """, (f"%{task_type}%", max_candidates)).fetchall()
        
        for struct in applicable:
            candidates.append({
                "structure_id": struct[0],
                "structure_type": struct[1],
                "name": struct[2],
                "lifecycle_state": struct[3],
                "evidence_count": struct[4] or 0,
                "success_rate": struct[5] or 0.0,
                "score": (struct[5] or 0.0) * 0.7 + min((struct[4] or 0) / 10.0, 1.0) * 0.3
            })
        
        # Sort by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        return candidates[:max_candidates]
    finally:
        conn.close()

# ============================================================================
# 5. EVIDENCE-BASED STRUCTURE SELECTION
# ============================================================================

def select_structure_for_task(
    task_id: str,
    candidates: List[str],
    capability_requirements: Dict[str, Any],
    role_requirements: List[str],
    explicit_constraints: Optional[Dict] = None,
    rule_config_version_id: Optional[str] = None,
) -> Tuple[str, str, float, str]:
    """
    Evidence-based selection of best structure for task.
    
    Returns: (selected_structure_id, rationale, confidence, evidence_sufficiency)
    """
    conn = get_db_connection()
    try:
        best_structure = None
        best_score = 0.0
        best_rationale = ""
        
        # Get rule config
        rules = conn.execute("""
            SELECT allow_autonomous_organisation, respect_node_availability,
                   min_evidence_for_promotion
            FROM organisational_rule_configs
            WHERE activated_at <= NOW()
            ORDER BY activated_at DESC LIMIT 1
        """).fetchone()
        
        # Score each candidate
        for structure_id in candidates:
            struct = conn.execute("""
                SELECT lifecycle_state, required_capabilities
                FROM organisational_structures WHERE structure_id = %s
            """, (structure_id,)).fetchone()
            
            if not struct:
                continue
            
            lifecycle, req_caps = struct
            
            # Get evidence
            evidence = conn.execute("""
                SELECT COUNT(*), 
                       SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN outcome_status = 'failure' THEN 1 ELSE 0 END),
                       AVG(quality_assessment)
                FROM organisational_evidence
                WHERE structure_id = %s
            """, (structure_id,)).fetchone()
            
            total_ev, successes, failures, avg_quality = evidence
            total_ev = total_ev or 0
            successes = successes or 0
            failures = failures or 0
            avg_quality = avg_quality or 0.5
            
            # Calculate score
            success_rate = successes / total_ev if total_ev > 0 else 0.5
            confidence = min(total_ev / 5.0, 1.0)  # Normalize to 0-1
            
            score = success_rate * 0.6 + confidence * 0.3 + (avg_quality or 0.5) * 0.1
            
            if score > best_score:
                best_score = score
                best_structure = structure_id
                best_rationale = f"Success rate: {success_rate:.2%}, Evidence: {total_ev} observations, Quality: {avg_quality:.2f}"
        
        if not best_structure and candidates:
            best_structure = candidates[0]  # Fallback to first candidate
            best_rationale = "No evidence, selected first candidate"
        
        evidence_sufficiency = "sufficient" if best_score >= (rules[2] if rules else 0.7) else "adequate"
        
        return best_structure, best_rationale, best_score, evidence_sufficiency
    finally:
        conn.close()

# ============================================================================
# 6. EXECUTION PLAN GENERATION
# ============================================================================

def create_execution_plan(
    team_id: str,
    task_id: str,
    selected_structure_id: str,
    selected_version_id: Optional[str],
    objective: str,
    members: List[Dict],
    coordination_directives: Optional[Dict] = None,
    fallback_structure_id: Optional[str] = None,
) -> str:
    """Generate a structured execution plan for team."""
    conn = get_db_connection()
    try:
        plan_id = str(uuid.uuid4())
        
        # Generate steps from structure
        steps = []
        struct_roles = conn.execute("""
            SELECT sr.sequence_number, sr.role_id, sr.required_capability_subset, or.role_name
            FROM structure_roles sr
            JOIN organisational_roles or ON sr.role_id = or.role_id
            WHERE sr.structure_id = %s
            ORDER BY sr.sequence_number
        """, (selected_structure_id,)).fetchall()
        
        for seq, role_id, caps, role_name in struct_roles:
            steps.append({
                "sequence": seq,
                "role": role_name,
                "capabilities": caps if caps else [],
                "status": "pending"
            })
        
        conn.execute("""
            INSERT INTO execution_plans (
                plan_id, team_id, task_id, objective,
                selected_structure_id, selected_version_id,
                members, steps, coordination_directives,
                fallback_structure_id, plan_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'created')
        """, (
            plan_id, team_id, task_id, objective,
            selected_structure_id, selected_version_id,
            json.dumps(members),
            json.dumps(steps),
            json.dumps(coordination_directives) if coordination_directives else None,
            fallback_structure_id
        ))
        
        conn.commit()
        return plan_id
    finally:
        conn.close()

# ============================================================================
# 7. HANDOFF RECORDING
# ============================================================================

def record_handoff(
    team_id: str,
    source_role_id: str,
    target_role_id: str,
    artifact_description: str,
    handoff_type: str,
    context_supplied: Optional[Dict] = None,
    plan_id: Optional[str] = None,
) -> str:
    """Record a work handoff between team members."""
    conn = get_db_connection()
    try:
        handoff_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO team_handoffs (
                handoff_id, team_id, execution_plan_id,
                source_role_id, target_role_id,
                artifact_description, context_supplied,
                handoff_type, handoff_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (
            handoff_id, team_id, plan_id,
            source_role_id, target_role_id,
            artifact_description,
            json.dumps(context_supplied) if context_supplied else None,
            handoff_type
        ))
        
        conn.commit()
        return handoff_id
    finally:
        conn.close()

# ============================================================================
# 8. ORGANISATIONAL EVIDENCE RECORDING
# ============================================================================

def record_organisational_evidence(
    structure_id: str,
    team_id: Optional[str],
    task_id: Optional[str],
    evidence_type: str,
    outcome_status: str,
    applicable_context: Dict,
    quality_assessment: Optional[float] = None,
    failure_attribution: Optional[Dict] = None,
) -> str:
    """Record evidence about structure effectiveness."""
    conn = get_db_connection()
    try:
        evidence_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO organisational_evidence (
                evidence_id, structure_id, team_id, task_id,
                evidence_type, outcome_status, applicable_context,
                quality_assessment, failure_attribution
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            evidence_id, structure_id, team_id, task_id,
            evidence_type, outcome_status,
            json.dumps(applicable_context),
            quality_assessment,
            json.dumps(failure_attribution) if failure_attribution else None
        ))
        
        conn.commit()
        return evidence_id
    finally:
        conn.close()

# ============================================================================
# 9. ORGANISATIONAL DECISION RECORDING
# ============================================================================

def create_organisational_decision(
    task_id: str,
    work_objective: str,
    capability_requirements: Dict,
    role_requirements: List[str],
    candidate_structures: List[str],
    selected_structure_id: str,
    decision_rationale: str,
    applied_constraints: Optional[Dict] = None,
    team_id: Optional[str] = None,
    rule_config_version_id: Optional[str] = None,
) -> str:
    """Record an organisational decision."""
    conn = get_db_connection()
    try:
        decision_id = str(uuid.uuid4())
        
        conn.execute("""
            INSERT INTO organisational_decisions (
                decision_id, task_id, work_objective,
                capability_requirements, role_requirements,
                candidate_structure_ids, selected_structure_id,
                decision_rationale, applied_constraints,
                team_id, rule_config_version_id,
                decision_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'made')
        """, (
            decision_id, task_id, work_objective,
            json.dumps(capability_requirements),
            role_requirements,
            candidate_structures,
            selected_structure_id,
            decision_rationale,
            json.dumps(applied_constraints) if applied_constraints else None,
            team_id,
            rule_config_version_id
        ))
        
        conn.commit()
        return decision_id
    finally:
        conn.close()

# ============================================================================
# 10. MEMBER REPLACEMENT
# ============================================================================

def replace_team_member(
    original_membership_id: str,
    new_node_definition_id: str,
    replacement_reason: str,
) -> str:
    """Replace unavailable team member with eligible alternative."""
    conn = get_db_connection()
    try:
        # Get original membership
        original = conn.execute("""
            SELECT team_id, role_id FROM team_memberships WHERE membership_id = %s
        """, (original_membership_id,)).fetchone()
        
        if not original:
            raise ValueError(f"Membership {original_membership_id} not found")
        
        team_id, role_id = original
        
        # Create new membership
        new_membership_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO team_memberships (
                membership_id, team_id, node_definition_id, role_id,
                membership_status, selection_rationale
            ) VALUES (%s, %s, %s, %s, 'assigned', %s)
        """, (
            new_membership_id, team_id, new_node_definition_id, role_id,
            json.dumps({"reason": replacement_reason})
        ))
        
        # Mark original as replaced
        conn.execute("""
            UPDATE team_memberships
            SET membership_status = 'replaced',
                replaced_by_membership_id = %s,
                replacement_reason = %s,
                replacement_time = NOW(),
                left_at = NOW()
            WHERE membership_id = %s
        """, (new_membership_id, replacement_reason, original_membership_id))
        
        # Record in history
        conn.execute("""
            INSERT INTO organisational_history (
                history_id, team_id, event_type, new_state
            ) VALUES (%s, %s, 'member_replaced', 'replaced')
        """, (str(uuid.uuid4()), team_id))
        
        conn.commit()
        return new_membership_id
    finally:
        conn.close()

# ============================================================================
# 11. TEMPORARY TEAM DISSOLUTION
# ============================================================================

def dissolve_temporary_team(
    team_id: str,
    reason: str,
) -> str:
    """Dissolve a temporary team, preserving all evidence."""
    conn = get_db_connection()
    try:
        dissolution_id = str(uuid.uuid4())
        
        # Gather evidence before dissolution
        memberships = conn.execute(
            "SELECT COUNT(*) FROM team_memberships WHERE team_id = %s",
            (team_id,)
        ).fetchone()[0]
        
        handoffs = conn.execute(
            "SELECT COUNT(*) FROM team_handoffs WHERE team_id = %s",
            (team_id,)
        ).fetchone()[0]
        
        # Create dissolution record
        conn.execute("""
            INSERT INTO temporary_team_dissolutions (
                dissolution_id, team_id, dissolution_reason,
                preserved_execution_records
            ) VALUES (%s, %s, %s, %s)
        """, (
            dissolution_id, team_id, reason,
            json.dumps({"members": memberships, "handoffs": handoffs})
        ))
        
        # Mark team as dissolved
        conn.execute("""
            UPDATE team_instantiations
            SET team_status = 'dissolved', end_time = NOW()
            WHERE team_id = %s
        """, (team_id,))
        
        # Record in history
        conn.execute("""
            INSERT INTO organisational_history (
                history_id, team_id, event_type, new_state
            ) VALUES (%s, %s, 'temporary_team_expired', 'dissolved')
        """, (str(uuid.uuid4()), team_id))
        
        conn.commit()
        return dissolution_id
    finally:
        conn.close()

# ============================================================================
# 12. HISTORICAL RECONSTRUCTION
# ============================================================================

def get_historical_structure_state(
    structure_id: str,
    at_timestamp: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Query exact historical state of structure at specific time."""
    conn = get_db_connection()
    try:
        if not at_timestamp:
            at_timestamp = datetime.now()
        
        # Get structure version active at that time
        version = conn.execute("""
            SELECT version_id, version_number, name, structure_type, purpose,
                   coordination_pattern, required_capabilities
            FROM organisational_structure_versions
            WHERE structure_id = %s AND created_at <= %s
            ORDER BY created_at DESC LIMIT 1
        """, (structure_id, at_timestamp)).fetchone()
        
        if not version:
            return None
        
        # Get roles as they were
        roles = conn.execute("""
            SELECT role_id, role_name, required_capabilities
            FROM structure_roles sr
            JOIN organisational_roles or ON sr.role_id = or.role_id
            WHERE sr.structure_id = %s
        """, (structure_id,)).fetchall()
        
        return {
            "version_id": version[0],
            "version_number": version[1],
            "name": version[2],
            "structure_type": version[3],
            "purpose": version[4],
            "coordination_pattern": version[5],
            "required_capabilities": version[6],
            "roles": [{"role_id": r[0], "role_name": r[1], "capabilities": r[2]} for r in roles],
            "at_timestamp": at_timestamp.isoformat()
        }
    finally:
        conn.close()

def get_team_historical_state(
    team_id: str,
    at_timestamp: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Query exact team composition and status at specific time."""
    conn = get_db_connection()
    try:
        if not at_timestamp:
            at_timestamp = datetime.now()
        
        team = conn.execute("""
            SELECT team_id, structure_id, team_status, team_type
            FROM team_instantiations WHERE team_id = %s
        """, (team_id,)).fetchone()
        
        if not team:
            return None
        
        # Get memberships as they were
        memberships = conn.execute("""
            SELECT tm.membership_id, tm.node_definition_id, or.role_name,
                   tm.membership_status, tm.joined_at, tm.left_at
            FROM team_memberships tm
            JOIN organisational_roles or ON tm.role_id = or.role_id
            WHERE tm.team_id = %s
              AND tm.joined_at <= %s
              AND (tm.left_at IS NULL OR tm.left_at > %s)
        """, (team_id, at_timestamp, at_timestamp)).fetchall()
        
        return {
            "team_id": team[0],
            "structure_id": team[1],
            "status": team[2],
            "type": team[3],
            "members": [
                {
                    "membership_id": m[0],
                    "node_def_id": m[1],
                    "role": m[2],
                    "status": m[3],
                    "joined": m[4],
                    "left": m[5]
                }
                for m in memberships
            ],
            "at_timestamp": at_timestamp.isoformat()
        }
    finally:
        conn.close()

# ============================================================================
# 13. DEDUPLICATION
# ============================================================================

def check_duplicate_proposal(
    proposal_content: Dict,
    dedup_type: str = "proposal",
) -> Optional[str]:
    """Check if similar proposal already exists."""
    conn = get_db_connection()
    try:
        source_hash = hashlib.sha256(
            json.dumps(proposal_content, sort_keys=True).encode()
        ).hexdigest()
        
        existing = conn.execute("""
            SELECT canonical_entity_id FROM organisational_dedup_registry
            WHERE source_hash = %s AND dedup_type = %s
        """, (source_hash, dedup_type)).fetchone()
        
        return existing[0] if existing else None
    finally:
        conn.close()

def register_deduplicated_entity(
    source_hash: str,
    canonical_entity_id: str,
    dedup_type: str,
) -> None:
    """Register an entity as canonical for deduplication."""
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO organisational_dedup_registry (
                dedup_id, dedup_type, source_hash, canonical_entity_id
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_hash) DO UPDATE
            SET duplicate_count = duplicate_count + 1
        """, (str(uuid.uuid4()), dedup_type, source_hash, canonical_entity_id))
        
        conn.commit()
    finally:
        conn.close()
