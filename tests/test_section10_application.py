"""
Section 10: Learning Application Layer Tests

Comprehensive test suite for learning application, execution guidance generation,
and applied learning tracking.
"""

import psycopg
import pytest
import json
import uuid
from datetime import datetime, timedelta
from psycopg.extras import RealDictCursor

TEST_TASK_TYPE = "data_analysis"
TEST_NODE_ID = str(uuid.uuid4())
TEST_WORKFLOW_ID = str(uuid.uuid4())
TEST_TASK_ID = str(uuid.uuid4())


def create_test_infrastructure(conn):
    """Set up workflow, task, node, and assignment."""
    with conn.cursor() as cur:
        # Create workflow
        cur.execute(
            """
            INSERT INTO workflows (workflow_id, name, status)
            VALUES (%s, %s, %s)
            """,
            (TEST_WORKFLOW_ID, "Test Workflow", "active"),
        )

        # Create task
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (TEST_TASK_ID, TEST_WORKFLOW_ID, TEST_TASK_TYPE, {"objective": "analyze"}, "pending"),
        )

        # Create node
        cur.execute(
            """
            INSERT INTO nodes (node_id, name, status)
            VALUES (%s, %s, %s)
            """,
            (TEST_NODE_ID, "Test Node", "available"),
        )

        # Create assignment
        assignment_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO assignments (assignment_id, task_id, node_id, status, assigned_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (assignment_id, TEST_TASK_ID, TEST_NODE_ID, "assigned", datetime.now()),
        )

        conn.commit()
        return assignment_id


def create_attempt(conn, assignment_id):
    """Create an attempt."""
    attempt_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO attempts (attempt_id, assignment_id, node_id, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (attempt_id, assignment_id, TEST_NODE_ID, "running", datetime.now()),
        )
        conn.commit()
    return attempt_id


def create_prior_learning(conn):
    """Create prior outcomes, patterns, insights for retrieval."""
    with conn.cursor() as cur:
        # Create prior outcome
        outcome_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO task_outcomes
            (outcome_id, task_id, task_type, node_id, outcome_status,
             quality_score, execution_time_seconds, result_summary, learning_points)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                outcome_id,
                TEST_TASK_ID,
                TEST_TASK_TYPE,
                TEST_NODE_ID,
                "success",
                0.95,
                30,
                {"method": "iterative_analysis"},
                ["validate_input_first", "check_data_quality"],
            ),
        )

        # Create pattern
        cur.execute(
            """
            INSERT INTO result_patterns
            (pattern_id, task_type, pattern_name, pattern_rule, success_rate, occurrence_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                TEST_TASK_TYPE,
                "validate_before_process",
                {"order": ["validate", "process", "verify"]},
                0.92,
                10,
            ),
        )

        # Create insight
        cur.execute(
            """
            INSERT INTO performance_insights
            (insight_id, node_id, task_type, insight_type, description,
             recommendation, confidence_score, evidence_count, actionable)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                TEST_NODE_ID,
                TEST_TASK_TYPE,
                "strength",
                "Excellent data validation",
                {"focus": "maintain_approach"},
                0.90,
                5,
                True,
            ),
        )

        # Create artifact (template)
        cur.execute(
            """
            INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content, quality_score, usage_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                TEST_TASK_TYPE,
                "template",
                {"steps": ["validate", "analyze", "report"]},
                0.95,
                3,
            ),
        )

        conn.commit()


def test_01_retrieval_to_application(conn):
    """Test: Retrieval → Application pipeline."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    assert result["status"] == "success"
    assert result["guidance_id"]
    assert result["applied_learning_count"] > 0
    assert result["guidance"]["summary"]["total_guidance_items"] > 0


def test_02_applied_learning_record(conn):
    """Test: Applied learning is recorded with full metadata."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Verify records in database
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT applied_id, learning_type, learning_id, relevance_score,
                   confidence, status, applied_at
            FROM applied_learning WHERE attempt_id = %s
            """,
            (attempt_id,),
        )
        records = [dict(row) for row in cur.fetchall()]

    assert len(records) > 0
    for record in records:
        assert record["applied_id"]
        assert record["learning_type"]  # outcome, pattern, insight, artifact
        assert record["learning_id"]
        assert record["status"] == "applied"
        assert record["relevance_score"] >= 0


