"""Section 8: Learning Memory Integration

Automatically converts learning outcomes (Section 6) into persistent memory 
entities (Section 7) with full provenance tracking and graph integration.
"""
import os
import json
import uuid
import hashlib
from typing import Optional, Dict, List, Tuple
import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_learning_hash(source_type: str, source_id: uuid.UUID) -> str:
    """Generate deterministic hash for deduplication"""
    content = f"{source_type}:{str(source_id)}"
    return hashlib.sha256(content.encode()).hexdigest()


def check_and_register_dedup(source_type: str, source_id: uuid.UUID) -> Tuple[bool, Optional[str]]:
    """
    Check if learning event already processed.
    Returns: (is_duplicate, canonical_id)
    """
    source_hash = get_learning_hash(source_type, source_id)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check if already processed
            cur.execute(
                "SELECT registry_id, canonical_id FROM learning_dedup_registry WHERE source_hash = %s",
                (source_hash,)
            )
            row = cur.fetchone()
            
            if row:
                # Already processed
                registry_id = row[0]
                canonical_id = row[1]
                
                # Update reprocess count
                cur.execute(
                    "UPDATE learning_dedup_registry SET reprocess_count = reprocess_count + 1, last_reprocess = now() WHERE registry_id = %s",
                    (registry_id,)
                )
                conn.commit()
                return (True, canonical_id)
            else:
                # New learning event - register it
                registry_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO learning_dedup_registry
                    (registry_id, source_hash, source_type, source_id, canonical_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (registry_id, source_hash, source_type, source_id, source_id)
                )
                conn.commit()
                return (False, None)


def create_provenance_record(
    source_type: str,
    source_id: uuid.UUID,
    node_id: Optional[uuid.UUID] = None,
    task_type: Optional[str] = None,
    task_id: Optional[uuid.UUID] = None,
    outcome_id: Optional[uuid.UUID] = None,
    confidence: float = 0.8,
    evidence_count: int = 1
) -> uuid.UUID:
    """Create provenance tracking record"""
    provenance_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning_provenance
                (provenance_id, source_type, source_id, node_id, task_type, task_id, outcome_id, confidence, evidence_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (provenance_id, source_type, source_id, node_id, task_type, task_id, outcome_id, confidence, evidence_count)
            )
            conn.commit()
    
    return provenance_id


def create_memory_trace(
    task_id: uuid.UUID,
    outcome_id: uuid.UUID,
    node_id: uuid.UUID,
    assignment_id: Optional[uuid.UUID] = None
) -> uuid.UUID:
    """Create task→outcome→memory trace"""
    trace_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory_trace
                (trace_id, task_id, outcome_id, node_id, assignment_id, trace_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (trace_id, task_id, outcome_id, node_id, assignment_id, 'processing')
            )
            conn.commit()
    
    return trace_id


def outcome_to_memory(outcome_id: uuid.UUID) -> Tuple[bool, Optional[str]]:
    """
    Convert task outcome into persistent memory.
    Returns: (success, provenance_id or error_message)
    """
    # Check deduplication
    is_dup, canonical_id = check_and_register_dedup('outcome', outcome_id)
    if is_dup:
        return (True, canonical_id)  # Already processed
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get outcome details
            cur.execute(
                """
                SELECT task_outcomes.task_id, node_id, assignment_id, outcome_status, quality_score,
                       execution_time_seconds, result_summary, tasks.task_type
                FROM task_outcomes
                JOIN tasks ON task_outcomes.task_id = tasks.task_id
                WHERE outcome_id = %s
                """,
                (outcome_id,)
            )
            outcome = cur.fetchone()
            
            if not outcome:
                return (False, "outcome not found")
            
            task_id, node_id, assignment_id, outcome_status, quality_score, exec_time, result_summary, task_type = outcome
            
            # Create provenance
            provenance_id = create_provenance_record(
                source_type='outcome',
                source_id=outcome_id,
                node_id=node_id,
                task_type=task_type,
                task_id=task_id,
                outcome_id=outcome_id,
                confidence=float(quality_score) if quality_score else 0.7,
                evidence_count=1
            )
            
            # Create trace
            trace_id = create_memory_trace(task_id, outcome_id, node_id, assignment_id)
            
            # Record in trace
            cur.execute(
                """
                UPDATE memory_trace SET learning_events = jsonb_set(
                    learning_events, '{0}', %s
                ) WHERE trace_id = %s
                """,
                (Jsonb({"type": "outcome", "id": str(outcome_id), "created_at": "now()"}), trace_id)
            )
            conn.commit()
    
    return (True, str(provenance_id))


