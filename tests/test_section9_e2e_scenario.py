"""
Section 9: End-to-End Scenario Test
Complete workflow: Task A execution → Learning → Task B retrieval → Context validation
"""

import psycopg
import uuid
from datetime import datetime
from psycopg.extras import RealDictCursor


def test_complete_scenario(conn):
    """
    Complete scenario: Execute Task A, create learning, then retrieve context for Task B.
    
    Workflow:
    1. Create workflow with task A and task B (same type)
    2. Create node and assignment for task A
    3. Execute task A: claim → attempt → result → complete
    4. Record outcome for task A
    5. Create pattern from task A learning
    6. Retrieve context for task B
    7. Verify task B context contains task A learning
    """

    task_type = "data_analysis"
    workflow_id = str(uuid.uuid4())
    node_id = str(uuid.uuid4())
    
    # Setup
    with conn.cursor() as cur:
        # Create workflow
        cur.execute(
            """
            INSERT INTO workflows (workflow_id, name, description, status)
            VALUES (%s, %s, %s, %s)
            """,
            (workflow_id, "E2E Test Workflow", "Scenario test", "active"),
        )

        # Create Task A (reference task)
        task_a_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                task_a_id,
                workflow_id,
                task_type,
                {"objective": "analyze_data", "data_source": "api"},
                "pending",
            ),
        )

        # Create Task B (new task, same type)
        task_b_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO tasks (task_id, workflow_id, task_type, specification, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                task_b_id,
                workflow_id,
                task_type,
                {"objective": "analyze_different_data", "data_source": "file"},
                "pending",
            ),
        )

        # Create node
        cur.execute(
            """
            INSERT INTO nodes (node_id, name, status)
            VALUES (%s, %s, %s)
            """,
            (node_id, "Scenario Test Node", "available"),
        )

        conn.commit()

    # Execute Task A through full lifecycle
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Create assignment for Task A
        assignment_a_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO assignments
            (assignment_id, task_id, node_id, status, assigned_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING assignment_id
            """,
            (assignment_a_id, task_a_id, node_id, "assigned", datetime.now()),
        )

        # Claim assignment
        cur.execute(
            """
            UPDATE assignments SET status = %s, claimed_at = %s
            WHERE assignment_id = %s
            """,
            ("claimed", datetime.now(), assignment_a_id),
        )

        # Create attempt
        attempt_a_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO attempts
            (attempt_id, assignment_id, node_id, status, started_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (attempt_a_id, assignment_a_id, node_id, "running", datetime.now()),
        )

        # Submit result
        cur.execute(
            """
            INSERT INTO results
            (result_id, attempt_id, node_id, result, quality_score, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                attempt_a_id,
                node_id,
                {"analysis": "detailed_findings", "confidence": 0.95},
                0.95,
                datetime.now(),
            ),
        )

        # Complete attempt
        cur.execute(
            """
            UPDATE attempts SET status = %s, completed_at = %s
            WHERE attempt_id = %s
            """,
            ("completed", datetime.now(), attempt_a_id),
        )

        # Complete assignment
        cur.execute(
            """
            UPDATE assignments SET status = %s, completed_at = %s
            WHERE assignment_id = %s
            """,
            ("completed", datetime.now(), assignment_a_id),
        )

        conn.commit()

    # Record outcome for Task A
    with conn.cursor() as cur:
        outcome_a_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO task_outcomes
            (outcome_id, task_id, task_type, node_id, outcome_status,
             quality_score, execution_time_seconds, result_summary,
             learning_points, patterns_matched)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                outcome_a_id,
                task_a_id,
                task_type,
                node_id,
                "success",
                0.95,
                42,
                {"analysis": "detailed_findings", "high_confidence": True},
                ["data_quality_matters", "confidence_threshold_is_critical"],
                [],
            ),
        )

        conn.commit()

    # Create pattern from Task A learning
    with conn.cursor() as cur:
        pattern_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO result_patterns
            (pattern_id, task_type, pattern_name, pattern_rule,
             success_rate, occurrence_count, first_seen, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pattern_id,
                task_type,
                "high_confidence_analysis",
                {"confidence_threshold": 0.9, "validate_data_quality": True},
                0.95,
                1,
                datetime.now(),
                datetime.now(),
            ),
        )

        conn.commit()

    # Create insight from Task A learning
    with conn.cursor() as cur:
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
                node_id,
                task_type,
                "strength",
                "Excellent data quality validation",
                {"focus": "maintain_current_approach", "confidence_threshold": 0.9},
                0.92,
                1,
                True,
            ),
        )

        conn.commit()

    # Create knowledge artifact from Task A success
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content,
             quality_score, usage_count, effectiveness_rating)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                task_type,
                "template",
                {
                    "steps": [
                        "validate_data_quality",
                        "check_confidence_threshold",
                        "generate_analysis",
                    ],
                    "validation_rules": {"min_confidence": 0.9},
                },
                0.95,
                1,
                0.95,
            ),
        )

        conn.commit()

    # NOW: Retrieve context for Task B (should get Task A learning)
    print("\n" + "=" * 60)
    print("SCENARIO TEST: Task A → Learning → Task B Context Retrieval")
    print("=" * 60)

    from retrieval import ContextRetriever

    retriever = ContextRetriever(conn)
    result = retriever.query_task_context(task_b_id, node_id=node_id)

    assert result["status"] == "success"
    context = result["context"]

    print(f"\n✓ Retrieved context package: {result['package_id']}")
    print(f"✓ Trace ID: {result['trace_id']}")
    print(f"✓ Query ID: {result['query_id']}")
    print(f"\nContext Summary:")
    print(f"  Total items: {context['summary']['total_items']}")
    print(f"  Outcomes: {context['summary']['outcome_count']}")
    print(f"  Patterns: {context['summary']['pattern_count']}")
    print(f"  Insights: {context['summary']['insight_count']}")
    print(f"  Artifacts: {context['summary']['artifact_count']}")

    # VERIFY: Context for Task B contains Task A learning
    print(f"\n--- Verification ---")

    # Should have outcome from Task A (same task type)
    if context["outcomes"]:
        print(f"✓ Task A outcome included (quality: {context['outcomes'][0]['quality_score']})")
        assert context["outcomes"][0]["quality_score"] == 0.95
    else:
        raise AssertionError("No outcomes found for Task B context")

    # Should have pattern from Task A
    if context["patterns"]:
        print(f"✓ Pattern from Task A included: {context['patterns'][0]['pattern_name']}")
        assert context["patterns"][0]["success_rate"] == 0.95
    else:
        raise AssertionError("No patterns found for Task B context")

    # Should have node-specific insight from Task A
    if context["insights"]:
        print(f"✓ Node-specific insight included: {context['insights'][0]['description']}")
        assert context["insights"][0]["confidence_score"] == 0.92
    else:
        raise AssertionError("No insights found for Task B context")

    # Should have artifact template from Task A
    if context["artifacts"]:
        print(f"✓ Knowledge artifact included (type: {context['artifacts'][0]['artifact_type']})")
        assert context["artifacts"][0]["quality_score"] == 0.95
        print(f"  Template steps: {len(context['artifacts'][0]['content']['steps'])}")
    else:
        raise AssertionError("No artifacts found for Task B context")

    # Verify trace recorded everything
    print(f"\n--- Retrieval Trace ---")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT outcomes_considered, patterns_considered, insights_considered,
                   artifacts_considered, total_items_returned, deduplication_count,
                   execution_time_ms
            FROM retrieval_traces WHERE trace_id = %s
            """,
            (result["trace_id"],),
        )
        trace = cur.fetchone()

    print(f"Considered: {trace['outcomes_considered']} outcomes, "
          f"{trace['patterns_considered']} patterns, "
          f"{trace['insights_considered']} insights, "
          f"{trace['artifacts_considered']} artifacts")
    print(f"Selected: {context['summary']['total_items']} items")
    print(f"Deduplication: {trace['deduplication_count']} duplicates removed")
    print(f"Execution time: {trace['execution_time_ms']}ms")

    # Record feedback: context was useful
    print(f"\n--- Recording Feedback ---")
    feedback = retriever.record_retrieval_feedback(
        package_id=result["package_id"],
        node_id=node_id,
        usefulness_score=0.90,
        used_items=["pattern", "artifact"],
        feedback_text="Pattern and template were directly applicable",
    )
    print(f"✓ Feedback recorded: {feedback['feedback_id']}")
    print(f"✓ Usefulness score: {feedback['usefulness_score']}")

    # Verify end-to-end trace
    print(f"\n--- End-to-End Trace ---")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Query
        cur.execute(
            """
            SELECT query_id FROM retrieval_queries WHERE query_id = %s
            """,
            (result["query_id"],),
        )
        assert cur.fetchone() is not None
        print(f"✓ Query recorded")

        # Trace
        cur.execute(
            """
            SELECT trace_id FROM retrieval_traces WHERE trace_id = %s
            """,
            (result["trace_id"],),
        )
        assert cur.fetchone() is not None
        print(f"✓ Trace recorded")

        # Package
        cur.execute(
            """
            SELECT package_id FROM context_packages WHERE package_id = %s
            """,
            (result["package_id"],),
        )
        assert cur.fetchone() is not None
        print(f"✓ Context package stored")

        # Feedback
        cur.execute(
            """
            SELECT feedback_id FROM retrieval_feedback WHERE feedback_id = %s
            """,
            (feedback["feedback_id"],),
        )
        assert cur.fetchone() is not None
        print(f"✓ Feedback stored")

    print(f"\n" + "=" * 60)
    print(f"✅ E2E SCENARIO TEST PASSED")
    print(f"=" * 60)
    print(f"\nSummary:")
    print(f"  Task A: Executed successfully with outcome quality 0.95")
    print(f"  Learning: Pattern, insight, and artifact created from Task A")
    print(f"  Task B: Retrieved complete context from Task A")
    print(f"  Context: {context['summary']['total_items']} relevant items")
    print(f"  Feedback: Recorded usefulness for learning improvement")
    print(f"\nThis demonstrates:")
    print(f"  • Section 2: Task lifecycle (A)")
    print(f"  • Section 6: Learning outcome recording")
    print(f"  • Section 7: Knowledge graph and artifacts")
    print(f"  • Section 9: Automatic context retrieval for new task (B)")
    print(f"\n✓ All systems integrated and working together")

    return result


if __name__ == "__main__":
    import os

    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://user:password@localhost:5432/learning"
    )

    with psycopg.connect(DATABASE_URL) as conn:
        test_complete_scenario(conn)
