# OpenClaw Executor Integration — Go-Live Phase 1

**Status**: PHASE 1 BEGINNING (2026-09-17 18:04 GMT+1)

**Objective**: Connect the actual OpenClaw instance running on WSL as the first real executor node to the Learning Fabric.

---

## 1. ARCHITECTURE OVERVIEW

### Existing Fabric Abstractions (Sections 2-24)

The Learning Fabric already provides:

- **Node Model** (`nodes` table): node_id, node_type, status, created_at, last_seen_at
- **Node Definitions** (`node_definitions`): Definition ID, provider_type, lifecycle_state
- **Node Instances** (`node_instances`): Real running instances
- **Node Capabilities** (`node_capabilities`): Declared capabilities/features
- **Worker Status** (endpoints): `/workers` endpoints, heartbeat, status updates
- **Task/Assignment Lifecycle** (Sections 2-3): Tasks → Assignments → Attempts → Results → Outcomes
- **Event Recording** (Section 3): Complete audit trail
- **Orchestration** (Section 15): Strategy & worker selection
- **Governance** (Section 20): Authority enforcement
- **Learning Pipeline** (Sections 6-14): Evidence capture and feedback

### OpenClaw Executor Role

OpenClaw will be integrated as:

- **Node Type**: `executor` (new type, distinct from existing `ai_assistant` test nodes)
- **Provider**: `openclaw`
- **Capabilities**: code execution, task automation, analysis
- **Status**: available/busy/offline (existing states)
- **Heartbeat**: periodic health/availability ping
- **Scope**: execute Fabric-assigned work, return structured results

### Integration Boundary

The integration will consist of two components:

1. **Fabric-side Components** (minimal changes):
   - Node definition for OpenClaw executor type
   - Task assignment logic (existing)
   - Result acceptance (existing)
   - Learning pipeline (existing)

2. **OpenClaw-side Adapter** (new Python module):
   - Node identity management
   - Fabric API client
   - Work receiver (polling for assignments)
   - Execution dispatcher
   - Result formatter
   - Heartbeat sender
   - Configuration management

The adapter runs in OpenClaw's environment (WSL) and communicates with the Fabric via authenticated HTTP/REST.

---

## 2. NODE REGISTRATION & IDENTITY

### Stable Node Identity

**Node ID**: Will be generated once and persisted in adapter configuration.

**Node Definition**: Will be created/registered via the Fabric API.

**Example structure**:

```json
{
  "node_id": "<persistent-uuid>",
  "node_type": "executor",
  "provider": "openclaw",
  "display_name": "OpenClaw Executor (WSL)",
  "capabilities": [
    "code_execution",
    "task_automation",
    "analysis",
    "text_generation"
  ],
  "status": "available",
  "adapter_version": "1.0.0",
  "openclaw_version": "<version>",
  "last_heartbeat": "<timestamp>"
}
```

**Persistence**: Node ID stored in adapter config file (no secrets).

**Lineage**: Node definition remains distinct from node instance; instance can be recreated without changing the definition.

---

## 3. ADAPTER ARCHITECTURE

### Adapter Location

**Path**: `~/Learning-System/fabric/adapter/openclaw_executor.py`

**Start Method**: Explicit Python script (not auto-started)

