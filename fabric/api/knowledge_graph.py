"""Section 7: Knowledge Graph and Vector Memory Layer

Provides semantic search, knowledge relationship discovery, and embedding-based retrieval.
"""
import os
import json
import uuid
from typing import Optional
import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException

router = APIRouter()
DATABASE_URL = os.environ.get("DATABASE_URL")


def as_uuid(val, name):
    """Convert to UUID with error handling"""
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {name}: {val}")


def get_embedding(text: str) -> list:
    """Get embedding from text using OpenAI API (mocked for local testing)
    
    In production, integrate with OpenAI embeddings or local embedding model.
    """
    # For development: generate deterministic fake embedding based on text length
    # In production, call OpenAI or use sentence-transformers
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16)
    import random
    random.seed(seed)
    # Return smaller embedding (384 dims) for JSON storage efficiency
    return [random.uniform(-1, 1) for _ in range(384)]


@router.post("/knowledge/{artifact_id}/relate")
def create_relationship(artifact_id: str, payload: dict):
    """Create a relationship between knowledge artifacts
    
    POST /knowledge/{artifact_id}/relate
    
    Payload:
    {
        "target_artifact_id": "uuid",
        "relationship_type": "related_to|extends|contradicts|prerequisite",
        "strength": 0.75
    }
    """
    source_id = as_uuid(artifact_id, "artifact_id")
    target_id = as_uuid(payload.get("target_artifact_id"), "target_artifact_id")
    rel_type = payload.get("relationship_type", "related_to")
    strength = payload.get("strength", 0.5)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify both artifacts exist
            cur.execute("SELECT artifact_id FROM knowledge_artifacts WHERE artifact_id = %s", (source_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="source artifact not found")
            
            cur.execute("SELECT artifact_id FROM knowledge_artifacts WHERE artifact_id = %s", (target_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="target artifact not found")
            
            # Create relationship
            rel_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO knowledge_relationships
                (relationship_id, source_artifact_id, target_artifact_id, relationship_type, strength)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_artifact_id, target_artifact_id, relationship_type) DO UPDATE SET
                    strength = %s
                """,
                (rel_id, source_id, target_id, rel_type, strength, strength)
            )
            conn.commit()
    
    return {
        "relationship_id": str(rel_id),
        "source_artifact_id": str(source_id),
        "target_artifact_id": str(target_id),
        "relationship_type": rel_type,
        "strength": strength
    }


@router.get("/knowledge/{artifact_id}/related")
def get_related_artifacts(artifact_id: str, relationship_type: Optional[str] = None, limit: int = 10):
    """Get artifacts related to a given artifact
    
    GET /knowledge/{artifact_id}/related?relationship_type=extends&limit=10
    """
    artifact_uuid = as_uuid(artifact_id, "artifact_id")
    limit = min(limit, 100)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify artifact exists
            cur.execute("SELECT artifact_id FROM knowledge_artifacts WHERE artifact_id = %s", (artifact_uuid,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="artifact not found")
            
            # Get related artifacts
            if relationship_type:
                cur.execute(
                    """
                    SELECT kr.target_artifact_id, kr.relationship_type, kr.strength, ka.artifact_type, ka.content
                    FROM knowledge_relationships kr
                    JOIN knowledge_artifacts ka ON kr.target_artifact_id = ka.artifact_id
                    WHERE kr.source_artifact_id = %s AND kr.relationship_type = %s
                    ORDER BY kr.strength DESC
                    LIMIT %s
                    """,
                    (artifact_uuid, relationship_type, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT kr.target_artifact_id, kr.relationship_type, kr.strength, ka.artifact_type, ka.content
                    FROM knowledge_relationships kr
                    JOIN knowledge_artifacts ka ON kr.target_artifact_id = ka.artifact_id
                    WHERE kr.source_artifact_id = %s
                    ORDER BY kr.strength DESC
                    LIMIT %s
                    """,
                    (artifact_uuid, limit)
                )
            
            rows = cur.fetchall()
    
    return {
        "artifact_id": str(artifact_id),
        "related": [
            {
                "artifact_id": str(row[0]),
                "relationship_type": row[1],
                "strength": row[2],
                "artifact_type": row[3],
                "content": row[4]
            }
            for row in rows
        ],
        "count": len(rows)
    }


