"""
SECTION 22: PRODUCTION HARDENING UTILITIES

Provides resilience patterns for mission-critical operations.

- Connection resilience
- Transaction safety
- Timeout protection
- Retry with backoff
- Failure isolation
- Audit durability
"""

import time
import logging
from functools import wraps
from typing import Callable, Any, Optional, TypeVar, ParamSpec
import psycopg
from psycopg import Error as PostgresError
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar('T')
P = ParamSpec('P')


# Connection resilience
class ConnectionPool:
    """Simple connection pool with health checking."""
    
    def __init__(self, db_url: str, min_size: int = 1, max_size: int = 5, timeout_seconds: int = 30):
        self.db_url = db_url
        self.max_size = max_size
        self.timeout_seconds = timeout_seconds
        self.connections = []
        self.in_use = set()
    
    def get_connection(self) -> psycopg.Connection:
        """Get a healthy connection from pool or create new."""
        # Try existing connections
        for conn in self.connections[:]:
            try:
                # Quick health check
                conn.execute("SELECT 1")
                self.in_use.add(id(conn))
                return conn
            except PostgresError:
                self.connections.remove(conn)
                try:
                    conn.close()
                except:
                    pass
        
        # Create new if under limit
        if len(self.connections) + len(self.in_use) < self.max_size:
            try:
                conn = psycopg.connect(self.db_url, connect_timeout=self.timeout_seconds)
                self.in_use.add(id(conn))
                return conn
            except PostgresError as e:
                logger.error(f"Connection pool exhausted and cannot create new: {e}")
                raise
        
        raise RuntimeError("Connection pool exhausted")
    
    def return_connection(self, conn: psycopg.Connection):
        """Return connection to pool."""
        self.in_use.discard(id(conn))
        if len(self.connections) < self.max_size:
            self.connections.append(conn)
        else:
            try:
                conn.close()
            except:
                pass
    
    def close_all(self):
        """Close all connections."""
        for conn in self.connections:
            try:
                conn.close()
            except:
                pass
        self.connections.clear()


