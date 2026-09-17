"""
System Memory & Node Reconstitution Endpoints (Section 25)

Provides API for:
- Node bootstrap configuration
- System memory retrieval/storage
- Node reconstitution packages
- Procedural memory lookup
- Work state recovery
- Memory access logging

Purpose: Enable AI nodes to recover operational state after context loss
"""

import os
import uuid
import json
import psycopg
from datetime import datetime, timedelta, timezone
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/api/v1", tags=["system-memory"])
DATABASE_URL = os.environ["DATABASE_URL"]


# ============================================================
# PYDANTIC MODELS
# ============================================================

class SystemMemoryIn(BaseModel):
    memory_type: str
    scope: str
    scope_id: Optional[str] = None
    content: Dict[str, Any]
    authority_classification: str = "operational"
    confidence: float = 1.0
    linked_knowledge_id: Optional[str] = None

class ProcedureIn(BaseModel):
    procedure_type: str
    provider_type: str
    title: str
    description: Optional[str] = None
    procedure_steps: List[Dict[str, Any]]
    version: str
    applicable_roles: Optional[List[str]] = None

class WorkStateCheckpointIn(BaseModel):
    task_id: Optional[str] = None
    assignment_id: Optional[str] = None
    attempt_id: Optional[str] = None
    checkpoint_data: Dict[str, Any]
    checkpoint_stage: str


# ============================================================
# NODE RECONSTITUTION ENDPOINT
# ============================================================

