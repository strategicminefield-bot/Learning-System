"""
Section 10: Learning Application Layer
Converts retrieved learning into actionable execution guidance for attempts.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import uuid
import psycopg
from psycopg.extras import RealDictCursor


class ApplicationError(Exception):
    """Learning application error."""
    pass


class LearningApplicationEngine:
    """Apply retrieved learning to attempts and generate execution guidance."""

    def __init__(self, conn):
        self.conn = conn

    def apply_learning_to_attempt(
        self,
        attempt_id: str,
        task_id: str,
        node_id: str,
        retrieval_trace_id: Optional[str] = None,
        context_package_id: Optional[str] = None,
        override_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point: retrieve learning and apply to attempt.

        Args:
            attempt_id: Attempt UUID
            task_id: Task UUID
            node_id: Node UUID
            retrieval_trace_id: Optional pre-existing retrieval trace
            context_package_id: Optional pre-existing context package
            override_config: Optional configuration overrides

        Returns:
            Complete execution guidance with applied learning record.
        """
        guidance_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        try:
            # Validate attempt exists
            attempt = self._get_attempt(attempt_id)
            if not attempt:
                raise ApplicationError(f"Attempt {attempt_id} not found")

            # Load configuration
            config = self._get_application_config(override_config)

            # If no retrieval trace provided, retrieve learning now
            if not retrieval_trace_id or not context_package_id:
                from retrieval import ContextRetriever

                retriever = ContextRetriever(self.conn)
                result = retriever.query_task_context(task_id, node_id=node_id)
                retrieval_trace_id = result["trace_id"]
                context_package_id = result["package_id"]
                context = result["context"]
            else:
                # Load existing context
                context = self._get_context_package(context_package_id)

            # Select applicable learning from context
            start_time = datetime.now()

            applicable_learning = self._select_applicable_learning(
                context, config, task_id, node_id
            )

            # Create applied learning records
            applied_records = self._create_applied_learning_records(
                attempt_id, applicable_learning, retrieval_trace_id, context_package_id
            )

            # Create application decisions log
            decision_records = self._create_decision_records(attempt_id, applicable_learning, config)

            # Assemble execution guidance
            execution_guidance = self._assemble_execution_guidance(
                task_id, node_id, applicable_learning, context
            )

            # Record guidance
            guidance_record = self._record_execution_guidance(
                guidance_id,
                attempt_id,
                task_id,
                node_id,
                retrieval_trace_id,
                execution_guidance,
            )

            # Create guidance trace
            trace_data = {
                "retrieval_trace_id": retrieval_trace_id,
                "learning_items_considered": len(context.get("outcomes", []))
                + len(context.get("patterns", []))
                + len(context.get("insights", []))
                + len(context.get("artifacts", []))
                + len(context.get("graph_entities", [])),
                "learning_items_applied": len(applied_records),
                "learning_items_rejected": len(decision_records)
                - len(applied_records),
                "total_decisions": len(decision_records),
                "applied_decisions": len(applied_records),
                "rejected_decisions": len(decision_records) - len(applied_records),
                "generation_time_ms": int(
                    (datetime.now() - start_time).total_seconds() * 1000
                ),
                "total_guidance_size_bytes": len(json.dumps(execution_guidance)),
            }

            trace_id = self._record_guidance_trace(guidance_id, attempt_id, retrieval_trace_id, trace_data)

            return {
                "status": "success",
                "guidance_id": guidance_id,
                "attempt_id": attempt_id,
                "trace_id": trace_id,
                "context_package_id": context_package_id,
                "retrieval_trace_id": retrieval_trace_id,
                "guidance": execution_guidance,
                "applied_learning_count": len(applied_records),
                "statistics": {
                    "learning_considered": trace_data["learning_items_considered"],
                    "learning_applied": len(applied_records),
                    "generation_time_ms": trace_data["generation_time_ms"],
                },
            }

        except Exception as e:
            raise ApplicationError(f"Learning application failed: {str(e)}")

    def _get_attempt(self, attempt_id: str) -> Optional[Dict]:
        """Load attempt details."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT attempt_id, assignment_id, node_id, status, started_at
                FROM attempts WHERE attempt_id = %s
                """,
                (attempt_id,),
            )
            return cur.fetchone()

    def _get_application_config(self, override: Optional[Dict] = None) -> Dict:
        """Load application configuration with optional overrides."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT min_relevance_threshold, min_confidence_threshold,
                       min_applicability_score, apply_outcomes, apply_patterns,
                       apply_insights, apply_artifacts, apply_graph_entities,
                       include_warnings, include_constraints,
                       max_recommended_approaches, max_warnings, max_constraints,
                       handle_conflicting_learning, deduplicate_guidance
                FROM application_config LIMIT 1
                """
            )
            config = cur.fetchone()

        if not config:
            config = {
                "min_relevance_threshold": 0.6,
                "min_confidence_threshold": 0.6,
                "min_applicability_score": 0.5,
                "apply_outcomes": True,
                "apply_patterns": True,
                "apply_insights": True,
                "apply_artifacts": True,
                "apply_graph_entities": True,
                "include_warnings": True,
                "include_constraints": True,
                "max_recommended_approaches": 5,
                "max_warnings": 3,
                "max_constraints": 3,
                "handle_conflicting_learning": "present_both",
                "deduplicate_guidance": True,
            }

        if override:
            config.update(override)

        return config

    def _get_context_package(self, package_id: str) -> Dict:
        """Retrieve stored context package."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT context_data FROM context_packages WHERE package_id = %s
                """,
                (package_id,),
            )
            row = cur.fetchone()

        if not row:
            return {}

        return row["context_data"] or {}

    def _select_applicable_learning(
        self, context: Dict, config: Dict, task_id: str, node_id: str
    ) -> Dict[str, List[Dict]]:
        """
        Determine which retrieved learning items are applicable.

        Selectivity based on:
        - Relevance score threshold
        - Confidence threshold
        - Type applicability flags
        - Applicability scoring
        """
        applicable = {
            "outcomes": [],
            "patterns": [],
            "insights": [],
            "artifacts": [],
            "warnings": [],
            "constraints": [],
        }

        # Process outcomes
        if config["apply_outcomes"]:
            for outcome in context.get("outcomes", []):
                if (
                    outcome.get("relevance_score", 0) >= config["min_relevance_threshold"]
                    and outcome.get("quality_score", 0) >= config["min_applicability_score"]
                ):
                    applicable["outcomes"].append(outcome)

        # Process patterns
        if config["apply_patterns"]:
            for pattern in context.get("patterns", []):
                if (
                    pattern.get("relevance_score", 0) >= config["min_relevance_threshold"]
                    and pattern.get("success_rate", 0) >= config["min_applicability_score"]
                ):
                    applicable["patterns"].append(pattern)

        # Process insights
        if config["apply_insights"]:
            for insight in context.get("insights", []):
                if (
                    insight.get("relevance_score", 0) >= config["min_relevance_threshold"]
                    and insight.get("confidence_score", 0) >= config["min_confidence_threshold"]
                ):
                    # Classify as warning or recommendation
                    if insight.get("insight_type") in ["weakness", "warning", "failure"]:
                        if len(applicable["warnings"]) < config["max_warnings"]:
                            applicable["warnings"].append(insight)
                    else:
                        applicable["insights"].append(insight)

        # Process artifacts
        if config["apply_artifacts"]:
            for artifact in context.get("artifacts", []):
                if (
                    artifact.get("relevance_score", 0) >= config["min_relevance_threshold"]
                    and artifact.get("quality_score", 0) >= config["min_applicability_score"]
                ):
                    applicable["artifacts"].append(artifact)

        # Extract constraints from artifacts
        for artifact in applicable["artifacts"]:
            if artifact.get("artifact_type") == "constraint":
                if len(applicable["constraints"]) < config["max_constraints"]:
                    applicable["constraints"].append(artifact)

        return applicable

    def _create_applied_learning_records(
        self,
        attempt_id: str,
        applicable: Dict[str, List],
        retrieval_trace_id: str,
        context_package_id: str,
    ) -> List[str]:
        """Create applied_learning records for selected items."""
        applied_ids = []

        with self.conn.cursor() as cur:
            for category, items in applicable.items():
                if category in ["warnings", "constraints"]:
                    continue  # These are tracked differently

                for item in items:
                    applied_id = str(uuid.uuid4())

                    # Determine learning_id and type
                    if category == "outcomes":
                        learning_id = item.get("outcome_id")
                        learning_type = "outcome"
                    elif category == "patterns":
                        learning_id = item.get("pattern_id")
                        learning_type = "pattern"
                    elif category == "insights":
                        learning_id = item.get("insight_id")
                        learning_type = "insight"
                    elif category == "artifacts":
                        learning_id = item.get("artifact_id")
                        learning_type = "artifact"
                    else:
                        continue

                    # Find source outcome if available
                    source_outcome_id = None
                    if learning_type == "outcome":
                        source_outcome_id = learning_id

                    cur.execute(
                        """
                        INSERT INTO applied_learning
                        (applied_id, attempt_id, retrieval_trace_id, context_package_id,
                         learning_type, learning_id, relevance_score, confidence,
                         applicability_reason, source_outcome_id, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            applied_id,
                            attempt_id,
                            retrieval_trace_id,
                            context_package_id,
                            learning_type,
                            learning_id,
                            item.get("relevance_score", 0.5),
                            item.get("confidence_score", item.get("quality_score", 0.5)),
                            f"Selected {learning_type} with relevance {item.get('relevance_score', 0.5):.2f}",
                            source_outcome_id,
                            "applied",
                        ),
                    )

                    applied_ids.append(applied_id)

            self.conn.commit()

        return applied_ids

    def _create_decision_records(
        self, attempt_id: str, applicable: Dict[str, List], config: Dict
    ) -> List[str]:
        """Create application_decisions log."""
        decision_ids = []

        with self.conn.cursor() as cur:
            for category, items in applicable.items():
                if category in ["warnings", "constraints"]:
                    continue

                for item in items:
                    decision_id = str(uuid.uuid4())

                    if category == "outcomes":
                        learning_id = item.get("outcome_id")
                    elif category == "patterns":
                        learning_id = item.get("pattern_id")
                    elif category == "insights":
                        learning_id = item.get("insight_id")
                    elif category == "artifacts":
                        learning_id = item.get("artifact_id")
                    else:
                        continue

                    cur.execute(
                        """
                        INSERT INTO application_decisions
                        (decision_id, attempt_id, considered_learning_id, considered_type,
                         decision, reason, relevance_score, confidence_score)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            decision_id,
                            attempt_id,
                            learning_id,
                            category,
                            "applied",
                            f"Applied {category} item",
                            item.get("relevance_score", 0.5),
                            item.get("confidence_score", item.get("quality_score", 0.5)),
                        ),
                    )

                    decision_ids.append(decision_id)

            self.conn.commit()

        return decision_ids

    def _assemble_execution_guidance(
        self, task_id: str, node_id: str, applicable: Dict[str, List], context: Dict
    ) -> Dict[str, Any]:
        """
        Assemble structured execution guidance from applicable learning.

        Distinguished categories:
        - recommended_approaches: Methods to try
        - known_patterns: Discovered patterns to follow
        - warnings: Things to avoid or be careful with
        - constraints: Limitations to respect
        - insights: Performance recommendations
        - useful_knowledge: Templates and resources
        """
        guidance = {
            "task_id": task_id,
            "node_id": node_id,
            "generated_at": datetime.now().isoformat(),
            "recommended_approaches": [],
            "known_patterns": [],
            "warnings": [],
            "constraints": [],
            "insights": [],
            "useful_knowledge": [],
            "summary": {},
        }

        # Recommended approaches from successful outcomes
        for outcome in applicable.get("outcomes", [])[:3]:
            guidance["recommended_approaches"].append({
                "source": "successful_outcome",
                "quality": float(outcome.get("quality_score", 0)),
                "learning": outcome.get("learning_points", []),
                "result_summary": outcome.get("result_summary"),
            })

        # Known patterns
        for pattern in applicable.get("patterns", [])[:3]:
            guidance["known_patterns"].append({
                "pattern_name": pattern.get("pattern_name"),
                "success_rate": float(pattern.get("success_rate", 0)),
                "pattern_rule": pattern.get("pattern_rule"),
                "occurrences": pattern.get("occurrence_count", 0),
            })

        # Warnings and failure indicators
        for warning in applicable.get("warnings", [])[:3]:
            guidance["warnings"].append({
                "warning": warning.get("description"),
                "type": warning.get("insight_type"),
                "confidence": float(warning.get("confidence_score", 0)),
                "recommendation": warning.get("recommendation"),
            })

        # Constraints
        for constraint in applicable.get("constraints", [])[:3]:
            guidance["constraints"].append({
                "constraint": constraint.get("content"),
                "type": constraint.get("artifact_type"),
                "quality": float(constraint.get("quality_score", 0)),
            })

        # Insights and recommendations
        for insight in applicable.get("insights", [])[:3]:
            guidance["insights"].append({
                "insight": insight.get("description"),
                "type": insight.get("insight_type"),
                "confidence": float(insight.get("confidence_score", 0)),
                "recommendation": insight.get("recommendation"),
            })

        # Useful knowledge (templates, solutions, etc.)
        for artifact in applicable.get("artifacts", [])[:3]:
            guidance["useful_knowledge"].append({
                "artifact_type": artifact.get("artifact_type"),
                "content": artifact.get("content"),
                "quality": float(artifact.get("quality_score", 0)),
                "usage_count": artifact.get("usage_count", 0),
            })

        # Summary
        guidance["summary"] = {
            "approaches": len(guidance["recommended_approaches"]),
            "patterns": len(guidance["known_patterns"]),
            "warnings": len(guidance["warnings"]),
            "constraints": len(guidance["constraints"]),
            "insights": len(guidance["insights"]),
            "knowledge_items": len(guidance["useful_knowledge"]),
            "total_guidance_items": sum(
                len(v) for k, v in guidance.items() if isinstance(v, list)
            ),
        }

        return guidance

    def _record_execution_guidance(
        self,
        guidance_id: str,
        attempt_id: str,
        task_id: str,
        node_id: str,
        retrieval_trace_id: str,
        guidance: Dict,
    ) -> Dict:
        """Record execution guidance for attempt."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_guidance
                (guidance_id, attempt_id, task_id, node_id,
                 retrieval_trace_id, guidance_data, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    guidance_id,
                    attempt_id,
                    task_id,
                    node_id,
                    retrieval_trace_id,
                    json.dumps(guidance),
                    datetime.now(),
                ),
            )
            self.conn.commit()

        return {"guidance_id": guidance_id, "status": "recorded"}

    def _record_guidance_trace(
        self,
        guidance_id: str,
        attempt_id: str,
        retrieval_trace_id: str,
        trace_data: Dict,
    ) -> str:
        """Record guidance generation trace."""
        trace_id = str(uuid.uuid4())

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO guidance_traces
                (trace_id, guidance_id, attempt_id, retrieval_trace_id,
                 learning_items_considered, learning_items_applied,
                 learning_items_rejected, total_decisions,
                 applied_decisions, rejected_decisions,
                 generation_time_ms, total_guidance_size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    guidance_id,
                    attempt_id,
                    retrieval_trace_id,
                    trace_data.get("learning_items_considered", 0),
                    trace_data.get("learning_items_applied", 0),
                    trace_data.get("learning_items_rejected", 0),
                    trace_data.get("total_decisions", 0),
                    trace_data.get("applied_decisions", 0),
                    trace_data.get("rejected_decisions", 0),
                    trace_data.get("generation_time_ms", 0),
                    trace_data.get("total_guidance_size_bytes", 0),
                ),
            )
            self.conn.commit()

        return trace_id

    def get_execution_guidance(self, attempt_id: str) -> Dict[str, Any]:
        """Retrieve execution guidance for an attempt."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT guidance_id, attempt_id, task_id, node_id,
                       guidance_data, generated_at, created_at
                FROM execution_guidance WHERE attempt_id = %s
                """,
                (attempt_id,),
            )
            row = cur.fetchone()

        if not row:
            return {}

        return {
            "guidance_id": row["guidance_id"],
            "attempt_id": row["attempt_id"],
            "task_id": row["task_id"],
            "node_id": row["node_id"],
            "guidance": row["guidance_data"],
            "generated_at": str(row["generated_at"]),
        }

    def get_applied_learning(self, attempt_id: str) -> List[Dict]:
        """Get all learning applied to an attempt."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT applied_id, learning_type, learning_id,
                       relevance_score, confidence, applicability_reason,
                       source_outcome_id, status, applied_at
                FROM applied_learning
                WHERE attempt_id = %s
                ORDER BY applied_at
                """,
                (attempt_id,),
            )
            return [dict(row) for row in cur.fetchall()]
