"""
SECTION 21: SYSTEM-LEVEL EVALUATION ENGINE

Evaluates whether the Learning Fabric organization is becoming more effective.

Core principle: Measures and evaluates using real production evidence.
Does NOT independently modify configuration, promote learning, evolve nodes, or bypass governance.
"""

import uuid
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timedelta
import psycopg
import json
from decimal import Decimal


class SystemEvaluationEngine:
    """Core evaluation engine for organizational effectiveness."""

    def __init__(self, db_conn: psycopg.Connection):
        self.conn = db_conn
        self.cursor = self.conn.cursor()
        self.rule_version = 1

    def create_evaluation_run(
        self,
        evaluation_type: str,
        population_definition: Dict,
        scope: Optional[str] = None,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
        baseline_definition: Optional[Dict] = None,
        trigger_source: str = "system",
        initiating_actor_type: str = "system",
        initiating_actor_reference: str = "evaluation_engine"
    ) -> str:
        """Create a new system evaluation run."""
        
        evaluation_id = str(uuid.uuid4())
        data_cutoff = datetime.utcnow()
        
        self.cursor.execute(
            """
            INSERT INTO system_evaluation_runs (
                evaluation_id, evaluation_type, status, evaluation_rule_version,
                population_definition, scope, time_window_start, time_window_end,
                baseline_definition, data_cutoff_timestamp,
                trigger_source, initiating_actor_type, initiating_actor_reference
            ) VALUES (%s, %s, 'created', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                evaluation_id, evaluation_type, self.rule_version,
                json.dumps(population_definition), scope,
                time_window_start, time_window_end,
                json.dumps(baseline_definition) if baseline_definition else None,
                data_cutoff,
                trigger_source, initiating_actor_type, initiating_actor_reference
            )
        )
        self.conn.commit()
        return evaluation_id

    def calculate_task_completion_metrics(
        self,
        evaluation_id: str,
        population_definition: Dict,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate task completion metrics from real task_outcomes data."""
        
        # Build query based on population definition
        where_clauses = []
        params = []
        
        if time_window_start:
            where_clauses.append("task_outcomes.created_at >= %s")
            params.append(time_window_start)
        
        if time_window_end:
            where_clauses.append("task_outcomes.created_at <= %s")
            params.append(time_window_end)
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Count completions and failures
        self.cursor.execute(
            f"""
            SELECT
                COUNT(*) as total_tasks,
                COUNT(DISTINCT task_id) as distinct_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_tasks,
                SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END) as abandoned_tasks,
                AVG(CASE WHEN attempts_recorded > 0 THEN attempts_recorded ELSE 1 END) as avg_attempts
            FROM task_outcomes
            WHERE {where_clause}
            """,
            params
        )
        
        row = self.cursor.fetchone()
        if not row:
            return {'status': 'insufficient_evidence', 'reason': 'No task outcomes found'}
        
        total_tasks = row[0]
        distinct_tasks = row[1]
        completed = row[2] or 0
        failed = row[3] or 0
        abandoned = row[4] or 0
        avg_attempts = float(row[5]) if row[5] else 1.0
        
        completion_rate = completed / total_tasks if total_tasks > 0 else 0
        failure_rate = failed / total_tasks if total_tasks > 0 else 0
        
        return {
            'status': 'calculated',
            'metrics': {
                'total_tasks': total_tasks,
                'distinct_tasks': distinct_tasks,
                'completed_tasks': completed,
                'completed_rate': float(completion_rate),
                'failed_tasks': failed,
                'failure_rate': float(failure_rate),
                'abandoned_tasks': abandoned,
                'avg_attempts_per_task': avg_attempts
            },
            'sample_info': {
                'sample_count': total_tasks,
                'independent_entities': distinct_tasks
            }
        }

    def calculate_verification_metrics(
        self,
        evaluation_id: str,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate verification pass rate from results table."""
        
        where_clauses = []
        params = []
        
        if time_window_start:
            where_clauses.append("results.created_at >= %s")
            params.append(time_window_start)
        
        if time_window_end:
            where_clauses.append("results.created_at <= %s")
            params.append(time_window_end)
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        self.cursor.execute(
            f"""
            SELECT
                COUNT(*) as total_results,
                COUNT(DISTINCT task_id) as distinct_tasks,
                SUM(CASE WHEN verified = true THEN 1 ELSE 0 END) as verified_results,
                SUM(CASE WHEN verification_passed = true THEN 1 ELSE 0 END) as verification_passed,
                SUM(CASE WHEN verification_passed = false THEN 1 ELSE 0 END) as verification_failed
            FROM results
            WHERE {where_clause}
            """,
            params
        )
        
        row = self.cursor.fetchone()
        if not row or row[0] == 0:
            return {'status': 'insufficient_evidence', 'reason': 'No results found'}
        
        total = row[0]
        distinct = row[1]
        verified = row[2] or 0
        passed = row[3] or 0
        failed = row[4] or 0
        
        verification_rate = verified / total if total > 0 else 0
        pass_rate = passed / verified if verified > 0 else 0
        
        return {
            'status': 'calculated',
            'metrics': {
                'total_results': total,
                'distinct_tasks': distinct,
                'verification_rate': float(verification_rate),
                'verified_results': verified,
                'verification_passed': passed,
                'verification_failed': failed,
                'pass_rate_given_verified': float(pass_rate)
            }
        }

    def calculate_experiment_metrics(
        self,
        evaluation_id: str,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate experiment effectiveness from experiments table."""
        
        where_clauses = ["experiments.status IN ('completed', 'concluded')"]
        params = []
        
        if time_window_start:
            where_clauses.append("experiments.created_at >= %s")
            params.append(time_window_start)
        
        if time_window_end:
            where_clauses.append("experiments.created_at <= %s")
            params.append(time_window_end)
        
        where_clause = " AND ".join(where_clauses)
        
        self.cursor.execute(
            f"""
            SELECT
                COUNT(*) as total_experiments,
                SUM(CASE WHEN conclusion IS NOT NULL THEN 1 ELSE 0 END) as experiments_with_conclusion,
                SUM(CASE WHEN conclusion LIKE '%treatment_superior%' THEN 1 ELSE 0 END) as treatment_superior,
                SUM(CASE WHEN conclusion LIKE '%control_superior%' THEN 1 ELSE 0 END) as control_superior,
                SUM(CASE WHEN conclusion LIKE '%insufficient%' THEN 1 ELSE 0 END) as insufficient_evidence
            FROM experiments
            WHERE {where_clause}
            """,
            params
        )
        
        row = self.cursor.fetchone()
        if not row or row[0] == 0:
            return {'status': 'insufficient_evidence', 'reason': 'No experiments found'}
        
        total = row[0]
        with_conclusion = row[1] or 0
        treatment_superior = row[2] or 0
        control_superior = row[3] or 0
        insufficient = row[4] or 0
        
        conclusion_rate = with_conclusion / total if total > 0 else 0
        useful_rate = (treatment_superior + control_superior) / total if total > 0 else 0
        
        return {
            'status': 'calculated',
            'metrics': {
                'total_experiments': total,
                'experiments_with_conclusion': with_conclusion,
                'treatment_superior': treatment_superior,
                'control_superior': control_superior,
                'insufficient_evidence_count': insufficient,
                'conclusion_rate': float(conclusion_rate),
                'useful_experiment_rate': float(useful_rate)
            }
        }

    def evaluate_evidence_sufficiency(
        self,
        sample_count: int,
        independent_entities: int,
        metric_type: str
    ) -> Tuple[bool, str]:
        """Determine if evidence is sufficient for evaluation."""
        
        # Use versioned rules
        self.cursor.execute(
            "SELECT minimum_sample_count, minimum_independent_entities FROM system_evaluation_rule_versions WHERE rule_version = %s",
            (self.rule_version,)
        )
        rule = self.cursor.fetchone()
        
        if not rule:
            return False, "evaluation_rules_not_found"
        
        min_samples, min_entities = rule
        
        if sample_count < min_samples:
            return False, f"insufficient_samples: {sample_count} < {min_samples}"
        
        if independent_entities < min_entities:
            return False, f"insufficient_entities: {independent_entities} < {min_entities}"
        
        return True, "sufficient"

    def persist_metric(
        self,
        evaluation_id: str,
        population_id: Optional[str],
        metric_name: str,
        metric_category: str,
        value: float,
        sample_count: int,
        independent_entities: int,
        data_sources: Dict
    ) -> str:
        """Persist a calculated metric."""
        
        metric_id = str(uuid.uuid4())
        
        self.cursor.execute(
            """
            INSERT INTO system_evaluation_metrics (
                metric_id, evaluation_id, population_id, metric_name, metric_category,
                value, sample_count, independent_entities, data_sources
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                metric_id, evaluation_id, population_id, metric_name, metric_category,
                Decimal(str(value)), sample_count, independent_entities,
                json.dumps(data_sources)
            )
        )
        self.conn.commit()
        return metric_id

    def persist_finding(
        self,
        evaluation_id: str,
        finding_type: str,
        scope: str,
        population_id: Optional[str],
        metric_references: Dict,
        evidence_sufficiency: str,
        direction: str,
        explanation: str,
        limitations: Optional[str] = None
    ) -> str:
        """Persist an evaluation finding."""
        
        finding_id = str(uuid.uuid4())
        confidence = "supported" if evidence_sufficiency == "sufficient" else "limited"
        
        self.cursor.execute(
            """
            INSERT INTO system_evaluation_findings (
                finding_id, evaluation_id, finding_type, scope, population_id,
                metric_references, evidence_sufficiency, direction, confidence_level,
                explanation, limitations
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                finding_id, evaluation_id, finding_type, scope, population_id,
                json.dumps(metric_references), evidence_sufficiency, direction,
                confidence, explanation, limitations
            )
        )
        self.conn.commit()
        return finding_id

    def complete_evaluation(
        self,
        evaluation_id: str,
        conclusion: str,
        evidence_sufficiency: str,
        result_data: Dict,
        limitations: Optional[str] = None
    ) -> bool:
        """Mark evaluation as completed."""
        
        self.cursor.execute(
            """
            UPDATE system_evaluation_runs
            SET status = 'completed',
                completed_at = NOW(),
                conclusion = %s,
                evidence_sufficiency = %s,
                result = %s,
                limitations = %s
            WHERE evaluation_id = %s
            """,
            (
                conclusion, evidence_sufficiency,
                json.dumps(result_data), limitations,
                evaluation_id
            )
        )
        self.conn.commit()
        
        # Record event
        self._record_evaluation_event(
            evaluation_id, "system_evaluation_completed",
            "success", f"Evaluation {evaluation_id} completed with conclusion: {conclusion}"
        )
        
        return True

    def _record_evaluation_event(
        self,
        evaluation_id: str,
        event_type: str,
        severity: str,
        description: str
    ):
        """Record evaluation event."""
        
        event_id = str(uuid.uuid4())
        self.cursor.execute(
            """
            INSERT INTO system_evaluation_events (
                event_id, event_type, evaluation_id, severity, description
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (event_id, event_type, evaluation_id, severity, description)
        )
        self.conn.commit()

    def run_baseline_evaluation(
        self,
        population_definition: Dict,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Run a baseline evaluation on a population."""
        
        # Create evaluation run
        eval_id = self.create_evaluation_run(
            evaluation_type="baseline",
            population_definition=population_definition,
            time_window_start=time_window_start,
            time_window_end=time_window_end
        )
        
        # Calculate metrics
        completion_metrics = self.calculate_task_completion_metrics(
            eval_id, population_definition, time_window_start, time_window_end
        )
        
        verification_metrics = self.calculate_verification_metrics(
            eval_id, time_window_start, time_window_end
        )
        
        experiment_metrics = self.calculate_experiment_metrics(
            eval_id, time_window_start, time_window_end
        )
        
        # Determine sufficiency
        sufficient = True
        sufficiency_msg = "sufficient"
        
        if completion_metrics.get('status') != 'calculated':
            sufficient = False
            sufficiency_msg = "insufficient_completion_data"
        elif completion_metrics.get('sample_info', {}).get('sample_count', 0) < 5:
            sufficient = False
            sufficiency_msg = "insufficient_sample_count"
        
        # Persist findings if sufficient
        findings = []
        if sufficient:
            # Create finding for completion rate
            completion_rate = completion_metrics['metrics']['completed_rate']
            finding_id = self.persist_finding(
                eval_id,
                finding_type="baseline_completion",
                scope="overall",
                population_id=None,
                metric_references={"completion_rate": completion_rate},
                evidence_sufficiency="sufficient",
                direction="neutral",
                explanation=f"Baseline completion rate: {completion_rate:.2%}",
                limitations=None
            )
            findings.append(finding_id)
        
        # Complete evaluation
        self.complete_evaluation(
            eval_id,
            conclusion="sufficient" if sufficient else "insufficient_evidence",
            evidence_sufficiency=sufficiency_msg,
            result_data={
                "completion_metrics": completion_metrics,
                "verification_metrics": verification_metrics,
                "experiment_metrics": experiment_metrics,
                "findings": findings
            }
        )
        
        return {
            "evaluation_id": eval_id,
            "status": "completed",
            "conclusion": "sufficient" if sufficient else "insufficient_evidence",
            "metrics": {
                "completion": completion_metrics,
                "verification": verification_metrics,
                "experiments": experiment_metrics
            },
            "findings": findings
        }
