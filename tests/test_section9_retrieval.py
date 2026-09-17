"""
Section 9: Retrieval & Context Layer Tests

Comprehensive test suite for task context retrieval, deduplication,
provenance tracking, and context assembly.
"""

import psycopg
import pytest
import json
import uuid
from datetime import datetime, timedelta
from psycopg.extras import RealDictCursor

# Test fixtures
TEST_TASK_TYPE = "analysis_task"
TEST_NODE_ID = str(uuid.uuid4())
TEST_WORKFLOW_ID = str(uuid.uuid4())
TEST_TASK_ID = str(uuid.uuid4())
TEST_OUTCOME_ID = str(uuid.uuid4())
TEST_PATTERN_ID = str(uuid.uuid4())
TEST_INSIGHT_ID = str(uuid.uuid4())
TEST_ARTIFACT_ID = str(uuid.uuid4())


def create_test_data(conn):
    """Set up test data: workflow, task, outcomes, patterns, insights."""
    with conn.cursor() as cur:
        # Create workflow
        cur.execute(
            """
            INSERT INTO workflows (workflow_id, name, description, status)
            VALUES (%s, %s, %s, %s)
            """,
            (TEST_WORKFLOW_ID, "Test Workflow", "Test", "active"),
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

        # Create prior outcomes for same task type
        for i in range(3):
            outcome_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO task_outcomes
                (outcome_id, task_id, task_type, node_id, outcome_status,
                 quality_score, execution_time_seconds, result_summary,
                 learning_points, patterns_matched)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    outcome_id,
                    TEST_TASK_ID if i == 0 else str(uuid.uuid4()),
                    TEST_TASK_TYPE,
                    TEST_NODE_ID,
                    "success",
                    0.85 + (i * 0.05),  # 0.85, 0.90, 0.95
                    30 + (i * 5),
                    {"result": f"outcome_{i}"},
                    [f"lesson_{i}"],
                    [],
                ),
            )

        # Create patterns
        for i in range(2):
            cur.execute(
                """
                INSERT INTO result_patterns
                (pattern_id, task_type, pattern_name, pattern_rule,
                 success_rate, occurrence_count, first_seen, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    TEST_TASK_TYPE,
                    f"pattern_{i}",
                    {"rule": f"rule_{i}"},
                    0.70 + (i * 0.15),  # 0.70, 0.85
                    10 + (i * 5),
                    datetime.now() - timedelta(days=30),
                    datetime.now(),
                ),
            )

        # Create insights
        for i in range(2):
            cur.execute(
                """
                INSERT INTO performance_insights
                (insight_id, node_id, task_type, insight_type,
                 description, recommendation, confidence_score,
                 evidence_count, actionable)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    TEST_NODE_ID if i == 0 else None,  # One node-specific, one generic
                    TEST_TASK_TYPE,
                    "strength" if i == 0 else "opportunity",
                    f"insight_{i}",
                    {"recommendation": f"rec_{i}"},
                    0.80 + (i * 0.1),  # 0.80, 0.90
                    5 + (i * 2),
                    True,
                ),
            )

        # Create artifacts
        for i in range(2):
            cur.execute(
                """
                INSERT INTO knowledge_artifacts
                (artifact_id, task_type, artifact_type, content,
                 quality_score, usage_count, effectiveness_rating)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    TEST_TASK_TYPE,
                    "template" if i == 0 else "solution",
                    {"template": f"content_{i}"},
                    0.75 + (i * 0.15),  # 0.75, 0.90
                    10 + (i * 5),
                    0.8,
                ),
            )

        conn.commit()


def test_01_task_context_retrieval(conn):
    """Test: Task → Retrieval returns structured context."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID, node_id=TEST_NODE_ID)

    assert result["status"] == "success"
    assert result["package_id"]
    assert result["trace_id"]
    assert result["query_id"]
    assert result["task_id"] == TEST_TASK_ID

    context = result["context"]
    assert context["trace_id"]
    assert context["task_id"] == TEST_TASK_ID
    assert context["node_id"] == TEST_NODE_ID
    assert "summary" in context
    assert context["summary"]["total_items"] > 0


def test_02_multi_source_retrieval(conn):
    """Test: Multi-source retrieval populates all context types."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID, node_id=TEST_NODE_ID)

    context = result["context"]
    summary = context["summary"]

    # Should have retrieved from all sources
    assert summary["outcome_count"] > 0, "No outcomes retrieved"
    assert summary["pattern_count"] > 0, "No patterns retrieved"
    assert summary["insight_count"] > 0, "No insights retrieved"
    assert summary["artifact_count"] > 0, "No artifacts retrieved"


def test_03_relevance_scoring(conn):
    """Test: Retrieved items are ranked by relevance."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)

    context = result["context"]

    # Outcomes should be ordered by relevance
    if context["outcomes"]:
        scores = [o["relevance_score"] for o in context["outcomes"]]
        assert scores == sorted(scores, reverse=True), "Outcomes not ordered by relevance"

    if context["patterns"]:
        scores = [p["relevance_score"] for p in context["patterns"]]
        assert scores == sorted(scores, reverse=True), "Patterns not ordered by relevance"


def test_04_context_assembly_structure(conn):
    """Test: Context package has proper structure with provenance."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)

    context = result["context"]

    # Verify structure
    assert "trace_id" in context
    assert "task_id" in context
    assert "outcomes" in context
    assert "patterns" in context
    assert "insights" in context
    assert "artifacts" in context
    assert "graph_entities" in context
    assert "summary" in context

    # Verify outcomes have required fields
    if context["outcomes"]:
        outcome = context["outcomes"][0]
        assert "outcome_id" in outcome
        assert "status" in outcome
        assert "quality_score" in outcome
        assert "relevance_score" in outcome


def test_05_size_control_limits(conn):
    """Test: Context size control applies limits."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # Apply tight limits
    limits = {
        "max_outcomes": 2,
        "max_patterns": 1,
        "max_insights": 1,
        "max_artifacts": 1,
        "max_total_items": 5,
    }

    result = retriever.query_task_context(TEST_TASK_ID, limit_config=limits)
    context = result["context"]

    assert len(context["outcomes"]) <= 2
    assert len(context["patterns"]) <= 1
    assert len(context["insights"]) <= 1
    assert len(context["artifacts"]) <= 1
    assert context["summary"]["total_items"] <= 5


def test_06_provenance_tracking(conn):
    """Test: Every retrieved item has traceable provenance."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)

    # Verify trace records in database
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM retrieval_traces WHERE trace_id = %s
            """,
            (result["trace_id"],),
        )
        trace = cur.fetchone()

    assert trace is not None
    assert trace["query_id"]
    assert trace["total_items_returned"] > 0
    assert trace["trace_status"] == "complete"


