# Section 25: System Memory & Node Reconstitution

**Purpose**: Persistent operational memory so AI nodes can lose context, restart, or be replaced while recovering state from the Fabric.

**Key Principle**: *The Fabric remembers. Nodes forget.*

---

## Overview

### The Problem

AI nodes (like OpenClaw executors) typically need conversational context to be useful:

- Lose context → lose state
- Restart → start over
- Replace → lost knowledge
- Context window full → can't continue

### The Solution: Persistent Memory in Fabric

Instead of storing memory in the node, store it in the Fabric:

- **Node identity** (UUID) persisted locally in `.executor_config.json`
- **Node bootstraps** from Fabric with reconstitution package
- **System memory** stored in database (identity, role, references)
- **Procedural memory** stored as persistent procedures
- **Work state** checkpointed at key stages
- **All memory sourced outside the node** → node-agnostic

---

## Architecture

### Memory Types (Stored in `system_memory` table)

1. **NODE_IDENTITY**: Stable UUID + display name
   - What it is: `{"node_id": "uuid", "display_name": "..."}`
   - Persisted locally + in Fabric
   - Never changes (unless node is recreated)

2. **NODE_ROLE**: Capabilities, authority, permissions
   - What it is: `{"role": "executor", "capabilities": ["code_execution", "analysis"]}`
   - Defines what the node is allowed to do
   - Authority stays in Governance (Section 20), not in memory

3. **OPERATIONAL_REFERENCE**: Fabric endpoints, API base URLs
   - What it is: `{"fabric_url": "...", "api_base": "/api/v1"}`
   - Node looks up where to send requests
   - System-wide (not node-specific)

4. **PROCEDURAL_MEMORY**: How to perform operations
   - What it is: Step-by-step procedures (startup, error handling, recovery)
   - Versioned, provider-specific (openclaw, openai, etc.)
   - Applicable to roles or specific nodes

5. **WORK_STATE_CHECKPOINT**: Current task state
   - What it is: `{"assignment_id": "...", "stage": "executing", "data": {...}}`
   - Expires in 7 days (recoverable window)
   - Node can resume exactly where it left off

6. **LINKED_ORGANISATIONAL**: References to existing knowledge
   - Links to Section 7 knowledge graph
   - Uses existing learning infrastructure
   - No duplication

---

## Reconstitution Flow

### 1. Node Startup (or After Context Loss)

```
Node starts with ONLY:
  - Persistent UUID in ~/.openclaw/executor_config.json
  - Fabric URL (or environment variable)
```

### 2. Request Reconstitution Package

```bash
POST /api/v1/nodes/{node_id}/reconstitute?reason=startup
```

**Response** (complete bootstrap package):

```json
{
  "node_id": "ed77b03c-...",
  "assembled_at": "2026-09-17T17:56:06Z",
  "bootstrap": {
    "fabric_url": "http://95.179.236.41:8000",
    "adapter_type": "openclaw",
    "adapter_version": "1.0.0",
    "auth_mechanism": "gateway_managed"
  },
  "current_work": null,
  "system_memory": [
    {
      "type": "node_identity",
      "version": 1,
      "content": {"node_id": "...", "display_name": "..."}
    },
    {
      "type": "node_role",
      "version": 1,
      "content": {"role": "executor", "capabilities": [...]}
    },
    ...
  ],
  "procedures": [
    {
      "type": "startup",
      "title": "OpenClaw Executor Startup",
      "version": "1.0.0",
      "steps": [...]
    },
    ...
  ]
}
```

### 3. Node Applies Reconstitution

1. Extract bootstrap (fabric_url, auth info)
2. Load system_memory into working context
3. Load procedures (know how to perform operations)
4. Check current_work → resume if in progress
5. Ready to claim assignments

### 4. During Execution: Save Checkpoints

```bash
POST /api/v1/nodes/{node_id}/work-checkpoint
{
  "assignment_id": "...",
  "task_id": "...",
  "attempt_id": "...",
  "checkpoint_stage": "executing",
  "checkpoint_data": {"prompt": "...", "start_time": "...", ...}
}
```

**Checkpoints expire in 7 days** → generous recovery window.

### 5. After Context Loss: Recover

```bash
GET /api/v1/nodes/{node_id}/work-checkpoint
```

