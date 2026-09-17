"""
Section 15: Adaptive Orchestration
Evidence-based task orchestration with learned strategy selection, worker allocation, and plan generation.
"""

import json
import hashlib
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class AdaptiveOrchestrationEngine:
    """Core orchestration decision engine using accumulated learning from Sections 2-14."""

    def __init__(self, db_conn):
        self.conn = db_conn
        self.cursor = self.conn.cursor()

    def orchestrate_task(
        self,
        task_id: UUID,
        context: Dict[str, Any],
        node_id: Optional[UUID] = None,
        explicit_constraints: Optional[Dict] = None,
        force_replan_from: Optional[UUID] = None,
        approval_request_id: Optional[str] = None,
        actor_type: str = 'system',
        actor_reference: str = 'orchestration_engine'
    ) -> Dict[str, Any]:
        """
        Main orchestration entry point with governance enforcement.
        
        Steps:
        1. GOVERNANCE: Evaluate orchestration_decision protected action
        2. Load task and context
        3. Check idempotency
        4. Retrieve relevant learning/evidence
        5. Generate strategy candidates
        6. Generate worker candidates
        7. Evaluate candidates using deterministic rules
        8. Select best strategy and worker
        9. Generate execution plan
        10. Create orchestration decision record
        11. Create assignment if worker selected
        12. Return orchestration result
        
        Returns: {
            decision_id, 
            strategy_selected, 
            worker_selected, 
            execution_plan, 
            confidence, 
            rationale,
            assignment_id (if applicable),
            candidates_considered,
            governance_decision (if governance was required)
        }
        """
        try:
            # PRE-EXECUTION GOVERNANCE CHECK
            from governance_enforcement import enforce_protected_action
            
            governance_check = enforce_protected_action(
                self.conn,
                protected_action_code='orchestration_decision',
                actor_type=actor_type,
                actor_reference=actor_reference,
                resource_type='task',
                resource_id=str(task_id),
                scope_context=explicit_constraints,
                approval_request_id=approval_request_id
            )
            
            if not governance_check['permitted']:
                # Governance denied the action
                return {
                    'decision_id': governance_check.get('decision_id'),
                    'strategy_selected': None,
                    'worker_selected': None,
                    'execution_plan': None,
                    'confidence': 0.0,
                    'evidence_sufficiency': 'governance_denied',
                    'rationale': {'governance_denial': governance_check['reason']},
                    'assignment_id': None,
                    'plan_id': None,
                    'candidates_considered': {},
                    'governance_decision': governance_check
                }
            
            # Governance permitted - continue with orchestration
            # Apply constraints if ALLOW_WITH_CONSTRAINTS
            if governance_check['effect'] == 'ALLOW_WITH_CONSTRAINTS' and governance_check['constraints']:
                if explicit_constraints:
                    explicit_constraints.update(governance_check['constraints'])
                else:
                    explicit_constraints = governance_check['constraints']
            
            # 1. Load and validate task
            self.cursor.execute(
                "SELECT task_id, task_type, specification, status FROM tasks WHERE task_id = %s",
                (task_id,)
            )
            task_row = self.cursor.fetchone()
            if not task_row:
                raise ValueError(f"Task {task_id} not found")
            
            task_type = task_row[1]
            task_spec = task_row[2] or {}
            
            # 2. Check idempotency - prevent duplicate active decisions
            request_hash = self._hash_orchestration_request(task_id, context, explicit_constraints)
            existing_decision = self._check_idempotency(task_id, request_hash)
            if existing_decision and not force_replan_from:
                logger.info(f"Idempotent orchestration: returning existing decision {existing_decision}")
                return self._get_decision_result(existing_decision)
            
            # 3. Retrieve relevant learning via Section 9 retrieval
            retrieval_trace = self._retrieve_context(task_id, task_type, node_id)
            
            # 4. Generate strategy candidates from Section 14
            strategy_candidates = self._generate_strategy_candidates(
                task_id, task_type, retrieval_trace, explicit_constraints
            )
            
            # 5. Generate worker candidates from Section 4
            worker_candidates = self._generate_worker_candidates(
                task_id, task_type, strategy_candidates, node_id
            )
            
            # 6. Evaluate and rank candidates using deterministic rules
            strategy_evaluation = self._evaluate_strategy_candidates(
                strategy_candidates, explicit_constraints, retrieval_trace
            )
            worker_evaluation = self._evaluate_worker_candidates(
                worker_candidates, strategy_evaluation.get('selected'), retrieval_trace
            )
            
            # 7. Select best strategy and worker
            selected_strategy = strategy_evaluation.get('selected')
            selected_worker = worker_evaluation.get('selected')
            
            # 8. Generate execution plan
            execution_plan = self._generate_execution_plan(
                task_id, task_type, selected_strategy, retrieval_trace
            )
            
            # 9. Create orchestration decision record
            decision_id = self._record_orchestration_decision(
                task_id=task_id,
                context_considered=context,
                strategy_candidates=strategy_candidates,
                strategy_selected=selected_strategy,
                worker_candidates=worker_candidates,
                worker_selected=selected_worker,
                execution_plan=execution_plan,
                strategy_rationale=strategy_evaluation.get('rationale'),
                worker_rationale=worker_evaluation.get('rationale'),
                confidence_score=strategy_evaluation.get('confidence', 0.50),
                evidence_summary=self._summarize_evidence(strategy_evaluation, worker_evaluation),
                decision_rationale=self._build_decision_rationale(strategy_evaluation, worker_evaluation),
                rule_version=self._get_active_rule_version(),
                replanned_from=force_replan_from
            )
            
            # 10. Create plan record
            plan_id = self._record_orchestration_plan(
                decision_id, selected_strategy, execution_plan, retrieval_trace
            )
            
            # 11. Create assignment if worker selected and strategy applicable
            assignment_id = None
            if selected_worker and selected_strategy:
                assignment_id = self._create_assignment_for_orchestration(
                    task_id, selected_worker, decision_id, execution_plan
                )
            
            # 12. Update idempotency registry
            self._record_idempotency(task_id, request_hash, decision_id, is_retry=force_replan_from is not None)
            
            # 13. Record orchestration event
            self._record_orchestration_event(
                decision_id, "orchestration_completed", "decision",
                {"strategy": str(selected_strategy), "worker": str(selected_worker), "plan": plan_id}
            )
            
            self.conn.commit()
            
            return {
                "decision_id": str(decision_id),
                "strategy_selected": str(selected_strategy) if selected_strategy else None,
                "worker_selected": str(selected_worker) if selected_worker else None,
                "execution_plan": execution_plan,
                "confidence": float(strategy_evaluation.get('confidence', 0.50)),
                "evidence_sufficiency": strategy_evaluation.get('evidence_sufficiency', 'adequate'),
                "rationale": {
                    "strategy_rationale": strategy_evaluation.get('rationale'),
                    "worker_rationale": worker_evaluation.get('rationale'),
                    "decision_rationale": self._build_decision_rationale(strategy_evaluation, worker_evaluation)
                },
                "assignment_id": str(assignment_id) if assignment_id else None,
                "plan_id": str(plan_id),
                "candidates_considered": {
                    "strategy_count": len(strategy_candidates),
                    "worker_count": len(worker_candidates),
                    "strategies_evaluated": len(strategy_evaluation.get('ranked', []))
                }
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Orchestration error for task {task_id}: {e}", exc_info=True)
            raise

    def _hash_orchestration_request(self, task_id: UUID, context: Dict, constraints: Optional[Dict]) -> str:
        """Create deterministic hash of orchestration request for idempotency."""
        content = json.dumps({
            "task_id": str(task_id),
            "context": context,
            "constraints": constraints or {}
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _check_idempotency(self, task_id: UUID, request_hash: str) -> Optional[UUID]:
        """Check if orchestration request is duplicate."""
        self.cursor.execute(
            """SELECT canonical_decision_id FROM orchestration_idempotency_registry
               WHERE task_id = %s AND request_hash = %s AND canonical_decision_id IS NOT NULL
               ORDER BY created_at DESC LIMIT 1""",
            (task_id, request_hash)
        )
        row = self.cursor.fetchone()
        return UUID(row[0]) if row else None

    def _retrieve_context(self, task_id: UUID, task_type: str, node_id: Optional[UUID]) -> Dict:
        """Retrieve relevant context using Section 9 retrieval system."""
        # This would normally call the Section 9 retrieval endpoint
        # For now, we stub a basic retrieval
        self.cursor.execute(
            """SELECT trace_id, context_data FROM context_packages
               WHERE task_id = %s ORDER BY created_at DESC LIMIT 1""",
            (task_id,)
        )
        row = self.cursor.fetchone()
        if row:
            return {"trace_id": UUID(row[0]), "context": row[1] or {}}
        return {"trace_id": None, "context": {}}

    def _generate_strategy_candidates(
        self,
        task_id: UUID,
        task_type: str,
        retrieval_trace: Dict,
        explicit_constraints: Optional[Dict]
    ) -> List[Dict]:
        """Generate candidate strategies from Section 14."""
        candidates = []
        
        # 1. Retrieve applicable strategies from Section 14
        self.cursor.execute(
            """SELECT s.strategy_id, s.strategy_name, sv.version_id, sv.version_number,
                      se.effectiveness_score, se.confidence_level, COUNT(se.evidence_id) as evidence_count,
                      STRING_AGG(DISTINCT se.evidence_type, ',') as evidence_types
               FROM strategies s
               LEFT JOIN strategy_versions sv ON s.strategy_id = sv.strategy_id
               LEFT JOIN strategy_effectiveness se ON sv.version_id = se.version_id
               WHERE s.domain_applicability ILIKE %s OR s.domain_applicability = 'general'
               GROUP BY s.strategy_id, s.strategy_name, sv.version_id, sv.version_number,
                        se.effectiveness_score, se.confidence_level
               ORDER BY se.effectiveness_score DESC NULLS LAST, evidence_count DESC
               LIMIT 10""",
            (f"%{task_type}%",)
        )
        
        for row in self.cursor.fetchall():
            strategy_id, strategy_name, version_id, version_number, effectiveness, confidence, ev_count, ev_types = row
            
            # 2. Check for negative/failure evidence
            negative_evidence = self._get_negative_evidence(UUID(version_id) if version_id else strategy_id)
            
            # 3. Apply constraint filtering
            if explicit_constraints and self._violates_constraints(strategy_name, explicit_constraints):
                continue
            
            candidates.append({
                "strategy_id": str(strategy_id),
                "strategy_name": strategy_name,
                "version_id": str(version_id) if version_id else None,
                "version_number": version_number,
                "effectiveness_score": float(effectiveness) if effectiveness else 0.0,
                "confidence_level": confidence,
                "evidence_count": int(ev_count) if ev_count else 0,
                "evidence_types": (ev_types or "").split(","),
                "negative_evidence": negative_evidence,
                "applicability_score": self._calculate_strategy_applicability(strategy_name, task_type)
            })
        
        # 4. Include fallback/default strategy
        candidates.append({
            "strategy_id": None,
            "strategy_name": "default_execution",
            "version_id": None,
            "effectiveness_score": 0.5,
            "confidence_level": "adequate",
            "evidence_count": 0,
            "is_fallback": True,
            "fallback_reason": "insufficient_evidence" if len(candidates) == 0 else "available_alternative"
        })
        
        return candidates

    def _generate_worker_candidates(
        self,
        task_id: UUID,
        task_type: str,
        strategy_candidates: List[Dict],
        preferred_node: Optional[UUID]
    ) -> List[Dict]:
        """Generate candidate workers from Section 4."""
        candidates = []
        
        # 1. Retrieve available workers with status
        self.cursor.execute(
            """SELECT n.node_id, n.node_name, n.status, wm.tasks_completed, wm.average_quality_score,
                      STRING_AGG(wc.capability_name, ',') as capabilities
               FROM nodes n
               LEFT JOIN worker_metrics wm ON n.node_id = wm.node_id
               LEFT JOIN worker_capabilities wc ON n.node_id = wc.node_id AND wc.enabled = TRUE
               WHERE n.status IN ('available', 'busy')
               GROUP BY n.node_id, n.node_name, n.status, wm.tasks_completed, wm.average_quality_score
               ORDER BY (CASE WHEN n.status = 'available' THEN 0 ELSE 1 END),
                        wm.average_quality_score DESC NULLS LAST
               LIMIT 5""",
            ()
        )
        
        for row in self.cursor.fetchall():
            node_id, node_name, status, tasks_completed, quality_score, capabilities = row
            
            # 2. Check capability match with strategy requirements
            capability_match = self._evaluate_capability_match(
                (capabilities or "").split(","),
                strategy_candidates
            )
            
            # 3. Retrieve worker-specific evidence from Sections 12 (cross-node)
            worker_evidence = self._get_worker_evidence(UUID(node_id))
            
            candidates.append({
                "node_id": str(node_id),
                "node_name": node_name,
                "status": status,
                "availability": status == 'available',
                "tasks_completed": int(tasks_completed) if tasks_completed else 0,
                "quality_score": float(quality_score) if quality_score else 0.5,
                "capabilities": (capabilities or "").split(","),
                "capability_match_score": capability_match,
                "worker_evidence": worker_evidence,
                "applicability_score": self._calculate_worker_applicability(
                    UUID(node_id), task_type, quality_score or 0.5
                ),
                "is_preferred": preferred_node and str(node_id) == str(preferred_node)
            })
        
        return candidates

    def _evaluate_strategy_candidates(
        self,
        candidates: List[Dict],
        explicit_constraints: Optional[Dict],
        retrieval_trace: Dict
    ) -> Dict:
        """Evaluate and rank strategy candidates using deterministic rules."""
        
        # Load active rule configuration
        self.cursor.execute(
            """SELECT * FROM orchestration_rule_config WHERE active = TRUE
               ORDER BY created_at DESC LIMIT 1"""
        )
        rule_row = self.cursor.fetchone()
        if not rule_row:
            # Use defaults
            min_effectiveness = 0.50
            min_confidence_score = 0.50
            respect_negative_evidence = True
        else:
            min_effectiveness = float(rule_row[2])
            min_confidence_score = float(rule_row[3])
            respect_negative_evidence = rule_row[9]
        
        ranked = []
        
        for candidate in candidates:
            if candidate.get('is_fallback'):
                ranked.append({
                    "candidate": candidate,
                    "rank": 999,  # Lowest priority
                    "score": 0.0,
                    "reason": "Fallback/default"
                })
                continue
            
            # Calculate selection score
            effectiveness = candidate.get('effectiveness_score', 0.0)
            evidence_count = candidate.get('evidence_count', 0)
            applicability = candidate.get('applicability_score', 0.5)
            
            # Determine evidence sufficiency
            if evidence_count >= 5:
                evidence_sufficiency = "high"
                confidence_multiplier = 1.0
            elif evidence_count >= 2:
                evidence_sufficiency = "adequate"
                confidence_multiplier = 0.8
            else:
                evidence_sufficiency = "low"
                confidence_multiplier = 0.5
            
            # Apply negative evidence penalty
            negative_evidence = candidate.get('negative_evidence', {})
            negative_penalty = len(negative_evidence.get('failures', [])) * 0.1
            
            # Calculate score
            score = (effectiveness * 0.5 + applicability * 0.3) * confidence_multiplier - negative_penalty
            
            # Check constraint compatibility
            excluded_reason = None
            if explicit_constraints:
                excluded_reason = self._check_constraint_compatibility(
                    candidate.get('strategy_name'), explicit_constraints
                )
            
            ranked.append({
                "candidate": candidate,
                "score": max(0.0, score),
                "effectiveness": effectiveness,
                "evidence_sufficiency": evidence_sufficiency,
                "evidence_count": evidence_count,
                "applicability": applicability,
                "negative_penalty": negative_penalty,
                "excluded_reason": excluded_reason
            })
        
        # Sort by score, exclude those below thresholds
        ranked.sort(key=lambda x: x['score'], reverse=True)
        
        selected = None
        selected_score = 0
        for item in ranked:
            if item['excluded_reason']:
                continue  # Skip excluded candidates
            if item['score'] > 0:
                selected = item['candidate']
                selected_score = item['score']
                break
        
        # Use fallback if no adequate strategy
        if not selected:
            for candidate in candidates:
                if candidate.get('is_fallback'):
                    selected = candidate
                    break
        
        return {
            "selected": selected,
            "ranked": ranked[:5],  # Top 5 for auditing
            "confidence": float(selected_score) if selected else 0.3,
            "evidence_sufficiency": "low" if not selected or selected.get('is_fallback') else "adequate",
            "rationale": f"Selected based on effectiveness ({selected_score:.2f} score), evidence sufficiency, and applicability"
        }

    def _evaluate_worker_candidates(
        self,
        candidates: List[Dict],
        strategy_selected: Optional[Dict],
        retrieval_trace: Dict
    ) -> Dict:
        """Evaluate and rank worker candidates."""
        
        ranked = []
        
        for candidate in candidates:
            availability = candidate['availability']
            quality = candidate['quality_score']
            capability_match = candidate['capability_match_score']
            
            # Score based on availability, quality, and capability match
            availability_score = 1.0 if availability else 0.3
            score = availability_score * 0.6 + quality * 0.3 + capability_match * 0.1
            
            ranked.append({
                "candidate": candidate,
                "score": score,
                "availability": availability,
                "quality": quality,
                "capability_match": capability_match,
                "reason": f"Availability: {availability}, Quality: {quality:.2f}, Match: {capability_match:.2f}"
            })
        
        ranked.sort(key=lambda x: x['score'], reverse=True)
        
        selected = ranked[0]['candidate'] if ranked else None
        
        return {
            "selected": selected,
            "ranked": ranked[:3],
            "rationale": ranked[0]['reason'] if ranked else "No workers available"
        }

    def _generate_execution_plan(
        self,
        task_id: UUID,
        task_type: str,
        strategy: Optional[Dict],
        retrieval_trace: Dict
    ) -> Dict:
        """Generate structured execution plan."""
        
        plan = {
            "strategy_name": strategy.get('strategy_name') if strategy else "default",
            "ordered_steps": [],
            "context_guidance": retrieval_trace.get('context', {}),
            "expected_verification": {
                "success_criteria": "Task completed with acceptable quality",
                "quality_threshold": 0.70
            },
            "constraints": []
        }
        
        # If strategy has method representation, use it for steps
        if strategy and strategy.get('version_id'):
            self.cursor.execute(
                """SELECT method_representation FROM strategy_versions WHERE version_id = %s""",
                (strategy['version_id'],)
            )
            row = self.cursor.fetchone()
            if row and row[0]:
                method_rep = row[0]
                if isinstance(method_rep, str):
                    method_rep = json.loads(method_rep)
                if isinstance(method_rep, dict) and 'steps' in method_rep:
                    plan['ordered_steps'] = method_rep['steps']
        
        # Default steps if no strategy
        if not plan['ordered_steps']:
            plan['ordered_steps'] = [
                {"step_order": 1, "method": "receive_assignment", "expected_output": "assignment_accepted"},
                {"step_order": 2, "method": "process_task", "expected_output": "task_completed"},
                {"step_order": 3, "method": "submit_result", "expected_output": "result_recorded"}
            ]
        
        return plan

    def _record_orchestration_decision(
        self,
        task_id: UUID,
        context_considered: Dict,
        strategy_candidates: List[Dict],
        strategy_selected: Optional[Dict],
        worker_candidates: List[Dict],
        worker_selected: Optional[Dict],
        execution_plan: Dict,
        strategy_rationale: str,
        worker_rationale: str,
        confidence_score: float,
        evidence_summary: Dict,
        decision_rationale: Dict,
        rule_version: int,
        replanned_from: Optional[UUID] = None
    ) -> UUID:
        """Record the orchestration decision in database."""
        
        decision_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO orchestration_decisions (
                decision_id, task_id, decision_timestamp, context_considered,
                strategy_candidates, strategy_selected, strategy_rationale,
                worker_candidates, worker_selected, worker_rationale,
                execution_plan, confidence_score, evidence_sufficiency,
                evidence_summary, decision_rationale, rule_version, replanned_from
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                decision_id,
                task_id,
                datetime.utcnow(),
                json.dumps(context_considered),
                json.dumps(strategy_candidates),
                UUID(strategy_selected['strategy_id']) if strategy_selected and strategy_selected.get('strategy_id') else None,
                strategy_rationale or "No rationale provided",
                json.dumps(worker_candidates),
                UUID(worker_selected['node_id']) if worker_selected else None,
                worker_rationale or "No rationale provided",
                json.dumps(execution_plan),
                confidence_score,
                evidence_summary.get('sufficiency', 'adequate'),
                json.dumps(evidence_summary),
                json.dumps(decision_rationale),
                rule_version,
                replanned_from
            )
        )
        
        return decision_id

    def _record_orchestration_plan(
        self,
        decision_id: UUID,
        strategy: Optional[Dict],
        execution_plan: Dict,
        retrieval_trace: Dict
    ) -> UUID:
        """Record execution plan."""
        
        plan_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO orchestration_plans (
                plan_id, decision_id, strategy_id, strategy_version_id,
                ordered_steps, context_guidance
            ) VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                plan_id,
                decision_id,
                UUID(strategy['strategy_id']) if strategy and strategy.get('strategy_id') else None,
                UUID(strategy['version_id']) if strategy and strategy.get('version_id') else None,
                json.dumps(execution_plan.get('ordered_steps', [])),
                json.dumps(retrieval_trace.get('context', {}))
            )
        )
        
        return plan_id

    def _create_assignment_for_orchestration(
        self,
        task_id: UUID,
        worker: Dict,
        decision_id: UUID,
        execution_plan: Dict
    ) -> UUID:
        """Create assignment based on orchestration decision."""
        
        assignment_id = uuid4()
        node_id = UUID(worker['node_id'])
        
        self.cursor.execute(
            """INSERT INTO assignments (
                assignment_id, task_id, node_id, status,
                created_at, assigned_at
            ) VALUES (%s, %s, %s, 'assigned', %s, %s)""",
            (assignment_id, task_id, node_id, datetime.utcnow(), datetime.utcnow())
        )
        
        # Link assignment to orchestration decision
        self.cursor.execute(
            """UPDATE orchestration_decisions SET assignment_id = %s WHERE decision_id = %s""",
            (assignment_id, decision_id)
        )
        
        # Record event
        self.cursor.execute(
            """INSERT INTO events (
                event_id, event_type, entity_type, entity_id, node_id,
                previous_state, current_state, metadata, created_at
            ) VALUES (%s, 'created', 'assignment', %s, %s, %s, %s, %s, %s)""",
            (
                uuid4(), assignment_id, node_id,
                json.dumps({"status": None}),
                json.dumps({"status": "assigned", "orchestration_decision": str(decision_id)}),
                json.dumps({"orchestration_decision_id": str(decision_id)}),
                datetime.utcnow()
            )
        )
        
        return assignment_id

    def _record_idempotency(
        self,
        task_id: UUID,
        request_hash: str,
        canonical_decision_id: UUID,
        is_retry: bool = False
    ):
        """Record orchestration request for idempotency."""
        
        self.cursor.execute(
            """INSERT INTO orchestration_idempotency_registry (
                task_id, request_hash, canonical_decision_id, is_retry
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (request_hash) DO UPDATE SET canonical_decision_id = %s""",
            (task_id, request_hash, canonical_decision_id, is_retry, canonical_decision_id)
        )

    def _record_orchestration_event(
        self,
        decision_id: UUID,
        event_type: str,
        entity_type: str,
        metadata: Dict
    ):
        """Record orchestration event."""
        
        self.cursor.execute(
            """INSERT INTO events (
                event_id, event_type, entity_type, entity_id,
                current_state, metadata, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                uuid4(), event_type, 'orchestration_decision', decision_id,
                json.dumps({"decision_id": str(decision_id), "event": event_type}),
                json.dumps(metadata),
                datetime.utcnow()
            )
        )

    def _get_decision_result(self, decision_id: UUID) -> Dict:
        """Retrieve result for existing decision."""
        
        self.cursor.execute(
            """SELECT strategy_selected, worker_selected, execution_plan, confidence_score,
                      decision_rationale, assignment_id
               FROM orchestration_decisions WHERE decision_id = %s""",
            (decision_id,)
        )
        
        row = self.cursor.fetchone()
        if not row:
            return {}
        
        return {
            "decision_id": str(decision_id),
            "strategy_selected": str(row[0]) if row[0] else None,
            "worker_selected": str(row[1]) if row[1] else None,
            "execution_plan": row[2] or {},
            "confidence": float(row[3]) if row[3] else 0.5,
            "rationale": row[4] or {},
            "assignment_id": str(row[5]) if row[5] else None
        }

    # ===== Helper Methods =====

    def _get_negative_evidence(self, entity_id: UUID) -> Dict:
        """Retrieve negative evidence for a strategy."""
        # Simplified: would query strategy_evidence for failures, repairs, etc.
        return {"failures": [], "repairs_required": []}

    def _violates_constraints(self, strategy_name: str, constraints: Dict) -> bool:
        """Check if strategy violates explicit constraints."""
        # Simplified constraint checking
        if constraints.get('excluded_strategies') and strategy_name in constraints['excluded_strategies']:
            return True
        return False

    def _calculate_strategy_applicability(self, strategy_name: str, task_type: str) -> float:
        """Calculate strategy applicability to task type."""
        # Simplified: would use Section 14 strategy_applicability metrics
        return 0.75

    def _check_constraint_compatibility(self, strategy_name: str, constraints: Dict) -> Optional[str]:
        """Check if strategy is compatible with constraints."""
        if constraints.get('excluded_strategies') and strategy_name in constraints['excluded_strategies']:
            return f"Strategy {strategy_name} excluded by constraint"
        return None

    def _evaluate_capability_match(self, capabilities: List[str], strategies: List[Dict]) -> float:
        """Evaluate worker capability match with required strategies."""
        # Simplified: would check required vs available capabilities
        return 0.75

    def _get_worker_evidence(self, node_id: UUID) -> Dict:
        """Retrieve worker-specific evidence from Sections 4, 12."""
        self.cursor.execute(
            """SELECT tasks_completed, tasks_failed, average_quality_score, successful_attempts, total_attempts
               FROM worker_metrics WHERE node_id = %s""",
            (node_id,)
        )
        row = self.cursor.fetchone()
        if row:
            return {
                "tasks_completed": row[0] or 0,
                "tasks_failed": row[1] or 0,
                "quality_score": float(row[2]) if row[2] else 0.5,
                "success_rate": float(row[3] / row[4]) if row[4] and row[4] > 0 else 0.5
            }
        return {}

    def _calculate_worker_applicability(self, node_id: UUID, task_type: str, quality: float) -> float:
        """Calculate worker applicability to task type."""
        # Simplified: would use cross-node learning
        return min(quality, 1.0)

    def _summarize_evidence(self, strategy_eval: Dict, worker_eval: Dict) -> Dict:
        """Summarize evidence for decision record."""
        return {
            "sufficiency": strategy_eval.get('evidence_sufficiency', 'adequate'),
            "strategy_evidence_count": sum(c.get('evidence_count', 0) for c in strategy_eval.get('ranked', [])),
            "contradictions": 0,
            "cross_node_evidence": 0
        }

    def _build_decision_rationale(self, strategy_eval: Dict, worker_eval: Dict) -> Dict:
        """Build comprehensive decision rationale."""
        return {
            "why_selected": strategy_eval.get('rationale', '') + " / " + worker_eval.get('rationale', ''),
            "alternatives_considered": len(strategy_eval.get('ranked', [])),
            "uncertainty": 1.0 - strategy_eval.get('confidence', 0.5),
            "fallback_available": True
        }

    def _get_active_rule_version(self) -> int:
        """Get current active orchestration rule version."""
        self.cursor.execute("SELECT rule_version FROM orchestration_rule_config WHERE active = TRUE ORDER BY created_at DESC LIMIT 1")
        row = self.cursor.fetchone()
        return int(row[0]) if row else 1

    def _record_orchestration_attempt_outcome(
        self,
        decision_id: UUID,
        assignment_id: UUID,
        task_id: UUID,
        outcome_status: str,
        outcome_id: Optional[UUID] = None,
        attempts_required: int = 1,
        quality_score: Optional[float] = None
    ) -> UUID:
        """Record outcome of orchestration decision execution."""
        
        outcome_eval_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO orchestration_outcomes (
                outcome_evaluation_id, decision_id, assignment_id, task_id,
                actual_outcome_status, actual_outcome_id, attempts_required, actual_quality_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                outcome_eval_id, decision_id, assignment_id, task_id,
                outcome_status, outcome_id, attempts_required, quality_score or 0.5
            )
        )
        
        # Update decision record
        self.cursor.execute(
            """UPDATE orchestration_decisions
               SET final_outcome_status = %s, final_outcome_id = %s, attempts_made = %s, updated_at = %s
               WHERE decision_id = %s""",
            (outcome_status, outcome_id, attempts_required, datetime.utcnow(), decision_id)
        )
        
        return outcome_eval_id

    def trigger_replan(
        self,
        original_decision_id: UUID,
        trigger_type: str,
        trigger_reason: str,
        attempt_number: int = 1
    ) -> UUID:
        """Trigger replanning after failure/unavailability/constraint conflict."""
        
        trigger_id = uuid4()
        
        # Record replan trigger
        self.cursor.execute(
            """INSERT INTO orchestration_replan_triggers (
                trigger_id, original_decision_id, trigger_type, trigger_reason, attempt_number
            ) VALUES (%s, %s, %s, %s, %s)""",
            (trigger_id, original_decision_id, trigger_type, trigger_reason, attempt_number)
        )
        
        # Get original decision
        self.cursor.execute(
            """SELECT task_id, context_considered FROM orchestration_decisions WHERE decision_id = %s""",
            (original_decision_id,)
        )
        row = self.cursor.fetchone()
        if not row:
            raise ValueError(f"Original decision {original_decision_id} not found")
        
        task_id, context_json = row
        context = json.loads(context_json) if context_json else {}
        
        # Orchestrate new plan
        new_decision = self.orchestrate_task(
            task_id=UUID(task_id),
            context=context,
            force_replan_from=original_decision_id
        )
        
        new_decision_id = UUID(new_decision['decision_id'])
        
        # Link old → new decision
        self.cursor.execute(
            """UPDATE orchestration_decisions SET replanned_to = %s WHERE decision_id = %s""",
            (new_decision_id, original_decision_id)
        )
        
        self.cursor.execute(
            """UPDATE orchestration_replan_triggers SET new_decision_id = %s WHERE trigger_id = %s""",
            (new_decision_id, trigger_id)
        )
        
        self.conn.commit()
        
        return new_decision_id
