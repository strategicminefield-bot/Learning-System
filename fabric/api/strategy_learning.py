"""
Section 14: Strategy / Method Learning Service

Learns which strategies, methods, workflows and approaches work best
for particular kinds of tasks based on actual execution evidence.
"""

import uuid
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import psycopg
from psycopg.types.json import Json


class StrategyLearningService:
    """Service for strategy and method learning"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
    
    def _get_conn(self):
        return psycopg.connect(self.db_url)
    
    def create_strategy(
        self,
        strategy_name: str,
        description: str = '',
        domain_applicability: Optional[str] = None,
        method_representation: Optional[Dict] = None,
        constraints: Optional[Dict] = None,
        provenance: Optional[Dict] = None
    ) -> str:
        """Create persistent strategy identity"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            strategy_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO strategies
                   (strategy_id, strategy_name, description, domain_applicability,
                    method_representation, constraints, provenance)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (strategy_id, strategy_name, description, domain_applicability,
                 Json(method_representation) if method_representation else None,
                 Json(constraints) if constraints else None,
                 Json(provenance) if provenance else None)
            )
            conn.commit()
            return strategy_id
        finally:
            conn.close()
    
    def create_strategy_version(
        self,
        strategy_id: str,
        method_representation: Dict,
        constraints: Optional[Dict] = None,
        creation_reason: str = 'initial',
        created_by_node_id: Optional[str] = None,
        parent_version_id: Optional[str] = None
    ) -> str:
        """Create strategy version with parent tracking"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            version_id = str(uuid.uuid4())
            
            # Get next version number
            cur.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM strategy_versions WHERE strategy_id = %s",
                (strategy_id,)
            )
            version_number = cur.fetchone()[0]
            
            cur.execute(
                """INSERT INTO strategy_versions
                   (version_id, strategy_id, version_number, parent_version_id,
                    method_representation, constraints, creation_reason, created_by_node_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (version_id, strategy_id, version_number, parent_version_id,
                 Json(method_representation), Json(constraints) if constraints else None,
                 creation_reason, created_by_node_id)
            )
            
            conn.commit()
            return version_id
        finally:
            conn.close()
    
    def record_strategy_execution(
        self,
        strategy_id: str,
        task_id: str,
        node_id: str,
        assignment_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        version_id: Optional[str] = None,
        context: Optional[Dict] = None,
        parameters: Optional[Dict] = None,
        execution_status: str = 'completed'
    ) -> str:
        """Record when a strategy is actually used"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            execution_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO strategy_execution_records
                   (execution_id, strategy_id, version_id, task_id, assignment_id,
                    node_id, attempt_id, context, parameters, execution_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (execution_id, strategy_id, version_id, task_id, assignment_id,
                 node_id, attempt_id, Json(context) if context else None,
                 Json(parameters) if parameters else None, execution_status)
            )
            
            conn.commit()
            return execution_id
        finally:
            conn.close()
    
    def add_evidence(
        self,
        strategy_id: str,
        evidence_type: str,  # success, failure, neutral, insufficient
        execution_id: Optional[str] = None,
        outcome_quality: Optional[float] = None,
        verification_result: Optional[str] = None,
        repair_required: bool = False,
        completion: bool = False,
        confidence: float = 1.0,
        source_node_id: Optional[str] = None,
        version_id: Optional[str] = None,
        evidence_data: Optional[Dict] = None
    ) -> str:
        """Add evidence to strategy"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            evidence_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO strategy_evidence
                   (evidence_id, strategy_id, version_id, execution_id, evidence_type,
                    outcome_quality, verification_result, repair_required, completion,
                    confidence, source_node_id, evidence_data)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (evidence_id, strategy_id, version_id, execution_id, evidence_type,
                 outcome_quality, verification_result, repair_required, completion,
                 confidence, source_node_id, Json(evidence_data) if evidence_data else None)
            )
            
            conn.commit()
            return evidence_id
        finally:
            conn.close()
    
    def calculate_effectiveness(
        self,
        strategy_id: str,
        version_id: Optional[str] = None,
        context_scope: Optional[Dict] = None,
        min_evidence: int = 2
    ) -> Dict:
        """Calculate strategy effectiveness in a context"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get evidence counts
            cur.execute(
                """SELECT 
                     COUNT(*) as total,
                     COUNT(*) FILTER (WHERE evidence_type = 'success') as success_count,
                     COUNT(*) FILTER (WHERE evidence_type = 'failure') as failure_count,
                     COUNT(*) FILTER (WHERE evidence_type = 'neutral') as neutral_count,
                     COUNT(DISTINCT source_node_id) as independent_nodes,
                     AVG(outcome_quality) as avg_quality
                   FROM strategy_evidence
                   WHERE strategy_id = %s""" + (f" AND version_id = %s" if version_id else ""),
                (strategy_id, version_id) if version_id else (strategy_id,)
            )
            
            row = cur.fetchone()
            total, success_count, failure_count, neutral_count, independent_nodes, avg_quality = row
            
            total = total or 0
            success_count = success_count or 0
            failure_count = failure_count or 0
            neutral_count = neutral_count or 0
            independent_nodes = independent_nodes or 0
            
            # Determine confidence level
            if total < min_evidence:
                confidence_level = 'insufficient'
            elif total < min_evidence * 3:
                confidence_level = 'low'
            elif total < min_evidence * 10:
                confidence_level = 'adequate'
            else:
                confidence_level = 'high'
            
            success_rate = success_count / total if total > 0 else 0
            failure_rate = failure_count / total if total > 0 else 0
            
            effectiveness_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO strategy_effectiveness
                   (effectiveness_id, strategy_id, version_id, context_scope,
                    success_rate, failure_rate, evidence_count, success_count,
                    failure_count, neutral_count, avg_outcome_quality,
                    confidence_level, independent_node_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (effectiveness_id, strategy_id, version_id, Json(context_scope) if context_scope else None,
                 success_rate, failure_rate, total, success_count, failure_count, neutral_count,
                 float(avg_quality) if avg_quality else None, confidence_level, independent_nodes)
            )
            
            conn.commit()
            
            return {
                'effectiveness_id': effectiveness_id,
                'strategy_id': strategy_id,
                'success_rate': float(success_rate),
                'failure_rate': float(failure_rate),
                'evidence_count': total,
                'success_count': success_count,
                'failure_count': failure_count,
                'neutral_count': neutral_count,
                'independent_nodes': independent_nodes,
                'confidence_level': confidence_level
            }
        finally:
            conn.close()
    
    def compare_strategies(
        self,
        strategy_id_1: str,
        strategy_id_2: str,
        comparison_scope: Optional[Dict] = None,
        min_population: int = 2
    ) -> Dict:
        """Compare two strategies on comparable tasks"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get evidence for strategy 1
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE evidence_type = 'success'),
                          COUNT(*) as total
                   FROM strategy_evidence WHERE strategy_id = %s""",
                (strategy_id_1,)
            )
            s1_success, s1_total = cur.fetchone()
            s1_success_rate = s1_success / s1_total if s1_total > 0 else 0
            
            # Get evidence for strategy 2
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE evidence_type = 'success'),
                          COUNT(*) as total
                   FROM strategy_evidence WHERE strategy_id = %s""",
                (strategy_id_2,)
            )
            s2_success, s2_total = cur.fetchone()
            s2_success_rate = s2_success / s2_total if s2_total > 0 else 0
            
            # Determine confidence
            total_population = s1_total + s2_total
            if total_population < min_population:
                confidence_level = 'insufficient'
                winner_id = None
            elif s1_success_rate > s2_success_rate:
                confidence_level = 'adequate' if total_population >= min_population * 3 else 'low'
                winner_id = strategy_id_1
            elif s2_success_rate > s1_success_rate:
                confidence_level = 'adequate' if total_population >= min_population * 3 else 'low'
                winner_id = strategy_id_2
            else:
                confidence_level = 'adequate' if total_population >= min_population * 3 else 'low'
                winner_id = None
            
            comparison_id = str(uuid.uuid4())
            success_diff = s1_success_rate - s2_success_rate
            
            cur.execute(
                """INSERT INTO strategy_comparisons
                   (comparison_id, strategy_id_1, strategy_id_2, comparison_scope,
                    population_count, strategy_1_success_rate, strategy_2_success_rate,
                    success_difference, confidence_level, winner_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (comparison_id, strategy_id_1, strategy_id_2, Json(comparison_scope) if comparison_scope else None,
                 total_population, s1_success_rate, s2_success_rate, success_diff,
                 confidence_level, winner_id)
            )
            
            conn.commit()
            
            return {
                'comparison_id': comparison_id,
                'strategy_1_success_rate': float(s1_success_rate),
                'strategy_2_success_rate': float(s2_success_rate),
                'success_difference': float(success_diff),
                'population_count': total_population,
                'confidence_level': confidence_level,
                'winner_id': winner_id
            }
        finally:
            conn.close()
    
    def record_repair(
        self,
        execution_id: str,
        strategy_id: str,
        failure_reason: str,
        repair_action: str,
        subsequent_result: str = 'unknown',
        repair_effectiveness: float = 0.5
    ) -> str:
        """Record a repair applied to a failure"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            repair_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO strategy_repairs
                   (repair_id, execution_id, strategy_id, failure_reason,
                    repair_action, repair_applied_at, subsequent_result, repair_effectiveness)
                   VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)""",
                (repair_id, execution_id, strategy_id, failure_reason, repair_action,
                 subsequent_result, repair_effectiveness)
            )
            
            conn.commit()
            return repair_id
        finally:
            conn.close()
    
    def create_variant(
        self,
        parent_strategy_id: str,
        variant_name: str,
        variant_type: str = 'specialization',
        reason: str = ''
    ) -> str:
        """Create a strategy variant"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Create variant strategy
            variant_strategy_id = self.create_strategy(
                strategy_name=variant_name,
                description=f'Variant of {parent_strategy_id}: {reason}'
            )
            
            # Record variant relationship
            variant_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO strategy_variants
                   (variant_id, parent_strategy_id, variant_strategy_id, variant_type, lineage_reason)
                   VALUES (%s, %s, %s, %s, %s)""",
                (variant_id, parent_strategy_id, variant_strategy_id, variant_type, reason)
            )
            
            conn.commit()
            return variant_strategy_id
        finally:
            conn.close()
    
    def record_selection_observation(
        self,
        task_id: str,
        strategy_id: str,
        observation_type: str,  # considered, selected, rejected, executed, evaluated
        node_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        rationale: str = '',
        context: Optional[Dict] = None
    ) -> str:
        """Record when a strategy is considered/selected/rejected"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            observation_id = str(uuid.uuid4())
            
            cur.execute(
                """INSERT INTO strategy_selection_observations
                   (observation_id, task_id, assignment_id, node_id, strategy_id,
                    observation_type, rationale, context)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (observation_id, task_id, assignment_id, node_id, strategy_id,
                 observation_type, rationale, Json(context) if context else None)
            )
            
            conn.commit()
            return observation_id
        finally:
            conn.close()
    
    def get_strategy_guidance(
        self,
        task_type: str,
        domain: Optional[str] = None,
        include_history: bool = False
    ) -> Dict:
        """Get structured strategy guidance for a task"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Get applicable strategies
            cur.execute(
                """SELECT s.strategy_id, s.strategy_name, s.description,
                          se.success_rate, se.failure_rate, se.confidence_level,
                          se.evidence_count, se.independent_node_count
                   FROM strategies s
                   LEFT JOIN strategy_effectiveness se ON se.strategy_id = s.strategy_id
                   WHERE s.domain_applicability = %s
                   AND s.lifecycle_state IN ('active', 'restricted')
                   ORDER BY se.success_rate DESC NULLS LAST""",
                (task_type,)
            )
            
            strategies = []
            for row in cur.fetchall():
                strategy_id, name, desc, success_rate, failure_rate, confidence_level, evidence_count, node_count = row
                
                # Get failure evidence
                cur.execute(
                    """SELECT COUNT(*) FROM strategy_evidence
                       WHERE strategy_id = %s AND evidence_type IN ('failure', 'neutral')""",
                    (strategy_id,)
                )
                failure_count = cur.fetchone()[0]
                
                strategies.append({
                    'strategy_id': strategy_id,
                    'name': name,
                    'description': desc,
                    'success_rate': float(success_rate) if success_rate else None,
                    'failure_rate': float(failure_rate) if failure_rate else None,
                    'confidence_level': confidence_level,
                    'evidence_count': evidence_count or 0,
                    'independent_nodes': node_count or 0,
                    'failure_evidence_count': failure_count,
                    'has_repairs': failure_count > 0
                })
            
            return {
                'task_type': task_type,
                'domain': domain,
                'strategies': strategies,
                'guidance_timestamp': datetime.now(datetime.timezone.utc).isoformat()
            }
        finally:
            conn.close()
    
    def get_strategy_version_history(
        self,
        strategy_id: str,
        at_time: Optional[datetime] = None
    ) -> List[Dict]:
        """Get strategy version history"""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            cur.execute(
                """SELECT version_id, version_number, parent_version_id, creation_reason, created_at
                   FROM strategy_versions
                   WHERE strategy_id = %s
                   ORDER BY version_number ASC""",
                (strategy_id,)
            )
            
            versions = []
            for version_id, version_num, parent_id, reason, created_at in cur.fetchall():
                versions.append({
                    'version_id': version_id,
                    'version_number': version_num,
                    'parent_version_id': parent_id,
                    'creation_reason': reason,
                    'created_at': created_at.isoformat() if created_at else None
                })
            
            return versions
        finally:
            conn.close()
