#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

import json
from uuid import UUID
import logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger(__name__)

from adaptive_orchestration import AdaptiveOrchestrationEngine
import psycopg

DATABASE_URL = "postgresql://fabric:fabric@postgres:5432/learning_fabric"
conn = psycopg.connect(DATABASE_URL)

TASK_ID = UUID("8667ec7b-bb87-4785-a95e-fd636a58ff82")

logger.info("=" * 60)
logger.info("ORCHESTRATION TRACE START")
logger.info(f"Task ID: {TASK_ID}")
logger.info("=" * 60)

engine = AdaptiveOrchestrationEngine(conn)

try:
    result = engine.orchestrate_task(
        task_id=TASK_ID,
        context={"trace": "debug"},
        node_id=None
    )
    logger.info("=" * 60)
    logger.info("ORCHESTRATION RESULT")
    logger.info("=" * 60)
    print(json.dumps(result, indent=2, default=str))
except Exception as e:
    logger.error(f"ERROR: {e}", exc_info=True)
    print(f"ERROR: {e}", file=sys.stderr)
finally:
    conn.close()
