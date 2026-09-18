import sys
sys.path.insert(0, "/app")
print("IMPORT START", flush=True)

from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg
from uuid import UUID

print("IMPORT DONE", flush=True)

DATABASE_URL = "postgresql://fabric:fabric@postgres:5432/learning_fabric"
conn = psycopg.connect(DATABASE_URL)

TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")
engine = AdaptiveOrchestrationEngine(conn)

print("ENGINE CREATED", flush=True)

cursor = conn.cursor()
cursor.execute("SELECT task_type FROM tasks WHERE task_id = %s", (TASK_ID,))
task_row = cursor.fetchone()
task_type = task_row[0] if task_row else None
print(f"TASK_TYPE: {task_type}", flush=True)

retrieval_trace = engine._retrieve_context(TASK_ID, task_type, None)
print(f"RETRIEVAL_TRACE: {type(retrieval_trace)}", flush=True)

candidates = engine._generate_strategy_candidates(TASK_ID, task_type, retrieval_trace, None)
print(f"CANDIDATES: {len(candidates)}", flush=True)
for i, c in enumerate(candidates[:3]):
    print(f"  [{i}] {c.get('strategy_name')}", flush=True)

evaluation = engine._evaluate_strategy_candidates(candidates, None, retrieval_trace)
selected = evaluation.get("selected")
strat_name = selected.get('strategy_name') if selected else None
print(f"SELECTED: {strat_name}", flush=True)

plan = engine._generate_execution_plan(TASK_ID, task_type, selected, retrieval_trace)
print(f"PLAN_STEPS: {len(plan.get('ordered_steps', []))}", flush=True)

print("SUCCESS", flush=True)

conn.close()
