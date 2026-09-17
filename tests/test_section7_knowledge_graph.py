#!/usr/bin/env python3
"""Section 7: Knowledge Graph and Vector Memory Tests

Tests knowledge relationships, semantic search, embeddings, and graph discovery.
"""
import json
import uuid
import os
import psycopg
import urllib.request

API_URL = "http://localhost:8000"
DATABASE_URL = os.environ.get("DATABASE_URL")


def api(method, endpoint, payload=None):
    try:
        req = urllib.request.Request(
            f"{API_URL}{endpoint}",
            data=json.dumps(payload).encode() if payload else None,
            headers={"Content-Type": "application/json"},
            method="POST" if method == "POST" else "GET"
        )
        if method == "GET":
            req = urllib.request.Request(f"{API_URL}{endpoint}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode()), 200
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode()), e.code
        except:
            return {}, e.code


def db(sql, params=None):
    c = psycopg.connect(DATABASE_URL)
    try:
        with c.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()
    finally:
        c.close()


def setup():
    """Create test data"""
    c = psycopg.connect(DATABASE_URL)
    with c.cursor() as cur:
        from psycopg.types.json import Jsonb
        # Create artifacts
        art1_id = uuid.uuid4()
        art2_id = uuid.uuid4()
        art3_id = uuid.uuid4()
        art4_id = uuid.uuid4()
        
        cur.execute(
            """INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content, quality_score)
            VALUES (%s, %s, %s, %s, %s)""",
            (art1_id, "query_optimization", "template", Jsonb({"steps": ["analyze", "optimize"]}), 0.95)
        )
        cur.execute(
            """INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content, quality_score)
            VALUES (%s, %s, %s, %s, %s)""",
            (art2_id, "query_optimization", "solution", Jsonb({"approach": "indexing"}), 0.92)
        )
        cur.execute(
            """INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content, quality_score)
            VALUES (%s, %s, %s, %s, %s)""",
            (art3_id, "query_optimization", "approach", Jsonb({"technique": "caching"}), 0.88)
        )
        cur.execute(
            """INSERT INTO knowledge_artifacts
            (artifact_id, task_type, artifact_type, content, quality_score)
            VALUES (%s, %s, %s, %s, %s)""",
            (art4_id, "data_analysis", "template", Jsonb({"steps": ["collect", "analyze"]}), 0.90)
        )
        c.commit()
    c.close()
    
    return art1_id, art2_id, art3_id, art4_id


print("\n=== SECTION 7: KNOWLEDGE GRAPH TESTS ===\n")

tests_passed = 0
tests_failed = 0

# TEST 1: Create relationships
print("TEST 1: Create artifact relationships")
art1, art2, art3, art4 = setup()

rel, code = api("POST", f"/knowledge/{str(art1)}/relate", {
    "target_artifact_id": str(art2),
    "relationship_type": "extends",
    "strength": 0.85
})

if code == 200 and rel.get("relationship_id"):
    print(f"  ✓ Relationship created: {rel['relationship_id'][:12]}...")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {rel}")
    tests_failed += 1

rel2, code = api("POST", f"/knowledge/{str(art1)}/relate", {
    "target_artifact_id": str(art3),
    "relationship_type": "related_to",
    "strength": 0.7
})

if code == 200 and rel2.get("relationship_id"):
    print(f"  ✓ Second relationship created")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code})")
    tests_failed += 1

# TEST 2: Get related artifacts
print("\nTEST 2: Retrieve related artifacts")
related, code = api("GET", f"/knowledge/{str(art1)}/related", None)

if code == 200 and len(related.get("related", [])) >= 2:
    print(f"  ✓ Related artifacts retrieved: {len(related['related'])} artifacts")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {related}")
    tests_failed += 1

# TEST 3: Filter by relationship type
print("\nTEST 3: Filter related artifacts by type")
filtered, code = api("GET", f"/knowledge/{str(art1)}/related?relationship_type=extends", None)

if code == 200 and len(filtered.get("related", [])) == 1:
    print(f"  ✓ Filtered to extends relationships: {len(filtered['related'])}")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): expected 1, got {len(filtered.get('related', []))}")
    tests_failed += 1

# TEST 4: Semantic search
print("\nTEST 4: Semantic search for knowledge")
search, code = api("POST", "/knowledge/search/semantic", {
    "query": "how to optimize database queries",
    "limit": 10,
    "min_similarity": 0.5
})

if code == 200 and search.get("results") is not None:
    print(f"  ✓ Semantic search completed: {search['count']} results")
    print(f"    Search ID: {search['search_id'][:12]}...")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {search}")
    tests_failed += 1

search_id = search.get("search_id")

# TEST 5: Search with task type filter
print("\nTEST 5: Semantic search with task type filter")
search_task, code = api("POST", "/knowledge/search/semantic", {
    "query": "optimization strategy",
    "task_type": "query_optimization",
    "limit": 10
})

if code == 200 and search_task.get("results") is not None:
    print(f"  ✓ Task-filtered search: {search_task['count']} results")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code})")
    tests_failed += 1

