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
