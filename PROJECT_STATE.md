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

SECTION 2 — Worker / Assignment Lifecycle

Objective:

Create the complete lifecycle allowing an AI worker/node to receive work, claim it, execute attempts, record results and observations, and complete or fail the assignment.

Required lifecycle:

assignment
→ claim
→ attempt
→ result
→ observations
→ complete/fail
→ task/node state updates

---

## Database

PostgreSQL is already available on the VPS.

Foundation migration:

`migrations/001_foundation.sql`

Learning Fabric core migration:

`migrations/002_learning_fabric_core.sql`

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
- events

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

## Section 2 Completed

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
