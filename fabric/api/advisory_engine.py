"""
advisory_engine.py - Push-Range Advisory Review Engine V0

Mechanical check runner for git push ranges. Generates advisory records
for observed codebase issues detected via static analysis and git diff
inspection.
"""
import os
import re
import subprocess
import json
import psycopg


def _get_conn():
    """Get a database connection, resolving container hostname for host access."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        db_url = re.sub(r"@[^:]+:", "@127.0.0.1:", db_url)
        return psycopg.connect(db_url)
    return psycopg.connect("dbname=learning_fabric user=fabric host=127.0.0.1")


def record_run(base_sha: str, head_sha: str, repo_path: str = None) -> str:
    """Record a push review run and return its UUID."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO push_review_run (base_sha, head_sha, repo_path) VALUES (%s, %s, %s) RETURNING id",
        (base_sha, head_sha, repo_path)
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return str(run_id)


def generate_advisories(run_id: str, base_sha: str, head_sha: str) -> list:
    """
    Run mechanical checks on the diff range and generate advisory records.
    Returns a list of advisory UUIDs.
    """
    conn = _get_conn()
    cur = conn.cursor()
    advisory_ids = []

    # Fetch all enabled mechanical check_specs
    cur.execute(
        "SELECT id, name FROM check_spec WHERE enabled = true AND check_type = 'mechanical'"
    )
    check_map = {name: cid for cid, name in cur.fetchall()}

    # 1. Migration endpoint check -- grep commit messages for 'migration'
    r = subprocess.run(
        ["git", "log", f"{base_sha}..{head_sha}", "--oneline", "--grep=migration"],
        capture_output=True, text=True, cwd="/opt/learning-fabric"
    )
    if r.stdout.strip() and "unauthenticated-migration-endpoint" in check_map:
        cur.execute(
            "INSERT INTO advisory (run_id, check_spec_id, reason, requested_action, severity) "
            "VALUES (%s, %s, %s, %s, 'warning') RETURNING id",
            (run_id, check_map["unauthenticated-migration-endpoint"],
             "Migration endpoint code change detected in push range",
             "Review unauthenticated migration endpoint for exposure to raw SQL execution")
        )
        advisory_ids.append(str(cur.fetchone()[0]))

    # 2. Docker-compose port change check
    r = subprocess.run(
        ["git", "diff", f"{base_sha}..{head_sha}", "--", "docker-compose.yml"],
        capture_output=True, text=True, cwd="/opt/learning-fabric"
    )
    if "8000" in r.stdout and "api-exposed-0000" in check_map:
        cur.execute(
            "INSERT INTO advisory (run_id, check_spec_id, reason, requested_action, severity) "
            "VALUES (%s, %s, %s, %s, 'advisory') RETURNING id",
            (run_id, check_map["api-exposed-0000"],
             "docker-compose.yml port or host binding changed in push range",
             "Verify port bindings are restricted to 127.0.0.1 on production")
        )
        advisory_ids.append(str(cur.fetchone()[0]))

    # 3. Dirty working tree check
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd="/opt/learning-fabric"
    )
    if r.stdout.strip() and "dirty-working-tree-bind-mount" in check_map:
        n = len(r.stdout.strip().split("\n"))
        cur.execute(
            "INSERT INTO advisory (run_id, check_spec_id, reason, requested_action, severity) "
            "VALUES (%s, %s, %s, %s, 'advisory') RETURNING id",
            (run_id, check_map["dirty-working-tree-bind-mount"],
             f"Working tree has {n} uncommitted changes",
             "Commit or stash dirty changes before push to keep bind-mount consistent")
        )
        advisory_ids.append(str(cur.fetchone()[0]))

    # Update run total
    cur.execute(
        "UPDATE push_review_run SET total_advisories = %s WHERE id = %s",
        (len(advisory_ids), run_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return advisory_ids


def record_observation(advisory_id: str, obs_type: str, detail: str) -> str:
    """Record an observation against an advisory."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO advisory_observation (advisory_id, observation_type, detail) VALUES (%s, %s, %s) RETURNING id",
        (advisory_id, obs_type, detail)
    )
    obs_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return str(obs_id)


def list_run(run_id: str) -> dict:
    """Return a summary of a push review run including advisories."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, base_sha, head_sha, repo_path, total_advisories, status, created_at "
        "FROM push_review_run WHERE id = %s", (run_id,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return {"error": "run not found"}
    run = {
        "id": str(row[0]),
        "base_sha": row[1],
        "head_sha": row[2],
        "repo_path": row[3],
        "total_advisories": row[4],
        "status": row[5],
        "created_at": row[6].isoformat() if row[6] else None,
    }
    cur.execute(
        "SELECT a.id, cs.name, a.reason, a.severity FROM advisory a "
        "JOIN check_spec cs ON a.check_spec_id = cs.id "
        "WHERE a.run_id = %s ORDER BY a.created_at", (run_id,)
    )
    run["advisories"] = [
        {"id": str(a[0]), "check_name": a[1], "reason": a[2], "severity": a[3]}
        for a in cur.fetchall()
    ]
    conn.commit()
    cur.close()
    conn.close()
    return run


if __name__ == "__main__":
    # Quick smoke test
    run_id = record_run("HEAD~1", "HEAD")
    print(f"Test run recorded: {run_id}")
    advs = generate_advisories(run_id, "HEAD~1", "HEAD")
    print(f"Advisories generated: {advs}")
    print(json.dumps(list_run(run_id), indent=2, default=str))