"""
Section 11 E2E: Complete Feedback Loop

Scenario:
1. Create task type with no prior learning
2. Execute Task A → record outcome → create learning
3. Task B (same type) → retrieve learning → apply guidance
4. Execute Task B with guidance → record outcome
5. Evaluate: learning effectiveness
6. Execute Task C (same type) → retrieve updated learning
7. Verify: confidence increased from evidence

Tests complete loop: retrieve → apply → execute → feedback → validate → retrieve again
"""

import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from fabric.api.feedback import LearningFeedbackEngine


@pytest.fixture(scope="function")
def db():
    """Create in-memory database for E2E test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.begin() as conn:
        # Minimal schema
        for table_sql in [
            """CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT
            )""",
            """CREATE TABLE nodes (
                node_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT
            )""",
            """CREATE TABLE attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT,
                node_id TEXT,
                status TEXT
            )""",
            """CREATE TABLE task_outcomes (
                outcome_id TEXT PRIMARY KEY,
                attempt_id TEXT,
                task_id TEXT,
                node_id TEXT,
                outcome_status TEXT,
                quality_score REAL,
                execution_time_seconds INTEGER
            )""",
            """CREATE TABLE applied_learning (
                applied_id TEXT PRIMARY KEY,
                attempt_id TEXT,
                learning_type TEXT,
                learning_id TEXT,
                relevance_score REAL
            )""",
            """CREATE TABLE execution_guidance (
                guidance_id TEXT PRIMARY KEY,
                attempt_id TEXT,
                task_id TEXT,
                node_id TEXT,
                generated_at TIMESTAMP
            )""",
            """CREATE TABLE feedback_records (
                feedback_id TEXT PRIMARY KEY,
                attempt_id TEXT,
                task_id TEXT,
                node_id TEXT,
                outcome_id TEXT,
                applied_learning_id TEXT,
                learning_type TEXT,
                learning_id TEXT,
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
            )""",
            """CREATE TABLE evidence_accumulation (
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
            )""",
            """CREATE TABLE confidence_adjustments (
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
            )""",
            """CREATE TABLE validation_transitions (
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
            )""",
            """CREATE TABLE feedback_processing_log (
                log_id TEXT PRIMARY KEY,
                attempt_id TEXT NOT NULL,
                outcome_id TEXT,
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
            )""",
            """CREATE TABLE feedback_config (
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
            )"""
        ]:
            conn.execute(text(table_sql))

        # Insert config
        conn.execute(text("""
            INSERT INTO feedback_config (config_id, config_name, active)
            VALUES ('cfg1', 'default', 1)
        """))

    yield engine


def test_complete_feedback_loop(db):
    """E2E: retrieve → apply → execute → feedback → validate → retrieve."""

    with db.connect() as conn:
        engine = LearningFeedbackEngine(conn)

        # Setup
        task_id_a = str(uuid.uuid4())
        task_id_b = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        learning_id = str(uuid.uuid4())

        # Create tasks
        conn.execute(text("""
            INSERT INTO tasks (task_id, task_type, status)
            VALUES (:tid, 'analysis', 'pending')
        """), {'tid': task_id_a})

        conn.execute(text("""
            INSERT INTO tasks (task_id, task_type, status)
            VALUES (:tid, 'analysis', 'pending')
        """), {'tid': task_id_b})

        conn.execute(text("""
            INSERT INTO nodes (node_id, name, status)
            VALUES (:nid, 'test-node', 'available')
        """), {'nid': node_id})

        # PHASE 1: Task A Execution
        # Baseline: previous attempts for same task type (simulated)
        # Insert historical outcomes for baseline
        for i in range(4):
            outcome_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO task_outcomes (
                    outcome_id, task_id, node_id, outcome_status, quality_score
                ) VALUES (:oid, :tid, :nid, 'success', 0.80)
            """), {'oid': outcome_id, 'tid': task_id_a, 'nid': node_id})

        # Task A attempt with learning applied
        attempt_a = str(uuid.uuid4())
        outcome_a = str(uuid.uuid4())
        applied_learning_a = str(uuid.uuid4())

        conn.execute(text("""
            INSERT INTO attempts (attempt_id, task_id, node_id, status)
            VALUES (:aid, :tid, :nid, 'completed')
        """), {'aid': attempt_a, 'tid': task_id_a, 'nid': node_id})

        # Record that learning was applied
        conn.execute(text("""
            INSERT INTO applied_learning (applied_id, attempt_id, learning_type, learning_id)
            VALUES (:alid, :aid, 'outcome', :lid)
        """), {'alid': applied_learning_a, 'aid': attempt_a, 'lid': learning_id})

        # Outcome: Task A succeeded with high quality (supportive)
        conn.execute(text("""
            INSERT INTO task_outcomes (outcome_id, attempt_id, task_id, node_id, outcome_status, quality_score)
            VALUES (:oid, :aid, :tid, :nid, 'success', 0.92)
        """), {
            'oid': outcome_a,
            'aid': attempt_a,
            'tid': task_id_a,
            'nid': node_id
        })

        # PHASE 2: Record Feedback for Task A
        result_a = engine.record_feedback(
            attempt_id=attempt_a,
            task_id=task_id_a,
            node_id=node_id,
            outcome_id=outcome_a,
            applied_learning_list=[{
                'applied_id': applied_learning_a,
                'type': 'outcome',
                'id': learning_id
            }],
            result={'method': 'learned_approach'},
            quality_score=0.92,
            outcome_status='success'
        )

        # Verify: Feedback recorded
        assert result_a['feedback_records_created'] == 1
        assert result_a['evidence_updated'] == 1
        assert result_a['duplicate_detected'] is False

        # Verify: Evidence accumulated
        evidence_query = """
            SELECT confidence_score, current_validation_state, supportive_count, times_applied
            FROM evidence_accumulation
            WHERE learning_id = :lid AND learning_type = 'outcome'
        """
        ev = conn.execute(
            text(evidence_query),
            {'lid': learning_id}
        ).fetchone()

        assert ev is not None
        assert ev[2] == 1  # supportive_count
        assert ev[3] == 1  # times_applied
        initial_confidence = ev[0]
        initial_state = ev[1]

        # PHASE 3: Task B (same type) - more evidence
        attempt_b = str(uuid.uuid4())
        outcome_b = str(uuid.uuid4())
        applied_learning_b = str(uuid.uuid4())

        conn.execute(text("""
            INSERT INTO attempts (attempt_id, task_id, node_id, status)
            VALUES (:aid, :tid, :nid, 'completed')
        """), {'aid': attempt_b, 'tid': task_id_b, 'nid': node_id})

        conn.execute(text("""
            INSERT INTO applied_learning (applied_id, attempt_id, learning_type, learning_id)
            VALUES (:alid, :aid, 'outcome', :lid)
        """), {'alid': applied_learning_b, 'aid': attempt_b, 'lid': learning_id})

        # Outcome: Task B succeeded with high quality (supportive again)
        conn.execute(text("""
            INSERT INTO task_outcomes (outcome_id, attempt_id, task_id, node_id, outcome_status, quality_score)
            VALUES (:oid, :aid, :tid, :nid, 'success', 0.90)
        """), {
            'oid': outcome_b,
            'aid': attempt_b,
            'tid': task_id_b,
            'nid': node_id
        })

        # Record Feedback for Task B
        result_b = engine.record_feedback(
            attempt_id=attempt_b,
            task_id=task_id_b,
            node_id=node_id,
            outcome_id=outcome_b,
            applied_learning_list=[{
                'applied_id': applied_learning_b,
                'type': 'outcome',
                'id': learning_id
            }],
            result={'method': 'learned_approach'},
            quality_score=0.90,
            outcome_status='success'
        )

        # Verify: Second feedback processed
        assert result_b['feedback_records_created'] == 1
        assert result_b['evidence_updated'] == 1

        # PHASE 4: Verify Evidence Grown & State Updated
        ev2 = conn.execute(
            text(evidence_query),
            {'lid': learning_id}
        ).fetchone()

        assert ev2[2] == 2  # supportive_count increased
        assert ev2[3] == 2  # times_applied increased
        assert ev2[0] > initial_confidence  # confidence increased
        assert ev2[1] in ['emerging', 'validated']  # state advanced

        # PHASE 5: Add Contradictory Evidence
        attempt_c = str(uuid.uuid4())
        outcome_c = str(uuid.uuid4())
        applied_learning_c = str(uuid.uuid4())

        conn.execute(text("""
            INSERT INTO attempts (attempt_id, task_id, node_id, status)
            VALUES (:aid, :tid, :nid, 'completed')
        """), {'aid': attempt_c, 'tid': task_id_b, 'nid': node_id})

        conn.execute(text("""
            INSERT INTO applied_learning (applied_id, attempt_id, learning_type, learning_id)
            VALUES (:alid, :aid, 'outcome', :lid)
        """), {'alid': applied_learning_c, 'aid': attempt_c, 'lid': learning_id})

        # Outcome: Failed despite learning (contradictory)
        conn.execute(text("""
            INSERT INTO task_outcomes (outcome_id, attempt_id, task_id, node_id, outcome_status, quality_score)
            VALUES (:oid, :aid, :tid, :nid, 'failure', 0.65)
        """), {
            'oid': outcome_c,
            'aid': attempt_c,
            'tid': task_id_b,
            'nid': node_id
        })

        # Record feedback
        result_c = engine.record_feedback(
            attempt_id=attempt_c,
            task_id=task_id_b,
            node_id=node_id,
            outcome_id=outcome_c,
            applied_learning_list=[{
                'applied_id': applied_learning_c,
                'type': 'outcome',
                'id': learning_id
            }],
            result={'method': 'learned_approach_failed'},
            quality_score=0.65,
            outcome_status='failure'
        )

        # Verify: Contradictory evidence recorded
        assert result_c['feedback_records_created'] == 1
        assert result_c['evidence_updated'] == 1

        # PHASE 6: Verify Mixed Evidence Preserved
        ev3 = conn.execute(
            text(evidence_query),
            {'lid': learning_id}
        ).fetchone()

        assert ev3[2] == 2  # supportive_count preserved
        assert ev3[3] == 3  # times_applied
        # Confidence likely decreased due to contradictory
        assert ev3[0] < ev2[0]  # Confidence dropped

        # PHASE 7: Check validation transition history
        transitions = conn.execute(text("""
            SELECT from_state, to_state FROM validation_transitions
            WHERE learning_id = :lid
            ORDER BY transitioned_at
        """), {'lid': learning_id}).fetchall()

        # Should have transitioned from candidate to emerging (at least)
        assert len(transitions) > 0
        assert transitions[0][0] == 'candidate'

        # PHASE 8: Verify idempotency
        result_dup = engine.record_feedback(
            attempt_id=attempt_a,
            task_id=task_id_a,
            node_id=node_id,
            outcome_id=outcome_a,
            applied_learning_list=[{
                'applied_id': applied_learning_a,
                'type': 'outcome',
                'id': learning_id
            }],
            result={'method': 'learned_approach'},
            quality_score=0.92,
            outcome_status='success'
        )

        assert result_dup['duplicate_detected'] is True

        print("\n✓ E2E Test PASSED: Complete feedback loop with evidence accumulation and state transitions")


