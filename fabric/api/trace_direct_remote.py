#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")

import json
from uuid import UUID, uuid4
import logging
logging.basicConfig(level=logging.INFO, format="%(name)s - %(message)s")
logger = logging.getLogger(__name__)

from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg

DATABASE_URL = "postgresql://fabric:fabric@postgres:5432/learning_fabric"
conn = psycopg.connect(DATABASE_URL)

TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")

logger.info("=" * 60)
logger.info("ORCHESTRATION PATH TRACE (DIRECT UNIT CALL)")
logger.info(f"Task ID: {TASK_ID}")
logger.info("=" * 60)

engine = AdaptiveOrchestrationEngine(conn)

try:
    # 1. Get task
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, task_type, specification, status FROM tasks WHERE task_id = %s", (TASK_ID,))
    task_row = cursor.fetchone()
    task_type = task_row[1] if task_row else None
    logger.info(f"\n1. LOAD TASK")
    logger.info(f"   Task Type: {task_type}")
    
    # 2. Retrieve context
    retrieval_trace = engine._retrieve_context(TASK_ID, task_type, None)
    logger.info(f"\n2. RETRIEVE CONTEXT")
    logger.info(f"   Retrieval Trace: {retrieval_trace}")
    
    # 3. Generate strategy candidates
    strategy_candidates = engine._generate_strategy_candidates(
        TASK_ID, task_type, retrieval_trace, None
    )
    logger.info(f"\n3. GENERATE STRATEGY CANDIDATES")
    logger.info(f"   Candidate Count: {len(strategy_candidates)}")
    for i, c in enumerate(strategy_candidates[:5]):
        logger.info(f"     [{i}] {c.get(\"strategy_name\")} (id: {c.get(\"strategy_id\")}, score: {c.get(\"effectiveness_score\")})")
    
    # 4. Evaluate strategy candidates
    strategy_evaluation = engine._evaluate_strategy_candidates(
        strategy_candidates, None, retrieval_trace
    )
    logger.info(f"\n4. EVALUATE STRATEGY CANDIDATES")
    selected = strategy_evaluation.get("selected")
    logger.info(f"   Selected: {selected.get(\"strategy_name\") if selected else \"None\"}")
    logger.info(f"   Confidence: {strategy_evaluation.get(\"confidence\")}")
    logger.info(f"   Evidence Sufficiency: {strategy_evaluation.get(\"evidence_sufficiency\")}")
    
    # 5. Generate execution plan
    execution_plan = engine._generate_execution_plan(
        TASK_ID, task_type, selected, retrieval_trace
    )
    logger.info(f"\n5. GENERATE EXECUTION PLAN")
    logger.info(f"   Strategy: {execution_plan.get(\"strategy_name\")}")
    logger.info(f"   Steps: {len(execution_plan.get(\"ordered_steps\", []))}")
    
    # 6. Record decision and plan
    logger.info(f"\n6. RECORD DECISION")
    decision_id = engine._record_orchestration_decision(
        task_id=TASK_ID,
        context_considered={"trace": "debug"},
        strategy_candidates=strategy_candidates,
        strategy_selected=selected,
        worker_candidates=[],
        worker_selected=None,
        execution_plan=execution_plan,
        strategy_rationale=strategy_evaluation.get("rationale"),
        worker_rationale="No worker required",
        confidence_score=strategy_evaluation.get("confidence", 0.50),
        evidence_summary={"sufficiency": strategy_evaluation.get("evidence_sufficiency")},
        decision_rationale={"test": "direct_trace"},
        rule_version=1
    )
    logger.info(f"   Decision ID: {decision_id}")
    
    # 7. Record plan
    logger.info(f"\n7. RECORD PLAN")
    plan_id = engine._record_orchestration_plan(
        decision_id, selected, execution_plan, retrieval_trace
    )
    logger.info(f"   Plan ID: {plan_id}")
    
    # Commit
    conn.commit()
    logger.info(f"\n" + "=" * 60)
    logger.info("ORCHESTRATION PATH COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Decision ID: {decision_id}")
    logger.info(f"Plan ID: {plan_id}")
    logger.info(f"Strategy: {selected.get(\"strategy_name\") if selected else \"default\"}")
    
except Exception as e:
    conn.rollback()
    logger.error(f"ERROR: {e}", exc_info=True)
    import traceback
    traceback.print_exc()
finally:
    conn.close()
