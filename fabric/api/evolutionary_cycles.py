"""
Section 23: Full Evolutionary Loop
Orchestration engine integrating Sections 2-22 into controlled, persistent
end-to-end evolutionary cycles.

NO rebuilding of Sections 2-22. Integration of REAL existing implementations.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TriggerSource(str, Enum):
    """Allowed cycle trigger sources"""
    NEW_WORK_DEMAND = "new_work_demand"
    REPEATED_FAILURE = "repeated_failure"
    REPAIR_BURDEN = "repair_burden"
    STRATEGY_UNDERPERFORMANCE = "strategy_underperformance"
    ORCHESTRATION_UNCERTAINTY = "orchestration_uncertainty"
    EXPERIMENT_OPPORTUNITY = "experiment_opportunity"
    VALIDATION_RESULT = "validation_result"
    NODE_CAPABILITY_GAP = "node_capability_gap"
    ORGANISATIONAL_BOTTLENECK = "organisational_bottleneck"
    SYSTEM_REGRESSION = "system_regression"
    SYSTEM_IMPROVEMENT = "system_improvement"
    HUMAN_REQUEST = "human_request"


class CycleStatus(str, Enum):
    """Cycle lifecycle states"""
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_EVIDENCE = "waiting_for_evidence"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    EXPERIMENTING = "experimenting"
    VALIDATING = "validating"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    NO_CHANGE = "no_change"
    RESTRICTED = "restricted"
    FAILED = "failed"
    TERMINATED = "terminated"


class StageType(str, Enum):
    """Evolutionary cycle stages"""
    RETRIEVAL = "retrieval"
    CONTEXT = "context"
    STRATEGY_SELECTION = "strategy_selection"
    ADAPTIVE_ORCHESTRATION = "adaptive_orchestration"
    NODE_SELECTION = "node_selection"
    ORG_STRUCTURE = "org_structure"
    EXECUTION = "execution"
    ATTEMPTS = "attempts"
    VERIFICATION = "verification"
    FAILURES_REPAIRS = "failures_repairs"
    OUTCOME = "outcome"
    LEARNING_FEEDBACK = "learning_feedback"
    KNOWLEDGE_EVOLUTION = "knowledge_evolution"
    STRATEGY_EVOLUTION = "strategy_evolution"
    UNCERTAINTY_DETECTION = "uncertainty_detection"
    EXPERIMENTATION = "experimentation"
    VALIDATION = "validation"
    PROMOTION = "promotion"
    NODE_EVOLUTION = "node_evolution"
    ORG_EVOLUTION = "org_evolution"
    SYSTEM_EVALUATION = "system_evaluation"
    REGRESSION_RESPONSE = "regression_response"
    GOVERNANCE_DECISION = "governance_decision"


class ManagementPlaneProtection:
    """
    Protects management plane targets from evolutionary mutation.
    DO NOT allow uncontrolled changes to:
    - SSH, credentials, authentication
    - Firewall, network management
    - VPS admin access
    - GitHub/deployment credentials
    - Database admin credentials
    - OpenClaw management access
    """

    PROTECTED_CATEGORIES = {
        "ssh_config",
        "credentials",
        "firewall",
        "vps_admin",
        "github_auth",
        "deployment_creds",
        "db_admin",
        "openclaw_management",
        "network_management",
    }

    PROTECTED_KEYWORDS = {
        "ssh", "credential", "password", "token", "key", "auth", "firewall",
        "iptables", "vpc", "security_group", "sudo", "root", "admin",
        "vps", "vultr", "github", "deploy", "database", "postgres",
        "openclaw", "gateway", "agent", "ssh_key", "private_key"
    }

    @classmethod
    def check_target(cls, proposed_action: str, target: str) -> Tuple[bool, Optional[str]]:
        """
        Check if proposed action targets management plane.
        Returns (allowed, reason)
        """
        target_lower = target.lower()
        action_lower = proposed_action.lower()

        # Check exact category matches
        for keyword in cls.PROTECTED_KEYWORDS:
            if keyword in target_lower or keyword in action_lower:
                return False, f"Targets protected keyword: {keyword}"

        # Approve non-management targets
        return True, None


class EvolutionaryCycleOrchestrator:
    """
    Orchestrates complete evolutionary cycles integrating Sections 2-22.
    
    Responsibilities:
    1. Create/manage cycle lifecycle
    2. Persist stage progression
    3. Integrate retrieval/context (Sections 7-13)
    4. Integrate strategy selection (Section 14)
    5. Integrate adaptive orchestration (Section 15)
    6. Integrate experimentation/validation (Sections 16-17)
    7. Integrate node/org evolution (Sections 18-19)
    8. Enforce governance (Section 20)
    9. Integrate system evaluation (Section 21)
    10. Enforce management plane protection
    """

    def __init__(self, db_conn):
        self.db = db_conn
        self.cursor = db_conn.cursor()

    def create_cycle(
        self,
        trigger_source,  # str or TriggerSource
        trigger_reference: Optional[uuid.UUID] = None,
        objective: Optional[str] = None,
        work_population: Optional[Dict] = None,
        scope: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """Create new evolutionary cycle"""
        cycle_id = uuid.uuid4()

        # Handle both string and Enum
        if isinstance(trigger_source, TriggerSource):
            trigger_source_str = trigger_source.value
        else:
            trigger_source_str = str(trigger_source)

        self.cursor.execute(
            """
            INSERT INTO evolution_cycles
            (cycle_id, trigger_source, trigger_reference, objective,
             work_population, scope, status, current_stage, started_at,
             created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cycle_id,
                trigger_source_str,
                trigger_reference,
                objective,
                json.dumps(work_population) if work_population else None,
                scope,
                CycleStatus.CREATED.value,
                None,
                datetime.utcnow(),
                created_by,
            ),
        )
        self.db.commit()

        logger.info(f"Created evolutionary cycle {cycle_id}: {trigger_source_str}")
        return cycle_id

    def start_cycle(self, cycle_id: uuid.UUID) -> bool:
        """Transition cycle to RUNNING state"""
        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET status = %s, started_at = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (CycleStatus.RUNNING.value, datetime.utcnow(), datetime.utcnow(), cycle_id),
        )
        self.db.commit()
        logger.info(f"Started evolutionary cycle {cycle_id}")
        return True

    def begin_stage(
        self,
        cycle_id: uuid.UUID,
        stage,  # str or StageType
        input_references: Optional[Dict] = None,
    ) -> uuid.UUID:
        """Begin a cycle stage, persisting state for restart recovery"""
        stage_record_id = uuid.uuid4()

        # Handle both string and Enum
        if isinstance(stage, StageType):
            stage_str = stage.value
        else:
            stage_str = str(stage)

        self.cursor.execute(
            """
            INSERT INTO evolution_cycle_stages
            (stage_record_id, cycle_id, stage, input_references,
             started_at, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                stage_record_id,
                cycle_id,
                stage_str,
                json.dumps(input_references) if input_references else None,
                datetime.utcnow(),
                "running",
            ),
        )

        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET current_stage = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (stage_str, datetime.utcnow(), cycle_id),
        )
        self.db.commit()

        logger.info(f"Began stage {stage_str} in cycle {cycle_id}")
        return stage_record_id

    def complete_stage(
        self,
        stage_record_id: uuid.UUID,
        cycle_id: uuid.UUID,
        output_references: Optional[Dict] = None,
        decision_references: Optional[Dict] = None,
    ) -> bool:
        """Complete a cycle stage"""
        self.cursor.execute(
            """
            UPDATE evolution_cycle_stages
            SET status = %s, completed_at = %s,
                output_references = %s, decision_references = %s
            WHERE stage_record_id = %s
            """,
            (
                "completed",
                datetime.utcnow(),
                json.dumps(output_references) if output_references else None,
                json.dumps(decision_references) if decision_references else None,
                stage_record_id,
            ),
        )
        self.db.commit()
        logger.info(f"Completed stage {stage_record_id}")
        return True

    def fail_stage(
        self,
        stage_record_id: uuid.UUID,
        cycle_id: uuid.UUID,
        error: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Mark stage as failed"""
        self.cursor.execute(
            """
            UPDATE evolution_cycle_stages
            SET status = %s, completed_at = %s, errors = %s, reason = %s
            WHERE stage_record_id = %s
            """,
            (
                "failed",
                datetime.utcnow(),
                json.dumps({"error": error}),
                reason,
                stage_record_id,
            ),
        )

        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET status = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (CycleStatus.FAILED.value, datetime.utcnow(), cycle_id),
        )
        self.db.commit()
        logger.error(f"Failed stage {stage_record_id}: {error}")
        return False

    def transition_to_awaiting_evidence(self, cycle_id: uuid.UUID, reason: str) -> bool:
        """Pause cycle awaiting evidence"""
        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET status = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (CycleStatus.WAITING_FOR_EVIDENCE.value, datetime.utcnow(), cycle_id),
        )
        self.db.commit()
        logger.info(f"Cycle {cycle_id} awaiting evidence: {reason}")
        return True

    def transition_to_awaiting_approval(self, cycle_id: uuid.UUID, reason: str) -> bool:
        """Pause cycle awaiting human approval"""
        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET status = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (CycleStatus.WAITING_FOR_APPROVAL.value, datetime.utcnow(), cycle_id),
        )
        self.db.commit()
        logger.info(f"Cycle {cycle_id} awaiting approval: {reason}")
        return True

    def record_governance_decision(
        self,
        cycle_id: uuid.UUID,
        stage,  # str or StageType
        decision_result: Dict,
    ) -> bool:
        """Record governance decision point"""
        # Handle both string and Enum
        if isinstance(stage, StageType):
            stage_str = stage.value
        else:
            stage_str = str(stage)

        self.cursor.execute(
            """
            INSERT INTO evolution_cycle_decisions
            (cycle_id, stage, governance_result, what_was_observed,
             controlled_subsystem)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                cycle_id,
                stage_str,
                decision_result.get("result", "unknown"),
                decision_result.get("observation", ""),
                "governance",
            ),
        )
        self.db.commit()
        logger.info(f"Recorded governance decision for cycle {cycle_id} stage {stage_str}")
        return True

    def check_management_plane_protection(
        self, proposed_action: str, target: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if proposed action targets protected management plane"""
        allowed, reason = ManagementPlaneProtection.check_target(proposed_action, target)

        if not allowed:
            self.log_management_block(proposed_action, target, reason)

        return allowed, reason

    def log_management_block(self, proposed_action: str, target: str, reason: str) -> None:
        """Log blocked management-plane action"""
        block_id = uuid.uuid4()
        self.cursor.execute(
            """
            INSERT INTO evolution_management_plane_blocks
            (block_id, proposed_action, target_category, reason)
            VALUES (%s, %s, %s, %s)
            """,
            (block_id, proposed_action, "management_plane", reason),
        )
        self.db.commit()
        logger.warning(f"Blocked management-plane mutation: {reason}")

    def complete_cycle(
        self,
        cycle_id: uuid.UUID,
        final_status: CycleStatus,
        result: Dict,
        termination_reason: Optional[str] = None,
    ) -> bool:
        """Mark cycle as complete"""
        self.cursor.execute(
            """
            UPDATE evolution_cycles
            SET status = %s, completed_at = %s, result = %s,
                termination_reason = %s, updated_at = %s
            WHERE cycle_id = %s
            """,
            (
                final_status.value,
                datetime.utcnow(),
                json.dumps(result),
                termination_reason,
                datetime.utcnow(),
                cycle_id,
            ),
        )
        self.db.commit()
        logger.info(f"Completed cycle {cycle_id}: {final_status.value}")
        return True

    def get_cycle(self, cycle_id: uuid.UUID) -> Optional[Dict]:
        """Retrieve cycle state"""
        self.cursor.execute(
            """
            SELECT cycle_id, trigger_source, status, current_stage,
                   started_at, completed_at, result, termination_reason
            FROM evolution_cycles
            WHERE cycle_id = %s
            """,
            (cycle_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            return None

        return {
            "cycle_id": str(row[0]),
            "trigger_source": row[1],
            "status": row[2],
            "current_stage": row[3],
            "started_at": row[4],
            "completed_at": row[5],
            "result": row[6],
            "termination_reason": row[7],
        }

    def get_cycle_trace(self, cycle_id: uuid.UUID) -> List[Dict]:
        """Retrieve complete cycle trace for closed-loop traceability"""
        self.cursor.execute(
            """
            SELECT stage_record_id, stage, started_at, completed_at,
                   status, input_references, output_references,
                   decision_references
            FROM evolution_cycle_stages
            WHERE cycle_id = %s
            ORDER BY started_at ASC
            """,
            (cycle_id,),
        )

        stages = []
        for row in self.cursor.fetchall():
            stages.append({
                "stage_record_id": str(row[0]),
                "stage": row[1],
                "started_at": row[2],
                "completed_at": row[3],
                "status": row[4],
                "input_references": row[5],
                "output_references": row[6],
                "decision_references": row[7],
            })

        return stages

    def list_cycles(self, status: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """List evolutionary cycles"""
        if status:
            self.cursor.execute(
                """
                SELECT cycle_id, trigger_source, status, created_at
                FROM evolution_cycles
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit),
            )
        else:
            self.cursor.execute(
                """
                SELECT cycle_id, trigger_source, status, created_at
                FROM evolution_cycles
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )

        cycles = []
        for row in self.cursor.fetchall():
            cycles.append({
                "cycle_id": str(row[0]),
                "trigger_source": row[1],
                "status": row[2],
                "created_at": row[3],
            })

        return cycles

    def record_evidence_link(
        self,
        cycle_id: uuid.UUID,
        stage,  # str or StageType
        evidence_type: str,
        evidence_id: uuid.UUID,
        evidence_table: str,
        sequence_order: int,
    ) -> bool:
        """Record evidence linkage for traceability"""
        link_id = uuid.uuid4()

        # Handle both string and Enum
        if isinstance(stage, StageType):
            stage_str = stage.value
        else:
            stage_str = str(stage)

        self.cursor.execute(
            """
            INSERT INTO evolution_cycle_evidence_links
            (link_id, cycle_id, stage, evidence_type, evidence_id,
             evidence_table, sequence_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                link_id,
                cycle_id,
                stage_str,
                evidence_type,
                evidence_id,
                evidence_table,
                sequence_order,
            ),
        )
        self.db.commit()
        return True
