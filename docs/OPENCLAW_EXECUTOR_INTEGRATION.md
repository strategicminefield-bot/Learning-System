# OpenClaw Executor Integration — Phase 1 Operational Procedure

**Status**: PHASE 1 OPERATIONAL (2026-09-17)  
**Integration Type**: Real executor node via Learning Fabric API  
**Execution Method**: ACTUAL OpenClaw with real AI models  

---

## QUICK START

### Prerequisites
- OpenClaw installed and functional on local system
- Python 3.9+
- Network access to Learning Fabric VPS (95.179.236.41:8000)
- Node ID persisted in ~/.openclaw/executor_config.json

### Start Procedure

```bash
cd ~/Learning-System
python3 fabric/adapter/openclaw_executor.py &
```

Expected output:
```
[INFO] Starting OpenClaw Executor Adapter
[INFO] Node ID: ed77b03c-7c4d-49ed-9918-30f0c6dc7c12
[INFO] Fabric URL: http://95.179.236.41:8000
[INFO] Registering node with Fabric...
[INFO] Entering main loop, polling for assignments...
```

The adapter will:
1. Register with the Fabric using persisted node ID
2. Enter polling loop (5-second intervals)
3. Poll for assignments
4. Execute via real OpenClaw CLI: `openclaw agent --local ...`
5. Submit results back to Fabric
6. Send heartbeat every 30 seconds

---

## INTEGRATION ARCHITECTURE

### Node Identity Persistence

**File**: `~/.openclaw/executor_config.json`

Example (DO NOT EDIT - auto-generated):
```json
{
  "node_id": "ed77b03c-7c4d-49ed-9918-30f0c6dc7c12",
  "node_type": "executor",
  "provider": "openclaw",
  "display_name": "OpenClaw Executor (WSL)",
  "fabric_url": "http://95.179.236.41:8000",
  "heartbeat_interval": 30,
  "poll_interval": 5,
  "capabilities": [
    "code_execution",
    "task_automation",
    "analysis",
    "text_generation"
  ],
  "created_at": "2026-09-17T17:14:18.154759+00:00"
}
```

**Node ID** remains stable across adapter restarts. Do NOT delete or modify this file.

---

## TASK FLOW

### Full Lifecycle

```
1. Create Task in Fabric
   → POST /tasks with workflow_id, task_type, specification
   ↓
2. Create Assignment
   → POST /assignments with task_id, node_id (ed77b03c-...)
   ↓
3. Adapter Polls for Assignments
   → GET /assignments?node_id=ed77b03c-...
   ↓
4. Adapter Claims Assignment
   → POST /assignments/{assignment_id}/claim
   ↓
5. Adapter Creates Attempt
   → POST /assignments/{assignment_id}/attempts
   ↓
6. REAL OpenClaw Execution
   → subprocess: openclaw agent --local --message <prompt>
   → Actual AI model (e.g., Claude Haiku 4.5 via OpenRouter)
   → Capture stdout + return code
   ↓
7. Format Result
   → {
       "task_id": "...",
       "result": "<AI output>",
       "execution_evidence": {
         "provider": "openclaw",
         "model": "claude-haiku-4.5",
         "execution_type": "real local agent",
         "success": true,
         "provider_confirmed": true
       }
     }
   ↓
8. Submit Result
   → POST /attempts/{attempt_id}/result with formatted result
   ↓
9. Fabric Records Outcome
   → Task marked complete
   → Result stored with full lineage
   → Evidence available for learning pipeline
   ↓
10. Learning Pipeline Processes Evidence
    → Evidence scored for validation
    → If threshold met, available for later tasks
    → Improvement captured in knowledge graph
```

---

## ADAPTER COMPONENTS

### ExecutorConfig
- Loads/creates `~/.openclaw/executor_config.json`
- Persists node identity across restarts
- Provides Fabric URL and polling intervals

### FabricClient
- HTTP client for Fabric REST API
- Endpoints used:
  - `POST /workers` → register node
  - `POST /workers/{node_id}/heartbeat` → send heartbeat
  - `GET /assignments?node_id=...` → poll for work
  - `POST /assignments/{id}/claim` → claim assignment
  - `POST /assignments/{id}/attempts` → create attempt
  - `POST /attempts/{id}/result` → submit result

