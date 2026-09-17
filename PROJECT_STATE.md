# Learning System — Project State

## Purpose

The Learning System is a persistent, VPS-hosted Learning Fabric intended to become the permanent source of truth for multiple AI assistants and AI workers.

The AI assistants are clients/workers of the system. The system itself must retain project state, task state, results, observations, history and learning independently of any particular AI conversation.

The long-term objective is for ChatGPT, Claude, OpenClaw and other AI systems to be able to work on the same projects without losing momentum when one AI becomes unavailable.

---

## Core Architecture

Current intended architecture:

- WSL/laptop = development and deployment interface
- GitHub = authoritative source for executable code
- VPS = 24/7 production/runtime environment
- PostgreSQL on VPS = authoritative persistent state/history
- Learning Fabric API = interface between AI nodes/workers and persistent state
- AI assistants/nodes = workers/controllers/clients
- Future layers include:
  - vector memory
  - knowledge graph
  - event/history
  - tasks/messages
  - learning
  - orchestration
  - API

The AI conversation itself must NOT be the sole source of project memory.

---

## Repository

GitHub repository:

`strategicminefield-bot/Learning-System`

Local WSL working directory:

`~/Learning-System`

VPS:

`vultr`

VPS application directory:

`/opt/learning-fabric`

API container:

`learning-fabric-api`

---

## Development Rule

Use this development cycle:

1. Develop a substantial coherent batch in WSL.
2. Test the complete batch.
3. Commit the completed batch.
4. Push to GitHub.
5. Deploy the batch to the VPS.
6. Run an end-to-end VPS verification.
7. Clean temporary development files.
8. Start the next substantial batch.

Do NOT unnecessarily split development into tiny endpoint-by-endpoint cycles.

GitHub remains the source of truth.

---

## Current Section

SECTION 3 — Event Recording and History API

Objective:

Implement event recording and audit trail system for complete history tracking of all lifecycle transitions. Enable querying of events for debugging, analysis, and foundation for learning layer.

Required capabilities:

- Event recording during all state transitions
- Audit trail queries
- Event filtering and pagination
- Previous/current state capture
- Metadata recording
- Chronological history reconstruction

---

## Database

PostgreSQL is already available on the VPS.

Foundation migration:

`migrations/001_foundation.sql`

Learning Fabric core migration:

`migrations/002_learning_fabric_core.sql`

Events migration:

`migrations/003_events.sql`

Important tables include:

- workflows
- tasks
- task_dependencies
- assignments
- attempts
- results
- observations
- nodes
- requests
- events (Section 3)

Important status values currently used:

### Assignment

- assigned
- claimed
- completed
- failed

### Task

- pending
- running
- completed
- failed

### Attempt

- running
- completed
- failed

### Node

- available
- busy

---

## Section 3 Completed

### Event Recording Table

Migration: `migrations/003_events.sql`

Schema:
- `event_id` UUID primary key
- `event_type` TEXT: type of event (created, claimed, completed, failed, result_submitted, etc.)
- `entity_type` TEXT: type of entity (assignment, attempt, task, etc.)
- `entity_id` UUID: ID of affected entity
- `node_id` UUID: optional reference to acting node
- `previous_state` JSONB: state before transition
- `current_state` JSONB: state after transition
- `metadata` JSONB: event-specific metadata (action, reason, etc.)
- `created_at` TIMESTAMPTZ: event timestamp

Indexes on:
- entity (entity_type, entity_id)
- event_type
- node_id
- created_at DESC
- entity+time (entity_type, entity_id, created_at DESC)

### Event Recording Integration

All lifecycle endpoints now record events:
- Assignment creation → `event_type: 'created', entity_type: 'assignment'`
- Assignment claim → `event_type: 'claimed', entity_type: 'assignment'`
- Attempt creation → `event_type: 'created', entity_type: 'attempt'`
- Result submission → `event_type: 'result_submitted', entity_type: 'attempt'`
- Assignment completion → `event_type: 'completed', entity_type: 'assignment'`
- Attempt failure → `event_type: 'failed', entity_type: 'attempt'`
- Assignment failure → `event_type: 'failed', entity_type: 'assignment'`