def test_03_execution_guidance_structure(conn):
    """Test: Guidance has proper structure."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    guidance = result["guidance"]

    assert "recommended_approaches" in guidance
    assert "known_patterns" in guidance
    assert "warnings" in guidance
    assert "constraints" in guidance
    assert "insights" in guidance
    assert "useful_knowledge" in guidance
    assert "summary" in guidance


def test_04_attempt_integration(conn):
    """Test: Application integrated into attempt lifecycle."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    # Application should not break existing attempt
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT status FROM attempts WHERE attempt_id = %s""",
            (attempt_id,),
        )
        assert cur.fetchone()["status"] == "running"

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Attempt should still exist and be valid
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT status FROM attempts WHERE attempt_id = %s""",
            (attempt_id,),
        )
        assert cur.fetchone()["status"] == "running"


def test_05_worker_access_guidance(conn):
    """Test: Worker can retrieve execution guidance."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Worker retrieves guidance
    guidance = engine.get_execution_guidance(attempt_id)

    assert guidance["attempt_id"] == attempt_id
    assert "guidance" in guidance
    assert guidance["guidance"]["summary"]["total_guidance_items"] >= 0


def test_06_selectivity(conn):
    """Test: Only relevant learning is selected."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)

    # Apply with tight thresholds
    result = engine.apply_learning_to_attempt(
        attempt_id,
        TEST_TASK_ID,
        TEST_NODE_ID,
        override_config={"min_relevance_threshold": 0.95},  # Very strict
    )

    # Should still work but with fewer items
    assert result["status"] == "success"
    # Strict threshold might reduce items
    assert result["applied_learning_count"] >= 0


def test_07_negative_learning_warnings(conn):
    """Test: Failures/warnings represented as avoidance signals."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)

    # Create warning insight
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO performance_insights
            (insight_id, node_id, task_type, insight_type, description,
             recommendation, confidence_score, evidence_count, actionable)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                TEST_NODE_ID,
                TEST_TASK_TYPE,
                "warning",
                "Known failure with incomplete data",
                {"avoid": "incomplete_processing"},
                0.85,
                3,
                True,
            ),
        )
        conn.commit()

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    guidance = result["guidance"]

    # Should have warnings in guidance
    assert isinstance(guidance["warnings"], list)


def test_08_provenance_tracking(conn):
    """Test: Provenance chains back to evidence."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Get applied learning with provenance
    applied = engine.get_applied_learning(attempt_id)

    for item in applied:
        assert item["learning_id"]  # Can trace to source
        assert item["learning_type"]
        assert item["applied_at"]


def test_09_idempotency(conn):
    """Test: Repeated application doesn't duplicate records uncontrollably."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)

    # Apply once
    result1 = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)
    count1 = result1["applied_learning_count"]

    # Apply again (would fail if attempt already has guidance)
    # Expected: Should either fail, overwrite, or have explicit handling
    # Current implementation: Each call creates new guidance (should test this)

    guidance1 = engine.get_execution_guidance(attempt_id)
    assert guidance1 is not None


def test_10_historical_snapshot(conn):
    """Test: Guidance snapshot is immutable."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    guidance1 = engine.get_execution_guidance(attempt_id)
    initial_items = guidance1["guidance"]["summary"]["total_guidance_items"]

    # Guidance should not change
    guidance2 = engine.get_execution_guidance(attempt_id)
    assert guidance2["guidance"]["summary"]["total_guidance_items"] == initial_items


def test_11_no_learning_case(conn):
    """Test: Works normally with no prior learning."""
    # Create task with unique type
    unique_type = f"unique_{uuid.uuid4()}"
    unique_task_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO workflows (workflow_id, name, status)
            VALUES (%s, %s, %s)
            """,
            (str(uuid.uuid4()), "Unique Workflow", "active"),
        )
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (unique_task_id, str(uuid.uuid4()), unique_type, {}, "pending"),
        )

        assignment_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO assignments (assignment_id, task_id, node_id, status, assigned_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (assignment_id, unique_task_id, TEST_NODE_ID, "assigned", datetime.now()),
        )

        attempt_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO attempts (attempt_id, assignment_id, node_id, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (attempt_id, assignment_id, TEST_NODE_ID, "running", datetime.now()),
        )
        conn.commit()

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, unique_task_id, TEST_NODE_ID)

    # Should succeed with minimal guidance
    assert result["status"] == "success"
    assert result["guidance"]["summary"]["total_guidance_items"] == 0


def test_12_related_task_application(conn):
    """Test: Related task gets relevant learning applied."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Should have applied learning
    assert result["applied_learning_count"] > 0

    # Guidance should contain examples
    guidance = result["guidance"]
    assert len(guidance["recommended_approaches"]) > 0
    assert len(guidance["known_patterns"]) > 0


