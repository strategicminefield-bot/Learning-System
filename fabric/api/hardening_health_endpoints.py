"""
SECTION 22: HARDENING HEALTH & READINESS ENDPOINTS

Separate health (is process alive?) from readiness (can we accept work?).
"""

from fastapi import APIRouter, HTTPException
import psycopg
import os
import json
from datetime import datetime

from hardening_utilities import check_db_health, check_governance_health

router = APIRouter(prefix="/api/v1/health", tags=["health-v22"])

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://fabric@localhost/learning_fabric')


@router.get("/alive")
def health_alive():
    """
    Basic liveness probe: Is the API process alive?
    
    Returns immediately. Does NOT check dependencies.
    Used by container orchestration for process health.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "learning-fabric-api"
    }


@router.get("/ready")
def health_ready():
    """
    Readiness probe: Can we safely accept work?
    
    Checks critical dependencies:
    - PostgreSQL connectivity
    - Critical tables exist
    - Governance subsystem available
    
    Returns 200 only if ready. Returns 503 if not ready.
    """
    issues = []
    
    # Check database
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        db_health = check_db_health(conn)
        
        if db_health['status'] != 'healthy':
            issues.append(f"Database: {db_health}")
        
        conn.close()
    except Exception as e:
        issues.append(f"Database connection failed: {e}")
    
    # Check governance
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        gov_health = check_governance_health(conn)
        
        if gov_health['status'] != 'operational':
            issues.append(f"Governance: {gov_health}")
        
        conn.close()
    except Exception as e:
        issues.append(f"Governance check failed: {e}")
    
    # Determine readiness
    ready = len(issues) == 0
    
    response = {
        "ready": ready,
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "database": "ok" if not any("Database" in i for i in issues) else "failed",
            "governance": "ok" if not any("Governance" in i for i in issues) else "failed"
        },
        "issues": issues if issues else None
    }
    
    if not ready:
        raise HTTPException(status_code=503, detail=response)
    
    return response


@router.get("/status")
def health_status():
    """
    Comprehensive operational status.
    
    Returns detailed component status without failing.
    Used for monitoring/dashboards.
    """
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "components": {}
    }
    
    # Database status
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        db_health = check_db_health(conn)
        status["components"]["database"] = db_health
        conn.close()
    except Exception as e:
        status["components"]["database"] = {"status": "unreachable", "error": str(e)}
    
    # Governance status
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        gov_health = check_governance_health(conn)
        status["components"]["governance"] = gov_health
        conn.close()
    except Exception as e:
        status["components"]["governance"] = {"status": "unreachable", "error": str(e)}
    
    # Configuration status
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM production_config WHERE required_at_startup = true
        """)
        config_count = cur.fetchone()[0]
        status["components"]["configuration"] = {
            "status": "ok" if config_count > 0 else "missing",
            "required_configs_present": config_count
        }
        conn.close()
    except Exception as e:
        status["components"]["configuration"] = {"status": "check_failed", "error": str(e)}
    
    return status


@router.post("/record-deployment")
def record_deployment(
    deployment_type: str,
    new_version: str,
    previous_version: str = None,
    deployed_by: str = "unknown"
):
    """
    Record deployment event for troubleshooting.
    """
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO deployment_events (
                deployment_type, new_version, previous_version, deployed_by, status, started_at
            ) VALUES (%s, %s, %s, %s, 'in_progress', NOW())
            RETURNING event_id
            """,
            (deployment_type, new_version, previous_version, deployed_by)
        )
        
        event_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        
        return {
            "event_id": str(event_id),
            "status": "recorded",
            "deployment_type": deployment_type,
            "new_version": new_version
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/record-event")
def record_event(
    event_type: str,
    severity: str,
    component: str,
    message: str,
    correlation_id: str = None,
    context_data: dict = None
):
    """
    Record application event for structured logging.
    """
    try:
        conn = psycopg.connect(DATABASE_URL, timeout=5)
        cur = conn.cursor()
        
        cur.execute(
            """
            INSERT INTO application_event_log (
                event_type, severity, component, correlation_id, message, context_data
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING event_id
            """,
            (
                event_type,
                severity,
                component,
                correlation_id,
                message,
                json.dumps(context_data) if context_data else None
            )
        )
        
        event_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        
        return {
            "event_id": str(event_id),
            "status": "recorded"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