def test_insufficient_evidence_handling(db):
    """E2E: Verify insufficient_evidence classification."""

    with db.connect() as conn:
        engine = LearningFeedbackEngine(conn)

        task_id = str(uuid.uuid4())
        node_id = str(uuid.uuid4())
        learning_id = str(uuid.uuid4())

        conn.execute(text("""
            INSERT INTO tasks (task_id, task_type, status)
            VALUES (:tid, 'novel_task', 'pending')
        """), {'tid': task_id})

        conn.execute(text("""
            INSERT INTO nodes (node_id, name, status)
            VALUES (:nid, 'node', 'available')
        """), {'nid': node_id})

        attempt_id = str(uuid.uuid4())
        outcome_id = str(uuid.uuid4())
        applied_learning_id = str(uuid.uuid4())

        conn.execute(text("""
            INSERT INTO attempts (attempt_id, task_id, node_id, status)
            VALUES (:aid, :tid, :nid, 'completed')
        """), {'aid': attempt_id, 'tid': task_id, 'nid': node_id})

        conn.execute(text("""
            INSERT INTO applied_learning (applied_id, attempt_id, learning_type, learning_id)
            VALUES (:alid, :aid, 'outcome', :lid)
        """), {'alid': applied_learning_id, 'aid': attempt_id, 'lid': learning_id})

        conn.execute(text("""
            INSERT INTO task_outcomes (outcome_id, attempt_id, task_id, node_id, outcome_status, quality_score)
            VALUES (:oid, :aid, :tid, :nid, 'success', 0.95)
        """), {
            'oid': outcome_id,
            'aid': attempt_id,
            'tid': task_id,
            'nid': node_id
        })

        # No baseline exists (novel task type)
        result = engine.record_feedback(
            attempt_id=attempt_id,
            task_id=task_id,
            node_id=node_id,
            outcome_id=outcome_id,
            applied_learning_list=[{
                'applied_id': applied_learning_id,
                'type': 'outcome',
                'id': learning_id
            }],
            result={},
            quality_score=0.95,
            outcome_status='success'
        )

        # Check feedback classification
        feedback = conn.execute(text("""
            SELECT effect_classification FROM feedback_records
            WHERE learning_id = :lid
        """), {'lid': learning_id}).fetchone()

        assert feedback is not None
        assert feedback[0] == 'insufficient_evidence'

        # Verify validation state stays as candidate
        evidence = conn.execute(text("""
            SELECT current_validation_state FROM evidence_accumulation
            WHERE learning_id = :lid
        """), {'lid': learning_id}).fetchone()

        assert evidence[0] == 'candidate'

        print("\n✓ E2E Test PASSED: Insufficient evidence handling")