**Configuration**: `~/.openclaw/executor_config.json` (user's OpenClaw home, no secrets)

### Adapter Components

1. **Configuration Manager**
   - Load/save node identity
   - API endpoint configuration
   - Heartbeat interval
   - Poll frequency
   - Timeout settings

2. **Fabric API Client**
   - Authenticated requests to Fabric
   - Poll for assignments
   - Claim assignment
   - Submit results
   - Heartbeat
   - Fetch task context

3. **Execution Engine**
   - Invoke OpenClaw CLI/API
   - Pass task + context
   - Capture execution output
   - Handle failures/timeouts
   - Record structured result

4. **Result Formatter**
   - Convert OpenClaw output to Fabric result schema
   - Capture execution evidence
   - Link to attempt/task/assignment
   - Include execution metadata

5. **Heartbeat Monitor**
   - Periodic status updates
   - Last seen timestamp
   - Availability status
   - Graceful shutdown

---

## 4. TASK FLOW

```
Fabric Task Creation
  ↓
Assignment to OpenClaw executor node
  ↓
OpenClaw adapter polls /assignments endpoint
  ↓
Adapter claims assignment (POST /assignments/{id}/claim)
  ↓
Adapter fetches task context from Fabric
  ↓
Adapter invokes OpenClaw execution with task+context
  ↓
OpenClaw performs actual work
  ↓
OpenClaw returns structured output
  ↓
Adapter formats result into Attempt result record
  ↓
Adapter POSTs result to /attempts/{attempt_id}/result
  ↓
Fabric records attempt, result, outcome
  ↓
Verification processes result
  ↓
Learning pipeline consumes evidence
  ↓
Complete lineage preserved in Fabric
```

---

## 5. RESULT SCHEMA

OpenClaw adapter must return structured results compatible with Fabric:

```json
{
  "node_id": "<openclaw-node-id>",
  "attempt_id": "<uuid>",
  "task_id": "<uuid>",
  "assignment_id": "<uuid>",
  "status": "completed|failed|timeout",
  "execution": {
    "start_time": "ISO-8601",
    "end_time": "ISO-8601",
    "duration_seconds": <number>,
    "model": "openclaw/model-name",
    "version": "1.2.3"
  },
  "output": {
    "artifacts": [
      {
        "type": "text|code|analysis",
        "content": "<content>",
        "format": "markdown|python|json",
        "checksum": "<sha256>"
      }
    ],
    "quality_score": 0.85,
    "confidence": 0.92
  },
  "observations": [
    {
      "type": "execution_metric|quality|constraint",
      "content": "<observation>",
      "confidence": 0.95
    }
  ],
  "errors": null,
  "repair_attempted": false
}
```

---

## 6. FAILURE HANDLING

If OpenClaw execution fails:

1. Adapter captures failure evidence
2. Posts failed attempt with reason
3. Fabric retains failed attempt in history
4. If repair is attempted:
   - Create new attempt record
   - Link to original failure
   - Retry execution
5. Both attempts remain in complete history

---

## 7. HEARTBEAT & HEALTH

Adapter sends periodic heartbeat:

```
POST /workers/{node_id}/heartbeat
```

Expected frequency: every 30 seconds

Updates:
- `last_seen_at` timestamp
- Status (available/busy/offline)
- Metrics (assignments_in_progress, failure_rate, etc.)

Fabric can detect offline nodes if heartbeat stops for > 60s.

---

## 8. AUTHORITY BOUNDARIES

**OpenClaw Executor Authority**:

- ✓ Receive assigned tasks
- ✓ Execute work within task constraints
- ✓ Return results
- ✓ Report heartbeat/status
- ✗ Modify node definition
- ✗ Create arbitrary tasks
- ✗ Modify governance
- ✗ Access SSH/VPS/infrastructure
- ✗ Access secrets/credentials
- ✗ Modify other nodes

**Fabric Authority**:

- ✓ Create/manage tasks
- ✓ Assign work to OpenClaw
- ✓ Evaluate results
- ✓ Make governance decisions
- ✓ Apply learning/evidence

---

## 9. SECURITY & SECRETS

**No Secrets in Adapter Configuration**:

- Node ID is not a secret (public identifier)
- API endpoint is known (VPS Fabric)
- Fabric API auth handled by OpenClaw gateway
- No database credentials in adapter config
- No GitHub tokens in adapter
- No OpenClaw secrets in Fabric

**Authentication**:

- Adapter calls Fabric API through OpenClaw gateway (existing auth)
- OpenClaw gateway handles credential management
- Fabric validates node identity from request

---

## 10. IMPLEMENTATION PLAN

### Phase 1a: Fabric-side Setup (minimal)

1. Register OpenClaw node definition
   - node_type = "executor"
   - provider = "openclaw"
   - lifecycle_state = "candidate" (will be validated through execution)

2. Verify existing endpoints support executor workflow
   - /workers (POST to create node)
   - /workers/{id}/heartbeat
   - /assignments (GET to poll)
   - /assignments/{id}/claim (POST)
   - /attempts/{id}/result (POST)

### Phase 1b: OpenClaw Adapter (new)

1. Create `fabric/adapter/openclaw_executor.py`
2. Implement configuration manager
3. Implement Fabric API client
4. Implement execution dispatcher
5. Implement result formatter
6. Add command-line interface for start/stop

### Phase 1c: Testing

1. Register adapter as node
2. Create test task
3. Assign to OpenClaw node
4. Run real OpenClaw execution
5. Capture and verify results
6. Test failure/repair
7. Test learning pipeline

---

## 11. OPENCLAW EXECUTION TESTING

### Test Task Characteristics

**Safety**: Bounded, non-destructive, verifiable

**Example**: Generate a structured summary of provided input

```
INPUT: "The Learning Fabric connects multiple AI nodes through persistent 
organisational memory and evidence-driven adaptation."

OPENCLAW TASK: "Summarize the input text in JSON format with title, main_idea, 
key_entities. Verify the summary is syntactically valid JSON."

EXPECTED OUTPUT:
{
  "title": "Learning Fabric Architecture Overview",
  "main_idea": "Persistent system enabling multiple AI nodes to collaborate through 
  shared memory and evidence-driven decision making",
  "key_entities": ["Learning Fabric", "AI nodes", "memory", "evidence", "adaptation"]
}
```

**Verification**: JSON is valid, structure matches schema, content is relevant

---

## 12. REAL EXECUTION EVIDENCE

**E2E Test A - Real Execution**:

1. Create task in Fabric
2. Assign to OpenClaw node
3. Adapter receives/claims assignment
4. **ACTUAL OpenClaw execution** (not simulated)
5. Capture output
6. Post result to Fabric
7. Verify attempt recorded
8. Verify result recorded
9. Verify complete lineage queryable

**FAIL CONDITION**: If OpenClaw execution is simulated or skipped.

---

## 13. LEARNING PIPELINE INTEGRATION

After real OpenClaw execution:

1. Fabric records outcome with real evidence
2. Learning pipeline processes the result
3. Evidence scored against validation thresholds
4. If evidence sufficient, learning is available for later tasks
5. Later comparable task can retrieve prior evidence/guidance

**Key**: Learning comes from real execution evidence, not manufactured conclusions.

---

## 14. RESTART & PERSISTENCE

On adapter restart:

1. Load persisted node identity from config
2. Reconnect to Fabric
3. Send heartbeat
4. Resume polling for assignments
5. Previous attempts/results remain in Fabric
6. No duplicate node identity created

---

## 15. DOCUMENTATION

After successful Phase 1, update:

- `OPERATING_ENVIRONMENT.md` - Add OpenClaw executor section
- `PROJECT_STATE.md` - Record Phase 1 completion
- `docs/OPENCLAW_EXECUTOR_INTEGRATION.md` - This file (implementation results)

Avoid committing secrets.

---

## Current Status

**Phase**: Beginning (startup verification complete)
**Core Build**: Sections 2-24 verified
**Next**: Begin Phase 1a (Fabric-side registration)
