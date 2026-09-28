#!/usr/bin/env python3
"""
Seed check_specs and incidents for Push-Range Advisory Review V0.
"""
import psycopg
import json

SEED_CHECKS = [
    {
        "name": "unauthenticated-migration-endpoint",
        "description": "Unauthenticated POST /api/v1/migrations/apply/{n} endpoint existed with live SQL execution",
        "severity": "warning",
        "check_type": "mechanical",
        "evidence_refs": {"commits": ["b80f3e9"], "files": ["fabric/api/migration_utility.py", "fabric/api/governance_endpoints.py"], "log_refs": ["LS-009", "SECURITY-2026-09-17"]},
        "impact": "Unauthenticated raw SQL execution endpoint exposed to network"
    },
    {
        "name": "api-exposed-0000",
        "description": "API port 8000 bound to 0.0.0.0 in committed docker-compose.yml (Sept 17-28) exposing API to network",
        "severity": "advisory",
        "check_type": "mechanical",
        "evidence_refs": {"commits": ["8035cb2"], "files": ["docker-compose.yml"], "log_refs": ["SECURITY-2026-09-28"]},
        "impact": "API reachable on all interfaces for ~11 days before lockdown to 127.0.0.1"
    },
    {
        "name": "dirty-working-tree-bind-mount",
        "description": "Dirty VPS working tree with bind mounts makes uncommitted changes live in production",
        "severity": "advisory",
        "check_type": "mechanical",
        "evidence_refs": {"commits": [], "files": ["docker-compose.yml"], "log_refs": ["OPS-2026-09-17-28"]},
        "impact": "Uncommitted or modified files on VPS are served by live API container"
    },
    {
        "name": "producer-quality-score-default",
        "description": "producer-supplied quality_score defaults to 0.5 when omitted, masking measurement quality",
        "severity": "advisory",
        "check_type": "static",
        "evidence_refs": {"commits": [], "files": ["fabric/api/knowledge_evolution.py", "fabric/api/feedback.py"], "log_refs": ["ARCH-2026-09-17"]},
        "impact": "Quality measurements indistinguishable from default values, reducing signal reliability"
    },
    {
        "name": "test-compileall-false-pass",
        "description": "test.sh compileall || true hides test failures, creating false-pass risk",
        "severity": "advisory",
        "check_type": "static",
        "evidence_refs": {"commits": [], "files": ["test.sh"], "log_refs": ["QA-2026-09-17"]},
        "impact": "CI pipeline can silently pass despite compilation or unit test failures"
    },
    {
        "name": "order-scope-subagent-drift",
        "description": "Order scope creep and subagent divergence from explicit instructions observed across LS orders",
        "severity": "info",
        "check_type": "process",
        "evidence_refs": {"commits": [], "files": [], "log_refs": ["LS-011", "LS-012", "LS-013"]},
        "impact": "Orders frequently overrun scope or subagents deviate, requiring supervision overhead"
    }
]

def seed():
    import os, re; db_url = re.sub(r"@[^:]+:", "@127.0.0.1:", os.environ["DATABASE_URL"]); conn = psycopg.connect(db_url)
    cur = conn.cursor()
    check_ids = {}
    for c in SEED_CHECKS:
        cur.execute("""
            INSERT INTO check_spec (name, version, description, check_type, severity, enabled)
            VALUES (%s, 1, %s, %s, %s, true)
            ON CONFLICT (name, version) DO UPDATE
                SET description = EXCLUDED.description,
                    check_type = EXCLUDED.check_type,
                    severity = EXCLUDED.severity
            RETURNING id
        """, (c["name"], c["description"], c["check_type"], c["severity"]))
        row = cur.fetchone()
        check_ids[c["name"]] = row[0]
        c_name = c["name"]
        c_severity = c["severity"]
        print(f"OBSERVED NOW: check_spec '{c_name}' id={row[0]} severity={c_severity}")

    for c in SEED_CHECKS:
        cur.execute("""
            INSERT INTO incident (summary, impact, affected_path_globs, evidence_refs, severity, status, check_spec_id, discovered_at)
            VALUES (%s, %s, %s, %s, %s, 'open', %s, now())
            RETURNING id
        """, (
            c["name"].replace("-", " ").title(),
            c["impact"],
            c["evidence_refs"].get("files", []),
            json.dumps(c["evidence_refs"]),
            c["severity"],
            check_ids[c["name"]]
        ))
        row = cur.fetchone()
        c_name = c["name"]
        c_ckid = check_ids[c["name"]]
        print(f"INFERRED: incident '{c_name}' id={row[0]} linked to check_spec {c_ckid}")

    conn.commit()
    cur.close()
    conn.close()
    print("READ FROM A RECORD: seed complete - 6 checks, 6 incidents")

if __name__ == "__main__":
    seed()