@router.post("/knowledge/search/semantic")
def semantic_search(payload: dict):
    """Search for knowledge artifacts using semantic similarity
    
    POST /knowledge/search/semantic
    
    Payload:
    {
        "query": "how to optimize database queries",
        "task_type": "database_optimization (optional)",
        "limit": 10,
        "min_similarity": 0.7,
        "node_id": "worker-uuid (optional)"
    }
    """
    query = payload.get("query", "")
    task_type = payload.get("task_type")
    limit = min(payload.get("limit", 10), 100)
    min_similarity = payload.get("min_similarity", 0.6)
    node_id_str = payload.get("node_id")
    
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    
    node_id = as_uuid(node_id_str, "node_id") if node_id_str else None
    
    # Get embedding for query
    query_embedding = get_embedding(query)
    search_id = uuid.uuid4()
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Record search
            cur.execute(
                """
                INSERT INTO knowledge_searches
                (search_id, node_id, query, query_embedding, query_type, task_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (search_id, node_id, query, query_embedding, "semantic", task_type)
            )
            
            # Semantic search - return top results by artifact quality (embeddings are JSONB for now)
            # In production with pgvector, this would use vector similarity
            if task_type:
                cur.execute(
                    """
                    SELECT ka.artifact_id, ka.artifact_type, ka.content, ka.quality_score,
                           ka.quality_score as similarity,
                           COALESCE(tkm.relevance_score, 0.5) as task_relevance
                    FROM knowledge_artifacts ka
                    LEFT JOIN artifact_embeddings ae ON ka.artifact_id = ae.artifact_id
                    LEFT JOIN task_knowledge_mappings tkm ON ka.artifact_id = tkm.artifact_id AND tkm.task_type = %s
                    WHERE ka.task_type IS NOT NULL
                    ORDER BY (ka.quality_score * COALESCE(tkm.relevance_score, 0.5)) DESC
                    LIMIT %s
                    """,
                    (task_type, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT ka.artifact_id, ka.artifact_type, ka.content, ka.quality_score,
                           ka.quality_score as similarity, 1.0
                    FROM knowledge_artifacts ka
                    LEFT JOIN artifact_embeddings ae ON ka.artifact_id = ae.artifact_id
                    ORDER BY ka.quality_score DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
            
            results = cur.fetchall()
            result_count = len(results)
            
            # Update search with result count
            cur.execute(
                "UPDATE knowledge_searches SET results_count = %s WHERE search_id = %s",
                (result_count, search_id)
            )
            conn.commit()
    
    return {
        "search_id": str(search_id),
        "query": query,
        "task_type": task_type,
        "results": [
            {
                "artifact_id": str(row[0]),
                "artifact_type": row[1],
                "content": row[2],
                "quality_score": row[3],
                "similarity": float(row[4]) if row[4] else 0.0,
                "task_relevance": float(row[5])
            }
            for row in results
        ],
        "count": result_count
    }


@router.get("/knowledge/graph/{task_type}")
def get_knowledge_graph(task_type: str):
    """Get knowledge graph for a task type
    
    GET /knowledge/graph/database_optimization
    
    Returns: All artifacts and relationships for task type
    """
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get artifacts for task type
            cur.execute(
                """
                SELECT ka.artifact_id, ka.artifact_type, ka.quality_score, ka.usage_count
                FROM knowledge_artifacts ka
                JOIN task_knowledge_mappings tkm ON ka.artifact_id = tkm.artifact_id
                WHERE tkm.task_type = %s
                ORDER BY tkm.relevance_score DESC
                """,
                (task_type,)
            )
            artifacts = cur.fetchall()
            
            # Get relationships between these artifacts
            artifact_ids = [row[0] for row in artifacts]
            if artifact_ids:
                placeholders = ",".join(["%s"] * len(artifact_ids))
                cur.execute(
                    f"""
                    SELECT source_artifact_id, target_artifact_id, relationship_type, strength
                    FROM knowledge_relationships
                    WHERE source_artifact_id IN ({placeholders}) OR target_artifact_id IN ({placeholders})
                    """,
                    artifact_ids + artifact_ids
                )
                relationships = cur.fetchall()
            else:
                relationships = []
            
            # Get graph stats
            cur.execute(
                """
                SELECT artifact_count, relationship_count, avg_connections_per_artifact
                FROM knowledge_graph_stats
                WHERE task_type = %s OR (task_type IS NULL AND %s IS NULL)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_type, task_type)
            )
            stats_row = cur.fetchone()
    
    return {
        "task_type": task_type,
        "artifacts": [
            {
                "artifact_id": str(row[0]),
                "artifact_type": row[1],
                "quality_score": row[2],
                "usage_count": row[3]
            }
            for row in artifacts
        ],
        "relationships": [
            {
                "source_artifact_id": str(row[0]),
                "target_artifact_id": str(row[1]),
                "relationship_type": row[2],
                "strength": row[3]
            }
            for row in relationships
        ],
        "stats": {
            "artifact_count": stats_row[0] if stats_row else len(artifacts),
            "relationship_count": stats_row[1] if stats_row else len(relationships),
            "avg_connections": stats_row[2] if stats_row else 0
        } if stats_row else {}
    }