Each event captures:
- Previous state (before transition)
- Current state (after transition)
- Node responsible for action
- Action metadata
- Precise timestamp

### Event Query Endpoints

#### GET /events

List events with optional filtering:

Query parameters:
- `entity_type` (optional): Filter by entity type (assignment, attempt, task)
- `entity_id` (optional): Filter by specific entity UUID
- `event_type` (optional): Filter by event type (created, claimed, completed, failed, etc.)
- `node_id` (optional): Filter by acting node
- `limit` (optional, default 100, max 1000): Result limit
- `offset` (optional, default 0): Pagination offset

Response:
```json
{
  "events": [
    {
      "event_id": "<uuid>",
      "event_type": "claimed",
      "entity_type": "assignment",
      "entity_id": "<uuid>",
      "node_id": "<uuid>",
      "previous_state": {"status": "assigned"},
      "current_state": {"status": "claimed"},
      "metadata": {"action": "assignment_claimed"},
      "created_at": "2026-09-17T08:47:00Z"
    }
  ],
  "count": <number>,
  "offset": <number>,
  "limit": <number>
}
```

#### GET /events/{event_id}

Retrieve specific event by ID:

Response: Single event object with full details.

#### GET /audit/{entity_type}/{entity_id}

Get complete chronological audit trail for an entity:

Path parameters:
- `entity_type`: Type of entity (assignment, attempt, task)
- `entity_id`: UUID of entity

Query parameters:
- `limit` (optional, default 100): Maximum events to return

Response:
```json
{
  "entity_type": "assignment",
  "entity_id": "<uuid>",
  "events": [
    {"event_type": "created", "previous_state": null, "current_state": {"status": "assigned"}, "created_at": "..."},
    {"event_type": "claimed", "previous_state": {"status": "assigned"}, "current_state": {"status": "claimed"}, "created_at": "..."}
  ],
  "total_events": <number>
}
```

### Helper Function: record_event()

Internal utility for event recording:

```python
record_event(
    conn,  # Active database connection
    event_type,  # Type of event
    entity_type,  # Type of entity affected
    entity_id,  # UUID of entity
    node_id=None,  # Optional node UUID
    previous_state=None,  # State before transition
    current_state=None,  # State after transition
    metadata=None  # Event metadata dict
)
```

Used internally by all lifecycle endpoints.

### Event-Based History Features

1. **Complete Audit Trail**: Every state transition recorded with before/after states
2. **Node Accountability**: All events linked to acting node when applicable
3. **Temporal Ordering**: Events queryable by timestamp for timeline reconstruction
4. **Metadata Tracking**: Action-specific details (reason for failure, quality scores, etc.)
5. **Filtering**: Events queryable by entity, type, node, or time
6. **Foundation for Learning**: Event history enables pattern analysis and AI learning

### Complete Lifecycle Test

Test script: `tests/test_section3_events.py`

Verifies:
1. Event recording during full lifecycle
2. Event table populated with all transitions
3. Event query endpoints functional
4. Filtering by entity_type, entity_id, event_type
5. Audit trail generation
6. State transitions captured correctly
7. Metadata properly recorded
8. Temporal ordering maintained

## Section 2 Completed (Previous)

### Assignment creation

Existing endpoint:

`POST /assignments`

Creates an assignment for a task/node.

### Assignment claim

Endpoint:

`POST /assignments/{assignment_id}/claim`

Behaviour:

- validates assignment
- validates node
- requires assignment status `assigned`
- changes assignment to `claimed`
- records `claimed_at`
- changes task to `running`
- records task `started_at` if not already set
- changes node to `busy`

This has been tested successfully on the live VPS.

### Attempt creation

Endpoint:

`POST /assignments/{assignment_id}/attempts`

Behaviour:

- validates assignment
- validates node
- requires assignment status `claimed`
- creates an attempt
- increments assignment attempt count
- starts attempt with status `running`

This has been tested successfully on the live VPS.

### Result submission

Endpoint:

`POST /attempts/{attempt_id}/result`

Behaviour:

- validates attempt exists
- validates node matches
- requires attempt status `running`
- creates a result record
- records result, quality_score, and timestamp
- updates attempt to `completed` with completed_at
- preserves attempt history

Payload:
- `node_id` (required): UUID of node submitting result
- `result` (optional): dict of result data
- `quality_score` (optional): numeric quality assessment

### Observation recording

Endpoint:

`POST /attempts/{attempt_id}/observations`

Behaviour:

- validates attempt exists
- validates node matches
- creates an observation record
- supports source and confidence metadata
- can link to a result where appropriate
- recorded with timestamp

Payload:
- `node_id` (required): UUID of observing node
- `observation_type` (required): string classification
- `content` (optional): dict of observation data
- `source` (optional): string source identifier
- `confidence` (optional): numeric confidence 0-1
- `result_id` (optional): UUID linking to result

### Assignment completion

Endpoint:

`POST /assignments/{assignment_id}/complete`

Behaviour:

- validates assignment exists
- validates node matches
- requires assignment status `claimed`
- updates assignment to `completed` with completed_at
- updates associated task to `completed` with completed_at
- returns node to `available` status

Payload:
- `node_id` (required): UUID of node completing work

### Attempt failure handling

Endpoint:

`POST /attempts/{attempt_id}/fail`

Behaviour:

- validates attempt exists
- validates node matches
- requires attempt status `running`
- updates attempt to `failed` with completed_at
- returns node to `available` for reassignment
- preserves all attempt/result/observation history

Payload:
- `node_id` (required): UUID of node
- `reason` (optional): string failure reason

### Assignment failure handling

Endpoint:

`POST /assignments/{assignment_id}/fail`

Behaviour:

- validates assignment exists
- validates node matches
- requires assignment status `assigned` or `claimed`
- updates assignment to `failed` with completed_at
- updates associated task to `failed` with completed_at (if not already completed)
- returns node to `available` for reassignment
- preserves all history and attempt records

Payload:
- `node_id` (required): UUID of node
- `reason` (optional): string failure reason

### Complete lifecycle test

Test script: `tests/test_section2_lifecycle.py`

Verifies end-to-end workflow:
1. Create workflow, task, node, assignment
2. Claim assignment
3. Create attempt
4. Submit result
5. Create observation
6. Complete assignment
7. Verify all state transitions
8. Verify database consistency

Test confirms:
- Assignment status progression: assigned → claimed → completed
- Task status progression: pending → running → completed
- Node status: available → busy → available
- Result, attempt, and observation records created
- All timestamps recorded
- No data loss in lifecycle

---

## Current Live Test Data

Clean worker lifecycle test:

Node:

`cea1feee-950d-4eeb-a586-cec64428ebf2`

Assignment:

`fb006371-b5ba-41ce-bf29-42762653daba`

Task:

`c78148e7-434b-44ff-a8ef-ff006075aaa3`

Latest test attempt:

`f0637df0-acf8-45ff-8373-b7ba0ebe7dc1`

Latest attempt number:

`1`

Latest attempt status:

`running`

The test assignment/task/node are currently part of the live test state.

---

## Git History

Important completed commits:

`1b50bae` — Add assignment claim lifecycle

`d3a40fe` — Add task attempt lifecycle

Both were pushed successfully to GitHub.

---

## Current Code

API:

`fabric/api/main.py`

Worker/orchestration API:

`fabric/api/orchestration.py`

Current orchestration API includes:

- workflow creation
- task creation
- task dependency creation
- assignment creation
- assignment claim
- attempt creation

---

## Deployment

API deployment script:

`scripts/deploy-api.sh`

Normal deployment command:

```bash
cd ~/Learning-System && ./scripts/deploy-api.sh