def pattern_to_memory(pattern_id: uuid.UUID) -> Tuple[bool, Optional[str]]:
    """Convert discovered pattern into persistent memory with provenance"""
    is_dup, canonical_id = check_and_register_dedup('pattern', pattern_id)
    if is_dup:
        return (True, canonical_id)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get pattern details
            cur.execute(
                """
                SELECT task_type, pattern_name, pattern_rule, success_rate, 
                       occurrence_count, source_outcome_ids
                FROM result_patterns
                WHERE pattern_id = %s
                """,
                (pattern_id,)
            )
            pattern = cur.fetchone()
            
            if not pattern:
                return (False, "pattern not found")
            
            task_type, pattern_name, pattern_rule, success_rate, occ_count, source_outcome_ids = pattern
            
            # Create provenance
            evidence_count = len(source_outcome_ids) if source_outcome_ids else occ_count
            provenance_id = create_provenance_record(
                source_type='pattern',
                source_id=pattern_id,
                task_type=task_type,
                confidence=float(success_rate) if success_rate else 0.75,
                evidence_count=evidence_count
            )
            
            # Link provenance to pattern
            cur.execute(
                "UPDATE result_patterns SET provenance_id = %s WHERE pattern_id = %s",
                (provenance_id, pattern_id)
            )
            
            # If source outcomes exist, track them
            if source_outcome_ids and len(source_outcome_ids) > 0:
                for outcome_id in source_outcome_ids[:5]:  # Track first 5 source outcomes
                    cur.execute(
                        "UPDATE task_outcomes SET patterns_matched = array_append(COALESCE(patterns_matched, '{}'), %s) WHERE outcome_id = %s",
                        (pattern_id, outcome_id)
                    )
            
            conn.commit()
    
    return (True, str(provenance_id))


def insight_to_memory(insight_id: uuid.UUID) -> Tuple[bool, Optional[str]]:
    """Convert performance insight into persistent memory with provenance"""
    is_dup, canonical_id = check_and_register_dedup('insight', insight_id)
    if is_dup:
        return (True, canonical_id)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get insight details
            cur.execute(
                """
                SELECT node_id, task_type, insight_type, description, confidence_score,
                       evidence_count, recommendation
                FROM performance_insights
                WHERE insight_id = %s
                """,
                (insight_id,)
            )
            insight = cur.fetchone()
            
            if not insight:
                return (False, "insight not found")
            
            node_id, task_type, insight_type, description, confidence, evidence_count, recommendation = insight
            
            # Create provenance
            provenance_id = create_provenance_record(
                source_type='insight',
                source_id=insight_id,
                node_id=node_id,
                task_type=task_type,
                confidence=float(confidence) if confidence else 0.8,
                evidence_count=int(evidence_count) if evidence_count else 1
            )
            
            # Link provenance to insight
            cur.execute(
                "UPDATE performance_insights SET provenance_id = %s WHERE insight_id = %s",
                (provenance_id, insight_id)
            )
            conn.commit()
    
    return (True, str(provenance_id))


def artifact_to_graph(artifact_id: uuid.UUID) -> Tuple[bool, Optional[str]]:
    """
    Create knowledge artifact graph entity from learning artifact.
    Returns: (success, graph_entity_id or error_message)
    """
    is_dup, canonical_id = check_and_register_dedup('artifact', artifact_id)
    if is_dup:
        return (True, canonical_id)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get artifact details
            cur.execute(
                """
                SELECT task_type, artifact_type, content, quality_score, usage_count, node_id
                FROM knowledge_artifacts
                WHERE artifact_id = %s
                """,
                (artifact_id,)
            )
            artifact = cur.fetchone()
            
            if not artifact:
                return (False, "artifact not found")
            
            task_type, artifact_type, content, quality_score, usage_count, node_id = artifact
            
            # Create provenance
            provenance_id = create_provenance_record(
                source_type='artifact',
                source_id=artifact_id,
                node_id=node_id,
                task_type=task_type,
                confidence=float(quality_score) if quality_score else 0.8,
                evidence_count=int(usage_count) if usage_count else 1
            )
            
            # Ensure artifact is mapped to task type for discovery
            cur.execute(
                """
                INSERT INTO task_knowledge_mappings
                (mapping_id, task_type, artifact_id, relevance_score, created_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (task_type, artifact_id) DO UPDATE SET
                    relevance_score = GREATEST(task_knowledge_mappings.relevance_score, %s)
                """,
                (uuid.uuid4(), task_type, artifact_id, float(quality_score) if quality_score else 0.8, 
                 float(quality_score) if quality_score else 0.8)
            )
            
            # Record graph link
            link_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO memory_graph_links
                (link_id, provenance_id, graph_entity_id, graph_entity_type, sync_status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (link_id, provenance_id, artifact_id, 'artifact', 'synced')
            )
            
            conn.commit()
    
    return (True, str(artifact_id))


