"""
Section 18: Node Evolution Engine
Manages node definition versioning, capability evolution, and evidence-based proposals.
"""

import json
import hashlib
from typing import Optional, Dict, List, Tuple, Any
from uuid import uuid4, UUID
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

def create_node_definition(
    conn,
    node_type: str,
    display_name: str,
    provider_type: Optional[str] = None,
    runtime_type: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
    supports_persistent: bool = True,
    supports_ephemeral: bool = False,
    definition_metadata: Optional[Dict] = None
) -> UUID:
    """Create a new node definition."""
    definition_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO node_definitions (
                definition_id, node_type, display_name, provider_type, runtime_type,
                supports_persistent, supports_ephemeral, definition_metadata,
                lifecycle_state
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            definition_id, node_type, display_name, provider_type, runtime_type,
            supports_persistent, supports_ephemeral,
            json.dumps(definition_metadata) if definition_metadata else None,
            'candidate'
        ))
        
        # Create initial version
        version_id = create_node_definition_version(
            conn, definition_id, 1, None, "Initial version",
            capabilities or [], None, None, None
        )
        
        # Update current version
        cur.execute("""
            UPDATE node_definitions SET current_version_id = %s WHERE definition_id = %s
        """, (version_id, definition_id))
        
        # Record history
        cur.execute("""
            INSERT INTO node_evolution_history (
                history_id, definition_id, event_type, new_state
            ) VALUES (%s, %s, %s, %s)
        """, (uuid4(), definition_id, 'definition_created', 'candidate'))
        
        conn.commit()
        return definition_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def create_node_definition_version(
    conn,
    definition_id: UUID,
    version_number: int,
    parent_version_id: Optional[UUID],
    description: str,
    capabilities: List[str],
    tool_requirements: Optional[Dict] = None,
    model_reference: Optional[str] = None,
    execution_configuration: Optional[Dict] = None
) -> UUID:
    """Create a new version of a node definition."""
    version_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO node_definition_versions (
                version_id, definition_id, version_number, parent_version_id,
                description, capabilities, tool_requirements, model_reference,
                execution_configuration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            version_id, definition_id, version_number, parent_version_id,
            description, json.dumps(capabilities),
            json.dumps(tool_requirements) if tool_requirements else None,
            model_reference,
            json.dumps(execution_configuration) if execution_configuration else None
        ))
        conn.commit()
        return version_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def record_capability_gap(
    conn,
    required_capability: str,
    task_type: Optional[str] = None,
    domain_context: Optional[str] = None,
    triggering_outcome_id: Optional[UUID] = None
) -> UUID:
    """Record a detected capability gap."""
    gap_id = uuid4()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Check if gap already exists
        cur.execute("""
            SELECT gap_id, observation_count FROM capability_gaps
            WHERE required_capability = %s AND task_type IS NOT DISTINCT FROM %s
            AND domain_context IS NOT DISTINCT FROM %s
        """, (required_capability, task_type, domain_context))
        
        existing = cur.fetchone()
        if existing:
            # Increment existing gap
            cur.execute("""
                UPDATE capability_gaps
                SET observation_count = observation_count + 1,
                    last_observed_at = NOW(),
                    evidence_ids = array_append(evidence_ids, %s)
                WHERE gap_id = %s
            """, (str(triggering_outcome_id), existing['gap_id']))
            conn.commit()
            return existing['gap_id']
        
        # Create new gap
        cur.execute("""
            INSERT INTO capability_gaps (
                gap_id, gap_type, required_capability, task_type, domain_context,
                evidence_ids
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            gap_id, 'missing_capability', required_capability, task_type,
            domain_context,
            [str(triggering_outcome_id)] if triggering_outcome_id else []
        ))
        conn.commit()
        return gap_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def create_evolution_proposal(
    conn,
    proposal_type: str,
    triggering_gap_id: Optional[UUID],
    existing_definition_id: Optional[UUID],
    existing_version_id: Optional[UUID],
    proposed_change: Dict,
    expected_benefit: str,
    applicability_scope: Optional[str] = None,
    triggering_failure_count: int = 0
) -> UUID:
    """Create a node evolution proposal."""
    proposal_id = uuid4()
    cur = conn.cursor()
    try:
        # Check deduplication
        proposal_hash = hashlib.sha256(
            json.dumps(proposed_change, sort_keys=True).encode()
        ).hexdigest()
        
        cur.execute("""
            SELECT canonical_proposal_id FROM node_proposal_dedup_registry
            WHERE proposal_hash = %s
        """, (proposal_hash,))
        dedup = cur.fetchone()
        
        if dedup:
            cur.execute("""
                UPDATE node_proposal_dedup_registry
                SET duplicate_count = duplicate_count + 1
                WHERE proposal_hash = %s
            """, (proposal_hash,))
            conn.commit()
            return dedup[0]  # Return existing proposal
        
        # Create new proposal
        cur.execute("""
            INSERT INTO node_evolution_proposals (
                proposal_id, proposal_type, triggering_gap_id,
                existing_definition_id, existing_version_id,
                proposed_change, expected_benefit, applicability_scope,
                triggering_failure_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            proposal_id, proposal_type, triggering_gap_id,
            existing_definition_id, existing_version_id,
            json.dumps(proposed_change), expected_benefit, applicability_scope,
            triggering_failure_count
        ))
        
        # Register dedup
        cur.execute("""
            INSERT INTO node_proposal_dedup_registry (
                registry_id, proposal_hash, canonical_proposal_id
            ) VALUES (%s, %s, %s)
        """, (uuid4(), proposal_hash, proposal_id))
        
        conn.commit()
        return proposal_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def create_candidate_node_definition(
    conn,
    proposal_id: UUID,
    existing_definition_id: UUID,
    capabilities: List[str],
    description: str
) -> Tuple[UUID, UUID]:
    """Create a candidate node definition from a proposal. Returns (definition_id, version_id)."""
    definition_id = uuid4()
    version_id = uuid4()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get existing definition to clone from
        cur.execute("""
            SELECT node_type, provider_type, runtime_type, display_name
            FROM node_definitions WHERE definition_id = %s
        """, (existing_definition_id,))
        existing = cur.fetchone()
        
        # Create candidate definition
        cur.execute("""
            INSERT INTO node_definitions (
                definition_id, node_type, provider_type, runtime_type,
                display_name, lifecycle_state, current_version_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            definition_id, existing['node_type'], existing['provider_type'],
            existing['runtime_type'], f"{existing['display_name']} (candidate)",
            'candidate', version_id
        ))
        
        # Create version
        cur.execute("""
            INSERT INTO node_definition_versions (
                version_id, definition_id, version_number, parent_version_id,
                description, capabilities
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            version_id, definition_id, 1, None, description,
            json.dumps(capabilities)
        ))
        
        # Link lineage
        cur.execute("""
            INSERT INTO node_definition_lineage (
                lineage_id, source_definition_id, source_version_id,
                target_definition_id, target_version_id, relationship_type
            ) SELECT %s, definition_id, current_version_id, %s, %s, %s
            FROM node_definitions WHERE definition_id = %s
        """, (uuid4(), definition_id, version_id, 'derived_from', existing_definition_id))
        
        # Link proposal
        cur.execute("""
            UPDATE node_evolution_proposals
            SET proposed_definition_id = %s, proposal_status = %s
            WHERE proposal_id = %s
        """, (definition_id, 'experimental', proposal_id))
        
        conn.commit()
        return definition_id, version_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def create_node_instance(
    conn,
    definition_id: UUID,
    version_id: UUID,
    provider_endpoint: Optional[str] = None,
    runtime_location: str = 'local',
    creation_context: Optional[Dict] = None
) -> UUID:
    """Create a new node instance from a definition."""
    instance_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO node_instances (
                instance_id, definition_id, version_id, provider_endpoint,
                runtime_location, creation_context, current_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            instance_id, definition_id, version_id, provider_endpoint,
            runtime_location, json.dumps(creation_context) if creation_context else None,
            'available'
        ))
        conn.commit()
        return instance_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def make_evolution_decision(
    conn,
    proposal_id: UUID,
    definition_id: UUID,
    version_id: UUID,
    decision_type: str,  # promote, retain, restrict, dispute, retire
    rationale: str,
    evidence_count: int = 0,
    contradictions_present: bool = False
) -> UUID:
    """Make a node evolution decision."""
    decision_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO node_evolution_decisions (
                decision_id, proposal_id, definition_id, version_id,
                decision_type, rationale, evidence_count,
                contradictions_present
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            decision_id, proposal_id, definition_id, version_id,
            decision_type, rationale, evidence_count, contradictions_present
        ))
        
        # Record in history
        cur.execute("""
            INSERT INTO node_evolution_history (
                history_id, definition_id, event_type, decision_id, new_state
            ) VALUES (%s, %s, %s, %s, %s)
        """, (uuid4(), definition_id, 'decision_made', decision_id, decision_type))
        
        conn.commit()
        return decision_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def apply_evolution_decision(
    conn,
    decision_id: UUID
) -> bool:
    """Apply an evolution decision to node definition."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get decision
        cur.execute("""
            SELECT decision_type, definition_id FROM node_evolution_decisions
            WHERE decision_id = %s
        """, (decision_id,))
        decision = cur.fetchone()
        
        if not decision:
            raise ValueError(f"Decision {decision_id} not found")
        
        # Map decision to lifecycle state
        decision_to_state = {
            'promote': 'validated',
            'restrict': 'restricted',
            'dispute': 'disputed',
            'retire': 'retired',
            'retain': 'experimental'
        }
        
        new_state = decision_to_state.get(decision['decision_type'], 'experimental')
        
        # Update definition
        update_time = datetime.utcnow() if decision['decision_type'] == 'retire' else None
        cur.execute("""
            UPDATE node_definitions
            SET lifecycle_state = %s, retired_at = %s, updated_at = NOW()
            WHERE definition_id = %s
        """, (new_state, update_time, decision['definition_id']))
        
        # Mark decision as applied
        cur.execute("""
            UPDATE node_evolution_decisions
            SET decision_status = %s, applied_at = NOW()
            WHERE decision_id = %s
        """, (b'applied', decision_id))
        
        # Record history
        cur.execute("""
            INSERT INTO node_evolution_history (
                history_id, definition_id, event_type, decision_id,
                new_state
            ) VALUES (%s, %s, %s, %s, %s)
        """, (uuid4(), decision['definition_id'], 'decision_applied', decision_id, new_state))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def request_node_instance(
    conn,
    definition_id: UUID,
    version_id: UUID,
    request_type: str,
    request_reason: str,
    requested_by: str = 'system'
) -> UUID:
    """Create a request for a new node instance."""
    request_id = uuid4()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO node_instance_requests (
                request_id, definition_id, version_id, request_type,
                request_reason, requested_by, request_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            request_id, definition_id, version_id, request_type,
            request_reason, requested_by, 'requested'
        ))
        conn.commit()
        return request_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def retire_node_definition(
    conn,
    definition_id: UUID,
    reason: str
) -> bool:
    """Retire a node definition."""
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE node_definitions
            SET lifecycle_state = %s, retired_at = NOW(), updated_at = NOW()
            WHERE definition_id = %s
        """, ('retired', definition_id))
        
        # Record history
        cur.execute("""
            INSERT INTO node_evolution_history (
                history_id, definition_id, event_type, new_state, event_metadata
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            uuid4(), definition_id, 'retired', 'retired',
            json.dumps({'reason': reason})
        ))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def get_node_definition(conn, definition_id: UUID) -> Optional[Dict]:
    """Get node definition."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM node_definitions WHERE definition_id = %s
        """, (definition_id,))
        return cur.fetchone()
    finally:
        cur.close()

def get_node_definition_version(conn, version_id: UUID) -> Optional[Dict]:
    """Get node definition version."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM node_definition_versions WHERE version_id = %s
        """, (version_id,))
        return cur.fetchone()
    finally:
        cur.close()

def get_evolution_decision(conn, decision_id: UUID) -> Optional[Dict]:
    """Get evolution decision."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM node_evolution_decisions WHERE decision_id = %s
        """, (decision_id,))
        return cur.fetchone()
    finally:
        cur.close()

def get_node_evolution_history(conn, definition_id: UUID) -> List[Dict]:
    """Get evolution history for a node definition."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM node_evolution_history
            WHERE definition_id = %s
            ORDER BY recorded_at ASC
        """, (definition_id,))
        return cur.fetchall()
    finally:
        cur.close()

def get_capability_gaps(
    conn,
    status: str = 'open',
    limit: int = 100
) -> List[Dict]:
    """Get capability gaps."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM capability_gaps
            WHERE gap_status = %s
            ORDER BY last_observed_at DESC
            LIMIT %s
        """, (status, limit))
        return cur.fetchall()
    finally:
        cur.close()

def get_node_instances(conn, definition_id: UUID) -> List[Dict]:
    """Get all instances of a definition."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM node_instances
            WHERE definition_id = %s
            ORDER BY created_at DESC
        """, (definition_id,))
        return cur.fetchall()
    finally:
        cur.close()
