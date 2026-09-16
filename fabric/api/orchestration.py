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