Returns latest checkpoint. Node can:
- Resume execution if stage is "executing"
- Retry if stage is "awaiting_response"
- Ask for new assignment if stage is "complete"

---

## Database Schema

### `system_memory`

| Column | Type | Purpose |
|--------|------|---------|
| `memory_id` | UUID | Primary key |
| `memory_type` | TEXT | Classification (node_identity, role, etc.) |
| `scope` | TEXT | 'node', 'role', 'system', 'task', 'provider' |
| `scope_id` | UUID | Which node/role/task (if applicable) |
| `content` | JSONB | Actual memory content |
| `version` | INT | For versioning updates |
| `is_current` | BOOL | True if latest version |
| `authority_classification` | TEXT | 'bootstrap', 'operational', 'procedural' |
| `confidence` | NUMERIC | 0-1 confidence level |
| `created_at` | TIMESTAMP | When created |
| `linked_knowledge_id` | UUID | Link to Section 7 knowledge if applicable |

### `procedural_memory`

| Column | Type | Purpose |
|--------|------|---------|
| `procedure_id` | UUID | Primary key |
| `procedure_type` | TEXT | 'startup', 'task_execution', 'error_handling', etc. |
| `provider_type` | TEXT | 'openclaw', 'openai', 'anthropic', etc. |
| `title` | TEXT | Human-readable name |
| `procedure_steps` | JSONB | Array of step objects |
| `version` | TEXT | Semantic version (1.0.0) |
| `applicable_roles` | TEXT[] | Which roles use this |
| `enabled` | BOOL | Is this procedure active |
| `effective_from` / `effective_until` | TIMESTAMP | When procedure is valid |

### `node_bootstrap_config`

| Column | Type | Purpose |
|--------|------|---------|
| `bootstrap_id` | UUID | Primary key |
| `node_id` | UUID | Which node |
| `fabric_url` | TEXT | Where to connect to Fabric |
| `adapter_type` | TEXT | 'openclaw', 'openai', etc. |
| `identity_store_path` | TEXT | Where node stores config (~/.openclaw/executor_config.json) |
| `auth_mechanism` | TEXT | 'gateway_managed', 'local_config', 'environment', etc. |

### `work_state_checkpoints`

| Column | Type | Purpose |
|--------|------|---------|
| `checkpoint_id` | UUID | Primary key |
| `node_id` | UUID | Which node |
| `task_id` | UUID | What task |
| `assignment_id` | UUID | Which assignment |
| `checkpoint_data` | JSONB | Current state snapshot |
| `checkpoint_stage` | TEXT | 'started', 'executing', 'awaiting_response', etc. |
| `is_recoverable` | BOOL | Can it be resumed |
| `expires_at` | TIMESTAMP | Recovery window (7 days) |

### `memory_access_log`

Observability table. Logs all memory access for debugging.

---

## API Reference

### Reconstitution

```
POST /api/v1/nodes/{node_id}/reconstitute?reason=startup
→ {node_id, bootstrap, system_memory, procedures, current_work}
```

### System Memory Operations

```
POST /api/v1/system-memory
  {memory_type, scope, content, ...}
  → {memory_id}

GET /api/v1/system-memory/{memory_id}
  → full memory record

GET /api/v1/system-memory?memory_type=role&scope_id={uuid}
  → filtered list

POST /api/v1/system-memory/link
  Link system_memory to knowledge_id (for learning integration)
```

### Procedural Memory

```
POST /api/v1/procedures
  {procedure_type, provider_type, title, steps, version}
  → {procedure_id}

GET /api/v1/procedures?provider_type=openclaw&procedure_type=startup
  → list of procedures
```

### Work State

```
POST /api/v1/nodes/{node_id}/work-checkpoint
  {assignment_id, task_id, checkpoint_stage, checkpoint_data}
  → {checkpoint_id}

GET /api/v1/nodes/{node_id}/work-checkpoint
  → latest checkpoint (or 404)
```

### Bootstrap Configuration

```
POST /api/v1/nodes/{node_id}/bootstrap
  {fabric_url, adapter_type, identity_store_path, auth_mechanism}
  → {bootstrap_id}

GET /api/v1/nodes/{node_id}/bootstrap
  → bootstrap config
```

### Memory Access Logging

