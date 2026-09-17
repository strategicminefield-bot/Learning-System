"""Utility for applying migrations via API."""

from fastapi import APIRouter, HTTPException
import psycopg
import os

router = APIRouter(prefix='/api/v1/migrations', tags=['migrations'])
DATABASE_URL = os.environ['DATABASE_URL']


@router.post('/apply/{migration_number}')
def apply_migration(migration_number: int, sql_content: str):
    """Apply a migration by number and SQL content."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Execute migration
                cur.execute(sql_content)
            conn.commit()
        
        return {
            'success': True,
            'migration': migration_number,
            'status': 'applied'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'migration': migration_number
        }


@router.get('/status')
def migration_status():
    """Check current migration status."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Check what tables exist
                cur.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name LIKE 'governance_%'
                    """
                )
                governance_tables = cur.fetchone()[0]
                
                # Check total tables
                cur.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
                total_tables = cur.fetchone()[0]
        
        return {
            'governance_tables': governance_tables,
            'total_tables': total_tables,
            'migration_020_applied': governance_tables > 0
        }
    except Exception as e:
        return {'error': str(e)}