# Transaction safety
def ensure_transaction_safety(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator: Ensure transaction rolls back on ANY exception.
    Prevents partial state corruption.
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        # Find connection in args/kwargs
        conn = None
        for arg in args:
            if isinstance(arg, psycopg.Connection):
                conn = arg
                break
        
        if not conn:
            conn = kwargs.get('conn') or kwargs.get('db_conn')
        
        if not conn:
            # No connection found, execute normally
            return func(*args, **kwargs)
        
        try:
            result = func(*args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            try:
                conn.rollback()
                logger.warning(f"Transaction rolled back due to {type(e).__name__}: {e}")
            except:
                logger.error("Failed to rollback transaction")
            raise
    
    return wrapper


# Timeout protection
def with_timeout(timeout_seconds: int = 30):
    """
    Decorator: Enforce operation timeout.
    Long-running DB/external calls must not block indefinitely.
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Find connection and set timeout
            for arg in args:
                if isinstance(arg, psycopg.Connection):
                    try:
                        arg.execute(f"SET statement_timeout TO {timeout_seconds * 1000}")
                    except:
                        pass  # Timeout setting is best-effort
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# Bounded retry with backoff
def with_bounded_retry(
    max_attempts: int = 3,
    base_delay_ms: int = 100,
    max_delay_ms: int = 5000,
    retryable_exceptions: tuple = (PostgresError,)
):
    """
    Decorator: Retry on transient failures with exponential backoff.
    Will NOT retry on:
    - Permanent failures (invalid query, auth, etc.)
    - Non-retryable exceptions
    - Governance denials (NEVER retry those)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            delay_ms = base_delay_ms
            last_error = None
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    attempt += 1
                    last_error = e
                    
                    # Check for non-retryable error codes
                    if hasattr(e, 'pgcode'):
                        # PostgreSQL error codes that should NOT be retried
                        no_retry_codes = {
                            '42P01',  # undefined table
                            '42703',  # undefined column
                            '23505',  # unique violation
                            '23503',  # foreign key violation
                        }
                        if e.pgcode in no_retry_codes:
                            raise
                    
                    if attempt >= max_attempts:
                        logger.error(f"Max retries ({max_attempts}) exceeded for {func.__name__}")
                        raise
                    
                    # Exponential backoff
                    delay_ms = min(delay_ms * 2, max_delay_ms)
                    logger.warning(f"Retry {attempt}/{max_attempts} after {delay_ms}ms: {e}")
                    time.sleep(delay_ms / 1000.0)
                
                except Exception as e:
                    # Non-retryable exception
                    logger.error(f"Non-retryable exception in {func.__name__}: {type(e).__name__}: {e}")
                    raise
            
            raise last_error
        
        return wrapper
    
    return decorator


# Failure isolation
class OperationContext:
    """Track operation for isolation and audit trail."""
    
    def __init__(self, operation_id: str, operation_type: str, actor_type: str, actor_ref: str):
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.actor_type = actor_type
        self.actor_ref = actor_ref
        self.start_time = datetime.utcnow()
        self.status = 'running'
        self.error = None
        self.result = None
    
    def succeed(self, result: Any):
        self.status = 'succeeded'
        self.result = result
    
    def fail(self, error: Exception):
        self.status = 'failed'
        self.error = str(error)
    
    def get_duration_ms(self) -> int:
        return int((datetime.utcnow() - self.start_time).total_seconds() * 1000)


def record_operation_audit(conn: psycopg.Connection, context: OperationContext):
    """Record operation outcome for audit trail."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO operation_audit_log (
                operation_id, operation_type, actor_type, actor_reference,
                status, error_message, duration_ms, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                context.operation_id,
                context.operation_type,
                context.actor_type,
                context.actor_ref,
                context.status,
                context.error,
                context.get_duration_ms()
            )
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record operation audit: {e}")
        # Continue anyway - audit failure should not crash operation


# Input validation
def validate_uuid(value: str) -> str:
    """Validate UUID format."""
    try:
        import uuid
        uuid.UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"Invalid UUID: {value}")


def validate_enum(value: str, allowed_values: list) -> str:
    """Validate enum value."""
    if value not in allowed_values:
        raise ValueError(f"Invalid value: {value}. Allowed: {allowed_values}")
    return value


# Health checks
def check_db_health(conn: psycopg.Connection) -> dict:
    """Check database health and readiness."""
    try:
        # Basic connectivity
        cur = conn.cursor()
        cur.execute("SELECT 1")
        
        # Check critical tables
        critical_tables = [
            'tasks',
            'governance_actors',
            'system_evaluation_runs'
        ]
        
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema='public' AND table_name = ANY(%s)
            """,
            (critical_tables,)
        )
        
        found_tables = cur.fetchone()[0]
        
        return {
            'status': 'healthy' if found_tables == len(critical_tables) else 'degraded',
            'connectivity': 'ok',
            'critical_tables_found': found_tables,
            'critical_tables_expected': len(critical_tables)
        }
    
    except Exception as e:
        return {
            'status': 'unhealthy',
            'connectivity': 'failed',
            'error': str(e)
        }


def check_governance_health(conn: psycopg.Connection) -> dict:
    """Check governance subsystem health."""
    try:
        cur = conn.cursor()
        
        # Check governance tables exist
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema='public' AND table_name LIKE 'governance_%'
            """
        )
        
        gov_tables = cur.fetchone()[0]
        
        # Check recent governance operations
        cur.execute(
            """
            SELECT COUNT(*) FROM governance_decisions
            WHERE created_at > NOW() - INTERVAL '1 hour'
            """
        )
        
        recent_decisions = cur.fetchone()[0]
        
        return {
            'status': 'operational' if gov_tables > 10 else 'degraded',
            'governance_tables': gov_tables,
            'recent_decisions_1h': recent_decisions
        }
    
    except Exception as e:
        return {
            'status': 'unavailable',
            'error': str(e)
        }
