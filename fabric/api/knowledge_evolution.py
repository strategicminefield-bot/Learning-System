"""
Section 13: Knowledge Evolution Service

Manages knowledge evolution based on accumulated evidence while preserving
provenance, history, contradictions and reversibility.
"""

import uuid
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import psycopg
from psycopg.types.json import Json


class KnowledgeEvolutionService:
    """Service for knowledge evolution management"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
    
    def _get_conn(self):
        return psycopg.connect(self.db_url)
    
    def create_knowledge_entity(
        self,
        entity_type: str,
        task_type: str,
        original_source_id: Optional[str] = None,
        first_evidence_at: Optional[datetime] = None
    ) -> str:
        """Create persistent knowledge entity identity"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            entity_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO knowledge_entities 
                   (entity_id, entity_type, task_type, original_source_id, first_evidence_at, last_evidence_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (entity_id, entity_type, task_type, original_source_id, 
                 first_evidence_at or datetime.now(datetime.timezone.utc), 
                 first_evidence_at or datetime.now(datetime.timezone.utc))
            )
            conn.commit()
            return entity_id
        finally:
            conn.close()
    
    def create_version(
        self,
        entity_id: str,
        content: Dict,
        parent_version_id: Optional[str] = None,
        applicability: Optional[Dict] = None,
        validation_state: str = 'confirmed',
        confidence: float = 0.8,
        creation_reason: str = 'initial',
        created_by_node_id: Optional[str] = None,
        created_by_rule: Optional[str] = None
    ) -> str:
        """Create knowledge version with parent tracking"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            version_id = str(uuid.uuid4())
            
            # Get next version number
            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM knowledge_versions WHERE entity_id = %s",
                (entity_id,)
            )
            version_number = cur.fetchone()[0]
            
            cur.execute(
                """INSERT INTO knowledge_versions
                   (version_id, entity_id, version_number, parent_version_id, content, applicability,
                    validation_state, confidence, creation_reason, created_by_node_id, created_by_rule)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (version_id, entity_id, version_number, parent_version_id, 
                 Json(content), Json(applicability) if applicability else None,
                 validation_state, confidence, creation_reason, created_by_node_id, created_by_rule)
            )
            
            # Set initial state
            state_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO knowledge_evolution_states
                   (state_id, version_id, state, state_reason)
                   VALUES (%s, %s, %s, %s)""",
                (state_id, version_id, 'active', f'Initial version: {creation_reason}')
            )
            
            conn.commit()
            return version_id
        finally:
            conn.close()
    
    def add_evidence(
        self,
        entity_id: str,
        evidence_type: str,  # supportive, contradictory, neutral
        source_type: str,
        source_id: str,
        confidence: float,
        source_node_id: Optional[str] = None,
        evidence_data: Optional[Dict] = None,
        version_id: Optional[str] = None
    ) -> str:
        """Add evidence to knowledge entity"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            evidence_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO knowledge_evidence
                   (evidence_id, entity_id, version_id, evidence_type, source_type, source_id,
                    source_node_id, confidence, evidence_data)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (evidence_id, entity_id, version_id, evidence_type, source_type, source_id,
                 source_node_id, confidence, Json(evidence_data) if evidence_data else None)
            )
            
            # Update entity last_evidence_at
            cur.execute(
                "UPDATE knowledge_entities SET last_evidence_at = now() WHERE entity_id = %s",
                (entity_id,)
            )
            
            conn.commit()
            return evidence_id
        finally:
            conn.close()
    
    def evaluate_evolution(self, entity_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluate if knowledge should evolve based on accumulated evidence.
        Returns: (should_evolve, decision, resulting_version_id)
        """
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get current version
            cur.execute(
                """SELECT v.version_id, v.content, v.confidence FROM knowledge_versions v
                   WHERE v.entity_id = %s ORDER BY v.version_number DESC LIMIT 1""",
                (entity_id,)
            )
            row = cur.fetchone()
            if not row:
                return False, "no_version", None
            
            current_version_id, current_content, current_confidence = row
            
            # Get evidence counts
            cur.execute(
                """SELECT evidence_type, COUNT(*) as count, AVG(confidence) as avg_confidence
                   FROM knowledge_evidence WHERE entity_id = %s
                   GROUP BY evidence_type""",
                (entity_id,)
            )
            
            evidence_stats = {}
            for etype, count, avg_conf in cur.fetchall():
                evidence_stats[etype] = {'count': count, 'avg_confidence': float(avg_conf)}
            
            supportive_count = evidence_stats.get('supportive', {}).get('count', 0)
            contradictory_count = evidence_stats.get('contradictory', {}).get('count', 0)
            total_evidence = supportive_count + contradictory_count
            
            # Get applicable rules
            cur.execute(
                """SELECT rule_id, rule_name, rule_type, condition, action FROM knowledge_evolution_rules
                   WHERE enabled = true ORDER BY priority ASC""",
                ()
            )
            
            for rule_id, rule_name, rule_type, condition, action in cur.fetchall():
                condition_dict = condition
                
                # Check strengthening rule
                if rule_type == 'strengthening':
                    min_supportive = condition_dict.get('min_supportive_evidence', 3)
                    supportive_ratio = condition_dict.get('supportive_ratio', 0.8)
                    min_conf = condition_dict.get('min_confidence', 0.75)
                    
                    if total_evidence > 0:
                        ratio = supportive_count / total_evidence
                        if (supportive_count >= min_supportive and ratio >= supportive_ratio and 
                            current_confidence >= min_conf):
                            return True, 'strengthened', current_version_id
                
                # Check contradiction/weaken rule
                elif rule_type == 'weakening':
                    min_contradictory = condition_dict.get('min_contradictory_evidence', 2)
                    contradiction_ratio = condition_dict.get('contradiction_ratio', 0.4)
                    min_contra_conf = condition_dict.get('min_contradiction_confidence', 0.7)
                    
                    if (contradictory_count >= min_contradictory and total_evidence > 0):
                        ratio = contradictory_count / total_evidence
                        if ratio >= contradiction_ratio and evidence_stats.get('contradictory', {}).get('avg_confidence', 0) >= min_contra_conf:
                            return True, 'weakened', current_version_id
                
                # Check dispute rule
                elif rule_type == 'dispute':
                    min_supp = condition_dict.get('min_supportive', 2)
                    min_contra = condition_dict.get('min_contradictory', 2)
                    min_balance = condition_dict.get('balance_ratio', 0.3)
                    max_balance = condition_dict.get('max_balance_ratio', 0.7)
                    
                    if total_evidence > 0:
                        ratio = contradictory_count / total_evidence
                        if (supportive_count >= min_supp and contradictory_count >= min_contra and
                            min_balance <= ratio <= max_balance):
                            return True, 'disputed', current_version_id
            
            return False, 'no_evolution', None
        finally:
            conn.close()
    
    def evolve_knowledge(
        self,
        entity_id: str,
        evolution_type: str,  # strengthen, weaken, dispute, restrict, supersede, retire
        rule_id: Optional[str] = None,
        reason: str = ''
    ) -> str:
        """Apply knowledge evolution and create new version if needed"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get current version
            cur.execute(
                """SELECT version_id, content, validation_state, confidence FROM knowledge_versions
                   WHERE entity_id = %s ORDER BY version_number DESC LIMIT 1""",
                (entity_id,)
            )
            current_version_id, content, validation_state, confidence = cur.fetchone()
            
            decision_id = str(uuid.uuid4())
            
            # Get evidence counts
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE evidence_type = 'supportive'),
                          COUNT(*) FILTER (WHERE evidence_type = 'contradictory')
                   FROM knowledge_evidence WHERE entity_id = %s""",
                (entity_id,)
            )
            supportive_count, contradictory_count = cur.fetchone()
            
            new_state = evolution_type
            
            # Create transition record
            transition_id = str(uuid.uuid4())
            cur.execute(
                """SELECT state FROM knowledge_evolution_states
                   WHERE version_id = %s ORDER BY created_at DESC LIMIT 1""",
                (current_version_id,)
            )
            old_state_row = cur.fetchone()
            old_state = old_state_row[0] if old_state_row else 'unknown'
            
            cur.execute(
                """INSERT INTO knowledge_evolution_transitions
                   (transition_id, entity_id, version_id, transition_from, transition_to, 
                    decision_id, transition_reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (transition_id, entity_id, current_version_id, old_state, new_state,
                 decision_id, reason or f'Evolved to {evolution_type}')
            )
            
            # Record evolution decision
            cur.execute(
                """INSERT INTO knowledge_evolution_decisions
                   (decision_id, entity_id, version_id, rule_id, decision, decision_reason,
                    evidence_considered, evidence_supportive, evidence_contradictory,
                    previous_state, resulting_state)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (decision_id, entity_id, current_version_id, rule_id, 'evolved',
                 reason or f'Evolved to {evolution_type}',
                 supportive_count + contradictory_count, supportive_count, contradictory_count,
                 old_state, new_state)
            )
            
            # Add evolution state
            state_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO knowledge_evolution_states
                   (state_id, version_id, state, state_reason)
                   VALUES (%s, %s, %s, %s)""",
                (state_id, current_version_id, new_state, reason)
            )
            
            conn.commit()
            return decision_id
        finally:
            conn.close()
    
    def get_effective_version(self, entity_id: str, at_time: Optional[datetime] = None) -> Optional[Dict]:
        """Get effective knowledge version at specific point in time"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            if at_time is None:
                at_time = datetime.now(datetime.timezone.utc)
            
            # Get effective version by finding active/most recent state at that time
            cur.execute(
                """SELECT v.version_id, v.version_number, v.content, v.validation_state,
                          v.confidence, es.state
                   FROM knowledge_versions v
                   LEFT JOIN knowledge_evolution_states es ON es.version_id = v.version_id
                   WHERE v.entity_id = %s
                   AND es.created_at <= %s
                   ORDER BY es.created_at DESC, v.version_number DESC
                   LIMIT 1""",
                (entity_id, at_time)
            )
            
            row = cur.fetchone()
            if not row:
                return None
            
            version_id, version_number, content, validation_state, confidence, state = row
            
            return {
                'version_id': version_id,
                'version_number': version_number,
                'content': content,
                'validation_state': validation_state,
                'confidence': float(confidence),
                'state': state,
                'effective_at': at_time.isoformat()
            }
        finally:
            conn.close()
    
    def create_lineage_relationship(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,  # derived_from, revises, supersedes, merged_from, etc.
        reason: str = '',
        confidence: float = 1.0,
        source_version_id: Optional[str] = None,
        target_version_id: Optional[str] = None
    ) -> str:
        """Create lineage relationship between knowledge entities"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            lineage_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO knowledge_lineage
                   (lineage_id, source_entity_id, source_version_id, target_entity_id,
                    target_version_id, relationship_type, lineage_reason, confidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (lineage_id, source_entity_id, source_version_id, target_entity_id,
                 target_version_id, relationship_type, reason, confidence)
            )
            
            conn.commit()
            return lineage_id
        finally:
            conn.close()
    
    def merge_knowledge_entities(
        self,
        entity_id_1: str,
        entity_id_2: str,
        reason: str = '',
        merge_evidence: Optional[Dict] = None
    ) -> str:
        """Merge two knowledge entities into target"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get versions
            cur.execute(
                """SELECT version_id FROM knowledge_versions
                   WHERE entity_id = %s ORDER BY version_number DESC LIMIT 1""",
                (entity_id_1,)
            )
            v1 = cur.fetchone()[0]
            
            cur.execute(
                """SELECT version_id FROM knowledge_versions
                   WHERE entity_id = %s ORDER BY version_number DESC LIMIT 1""",
                (entity_id_2,)
            )
            v2 = cur.fetchone()[0]
            
            # Create merged entity
            merged_entity_id = str(uuid.uuid4())
            cur.execute(
                """SELECT entity_type, task_type FROM knowledge_entities WHERE entity_id = %s""",
                (entity_id_1,)
            )
            entity_type, task_type = cur.fetchone()
            
            cur.execute(
                """INSERT INTO knowledge_entities (entity_id, entity_type, task_type)
                   VALUES (%s, %s, %s)""",
                (merged_entity_id, entity_type, task_type)
            )
            
            # Create merged version combining content
            cur.execute(
                "SELECT content FROM knowledge_versions WHERE version_id = %s",
                (v1,)
            )
            content_1 = cur.fetchone()[0]
            
            cur.execute(
                "SELECT content FROM knowledge_versions WHERE version_id = %s",
                (v2,)
            )
            content_2 = cur.fetchone()[0]
            
            merged_content = {'merged_from': [content_1, content_2]}
            
            merged_version_id = self.create_version(
                merged_entity_id,
                merged_content,
                validation_state='confirmed',
                creation_reason=f'Merged from {entity_id_1} and {entity_id_2}'
            )
            
            # Record merge
            merge_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO knowledge_merge_records
                   (merge_id, source_entity_id_1, source_version_id_1, source_entity_id_2,
                    source_version_id_2, target_entity_id, target_version_id, merge_reason,
                    merge_evidence)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (merge_id, entity_id_1, v1, entity_id_2, v2, merged_entity_id,
                 merged_version_id, reason, Json(merge_evidence) if merge_evidence else None)
            )
            
            conn.commit()
            return merged_entity_id
        finally:
            conn.close()
    
    def restrict_knowledge_scope(
        self,
        entity_id: str,
        restriction_type: str,  # constraint, condition, includes, excludes
        scope_criteria: Dict,
        reason: str = ''
    ) -> str:
        """Create scope restriction for knowledge"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get current version
            cur.execute(
                """SELECT version_id FROM knowledge_versions
                   WHERE entity_id = %s ORDER BY version_number DESC LIMIT 1""",
                (entity_id,)
            )
            version_id = cur.fetchone()[0]
            
            restriction_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO knowledge_scope_restrictions
                   (restriction_id, entity_id, version_id, restriction_type, scope_criteria, restriction_reason)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (restriction_id, entity_id, version_id, restriction_type, Json(scope_criteria), reason)
            )
            
            conn.commit()
            return restriction_id
        finally:
            conn.close()
    
    def get_entity_lineage(self, entity_id: str) -> Dict:
        """Get complete lineage tree for entity"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            lineage = {
                'entity_id': entity_id,
                'predecessors': [],
                'successors': [],
                'merged_with': [],
                'contradicts': []
            }
            
            # Get predecessors (derived_from, revises, merged_from)
            cur.execute(
                """SELECT source_entity_id, relationship_type FROM knowledge_lineage
                   WHERE target_entity_id = %s""",
                (entity_id,)
            )
            
            for source_id, rel_type in cur.fetchall():
                lineage['predecessors'].append({'entity_id': source_id, 'type': rel_type})
            
            # Get successors (supersedes, restricted_from)
            cur.execute(
                """SELECT target_entity_id, relationship_type FROM knowledge_lineage
                   WHERE source_entity_id = %s""",
                (entity_id,)
            )
            
            for target_id, rel_type in cur.fetchall():
                if rel_type == 'supersedes':
                    lineage['successors'].append(target_id)
                elif rel_type == 'contradicts':
                    lineage['contradicts'].append(target_id)
            
            return lineage
        finally:
            conn.close()
    
    def retire_knowledge(
        self,
        entity_id: str,
        reason: str = ''
    ) -> str:
        """Retire knowledge without deleting"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get current version
            cur.execute(
                """SELECT version_id FROM knowledge_versions
                   WHERE entity_id = %s ORDER BY version_number DESC LIMIT 1""",
                (entity_id,)
            )
            version_id = cur.fetchone()[0]
            
            # Add retired state
            state_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO knowledge_evolution_states
                   (state_id, version_id, state, state_reason, effective_until)
                   VALUES (%s, %s, %s, %s, NOW())""",
                (state_id, version_id, 'retired', reason)
            )
            
            conn.commit()
            return state_id
        finally:
            conn.close()