### OpenClawExecutor
- Executes tasks using **REAL** OpenClaw CLI
- Command: `openclaw agent --local --message <prompt>`
- Captures stdout/stderr
- Returns structured result JSON
- Timing: ~2-4 seconds per execution (AI model latency)

### ExecutorAdapter
- Main orchestration loop
- Polling: 5-second intervals
- Heartbeat: 30-second intervals
- Error handling: Retries on transient failures
- Graceful shutdown: Ctrl+C to stop

---

## RESULT FORMAT

Adapter formats results like this:

```json
{
  "task_id": "<from task specification>",
  "test_id": "<from task specification>",
  "result": "<actual OpenClaw agent output>",
  "timestamp": "2026-09-17T18:30:00.000Z",
  "execution_evidence": {
    "provider": "openclaw",
    "model": "claude-haiku-4.5",
    "execution_type": "real local agent via CLI --local",
    "success": true,
    "provider_confirmed": true
  }
}
```

**Key**: `execution_evidence` proves the execution was:
- Real (not simulated)
- Local (--local flag, no gateway round-trip)
- Provider-confirmed (from actual AI model, not mock)

---

## HEARTBEAT & NODE STATUS

The adapter sends heartbeat every 30 seconds:

```
POST /workers/ed77b03c-7c4d-49ed-9918-30f0c6dc7c12/heartbeat
{
  "node_id": "ed77b03c-7c4d-49ed-9918-30f0c6dc7c12",
  "status": "available",
  "timestamp": "2026-09-17T18:30:00.000Z"
}
```

Fabric tracks:
- `last_seen_at`: timestamp of last heartbeat
- `status`: available/busy/offline
- Node is considered offline if no heartbeat for 60s

---

## FAILURE HANDLING

If OpenClaw execution fails:

1. Adapter catches subprocess exception
2. Logs error with details
3. Returns failed attempt with error message
4. Posts to Fabric: `POST /attempts/{id}/fail`
5. Attempts marked as "failed" in database
6. Reason preserved for learning

Example failed result:
```json
{
  "task_id": "abc123",
  "error": "ZeroDivisionError: division by zero",
  "stderr": "Traceback (most recent call last)...",
  "execution_evidence": {
    "provider": "openclaw",
    "model": "claude-haiku-4.5",
    "success": false,
    "error_type": "execution_error"
  }
}
```

---

## VERIFICATION CHECKLIST

After starting adapter, verify:

```bash
# Check if process is running
ps aux | grep openclaw_executor

# Check if config was created
ls -l ~/.openclaw/executor_config.json

# Check Fabric connectivity
curl http://95.179.236.41:8000/api/v1/health/alive

# Check if node is registered in Fabric
ssh vultr 'curl http://localhost:8000/api/v1/workers'

# Check recent attempts in database
ssh vultr 'docker exec learning-fabric-postgres psql -U fabric -d learning_fabric \
  -c "SELECT attempt_id, status FROM attempts \
      WHERE node_id = '\''ed77b03c-7c4d-49ed-9918-30f0c6dc7c12'\''::uuid \
      ORDER BY started_at DESC LIMIT 5;"'
```

---

## RESTART & RECONNECTION

If adapter crashes or is stopped:

```bash
# Kill existing process
pkill -f "openclaw_executor.py"

# Wait 5 seconds
sleep 5

# Restart
cd ~/Learning-System && python3 fabric/adapter/openclaw_executor.py &
```

The adapter will:
1. Load node ID from `~/.openclaw/executor_config.json` (same ID!)
2. Re-register with Fabric (Fabric deduplicates by node_id)
3. Resume polling
4. Previous attempts/results remain in Fabric

**No duplicate node created**. Node identity is persistent.

---

## DEBUGGING

### Check Adapter Logs

The adapter writes to stdout. To capture:

```bash
cd ~/Learning-System && python3 fabric/adapter/openclaw_executor.py 2>&1 | tee /tmp/adapter.log &

# Monitor in another terminal
tail -f /tmp/adapter.log
```

### Common Issues