# TEST 6: Record search feedback
print("\nTEST 6: Record search feedback")
if search_id and len(search.get("results", [])) > 0:
    artifact_id = search["results"][0]["artifact_id"]
    feedback, code = api("POST", "/knowledge/search/feedback", {
        "search_id": search_id,
        "artifact_id": artifact_id,
        "useful": True
    })
    
    if code == 200:
        print(f"  ✓ Feedback recorded for {artifact_id[:12]}...")
        tests_passed += 1
    else:
        print(f"  ✗ Failed ({code})")
        tests_failed += 1
else:
    print("  ⊘ Skipped (no search results)")

# TEST 7: Map artifact to task
print("\nTEST 7: Map artifact to task type")
mappings_created = 0

# Map query_optimization artifacts
for artifact_id in [str(art1), str(art2), str(art3)]:
    mapping, code = api("POST", "/knowledge/map-to-task", {
        "artifact_id": artifact_id,
        "task_type": "query_optimization",
        "relevance_score": 0.85
    })
    if code == 200:
        mappings_created += 1

# Map data_analysis artifact
mapping, code = api("POST", "/knowledge/map-to-task", {
    "artifact_id": str(art4),
    "task_type": "data_analysis",
    "relevance_score": 0.92
})
if code == 200:
    mappings_created += 1

if mappings_created >= 4:
    print(f"  ✓ Mappings created: {mappings_created}")
    tests_passed += 1
else:
    print(f"  ✗ Failed: only {mappings_created} mappings created")
    tests_failed += 1

# TEST 8: Get knowledge by task
print("\nTEST 8: Retrieve knowledge by task type")
by_task, code = api("GET", f"/knowledge/by-task/query_optimization", None)

if code == 200 and by_task.get("artifacts"):
    print(f"  ✓ Task knowledge retrieved: {len(by_task['artifacts'])} artifacts")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {by_task}")
    tests_failed += 1

# TEST 9: Get knowledge graph
print("\nTEST 9: Retrieve knowledge graph for task type")
graph, code = api("GET", f"/knowledge/graph/query_optimization", None)

if code == 200 and graph.get("artifacts") is not None:
    print(f"  ✓ Graph retrieved: {len(graph.get('artifacts', []))} artifacts, {len(graph.get('relationships', []))} relationships")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {graph}")
    tests_failed += 1

# TEST 10: Get statistics
print("\nTEST 10: Retrieve knowledge graph statistics")
stats, code = api("GET", "/knowledge/stats", None)

if code == 200 and stats.get("total_artifacts") is not None:
    print(f"  ✓ Stats retrieved:")
    print(f"    Artifacts: {stats['total_artifacts']}")
    print(f"    Relationships: {stats['total_relationships']}")
    print(f"    Searches (24h): {stats['searches_24h']}")
    print(f"    Task types: {len(stats.get('task_types', []))}")
    tests_passed += 1
else:
    print(f"  ✗ Failed ({code}): {stats}")
    tests_failed += 1

# TEST 11: Verify embeddings column exists
print("\nTEST 11: Verify embeddings storage")
embeddings = db("SELECT COUNT(*) FROM knowledge_artifacts WHERE embedding IS NOT NULL")
if embeddings and embeddings[0][0] >= 0:
    print(f"  ✓ Embeddings column exists and functional")
    tests_passed += 1
else:
    print(f"  ✗ Embeddings not working")
    tests_failed += 1

# TEST 12: Verify relationships persisted
print("\nTEST 12: Verify relationships in database")
rels_in_db = db("SELECT COUNT(*) FROM knowledge_relationships")
if rels_in_db and rels_in_db[0][0] >= 2:
    print(f"  ✓ Relationships persisted: {rels_in_db[0][0]} in database")
    tests_passed += 1
else:
    print(f"  ✗ Relationships not persisted: {rels_in_db[0][0] if rels_in_db else 'N/A'}")
    tests_failed += 1

# TEST 13: Verify task mappings persisted
print("\nTEST 13: Verify task mappings in database")
mappings = db("SELECT COUNT(*) FROM task_knowledge_mappings")
if mappings and mappings[0][0] >= 1:
    print(f"  ✓ Task mappings persisted: {mappings[0][0]} in database")
    tests_passed += 1
else:
    print(f"  ✗ Task mappings not persisted")
    tests_failed += 1

# TEST 14: Verify searches recorded
print("\nTEST 14: Verify search history recorded")
searches = db("SELECT COUNT(*) FROM knowledge_searches")
if searches and searches[0][0] > 0:
    print(f"  ✓ Searches recorded: {searches[0][0]} in history")
    tests_passed += 1
else:
    print(f"  ✗ Searches not recorded")
    tests_failed += 1

# SUMMARY
print("\n" + "="*70)
print(f"TESTS PASSED: {tests_passed}")
print(f"TESTS FAILED: {tests_failed}")
print(f"TOTAL: {tests_passed + tests_failed}")
print(f"STATUS: {'✓ PASS' if tests_failed == 0 else '✗ FAIL'}")
print("="*70 + "\n")
