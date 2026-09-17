"""
Section 12: Cross-Node Learning Distribution

Enables validated learning from one node to be safely shared with other nodes
while preserving provenance, scope, validation state, and conflict information.
"""

import uuid
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from decimal import Decimal
from db_utils import get_db_connection, Jsonb


class CrossNodeLearningService:
    """Service for managing cross-node learning distribution."""
    
    def __init__(self):
        self.conn = None
    
    def _ensure_connection(self):
        """Ensure database connection is available."""
        if not self.conn:
            self.conn = get_db_connection()
    
    def _decimal_to_float(self, obj):
        """Convert Decimal to float for JSON serialization."""
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: self._decimal_to_float(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._decimal_to_float(v) for v in obj]
        return obj
    
    def check_promotion_eligibility(self, 
                                   learning_id: str,
                                   learning_type: str,
                                   confidence: float,
                                   evidence_count: int,
                                   validation_state: str,
                                   task_type: str,
                                   contradictions: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Check if learning is eligible for organisational promotion.
        
        Uses deterministic rules to decide eligibility.
        Returns detailed eligibility report.
        """
        self._ensure_connection()
        
        eligibility_check = {
            "learning_id": learning_id,
            "eligible": True,
            "rules_passed": [],
            "rules_failed": [],
            "overall_promotion_confidence": 0.8
        }
        
        try:
            with self.conn.cursor() as cur:
                # Load all active promotion rules
                cur.execute(
                    "SELECT rule_name, rule_type, parameter FROM promotion_eligibility_rules WHERE enabled=TRUE"
                )
                rules = cur.fetchall()
                
                for rule_name, rule_type, params in rules:
                    params = json.loads(params) if isinstance(params, str) else params
                    passed = True
                    reason = ""
                    
                    if rule_type == 'confidence_threshold':
                        threshold = params.get('threshold', 0.75)
                        if confidence >= threshold:
                            eligibility_check["rules_passed"].append(rule_name)
                        else:
                            eligibility_check["rules_failed"].append({
                                "rule": rule_name,
                                "reason": f"Confidence {confidence:.2f} below threshold {threshold}"
                            })
                            passed = False
                    
                    elif rule_type == 'evidence_count':
                        min_count = params.get('count', 2)
                        if evidence_count >= min_count:
                            eligibility_check["rules_passed"].append(rule_name)
                        else:
                            eligibility_check["rules_failed"].append({
                                "rule": rule_name,
                                "reason": f"Evidence count {evidence_count} below minimum {min_count}"
                            })
                            passed = False
                    
                    elif rule_type == 'validation_state_required':
                        allowed_states = params.get('states', ['confirmed', 'recommended'])
                        if validation_state in allowed_states:
                            eligibility_check["rules_passed"].append(rule_name)
                        else:
                            eligibility_check["rules_failed"].append({
                                "rule": rule_name,
                                "reason": f"Validation state '{validation_state}' not in allowed states: {allowed_states}"
                            })
                            passed = False
                    
                    elif rule_type == 'task_type_required':
                        if task_type and len(str(task_type)) > 0:
                            eligibility_check["rules_passed"].append(rule_name)
                        else:
                            eligibility_check["rules_failed"].append({
                                "rule": rule_name,
                                "reason": "Task type is required but not specified"
                            })
                            passed = False
                    
                    elif rule_type == 'contradiction_check':
                        allow_contradictions = params.get('allow_contradictions', False)
                        threshold = params.get('threshold', 0.7)
                        
                        if contradictions:
                            high_conf_contradictions = [c for c in contradictions if c.get('confidence', 0) > threshold]
                            if high_conf_contradictions and not allow_contradictions:
                                eligibility_check["rules_failed"].append({
                                    "rule": rule_name,
                                    "reason": f"High-confidence contradictions found ({len(high_conf_contradictions)})"
                                })
                                passed = False
                            else:
                                eligibility_check["rules_passed"].append(rule_name)
                        else:
                            eligibility_check["rules_passed"].append(rule_name)
                    
                    if not passed:
                        eligibility_check["eligible"] = False
        
        except Exception as e:
            eligibility_check["error"] = str(e)
            eligibility_check["eligible"] = False
        
        return eligibility_check
    
    def promote_learning_to_organisational(self,
                                          learning_id: str,
                                          learning_type: str,
                                          source_node_id: str,
                                          task_type: str,
                                          content: Dict[str, Any],
                                          confidence: float = 0.8,
                                          promotion_reason: str = "automated_promotion") -> Dict[str, Any]:
        """
        Promote learning to organisational level for cross-node sharing.
        """
        self._ensure_connection()
        
        org_learning_id = str(uuid.uuid4())
        
        try:
            with self.conn.cursor() as cur:
                # Check if already promoted (idempotency)
                cur.execute(
                    "SELECT org_learning_id FROM organisational_learning WHERE source_learning_id=%s AND source_type=%s",
                    (learning_id, learning_type)
                )
                existing = cur.fetchone()
                if existing:
                    return {
                        "status": "already_promoted",
                        "org_learning_id": existing[0],
                        "message": "Learning already promoted to organisational level"
                    }
                
                # Insert organisational learning record
                cur.execute(
                    """INSERT INTO organisational_learning
                       (org_learning_id, source_learning_id, source_type, source_node_id, source_task_type,
                        task_type, content, promotion_reason, promotion_confidence, current_state)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING org_learning_id, promoted_at""",
                    (org_learning_id, learning_id, learning_type, source_node_id, task_type,
                     task_type, Jsonb(content), promotion_reason, confidence, 'organisational')
                )
                result = cur.fetchone()
                org_learning_id, promoted_at = result
                
                # Record promotion in history
                cur.execute(
                    """INSERT INTO learning_promotion_history
                       (org_learning_id, transition_from, transition_to, reason, triggered_by)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (org_learning_id, 'node_specific', 'organisational', promotion_reason, 'automated')
                )
            
            self.conn.commit()
            
            return {
                "status": "promoted",
                "org_learning_id": str(org_learning_id),
                "promoted_at": promoted_at.isoformat() if hasattr(promoted_at, 'isoformat') else str(promoted_at)
            }
        
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "error": str(e)}
    
    def get_organisational_learning_for_task_type(self, task_type: str, limit: int = 100) -> Dict[str, Any]:
        """
        Retrieve organisational learning applicable to a specific task type.
        Filters by current state (excludes retired/rejected).
        """
        self._ensure_connection()
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT org_learning_id, source_node_id, source_learning_id, source_type,
                              promotion_confidence, current_state, evidence_count, promoted_at, content
                       FROM organisational_learning
                       WHERE task_type=%s AND current_state IN ('organisational', 'disputed', 'restricted')
                       ORDER BY promoted_at DESC
                       LIMIT %s""",
                    (task_type, limit)
                )
                
                items = []
                for row in cur.fetchall():
                    org_id, source_node, source_learning, learning_type, confidence, state, ev_count, promoted_at, content = row
                    content = json.loads(content) if isinstance(content, str) else content
                    items.append({
                        "org_learning_id": str(org_id),
                        "source_node_id": str(source_node),
                        "source_learning_id": str(source_learning),
                        "source_type": learning_type,
                        "promotion_confidence": float(confidence),
                        "current_state": state,
                        "evidence_count": ev_count,
                        "promoted_at": promoted_at.isoformat() if hasattr(promoted_at, 'isoformat') else str(promoted_at),
                        "content": self._decimal_to_float(content)
                    })
                
                return {
                    "task_type": task_type,
                    "organisational_learning": items,
                    "total": len(items)
                }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def record_cross_node_distribution(self,
                                      org_learning_id: str,
                                      source_node_id: str,
                                      target_node_id: str,
                                      retrieval_trace_id: Optional[str] = None,
                                      context_package_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Record when a node retrieves organisational learning.
        """
        self._ensure_connection()
        
        distribution_id = str(uuid.uuid4())
        
        try:
            with self.conn.cursor() as cur:
                # Check idempotency: prevent duplicate distribution records
                cur.execute(
                    """SELECT distribution_id FROM cross_node_distribution
                       WHERE org_learning_id=%s AND target_node_id=%s AND retrieved_at > now() - interval '1 hour'""",
                    (org_learning_id, target_node_id)
                )
                existing = cur.fetchone()
                if existing:
                    return {
                        "status": "already_recorded",
                        "distribution_id": existing[0],
                        "message": "Distribution already recorded recently"
                    }
                
                cur.execute(
                    """INSERT INTO cross_node_distribution
                       (distribution_id, org_learning_id, source_node_id, target_node_id,
                        retrieval_trace_id, context_package_id, distribution_status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       RETURNING distribution_id, retrieved_at""",
                    (distribution_id, org_learning_id, source_node_id, target_node_id,
                     retrieval_trace_id, context_package_id, 'available')
                )
                result = cur.fetchone()
                distribution_id, retrieved_at = result
            
            self.conn.commit()
            
            return {
                "status": "recorded",
                "distribution_id": str(distribution_id),
                "retrieved_at": retrieved_at.isoformat() if hasattr(retrieved_at, 'isoformat') else str(retrieved_at)
            }
        
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "error": str(e)}
    
    def record_applied_organisational_learning(self,
                                              org_learning_id: str,
                                              attempt_id: str,
                                              applicability_score: float) -> Dict[str, Any]:
        """
        Record when organisational learning is applied to an attempt.
        """
        self._ensure_connection()
        
        applied_org_id = str(uuid.uuid4())
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO applied_organisational_learning
                       (applied_org_id, org_learning_id, attempt_id, applicability_score)
                       VALUES (%s, %s, %s, %s)
                       RETURNING applied_org_id, applied_at""",
                    (applied_org_id, org_learning_id, attempt_id, applicability_score)
                )
                result = cur.fetchone()
                applied_org_id, applied_at = result
            
            self.conn.commit()
            
            return {
                "status": "recorded",
                "applied_org_id": str(applied_org_id),
                "applied_at": applied_at.isoformat() if hasattr(applied_at, 'isoformat') else str(applied_at)
            }
        
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "error": str(e)}
    
    def record_cross_node_evidence_link(self,
                                       org_learning_id: str,
                                       outcome_id: str,
                                       source_node_id: str,
                                       consuming_node_id: str,
                                       agreement_type: str,
                                       agreement_confidence: float,
                                       evidence_summary: Optional[Dict] = None,
                                       distribution_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Record evidence from a consuming node using organisational learning.
        Supports supportive, contradictory, or neutral evidence.
        """
        self._ensure_connection()
        
        link_id = str(uuid.uuid4())
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO cross_node_evidence_links
                       (link_id, org_learning_id, outcome_id, source_node_id, consuming_node_id,
                        agreement_type, agreement_confidence, evidence_summary, distribution_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING link_id, created_at""",
                    (link_id, org_learning_id, outcome_id, source_node_id, consuming_node_id,
                     agreement_type, agreement_confidence, Jsonb(evidence_summary or {}), distribution_id)
                )
                result = cur.fetchone()
                link_id, created_at = result
                
                # Update organisational learning evidence count
                cur.execute(
                    """UPDATE organisational_learning
                       SET evidence_count = evidence_count + 1, updated_at = now()
                       WHERE org_learning_id=%s""",
                    (org_learning_id,)
                )
                
                # If contradictory evidence, consider updating state
                if agreement_type == 'contradictory' and agreement_confidence > 0.7:
                    cur.execute(
                        """SELECT COUNT(*) FROM cross_node_evidence_links
                           WHERE org_learning_id=%s AND agreement_type='contradictory' AND agreement_confidence > 0.7""",
                        (org_learning_id,)
                    )
                    contradictory_count = cur.fetchone()[0]
                    
                    # If multiple contradictions, mark as disputed
                    if contradictory_count >= 2:
                        cur.execute(
                            "SELECT current_state FROM organisational_learning WHERE org_learning_id=%s",
                            (org_learning_id,)
                        )
                        current_state = cur.fetchone()[0]
                        
                        if current_state != 'disputed':
                            cur.execute(
                                """UPDATE organisational_learning
                                   SET current_state='disputed', updated_at=now()
                                   WHERE org_learning_id=%s""",
                                (org_learning_id,)
                            )
                            
                            # Record state transition
                            cur.execute(
                                """INSERT INTO learning_promotion_history
                                   (org_learning_id, transition_from, transition_to, reason, triggered_by)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                (org_learning_id, current_state, 'disputed', 'contradictory_evidence', 'automated')
                            )
            
            self.conn.commit()
            
            return {
                "status": "recorded",
                "link_id": str(link_id),
                "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
            }
        
        except Exception as e:
            self.conn.rollback()
            return {"status": "error", "error": str(e)}
    
    def get_organisational_learning_provenance(self, org_learning_id: str) -> Dict[str, Any]:
        """
        Retrieve complete provenance for organisational learning.
        """
        self._ensure_connection()
        
        try:
            with self.conn.cursor() as cur:
                # Get organisational learning
                cur.execute(
                    """SELECT org_learning_id, source_node_id, source_learning_id, source_type,
                              promotion_confidence, current_state, evidence_count, promoted_at, content
                       FROM organisational_learning
                       WHERE org_learning_id=%s""",
                    (org_learning_id,)
                )
                org_row = cur.fetchone()
                
                if not org_row:
                    return {"status": "not_found"}
                
                org_id, source_node, source_learning, learning_type, confidence, state, ev_count, promoted_at, content = org_row
                content = json.loads(content) if isinstance(content, str) else content
                
                # Get promotion history
                cur.execute(
                    """SELECT transition_from, transition_to, reason, triggered_by, created_at
                       FROM learning_promotion_history
                       WHERE org_learning_id=%s
                       ORDER BY created_at ASC""",
                    (org_learning_id,)
                )
                
                history = []
                for row in cur.fetchall():
                    trans_from, trans_to, reason, triggered, created_at = row
                    history.append({
                        "transition": f"{trans_from} → {trans_to}",
                        "reason": reason,
                        "triggered_by": triggered,
                        "timestamp": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
                    })
                
                # Get cross-node evidence links
                cur.execute(
                    """SELECT consuming_node_id, agreement_type, agreement_confidence, created_at
                       FROM cross_node_evidence_links
                       WHERE org_learning_id=%s
                       ORDER BY created_at DESC""",
                    (org_learning_id,)
                )
                
                cross_node_evidence = []
                for row in cur.fetchall():
                    consuming_node, agreement, agr_confidence, created_at = row
                    cross_node_evidence.append({
                        "consuming_node_id": str(consuming_node),
                        "agreement_type": agreement,
                        "confidence": float(agr_confidence),
                        "timestamp": created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
                    })
                
                return {
                    "org_learning_id": str(org_id),
                    "source_node_id": str(source_node),
                    "source_learning_id": str(source_learning),
                    "source_type": learning_type,
                    "promotion_confidence": float(confidence),
                    "current_state": state,
                    "evidence_count": ev_count,
                    "promoted_at": promoted_at.isoformat() if hasattr(promoted_at, 'isoformat') else str(promoted_at),
                    "promotion_history": history,
                    "cross_node_evidence": cross_node_evidence,
                    "content": self._decimal_to_float(content)
                }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global service instance
_service = None

def get_cross_node_service():
    """Get or create the cross-node learning service."""
    global _service
    if _service is None:
        _service = CrossNodeLearningService()
    return _service
