import sys
sys.path.insert(0, "/app")
from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg
from uuid import UUID
import json

try:
    DATABASE_URL = "postgresql://fabric:fabric@postgres:5432/learning_fabric"
    conn = psycopg.connect(DATABASE_URL)
    
    TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")
    engine = AdaptiveOrchestrationEngine(conn)
    
    # Test orchestration path
    cursor = conn.cursor()
    cursor.execute("SELECT task_type FROM tasks WHERE task_id = %s", (TASK_ID,))
    task_row = cursor.fetchone()
    task_type = task_row[0] if task_row else None
    
    retrieval_trace = engine._retrieve_context(TASK_ID, task_type, None)
    strategy_candidates = engine._generate_strategy_candidates(TASK_ID, task_type, retrieval_trace, None)
    strategy_evaluation = engine._evaluate_strategy_candidates(strategy_candidates, None, retrieval_trace)
    selected_strategy = strategy_evaluation.get("selected")
    
    execution_plan = engine._generate_execution_plan(TASK_ID, task_type, selected_strategy, retrieval_trace)
    
    decision_id = engine._record_orchestration_decision(
        task_id=TASK_ID,
        context_considered={"trace": "test"},
        strategy_candidates=strategy_candidates,
        strategy_selected=selected_strategy,
        worker_candidates=[],
        worker_selected=None,
        execution_plan=execution_plan,
        strategy_rationale=strategy_evaluation.get("rationale"),
        worker_rationale="No worker",
        confidence_score=strategy_evaluation.get("confidence", 0.50),
        evidence_summary={"sufficiency": strategy_evaluation.get("evidence_sufficiency")},
        decision_rationale={"test": "direct_path"},
        rule_version=1
    )
    
    plan_id = engine._record_orchestration_plan(decision_id, selected_strategy, execution_plan, retrieval_trace)
    
    conn.commit()
    
    result = {
        "decision_id": str(decision_id),
        "plan_id": str(plan_id),
        "strategy_selected": selected_strategy.get("strategy_name") if selected_strategy else None,
        "execution_plan_steps": len(execution_plan.get("ordered_steps", []))
    }
    
    print(json.dumps(result, indent=2))
    
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
finally:
    conn.close()
