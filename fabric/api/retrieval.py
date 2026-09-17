"""
Section 9: Retrieval & Context Layer
Task-aware memory and learning retrieval with structured context assembly.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


class RetrieverError(Exception):
    """Retrieval operation error."""
    pass


class ContextRetriever:
    """Retrieve and assemble learning context for task execution."""

    def __init__(self, conn):
        self.conn = conn

    def query_task_context(
        self,
        task_id: str,
        node_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        limit_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point: retrieve all relevant learning for a task.

        Args:
            task_id: Task UUID to build context for
            node_id: Optional node requesting context
            assignment_id: Optional assignment context
            limit_config: Optional override limits {max_outcomes, max_patterns, ...}

        Returns:
            Complete context package with structured learning and provenance.
        """
        trace_id = str(uuid.uuid4())
        query_id = str(uuid.uuid4())

        try:
            # Load task and retrieval config
            task = self._get_task(task_id)
            if not task:
                raise RetrieverError(f"Task {task_id} not found")

            config = self._get_retrieval_config(limit_config)

            # Create query record
            query_params = {
                "task_id": task_id,
                "task_type": task.get("task_type"),
                "node_id": node_id,
                "specification": task.get("specification"),
            }
            self._record_query(query_id, task_id, node_id, assignment_id, query_params)

            # Multi-source retrieval
            start_time = datetime.now()

            outcomes = self._retrieve_outcomes(task_id, task, config, node_id)
            patterns = self._retrieve_patterns(task, config)
            insights = self._retrieve_insights(task, config, node_id)
            artifacts = self._retrieve_artifacts(task, config)
            graph_entities = self._retrieve_graph_relationships(task, artifacts, config)

            # Deduplication
            all_items = []
            all_items.extend([("outcome", o) for o in outcomes])
            all_items.extend([("pattern", p) for p in patterns])
            all_items.extend([("insight", i) for i in insights])
            all_items.extend([("artifact", a) for a in artifacts])
            all_items.extend([("graph_entity", g) for g in graph_entities])

            deduplicated_items, dedup_count = self._deduplicate_items(all_items)

            # Apply final size/count limits
            final_items = self._apply_size_limits(deduplicated_items, config)

            # Record trace
            trace_data = {
                "outcomes_considered": len(outcomes),
                "patterns_considered": len(patterns),
                "insights_considered": len(insights),
                "artifacts_considered": len(artifacts),
                "graph_entities_considered": len(graph_entities),
                "outcomes_selected": sum(1 for t, _ in final_items if t == "outcome"),
                "patterns_selected": sum(1 for t, _ in final_items if t == "pattern"),
                "insights_selected": sum(1 for t, _ in final_items if t == "insight"),
                "artifacts_selected": sum(1 for t, _ in final_items if t == "artifact"),
                "graph_entities_selected": sum(1 for t, _ in final_items if t == "graph_entity"),
                "total_items_returned": len(final_items),
                "deduplication_count": dedup_count,
                "execution_time_ms": int((datetime.now() - start_time).total_seconds() * 1000),
            }

            trace_id = self._record_trace(query_id, trace_data)

            # Record individual items with provenance
            retrieved_items = []
            for item_type, item_data in final_items:
                item_record = self._record_retrieved_item(trace_id, item_type, item_data)
                retrieved_items.append(item_record)

            # Assemble context package
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            context = self._assemble_context_package(
                trace_id, task_id, node_id, retrieved_items, execution_time
            )

            # Record context package
            package_id = self._record_context_package(
                trace_id, task_id, node_id, context, execution_time
            )

            return {
                "status": "success",
                "package_id": package_id,
                "trace_id": trace_id,
                "query_id": query_id,
                "task_id": task_id,
                "context": context,
                "retrieval_stats": {
                    "total_items": len(final_items),
                    "deduplication_count": dedup_count,
                    "execution_time_ms": execution_time,
                },
            }

        except Exception as e:
            # Record error trace
            self._record_trace(query_id, {"trace_status": "error", "trace_error": str(e)})
            raise RetrieverError(f"Context retrieval failed: {str(e)}")

    def _get_task(self, task_id: str) -> Optional[Dict]:
        """Load task details."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT task_id, workflow_id, task_type, specification, 
                       status, created_at
                FROM tasks WHERE task_id = %s
                """,
                (task_id,),
            )
            return cur.fetchone()

    def _get_retrieval_config(self, override: Optional[Dict] = None) -> Dict:
        """Load retrieval configuration with optional overrides."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT max_outcomes, max_patterns, max_insights, max_artifacts,
                       max_graph_entities, min_outcome_confidence, min_pattern_success_rate,
                       min_insight_confidence, min_artifact_quality, max_total_items,
                       max_context_size_bytes, max_age_days, deduplicate_by_source
                FROM retrieval_config LIMIT 1
                """
            )
            config = cur.fetchone()

        if not config:
            config = {
                "max_outcomes": 5,
                "max_patterns": 3,
                "max_insights": 3,
                "max_artifacts": 5,
                "max_graph_entities": 10,
                "min_outcome_confidence": 0.5,
                "min_pattern_success_rate": 0.6,
                "min_insight_confidence": 0.5,
                "min_artifact_quality": 0.5,
                "max_total_items": 25,
                "max_context_size_bytes": 1000000,
                "max_age_days": 90,
                "deduplicate_by_source": True,
            }

        # Apply overrides
        if override:
            config.update(override)

        return config

    def _retrieve_outcomes(
        self, task_id: str, task: Dict, config: Dict, node_id: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve relevant prior outcomes for task type."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query outcomes by task type and quality, with recency weighting
            cutoff_date = datetime.now() - timedelta(days=config["max_age_days"])

            query = """
                SELECT outcome_id, task_id, assignment_id, node_id, 
                       outcome_status, quality_score, execution_time_seconds,
                       result_summary, learning_points, patterns_matched,
                       created_at,
                       EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 86400 as age_days,
                       quality_score as relevance_score
                FROM task_outcomes
                WHERE task_type = %s
                  AND quality_score >= %s
                  AND created_at >= %s
                  AND outcome_status IN ('success', 'partial')
                ORDER BY quality_score DESC, created_at DESC
                LIMIT %s
            """

            cur.execute(
                query,
                (
                    task.get("task_type"),
                    config["min_outcome_confidence"],
                    cutoff_date,
                    config["max_outcomes"],
                ),
            )
            return [dict(row) for row in cur.fetchall()]

    def _retrieve_patterns(self, task: Dict, config: Dict) -> List[Dict]:
        """Retrieve patterns discovered for task type."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT pattern_id, task_type, pattern_name, pattern_rule,
                       success_rate, occurrence_count, first_seen, last_seen,
                       success_rate as relevance_score
                FROM result_patterns
                WHERE task_type = %s
                  AND success_rate >= %s
                ORDER BY success_rate DESC, occurrence_count DESC
                LIMIT %s
            """

            cur.execute(
                query,
                (
                    task.get("task_type"),
                    config["min_pattern_success_rate"],
                    config["max_patterns"],
                ),
            )
            return [dict(row) for row in cur.fetchall()]

    def _retrieve_insights(
        self, task: Dict, config: Dict, node_id: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve performance insights for task type and optionally node."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            if node_id:
                query = """
                    SELECT insight_id, node_id, task_type, insight_type,
                           description, recommendation, confidence_score,
                           evidence_count, actionable, created_at,
                           confidence_score as relevance_score
                    FROM performance_insights
                    WHERE (node_id = %s OR node_id IS NULL)
                      AND task_type = %s
                      AND confidence_score >= %s
                      AND actionable = TRUE
                    ORDER BY confidence_score DESC, evidence_count DESC
                    LIMIT %s
                """

                cur.execute(
                    query,
                    (
                        node_id,
                        task.get("task_type"),
                        config["min_insight_confidence"],
                        config["max_insights"],
                    ),
                )
            else:
                query = """
                    SELECT insight_id, node_id, task_type, insight_type,
                           description, recommendation, confidence_score,
                           evidence_count, actionable, created_at,
                           confidence_score as relevance_score
                    FROM performance_insights
                    WHERE node_id IS NULL
                      AND task_type = %s
                      AND confidence_score >= %s
                      AND actionable = TRUE
                    ORDER BY confidence_score DESC, evidence_count DESC
                    LIMIT %s
                """

                cur.execute(
                    query,
                    (
                        task.get("task_type"),
                        config["min_insight_confidence"],
                        config["max_insights"],
                    ),
                )

            return [dict(row) for row in cur.fetchall()]

    def _retrieve_artifacts(self, task: Dict, config: Dict) -> List[Dict]:
        """Retrieve knowledge artifacts relevant to task type."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Try direct task type mapping first
            query = """
                SELECT ka.artifact_id, ka.task_type, ka.artifact_type,
                       ka.content, ka.quality_score, ka.usage_count,
                       ka.effectiveness_rating, ka.created_at,
                       ka.quality_score as relevance_score
                FROM knowledge_artifacts ka
                WHERE ka.task_type = %s
                  AND ka.quality_score >= %s
                ORDER BY ka.quality_score DESC, ka.usage_count DESC
                LIMIT %s
            """

            cur.execute(
                query,
                (
                    task.get("task_type"),
                    config["min_artifact_quality"],
                    config["max_artifacts"],
                ),
            )
            return [dict(row) for row in cur.fetchall()]

    def _retrieve_graph_relationships(
        self, task: Dict, artifacts: List[Dict], config: Dict
    ) -> List[Dict]:
        """Retrieve related artifacts through knowledge graph."""
        if not artifacts:
            return []

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            artifact_ids = [a["artifact_id"] for a in artifacts]

            # Find related artifacts through graph edges
            query = """
                SELECT DISTINCT ka.artifact_id, ka.task_type, ka.artifact_type,
                       ka.content, ka.quality_score, ka.usage_count,
                       ka.effectiveness_rating, ka.created_at,
                       kr.strength as relationship_strength,
                       (ka.quality_score * kr.strength) as relevance_score
                FROM knowledge_relationships kr
                JOIN knowledge_artifacts ka ON 
                    (kr.source_artifact_id = ka.artifact_id AND kr.target_artifact_id = ANY(%s))
                    OR (kr.target_artifact_id = ka.artifact_id AND kr.source_artifact_id = ANY(%s))
                WHERE kr.strength > 0
                  AND ka.quality_score >= %s
                ORDER BY relevance_score DESC
                LIMIT %s
            """

            cur.execute(
                query,
                (
                    artifact_ids,
                    artifact_ids,
                    config["min_artifact_quality"],
                    config["max_graph_entities"],
                ),
            )
            return [dict(row) for row in cur.fetchall()]

    def _deduplicate_items(
        self, items: List[Tuple[str, Dict]]
    ) -> Tuple[List[Tuple[str, Dict]], int]:
        """Remove duplicate items preserving source tracking."""
        seen = {}
        deduplicated = []
        dedup_count = 0

        for item_type, item_data in items:
            source_id = item_data.get("artifact_id") or item_data.get(
                "outcome_id"
            ) or item_data.get("pattern_id") or item_data.get("insight_id")

            key = f"{item_type}:{source_id}"

            if key not in seen:
                seen[key] = (item_type, item_data)
                deduplicated.append((item_type, item_data))
            else:
                dedup_count += 1

        return deduplicated, dedup_count

    def _apply_size_limits(
        self, items: List[Tuple[str, Dict]], config: Dict
    ) -> List[Tuple[str, Dict]]:
        """Apply total count and size limits."""
        # Sort by relevance score
        sorted_items = sorted(
            items, key=lambda x: x[1].get("relevance_score", 0), reverse=True
        )

        # Apply count limit
        limited = sorted_items[: config["max_total_items"]]

        # Apply size limit
        total_size = 0
        final = []
        for item_type, item_data in limited:
            item_size = len(json.dumps(item_data))
            if total_size + item_size <= config["max_context_size_bytes"]:
                final.append((item_type, item_data))
                total_size += item_size
            else:
                break

        return final

    def _record_query(
        self,
        query_id: str,
        task_id: str,
        node_id: Optional[str],
        assignment_id: Optional[str],
        params: Dict,
    ) -> None:
        """Record retrieval query."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_queries 
                (query_id, task_id, node_id, assignment_id, query_params)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (query_id, task_id, node_id, assignment_id, json.dumps(params)),
            )
            self.conn.commit()

    def _record_trace(self, query_id: str, trace_data: Dict) -> str:
        """Record retrieval trace."""
        trace_id = str(uuid.uuid4())

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_traces
                (trace_id, query_id, outcomes_considered, patterns_considered,
                 insights_considered, artifacts_considered, graph_entities_considered,
                 outcomes_selected, patterns_selected, insights_selected,
                 artifacts_selected, graph_entities_selected, total_items_returned,
                 deduplication_count, execution_time_ms, trace_status, trace_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    query_id,
                    trace_data.get("outcomes_considered", 0),
                    trace_data.get("patterns_considered", 0),
                    trace_data.get("insights_considered", 0),
                    trace_data.get("artifacts_considered", 0),
                    trace_data.get("graph_entities_considered", 0),
                    trace_data.get("outcomes_selected", 0),
                    trace_data.get("patterns_selected", 0),
                    trace_data.get("insights_selected", 0),
                    trace_data.get("artifacts_selected", 0),
                    trace_data.get("graph_entities_selected", 0),
                    trace_data.get("total_items_returned", 0),
                    trace_data.get("deduplication_count", 0),
                    trace_data.get("execution_time_ms", 0),
                    trace_data.get("trace_status", "complete"),
                    trace_data.get("trace_error"),
                ),
            )
            self.conn.commit()

        return trace_id

    def _record_retrieved_item(self, trace_id: str, item_type: str, item_data: Dict) -> Dict:
        """Record individual retrieved item."""
        item_id = str(uuid.uuid4())
        source_id = item_data.get("artifact_id") or item_data.get("outcome_id") or item_data.get("pattern_id") or item_data.get("insight_id")

        provenance_id = None
        if item_type == "outcome" and "outcome_id" in item_data:
            # Link to learning provenance if it exists
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT provenance_id FROM learning_provenance
                    WHERE source_type = 'outcome' AND source_id = %s
                    LIMIT 1
                    """,
                    (item_data["outcome_id"],),
                )
                prov = cur.fetchone()
                if prov:
                    provenance_id = prov["provenance_id"]

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieved_items
                (item_id, trace_id, source_type, source_id, provenance_id,
                 relevance_score, ranking_factors, item_metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item_id,
                    trace_id,
                    item_type,
                    source_id,
                    provenance_id,
                    item_data.get("relevance_score", 0.5),
                    json.dumps({"source": item_type, "scored": True}),
                    json.dumps({k: v for k, v in item_data.items() if k != "relevance_score"}),
                ),
            )
            self.conn.commit()

        return {
            "item_id": item_id,
            "trace_id": trace_id,
            "source_type": item_type,
            "source_id": source_id,
            "relevance_score": item_data.get("relevance_score", 0.5),
            "data": item_data,
        }

    def _assemble_context_package(
        self, trace_id: str, task_id: str, node_id: Optional[str], items: List[Dict], exec_time: int
    ) -> Dict:
        """Assemble structured context for task execution."""
        outcomes = []
        patterns = []
        insights = []
        artifacts = []
        graph_entities = []
        provenance_map = {}

        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            for item in items:
                source_type = item["source_type"]
                item_data = item["data"]

                if source_type == "outcome":
                    outcomes.append({
                        "outcome_id": item_data.get("outcome_id"),
                        "status": item_data.get("outcome_status"),
                        "quality_score": float(item_data.get("quality_score", 0)),
                        "execution_time_seconds": item_data.get("execution_time_seconds"),
                        "result_summary": item_data.get("result_summary"),
                        "learning_points": item_data.get("learning_points"),
                        "relevance_score": float(item_data.get("relevance_score", 0)),
                    })

                elif source_type == "pattern":
                    patterns.append({
                        "pattern_id": item_data.get("pattern_id"),
                        "pattern_name": item_data.get("pattern_name"),
                        "pattern_rule": item_data.get("pattern_rule"),
                        "success_rate": float(item_data.get("success_rate", 0)),
                        "occurrence_count": item_data.get("occurrence_count"),
                        "relevance_score": float(item_data.get("relevance_score", 0)),
                    })

                elif source_type == "insight":
                    insights.append({
                        "insight_id": item_data.get("insight_id"),
                        "insight_type": item_data.get("insight_type"),
                        "description": item_data.get("description"),
                        "recommendation": item_data.get("recommendation"),
                        "confidence_score": float(item_data.get("confidence_score", 0)),
                        "relevance_score": float(item_data.get("relevance_score", 0)),
                    })

                elif source_type == "artifact":
                    artifacts.append({
                        "artifact_id": item_data.get("artifact_id"),
                        "artifact_type": item_data.get("artifact_type"),
                        "content": item_data.get("content"),
                        "quality_score": float(item_data.get("quality_score", 0)),
                        "usage_count": item_data.get("usage_count"),
                        "relevance_score": float(item_data.get("relevance_score", 0)),
                    })

                elif source_type == "graph_entity":
                    graph_entities.append({
                        "artifact_id": item_data.get("artifact_id"),
                        "artifact_type": item_data.get("artifact_type"),
                        "content": item_data.get("content"),
                        "relationship_strength": float(item_data.get("relationship_strength", 0)),
                        "relevance_score": float(item_data.get("relevance_score", 0)),
                    })

        context = {
            "trace_id": trace_id,
            "task_id": task_id,
            "node_id": node_id,
            "assembly_time_ms": exec_time,
            "outcomes": outcomes,
            "patterns": patterns,
            "insights": insights,
            "artifacts": artifacts,
            "graph_entities": graph_entities,
            "summary": {
                "total_items": len(items),
                "outcome_count": len(outcomes),
                "pattern_count": len(patterns),
                "insight_count": len(insights),
                "artifact_count": len(artifacts),
                "graph_entity_count": len(graph_entities),
            },
        }

        return context

    def _record_context_package(
        self, trace_id: str, task_id: str, node_id: Optional[str], context: Dict, exec_time: int
    ) -> str:
        """Record assembled context package."""
        package_id = str(uuid.uuid4())
        context_bytes = len(json.dumps(context))

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO context_packages
                (package_id, trace_id, task_id, node_id, context_data, 
                 context_size_bytes, item_count, assembly_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    package_id,
                    trace_id,
                    task_id,
                    node_id,
                    json.dumps(context),
                    context_bytes,
                    context.get("summary", {}).get("total_items", 0),
                    exec_time,
                ),
            )
            self.conn.commit()

        return package_id

    def record_retrieval_feedback(
        self,
        package_id: str,
        node_id: str,
        usefulness_score: float,
        used_items: Optional[List[str]] = None,
        assignment_id: Optional[str] = None,
        outcome_id: Optional[str] = None,
        feedback_text: Optional[str] = None,
    ) -> Dict:
        """Record feedback on retrieval usefulness for learning."""
        feedback_id = str(uuid.uuid4())

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO retrieval_feedback
                (feedback_id, package_id, node_id, usefulness_score, used_items,
                 assignment_id, outcome_id, feedback_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    feedback_id,
                    package_id,
                    node_id,
                    usefulness_score,
                    json.dumps(used_items or []),
                    assignment_id,
                    outcome_id,
                    feedback_text,
                ),
            )
            self.conn.commit()

        return {
            "feedback_id": feedback_id,
            "package_id": package_id,
            "node_id": node_id,
            "usefulness_score": usefulness_score,
            "status": "recorded",
        }