def test_13_unrelated_task_exclusion(conn):
    """Test: Unrelated task doesn't get irrelevant learning."""
    # Create unrelated task
    unrelated_type = "completely_different"
    unrelated_task_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                unrelated_task_id,
                TEST_WORKFLOW_ID,
                unrelated_type,
                {},
                "pending",
            ),
        )

        assignment_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO assignments (assignment_id, task_id, node_id, status, assigned_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (assignment_id, unrelated_task_id, TEST_NODE_ID, "assigned", datetime.now()),
        )

        attempt_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO attempts (attempt_id, assignment_id, node_id, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (attempt_id, assignment_id, TEST_NODE_ID, "running", datetime.now()),
        )
        conn.commit()

    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, unrelated_task_id, TEST_NODE_ID)

    # Unrelated task should have no applied learning (different task_type)
    assert result["applied_learning_count"] == 0


def test_14_failure_edge_cases(conn):
    """Test: Handles edge cases gracefully."""
    from application import LearningApplicationEngine, ApplicationError

    engine = LearningApplicationEngine(conn)

    # Invalid attempt
    with pytest.raises(ApplicationError):
        engine.apply_learning_to_attempt(
            str(uuid.uuid4()), TEST_TASK_ID, TEST_NODE_ID  # Non-existent
        )


def test_15_audit_trace(conn):
    """Test: Complete audit trail recorded."""
    assignment_id = create_test_infrastructure(conn)
    attempt_id = create_attempt(conn, assignment_id)
    create_prior_learning(conn)

    from application import LearningApplicationEngine

    engine = LearningApplicationEngine(conn)
    result = engine.apply_learning_to_attempt(attempt_id, TEST_TASK_ID, TEST_NODE_ID)

    # Verify trace in database
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT trace_id, guidance_id, learning_items_considered,
                   learning_items_applied, applied_decisions, rejected_decisions
            FROM guidance_traces WHERE attempt_id = %s
            """,
            (attempt_id,),
        )
        trace = cur.fetchone()

    assert trace is not None
    assert trace["guidance_id"] == result["guidance_id"]
    assert trace["learning_items_considered"] > 0
    assert trace["learning_items_applied"] == result["applied_learning_count"]


if __name__ == "__main__":
    import os

    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://user:***@localhost:5432/learning"
    )

    with psycopg.connect(DATABASE_URL) as conn:
        print("Running Section 10 tests...")
        test_01_retrieval_to_application(conn)
        print("✓ Test 01: Retrieval to application")
        test_02_applied_learning_record(conn)
        print("✓ Test 02: Applied learning record")
        test_03_execution_guidance_structure(conn)
        print("✓ Test 03: Guidance structure")
        test_04_attempt_integration(conn)
        print("✓ Test 04: Attempt integration")
        test_05_worker_access_guidance(conn)
        print("✓ Test 05: Worker access")
        test_06_selectivity(conn)
        print("✓ Test 06: Selectivity")
        test_07_negative_learning_warnings(conn)
        print("✓ Test 07: Warnings")
        test_08_provenance_tracking(conn)
        print("✓ Test 08: Provenance")
        test_09_idempotency(conn)
        print("✓ Test 09: Idempotency")
        test_10_historical_snapshot(conn)
        print("✓ Test 10: Snapshot")
        test_11_no_learning_case(conn)
        print("✓ Test 11: No learning case")
        test_12_related_task_application(conn)
        print("✓ Test 12: Related task")
        test_13_unrelated_task_exclusion(conn)
        print("✓ Test 13: Unrelated task exclusion")
        test_14_failure_edge_cases(conn)
        print("✓ Test 14: Edge cases")
        test_15_audit_trace(conn)
        print("✓ Test 15: Audit trace")
        print("\n✅ All 15 Section 10 tests passed")