def get_memory_trace(task_id: uuid.UUID) -> Optional[Dict]:
    """Get complete task→outcome→memory trace with all provenance"""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trace_id, task_id, outcome_id, node_id, learning_events, graph_entities,
                       trace_status, created_at, updated_at
                FROM memory_trace
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            trace_id, task_id, outcome_id, node_id, learning_events, graph_entities, status, created_at, updated_at = row
            
            # Get provenance details for this trace
            cur.execute(
                """
                SELECT p.provenance_id, p.source_type, p.source_id, p.task_type,
                       p.confidence, p.evidence_count, p.created_at
                FROM learning_provenance p
                WHERE p.task_id = %s OR p.outcome_id = %s
                ORDER BY p.created_at
                """,
                (task_id, outcome_id)
            )
            provenance_records = cur.fetchall()
            
            return {
                "trace_id": str(trace_id),
                "task_id": str(task_id),
                "outcome_id": str(outcome_id),
                "node_id": str(node_id),
                "learning_events": learning_events or [],
                "graph_entities": graph_entities or [],
                "trace_status": status,
                "provenance": [
                    {
                        "provenance_id": str(p[0]),
                        "source_type": p[1],
                        "source_id": str(p[2]),
                        "task_type": p[3],
                        "confidence": p[4],
                        "evidence_count": p[5],
                        "created_at": p[6].isoformat()
                    }
                    for p in provenance_records
                ],
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat()
            }


def get_provenance_evidence(provenance_id: uuid.UUID) -> Optional[Dict]:
    """Get evidence supporting a provenance record (for traceability)"""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_type, source_id, task_id, outcome_id, confidence, evidence_count
                FROM learning_provenance
                WHERE provenance_id = %s
                """,
                (provenance_id,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            source_type, source_id, task_id, outcome_id, confidence, evidence_count = row
            
            evidence = {
                "provenance_id": str(provenance_id),
                "source_type": source_type,
                "source_id": str(source_id),
                "confidence": confidence,
                "evidence_count": evidence_count,
            }
            
            # Get source-specific details
            if source_type == 'outcome':
                cur.execute(
                    "SELECT outcome_status, quality_score, execution_time_seconds FROM task_outcomes WHERE outcome_id = %s",
                    (source_id,)
                )
                outcome = cur.fetchone()
                if outcome:
                    evidence["outcome_details"] = {
                        "status": outcome[0],
                        "quality": outcome[1],
                        "execution_time_seconds": outcome[2]
                    }
            
            elif source_type == 'pattern':
                cur.execute(
                    "SELECT pattern_name, success_rate, occurrence_count FROM result_patterns WHERE pattern_id = %s",
                    (source_id,)
                )
                pattern = cur.fetchone()
                if pattern:
                    evidence["pattern_details"] = {
                        "name": pattern[0],
                        "success_rate": float(pattern[1]) if pattern[1] else 0,
                        "occurrence_count": pattern[2]
                    }
            
            elif source_type == 'insight':
                cur.execute(
                    "SELECT insight_type, description, recommendation FROM performance_insights WHERE insight_id = %s",
                    (source_id,)
                )
                insight = cur.fetchone()
                if insight:
                    evidence["insight_details"] = {
                        "type": insight[0],
                        "description": insight[1],
                        "recommendation": insight[2]
                    }
            
            evidence["task_id"] = str(task_id) if task_id else None
            evidence["outcome_id"] = str(outcome_id) if outcome_id else None
            
            return evidence