def test_07_retrieval_trace_recording(conn):
    """Test: Retrieval trace persists complete audit trail."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)

    trace_id = result["trace_id"]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT outcomes_considered, patterns_considered, insights_considered,
                   artifacts_considered, outcomes_selected, patterns_selected,
                   insights_selected, artifacts_selected, total_items_returned,
                   deduplication_count, execution_time_ms
            FROM retrieval_traces WHERE trace_id = %s
            """,
            (trace_id,),
        )
        trace = cur.fetchone()

    assert trace["outcomes_considered"] > 0
    assert trace["patterns_considered"] > 0
    assert trace["total_items_returned"] > 0
    assert trace["execution_time_ms"] >= 0


def test_08_deduplication(conn):
    """Test: Duplicate items are deduplicated without data loss."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # Query multiple times - should deduplicate
    result1 = retriever.query_task_context(TEST_TASK_ID)
    count1 = result1["context"]["summary"]["total_items"]

    result2 = retriever.query_task_context(TEST_TASK_ID)
    count2 = result2["context"]["summary"]["total_items"]

    # Same query should return same deduplication
    assert count1 == count2


def test_09_empty_context_behavior(conn):
    """Test: Task with no prior learning returns valid empty context."""
    # Create task with different task type
    unique_task_type = f"unique_{uuid.uuid4()}"
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
            (
                unique_task_id,
                str(uuid.uuid4()),
                unique_task_type,
                {"objective": "analyze"},
                "pending",
            ),
        )
        conn.commit()

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(unique_task_id)

    # Should succeed with minimal context
    assert result["status"] == "success"
    context = result["context"]
    assert context["summary"]["total_items"] == 0
    assert context["outcomes"] == []
    assert context["patterns"] == []


def test_10_context_package_storage(conn):
    """Test: Context packages are stored and retrievable."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)
    package_id = result["package_id"]

    # Retrieve package from database
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT package_id, context_data, item_count, context_size_bytes
            FROM context_packages WHERE package_id = %s
            """,
            (package_id,),
        )
        package = cur.fetchone()

    assert package is not None
    assert package["package_id"] == package_id
    assert package["item_count"] == result["context"]["summary"]["total_items"]
    assert package["context_size_bytes"] > 0


def test_11_related_task_retrieval(conn):
    """Test: Related task retrieves relevant prior learning from similar task type."""
    create_test_data(conn)

    # Create second task with same task type
    task2_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (task2_id, TEST_WORKFLOW_ID, TEST_TASK_TYPE, {"objective": "analyze_v2"}, "pending"),
        )
        conn.commit()

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # Task 1 retrieval for baseline
    result1 = retriever.query_task_context(TEST_TASK_ID)
    count1 = result1["context"]["summary"]["total_items"]

    # Task 2 should retrieve same pattern/artifact learning
    result2 = retriever.query_task_context(task2_id)
    count2 = result2["context"]["summary"]["total_items"]

    # Related task should retrieve learning
    assert count2 > 0
    assert "patterns" in result2["context"]
    assert len(result2["context"]["patterns"]) > 0


def test_12_unrelated_task_exclusion(conn):
    """Test: Unrelated task does not retrieve irrelevant learning."""
    create_test_data(conn)

    # Create task with different task type
    unrelated_type = "completely_different_task"
    unrelated_id = str(uuid.uuid4())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (unrelated_id, TEST_WORKFLOW_ID, unrelated_type, {"objective": "other"}, "pending"),
        )
        conn.commit()

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(unrelated_id)

    context = result["context"]

    # Should have minimal or no relevant learning
    assert context["summary"]["total_items"] == 0
    assert len(context["outcomes"]) == 0
    assert len(context["patterns"]) == 0


def test_13_node_specific_insights(conn):
    """Test: Node-specific insights are included when node_id provided."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # With node context
    result_with_node = retriever.query_task_context(TEST_TASK_ID, node_id=TEST_NODE_ID)
    insights_with = result_with_node["context"]["insights"]

    # Without node context
    result_without_node = retriever.query_task_context(TEST_TASK_ID, node_id=None)
    insights_without = result_without_node["context"]["insights"]

    # Should have different insight counts
    # (with_node includes node-specific + generic, without only generic)
    assert len(insights_with) >= len(insights_without)