```
GET /api/v1/nodes/{node_id}/memory-access-log?access_type=reconstitution_package
  → access history for debugging
```

---

## OpenClaw Executor Implementation

### Identity Persistence

**File**: `~/.openclaw/executor_config.json`

```json
{
  "node_id": "ed77b03c-7c4d-49ed-9918-30f0c6dc7c12",
  "fabric_url": "http://95.179.236.41:8000",
  "adapter_type": "openclaw",
  "created_at": "2026-09-17T17:14:18Z"
}
```

This file is the **minimal persistent state**. Everything else comes from Fabric.

### Startup Procedure

```python
# 1. Load identity
node_id, fabric_url = ExecutorIdentity.load_or_create()

# 2. Request reconstitution package
reconstitution = Reconstitution(fabric_url, node_id)
package = reconstitution.request_package(reason="startup")

# 3. Apply bootstrap
reconstitution.apply_bootstrap(package)

# 4. Load memory
system_memory = reconstitution.get_system_memory(package)
procedures = reconstitution.get_procedures(package)

# 5. Ready for work
executor = ExecutionEngine(system_memory)
```

### Recovery After Context Loss

```python
# Node detects lost context (e.g., new Python process)
# 1. Identity is still in ~/.openclaw/executor_config.json
# 2. Call reconstitution again with reason="context_loss"
# 3. Get full state from Fabric

package = reconstitution.request_package(reason="context_loss")

# Check for work in progress
work = reconstitution.get_work_in_progress(package)
if work:
    # Resume from checkpoint
    checkpoint_mgr = WorkCheckpoint(fabric_url, node_id)
    checkpoint = checkpoint_mgr.recover()
    # Continue execution
```

### Checkpoint Saving (During Execution)

```python
checkpoint_mgr.save(
    assignment_id=assignment_id,
    task_id=task_id,
    attempt_id=attempt_id,
    stage="executing",
    data={
        "prompt": prompt,
        "start_time": time.time(),
        "partial_result": result_so_far
    }
)
```

---

## Security & Constraints

### What's Stored in Memory?

✅ Safe:
- Node identity (UUID, name)
- Capabilities & roles
- Procedures (how-to steps)
- API endpoints
- References to knowledge