**Issue**: Adapter starts but doesn't poll  
**Check**: Is adapter process running? `ps aux | grep openclaw_executor`  
**Fix**: Ensure no other instance is running; then restart

**Issue**: Assignments not being found  
**Check**: Are tasks/assignments created in Fabric?  
**Fix**: Create a test task via API or database

**Issue**: OpenClaw command not found  
**Check**: Is OpenClaw installed? `which openclaw`  
**Fix**: Install OpenClaw or add to PATH

**Issue**: Adapter can't reach Fabric  
**Check**: Network connectivity: `ping 95.179.236.41`  
**Fix**: Verify VPS is up; check firewall; check fabric_url in config

---

## PERFORMANCE CHARACTERISTICS

**Polling frequency**: 5 seconds (configurable)  
**Heartbeat interval**: 30 seconds (configurable)  
**OpenClaw execution**: ~2-4 seconds per task (AI model latency)  
**Result submission**: <1 second (HTTP POST)

**For 10 tasks**:
- Polling overhead: ~0.5-1 second total
- Heartbeats: ~0.1 second
- Execution: ~20-40 seconds (dominant)
- Total: ~20-50 seconds for 10 tasks

---

## AUTHORITY BOUNDARIES

**OpenClaw Executor Can**:
- ✅ Receive assigned tasks
- ✅ Execute work within task constraints
- ✅ Return results with execution evidence
- ✅ Report heartbeat/status
- ✅ Fail and retry

**OpenClaw Executor Cannot**:
- ❌ Modify node definition
- ❌ Create arbitrary tasks
- ❌ Modify governance
- ❌ Access SSH/VPS/infrastructure
- ❌ Access credentials
- ❌ Modify other nodes
- ❌ Delete data

All task creation, assignment, and validation is done by Fabric/authority nodes.

---

## SECURITY NOTES

**No secrets in adapter config**:
- Node ID is public
- Fabric URL is public
- No API keys, tokens, or passwords

**Authentication**:
- Handled by OpenClaw gateway (upstream)
- Adapter calls Fabric through VPS network
- Network isolation: Only port 8000 exposed

**Data isolation**:
- Results marked with execution_evidence
- Lineage trackable in Fabric
- Learning pipeline applies validation before using evidence

---

## INTEGRATION WITH LEARNING PIPELINE

After OpenClaw execution:

1. **Evidence Capture**: Result + execution_evidence stored
2. **Validation**: Fabric evaluates evidence against thresholds
3. **Learning Record**: If valid, creates learning record in knowledge graph
4. **Adaptation**: Later tasks can retrieve and apply learning
5. **Traceability**: All steps recorded in audit_events

Example learning flow:
```
Task A executes via OpenClaw
  → Evidence: "Successfully computed X using Y approach"
  → Validation: Confidence 0.92, learning_threshold 0.85 → QUALIFIED
  → Learning Record: "Approach Y works for X" with confidence 0.92
  ↓
Later Task B (similar to A)
  → Query learning pipeline
  → Retrieve evidence from A
  → Suggest applying approach Y
  → Higher success probability
```

---

## NEXT: PHASE 2

Phase 2 will integrate additional AI providers:
- OpenAI (Architect/Verifier nodes)
- Anthropic (Designer nodes)
- Other LLM providers

The executor adapter model (persistent node, polling, real execution, lineage) will be reused for each provider.

---

## RELATED DOCUMENTS

- `OPENCLAW_START.md` – Startup verification procedure
- `PROJECT_STATE.md` – Current project status
- `OPERATING_ENVIRONMENT.md` – Infrastructure map
- `fabric/adapter/openclaw_executor.py` – Full adapter source code

---

## SUPPORT

For integration issues:
1. Check OPENCLAW_START.md startup verification
2. Review adapter logs
3. Verify Fabric health: `/api/v1/health/ready`
4. Check node registration in database
5. Ensure task/assignment exist before adapter polls

---

**Last Updated**: 2026-09-17 18:40 GMT+1  
**Integration Status**: OPERATIONAL  
**Verified Execution**: YES (Real OpenClaw with AI models)  
**Node ID**: ed77b03c-7c4d-49ed-9918-30f0c6dc7c12  