@router.post("/knowledge/map-to-task")
def map_artifact_to_task(payload: dict):
    """Map a knowledge artifact to a task type for discovery
    
    POST /knowledge/map-to-task
    
    Payload:
    {
        "artifact_id": "uuid",
        "task_type": "database_optimization",
        "relevance_score": 0.85
    }
    """
    artifact_id = as_uuid(payload.get("artifact_id"), "artifact_id")
    task_type = payload.get("task_type", "")
    relevance = payload.get("relevance_score", 0.8)
    
    if not task_type:
        raise HTTPException(status_code=400, detail="task_type required")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Verify artifact exists
            cur.execute("SELECT artifact_id FROM knowledge_artifacts WHERE artifact_id = %s", (artifact_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="artifact not found")
            
            # Create mapping
            mapping_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO task_knowledge_mappings
                (mapping_id, task_type, artifact_id, relevance_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (task_type, artifact_id) DO UPDATE SET
                    relevance_score = %s
                """,
                (mapping_id, task_type, artifact_id, relevance, relevance)
            )
            conn.commit()
    
    return {
        "mapping_id": str(mapping_id),
        "artifact_id": str(artifact_id),
        "task_type": task_type,
        "relevance_score": relevance
    }


@router.get("/knowledge/by-task/{task_type}")
def get_knowledge_by_task(task_type: str, limit: int = 50):
    """Get all knowledge artifacts relevant to a task type
    
    GET /knowledge/by-task/database_optimization?limit=20
    """
    limit = min(limit, 1000)
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ka.artifact_id, ka.artifact_type, ka.content, ka.quality_score,
                       ka.usage_count, tkm.relevance_score, tkm.usage_in_task_count
                FROM knowledge_artifacts ka
                JOIN task_knowledge_mappings tkm ON ka.artifact_id = tkm.artifact_id
                WHERE tkm.task_type = %s
                ORDER BY tkm.relevance_score DESC, ka.usage_count DESC
                LIMIT %s
                """,
                (task_type, limit)
            )
            rows = cur.fetchall()
    
    return {
        "task_type": task_type,
        "artifacts": [
            {
                "artifact_id": str(row[0]),
                "artifact_type": row[1],
                "content": row[2],
                "quality_score": row[3],
                "global_usage_count": row[4],
                "task_relevance": row[5],
                "task_usage_count": row[6]
            }
            for row in rows
        ],
        "count": len(rows)
    }


@router.post("/knowledge/search/feedback")
def record_search_feedback(payload: dict):
    """Record whether a search result was useful
    
    POST /knowledge/search/feedback
    
    Payload:
    {
        "search_id": "uuid",
        "artifact_id": "uuid (optional)",
        "useful": true
    }
    """
    search_id = as_uuid(payload.get("search_id"), "search_id")
    artifact_id_str = payload.get("artifact_id")
    useful = payload.get("useful", False)
    
    artifact_id = as_uuid(artifact_id_str, "artifact_id") if artifact_id_str else None
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE knowledge_searches
                SET useful = %s, selected_artifact_id = %s
                WHERE search_id = %s
                """,
                (useful, artifact_id, search_id)
            )
            
            # Increment usage if artifact selected
            if artifact_id:
                cur.execute(
                    """
                    UPDATE knowledge_artifacts
                    SET usage_count = usage_count + 1
                    WHERE artifact_id = %s
                    """,
                    (artifact_id,)
                )
            
            conn.commit()
    
    return {
        "search_id": str(search_id),
        "artifact_id": str(artifact_id) if artifact_id else None,
        "useful": useful
    }


@router.get("/knowledge/stats")
def get_knowledge_stats():
    """Get overall knowledge graph statistics
    
    GET /knowledge/stats
    """
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Total artifacts
            cur.execute("SELECT COUNT(*) FROM knowledge_artifacts")
            total_artifacts = cur.fetchone()[0]
            
            # Total relationships
            cur.execute("SELECT COUNT(*) FROM knowledge_relationships")
            total_relationships = cur.fetchone()[0]
            
            # Total searches
            cur.execute("SELECT COUNT(*) FROM knowledge_searches")
            total_searches = cur.fetchone()[0]
            
            # Searches in last 24h
            cur.execute(
                "SELECT COUNT(*) FROM knowledge_searches WHERE created_at > now() - interval '24 hours'"
            )
            searches_24h = cur.fetchone()[0]
            
            # Most used artifact
            cur.execute(
                "SELECT artifact_id, artifact_type, usage_count FROM knowledge_artifacts ORDER BY usage_count DESC LIMIT 1"
            )
            most_used = cur.fetchone()
            
            # Task types in system
            cur.execute("SELECT DISTINCT task_type FROM task_knowledge_mappings ORDER BY task_type")
            task_types = [row[0] for row in cur.fetchall()]
            
            # Average connections per artifact
            cur.execute(
                """
                SELECT AVG(connection_count) FROM (
                    SELECT COUNT(*) as connection_count
                    FROM knowledge_relationships
                    GROUP BY source_artifact_id
                ) t
                """
            )
            avg_connections = cur.fetchone()[0] or 0
    
    return {
        "total_artifacts": total_artifacts,
        "total_relationships": total_relationships,
        "total_searches": total_searches,
        "searches_24h": searches_24h,
        "task_types": task_types,
        "avg_connections_per_artifact": float(avg_connections),
        "most_used_artifact": {
            "artifact_id": str(most_used[0]),
            "artifact_type": most_used[1],
            "usage_count": most_used[2]
        } if most_used else None
    }