❌ Never:
- Credentials, API keys, passwords
- Secrets (use `secret_store_reference` instead)
- Private user data (link to it, don't store)
- Governance decisions (they stay in Section 20)

### Key Principles

1. **Memory is information-only** → Authority is separate (Section 20 Governance)
2. **No secrets in memory** → Use `.secret_store_reference` for references
3. **Memory is observable** → All access logged (`memory_access_log`)
4. **Memory is versioned** → Can roll back or supersede
5. **Memory is bounded** → Checkpoints expire; retrieval is limited

---

## Testing & Verification

### Test 1: Reconstitution Package Retrieval

```bash
curl -X POST "http://95.179.236.41:8000/api/v1/nodes/ed77b03c-7c4d-49ed-9918-30f0c6dc7c12/reconstitute?reason=startup" | jq .
```

**Expected**: Full package with bootstrap, system_memory, procedures.

### Test 2: System Memory Query

```bash
curl "http://95.179.236.41:8000/api/v1/system-memory?scope=node&scope_id=ed77b03c-7c4d-49ed-9918-30f0c6dc7c12" | jq .
```

**Expected**: Node identity, role, references.

### Test 3: Procedure Lookup

```bash
curl "http://95.179.236.41:8000/api/v1/procedures?provider_type=openclaw&procedure_type=startup" | jq .
```

**Expected**: Startup procedures for OpenClaw.

### Test 4: Executor Recovery

```bash
python3 fabric/adapter/openclaw_executor_with_memory.py
```

**Expected**: 
1. Load identity from disk
2. Request reconstitution from Fabric
3. Extract memory, procedures, bootstrap
4. Report "✓ EXECUTOR READY"

### Test 5: Context Loss Simulation (Advanced)

```bash
# Save checkpoint
curl -X POST "http://95.179.236.41:8000/api/v1/nodes/ed77b03c-7c4d-49ed-9918-30f0c6dc7c12/work-checkpoint" \
  -H "Content-Type: application/json" \
  -d '{"assignment_id": "...", "checkpoint_stage": "executing", "checkpoint_data": {...}}'

# "Node crashes" (restart Python process)

# Node requests reconstitution
curl -X POST "http://95.179.236.41:8000/api/v1/nodes/ed77b03c-7c4d-49ed-9918-30f0c6dc7c12/reconstitute?reason=context_loss" | jq .

# Recover work checkpoint
curl "http://95.179.236.41:8000/api/v1/nodes/ed77b03c-7c4d-49ed-9918-30f0c6dc7c12/work-checkpoint" | jq .
```

**Expected**: All work state recovered, node can resume.

---

## Integration with Existing Fabric

### Links to Section 7 (Knowledge Graph)

System memory can be linked to knowledge via `linked_knowledge_id`:

```python
INSERT INTO system_memory_to_knowledge
(system_memory_id, knowledge_id, relationship_type)
VALUES ('...', '...', 'derived_from');
```

This allows learning pipeline (Sections 6-14) to use system memory as evidence.

### Links to Sections 6-14 (Learning Pipeline)

- Memory access logged → becomes evidence
- Procedural memory can be updated via learning outcomes
- Bootstrap config can be evolved per node behavior
- Work checkpoints feed into attempt history

### Links to Section 20 (Governance)

- Memory provides information only
- Authority decisions (can this node run this task?) stay in Governance
- Node role memory references governance policy
- No override of governance decisions in memory

---

## Migration & Deployment

### Migration: `025_system_memory_node_reconstitution.sql`

Adds 7 new tables:
1. `system_memory`
2. `node_bootstrap_config`
3. `node_reconstitution_packages`
4. `procedural_memory`
5. `work_state_checkpoints`
6. `memory_access_log`
7. `system_memory_to_knowledge`

All with proper indexes and constraints.

### API Deployment

New router: `fabric/api/system_memory_endpoints.py`

Endpoints registered in `main.py`:

```python
from system_memory_endpoints import router as system_memory_router
...
app.include_router(system_memory_router)
```

### Executor Deployment

New executable: `fabric/adapter/openclaw_executor_with_memory.py`

Can be run standalone:

```bash
python3 openclaw_executor_with_memory.py
# Loads identity, requests reconstitution, ready for work
```

Or modified to integrate with existing adapter startup script.

---

## Future: Multi-Provider Support

This architecture supports any provider:

1. Create `node_bootstrap_config` for provider
2. Insert system_memory for provider
3. Create `procedural_memory` entries with `provider_type='openai'` (etc.)
4. Provider-agnostic `/reconstitute` endpoint returns all of it
5. Each provider adapter applies memory differently

Example: OpenAI executor

```python
class OpenAIExecutor(ExecutionEngine):
    def execute_task(self, prompt):
        # Use system_memory to find API key (reference, not stored)
        # Load procedures for openai
        # Call OpenAI API
        # Save checkpoint
```

---

## Observability & Debugging

### Memory Access Log

```sql
SELECT * FROM memory_access_log WHERE node_id = 'ed77b03c-...' ORDER BY requested_at DESC LIMIT 10;
```

Shows every memory access: when, what, how many items, success/failure.

### Reconstitution Packages Log

```sql
SELECT * FROM node_reconstitution_packages WHERE node_id = 'ed77b03c-...' ORDER BY assembled_at DESC;
```

Shows each time a node requested reconstitution, what was included, success.

### Procedure Audit

```sql
SELECT * FROM procedural_memory WHERE procedure_type = 'startup' ORDER BY created_at DESC;
```

Track procedure versions and changes.

---

## Next Steps (Phase 2)

1. **Multi-Provider Integration**: OpenAI, Anthropic, others
2. **Learning Integration**: Update procedures based on success/failure
3. **Adaptive Memory**: Trim/update system_memory based on usage
4. **Node Evolution**: Procedures improve over time (Section 18)
5. **Cross-Node Memory Sharing**: Link evidence between nodes (Sections 12-14)

---

## References

- **Section 6**: Learning Foundation
- **Section 7**: Knowledge Graph
- **Section 12**: Cross-Node Learning
- **Section 14**: Strategy Learning
- **Section 20**: Governance & Safety
- **Schema**: `migrations/025_system_memory_node_reconstitution.sql`
- **Endpoints**: `fabric/api/system_memory_endpoints.py`
- **Executor**: `fabric/adapter/openclaw_executor_with_memory.py`