@router.post("/nodes/{node_id}/reconstitute")
def reconstitute_node(
    node_id: str,
    reason: Optional[str] = Query("startup")
):
    """
    Assemble reconstitution package for a node.
    
    Called after node context loss or startup.
    Returns minimal bounded context necessary for node to resume operation.
    """
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify node exists
            cur.execute("SELECT node_id FROM nodes WHERE node_id = %s", (node_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="node not found")
            
            # Retrieve bootstrap config
            cur.execute("""
                SELECT fabric_url, adapter_type, adapter_version, auth_mechanism
                FROM node_bootstrap_config
                WHERE node_id = %s AND enabled = true
            """, (node_uuid,))
            bootstrap = cur.fetchone()
            
            if not bootstrap:
                raise HTTPException(status_code=404, detail="no bootstrap config")
            
            fabric_url, adapter_type, adapter_version, auth_mechanism = bootstrap
            
            # Retrieve current work state (if any)
            cur.execute("""
                SELECT assignment_id, task_id, attempt_id, checkpoint_data, checkpoint_stage
                FROM work_state_checkpoints
                WHERE node_id = %s AND expires_at > now()
                ORDER BY created_at DESC
                LIMIT 1
            """, (node_uuid,))
            work_state = cur.fetchone()
            
            # Retrieve node operational memory
            cur.execute("""
                SELECT memory_type, content, version
                FROM system_memory
                WHERE (scope_id = %s OR scope = 'system')
                  AND is_current = true
                  AND enabled = true
                  AND effective_from <= now()
                  AND (effective_until IS NULL OR effective_until > now())
                ORDER BY memory_type
            """, (node_uuid,))
            memories = cur.fetchall()
            
            # Retrieve applicable procedures
            cur.execute("""
                SELECT procedure_type, provider_type, title, procedure_steps, version
                FROM procedural_memory
                WHERE provider_type = %s
                  AND enabled = true
                  AND effective_from <= now()
                  AND (effective_until IS NULL OR effective_until > now())
                  AND (applicable_to_node_ids IS NULL OR %s = ANY(applicable_to_node_ids))
            """, (adapter_type, node_uuid))
            procedures = cur.fetchall()
            
            # Assemble reconstitution package
            package = {
                "node_id": str(node_uuid),
                "assembled_at": datetime.now(timezone.utc).isoformat(),
                "bootstrap": {
                    "fabric_url": fabric_url,
                    "adapter_type": adapter_type,
                    "adapter_version": adapter_version,
                    "auth_mechanism": auth_mechanism,
                },
                "current_work": None,
                "system_memory": [],
                "procedures": [],
            }
            
            # Add work state if present
            if work_state:
                assignment_id, task_id, attempt_id, checkpoint_data, checkpoint_stage = work_state
                package["current_work"] = {
                    "assignment_id": str(assignment_id) if assignment_id else None,
                    "task_id": str(task_id) if task_id else None,
                    "attempt_id": str(attempt_id) if attempt_id else None,
                    "stage": checkpoint_stage,
                    "data": checkpoint_data,
                }
            
            # Add system memory
            for memory_type, content, version in memories:
                package["system_memory"].append({
                    "type": memory_type,
                    "version": version,
                    "content": content,
                })
            
            # Add procedures
            for proc_type, provider, title, steps, version in procedures:
                package["procedures"].append({
                    "type": proc_type,
                    "title": title,
                    "version": version,
                    "steps": steps,
                })
            
            # Record access
            package_id = uuid.uuid4()
            cur.execute("""
                INSERT INTO node_reconstitution_packages
                (package_id, node_id, request_reason, package_content, memory_categories_included,
                 procedures_included, current_assignment_id, current_task_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                package_id, node_uuid, reason,
                Jsonb(package),
                [mem[0] for mem in memories],
                len(procedures),
                work_state[0] if work_state else None,
                work_state[1] if work_state else None,
            ))
            
            # Log memory access
            cur.execute("""
                INSERT INTO memory_access_log
                (node_id, access_type, reason, items_returned, context_bytes_returned, success)
                VALUES (%s, 'reconstitution_package', %s, %s, %s, true)
            """, (
                node_uuid, reason,
                len(memories) + len(procedures),
                len(json.dumps(package).encode()),
            ))
            
            conn.commit()
    
    return package


# ============================================================
# SYSTEM MEMORY ENDPOINTS
# ============================================================

@router.post("/system-memory")
def create_system_memory(memory: SystemMemoryIn):
    """Create a system memory record."""
    try:
        scope_id = uuid.UUID(memory.scope_id) if memory.scope_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid scope_id")
    
    memory_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO system_memory
                (memory_id, memory_type, scope, scope_id, content, authority_classification,
                 confidence, linked_knowledge_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING memory_id
            """, (
                memory_id, memory.memory_type, memory.scope, scope_id,
                Jsonb(memory.content), memory.authority_classification,
                memory.confidence, memory.linked_knowledge_id,
            ))
            result = cur.fetchone()
            conn.commit()
    
    return {"memory_id": str(result[0]), "created_at": datetime.now(timezone.utc).isoformat()}


@router.get("/system-memory/{memory_id}")
def get_system_memory(memory_id: str):
    """Retrieve a system memory record."""
    try:
        mid = uuid.UUID(memory_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid memory_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT memory_id, memory_type, scope, scope_id, content, version,
                       created_at, confidence, authority_classification, is_current
                FROM system_memory
                WHERE memory_id = %s
            """, (mid,))
            row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="memory not found")
    
    return {
        "memory_id": str(row[0]),
        "memory_type": row[1],
        "scope": row[2],
        "scope_id": str(row[3]) if row[3] else None,
        "content": row[4],
        "version": row[5],
        "created_at": row[6].isoformat(),
        "confidence": float(row[7]),
        "authority_classification": row[8],
        "is_current": row[9],
    }


@router.get("/system-memory")
def list_system_memory(
    memory_type: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    is_current_only: bool = Query(True),
    limit: int = Query(100)
):
    """List system memory records."""
    try:
        sid = uuid.UUID(scope_id) if scope_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid scope_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            query = "SELECT memory_id, memory_type, scope, scope_id, content, version, created_at FROM system_memory WHERE 1=1"
            params = []
            
            if memory_type:
                query += " AND memory_type = %s"
                params.append(memory_type)
            if scope:
                query += " AND scope = %s"
                params.append(scope)
            if sid:
                query += " AND scope_id = %s"
                params.append(sid)
            if is_current_only:
                query += " AND is_current = true"
            
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            rows = cur.fetchall()
    
    return [
        {
            "memory_id": str(row[0]),
            "memory_type": row[1],
            "scope": row[2],
            "scope_id": str(row[3]) if row[3] else None,
            "content": row[4],
            "version": row[5],
            "created_at": row[6].isoformat(),
        }
        for row in rows
    ]


# ============================================================
# PROCEDURAL MEMORY ENDPOINTS
# ============================================================

@router.post("/procedures")
def create_procedure(procedure: ProcedureIn):
    """Create a procedural memory record."""
    procedure_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO procedural_memory
                (procedure_id, procedure_type, provider_type, title, description,
                 procedure_steps, version, applicable_roles)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING procedure_id
            """, (
                procedure_id, procedure.procedure_type, procedure.provider_type,
                procedure.title, procedure.description,
                Jsonb(procedure.procedure_steps), procedure.version,
                procedure.applicable_roles,
            ))
            result = cur.fetchone()
            conn.commit()
    
    return {"procedure_id": str(result[0]), "created_at": datetime.now(timezone.utc).isoformat()}


@router.get("/procedures")
def list_procedures(
    procedure_type: Optional[str] = Query(None),
    provider_type: Optional[str] = Query(None),
    enabled_only: bool = Query(True),
    limit: int = Query(50)
):
    """List procedural memory records."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            query = "SELECT procedure_id, procedure_type, provider_type, title, version FROM procedural_memory WHERE 1=1"
            params = []
            
            if procedure_type:
                query += " AND procedure_type = %s"
                params.append(procedure_type)
            if provider_type:
                query += " AND provider_type = %s"
                params.append(provider_type)
            if enabled_only:
                query += " AND enabled = true AND effective_from <= now() AND (effective_until IS NULL OR effective_until > now())"
            
            query += " ORDER BY effective_from DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            rows = cur.fetchall()
    
    return [
        {
            "procedure_id": str(row[0]),
            "procedure_type": row[1],
            "provider_type": row[2],
            "title": row[3],
            "version": row[4],
        }
        for row in rows
    ]


# ============================================================
# WORK STATE RECOVERY
# ============================================================

@router.post("/nodes/{node_id}/work-checkpoint")
def save_work_checkpoint(node_id: str, checkpoint: WorkStateCheckpointIn):
    """Save current work state for recovery."""
    try:
        node_uuid = uuid.UUID(node_id)
        assignment_uuid = uuid.UUID(checkpoint.assignment_id) if checkpoint.assignment_id else None
        attempt_uuid = uuid.UUID(checkpoint.attempt_id) if checkpoint.attempt_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid uuid format")
    
    checkpoint_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO work_state_checkpoints
                (checkpoint_id, node_id, task_id, assignment_id, attempt_id,
                 checkpoint_data, checkpoint_stage, is_recoverable)
                VALUES (%s, %s, %s, %s, %s, %s, %s, true)
                RETURNING checkpoint_id
            """, (
                checkpoint_id, node_uuid, checkpoint.task_id,
                assignment_uuid, attempt_uuid,
                Jsonb(checkpoint.checkpoint_data), checkpoint.checkpoint_stage,
            ))
            result = cur.fetchone()
            conn.commit()
    
    return {"checkpoint_id": str(result[0])}


