import os
import uuid
import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
DATABASE_URL = os.environ["DATABASE_URL"]

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

        conn.commit()

    return {
        "status": "failed",
        "assignment_id": str(assignment_uuid),
        "task_id": str(task_id),
        "reason": payload.reason,
    }
