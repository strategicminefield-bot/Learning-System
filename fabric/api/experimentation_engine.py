"""
Section 16: Experimentation Layer
Controlled autonomous experimentation with hypothesis testing, evidence collection, and analysis.
"""

import json
import hashlib
from typing import Optional, Dict, List, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import logging
from decimal import Decimal
import statistics

logger = logging.getLogger(__name__)


class ExperimentationEngine:
    """Core experimentation engine for controlled strategy testing."""

    def __init__(self, db_conn):
        self.conn = db_conn
        self.cursor = self.conn.cursor()

    def create_experiment(
        self,
        hypothesis: str,
        objective: str,
        control_strategy_id: UUID,
        treatment_strategy_id: UUID,
        task_domain: str,
        metrics: List[Dict],
        min_sample_size: int = 10,
        evidence_threshold: float = 0.70,
        autonomous_initiated: bool = False,
        autonomous_trigger_reason: Optional[str] = None,
        actor_type: str = 'system',
        actor_reference: str = 'experimentation_engine',
        approval_request_id: Optional[str] = None
    ) -> dict:
        """Create a new experiment with control and treatment strategies.
        
        PRE-EXECUTION GOVERNANCE CHECK: Experiment creation is a protected action
        requiring governance evaluation before any DB mutation.
        """
        from governance_enforcement import enforce_protected_action
        
        # PRE-EXECUTION GOVERNANCE CHECK
        governance_check = enforce_protected_action(
            self.conn,
            protected_action_code='experiment_creation',
            actor_type=actor_type,
            actor_reference=actor_reference,
            resource_type='task_domain',
            resource_id=task_domain,
            scope_context={'hypothesis': hypothesis, 'objective': objective},
            approval_request_id=approval_request_id
        )
        
        if not governance_check['permitted']:
            # Governance denied the action
            return {
                'experiment_id': None,
                'status': 'governance_denied',
                'governance_decision': governance_check,
                'reason': governance_check['reason']
            }
        
        experiment_id = uuid4()
        
        # Create experiment record
        self.cursor.execute(
            """INSERT INTO experiments (
                experiment_id, hypothesis, objective, task_domain,
                control_strategy_id, treatment_count, metrics,
                min_sample_size, evidence_threshold,
                autonomous_initiated, autonomous_trigger_reason, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'proposed')""",
            (
                experiment_id, hypothesis, objective, task_domain,
                control_strategy_id, 1, json.dumps(metrics),
                min_sample_size, Decimal(str(evidence_threshold)),
                autonomous_initiated, autonomous_trigger_reason
            )
        )
        
        # Create control arm
        self.cursor.execute(
            """INSERT INTO experiment_arms (
                arm_id, experiment_id, arm_name, arm_type, strategy_id
            ) VALUES (%s, %s, 'control', 'control', %s)""",
            (uuid4(), experiment_id, control_strategy_id)
        )
        
        # Create treatment arm
        self.cursor.execute(
            """INSERT INTO experiment_arms (
                arm_id, experiment_id, arm_name, arm_type, strategy_id
            ) VALUES (%s, %s, 'treatment_A', 'treatment', %s)""",
            (uuid4(), experiment_id, treatment_strategy_id)
        )
        
        # Record status transition
        self.cursor.execute(
            """INSERT INTO experiment_status_history (
                experiment_id, previous_status, new_status, reason
            ) VALUES (%s, %s, 'proposed', 'Experiment created')""",
            (experiment_id, None)
        )
        
        self.conn.commit()
        return {
            'experiment_id': str(experiment_id),
            'status': 'created',
            'governance_decision': governance_check
        }

    def check_eligibility(self, experiment_id: UUID) -> Tuple[bool, str]:
        """Check if experiment is eligible to run."""
        
        self.cursor.execute(
            """SELECT status, max_enrolled_tasks, task_domain FROM experiments WHERE experiment_id = %s""",
            (experiment_id,)
        )
        row = self.cursor.fetchone()
        if not row:
            return False, "Experiment not found"
        
        status, max_tasks, task_domain = row
        
        if status not in ['proposed', 'approved']:
            return False, f"Experiment status {status} not eligible"
        
        # Check available tasks
        if task_domain:
            self.cursor.execute(
                """SELECT COUNT(*) FROM tasks WHERE task_type = %s AND status = 'pending'""",
                (task_domain,)
            )
            available = self.cursor.fetchone()[0] or 0
            if available < 5:
                return False, f"Insufficient available tasks in domain {task_domain}"
        
        # Check active experiment count
        self.cursor.execute(
            """SELECT MAX(max_active_experiments) FROM experiment_budget_config WHERE active = TRUE"""
        )
        max_active = self.cursor.fetchone()[0] or 5
        
        self.cursor.execute(
            """SELECT COUNT(*) FROM experiments WHERE status = 'running'"""
        )
        active_count = self.cursor.fetchone()[0] or 0
        
        if active_count >= max_active:
            return False, f"Maximum active experiments ({max_active}) reached"
        
        return True, "Eligible"

    def start_experiment(self, experiment_id: UUID) -> Tuple[bool, str]:
        """Start an approved experiment."""
        
        eligible, reason = self.check_eligibility(experiment_id)
        if not eligible:
            return False, reason
        
        self.cursor.execute(
            """UPDATE experiments SET status = 'running', updated_at = %s WHERE experiment_id = %s""",
            (datetime.utcnow(), experiment_id)
        )
        
        self.cursor.execute(
            """INSERT INTO experiment_status_history (
                experiment_id, previous_status, new_status, reason
            ) VALUES (%s, 'proposed', 'running', 'Experiment started')""",
            (experiment_id,)
        )
        
        self.conn.commit()
        return True, "Experiment started"

    def assign_task_to_arm(
        self,
        experiment_id: UUID,
        task_id: UUID,
        arm_id: UUID
    ) -> Tuple[bool, UUID, str]:
        """Assign an eligible task to an experiment arm (deterministic)."""
        
        # Check for duplicate enrollment
        self.cursor.execute(
            """SELECT assignment_id FROM experiment_assignments 
               WHERE experiment_id = %s AND task_id = %s""",
            (experiment_id, task_id)
        )
        if self.cursor.fetchone():
            return False, None, "Task already enrolled"
        
        # Create deterministic assignment hash
        assignment_hash = hashlib.sha256(
            f"{experiment_id}{task_id}".encode()
        ).hexdigest()
        
        assignment_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO experiment_assignments (
                assignment_id, experiment_id, arm_id, task_id, assignment_hash
            ) VALUES (%s, %s, %s, %s, %s)""",
            (assignment_id, experiment_id, arm_id, task_id, assignment_hash)
        )
        
        # Increment arm enrollment count
        self.cursor.execute(
            """UPDATE experiment_arms SET enrolled_count = enrolled_count + 1 WHERE arm_id = %s""",
            (arm_id,)
        )
        
        self.conn.commit()
        return True, assignment_id, "Task assigned to arm"

    def record_observation(
        self,
        experiment_id: UUID,
        assignment_id: UUID,
        arm_id: UUID,
        orchestration_decision_id: UUID,
        strategy_used_id: UUID,
        worker_node_id: UUID,
        final_outcome_status: str,
        metric_values: Dict,
        quality_score: Optional[float] = None,
        execution_time_seconds: Optional[int] = None
    ) -> UUID:
        """Record observation from experiment execution."""
        
        observation_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO experiment_observations (
                observation_id, experiment_id, assignment_id, arm_id,
                orchestration_decision_id, strategy_used_id, worker_node_id,
                final_outcome_status, metric_values,
                quality_score, execution_time_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                observation_id, experiment_id, assignment_id, arm_id,
                orchestration_decision_id, strategy_used_id, worker_node_id,
                final_outcome_status, json.dumps(metric_values),
                Decimal(str(quality_score)) if quality_score else None,
                execution_time_seconds
            )
        )
        
        # Update arm counts
        if final_outcome_status == 'success':
            self.cursor.execute(
                """UPDATE experiment_arms SET completed_count = completed_count + 1 WHERE arm_id = %s""",
                (arm_id,)
            )
        else:
            self.cursor.execute(
                """UPDATE experiment_arms SET failed_count = failed_count + 1 WHERE arm_id = %s""",
                (arm_id,)
            )
        
        self.conn.commit()
        return observation_id

    def analyze_experiment(self, experiment_id: UUID) -> Dict:
        """Analyze experiment results and produce conclusion."""
        
        # Retrieve experiment metadata
        self.cursor.execute(
            """SELECT min_sample_size, min_evidence_count, metrics, evidence_threshold
               FROM experiments WHERE experiment_id = %s""",
            (experiment_id,)
        )
        row = self.cursor.fetchone()
        if not row:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        min_sample, min_evidence, metrics_json, threshold = row
        metrics = json.loads(metrics_json) if metrics_json else []
        
        # Retrieve arms
        self.cursor.execute(
            """SELECT arm_id, arm_type, strategy_id FROM experiment_arms 
               WHERE experiment_id = %s ORDER BY arm_type""",
            (experiment_id,)
        )
        arms = {}
        for arm_id, arm_type, strategy_id in self.cursor.fetchall():
            arms[arm_type] = {'arm_id': arm_id, 'strategy_id': strategy_id}
        
        # Collect observations by arm
        observations_by_arm = {'control': [], 'treatment': []}
        
        for arm_type in ['control', 'treatment']:
            if arm_type not in arms:
                continue
            
            arm_id = arms[arm_type]['arm_id']
            
            self.cursor.execute(
                """SELECT metric_values, quality_score, final_outcome_status
                   FROM experiment_observations
                   WHERE experiment_id = %s AND arm_id = %s
                   ORDER BY observation_timestamp""",
                (experiment_id, arm_id)
            )
            
            for metric_vals_json, quality, outcome in self.cursor.fetchall():
                metric_vals = json.loads(metric_vals_json) if metric_vals_json else {}
                observations_by_arm[arm_type].append({
                    'metrics': metric_vals,
                    'quality': float(quality) if quality else 0.0,
                    'outcome': outcome
                })
        
        # Compute summary statistics
        control_summary = self._summarize_observations(observations_by_arm['control'])
        treatment_summary = self._summarize_observations(observations_by_arm['treatment'])
        
        # Determine conclusion
        control_count = len(observations_by_arm['control'])
        treatment_count = len(observations_by_arm['treatment'])
        total_count = control_count + treatment_count
        
        if total_count < min_sample:
            conclusion = "insufficient_evidence"
            effect_direction = "none"
            evidence_sufficiency = "insufficient"
            confidence = 0.0
        else:
            # Simple comparison: if treatment quality > control quality
            treatment_quality = treatment_summary.get('mean_quality', 0.0)
            control_quality = control_summary.get('mean_quality', 0.0)
            
            if treatment_quality > control_quality + 0.1:  # 10% improvement threshold
                conclusion = "supportive"
                effect_direction = "positive"
                effect_size = treatment_quality - control_quality
            elif treatment_quality < control_quality - 0.1:
                conclusion = "contradictory"
                effect_direction = "negative"
                effect_size = control_quality - treatment_quality
            else:
                conclusion = "neutral"
                effect_direction = "none"
                effect_size = 0.0
            
            # Confidence based on sample size
            if total_count >= min_evidence:
                evidence_sufficiency = "adequate"
                confidence = min(0.95, 0.5 + (total_count / (min_evidence * 2)) * 0.45)
            else:
                evidence_sufficiency = "low"
                confidence = 0.5
        
        # Create analysis record
        analysis_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO experiment_analysis (
                analysis_id, experiment_id, total_observations,
                control_count, treatment_count,
                control_metric_summary, treatment_metric_summary,
                conclusion, effect_direction, effect_size,
                evidence_sufficiency, confidence_level
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                analysis_id, experiment_id, total_count,
                control_count, treatment_count,
                json.dumps(control_summary),
                json.dumps(treatment_summary),
                conclusion, effect_direction,
                Decimal(str(effect_size)) if effect_size else 0,
                evidence_sufficiency,
                Decimal(str(confidence))
            )
        )
        
        # Create conclusion record
        conclusion_id = uuid4()
        
        ready_for_promotion = conclusion == "supportive" and evidence_sufficiency in ['adequate', 'high']
        
        self.cursor.execute(
            """INSERT INTO experiment_conclusions (
                conclusion_id, experiment_id, analysis_id,
                conclusion_status, evidence_summary,
                raw_observation_count, ready_for_promotion
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                conclusion_id, experiment_id, analysis_id,
                conclusion, json.dumps({'control': control_summary, 'treatment': treatment_summary}),
                total_count, ready_for_promotion
            )
        )
        
        # Update experiment status
        self.cursor.execute(
            """UPDATE experiments SET status = 'completed', updated_at = %s 
               WHERE experiment_id = %s""",
            (datetime.utcnow(), experiment_id)
        )
        
        self.cursor.execute(
            """INSERT INTO experiment_status_history (
                experiment_id, previous_status, new_status, reason
            ) VALUES (%s, 'running', 'completed', 'Analysis completed')""",
            (experiment_id,)
        )
        
        self.conn.commit()
        
        return {
            "analysis_id": str(analysis_id),
            "conclusion": conclusion,
            "evidence_sufficiency": evidence_sufficiency,
            "confidence": float(confidence),
            "ready_for_promotion": ready_for_promotion,
            "control_count": control_count,
            "treatment_count": treatment_count,
            "effect_direction": effect_direction
        }

    def _summarize_observations(self, observations: List[Dict]) -> Dict:
        """Summarize observations for an arm."""
        if not observations:
            return {"count": 0, "mean_quality": 0.0}
        
        qualities = [o['quality'] for o in observations]
        outcomes = [o['outcome'] for o in observations]
        success_count = outcomes.count('success')
        
        return {
            "count": len(observations),
            "mean_quality": statistics.mean(qualities) if qualities else 0.0,
            "success_rate": success_count / len(observations),
            "success_count": success_count,
            "failure_count": len(observations) - success_count
        }

    def identify_experiment_opportunities(self) -> List[Dict]:
        """Identify opportunities for autonomous experimentation."""
        
        opportunities = []
        
        # Opportunity 1: Strategies with insufficient comparative evidence
        self.cursor.execute(
            """SELECT s1.strategy_id, s2.strategy_id, s1.domain_applicability
               FROM strategies s1
               JOIN strategies s2 ON s1.domain_applicability = s2.domain_applicability
               WHERE s1.strategy_id < s2.strategy_id
               GROUP BY s1.strategy_id, s2.strategy_id, s1.domain_applicability
               LIMIT 5"""
        )
        
        for s1_id, s2_id, domain in self.cursor.fetchall():
            # Check if comparative evidence exists
            self.cursor.execute(
                """SELECT COUNT(DISTINCT strategy_id) FROM strategy_evidence
                   WHERE strategy_id IN (%s, %s)""",
                (s1_id, s2_id)
            )
            if self.cursor.fetchone()[0] < 2:
                opportunities.append({
                    "type": "insufficient_evidence",
                    "strategy_1": str(s1_id),
                    "strategy_2": str(s2_id),
                    "domain": domain,
                    "reason": "Two applicable strategies lack comparative evidence"
                })
        
        return opportunities

    def propose_autonomous_experiment(
        self,
        opportunity: Dict
    ) -> Tuple[bool, Optional[UUID], str]:
        """Propose an autonomous experiment based on identified opportunity."""
        
        # Check if autonomous initiation is enabled
        self.cursor.execute(
            """SELECT allow_autonomous_initiation FROM experiment_budget_config 
               WHERE active = TRUE LIMIT 1"""
        )
        row = self.cursor.fetchone()
        if not row or not row[0]:
            return False, None, "Autonomous experimentation disabled"
        
        # Create opportunity record
        opportunity_id = uuid4()
        
        self.cursor.execute(
            """INSERT INTO experiment_opportunities (
                opportunity_type, strategy_id_1, strategy_id_2, task_domain,
                reason_text, eligible_for_autonomous_initiation, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'proposed')""",
            (
                opportunity.get('type'),
                UUID(opportunity.get('strategy_1')) if opportunity.get('strategy_1') else None,
                UUID(opportunity.get('strategy_2')) if opportunity.get('strategy_2') else None,
                opportunity.get('domain'),
                opportunity.get('reason'),
                True
            )
        )
        
        # Create experiment from opportunity
        try:
            experiment_id = self.create_experiment(
                hypothesis=f"Strategy {opportunity.get('strategy_1')} vs {opportunity.get('strategy_2')}",
                objective="Compare effectiveness on same task domain",
                control_strategy_id=UUID(opportunity.get('strategy_1')),
                treatment_strategy_id=UUID(opportunity.get('strategy_2')),
                task_domain=opportunity.get('domain'),
                metrics=[
                    {"name": "success_rate", "type": "numeric", "threshold": 0.80},
                    {"name": "quality_score", "type": "numeric", "threshold": 0.85}
                ],
                autonomous_initiated=True,
                autonomous_trigger_reason=opportunity.get('reason')
            )
            
            # Update opportunity with experiment
            self.cursor.execute(
                """UPDATE experiment_opportunities SET experiment_id = %s, status = 'experiment_created'
                   WHERE opportunity_id = %s""",
                (experiment_id, opportunity_id)
            )
            
            self.conn.commit()
            return True, experiment_id, "Autonomous experiment proposed"
        
        except Exception as e:
            logger.error(f"Error proposing autonomous experiment: {e}")
            return False, None, str(e)

    def check_experiment_isolation(
        self,
        experiment_id: UUID,
        task_id: UUID
    ) -> bool:
        """Verify that non-enrolled tasks don't receive experimental treatment."""
        
        # Check if task is enrolled
        self.cursor.execute(
            """SELECT assignment_id FROM experiment_assignments
               WHERE experiment_id = %s AND task_id = %s""",
            (experiment_id, task_id)
        )
        
        return self.cursor.fetchone() is None
