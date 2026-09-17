"""
Section 11: Learning Feedback & Validation Engine

Closes the learning loop by evaluating applied learning against outcomes.

Core responsibility:
  Attempt + Applied Learning + Outcome
    → Evaluate effect
    → Record immutable evidence
    → Accumulate evidence across repetitions
    → Deterministically adjust confidence based on rules
    → Update validation state
    → Update memory/provenance

Maintains operational distinction between:
  - Observed association (learning was applied, outcome followed)
  - Evidence strength (how much/what quality of evidence)
  - Causality claims (carefully bounded)
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal
import uuid
import json

from sqlalchemy import text


class LearningFeedbackEngine:
    """Deterministic learning feedback and validation."""

    def __init__(self, db_conn):
        self.db = db_conn
        self._load_config()

    def _load_config(self) -> None:
        """Load feedback configuration from database."""
        query = "SELECT * FROM feedback_config WHERE config_name = 'default' AND active = TRUE"
        try:
            result = self.db.execute(text(query)).fetchone()
            if result:
                # Handle both Row and tuple types
                if hasattr(result, 'keys'):
                    self.config = dict(result)
                else:
                    # For tuples, use column names from query
                    cols = ['config_id', 'config_name', 'confidence_increase_per_supportive',
                            'confidence_decrease_per_contradictory', 'min_evidence_for_confidence_move',
                            'confidence_min', 'confidence_max', 'emerging_threshold_min_evidence',
                            'emerging_threshold_supportive_ratio', 'validated_threshold_min_evidence',
                            'validated_threshold_supportive_ratio', 'disputed_threshold_min_evidence',
                            'disputed_threshold_contradictory_ratio', 'rejected_threshold_min_evidence',
                            'rejected_threshold_contradictory_ratio', 'supportive_quality_delta_threshold',
                            'contradictory_quality_delta_threshold', 'min_baseline_attempts', 'active']
                    self.config = dict(zip(cols[:len(result)], result))
            else:
                self.config = None
        except Exception:
            self.config = None
        else:
            # Fallback defaults
            self.config = {
                'confidence_increase_per_supportive': 0.10,
                'confidence_decrease_per_contradictory': 0.10,
                'min_evidence_for_confidence_move': 3,
                'confidence_min': 0.05,
                'confidence_max': 0.95,
                'emerging_threshold_min_evidence': 3,
                'emerging_threshold_supportive_ratio': 0.50,
                'validated_threshold_min_evidence': 5,
                'validated_threshold_supportive_ratio': 0.70,
                'disputed_threshold_min_evidence': 5,
                'disputed_threshold_contradictory_ratio': 0.30,
                'rejected_threshold_min_evidence': 5,
                'rejected_threshold_contradictory_ratio': 0.80,
                'supportive_quality_delta_threshold': 0.05,
                'contradictory_quality_delta_threshold': 0.05,
                'min_baseline_attempts': 3,
            }

    def record_feedback(
        self,
        attempt_id: str,
        task_id: str,
        node_id: str,
        outcome_id: Optional[str],
        applied_learning_list: List[Dict[str, Any]],
        result: Dict[str, Any],
        quality_score: float,
        outcome_status: str,
        execution_time_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Record feedback for attempt outcome.

        Args:
            attempt_id: Attempt UUID
            task_id: Task UUID
            node_id: Node UUID
            outcome_id: Outcome UUID
            applied_learning_list: List of applied learning items with effect_classification
            result: Result dict
            quality_score: 0-1 quality metric
            outcome_status: success, partial, failure
            execution_time_seconds: Optional execution time

        Returns:
            {
                'feedback_records_created': int,
                'evidence_updated': int,
                'confidence_adjustments': List[Dict],
                'state_transitions': List[Dict],
                'processing_trace': Dict,
                'duplicate_detected': bool,
                'original_feedback_id': Optional[str]
            }
        """

        processing_log_id = str(uuid.uuid4())
        trace = {
            'stage': 'init',
            'timestamp': datetime.utcnow().isoformat(),
            'attempt_id': attempt_id,
            'applied_learning_count': len(applied_learning_list)
        }

        try:
            # Check for duplicate processing
            duplicate_check = self._check_feedback_duplicate(attempt_id, outcome_id)
            if duplicate_check['is_duplicate']:
                trace['stage'] = 'duplicate_detected'
                self._record_processing_log(
                    processing_log_id, attempt_id, outcome_id,
                    'duplicate', None, duplicate_check['original_feedback_id'],
                    trace
                )
                return {
                    'duplicate_detected': True,
                    'original_feedback_id': duplicate_check['original_feedback_id'],
                    'processing_log_id': processing_log_id,
                }

            # Get baseline for comparison
            trace['stage'] = 'baseline_retrieval'
            baseline = self._get_baseline(task_id, node_id, outcome_status)

            # Process each applied learning item
            trace['stage'] = 'feedback_generation'
            feedback_records = []
            evidence_updates = []

            for learning_item in applied_learning_list:
                # Classify effect
                effect = self._classify_effect(
                    quality_score=quality_score,
                    baseline=baseline,
                    learning_item=learning_item,
                    outcome_status=outcome_status
                )

                # Create feedback record
                fb_record = self._create_feedback_record(
                    attempt_id=attempt_id,
                    task_id=task_id,
                    node_id=node_id,
                    outcome_id=outcome_id,
                    applied_learning_id=learning_item.get('applied_id'),
                    learning_type=learning_item.get('type'),
                    learning_id=learning_item.get('id'),
                    result=result,
                    quality_score=quality_score,
                    outcome_status=outcome_status,
                    execution_time_seconds=execution_time_seconds,
                    effect=effect,
                    baseline=baseline
                )

                fb_record_id = self._insert_feedback_record(fb_record)
                feedback_records.append({
                    'feedback_id': fb_record_id,
                    'learning_id': learning_item.get('id'),
                    'learning_type': learning_item.get('type'),
                    'effect_classification': effect['classification']
                })

                # Track for evidence update
                evidence_updates.append({
                    'learning_id': learning_item.get('id'),
                    'learning_type': learning_item.get('type'),
                    'effect_classification': effect['classification'],
                    'quality_score': quality_score,
                    'baseline_quality': baseline.get('baseline_quality'),
                    'quality_delta': effect.get('quality_delta')
                })

            trace['feedback_records_created'] = len(feedback_records)

            # Update evidence accumulation
            trace['stage'] = 'evidence_accumulation'
            evidence_affected = []
            for update in evidence_updates:
                updated_accum = self._update_evidence_accumulation(
                    learning_id=update['learning_id'],
                    learning_type=update['learning_type'],
                    effect_classification=update['effect_classification'],
                    quality_score=update['quality_score'],
                    quality_delta=update['quality_delta'],
                    task_type=baseline.get('task_type'),
                    node_id=node_id
                )
                evidence_affected.append(updated_accum)

            trace['evidence_updated'] = len(evidence_affected)

            # Adjust confidence scores
            trace['stage'] = 'confidence_adjustment'
            confidence_adjustments = []
            for accum in evidence_affected:
                adj = self._adjust_confidence(
                    learning_id=accum['learning_id'],
                    learning_type=accum['learning_type'],
                    evidence_accumulation=accum,
                    trigger_feedback_ids=feedback_records
                )
                if adj:
                    confidence_adjustments.append(adj)

            trace['confidence_adjustments'] = len(confidence_adjustments)

            # Update validation states
            trace['stage'] = 'validation_state_update'
            state_transitions = []
            for accum in evidence_affected:
                transition = self._update_validation_state(
                    learning_id=accum['learning_id'],
                    learning_type=accum['learning_type'],
                    evidence_accumulation=accum,
                    trigger_feedback_ids=feedback_records
                )
                if transition:
                    state_transitions.append(transition)

            trace['state_transitions'] = len(state_transitions)

            # Update memory/provenance metadata
            trace['stage'] = 'memory_metadata_update'
            self._update_learning_metadata(evidence_affected)

            # Record processing success
            trace['stage'] = 'complete'
            self._record_processing_log(
                processing_log_id, attempt_id, outcome_id,
                'completed', None, None,
                trace,
                len(feedback_records),
                len(evidence_affected),
                len(confidence_adjustments),
                len(state_transitions)
            )

            return {
                'feedback_records_created': len(feedback_records),
                'evidence_updated': len(evidence_affected),
                'confidence_adjustments': confidence_adjustments,
                'state_transitions': state_transitions,
                'processing_trace': trace,
                'duplicate_detected': False,
                'original_feedback_id': None,
            }

        except Exception as e:
            trace['stage'] = 'error'
            trace['error'] = str(e)
            self._record_processing_log(
                processing_log_id, attempt_id, outcome_id,
                'failed', str(e), None,
                trace
            )
            raise

    def _check_feedback_duplicate(self, attempt_id: str, outcome_id: Optional[str]) -> Dict[str, Any]:
        """Check if feedback already processed for this attempt."""
        query = """
            SELECT processing_status, original_feedback_id
            FROM feedback_processing_log
            WHERE attempt_id = :attempt_id
              AND processing_status IN ('completed', 'duplicate')
            ORDER BY created_at DESC
            LIMIT 1
        """
        result = self.db.execute(
            text(query),
            {'attempt_id': attempt_id}
        ).fetchone()

        if result:
            return {
                'is_duplicate': True,
                'original_feedback_id': result[1]
            }
        return {'is_duplicate': False, 'original_feedback_id': None}

    def _get_baseline(
        self,
        task_id: str,
        node_id: str,
        outcome_status: str
    ) -> Dict[str, Any]:
        """Retrieve baseline for comparison."""
        # Get same task type attempts (excluding this one)
        query = """
            SELECT
                t.task_type,
                COUNT(DISTINCT a.attempt_id) as attempt_count,
                AVG(ro.quality_score) as avg_quality,
                COUNT(CASE WHEN ro.outcome_status = 'success' THEN 1 END) as success_count,
                AVG(ro.execution_time_seconds) as avg_time
            FROM tasks t
            JOIN assignments a ON t.task_id = a.task_id
            JOIN attempts a2 ON a.assignment_id = a2.assignment_id
            JOIN results r ON a2.attempt_id = r.attempt_id
            JOIN task_outcomes ro ON a2.attempt_id = ro.attempt_id
            WHERE t.task_type = (SELECT task_type FROM tasks WHERE task_id = :task_id)
              AND ro.outcome_status IN ('success', 'partial')
            GROUP BY t.task_type
        """

        result = self.db.execute(
            text(query),
            {'task_id': task_id}
        ).fetchone()

        if result and result[1] >= self.config['min_baseline_attempts']:
            return {
                'baseline_type': 'same_task_type',
                'task_type': result[0],
                'baseline_count': int(result[1]) if result[1] else 0,
                'baseline_quality': float(result[2]) if result[2] else None,
                'baseline_success_rate': float(result[3]) / float(result[1]) if result[1] else 0,
                'baseline_avg_time': result[4],
                'comparable': True
            }

        return {
            'baseline_type': 'none',
            'comparable': False,
            'baseline_quality': None
        }

    def _classify_effect(
        self,
        quality_score: float,
        baseline: Dict[str, Any],
        learning_item: Dict[str, Any],
        outcome_status: str
    ) -> Dict[str, Any]:
        """Classify effect of applied learning."""

        if not baseline['comparable'] or baseline['baseline_quality'] is None:
            return {
                'classification': 'insufficient_evidence',
                'reasoning': 'No valid baseline for comparison',
                'quality_delta': None
            }

        quality_delta = quality_score - baseline['baseline_quality']
        support_threshold = self.config['supportive_quality_delta_threshold']
        contradict_threshold = self.config['contradictory_quality_delta_threshold']

        if quality_delta > support_threshold:
            return {
                'classification': 'supportive',
                'reasoning': f'Quality improved by {quality_delta:.3f} (threshold: {support_threshold})',
                'quality_delta': quality_delta
            }
        elif quality_delta < -contradict_threshold:
            return {
                'classification': 'contradictory',
                'reasoning': f'Quality degraded by {abs(quality_delta):.3f} (threshold: {contradict_threshold})',
                'quality_delta': quality_delta
            }
        else:
            return {
                'classification': 'neutral',
                'reasoning': f'Quality change {quality_delta:.3f} within ±{support_threshold} threshold',
                'quality_delta': quality_delta
            }

    def _create_feedback_record(
        self,
        attempt_id: str,
        task_id: str,
        node_id: str,
        outcome_id: Optional[str],
        applied_learning_id: str,
        learning_type: str,
        learning_id: str,
        result: Dict[str, Any],
        quality_score: float,
        outcome_status: str,
        execution_time_seconds: Optional[int],
        effect: Dict[str, Any],
        baseline: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create feedback record."""

        feedback_hash = hashlib.sha256(
            f"{attempt_id}|{applied_learning_id}|{outcome_id}".encode()
        ).hexdigest()

        return {
            'feedback_id': str(uuid.uuid4()),
            'attempt_id': attempt_id,
            'task_id': task_id,
            'node_id': node_id,
            'outcome_id': outcome_id,
            'applied_learning_id': applied_learning_id,
            'learning_type': learning_type,
            'learning_id': learning_id,
            'result': json.dumps(result) if isinstance(result, dict) else result,
            'quality_score': quality_score,
            'outcome_status': outcome_status,
            'execution_time_seconds': execution_time_seconds,
            'effect_classification': effect['classification'],
            'effect_reasoning': json.dumps({'reasoning': effect['reasoning']}),
            'baseline_type': baseline['baseline_type'],
            'baseline_quality': baseline.get('baseline_quality'),
            'baseline_count': baseline.get('baseline_count'),
            'quality_delta': effect.get('quality_delta'),
            'evidence_strength': 0.8 if baseline['comparable'] else 0.0,
            'comparable': 1 if baseline['comparable'] else 0,
            'attribution_confidence': 'associated',  # Empirical observation
            'causality_note': 'Learning was applied; outcome followed. See accumulated evidence for confidence.',
            'feedback_hash': feedback_hash,
            'created_at': datetime.utcnow(),
            'created_by': 'feedback_engine'
        }

    def _insert_feedback_record(self, record: Dict[str, Any]) -> str:
        """Insert feedback record to database."""
        query = """
            INSERT INTO feedback_records (
                feedback_id, attempt_id, task_id, node_id, outcome_id, applied_learning_id,
                learning_type, learning_id, result, quality_score, outcome_status, 
                execution_time_seconds, effect_classification, effect_reasoning,
                baseline_type, baseline_quality, baseline_count, quality_delta,
                evidence_strength, comparable, attribution_confidence, causality_note,
                feedback_hash, created_at, created_by
            ) VALUES (
                :feedback_id, :attempt_id, :task_id, :node_id, :outcome_id, :applied_learning_id,
                :learning_type, :learning_id, :result, :quality_score, :outcome_status,
                :execution_time_seconds, :effect_classification, :effect_reasoning,
                :baseline_type, :baseline_quality, :baseline_count, :quality_delta,
                :evidence_strength, :comparable, :attribution_confidence, :causality_note,
                :feedback_hash, :created_at, :created_by
            )
            ON CONFLICT (feedback_hash) DO NOTHING
            RETURNING feedback_id
        """
        result = self.db.execute(text(query), record).fetchone()
        return result[0] if result else record['feedback_id']

    def _update_evidence_accumulation(
        self,
        learning_id: str,
        learning_type: str,
        effect_classification: str,
        quality_score: float,
        quality_delta: Optional[float],
        task_type: Optional[str],
        node_id: str
    ) -> Dict[str, Any]:
        """Update evidence accumulation for learning item."""

        # Get or create accumulation record
        query = """
            SELECT * FROM evidence_accumulation
            WHERE learning_id = :learning_id AND learning_type = :learning_type
        """
        accum_row = self.db.execute(
            text(query),
            {'learning_id': learning_id, 'learning_type': learning_type}
        ).fetchone()

        if accum_row:
            # Handle both mapping and tuple Row types
            if hasattr(accum_row, 'keys'):
                accum = dict(accum_row)
            else:
                # For tuples, reconstruct
                cols = ['accumulation_id', 'learning_id', 'learning_type', 'times_applied', 'supportive_count',
                        'contradictory_count', 'neutral_count', 'insufficient_evidence_count', 'supportive_ratio',
                        'contradictory_ratio', 'avg_quality_when_applied', 'avg_quality_delta', 'quality_variance',
                        'task_types', 'node_count', 'first_applied', 'last_applied', 'last_evaluated',
                        'current_validation_state', 'validation_changed_at', 'confidence_score', 'evidence_count',
                        'updated_at']
                accum = dict(zip(cols[:len(accum_row)], accum_row))
        else:
            accum = {
                'accumulation_id': str(uuid.uuid4()),
                'learning_id': learning_id,
                'learning_type': learning_type,
                'times_applied': 0,
                'supportive_count': 0,
                'contradictory_count': 0,
                'neutral_count': 0,
                'insufficient_evidence_count': 0,
                'supportive_ratio': 0,
                'contradictory_ratio': 0,
                'avg_quality_when_applied': None,
                'avg_quality_delta': None,
                'quality_variance': None,
                'task_types': {},
                'node_count': 0,
                'first_applied': datetime.utcnow(),
                'last_applied': None,
                'last_evaluated': None,
                'current_validation_state': 'candidate',
                'validation_changed_at': datetime.utcnow(),
                'confidence_score': 0.50,
                'evidence_count': 0,
            }

        # Update counts
        accum['times_applied'] = (accum.get('times_applied') or 0) + 1
        accum['evidence_count'] = (accum.get('evidence_count') or 0) + 1
        accum['last_applied'] = datetime.utcnow()
        accum['last_evaluated'] = datetime.utcnow()

        if effect_classification == 'supportive':
            accum['supportive_count'] = (accum.get('supportive_count') or 0) + 1
        elif effect_classification == 'contradictory':
            accum['contradictory_count'] = (accum.get('contradictory_count') or 0) + 1
        elif effect_classification == 'neutral':
            accum['neutral_count'] = (accum.get('neutral_count') or 0) + 1
        else:  # insufficient_evidence
            accum['insufficient_evidence_count'] = (accum.get('insufficient_evidence_count') or 0) + 1

        # Update ratios
        times_applied = accum['times_applied']
        accum['supportive_ratio'] = accum['supportive_count'] / times_applied if times_applied > 0 else 0
        accum['contradictory_ratio'] = accum['contradictory_count'] / times_applied if times_applied > 0 else 0

        # Update quality metrics
        if quality_score:
            current_avg = accum.get('avg_quality_when_applied') or quality_score
            accum['avg_quality_when_applied'] = (
                (current_avg * (times_applied - 1) + quality_score) / times_applied
            )

        if quality_delta is not None:
            current_delta_avg = accum.get('avg_quality_delta') or 0
            accum['avg_quality_delta'] = (
                (current_delta_avg * (times_applied - 1) + quality_delta) / times_applied
            )

        # Update task type coverage
        if task_type:
            task_types_str = accum.get('task_types')
            if isinstance(task_types_str, str):
                task_types = json.loads(task_types_str) if task_types_str else {}
            else:
                task_types = task_types_str or {}
            task_types[task_type] = (task_types.get(task_type) or 0) + 1
            accum['task_types'] = json.dumps(task_types) if isinstance(task_types, dict) else task_types

        # Update node count (simplified)
        accum['node_count'] = (accum.get('node_count') or 0) + 1

        # Upsert to database
        if accum_row:
            update_query = """
                UPDATE evidence_accumulation SET
                    times_applied = :times_applied,
                    supportive_count = :supportive_count,
                    contradictory_count = :contradictory_count,
                    neutral_count = :neutral_count,
                    insufficient_evidence_count = :insufficient_evidence_count,
                    supportive_ratio = :supportive_ratio,
                    contradictory_ratio = :contradictory_ratio,
                    avg_quality_when_applied = :avg_quality_when_applied,
                    avg_quality_delta = :avg_quality_delta,
                    task_types = :task_types,
                    node_count = :node_count,
                    last_applied = :last_applied,
                    last_evaluated = :last_evaluated,
                    evidence_count = :evidence_count,
                    updated_at = NOW()
                WHERE learning_id = :learning_id AND learning_type = :learning_type
            """
            self.db.execute(text(update_query), accum)
        else:
            insert_query = """
                INSERT INTO evidence_accumulation (
                    accumulation_id, learning_id, learning_type, times_applied,
                    supportive_count, contradictory_count, neutral_count,
                    insufficient_evidence_count, supportive_ratio, contradictory_ratio,
                    avg_quality_when_applied, avg_quality_delta, task_types, node_count,
                    first_applied, last_applied, last_evaluated, current_validation_state,
                    validation_changed_at, confidence_score, evidence_count
                ) VALUES (
                    :accumulation_id, :learning_id, :learning_type, :times_applied,
                    :supportive_count, :contradictory_count, :neutral_count,
                    :insufficient_evidence_count, :supportive_ratio, :contradictory_ratio,
                    :avg_quality_when_applied, :avg_quality_delta, :task_types, :node_count,
                    :first_applied, :last_applied, :last_evaluated, :current_validation_state,
                    :validation_changed_at, :confidence_score, :evidence_count
                )
            """
            self.db.execute(text(insert_query), accum)

        return accum

    def _adjust_confidence(
        self,
        learning_id: str,
        learning_type: str,
        evidence_accumulation: Dict[str, Any],
        trigger_feedback_ids: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Adjust confidence based on accumulated evidence."""

        # Only adjust if we have minimum evidence
        min_evidence = self.config['min_evidence_for_confidence_move']
        if evidence_accumulation['evidence_count'] < min_evidence:
            return None

        old_confidence = evidence_accumulation['confidence_score']
        new_confidence = old_confidence

        # Supportive evidence increases confidence
        supportive_count = evidence_accumulation['supportive_count']
        if supportive_count > 0:
            increase = supportive_count * self.config['confidence_increase_per_supportive']
            new_confidence = min(
                new_confidence + increase,
                self.config['confidence_max']
            )

        # Contradictory evidence decreases confidence
        contradictory_count = evidence_accumulation['contradictory_count']
        if contradictory_count > 0:
            decrease = contradictory_count * self.config['confidence_decrease_per_contradictory']
            new_confidence = max(
                new_confidence - decrease,
                self.config['confidence_min']
            )

        # Clamp to bounds
        new_confidence = max(
            self.config['confidence_min'],
            min(new_confidence, self.config['confidence_max'])
        )

        if abs(new_confidence - old_confidence) < 0.001:
            return None  # No meaningful change

        # Record adjustment
        adjustment = {
            'adjustment_id': str(uuid.uuid4()),
            'learning_id': learning_id,
            'learning_type': learning_type,
            'previous_confidence': old_confidence,
            'new_confidence': new_confidence,
            'confidence_change': new_confidence - old_confidence,
            'trigger_type': 'feedback',
            'trigger_reason': f'Supportive: {supportive_count}, Contradictory: {contradictory_count}',
            'supportive_count_at_adjustment': supportive_count,
            'contradictory_count_at_adjustment': contradictory_count,
            'evidence_count_at_adjustment': evidence_accumulation['evidence_count'],
            'adjustment_rule': 'empirical_accumulation',
            'adjustment_magnitude': abs(new_confidence - old_confidence),
            'adjusted_at': datetime.utcnow(),
            'adjusted_by': 'feedback_engine'
        }

        # Insert to database
        insert_query = """
            INSERT INTO confidence_adjustments (
                adjustment_id, learning_id, learning_type, previous_confidence,
                new_confidence, confidence_change, trigger_type, trigger_reason,
                supportive_count_at_adjustment, contradictory_count_at_adjustment,
                evidence_count_at_adjustment, adjustment_rule, adjustment_magnitude,
                adjusted_at, adjusted_by
            ) VALUES (
                :adjustment_id, :learning_id, :learning_type, :previous_confidence,
                :new_confidence, :confidence_change, :trigger_type, :trigger_reason,
                :supportive_count_at_adjustment, :contradictory_count_at_adjustment,
                :evidence_count_at_adjustment, :adjustment_rule, :adjustment_magnitude,
                :adjusted_at, :adjusted_by
            )
        """
        self.db.execute(text(insert_query), adjustment)

        # Update evidence_accumulation with new confidence
        update_query = """
            UPDATE evidence_accumulation SET
                confidence_score = :new_confidence,
                updated_at = NOW()
            WHERE learning_id = :learning_id AND learning_type = :learning_type
        """
        self.db.execute(
            text(update_query),
            {'new_confidence': new_confidence, 'learning_id': learning_id, 'learning_type': learning_type}
        )

        return adjustment

    def _update_validation_state(
        self,
        learning_id: str,
        learning_type: str,
        evidence_accumulation: Dict[str, Any],
        trigger_feedback_ids: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Update validation state based on evidence thresholds."""

        current_state = evidence_accumulation['current_validation_state']
        evidence_count = evidence_accumulation['evidence_count']
        supportive_ratio = evidence_accumulation['supportive_ratio']
        contradictory_ratio = evidence_accumulation['contradictory_ratio']

        new_state = current_state
        transition_reason = None

        # Determine target state based on evidence
        if evidence_count < 1:
            new_state = 'candidate'
        elif evidence_count < self.config['emerging_threshold_min_evidence']:
            new_state = 'candidate'
        elif (evidence_count >= self.config['validated_threshold_min_evidence'] and
              supportive_ratio >= self.config['validated_threshold_supportive_ratio']):
            new_state = 'validated'
            transition_reason = f'High supportive ratio: {supportive_ratio:.2f}'
        elif (evidence_count >= self.config['rejected_threshold_min_evidence'] and
              contradictory_ratio >= self.config['rejected_threshold_contradictory_ratio']):
            new_state = 'rejected'
            transition_reason = f'High contradictory ratio: {contradictory_ratio:.2f}'
        elif (evidence_count >= self.config['disputed_threshold_min_evidence'] and
              contradictory_ratio >= self.config['disputed_threshold_contradictory_ratio']):
            new_state = 'disputed'
            transition_reason = f'Mixed evidence - contradictory ratio: {contradictory_ratio:.2f}'
        elif evidence_count >= self.config['emerging_threshold_min_evidence']:
            new_state = 'emerging'
            transition_reason = f'Sufficient evidence, trend visible: {supportive_ratio:.2f} supportive'

        if new_state == current_state:
            return None  # No state change

        # Record transition
        transition = {
            'transition_id': str(uuid.uuid4()),
            'learning_id': learning_id,
            'learning_type': learning_type,
            'from_state': current_state,
            'to_state': new_state,
            'trigger_type': 'evidence_threshold',
            'trigger_reason': transition_reason,
            'evidence_state': {
                'evidence_count': evidence_count,
                'supportive_count': evidence_accumulation['supportive_count'],
                'contradictory_count': evidence_accumulation['contradictory_count'],
                'neutral_count': evidence_accumulation['neutral_count'],
                'insufficient_evidence_count': evidence_accumulation['insufficient_evidence_count'],
                'supportive_ratio': supportive_ratio,
                'contradictory_ratio': contradictory_ratio,
            },
            'thresholds_checked': {
                'validated_min_evidence': self.config['validated_threshold_min_evidence'],
                'validated_supportive_ratio': self.config['validated_threshold_supportive_ratio'],
                'rejected_min_evidence': self.config['rejected_threshold_min_evidence'],
                'rejected_contradictory_ratio': self.config['rejected_threshold_contradictory_ratio'],
                'disputed_min_evidence': self.config['disputed_threshold_min_evidence'],
                'disputed_contradictory_ratio': self.config['disputed_threshold_contradictory_ratio'],
            },
            'transitioned_at': datetime.utcnow(),
            'transitioned_by': 'feedback_engine'
        }

        # Serialize JSON fields
        transition['evidence_state'] = json.dumps(transition['evidence_state'])
        transition['thresholds_checked'] = json.dumps(transition['thresholds_checked'])

        # Insert transition
        insert_query = """
            INSERT INTO validation_transitions (
                transition_id, learning_id, learning_type, from_state, to_state,
                trigger_type, trigger_reason, evidence_state, thresholds_checked,
                transitioned_at, transitioned_by
            ) VALUES (
                :transition_id, :learning_id, :learning_type, :from_state, :to_state,
                :trigger_type, :trigger_reason, :evidence_state, :thresholds_checked,
                :transitioned_at, :transitioned_by
            )
        """
        self.db.execute(text(insert_query), transition)

        # Update evidence_accumulation with new state
        update_query = """
            UPDATE evidence_accumulation SET
                current_validation_state = :new_state,
                validation_changed_at = NOW(),
                updated_at = NOW()
            WHERE learning_id = :learning_id AND learning_type = :learning_type
        """
        self.db.execute(
            text(update_query),
            {'new_state': new_state, 'learning_id': learning_id, 'learning_type': learning_type}
        )

        return transition

    def _update_learning_metadata(self, evidence_updates: List[Dict[str, Any]]) -> None:
        """Update learning/memory metadata based on evidence."""
        # This will link to Section 6/8 to update confidence/validation in source learning
        for update in evidence_updates:
            learning_id = update['learning_id']
            learning_type = update['learning_type']

            # Get current evidence accumulation
            query = """
                SELECT confidence_score, current_validation_state
                FROM evidence_accumulation
                WHERE learning_id = :learning_id AND learning_type = :learning_type
            """
            result = self.db.execute(
                text(query),
                {'learning_id': learning_id, 'learning_type': learning_type}
            ).fetchone()

            if result:
                # Update metadata in source tables (handled in endpoints)
                pass

    def _record_processing_log(
        self,
        log_id: str,
        attempt_id: str,
        outcome_id: Optional[str],
        status: str,
        error: Optional[str],
        original_feedback_id: Optional[str],
        trace: Dict[str, Any],
        feedback_count: int = 0,
        evidence_count: int = 0,
        confidence_count: int = 0,
        transition_count: int = 0
    ) -> None:
        """Record feedback processing in log."""
        query = """
            INSERT INTO feedback_processing_log (
                log_id, attempt_id, outcome_id, processing_status, processing_error,
                original_feedback_id, duplicate_detected, feedback_records_created,
                evidence_updated, confidence_adjustments_made, state_transitions_made,
                processing_trace, processed_at, processing_duration_ms
            ) VALUES (
                :log_id, :attempt_id, :outcome_id, :status, :error,
                :original_feedback_id, :duplicate, :feedback_count,
                :evidence_count, :confidence_count, :transition_count,
                :trace, NOW(), 0
            )
        """
        self.db.execute(
            text(query),
            {
                'log_id': log_id,
                'attempt_id': attempt_id,
                'outcome_id': outcome_id,
                'status': status,
                'error': error,
                'original_feedback_id': original_feedback_id,
                'duplicate': original_feedback_id is not None,
                'feedback_count': feedback_count,
                'evidence_count': evidence_count,
                'confidence_count': confidence_count,
                'transition_count': transition_count,
                'trace': json.dumps(trace) if isinstance(trace, dict) else trace,
            }
        )

    def get_feedback_trace(self, attempt_id: str) -> Dict[str, Any]:
        """Get complete trace from attempt through feedback to validation updates."""
        query = """
            SELECT
                a.attempt_id,
                a.task_id,
                a.node_id,
                a.status as attempt_status,
                t.task_type,
                al.applied_id,
                al.learning_type,
                al.learning_id,
                eg.guidance_id,
                eg.generated_at,
                fb.feedback_id,
                fb.effect_classification,
                fb.quality_score,
                fb.baseline_quality,
                fb.quality_delta,
                ea.confidence_score,
                ea.current_validation_state,
                ea.supportive_count,
                ea.contradictory_count,
                ea.evidence_count
            FROM attempts a
            LEFT JOIN tasks t ON a.task_id = t.task_id
            LEFT JOIN applied_learning al ON a.attempt_id = al.attempt_id
            LEFT JOIN execution_guidance eg ON a.attempt_id = eg.attempt_id
            LEFT JOIN feedback_records fb ON a.attempt_id = fb.attempt_id
            LEFT JOIN evidence_accumulation ea ON (
                fb.learning_id = ea.learning_id AND
                fb.learning_type = ea.learning_type
            )
            WHERE a.attempt_id = :attempt_id
            ORDER BY al.applied_id, fb.feedback_id
        """

        rows = self.db.execute(
            text(query),
            {'attempt_id': attempt_id}
        ).fetchall()

        if not rows:
            return None

        # Build trace structure
        trace = {
            'attempt_id': attempt_id,
            'task_type': rows[0][4] if rows else None,
            'node_id': rows[0][2] if rows else None,
            'applied_learning': [],
            'feedback': [],
            'validation': []
        }

        seen_learning = set()
        for row in rows:
            # Applied learning
            if row[5] and row[5] not in seen_learning:
                trace['applied_learning'].append({
                    'applied_id': row[5],
                    'learning_type': row[6],
                    'learning_id': row[7],
                })
                seen_learning.add(row[5])

            # Feedback
            if row[10]:
                trace['feedback'].append({
                    'feedback_id': row[10],
                    'effect_classification': row[11],
                    'quality_score': row[12],
                    'baseline_quality': row[13],
                    'quality_delta': row[14],
                })

            # Validation
            if row[16]:
                trace['validation'].append({
                    'validation_state': row[16],
                    'confidence_score': row[15],
                    'supportive_count': row[17],
                    'contradictory_count': row[18],
                    'evidence_count': row[19],
                })

        return trace