@router.get("/nodes/{node_id}/work-checkpoint")
def get_latest_work_checkpoint(node_id: str):
    """Get the latest work checkpoint for a node."""
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT checkpoint_id, task_id, assignment_id, attempt_id,
                       checkpoint_data, checkpoint_stage, created_at
                FROM work_state_checkpoints
                WHERE node_id = %s AND expires_at > now() AND is_recoverable = true
                ORDER BY created_at DESC
                LIMIT 1
            """, (node_uuid,))
            row = cur.fetchone()
    
    if not row:
        return None
    
    return {
        "checkpoint_id": str(row[0]),
        "task_id": row[1],
        "assignment_id": str(row[2]) if row[2] else None,
        "attempt_id": str(row[3]) if row[3] else None,
        "checkpoint_data": row[4],
        "checkpoint_stage": row[5],
        "created_at": row[6].isoformat(),
    }


# ============================================================
# BOOTSTRAP CONFIGURATION
# ============================================================

@router.post("/nodes/{node_id}/bootstrap")
def create_bootstrap_config(
    node_id: str,
    fabric_url: str,
    adapter_type: str,
    adapter_version: Optional[str] = None,
    identity_store_path: Optional[str] = None,
    auth_mechanism: str = "gateway_managed"
):
    """Register bootstrap configuration for a node."""
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid node_id")
    
    bootstrap_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Check if bootstrap already exists
            cur.execute("SELECT bootstrap_id FROM node_bootstrap_config WHERE node_id = %s", (node_uuid,))
            existing = cur.fetchone()
            
            if existing:
                raise HTTPException(status_code=409, detail="bootstrap config already exists")
            
            cur.execute("""
                INSERT INTO node_bootstrap_config
                (bootstrap_id, node_id, fabric_url, adapter_type, adapter_version,
                 identity_store_path, auth_mechanism)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING bootstrap_id
            """, (
                bootstrap_id, node_uuid, fabric_url, adapter_type, adapter_version,
                identity_store_path, auth_mechanism,
            ))
            result = cur.fetchone()
            conn.commit()
    
    return {"bootstrap_id": str(result[0])}


@router.get("/nodes/{node_id}/bootstrap")
def get_bootstrap_config(node_id: str):
    """Retrieve bootstrap configuration."""
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bootstrap_id, fabric_url, adapter_type, adapter_version,
                       identity_store_path, auth_mechanism
                FROM node_bootstrap_config
                WHERE node_id = %s AND enabled = true
            """, (node_uuid,))
            row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="bootstrap config not found")
    
    return {
        "bootstrap_id": str(row[0]),
        "fabric_url": row[1],
        "adapter_type": row[2],
        "adapter_version": row[3],
        "identity_store_path": row[4],
        "auth_mechanism": row[5],
    }


# ============================================================
# MEMORY ACCESS LOGGING (for observability)
# ============================================================

@router.get("/nodes/{node_id}/memory-access-log")
def get_memory_access_log(
    node_id: str,
    access_type: Optional[str] = Query(None),
    limit: int = Query(50)
):
    """Retrieve memory access log for a node."""
    try:
        node_uuid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid node_id")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            query = """
                SELECT log_id, access_type, reason, items_returned, context_bytes_returned,
                       success, requested_at, duration_ms
                FROM memory_access_log
                WHERE node_id = %s
            """
            params = [node_uuid]
            
            if access_type:
                query += " AND access_type = %s"
                params.append(access_type)
            
            query += " ORDER BY requested_at DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            rows = cur.fetchall()
    
    return [
        {
            "log_id": str(row[0]),
            "access_type": row[1],
            "reason": row[2],
            "items_returned": row[3],
            "context_bytes_returned": row[4],
            "success": row[5],
            "requested_at": row[6].isoformat(),
            "duration_ms": float(row[7]) if row[7] else None,
        }
        for row in rows
    ]
