"""
Section 11: Learning Feedback & Validation Tests

Test deterministic confidence/validation logic, effect classification,
evidence accumulation, and idempotency.
"""

import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from fabric.api.feedback import LearningFeedbackEngine


@pytest.fixture(scope="function")
def db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create minimal schema
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS assignments (
                assignment_id TEXT PRIMARY KEY,
                task_id TEXT REFERENCES tasks(task_id),
                node_id TEXT REFERENCES nodes(node_id),
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                assignment_id TEXT REFERENCES assignments(assignment_id),
                task_id TEXT REFERENCES tasks(task_id),
                node_id TEXT,
                status TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS results (
                result_id TEXT PRIMARY KEY,
                attempt_id TEXT REFERENCES attempts(attempt_id),
                quality_score REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_outcomes (
                outcome_id TEXT PRIMARY KEY,
                attempt_id TEXT REFERENCES attempts(attempt_id),
                task_id TEXT REFERENCES tasks(task_id),
                node_id TEXT,
                outcome_status TEXT,
                quality_score REAL,
                execution_time_seconds INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS applied_learning (
                applied_id TEXT PRIMARY KEY,
                attempt_id TEXT REFERENCES attempts(attempt_id),
                learning_type TEXT,
                learning_id TEXT,
                relevance_score REAL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS execution_guidance (
                guidance_id TEXT PRIMARY KEY,
                attempt_id TEXT REFERENCES attempts(attempt_id),
                task_id TEXT,
                node_id TEXT,
                generated_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feedback_records (
                feedback_id TEXT PRIMARY KEY,
                attempt_id TEXT REFERENCES attempts(attempt_id),
                task_id TEXT REFERENCES tasks(task_id),
                node_id TEXT REFERENCES nodes(node_id),
                outcome_id TEXT REFERENCES task_outcomes(outcome_id),
                applied_learning_id TEXT REFERENCES applied_learning(applied_id),
                learning_type TEXT NOT NULL,
                learning_id TEXT NOT NULL,
                result TEXT,
                quality_score REAL,
                outcome_status TEXT,
                execution_time_seconds INTEGER,
                effect_classification TEXT,
                effect_reasoning TEXT,
                baseline_type TEXT,
                baseline_quality REAL,
                baseline_count INTEGER,
                quality_delta REAL,
                evidence_strength REAL,
                comparable INTEGER,
                attribution_confidence TEXT,
                causality_note TEXT,
                feedback_hash TEXT UNIQUE,
                created_at TIMESTAMP,
                created_by TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evidence_accumulation (
                accumulation_id TEXT PRIMARY KEY,
                learning_id TEXT NOT NULL,
                learning_type TEXT NOT NULL,
                times_applied INTEGER DEFAULT 0,
                supportive_count INTEGER DEFAULT 0,
                contradictory_count INTEGER DEFAULT 0,
                neutral_count INTEGER DEFAULT 0,
                insufficient_evidence_count INTEGER DEFAULT 0,
                supportive_ratio REAL DEFAULT 0,
                contradictory_ratio REAL DEFAULT 0,
                avg_quality_when_applied REAL,
                avg_quality_delta REAL,
                quality_variance REAL,
                task_types TEXT,
                node_count INTEGER,
                first_applied TIMESTAMP,
                last_applied TIMESTAMP,
                last_evaluated TIMESTAMP,
                current_validation_state TEXT,
                validation_changed_at TIMESTAMP,
                confidence_score REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP,
                UNIQUE(learning_id, learning_type)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS confidence_adjustments (
                adjustment_id TEXT PRIMARY KEY,
                learning_id TEXT NOT NULL,
                learning_type TEXT NOT NULL,
                previous_confidence REAL,
                new_confidence REAL,
                confidence_change REAL,
                trigger_type TEXT,
                trigger_reason TEXT,
                supportive_count_at_adjustment INTEGER,
                contradictory_count_at_adjustment INTEGER,
                evidence_count_at_adjustment INTEGER,
                adjustment_rule TEXT,
                adjustment_magnitude REAL,
                adjusted_at TIMESTAMP,
                adjusted_by TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS validation_transitions (
                transition_id TEXT PRIMARY KEY,
                learning_id TEXT NOT NULL,
                learning_type TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT,
                trigger_type TEXT,
                trigger_reason TEXT,
                evidence_state TEXT,
                thresholds_checked TEXT,
                transitioned_at TIMESTAMP,
                transitioned_by TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feedback_processing_log (
                log_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                outcome_id TEXT REFERENCES task_outcomes(outcome_id),
                processing_status TEXT,
                processing_error TEXT,
                original_feedback_id TEXT,
                duplicate_detected INTEGER,
                processed_at TIMESTAMP,
                processing_duration_ms INTEGER,
                feedback_records_created INTEGER,
                evidence_updated INTEGER,
                confidence_adjustments_made INTEGER,
                state_transitions_made INTEGER,
                processing_trace TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feedback_config (
                config_id TEXT PRIMARY KEY,
                config_name TEXT UNIQUE,
                confidence_increase_per_supportive REAL DEFAULT 0.10,
                confidence_decrease_per_contradictory REAL DEFAULT 0.10,
                min_evidence_for_confidence_move INTEGER DEFAULT 3,
                confidence_min REAL DEFAULT 0.05,
                confidence_max REAL DEFAULT 0.95,
                emerging_threshold_min_evidence INTEGER DEFAULT 3,
                emerging_threshold_supportive_ratio REAL DEFAULT 0.5,
                validated_threshold_min_evidence INTEGER DEFAULT 5,
                validated_threshold_supportive_ratio REAL DEFAULT 0.70,
                disputed_threshold_min_evidence INTEGER DEFAULT 5,
                disputed_threshold_contradictory_ratio REAL DEFAULT 0.30,
                rejected_threshold_min_evidence INTEGER DEFAULT 5,
                rejected_threshold_contradictory_ratio REAL DEFAULT 0.80,
                supportive_quality_delta_threshold REAL DEFAULT 0.05,
                contradictory_quality_delta_threshold REAL DEFAULT 0.05,
                min_baseline_attempts INTEGER DEFAULT 3,
                active INTEGER DEFAULT 1
            )
        """))
        conn.execute(text("""
            INSERT INTO feedback_config (config_id, config_name, active)
            VALUES ('default-cfg', 'default', 1)
        """))

    yield engine


class TestEffectClassification:
    """Test effect classification logic."""

    def test_supportive_effect(self, db):
        """Quality improvement above threshold = supportive."""
        engine = LearningFeedbackEngine(db.connect())

        with db.connect() as conn:
            engine.db = conn

            effect = engine._classify_effect(
                quality_score=0.90,
                baseline={
                    'comparable': True,
                    'baseline_type': 'same_task_type',
                    'baseline_quality': 0.80,
                    'baseline_count': 5
                },
                learning_item={'id': 'L1', 'type': 'outcome'},
                outcome_status='success'
            )

        assert effect['classification'] == 'supportive'
        assert effect['quality_delta'] == pytest.approx(0.10, rel=0.01)

    def test_contradictory_effect(self, db):
        """Quality degradation below threshold = contradictory."""
        engine = LearningFeedbackEngine(db.connect())

        with db.connect() as conn:
            engine.db = conn

            effect = engine._classify_effect(
                quality_score=0.70,
                baseline={
                    'comparable': True,
                    'baseline_type': 'same_task_type',
                    'baseline_quality': 0.80,
                    'baseline_count': 5
                },
                learning_item={'id': 'L1', 'type': 'outcome'},
                outcome_status='failure'
            )

        assert effect['classification'] == 'contradictory'
        assert effect['quality_delta'] == pytest.approx(-0.10, rel=0.01)

    def test_neutral_effect(self, db):
        """Quality within threshold = neutral."""
        engine = LearningFeedbackEngine(db.connect())

        with db.connect() as conn:
            engine.db = conn

            effect = engine._classify_effect(
                quality_score=0.82,
                baseline={
                    'comparable': True,
                    'baseline_type': 'same_task_type',
                    'baseline_quality': 0.80,
                    'baseline_count': 5
                },
                learning_item={'id': 'L1', 'type': 'outcome'},
                outcome_status='success'
            )

        assert effect['classification'] == 'neutral'
        assert effect['quality_delta'] == pytest.approx(0.02, rel=0.01)

    def test_insufficient_evidence(self, db):
        """No baseline = insufficient_evidence."""
        engine = LearningFeedbackEngine(db.connect())

        with db.connect() as conn:
            engine.db = conn

            effect = engine._classify_effect(
                quality_score=0.90,
                baseline={
                    'comparable': False,
                    'baseline_type': 'none',
                    'baseline_quality': None
                },
                learning_item={'id': 'L1', 'type': 'outcome'},
                outcome_status='success'
            )

        assert effect['classification'] == 'insufficient_evidence'


class TestEvidenceAccumulation:
    """Test evidence accumulation logic."""

    def test_accumulate_supportive_evidence(self, db):
        """Multiple supportive outcomes increase counts."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # First supportive
            accum1 = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.90,
                quality_delta=0.10,
                task_type='analysis',
                node_id='N1'
            )

            assert accum1['supportive_count'] == 1
            assert accum1['times_applied'] == 1
            assert accum1['supportive_ratio'] == 1.0

            # Second supportive
            accum2 = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.92,
                quality_delta=0.12,
                task_type='analysis',
                node_id='N1'
            )

            assert accum2['supportive_count'] == 2
            assert accum2['times_applied'] == 2
            assert accum2['supportive_ratio'] == 1.0

    def test_accumulate_mixed_evidence(self, db):
        """Supportive + contradictory = mixed ratio."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Supportive
            engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.90,
                quality_delta=0.10,
                task_type='analysis',
                node_id='N1'
            )

            # Contradictory
            accum = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='contradictory',
                quality_score=0.70,
                quality_delta=-0.10,
                task_type='analysis',
                node_id='N2'
            )

            assert accum['supportive_count'] == 1
            assert accum['contradictory_count'] == 1
            assert accum['times_applied'] == 2
            assert accum['supportive_ratio'] == 0.5
            assert accum['contradictory_ratio'] == 0.5

    def test_quality_metrics_calculation(self, db):
        """Avg quality and delta calculated correctly."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.80,
                quality_delta=0.10,
                task_type='analysis',
                node_id='N1'
            )

            accum = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.90,
                quality_delta=0.20,
                task_type='analysis',
                node_id='N1'
            )

            assert accum['avg_quality_when_applied'] == pytest.approx(0.85, rel=0.01)
            assert accum['avg_quality_delta'] == pytest.approx(0.15, rel=0.01)


class TestConfidenceAdjustment:
    """Test deterministic confidence adjustment."""

    def test_confidence_increase_on_supportive(self, db):
        """Supportive evidence increases confidence."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Build up evidence
            for i in range(5):
                engine._update_evidence_accumulation(
                    learning_id='L1',
                    learning_type='outcome',
                    effect_classification='supportive',
                    quality_score=0.90,
                    quality_delta=0.10,
                    task_type='analysis',
                    node_id=f'N{i}'
                )

            accum = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.90,
                quality_delta=0.10,
                task_type='analysis',
                node_id='N5'
            )

            # Now adjust
            adj = engine._adjust_confidence(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert adj is not None
            assert adj['new_confidence'] > 0.50  # Default start

    def test_confidence_decrease_on_contradictory(self, db):
        """Contradictory evidence decreases confidence."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Initial confidence 0.80 (from previous validation)
            conn.execute(text("""
                INSERT INTO evidence_accumulation (
                    accumulation_id, learning_id, learning_type, times_applied,
                    supportive_count, evidence_count, confidence_score,
                    current_validation_state
                ) VALUES (
                    'A1', 'L1', 'outcome', 1, 1, 1, 0.80, 'validated'
                )
            """))

            # Add contradictory evidence
            accum = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='contradictory',
                quality_score=0.70,
                quality_delta=-0.10,
                task_type='analysis',
                node_id='N1'
            )

            # Refresh from DB
            result = conn.execute(text("""
                SELECT confidence_score FROM evidence_accumulation
                WHERE learning_id = 'L1'
            """)).fetchone()

            current_conf = result[0]

            adj = engine._adjust_confidence(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert adj is not None
            # Should have decreased
            if adj:
                assert adj['new_confidence'] < 0.80

    def test_confidence_bounded(self, db):
        """Confidence stays within 0.05 - 0.95."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Insert with max confidence
            conn.execute(text("""
                INSERT INTO evidence_accumulation (
                    accumulation_id, learning_id, learning_type, times_applied,
                    supportive_count, contradictory_count, evidence_count,
                    confidence_score, current_validation_state
                ) VALUES (
                    'A1', 'L1', 'outcome', 100, 95, 5, 0.95, 'validated'
                )
            """))

            accum = {
                'accumulation_id': 'A1',
                'learning_id': 'L1',
                'learning_type': 'outcome',
                'times_applied': 101,
                'supportive_count': 96,
                'contradictory_count': 5,
                'evidence_count': 101,
                'confidence_score': 0.95
            }

            adj = engine._adjust_confidence(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            # Should not exceed max
            if adj:
                assert adj['new_confidence'] <= 0.95


class TestValidationStateTransitions:
    """Test validation state machine."""

    def test_candidate_to_emerging(self, db):
        """Sufficient evidence → emerging."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            accum = {
                'accumulation_id': 'A1',
                'learning_id': 'L1',
                'learning_type': 'outcome',
                'times_applied': 3,
                'supportive_count': 2,
                'contradictory_count': 1,
                'neutral_count': 0,
                'insufficient_evidence_count': 0,
                'evidence_count': 3,
                'supportive_ratio': 0.67,
                'contradictory_ratio': 0.33,
                'current_validation_state': 'candidate'
            }

            trans = engine._update_validation_state(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert trans is not None
            assert trans['from_state'] == 'candidate'
            assert trans['to_state'] == 'emerging'

    def test_emerging_to_validated(self, db):
        """High supportive ratio → validated."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            accum = {
                'accumulation_id': 'A1',
                'learning_id': 'L1',
                'learning_type': 'outcome',
                'times_applied': 7,
                'supportive_count': 6,
                'contradictory_count': 1,
                'neutral_count': 0,
                'insufficient_evidence_count': 0,
                'evidence_count': 7,
                'supportive_ratio': 0.86,
                'contradictory_ratio': 0.14,
                'current_validation_state': 'emerging'
            }

            trans = engine._update_validation_state(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert trans is not None
            assert trans['from_state'] == 'emerging'
            assert trans['to_state'] == 'validated'

    def test_emerging_to_disputed(self, db):
        """High contradictory ratio → disputed."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            accum = {
                'accumulation_id': 'A1',
                'learning_id': 'L1',
                'learning_type': 'outcome',
                'times_applied': 6,
                'supportive_count': 2,
                'contradictory_count': 4,
                'neutral_count': 0,
                'insufficient_evidence_count': 0,
                'evidence_count': 6,
                'supportive_ratio': 0.33,
                'contradictory_ratio': 0.67,
                'current_validation_state': 'emerging'
            }

            trans = engine._update_validation_state(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert trans is not None
            assert trans['from_state'] == 'emerging'
            assert trans['to_state'] == 'disputed'

    def test_disputed_to_rejected(self, db):
        """Very high contradictory → rejected."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            accum = {
                'accumulation_id': 'A1',
                'learning_id': 'L1',
                'learning_type': 'outcome',
                'times_applied': 9,
                'supportive_count': 1,
                'contradictory_count': 8,
                'neutral_count': 0,
                'insufficient_evidence_count': 0,
                'evidence_count': 9,
                'supportive_ratio': 0.11,
                'contradictory_ratio': 0.89,
                'current_validation_state': 'disputed'
            }

            trans = engine._update_validation_state(
                learning_id='L1',
                learning_type='outcome',
                evidence_accumulation=accum,
                trigger_feedback_ids=[]
            )

            assert trans is not None
            assert trans['from_state'] == 'disputed'
            assert trans['to_state'] == 'rejected'


class TestIdempotency:
    """Test duplicate handling and idempotent processing."""

    def test_duplicate_feedback_detected(self, db):
        """Same attempt/outcome not processed twice."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Insert processing log for this attempt
            conn.execute(text("""
                INSERT INTO feedback_processing_log (
                    log_id, attempt_id, outcome_id, processing_status, created_at
                ) VALUES (
                    'L1', 'A1', 'O1', 'completed', datetime('now')
                )
            """))

            duplicate = engine._check_feedback_duplicate('A1', 'O1')

            assert duplicate['is_duplicate'] is True

    def test_unique_feedback_hash(self, db):
        """Feedback hash prevents duplicate records."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            record1 = {
                'feedback_id': str(uuid.uuid4()),
                'attempt_id': 'A1',
                'task_id': 'T1',
                'node_id': 'N1',
                'outcome_id': 'O1',
                'applied_learning_id': 'AL1',
                'learning_type': 'outcome',
                'learning_id': 'L1',
                'result': {},
                'quality_score': 0.90,
                'outcome_status': 'success',
                'execution_time_seconds': 30,
                'effect_classification': 'supportive',
                'effect_reasoning': '{}',
                'baseline_type': 'same_task_type',
                'baseline_quality': 0.80,
                'baseline_count': 5,
                'quality_delta': 0.10,
                'evidence_strength': 0.8,
                'comparable': 1,
                'attribution_confidence': 'associated',
                'causality_note': 'test',
                'feedback_hash': 'hash1',
                'created_at': datetime.utcnow(),
                'created_by': 'test'
            }

            engine._insert_feedback_record(record1)

            # Try same hash again
            record2 = record1.copy()
            record2['feedback_id'] = str(uuid.uuid4())

            result = engine._insert_feedback_record(record2)

            # Should return existing ID due to ON CONFLICT DO NOTHING
            records = conn.execute(text("""
                SELECT COUNT(*) FROM feedback_records WHERE feedback_hash = 'hash1'
            """)).fetchone()

            assert records[0] == 1  # Only one record


class TestContradictoryEvidence:
    """Test handling of conflicting evidence."""

    def test_preserve_contradictory_records(self, db):
        """Both supportive and contradictory kept."""
        with db.connect() as conn:
            engine = LearningFeedbackEngine(conn)

            # Supportive
            engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='supportive',
                quality_score=0.90,
                quality_delta=0.10,
                task_type='analysis',
                node_id='N1'
            )

            # Contradictory
            accum = engine._update_evidence_accumulation(
                learning_id='L1',
                learning_type='outcome',
                effect_classification='contradictory',
                quality_score=0.70,
                quality_delta=-0.10,
                task_type='analysis',
                node_id='N2'
            )

            # Both should be preserved
            assert accum['supportive_count'] == 1
            assert accum['contradictory_count'] == 1
            assert accum['times_applied'] == 2


class TestInsufficientEvidence:
    """Test insufficient evidence handling."""

    def test_no_baseline_comparison(self, db):
        """Task with no prior outcomes = insufficient_evidence."""
        engine = LearningFeedbackEngine(db.connect())

        with db.connect() as conn:
            engine.db = conn

            effect = engine._classify_effect(
                quality_score=0.90,
                baseline={
                    'comparable': False,
                    'baseline_type': 'none',
                    'baseline_quality': None,
                    'baseline_count': 0
                },
                learning_item={'id': 'L1', 'type': 'outcome'},
                outcome_status='success'
            )

            assert effect['classification'] == 'insufficient_evidence'
            assert 'baseline' in effect['reasoning'].lower()
