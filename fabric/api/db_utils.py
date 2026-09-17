"""
Database utilities for Learning Fabric API.
"""

import os
import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db_connection():
    """Get a database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg.connect(DATABASE_URL)


__all__ = ["get_db_connection", "Jsonb"]
