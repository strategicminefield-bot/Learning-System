import sys
sys.path.insert(0, "/app")
from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg
from uuid import UUID
import json

print("START", flush=True)

DATABASE_URL = "postgresql://fabric:fabric@postgres:5432/learning_fabric"
conn = psycopg.connect(DATABASE_URL)

TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")
APPROVAL_REQ = "ba2dd7b5-667c-44ed-a453-2e1f086b7b68"

engine = AdaptiveOrchestrationEngine(conn)

try:
    print("Calling orchestrate_task", flush=True)
    result = engine.orchestrate_task(
        task_id=TASK_ID,
        context={"test": "normal_path"},
        approval_request_id=APPROVAL_REQ
    )
    
    print("Result received", flush=True)
    print(json.dumps(result, indent=2, default=str))
    
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
finally:
    conn.close()
