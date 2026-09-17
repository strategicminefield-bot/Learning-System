import os
import uuid
import json
import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

router = APIRouter()
DATABASE_URL = os.environ["DATABASE_URL"]

def record_event(conn, event_type, entity_type, entity_id, node_id=None, previous_state=None, current_state=None, metadata=None):
    """Record an event to the audit_events table. Call within an active transaction."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_events
            (event_type, entity_type, entity_id, node_id, previous_state, current_state, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            RETURNING event_id
            """,
            (
                event_type,
                entity_type,
                entity_id,
                node_id,
                Jsonb(previous_state) if previous_state else None,
                Jsonb(current_state) if current_state else None,
                Jsonb(metadata) if metadata else Jsonb({}),
            )
        )
        return cur.fetchone()[0]

class WorkflowIn(BaseModel):
    request_id: str
    workflow_type: str = "general"
    objective: dict = Field(default_factory=dict)

class TaskIn(BaseModel):
    workflow_id: str
    task_type: str
    specification: dict = Field(default_factory=dict)
    priority: int = 0
    parent_task_id: str | None = None

class DependencyIn(BaseModel):
    depends_on_task_id: str
    dependency_type: str = "blocks"

class AssignmentIn(BaseModel):
    task_id: str
    node_id: str

def as_uuid(value: str, field: str):
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {field}")
@router.post("/workflows")
def create_workflow(workflow: WorkflowIn):
    request_id = as_uuid(workflow.request_id, "request_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT request_id FROM requests WHERE request_id = %s", (request_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Request not found")

            cur.execute(
                """
                INSERT INTO workflows (request_id, workflow_type, objective)
                VALUES (%s, %s, %s)
                RETURNING workflow_id
                """,
                (request_id, workflow.workflow_type, Jsonb(workflow.objective)),
            )
            workflow_id = cur.fetchone()[0]

            cur.execute("UPDATE requests SET status = 'queued' WHERE request_id = %s", (request_id,))

        conn.commit()

    return {"status": "created", "workflow_id": str(workflow_id)}
@router.post("/tasks")
def create_task(task: TaskIn):
    workflow_id = as_uuid(task.workflow_id, "workflow_id")
    parent_task_id = as_uuid(task.parent_task_id, "parent_task_id") if task.parent_task_id else None

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT workflow_id FROM workflows WHERE workflow_id = %s", (workflow_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Workflow not found")

            if parent_task_id:
                cur.execute("SELECT task_id FROM tasks WHERE task_id = %s", (parent_task_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Parent task not found")

            cur.execute(
                """INSERT INTO tasks
                   (workflow_id, parent_task_id, task_type, specification, priority)
                   VALUES (%s, %s, %s, %s, %s) RETURNING task_id""",
                (workflow_id, parent_task_id, task.task_type, Jsonb(task.specification), task.priority),
            )
            task_id = cur.fetchone()[0]

        conn.commit()

    return {"status": "created", "task_id": str(task_id), "workflow_id": str(workflow_id)}
@router.post("/tasks/{task_id}/dependencies")
def add_dependency(task_id: str, dependency: DependencyIn):
    task_uuid = as_uuid(task_id, "task_id")
    depends_uuid = as_uuid(dependency.depends_on_task_id, "depends_on_task_id")

    if task_uuid == depends_uuid:
        raise HTTPException(status_code=400, detail="task cannot depend on itself")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT workflow_id FROM tasks WHERE task_id = %s", (task_uuid,))
            task = cur.fetchone()

            cur.execute("SELECT workflow_id FROM tasks WHERE task_id = %s", (depends_uuid,))
            dependency_task = cur.fetchone()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            if not dependency_task:
                raise HTTPException(status_code=404, detail="Dependency task not found")

            if task[0] != dependency_task[0]:
                raise HTTPException(status_code=400, detail="dependency must belong to same workflow")

            cur.execute(
                """INSERT INTO task_dependencies
                   (task_id, depends_on_task_id, dependency_type)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (task_id, depends_on_task_id) DO NOTHING""",
                (task_uuid, depends_uuid, dependency.dependency_type),
            )

        conn.commit()

    return {"status": "created", "task_id": str(task_uuid), "depends_on_task_id": str(depends_uuid)}
@router.post("/assignments")
def create_assignment(assignment: AssignmentIn):
    task_uuid = as_uuid(assignment.task_id, "task_id")
    node_uuid = as_uuid(assignment.node_id, "node_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM tasks WHERE task_id = %s", (task_uuid,))
            task = cur.fetchone()

            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            if task[0] != "pending":
                raise HTTPException(status_code=409, detail=f"task is {task[0]}, not pending")

            cur.execute("SELECT status FROM nodes WHERE node_id = %s", (node_uuid,))
            node = cur.fetchone()

            if not node:
                raise HTTPException(status_code=404, detail="Node not found")
            if node[0] != "available":
                raise HTTPException(status_code=409, detail=f"node is {node[0]}, not available")

            cur.execute("SELECT 1 FROM task_dependencies d JOIN tasks dt ON dt.task_id = d.depends_on_task_id WHERE d.task_id = %s AND dt.status <> 'completed' LIMIT 1", (task_uuid,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="task dependencies are not complete")

            cur.execute("INSERT INTO assignments (task_id, node_id, status) VALUES (%s, %s, 'assigned') RETURNING assignment_id", (task_uuid, node_uuid))
            assignment_id = cur.fetchone()[0]
            
            # Record assignment created event
            record_event(
                conn,
                event_type="created",
                entity_type="assignment",
                entity_id=assignment_id,
                node_id=node_uuid,
                previous_state=None,
                current_state={"status": "assigned", "task_id": str(task_uuid)},
                metadata={"action": "assignment_created", "task_id": str(task_uuid)}
            )

        conn.commit()

    return {"status": "assigned", "assignment_id": str(assignment_id), "task_id": str(task_uuid), "node_id": str(node_uuid)}


@router.post("/assignments/{assignment_id}/claim")
def claim_assignment(assignment_id: str, payload: dict):
    assignment_uuid = as_uuid(assignment_id, "assignment_id")
    node_uuid = as_uuid(payload["node_id"], "node_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id, node_id, status FROM assignments "
                "WHERE assignment_id = %s FOR UPDATE",
                (assignment_uuid,),
            )
            assignment = cur.fetchone()

            if not assignment:
                raise HTTPException(status_code=404, detail="assignment not found")
            if assignment[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if assignment[2] != "assigned":
                raise HTTPException(status_code=409, detail="not claimable")

            cur.execute(
                "UPDATE assignments SET status='claimed', claimed_at=now() "
                "WHERE assignment_id=%s",
                (assignment_uuid,),
            )
            cur.execute(
                "UPDATE tasks SET status='running', started_at=COALESCE(started_at,now()) "
                "WHERE task_id=%s",
                (assignment[0],),
            )
            cur.execute(
                "UPDATE nodes SET status='busy' WHERE node_id=%s",
                (node_uuid,),
            )
            
            # Record claim event
            record_event(
                conn,
                event_type="claimed",
                entity_type="assignment",
                entity_id=assignment_uuid,
                node_id=node_uuid,
                previous_state={"status": "assigned"},
                current_state={"status": "claimed"},
                metadata={"action": "assignment_claimed"}
            )

        conn.commit()

    return {"status": "claimed", "assignment_id": str(assignment_uuid)}


@router.post("/assignments/{assignment_id}/attempts")
def create_attempt(assignment_id: str, payload: dict):
    assignment_uuid = as_uuid(assignment_id, "assignment_id")
    node_uuid = as_uuid(payload["node_id"], "node_id")
    attempt_id = uuid.uuid4()

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id, node_id, status, attempt_count "
                "FROM assignments WHERE assignment_id=%s",
                (assignment_uuid,),
            )
            assignment = cur.fetchone()

            if not assignment:
                raise HTTPException(status_code=404, detail="assignment not found")
            if assignment[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if assignment[2] != "claimed":
                raise HTTPException(status_code=409, detail="assignment not claimed")

            number = assignment[3] + 1

            cur.execute(
                "INSERT INTO attempts "
                "(attempt_id, task_id, assignment_id, node_id, attempt_number, method, status, started_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,'running',now())",
                (
                    attempt_id, assignment[0], assignment_uuid,
                    node_uuid, number, Jsonb(payload.get("method", {}))
                ),
            )

            cur.execute(
                "UPDATE assignments SET attempt_count=attempt_count+1 "
                "WHERE assignment_id=%s",
                (assignment_uuid,),
            )
            
            # Record attempt creation event
            record_event(
                conn,
                event_type="created",
                entity_type="attempt",
                entity_id=attempt_id,
                node_id=node_uuid,
                previous_state=None,
                current_state={"status": "running", "attempt_number": number},
                metadata={"action": "attempt_created", "attempt_number": number, "assignment_id": str(assignment_uuid)}
            )

        conn.commit()

    return {
        "status": "running",
        "attempt_id": str(attempt_id),
        "attempt_number": number,
    }


class ResultIn(BaseModel):
    node_id: str
    result: dict = Field(default_factory=dict)
    quality_score: float | None = None


@router.post("/attempts/{attempt_id}/result")
def submit_attempt_result(attempt_id: str, payload: ResultIn):
    attempt_uuid = as_uuid(attempt_id, "attempt_id")
    node_uuid = as_uuid(payload.node_id, "node_id")

    result_id = uuid.uuid4()

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Validate attempt exists and is running
            cur.execute(
                "SELECT task_id, node_id, status, assignment_id "
                "FROM attempts WHERE attempt_id=%s FOR UPDATE",
                (attempt_uuid,),
            )
            attempt = cur.fetchone()

            if not attempt:
                raise HTTPException(status_code=404, detail="attempt not found")
            if attempt[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if attempt[2] != "running":
                raise HTTPException(status_code=409, detail="attempt not running")

            task_id, _, _, _ = attempt

            # Create result record
            cur.execute(
                "INSERT INTO results "
                "(result_id, attempt_id, task_id, node_id, result, quality_score, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'recorded', now())",
                (
                    result_id,
                    attempt_uuid,
                    task_id,
                    node_uuid,
                    Jsonb(payload.result),
                    payload.quality_score,
                ),
            )

            # Complete the attempt
            cur.execute(
                "UPDATE attempts SET status='completed', completed_at=now() "
                "WHERE attempt_id=%s",
                (attempt_uuid,),
            )
            
            # Record result event
            record_event(
                conn,
                event_type="result_submitted",
                entity_type="attempt",
                entity_id=attempt_uuid,
                node_id=node_uuid,
                previous_state={"status": "running"},
                current_state={"status": "completed"},
                metadata={"action": "result_recorded", "result_id": str(result_id), "quality_score": payload.quality_score}
            )
            
            # Update worker metrics
            cur.execute(
                """
                UPDATE worker_metrics
                SET successful_attempts = COALESCE(successful_attempts, 0) + 1,
                    total_attempts = COALESCE(total_attempts, 0) + 1,
                    average_quality_score = (
                        CASE WHEN COALESCE(total_attempts, 0) > 0
                        THEN (COALESCE(average_quality_score, 0) * COALESCE(total_attempts, 0) + %s) / (COALESCE(total_attempts, 0) + 1)
                        ELSE %s
                        END
                    ),
                    updated_at = now()
                WHERE node_id=%s
                """,
                (payload.quality_score or 0.5, payload.quality_score or 0.5, node_uuid)
            )

        conn.commit()

    return {
        "status": "recorded",
        "result_id": str(result_id),
        "attempt_id": str(attempt_uuid),
    }


class ObservationIn(BaseModel):
    node_id: str
    observation_type: str
    content: dict = Field(default_factory=dict)
    source: str | None = None
    confidence: float | None = None
    result_id: str | None = None


@router.post("/attempts/{attempt_id}/observations")
def create_observation(attempt_id: str, payload: ObservationIn):
    attempt_uuid = as_uuid(attempt_id, "attempt_id")
    node_uuid = as_uuid(payload.node_id, "node_id")
    result_uuid = as_uuid(payload.result_id, "result_id") if payload.result_id else None

    observation_id = uuid.uuid4()

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Validate attempt exists
            cur.execute(
                "SELECT task_id, node_id, status FROM attempts WHERE attempt_id=%s",
                (attempt_uuid,),
            )
            attempt = cur.fetchone()

            if not attempt:
                raise HTTPException(status_code=404, detail="attempt not found")
            if attempt[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")

            # If result_id provided, validate it exists
            if result_uuid:
                cur.execute(
                    "SELECT result_id FROM results WHERE result_id=%s",
                    (result_uuid,),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="result not found")

            # Create observation
            cur.execute(
                "INSERT INTO observations "
                "(observation_id, attempt_id, result_id, observation_type, content, source, confidence, observed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, now())",
                (
                    observation_id,
                    attempt_uuid,
                    result_uuid,
                    payload.observation_type,
                    Jsonb(payload.content),
                    payload.source,
                    payload.confidence,
                ),
            )

        conn.commit()

    return {
        "status": "created",
        "observation_id": str(observation_id),
        "attempt_id": str(attempt_uuid),
    }


class CompletionIn(BaseModel):
    node_id: str


@router.post("/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: str, payload: CompletionIn):
    assignment_uuid = as_uuid(assignment_id, "assignment_id")
    node_uuid = as_uuid(payload.node_id, "node_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Validate assignment and node
            cur.execute(
                "SELECT task_id, node_id, status FROM assignments "
                "WHERE assignment_id=%s FOR UPDATE",
                (assignment_uuid,),
            )
            assignment = cur.fetchone()

            if not assignment:
                raise HTTPException(status_code=404, detail="assignment not found")
            if assignment[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if assignment[2] != "claimed":
                raise HTTPException(status_code=409, detail="assignment not claimable")

            task_id = assignment[0]

            # Complete the assignment
            cur.execute(
                "UPDATE assignments SET status='completed', completed_at=now() "
                "WHERE assignment_id=%s",
                (assignment_uuid,),
            )

            # Complete the task
            cur.execute(
                "UPDATE tasks SET status='completed', completed_at=now() "
                "WHERE task_id=%s",
                (task_id,),
            )

            # Return node to available
            cur.execute(
                "UPDATE nodes SET status='available' WHERE node_id=%s",
                (node_uuid,),
            )
            
            # Record completion event
            record_event(
                conn,
                event_type="completed",
                entity_type="assignment",
                entity_id=assignment_uuid,
                node_id=node_uuid,
                previous_state={"status": "claimed"},
                current_state={"status": "completed"},
                metadata={"action": "assignment_completed", "task_id": str(task_id)}
            )
            
            # Update worker metrics - increment completed tasks
            cur.execute(
                """
                UPDATE worker_metrics
                SET tasks_completed = COALESCE(tasks_completed, 0) + 1,
                    updated_at = now()
                WHERE node_id=%s
                """,
                (node_uuid,)
            )

        conn.commit()

    return {
        "status": "completed",
        "assignment_id": str(assignment_uuid),
        "task_id": str(task_id),
    }


class FailureIn(BaseModel):
    node_id: str
    reason: str = "unknown"


@router.post("/attempts/{attempt_id}/fail")
def fail_attempt(attempt_id: str, payload: FailureIn):
    attempt_uuid = as_uuid(attempt_id, "attempt_id")
    node_uuid = as_uuid(payload.node_id, "node_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Validate attempt
            cur.execute(
                "SELECT task_id, node_id, status, assignment_id FROM attempts "
                "WHERE attempt_id=%s FOR UPDATE",
                (attempt_uuid,),
            )
            attempt = cur.fetchone()

            if not attempt:
                raise HTTPException(status_code=404, detail="attempt not found")
            if attempt[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if attempt[2] not in ("running",):
                raise HTTPException(status_code=409, detail="attempt not running")

            task_id, _, _, assignment_id = attempt

            # Mark attempt as failed
            cur.execute(
                "UPDATE attempts SET status='failed', completed_at=now() "
                "WHERE attempt_id=%s",
                (attempt_uuid,),
            )

            # Return node to available (remains available for reassignment)
            cur.execute(
                "UPDATE nodes SET status='available' WHERE node_id=%s",
                (node_uuid,),
            )
            
            # Record failure event
            record_event(
                conn,
                event_type="failed",
                entity_type="attempt",
                entity_id=attempt_uuid,
                node_id=node_uuid,
                previous_state={"status": "running"},
                current_state={"status": "failed"},
                metadata={"action": "attempt_failed", "reason": payload.reason}
            )

        conn.commit()

    return {
        "status": "failed",
        "attempt_id": str(attempt_uuid),
        "reason": payload.reason,
    }


@router.post("/assignments/{assignment_id}/fail")
def fail_assignment(assignment_id: str, payload: FailureIn):
    assignment_uuid = as_uuid(assignment_id, "assignment_id")
    node_uuid = as_uuid(payload.node_id, "node_id")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Validate assignment
            cur.execute(
                "SELECT task_id, node_id, status FROM assignments "
                "WHERE assignment_id=%s FOR UPDATE",
                (assignment_uuid,),
            )
            assignment = cur.fetchone()

            if not assignment:
                raise HTTPException(status_code=404, detail="assignment not found")
            if assignment[1] != node_uuid:
                raise HTTPException(status_code=403, detail="wrong node")
            if assignment[2] not in ("assigned", "claimed"):
                raise HTTPException(status_code=409, detail="assignment not in claimable state")

            task_id = assignment[0]

            # Mark assignment as failed
            cur.execute(
                "UPDATE assignments SET status='failed', completed_at=now() "
                "WHERE assignment_id=%s",
                (assignment_uuid,),
            )

            # Mark task as failed
            cur.execute(
                "UPDATE tasks SET status='failed', completed_at=now() "
                "WHERE task_id=%s AND status IN ('pending', 'running')",
                (task_id,),
            )

            # Return node to available
            cur.execute(
                "UPDATE nodes SET status='available' WHERE node_id=%s",
                (node_uuid,),
            )
            
            # Record failure event
            record_event(
                conn,
                event_type="failed",
                entity_type="assignment",
                entity_id=assignment_uuid,
                node_id=node_uuid,
                previous_state={"status": assignment[2]},
                current_state={"status": "failed"},
                metadata={"action": "assignment_failed", "reason": payload.reason, "task_id": str(task_id)}
            )
            
            # Update worker metrics - increment failed tasks
            cur.execute(
                """
                UPDATE worker_metrics
                SET tasks_failed = COALESCE(tasks_failed, 0) + 1,
                    updated_at = now()
                WHERE node_id=%s
                """,
                (node_uuid,)
            )

        conn.commit()

    return {
        "status": "failed",
        "assignment_id": str(assignment_uuid),
        "task_id": str(task_id),
        "reason": payload.reason,
    }


# Event Query Endpoints (Section 3)

class EventResponse(BaseModel):
    event_id: str
    event_type: str
    entity_type: str
    entity_id: str
    node_id: str | None
    previous_state: dict | None
    current_state: dict | None
    metadata: dict
    created_at: str


@router.get("/events")
def list_events(
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    event_type: str | None = Query(None),
    node_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List events with optional filtering."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            where_clauses = []
            params = []
            
            if entity_type:
                where_clauses.append("entity_type = %s")
                params.append(entity_type)
            if entity_id:
                entity_uuid = as_uuid(entity_id, "entity_id")
                where_clauses.append("entity_id = %s")
                params.append(entity_uuid)
            if event_type:
                where_clauses.append("event_type = %s")
                params.append(event_type)
            if node_id:
                node_uuid = as_uuid(node_id, "node_id")
                where_clauses.append("node_id = %s")
                params.append(node_uuid)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            cur.execute(
                f"""
                SELECT event_id, event_type, entity_type, entity_id, node_id,
                       previous_state, current_state, metadata, created_at
                FROM audit_events
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset]
            )
            
            events = []
            for row in cur.fetchall():
                event_id, event_type, entity_type, entity_id, node_id, prev_state, curr_state, metadata, created_at = row
                events.append({
                    "event_id": str(event_id),
                    "event_type": event_type,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id),
                    "node_id": str(node_id) if node_id else None,
                    "previous_state": dict(prev_state) if prev_state else None,
                    "current_state": dict(curr_state) if curr_state else None,
                    "metadata": dict(metadata) if metadata else {},
                    "created_at": created_at.isoformat() if created_at else None,
                })
    
    return {"events": events, "count": len(events), "offset": offset, "limit": limit}


@router.get("/events/{event_id}")
def get_event(event_id: str):
    """Get a specific event by ID."""
    event_uuid = as_uuid(event_id, "event_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, event_type, entity_type, entity_id, node_id,
                       previous_state, current_state, metadata, created_at
                FROM audit_events
                WHERE event_id = %s
                """,
                (event_uuid,)
            )
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Event not found")
            
            event_id, event_type, entity_type, entity_id, node_id, prev_state, curr_state, metadata, created_at = row
            
    return {
        "event_id": str(event_id),
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "node_id": str(node_id) if node_id else None,
        "previous_state": dict(prev_state) if prev_state else None,
        "current_state": dict(curr_state) if curr_state else None,
        "metadata": dict(metadata) if metadata else {},
        "created_at": created_at.isoformat() if created_at else None,
    }


@router.get("/audit/{entity_type}/{entity_id}")
def audit_trail(entity_type: str, entity_id: str, limit: int = Query(100, ge=1, le=1000)):
    """Get complete audit trail for an entity (assignment, attempt, task, etc.)."""
    entity_uuid = as_uuid(entity_id, "entity_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_id, event_type, entity_type, entity_id, node_id,
                       previous_state, current_state, metadata, created_at
                FROM audit_events
                WHERE entity_type = %s AND entity_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (entity_type, entity_uuid, limit)
            )
            
            events = []
            for row in cur.fetchall():
                event_id, event_type, ent_type, ent_id, node_id, prev_state, curr_state, metadata, created_at = row
                events.append({
                    "event_id": str(event_id),
                    "event_type": event_type,
                    "previous_state": dict(prev_state) if prev_state else None,
                    "current_state": dict(curr_state) if curr_state else None,
                    "metadata": dict(metadata) if metadata else {},
                    "created_at": created_at.isoformat() if created_at else None,
                })
    
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_uuid),
        "events": events,
        "total_events": len(events),
    }


# Worker Status Endpoints (Section 4)

class WorkerStatusUpdate(BaseModel):
    status: str
    reason: str | None = None

class WorkerCapabilityIn(BaseModel):
    capability_name: str
    capability_version: str | None = None
    enabled: bool = True

@router.post("/workers/{node_id}/status")
def update_worker_status(node_id: str, payload: WorkerStatusUpdate):
    """Update worker status and record status history."""
    node_uuid = as_uuid(node_id, "node_id")
    
    if payload.status not in ("available", "busy", "unavailable", "error"):
        raise HTTPException(status_code=400, detail="Invalid status")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get current status
            cur.execute("SELECT status FROM nodes WHERE node_id=%s", (node_uuid,))
            node = cur.fetchone()
            
            if not node:
                raise HTTPException(status_code=404, detail="Node not found")
            
            previous_status = node[0]
            
            # Update node status
            cur.execute(
                "UPDATE nodes SET status=%s WHERE node_id=%s",
                (payload.status, node_uuid)
            )
            
            # Record status history
            cur.execute(
                """
                INSERT INTO worker_status_history
                (node_id, previous_status, current_status, reason, created_at)
                VALUES (%s, %s, %s, %s, now())
                """,
                (node_uuid, previous_status, payload.status, payload.reason)
            )
            
            # Update heartbeat in metrics
            cur.execute(
                """
                INSERT INTO worker_metrics (node_id, last_heartbeat, updated_at)
                VALUES (%s, now(), now())
                ON CONFLICT (node_id) DO UPDATE SET last_heartbeat=now(), updated_at=now()
                """,
                (node_uuid,)
            )
        
        conn.commit()
    
    return {
        "status": "updated",
        "node_id": str(node_uuid),
        "previous_status": previous_status,
        "current_status": payload.status
    }

@router.get("/workers/{node_id}")
def get_worker_status(node_id: str):
    """Get worker status and metrics."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get node info
            cur.execute(
                "SELECT node_id, node_type, status, created_at FROM nodes WHERE node_id=%s",
                (node_uuid,)
            )
            node = cur.fetchone()
            
            if not node:
                raise HTTPException(status_code=404, detail="Node not found")
            
            node_id_ret, node_type, status, created_at = node
            
            # Get metrics
            cur.execute(
                """
                SELECT tasks_completed, tasks_failed, average_quality_score,
                       successful_attempts, total_attempts, last_heartbeat, uptime_seconds
                FROM worker_metrics WHERE node_id=%s
                """,
                (node_uuid,)
            )
            metrics_row = cur.fetchone()
            
            if metrics_row:
                metrics = {
                    "tasks_completed": metrics_row[0] or 0,
                    "tasks_failed": metrics_row[1] or 0,
                    "average_quality_score": float(metrics_row[2]) if metrics_row[2] else None,
                    "successful_attempts": metrics_row[3] or 0,
                    "total_attempts": metrics_row[4] or 0,
                    "last_heartbeat": metrics_row[5].isoformat() if metrics_row[5] else None,
                    "uptime_seconds": metrics_row[6] or 0,
                }
            else:
                metrics = None
            
            # Get capabilities
            cur.execute(
                """
                SELECT capability_name, capability_version, enabled, performance_rating, last_used
                FROM worker_capabilities WHERE node_id=%s ORDER BY capability_name
                """,
                (node_uuid,)
            )
            capabilities = []
            for row in cur.fetchall():
                capabilities.append({
                    "name": row[0],
                    "version": row[1],
                    "enabled": row[2],
                    "performance_rating": float(row[3]) if row[3] else 1.0,
                    "last_used": row[4].isoformat() if row[4] else None
                })
    
    return {
        "node_id": str(node_id_ret),
        "node_type": node_type,
        "status": status,
        "created_at": created_at.isoformat(),
        "metrics": metrics,
        "capabilities": capabilities
    }

@router.post("/workers/{node_id}/heartbeat")
def worker_heartbeat(node_id: str):
    """Record worker heartbeat."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check node exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (node_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Node not found")
            
            # Update heartbeat
            cur.execute(
                """
                INSERT INTO worker_metrics (node_id, last_heartbeat, updated_at)
                VALUES (%s, now(), now())
                ON CONFLICT (node_id) DO UPDATE SET last_heartbeat=now(), updated_at=now()
                """,
                (node_uuid,)
            )
        
        conn.commit()
    
    return {
        "status": "heartbeat_recorded",
        "node_id": str(node_uuid),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/workers/{node_id}/capabilities")
def add_worker_capability(node_id: str, payload: WorkerCapabilityIn):
    """Add or update worker capability."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check node exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (node_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Node not found")
            
            # Insert or update capability
            cur.execute(
                """
                INSERT INTO worker_capabilities
                (node_id, capability_name, capability_version, enabled, performance_rating, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 1.0, now(), now())
                ON CONFLICT (node_id, capability_name) DO UPDATE SET
                    capability_version=EXCLUDED.capability_version,
                    enabled=EXCLUDED.enabled,
                    updated_at=now()
                """,
                (node_uuid, payload.capability_name, payload.capability_version, payload.enabled)
            )
        
        conn.commit()
    
    return {
        "status": "capability_added",
        "node_id": str(node_uuid),
        "capability": payload.capability_name
    }

@router.get("/workers")
def list_workers(status: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """List all workers with optional status filter."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT node_id, node_type, status, created_at
                    FROM nodes
                    WHERE status=%s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (status, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT node_id, node_type, status, created_at
                    FROM nodes
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
            
            workers = []
            for row in cur.fetchall():
                node_id, node_type, node_status, created_at = row
                
                # Get metrics for this node
                cur.execute(
                    "SELECT last_heartbeat FROM worker_metrics WHERE node_id=%s",
                    (node_id,)
                )
                metrics_row = cur.fetchone()
                last_heartbeat = metrics_row[0].isoformat() if metrics_row and metrics_row[0] else None
                
                workers.append({
                    "node_id": str(node_id),
                    "node_type": node_type,
                    "status": node_status,
                    "created_at": created_at.isoformat(),
                    "last_heartbeat": last_heartbeat
                })
    
    return {
        "workers": workers,
        "total": len(workers),
        "status_filter": status,
        "limit": limit
    }

@router.get("/workers/metrics/summary")
def workers_metrics_summary():
    """Get summary metrics for all workers."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Worker counts by status
            cur.execute(
                """
                SELECT status, COUNT(*) FROM nodes GROUP BY status
                """
            )
            status_counts = {row[0]: row[1] for row in cur.fetchall()}
            
            # Aggregate metrics
            cur.execute(
                """
                SELECT
                    SUM(tasks_completed) as total_completed,
                    SUM(tasks_failed) as total_failed,
                    AVG(average_quality_score) as avg_quality,
                    COUNT(*) as worker_count
                FROM worker_metrics
                """
            )
            metrics_row = cur.fetchone()
            
            aggregate = {
                "total_tasks_completed": metrics_row[0] or 0,
                "total_tasks_failed": metrics_row[1] or 0,
                "average_quality_score": float(metrics_row[2]) if metrics_row[2] else None,
                "workers_with_metrics": metrics_row[3] or 0
            }
    
    return {
        "workers_by_status": status_counts,
        "aggregate_metrics": aggregate
    }


# Task Messaging and Communication Endpoints (Section 5)

class MessageIn(BaseModel):
    recipient_node_id: str | None = None
    task_id: str | None = None
    assignment_id: str | None = None
    message_type: str
    subject: str | None = None
    content: dict = Field(default_factory=dict)
    priority: int = 0
    expires_in_seconds: int | None = None

class SubscriptionIn(BaseModel):
    topic: str
    filter_criteria: dict | None = None

@router.post("/messages/{sender_node_id}")
def send_message(sender_node_id: str, payload: MessageIn):
    """Send a message from one worker to another or broadcast to task."""
    sender_uuid = as_uuid(sender_node_id, "sender_node_id")
    recipient_uuid = as_uuid(payload.recipient_node_id, "recipient_node_id") if payload.recipient_node_id else None
    task_uuid = as_uuid(payload.task_id, "task_id") if payload.task_id else None
    assignment_uuid = as_uuid(payload.assignment_id, "assignment_id") if payload.assignment_id else None
    
    if not (recipient_uuid or task_uuid or assignment_uuid):
        raise HTTPException(status_code=400, detail="Must specify recipient, task, or assignment")
    
    message_id = uuid.uuid4()
    expires_at = None
    if payload.expires_in_seconds:
        expires_at = datetime.utcnow() + timedelta(seconds=payload.expires_in_seconds)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify sender exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (sender_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Sender node not found")
            
            # Verify recipient if specified
            if recipient_uuid:
                cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (recipient_uuid,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Recipient node not found")
            
            # Insert message
            cur.execute(
                """
                INSERT INTO messages
                (message_id, sender_node_id, recipient_node_id, task_id, assignment_id,
                 message_type, subject, content, priority, status, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, now())
                """,
                (
                    message_id, sender_uuid, recipient_uuid, task_uuid, assignment_uuid,
                    payload.message_type, payload.subject,
                    Jsonb(payload.content), payload.priority, expires_at
                )
            )
        
        conn.commit()
    
    return {
        "status": "sent",
        "message_id": str(message_id),
        "sender_node_id": str(sender_uuid),
        "recipient_node_id": str(recipient_uuid) if recipient_uuid else None,
        "task_id": str(task_uuid) if task_uuid else None
    }

@router.get("/messages/{node_id}")
def get_messages(node_id: str, status: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """Get messages for a worker."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify node exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (node_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Node not found")
            
            # Get messages
            if status:
                cur.execute(
                    """
                    SELECT message_id, sender_node_id, message_type, subject, content,
                           priority, status, read_at, created_at
                    FROM messages
                    WHERE recipient_node_id=%s AND status=%s
                    ORDER BY priority DESC, created_at DESC
                    LIMIT %s
                    """,
                    (node_uuid, status, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT message_id, sender_node_id, message_type, subject, content,
                           priority, status, read_at, created_at
                    FROM messages
                    WHERE recipient_node_id=%s
                    ORDER BY priority DESC, created_at DESC
                    LIMIT %s
                    """,
                    (node_uuid, limit)
                )
            
            messages = []
            for row in cur.fetchall():
                msg_id, sender, msg_type, subject, content, priority, msg_status, read_at, created_at = row
                messages.append({
                    "message_id": str(msg_id),
                    "sender_node_id": str(sender),
                    "message_type": msg_type,
                    "subject": subject,
                    "content": dict(content) if content else {},
                    "priority": priority,
                    "status": msg_status,
                    "read_at": read_at.isoformat() if read_at else None,
                    "created_at": created_at.isoformat()
                })
    
    return {
        "messages": messages,
        "total": len(messages),
        "node_id": str(node_uuid),
        "status_filter": status
    }

@router.post("/messages/{message_id}/read")
def mark_message_read(message_id: str):
    """Mark a message as read."""
    message_uuid = as_uuid(message_id, "message_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE messages SET read_at=now(), status='read' WHERE message_id=%s RETURNING message_id",
                (message_uuid,)
            )
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Message not found")
        
        conn.commit()
    
    return {"status": "read", "message_id": str(message_uuid)}

@router.post("/subscriptions/{node_id}")
def subscribe_to_topic(node_id: str, payload: SubscriptionIn):
    """Subscribe a worker to a topic for notifications."""
    node_uuid = as_uuid(node_id, "node_id")
    subscription_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify node exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id=%s", (node_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Node not found")
            
            # Create or update subscription
            cur.execute(
                """
                INSERT INTO message_subscriptions
                (subscription_id, node_id, topic, filter_criteria, active, created_at)
                VALUES (%s, %s, %s, %s, TRUE, now())
                ON CONFLICT (node_id, topic) DO UPDATE SET active=TRUE, subscription_id=EXCLUDED.subscription_id
                RETURNING subscription_id
                """,
                (subscription_id, node_uuid, payload.topic, Jsonb(payload.filter_criteria) if payload.filter_criteria else None)
            )
        
        conn.commit()
    
    return {
        "status": "subscribed",
        "node_id": str(node_uuid),
        "topic": payload.topic
    }

@router.get("/subscriptions/{node_id}")
def get_subscriptions(node_id: str):
    """Get all active subscriptions for a worker."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT subscription_id, topic, filter_criteria, created_at
                FROM message_subscriptions
                WHERE node_id=%s AND active=TRUE
                ORDER BY created_at
                """,
                (node_uuid,)
            )
            
            subscriptions = []
            for row in cur.fetchall():
                sub_id, topic, filters, created_at = row
                subscriptions.append({
                    "subscription_id": str(sub_id),
                    "topic": topic,
                    "filter_criteria": dict(filters) if filters else None,
                    "created_at": created_at.isoformat()
                })
    
    return {
        "subscriptions": subscriptions,
        "total": len(subscriptions),
        "node_id": str(node_uuid)
    }

@router.get("/tasks/{task_id}")
def get_task_details(task_id: str):
    """Get task details with status and related information."""
    task_uuid = as_uuid(task_id, "task_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT task_id, workflow_id, task_type, status, specification,
                       priority, created_at, started_at, completed_at
                FROM tasks
                WHERE task_id=%s
                """,
                (task_uuid,)
            )
            task_row = cur.fetchone()
            
            if not task_row:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task_id_ret, workflow_id, task_type, status, spec, priority, created_at, started_at, completed_at = task_row
            
            # Get assignments
            cur.execute(
                """
                SELECT assignment_id, node_id, status, attempt_count, created_at, claimed_at, completed_at
                FROM assignments
                WHERE task_id=%s
                ORDER BY created_at
                """,
                (task_uuid,)
            )
            
            assignments = []
            for row in cur.fetchall():
                assign_id, node_id, assign_status, attempt_count, assign_created, claimed, assign_completed = row
                assignments.append({
                    "assignment_id": str(assign_id),
                    "node_id": str(node_id),
                    "status": assign_status,
                    "attempt_count": attempt_count,
                    "created_at": assign_created.isoformat(),
                    "claimed_at": claimed.isoformat() if claimed else None,
                    "completed_at": assign_completed.isoformat() if assign_completed else None
                })
    
    return {
        "task_id": str(task_id_ret),
        "workflow_id": str(workflow_id),
        "type": task_type,
        "status": status,
        "specification": dict(spec) if spec else {},
        "priority": priority,
        "created_at": created_at.isoformat(),
        "started_at": started_at.isoformat() if started_at else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "assignments": assignments
    }

@router.post("/tasks/{task_id}/notify")
def notify_task_change(task_id: str, node_id: str | None = Query(None)):
    """Create notifications for task state changes."""
    task_uuid = as_uuid(task_id, "task_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get task info
            cur.execute(
                "SELECT task_id, status FROM tasks WHERE task_id=%s",
                (task_uuid,)
            )
            task = cur.fetchone()
            
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task_status = task[1]
            
            # Get subscribed workers
            cur.execute(
                "SELECT DISTINCT node_id FROM message_subscriptions WHERE active=TRUE"
            )
            
            notified = []
            for row in cur.fetchall():
                subscriber_node_id = row[0]
                
                # Skip if node_id filter applied and doesn't match
                if node_id and str(subscriber_node_id) != node_id:
                    continue
                
                notification_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO task_notifications
                    (notification_id, task_id, node_id, notification_type, detail, created_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    """,
                    (
                        notification_id, task_uuid, subscriber_node_id,
                        f"task_{task_status}",
                        Jsonb({"task_status": task_status, "updated_at": datetime.utcnow().isoformat()})
                    )
                )
                notified.append(str(subscriber_node_id))
        
        conn.commit()
    
    return {
        "status": "notified",
        "task_id": str(task_uuid),
        "nodes_notified": notified,
        "total_notified": len(notified)
    }

@router.get("/tasks/{task_id}/notifications")
def get_task_notifications(task_id: str, node_id: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """Get notifications for a task."""
    task_uuid = as_uuid(task_id, "task_id")
    node_uuid = as_uuid(node_id, "node_id") if node_id else None
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            if node_uuid:
                cur.execute(
                    """
                    SELECT notification_id, node_id, notification_type, detail, read_at, created_at
                    FROM task_notifications
                    WHERE task_id=%s AND node_id=%s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (task_uuid, node_uuid, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT notification_id, node_id, notification_type, detail, read_at, created_at
                    FROM task_notifications
                    WHERE task_id=%s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (task_uuid, limit)
                )
            
            notifications = []
            for row in cur.fetchall():
                notif_id, notif_node_id, notif_type, detail, read_at, created_at = row
                notifications.append({
                    "notification_id": str(notif_id),
                    "node_id": str(notif_node_id),
                    "type": notif_type,
                    "detail": dict(detail) if detail else {},
                    "read_at": read_at.isoformat() if read_at else None,
                    "created_at": created_at.isoformat()
                })
    
    return {
        "notifications": notifications,
        "total": len(notifications),
        "task_id": str(task_uuid),
        "node_filter": str(node_uuid) if node_uuid else None
    }


# Learning and Pattern Analysis Endpoints (Section 6)

@router.post("/outcomes/{task_id}")
def record_task_outcome(task_id: str, payload: dict, node_id: str = Query(...)):
    """Record task outcome for learning analysis."""
    task_uuid = as_uuid(task_id, "task_id")
    node_uuid = as_uuid(node_id, "node_id")
    
    outcome_id = uuid.uuid4()
    outcome_status = payload.get("status", "completed")
    quality_score = payload.get("quality_score", 0.5)
    execution_time = payload.get("execution_time_seconds")
    result_summary = payload.get("result_summary", {})
    learning_points = payload.get("learning_points", [])
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get task info
            cur.execute(
                "SELECT task_id, task_type FROM tasks WHERE task_id=%s",
                (task_uuid,)
            )
            task_row = cur.fetchone()
            if not task_row:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task_type = task_row[1]
            
            # Get assignment if exists
            cur.execute(
                "SELECT assignment_id FROM assignments WHERE task_id=%s AND node_id=%s LIMIT 1",
                (task_uuid, node_uuid)
            )
            assignment_row = cur.fetchone()
            assignment_uuid = assignment_row[0] if assignment_row else None
            
            # Record outcome
            cur.execute(
                """
                INSERT INTO task_outcomes
                (outcome_id, task_id, assignment_id, node_id, outcome_status,
                 quality_score, execution_time_seconds, result_summary, learning_points, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    outcome_id, task_uuid, assignment_uuid, node_uuid, outcome_status,
                    quality_score, execution_time,
                    Jsonb(result_summary), Jsonb(learning_points)
                )
            )
            
            # Update worker learning profile
            cur.execute(
                """
                INSERT INTO worker_learning
                (learning_id, node_id, task_type, skill_area, proficiency_score,
                 tasks_completed, success_rate, avg_time_seconds, quality_score, last_updated, created_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, now(), now())
                ON CONFLICT (node_id, task_type, skill_area) DO UPDATE SET
                    tasks_completed = worker_learning.tasks_completed + 1,
                    success_rate = CASE WHEN %s = 'success' THEN 
                        (worker_learning.success_rate * worker_learning.tasks_completed + 1) / (worker_learning.tasks_completed + 1)
                    ELSE
                        worker_learning.success_rate
                    END,
                    avg_time_seconds = CASE WHEN %s > 0 THEN
                        (worker_learning.avg_time_seconds * worker_learning.tasks_completed + %s) / (worker_learning.tasks_completed + 1)
                    ELSE
                        worker_learning.avg_time_seconds
                    END,
                    quality_score = (worker_learning.quality_score * worker_learning.tasks_completed + %s) / (worker_learning.tasks_completed + 1),
                    last_updated = now()
                """,
                (
                    uuid.uuid4(), node_uuid, task_type, "general",
                    0.5, quality_score, execution_time, quality_score,
                    outcome_status, execution_time, execution_time or 0, quality_score
                )
            )
        
        conn.commit()
    
    return {
        "status": "recorded",
        "outcome_id": str(outcome_id),
        "task_id": str(task_uuid),
        "node_id": str(node_uuid),
        "quality_score": quality_score
    }

@router.get("/outcomes/{node_id}")
def get_worker_outcomes(node_id: str, task_type: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """Get task outcomes for a worker."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            if task_type:
                cur.execute(
                    """
                    SELECT outcome_id, task_id, outcome_status, quality_score,
                           execution_time_seconds, result_summary, created_at
                    FROM task_outcomes
                    WHERE node_id=%s AND task_id IN (
                        SELECT task_id FROM tasks WHERE task_type=%s
                    )
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (node_uuid, task_type, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT outcome_id, task_id, outcome_status, quality_score,
                           execution_time_seconds, result_summary, created_at
                    FROM task_outcomes
                    WHERE node_id=%s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (node_uuid, limit)
                )
            
            outcomes = []
            for row in cur.fetchall():
                outcome_id, task_id, status, quality, exec_time, result, created_at = row
                outcomes.append({
                    "outcome_id": str(outcome_id),
                    "task_id": str(task_id),
                    "status": status,
                    "quality_score": float(quality) if quality else None,
                    "execution_time_seconds": exec_time,
                    "result_summary": dict(result) if result else {},
                    "created_at": created_at.isoformat()
                })
    
    return {
        "outcomes": outcomes,
        "total": len(outcomes),
        "node_id": str(node_uuid),
        "task_type_filter": task_type
    }

@router.get("/learning/{node_id}")
def get_worker_learning_profile(node_id: str):
    """Get worker learning profile and skill development."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT learning_id, task_type, skill_area, proficiency_score,
                       tasks_completed, success_rate, avg_time_seconds, quality_score, last_updated
                FROM worker_learning
                WHERE node_id=%s
                ORDER BY proficiency_score DESC
                """,
                (node_uuid,)
            )
            
            skills = []
            for row in cur.fetchall():
                learning_id, task_type, skill_area, prof_score, tasks, success, avg_time, quality, updated = row
                skills.append({
                    "learning_id": str(learning_id),
                    "task_type": task_type,
                    "skill_area": skill_area,
                    "proficiency_score": float(prof_score) if prof_score else 0.5,
                    "tasks_completed": tasks,
                    "success_rate": float(success) if success else None,
                    "avg_time_seconds": avg_time,
                    "quality_score": float(quality) if quality else None,
                    "last_updated": updated.isoformat() if updated else None
                })
    
    return {
        "node_id": str(node_uuid),
        "skills": skills,
        "total_skills": len(skills)
    }

@router.get("/patterns")
def get_result_patterns(task_type: str | None = Query(None), min_success_rate: float = Query(0.0, ge=0, le=1)):
    """Get discovered patterns from task results."""
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            if task_type:
                cur.execute(
                    """
                    SELECT pattern_id, task_type, pattern_name, pattern_rule,
                           success_rate, occurrence_count, first_seen, last_seen
                    FROM result_patterns
                    WHERE task_type=%s AND success_rate >= %s
                    ORDER BY success_rate DESC, occurrence_count DESC
                    """,
                    (task_type, min_success_rate)
                )
            else:
                cur.execute(
                    """
                    SELECT pattern_id, task_type, pattern_name, pattern_rule,
                           success_rate, occurrence_count, first_seen, last_seen
                    FROM result_patterns
                    WHERE success_rate >= %s
                    ORDER BY success_rate DESC, occurrence_count DESC
                    """,
                    (min_success_rate,)
                )
            
            patterns = []
            for row in cur.fetchall():
                pattern_id, task_type_val, name, rule, success, count, first, last = row
                patterns.append({
                    "pattern_id": str(pattern_id),
                    "task_type": task_type_val,
                    "pattern_name": name,
                    "pattern_rule": dict(rule) if rule else {},
                    "success_rate": float(success) if success else None,
                    "occurrence_count": count,
                    "first_seen": first.isoformat(),
                    "last_seen": last.isoformat() if last else None
                })
    
    return {
        "patterns": patterns,
        "total": len(patterns),
        "task_type_filter": task_type,
        "min_success_rate": min_success_rate
    }

@router.post("/patterns")
def create_pattern(payload: dict):
    """Create a new result pattern from observed outcomes."""
    pattern_id = uuid.uuid4()
    task_type = payload.get("task_type")
    pattern_name = payload.get("pattern_name")
    pattern_rule = payload.get("pattern_rule", {})
    success_rate = payload.get("success_rate", 0.5)
    occurrence_count = payload.get("occurrence_count", 1)
    
    if not task_type or not pattern_name:
        raise HTTPException(status_code=400, detail="task_type and pattern_name required")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO result_patterns
                (pattern_id, task_type, pattern_name, pattern_rule, success_rate,
                 occurrence_count, first_seen, last_seen, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now(), now(), now())
                """,
                (
                    pattern_id, task_type, pattern_name,
                    Jsonb(pattern_rule), success_rate, occurrence_count
                )
            )
        
        conn.commit()
    
    return {
        "status": "created",
        "pattern_id": str(pattern_id),
        "task_type": task_type,
        "pattern_name": pattern_name
    }

@router.get("/insights/{node_id}")
def get_worker_insights(node_id: str, actionable_only: bool = Query(True)):
    """Get performance insights and recommendations for a worker."""
    node_uuid = as_uuid(node_id, "node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            if actionable_only:
                cur.execute(
                    """
                    SELECT insight_id, task_type, insight_type, description,
                           recommendation, confidence_score, evidence_count, created_at
                    FROM performance_insights
                    WHERE node_id=%s AND actionable=TRUE
                    ORDER BY confidence_score DESC, created_at DESC
                    """,
                    (node_uuid,)
                )
            else:
                cur.execute(
                    """
                    SELECT insight_id, task_type, insight_type, description,
                           recommendation, confidence_score, evidence_count, created_at
                    FROM performance_insights
                    WHERE node_id=%s
                    ORDER BY confidence_score DESC, created_at DESC
                    """,
                    (node_uuid,)
                )
            
            insights = []
            for row in cur.fetchall():
                insight_id, task_type_val, insight_type, desc, rec, conf, evidence, created = row
                insights.append({
                    "insight_id": str(insight_id),
                    "task_type": task_type_val,
                    "insight_type": insight_type,
                    "description": desc,
                    "recommendation": dict(rec) if rec else {},
                    "confidence_score": float(conf) if conf else None,
                    "evidence_count": evidence,
                    "created_at": created.isoformat()
                })
    
    return {
        "insights": insights,
        "total": len(insights),
        "node_id": str(node_uuid),
        "actionable_only": actionable_only
    }

@router.post("/insights/{node_id}")
def create_insight(node_id: str, payload: dict):
    """Create a performance insight or recommendation."""
    node_uuid = as_uuid(node_id, "node_id")
    insight_id = uuid.uuid4()
    
    insight_type = payload.get("insight_type")
    description = payload.get("description")
    recommendation = payload.get("recommendation", {})
    confidence_score = payload.get("confidence_score", 0.7)
    task_type = payload.get("task_type")
    evidence_count = payload.get("evidence_count", 1)
    actionable = payload.get("actionable", True)
    
    if not insight_type:
        raise HTTPException(status_code=400, detail="insight_type required")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO performance_insights
                (insight_id, node_id, task_type, insight_type, description,
                 recommendation, confidence_score, evidence_count, actionable, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    insight_id, node_uuid, task_type, insight_type, description,
                    Jsonb(recommendation), confidence_score, evidence_count, actionable
                )
            )
        
        conn.commit()
    
    return {
        "status": "created",
        "insight_id": str(insight_id),
        "node_id": str(node_uuid),
        "insight_type": insight_type,
        "confidence_score": confidence_score
    }

@router.get("/knowledge")
def get_knowledge_artifacts(artifact_type: str | None = Query(None), task_type: str | None = Query(None), limit: int = Query(100, ge=1, le=1000)):
    """Get knowledge artifacts from successful tasks."""
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            query = "SELECT artifact_id, task_type, artifact_type, content, quality_score, usage_count, created_at FROM knowledge_artifacts WHERE 1=1"
            params = []
            
            if artifact_type:
                query += " AND artifact_type=%s"
                params.append(artifact_type)
            
            if task_type:
                query += " AND task_type=%s"
                params.append(task_type)
            
            query += " ORDER BY quality_score DESC, usage_count DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            
            artifacts = []
            for row in cur.fetchall():
                artifact_id, task_type_val, artifact_type_val, content, quality, usage, created = row
                artifacts.append({
                    "artifact_id": str(artifact_id),
                    "task_type": task_type_val,
                    "artifact_type": artifact_type_val,
                    "content": dict(content) if content else {},
                    "quality_score": float(quality) if quality else None,
                    "usage_count": usage,
                    "created_at": created.isoformat()
                })
    
    return {
        "artifacts": artifacts,
        "total": len(artifacts),
        "artifact_type_filter": artifact_type,
        "task_type_filter": task_type
    }

@router.post("/knowledge")
def store_knowledge_artifact(payload: dict):
    """Store a knowledge artifact from successful task outcomes."""
    artifact_id = uuid.uuid4()
    
    task_type = payload.get("task_type")
    artifact_type = payload.get("artifact_type")
    content = payload.get("content", {})
    quality_score = payload.get("quality_score", 0.8)
    node_id = payload.get("node_id")
    
    if not task_type or not artifact_type:
        raise HTTPException(status_code=400, detail="task_type and artifact_type required")
    
    node_uuid = as_uuid(node_id, "node_id") if node_id else None
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge_artifacts
                (artifact_id, task_type, node_id, artifact_type, content,
                 quality_score, usage_count, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, 0, now(), now())
                """,
                (
                    artifact_id, task_type, node_uuid, artifact_type,
                    Jsonb(content), quality_score
                )
            )
        
        conn.commit()
    
    return {
        "status": "stored",
        "artifact_id": str(artifact_id),
        "task_type": task_type,
        "artifact_type": artifact_type,
        "quality_score": quality_score
    }