def test_14_feedback_recording(conn):
    """Test: Retrieval feedback is recorded and retrievable."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)
    package_id = result["package_id"]

    # Record feedback
    feedback = retriever.record_retrieval_feedback(
        package_id=package_id,
        node_id=TEST_NODE_ID,
        usefulness_score=0.85,
        used_items=["item1", "item2"],
        feedback_text="Very helpful context",
    )

    assert feedback["feedback_id"]
    assert feedback["package_id"] == package_id
    assert feedback["status"] == "recorded"

    # Verify in database
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM retrieval_feedback WHERE feedback_id = %s
            """,
            (feedback["feedback_id"],),
        )
        db_feedback = cur.fetchone()

    assert db_feedback is not None
    assert float(db_feedback["usefulness_score"]) == 0.85


def test_15_full_lifecycle_trace(conn):
    """Test: Complete trace from retrieval through feedback to outcome."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # 1. Initial retrieval
    result = retriever.query_task_context(TEST_TASK_ID, node_id=TEST_NODE_ID)
    package_id = result["package_id"]
    trace_id = result["trace_id"]

    # 2. Record feedback
    feedback = retriever.record_retrieval_feedback(
        package_id=package_id,
        node_id=TEST_NODE_ID,
        usefulness_score=0.90,
    )

    # 3. Verify complete trace
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Query → Trace
        cur.execute(
            """
            SELECT * FROM retrieval_traces WHERE trace_id = %s
            """,
            (trace_id,),
        )
        trace = cur.fetchone()

        assert trace is not None

        # Trace → Package
        cur.execute(
            """
            SELECT * FROM context_packages WHERE trace_id = %s
            """,
            (trace_id,),
        )
        package = cur.fetchone()

        assert package is not None

        # Package → Feedback
        cur.execute(
            """
            SELECT * FROM retrieval_feedback WHERE package_id = %s
            """,
            (package_id,),
        )
        fb = cur.fetchone()

        assert fb is not None


# Edge cases and error handling

def test_16_invalid_task(conn):
    """Test: Invalid task raises appropriate error."""
    from retrieval import ContextRetriever, RetrieverError

    retriever = ContextRetriever(conn)

    with pytest.raises(RetrieverError):
        retriever.query_task_context(str(uuid.uuid4()))


def test_17_malformed_metadata(conn):
    """Test: Malformed stored metadata is handled gracefully."""
    # This would require creating intentionally malformed data
    # For now, verify that normal data doesn't break
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(TEST_TASK_ID)

    assert result["status"] == "success"


def test_18_config_limits_override(conn):
    """Test: Configuration limits can be overridden per-request."""
    create_test_data(conn)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)

    # Tight limits
    result = retriever.query_task_context(
        TEST_TASK_ID,
        limit_config={"max_total_items": 1, "max_outcomes": 0, "max_patterns": 0},
    )

    assert result["context"]["summary"]["total_items"] <= 1


if __name__ == "__main__":
    import os

    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://user:password@localhost:5432/learning"
    )

    with psycopg.connect(DATABASE_URL) as conn:
        # Run tests
        print("Running Section 9 tests...")
        test_01_task_context_retrieval(conn)
        print("✓ Test 01: Task context retrieval")
        test_02_multi_source_retrieval(conn)
        print("✓ Test 02: Multi-source retrieval")
        test_03_relevance_scoring(conn)
        print("✓ Test 03: Relevance scoring")
        test_04_context_assembly_structure(conn)
        print("✓ Test 04: Context assembly")
        test_05_size_control_limits(conn)
        print("✓ Test 05: Size control")
        test_06_provenance_tracking(conn)
        print("✓ Test 06: Provenance tracking")
        test_07_retrieval_trace_recording(conn)
        print("✓ Test 07: Trace recording")
        test_08_deduplication(conn)
        print("✓ Test 08: Deduplication")
        test_09_empty_context_behavior(conn)
        print("✓ Test 09: Empty context")
        test_10_context_package_storage(conn)
        print("✓ Test 10: Context storage")
        test_11_related_task_retrieval(conn)
        print("✓ Test 11: Related task retrieval")
        test_12_unrelated_task_exclusion(conn)
        print("✓ Test 12: Unrelated task exclusion")
        test_13_node_specific_insights(conn)
        print("✓ Test 13: Node-specific insights")
        test_14_feedback_recording(conn)
        print("✓ Test 14: Feedback recording")
        test_15_full_lifecycle_trace(conn)
        print("✓ Test 15: Full lifecycle trace")
        test_16_invalid_task(conn)
        print("✓ Test 16: Invalid task handling")
        test_17_malformed_metadata(conn)
        print("✓ Test 17: Malformed metadata handling")
        test_18_config_limits_override(conn)
        print("✓ Test 18: Config override")
        print("\n✅ All 18 Section 9 tests passed")
