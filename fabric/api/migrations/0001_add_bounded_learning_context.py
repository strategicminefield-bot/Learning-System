"""
Migration: Add bounded learning context storage

Adds metadata column to assignments table for storing retrieved bounded learning context.
This enables passing task-relevant learning to executor nodes before execution.

Safe for:
- Existing production databases (ALTER TABLE ADD COLUMN is safe)
- Fresh deployments (column created as part of schema)
- Repeated migrations (IF NOT EXISTS prevents errors)

No data is lost or modified.
"""

def up(conn):
    """Add metadata and bounded_context columns."""
    with conn.cursor() as cur:
        # Add metadata column to assignments (stores bounded_learning_context, etc)
        cur.execute("""
            ALTER TABLE assignments ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;
        """)
        
        # Add bounded_context column to attempts (optional, for executor to read context)
        cur.execute("""
            ALTER TABLE attempts ADD COLUMN IF NOT EXISTS bounded_context jsonb DEFAULT '[]'::jsonb;
        """)
        
        conn.commit()
        print("✓ Added metadata column to assignments")
        print("✓ Added bounded_context column to attempts")

def down(conn):
    """Rollback: Remove added columns."""
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE assignments DROP COLUMN IF EXISTS metadata;
        """)
        
        cur.execute("""
            ALTER TABLE attempts DROP COLUMN IF EXISTS bounded_context;
        """)
        
        conn.commit()
        print("✓ Removed metadata column from assignments")
        print("✓ Removed bounded_context column from attempts")

# Version info
VERSION = "0001"
DESCRIPTION = "Add bounded learning context storage"
