import sys, json
from uuid import UUID
import logging
logging.basicConfig(level=logging.INFO)

from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg

DATABASE_URL = "postgresql://fabric:learning_fabric_dev@localhost:5432/learning_fabric"
conn = psycopg.connect(DATABASE_URL)

TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")

engine = AdaptiveOrchestrationEngine(conn)

try:
    result = engine.orchestrate_task(
        task_id=TASK_ID,
        context={"trace": "debug"},
        node_id=None
    )
    print(json.dumps(result, indent=2, default=str))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
finally:
    conn.close()
